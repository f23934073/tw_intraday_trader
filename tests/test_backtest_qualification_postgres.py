from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from backtest.application import BacktestApplicationService
from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog
from backtest.domain import digest
from backtest.migrations import apply_migrations
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.qualification import (
    experiment_family_id,
    research_baseline_identity_digest,
)
from backtest.repository import BacktestIdempotencyConflict
from market_data.provider import MockProvider


def _atomic_snapshot(set_id: str, version_id: str) -> dict:
    value = {
        "contract_version": "atomic-backtest-run-snapshot-v2",
        "strategy_set": {
            "strategy_set_version_id": set_id,
            "members": [{"strategy_version_id": version_id}],
        },
        "feature_adapter_identity": "backtest.completed-kbar-1m-feature-adapter-v1",
        "feature_requests": [],
    }
    value["snapshot_digest"] = digest(value)
    return value


def _config(
    set_id: str,
    version_id: str,
    dataset_digest: str,
    *,
    baseline_run_id: str | None = None,
    baseline_config: dict | None = None,
) -> dict:
    value = {
        "dataset_id": "qualification-dataset",
        "dataset_digest": dataset_digest,
        "strategy_set": {
            "entry_strategy_ids": [version_id],
            "exit_strategy_ids": ["end_of_day_exit_v1"],
            "entry_policy": "ANY",
            "exit_policy": "ANY",
            "entry_min_trigger_count": 1,
            "exit_min_trigger_count": 1,
        },
        "starting_cash": "10000000",
        "position_fraction": "0.10",
        "commission_rate": "0.001425",
        "sell_tax_rate": "0.003",
        "slippage_bps": "5",
        "min_lot_shares": 1000,
        "engine_version": "backtest-engine-v2",
        "atomic_strategy_run_snapshot": _atomic_snapshot(set_id, version_id),
    }
    if baseline_run_id is not None:
        if baseline_config is None:
            raise ValueError("test Challenger requires the Baseline config")
        research_digest = research_baseline_identity_digest(baseline_config)
        value["baseline_run_id"] = baseline_run_id
        value["research_baseline_digest"] = research_digest
        value["experiment_id"] = experiment_family_id(research_digest)
    return value


def _protocol() -> dict:
    return {
        "contract_version": "backtest-qualification-request-v2",
        "primary_window": {
            "label": "primary",
            "train_start": "2025-01-01",
            "train_end": "2025-06-30",
            "validation_start": "2025-07-01",
            "validation_end": "2025-09-30",
            "oos_start": "2026-01-01",
            "oos_end": "2026-03-31",
        },
        "walk_forward_windows": [
            {
                "label": "fold-1",
                "train_start": "2025-01-01",
                "train_end": "2025-06-30",
                "validation_start": "2025-07-01",
                "validation_end": "2025-09-30",
                "oos_start": "2025-10-01",
                "oos_end": "2025-10-31",
            },
            {
                "label": "fold-2",
                "train_start": "2025-01-01",
                "train_end": "2025-06-30",
                "validation_start": "2025-07-01",
                "validation_end": "2025-09-30",
                "oos_start": "2025-11-01",
                "oos_end": "2025-11-30",
            },
        ],
    }


def _manifest(dataset_id: str = "qualification-dataset") -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        source="qualification-fixture",
        profile="KBAR_1M_V1",
        capabilities=("OHLCV", "KBAR_1M"),
        start_date="2025-01-01",
        end_date="2026-03-31",
        requested_symbols=("2330",),
        observed_symbols=("2330",),
        bar_count=1,
        bars_sha256="bars-digest",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )


def _save_completed_run(
    repository: PostgresBacktestRepository,
    run_id: str,
    set_id: str,
    version_id: str,
    dataset_digest: str,
    *,
    baseline_run_id: str | None = None,
) -> None:
    baseline_config = (
        repository.get_run(baseline_run_id)["config"] if baseline_run_id is not None else None
    )
    config = _config(
        set_id,
        version_id,
        dataset_digest,
        baseline_run_id=baseline_run_id,
        baseline_config=baseline_config,
    )
    repository.create_run(
        {
            "run_id": run_id,
            "idempotency_key": f"create-{run_id}",
            "status": "QUEUED",
            "config": config,
            "config_digest": digest(config),
            "dataset_id": "qualification-dataset",
            "dataset_digest": dataset_digest,
            "created_at": "2026-08-22T09:00:00+08:00",
        }
    )
    result_digest = digest({"summary": {}, "trades": [], "equity": [], "decisions": []})
    repository.save_result(
        run_id,
        {
            "summary": {"result_digest": result_digest},
            "trades": [],
            "daily_equity": [],
            "decisions": [],
        },
    )
    repository.update_run(
        run_id,
        status="COMPLETED",
        result_digest=result_digest,
        progress=1.0,
        progress_message="完成",
    )


