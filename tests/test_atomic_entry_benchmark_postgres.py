from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Barrier

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_benchmark.application import (
    FROZEN_VERSION_INVENTORY,
    AtomicBenchmarkApplicationService,
    frozen_hypothesis_specs,
    matrix_activation_request_from_inventory,
    matrix_seal_request_from_inventory,
)
from backtest.atomic_benchmark.artifacts import (
    build_ledger_manifest,
    build_match_manifest,
)
from backtest.atomic_benchmark.domain import (
    ALGORITHM_CONTRACT_DIGEST,
    FAMILY_ID,
    DatasetIdentityRejected,
    MatchPlanBuild,
    canonical_object_bytes,
    layer_multiplicity_digest,
)
from backtest.atomic_benchmark.preflight import (
    ELIGIBILITY_MANIFEST_SCHEMA,
    ELIGIBILITY_ROW_SCHEMA,
    PREFLIGHT_MANIFEST_SCHEMA,
    PREFLIGHT_SLOT_ROOT_SCHEMA,
    verify_eligibility_manifest,
    verify_eligibility_row,
    verify_preflight_artifact,
)
from backtest.atomic_benchmark.postgres_repository import (
    AtomicBenchmarkPostgresRepository,
)
from backtest.atomic_benchmark.repository import AtomicBenchmarkConflict
from backtest.domain import canonical_json, digest
from backtest.migrations import apply_migrations, migration_files
from strategy_catalog.application import AtomicStrategyCatalogService
from strategy_catalog.drafts import PublishStrategyRequest
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository


ROOT = Path(__file__).resolve().parents[1]
R6_TEST_DATASET_MANIFEST = Path(
    os.environ.get(
        "R6_TEST_DATASET_MANIFEST_PATH",
        str(
            ROOT
            / "data/backtest/dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6/manifest.json"
        ),
    )
)


def _request(note: str = "seal frozen R6 matrix"):
    return matrix_seal_request_from_inventory(
        version_inventory=FROZEN_VERSION_INVENTORY,
        repository_root=ROOT,
        actor_id="local-researcher",
        change_note=note,
    )


