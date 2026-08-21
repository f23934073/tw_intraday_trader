"""Contracts for bounded-memory historical backtest replay."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySetSnapshot
from backtest.engine import HistoricalBacktestEngine


TAIPEI = ZoneInfo("Asia/Taipei")


def _bar(symbol: str, day: int, minute: int, close: int) -> HistoricalBar:
    price = Decimal(close)
    return HistoricalBar(
        symbol=symbol,
        name=symbol,
        market="TWSE",
        timestamp=datetime(2026, 1, day, 9, minute, tzinfo=TAIPEI),
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=10_000,
    )


def _config() -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="dataset-streaming-fixture",
        dataset_digest="fixture-digest",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
            priority_order=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
        minimum_oos_trades=1,
    )


def _terminal_timestamps(bars: list[HistoricalBar]) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    for bar in bars:
        result[bar.symbol] = max(bar.timestamp, result.get(bar.symbol, bar.timestamp))
    return result


def test_ordered_stream_matches_materialized_engine_result() -> None:
    bars = [
        _bar("2330", 2, 2, 100),
        _bar("2317", 3, 0, 103),
        _bar("2330", 3, 0, 103),
        _bar("2317", 3, 1, 105),
        _bar("2330", 3, 1, 105),
        _bar("2317", 3, 2, 108),
        _bar("2330", 3, 2, 108),
        _bar("2317", 3, 3, 108),
        _bar("2330", 3, 3, 108),
    ]
    ordered = sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))

    materialized = HistoricalBacktestEngine().run(config=_config(), bars=reversed(bars))
    streamed = HistoricalBacktestEngine().run(
        config=_config(),
        bars=iter(ordered),
        bars_are_ordered=True,
        total_bars=len(ordered),
        terminal_timestamp_by_symbol=_terminal_timestamps(ordered),
    )

    assert streamed.to_dict() == materialized.to_dict()


def test_ordered_stream_is_consumed_one_session_at_a_time() -> None:
    bars = [
        _bar("2330", 2, 0, 100),
        _bar("2330", 2, 1, 100),
        _bar("2330", 3, 0, 100),
        _bar("2330", 3, 1, 100),
    ]
    exhausted = False
    first_session_completed_before_exhaustion = False

    def source():
        nonlocal exhausted
        yield from bars
        exhausted = True

    def progress(_value: float, message: str) -> None:
        nonlocal first_session_completed_before_exhaustion
        if message == "已完成 2026-01-02":
            first_session_completed_before_exhaustion = not exhausted

    HistoricalBacktestEngine().run(
        config=_config(),
        bars=source(),
        progress=progress,
        bars_are_ordered=True,
        total_bars=len(bars),
        terminal_timestamp_by_symbol=_terminal_timestamps(bars),
    )

    assert first_session_completed_before_exhaustion is True
    assert exhausted is True


def test_ordered_stream_rejects_out_of_order_events() -> None:
    bars = [_bar("2330", 3, 1, 100), _bar("2330", 3, 0, 100)]

    with pytest.raises(ValueError, match="順序或唯一性"):
        HistoricalBacktestEngine().run(
            config=_config(),
            bars=iter(bars),
            bars_are_ordered=True,
            total_bars=len(bars),
            terminal_timestamp_by_symbol=_terminal_timestamps(bars),
        )


def test_catalog_orders_symbol_partitions_with_bounded_external_merge() -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory))
        partitions = (
            [_bar("2330", 3, 0, 100), _bar("2330", 3, 1, 101)],
            [_bar("2317", 3, 0, 90), _bar("2317", 3, 1, 91)],
        )
        manifest = catalog.create_provider_dataset_from_partitions(
            dataset_id="dataset-provider-partitions",
            partitions=partitions,
            source="fixture",
            requested_symbols=("2317", "2330"),
            issues=(),
        )

        ordered = list(
            catalog.iter_bars_ordered(
                manifest.dataset_id,
                chunk_size=2,
                merge_fan_in=2,
            )
        )

        assert manifest.payload_order == "SYMBOL_TIMESTAMP"
        assert [(bar.timestamp, bar.symbol) for bar in ordered] == sorted(
            (bar.timestamp, bar.symbol) for partition in partitions for bar in partition
        )


def test_catalog_merges_incremental_parent_and_delta_without_load_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory))
        base = catalog.create_imported_dataset(
            bars=[_bar("2330", 2, 0, 100), _bar("2317", 2, 0, 90)],
            source="fixture",
        )
        incremental = catalog.create_incremental_dataset(
            dataset_id="dataset-incremental",
            base_dataset_id=base.dataset_id,
            partitions=(
                [_bar("2330", 3, 0, 101), _bar("2330", 3, 1, 102)],
                [_bar("2317", 3, 0, 91), _bar("2317", 3, 1, 92)],
            ),
            source="fixture",
            requested_symbols=("2317", "2330"),
            issues=(),
        )
        monkeypatch.setattr(
            catalog,
            "load_bars",
            lambda _dataset_id: (_ for _ in ()).throw(
                AssertionError("ordered delta replay must not materialize load_bars()")
            ),
        )

        ordered = list(
            catalog.iter_bars_ordered(
                incremental.dataset_id,
                chunk_size=2,
                merge_fan_in=2,
            )
        )

        assert incremental.payload_order == "SYMBOL_TIMESTAMP"
        assert len(ordered) == incremental.bar_count
        assert [(bar.timestamp, bar.symbol) for bar in ordered] == sorted(
            (bar.timestamp, bar.symbol) for bar in ordered
        )


def test_legacy_manifest_without_payload_order_keeps_legacy_digest() -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory))
        manifest = catalog.create_imported_dataset(
            bars=[_bar("2330", 2, 0, 100)],
            source="fixture",
        )
        legacy_payload = manifest.to_dict(include_digest=False)
        legacy_payload.pop("payload_order")

        restored = type(manifest).from_dict(legacy_payload)

        assert "payload_order" not in restored.to_dict(include_digest=False)
