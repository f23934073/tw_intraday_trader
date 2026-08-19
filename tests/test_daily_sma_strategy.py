from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
from backtest.daily_features import DailySmaFeatureState
from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySetSnapshot
from backtest.engine import HistoricalBacktestEngine
from backtest.indicators import simple_moving_average
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyContext, StrategyRegistry
from market_data.provider import MockProvider


TAIPEI = ZoneInfo("Asia/Taipei")


def _bar(session: date, close: int, *, opened: int | None = None) -> HistoricalBar:
    close_value = Decimal(close)
    open_value = Decimal(opened if opened is not None else close)
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(session.year, session.month, session.day, 13, 30, tzinfo=TAIPEI),
        open=open_value,
        high=max(open_value, close_value),
        low=min(open_value, close_value),
        close=close_value,
        volume=1,
        amount=open_value,
        session_date=session,
        session_open_at=datetime(session.year, session.month, session.day, 9, 0, tzinfo=TAIPEI),
    )


def _context(bar: HistoricalBar, current, previous) -> StrategyContext:
    return StrategyContext(
        symbol=bar.symbol,
        bar=bar,
        previous_close=None,
        session_open=bar.open,
        session_high_before=None,
        vwap=bar.close,
        cumulative_volume=bar.volume,
        bars_seen=1,
        is_last_bar=True,
        daily_features=current,
        previous_daily_features=previous,
        resolved_session_date=bar.session_date,
    )


def test_simple_moving_average_and_daily_crossing_warmup_contract():
    assert simple_moving_average((Decimal("1"), Decimal("2")), 3) is None
    assert simple_moving_average((Decimal("1"), Decimal("2"), Decimal("3")), 3) == Decimal("2")

    state = DailySmaFeatureState("2330")
    start = date(2026, 1, 1)
    previous = None
    for index in range(60):
        previous = state.current
        current = state.apply(_bar(start + timedelta(days=index), 100))
    assert current.sma20 == current.sma60 == Decimal("100")
    cross_bar = _bar(start + timedelta(days=60), 160)
    previous = state.current
    current = state.apply(cross_bar)
    assert current.daily_bars_seen == 61
    assert current.sma20 == Decimal("103")
    assert current.sma60 == Decimal("101")

    evaluation = StrategyRegistry().evaluate(
        "sma_20_60_golden_cross_entry_v1",
        _context(cross_bar, current, previous),
    )
    assert evaluation.status.value == "TRIGGERED"
    assert evaluation.execution_horizon is not None
    assert evaluation.execution_horizon.value == "DAILY_NEXT_BAR"
    assert evaluation.observed["cross_direction"] == "UP"


def test_daily_next_bar_entry_and_exit_cross_session_without_eod_shortcut():
    start = date(2026, 1, 1)
    bars = [_bar(start + timedelta(days=index), 100) for index in range(60)]
    bars.extend(
        (
            _bar(start + timedelta(days=60), 160),
            _bar(start + timedelta(days=61), 40, opened=90),
            _bar(start + timedelta(days=62), 40),
            _bar(start + timedelta(days=63), 40, opened=35),
        )
    )
    config = BacktestRunConfig(
        dataset_id="dataset-daily",
        dataset_digest="daily-fixture",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("sma_20_60_golden_cross_entry_v1",),
            exit_strategy_ids=("sma_20_60_death_cross_exit_v1",),
        ),
    )

    result = HistoricalBacktestEngine().run(config=config, bars=bars)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_decision.event_at.date() == start + timedelta(days=60)
    assert trade.entry_fill.filled_at == datetime.combine(
        start + timedelta(days=61), time(9, 0), tzinfo=TAIPEI
    )
    assert trade.entry_fill.source == "DAILY_NEXT_BAR_OPEN"
    assert trade.exit_decision.event_at.date() == start + timedelta(days=62)
    assert trade.exit_fill.filled_at == datetime.combine(
        start + timedelta(days=63), time(9, 0), tzinfo=TAIPEI
    )
    assert trade.exit_fill.source == "DAILY_NEXT_BAR_OPEN"
    assert all(fill.source != "EOD_CLOSE" for fill in result.fills)
    assert result.decisions[0].execution_horizon is not None
    assert result.decisions[0].execution_horizon.value == "DAILY_NEXT_BAR"


def test_daily_sma_rejects_bars_without_an_auditable_session_open_time():
    bar = replace(_bar(date(2026, 1, 1), 100), session_open_at=None)
    config = BacktestRunConfig(
        dataset_id="dataset-daily",
        dataset_digest="daily-fixture",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("sma_20_60_golden_cross_entry_v1",),
            exit_strategy_ids=("sma_20_60_death_cross_exit_v1",),
        ),
    )

    with pytest.raises(ValueError, match="session_open_at"):
        HistoricalBacktestEngine().run(config=config, bars=[bar])