def _prepare_durable_inputs(connection, *, apply_schema: bool = True) -> None:
    if apply_schema:
        apply_migrations(connection)
    registry = AtomicStrategyRegistry()
    AtomicStrategyCatalogService(
        PostgresAtomicStrategyRepository(connection), registry.templates()
    ).sync_templates()
    specs = frozen_hypothesis_specs()
    now = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
    actor_id = "r6-g1-research-operator"
    actor_session_id = "r6-g1-version-admission-v1"
    change_note = "R6 G1 frozen atomic-entry benchmark Version admission"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO backtest.backtest_runs (
                run_id, idempotency_key, status, config_json, config_digest,
                dataset_id, dataset_digest, progress, progress_message,
                created_at, updated_at, error_message, result_digest
            ) VALUES (%s, %s, 'COMPLETED', %s::jsonb, %s, %s, %s, 1,
                      'completed', %s, %s, NULL, %s)
            """,
            (
                "run-91ad87981676414da87b928398fa43c9",
                "r6-source-lineage",
                canonical_json({"source": "R6"}),
                digest({"source": "R6"}),
                "dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6",
                "ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29",
                now.isoformat(),
                now.isoformat(),
                "a" * 64,
            ),
        )
        for spec, binding in zip(specs, FROZEN_VERSION_INVENTORY, strict=True):
            slot = int(binding["slot_sequence"])
            template = registry.strategy(str(spec["strategy_id"])).template
            draft_id = f"r6-g1-draft-{slot}"
            operation_id = f"r6-g1-operation-{slot}"
            outbox_id = f"r6-g1-outbox-{slot}"
            publish_request = PublishStrategyRequest(
                draft_id=draft_id,
                idempotency_key=f"r6-g1-publish-{slot}",
                expected_draft_revision=1,
                actor_id=actor_id,
                actor_session_id=actor_session_id,
                change_note=change_note,
            )
            request_digest = publish_request.request_digest
            configuration = {
                "strategy_id": spec["strategy_id"],
                "parameters": spec["parameters"],
                "parameter_schema_version": template.parameter_schema.version,
                "parameter_schema_digest": spec["parameter_schema_digest"],
                "parameters_digest": spec["parameters_digest"],
                "template_digest": spec["template_digest"],
                "implementation_digest": spec["strategy_implementation_digest"],
            }
            evidence = {**configuration, "source_draft_id": draft_id}
            event_document = {
                "event_id": binding["lifecycle_event_id"],
                "strategy_version_id": binding["strategy_version_id"],
                "sequence": 1,
                "event_type": "PUBLISHED",
                "from_status": None,
                "to_status": "PUBLISHED",
                "evidence_digest": digest(evidence),
                "actor_id": actor_id,
                "actor_session_id": actor_session_id,
                "idempotency_key": f"r6-g1-publish-{slot}",
                "request_digest": request_digest,
                "expected_sequence": 0,
                "occurred_at": now.isoformat(),
            }
            event_digest = digest(event_document)
            result_document = {
                "publish_operation_id": operation_id,
                "draft_id": draft_id,
                "strategy_version_id": binding["strategy_version_id"],
                "published_event_id": binding["lifecycle_event_id"],
                "version_number": 1,
                "configuration_digest": spec["strategy_configuration_digest"],
            }
            outbox_payload = {**event_document, "event_digest": event_digest}
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_drafts (
                    draft_id, strategy_id, revision, parameters_json,
                    parameters_digest, change_note, created_by, updated_by,
                    published_strategy_version_id, published_event_id,
                    published_operation_id, created_at, updated_at, published_at
                ) VALUES (
                    %s, %s, 2, %s::jsonb, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    draft_id,
                    spec["strategy_id"],
                    canonical_json(spec["parameters"]),
                    spec["parameters_digest"],
                    change_note,
                    actor_id,
                    actor_id,
                    binding["strategy_version_id"],
                    binding["lifecycle_event_id"],
                    operation_id,
                    now,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_versions (
                    strategy_version_id, strategy_id, source_draft_id,
                    version_number, parameters_json, parameter_schema_version,
                    parameter_schema_digest, parameters_digest, template_digest,
                    implementation_digest, configuration_digest, change_note,
                    created_by, created_at, published_at
                ) VALUES (
                    %s, %s, %s, 1, %s::jsonb, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    binding["strategy_version_id"],
                    spec["strategy_id"],
                    draft_id,
                    canonical_json(spec["parameters"]),
                    template.parameter_schema.version,
                    spec["parameter_schema_digest"],
                    spec["parameters_digest"],
                    spec["template_digest"],
                    spec["strategy_implementation_digest"],
                    spec["strategy_configuration_digest"],
                    change_note,
                    actor_id,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_events (
                    event_id, strategy_version_id, sequence, event_type,
                    from_status, to_status, evidence_json, evidence_digest,
                    reason, actor_id, actor_session_id, idempotency_key,
                    request_digest, expected_sequence, occurred_at, event_digest
                ) VALUES (
                    %s, %s, 1, 'PUBLISHED', NULL, 'PUBLISHED', %s::jsonb, %s,
                    %s, %s, %s, %s, %s, 0, %s, %s
                )
                """,
                (
                    binding["lifecycle_event_id"],
                    binding["strategy_version_id"],
                    canonical_json(evidence),
                    digest(evidence),
                    change_note,
                    event_document["actor_id"],
                    event_document["actor_session_id"],
                    event_document["idempotency_key"],
                    request_digest,
                    now,
                    event_digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_state (
                    strategy_version_id, status, last_sequence, last_event_id,
                    projection_digest, updated_at
                ) VALUES (%s, 'PUBLISHED', 1, %s, %s, %s)
                """,
                (
                    binding["strategy_version_id"],
                    binding["lifecycle_event_id"],
                    binding["lifecycle_projection_digest"],
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_publish_operations (
                    publish_operation_id, draft_id, idempotency_key,
                    request_digest, expected_draft_revision,
                    strategy_version_id, published_event_id, result_digest,
                    committed_at
                ) VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
                """,
                (
                    operation_id,
                    draft_id,
                    event_document["idempotency_key"],
                    request_digest,
                    binding["strategy_version_id"],
                    binding["lifecycle_event_id"],
                    digest(result_document),
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_lifecycle_outbox (
                    outbox_id, event_id, event_digest, topic, payload_json,
                    payload_digest, delivery_status, delivery_attempts, created_at
                ) VALUES (%s, %s, %s, 'strategy.lifecycle.v1', %s::jsonb, %s,
                          'PENDING', 0, %s)
                """,
                (
                    outbox_id,
                    binding["lifecycle_event_id"],
                    event_digest,
                    canonical_json(outbox_payload),
                    digest(outbox_payload),
                    now,
                ),
            )
    connection.commit()


def _apply_migrations_through_017(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS backtest")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest.backtest_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for path in migration_files():
            if path.name == "018_r6_dynamic_entry_reserve.sql":
                break
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO backtest.backtest_schema_migrations (version) VALUES (%s)",
                (path.name,),
            )
    connection.commit()


def _service(connection):
    return AtomicBenchmarkApplicationService(
        AtomicBenchmarkPostgresRepository(connection, apply_schema=False)
    )


def _prepare_dataset_binding(connection) -> dict:
    manifest_path = R6_TEST_DATASET_MANIFEST
    if not manifest_path.is_file():
        raise RuntimeError(
            "R6 PostgreSQL integration requires the canonical Dataset manifest; "
            "set R6_TEST_DATASET_MANIFEST_PATH for a clean worktree"
        )
    manifest = json.loads(manifest_path.read_bytes())
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO backtest.backtest_datasets (
                dataset_id, status, manifest_json, created_at, updated_at
            ) VALUES (%s, 'READY', %s::jsonb, %s, %s)
            """,
            (
                manifest["dataset_id"],
                canonical_json(manifest),
                manifest["created_at"],
                manifest["created_at"],
            ),
        )
        cursor.execute(
            """
            INSERT INTO backtest.backtest_dataset_bindings (
                binding_name, dataset_id, dataset_digest,
                plan_identity_digest, revision, actor_id, change_note
            ) VALUES (
                'ATOMIC_BACKTEST_DEFAULT', %s, %s, %s, 1,
                'test', 'R6 G3 fixture binding'
            )
            """,
            (
                manifest["dataset_id"],
                manifest["manifest_digest"],
                manifest["plan_identity_digest"],
            ),
        )
    connection.commit()
    return manifest


def _write_canonical(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_object_bytes(value))


def _build_empty_a1_preflight_artifact(
    *, context: dict, artifact_root: Path
) -> tuple[Path, dict]:
    """Build a bounded exact-shape artifact for PostgreSQL contract tests."""

    anchor_digest = hashlib.sha256(b"r6-a1-test-anchor").hexdigest()
    eligibility_body = {
        "schema_version": ELIGIBILITY_ROW_SCHEMA,
        "sequence": 1,
        "symbol": "2330",
        "session_date": "2026-08-26",
        "entry_reserve_at": "2026-08-26T12:45:00+08:00",
        "entry_reserve_bar_digest": anchor_digest,
        "terminal_exit_at": "2026-08-26T13:30:00+08:00",
        "terminal_exit_bar_digest": anchor_digest,
        "eligibility_status": "ELIGIBLE",
        "exclusion_reason_codes": [],
    }
    eligibility_row = verify_eligibility_row(
        {
            **eligibility_body,
            "eligibility_row_digest": digest(eligibility_body),
        }
    )
    eligibility_payload = canonical_object_bytes(eligibility_row)
    registered_manifest = context["registered_manifest"]
    eligibility_manifest_body = {
        "schema_version": ELIGIBILITY_MANIFEST_SCHEMA,
        "dataset_id": registered_manifest["dataset_id"],
        "dataset_digest": registered_manifest["manifest_digest"],
        "dataset_bars_sha256": registered_manifest["bars_sha256"],
        "common_signal_cutoff_time": "12:45",
        "entry_fill_deadline_time": "12:45",
        "required_terminal_exit_time": "13:30",
        "eligibility_row_schema_version": ELIGIBILITY_ROW_SCHEMA,
        "observed_symbol_session_count": 1,
        "eligible_symbol_session_count": 1,
        "excluded_symbol_session_count": 0,
        "missing_entry_reserve_count": 0,
        "missing_terminal_exit_count": 0,
        "eligible_symbol_session_ratio": "1.000000000000000000",
        "minimum_eligible_symbol_session_ratio": "0.95",
        "eligibility_rows_sha256": hashlib.sha256(eligibility_payload).hexdigest(),
    }
    eligibility_manifest = verify_eligibility_manifest(
        {
            **eligibility_manifest_body,
            "eligibility_manifest_digest": digest(eligibility_manifest_body),
        }
    )
    empty_sha = hashlib.sha256(b"").hexdigest()
    empty_multiplicity = layer_multiplicity_digest(())
    slot_roots = []
    root = artifact_root / "r6-a1-preflight"
    _write_canonical(root / "eligibility/manifest.json", eligibility_manifest)
    (root / "eligibility/rows.jsonl").write_bytes(eligibility_payload)
    for slot in context["slots"]:
        specification = slot["hypothesis_spec"]
        version = slot["version_binding"]
        identity = {
            "matrix_id": context["matrix_id"],
            "registration_digest": context["registration_digest"],
            "family_id": context["family_id"],
            "research_baseline_digest": context["research_baseline_digest"],
            "slot_sequence": slot["slot_sequence"],
            "hypothesis_id": slot["hypothesis_id"],
            "strategy_id": specification["strategy_id"],
            "strategy_version_id": version["strategy_version_id"],
            "strategy_configuration_digest": specification[
                "strategy_configuration_digest"
            ],
            "strategy_implementation_digest": specification[
                "strategy_implementation_digest"
            ],
            "lifecycle_sequence": version["lifecycle_sequence"],
            "lifecycle_event_id": version["lifecycle_event_id"],
            "lifecycle_projection_digest": version[
                "lifecycle_projection_digest"
            ],
            "dataset_id": registered_manifest["dataset_id"],
            "dataset_digest": registered_manifest["manifest_digest"],
            "dataset_bars_sha256": registered_manifest["bars_sha256"],
            "dataset_binding_revision": context["research_baseline"][
                "dataset_binding_revision"
            ],
            "protocol_core_digest": context["protocol_core_digest"],
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "algorithm_implementation_digest": context[
                "benchmark_build_binding"
            ]["algorithm_implementation_digest"],
        }
        ledger = build_ledger_manifest(
            identity=identity,
            ledger_rows=(),
            eligibility_manifest_digest=eligibility_manifest[
                "eligibility_manifest_digest"
            ],
        )
        matches = build_match_manifest(
            ledger_manifest=ledger,
            match_plan=MatchPlanBuild(
                rows=(),
                signal_count=0,
                missing_entry_count=0,
                missing_exit_count=0,
                duplicate_match_count=0,
                rows_sha256=empty_sha,
                signal_multiplicity_digest=empty_multiplicity,
                source_bar_count=registered_manifest["bar_count"],
                source_bars_sha256=registered_manifest["bars_sha256"],
                max_waiting_count=0,
                max_active_count=0,
            ),
        )
        directory = root / f"slot-{slot['slot_sequence']:02d}"
        _write_canonical(directory / "ledger_manifest.json", ledger)
        _write_canonical(directory / "match_manifest.json", matches)
        (directory / "ledger.jsonl").write_bytes(b"")
        (directory / "matches.jsonl").write_bytes(b"")
        slot_roots.append(
            {
                "schema_version": PREFLIGHT_SLOT_ROOT_SCHEMA,
                "slot_sequence": slot["slot_sequence"],
                "hypothesis_id": slot["hypothesis_id"],
                "eligibility_manifest_digest": eligibility_manifest[
                    "eligibility_manifest_digest"
                ],
                "ledger_manifest_digest": ledger["ledger_manifest_digest"],
                "match_manifest_digest": matches["match_manifest_digest"],
                "signal_count": 0,
                "matched_count": 0,
            }
        )
    preflight_body = {
        "schema_version": PREFLIGHT_MANIFEST_SCHEMA,
        "family_id": context["family_id"],
        "matrix_id": context["matrix_id"],
        "matrix_revision": 2,
        "registration_digest": context["registration_digest"],
        "research_baseline_digest": context["research_baseline_digest"],
        "dataset_id": registered_manifest["dataset_id"],
        "dataset_digest": registered_manifest["manifest_digest"],
        "dataset_bars_sha256": registered_manifest["bars_sha256"],
        "dataset_bar_count": registered_manifest["bar_count"],
        "dataset_binding_revision": context["research_baseline"][
            "dataset_binding_revision"
        ],
        "source_bar_count": registered_manifest["bar_count"],
        "source_bars_sha256": registered_manifest["bars_sha256"],
        "source_eof_verified": True,
        "protocol_core_digest": context["protocol_core_digest"],
        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
        "algorithm_implementation_digest": context["benchmark_build_binding"][
            "algorithm_implementation_digest"
        ],
        "preflight_implementation_digest": context["benchmark_build_binding"][
            "preflight_implementation_digest"
        ],
        "eligibility_manifest_digest": eligibility_manifest[
            "eligibility_manifest_digest"
        ],
        "slots": slot_roots,
    }
    preflight = {**preflight_body, "preflight_digest": digest(preflight_body)}
    _write_canonical(root / "preflight_manifest.json", preflight)
    verified = verify_preflight_artifact(root, expected_manifest=preflight)
    return root, verified.manifest


def _activate_and_register_a1_preflight(
    connection, *, artifact_root: Path
) -> tuple[dict, dict]:
    service = _service(connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    matrix = service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate R6 A1 matrix revision 2",
        ),
        idempotency_key="activate-r6-a1",
    )
    context = service.get_preflight_context(FAMILY_ID)
    artifact_path, manifest = _build_empty_a1_preflight_artifact(
        context=context, artifact_root=artifact_root
    )
    preflight = service.register_preflight(
        manifest=manifest,
        matrix_registration_digest=matrix["registration_digest"],
        artifact_locator=str(artifact_path),
        idempotency_key="register-r6-a1-preflight",
        actor_id="local-researcher",
        change_note="register bounded A1 PostgreSQL fixture",
    )
    return matrix, preflight


