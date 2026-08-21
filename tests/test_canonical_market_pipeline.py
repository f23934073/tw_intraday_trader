from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.health import DataHealth, DataHealthReason, DataHealthState
from market_data.ingestion import IngestStatus, MarketDataIngestor
from market_data.ingress import (
    AdmissionStatus,
    BoundedIngressQueue,
    LifecycleIngressMessage,
)
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import (
    CanonicalMarketDataPipeline,
    DecisionGateState,
    PipelineProcessStatus,
)
from market_data.recording import InMemoryMarketEventRecorder


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 20)
SESSION_ID = "20260820-live"


def timestamp(second: int) -> datetime:
    return datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI) + timedelta(
        seconds=second
    )


def tick_envelope(
    sequence: int,
    *,
    event_second: int,
    received_second: int | None = None,
    total_volume: int,
) -> EventEnvelope:
    event_at = timestamp(event_second)
    received_at = timestamp(
        event_second if received_second is None else received_second
    )
    event_id = f"tick-{sequence}"
    payload = TickEvent(
        event_id=event_id,
        source=MarketEventSource.TICK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=received_at,
        ingress_sequence=sequence,
        price=Decimal("600"),
        tick_volume_lots=1,
        total_volume_lots=total_volume,
        average_price=Decimal("599.5"),
        intraday_high=Decimal("601"),
        intraday_low=Decimal("598"),
        raw_tick_type=1,
        aggressor_side=AggressorSide.BUY,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.TICK,
        source_mode="TEST",
        stream_kind=MarketStreamKind.TICK,
        symbol="2330",
        event_at=event_at,
        received_at=received_at,
        ingress_sequence=sequence,
        source_identity=f"test:tick:{sequence}",
        payload=payload,
    )


def book_envelope(sequence: int, *, event_second: int) -> EventEnvelope:
    event_at = timestamp(event_second)
    event_id = f"book-{sequence}"
    payload = BidAskEvent(
        event_id=event_id,
        source=MarketEventSource.BIDASK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        bid_prices=(Decimal("599.5"),),
        bid_volume_lots=(4,),
        ask_prices=(Decimal("600"),),
        ask_volume_lots=(5,),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.BIDASK,
        source_mode="TEST",
        stream_kind=MarketStreamKind.BIDASK,
        symbol="2330",
        event_at=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        source_identity=f"test:book:{sequence}",
        payload=payload,
    )


def lifecycle_message(sequence: int, *, event_type: str) -> LifecycleIngressMessage:
    return LifecycleIngressMessage(
        event_id=f"lifecycle-{sequence}",
        session_id=SESSION_ID,
        event_type=event_type,
        occurred_at=timestamp(4),
        ingress_sequence=sequence,
        source_identity=f"test:lifecycle:{sequence}",
        reason="test evidence",
    )


def components(
    *,
    capacity: int = 8,
    control_reserve: int = 1,
    recorder: InMemoryMarketEventRecorder | None = None,
):
    references = InstrumentReferenceStore(SESSION_DATE)
    references.put(
        InstrumentReference(
            symbol="2330",
            exchange="TSE",
            session_date=SESSION_DATE,
            reference_price=Decimal("590"),
            limit_up_price=Decimal("649"),
            limit_down_price=Decimal("531"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=SESSION_DATE,
        )
    )
    bars = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    books = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    health = DataHealth(SESSION_DATE, started_at=timestamp(0))
    health.mark_ready(occurred_at=timestamp(0), evidence="fixture")
    ingestor = MarketDataIngestor(
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        references=references,
        bars=bars,
        books=books,
        health=health,
    )
    queue = BoundedIngressQueue(
        capacity=capacity,
        control_reserve=control_reserve,
        health=health,
    )
    actual_recorder = recorder or InMemoryMarketEventRecorder()
    pipeline = CanonicalMarketDataPipeline(
        queue=queue,
        recorder=actual_recorder,
        ingestor=ingestor,
        health=health,
    )
    return pipeline, queue, actual_recorder, bars, books, health


def test_market_overflow_blocks_gate_without_crashing_and_drains_prefix():
    pipeline, queue, recorder, bars, _, health = components(
        capacity=3,
        control_reserve=1,
    )

    first = pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=1,
            total_volume=1,
        )
    )
    second = pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=2,
            total_volume=2,
        )
    )
    overflow = pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=3,
            total_volume=3,
        )
    )
    control = pipeline.submit_lifecycle(
        lambda sequence: lifecycle_message(
            sequence,
            event_type="STOP_REQUESTED",
        )
    )
    rejected_after_close = pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=5,
            total_volume=4,
        )
    )

    assert first.status is AdmissionStatus.ACCEPTED
    assert second.status is AdmissionStatus.ACCEPTED
    assert overflow.status is AdmissionStatus.REJECTED_OVERFLOW
    assert control.status is AdmissionStatus.ACCEPTED
    assert rejected_after_close.status is AdmissionStatus.REJECTED_CLOSED
    assert pipeline.decision_gate is DecisionGateState.BLOCK_NEW_ENTRY
    queue_snapshot = queue.snapshot()
    assert queue_snapshot.market_admission_open is False
    assert queue_snapshot.accepted_count == 3
    assert queue_snapshot.rejected_overflow_count == 1
    assert queue_snapshot.rejected_closed_count == 1
    assert queue_snapshot.incidents[0].event_id == "tick-3"
    assert queue_snapshot.incidents[0].ingress_sequence == 3

    processed = pipeline.process_pending(occurred_at=timestamp(6))

    assert [item.status for item in processed] == [
        PipelineProcessStatus.MARKET_INGESTED,
        PipelineProcessStatus.MARKET_INGESTED,
        PipelineProcessStatus.LIFECYCLE_RECORDED,
    ]
    assert [item.envelope.event_id for item in recorder.market_records] == [
        "tick-1",
        "tick-2",
    ]
    assert [item.record_index for item in recorder.records] == [0, 1, 2]
    first_recorded = recorder.market_records[0].envelope
    assert first_recorded.source_identity == "test:tick:1"
    assert first_recorded.event_at == timestamp(1)
    assert first_recorded.received_at == timestamp(1)
    assert first_recorded.payload.total_volume_lots == 1
    assert bars.bars("2330")[0].volume_lots == 2
    snapshot = health.snapshot()
    assert snapshot.state is DataHealthState.BLOCKED
    assert DataHealthReason.QUEUE_OVERFLOW in snapshot.reasons
    assert snapshot.queue_overflow_count == 1


