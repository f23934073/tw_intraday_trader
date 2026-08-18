from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.health import DataHealth, DataHealthReason, DataHealthState
from market_data.ingestion import (
    BoundedMarketEventQueue,
    IngestStatus,
    MarketDataIngestor,
    QueueOverflowError,
)
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)


def timestamp(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 18, 9, minute, second, tzinfo=TAIPEI)


def tick_envelope(
    event_id: str,
    *,
    minute: int,
    second: int,
    sequence: int,
    tick_volume: int,
    total_volume: int,
    received_at: datetime | None = None,
    session_date: date = SESSION_DATE,
) -> EventEnvelope:
    event_at = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        9,
        minute,
        second,
        tzinfo=TAIPEI,
    )
    received = received_at or event_at
    event = TickEvent(
        event_id=event_id,
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=session_date,
        event_time=event_at,
        received_at=received,
        ingress_sequence=sequence,
        price=Decimal("278"),
        tick_volume_lots=tick_volume,
        total_volume_lots=total_volume,
        average_price=Decimal("270.76"),
        intraday_high=Decimal("278"),
        intraday_low=Decimal("258.5"),
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version="market-event-v1",
        session_id="20260818-replay",
        session_date=session_date,
        source=MarketEventSource.REPLAY,
        source_mode="SYNTHETIC_REPLAY",
        stream_kind=MarketStreamKind.TICK,
        symbol="8039",
        event_at=event_at,
        received_at=received,
        ingress_sequence=sequence,
        source_identity=f"tick:{sequence}",
        payload=event,
    )


def book_envelope(
    event_id: str,
    *,
    minute: int,
    second: int,
    sequence: int,
    received_at: datetime | None = None,
    crossed: bool = False,
) -> EventEnvelope:
    event_at = timestamp(minute, second)
    received = received_at or event_at
    event = BidAskEvent(
        event_id=event_id,
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=received,
        ingress_sequence=sequence,
        bid_prices=(Decimal("278.5") if crossed else Decimal("277.5"),),
        bid_volume_lots=(3000,),
        ask_prices=(Decimal("278"),),
        ask_volume_lots=(1000,),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version="market-event-v1",
        session_id="20260818-replay",
        session_date=SESSION_DATE,
        source=MarketEventSource.REPLAY,
        source_mode="SYNTHETIC_REPLAY",
        stream_kind=MarketStreamKind.BIDASK,
        symbol="8039",
        event_at=event_at,
        received_at=received,
        ingress_sequence=sequence,
        source_identity=f"book:{sequence}",
        payload=event,
    )


def components(*, with_reference: bool = True):
    references = InstrumentReferenceStore(SESSION_DATE)
    if with_reference:
        references.put(
            InstrumentReference(
                symbol="8039",
                exchange="TSE",
                session_date=SESSION_DATE,
                reference_price=Decimal("258.5"),
                limit_up_price=Decimal("284.5"),
                limit_down_price=Decimal("232.5"),
                price_limit_applies=True,
                trading_unit_shares=1000,
                source_updated_at=SESSION_DATE,
            )
        )
    bars = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    books = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    health = DataHealth(SESSION_DATE, started_at=timestamp(0))
    health.mark_ready(occurred_at=timestamp(0), evidence="fixture_validated")
    ingestor = MarketDataIngestor(
        session_id="20260818-replay",
        session_date=SESSION_DATE,
        references=references,
        bars=bars,
        books=books,
        health=health,
    )
    return ingestor, references, bars, books, health


def test_tick_and_bidask_keep_independent_watermarks():
    ingestor, _, bars, books, health = components()
    tick = tick_envelope(
        "tick-2",
        minute=18,
        second=10,
        sequence=2,
        tick_volume=10,
        total_volume=100,
        received_at=timestamp(18, 10),
    )
    earlier_book = book_envelope(
        "book-1",
        minute=18,
        second=5,
        sequence=1,
        received_at=timestamp(18, 11),
    )

    assert ingestor.ingest(tick).status is IngestStatus.APPLIED
    assert ingestor.ingest(earlier_book).status is IngestStatus.APPLIED
    assert len(bars.bars("8039")) == 1
    assert books.latest("8039") is not None
    assert health.state is DataHealthState.HEALTHY


def test_duplicate_and_out_of_order_are_explicit_and_do_not_add_volume():
    ingestor, _, bars, _, health = components()
    first = tick_envelope(
        "tick-2",
        minute=18,
        second=10,
        sequence=2,
        tick_volume=10,
        total_volume=100,
    )
    older = tick_envelope(
        "tick-1",
        minute=18,
        second=5,
        sequence=1,
        tick_volume=10,
        total_volume=90,
        received_at=timestamp(18, 11),
    )
    ingestor.ingest(first)

    duplicate = ingestor.ingest(first)
    out_of_order = ingestor.ingest(older)

    assert duplicate.status is IngestStatus.DUPLICATE
    assert out_of_order.status is IngestStatus.OUT_OF_ORDER_REJECTED
    assert bars.bars("8039")[0].volume_lots == 10
    assert health.state is DataHealthState.DEGRADED
    stream = health.snapshot().streams[0]
    assert stream.duplicate_count == 1
    assert stream.out_of_order_count == 1