def _start_a1_attempt(
    service: AtomicBenchmarkApplicationService,
    *,
    matrix: dict,
    preflight: dict,
    expected_family_head_sequence: int,
    idempotency_key: str,
    change_note: str,
) -> dict:
    return service.start_next_attempt(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        expected_family_head_sequence=expected_family_head_sequence,
        idempotency_key=idempotency_key,
        actor_id="operator",
        change_note=change_note,
        expected_preflight_id=preflight["preflight_id"],
        expected_preflight_registration_digest=preflight[
            "preflight_registration_digest"
        ],
    )


def test_migration_016_creates_complete_r6_ledger(postgres_test_connection) -> None:
    apply_migrations(postgres_test_connection)
    expected = {
        "atomic_entry_benchmark_families",
        "atomic_entry_benchmark_matrices",
        "atomic_entry_benchmark_slots",
        "atomic_entry_benchmark_attempts",
        "atomic_entry_benchmark_operations",
        "atomic_entry_benchmark_transition_evidence",
        "atomic_entry_benchmark_outbox",
        "atomic_entry_benchmark_result_chunks",
        "atomic_entry_benchmark_releases",
    }
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'backtest'"
        )
        names = {str(row[0]) for row in cursor.fetchall()}
    assert expected <= names


def test_migration_018_upgrades_exact_revision2_state_without_activation(
    postgres_test_connection,
) -> None:
    _apply_migrations_through_017(postgres_test_connection)
    _prepare_durable_inputs(postgres_test_connection, apply_schema=False)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate revision 2 before Migration 018",
        ),
        idempotency_key="activate-r6-a1",
    )

    assert apply_migrations(postgres_test_connection) == (
        "018_r6_dynamic_entry_reserve.sql",
    )
    context = service.get_preflight_context(FAMILY_ID)
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT active_matrix_revision, head_sequence,
                   (SELECT COUNT(*)
                      FROM backtest.atomic_entry_benchmark_attempts),
                   (SELECT COUNT(*)
                      FROM backtest.atomic_entry_benchmark_matrices
                     WHERE matrix_revision = 3),
                   to_regclass(
                       'backtest.atomic_entry_benchmark_eligibility_audits'
                   ) IS NOT NULL
            FROM backtest.atomic_entry_benchmark_families
            WHERE family_id = %s
            """,
            (FAMILY_ID,),
        )
        assert cursor.fetchone() == (
            2,
            0,
            0,
            0,
            True,
        )
    assert context["matrix_revision"] == 2
    assert context["family_head_sequence"] == 0
    assert context["attempt_count"] == 0


def test_migration_018_rejects_family_state_drift(
    postgres_test_connection,
) -> None:
    _apply_migrations_through_017(postgres_test_connection)
    _prepare_durable_inputs(postgres_test_connection, apply_schema=False)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate revision 2 before failed Migration 018",
        ),
        idempotency_key="activate-r6-a1",
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_families
            SET head_sequence = 1
            WHERE family_id = %s
            """,
            (FAMILY_ID,),
        )
    postgres_test_connection.commit()

    raise_exception = pytest.importorskip("psycopg").errors.RaiseException
    with pytest.raises(
        raise_exception,
        match="R6_MIGRATION_018_PRECONDITION_CONFLICT",
    ):
        apply_migrations(postgres_test_connection)
    postgres_test_connection.rollback()
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM backtest.backtest_schema_migrations
            WHERE version = '018_r6_dynamic_entry_reserve.sql'
            """
        )
        assert cursor.fetchone()[0] == 0


def test_g3_preflight_context_is_read_only_and_exact(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    manifest = _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    matrix = service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate A1 context",
        ),
        idempotency_key="activate-r6-a1",
    )

    context = service.get_preflight_context(FAMILY_ID)

    assert context["matrix_id"] == matrix["matrix_id"]
    assert context["registered_manifest"] == manifest
    assert context["family_head_sequence"] == 0
    assert context["attempt_count"] == 0
    assert [item["slot_sequence"] for item in context["slots"]] == list(range(1, 8))
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT head_sequence,
                   (SELECT count(*) FROM backtest.atomic_entry_benchmark_attempts)
            FROM backtest.atomic_entry_benchmark_families
            WHERE family_id = %s
            """,
            (FAMILY_ID,),
        )
        assert cursor.fetchone() == (0, 0)