def test_postgres_qualification_is_immutable_replayable_and_integrity_checked(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=3, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    manifest = _manifest()
    repository.upsert_dataset(manifest.to_dict(), "READY")
    _save_completed_run(
        repository,
        "qualification-baseline",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )
    _save_completed_run(
        repository,
        "qualification-challenger",
        "strategy-set-v2",
        "strategy-version-v2",
        manifest.manifest_digest,
        baseline_run_id="qualification-baseline",
    )
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=HistoricalDatasetCatalog(tmp_path / "datasets"),
        workers=1,
    )
    try:

        def qualify():
            return service.qualify_runs(
                baseline_run_id="qualification-baseline",
                challenger_run_id="qualification-challenger",
                protocol=_protocol(),
                hypothesis_id="challenger-beats-baseline",
                idempotency_key="qualification-create-1",
                actor_id="reviewer",
                change_note="固定 OOS evidence",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = tuple(executor.map(lambda _: qualify(), range(2)))
        assert {item[1] for item in concurrent_results} == {False, True}
        first = concurrent_results[0][0]
        replayed = concurrent_results[0][1]
        # A response-loss retry must replay the durable operation even if the
        # mutable dataset projection has changed after the original commit.
        repository.upsert_dataset(
            {
                "dataset_id": "qualification-dataset",
                "created_at": "2026-08-22T08:00:00+08:00",
                "manifest_digest": "later-dataset-digest",
                "research_eligible": False,
            },
            "READY",
        )
        second, second_replayed = service.qualify_runs(
            baseline_run_id="qualification-baseline",
            challenger_run_id="qualification-challenger",
            protocol=_protocol(),
            hypothesis_id="challenger-beats-baseline",
            idempotency_key="qualification-create-1",
            actor_id="reviewer",
            change_note="固定 OOS evidence",
        )

        assert replayed in {False, True}
        assert second_replayed is True
        assert first == second
        assert first["evidence"]["effect"] == "REVIEW_ONLY_NO_LIFECYCLE_MUTATION"
        assert first["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert first["display_status"] == "NO_QUALIFYING_STRATEGY"
        assert first["strategy_readiness"] == {
            "ready": False,
            "status": "NO_QUALIFYING_STRATEGY",
            "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
        }
        detail = service.get_qualification(first["qualification_id"])
        assert {key: detail[key] for key in first} == first
        historical_family = dict(first["family_snapshot"])
        historical_digest = historical_family.pop("family_snapshot_digest")
        assert digest(historical_family) == historical_digest
        assert historical_digest == first["family_snapshot_digest"]
        assert historical_family["attempts"][0]["qualification_id"] is None
        assert (
            detail["current_family_snapshot"]["attempts"][0]["qualification_id"]
            == first["qualification_id"]
        )
        assert (
            detail["current_family_snapshot"]["attempts"][0]["hypothesis_id"]
            == "challenger-beats-baseline"
        )
        assert service.list_qualifications()[0] == first
        with pytest.raises(BacktestIdempotencyConflict):
            service.qualify_runs(
                baseline_run_id="qualification-baseline",
                challenger_run_id="qualification-challenger",
                protocol=_protocol(),
                hypothesis_id="challenger-beats-baseline",
                idempotency_key="qualification-create-1",
                actor_id="reviewer",
                change_note="不同 request",
            )

        family = repository.get_experiment_family_for_run("qualification-challenger")
        baseline = repository.get_run("qualification-baseline")
        assert family["family_id"] == experiment_family_id(
            research_baseline_identity_digest(baseline["config"])
        )
        assert family["head_sequence"] == 1
        assert family["attempts"][0]["qualification_id"] == first["qualification_id"]

        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET actor_id = 'tampered-reviewer'
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )
        with pytest.raises(ValueError, match="actor projection"):
            service.get_qualification(first["qualification_id"])
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET actor_id = 'reviewer'
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET change_note = '被篡改的說明'
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )
        with pytest.raises(ValueError, match="change note projection"):
            service.get_qualification(first["qualification_id"])
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET change_note = '固定 OOS evidence'
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )

        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET family_snapshot_json = jsonb_set(
                    family_snapshot_json,
                    '{head_sequence}',
                    '999'::jsonb
                )
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )
        with pytest.raises(ValueError, match="family snapshot digest"):
            service.get_qualification(first["qualification_id"])
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET family_snapshot_json = jsonb_set(
                    family_snapshot_json,
                    '{head_sequence}',
                    '1'::jsonb
                )
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )

        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_qualifications
                SET evidence_json = jsonb_set(evidence_json, '{verdict}', '"ELIGIBLE_FOR_PROMOTION_REVIEW"')
                WHERE qualification_id = %s
                """,
                (first["qualification_id"],),
            )
        with pytest.raises(ValueError, match="evidence digest"):
            service.get_qualification(first["qualification_id"])
    finally:
        service.close()
        pool.close()


def test_postgres_equivalent_baseline_runs_share_one_family_budget(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=3, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    manifest = _manifest()
    repository.upsert_dataset(manifest.to_dict(), "READY")
    _save_completed_run(
        repository,
        "equivalent-baseline-a",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )
    _save_completed_run(
        repository,
        "equivalent-baseline-b",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )
    try:
        _save_completed_run(
            repository,
            "equivalent-challenger-a",
            "strategy-set-v2",
            "strategy-version-v2",
            manifest.manifest_digest,
            baseline_run_id="equivalent-baseline-a",
        )
        _save_completed_run(
            repository,
            "equivalent-challenger-b",
            "strategy-set-v3",
            "strategy-version-v3",
            manifest.manifest_digest,
            baseline_run_id="equivalent-baseline-b",
        )

        family_a = repository.get_experiment_family_for_run("equivalent-challenger-a")
        family_b = repository.get_experiment_family_for_run("equivalent-challenger-b")
        assert family_a == family_b
        assert family_a["baseline_run_id"] == "equivalent-baseline-a"
        assert family_a["head_sequence"] == 2
        assert [item["attempt_sequence"] for item in family_a["attempts"]] == [1, 2]
        assert family_a["family_id"] == experiment_family_id(family_a["research_baseline_digest"])
    finally:
        repository.close()
        pool.close()


def test_postgres_family_allocates_monotonic_attempts_concurrently(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=3, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    manifest = _manifest()
    repository.upsert_dataset(manifest.to_dict(), "READY")
    _save_completed_run(
        repository,
        "family-baseline",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )

    def create(run_id: str, version: str):
        baseline_config = repository.get_run("family-baseline")["config"]
        config = _config(
            f"set-{version}",
            version,
            manifest.manifest_digest,
            baseline_run_id="family-baseline",
            baseline_config=baseline_config,
        )
        return repository.create_run(
            {
                "run_id": run_id,
                "idempotency_key": f"create-{run_id}",
                "status": "QUEUED",
                "config": config,
                "config_digest": digest(config),
                "dataset_id": "qualification-dataset",
                "dataset_digest": manifest.manifest_digest,
                "created_at": "2026-08-22T09:00:00+08:00",
            }
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            tuple(
                executor.map(
                    lambda args: create(*args),
                    (
                        ("family-challenger-1", "strategy-version-v2"),
                        ("family-challenger-2", "strategy-version-v3"),
                    ),
                )
            )
        family = repository.get_experiment_family_for_run("family-challenger-1")
        assert family["head_sequence"] == 2
        assert [item["attempt_sequence"] for item in family["attempts"]] == [1, 2]
        assert {item["run_id"] for item in family["attempts"]} == {
            "family-challenger-1",
            "family-challenger-2",
        }
    finally:
        repository.close()
        pool.close()


def test_postgres_qualification_rejects_run_config_digest_tamper(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=3, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    manifest = _manifest()
    repository.upsert_dataset(manifest.to_dict(), "READY")
    _save_completed_run(
        repository,
        "tamper-baseline",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )
    _save_completed_run(
        repository,
        "tamper-challenger",
        "strategy-set-v2",
        "strategy-version-v2",
        manifest.manifest_digest,
        baseline_run_id="tamper-baseline",
    )
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=HistoricalDatasetCatalog(tmp_path / "datasets"),
        workers=1,
    )
    try:
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_runs
                SET config_json = jsonb_set(config_json, '{commission_rate}', '"0"')
                WHERE run_id = 'tamper-challenger'
                """
            )
        with pytest.raises(ValueError, match="Run config digest"):
            service.qualify_runs(
                baseline_run_id="tamper-baseline",
                challenger_run_id="tamper-challenger",
                protocol=_protocol(),
                hypothesis_id="tamper-must-fail",
                idempotency_key="tamper-qualification",
                actor_id="reviewer",
                change_note="tamper probe",
            )
    finally:
        service.close()
        pool.close()


