from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.dataset_binding import (
    ATOMIC_BACKTEST_DEFAULT,
    AtomicBacktestBindingChanged,
)
from backtest.domain import HistoricalBar
from backtest.migrations import apply_migrations
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.repository import BacktestIdempotencyConflict
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MockProvider
from strategy_catalog.application import AtomicStrategyCatalogService
from strategy_catalog.drafts import PublishStrategyRequest, StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.domain import StrategyRole
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository
from strategy_catalog.repository import StrategyCatalogConflict
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


def _finmind_dataset(
    catalog: HistoricalDatasetCatalog,
    identity: str,
    *,
    amount_contract: dict[str, object] | None = None,
):
    bars = _one_minute_bars()
    source_digest = canonical_digest({"source": identity})
    dataset_id = f"dataset-finmind-sponsor-sha256-{source_digest}"
    plan_identity = {
        "dataset_id": dataset_id,
        "source_snapshot_digest": source_digest,
    }
    if amount_contract is None:
        amount_contract = {
            "is_actual_turnover": False,
            "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
            "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
        }
        amount_contract["digest"] = canonical_digest(amount_contract)
    return catalog.create_finmind_snapshot_dataset(
        dataset_id=dataset_id,
        symbol_streams=(bars,),
        created_at=datetime(2026, 1, 5, 13, 30, tzinfo=TAIPEI),
        source="FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        requested_symbols=("2330",),
        expected_bar_count=len(bars),
        start_date="2026-01-05",
        end_date="2026-01-05",
        issues=("AMOUNT_DERIVED_PROXY",),
        volume_contract={"unit": "COMMON_LOTS"},
        amount_contract=amount_contract,
        source_snapshot_digest=source_digest,
        plan_identity=plan_identity,
        plan_identity_digest=canonical_digest(plan_identity),
    )