def test_g3_preflight_context_rejects_binding_drift(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate A1 context",
        ),
        idempotency_key="activate-r6-a1",
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.backtest_dataset_bindings
            SET dataset_digest = %s
            WHERE binding_name = 'ATOMIC_BACKTEST_DEFAULT'
            """,
            ("b" * 64,),
        )
    postgres_test_connection.commit()

    with pytest.raises(AtomicBenchmarkConflict, match="PREFLIGHT_CONTEXT"):
        service.get_preflight_context(FAMILY_ID)


def test_matrix_seal_is_atomic_and_response_loss_replays(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    service = _service(postgres_test_connection)
    first = service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    second = service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert first["matrix_id"] == second["matrix_id"]
    with postgres_test_connection.cursor() as cursor:
        counts = []
        for table in (
            "atomic_entry_benchmark_families",
            "atomic_entry_benchmark_matrices",
            "atomic_entry_benchmark_operations",
            "atomic_entry_benchmark_outbox",
            "atomic_entry_benchmark_releases",
        ):
            cursor.execute(f"SELECT count(*) FROM backtest.{table}")
            counts.append(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_slots")
        slot_count = cursor.fetchone()[0]
    assert counts == [1, 1, 1, 1, 1]
    assert slot_count == 7


def test_same_key_different_digest_and_second_matrix_conflict(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    with pytest.raises(AtomicBenchmarkConflict, match="IDEMPOTENCY"):
        service.seal_matrix(
            request=_request("different note"), idempotency_key="seal-r6"
        )
    with pytest.raises(AtomicBenchmarkConflict, match="ALREADY_SEALED"):
        service.seal_matrix(request=_request(), idempotency_key="other-key")


def test_a1_activation_preserves_historical_seal_response_loss_replay(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    service = _service(postgres_test_connection)
    historical = service.seal_matrix(
        request=_request(), idempotency_key="seal-r6"
    )
    active = service.activate_matrix_revision2(
        request=matrix_activation_request_from_inventory(
            version_inventory=FROZEN_VERSION_INVENTORY,
            repository_root=ROOT,
            actor_id="local-researcher",
            change_note="activate A1 replay test",
        ),
        idempotency_key="activate-r6-a1",
    )

    replayed = service.seal_matrix(
        request=_request(), idempotency_key="seal-r6"
    )

    assert historical["matrix_revision"] == replayed["matrix_revision"] == 1
    assert historical["matrix_id"] == replayed["matrix_id"]
    assert active["matrix_revision"] == 2
    assert active["matrix_id"] != historical["matrix_id"]
    assert replayed["replayed"] is True


def test_preflight_registration_response_loss_replays_one_durable_result(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    matrix, first = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT preflight_json, artifact_locator
            FROM backtest.atomic_entry_benchmark_preflights
            WHERE preflight_id = %s
            """,
            (first["preflight_id"],),
        )
        manifest, artifact_locator = cursor.fetchone()
    second = _service(postgres_test_connection).register_preflight(
        manifest=dict(manifest),
        matrix_registration_digest=matrix["registration_digest"],
        artifact_locator=str(artifact_locator),
        idempotency_key="register-r6-a1-preflight",
        actor_id="local-researcher",
        change_note="register bounded A1 PostgreSQL fixture",
    )
    assert first["preflight_id"] == second["preflight_id"]
    assert second["replayed"] is True
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM backtest.atomic_entry_benchmark_preflights"
        )
        preflight_count = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT count(*) FROM backtest.atomic_entry_benchmark_operations
            WHERE operation_type = 'REGISTER_PREFLIGHT_V2'
            """
        )
        operation_count = cursor.fetchone()[0]
    assert (preflight_count, operation_count) == (1, 1)


def test_attempt_admission_reverifies_accepted_preflight_artifact(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT artifact_locator
            FROM backtest.atomic_entry_benchmark_preflights
            WHERE preflight_id = %s
            """,
            (preflight["preflight_id"],),
        )
        artifact_locator = Path(str(cursor.fetchone()[0]))
    rows_path = artifact_locator / "eligibility/rows.jsonl"
    rows_path.write_bytes(rows_path.read_bytes() + b"\n")

    with pytest.raises(AtomicBenchmarkConflict, match="PREFLIGHT_NOT_ACCEPTED"):
        _start_a1_attempt(
            _service(postgres_test_connection),
            matrix=matrix,
            preflight=preflight,
            expected_family_head_sequence=0,
            idempotency_key="start-tampered-preflight",
            change_note="must reverify accepted preflight bytes",
        )