def test_control_reserve_failure_is_explicit_and_closes_all_admission():
    pipeline, queue, _, _, _, health = components(capacity=2, control_reserve=1)
    assert pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=1,
            total_volume=1,
        )
    ).accepted
    assert pipeline.submit_lifecycle(
        lambda sequence: lifecycle_message(sequence, event_type="DISCONNECTED")
    ).accepted

    timeout = pipeline.submit_lifecycle(
        lambda sequence: lifecycle_message(sequence, event_type="RECONNECTING"),
        timeout=0,
    )

    assert timeout.status is AdmissionStatus.REJECTED_CONTROL_TIMEOUT
    snapshot = queue.snapshot()
    assert snapshot.market_admission_open is False
    assert snapshot.control_admission_open is False
    assert health.state is DataHealthState.BLOCKED


class FailingRecorder(InMemoryMarketEventRecorder):
    def record_market(self, *, record_index: int, envelope: EventEnvelope) -> None:
        raise OSError("recorder unavailable")


def test_recorder_failure_blocks_before_ingest_and_does_not_raise():
    pipeline, queue, _, bars, _, health = components(recorder=FailingRecorder())
    assert pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=1,
            total_volume=1,
        )
    ).accepted

    result = pipeline.process_pending(occurred_at=timestamp(2))

    assert len(result) == 1
    assert result[0].status is PipelineProcessStatus.RECORDER_FAILED
    assert result[0].ingest_result is None
    assert bars.bars("2330") == ()
    assert health.state is DataHealthState.BLOCKED
    assert DataHealthReason.RECORDER_FAILURE in health.snapshot().reasons
    assert queue.snapshot().market_admission_open is False
    assert pipeline.decision_gate is DecisionGateState.BLOCK_NEW_ENTRY


def test_out_of_order_event_is_recorded_before_rejection():
    pipeline, _, recorder, bars, _, health = components()
    pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=20,
            total_volume=1,
        )
    )
    pipeline.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=19,
            received_second=21,
            total_volume=2,
        )
    )

    processed = pipeline.process_pending(occurred_at=timestamp(22))

    assert [item.ingest_result.status for item in processed] == [
        IngestStatus.APPLIED,
        IngestStatus.OUT_OF_ORDER_REJECTED,
    ]
    assert [item.envelope.event_id for item in recorder.market_records] == [
        "tick-1",
        "tick-2",
    ]
    assert [item.result.status for item in recorder.disposition_records] == [
        IngestStatus.APPLIED,
        IngestStatus.OUT_OF_ORDER_REJECTED,
    ]
    assert bars.bars("2330")[0].volume_lots == 1
    assert health.state is DataHealthState.DEGRADED


def test_concurrent_admission_keeps_sequence_and_fifo_atomic():
    _, queue, _, _, _, _ = components(capacity=40, control_reserve=1)

    def admit(_: int):
        return queue.admit_market(
            lambda sequence: tick_envelope(
                sequence,
                event_second=sequence,
                total_volume=sequence,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(admit, range(32)))

    assert all(item.accepted for item in results)
    drained = queue.drain(occurred_at=timestamp(59))
    assert [item.ingress_sequence for item in drained] == list(range(1, 33))


def test_admission_rejects_factory_sequence_violation():
    _, queue, _, _, _, _ = components()
    assert queue.admit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=1,
            total_volume=1,
        )
    ).accepted

    with pytest.raises(ValueError, match="allocated sequence 2; got 1"):
        queue.admit_market(
            lambda _: tick_envelope(
                1,
                event_second=2,
                total_volume=2,
            )
        )


def preserve_recorded_sequence(
    sequence: int,
    envelope: EventEnvelope,
) -> EventEnvelope:
    if sequence != envelope.ingress_sequence:
        raise AssertionError("recorded ingress sequence changed during replay")
    return envelope


def test_in_memory_record_replay_reproduces_bar_and_book_projection():
    source, _, recorder, source_bars, source_books, _ = components()
    source.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=1,
            total_volume=1,
        )
    )
    source.submit_market(
        lambda sequence: book_envelope(sequence, event_second=2)
    )
    source.submit_market(
        lambda sequence: tick_envelope(
            sequence,
            event_second=3,
            total_volume=2,
        )
    )
    source_results = source.process_pending(occurred_at=timestamp(4))

    replay, _, _, replay_bars, replay_books, _ = components()
    for recorded in recorder.market_records:
        admission = replay.submit_market(
            lambda sequence, envelope=recorded.envelope: preserve_recorded_sequence(
                sequence,
                envelope,
            )
        )
        assert admission.accepted
    replay_results = replay.process_pending(occurred_at=timestamp(4))

    assert [item.ingest_result.status for item in replay_results] == [
        item.ingest_result.status for item in source_results
    ]
    assert replay_bars.digest == source_bars.digest
    assert replay_books.digest == source_books.digest
