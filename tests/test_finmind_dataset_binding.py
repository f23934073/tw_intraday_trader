from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

import pytest

from backtest.dataset import DatasetManifest
from backtest.dataset_binding import (
    ATOMIC_BACKTEST_DEFAULT,
    AtomicBacktestBindingChanged,
    DatasetBindingIdempotencyConflict,
    DatasetBindingIntegrityError,
    DatasetBindingRevisionConflict,
    DatasetRegistrationConflict,
    activation_request_digest,
    canonical_registration_manifest,
)
from backtest.domain import digest
from backtest.migrations import apply_migrations, migration_files
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.sqlite_repository import SQLiteBacktestRepository
from scripts.materialize_finmind_backtest_dataset import (
    activate_default_binding,
    main as materialize_main,
)


def _manifest(identity: str) -> dict[str, object]:
    dataset_id = f"dataset-{identity}"
    source_snapshot_digest = digest(f"source-{identity}")
    plan_identity = {
        "dataset_id": dataset_id,
        "source_snapshot_digest": source_snapshot_digest,
    }
    return DatasetManifest(
        dataset_id=dataset_id,
        created_at=datetime.fromisoformat("2026-08-18T13:30:00+08:00"),
        source="FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        profile="KBAR_1M_V1",
        capabilities=("OHLCV", "KBAR_INTRADAY", "SESSION_BOUNDARIES", "KBAR_1M"),
        start_date="2026-08-18",
        end_date="2026-08-18",
        requested_symbols=("2330",),
        observed_symbols=("2330",),
        bar_count=1,
        bars_sha256=digest(f"bars-{identity}"),
        universe_scope="CURRENT_SNAPSHOT",
        research_eligible=False,
        issues=("CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",),
        payload_order="TIMESTAMP_SYMBOL",
        universe_selection="FINMIND_COMPLETE_SYMBOLS_V1",
        volume_contract={"unit": "COMMON_LOTS"},
        amount_contract={
            "digest": digest("amount-contract"),
            "is_actual_turnover": False,
            "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
            "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
        },
        source_snapshot_digest=source_snapshot_digest,
        plan_identity=plan_identity,
        plan_identity_digest=digest(plan_identity),
    ).to_dict()


def _activation(manifest: dict[str, object], **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "binding_name": ATOMIC_BACKTEST_DEFAULT,
        "dataset_id": manifest["dataset_id"],
        "dataset_digest": manifest["manifest_digest"],
        "plan_identity_digest": manifest["plan_identity_digest"],
        "expected_revision": 0,
        "idempotency_key": "activate-1",
        "actor_id": "g4-test",
        "change_note": "activate verified Dataset",
    }
    values.update(overrides)
    return values


def test_binding_migration_uses_the_next_number_and_declares_all_tables() -> None:
    files = migration_files()
    assert files[-1].name == "012_backtest_dataset_bindings.sql"
    sql = files[-1].read_text(encoding="utf-8")
    for table in (
        "backtest.backtest_dataset_bindings",
        "backtest.backtest_dataset_binding_revisions",
        "backtest.backtest_dataset_binding_operations",
    ):
        assert table in sql


def test_registration_manifest_is_exact_and_activation_digest_is_stable() -> None:
    manifest = _manifest("one")
    assert canonical_registration_manifest(manifest) == manifest

    unknown = {**manifest, "locator": "/tmp/source.sqlite3"}
    with pytest.raises(ValueError, match="canonical"):
        canonical_registration_manifest(unknown)

    values = _activation(manifest)
    idempotency_key = values.pop("idempotency_key")
    assert idempotency_key == "activate-1"
    first = activation_request_digest(**values)
    second = activation_request_digest(**dict(reversed(tuple(values.items()))))
    assert first == second


def test_sqlite_never_registers_or_activates_dataset_binding(tmp_path: Path) -> None:
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            repository.register_immutable_dataset(_manifest("sqlite"))
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
    finally:
        repository.close()


def test_activation_without_postgres_dsn_fails_closed() -> None:
    manifest = DatasetManifest.from_dict(_manifest("no-postgres"))
    with pytest.raises(RuntimeError, match="BACKTEST_DATABASE_URL"):
        activate_default_binding(
            manifest=manifest,
            expected_revision=0,
            idempotency_key="activate-no-postgres",
            actor="g4-test",
            change_note="must fail closed",
            postgres_dsn="",
        )