def test_postgres_qualification_rejects_run_row_dataset_identity_tamper(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=3, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    manifest = _manifest()
    replacement = _manifest("replacement-dataset")
    repository.upsert_dataset(manifest.to_dict(), "READY")
    repository.upsert_dataset(replacement.to_dict(), "READY")
    _save_completed_run(
        repository,
        "dataset-tamper-baseline",
        "strategy-set-v1",
        "strategy-version-v1",
        manifest.manifest_digest,
    )
    _save_completed_run(
        repository,
        "dataset-tamper-challenger",
        "strategy-set-v2",
        "strategy-version-v2",
        manifest.manifest_digest,
        baseline_run_id="dataset-tamper-baseline",
    )
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=HistoricalDatasetCatalog(tmp_path / "datasets"),
        workers=1,
    )
    try:
        with repository._transaction() as cursor:
            cursor.execute(
                """
                UPDATE backtest_runs
                SET dataset_id = 'replacement-dataset',
                    dataset_digest = %s
                WHERE run_id IN (
                    'dataset-tamper-baseline',
                    'dataset-tamper-challenger'
                )
                """,
                (replacement.manifest_digest,),
            )
        with pytest.raises(ValueError, match="Run dataset_id identity"):
            service.qualify_runs(
                baseline_run_id="dataset-tamper-baseline",
                challenger_run_id="dataset-tamper-challenger",
                protocol=_protocol(),
                hypothesis_id="dataset-row-tamper-must-fail",
                idempotency_key="dataset-row-tamper-qualification",
                actor_id="reviewer",
                change_note="dataset row tamper probe",
            )
    finally:
        service.close()
        pool.close()
