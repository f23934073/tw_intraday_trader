"""Contracts for cadence-gated experimental historical strategies."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import (
    BacktestRunConfig,
    EvaluationStatus,
    HistoricalBar,
    StrategySetSnapshot,
    digest,
)
from backtest.engine import HistoricalBacktestEngine
from backtest.features import BarFeatureState, PositionStrategyContext
from backtest.indicators import (
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    relative_strength_index,
)
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyContext, StrategyRegistry
from market_data.provider import MockProvider


TAIPEI = ZoneInfo("Asia/Taipei")


def _bar(
    minute: int,
    close: Decimal | int | str,
    *,
    symbol: str = "2330",
    day: int = 5,
    hour: int = 9,
    high: Decimal | int | str | None = None,
    low: Decimal | int | str | None = None,
) -> HistoricalBar:
    close_value = Decimal(str(close))
    high_value = Decimal(str(high)) if high is not None else close_value + Decimal("1")
    low_value = Decimal(str(low)) if low is not None else close_value - Decimal("1")
    return HistoricalBar(
        symbol=symbol,
        name=symbol,
        market="TWSE",
        timestamp=datetime(2026, 1, day, hour, minute, tzinfo=TAIPEI),
        open=close_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=1_000,
    )


def _context(
    bar: HistoricalBar,
    features,
    previous_features=None,
    position: PositionStrategyContext | None = None,
) -> StrategyContext:
    return StrategyContext(
        symbol=bar.symbol,
        bar=bar,
        previous_close=Decimal("100"),
        session_open=Decimal("100"),
        session_high_before=Decimal("101"),
        vwap=Decimal("100"),
        cumulative_volume=1_000,
        bars_seen=features.bars_seen,
        is_last_bar=False,
        entry_price=position.entry_fill_price if position else None,
        features=features,
        previous_features=previous_features,
        position=position,
    )


def test_decimal_indicator_formulas_freeze_seed_and_edge_cases() -> None:
    values = tuple(Decimal(value) for value in (1, 2, 3, 4))
    assert exponential_moving_average(values, 3) == Decimal("3.0")
    assert relative_strength_index(tuple(Decimal(100) for _ in range(15)), 14) == Decimal(50)
    assert relative_strength_index(tuple(Decimal(value) for value in range(15)), 14) == Decimal(100)
    middle, upper, lower = bollinger_bands(values, 4) or (None, None, None)
    assert middle == Decimal("2.5")
    assert upper == Decimal("2.5") + Decimal(2) * Decimal("1.25").sqrt()
    assert lower == Decimal("2.5") - Decimal(2) * Decimal("1.25").sqrt()

    bars = [_bar(minute, 100 + minute, high=101 + minute, low=99 + minute) for minute in range(14)]
    assert average_true_range(bars, 14) == Decimal(2)


def test_dataset_capabilities_use_symbol_session_cadence_not_daily_row_total() -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory))
        many_daily_symbols = [
            _bar(0, 100, symbol=f"{index:04d}", hour=13)
            for index in range(30)
        ]
        daily = catalog.create_imported_dataset(
            bars=many_daily_symbols,
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        one_minute = catalog.create_imported_dataset(
            bars=[_bar(minute, 100) for minute in range(21)],
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        irregular = catalog.create_imported_dataset(
            bars=[_bar(0, 100), _bar(1, 100), _bar(6, 100)],
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )

        assert daily.profile == "KBAR_DAILY_TEST_V1"
        assert daily.capabilities == ("OHLCV",)
        assert set(one_minute.capabilities) == {
            "OHLCV",
            "KBAR_INTRADAY",
            "KBAR_1M",
            "SESSION_BOUNDARIES",
        }
        assert one_minute.cadence_summary["dominant_interval_seconds"] == 60
        assert irregular.profile == "KBAR_INTRADAY_V1"
        assert "KBAR_1M" not in irregular.capabilities


def test_legacy_manifest_digest_is_not_changed_by_new_optional_cadence_field() -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory))
        manifest = catalog.create_imported_dataset(
            bars=[_bar(0, 100, hour=13)],
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        legacy_payload = manifest.to_dict(include_digest=False)
        legacy_payload.pop("cadence_summary")
        restored = type(manifest).from_dict(legacy_payload)

        assert restored.manifest_digest == digest(legacy_payload)
        assert "cadence_summary" not in restored.to_dict(include_digest=False)


def test_create_run_fails_closed_when_dataset_lacks_strategy_capability() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        manifest = catalog.create_imported_dataset(
            bars=[_bar(0, 100, hour=13)],
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        repository.upsert_dataset(manifest.to_dict(), "READY")
        service = BacktestApplicationService(
            MockProvider(), repository=repository, catalog=catalog, workers=1
        )
        try:
            with pytest.raises(ValueError, match="opening_range_breakout_entry_v1.*KBAR_1M"):
                service.create_run(
                    dataset_id=manifest.dataset_id,
                    entry_strategy_ids=["opening_range_breakout_entry_v1"],
                    exit_strategy_ids=["end_of_day_exit_v1"],
                    idempotency_key="cadence-preflight-reject",
                )
        finally:
            service.close()


def test_application_worker_executes_capability_approved_v2_strategy_run() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        bars = [_bar(minute, 100, high=101, low=99) for minute in range(15)]
        bars.append(_bar(15, "101.2", high="101.3", low=100))
        bars.extend(_bar(minute, "101.2", high=102, low=100) for minute in range(16, 29))
        manifest = catalog.create_imported_dataset(
            bars=bars,
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        repository.upsert_dataset(manifest.to_dict(), "READY")
        service = BacktestApplicationService(
            MockProvider(), repository=repository, catalog=catalog, workers=1
        )
        try:
            run, _ = service.create_run(
                dataset_id=manifest.dataset_id,
                entry_strategy_ids=["opening_range_breakout_entry_v1"],
                exit_strategy_ids=["time_stop_exit_v1"],
                idempotency_key="v2-experimental-worker-run",
            )
            for _ in range(100):
                current = service.get_run(str(run["run_id"]))
                if current["status"] in {"COMPLETED", "FAILED"}:
                    break
                sleep(0.01)

            assert current["status"] == "COMPLETED", current["error_message"]
            assert current["config"]["engine_version"] == "backtest-engine-v2"
            assert len(service.result(str(run["run_id"]))["trades"]) == 1
        finally:
            service.close()


def test_new_strategy_catalog_contracts_are_experimental_and_one_minute_only() -> None:
    registry = StrategyRegistry()
    strategy_ids = {
        "opening_range_breakout_entry_v1",
        "ema_crossover_entry_v1",
        "rsi_bollinger_reversion_entry_v0",
        "atr_stop_exit_v1",
        "time_stop_exit_v1",
    }
    definitions = {
        definition.strategy_id: definition
        for definition in registry.definitions()
        if definition.strategy_id in strategy_ids
    }

    assert set(definitions) == strategy_ids
    assert all(definition.status.value == "EXPERIMENTAL" for definition in definitions.values())
    assert all(
        set(definition.required_capabilities)
        == {"OHLCV", "KBAR_INTRADAY", "KBAR_1M", "SESSION_BOUNDARIES"}
        for definition in definitions.values()
    )


def test_opening_range_requires_all_fifteen_exact_minutes_and_freezes_range() -> None:
    registry = StrategyRegistry()
    state = BarFeatureState("2330", datetime(2026, 1, 5, tzinfo=TAIPEI).date())
    previous = None
    for minute in range(15):
        bar = _bar(minute, 100, high=101, low=99)
        previous = state.current
        features = state.apply(bar)
    breakout = _bar(15, "101.2", high="101.3", low="100.5")
    previous = state.current
    features = state.apply(breakout)
    evaluation = registry.evaluate(
        "opening_range_breakout_entry_v1",
        _context(breakout, features, previous),
    )

    assert evaluation.status is EvaluationStatus.TRIGGERED
    assert evaluation.observed["opening_range_high"] == 101.0

    missing_state = BarFeatureState("2330", datetime(2026, 1, 5, tzinfo=TAIPEI).date())
    for minute in (*range(7), *range(8, 15)):
        missing_state.apply(_bar(minute, 100))
    missing_bar = _bar(15, 102)
    missing_features = missing_state.apply(missing_bar)
    missing = registry.evaluate(
        "opening_range_breakout_entry_v1",
        _context(missing_bar, missing_features, missing_state.current),
    )
    assert missing.status is EvaluationStatus.INSUFFICIENT_DATA


def test_ema_and_rsi_bollinger_entries_trigger_only_on_completed_patterns() -> None:
    registry = StrategyRegistry()
    state = BarFeatureState("2330", datetime(2026, 1, 5, tzinfo=TAIPEI).date())
    previous = None
    for minute in range(20):
        previous = state.current
        features = state.apply(_bar(minute, 100))
    cross_bar = _bar(20, 101)
    previous = state.current
    features = state.apply(cross_bar)
    ema = registry.evaluate(
        "ema_crossover_entry_v1",
        _context(cross_bar, features, previous),
    )
    assert ema.status is EvaluationStatus.TRIGGERED

    mean_state = BarFeatureState("2330", datetime(2026, 1, 5, tzinfo=TAIPEI).date())
    for minute in range(19):
        mean_state.apply(_bar(minute, 100))
    mean_state.apply(_bar(19, 80, high=81, low=79))
    recovery = _bar(20, 95, high=96, low=94)
    previous = mean_state.current
    current = mean_state.apply(recovery)
    mean_reversion = registry.evaluate(
        "rsi_bollinger_reversion_entry_v0",
        _context(recovery, current, previous),
    )
    assert mean_reversion.status is EvaluationStatus.TRIGGERED


def test_atr_stop_uses_entry_signal_snapshot_and_time_stop_counts_fill_bar() -> None:
    registry = StrategyRegistry()
    bar = _bar(20, 98, high=100, low=97)
    state = BarFeatureState("2330", bar.timestamp.date())
    features = state.apply(bar)
    position = PositionStrategyContext(
        entry_fill_price=Decimal(100),
        entry_fill_at=bar.timestamp - timedelta(minutes=2),
        entry_event_index=2,
        bars_held_completed=3,
        entry_signal_atr=Decimal(2),
        fixed_atr_stop_price=Decimal(97),
    )
    atr = registry.evaluate("atr_stop_exit_v1", _context(bar, features, position=position))
    assert atr.status is EvaluationStatus.TRIGGERED
    assert atr.threshold["stop_price"] == 97.0

    bars = [_bar(minute, 100, high=101, low=99) for minute in range(15)]
    bars.append(_bar(15, "101.2", high="101.3", low=100))
    bars.extend(_bar(minute, "101.2", high="102", low=100) for minute in range(16, 29))
    config = BacktestRunConfig(
        dataset_id="dataset-fixture",
        dataset_digest="fixture",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("opening_range_breakout_entry_v1",),
            exit_strategy_ids=("time_stop_exit_v1",),
        ),
    )
    result = HistoricalBacktestEngine().run(config=config, bars=bars)

    assert len(result.trades) == 1
    assert result.trades[0].entry_fill.filled_at.minute == 16
    assert result.trades[0].exit_decision.event_at.minute == 27
    assert result.trades[0].exit_fill.filled_at.minute == 28

    atr_bars = [_bar(minute, 100, high=101, low=99) for minute in range(15)]
    atr_bars.extend(
        (
            _bar(15, "101.2", high="101.3", low=100),
            _bar(16, "101.2", high=102, low=100),
            _bar(17, 99, high=102, low=97),
            _bar(18, 99, high=100, low=98),
        )
    )
    atr_config = replace(
        config,
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("opening_range_breakout_entry_v1",),
            exit_strategy_ids=("atr_stop_exit_v1",),
        ),
    )
    atr_result = HistoricalBacktestEngine().run(config=atr_config, bars=atr_bars)
    assert len(atr_result.trades) == 1
    assert atr_result.trades[0].entry_fill.filled_at.minute == 16
    assert atr_result.trades[0].exit_decision.event_at.minute == 17
    assert atr_result.trades[0].exit_fill.filled_at.minute == 18


def test_legacy_strategy_output_is_identical_between_frozen_v1_and_v2() -> None:
    bars = [
        _bar(0, 100, day=4, hour=13),
        _bar(0, 103),
        _bar(1, 104),
        _bar(2, 108),
        _bar(25, 108, hour=13),
    ]
    config_v2 = BacktestRunConfig(
        dataset_id="dataset-fixture",
        dataset_digest="fixture",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
    )
    config_v1 = replace(config_v2, engine_version="backtest-engine-v1")

    engine = HistoricalBacktestEngine()
    assert engine.run(config=config_v1, bars=bars).to_dict() == engine.run(
        config=config_v2,
        bars=bars,
    ).to_dict()
