from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_data.events import (
    AggressorSide,
    MarketEventSource,
    ProjectionApplyStatus,
    TickEvent,
)
from market_data.intraday_bar_store import IntradayBarStore


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)


def tick(
    event_id: str,
    *,
    minute: int,
    second: int,
    sequence: int,
    price: str,
    tick_volume: int,
    total_volume: int,
    session_date: date = SESSION_DATE,
) -> TickEvent:
    event_time = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        9,
        minute,
        second,
        tzinfo=TAIPEI,
    )
    value = Decimal(price)
    return TickEvent(
        event_id=event_id,
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=session_date,
        event_time=event_time,
        received_at=event_time,
        ingress_sequence=sequence,
        price=value,
        tick_volume_lots=tick_volume,
        total_volume_lots=total_volume,
        average_price=value,
        intraday_high=max(value, Decimal("278")),
        intraday_low=min(value, Decimal("258.5")),
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )


def store() -> IntradayBarStore:
    return IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))


def test_duplicate_is_idempotent_but_identical_trades_with_unique_ids_apply():
    bars = store()
    first = tick(
        "row-1",
        minute=16,
        second=0,
        sequence=1,
        price="272",
        tick_volume=10,
        total_volume=100,
    )
    second = tick(
        "row-2",
        minute=16,
        second=0,
        sequence=2,
        price="272",
        tick_volume=10,
        total_volume=110,
    )

    assert bars.apply(first).status is ProjectionApplyStatus.APPLIED
    digest_after_first = bars.digest
    assert bars.apply(first).status is ProjectionApplyStatus.DUPLICATE
    assert bars.digest == digest_after_first
    assert bars.apply(second).status is ProjectionApplyStatus.APPLIED

    bar = bars.bars("8039")[0]
    assert bar.volume_lots == 20
    assert bar.tick_count == 2


def test_out_of_order_and_bad_cumulative_volume_do_not_change_projection():
    bars = store()
    accepted = tick(
        "row-2",
        minute=16,
        second=10,
        sequence=2,
        price="273",
        tick_volume=10,
        total_volume=110,
    )
    bars.apply(accepted)
    expected_digest = bars.digest

    older = tick(
        "row-1",
        minute=16,
        second=5,
        sequence=1,
        price="272",
        tick_volume=10,
        total_volume=100,
    )
    invalid_total = tick(
        "row-3",
        minute=16,
        second=20,
        sequence=3,
        price="274",
        tick_volume=20,
        total_volume=115,
    )

    assert bars.apply(older).status is ProjectionApplyStatus.OUT_OF_ORDER
    assert bars.apply(invalid_total).status is ProjectionApplyStatus.INVALID
    assert bars.digest == expected_digest


def test_cumulative_gap_is_explicit_and_bar_does_not_invent_missing_volume():
    bars = store()
    bars.apply(
        tick(
            "row-1",
            minute=16,
            second=0,
            sequence=1,
            price="272",
            tick_volume=10,
            total_volume=100,
        )
    )
    result = bars.apply(
        tick(
            "row-2",
            minute=16,
            second=10,
            sequence=2,
            price="273",
            tick_volume=10,
            total_volume=130,
        )
    )

    assert result.status is ProjectionApplyStatus.APPLIED_WITH_GAP
    assert result.reason == "cumulative_volume_gap"
    assert bars.bars("8039")[0].volume_lots == 20


def test_zero_volume_tick_is_valid_and_session_reset_clears_history():
    bars = store()
    zero = tick(
        "zero",
        minute=0,
        second=0,
        sequence=1,
        price="258.5",
        tick_volume=0,
        total_volume=0,
    )

    assert bars.apply(zero).status is ProjectionApplyStatus.APPLIED
    assert bars.bars("8039")[0].volume_lots == 0

    next_date = date(2026, 8, 19)
    bars.begin_session(next_date)
    assert bars.bars("8039") == ()
    assert bars.apply(zero).status is ProjectionApplyStatus.SESSION_MISMATCH


def test_retention_and_finalize_are_deterministic():
    bars = store()
    bars.apply(
        tick(
            "early",
            minute=0,
            second=0,
            sequence=1,
            price="258.5",
            tick_volume=1,
            total_volume=1,
        )
    )
    bars.apply(
        tick(
            "late",
            minute=21,
            second=0,
            sequence=2,
            price="260",
            tick_volume=1,
            total_volume=2,
        )
    )

    assert [bar.minute.minute for bar in bars.bars("8039")] == [21]
    finalized_digest = bars.finalize_session()
    rejected = bars.apply(
        tick(
            "after-finalize",
            minute=22,
            second=0,
            sequence=3,
            price="261",
            tick_volume=1,
            total_volume=3,
        )
    )
    assert rejected.status is ProjectionApplyStatus.INVALID
    assert bars.digest == finalized_digest