def test_matrix_and_version_tamper_fail_closed(postgres_test_connection) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_matrices
            SET registration_json = jsonb_set(registration_json, '{matrix_revision}', '2')
            """
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="MATRIX_INTEGRITY"):
        service.get_matrix(FAMILY_ID)


def test_self_consistent_operation_result_tamper_fails_closed(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    service = _service(postgres_test_connection)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT result_json FROM backtest.atomic_entry_benchmark_operations
            WHERE idempotency_key = 'seal-r6'
            """
        )
        result = dict(cursor.fetchone()[0])
        result["family_head_sequence"] = 1
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_operations
            SET result_json = %s::jsonb, result_digest = %s
            WHERE idempotency_key = 'seal-r6'
            """,
            (canonical_json(result), digest(result)),
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="IDEMPOTENCY"):
        service.seal_matrix(request=_request(), idempotency_key="seal-r6")


def test_lifecycle_tamper_is_rejected_before_any_family_write(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.strategy_version_events
            SET actor_id = 'tampered'
            WHERE event_id = %s
            """,
            (FROZEN_VERSION_INVENTORY[0]["lifecycle_event_id"],),
        )
    postgres_test_connection.commit()
    with pytest.raises((AtomicBenchmarkConflict, ValueError), match="IDENTITY|rebuild"):
        _service(postgres_test_connection).seal_matrix(
            request=_request(), idempotency_key="seal-r6"
        )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_families")
        assert cursor.fetchone()[0] == 0


