from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import HistoricalBar
from backtest.migrations import apply_migrations
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.repository import BacktestIdempotencyConflict
from market_data.provider import MockProvider
from strategy_catalog.application import AtomicStrategyCatalogService
from strategy_catalog.drafts import PublishStrategyRequest
from strategy_catalog.domain import StrategyRole
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _one_minute_bars() -> list[HistoricalBar]:
    bars = []
    for minute in range(21):
        close = Decimal("100") + Decimal(minute) / Decimal("10")
        bars.append(
            HistoricalBar(
                symbol="2330",
                name="台積電",
                market="TWSE",
                timestamp=datetime(2026, 1, 5, 9, minute, tzinfo=TAIPEI),
                open=close,
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=10_000 + minute * 100,
            )
        )
    bars.append(
        HistoricalBar(
            symbol="2330",
            name="台積電",
            market="TWSE",
            timestamp=datetime(2026, 1, 5, 13, 25, tzinfo=TAIPEI),
            open=Decimal("102"),
            high=Decimal("102.5"),
            low=Decimal("101.5"),
            close=Decimal("102"),
            volume=20_000,
        )
    )
    return bars


def _wait_for_terminal(service: BacktestApplicationService, run_id: str) -> dict:
    current = service.get_run(run_id)
    for _ in range(200):
        if current["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return current
        time.sleep(0.01)
        current = service.get_run(run_id)
    return current


def test_exact_strategy_set_launches_reproducible_atomic_backtest(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    apply_migrations(postgres_test_connection)
    atomic_connection = psycopg.connect(postgres_test_dsn)
    backtest_connection = psycopg.connect(postgres_test_dsn)
    atomic_repository = PostgresAtomicStrategyRepository(atomic_connection)
    registry = AtomicStrategyRegistry()
    atomic_service = AtomicStrategyCatalogService(atomic_repository, registry.templates())
    atomic_service.sync_templates()

    draft = atomic_service.create_draft(
        "above_vwap_entry",
        {},
        actor_id="local-researcher",
        change_note="atomic web integration",
    )
    published = atomic_service.publish(
        PublishStrategyRequest(
            draft_id=draft.draft_id,
            idempotency_key="atomic-web-publish-1",
            expected_draft_revision=1,
            actor_id="local-researcher",
            actor_session_id="test-session",
        )
    )
    version = atomic_service.get_version(published.strategy_version_id)
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="atomic-web-set-version-1",
        strategy_set_id="atomic-web-set",
        version_number=1,
        display_name_zh_tw="VWAP 原子策略",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(
            StrategySetMemberSnapshot(
                strategy_version_id=version.strategy_version_id,
                strategy_id=version.strategy_id,
                role=StrategyRole.ENTRY,
                configuration_digest=version.configuration_digest,
                implementation_digest=version.implementation_digest,
                member_order=0,
                attribution_priority=0,
            ),
        ),
    )
    atomic_service.save_strategy_set(snapshot, actor_id="local-researcher")

    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    manifest = catalog.create_imported_dataset(
        bars=_one_minute_bars(),
        source="atomic-web-fixture",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    repository = PostgresBacktestRepository(backtest_connection)
    repository.upsert_dataset(manifest.to_dict(), "READY")
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=catalog,
        atomic_repository=atomic_repository,
        atomic_registry=registry,
        workers=1,
    )
    try:
        run, replayed = service.create_atomic_run(
            dataset_id=manifest.dataset_id,
            strategy_set_version_id=snapshot.strategy_set_version_id,
            minimum_oos_trades=1,
            idempotency_key="atomic-web-backtest-1",
        )
        assert replayed is False
        current = _wait_for_terminal(service, run["run_id"])
        assert current["status"] == "COMPLETED", current.get("error_message")
        atomic_snapshot = current["config"]["atomic_strategy_run_snapshot"]
        assert atomic_snapshot["contract_version"] == "atomic-backtest-run-snapshot-v2"
        assert atomic_snapshot["strategy_set"]["strategy_set_version_id"] == snapshot.strategy_set_version_id
        assert atomic_snapshot["strategy_set"]["members"][0]["strategy_version_id"] == version.strategy_version_id
        assert atomic_snapshot["snapshot_digest"]

        cloned, clone_replayed = service.clone_run(
            run["run_id"],
            overrides={"starting_cash": "12000000"},
            idempotency_key="atomic-web-clone-1",
            change_note="調整起始資金",
        )
        assert clone_replayed is False
        cloned_current = _wait_for_terminal(service, cloned["run_id"])
        assert cloned_current["status"] == "COMPLETED", cloned_current.get("error_message")
        assert cloned_current["config"]["starting_cash"] == "12000000"
        assert cloned_current["config"]["atomic_strategy_run_snapshot"] == atomic_snapshot

        with pytest.raises(ValueError, match="不可覆寫：strategy_set"):
            service.clone_run(
                run["run_id"],
                overrides={"strategy_set": {"entry_strategy_ids": ["raw-id"]}},
                idempotency_key="atomic-web-clone-raw-id",
                change_note="不允許更換原子策略身分",
            )

        repository.update_run(run["run_id"], status="FAILED", error_message="test retry")
        retried, retry_replayed = service.retry_run(
            run["run_id"],
            idempotency_key="atomic-web-retry-1",
        )
        assert retry_replayed is False
        retried_current = _wait_for_terminal(service, retried["run_id"])
        assert retried_current["status"] == "COMPLETED", retried_current.get("error_message")
        assert retried_current["config"]["atomic_strategy_run_snapshot"] == atomic_snapshot
    finally:
        service.close()
        atomic_connection.close()


def test_postgres_pool_checks_out_distinct_connections_for_concurrent_operations(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=2, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    barrier = Barrier(2)

    def transaction_backend_pid(_: int) -> int:
        with repository._transaction() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            pid = int(cursor.fetchone()[0])
            barrier.wait(timeout=5)
            return pid

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            backend_pids = tuple(executor.map(transaction_backend_pid, range(2)))
        assert len(set(backend_pids)) == 2
    finally:
        pool.close()


def test_postgres_concurrent_run_create_replays_and_checks_request_digest(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(postgres_test_dsn, min_size=1, max_size=2, open=True)
    repository = PostgresBacktestRepository(pool=pool)
    barrier = Barrier(2)

    def create_once(index: int):
        barrier.wait(timeout=5)
        return repository.create_run(
            {
                "run_id": f"concurrent-run-{index}",
                "idempotency_key": "concurrent-run-key",
                "status": "QUEUED",
                "config": {"contract": "same"},
                "config_digest": "same-config-digest",
                "dataset_id": "dataset-concurrent",
                "dataset_digest": "dataset-digest",
                "created_at": "2026-08-21T09:00:00+08:00",
            }
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(create_once, range(2)))
        assert {item[1] for item in results} == {False, True}
        assert len({item[0]["run_id"] for item in results}) == 1
        with pytest.raises(BacktestIdempotencyConflict):
            repository.create_run(
                {
                    "run_id": "concurrent-run-conflict",
                    "idempotency_key": "concurrent-run-key",
                    "status": "QUEUED",
                    "config": {"contract": "different"},
                    "config_digest": "different-config-digest",
                    "dataset_id": "dataset-concurrent",
                    "dataset_digest": "dataset-digest",
                    "created_at": "2026-08-21T09:01:00+08:00",
                }
            )

        repository.create_run(
            {
                "run_id": "atomic-cancel-run",
                "idempotency_key": "atomic-cancel-create",
                "status": "QUEUED",
                "config": {"atomic_strategy_run_snapshot": {"snapshot_digest": "atomic"}},
                "config_digest": "atomic-cancel-config",
                "dataset_id": "dataset-concurrent",
                "dataset_digest": "dataset-digest",
                "created_at": "2026-08-21T09:02:00+08:00",
            }
        )
        cancelled, cancel_replayed = repository.cancel_atomic_run(
            "atomic-cancel-run",
            idempotency_key="atomic-cancel-key",
            actor_id="reviewer",
            request_digest="atomic-cancel-request-digest",
        )
        replay, replayed_again = repository.cancel_atomic_run(
            "atomic-cancel-run",
            idempotency_key="atomic-cancel-key",
            actor_id="reviewer",
            request_digest="atomic-cancel-request-digest",
        )
        assert cancel_replayed is False
        assert replayed_again is True
        assert cancelled["status"] == replay["status"] == "CANCELLING"
        with pytest.raises(BacktestIdempotencyConflict):
            repository.cancel_atomic_run(
                "atomic-cancel-run",
                idempotency_key="atomic-cancel-key",
                actor_id="reviewer",
                request_digest="different-cancel-digest",
            )
    finally:
        pool.close()