@pytest.mark.parametrize(
    ("omitted", "message"),
    (
        ("expected", "--expected-binding-revision"),
        ("key", "--activation-idempotency-key"),
        ("actor", "--actor"),
        ("note", "--change-note"),
    ),
)
def test_activation_cli_requires_all_audit_and_cas_arguments(
    omitted: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    optional = {
        "expected": ("--expected-binding-revision", "0"),
        "key": ("--activation-idempotency-key", "activate-cli"),
        "actor": ("--actor", "g4-test"),
        "note": ("--change-note", "activate verified Dataset"),
    }
    argv = ["--execute", "--plan-file", "missing.json", "--activate-default"]
    for name, values in optional.items():
        if name != omitted:
            argv.extend(values)
    with pytest.raises(SystemExit) as error:
        materialize_main(argv)
    assert error.value.code == 2
    assert message in capsys.readouterr().err


def test_postgres_registration_binding_replay_noop_and_conflicts(
    postgres_test_connection,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    first_manifest = _manifest("first")
    second_manifest = _manifest("second")

    registered, registration_replayed = repository.register_immutable_dataset(
        first_manifest
    )
    replayed_registration, replayed = repository.register_immutable_dataset(
        first_manifest
    )
    assert registration_replayed is False
    assert replayed is True
    assert registered["manifest_digest"] == first_manifest["manifest_digest"]
    assert replayed_registration["manifest_digest"] == first_manifest["manifest_digest"]

    drifted = DatasetManifest.from_dict(
        {**first_manifest, "issues": ["DRIFTED"]}
    ).to_dict()
    with pytest.raises(DatasetRegistrationConflict):
        repository.register_immutable_dataset(drifted)

    first_result, first_replayed = repository.activate_dataset_binding(
        **_activation(first_manifest)
    )
    same_result, response_replayed = repository.activate_dataset_binding(
        **_activation(first_manifest)
    )
    assert first_replayed is False
    assert response_replayed is True
    assert same_result == first_result
    assert first_result["outcome"] == "BOUND"
    assert first_result["revision"] == 1

    noop, noop_replayed = repository.activate_dataset_binding(
        **_activation(
            first_manifest,
            expected_revision=1,
            idempotency_key="activate-noop",
            change_note="confirm exact current target",
        )
    )
    assert noop_replayed is False
    assert noop["outcome"] == "NOOP_ALREADY_BOUND"
    assert noop["revision"] == 1

    with pytest.raises(DatasetBindingIdempotencyConflict):
        repository.activate_dataset_binding(
            **_activation(first_manifest, change_note="different request")
        )
    with pytest.raises(DatasetBindingRevisionConflict):
        repository.activate_dataset_binding(
            **_activation(
                first_manifest,
                idempotency_key="activate-stale",
                change_note="stale request",
            )
        )

    repository.register_immutable_dataset(second_manifest)
    second_result, second_replayed = repository.activate_dataset_binding(
        **_activation(
            second_manifest,
            expected_revision=1,
            idempotency_key="activate-2",
            change_note="advance verified target",
        )
    )
    assert second_replayed is False
    assert second_result["outcome"] == "BOUND"
    assert second_result["revision"] == 2
    current = repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
    assert current is not None
    assert current == {
        "actor_id": "g4-test",
        "binding_name": ATOMIC_BACKTEST_DEFAULT,
        "change_note": "advance verified target",
        "created_at": current["created_at"],
        "dataset_digest": second_manifest["manifest_digest"],
        "dataset_id": second_manifest["dataset_id"],
        "plan_identity_digest": second_manifest["plan_identity_digest"],
        "revision": 2,
        "updated_at": current["updated_at"],
    }

    original_after_advance, late_replay = repository.activate_dataset_binding(
        **_activation(first_manifest)
    )
    assert late_replay is True
    assert original_after_advance == first_result

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM backtest_dataset_binding_revisions"
        )
        assert cursor.fetchone()[0] == 2
        cursor.execute(
            "SELECT COUNT(*) FROM backtest_dataset_binding_operations"
        )
        assert cursor.fetchone()[0] == 3


def test_atomic_run_insert_rechecks_locked_binding_and_replays_before_head(
    postgres_test_connection,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    first = _manifest("run-first")
    second = _manifest("run-second")
    repository.register_immutable_dataset(first)
    repository.register_immutable_dataset(second)
    repository.activate_dataset_binding(
        **_activation(first, idempotency_key="bind-run-first")
    )

    request = {
        "contract_version": "atomic-backtest-run-request-v1",
        "expected_binding_revision": 1,
        "expected_dataset_digest": first["manifest_digest"],
    }
    request_digest = digest(request)
    config = {
        "dataset_id": first["dataset_id"],
        "dataset_digest": first["manifest_digest"],
        "atomic_run_request": request,
        "atomic_run_request_digest": request_digest,
    }
    record = {
        "run_id": "g5-bound-run-1",
        "idempotency_key": "g5-bound-run-key-1",
        "status": "QUEUED",
        "config": config,
        "config_digest": digest(config),
        "dataset_id": first["dataset_id"],
        "dataset_digest": first["manifest_digest"],
        "created_at": "2026-08-23T12:00:00+08:00",
    }
    created, replayed = repository.create_atomic_run_from_binding(
        record,
        binding_name=ATOMIC_BACKTEST_DEFAULT,
        expected_binding_revision=1,
        expected_dataset_digest=str(first["manifest_digest"]),
        request_digest=request_digest,
    )
    assert replayed is False
    assert created["dataset_id"] == first["dataset_id"]

    repository.activate_dataset_binding(
        **_activation(
            second,
            expected_revision=1,
            idempotency_key="bind-run-second",
        )
    )
    replay, idempotent = repository.create_atomic_run_from_binding(
        record,
        binding_name=ATOMIC_BACKTEST_DEFAULT,
        expected_binding_revision=1,
        expected_dataset_digest=str(first["manifest_digest"]),
        request_digest=request_digest,
    )
    assert idempotent is True
    assert replay["run_id"] == created["run_id"]

    stale_record = {
        **record,
        "run_id": "g5-bound-run-stale",
        "idempotency_key": "g5-bound-run-key-stale",
    }
    with pytest.raises(AtomicBacktestBindingChanged):
        repository.create_atomic_run_from_binding(
            stale_record,
            binding_name=ATOMIC_BACKTEST_DEFAULT,
            expected_binding_revision=1,
            expected_dataset_digest=str(first["manifest_digest"]),
            request_digest=request_digest,
        )
    assert {run["run_id"] for run in repository.list_runs()} == {
        created["run_id"]
    }


def test_postgres_binding_migration_acceptance(postgres_test_connection) -> None:
    apply_migrations(postgres_test_connection)
    with postgres_test_connection.cursor() as cursor:
        for table in (
            "backtest_dataset_bindings",
            "backtest_dataset_binding_revisions",
            "backtest_dataset_binding_operations",
        ):
            cursor.execute("SELECT to_regclass(%s)", (f"backtest.{table}",))
            assert cursor.fetchone()[0] == f"backtest.{table}"
        cursor.execute(
            """
            SELECT conname
            FROM pg_constraint
            WHERE connamespace = 'backtest'::regnamespace
              AND conname LIKE 'backtest_dataset_binding%'
            """
        )
        constraints = {row[0] for row in cursor.fetchall()}
        assert {
            "backtest_dataset_bindings_pkey",
            "backtest_dataset_binding_revisions_pkey",
            "backtest_dataset_binding_operations_pkey",
            "backtest_dataset_bindings_revision_positive",
            "backtest_dataset_binding_operations_result_kind",
        } <= constraints
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'backtest'
              AND indexname LIKE 'backtest_dataset_binding%'
            """
        )
        indexes = {row[0] for row in cursor.fetchall()}
        assert {
            "backtest_dataset_bindings_dataset_index",
            "backtest_dataset_binding_revisions_dataset_index",
            "backtest_dataset_binding_operations_actor_index",
        } <= indexes


def test_postgres_binding_rejects_missing_and_non_ready_datasets(
    postgres_test_connection,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    missing = _manifest("missing")
    with pytest.raises(KeyError, match="not registered"):
        repository.activate_dataset_binding(**_activation(missing))

    non_ready = _manifest("non-ready")
    repository.upsert_dataset(non_ready, "CREATING")
    with pytest.raises(DatasetBindingIntegrityError, match="not READY"):
        repository.activate_dataset_binding(
            **_activation(non_ready, idempotency_key="activate-non-ready")
        )


def test_postgres_same_registration_is_serialized_and_replayed(
    postgres_test_connection,
    postgres_test_dsn: str,
) -> None:
    psycopg_pool = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = psycopg_pool.ConnectionPool(
        postgres_test_dsn,
        min_size=2,
        max_size=4,
        open=True,
    )
    try:
        repository = PostgresBacktestRepository(pool=pool)
        manifest = _manifest("concurrent-registration")
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = tuple(
                executor.map(
                    lambda _index: repository.register_immutable_dataset(manifest),
                    range(2),
                )
            )
        assert outcomes[0][0] == outcomes[1][0]
        assert sorted(replayed for _dataset, replayed in outcomes) == [False, True]
    finally:
        pool.close()


def test_postgres_same_activation_is_serialized_and_replayed(
    postgres_test_connection,
    postgres_test_dsn: str,
) -> None:
    psycopg_pool = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = psycopg_pool.ConnectionPool(
        postgres_test_dsn,
        min_size=2,
        max_size=4,
        open=True,
    )
    try:
        repository = PostgresBacktestRepository(pool=pool)
        manifest = _manifest("concurrent")
        repository.register_immutable_dataset(manifest)
        request = _activation(manifest, idempotency_key="activate-concurrent")
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = tuple(
                executor.map(
                    lambda _index: repository.activate_dataset_binding(**request),
                    range(2),
                )
            )
        assert outcomes[0][0] == outcomes[1][0]
        assert sorted(replayed for _result, replayed in outcomes) == [False, True]
    finally:
        pool.close()


def test_postgres_distinct_activations_from_same_revision_allow_one_mutation(
    postgres_test_connection,
    postgres_test_dsn: str,
) -> None:
    psycopg_pool = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = psycopg_pool.ConnectionPool(
        postgres_test_dsn,
        min_size=2,
        max_size=4,
        open=True,
    )
    try:
        repository = PostgresBacktestRepository(pool=pool)
        first_manifest = _manifest("cas-first")
        second_manifest = _manifest("cas-second")
        repository.register_immutable_dataset(first_manifest)
        repository.register_immutable_dataset(second_manifest)
        requests = (
            _activation(
                first_manifest,
                idempotency_key="activate-cas-first",
                change_note="first CAS contender",
            ),
            _activation(
                second_manifest,
                idempotency_key="activate-cas-second",
                change_note="second CAS contender",
            ),
        )
        barrier = Barrier(2)

        def activate(request: dict[str, object]) -> tuple[str, object | None]:
            barrier.wait()
            try:
                return "success", repository.activate_dataset_binding(**request)
            except DatasetBindingRevisionConflict:
                return "revision_conflict", None

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = tuple(executor.map(activate, requests))

        assert sorted(kind for kind, _result in outcomes) == [
            "revision_conflict",
            "success",
        ]
        success = next(result for kind, result in outcomes if kind == "success")
        assert success is not None
        result, replayed = success
        assert replayed is False
        assert result["outcome"] == "BOUND"
        assert result["revision"] == 1
        assert result["dataset_id"] in {
            first_manifest["dataset_id"],
            second_manifest["dataset_id"],
        }

        head = repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
        assert head is not None
        assert head["revision"] == 1
        assert head["dataset_id"] == result["dataset_id"]
        with postgres_test_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM backtest.backtest_dataset_bindings")
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM backtest.backtest_dataset_binding_revisions"
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM backtest.backtest_dataset_binding_operations"
            )
            assert cursor.fetchone()[0] == 1
    finally:
        pool.close()


def test_postgres_binding_read_fails_closed_after_manifest_tamper(
    postgres_test_connection,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    manifest = _manifest("tamper")
    repository.register_immutable_dataset(manifest)
    repository.activate_dataset_binding(**_activation(manifest))
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest_datasets
            SET manifest_json = jsonb_set(manifest_json, '{issues}', '["tampered"]')
            WHERE dataset_id = %s
            """,
            (manifest["dataset_id"],),
        )
    postgres_test_connection.commit()
    with pytest.raises(DatasetBindingIntegrityError):
        repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