def test_self_consistent_g1_publication_actor_substitution_is_rejected(
    postgres_test_connection,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    binding = FROZEN_VERSION_INVENTORY[0]
    forged_actor = "forged-publication-actor"
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event.*, version.source_draft_id
            FROM backtest.strategy_version_events AS event
            JOIN backtest.strategy_versions AS version
              ON version.strategy_version_id = event.strategy_version_id
            WHERE event.event_id = %s
            """,
            (binding["lifecycle_event_id"],),
        )
        row = cursor.fetchone()
        columns = [column.name for column in cursor.description]
        event = dict(zip(columns, row, strict=True))
        request = PublishStrategyRequest(
            draft_id=str(event["source_draft_id"]),
            idempotency_key=str(event["idempotency_key"]),
            expected_draft_revision=1,
            actor_id=forged_actor,
            actor_session_id=str(event["actor_session_id"]),
            change_note=str(event["reason"]),
        )
        event_document = {
            "event_id": str(event["event_id"]),
            "strategy_version_id": str(event["strategy_version_id"]),
            "sequence": int(event["sequence"]),
            "event_type": str(event["event_type"]),
            "from_status": event["from_status"],
            "to_status": str(event["to_status"]),
            "evidence_digest": str(event["evidence_digest"]),
            "actor_id": forged_actor,
            "actor_session_id": str(event["actor_session_id"]),
            "idempotency_key": str(event["idempotency_key"]),
            "request_digest": request.request_digest,
            "expected_sequence": int(event["expected_sequence"]),
            "occurred_at": event["occurred_at"].isoformat(),
        }
        event_digest = digest(event_document)
        outbox_payload = {**event_document, "event_digest": event_digest}
        cursor.execute(
            """
            UPDATE backtest.strategy_version_events
            SET actor_id = %s, request_digest = %s, event_digest = %s
            WHERE event_id = %s
            """,
            (
                forged_actor,
                request.request_digest,
                event_digest,
                event["event_id"],
            ),
        )
        cursor.execute(
            """
            UPDATE backtest.strategy_publish_operations
            SET request_digest = %s WHERE published_event_id = %s
            """,
            (request.request_digest, event["event_id"]),
        )
        cursor.execute(
            """
            UPDATE backtest.strategy_lifecycle_outbox
            SET event_digest = %s, payload_json = %s::jsonb, payload_digest = %s
            WHERE event_id = %s
            """,
            (
                event_digest,
                canonical_json(outbox_payload),
                digest(outbox_payload),
                event["event_id"],
            ),
        )
        cursor.execute(
            """
            UPDATE backtest.strategy_version_drafts
            SET created_by = %s, updated_by = %s WHERE draft_id = %s
            """,
            (forged_actor, forged_actor, event["source_draft_id"]),
        )
        cursor.execute(
            """
            UPDATE backtest.strategy_versions
            SET created_by = %s WHERE strategy_version_id = %s
            """,
            (forged_actor, event["strategy_version_id"]),
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="VERSION_IDENTITY"):
        _service(postgres_test_connection).seal_matrix(
            request=_request(), idempotency_key="seal-forged-g1"
        )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_families")
        assert cursor.fetchone()[0] == 0


def test_pre_release_reader_exposes_only_redacted_status(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    repository = AtomicBenchmarkPostgresRepository(
        postgres_test_connection, apply_schema=False
    )
    result, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO backtest.atomic_entry_benchmark_attempts (
                attempt_id, family_id, matrix_id, attempt_sequence,
                slot_sequence, hypothesis_id, request_json, request_digest,
                status, attempt_revision, retry_generation, progress,
                integrity_status, integrity_diagnostic_codes_json, preflight_id
            ) SELECT
                'attempt-1', family.family_id, matrix.matrix_id, 1, 1,
                slot.hypothesis_id, '{}'::jsonb, repeat('a', 64),
                'RUNNING', 1, 1, 0.25, 'PENDING',
                '["DATASET_IDENTITY_VERIFIED"]'::jsonb, %s
            FROM backtest.atomic_entry_benchmark_families AS family
            JOIN backtest.atomic_entry_benchmark_matrices AS matrix
              ON matrix.family_id = family.family_id
             AND matrix.matrix_revision = family.active_matrix_revision
            JOIN backtest.atomic_entry_benchmark_slots AS slot
              ON slot.matrix_id = matrix.matrix_id AND slot.slot_sequence = 1
            """,
            (preflight["preflight_id"],),
        )
        cursor.execute(
            """
            INSERT INTO backtest.atomic_entry_benchmark_result_chunks (
                attempt_id, retry_generation, field_name, chunk_sequence,
                row_count, payload_bytes, payload_sha256
            ) VALUES ('attempt-1', 1, 'summary', 0, 1, %s, %s)
            """,
            (b'{"secret_pnl":"999"}\n', "b" * 64),
        )
    postgres_test_connection.commit()
    visibility = repository.get_family_visibility(FAMILY_ID)
    assert visibility["release_state"] == "NOT_READY"
    assert visibility["matrix_id"] == result["matrix_id"]
    assert visibility["attempts"][0] == {
        "schema_version": "r6-redacted-attempt-status-v1",
        "family_id": FAMILY_ID,
        "matrix_id": result["matrix_id"],
        "slot_sequence": 1,
        "attempt_id": "attempt-1",
        "status": "RUNNING",
        "attempt_revision": 1,
        "retry_generation": 1,
        "progress": "0.250000",
        "integrity_status": "PENDING",
        "integrity_diagnostic_codes": ["DATASET_IDENTITY_VERIFIED"],
    }
    assert "secret" not in canonical_json(visibility)