def _wait_for_terminal(service: BacktestApplicationService, run_id: str) -> dict:
    current = service.get_run(run_id)
    for _ in range(200):
        if current["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return current
        time.sleep(0.01)
        current = service.get_run(run_id)
    return current


class _ArchivedStrategySetRepository:
    def is_strategy_set_archived(self, strategy_set_version_id: str) -> bool:
        assert strategy_set_version_id == "archived-strategy-set-version"
        return True

    def get_strategy_set(self, strategy_set_version_id: str):
        raise AssertionError("封存組合必須在載入 exact snapshot 前被拒絕")


class _AtomicVersionSetRepository:
    def __init__(
        self,
        snapshot: ExactStrategySetSnapshot,
        version: StrategyVersion,
    ) -> None:
        self._snapshot = snapshot
        self._version = version

    def is_strategy_set_archived(self, strategy_set_version_id: str) -> bool:
        assert strategy_set_version_id == self._snapshot.strategy_set_version_id
        return False

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot:
        assert strategy_set_version_id == self._snapshot.strategy_set_version_id
        return self._snapshot

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        assert strategy_version_id == self._version.strategy_version_id
        return self._version


def _atomic_vwap_fixture() -> tuple[
    AtomicStrategyRegistry,
    _AtomicVersionSetRepository,
    ExactStrategySetSnapshot,
]:
    registry = AtomicStrategyRegistry()
    template = registry.strategy("above_vwap_entry").template
    parameters = template.validate_parameters({})
    parameters_digest = canonical_digest(parameters)
    version = StrategyVersion(
        strategy_version_id="auto-dataset-vwap-version-1",
        strategy_id=template.strategy_id,
        source_draft_id="auto-dataset-draft-1",
        version_number=1,
        parameters=parameters,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=parameters_digest,
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=canonical_digest(
            {
                "strategy_id": template.strategy_id,
                "parameters": parameters,
                "parameter_schema_version": template.parameter_schema.version,
                "parameter_schema_digest": template.parameter_schema.schema_digest,
                "parameters_digest": parameters_digest,
                "template_digest": template.template_digest,
                "implementation_digest": template.implementation_digest,
            }
        ),
        change_note="automatic dataset fixture",
        created_by="test",
        created_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
    )
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="auto-dataset-set-version-1",
        strategy_set_id="auto-dataset-set-1",
        version_number=1,
        display_name_zh_tw="自動資料快照測試",
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
    return registry, _AtomicVersionSetRepository(snapshot, version), snapshot


def test_archived_strategy_set_cannot_launch_new_backtest(tmp_path) -> None:
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    manifest = catalog.create_imported_dataset(
        bars=_one_minute_bars(),
        source="archived-set-fixture",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    repository.upsert_dataset(manifest.to_dict(), "READY")
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=catalog,
        atomic_repository=_ArchivedStrategySetRepository(),
        workers=1,
    )
    try:
        with pytest.raises(StrategyCatalogConflict) as archived:
            service.create_atomic_run(
                strategy_set_version_id="archived-strategy-set-version",
                idempotency_key="archived-set-backtest",
            )
        assert archived.value.code == "STRATEGY_SET_ARCHIVED"
    finally:
        service.close()


def test_atomic_standalone_run_never_falls_back_to_sqlite_ready_datasets(
    tmp_path,
) -> None:
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    first = catalog.create_imported_dataset(
        bars=_one_minute_bars(),
        source="automatic-dataset-older",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    time.sleep(0.002)
    second = catalog.create_imported_dataset(
        bars=_one_minute_bars(),
        source="automatic-dataset-newer",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    repository.upsert_dataset(first.to_dict(), "READY")
    repository.upsert_dataset(second.to_dict(), "READY")
    time.sleep(0.002)
    newest_exploratory = catalog.create_imported_dataset(
        bars=_one_minute_bars(),
        source="automatic-dataset-newest-exploratory",
        universe_scope="CURRENT_SNAPSHOT",
        research_eligible=False,
    )
    repository.upsert_dataset(newest_exploratory.to_dict(), "READY")
    registry, atomic_repository, snapshot = _atomic_vwap_fixture()
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=catalog,
        atomic_repository=atomic_repository,
        atomic_registry=registry,
        workers=1,
    )
    try:
        with pytest.raises(RuntimeError, match="Dataset binding requires PostgreSQL"):
            service.create_atomic_run(
                strategy_set_version_id=snapshot.strategy_set_version_id,
                expected_binding_revision=1,
                expected_dataset_digest=second.manifest_digest,
                idempotency_key="automatic-dataset-run-1",
            )
    finally:
        service.close()


def test_atomic_run_without_binding_preconditions_fails_closed(tmp_path) -> None:
    registry, atomic_repository, snapshot = _atomic_vwap_fixture()
    service = BacktestApplicationService(
        MockProvider(),
        repository=SQLiteBacktestRepository(tmp_path / "backtest.sqlite3"),
        catalog=HistoricalDatasetCatalog(tmp_path / "datasets"),
        atomic_repository=atomic_repository,
        atomic_registry=registry,
        workers=1,
    )
    try:
        with pytest.raises(ValueError, match="binding revision"):
            service.create_atomic_run(
                strategy_set_version_id=snapshot.strategy_set_version_id,
                idempotency_key="automatic-dataset-missing-1",
            )
    finally:
        service.close()


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
    manifest = _finmind_dataset(catalog, "atomic-web-fixture")
    repository = PostgresBacktestRepository(backtest_connection)
    repository.register_immutable_dataset(manifest.to_dict())
    binding, replayed_binding = repository.activate_dataset_binding(
        binding_name=ATOMIC_BACKTEST_DEFAULT,
        dataset_id=manifest.dataset_id,
        dataset_digest=manifest.manifest_digest,
        plan_identity_digest=str(manifest.plan_identity_digest),
        expected_revision=0,
        idempotency_key="atomic-web-binding-1",
        actor_id="test",
        change_note="activate test Dataset",
    )
    assert replayed_binding is False
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
            strategy_set_version_id=snapshot.strategy_set_version_id,
            expected_binding_revision=binding["revision"],
            expected_dataset_digest=manifest.manifest_digest,
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


def test_atomic_binding_switch_replays_original_run_and_rejects_stale_new_run(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    repository = PostgresBacktestRepository(psycopg.connect(postgres_test_dsn))
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    first = _finmind_dataset(catalog, "g5-binding-first")
    second = _finmind_dataset(catalog, "g5-binding-second")
    repository.register_immutable_dataset(first.to_dict())
    repository.register_immutable_dataset(second.to_dict())
    first_binding, _ = repository.activate_dataset_binding(
        binding_name=ATOMIC_BACKTEST_DEFAULT,
        dataset_id=first.dataset_id,
        dataset_digest=first.manifest_digest,
        plan_identity_digest=str(first.plan_identity_digest),
        expected_revision=0,
        idempotency_key="g5-bind-first",
        actor_id="test",
        change_note="activate first",
    )
    registry, atomic_repository, snapshot = _atomic_vwap_fixture()
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=catalog,
        atomic_repository=atomic_repository,
        atomic_registry=registry,
        workers=1,
    )
    try:
        status = service.atomic_backtest_dataset_status(
            strategy_set_version_id=snapshot.strategy_set_version_id
        )
        assert status["available"] is True
        assert status["binding_revision"] == 1
        assert status["dataset_id"] == first.dataset_id
        assert status["amount_kind"] == "DERIVED_CLOSE_X_VOLUME_PROXY"

        run, replayed = service.create_atomic_run(
            strategy_set_version_id=snapshot.strategy_set_version_id,
            expected_binding_revision=1,
            expected_dataset_digest=first.manifest_digest,
            idempotency_key="g5-run-response-loss",
        )
        assert replayed is False
        feature_requests = run["config"]["atomic_strategy_run_snapshot"][
            "feature_requests"
        ]
        vwap_request = feature_requests[0]["requests"][0]
        assert vwap_request["dataset_input_contract"]["amount_contract"] == first.amount_contract
        assert run["config"]["dataset_amount_contract"] == first.amount_contract
        completed = _wait_for_terminal(service, run["run_id"])
        assert completed["status"] == "COMPLETED", completed.get("error_message")
        result = repository.get_result(run["run_id"])
        evaluation = next(
            evaluation
            for decision in result["decisions"]
            for evaluation in decision["evaluations"]
            if evaluation["strategy_id"] == "above_vwap_entry"
        )
        feature_evidence = evaluation["observed"]["feature_input_evidence"]
        assert feature_evidence["dataset_input_contract"]["amount_contract"] == (
            first.amount_contract
        )
        assert len(feature_evidence["feature_input_digest"]) == 64

        second_binding, _ = repository.activate_dataset_binding(
            binding_name=ATOMIC_BACKTEST_DEFAULT,
            dataset_id=second.dataset_id,
            dataset_digest=second.manifest_digest,
            plan_identity_digest=str(second.plan_identity_digest),
            expected_revision=1,
            idempotency_key="g5-bind-second",
            actor_id="test",
            change_note="activate second",
        )
        assert second_binding["revision"] == 2

        replay, idempotent = service.create_atomic_run(
            strategy_set_version_id=snapshot.strategy_set_version_id,
            expected_binding_revision=1,
            expected_dataset_digest=first.manifest_digest,
            idempotency_key="g5-run-response-loss",
        )
        assert idempotent is True
        assert replay["run_id"] == run["run_id"]
        assert replay["dataset_id"] == first.dataset_id

        baseline_status = service.atomic_backtest_dataset_status(
            strategy_set_version_id=snapshot.strategy_set_version_id,
            baseline_run_id=run["run_id"],
        )
        assert baseline_status["resolution_mode"] == "BASELINE_DATASET"
        assert baseline_status["dataset_id"] == first.dataset_id
        challenger, challenger_replayed = service.create_atomic_run(
            strategy_set_version_id=snapshot.strategy_set_version_id,
            baseline_run_id=run["run_id"],
            idempotency_key="g5-run-challenger-original-dataset",
        )
        assert challenger_replayed is False
        assert challenger["dataset_id"] == first.dataset_id

        with pytest.raises(BacktestIdempotencyConflict):
            service.create_atomic_run(
                strategy_set_version_id=snapshot.strategy_set_version_id,
                expected_binding_revision=1,
                expected_dataset_digest=first.manifest_digest,
                position_fraction="0.20",
                idempotency_key="g5-run-response-loss",
            )
        with pytest.raises(AtomicBacktestBindingChanged):
            service.create_atomic_run(
                strategy_set_version_id=snapshot.strategy_set_version_id,
                expected_binding_revision=1,
                expected_dataset_digest=first.manifest_digest,
                idempotency_key="g5-run-stale-binding",
            )
        assert {item["run_id"] for item in repository.list_runs()} == {
            run["run_id"],
            challenger["run_id"],
        }
    finally:
        service.close()


def test_vwap_atomic_run_rejects_ready_dataset_without_amount_contract(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    repository = PostgresBacktestRepository(psycopg.connect(postgres_test_dsn))
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    manifest = _finmind_dataset(
        catalog,
        "g5-no-amount-contract",
        amount_contract={},
    )
    repository.register_immutable_dataset(manifest.to_dict())
    binding, _ = repository.activate_dataset_binding(
        binding_name=ATOMIC_BACKTEST_DEFAULT,
        dataset_id=manifest.dataset_id,
        dataset_digest=manifest.manifest_digest,
        plan_identity_digest=str(manifest.plan_identity_digest),
        expected_revision=0,
        idempotency_key="g5-bind-no-amount",
        actor_id="test",
        change_note="negative amount contract",
    )
    registry, atomic_repository, snapshot = _atomic_vwap_fixture()
    service = BacktestApplicationService(
        MockProvider(),
        repository=repository,
        catalog=catalog,
        atomic_repository=atomic_repository,
        atomic_registry=registry,
        workers=1,
    )
    try:
        with pytest.raises(ValueError, match="amount contract"):
            service.create_atomic_run(
                strategy_set_version_id=snapshot.strategy_set_version_id,
                expected_binding_revision=binding["revision"],
                expected_dataset_digest=manifest.manifest_digest,
                idempotency_key="g5-run-no-amount",
            )
        assert repository.list_runs() == []
    finally:
        service.close()


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


def test_postgres_worker_status_cas_cannot_overwrite_committed_cancellation(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    pool_module = pytest.importorskip("psycopg_pool")
    apply_migrations(postgres_test_connection)
    pool = pool_module.ConnectionPool(
        postgres_test_dsn,
        min_size=1,
        max_size=2,
        open=True,
    )
    repository = PostgresBacktestRepository(pool=pool)
    repository.create_run(
        {
            "run_id": "worker-cancel-cas-run",
            "idempotency_key": "worker-cancel-cas-create",
            "status": "QUEUED",
            "config": {
                "atomic_strategy_run_snapshot": {"snapshot_digest": "atomic"}
            },
            "config_digest": "worker-cancel-cas-config",
            "dataset_id": "dataset-worker-cancel-cas",
            "dataset_digest": "dataset-worker-cancel-cas-digest",
            "created_at": "2026-08-21T09:00:00+08:00",
        }
    )
    barrier = Barrier(2)
    cancellation_committed = Event()

    def accept_cancellation():
        barrier.wait(timeout=5)
        result = repository.cancel_atomic_run(
            "worker-cancel-cas-run",
            idempotency_key="worker-cancel-cas-key",
            actor_id="reviewer",
            request_digest="worker-cancel-cas-request",
        )
        cancellation_committed.set()
        return result

    def attempt_worker_preflight():
        barrier.wait(timeout=5)
        assert cancellation_committed.wait(timeout=5)
        return repository.transition_run_status(
            "worker-cancel-cas-run",
            expected_statuses=("QUEUED",),
            status="PREFLIGHT",
            progress_message="worker preflight",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            cancel_future = executor.submit(accept_cancellation)
            worker_future = executor.submit(attempt_worker_preflight)
            cancelled, replayed = cancel_future.result(timeout=10)
            current, changed = worker_future.result(timeout=10)
        assert replayed is False
        assert cancelled["status"] == "CANCELLING"
        assert changed is False
        assert current["status"] == "CANCELLING"
        assert repository.get_run("worker-cancel-cas-run")["status"] == "CANCELLING"
    finally:
        pool.close()