def test_daily_signal_on_terminal_bar_remains_unfilled_without_a_future_session():
    start = date(2026, 1, 1)
    bars = [_bar(start + timedelta(days=index), 100) for index in range(60)]
    bars.append(_bar(start + timedelta(days=60), 160))
    config = BacktestRunConfig(
        dataset_id="dataset-daily",
        dataset_digest="daily-fixture",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("sma_20_60_golden_cross_entry_v1",),
            exit_strategy_ids=("sma_20_60_death_cross_exit_v1",),
        ),
    )

    result = HistoricalBacktestEngine().run(config=config, bars=bars)

    assert result.fills == []
    assert result.orders[0]["status"] == "UNFILLED_END_OF_DATA"
    assert result.orders[0]["execution_horizon"] == "DAILY_NEXT_BAR"


def _weekday_sessions(start: date, count: int) -> list[date]:
    sessions: list[date] = []
    current = start
    while len(sessions) < count:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _intraday_bar(session: date, hour: int, minute: int, price: int) -> HistoricalBar:
    value = Decimal(price)
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(session.year, session.month, session.day, hour, minute, tzinfo=TAIPEI),
        open=value,
        high=value,
        low=value,
        close=value,
        volume=1,
        amount=value,
        session_date=session,
    )


def test_application_seals_daily_child_then_runs_sma_pair_with_capability_preflight():
    sessions = _weekday_sessions(date(2026, 1, 5), 64)
    parent_bars: list[HistoricalBar] = []
    completion_proofs: dict[tuple[str, date], str] = {}
    for index, session in enumerate(sessions):
        daily_close = 100 if index < 60 else 160 if index == 60 else 40
        daily_open = 90 if index == 61 else 35 if index == 63 else daily_close
        parent_bars.extend(
            (
                _intraday_bar(session, 9, 1, daily_open),
                _intraday_bar(session, 13, 30, daily_close),
            )
        )
        completion_proofs[("2330", session)] = f"proof-{index}"

    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        parent = catalog.create_imported_dataset(bars=parent_bars, source="fixture")
        repository.upsert_dataset(parent.to_dict(), "READY")
        service = BacktestApplicationService(
            MockProvider(), repository=repository, catalog=catalog, workers=1
        )
        try:
            repository.upsert_dataset(parent.to_dict(), "FAILED")
            try:
                service.create_derived_daily_dataset(
                    dataset_id="dataset-daily-sma-fixture",
                    base_dataset_id=parent.dataset_id,
                    completion_proofs=completion_proofs,
                    session_contract={"version": "fixture-calendar-v1", "timezone": "Asia/Taipei"},
                    volume_contract={"scope": "REGULAR_SESSION", "unit": "COMMON_LOT"},
                )
            except ValueError as error:
                assert "尚未 READY" in str(error)
            else:
                raise AssertionError("non-READY parent must not be derivable")
            repository.upsert_dataset(parent.to_dict(), "READY")
            try:
                service.create_run(
                    dataset_id=parent.dataset_id,
                    entry_strategy_ids=["sma_20_60_golden_cross_entry_v1"],
                    exit_strategy_ids=["sma_20_60_death_cross_exit_v1"],
                    idempotency_key="daily-sma-parent-must-reject",
                )
            except ValueError as error:
                assert "sma_20_60_golden_cross_entry_v1" in str(error)
                assert "KBAR_DAILY" in str(error)
            else:
                raise AssertionError("intraday parent must not be selectable for daily SMA")
            daily = service.create_derived_daily_dataset(
                dataset_id="dataset-daily-sma-fixture",
                base_dataset_id=parent.dataset_id,
                completion_proofs=completion_proofs,
                session_contract={"version": "fixture-calendar-v1", "timezone": "Asia/Taipei"},
                volume_contract={
                    "scope": "REGULAR_SESSION",
                    "unit": "COMMON_LOT",
                    "shares_per_lot": 1000,
                },
            )
            assert daily.capabilities == ("OHLCV", "KBAR_DAILY")
            assert repository.get_dataset(daily.dataset_id)["status"] == "READY"

            run, _ = service.create_run(
                dataset_id=daily.dataset_id,
                entry_strategy_ids=["sma_20_60_golden_cross_entry_v1"],
                exit_strategy_ids=["sma_20_60_death_cross_exit_v1"],
                idempotency_key="daily-sma-e2e-qualification",
            )
            for _ in range(100):
                current = service.get_run(str(run["run_id"]))
                if current["status"] in {"COMPLETED", "FAILED"}:
                    break
                sleep(0.01)

            assert current["status"] == "COMPLETED", current["error_message"]
            result = service.result(str(run["run_id"]))
            assert len(result["trades"]) == 1
            assert [item["source"] for item in result["fills"]] == [
                "DAILY_NEXT_BAR_OPEN",
                "DAILY_NEXT_BAR_OPEN",
            ]
            assert [item["filled_at"] for item in result["fills"]] == [
                f"{sessions[61].isoformat()}T09:01:00+08:00",
                f"{sessions[63].isoformat()}T09:01:00+08:00",
            ]
        finally:
            service.close()