def test_diagnostic_allowlist_is_enforced_on_write_and_read(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    started = _start_a1_attempt(
        service,
        matrix=matrix,
        preflight=preflight,
        expected_family_head_sequence=0,
        idempotency_key="start-diagnostic",
        change_note="diagnostic allowlist",
    )
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.CheckViolation, match="diagnostic_codes"):
        with postgres_test_connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE backtest.atomic_entry_benchmark_attempts
                SET integrity_diagnostic_codes_json = '["secret_pnl=999"]'::jsonb
                WHERE attempt_id = %s
                """,
                (started["attempt_id"],),
            )
        postgres_test_connection.commit()
    postgres_test_connection.rollback()

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE backtest.atomic_entry_benchmark_attempts
            DROP CONSTRAINT atomic_benchmark_attempt_diagnostic_codes
            """
        )
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_attempts
            SET integrity_diagnostic_codes_json = '["secret_pnl=999"]'::jsonb
            WHERE attempt_id = %s
            """,
            (started["attempt_id"],),
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="REDACTED_PROJECTION"):
        AtomicBenchmarkPostgresRepository(
            postgres_test_connection, apply_schema=False
        ).get_family_visibility(FAMILY_ID)


def test_attempt_start_cancel_terminalize_and_retry_preserve_identity_and_progress(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    started = _start_a1_attempt(
        service,
        matrix=matrix,
        preflight=preflight,
        expected_family_head_sequence=0,
        idempotency_key="start-1",
        change_note="start frozen slot one",
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_attempts
            SET progress = 0.3 WHERE attempt_id = %s
            """,
            (started["attempt_id"],),
        )
    postgres_test_connection.commit()
    cancelling = service.request_attempt_cancellation(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=1,
        retry_generation=1,
        idempotency_key="cancel-1",
        actor_id="operator",
    )
    assert cancelling["progress"] == "0.300000"
    cancelled = service.complete_attempt_cancellation(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=2,
        retry_generation=1,
        progress="0.4",
        idempotency_key="cancel-terminal-1",
        actor_id="worker",
    )
    retried = service.retry_attempt(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=3,
        expected_status="CANCELLED_RETRYABLE",
        retry_generation=1,
        progress="0.4",
        idempotency_key="retry-1",
        actor_id="operator",
    )
    replayed = service.retry_attempt(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=3,
        expected_status="CANCELLED_RETRYABLE",
        retry_generation=1,
        progress="0.4",
        idempotency_key="retry-1",
        actor_id="operator",
    )
    assert cancelled["status"] == "CANCELLED_RETRYABLE"
    assert retried["retry_generation"] == 2
    assert retried["attempt_id"] == started["attempt_id"]
    assert replayed["replayed"] is True
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT head_sequence FROM backtest.atomic_entry_benchmark_families
            WHERE family_id = %s
            """,
            (FAMILY_ID,),
        )
        assert cursor.fetchone()[0] == 1


def test_transition_replay_rebuilds_canonical_result_from_request_and_outbox(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    started = _start_a1_attempt(
        service,
        matrix=matrix,
        preflight=preflight,
        expected_family_head_sequence=0,
        idempotency_key="start-forged-transition",
        change_note="transition replay tamper",
    )
    service.request_attempt_cancellation(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=1,
        retry_generation=1,
        idempotency_key="cancel-forged-transition",
        actor_id="operator",
    )
    forged_result = {
        "schema_version": "r6-attempt-transition-result-v1",
        "family_id": FAMILY_ID,
        "matrix_id": matrix["matrix_id"],
        "attempt_id": started["attempt_id"],
        "status": "FAILED_RETRYABLE",
        "attempt_revision": 99,
        "retry_generation": 3,
        "progress": "0.900000",
        "outcome_code": "POSTGRES_TRANSIENT_UNAVAILABLE",
    }
    forged_outbox = {
        "schema_version": "r6-benchmark-operation-outbox-v1",
        "operation_type": "TRANSITION_ATTEMPT",
        "event_type": "POSTGRES_TRANSIENT_UNAVAILABLE",
        "result": forged_result,
        "result_digest": digest(forged_result),
    }
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_operations
            SET result_json = %s::jsonb, result_digest = %s
            WHERE idempotency_key = 'cancel-forged-transition'
            """,
            (canonical_json(forged_result), digest(forged_result)),
        )
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_outbox AS outbox
            SET payload_json = %s::jsonb, payload_digest = %s
            FROM backtest.atomic_entry_benchmark_operations AS operation
            WHERE outbox.operation_id = operation.operation_id
              AND operation.idempotency_key = 'cancel-forged-transition'
            """,
            (canonical_json(forged_outbox), digest(forged_outbox)),
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="IDEMPOTENCY"):
        service.request_attempt_cancellation(
            family_id=FAMILY_ID,
            matrix_id=matrix["matrix_id"],
            attempt_id=started["attempt_id"],
            expected_revision=1,
            retry_generation=1,
            idempotency_key="cancel-forged-transition",
            actor_id="operator",
        )


def test_transition_replay_rejects_progress_only_substitution(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    started = _start_a1_attempt(
        service,
        matrix=matrix,
        preflight=preflight,
        expected_family_head_sequence=0,
        idempotency_key="start-progress-substitution",
        change_note="progress replay tamper",
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_attempts
            SET progress = 0.300000
            WHERE attempt_id = %s
            """,
            (started["attempt_id"],),
        )
    postgres_test_connection.commit()
    service.request_attempt_cancellation(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=1,
        retry_generation=1,
        idempotency_key="cancel-progress-substitution",
        actor_id="operator",
    )
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT result_json
            FROM backtest.atomic_entry_benchmark_operations
            WHERE idempotency_key = 'cancel-progress-substitution'
            """
        )
        forged_result = dict(cursor.fetchone()[0])
        forged_result["progress"] = "0.900000"
        forged_outbox = {
            "schema_version": "r6-benchmark-operation-outbox-v1",
            "operation_type": "TRANSITION_ATTEMPT",
            "event_type": "OPERATOR_CANCELLED",
            "result": forged_result,
            "result_digest": digest(forged_result),
        }
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_operations
            SET result_json = %s::jsonb, result_digest = %s
            WHERE idempotency_key = 'cancel-progress-substitution'
            """,
            (canonical_json(forged_result), digest(forged_result)),
        )
        cursor.execute(
            """
            UPDATE backtest.atomic_entry_benchmark_outbox AS outbox
            SET payload_json = %s::jsonb, payload_digest = %s
            FROM backtest.atomic_entry_benchmark_operations AS operation
            WHERE outbox.operation_id = operation.operation_id
              AND operation.idempotency_key = 'cancel-progress-substitution'
            """,
            (canonical_json(forged_outbox), digest(forged_outbox)),
        )
    postgres_test_connection.commit()
    with pytest.raises(AtomicBenchmarkConflict, match="IDEMPOTENCY"):
        service.request_attempt_cancellation(
            family_id=FAMILY_ID,
            matrix_id=matrix["matrix_id"],
            attempt_id=started["attempt_id"],
            expected_revision=1,
            retry_generation=1,
            idempotency_key="cancel-progress-substitution",
            actor_id="operator",
        )


