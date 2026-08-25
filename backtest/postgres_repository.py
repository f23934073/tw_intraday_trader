"""Optional PostgreSQL adapter used by platform deployments."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Any, Mapping
from uuid import uuid4

from backtest.comparability import (
    comparability_contract_digest,
    run_comparability_diff,
    verify_run_identity,
)
from backtest.dataset_binding import (
    AtomicBacktestBindingChanged,
    AtomicBacktestBindingUnavailable,
    DatasetBindingIdempotencyConflict,
    DatasetBindingIntegrityError,
    DatasetBindingRevisionConflict,
    DatasetRegistrationConflict,
    activation_request,
    canonical_registration_manifest,
    require_text,
)
from backtest.migrations import apply_migrations
from backtest.domain import BacktestRunConfig, RunStatus, digest
from backtest.qualification import (
    experiment_family_definition,
    experiment_family_id,
    research_baseline_identity_digest,
    verify_experiment_family_snapshot,
    verify_qualification_record,
)
from backtest.repository import (
    BacktestIdempotencyConflict,
    _JsonBacktestRepository,
    _chunked_result_root,
    _decode_json,
    _json,
    _rebuild_chunked_result,
)
from backtest.research_control import (
    CONTROL_CONTRACT_VERSION,
    CashAdmissionControlConflict,
    CashAdmissionControlIntegrityError,
    build_cash_admission_postflight,
    cash_admission_identity_validation_digest,
    recompute_backtest_result_digest,
    verify_cash_admission_postflight,
    verify_cash_admission_preflight,
    verify_research_control_snapshot,
)


class PostgresBacktestRepository(_JsonBacktestRepository):
    def __init__(
        self,
        connection: Any | None = None,
        *,
        pool: Any | None = None,
        owns_pool: bool = False,
    ) -> None:
        if (connection is None) == (pool is None):
            raise ValueError("exactly one of connection or pool is required")
        self._pool = pool
        self._owns_pool = owns_pool
        migration_connection = connection
        if pool is not None:
            with pool.connection() as checked_out:
                apply_migrations(checked_out)
                self._set_search_path(checked_out)
        else:
            assert migration_connection is not None
            apply_migrations(migration_connection)
            self._set_search_path(migration_connection)
        super().__init__(
            connection,
            placeholder="%s",
            json_type="JSONB",
            blob_type="BYTEA",
            apply_schema=False,
        )

    @property
    def connection_pool(self) -> Any | None:
        return self._pool

    def register_immutable_dataset(
        self,
        manifest: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Insert one canonical READY Dataset or replay the exact existing row."""

        canonical = canonical_registration_manifest(manifest)
        dataset_id = str(canonical["dataset_id"])
        lock_key = self._advisory_lock_key("backtest-dataset:register", dataset_id)
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                "SELECT * FROM backtest_datasets WHERE dataset_id = %s FOR UPDATE",
                (dataset_id,),
            )
            raw = cursor.fetchone()
            if raw is not None:
                row = self._row(cursor, raw)
                existing_manifest = _decode_json(row["manifest_json"])
                if row["status"] != "READY" or existing_manifest != canonical:
                    raise DatasetRegistrationConflict(
                        f"immutable Dataset identity conflict: {dataset_id}"
                    )
                return self._dataset_payload(row), True
            cursor.execute(
                """
                INSERT INTO backtest_datasets (
                    dataset_id, status, manifest_json, created_at, updated_at
                ) VALUES (%s, 'READY', %s::jsonb, %s, CURRENT_TIMESTAMP::text)
                RETURNING *
                """,
                (dataset_id, _json(canonical), canonical["created_at"]),
            )
            return self._dataset_payload(self._row(cursor, cursor.fetchone())), False

    def get_dataset_binding(self, binding_name: str) -> dict[str, Any] | None:
        binding_name = require_text(binding_name, "binding name")
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT binding.*, dataset.status AS dataset_status,
                       dataset.manifest_json AS dataset_manifest_json
                FROM backtest_dataset_bindings AS binding
                JOIN backtest_datasets AS dataset
                  ON dataset.dataset_id = binding.dataset_id
                WHERE binding.binding_name = %s
                """,
                (binding_name,),
            )
            raw = cursor.fetchone()
            if raw is None:
                return None
            return self._verified_binding_payload(self._row(cursor, raw))

    def create_atomic_run_from_binding(
        self,
        record: Mapping[str, Any],
        *,
        binding_name: str,
        expected_binding_revision: int,
        expected_dataset_digest: str,
        request_digest: str,
    ) -> tuple[dict[str, Any], bool]:
        """Insert a standalone Atomic Run under one locked binding head."""

        binding_name = require_text(binding_name, "binding name")
        idempotency_key = require_text(
            str(record["idempotency_key"]), "idempotency key"
        )
        if expected_binding_revision < 1:
            raise ValueError("expected binding revision must be positive")
        if digest(dict(record["config"]).get("atomic_run_request")) != request_digest:
            raise ValueError("atomic Run request digest does not match config evidence")
        if dict(record["config"]).get("atomic_run_request_digest") != request_digest:
            raise ValueError("atomic Run request digest is not preserved in config")
        lock_key = self._advisory_lock_key(
            "backtest-run:create:atomic", idempotency_key
        )
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                "SELECT * FROM backtest_runs WHERE idempotency_key = %s FOR UPDATE",
                (idempotency_key,),
            )
            raw_existing = cursor.fetchone()
            if raw_existing is not None:
                existing = self._run_payload(self._row(cursor, raw_existing))
                verify_run_identity(existing)
                if (
                    existing["config"].get("atomic_run_request_digest")
                    != request_digest
                ):
                    raise BacktestIdempotencyConflict(
                        "相同 idempotency key 的 Atomic Run request 不同"
                    )
                return existing, True

            cursor.execute(
                """
                SELECT binding.*, dataset.status AS dataset_status,
                       dataset.manifest_json AS dataset_manifest_json
                FROM backtest_dataset_bindings AS binding
                JOIN backtest_datasets AS dataset
                  ON dataset.dataset_id = binding.dataset_id
                WHERE binding.binding_name = %s
                FOR UPDATE OF binding
                """,
                (binding_name,),
            )
            raw_binding = cursor.fetchone()
            if raw_binding is None:
                raise AtomicBacktestBindingUnavailable(
                    f"Dataset binding 不存在：{binding_name}"
                )
            binding = self._verified_binding_payload(
                self._row(cursor, raw_binding)
            )
            if (
                binding["revision"] != expected_binding_revision
                or binding["dataset_digest"] != expected_dataset_digest
            ):
                raise AtomicBacktestBindingChanged(
                    "ATOMIC_BACKTEST_DEFAULT 已變更，請重新整理後再確認"
                )
            if (
                binding["dataset_id"] != record["dataset_id"]
                or binding["dataset_digest"] != record["dataset_digest"]
            ):
                raise DatasetBindingIntegrityError(
                    "Atomic Run record 與 locked Dataset binding 不一致"
                )

            cursor.execute(
                """
                INSERT INTO backtest_runs (
                    run_id, idempotency_key, status, config_json, config_digest,
                    dataset_id, dataset_digest, progress, progress_message,
                    created_at, updated_at, error_message, result_digest
                ) VALUES (
                    %s, %s, %s, %s::jsonb, %s, %s, %s, 0.0,
                    '已建立回測工作', %s, %s, NULL, NULL
                )
                RETURNING *
                """,
                (
                    record["run_id"],
                    idempotency_key,
                    record["status"],
                    _json(record["config"]),
                    record["config_digest"],
                    record["dataset_id"],
                    record["dataset_digest"],
                    record["created_at"],
                    record["created_at"],
                ),
            )
            created = self._run_payload(self._row(cursor, cursor.fetchone()))
            self._after_run_created(cursor, created)
            return created, False

    def create_cash_admission_control(
        self,
        record: Mapping[str, Any],
        *,
        request: Mapping[str, Any],
        request_digest: str,
        preflight: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Seal the sole R5 control and its Run in one PostgreSQL transaction."""

        request_body = dict(request)
        required_request_fields = {
            "request_schema_version",
            "control_contract_version",
            "preflight_digest",
            "expected_registration_revision",
            "idempotency_key",
            "actor_id",
            "change_note",
        }
        if set(request_body) != required_request_fields:
            raise ValueError("R5 control request schema 不合法")
        if digest(request_body) != request_digest:
            raise CashAdmissionControlIntegrityError("R5 request digest 不一致")
        verified_preflight = verify_cash_admission_preflight(preflight)
        baseline_run_id = str(verified_preflight["identity"]["baseline_run_id"])
        contract_version = str(request_body["control_contract_version"])
        if contract_version != CONTROL_CONTRACT_VERSION:
            raise ValueError("R5 control contract version 不支援")
        if request_body["preflight_digest"] != verified_preflight["artifact_digest"]:
            raise CashAdmissionControlIntegrityError("R5 request 與 preflight 不一致")
        if str(request_body["idempotency_key"]) != str(record["idempotency_key"]):
            raise CashAdmissionControlIntegrityError("R5 operation key 與 Run 不一致")
        lock_key = self._advisory_lock_key(
            "backtest-r5-control:create",
            f"{baseline_run_id}\0{contract_version}",
        )
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                """
                SELECT request_digest, result_json, result_digest
                FROM backtest_cash_admission_control_operations
                WHERE baseline_run_id = %s AND contract_version = %s
                  AND idempotency_key = %s
                """,
                (
                    baseline_run_id,
                    contract_version,
                    request_body["idempotency_key"],
                ),
            )
            replay = cursor.fetchone()
            if replay is not None:
                replay_row = self._row(cursor, replay)
                if str(replay_row["request_digest"]) != request_digest:
                    raise CashAdmissionControlConflict(
                        "相同 R5 idempotency key 的 request 不同"
                    )
                replay_result = _decode_json(replay_row["result_json"])
                if digest(replay_result) != str(replay_row["result_digest"]):
                    raise CashAdmissionControlIntegrityError(
                        "R5 operation replay result digest 不一致"
                    )
                return self._control_run_payload(cursor, replay_result), True

            cursor.execute(
                """
                SELECT * FROM backtest_cash_admission_control_heads
                WHERE baseline_run_id = %s AND contract_version = %s
                FOR UPDATE
                """,
                (baseline_run_id, contract_version),
            )
            raw_head = cursor.fetchone()
            if raw_head is not None:
                cursor.execute(
                    """
                    SELECT * FROM backtest_cash_admission_control_registrations
                    WHERE baseline_run_id = %s AND contract_version = %s
                      AND revision = %s
                    """,
                    (
                        baseline_run_id,
                        contract_version,
                        int(self._row(cursor, raw_head)["current_revision"]),
                    ),
                )
                registration = self._verified_control_registration(
                    self._row(cursor, cursor.fetchone())
                )
                if registration["preflight_digest"] != verified_preflight["artifact_digest"]:
                    raise CashAdmissionControlConflict(
                        "R5_CONTROL_ALREADY_SEALED: authoritative preflight 不同"
                    )
                result = self._control_operation_result(registration)
                self._insert_control_operation(
                    cursor,
                    request=request_body,
                    request_digest=request_digest,
                    result=result,
                )
                return self._control_run_payload(cursor, result), True

            if int(request_body["expected_registration_revision"]) != 0:
                raise CashAdmissionControlConflict(
                    "R5_CONTROL_REVISION_CONFLICT: initial expected revision must be 0"
                )
            cursor.execute(
                "SELECT * FROM backtest_runs WHERE run_id = %s FOR SHARE",
                (baseline_run_id,),
            )
            raw_baseline = cursor.fetchone()
            if raw_baseline is None:
                raise KeyError(f"找不到 R5 baseline Run：{baseline_run_id}")
            baseline = self._run_payload(self._row(cursor, raw_baseline))
            self._verify_control_preflight_identity(
                cursor,
                baseline=baseline,
                preflight=verified_preflight,
            )
            if baseline["status"] != RunStatus.COMPLETED.value:
                raise ValueError("R5 baseline 必須是 COMPLETED")

            config = BacktestRunConfig.from_dict(dict(record["config"]))
            self._verify_control_config(
                baseline=baseline,
                control_config=config,
                preflight=verified_preflight,
            )
            if config.config_digest != str(record["config_digest"]):
                raise CashAdmissionControlIntegrityError("R5 control config digest 不一致")
            if (
                record["status"] != RunStatus.QUEUED.value
                or record["dataset_id"] != config.dataset_id
                or record["dataset_digest"] != config.dataset_digest
            ):
                raise CashAdmissionControlIntegrityError(
                    "R5 Run row proposal 與 immutable config 不一致"
                )

            cursor.execute(
                """
                INSERT INTO backtest_runs (
                    run_id, idempotency_key, status, config_json, config_digest,
                    dataset_id, dataset_digest, progress, progress_message,
                    created_at, updated_at, error_message, result_digest
                ) VALUES (
                    %s, %s, %s, %s::jsonb, %s, %s, %s, 0.0,
                    '已建立 R5 cash-admission control', %s, %s, NULL, NULL
                )
                RETURNING *
                """,
                (
                    record["run_id"],
                    record["idempotency_key"],
                    record["status"],
                    _json(config.to_dict()),
                    record["config_digest"],
                    record["dataset_id"],
                    record["dataset_digest"],
                    record["created_at"],
                    record["created_at"],
                ),
            )
            created_run = self._run_payload(self._row(cursor, cursor.fetchone()))
            snapshot = verify_research_control_snapshot(
                dict(config.research_control_snapshot or {})
            )
            sizing = dict(verified_preflight["sizing"])
            cursor.execute(
                """
                INSERT INTO backtest_cash_admission_control_heads (
                    baseline_run_id, contract_version, current_revision, status
                ) VALUES (%s, %s, 1, 'RUN_CREATED')
                """,
                (baseline_run_id, contract_version),
            )
            cursor.execute(
                """
                INSERT INTO backtest_cash_admission_control_registrations (
                    baseline_run_id, contract_version, revision, control_run_id,
                    preflight_digest, preflight_json, sizing_digest, sizing_json,
                    research_control_snapshot_digest,
                    research_control_snapshot_json, status, actor_id, change_note
                ) VALUES (
                    %s, %s, 1, %s, %s, %s::jsonb, %s, %s::jsonb,
                    %s, %s::jsonb, 'RUN_CREATED', %s, %s
                )
                """,
                (
                    baseline_run_id,
                    contract_version,
                    created_run["run_id"],
                    verified_preflight["artifact_digest"],
                    _json(verified_preflight),
                    digest(sizing),
                    _json(sizing),
                    snapshot["snapshot_digest"],
                    _json(snapshot),
                    request_body["actor_id"],
                    request_body["change_note"],
                ),
            )
            registration = {
                "baseline_run_id": baseline_run_id,
                "contract_version": contract_version,
                "revision": 1,
                "control_run_id": created_run["run_id"],
                "preflight_digest": verified_preflight["artifact_digest"],
                "status": "RUN_CREATED",
                "research_control_snapshot_digest": snapshot["snapshot_digest"],
                "postflight_digest": None,
            }
            result = self._control_operation_result(registration)
            self._insert_control_operation(
                cursor,
                request=request_body,
                request_digest=request_digest,
                result=result,
            )
            return {**created_run, "cash_admission_control": registration}, False

    def get_cash_admission_control(self, run_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM backtest_cash_admission_control_registrations
                WHERE control_run_id = %s
                """,
                (run_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"Run 不是 R5 cash-admission control：{run_id}")
            return self._verified_control_registration(self._row(cursor, raw))

    def finalize_cash_admission_control(
        self,
        run_id: str,
        *,
        result: Mapping[str, Any],
        postflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Atomically publish accepted performance or diagnostics-only invalidity."""

        supplied_postflight = verify_cash_admission_postflight(postflight)
        summary = dict(result["summary"])
        root, chunk_manifests = _chunked_result_root(result)
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT * FROM backtest_runs WHERE run_id = %s FOR UPDATE",
                (run_id,),
            )
            raw_control = cursor.fetchone()
            if raw_control is None:
                raise KeyError(f"找不到 R5 control Run：{run_id}")
            control = self._run_payload(self._row(cursor, raw_control))
            verify_run_identity(control)
            cursor.execute(
                """
                SELECT * FROM backtest_cash_admission_control_registrations
                WHERE control_run_id = %s FOR UPDATE
                """,
                (run_id,),
            )
            raw_registration = cursor.fetchone()
            if raw_registration is None:
                raise CashAdmissionControlIntegrityError("R5 control registration 遺失")
            registration = self._verified_control_registration(
                self._row(cursor, raw_registration)
            )
            if registration["status"] in {"ACCEPTED", "INVALID"}:
                if registration["postflight_digest"] != supplied_postflight["postflight_digest"]:
                    raise CashAdmissionControlConflict("R5 postflight 已封存且 evidence 不同")
                return registration
            if control["status"] != RunStatus.RUNNING.value:
                raise CashAdmissionControlIntegrityError(
                    f"R5 control 必須由 RUNNING 進入 postflight：{control['status']}"
                )
            control_config = BacktestRunConfig.from_dict(control["config"])
            snapshot = verify_research_control_snapshot(
                dict(control_config.research_control_snapshot or {})
            )
            verified_preflight = verify_cash_admission_preflight(snapshot["preflight"])
            cursor.execute(
                "SELECT * FROM backtest_runs WHERE run_id = %s FOR SHARE",
                (registration["baseline_run_id"],),
            )
            baseline = self._run_payload(self._row(cursor, cursor.fetchone()))
            if baseline["status"] != RunStatus.COMPLETED.value:
                raise CashAdmissionControlIntegrityError(
                    "R5 baseline 已不再是 COMPLETED"
                )
            baseline_result = self._verify_control_preflight_identity(
                cursor,
                baseline=baseline,
                preflight=verified_preflight,
            )
            self._verify_control_config(
                baseline=baseline,
                control_config=control_config,
                preflight=verified_preflight,
            )
            result_digest = str(summary.get("result_digest") or "")
            if recompute_backtest_result_digest(result) != result_digest:
                raise CashAdmissionControlIntegrityError(
                    "R5 control immutable result digest 無法重建"
                )
            identity_validation_digest = self._control_identity_validation_digest(
                baseline=baseline,
                control=control,
                preflight=verified_preflight,
            )
            expected_postflight = build_cash_admission_postflight(
                baseline_orders=baseline_result.get("orders", ()),
                control_result=result,
                preflight=verified_preflight,
                control_run_id=run_id,
                control_config_digest=control["config_digest"],
                control_result_digest=result_digest,
                identity_validation_digest=identity_validation_digest,
            )
            if expected_postflight != supplied_postflight:
                raise CashAdmissionControlIntegrityError(
                    "R5 postflight 無法由 locked result projection 重建"
                )
            accepted = expected_postflight["verdict"] == "ACCEPTED"
            terminal_status = (
                RunStatus.COMPLETED.value
                if accepted
                else RunStatus.INVALID_CASH_ADMISSION_CONTROL.value
            )
            cursor.execute(
                """
                UPDATE backtest_runs
                SET status = %s, progress = 1.0, progress_message = %s,
                    result_digest = %s, updated_at = CURRENT_TIMESTAMP::text
                WHERE run_id = %s AND status = %s
                """,
                (
                    RunStatus.CONTROL_POSTFLIGHT.value,
                    "正在驗證 R5 server postflight",
                    None,
                    run_id,
                    RunStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise CashAdmissionControlConflict("R5 control status transition conflict")
            if accepted:
                self._save_result_with_cursor(
                    cursor,
                    run_id=run_id,
                    result=result,
                    summary=summary,
                    root=root,
                    chunk_manifests=chunk_manifests,
                    allow_research_control=True,
                )
            cursor.execute(
                """
                UPDATE backtest_cash_admission_control_registrations
                SET status = %s, postflight_digest = %s,
                    postflight_json = %s::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE control_run_id = %s AND status = 'RUN_CREATED'
                """,
                (
                    "ACCEPTED" if accepted else "INVALID",
                    expected_postflight["postflight_digest"],
                    _json(expected_postflight),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise CashAdmissionControlConflict("R5 registration finalize conflict")
            cursor.execute(
                """
                UPDATE backtest_cash_admission_control_heads
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE baseline_run_id = %s AND contract_version = %s
                  AND current_revision = %s
                """,
                (
                    "ACCEPTED" if accepted else "INVALID",
                    registration["baseline_run_id"],
                    registration["contract_version"],
                    registration["revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise CashAdmissionControlConflict("R5 head finalize conflict")
            cursor.execute(
                """
                UPDATE backtest_runs
                SET status = %s, progress = 1.0, progress_message = %s,
                    result_digest = %s, updated_at = CURRENT_TIMESTAMP::text
                WHERE run_id = %s AND status = %s
                """,
                (
                    terminal_status,
                    (
                        "R5 cash-admission control postflight 通過"
                        if accepted
                        else "R5 cash-admission control postflight 未通過"
                    ),
                    result_digest if accepted else None,
                    run_id,
                    RunStatus.CONTROL_POSTFLIGHT.value,
                ),
            )
            if cursor.rowcount != 1:
                raise CashAdmissionControlConflict("R5 terminal status conflict")
            return {
                **registration,
                "status": "ACCEPTED" if accepted else "INVALID",
                "postflight_digest": expected_postflight["postflight_digest"],
                "postflight": expected_postflight,
            }

    def activate_dataset_binding(
        self,
        *,
        binding_name: str,
        dataset_id: str,
        dataset_digest: str,
        plan_identity_digest: str,
        expected_revision: int,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        """Apply one serialized binding mutation with durable response replay."""

        request = activation_request(
            binding_name=binding_name,
            dataset_id=dataset_id,
            dataset_digest=dataset_digest,
            plan_identity_digest=plan_identity_digest,
            expected_revision=expected_revision,
            actor_id=actor_id,
            change_note=change_note,
        )
        idempotency_key = require_text(idempotency_key, "idempotency key")
        request_digest = digest(request)
        lock_key = self._advisory_lock_key(
            "backtest-dataset-binding:activate",
            str(request["binding_name"]),
        )
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                """
                SELECT request_digest, result_json, result_digest
                FROM backtest_dataset_binding_operations
                WHERE binding_name = %s AND idempotency_key = %s
                """,
                (request["binding_name"], idempotency_key),
            )
            replay = cursor.fetchone()
            if replay is not None:
                replay_row = self._row(cursor, replay)
                if str(replay_row["request_digest"]) != request_digest:
                    raise DatasetBindingIdempotencyConflict(
                        "Dataset binding idempotency key request conflict"
                    )
                result = _decode_json(replay_row["result_json"])
                if digest(result) != str(replay_row["result_digest"]):
                    raise DatasetBindingIntegrityError(
                        "Dataset binding operation result digest conflict"
                    )
                return result, True

            cursor.execute(
                """
                SELECT * FROM backtest_dataset_bindings
                WHERE binding_name = %s
                FOR UPDATE
                """,
                (request["binding_name"],),
            )
            raw_head = cursor.fetchone()
            head = self._row(cursor, raw_head) if raw_head is not None else None
            current_revision = int(head["revision"]) if head is not None else 0
            if int(request["expected_revision"]) != current_revision:
                raise DatasetBindingRevisionConflict(
                    "DATASET_BINDING_REVISION_CONFLICT: "
                    f"expected {request['expected_revision']}, current {current_revision}"
                )

            cursor.execute(
                "SELECT * FROM backtest_datasets WHERE dataset_id = %s FOR SHARE",
                (request["dataset_id"],),
            )
            raw_dataset = cursor.fetchone()
            if raw_dataset is None:
                raise KeyError(f"Dataset is not registered: {request['dataset_id']}")
            dataset_row = self._row(cursor, raw_dataset)
            if dataset_row["status"] != "READY":
                raise DatasetBindingIntegrityError("bound Dataset is not READY")
            stored_manifest = self._verified_registered_manifest(
                dataset_row["manifest_json"]
            )
            if (
                stored_manifest["manifest_digest"] != request["dataset_digest"]
                or stored_manifest.get("plan_identity_digest")
                != request["plan_identity_digest"]
            ):
                raise DatasetBindingIntegrityError(
                    "bound Dataset manifest identity conflict"
                )

            same_target = head is not None and (
                head["dataset_id"] == request["dataset_id"]
                and head["dataset_digest"] == request["dataset_digest"]
                and head["plan_identity_digest"]
                == request["plan_identity_digest"]
            )
            if same_target:
                result_kind = "NOOP_ALREADY_BOUND"
                result_revision = current_revision
            else:
                result_kind = "BOUND"
                result_revision = current_revision + 1
                if head is None:
                    cursor.execute(
                        """
                        INSERT INTO backtest_dataset_bindings (
                            binding_name, dataset_id, dataset_digest,
                            plan_identity_digest, revision, actor_id, change_note
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request["binding_name"],
                            request["dataset_id"],
                            request["dataset_digest"],
                            request["plan_identity_digest"],
                            result_revision,
                            request["actor_id"],
                            request["change_note"],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE backtest_dataset_bindings
                        SET dataset_id = %s, dataset_digest = %s,
                            plan_identity_digest = %s, revision = %s,
                            actor_id = %s, change_note = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE binding_name = %s AND revision = %s
                        """,
                        (
                            request["dataset_id"],
                            request["dataset_digest"],
                            request["plan_identity_digest"],
                            result_revision,
                            request["actor_id"],
                            request["change_note"],
                            request["binding_name"],
                            current_revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise DatasetBindingRevisionConflict(
                            "Dataset binding head changed during activation"
                        )
                cursor.execute(
                    """
                    INSERT INTO backtest_dataset_binding_revisions (
                        binding_name, revision, dataset_id, dataset_digest,
                        plan_identity_digest, previous_dataset_id,
                        previous_dataset_digest, actor_id, change_note,
                        idempotency_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request["binding_name"],
                        result_revision,
                        request["dataset_id"],
                        request["dataset_digest"],
                        request["plan_identity_digest"],
                        head["dataset_id"] if head is not None else None,
                        head["dataset_digest"] if head is not None else None,
                        request["actor_id"],
                        request["change_note"],
                        idempotency_key,
                    ),
                )

            result = {
                "binding_name": request["binding_name"],
                "dataset_digest": request["dataset_digest"],
                "dataset_id": request["dataset_id"],
                "outcome": result_kind,
                "plan_identity_digest": request["plan_identity_digest"],
                "request_digest": request_digest,
                "revision": result_revision,
            }
            result_digest = digest(result)
            cursor.execute(
                """
                INSERT INTO backtest_dataset_binding_operations (
                    binding_name, idempotency_key, request_digest,
                    expected_revision, target_dataset_id, target_dataset_digest,
                    target_plan_identity_digest, actor_id, change_note,
                    result_kind, result_revision, result_json, result_digest
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s
                )
                """,
                (
                    request["binding_name"],
                    idempotency_key,
                    request_digest,
                    request["expected_revision"],
                    request["dataset_id"],
                    request["dataset_digest"],
                    request["plan_identity_digest"],
                    request["actor_id"],
                    request["change_note"],
                    result_kind,
                    result_revision,
                    _json(result),
                    result_digest,
                ),
            )
            return result, False

    def cancel_atomic_run(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        actor_id: str,
        request_digest: str,
    ) -> tuple[dict[str, Any], bool]:
        scope = f"backtest-run:cancel:{run_id}"
        lock_digest = hashlib.sha256(f"{scope}\0{idempotency_key}".encode("utf-8")).digest()
        lock_key = int.from_bytes(lock_digest[:8], byteorder="big", signed=True)
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                """
                SELECT request_digest, result_json
                FROM strategy_mutation_operations
                WHERE operation_scope = %s AND idempotency_key = %s
                """,
                (scope, idempotency_key),
            )
            replay = cursor.fetchone()
            if replay is not None:
                replay_row = self._row(cursor, replay)
                if str(replay_row["request_digest"]) != request_digest:
                    raise BacktestIdempotencyConflict(
                        "相同 idempotency key 的 atomic cancel 內容不同"
                    )
                result = _decode_json(replay_row["result_json"])
                saved_run = result.get("run")
                if not isinstance(saved_run, dict):
                    raise RuntimeError("atomic cancel operation result 損壞")
                return saved_run, True

            cursor.execute("SELECT * FROM backtest_runs WHERE run_id = %s FOR UPDATE", (run_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到回測工作：{run_id}")
            current = self._run_payload(self._row(cursor, raw))
            if current["config"].get("atomic_strategy_run_snapshot") is None:
                raise ValueError("cancel_atomic_run 只接受 atomic Run")
            if current["status"] not in {"QUEUED", "PREFLIGHT", "RUNNING"}:
                raise ValueError("只有尚未完成的回測可以取消")
            cursor.execute(
                """
                UPDATE backtest_runs
                SET status = 'CANCELLING',
                    progress_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %s
                RETURNING *
                """,
                ("正在取消，會在下一個安全事件邊界停止", run_id),
            )
            updated = self._run_payload(self._row(cursor, cursor.fetchone()))
            saved_run = dict(updated)
            for timestamp_field in ("created_at", "updated_at"):
                value = saved_run.get(timestamp_field)
                if hasattr(value, "isoformat"):
                    saved_run[timestamp_field] = value.isoformat()
            before_run = dict(current)
            for timestamp_field in ("created_at", "updated_at"):
                value = before_run.get(timestamp_field)
                if hasattr(value, "isoformat"):
                    before_run[timestamp_field] = value.isoformat()
            result = {"run": saved_run}
            cursor.execute(
                """
                INSERT INTO strategy_mutation_operations (
                    operation_scope, idempotency_key, request_digest, result_json,
                    result_digest, actor_id
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    scope,
                    idempotency_key,
                    request_digest,
                    _json(result),
                    hashlib.sha256(_json(result).encode("utf-8")).hexdigest(),
                    actor_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO strategy_audit_events (
                    audit_event_id, action, resource_type, resource_id, actor_id,
                    before_digest, after_digest, change_note, operation_scope,
                    idempotency_key, outcome, request_digest, details_json
                ) VALUES (%s, 'ATOMIC_BACKTEST_RUN_CANCEL', 'BACKTEST_RUN', %s, %s,
                          %s, %s, '', %s, %s, 'SUCCESS', %s, '{}'::jsonb)
                """,
                (
                    str(uuid4()),
                    run_id,
                    actor_id,
                    hashlib.sha256(_json(before_run).encode("utf-8")).hexdigest(),
                    hashlib.sha256(_json(saved_run).encode("utf-8")).hexdigest(),
                    scope,
                    idempotency_key,
                    request_digest,
                ),
            )
            return updated, False

    def _after_run_created(self, cursor: Any, run: dict[str, Any]) -> None:
        """Append a Challenger attempt atomically with its durable Run."""

        config = run["config"]
        family_id = config.get("experiment_id")
        baseline_run_id = config.get("baseline_run_id")
        stored_research_baseline_digest = config.get("research_baseline_digest")
        if family_id is None and baseline_run_id is None:
            return
        if not str(family_id or "").startswith("experiment-family-"):
            return
        if not family_id or not baseline_run_id or not stored_research_baseline_digest:
            raise ValueError(
                "Experiment Run 必須同時包含 family、Baseline 與 research identity"
            )
        verify_run_identity(run)
        cursor.execute(
            "SELECT * FROM backtest_runs WHERE run_id = %s FOR UPDATE",
            (baseline_run_id,),
        )
        raw_baseline = cursor.fetchone()
        if raw_baseline is None:
            raise KeyError(f"找不到 Experiment Baseline Run：{baseline_run_id}")
        baseline = self._run_payload(self._row(cursor, raw_baseline))
        verify_run_identity(baseline)
        if baseline["status"] != "COMPLETED":
            raise ValueError("Experiment Baseline 必須先完成")
        actual_research_baseline_digest = research_baseline_identity_digest(
            baseline["config"]
        )
        if str(stored_research_baseline_digest) != actual_research_baseline_digest:
            raise ValueError("Experiment research Baseline identity 已漂移")
        if family_id != experiment_family_id(actual_research_baseline_digest):
            raise ValueError("Experiment family identity 不是 server-derived value")
        config_diff = run_comparability_diff(baseline["config"], config)
        if config_diff:
            fields = "、".join(item["field"] for item in config_diff)
            raise ValueError(f"Challenger 與 Baseline 不可比較：{fields}")
        proposed_definition = experiment_family_definition(
            canonical_baseline_run_id=str(baseline_run_id),
            research_baseline_digest=actual_research_baseline_digest,
            comparability_digest=comparability_contract_digest(baseline["config"]),
        )
        cursor.execute(
            """
            INSERT INTO backtest_experiment_families (
                family_id, baseline_run_id, contract_version, planned_attempts,
                alpha, adjustment_method, policy_json, policy_digest,
                comparability_digest, definition_digest, head_sequence,
                research_baseline_digest, research_protocol_identity_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, 0,
                %s, %s::jsonb
            )
            ON CONFLICT (research_baseline_digest) DO NOTHING
            """,
            (
                proposed_definition["family_id"],
                proposed_definition["baseline_run_id"],
                proposed_definition["contract_version"],
                proposed_definition["planned_attempts"],
                proposed_definition["alpha"],
                proposed_definition["adjustment_method"],
                _json(proposed_definition["policy"]),
                proposed_definition["policy_digest"],
                proposed_definition["comparability_digest"],
                proposed_definition["definition_digest"],
                proposed_definition["research_baseline_digest"],
                _json(proposed_definition["research_protocol_identity"]),
            ),
        )
        cursor.execute(
            """
            SELECT * FROM backtest_experiment_families
            WHERE research_baseline_digest = %s
            FOR UPDATE
            """,
            (actual_research_baseline_digest,),
        )
        family = self._row(cursor, cursor.fetchone())
        canonical_baseline_run_id = str(family["baseline_run_id"])
        if canonical_baseline_run_id == str(baseline_run_id):
            canonical_baseline = baseline
        else:
            cursor.execute(
                "SELECT * FROM backtest_runs WHERE run_id = %s FOR UPDATE",
                (canonical_baseline_run_id,),
            )
            raw_canonical_baseline = cursor.fetchone()
            if raw_canonical_baseline is None:
                raise ValueError("Experiment canonical Baseline 已遺失")
            canonical_baseline = self._run_payload(
                self._row(cursor, raw_canonical_baseline)
            )
            verify_run_identity(canonical_baseline)
            if canonical_baseline["status"] != "COMPLETED":
                raise ValueError("Experiment canonical Baseline 必須維持完成")
            if (
                research_baseline_identity_digest(canonical_baseline["config"])
                != actual_research_baseline_digest
            ):
                raise ValueError("Experiment canonical Baseline identity 已漂移")
        definition = experiment_family_definition(
            canonical_baseline_run_id=canonical_baseline_run_id,
            research_baseline_digest=actual_research_baseline_digest,
            comparability_digest=comparability_contract_digest(
                canonical_baseline["config"]
            ),
        )
        for field_name in (
            "family_id",
            "baseline_run_id",
            "research_baseline_digest",
            "contract_version",
            "planned_attempts",
            "adjustment_method",
            "policy_digest",
            "comparability_digest",
            "definition_digest",
        ):
            if str(family[field_name]) != str(definition[field_name]):
                raise ValueError(f"Experiment family {field_name} 已漂移")
        if str(family["alpha"]) != definition["alpha"]:
            raise ValueError("Experiment family alpha 已漂移")
        if _decode_json(family["policy_json"]) != definition["policy"]:
            raise ValueError("Experiment family policy 已漂移")
        if (
            _decode_json(family["research_protocol_identity_json"])
            != definition["research_protocol_identity"]
        ):
            raise ValueError("Experiment family research protocol identity 已漂移")
        canonical_diff = run_comparability_diff(
            canonical_baseline["config"], config
        )
        if canonical_diff:
            fields = "、".join(item["field"] for item in canonical_diff)
            raise ValueError(f"Challenger 與 canonical Baseline 不可比較：{fields}")
        next_sequence = int(family["head_sequence"]) + 1
        if next_sequence > int(family["planned_attempts"]):
            raise ValueError("Experiment family 已達 server-owned attempt ceiling")
        cursor.execute(
            """
            INSERT INTO backtest_experiment_attempts (
                family_id, attempt_sequence, run_id
            ) VALUES (%s, %s, %s)
            """,
            (family_id, next_sequence, run["run_id"]),
        )
        cursor.execute(
            """
            UPDATE backtest_experiment_families
            SET head_sequence = %s
            WHERE family_id = %s
            """,
            (next_sequence, family_id),
        )

    def create_qualification(
        self,
        record: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Persist immutable research evidence with same-key replay semantics."""

        idempotency_key = str(record["idempotency_key"])
        lock_digest = hashlib.sha256(
            f"backtest-qualification:create\0{idempotency_key}".encode("utf-8")
        ).digest()
        lock_key = int.from_bytes(lock_digest[:8], byteorder="big", signed=True)
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cursor.execute(
                """
                SELECT *
                FROM backtest_qualifications
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                payload = self._qualification_payload(self._row(cursor, existing))
                if payload["request_digest"] != record["request_digest"]:
                    raise BacktestIdempotencyConflict(
                        "相同 idempotency key 的 qualification request 不同"
                    )
                return payload, True
            cursor.execute(
                """
                SELECT * FROM backtest_experiment_families
                WHERE family_id = %s
                FOR UPDATE
                """,
                (record["family_id"],),
            )
            raw_family = cursor.fetchone()
            if raw_family is None:
                raise KeyError(f"找不到 Experiment family：{record['family_id']}")
            family_snapshot = self._experiment_family_payload(
                cursor,
                self._row(cursor, raw_family),
            )
            if (
                family_snapshot["head_sequence"] != record["family_head_sequence"]
                or family_snapshot["family_snapshot_digest"]
                != record["family_snapshot_digest"]
            ):
                raise BacktestIdempotencyConflict(
                    "Experiment family history 已變更，請重新建立資格證據"
                )
            if family_snapshot != record.get("family_snapshot"):
                raise BacktestIdempotencyConflict(
                    "Experiment family snapshot body 已變更，請重新建立資格證據"
                )
            cursor.execute(
                """
                SELECT attempt_sequence, hypothesis_id, qualification_id
                FROM backtest_experiment_attempts
                WHERE family_id = %s AND run_id = %s
                FOR UPDATE
                """,
                (record["family_id"], record["challenger_run_id"]),
            )
            raw_attempt = cursor.fetchone()
            if raw_attempt is None:
                raise ValueError("Challenger 不在 authoritative family history")
            attempt = self._row(cursor, raw_attempt)
            if int(attempt["attempt_sequence"]) != int(record["attempt_number"]):
                raise ValueError("Challenger attempt sequence 與 family history 不一致")
            if attempt.get("qualification_id") is not None:
                raise ValueError("此 Challenger 已建立資格證據")
            cursor.execute(
                """
                INSERT INTO backtest_qualifications (
                    qualification_id, idempotency_key, request_digest, request_json,
                    baseline_run_id, challenger_run_id, protocol_digest, protocol_json,
                    evidence_digest, evidence_json, verdict, actor_id, change_note, created_at,
                    family_id, attempt_number, family_head_sequence,
                    family_snapshot_digest, family_snapshot_json
                ) VALUES (
                    %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb,
                    %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb
                )
                RETURNING *
                """,
                (
                    record["qualification_id"],
                    idempotency_key,
                    record["request_digest"],
                    _json(record["request"]),
                    record["baseline_run_id"],
                    record["challenger_run_id"],
                    record["protocol_digest"],
                    _json(record["protocol"]),
                    record["evidence_digest"],
                    _json(record["evidence"]),
                    record["verdict"],
                    record["actor_id"],
                    record["change_note"],
                    record["created_at"],
                    record["family_id"],
                    record["attempt_number"],
                    record["family_head_sequence"],
                    record["family_snapshot_digest"],
                    _json(record["family_snapshot"]),
                ),
            )
            qualification = self._qualification_payload(
                self._row(cursor, cursor.fetchone())
            )
            cursor.execute(
                """
                UPDATE backtest_experiment_attempts
                SET hypothesis_id = %s,
                    qualification_id = %s,
                    qualified_at = CURRENT_TIMESTAMP
                WHERE family_id = %s AND attempt_sequence = %s
                """,
                (
                    record["hypothesis_id"],
                    record["qualification_id"],
                    record["family_id"],
                    record["attempt_number"],
                ),
            )
            return qualification, False

    def replay_qualification(
        self,
        *,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        """Optional fast replay that does not depend on mutable Run/Dataset rows."""

        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM backtest_qualifications WHERE idempotency_key = %s",
                (idempotency_key,),
            )
            raw = cursor.fetchone()
            if raw is None:
                return None
            payload = self._qualification_payload(self._row(cursor, raw))
            if payload["request_digest"] != request_digest:
                raise BacktestIdempotencyConflict(
                    "相同 idempotency key 的 qualification request 不同"
                )
            return payload

    def get_qualification(self, qualification_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM backtest_qualifications WHERE qualification_id = %s",
                (qualification_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到回測 qualification：{qualification_id}")
            payload = self._qualification_payload(self._row(cursor, raw))
            if payload.get("family_id") is not None:
                cursor.execute(
                    "SELECT * FROM backtest_experiment_families WHERE family_id = %s",
                    (payload["family_id"],),
                )
                raw_family = cursor.fetchone()
                if raw_family is None:
                    raise ValueError("Qualification current family 已遺失")
                payload["current_family_snapshot"] = self._experiment_family_payload(
                    cursor,
                    self._row(cursor, raw_family),
                )
            return payload

    def list_qualifications(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 250:
            raise ValueError("qualification list limit 必須介於 1 與 250")
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM backtest_qualifications ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [
                self._qualification_payload(self._row(cursor, raw))
                for raw in cursor.fetchall()
            ]

    def get_experiment_family_for_run(self, run_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT family.*
                FROM backtest_experiment_families AS family
                JOIN backtest_experiment_attempts AS attempt
                  ON attempt.family_id = family.family_id
                WHERE attempt.run_id = %s
                """,
                (run_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"Run 尚未登錄 Experiment family：{run_id}")
            return self._experiment_family_payload(cursor, self._row(cursor, raw))

    def _experiment_family_payload(
        self,
        cursor: Any,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        cursor.execute(
            """
            SELECT attempt_sequence, run_id, hypothesis_id, qualification_id,
                   registered_at, qualified_at
            FROM backtest_experiment_attempts
            WHERE family_id = %s
            ORDER BY attempt_sequence
            """,
            (row["family_id"],),
        )
        attempts = []
        for raw_attempt in cursor.fetchall():
            attempt = self._row(cursor, raw_attempt)
            attempts.append(
                {
                    "attempt_sequence": int(attempt["attempt_sequence"]),
                    "run_id": attempt["run_id"],
                    "hypothesis_id": attempt.get("hypothesis_id"),
                    "qualification_id": attempt.get("qualification_id"),
                    "registered_at": attempt["registered_at"].isoformat(),
                    "qualified_at": (
                        attempt["qualified_at"].isoformat()
                        if attempt.get("qualified_at") is not None
                        else None
                    ),
                }
            )
        created_at = row["created_at"]
        payload: dict[str, Any] = {
            "contract_version": row["contract_version"],
            "family_id": row["family_id"],
            "baseline_run_id": row["baseline_run_id"],
            "research_baseline_digest": row["research_baseline_digest"],
            "research_protocol_identity": _decode_json(
                row["research_protocol_identity_json"]
            ),
            "planned_attempts": int(row["planned_attempts"]),
            "alpha": str(row["alpha"]),
            "adjustment_method": row["adjustment_method"],
            "policy": _decode_json(row["policy_json"]),
            "policy_digest": row["policy_digest"],
            "comparability_digest": row["comparability_digest"],
            "definition_digest": row["definition_digest"],
            "head_sequence": int(row["head_sequence"]),
            "attempts": attempts,
            "created_at": (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at)
            ),
        }
        payload["family_snapshot_digest"] = digest(payload)
        return verify_experiment_family_snapshot(payload)

    @staticmethod
    def _qualification_payload(row: dict[str, Any]) -> dict[str, Any]:
        created_at = row["created_at"]
        payload = {
            "qualification_id": row["qualification_id"],
            "idempotency_key": row["idempotency_key"],
            "request_digest": row["request_digest"],
            "request": _decode_json(row["request_json"]),
            "baseline_run_id": row["baseline_run_id"],
            "challenger_run_id": row["challenger_run_id"],
            "protocol_digest": row["protocol_digest"],
            "protocol": _decode_json(row["protocol_json"]),
            "evidence_digest": row["evidence_digest"],
            "evidence": _decode_json(row["evidence_json"]),
            "verdict": row["verdict"],
            "actor_id": row["actor_id"],
            "change_note": row["change_note"],
            "family_id": row.get("family_id"),
            "attempt_number": (
                int(row["attempt_number"])
                if row.get("attempt_number") is not None
                else None
            ),
            "family_head_sequence": (
                int(row["family_head_sequence"])
                if row.get("family_head_sequence") is not None
                else None
            ),
            "family_snapshot_digest": row.get("family_snapshot_digest"),
            "family_snapshot": (
                _decode_json(row["family_snapshot_json"])
                if row.get("family_snapshot_json") is not None
                else None
            ),
            "created_at": (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at)
            ),
        }
        return verify_qualification_record(payload)

    def _result_with_cursor(self, cursor: Any, run_id: str) -> dict[str, Any]:
        cursor.execute(
            "SELECT result_json FROM backtest_results WHERE run_id = %s",
            (run_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise KeyError(f"回測工作尚未產生結果：{run_id}")
        root = _decode_json(self._row(cursor, raw)["result_json"])
        if root.get("_storage") is None:
            return root
        cursor.execute(
            """
            SELECT field_name, chunk_sequence, item_count,
                   payload_json, payload_digest
            FROM backtest_result_chunks
            WHERE run_id = %s
            ORDER BY field_name, chunk_sequence
            """,
            (run_id,),
        )
        rows = [self._row(cursor, item) for item in cursor.fetchall()]
        return _rebuild_chunked_result(root, rows)

    def _verify_control_preflight_identity(
        self,
        cursor: Any,
        *,
        baseline: Mapping[str, Any],
        preflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        verify_run_identity(baseline)
        verified = verify_cash_admission_preflight(preflight)
        result = self._result_with_cursor(cursor, str(baseline["run_id"]))
        summary_digest = str(result.get("summary", {}).get("result_digest") or "")
        if (
            not summary_digest
            or summary_digest != str(baseline.get("result_digest") or "")
            or recompute_backtest_result_digest(result) != summary_digest
        ):
            raise CashAdmissionControlIntegrityError(
                "R5 baseline result digest 與 Run row 不一致"
            )
        config = dict(baseline["config"])
        atomic_snapshot = config.get("atomic_strategy_run_snapshot")
        amount_contract = config.get("dataset_amount_contract")
        binding_snapshot = config.get("dataset_binding_snapshot")
        if not all(
            isinstance(item, Mapping)
            for item in (atomic_snapshot, amount_contract, binding_snapshot)
        ):
            raise CashAdmissionControlIntegrityError(
                "R5 baseline 缺少 Atomic/Dataset/amount immutable evidence"
            )
        cursor.execute(
            "SELECT * FROM backtest_datasets WHERE dataset_id = %s FOR SHARE",
            (baseline["dataset_id"],),
        )
        raw_dataset = cursor.fetchone()
        if raw_dataset is None:
            raise CashAdmissionControlIntegrityError("R5 baseline Dataset registration 遺失")
        dataset_row = self._row(cursor, raw_dataset)
        if dataset_row["status"] != "READY":
            raise CashAdmissionControlIntegrityError("R5 baseline Dataset 不是 READY")
        manifest = self._verified_registered_manifest(dataset_row["manifest_json"])
        expected_identity = {
            "baseline_run_id": baseline["run_id"],
            "baseline_config_digest": baseline["config_digest"],
            "baseline_result_digest": baseline["result_digest"],
            "dataset_id": baseline["dataset_id"],
            "dataset_digest": baseline["dataset_digest"],
            "dataset_manifest_digest": manifest["manifest_digest"],
            "dataset_bars_sha256": manifest["bars_sha256"],
            "dataset_binding_revision": int(binding_snapshot["revision"]),
            "strategy_set_snapshot_digest": digest(dict(config["strategy_set"])),
            "atomic_strategy_run_snapshot_digest": str(
                atomic_snapshot.get("snapshot_digest") or ""
            ),
            "dataset_amount_contract_digest": digest(dict(amount_contract)),
            "engine_version": config["engine_version"],
            "commission_rate": str(config["commission_rate"]),
            "sell_tax_rate": str(config["sell_tax_rate"]),
            "slippage_bps": str(config["slippage_bps"]),
            "min_lot_shares": int(config["min_lot_shares"]),
        }
        if dict(verified["identity"]) != expected_identity:
            raise CashAdmissionControlIntegrityError(
                "R5 preflight 與 durable baseline identity 不一致"
            )
        if (
            binding_snapshot.get("dataset_id") != baseline["dataset_id"]
            or binding_snapshot.get("dataset_digest") != baseline["dataset_digest"]
        ):
            raise CashAdmissionControlIntegrityError("R5 baseline binding identity 已漂移")
        return result

    @staticmethod
    def _verify_control_config(
        *,
        baseline: Mapping[str, Any],
        control_config: BacktestRunConfig,
        preflight: Mapping[str, Any],
    ) -> None:
        snapshot = verify_research_control_snapshot(
            dict(control_config.research_control_snapshot or {})
        )
        verified_preflight = verify_cash_admission_preflight(preflight)
        if snapshot["preflight_digest"] != verified_preflight["artifact_digest"]:
            raise CashAdmissionControlIntegrityError("R5 control config preflight 已漂移")
        expected = dict(baseline["config"])
        expected.update(
            {
                "starting_cash": verified_preflight["sizing"]["starting_cash"],
                "position_fraction": verified_preflight["sizing"]["position_fraction"],
                "experiment_id": None,
                "baseline_run_id": None,
                "research_baseline_digest": None,
                "parent_run_id": baseline["run_id"],
                "change_note": snapshot["change_note"],
                "research_control_snapshot": snapshot,
            }
        )
        normalized_expected = BacktestRunConfig.from_dict(expected).to_dict()
        if control_config.to_dict() != normalized_expected:
            raise CashAdmissionControlIntegrityError(
                "R5 control config 存在未核准的 baseline delta"
            )

    @staticmethod
    def _control_identity_validation_digest(
        *,
        baseline: Mapping[str, Any],
        control: Mapping[str, Any],
        preflight: Mapping[str, Any],
    ) -> str:
        return cash_admission_identity_validation_digest(
            baseline_run=baseline,
            control_run=control,
            preflight=preflight,
        )

    @staticmethod
    def _control_operation_result(registration: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "baseline_run_id": registration["baseline_run_id"],
            "contract_version": registration["contract_version"],
            "revision": int(registration["revision"]),
            "control_run_id": registration["control_run_id"],
            "preflight_digest": registration["preflight_digest"],
            "status": registration["status"],
            "research_control_snapshot_digest": registration[
                "research_control_snapshot_digest"
            ],
            "postflight_digest": registration.get("postflight_digest"),
        }

    def _insert_control_operation(
        self,
        cursor: Any,
        *,
        request: Mapping[str, Any],
        request_digest: str,
        result: Mapping[str, Any],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO backtest_cash_admission_control_operations (
                baseline_run_id, contract_version, idempotency_key,
                request_digest, request_json, result_digest, result_json
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
            """,
            (
                result["baseline_run_id"],
                result["contract_version"],
                request["idempotency_key"],
                request_digest,
                _json(request),
                digest(dict(result)),
                _json(result),
            ),
        )

    def _control_run_payload(
        self,
        cursor: Any,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        cursor.execute(
            "SELECT * FROM backtest_runs WHERE run_id = %s",
            (result["control_run_id"],),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise CashAdmissionControlIntegrityError("R5 operation Run result 遺失")
        run = self._run_payload(self._row(cursor, raw))
        return {**run, "cash_admission_control": dict(result)}

    @staticmethod
    def _verified_control_registration(row: Mapping[str, Any]) -> dict[str, Any]:
        preflight = verify_cash_admission_preflight(
            _decode_json(row["preflight_json"])
        )
        sizing = _decode_json(row["sizing_json"])
        snapshot = verify_research_control_snapshot(
            _decode_json(row["research_control_snapshot_json"])
        )
        if row["preflight_digest"] != preflight["artifact_digest"]:
            raise CashAdmissionControlIntegrityError("R5 registration preflight digest 不一致")
        if row["sizing_digest"] != digest(sizing) or sizing != preflight["sizing"]:
            raise CashAdmissionControlIntegrityError("R5 registration sizing digest 不一致")
        if row["research_control_snapshot_digest"] != snapshot["snapshot_digest"]:
            raise CashAdmissionControlIntegrityError("R5 registration snapshot digest 不一致")
        postflight = None
        if row.get("postflight_json") is not None:
            postflight = verify_cash_admission_postflight(
                _decode_json(row["postflight_json"])
            )
            if row["postflight_digest"] != postflight["postflight_digest"]:
                raise CashAdmissionControlIntegrityError("R5 registration postflight digest 不一致")
        elif row.get("postflight_digest") is not None:
            raise CashAdmissionControlIntegrityError("R5 registration postflight evidence 不完整")
        status = str(row["status"])
        if (status == "RUN_CREATED") != (postflight is None):
            raise CashAdmissionControlIntegrityError("R5 registration status/evidence 不一致")
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        return {
            "baseline_run_id": row["baseline_run_id"],
            "contract_version": row["contract_version"],
            "revision": int(row["revision"]),
            "control_run_id": row["control_run_id"],
            "preflight_digest": row["preflight_digest"],
            "preflight": preflight,
            "sizing_digest": row["sizing_digest"],
            "sizing": sizing,
            "research_control_snapshot_digest": row[
                "research_control_snapshot_digest"
            ],
            "research_control_snapshot": snapshot,
            "status": status,
            "actor_id": row["actor_id"],
            "change_note": row["change_note"],
            "postflight_digest": row.get("postflight_digest"),
            "postflight": postflight,
            "created_at": (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at)
            ),
            "updated_at": (
                updated_at.isoformat()
                if hasattr(updated_at, "isoformat")
                else str(updated_at)
            ),
        }

    @staticmethod
    def _advisory_lock_key(scope: str, identity: str) -> int:
        lock_digest = hashlib.sha256(
            f"{scope}\0{identity}".encode("utf-8")
        ).digest()
        return int.from_bytes(lock_digest[:8], byteorder="big", signed=True)

    @staticmethod
    def _verified_binding_payload(row: dict[str, Any]) -> dict[str, Any]:
        if row["dataset_status"] != "READY":
            raise DatasetBindingIntegrityError("bound Dataset is not READY")
        manifest = PostgresBacktestRepository._verified_registered_manifest(
            row["dataset_manifest_json"]
        )
        if (
            manifest["manifest_digest"] != row["dataset_digest"]
            or manifest.get("plan_identity_digest")
            != row["plan_identity_digest"]
        ):
            raise DatasetBindingIntegrityError(
                "Dataset binding head does not match the registered manifest"
            )
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        return {
            "actor_id": row["actor_id"],
            "binding_name": row["binding_name"],
            "change_note": row["change_note"],
            "created_at": (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at)
            ),
            "dataset_digest": row["dataset_digest"],
            "dataset_id": row["dataset_id"],
            "plan_identity_digest": row["plan_identity_digest"],
            "revision": int(row["revision"]),
            "updated_at": (
                updated_at.isoformat()
                if hasattr(updated_at, "isoformat")
                else str(updated_at)
            ),
        }

    @staticmethod
    def _verified_registered_manifest(value: Any) -> dict[str, Any]:
        try:
            return canonical_registration_manifest(_decode_json(value))
        except (KeyError, TypeError, ValueError) as error:
            raise DatasetBindingIntegrityError(
                "registered Dataset manifest integrity conflict"
            ) from error

    def close(self) -> None:
        if self._pool is not None:
            if self._owns_pool:
                self._pool.close()
            return
        super().close()

    @staticmethod
    def _set_search_path(connection: Any) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO backtest, public")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    @contextmanager
    def _transaction(self):
        if self._pool is None:
            with super()._transaction() as cursor:
                yield cursor
            return
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO backtest, public")
                yield cursor

    @contextmanager
    def _cursor(self):
        if self._pool is None:
            with super()._cursor() as cursor:
                yield cursor
            return
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO backtest, public")
                yield cursor
