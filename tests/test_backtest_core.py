"""Focused contracts for the durable historical-backtest bounded context."""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.decision_aggregator import DecisionAggregator
from backtest.domain import (
    AggregationPolicy,
    BacktestRunConfig,
    EvaluationStatus,
    HistoricalBar,
    StrategyEvaluation,
    StrategySetSnapshot,
    StrategySide,
)
from backtest.engine import HistoricalBacktestEngine
from backtest.metrics import summarize_run
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MockProvider


TAIPEI = ZoneInfo("Asia/Taipei")


def _bar(day: int, hour: int, minute: int, opened: int, high: int, low: int, close: int) -> HistoricalBar:
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(2026, 1, day, hour, minute, tzinfo=TAIPEI),
        open=Decimal(str(opened)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=10_000,
    )


def _bars() -> list[HistoricalBar]:
    return [
        _bar(2, 13, 25, 100, 101, 99, 100),
        _bar(3, 9, 0, 103, 104, 102, 104),
        _bar(3, 9, 1, 104, 106, 103, 105),
        _bar(3, 9, 2, 105, 109, 104, 108),
        _bar(3, 13, 25, 108, 109, 107, 108),
    ]


def _config(entry: tuple[str, ...] = ("legacy_gap_volume_vwap_entry_v1",)) -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="dataset-fixture",
        dataset_digest="fixture-digest",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=entry,
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
            priority_order=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
        minimum_oos_trades=1,
    )


def test_any_all_and_at_least_n_aggregation_are_deterministic() -> None:
    event_at = datetime(2026, 1, 3, 9, 0, tzinfo=TAIPEI)
    evaluations = (
        StrategyEvaluation("a", "策略 A", "v1", StrategySide.ENTRY, EvaluationStatus.TRIGGERED, "2330", event_at, "達標"),
        StrategyEvaluation("b", "策略 B", "v1", StrategySide.ENTRY, EvaluationStatus.NOT_TRIGGERED, "2330", event_at, "未達標"),
    )
    aggregator = DecisionAggregator()
    any_decision = aggregator.aggregate(
        symbol="2330", event_at=event_at, side=StrategySide.ENTRY,
        policy=AggregationPolicy.ANY, minimum_trigger_count=1,
        selected_strategy_ids=("a", "b"), priority_order=("a", "b"),
        evaluations=evaluations, strategy_set_digest="set",
    )
    all_decision = aggregator.aggregate(
        symbol="2330", event_at=event_at, side=StrategySide.ENTRY,
        policy=AggregationPolicy.ALL, minimum_trigger_count=1,
        selected_strategy_ids=("a", "b"), priority_order=("a", "b"),
        evaluations=evaluations, strategy_set_digest="set",
    )
    at_least_two = aggregator.aggregate(
        symbol="2330", event_at=event_at, side=StrategySide.ENTRY,
        policy=AggregationPolicy.AT_LEAST_N, minimum_trigger_count=2,
        selected_strategy_ids=("a", "b"), priority_order=("a", "b"),
        evaluations=evaluations, strategy_set_digest="set",
    )

    assert any_decision is not None
    assert any_decision.primary_strategy_id == "a"
    assert any_decision.triggered_strategy_ids == ("a",)
    assert all_decision is None
    assert at_least_two is None


def test_strategy_set_accepts_single_or_multiple_unique_strategies() -> None:
    single = StrategySetSnapshot(
        entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
        exit_strategy_ids=("end_of_day_exit_v1",),
    )
    multiple = StrategySetSnapshot(
        entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1", "momentum_breakout_entry_v1"),
        exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
        entry_policy=AggregationPolicy.AT_LEAST_N,
        entry_min_trigger_count=2,
    )

    assert len(single.entry_strategy_ids) == len(single.exit_strategy_ids) == 1
    assert len(multiple.entry_strategy_ids) == len(multiple.exit_strategy_ids) == 2
    with pytest.raises(ValueError, match="不可重複選擇"):
        StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1", "legacy_gap_volume_vwap_entry_v1"),
            exit_strategy_ids=("end_of_day_exit_v1",),
        )


def test_engine_uses_next_bar_entry_and_keeps_entry_exit_attribution() -> None:
    result = HistoricalBacktestEngine().run(config=_config(), bars=_bars())

    assert len(result.trades) == 1
    trade = result.trades[0].to_dict()
    assert trade["entry"]["filled_at"] == "2026-01-03T09:02:00+08:00"
    assert trade["entry_decision"]["event_at"] == "2026-01-03T09:01:00+08:00"
    assert trade["entry_decision"]["primary_strategy_id"] == "legacy_gap_volume_vwap_entry_v1"
    assert trade["exit_decision"]["primary_strategy_id"] == "take_profit_exit_v1"
    assert len(result.orders) == 2


def test_engine_result_is_reproducible_across_repeated_runs() -> None:
    """Audit output must not contain random order/fill/trade identifiers."""
    config = _config()
    results = [HistoricalBacktestEngine().run(config=config, bars=_bars()) for _ in range(10)]
    outputs = [result.to_dict() for result in results]
    digests = [
        summarize_run(config=config, result=result, dataset_research_eligible=True)["result_digest"]
        for result in results
    ]

    assert outputs[1:] == [outputs[0]] * 9
    assert len(set(digests)) == 1


def test_durable_service_persists_run_trade_and_comparison() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        manifest = catalog.create_imported_dataset(
            bars=_bars(),
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        repository.upsert_dataset(manifest.to_dict(), "READY")
        service = BacktestApplicationService(
            MockProvider(), repository=repository, catalog=catalog, workers=1,
        )
        try:
            baseline = _create_and_wait(service, manifest.dataset_id, "backtest-test-baseline")
            challenger = _create_and_wait(
                service,
                manifest.dataset_id,
                "backtest-test-challenger",
                entry_strategy_ids=["legacy_gap_volume_vwap_entry_v1", "momentum_breakout_entry_v1"],
                entry_policy="ANY",
            )
            stored = service.trades(baseline["run_id"], page=1, page_size=10)
            comparison = service.compare(baseline["run_id"], challenger["run_id"])

            assert stored["total"] == 1
            assert stored["trades"][0]["entry_strategies"][0]["strategy_name"] == "跳空＋VWAP 買入策略"
            assert comparison["comparable"] is True
            assert comparison["comparison_id"].startswith("comparison-")
        finally:
            service.close()


def _create_and_wait(
    service: BacktestApplicationService,
    dataset_id: str,
    idempotency_key: str,
    **overrides: object,
) -> dict[str, object]:
    request: dict[str, object] = {
        "dataset_id": dataset_id,
        "entry_strategy_ids": ["legacy_gap_volume_vwap_entry_v1"],
        "exit_strategy_ids": ["take_profit_exit_v1", "end_of_day_exit_v1"],
        "priority_order": ["take_profit_exit_v1", "end_of_day_exit_v1"],
        "minimum_oos_trades": 1,
        "idempotency_key": idempotency_key,
    }
    request.update(overrides)
    run, _ = service.create_run(**request)  # type: ignore[arg-type]
    for _ in range(100):
        current = service.get_run(run["run_id"])
        if current["status"] in {"COMPLETED", "FAILED"}:
            assert current["status"] == "COMPLETED", current["error_message"]
            return current
        time.sleep(0.01)
    raise AssertionError("backtest worker did not finish")