def test_cumulative_gap_applies_incomplete_tick_but_blocks_health():
    ingestor, _, bars, _, health = components()
    ingestor.ingest(
        tick_envelope(
            "tick-1",
            minute=18,
            second=0,
            sequence=1,
            tick_volume=10,
            total_volume=100,
        )
    )
    result = ingestor.ingest(
        tick_envelope(
            "tick-2",
            minute=18,
            second=1,
            sequence=2,
            tick_volume=10,
            total_volume=130,
        )
    )

    assert result.status is IngestStatus.APPLIED_HEALTH_BLOCKED
    assert result.projection_applied is True
    assert bars.bars("8039")[0].volume_lots == 20
    assert health.state is DataHealthState.BLOCKED
    assert DataHealthReason.CUMULATIVE_VOLUME_GAP in health.snapshot().reasons


def test_missing_reference_and_crossed_book_fail_closed():
    missing, _, bars, _, missing_health = components(with_reference=False)
    missing_result = missing.ingest(
        tick_envelope(
            "tick-1",
            minute=18,
            second=0,
            sequence=1,
            tick_volume=1,
            total_volume=1,
        )
    )
    assert missing_result.status is IngestStatus.INVALID_REJECTED
    assert bars.bars("8039") == ()
    assert missing_health.state is DataHealthState.BLOCKED

    ingestor, _, _, books, health = components()
    crossed_result = ingestor.ingest(
        book_envelope(
            "crossed",
            minute=18,
            second=0,
            sequence=1,
            crossed=True,
        )
    )
    assert crossed_result.status is IngestStatus.INVALID_REJECTED
    assert books.latest("8039") is None
    assert health.state is DataHealthState.BLOCKED


def test_queue_overflow_is_visible_preserves_accepted_events_and_blocks_health():
    _, _, _, _, health = components()
    queue = BoundedMarketEventQueue(2, health)
    first = tick_envelope(
        "tick-1",
        minute=18,
        second=0,
        sequence=1,
        tick_volume=1,
        total_volume=1,
    )
    second = tick_envelope(
        "tick-2",
        minute=18,
        second=1,
        sequence=2,
        tick_volume=1,
        total_volume=2,
    )
    rejected = tick_envelope(
        "tick-3",
        minute=18,
        second=2,
        sequence=3,
        tick_volume=1,
        total_volume=3,
    )
    queue.put(first)
    queue.put(second)

    with pytest.raises(QueueOverflowError, match="tick-3"):
        queue.put(rejected)

    assert len(queue) == 2
    assert queue.drain(occurred_at=timestamp(18, 3)) == (first, second)
    snapshot = health.snapshot()
    assert snapshot.state is DataHealthState.BLOCKED
    assert snapshot.queue_high_watermark == 2
    assert snapshot.queue_overflow_count == 1


def test_blocked_health_requires_new_epoch_and_resync_evidence_to_recover():
    _, _, _, _, health = components()
    health.record_invalid(
        DataHealthReason.INVALID_EVENT,
        occurred_at=timestamp(1),
    )

    with pytest.raises(ValueError, match="verified recovery"):
        health.mark_ready(occurred_at=timestamp(2), evidence="next_event")
    with pytest.raises(ValueError, match="newer reconnect epoch"):
        health.recover(
            reconnect_epoch=0,
            occurred_at=timestamp(2),
            evidence="resync",
        )

    health.recover(
        reconnect_epoch=1,
        occurred_at=timestamp(2),
        evidence="manifest_and_stream_resynced",
    )
    assert health.state is DataHealthState.HEALTHY
    assert health.snapshot().reconnect_epoch == 1


def test_negative_source_latency_is_recorded_without_using_wall_clock():
    ingestor, _, _, _, health = components()
    future_event = tick_envelope(
        "tick-skew",
        minute=18,
        second=2,
        sequence=1,
        tick_volume=1,
        total_volume=1,
        received_at=timestamp(18, 1),
    )

    assert ingestor.ingest(future_event).status is IngestStatus.APPLIED
    snapshot = health.snapshot()
    assert snapshot.state is DataHealthState.DEGRADED
    assert snapshot.source_clock_skew_count == 1
    assert DataHealthReason.SOURCE_CLOCK_SKEW in snapshot.reasons


def test_session_rollover_clears_stores_and_seen_event_ids():
    ingestor, references, bars, books, health = components()
    first = tick_envelope(
        "same-row-id",
        minute=18,
        second=0,
        sequence=1,
        tick_volume=1,
        total_volume=1,
    )
    ingestor.ingest(first)

    next_date = date(2026, 8, 19)
    next_start = datetime(2026, 8, 19, 9, 0, tzinfo=TAIPEI)
    ingestor.begin_session("20260819-replay", next_date, started_at=next_start)

    assert references.all() == ()
    assert bars.bars("8039") == ()
    assert books.latest("8039") is None
    assert health.state is DataHealthState.STARTING


def test_same_date_different_session_id_is_rejected():
    ingestor, _, bars, _, health = components()
    event = tick_envelope(
        "tick-other-session",
        minute=18,
        second=0,
        sequence=1,
        tick_volume=1,
        total_volume=1,
    )
    wrong_session = replace(event, session_id="other-session")

    result = ingestor.ingest(wrong_session)

    assert result.status is IngestStatus.SESSION_MISMATCH_REJECTED
    assert bars.bars("8039") == ()
    assert health.state is DataHealthState.BLOCKED
