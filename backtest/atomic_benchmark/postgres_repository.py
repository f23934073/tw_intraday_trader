"""PostgreSQL-only persistence adapter for R6 family and matrix registration."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.dataset_binding import (
    ATOMIC_BACKTEST_DEFAULT,
    canonical_registration_manifest,
)
from backtest.domain import canonical_json, digest
from backtest.migrations import apply_migrations
from strategy_catalog.drafts import PublishStrategyRequest
from strategy_catalog.parameter_schema import canonical_digest

from .domain import (
    FAMILY_ID,
    MatrixSealBuild,
    build_matrix_seal,
    build_version_binding,
    validate_attempt_transition,
    verify_integrity_diagnostic_codes,
)
from .repository import AtomicBenchmarkConflict
from .preflight import preflight_implementation_digest, verify_preflight_artifact


_G1_FROZEN_PUBLICATION_SLOTS = frozenset({1, 3, 4, 5})
_G1_ACTOR_ID = "r6-g1-research-operator"
_G1_ACTOR_SESSION_ID = "r6-g1-version-admission-v1"
_G1_CHANGE_NOTE = "R6 G1 frozen atomic-entry benchmark Version admission"
_OPERATION_OUTBOX_TOPIC = "research.atomic-entry-benchmark.v1"


def _json(value: Mapping[str, Any] | list[Any]) -> str:
    return canonical_json(value)


def _decoded(value: Any, label: str) -> Any:
    resolved = json.loads(value) if isinstance(value, str) else value
    if not isinstance(resolved, (dict, list)):
        raise AtomicBenchmarkConflict(f"R6_{label.upper()}_INTEGRITY_ERROR")
    return resolved


class AtomicBenchmarkPostgresRepository:
    """Serialize one sealed matrix for the stable R6 research family."""

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

    def close(self) -> None:
        if self._owns_pool and self._pool is not None:
            self._pool.close()

    @staticmethod
    def _preflight_slot_bindings_valid(
        *,
        preflight_slots: object,
        matrix_slots: list[dict[str, Any]],
        artifact_slot_manifests: list[dict[str, dict[str, object]]],
        eligibility_manifest_digest: object,
    ) -> bool:
        if (
            not isinstance(preflight_slots, list)
            or not (
                len(preflight_slots)
                == len(matrix_slots)
                == len(artifact_slot_manifests)
            )
        ):
            return False
        if len(matrix_slots) != 7:
            return False
        for root, stored, manifest_pair in zip(
            preflight_slots,
            matrix_slots,
            artifact_slot_manifests,
            strict=True,
        ):
            if not isinstance(root, Mapping):
                return False
            specification = _decoded(
                stored["hypothesis_spec_json"], "hypothesis_spec"
            )
            version = _decoded(stored["version_binding_json"], "version_binding")
            ledger = manifest_pair["ledger"]
            if (
                root.get("slot_sequence") != int(stored["slot_sequence"])
                or root.get("hypothesis_id") != stored["hypothesis_id"]
                or root.get("eligibility_manifest_digest")
                != eligibility_manifest_digest
                or ledger.get("ledger_manifest_digest")
                != root.get("ledger_manifest_digest")
                or ledger.get("slot_sequence") != int(stored["slot_sequence"])
                or ledger.get("hypothesis_id") != stored["hypothesis_id"]
                or ledger.get("strategy_version_id")
                != stored["strategy_version_id"]
                or ledger.get("strategy_id") != specification.get("strategy_id")
                or ledger.get("strategy_configuration_digest")
                != specification.get("strategy_configuration_digest")
                or ledger.get("strategy_implementation_digest")
                != specification.get("strategy_implementation_digest")
                or ledger.get("lifecycle_sequence")
                != version.get("lifecycle_sequence")
                or ledger.get("lifecycle_event_id")
                != version.get("lifecycle_event_id")
                or ledger.get("lifecycle_projection_digest")
                != version.get("lifecycle_projection_digest")
            ):
                return False
        return True

    def seal_matrix(
        self,
        *,
        build: MatrixSealBuild,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        if digest(request_body) != request_digest:
            raise AtomicBenchmarkConflict("R6_MATRIX_REQUEST_DIGEST_CONFLICT")
        if build.family_id != FAMILY_ID:
            raise AtomicBenchmarkConflict("R6_FAMILY_IDENTITY_CONFLICT")

        with self._transaction() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (self._advisory_lock_key("r6:matrix-seal", build.family_id),),
            )
            replay = self._operation_replay(
                cursor,
                family_id=build.family_id,
                operation_type="SEAL_MATRIX",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True

            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_families
                WHERE family_id = %s FOR UPDATE
                """,
                (build.family_id,),
            )
            existing_family = cursor.fetchone()
            if existing_family is not None:
                self._verify_matrix(cursor, build.family_id)
                raise AtomicBenchmarkConflict("R6_MATRIX_REVISION_ALREADY_SEALED")

            self._verify_source_run(cursor, build)
            self._verify_versions(cursor, build)
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_families (
                    family_id, source_lineage_run_id, research_baseline_json,
                    research_baseline_digest, protocol_core_json,
                    protocol_core_digest, planned_attempts, family_alpha,
                    adjustment_method, head_sequence, active_matrix_revision,
                    release_state, actor_id
                ) VALUES (
                    %s, %s, %s::jsonb, %s, %s::jsonb, %s,
                    20, 0.05, 'BONFERRONI', 0, 1, 'NOT_READY', %s
                )
                """,
                (
                    build.family_id,
                    build.research_baseline["source_lineage_run_id"],
                    _json(build.research_baseline),
                    digest(build.research_baseline),
                    _json(build.protocol_core),
                    digest(build.protocol_core),
                    actor_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_matrices (
                    matrix_id, family_id, matrix_revision, matrix_core_json,
                    matrix_core_digest, benchmark_build_binding_json,
                    benchmark_build_binding_digest, registration_json,
                    registration_digest, registered_slots_json, status,
                    actor_id, change_note
                ) VALUES (
                    %s, %s, 1, %s::jsonb, %s, %s::jsonb, %s,
                    %s::jsonb, %s, %s::jsonb, 'SEALED', %s, %s
                )
                """,
                (
                    build.matrix_id,
                    build.family_id,
                    _json(build.matrix_core),
                    digest(build.matrix_core),
                    _json(build.benchmark_build_binding),
                    digest(build.benchmark_build_binding),
                    _json(build.registration),
                    build.registration_digest,
                    _json(list(range(1, 8))),
                    actor_id,
                    change_note,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_matrix_protocols (
                    matrix_id, family_id, matrix_revision,
                    protocol_core_json, protocol_core_digest
                ) VALUES (%s, %s, 1, %s::jsonb, %s)
                """,
                (
                    build.matrix_id,
                    build.family_id,
                    _json(build.protocol_core),
                    digest(build.protocol_core),
                ),
            )
            for slot in build.slots:
                version = slot["version_binding"]
                cursor.execute(
                    """
                    INSERT INTO backtest.atomic_entry_benchmark_slots (
                        matrix_id, family_id, slot_sequence, strategy_version_id,
                        hypothesis_spec_json, hypothesis_spec_digest,
                        version_binding_json, version_binding_digest,
                        hypothesis_id, slot_binding_json, slot_digest
                    ) VALUES (
                        %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s,
                        %s, %s::jsonb, %s
                    )
                    """,
                    (
                        build.matrix_id,
                        build.family_id,
                        slot["slot_sequence"],
                        version["strategy_version_id"],
                        _json(slot["hypothesis_spec"]),
                        slot["hypothesis_spec_digest"],
                        _json(version),
                        slot["version_binding_digest"],
                        slot["hypothesis_id"],
                        _json(slot["slot_binding"]),
                        slot["slot_digest"],
                    ),
                )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_releases (
                    family_id, matrix_id, matrix_revision, release_state
                ) VALUES (%s, %s, 1, 'NOT_READY')
                """,
                (build.family_id, build.matrix_id),
            )
            result = {
                "schema_version": "r6-matrix-seal-result-v1",
                "family_id": build.family_id,
                "matrix_id": build.matrix_id,
                "matrix_revision": 1,
                "registration_digest": build.registration_digest,
                "family_head_sequence": 0,
                "status": "SEALED",
            }
            operation_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_operations (
                    operation_id, family_id, matrix_id, attempt_id,
                    operation_type, idempotency_key, request_json,
                    request_digest, result_json, result_digest, actor_id
                ) VALUES (
                    %s, %s, %s, NULL, 'SEAL_MATRIX', %s, %s::jsonb,
                    %s, %s::jsonb, %s, %s
                )
                """,
                (
                    operation_id,
                    build.family_id,
                    build.matrix_id,
                    idempotency_key,
                    _json(request_body),
                    request_digest,
                    _json(result),
                    digest(result),
                    actor_id,
                ),
            )
            event = {
                "schema_version": "r6-benchmark-outbox-v1",
                "event_type": "MATRIX_SEALED",
                "family_id": build.family_id,
                "matrix_id": build.matrix_id,
                "registration_digest": build.registration_digest,
                "family_head_sequence": 0,
            }
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_outbox (
                    outbox_id, family_id, matrix_id, attempt_id, operation_id,
                    topic, payload_json, payload_digest
                ) VALUES (%s, %s, %s, NULL, %s, %s, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    build.family_id,
                    build.matrix_id,
                    operation_id,
                    "research.atomic-entry-benchmark.v1",
                    _json(event),
                    digest(event),
                ),
            )
            return result, False

    def activate_matrix_revision2(
        self,
        *,
        build: MatrixSealBuild,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        if digest(request_body) != request_digest:
            raise AtomicBenchmarkConflict("R6_MATRIX_REQUEST_DIGEST_CONFLICT")
        if (
            build.family_id != FAMILY_ID
            or build.matrix_core.get("matrix_revision") != 2
        ):
            raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")

        with self._transaction() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (self._advisory_lock_key("r6:matrix-seal", build.family_id),),
            )
            replay = self._operation_replay(
                cursor,
                family_id=build.family_id,
                operation_type="ACTIVATE_MATRIX_REVISION_2",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True

            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_families
                WHERE family_id = %s FOR UPDATE
                """,
                (build.family_id,),
            )
            raw_family = cursor.fetchone()
            if raw_family is None:
                raise AtomicBenchmarkConflict("R6_FAMILY_IDENTITY_CONFLICT")
            family_before = self._row(cursor, raw_family)
            matrix_v1 = self._verify_matrix(cursor, build.family_id)
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM backtest.atomic_entry_benchmark_attempts
                WHERE family_id = %s
                """,
                (build.family_id,),
            )
            attempt_count = int(cursor.fetchone()[0])
            if (
                matrix_v1["matrix_revision"] != 1
                or int(family_before["active_matrix_revision"]) != 1
                or int(family_before["head_sequence"]) != 0
                or attempt_count != 0
                or request_body.get("expected_active_matrix_revision") != 1
                or request_body.get("expected_family_head_sequence") != 0
                or request_body.get("expected_attempt_count") != 0
            ):
                raise AtomicBenchmarkConflict(
                    "R6_MATRIX_ACTIVATION_PRECONDITION_CONFLICT"
                )
            self._verify_source_run(cursor, build)
            self._verify_versions(cursor, build)

            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_matrices (
                    matrix_id, family_id, matrix_revision, matrix_core_json,
                    matrix_core_digest, benchmark_build_binding_json,
                    benchmark_build_binding_digest, registration_json,
                    registration_digest, registered_slots_json, status,
                    actor_id, change_note
                ) VALUES (
                    %s, %s, 2, %s::jsonb, %s, %s::jsonb, %s,
                    %s::jsonb, %s, %s::jsonb, 'SEALED', %s, %s
                )
                """,
                (
                    build.matrix_id,
                    build.family_id,
                    _json(build.matrix_core),
                    digest(build.matrix_core),
                    _json(build.benchmark_build_binding),
                    digest(build.benchmark_build_binding),
                    _json(build.registration),
                    build.registration_digest,
                    _json(list(range(1, 8))),
                    actor_id,
                    change_note,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_matrix_protocols (
                    matrix_id, family_id, matrix_revision,
                    protocol_core_json, protocol_core_digest
                ) VALUES (%s, %s, 2, %s::jsonb, %s)
                """,
                (
                    build.matrix_id,
                    build.family_id,
                    _json(build.protocol_core),
                    digest(build.protocol_core),
                ),
            )
            for slot in build.slots:
                version = slot["version_binding"]
                cursor.execute(
                    """
                    INSERT INTO backtest.atomic_entry_benchmark_slots (
                        matrix_id, family_id, slot_sequence, strategy_version_id,
                        hypothesis_spec_json, hypothesis_spec_digest,
                        version_binding_json, version_binding_digest,
                        hypothesis_id, slot_binding_json, slot_digest
                    ) VALUES (
                        %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s,
                        %s, %s::jsonb, %s
                    )
                    """,
                    (
                        build.matrix_id,
                        build.family_id,
                        slot["slot_sequence"],
                        version["strategy_version_id"],
                        _json(slot["hypothesis_spec"]),
                        slot["hypothesis_spec_digest"],
                        _json(version),
                        slot["version_binding_digest"],
                        slot["hypothesis_id"],
                        _json(slot["slot_binding"]),
                        slot["slot_digest"],
                    ),
                )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_releases (
                    family_id, matrix_id, matrix_revision, release_state
                ) VALUES (%s, %s, 2, 'NOT_READY')
                """,
                (build.family_id, build.matrix_id),
            )
            cursor.execute(
                """
                UPDATE backtest.atomic_entry_benchmark_families
                SET active_matrix_revision = 2, updated_at = CURRENT_TIMESTAMP
                WHERE family_id = %s
                  AND active_matrix_revision = 1
                  AND head_sequence = 0
                """,
                (build.family_id,),
            )
            if cursor.rowcount != 1:
                raise AtomicBenchmarkConflict(
                    "R6_MATRIX_ACTIVATION_PRECONDITION_CONFLICT"
                )
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_families
                WHERE family_id = %s
                """,
                (build.family_id,),
            )
            family_after = self._row(cursor, cursor.fetchone())
            allowed_changes = {"active_matrix_revision", "updated_at"}
            if any(
                family_before[field] != family_after[field]
                for field in family_before
                if field not in allowed_changes
            ):
                raise AtomicBenchmarkConflict("R6_FAMILY_IDENTITY_CONFLICT")
            result = {
                "schema_version": "r6-matrix-activate-result-v2",
                "family_id": build.family_id,
                "matrix_id": build.matrix_id,
                "matrix_revision": 2,
                "registration_digest": build.registration_digest,
                "previous_active_matrix_revision": 1,
                "active_matrix_revision": 2,
                "family_head_sequence": 0,
                "attempt_count": 0,
                "status": "SEALED",
            }
            self._insert_operation_outbox(
                cursor,
                family_id=build.family_id,
                matrix_id=build.matrix_id,
                attempt_id=None,
                operation_type="ACTIVATE_MATRIX_REVISION_2",
                idempotency_key=idempotency_key,
                request=request_body,
                request_digest=request_digest,
                result=result,
                actor_id=actor_id,
                event_type="MATRIX_REVISION_ACTIVATED",
            )
            return result, False

    def register_preflight(
        self,
        *,
        request: Mapping[str, Any],
        request_digest: str,
        manifest: Mapping[str, Any],
        artifact_locator: str,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        preflight = dict(manifest)
        if digest(request_body) != request_digest:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
        try:
            verified_artifact = verify_preflight_artifact(
                Path(artifact_locator), expected_manifest=preflight
            )
        except (OSError, ValueError) as error:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR") from error
        if verified_artifact.manifest != preflight:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
        family_id = str(request_body.get("family_id", ""))
        matrix_id = str(request_body.get("matrix_id", ""))
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (self._advisory_lock_key("r6:preflight", family_id),),
            )
            replay = self._operation_replay(
                cursor,
                family_id=family_id,
                operation_type="REGISTER_PREFLIGHT_V2",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_families
                WHERE family_id = %s FOR UPDATE
                """,
                (family_id,),
            )
            raw_family = cursor.fetchone()
            if raw_family is None:
                raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
            family = self._row(cursor, raw_family)
            matrix = self._verify_matrix(cursor, family_id)
            cursor.execute(
                "SELECT COUNT(*) FROM backtest.atomic_entry_benchmark_attempts WHERE family_id = %s",
                (family_id,),
            )
            attempt_count = int(cursor.fetchone()[0])
            if (
                matrix["matrix_id"] != matrix_id
                or matrix["matrix_revision"] != 2
                or int(family["active_matrix_revision"]) != 2
                or request_body.get("matrix_revision") != 2
                or request_body.get("expected_active_matrix_revision") != 2
            ):
                raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
            if int(family["head_sequence"]) != 0:
                raise AtomicBenchmarkConflict("R6_FAMILY_HEAD_SEQUENCE_CONFLICT")
            if attempt_count != 0:
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_ATTEMPT_COUNT_CONFLICT")
            cursor.execute(
                "SELECT preflight_registration_digest FROM backtest.atomic_entry_benchmark_preflights WHERE family_id = %s",
                (family_id,),
            )
            if cursor.fetchone() is not None:
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_ALREADY_ACCEPTED")
            cursor.execute(
                """
                SELECT registration_digest, benchmark_build_binding_json
                FROM backtest.atomic_entry_benchmark_matrices
                WHERE matrix_id = %s AND family_id = %s AND matrix_revision = 2
                FOR SHARE
                """,
                (matrix_id, family_id),
            )
            matrix_raw = cursor.fetchone()
            if matrix_raw is None:
                raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
            matrix_row = self._row(cursor, matrix_raw)
            build_binding = _decoded(
                matrix_row["benchmark_build_binding_json"], "benchmark_build_binding"
            )
            baseline = _decoded(family["research_baseline_json"], "research_baseline")
            cursor.execute(
                """
                SELECT slot_sequence, hypothesis_id, strategy_version_id,
                       hypothesis_spec_json, version_binding_json
                FROM backtest.atomic_entry_benchmark_slots
                WHERE matrix_id = %s AND family_id = %s
                ORDER BY slot_sequence
                """,
                (matrix_id, family_id),
            )
            matrix_slots = [self._row(cursor, raw) for raw in cursor.fetchall()]
            preflight_slots = preflight.get("slots")
            slot_roots_valid = self._preflight_slot_bindings_valid(
                preflight_slots=preflight_slots,
                matrix_slots=matrix_slots,
                artifact_slot_manifests=list(
                    verified_artifact.slot_manifests
                ),
                eligibility_manifest_digest=preflight.get(
                    "eligibility_manifest_digest"
                ),
            )
            expected_manifest_fields = {
                "schema_version", "family_id", "matrix_id", "matrix_revision",
                "registration_digest", "research_baseline_digest", "dataset_id",
                "dataset_digest", "dataset_bars_sha256", "dataset_bar_count",
                "dataset_binding_revision", "source_bar_count", "source_bars_sha256",
                "source_eof_verified", "protocol_core_digest",
                "algorithm_contract_digest", "algorithm_implementation_digest",
                "preflight_implementation_digest", "eligibility_manifest_digest",
                "slots", "preflight_digest",
            }
            preflight_body = {
                key: value for key, value in preflight.items() if key != "preflight_digest"
            }
            if (
                frozenset(preflight) != expected_manifest_fields
                or preflight.get("schema_version") != "r6-preflight-manifest-v2"
                or preflight.get("family_id") != family_id
                or preflight.get("matrix_id") != matrix_id
                or preflight.get("matrix_revision") != 2
                or preflight.get("registration_digest") != matrix["registration_digest"]
                or preflight.get("research_baseline_digest")
                != family["research_baseline_digest"]
                or preflight.get("protocol_core_digest")
                != matrix["protocol_core_digest"]
                or preflight.get("dataset_id") != baseline.get("dataset_id")
                or preflight.get("dataset_digest")
                != baseline.get("dataset_manifest_digest")
                or preflight.get("dataset_bars_sha256")
                != baseline.get("dataset_bars_sha256")
                or preflight.get("dataset_binding_revision")
                != baseline.get("dataset_binding_revision")
                or digest(preflight_body) != preflight.get("preflight_digest")
                or preflight.get("source_eof_verified") is not True
                or preflight.get("source_bar_count") != preflight.get("dataset_bar_count")
                or preflight.get("source_bars_sha256")
                != preflight.get("dataset_bars_sha256")
                or preflight.get("preflight_implementation_digest")
                != build_binding.get("preflight_implementation_digest")
                or preflight.get("algorithm_implementation_digest")
                != build_binding.get("algorithm_implementation_digest")
                or not slot_roots_valid
            ):
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
            preflight_digest = str(preflight["preflight_digest"])
            registration = {
                "schema_version": "r6-preflight-registration-v1",
                "preflight_id": f"r6-preflight-sha256-{preflight_digest}",
                "family_id": family_id,
                "matrix_id": matrix_id,
                "matrix_revision": 2,
                "matrix_registration_digest": matrix["registration_digest"],
                "protocol_core_digest": preflight["protocol_core_digest"],
                "dataset_id": preflight["dataset_id"],
                "dataset_digest": preflight["dataset_digest"],
                "dataset_bars_sha256": preflight["dataset_bars_sha256"],
                "dataset_binding_revision": preflight["dataset_binding_revision"],
                "eligibility_manifest_digest": preflight[
                    "eligibility_manifest_digest"
                ],
                "preflight_digest": preflight_digest,
                "preflight_implementation_digest": preflight[
                    "preflight_implementation_digest"
                ],
                "status": "ACCEPTED",
            }
            registration_digest = digest(registration)
            if (
                request_body.get("preflight_id") != registration["preflight_id"]
                or request_body.get("preflight_digest") != preflight_digest
                or request_body.get("eligibility_manifest_digest")
                != registration["eligibility_manifest_digest"]
                or request_body.get("preflight_registration_digest")
                != registration_digest
            ):
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
            result = {
                "schema_version": "r6-preflight-register-result-v1",
                "family_id": family_id,
                "matrix_id": matrix_id,
                "matrix_revision": 2,
                "preflight_id": registration["preflight_id"],
                "preflight_digest": preflight_digest,
                "eligibility_manifest_digest": registration[
                    "eligibility_manifest_digest"
                ],
                "preflight_registration_digest": registration_digest,
                "status": "ACCEPTED",
                "family_head_sequence": 0,
                "attempt_count": 0,
            }
            operation_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_operations (
                    operation_id, family_id, matrix_id, attempt_id,
                    operation_type, idempotency_key, request_json,
                    request_digest, result_json, result_digest, actor_id
                ) VALUES (
                    %s, %s, %s, NULL, 'REGISTER_PREFLIGHT_V2', %s,
                    %s::jsonb, %s, %s::jsonb, %s, %s
                )
                """,
                (
                    operation_id, family_id, matrix_id, idempotency_key,
                    _json(request_body), request_digest, _json(result),
                    digest(result), actor_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_preflights (
                    preflight_id, family_id, matrix_id, matrix_revision,
                    preflight_json, preflight_digest,
                    eligibility_manifest_digest, preflight_registration_json,
                    preflight_registration_digest, status, operation_id,
                    artifact_locator, actor_id, change_note
                ) VALUES (
                    %s, %s, %s, 2, %s::jsonb, %s, %s, %s::jsonb, %s,
                    'ACCEPTED', %s, %s, %s, %s
                )
                """,
                (
                    registration["preflight_id"], family_id, matrix_id,
                    _json(preflight), preflight_digest,
                    registration["eligibility_manifest_digest"],
                    _json(registration), registration_digest, operation_id,
                    artifact_locator, actor_id, change_note,
                ),
            )
            event = self._operation_outbox_event(
                operation_type="REGISTER_PREFLIGHT_V2",
                event_type="ATOMIC_ENTRY_BENCHMARK_PREFLIGHT_ACCEPTED",
                result=result,
            )
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_outbox (
                    outbox_id, family_id, matrix_id, attempt_id, operation_id,
                    topic, payload_json, payload_digest
                ) VALUES (%s, %s, %s, NULL, %s, %s, %s::jsonb, %s)
                """,
                (
                    str(uuid4()), family_id, matrix_id, operation_id,
                    _OPERATION_OUTBOX_TOPIC, _json(event), digest(event),
                ),
            )
            return result, False

    def get_matrix(self, family_id: str) -> dict[str, Any]:
        with self._transaction(read_only=True) as cursor:
            return self._verify_matrix(cursor, family_id)

    def get_preflight_context(self, family_id: str) -> dict[str, Any]:
        """Rebuild the sealed matrix plus exact Dataset authority for G3."""

        with self._transaction(read_only=True) as cursor:
            matrix = self._verify_matrix(cursor, family_id)
            cursor.execute(
                """
                SELECT family.research_baseline_json,
                       family.research_baseline_digest,
                       protocol.protocol_core_json,
                       protocol.protocol_core_digest,
                       family.head_sequence,
                       matrix.benchmark_build_binding_json,
                       matrix.benchmark_build_binding_digest,
                       matrix.registration_json,
                       matrix.registration_digest
                FROM backtest.atomic_entry_benchmark_families AS family
                JOIN backtest.atomic_entry_benchmark_matrices AS matrix
                  ON matrix.family_id = family.family_id
                 AND matrix.matrix_revision = family.active_matrix_revision
                JOIN backtest.atomic_entry_benchmark_matrix_protocols AS protocol
                  ON protocol.matrix_id = matrix.matrix_id
                 AND protocol.family_id = matrix.family_id
                 AND protocol.matrix_revision = matrix.matrix_revision
                WHERE family.family_id = %s
                """,
                (family_id,),
            )
            row = self._row(cursor, cursor.fetchone())
            baseline = _decoded(row["research_baseline_json"], "research_baseline")
            protocol = _decoded(row["protocol_core_json"], "protocol_core")
            build_binding = _decoded(
                row["benchmark_build_binding_json"], "benchmark_build_binding"
            )
            registration = _decoded(row["registration_json"], "registration")
            if not all(
                isinstance(value, dict)
                for value in (baseline, protocol, build_binding, registration)
            ):
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_CONTEXT_INTEGRITY_ERROR")
            cursor.execute(
                """
                SELECT slot_sequence, strategy_version_id,
                       hypothesis_spec_json, hypothesis_spec_digest,
                       version_binding_json, version_binding_digest,
                       hypothesis_id, slot_binding_json, slot_digest
                FROM backtest.atomic_entry_benchmark_slots
                WHERE family_id = %s AND matrix_id = %s
                ORDER BY slot_sequence
                """,
                (family_id, matrix["matrix_id"]),
            )
            slots = []
            for raw_slot in cursor.fetchall():
                stored = self._row(cursor, raw_slot)
                hypothesis_spec = _decoded(
                    stored["hypothesis_spec_json"], "hypothesis_spec"
                )
                version_binding = _decoded(
                    stored["version_binding_json"], "version_binding"
                )
                slot_binding = _decoded(stored["slot_binding_json"], "slot_binding")
                if not all(
                    isinstance(value, dict)
                    for value in (hypothesis_spec, version_binding, slot_binding)
                ):
                    raise AtomicBenchmarkConflict(
                        "R6_PREFLIGHT_CONTEXT_INTEGRITY_ERROR"
                    )
                slots.append(
                    {
                        "slot_sequence": int(stored["slot_sequence"]),
                        "strategy_version_id": str(stored["strategy_version_id"]),
                        "hypothesis_spec": hypothesis_spec,
                        "hypothesis_spec_digest": str(
                            stored["hypothesis_spec_digest"]
                        ),
                        "version_binding": version_binding,
                        "version_binding_digest": str(
                            stored["version_binding_digest"]
                        ),
                        "hypothesis_id": str(stored["hypothesis_id"]),
                        "slot_binding": slot_binding,
                        "slot_digest": str(stored["slot_digest"]),
                    }
                )
            cursor.execute(
                """
                SELECT COUNT(*) FROM backtest.atomic_entry_benchmark_attempts
                WHERE family_id = %s
                """,
                (family_id,),
            )
            attempt_count = int(cursor.fetchone()[0])
            dataset_id = str(baseline["dataset_id"])
            cursor.execute(
                """
                SELECT dataset.status, dataset.manifest_json,
                       binding.dataset_id AS binding_dataset_id,
                       binding.dataset_digest AS binding_dataset_digest,
                       binding.revision AS binding_revision
                FROM backtest.backtest_datasets AS dataset
                JOIN backtest.backtest_dataset_bindings AS binding
                  ON binding.dataset_id = dataset.dataset_id
                WHERE dataset.dataset_id = %s AND binding.binding_name = %s
                """,
                (dataset_id, ATOMIC_BACKTEST_DEFAULT),
            )
            dataset_raw = cursor.fetchone()
            if dataset_raw is None:
                raise AtomicBenchmarkConflict("R6_DATASET_IDENTITY_REJECTED")
            dataset_row = self._row(cursor, dataset_raw)
            registered_manifest = canonical_registration_manifest(
                _decoded(dataset_row["manifest_json"], "dataset_manifest")
            )
            if (
                len(slots) != 7
                or tuple(item["slot_sequence"] for item in slots)
                != tuple(range(1, 8))
                or int(row["head_sequence"]) != 0
                or matrix["family_head_sequence"] != 0
                or attempt_count != 0
                or dataset_row["status"] != "READY"
                or dataset_row["binding_dataset_id"] != dataset_id
                or dataset_row["binding_dataset_digest"]
                != baseline["dataset_manifest_digest"]
                or int(dataset_row["binding_revision"])
                != int(baseline["dataset_binding_revision"])
                or registered_manifest["dataset_id"] != dataset_id
                or registered_manifest["manifest_digest"]
                != baseline["dataset_manifest_digest"]
                or registered_manifest["bars_sha256"]
                != baseline["dataset_bars_sha256"]
                or int(registered_manifest["bar_count"])
                != int(baseline["dataset_bar_count"])
                or digest(baseline) != row["research_baseline_digest"]
                or digest(protocol) != row["protocol_core_digest"]
                or digest(build_binding)
                != row["benchmark_build_binding_digest"]
                or digest(registration) != row["registration_digest"]
                or matrix["matrix_revision"] != 2
                or build_binding.get("schema_version")
                != "r6-benchmark-build-binding-v2"
            ):
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_CONTEXT_INTEGRITY_ERROR")
            return {
                "schema_version": "r6-preflight-context-v2",
                "family_id": family_id,
                "matrix_id": matrix["matrix_id"],
                "matrix_revision": 2,
                "registration_digest": matrix["registration_digest"],
                "research_baseline": baseline,
                "research_baseline_digest": str(row["research_baseline_digest"]),
                "protocol_core": protocol,
                "protocol_core_digest": str(row["protocol_core_digest"]),
                "benchmark_build_binding": build_binding,
                "registered_manifest": registered_manifest,
                "slots": slots,
                "family_head_sequence": 0,
                "attempt_count": 0,
            }

    def start_next_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        expected_family_head_sequence: int,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        if digest(request_body) != request_digest:
            raise AtomicBenchmarkConflict("R6_ATTEMPT_REQUEST_DIGEST_CONFLICT")
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (self._advisory_lock_key("r6:attempt", family_id),),
            )
            replay = self._operation_replay(
                cursor,
                family_id=family_id,
                operation_type="START_ATTEMPT",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True
            matrix = self._verify_matrix(cursor, family_id)
            if matrix["matrix_id"] != matrix_id:
                raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_families
                WHERE family_id = %s FOR UPDATE
                """,
                (family_id,),
            )
            family = self._row(cursor, cursor.fetchone())
            head = int(family["head_sequence"])
            if head != expected_family_head_sequence or head >= 7:
                raise AtomicBenchmarkConflict("R6_FAMILY_HEAD_SEQUENCE_CONFLICT")
            if family["release_state"] == "BLOCKED_FINAL":
                raise AtomicBenchmarkConflict("R6_FAMILY_BLOCKED_FINAL")
            if matrix["matrix_revision"] != 2:
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_NOT_ACCEPTED")
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_preflights
                WHERE family_id = %s AND matrix_id = %s AND matrix_revision = 2
                  AND status = 'ACCEPTED'
                FOR SHARE
                """,
                (family_id, matrix_id),
            )
            preflight_raw = cursor.fetchone()
            if preflight_raw is None:
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_NOT_ACCEPTED")
            preflight = self._row(cursor, preflight_raw)
            preflight_registration = _decoded(
                preflight["preflight_registration_json"],
                "preflight_registration",
            )
            stored_preflight_manifest = _decoded(
                preflight["preflight_json"], "preflight_manifest"
            )
            try:
                verified_preflight = verify_preflight_artifact(
                    Path(str(preflight["artifact_locator"])),
                    expected_manifest=stored_preflight_manifest,
                )
            except (OSError, ValueError) as error:
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_NOT_ACCEPTED") from error
            current_preflight_digest = preflight_implementation_digest(
                Path(__file__).resolve().parents[2]
            )
            if (
                digest(preflight_registration)
                != preflight["preflight_registration_digest"]
                or request_body.get("expected_preflight_id")
                != preflight["preflight_id"]
                or request_body.get("expected_preflight_registration_digest")
                != preflight["preflight_registration_digest"]
                or verified_preflight.manifest != stored_preflight_manifest
                or preflight_registration.get("preflight_implementation_digest")
                != current_preflight_digest
            ):
                raise AtomicBenchmarkConflict("R6_PREFLIGHT_NOT_ACCEPTED")
            slot_sequence = head + 1
            cursor.execute(
                """
                SELECT hypothesis_id FROM backtest.atomic_entry_benchmark_slots
                WHERE matrix_id = %s AND slot_sequence = %s
                """,
                (matrix_id, slot_sequence),
            )
            slot = cursor.fetchone()
            if slot is None:
                raise AtomicBenchmarkConflict("R6_SLOT_UNAVAILABLE")
            attempt_id = f"r6-attempt-{uuid4().hex}"
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_attempts (
                    attempt_id, family_id, matrix_id, attempt_sequence,
                    slot_sequence, hypothesis_id, request_json, request_digest,
                    status, attempt_revision, retry_generation, progress,
                    integrity_status, integrity_diagnostic_codes_json,
                    preflight_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                    'RUNNING', 1, 1, 0, 'PENDING', '[]'::jsonb, %s
                )
                """,
                (
                    attempt_id,
                    family_id,
                    matrix_id,
                    slot_sequence,
                    slot_sequence,
                    slot[0],
                    _json(request_body),
                    request_digest,
                    preflight["preflight_id"],
                ),
            )
            cursor.execute(
                """
                UPDATE backtest.atomic_entry_benchmark_families
                SET head_sequence = %s, updated_at = CURRENT_TIMESTAMP
                WHERE family_id = %s AND head_sequence = %s
                """,
                (slot_sequence, family_id, head),
            )
            if cursor.rowcount != 1:
                raise AtomicBenchmarkConflict("R6_FAMILY_HEAD_SEQUENCE_CONFLICT")
            result = {
                "schema_version": "r6-attempt-start-result-v1",
                "family_id": family_id,
                "matrix_id": matrix_id,
                "attempt_id": attempt_id,
                "slot_sequence": slot_sequence,
                "attempt_sequence": slot_sequence,
                "status": "RUNNING",
                "attempt_revision": 1,
                "retry_generation": 1,
                "family_head_sequence": slot_sequence,
            }
            self._insert_operation_outbox(
                cursor,
                family_id=family_id,
                matrix_id=matrix_id,
                attempt_id=attempt_id,
                operation_type="START_ATTEMPT",
                idempotency_key=idempotency_key,
                request=request_body,
                request_digest=request_digest,
                result=result,
                actor_id=actor_id,
                event_type="ATTEMPT_STARTED",
            )
            return result, False

    def transition_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        expected_status: str,
        next_status: str,
        retry_generation: int,
        outcome_code: str,
        progress: str | None,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        request_body = dict(request)
        if digest(request_body) != request_digest:
            raise AtomicBenchmarkConflict("R6_ATTEMPT_REQUEST_DIGEST_CONFLICT")
        if next_status == "ACCEPTED":
            raise AtomicBenchmarkConflict("R6_ACCEPTED_REQUIRES_G4_POSTFLIGHT")
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (self._advisory_lock_key("r6:attempt", family_id),),
            )
            replay = self._operation_replay(
                cursor,
                family_id=family_id,
                operation_type="TRANSITION_ATTEMPT",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if replay is not None:
                return replay, True
            matrix = self._verify_matrix(cursor, family_id)
            if matrix["matrix_id"] != matrix_id:
                raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_attempts
                WHERE attempt_id = %s AND family_id = %s AND matrix_id = %s
                FOR UPDATE
                """,
                (attempt_id, family_id, matrix_id),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(attempt_id)
            current = self._row(cursor, raw)
            if (
                int(current["attempt_revision"]) != expected_revision
                or str(current["status"]) != expected_status
                or int(current["retry_generation"]) != retry_generation
            ):
                raise AtomicBenchmarkConflict("R6_ATTEMPT_REVISION_STATUS_CONFLICT")
            next_generation = validate_attempt_transition(
                current_status=expected_status,
                next_status=next_status,
                retry_generation=retry_generation,
                outcome_code=outcome_code,
            )
            progress_value = (
                str(current["progress"])
                if progress is None
                else str(max(current["progress"], type(current["progress"])(progress)))
            )
            terminal = next_status in {
                "CANCELLED_RETRYABLE",
                "CANCELLED_FINAL",
                "FAILED_RETRYABLE",
                "FAILED_FINAL",
                "REJECTED_FINAL",
            }
            cursor.execute(
                """
                UPDATE backtest.atomic_entry_benchmark_attempts
                SET status = %s,
                    attempt_revision = attempt_revision + 1,
                    retry_generation = %s,
                    progress = GREATEST(progress, %s::numeric),
                    failure_code = CASE WHEN %s THEN %s ELSE NULL END,
                    integrity_status = CASE
                        WHEN %s = 'REJECTED_FINAL' THEN 'REJECTED'
                        ELSE integrity_status
                    END,
                    terminal_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE attempt_id = %s AND attempt_revision = %s AND status = %s
                """,
                (
                    next_status,
                    next_generation,
                    progress_value,
                    terminal,
                    outcome_code,
                    next_status,
                    terminal,
                    attempt_id,
                    expected_revision,
                    expected_status,
                ),
            )
            if cursor.rowcount != 1:
                raise AtomicBenchmarkConflict("R6_ATTEMPT_REVISION_STATUS_CONFLICT")
            new_revision = expected_revision + 1
            result = {
                "schema_version": "r6-attempt-transition-result-v1",
                "family_id": family_id,
                "matrix_id": matrix_id,
                "attempt_id": attempt_id,
                "status": next_status,
                "attempt_revision": new_revision,
                "retry_generation": next_generation,
                "progress": progress_value,
                "outcome_code": outcome_code,
            }
            operation_id = self._insert_operation_outbox(
                cursor,
                family_id=family_id,
                matrix_id=matrix_id,
                attempt_id=attempt_id,
                operation_type="TRANSITION_ATTEMPT",
                idempotency_key=idempotency_key,
                request=request_body,
                request_digest=request_digest,
                result=result,
                actor_id=actor_id,
                event_type=outcome_code,
            )
            transition_evidence = {
                "schema_version": "r6-attempt-transition-evidence-v1",
                "operation_id": operation_id,
                "family_id": family_id,
                "matrix_id": matrix_id,
                "attempt_id": attempt_id,
                "from_revision": expected_revision,
                "to_revision": new_revision,
                "from_status": expected_status,
                "to_status": next_status,
                "retry_generation": retry_generation,
                "next_retry_generation": next_generation,
                "from_progress": str(current["progress"]),
                "requested_progress": progress,
                "result_progress": progress_value,
                "outcome_code": outcome_code,
                "request_digest": request_digest,
                "result_digest": digest(result),
            }
            cursor.execute(
                """
                INSERT INTO backtest.atomic_entry_benchmark_transition_evidence (
                    operation_id, family_id, matrix_id, attempt_id,
                    from_revision, to_revision, from_status, to_status,
                    retry_generation, next_retry_generation, from_progress,
                    requested_progress, result_progress, outcome_code,
                    evidence_json, evidence_digest
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::numeric, %s::numeric, %s::numeric, %s, %s::jsonb, %s
                )
                """,
                (
                    operation_id, family_id, matrix_id, attempt_id,
                    expected_revision, new_revision, expected_status, next_status,
                    retry_generation, next_generation, str(current["progress"]),
                    progress, progress_value, outcome_code,
                    _json(transition_evidence), digest(transition_evidence),
                ),
            )
            if next_status in {"CANCELLED_FINAL", "FAILED_FINAL", "REJECTED_FINAL"}:
                cursor.execute(
                    """
                    UPDATE backtest.atomic_entry_benchmark_families
                    SET release_state = 'BLOCKED_FINAL', updated_at = CURRENT_TIMESTAMP
                    WHERE family_id = %s
                    """,
                    (family_id,),
                )
                cursor.execute(
                    """
                    UPDATE backtest.atomic_entry_benchmark_releases
                    SET release_state = 'BLOCKED_FINAL'
                    WHERE family_id = %s AND matrix_revision = %s
                    """,
                    (family_id, matrix["matrix_revision"]),
                )
            return result, False

    def get_family_visibility(self, family_id: str) -> dict[str, Any]:
        with self._transaction(read_only=True) as cursor:
            matrix = self._verify_matrix(cursor, family_id)
            cursor.execute(
                """
                SELECT family.release_state, attempt.*
                FROM backtest.atomic_entry_benchmark_families AS family
                LEFT JOIN backtest.atomic_entry_benchmark_attempts AS attempt
                  ON attempt.family_id = family.family_id
                WHERE family.family_id = %s
                ORDER BY attempt.slot_sequence
                """,
                (family_id,),
            )
            rows = [self._row(cursor, row) for row in cursor.fetchall()]
        release_state = str(rows[0]["release_state"]) if rows else "NOT_READY"
        attempts = []
        for row in rows:
            if row.get("attempt_id") is None:
                continue
            try:
                codes = verify_integrity_diagnostic_codes(
                    _decoded(
                        row["integrity_diagnostic_codes_json"],
                        "diagnostic_codes",
                    )
                )
            except ValueError as error:
                raise AtomicBenchmarkConflict(
                    "R6_REDACTED_PROJECTION_INTEGRITY_ERROR"
                ) from error

            attempts.append(
                {
                    "schema_version": "r6-redacted-attempt-status-v1",
                    "family_id": family_id,
                    "matrix_id": matrix["matrix_id"],
                    "slot_sequence": int(row["slot_sequence"]),
                    "attempt_id": str(row["attempt_id"]),
                    "status": str(row["status"]),
                    "attempt_revision": int(row["attempt_revision"]),
                    "retry_generation": int(row["retry_generation"]),
                    "progress": str(row["progress"]),
                    "integrity_status": str(row["integrity_status"]),
                    "integrity_diagnostic_codes": codes,
                }
            )
        return {
            "schema_version": "r6-family-visibility-v1",
            "family_id": family_id,
            "matrix_id": matrix["matrix_id"],
            "registration_digest": matrix["registration_digest"],
            "release_state": release_state,
            "attempts": attempts,
        }

    def get_verified_public_bundle(self, family_id: str) -> dict[str, Any] | None:
        # G2 has no public bundle materializer.  RELEASED without the G5 adapter
        # is an integrity error and must remain invisible.
        return None

    def _verify_matrix(
        self,
        cursor: Any,
        family_id: str,
        *,
        matrix_id: str | None = None,
    ) -> dict[str, Any]:
        matrix_selector = (
            "matrix.matrix_id = %s"
            if matrix_id is not None
            else "matrix.matrix_revision = family.active_matrix_revision"
        )
        cursor.execute(
            f"""
            SELECT family.*, matrix.*,
                   protocol.protocol_core_json AS matrix_protocol_core_json,
                   protocol.protocol_core_digest AS matrix_protocol_core_digest
            FROM backtest.atomic_entry_benchmark_families AS family
            JOIN backtest.atomic_entry_benchmark_matrices AS matrix
              ON matrix.family_id = family.family_id
             AND {matrix_selector}
            JOIN backtest.atomic_entry_benchmark_matrix_protocols AS protocol
              ON protocol.matrix_id = matrix.matrix_id
             AND protocol.family_id = matrix.family_id
             AND protocol.matrix_revision = matrix.matrix_revision
            WHERE family.family_id = %s
            """,
            ((matrix_id, family_id) if matrix_id is not None else (family_id,)),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise KeyError(family_id)
        row = self._row(cursor, raw)
        baseline = _decoded(row["research_baseline_json"], "research_baseline")
        protocol = _decoded(
            row["matrix_protocol_core_json"], "matrix_protocol_core"
        )
        build_binding = _decoded(
            row["benchmark_build_binding_json"], "benchmark_build_binding"
        )
        cursor.execute(
            """
            SELECT * FROM backtest.atomic_entry_benchmark_slots
            WHERE matrix_id = %s ORDER BY slot_sequence
            """,
            (row["matrix_id"],),
        )
        slot_rows = [self._row(cursor, value) for value in cursor.fetchall()]
        slot_inputs = [
            {
                "hypothesis_spec": _decoded(value["hypothesis_spec_json"], "hypothesis_spec"),
                "version_binding": _decoded(value["version_binding_json"], "version_binding"),
            }
            for value in slot_rows
        ]
        rebuilt = build_matrix_seal(
            research_baseline=baseline,
            protocol_core=protocol,
            benchmark_build_binding=build_binding,
            slot_inputs=slot_inputs,
        )
        stored_matrix = _decoded(row["matrix_core_json"], "matrix_core")
        stored_registration = _decoded(row["registration_json"], "registration")
        registered_slots = _decoded(row["registered_slots_json"], "registered_slots")
        cursor.execute(
            """
            SELECT matrix_id, release_state
            FROM backtest.atomic_entry_benchmark_releases
            WHERE family_id = %s AND matrix_revision = %s
            """,
            (family_id, int(row["matrix_revision"])),
        )
        release_raw = cursor.fetchone()
        release = self._row(cursor, release_raw) if release_raw is not None else None
        for expected_slot, stored_slot in zip(
            rebuilt.slots, slot_rows, strict=True
        ):
            if (
                int(stored_slot["slot_sequence"]) != expected_slot["slot_sequence"]
                or stored_slot["hypothesis_spec_digest"]
                != expected_slot["hypothesis_spec_digest"]
                or stored_slot["version_binding_digest"]
                != expected_slot["version_binding_digest"]
                or stored_slot["hypothesis_id"] != expected_slot["hypothesis_id"]
                or _decoded(stored_slot["slot_binding_json"], "slot_binding")
                != expected_slot["slot_binding"]
                or stored_slot["slot_digest"] != expected_slot["slot_digest"]
            ):
                raise AtomicBenchmarkConflict("R6_MATRIX_INTEGRITY_ERROR")
        if (
            rebuilt.matrix_id != str(row["matrix_id"])
            or rebuilt.matrix_core != stored_matrix
            or digest(stored_matrix) != str(row["matrix_core_digest"])
            or rebuilt.registration != stored_registration
            or rebuilt.registration_digest != str(row["registration_digest"])
            or digest(baseline) != str(row["research_baseline_digest"])
            or digest(protocol) != str(row["matrix_protocol_core_digest"])
            or digest(build_binding)
            != str(row["benchmark_build_binding_digest"])
            or registered_slots != list(range(1, 8))
            or int(row["planned_attempts"]) != 20
            or str(row["family_alpha"]) not in {"0.05", "0.050000"}
            or str(row["adjustment_method"]) != "BONFERRONI"
            or (
                matrix_id is None
                and int(row["active_matrix_revision"])
                != int(rebuilt.matrix_core["matrix_revision"])
            )
            or release is None
            or release["matrix_id"] != rebuilt.matrix_id
            or (
                matrix_id is None
                and release["release_state"] != row["release_state"]
            )
            or len(slot_rows) != 7
        ):
            raise AtomicBenchmarkConflict("R6_MATRIX_INTEGRITY_ERROR")
        return {
            "family_id": family_id,
            "matrix_id": rebuilt.matrix_id,
            "matrix_revision": int(rebuilt.matrix_core["matrix_revision"]),
            "registration_digest": rebuilt.registration_digest,
            "protocol_core_digest": digest(protocol),
            "benchmark_build_binding": build_binding,
            "family_head_sequence": int(row["head_sequence"]),
            "release_state": str(release["release_state"]),
            "status": str(row["status"]),
        }

    def _verify_source_run(self, cursor: Any, build: MatrixSealBuild) -> None:
        cursor.execute(
            """
            SELECT run_id, status, config_json, config_digest,
                   dataset_id, dataset_digest
            FROM backtest.backtest_runs WHERE run_id = %s FOR SHARE
            """,
            (build.research_baseline["source_lineage_run_id"],),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise AtomicBenchmarkConflict("R6_SOURCE_LINEAGE_RUN_INVALID")
        row = self._row(cursor, raw)
        config = _decoded(row["config_json"], "source_run_config")
        if (
            str(row["status"]) != "COMPLETED"
            or digest(config) != str(row["config_digest"])
            or str(row["dataset_id"]) != build.research_baseline["dataset_id"]
            or str(row["dataset_digest"])
            != build.research_baseline["dataset_manifest_digest"]
        ):
            raise AtomicBenchmarkConflict("R6_SOURCE_LINEAGE_RUN_INVALID")

    def _verify_versions(self, cursor: Any, build: MatrixSealBuild) -> None:
        registry = AtomicStrategyRegistry()
        for slot in build.slots:
            expected = slot["version_binding"]
            cursor.execute(
                """
                SELECT
                    version.strategy_version_id AS version_id,
                    version.strategy_id AS version_strategy_id,
                    version.source_draft_id,
                    version.version_number,
                    version.parameters_json AS version_parameters_json,
                    version.parameter_schema_version,
                    version.parameter_schema_digest,
                    version.parameters_digest AS version_parameters_digest,
                    version.template_digest,
                    version.implementation_digest,
                    version.configuration_digest,
                    version.change_note AS version_change_note,
                    version.created_by AS version_created_by,
                    stored_template.template_digest AS stored_template_digest,
                    stored_template.implementation_digest AS stored_implementation_digest,
                    stored_template.parameter_schema_version AS stored_schema_version,
                    stored_template.parameter_schema_digest AS stored_schema_digest,
                    draft.draft_id,
                    draft.strategy_id AS draft_strategy_id,
                    draft.revision AS draft_revision,
                    draft.parameters_json AS draft_parameters_json,
                    draft.parameters_digest AS draft_parameters_digest,
                    draft.change_note AS draft_change_note,
                    draft.created_by AS draft_created_by,
                    draft.updated_by AS draft_updated_by,
                    draft.published_strategy_version_id,
                    draft.published_event_id AS draft_published_event_id,
                    draft.published_operation_id AS draft_published_operation_id,
                    draft.published_at AS draft_published_at,
                    state.status AS lifecycle_status,
                    state.last_sequence AS lifecycle_sequence,
                    state.last_event_id AS lifecycle_event_id,
                    state.projection_digest AS lifecycle_projection_digest,
                    event.sequence AS event_sequence,
                    event.event_type,
                    event.from_status,
                    event.to_status,
                    event.evidence_json,
                    event.evidence_digest,
                    event.reason AS event_reason,
                    event.actor_id AS event_actor_id,
                    event.actor_session_id AS event_actor_session_id,
                    event.idempotency_key AS event_idempotency_key,
                    event.request_digest AS event_request_digest,
                    event.expected_sequence AS event_expected_sequence,
                    event.occurred_at AS event_occurred_at,
                    event.event_digest,
                    operation.publish_operation_id,
                    operation.idempotency_key AS operation_idempotency_key,
                    operation.request_digest AS operation_request_digest,
                    operation.expected_draft_revision,
                    operation.strategy_version_id AS operation_version_id,
                    operation.published_event_id AS operation_event_id,
                    operation.result_digest AS publish_result_digest,
                    outbox.outbox_id,
                    outbox.event_digest AS outbox_event_digest,
                    outbox.topic AS outbox_topic,
                    outbox.payload_json AS outbox_payload_json,
                    outbox.payload_digest AS outbox_payload_digest
                FROM backtest.strategy_versions AS version
                JOIN backtest.strategy_templates AS stored_template
                  ON stored_template.strategy_id = version.strategy_id
                JOIN backtest.strategy_version_drafts AS draft
                  ON draft.draft_id = version.source_draft_id
                JOIN backtest.strategy_version_state AS state
                  ON state.strategy_version_id = version.strategy_version_id
                JOIN backtest.strategy_version_events AS event
                  ON event.event_id = state.last_event_id
                JOIN backtest.strategy_publish_operations AS operation
                  ON operation.strategy_version_id = version.strategy_version_id
                JOIN backtest.strategy_lifecycle_outbox AS outbox
                  ON outbox.event_id = event.event_id
                 AND outbox.topic = 'strategy.lifecycle.v1'
                WHERE version.strategy_version_id = %s
                FOR SHARE OF version, stored_template, draft, state, event,
                             operation, outbox
                """,
                (expected["strategy_version_id"],),
            )
            rows = [self._row(cursor, raw) for raw in cursor.fetchall()]
            if len(rows) != 1:
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")
            row = rows[0]
            specification = slot["hypothesis_spec"]
            strategy_id = str(specification["strategy_id"])
            template = registry.strategy(strategy_id).template
            parameters = _decoded(row["version_parameters_json"], "parameters")
            if not isinstance(parameters, dict):
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")
            canonical_parameters = template.validate_parameters(parameters)
            configuration = {
                "strategy_id": str(row["version_strategy_id"]),
                "parameters": parameters,
                "parameter_schema_version": row["parameter_schema_version"],
                "parameter_schema_digest": row["parameter_schema_digest"],
                "parameters_digest": row["version_parameters_digest"],
                "template_digest": row["template_digest"],
                "implementation_digest": row["implementation_digest"],
            }
            expected_configuration = {
                "strategy_id": strategy_id,
                "parameters": canonical_parameters,
                "parameter_schema_version": template.parameter_schema.version,
                "parameter_schema_digest": template.parameter_schema.schema_digest,
                "parameters_digest": canonical_digest(canonical_parameters),
                "template_digest": template.template_digest,
                "implementation_digest": template.implementation_digest,
            }
            rebuilt_configuration_digest = canonical_digest(configuration)
            if (
                parameters != canonical_parameters
                or configuration != expected_configuration
                or rebuilt_configuration_digest != row["configuration_digest"]
                or rebuilt_configuration_digest
                != specification["strategy_configuration_digest"]
                or row["stored_template_digest"] != template.template_digest
                or row["stored_implementation_digest"]
                != template.implementation_digest
                or row["stored_schema_version"] != template.parameter_schema.version
                or row["stored_schema_digest"]
                != template.parameter_schema.schema_digest
            ):
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")

            source_draft_id = str(row["source_draft_id"])
            version_id = str(row["version_id"])
            event_id = str(row["lifecycle_event_id"])
            operation_id = str(row["publish_operation_id"])
            expected_draft_revision = int(row["expected_draft_revision"])
            draft_parameters = _decoded(row["draft_parameters_json"], "draft_parameters")
            if (
                not isinstance(draft_parameters, dict)
                or row["draft_id"] != source_draft_id
                or row["draft_strategy_id"] != strategy_id
                or int(row["draft_revision"]) != expected_draft_revision + 1
                or draft_parameters != parameters
                or canonical_digest(draft_parameters)
                != row["draft_parameters_digest"]
                or row["published_strategy_version_id"] != version_id
                or row["draft_published_event_id"] != event_id
                or row["draft_published_operation_id"] != operation_id
                or row["draft_published_at"] is None
            ):
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")

            evidence = {**configuration, "source_draft_id": source_draft_id}
            occurred_at = row["event_occurred_at"].isoformat()
            publish_request = PublishStrategyRequest(
                draft_id=source_draft_id,
                idempotency_key=str(row["event_idempotency_key"]),
                expected_draft_revision=expected_draft_revision,
                actor_id=str(row["event_actor_id"]),
                actor_session_id=str(row["event_actor_session_id"]),
                change_note=str(row["event_reason"]),
            )
            evidence = _decoded(row["evidence_json"], "lifecycle_evidence")
            event_document = {
                "event_id": event_id,
                "strategy_version_id": version_id,
                "sequence": 1,
                "event_type": str(row["event_type"]),
                "from_status": row["from_status"],
                "to_status": str(row["to_status"]),
                "evidence_digest": str(row["evidence_digest"]),
                "actor_id": str(row["event_actor_id"]),
                "actor_session_id": str(row["event_actor_session_id"]),
                "idempotency_key": str(row["event_idempotency_key"]),
                "request_digest": str(row["event_request_digest"]),
                "expected_sequence": int(row["event_expected_sequence"]),
                "occurred_at": occurred_at,
            }
            projection = {
                "strategy_version_id": version_id,
                "status": "PUBLISHED",
                "last_sequence": 1,
                "last_event_id": event_id,
            }
            actual = build_version_binding(
                hypothesis_spec_digest=slot["hypothesis_spec_digest"],
                strategy_version_id=version_id,
                version_number=int(row["version_number"]),
                strategy_configuration_digest=rebuilt_configuration_digest,
                lifecycle_status=str(row["lifecycle_status"]),
                lifecycle_sequence=int(row["lifecycle_sequence"]),
                lifecycle_event_id=event_id,
                lifecycle_projection_digest=str(row["lifecycle_projection_digest"]),
            )
            publish_result = {
                "publish_operation_id": operation_id,
                "draft_id": source_draft_id,
                "strategy_version_id": version_id,
                "published_event_id": event_id,
                "version_number": int(row["version_number"]),
                "configuration_digest": rebuilt_configuration_digest,
            }
            outbox_payload = _decoded(row["outbox_payload_json"], "lifecycle_outbox")
            if (
                actual != expected
                or row["event_sequence"] != 1
                or row["event_type"] != "PUBLISHED"
                or row["from_status"] is not None
                or row["to_status"] != "PUBLISHED"
                or evidence != {**configuration, "source_draft_id": source_draft_id}
                or row["evidence_digest"] != canonical_digest(evidence)
                or row["event_expected_sequence"] != 0
                or row["event_request_digest"] != publish_request.request_digest
                or row["event_digest"] != canonical_digest(event_document)
                or row["operation_idempotency_key"]
                != row["event_idempotency_key"]
                or row["operation_request_digest"] != publish_request.request_digest
                or expected_draft_revision < 1
                or row["operation_version_id"] != version_id
                or row["operation_event_id"] != event_id
                or row["publish_result_digest"] != canonical_digest(publish_result)
                or row["lifecycle_status"] != "PUBLISHED"
                or row["lifecycle_sequence"] != 1
                or row["lifecycle_projection_digest"]
                != canonical_digest(projection)
                or row["outbox_event_digest"] != row["event_digest"]
                or row["outbox_topic"] != "strategy.lifecycle.v1"
                or outbox_payload
                != {**event_document, "event_digest": row["event_digest"]}
                or row["outbox_payload_digest"] != canonical_digest(outbox_payload)
            ):
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")

            if int(slot["slot_sequence"]) in _G1_FROZEN_PUBLICATION_SLOTS and (
                expected_draft_revision != 1
                or row["event_actor_id"] != _G1_ACTOR_ID
                or row["version_created_by"] != _G1_ACTOR_ID
                or row["draft_created_by"] != _G1_ACTOR_ID
                or row["draft_updated_by"] != _G1_ACTOR_ID
                or row["event_actor_session_id"] != _G1_ACTOR_SESSION_ID
                or row["event_reason"] != _G1_CHANGE_NOTE
                or row["version_change_note"] != _G1_CHANGE_NOTE
                or row["draft_change_note"] != _G1_CHANGE_NOTE
            ):
                raise AtomicBenchmarkConflict("R6_VERSION_IDENTITY_REJECTED")

    def _operation_replay(
        self,
        cursor: Any,
        *,
        family_id: str,
        operation_type: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT operation.*,
                   outbox.outbox_id AS operation_outbox_id,
                   outbox.topic AS operation_outbox_topic,
                   outbox.payload_json AS operation_outbox_payload_json,
                   outbox.payload_digest AS operation_outbox_payload_digest,
                   transition.evidence_json AS transition_evidence_json,
                   transition.evidence_digest AS transition_evidence_digest,
                   transition.from_revision AS transition_from_revision,
                   transition.to_revision AS transition_to_revision,
                   transition.from_status AS transition_from_status,
                   transition.to_status AS transition_to_status,
                   transition.retry_generation AS transition_retry_generation,
                   transition.next_retry_generation
                       AS transition_next_retry_generation,
                   transition.from_progress AS transition_from_progress,
                   transition.requested_progress AS transition_requested_progress,
                   transition.result_progress AS transition_result_progress,
                   transition.outcome_code AS transition_outcome_code
            FROM backtest.atomic_entry_benchmark_operations AS operation
            LEFT JOIN backtest.atomic_entry_benchmark_outbox AS outbox
              ON outbox.operation_id = operation.operation_id
             AND outbox.topic = %s
            LEFT JOIN backtest.atomic_entry_benchmark_transition_evidence
                AS transition
              ON transition.operation_id = operation.operation_id
            WHERE operation.family_id = %s
              AND operation.operation_type = %s
              AND operation.idempotency_key = %s
            FOR UPDATE OF operation
            """,
            (
                _OPERATION_OUTBOX_TOPIC,
                family_id,
                operation_type,
                idempotency_key,
            ),
        )
        raw = cursor.fetchone()
        if raw is None:
            return None
        row = self._row(cursor, raw)
        request = _decoded(row["request_json"], "operation_request")
        result = _decoded(row["result_json"], "operation_result")
        outbox = _decoded(
            row["operation_outbox_payload_json"], "operation_outbox"
        ) if row.get("operation_outbox_payload_json") is not None else None
        if not isinstance(request, dict) or not isinstance(result, dict):
            raise AtomicBenchmarkConflict("R6_IDEMPOTENCY_CONFLICT")
        matrix = self._verify_matrix(
            cursor,
            family_id,
            matrix_id=str(row["matrix_id"]),
        )
        attempt = None
        if row.get("attempt_id") is not None:
            cursor.execute(
                """
                SELECT attempt.attempt_id, attempt.family_id,
                       attempt.matrix_id, attempt.attempt_sequence,
                       attempt.slot_sequence, attempt.preflight_id,
                       preflight.preflight_registration_digest,
                       preflight.status AS preflight_status
                FROM backtest.atomic_entry_benchmark_attempts AS attempt
                JOIN backtest.atomic_entry_benchmark_preflights AS preflight
                  ON preflight.preflight_id = attempt.preflight_id
                 AND preflight.matrix_id = attempt.matrix_id
                WHERE attempt.attempt_id = %s
                """,
                (row["attempt_id"],),
            )
            attempt_raw = cursor.fetchone()
            attempt = (
                self._row(cursor, attempt_raw) if attempt_raw is not None else None
            )
        common_invalid = (
            digest(request) != row["request_digest"]
            or row["request_digest"] != request_digest
            or digest(result) != row["result_digest"]
            or row.get("operation_outbox_id") is None
            or row.get("operation_outbox_topic") != _OPERATION_OUTBOX_TOPIC
            or not isinstance(outbox, dict)
            or digest(outbox) != row.get("operation_outbox_payload_digest")
            or result.get("family_id") != family_id
            or result.get("matrix_id") != matrix["matrix_id"]
            or row.get("matrix_id") != matrix["matrix_id"]
            or request.get("family_id", family_id) != family_id
            or request.get("matrix_id", matrix["matrix_id"])
            != matrix["matrix_id"]
            or request.get("actor_id") != row.get("actor_id")
            or (
                row.get("attempt_id") is not None
                and (
                    attempt is None
                    or attempt["family_id"] != family_id
                    or attempt["matrix_id"] != matrix["matrix_id"]
                )
            )
        )
        if operation_type == "SEAL_MATRIX":
            expected_outbox = {
                "schema_version": "r6-benchmark-outbox-v1",
                "event_type": "MATRIX_SEALED",
                "family_id": family_id,
                "matrix_id": matrix["matrix_id"],
                "registration_digest": matrix["registration_digest"],
                "family_head_sequence": 0,
            }
            invalid = (
                frozenset(result)
                != {
                "schema_version",
                "family_id",
                "matrix_id",
                "matrix_revision",
                "registration_digest",
                "family_head_sequence",
                "status",
                }
                or result.get("matrix_revision") != 1
                or result.get("registration_digest") != matrix["registration_digest"]
                or result.get("family_head_sequence") != 0
                or result.get("status") != "SEALED"
                or result.get("schema_version") != "r6-matrix-seal-result-v1"
                or outbox != expected_outbox
            )
        elif operation_type == "ACTIVATE_MATRIX_REVISION_2":
            expected_outbox = self._operation_outbox_event(
                operation_type=operation_type,
                event_type="MATRIX_REVISION_ACTIVATED",
                result=result,
            )
            invalid = (
                frozenset(result)
                != {
                    "schema_version", "family_id", "matrix_id",
                    "matrix_revision", "registration_digest",
                    "previous_active_matrix_revision",
                    "active_matrix_revision", "family_head_sequence",
                    "attempt_count", "status",
                }
                or result.get("schema_version")
                != "r6-matrix-activate-result-v2"
                or result.get("matrix_revision") != 2
                or result.get("registration_digest")
                != matrix["registration_digest"]
                or result.get("previous_active_matrix_revision") != 1
                or result.get("active_matrix_revision") != 2
                or result.get("family_head_sequence") != 0
                or result.get("attempt_count") != 0
                or result.get("status") != "SEALED"
                or request.get("schema_version")
                != "r6-matrix-activate-request-v2"
                or request.get("expected_active_matrix_revision") != 1
                or request.get("expected_family_head_sequence") != 0
                or request.get("expected_attempt_count") != 0
                or outbox != expected_outbox
            )
        elif operation_type == "REGISTER_PREFLIGHT_V2":
            cursor.execute(
                """
                SELECT * FROM backtest.atomic_entry_benchmark_preflights
                WHERE operation_id = %s AND family_id = %s AND matrix_id = %s
                """,
                (row["operation_id"], family_id, matrix["matrix_id"]),
            )
            preflight_raw = cursor.fetchone()
            preflight_row = (
                self._row(cursor, preflight_raw)
                if preflight_raw is not None
                else None
            )
            registration = (
                _decoded(
                    preflight_row["preflight_registration_json"],
                    "preflight_registration",
                )
                if preflight_row is not None
                else None
            )
            artifact_verified = False
            stored_manifest = None
            slot_bindings_valid = False
            if preflight_row is not None:
                try:
                    stored_manifest = _decoded(
                        preflight_row["preflight_json"], "preflight_manifest"
                    )
                    artifact = verify_preflight_artifact(
                        Path(str(preflight_row["artifact_locator"])),
                        expected_manifest=stored_manifest,
                    )
                    artifact_verified = artifact.manifest == stored_manifest
                    cursor.execute(
                        """
                        SELECT slot_sequence, hypothesis_id,
                               strategy_version_id, hypothesis_spec_json,
                               version_binding_json
                        FROM backtest.atomic_entry_benchmark_slots
                        WHERE matrix_id = %s AND family_id = %s
                        ORDER BY slot_sequence
                        """,
                        (matrix["matrix_id"], family_id),
                    )
                    matrix_slots = [
                        self._row(cursor, stored)
                        for stored in cursor.fetchall()
                    ]
                    slot_bindings_valid = self._preflight_slot_bindings_valid(
                        preflight_slots=stored_manifest.get("slots"),
                        matrix_slots=matrix_slots,
                        artifact_slot_manifests=list(artifact.slot_manifests),
                        eligibility_manifest_digest=stored_manifest.get(
                            "eligibility_manifest_digest"
                        ),
                    )
                except (OSError, ValueError):
                    artifact_verified = False
            expected_outbox = self._operation_outbox_event(
                operation_type=operation_type,
                event_type="ATOMIC_ENTRY_BENCHMARK_PREFLIGHT_ACCEPTED",
                result=result,
            )
            invalid = (
                frozenset(result)
                != {
                    "schema_version", "family_id", "matrix_id",
                    "matrix_revision", "preflight_id", "preflight_digest",
                    "eligibility_manifest_digest",
                    "preflight_registration_digest", "status",
                    "family_head_sequence", "attempt_count",
                }
                or result.get("schema_version")
                != "r6-preflight-register-result-v1"
                or preflight_row is None
                or not isinstance(registration, dict)
                or not isinstance(stored_manifest, dict)
                or not artifact_verified
                or not slot_bindings_valid
                or digest(registration)
                != preflight_row.get("preflight_registration_digest")
                or registration.get("matrix_id") != matrix["matrix_id"]
                or registration.get("matrix_revision") != 2
                or registration.get("matrix_registration_digest")
                != matrix["registration_digest"]
                or registration.get("protocol_core_digest")
                != matrix["protocol_core_digest"]
                or registration.get("preflight_digest")
                != stored_manifest.get("preflight_digest")
                or registration.get("eligibility_manifest_digest")
                != stored_manifest.get("eligibility_manifest_digest")
                or result.get("preflight_id") != preflight_row.get("preflight_id")
                or result.get("preflight_digest")
                != preflight_row.get("preflight_digest")
                or result.get("eligibility_manifest_digest")
                != preflight_row.get("eligibility_manifest_digest")
                or result.get("preflight_registration_digest")
                != preflight_row.get("preflight_registration_digest")
                or result.get("matrix_revision") != 2
                or result.get("status") != "ACCEPTED"
                or result.get("family_head_sequence") != 0
                or result.get("attempt_count") != 0
                or request.get("preflight_id") != result.get("preflight_id")
                or request.get("preflight_digest") != result.get("preflight_digest")
                or request.get("eligibility_manifest_digest")
                != result.get("eligibility_manifest_digest")
                or request.get("preflight_registration_digest")
                != result.get("preflight_registration_digest")
                or outbox != expected_outbox
            )
        elif operation_type == "START_ATTEMPT":
            expected_outbox = self._operation_outbox_event(
                operation_type=operation_type,
                event_type="ATTEMPT_STARTED",
                result=result,
            )
            invalid = (
                frozenset(result)
                != {
                    "schema_version", "family_id", "matrix_id", "attempt_id",
                    "slot_sequence", "attempt_sequence", "status",
                    "attempt_revision", "retry_generation", "family_head_sequence",
                }
                or result.get("schema_version") != "r6-attempt-start-result-v1"
                or attempt is None
                or result.get("attempt_id") != row["attempt_id"]
                or result.get("slot_sequence") != (
                    attempt["slot_sequence"] if attempt is not None else None
                )
                or result.get("attempt_sequence") != (
                    attempt["attempt_sequence"] if attempt is not None else None
                )
                or result.get("slot_sequence") != result.get("attempt_sequence")
                or result.get("family_head_sequence") != result.get("slot_sequence")
                or result.get("status") != "RUNNING"
                or result.get("attempt_revision") != 1
                or result.get("retry_generation") != 1
                or frozenset(request)
                != {
                    "schema_version", "family_id", "matrix_id",
                    "expected_family_head_sequence", "actor_id", "change_note",
                    "expected_preflight_id",
                    "expected_preflight_registration_digest",
                }
                or request.get("schema_version") != "r6-attempt-start-request-v1"
                or type(request.get("expected_family_head_sequence")) is not int
                or type(result.get("slot_sequence")) is not int
                or type(result.get("attempt_sequence")) is not int
                or type(result.get("attempt_revision")) is not int
                or type(result.get("retry_generation")) is not int
                or type(result.get("family_head_sequence")) is not int
                or request.get("expected_family_head_sequence")
                != result.get("slot_sequence") - 1
                or attempt.get("preflight_id")
                != request.get("expected_preflight_id")
                or attempt.get("preflight_registration_digest")
                != request.get("expected_preflight_registration_digest")
                or attempt.get("preflight_status") != "ACCEPTED"
                or outbox != expected_outbox
            )
        elif operation_type == "TRANSITION_ATTEMPT":
            request_fields = {
                "schema_version", "family_id", "matrix_id", "attempt_id",
                "expected_revision", "expected_status", "next_status",
                "retry_generation", "next_retry_generation", "outcome_code",
                "progress", "actor_id",
            }
            request_valid = frozenset(request) == request_fields
            if request_valid:
                try:
                    next_generation = validate_attempt_transition(
                        current_status=request["expected_status"],
                        next_status=request["next_status"],
                        retry_generation=request["retry_generation"],
                        outcome_code=request["outcome_code"],
                    )
                except ValueError:
                    request_valid = False
                    next_generation = None
            else:
                next_generation = None
            transition_evidence = (
                _decoded(
                    row["transition_evidence_json"],
                    "transition_evidence",
                )
                if row.get("transition_evidence_json") is not None
                else None
            )
            evidence_fields = {
                "schema_version", "operation_id", "family_id", "matrix_id",
                "attempt_id", "from_revision", "to_revision", "from_status",
                "to_status", "retry_generation", "next_retry_generation",
                "from_progress", "requested_progress", "result_progress",
                "outcome_code", "request_digest", "result_digest",
            }
            evidence_valid = (
                isinstance(transition_evidence, dict)
                and frozenset(transition_evidence) == evidence_fields
            )
            try:
                from_progress = Decimal(transition_evidence.get("from_progress"))
                requested_progress = (
                    None
                    if transition_evidence.get("requested_progress") is None
                    else Decimal(transition_evidence["requested_progress"])
                )
                result_progress = Decimal(
                    transition_evidence.get("result_progress")
                )
                expected_result_progress = (
                    from_progress
                    if requested_progress is None
                    else max(from_progress, requested_progress)
                )
                progress_valid = (
                    type(transition_evidence.get("from_progress")) is str
                    and (
                        transition_evidence.get("requested_progress") is None
                        or type(
                            transition_evidence.get("requested_progress")
                        ) is str
                    )
                    and type(transition_evidence.get("result_progress")) is str
                    and from_progress.is_finite()
                    and result_progress.is_finite()
                    and (
                        requested_progress is None
                        or requested_progress.is_finite()
                    )
                    and Decimal(0) <= from_progress <= Decimal(1)
                    and (
                        requested_progress is None
                        or Decimal(0) <= requested_progress <= Decimal(1)
                    )
                    and result_progress == expected_result_progress
                    and Decimal(0) <= result_progress <= Decimal(1)
                )
            except (AttributeError, InvalidOperation, TypeError, ValueError):
                progress_valid = False
            canonical_result = {
                "schema_version": "r6-attempt-transition-result-v1",
                "family_id": family_id,
                "matrix_id": matrix["matrix_id"],
                "attempt_id": row["attempt_id"],
                "status": request.get("next_status"),
                "attempt_revision": (
                    request.get("expected_revision") + 1
                    if type(request.get("expected_revision")) is int
                    else None
                ),
                "retry_generation": next_generation,
                "progress": (
                    transition_evidence.get("result_progress")
                    if isinstance(transition_evidence, dict)
                    else None
                ),
                "outcome_code": request.get("outcome_code"),
            }
            expected_transition_evidence = {
                "schema_version": "r6-attempt-transition-evidence-v1",
                "operation_id": row.get("operation_id"),
                "family_id": family_id,
                "matrix_id": matrix["matrix_id"],
                "attempt_id": row.get("attempt_id"),
                "from_revision": request.get("expected_revision"),
                "to_revision": canonical_result["attempt_revision"],
                "from_status": request.get("expected_status"),
                "to_status": request.get("next_status"),
                "retry_generation": request.get("retry_generation"),
                "next_retry_generation": next_generation,
                "from_progress": (
                    transition_evidence.get("from_progress")
                    if isinstance(transition_evidence, dict)
                    else None
                ),
                "requested_progress": request.get("progress"),
                "result_progress": canonical_result["progress"],
                "outcome_code": request.get("outcome_code"),
                "request_digest": row.get("request_digest"),
                "result_digest": digest(canonical_result),
            }
            expected_outbox = self._operation_outbox_event(
                operation_type=operation_type,
                event_type=str(request.get("outcome_code")),
                result=canonical_result,
            )
            invalid = (
                frozenset(result)
                != {
                    "schema_version", "family_id", "matrix_id", "attempt_id",
                    "status", "attempt_revision", "retry_generation", "progress",
                    "outcome_code",
                }
                or result.get("schema_version")
                != "r6-attempt-transition-result-v1"
                or attempt is None
                or result.get("attempt_id") != row["attempt_id"]
                or not request_valid
                or request.get("schema_version")
                != "r6-attempt-transition-request-v1"
                or request.get("attempt_id") != row["attempt_id"]
                or type(request.get("expected_revision")) is not int
                or type(request.get("retry_generation")) is not int
                or type(request.get("next_retry_generation")) is not int
                or type(result.get("attempt_revision")) is not int
                or type(result.get("retry_generation")) is not int
                or request.get("next_retry_generation") != next_generation
                or not evidence_valid
                or not progress_valid
                or transition_evidence != expected_transition_evidence
                or row.get("transition_evidence_digest")
                != digest(expected_transition_evidence)
                or row.get("transition_from_revision")
                != request.get("expected_revision")
                or row.get("transition_to_revision")
                != canonical_result["attempt_revision"]
                or row.get("transition_from_status")
                != request.get("expected_status")
                or row.get("transition_to_status") != request.get("next_status")
                or row.get("transition_retry_generation")
                != request.get("retry_generation")
                or row.get("transition_next_retry_generation") != next_generation
                or row.get("transition_from_progress") != from_progress
                or (
                    row.get("transition_requested_progress") is None
                    and requested_progress is not None
                )
                or (
                    row.get("transition_requested_progress") is not None
                    and row.get("transition_requested_progress")
                    != requested_progress
                )
                or row.get("transition_result_progress") != result_progress
                or row.get("transition_outcome_code")
                != request.get("outcome_code")
                or result != canonical_result
                or outbox != expected_outbox
            )
        else:
            invalid = True
        if common_invalid or invalid:
            raise AtomicBenchmarkConflict("R6_IDEMPOTENCY_CONFLICT")
        return result

    @staticmethod
    def _operation_outbox_event(
        *, operation_type: str, event_type: str, result: Mapping[str, Any]
    ) -> dict[str, Any]:
        result_body = dict(result)
        return {
            "schema_version": "r6-benchmark-operation-outbox-v1",
            "operation_type": operation_type,
            "event_type": event_type,
            "result": result_body,
            "result_digest": digest(result_body),
        }

    def _insert_operation_outbox(
        self,
        cursor: Any,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str | None,
        operation_type: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        result: Mapping[str, Any],
        actor_id: str,
        event_type: str,
    ) -> str:
        operation_id = str(uuid4())
        cursor.execute(
            """
            INSERT INTO backtest.atomic_entry_benchmark_operations (
                operation_id, family_id, matrix_id, attempt_id,
                operation_type, idempotency_key, request_json,
                request_digest, result_json, result_digest, actor_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
            """,
            (
                operation_id, family_id, matrix_id, attempt_id, operation_type,
                idempotency_key, _json(dict(request)), request_digest,
                _json(dict(result)), digest(dict(result)), actor_id,
            ),
        )
        event = self._operation_outbox_event(
            operation_type=operation_type,
            event_type=event_type,
            result=result,
        )
        cursor.execute(
            """
            INSERT INTO backtest.atomic_entry_benchmark_outbox (
                outbox_id, family_id, matrix_id, attempt_id, operation_id,
                topic, payload_json, payload_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(uuid4()), family_id, matrix_id, attempt_id, operation_id,
                _OPERATION_OUTBOX_TOPIC, _json(event), digest(event),
            ),
        )
        return operation_id

    @contextmanager
    def _transaction(self, *, read_only: bool = False) -> Iterator[Any]:
        if self._pool is None:
            connection = self._connection
            try:
                with connection.cursor() as cursor:
                    if read_only:
                        cursor.execute("SET TRANSACTION READ ONLY")
                    yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return
        with self._pool.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    self._set_search_path(connection)
                    if read_only:
                        cursor.execute("SET TRANSACTION READ ONLY")
                    yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _set_search_path(connection: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO backtest, public")
        connection.commit()

    @staticmethod
    def _row(cursor: Any, row: Any) -> dict[str, Any]:
        if isinstance(row, Mapping):
            return dict(row)
        return {
            str(column.name): value
            for column, value in zip(cursor.description, row, strict=True)
        }

    @staticmethod
    def _advisory_lock_key(scope: str, identity: str) -> int:
        raw = hashlib.sha256(f"{scope}\0{identity}".encode("utf-8")).digest()
        return int.from_bytes(raw[:8], "big", signed=True)
