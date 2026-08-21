"""Repeatable synthetic profile for the ordered streaming engine path."""

from __future__ import annotations

import os
import gc
import time
import tracemalloc
from datetime import date, datetime, time as clock_time, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

os.environ.setdefault("BACKTEST_DATABASE_BACKEND", "sqlite")

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySetSnapshot, digest
from backtest.engine import HistoricalBacktestEngine


TAIPEI = ZoneInfo("Asia/Taipei")


def build_bars() -> list[HistoricalBar]:
    sessions: list[date] = []
    cursor = date(2025, 1, 2)
    while len(sessions) < 60:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    bars: list[HistoricalBar] = []
    for symbol_index in range(100):
        symbol = f"{symbol_index + 1000:04d}"
        previous_close = Decimal("100") + Decimal(symbol_index % 5)
        for session in sessions:
            opened = previous_close * Decimal("1.03")
            prices = (
                opened,
                opened + Decimal("1"),
                opened + Decimal("2"),
                opened + Decimal("4"),
                opened + Decimal("3"),
            )
            for minute, price in enumerate(prices):
                bars.append(
                    HistoricalBar(
                        symbol=symbol,
                        name=symbol,
                        market="TWSE",
                        timestamp=datetime.combine(
                            session,
                            clock_time(9, minute),
                            tzinfo=TAIPEI,
                        ),
                        open=price,
                        high=price + Decimal("1"),
                        low=price - Decimal("1"),
                        close=price,
                        volume=100_000,
                    )
                )
            previous_close = prices[-1]
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))


def profile(run) -> tuple[float, float, int, str]:
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = run()
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak / 1024 / 1024, len(result.trades), digest(result.to_dict())


with TemporaryDirectory() as directory:
    catalog = HistoricalDatasetCatalog(Path(directory))
    source_bars = build_bars()
    manifest = catalog.create_imported_dataset(
        bars=source_bars,
        source="memory-profile",
    )
    bar_count = len(source_bars)
    del source_bars
    config = BacktestRunConfig(
        dataset_id=manifest.dataset_id,
        dataset_digest=manifest.manifest_digest,
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
            priority_order=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
        minimum_oos_trades=1,
    )
    direct = profile(
        lambda: HistoricalBacktestEngine().run(
            config=config,
            bars=catalog.iter_bars(manifest.dataset_id),
        )
    )
    terminals = catalog.symbol_last_timestamps(manifest.dataset_id)
    streamed = profile(
        lambda: HistoricalBacktestEngine().run(
            config=config,
            bars=catalog.iter_bars_ordered(manifest.dataset_id),
            bars_are_ordered=True,
            total_bars=manifest.bar_count,
            terminal_timestamp_by_symbol=terminals,
        )
    )

print(
    f"bars={bar_count} direct_seconds={direct[0]:.3f} "
    f"direct_peak_mib={direct[1]:.2f} streaming_seconds={streamed[0]:.3f} "
    f"streaming_peak_mib={streamed[1]:.2f} trades={streamed[2]} "
    f"same_result={direct[3] == streamed[3]}"
)
