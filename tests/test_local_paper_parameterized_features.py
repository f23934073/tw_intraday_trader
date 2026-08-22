from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from features.engine import FeatureEngine
from features.models import FeatureStatus
from features.specifications import FeatureRequestSpec
from market_data.events import AggressorSide, MarketEventSource, TickEvent
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 24)


def _tick(
    minute: int,
    *,
    sequence: int,
    price: str,
    volume: int,
    total_volume: int,
) -> TickEvent:
    occurred_at = datetime(2026, 8, 24, 9, minute, 1, tzinfo=TAIPEI)
    decimal_price = Decimal(price)
    return TickEvent(
        event_id=f"tick-{minute}-{sequence}",
        source=MarketEventSource.REPLAY,
        symbol="3231",
        session_date=SESSION_DATE,
        event_time=occurred_at,
        received_at=occurred_at,
        ingress_sequence=sequence,
        price=decimal_price,
        tick_volume_lots=volume,
        total_volume_lots=total_volume,
        average_price=decimal_price,
        intraday_high=max(decimal_price, Decimal("110")),
        intraday_low=min(decimal_price, Decimal("90")),
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )


def _engine() -> tuple[FeatureEngine, IntradayBarStore]:
    bars = IntradayBarStore(
        SESSION_DATE,
        retention=timedelta(minutes=20),
        bar_retention=timedelta(hours=6),
    )
    return (
        FeatureEngine(
            references=InstrumentReferenceStore(SESSION_DATE),
            bars=bars,
            books=OrderBookStore(
                SESSION_DATE,
                retention=timedelta(minutes=20),
            ),
        ),
        bars,
    )


def test_request_projection_separates_two_and_three_minute_return() -> None:
    engine, bars = _engine()
    total = 0
    prices = ("99", "100", "101", "102", "103", "104")
    current = None
    for minute, price in enumerate(prices):
        total += 100
        current = _tick(
            minute,
            sequence=minute + 1,
            price=price,
            volume=100,
            total_volume=total,
        )
        assert bars.apply(current).projection_applied
    assert current is not None

    requests = (
        FeatureRequestSpec("rolling_return_v1", {"window_minutes": 2}),
        FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3}),
    )
    projected = engine.evaluate_requests(current, requests)

    assert projected[0].request_digest != projected[1].request_digest
    assert projected[0].value.value == Decimal("103") / Decimal("101") - 1
    assert projected[1].value.value == Decimal("103") / Decimal("100") - 1
    assert all(item.value.status is FeatureStatus.VALID for item in projected)


def test_completed_bars_outlive_raw_tick_retention_but_remain_bounded() -> None:
    _, bars = _engine()
    first = _tick(
        0,
        sequence=1,
        price="100",
        volume=100,
        total_volume=100,
    )
    later = _tick(
        30,
        sequence=2,
        price="101",
        volume=100,
        total_volume=200,
    )
    bars.apply(first)
    bars.apply(later)

    assert bars.ticks("3231") == (later,)
    assert [item.minute.minute for item in bars.bars("3231")] == [0, 30]


def test_request_projection_rejects_middle_volume_gap() -> None:
    engine, bars = _engine()
    total = 0
    current = None
    sequence = 0
    for minute in (*range(5), *range(6, 13)):
        sequence += 1
        volume = 200 if minute in {10, 11} else 100
        total += volume
        current = _tick(
            minute,
            sequence=sequence,
            price="100",
            volume=volume,
            total_volume=total,
        )
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec(
        "rolling_volume_ratio_v1",
        {
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
        },
    )
    projected = engine.evaluate_requests(current, (request,))[0]

    assert projected.value.status is FeatureStatus.MISSING
    assert projected.value.reason == "baseline_volume_windows_non_contiguous"