def test_integrity_failure_cannot_be_reclassified_as_retryable(
    postgres_test_connection,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    service = _service(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    started = _start_a1_attempt(
        service,
        matrix=matrix,
        preflight=preflight,
        expected_family_head_sequence=0,
        idempotency_key="start-integrity-failure",
        change_note="integrity mapping",
    )
    failed = service.record_attempt_failure(
        family_id=FAMILY_ID,
        matrix_id=matrix["matrix_id"],
        attempt_id=started["attempt_id"],
        expected_revision=1,
        retry_generation=1,
        progress="0.5",
        error=DatasetIdentityRejected("dataset digest drift"),
        idempotency_key="dataset-rejected",
        actor_id="worker",
    )
    assert failed["status"] == "REJECTED_FINAL"
    assert failed["outcome_code"] == "DATASET_IDENTITY_REJECTED"
    with pytest.raises(AtomicBenchmarkConflict, match="RETRY_STATUS"):
        service.retry_attempt(
            family_id=FAMILY_ID,
            matrix_id=matrix["matrix_id"],
            attempt_id=started["attempt_id"],
            expected_revision=2,
            expected_status="REJECTED_FINAL",
            retry_generation=1,
            progress="0.5",
            idempotency_key="illegal-retry",
            actor_id="operator",
        )
        cursor.execute(
            """
            SELECT count(*) FROM backtest.atomic_entry_benchmark_attempts
            WHERE family_id = %s
            """,
            (FAMILY_ID,),
        )
        assert cursor.fetchone()[0] == 1


def test_concurrent_attempt_consumption_keeps_strict_slot_order(
    postgres_test_connection,
    postgres_test_dsn: str,
    tmp_path: Path,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    _prepare_dataset_binding(postgres_test_connection)
    matrix, preflight = _activate_and_register_a1_preflight(
        postgres_test_connection, artifact_root=tmp_path
    )
    psycopg = pytest.importorskip("psycopg")
    barrier = Barrier(2)

    def worker(key: str):
        with psycopg.connect(postgres_test_dsn) as connection:
            service = _service(connection)
            barrier.wait()
            try:
                return _start_a1_attempt(
                    service,
                    matrix=matrix,
                    preflight=preflight,
                    expected_family_head_sequence=0,
                    idempotency_key=key,
                    change_note="concurrent start",
                )
            except AtomicBenchmarkConflict as error:
                return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(worker, ("attempt-a", "attempt-b")))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert sum("HEAD_SEQUENCE" in value for value in values if isinstance(value, str)) == 1
    success = next(value for value in values if isinstance(value, dict))
    assert success["slot_sequence"] == 1
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_attempts")
        assert cursor.fetchone()[0] == 1


def test_concurrent_different_keys_only_one_seals_revision(
    postgres_test_connection,
    postgres_test_dsn: str,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    psycopg = pytest.importorskip("psycopg")
    barrier = Barrier(2)

    def worker(key: str):
        with psycopg.connect(postgres_test_dsn) as connection:
            service = _service(connection)
            barrier.wait()
            try:
                return service.seal_matrix(request=_request(), idempotency_key=key)
            except AtomicBenchmarkConflict as error:
                return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(worker, ("seal-a", "seal-b")))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert sum("ALREADY_SEALED" in value for value in values if isinstance(value, str)) == 1
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_operations")
        assert cursor.fetchone()[0] == 1


def test_concurrent_same_key_replays_one_durable_result(
    postgres_test_connection,
    postgres_test_dsn: str,
) -> None:
    _prepare_durable_inputs(postgres_test_connection)
    psycopg = pytest.importorskip("psycopg")
    barrier = Barrier(2)

    def worker():
        with psycopg.connect(postgres_test_dsn) as connection:
            service = _service(connection)
            barrier.wait()
            return service.seal_matrix(
                request=_request(), idempotency_key="same-key"
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(lambda _: worker(), range(2)))
    assert sorted(value["replayed"] for value in values) == [False, True]
    assert len({value["matrix_id"] for value in values}) == 1
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM backtest.atomic_entry_benchmark_operations")
        assert cursor.fetchone()[0] == 1
