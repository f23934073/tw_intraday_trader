"""PostgreSQL adapter for the sealed R5 revision-2 replay aggregate."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from backtest.comparability import verify_run_identity, verified_atomic_snapshot
from backtest.dataset_binding import canonical_registration_manifest
from backtest.domain import BacktestRunConfig, digest
from backtest.migrations import apply_migrations
from backtest.repository import _decode_json, _json, _rebuild_chunked_result
from backtest.research_control import (
    CONTROL_CONTRACT_VERSION as V1_CONTROL_CONTRACT_VERSION,
    entry_signal_multiplicity_digest,
    recompute_backtest_result_digest,
    verify_cash_admission_postflight,
    verify_cash_admission_preflight,
)

from .application import (
    SignalReplayConflict,
    SignalReplayNotAccepted,
    verify_create_request,
)
from .ports import BaselinePreflightEvidence
from .domain import (
    CONTROL_CONTRACT_VERSION,
    ResearchReplayIntegrityError,
    build_ledger,
    build_ledger_manifest,
    build_order_derivation,
    build_postflight,
    canonical_object_bytes,
    layer_multiplicity_digest,
    require_sha256,
    verify_episode_row,
    verify_ledger_manifest,
    verify_ledger_row,
    verify_match_manifest,
    verify_match_row,
    verify_modeled_entry_row,
    verify_modeled_exit_row,
    verify_order_row,
    verify_postflight,
    verify_replay_consistency,
    verify_result_manifest,
)


_CHUNK_SIZE = 100
_CHUNK_FIELDS = {
    "episodes": verify_episode_row,
    "modeled_entries": verify_modeled_entry_row,
    "modeled_exits": verify_modeled_exit_row,
}
_OPERATION_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "baseline_run_id",
        "control_contract_version",
        "revision",
        "replay_id",
        "preflight_digest",
        "ledger_manifest_digest",
        "status",
        "postflight_digest",
        "result_manifest_digest",
    }
)
_TRANSITIONS = {
    ("SEALED", "RUNNING"),
    ("RUNNING", "CANCELLING"),
    ("CANCELLING", "CANCELLED"),
    ("RUNNING", "FAILED"),
}


def _json_array(value: Any) -> list[Any]:
    parsed = value if isinstance(value, list) else json.loads(value)
    if not isinstance(parsed, list):
        raise ResearchReplayIntegrityError("replay result chunk 必須是 array")
    return parsed


def _timestamp(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _operation_result(registration: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "r5-signal-ledger-replay-operation-result-v2",
        "baseline_run_id": registration["baseline_run_id"],
        "control_contract_version": registration["control_contract_version"],
        "revision": int(registration["revision"]),
        "replay_id": registration["replay_id"],
        "preflight_digest": registration["preflight_digest"],
        "ledger_manifest_digest": registration["ledger_manifest_digest"],
        "status": registration["status"],
        "postflight_digest": registration.get("postflight_digest"),
        "result_manifest_digest": registration.get("result_manifest_digest"),
    }


def _verify_operation_result(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if set(result) != _OPERATION_RESULT_FIELDS:
        raise ResearchReplayIntegrityError("replay operation result schema 不一致")
    if (
        result["schema_version"]
        != "r5-signal-ledger-replay-operation-result-v2"
        or result["control_contract_version"] != CONTROL_CONTRACT_VERSION
    ):
        raise ResearchReplayIntegrityError("replay operation result identity 不支援")
    if type(result["revision"]) is not int or result["revision"] < 1:
        raise ResearchReplayIntegrityError("replay operation revision 不合法")
    for field in ("preflight_digest", "ledger_manifest_digest"):
        require_sha256(result[field], field)
    for field in ("postflight_digest", "result_manifest_digest"):
        if result[field] is not None:
            require_sha256(result[field], field)
    if result["status"] not in {
        "SEALED",
        "RUNNING",
        "POSTFLIGHT",
        "CANCELLING",
        "CANCELLED",
        "FAILED",
        "ACCEPTED",
        "INVALID",
    }:
        raise ResearchReplayIntegrityError("replay operation status 不支援")
    return result


class SignalReplayPostgresRepository:
    """Serialize one authoritative replay per baseline and contract."""

    def __init__(
        self,
        connection: Any | None = None,
        *,
        pool: Any | None = None,
        owns_pool: bool = False,
        apply_schema: bool = True,
    ) -> None:
        if (connection is None) == (pool is None):
            raise ValueError("exactly one of connection or pool is required")
        self._connection = connection
        self._pool = pool
        self._owns_pool = owns_pool
        if pool is None:
            if apply_schema:
                apply_migrations(connection)
            self._set_search_path(connection)
        else:
            with pool.connection() as checked_out:
                if apply_schema:
                    apply_migrations(checked_out)
                self._set_search_path(checked_out)

    def replay_create_operation(
        self,
        *,
        baseline_run_id: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        require_sha256(request_digest, "request_digest")
        with self._transaction() as cursor:
            return self._operation_replay(
                cursor,
                baseline_run_id=baseline_run_id,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )

    def load_preflight_evidence(
        self, baseline_run_id: str
    ) -> BaselinePreflightEvidence:
        """Read authoritative G3 inputs without creating durable replay state."""

        with self._transaction(read_only=True) as cursor:
            evidence = self._baseline_evidence(
                cursor, baseline_run_id, lock_rows=False
            )
        return BaselinePreflightEvidence(
            identity=dict(evidence["identity"]),
            dataset_manifest=dict(evidence["dataset_manifest"]),
            ledger=evidence["ledger_build"],
            order_derivation=evidence["order_build"],
        )

    def create_replay(
        self,
        *,
        replay_id: str,
        baseline_run_id: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        ledger_manifest: Mapping[str, Any],
        match_manifest: Mapping[str, Any],
        ledger_rows: Iterable[Mapping[str, Any]],
        order_rows: Iterable[Mapping[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        if digest(request_body) != request_digest:
            raise ResearchReplayIntegrityError("replay request digest 不一致")
        require_sha256(request_digest, "request_digest")
        ledger_meta = verify_ledger_manifest(ledger_manifest)
        match_meta = verify_match_manifest(match_manifest)
        ledgers = tuple(verify_ledger_row(row) for row in ledger_rows)
        orders = tuple(verify_order_row(row) for row in order_rows)
        if request_body.get("control_contract_version") != CONTROL_CONTRACT_VERSION:
            raise ValueError("R5 v2 contract version 不支援")
        if request_body.get("expected_registration_revision") != 0:
            raise SignalReplayConflict("R5_V2_REGISTRATION_REVISION_CONFLICT")
        if (
            request_body.get("preflight_digest")
            != match_meta["match_plan_manifest_digest"]
            or match_meta["ledger_manifest_digest"]
            != ledger_meta["ledger_manifest_digest"]
            or ledger_meta["baseline_run_id"] != baseline_run_id
            or match_meta["baseline_run_id"] != baseline_run_id
        ):
            raise ResearchReplayIntegrityError("replay request/artifact lineage 不一致")
        lock_key = self._advisory_lock_key(
            "r5-signal-ledger-replay:create",
            f"{baseline_run_id}\0{CONTROL_CONTRACT_VERSION}",
        )
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            replay = self._operation_replay(
                cursor,
                baseline_run_id=baseline_run_id,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True

            cursor.execute(
                """
                SELECT * FROM r5_signal_ledger_replay_heads
                WHERE baseline_run_id = %s AND control_contract_version = %s
                FOR UPDATE
                """,
                (baseline_run_id, CONTROL_CONTRACT_VERSION),
            )
            raw_head = cursor.fetchone()
            if raw_head is not None:
                head = self._row(cursor, raw_head)
                registration = self._registration_by_replay(
                    cursor, str(head["replay_id"]), lock=True
                )
                self._verify_current_registration(
                    cursor,
                    registration=registration,
                    ledger_rows=ledgers,
                    order_rows=orders,
                )
                same_request = (
                    registration["preflight_digest"]
                    == request_body["preflight_digest"]
                    and registration["actor_id"] == request_body["actor_id"]
                    and registration["change_note"] == request_body["change_note"]
                )
                if not same_request:
                    raise SignalReplayConflict(
                        "R5_V2_REPLAY_ALREADY_SEALED: authoritative request 不同"
                    )
                result = _operation_result(registration)
                self._insert_operation(
                    cursor,
                    baseline_run_id=baseline_run_id,
                    idempotency_key=idempotency_key,
                    request=request_body,
                    request_digest=request_digest,
                    result=result,
                )
                return result, True

            evidence = self._baseline_evidence(cursor, baseline_run_id)
            self._verify_creation_artifacts(
                evidence=evidence,
                ledger_manifest=ledger_meta,
                match_manifest=match_meta,
                ledger_rows=ledgers,
                order_rows=orders,
            )
            cursor.execute(
                """
                INSERT INTO r5_signal_ledger_replay_heads (
                    baseline_run_id, control_contract_version,
                    current_revision, replay_id, status
                ) VALUES (%s, %s, 1, %s, 'SEALED')
                """,
                (baseline_run_id, CONTROL_CONTRACT_VERSION, replay_id),
            )
            cursor.execute(
                """
                INSERT INTO r5_signal_ledger_replay_registrations (
                    baseline_run_id, control_contract_version, revision,
                    replay_id, request_digest, request_json,
                    preflight_digest, ledger_manifest_digest,
                    ledger_manifest_json, match_plan_manifest_digest,
                    match_plan_manifest_json, order_derivation_digest,
                    status, progress, progress_message, actor_id, change_note
                ) VALUES (
                    %s, %s, 1, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s::jsonb,
                    %s, 'SEALED', 0, 'R5 v2 replay 已封存', %s, %s
                )
                RETURNING *
                """,
                (
                    baseline_run_id,
                    CONTROL_CONTRACT_VERSION,
                    replay_id,
                    request_digest,
                    _json(request_body),
                    match_meta["match_plan_manifest_digest"],
                    ledger_meta["ledger_manifest_digest"],
                    _json(ledger_meta),
                    match_meta["match_plan_manifest_digest"],
                    _json(match_meta),
                    ledger_meta["v2_inception_order_derivation_digest"],
                    request_body["actor_id"],
                    request_body["change_note"],
                ),
            )
            registration = self._verified_registration(
                self._row(cursor, cursor.fetchone())
            )
            result = _operation_result(registration)
            self._insert_operation(
                cursor,
                baseline_run_id=baseline_run_id,
                idempotency_key=idempotency_key,
                request=request_body,
                request_digest=request_digest,
                result=result,
            )
            return result, False

    def get_replay(self, replay_id: str) -> dict[str, Any]:
        with self._transaction() as cursor:
            registration = self._registration_by_replay(cursor, replay_id, lock=False)
            self._verify_current_registration(cursor, registration=registration)
            return registration

    def transition_replay_status(
        self,
        replay_id: str,
        *,
        expected_statuses: tuple[str, ...],
        status: str,
        progress: str | None,
        progress_message: str,
        error_message: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if not expected_statuses or any(
            (source, status) not in _TRANSITIONS for source in expected_statuses
        ):
            raise ValueError("R5 v2 status transition 不合法")
        progress_value: Decimal | None = None
        if progress is None:
            if status != "CANCELLING":
                raise ValueError("只有 CANCELLING transition 可保留既有 progress")
        else:
            try:
                progress_value = Decimal(progress)
            except (InvalidOperation, TypeError) as error:
                raise ValueError("R5 v2 progress 不合法") from error
            if not progress_value.is_finite() or not 0 <= progress_value <= 1:
                raise ValueError("R5 v2 progress 必須介於 0 與 1")
        if status == "FAILED" and not str(error_message or "").strip():
            raise ValueError("FAILED transition 必須包含 error_message")
        if status != "FAILED" and error_message is not None:
            raise ValueError("只有 FAILED transition 可包含 error_message")
        with self._transaction() as cursor:
            registration = self._registration_by_replay(cursor, replay_id, lock=True)
            self._verify_current_registration(cursor, registration=registration)
            if registration["status"] == status:
                return registration, True
            if registration["status"] not in expected_statuses:
                raise SignalReplayConflict(
                    "R5_V2_STATUS_CONFLICT: "
                    f"expected={expected_statuses}, current={registration['status']}"
                )
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_registrations
                SET status = %s,
                    progress = COALESCE(%s::numeric, progress),
                    progress_message = %s,
                    error_message = %s, updated_at = CURRENT_TIMESTAMP
                WHERE replay_id = %s AND status = ANY(%s)
                RETURNING *
                """,
                (
                    status,
                    progress_value,
                    progress_message,
                    error_message,
                    replay_id,
                    list(expected_statuses),
                ),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise SignalReplayConflict("R5_V2_STATUS_CONFLICT")
            updated = self._verified_registration(self._row(cursor, raw))
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_heads
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE baseline_run_id = %s AND control_contract_version = %s
                  AND current_revision = %s AND replay_id = %s
                """,
                (
                    status,
                    updated["baseline_run_id"],
                    updated["control_contract_version"],
                    updated["revision"],
                    replay_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchReplayIntegrityError("replay head CAS 失敗")
            return updated, False

    def publish_result(
        self,
        replay_id: str,
        *,
        ledger_rows: Iterable[Mapping[str, Any]],
        order_rows: Iterable[Mapping[str, Any]],
        match_rows: Iterable[Mapping[str, Any]],
        result_manifest: Mapping[str, Any],
        episode_rows: Iterable[Mapping[str, Any]],
        modeled_entry_rows: Iterable[Mapping[str, Any]],
        modeled_exit_rows: Iterable[Mapping[str, Any]],
        postflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        ledgers = tuple(verify_ledger_row(row) for row in ledger_rows)
        orders = tuple(verify_order_row(row) for row in order_rows)
        matches = tuple(verify_match_row(row) for row in match_rows)
        episodes = tuple(verify_episode_row(row) for row in episode_rows)
        entries = tuple(verify_modeled_entry_row(row) for row in modeled_entry_rows)
        exits = tuple(verify_modeled_exit_row(row) for row in modeled_exit_rows)
        result_meta = verify_result_manifest(result_manifest)
        supplied_postflight = verify_postflight(postflight)
        verify_replay_consistency(
            episode_rows=episodes,
            modeled_entry_rows=entries,
            modeled_exit_rows=exits,
            summary=result_meta["summary"],
        )
        with self._transaction() as cursor:
            registration = self._registration_by_replay(cursor, replay_id, lock=True)
            if registration["status"] in {"ACCEPTED", "INVALID"}:
                if registration["postflight_digest"] != supplied_postflight[
                    "postflight_digest"
                ]:
                    raise SignalReplayConflict("R5 v2 postflight 已封存且 evidence 不同")
                return registration
            if registration["status"] != "RUNNING":
                raise SignalReplayConflict(
                    f"R5 v2 replay 必須由 RUNNING publication：{registration['status']}"
                )
            evidence = self._verify_current_registration(
                cursor,
                registration=registration,
                ledger_rows=ledgers,
                order_rows=orders,
            )
            self._verify_match_and_result_artifacts(
                registration=registration,
                match_rows=matches,
                result_manifest=result_meta,
                episode_rows=episodes,
                modeled_entry_rows=entries,
                modeled_exit_rows=exits,
            )
            config = BacktestRunConfig.from_dict(evidence["baseline"]["config"])
            rebuilt_postflight = build_postflight(
                replay_id=replay_id,
                registration_revision=registration["revision"],
                baseline_result_digest=evidence["baseline"]["result_digest"],
                ledger_manifest=registration["ledger_manifest"],
                match_manifest=registration["match_plan_manifest"],
                result_manifest=result_meta,
                decision_rows=evidence["ledger_build"].rows,
                order_rows=orders,
                ledger_rows=ledgers,
                match_rows=matches,
                episode_rows=episodes,
                modeled_entry_rows=entries,
                modeled_exit_rows=exits,
                min_lot_shares=config.min_lot_shares,
                slippage_bps=config.slippage_bps,
                commission_rate=config.commission_rate,
                sell_tax_rate=config.sell_tax_rate,
                baseline_identity_valid=True,
                v1_invalid_lineage_valid=True,
                order_inception_seal_valid=True,
                ledger_artifact_valid=True,
                match_plan_artifact_valid=True,
                result_artifact_valid=True,
                v1_signal_multiplicity_valid=True,
                strategy_evaluation_count=0,
                provider_call_count=0,
                broker_call_count=0,
            )
            if rebuilt_postflight != supplied_postflight:
                raise ResearchReplayIntegrityError("R5 v2 postflight 無法由 current evidence 重建")
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_registrations
                SET status = 'POSTFLIGHT', progress_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE replay_id = %s AND status = 'RUNNING'
                """,
                ("R5 v2 正在執行 postflight", replay_id),
            )
            if cursor.rowcount != 1:
                raise SignalReplayConflict("R5_V2_STATUS_CONFLICT")
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_heads
                SET status = 'POSTFLIGHT', updated_at = CURRENT_TIMESTAMP
                WHERE replay_id = %s AND status = 'RUNNING'
                """,
                (replay_id,),
            )
            if cursor.rowcount != 1:
                raise ResearchReplayIntegrityError("replay postflight head CAS 失敗")
            status = supplied_postflight["verdict"]
            if status == "ACCEPTED":
                self._insert_result(
                    cursor,
                    replay_id=replay_id,
                    result_manifest=result_meta,
                    postflight=supplied_postflight,
                    episodes=episodes,
                    entries=entries,
                    exits=exits,
                )
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_registrations
                SET status = %s, progress = 1, progress_message = %s,
                    postflight_digest = %s, postflight_json = %s::jsonb,
                    result_manifest_digest = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE replay_id = %s AND status = 'POSTFLIGHT'
                RETURNING *
                """,
                (
                    status,
                    "R5 v2 postflight accepted"
                    if status == "ACCEPTED"
                    else "R5 v2 postflight invalid",
                    supplied_postflight["postflight_digest"],
                    _json(supplied_postflight),
                    result_meta["result_manifest_digest"]
                    if status == "ACCEPTED"
                    else None,
                    replay_id,
                ),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise SignalReplayConflict("R5_V2_STATUS_CONFLICT")
            updated = self._verified_registration(self._row(cursor, raw))
            cursor.execute(
                """
                UPDATE r5_signal_ledger_replay_heads
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE replay_id = %s AND status = 'POSTFLIGHT'
                """,
                (status, replay_id),
            )
            if cursor.rowcount != 1:
                raise ResearchReplayIntegrityError("replay terminal head CAS 失敗")
            return updated

    def get_accepted_result(
        self,
        replay_id: str,
        *,
        ledger_rows: Iterable[Mapping[str, Any]] = (),
        order_rows: Iterable[Mapping[str, Any]] = (),
        match_rows: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        ledgers = tuple(verify_ledger_row(row) for row in ledger_rows)
        orders = tuple(verify_order_row(row) for row in order_rows)
        matches = tuple(verify_match_row(row) for row in match_rows)
        with self._transaction() as cursor:
            registration = self._registration_by_replay(cursor, replay_id, lock=False)
            if registration["status"] != "ACCEPTED":
                raise SignalReplayNotAccepted("R5_V2_POSTFLIGHT_NOT_ACCEPTED")
            evidence = self._verify_current_registration(
                cursor,
                registration=registration,
                ledger_rows=ledgers or None,
                order_rows=orders or None,
            )
            result = self._result_with_cursor(cursor, replay_id)
            self._verify_match_and_result_artifacts(
                registration=registration,
                match_rows=matches,
                result_manifest=result["result_manifest"],
                episode_rows=result["episodes"],
                modeled_entry_rows=result["modeled_entries"],
                modeled_exit_rows=result["modeled_exits"],
            )
            config = BacktestRunConfig.from_dict(evidence["baseline"]["config"])
            rebuilt = build_postflight(
                replay_id=replay_id,
                registration_revision=registration["revision"],
                baseline_result_digest=evidence["baseline"]["result_digest"],
                ledger_manifest=registration["ledger_manifest"],
                match_manifest=registration["match_plan_manifest"],
                result_manifest=result["result_manifest"],
                decision_rows=evidence["ledger_build"].rows,
                order_rows=orders,
                ledger_rows=ledgers,
                match_rows=matches,
                episode_rows=result["episodes"],
                modeled_entry_rows=result["modeled_entries"],
                modeled_exit_rows=result["modeled_exits"],
                min_lot_shares=config.min_lot_shares,
                slippage_bps=config.slippage_bps,
                commission_rate=config.commission_rate,
                sell_tax_rate=config.sell_tax_rate,
                baseline_identity_valid=True,
                v1_invalid_lineage_valid=True,
                order_inception_seal_valid=True,
                ledger_artifact_valid=True,
                match_plan_artifact_valid=True,
                result_artifact_valid=True,
                v1_signal_multiplicity_valid=True,
                strategy_evaluation_count=0,
                provider_call_count=0,
                broker_call_count=0,
            )
            if rebuilt != registration["postflight"]:
                raise ResearchReplayIntegrityError("accepted postflight current evidence conflict")
            return result

    def _baseline_evidence(
        self,
        cursor: Any,
        baseline_run_id: str,
        *,
        lock_rows: bool = True,
    ) -> dict[str, Any]:
        cursor.execute(
            "SELECT * FROM backtest_runs WHERE run_id = %s"
            + (" FOR SHARE" if lock_rows else ""),
            (baseline_run_id,),
        )
        raw_run = cursor.fetchone()
        if raw_run is None:
            raise KeyError(f"找不到 R5 v2 baseline：{baseline_run_id}")
        baseline = self._run_payload(self._row(cursor, raw_run))
        if baseline["status"] != "COMPLETED":
            raise ResearchReplayIntegrityError("R5 v2 baseline 必須是 COMPLETED")
        verify_run_identity(baseline)
        result = self._baseline_result_with_cursor(cursor, baseline_run_id)
        stored_result_digest = str(baseline.get("result_digest") or "")
        if (
            not stored_result_digest
            or result.get("summary", {}).get("result_digest") != stored_result_digest
            or recompute_backtest_result_digest(result) != stored_result_digest
        ):
            raise ResearchReplayIntegrityError("baseline result digest 無法重建")
        ledger_build = build_ledger(
            baseline_run_id=baseline_run_id,
            decisions=result.get("decisions", ()),
        )
        order_build = build_order_derivation(
            ledger_rows=ledger_build.rows,
            orders=result.get("orders", ()),
        )
        cursor.execute(
            """
            SELECT registration.*
            FROM backtest_cash_admission_control_registrations AS registration
            JOIN backtest_cash_admission_control_heads AS head
              ON head.baseline_run_id = registration.baseline_run_id
             AND head.contract_version = registration.contract_version
             AND head.current_revision = registration.revision
            WHERE registration.baseline_run_id = %s
              AND registration.contract_version = %s
            """
            + (" FOR SHARE OF registration" if lock_rows else ""),
            (baseline_run_id, V1_CONTROL_CONTRACT_VERSION),
        )
        v1_rows = cursor.fetchall()
        if len(v1_rows) != 1:
            raise ResearchReplayIntegrityError("R5 v1 terminal registration 不唯一")
        v1 = self._row(cursor, v1_rows[0])
        if v1["status"] != "INVALID" or v1.get("postflight_json") is None:
            raise ResearchReplayIntegrityError("R5 v1 必須 terminal INVALID")
        v1_preflight = verify_cash_admission_preflight(
            _decode_json(v1["preflight_json"])
        )
        v1_postflight = verify_cash_admission_postflight(
            _decode_json(v1["postflight_json"])
        )
        if (
            v1["preflight_digest"] != v1_preflight["artifact_digest"]
            or v1["postflight_digest"] != v1_postflight["postflight_digest"]
            or v1_postflight["verdict"] != "INVALID"
            or v1_postflight["baseline_run_id"] != baseline_run_id
        ):
            raise ResearchReplayIntegrityError("R5 v1 lineage digest 無法重建")
        compatible_orders = [
            {
                "side": "ENTRY",
                "symbol": item["symbol"],
                "created_at": item["event_at"],
                "primary_strategy_id": item["primary_strategy_id"],
                "triggered_strategy_ids": list(item["triggered_strategy_ids"]),
            }
            for item in result.get("decisions", ())
            if item.get("side") == "ENTRY"
        ]
        v1_signal_digest = entry_signal_multiplicity_digest(compatible_orders)
        if (
            v1_signal_digest
            != v1_preflight["statistics"]["baseline_signal_multiplicity_digest"]
        ):
            raise ResearchReplayIntegrityError("R5 v1 signal multiplicity 已漂移")
        cursor.execute(
            "SELECT * FROM backtest_datasets WHERE dataset_id = %s"
            + (" FOR SHARE" if lock_rows else ""),
            (baseline["dataset_id"],),
        )
        raw_dataset = cursor.fetchone()
        if raw_dataset is None:
            raise ResearchReplayIntegrityError("baseline Dataset registration 遺失")
        dataset = self._row(cursor, raw_dataset)
        if dataset["status"] != "READY":
            raise ResearchReplayIntegrityError("baseline Dataset 不是 READY")
        manifest = canonical_registration_manifest(_decode_json(dataset["manifest_json"]))
        config = BacktestRunConfig.from_dict(baseline["config"])
        atomic_snapshot = verified_atomic_snapshot(baseline["config"])
        amount_contract = baseline["config"].get("dataset_amount_contract")
        binding = baseline["config"].get("dataset_binding_snapshot")
        if (
            atomic_snapshot is None
            or not isinstance(amount_contract, Mapping)
            or not isinstance(binding, Mapping)
            or binding.get("dataset_id") != baseline["dataset_id"]
            or binding.get("dataset_digest") != baseline["dataset_digest"]
        ):
            raise ResearchReplayIntegrityError("baseline Atomic/Dataset lineage 不完整")
        identity = {
            "baseline_run_id": baseline_run_id,
            "baseline_config_digest": baseline["config_digest"],
            "baseline_result_digest": stored_result_digest,
            "v1_preflight_digest": v1_preflight["artifact_digest"],
            "v1_signal_multiplicity_digest": v1_signal_digest,
            "v1_invalid_postflight_digest": v1_postflight["postflight_digest"],
            "atomic_strategy_run_snapshot_digest": atomic_snapshot["snapshot_digest"],
            "dataset_id": baseline["dataset_id"],
            "dataset_digest": baseline["dataset_digest"],
            "dataset_manifest_digest": manifest["manifest_digest"],
            "dataset_bars_sha256": manifest["bars_sha256"],
            "dataset_binding_revision": int(binding["revision"]),
            "dataset_amount_contract_digest": digest(dict(amount_contract)),
        }
        expected_v1_identity = {
            "baseline_run_id": baseline_run_id,
            "baseline_config_digest": baseline["config_digest"],
            "baseline_result_digest": stored_result_digest,
            "dataset_id": baseline["dataset_id"],
            "dataset_digest": baseline["dataset_digest"],
            "dataset_manifest_digest": manifest["manifest_digest"],
            "dataset_bars_sha256": manifest["bars_sha256"],
            "dataset_binding_revision": int(binding["revision"]),
            "strategy_set_snapshot_digest": digest(
                dict(baseline["config"]["strategy_set"])
            ),
            "atomic_strategy_run_snapshot_digest": atomic_snapshot[
                "snapshot_digest"
            ],
            "dataset_amount_contract_digest": digest(dict(amount_contract)),
            "engine_version": config.engine_version,
            "commission_rate": str(config.commission_rate),
            "sell_tax_rate": str(config.sell_tax_rate),
            "slippage_bps": str(config.slippage_bps),
            "min_lot_shares": config.min_lot_shares,
        }
        if dict(v1_preflight["identity"]) != expected_v1_identity:
            raise ResearchReplayIntegrityError("R5 v1 preflight baseline identity 已漂移")
        if (
            config.dataset_id != identity["dataset_id"]
            or config.dataset_digest != identity["dataset_digest"]
        ):
            raise ResearchReplayIntegrityError("baseline config Dataset identity 已漂移")
        return {
            "baseline": baseline,
            "result": result,
            "ledger_build": ledger_build,
            "order_build": order_build,
            "identity": identity,
            "dataset_manifest": manifest,
            "v1_preflight": v1_preflight,
            "v1_postflight": v1_postflight,
        }

    def _verify_creation_artifacts(
        self,
        *,
        evidence: Mapping[str, Any],
        ledger_manifest: Mapping[str, Any],
        match_manifest: Mapping[str, Any],
        ledger_rows: tuple[dict[str, Any], ...],
        order_rows: tuple[dict[str, Any], ...],
    ) -> None:
        expected_ledger = build_ledger_manifest(
            identity=evidence["identity"],
            ledger=evidence["ledger_build"],
            order_derivation=evidence["order_build"],
        )
        if (
            dict(ledger_manifest) != expected_ledger
            or ledger_rows != evidence["ledger_build"].rows
            or order_rows != evidence["order_build"].rows
        ):
            raise ResearchReplayIntegrityError("ledger inception evidence 與 baseline 不一致")
        if (
            match_manifest["ledger_manifest_digest"]
            != expected_ledger["ledger_manifest_digest"]
            or match_manifest["dataset_id"] != expected_ledger["dataset_id"]
            or match_manifest["dataset_digest"] != expected_ledger["dataset_digest"]
            or match_manifest["signal_count"] != expected_ledger["ledger_signal_count"]
            or match_manifest["matched_entry_count"] != match_manifest["signal_count"]
            or match_manifest["matched_exit_count"] != match_manifest["signal_count"]
            or match_manifest["missing_entry_count"] != 0
            or match_manifest["missing_exit_count"] != 0
            or match_manifest["duplicate_match_count"] != 0
        ):
            raise ResearchReplayIntegrityError("preflight coverage/lineage 不完整")

    def _verify_current_registration(
        self,
        cursor: Any,
        *,
        registration: Mapping[str, Any],
        ledger_rows: tuple[dict[str, Any], ...] | None = None,
        order_rows: tuple[dict[str, Any], ...] | None = None,
    ) -> dict[str, Any]:
        evidence = self._baseline_evidence(cursor, registration["baseline_run_id"])
        expected_ledger = build_ledger_manifest(
            identity=evidence["identity"],
            ledger=evidence["ledger_build"],
            order_derivation=evidence["order_build"],
        )
        if (
            registration["ledger_manifest"] != expected_ledger
            or registration["order_derivation_digest"]
            != expected_ledger["v2_inception_order_derivation_digest"]
            or registration["match_plan_manifest"]["ledger_manifest_digest"]
            != expected_ledger["ledger_manifest_digest"]
        ):
            raise ResearchReplayIntegrityError("durable replay inception evidence 已漂移")
        if ledger_rows is not None and ledger_rows != evidence["ledger_build"].rows:
            raise ResearchReplayIntegrityError("current ledger artifact 已漂移")
        if order_rows is not None and order_rows != evidence["order_build"].rows:
            raise ResearchReplayIntegrityError("current order derivation artifact 已漂移")
        return evidence

    def _verify_match_and_result_artifacts(
        self,
        *,
        registration: Mapping[str, Any],
        match_rows: tuple[dict[str, Any], ...],
        result_manifest: Mapping[str, Any],
        episode_rows: tuple[dict[str, Any], ...],
        modeled_entry_rows: tuple[dict[str, Any], ...],
        modeled_exit_rows: tuple[dict[str, Any], ...],
    ) -> None:
        match_meta = registration["match_plan_manifest"]
        if (
            len(match_rows) != match_meta["matched_exit_count"]
            or self._rows_sha256(match_rows) != match_meta["match_rows_sha256"]
            or layer_multiplicity_digest(match_rows)
            != match_meta["match_signal_multiplicity_digest"]
        ):
            raise ResearchReplayIntegrityError("current match-plan artifact 已漂移")
        result_meta = verify_result_manifest(result_manifest)
        if (
            result_meta["replay_id"] != registration["replay_id"]
            or result_meta["baseline_run_id"] != registration["baseline_run_id"]
            or result_meta["registration_revision"] != registration["revision"]
            or result_meta["ledger_manifest_digest"]
            != registration["ledger_manifest_digest"]
            or result_meta["match_plan_manifest_digest"]
            != registration["preflight_digest"]
        ):
            raise ResearchReplayIntegrityError("result manifest lineage 不一致")
        row_sets = (
            (episode_rows, "episode"),
            (modeled_entry_rows, "modeled_entry"),
            (modeled_exit_rows, "modeled_exit"),
        )
        for rows, prefix in row_sets:
            if (
                len(rows) != result_meta[f"{prefix}_count"]
                or self._rows_sha256(rows) != result_meta[f"{prefix}_rows_sha256"]
                or layer_multiplicity_digest(rows)
                != result_meta[f"{prefix}_signal_multiplicity_digest"]
            ):
                raise ResearchReplayIntegrityError(f"current {prefix} artifact 已漂移")
        verify_replay_consistency(
            episode_rows=episode_rows,
            modeled_entry_rows=modeled_entry_rows,
            modeled_exit_rows=modeled_exit_rows,
            summary=result_meta["summary"],
        )

    def _registration_by_replay(
        self, cursor: Any, replay_id: str, *, lock: bool
    ) -> dict[str, Any]:
        cursor.execute(
            "SELECT * FROM r5_signal_ledger_replay_registrations "
            "WHERE replay_id = %s" + (" FOR UPDATE" if lock else ""),
            (replay_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise KeyError(f"找不到 R5 v2 replay：{replay_id}")
        registration = self._verified_registration(self._row(cursor, raw))
        cursor.execute(
            """
            SELECT * FROM r5_signal_ledger_replay_heads
            WHERE baseline_run_id = %s AND control_contract_version = %s
            """,
            (
                registration["baseline_run_id"],
                registration["control_contract_version"],
            ),
        )
        raw_head = cursor.fetchone()
        if raw_head is None:
            raise ResearchReplayIntegrityError("replay head 遺失")
        head = self._row(cursor, raw_head)
        if (
            int(head["current_revision"]) != registration["revision"]
            or head["replay_id"] != registration["replay_id"]
            or head["status"] != registration["status"]
        ):
            raise ResearchReplayIntegrityError("replay head/registration projection 不一致")
        return registration

    def _operation_replay(
        self,
        cursor: Any,
        *,
        baseline_run_id: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT request_digest, result_digest, result_json
                 , request_json
            FROM r5_signal_ledger_replay_operations
            WHERE baseline_run_id = %s AND control_contract_version = %s
              AND idempotency_key = %s
            """,
            (baseline_run_id, CONTROL_CONTRACT_VERSION, idempotency_key),
        )
        raw = cursor.fetchone()
        if raw is None:
            return None
        row = self._row(cursor, raw)
        stored_request = verify_create_request(_decode_json(row["request_json"]))
        if digest(stored_request) != row["request_digest"]:
            raise ResearchReplayIntegrityError("replay operation request digest 已漂移")
        if row["request_digest"] != request_digest:
            raise SignalReplayConflict("相同 R5 v2 idempotency key 的 request 不同")
        result = _verify_operation_result(_decode_json(row["result_json"]))
        if digest(result) != row["result_digest"]:
            raise ResearchReplayIntegrityError("replay operation result digest 已漂移")
        if (
            result["baseline_run_id"] != baseline_run_id
            or result["control_contract_version"] != CONTROL_CONTRACT_VERSION
            or result["preflight_digest"] != stored_request["preflight_digest"]
        ):
            raise ResearchReplayIntegrityError("replay operation result scope 已漂移")
        try:
            registration = self._registration_by_replay(
                cursor, str(result["replay_id"]), lock=False
            )
        except KeyError as error:
            raise ResearchReplayIntegrityError(
                "replay operation result scope 已漂移"
            ) from error
        if (
            registration["baseline_run_id"] != baseline_run_id
            or registration["control_contract_version"]
            != CONTROL_CONTRACT_VERSION
            or registration["request_digest"] != row["request_digest"]
            or registration["preflight_digest"] != result["preflight_digest"]
            or registration["replay_id"] != result["replay_id"]
            or registration["revision"] != result["revision"]
            or registration["ledger_manifest_digest"]
            != result["ledger_manifest_digest"]
        ):
            raise ResearchReplayIntegrityError("replay operation result scope 已漂移")
        return result

    def _insert_operation(
        self,
        cursor: Any,
        *,
        baseline_run_id: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        result: Mapping[str, Any],
    ) -> None:
        verified_result = _verify_operation_result(result)
        cursor.execute(
            """
            INSERT INTO r5_signal_ledger_replay_operations (
                baseline_run_id, control_contract_version, idempotency_key,
                request_digest, request_json, result_digest, result_json
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
            """,
            (
                baseline_run_id,
                CONTROL_CONTRACT_VERSION,
                idempotency_key,
                request_digest,
                _json(request),
                digest(verified_result),
                _json(verified_result),
            ),
        )

    def _insert_result(
        self,
        cursor: Any,
        *,
        replay_id: str,
        result_manifest: Mapping[str, Any],
        postflight: Mapping[str, Any],
        episodes: tuple[dict[str, Any], ...],
        entries: tuple[dict[str, Any], ...],
        exits: tuple[dict[str, Any], ...],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO r5_signal_ledger_replay_results (
                replay_id, result_manifest_digest, result_manifest_json,
                postflight_digest, postflight_json
            ) VALUES (%s, %s, %s::jsonb, %s, %s::jsonb)
            """,
            (
                replay_id,
                result_manifest["result_manifest_digest"],
                _json(result_manifest),
                postflight["postflight_digest"],
                _json(postflight),
            ),
        )
        for field_name, rows in (
            ("episodes", episodes),
            ("modeled_entries", entries),
            ("modeled_exits", exits),
        ):
            for sequence, start in enumerate(range(0, len(rows), _CHUNK_SIZE)):
                payload = list(rows[start : start + _CHUNK_SIZE])
                cursor.execute(
                    """
                    INSERT INTO r5_signal_ledger_replay_result_chunks (
                        replay_id, field_name, chunk_sequence,
                        item_count, payload_json, payload_digest
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        replay_id,
                        field_name,
                        sequence,
                        len(payload),
                        _json(payload),
                        digest(payload),
                    ),
                )

    def _result_with_cursor(self, cursor: Any, replay_id: str) -> dict[str, Any]:
        cursor.execute(
            "SELECT * FROM r5_signal_ledger_replay_results WHERE replay_id = %s",
            (replay_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise SignalReplayNotAccepted("R5_V2_POSTFLIGHT_NOT_ACCEPTED")
        row = self._row(cursor, raw)
        result_manifest = verify_result_manifest(
            _decode_json(row["result_manifest_json"])
        )
        postflight = verify_postflight(_decode_json(row["postflight_json"]))
        if (
            row["result_manifest_digest"]
            != result_manifest["result_manifest_digest"]
            or row["postflight_digest"] != postflight["postflight_digest"]
            or postflight["verdict"] != "ACCEPTED"
            or postflight["result_manifest_digest"]
            != result_manifest["result_manifest_digest"]
        ):
            raise ResearchReplayIntegrityError("accepted replay root evidence 已漂移")
        cursor.execute(
            """
            SELECT field_name, chunk_sequence, item_count,
                   payload_json, payload_digest
            FROM r5_signal_ledger_replay_result_chunks
            WHERE replay_id = %s
            ORDER BY field_name, chunk_sequence
            """,
            (replay_id,),
        )
        grouped: dict[str, list[dict[str, Any]]] = {
            field: [] for field in _CHUNK_FIELDS
        }
        for raw_chunk in cursor.fetchall():
            chunk = self._row(cursor, raw_chunk)
            field = str(chunk["field_name"])
            if field not in grouped:
                raise ResearchReplayIntegrityError("accepted replay chunk field 不支援")
            grouped[field].append(chunk)
        rebuilt: dict[str, list[dict[str, Any]]] = {}
        for field, verifier in _CHUNK_FIELDS.items():
            values: list[dict[str, Any]] = []
            for expected_sequence, chunk in enumerate(grouped[field]):
                payload = _json_array(chunk["payload_json"])
                if (
                    int(chunk["chunk_sequence"]) != expected_sequence
                    or len(payload) != int(chunk["item_count"])
                    or digest(payload) != chunk["payload_digest"]
                ):
                    raise ResearchReplayIntegrityError("accepted replay chunk integrity conflict")
                values.extend(verifier(item) for item in payload)
            rebuilt[field] = values
        return {
            "result_manifest_digest": result_manifest["result_manifest_digest"],
            "result_manifest": result_manifest,
            "postflight": postflight,
            **rebuilt,
        }

    @staticmethod
    def _verified_registration(row: Mapping[str, Any]) -> dict[str, Any]:
        request = verify_create_request(_decode_json(row["request_json"]))
        ledger = verify_ledger_manifest(_decode_json(row["ledger_manifest_json"]))
        match = verify_match_manifest(_decode_json(row["match_plan_manifest_json"]))
        postflight = (
            verify_postflight(_decode_json(row["postflight_json"]))
            if row.get("postflight_json") is not None
            else None
        )
        if (
            row["control_contract_version"] != CONTROL_CONTRACT_VERSION
            or row["request_digest"] != digest(request)
            or request["control_contract_version"] != row["control_contract_version"]
            or request["preflight_digest"] != row["preflight_digest"]
            or request["expected_registration_revision"] != 0
            or request["actor_id"] != row["actor_id"]
            or request["change_note"] != row["change_note"]
            or row["ledger_manifest_digest"] != ledger["ledger_manifest_digest"]
            or row["match_plan_manifest_digest"]
            != match["match_plan_manifest_digest"]
            or row["preflight_digest"] != match["match_plan_manifest_digest"]
            or row["order_derivation_digest"]
            != ledger["v2_inception_order_derivation_digest"]
            or match["ledger_manifest_digest"] != ledger["ledger_manifest_digest"]
        ):
            raise ResearchReplayIntegrityError("replay registration immutable evidence 已漂移")
        if (row.get("postflight_digest") is None) != (postflight is None):
            raise ResearchReplayIntegrityError("replay postflight evidence pair 不完整")
        if postflight is not None and row["postflight_digest"] != postflight["postflight_digest"]:
            raise ResearchReplayIntegrityError("replay postflight digest 已漂移")
        status = str(row["status"])
        result_digest = row.get("result_manifest_digest")
        if (
            (status == "ACCEPTED" and (postflight is None or result_digest is None))
            or (status == "INVALID" and (postflight is None or result_digest is not None))
            or (
                status not in {"ACCEPTED", "INVALID"}
                and (postflight is not None or result_digest is not None)
            )
        ):
            raise ResearchReplayIntegrityError("replay status/evidence projection 不一致")
        if result_digest is not None:
            require_sha256(result_digest, "result_manifest_digest")
        progress = Decimal(str(row["progress"]))
        if not progress.is_finite() or not 0 <= progress <= 1:
            raise ResearchReplayIntegrityError("replay progress 不合法")
        return {
            "baseline_run_id": row["baseline_run_id"],
            "control_contract_version": row["control_contract_version"],
            "revision": int(row["revision"]),
            "replay_id": row["replay_id"],
            "request_digest": row["request_digest"],
            "preflight_digest": row["preflight_digest"],
            "ledger_manifest_digest": row["ledger_manifest_digest"],
            "ledger_manifest": ledger,
            "match_plan_manifest_digest": row["match_plan_manifest_digest"],
            "match_plan_manifest": match,
            "order_derivation_digest": row["order_derivation_digest"],
            "status": status,
            "progress": str(progress.normalize()) if progress else "0",
            "progress_message": row["progress_message"],
            "actor_id": row["actor_id"],
            "change_note": row["change_note"],
            "postflight_digest": row.get("postflight_digest"),
            "postflight": postflight,
            "result_manifest_digest": result_digest,
            "error_message": row.get("error_message"),
            "created_at": _timestamp(row["created_at"]),
            "updated_at": _timestamp(row["updated_at"]),
        }

    @staticmethod
    def _run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "config": _decode_json(row["config_json"]),
            "config_digest": row["config_digest"],
            "dataset_id": row["dataset_id"],
            "dataset_digest": row["dataset_digest"],
            "progress": float(row["progress"]),
            "progress_message": row["progress_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_message": row.get("error_message"),
            "result_digest": row.get("result_digest"),
        }

    def _baseline_result_with_cursor(self, cursor: Any, run_id: str) -> dict[str, Any]:
        cursor.execute(
            "SELECT result_json FROM backtest_results WHERE run_id = %s",
            (run_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise ResearchReplayIntegrityError("baseline result 遺失")
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
        return _rebuild_chunked_result(
            root, [self._row(cursor, item) for item in cursor.fetchall()]
        )

    @staticmethod
    def _rows_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
        checksum = hashlib.sha256()
        for row in rows:
            checksum.update(canonical_object_bytes(row))
        return checksum.hexdigest()

    @staticmethod
    def _advisory_lock_key(scope: str, identity: str) -> int:
        payload = hashlib.sha256(f"{scope}\0{identity}".encode("utf-8")).digest()
        return int.from_bytes(payload[:8], byteorder="big", signed=True)

    @staticmethod
    def _row(cursor: Any, raw: Any) -> dict[str, Any]:
        return dict(zip((item.name for item in cursor.description), raw))

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
    def _transaction(self, *, read_only: bool = False):
        if self._pool is None:
            assert self._connection is not None
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute("SET search_path TO backtest, public")
                    if read_only:
                        cursor.execute(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                        )
                    yield cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            return
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO backtest, public")
                if read_only:
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                yield cursor

    def close(self) -> None:
        if self._pool is not None:
            if self._owns_pool:
                self._pool.close()
            return
        if self._connection is not None:
            self._connection.close()
