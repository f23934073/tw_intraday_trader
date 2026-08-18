from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event
from time import monotonic
from zoneinfo import ZoneInfo

import pytest

from candidate.models import CandidateSource
from candidate.pool import CandidatePool, CandidatePoolConfig
from candidate.sources import CandidateDiscovery
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig
from market_data.events import EventEnvelope, InstrumentReference
from market_data.health import DataHealthReason, DataHealthState
from market_data.ingestion import QueueOverflowError
from market_data.momentum_stream import (
    StreamConnectionState,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.replay import ReplayDatasetLoader
from market_data.subscriptions import (
    MissReason,
    SubscriptionManager,
    SubscriptionPolicy,
)
from runtime.momentum_shadow import (
    MomentumShadowRuntime,
    MomentumShadowRuntimeConfig,
)
from signals.models import MomentumStage


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)
SESSION_ID = "20260818-shadow-test"
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "8039_2026-08-18_phase3_enriched_replay.json"
)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()

    def advance_to(self, value: datetime) -> None:
        if value < self.value:
            raise ValueError("test clock cannot move backward")
        self.value = value


class FakeMomentumStream:
    def __init__(
        self,
        references: tuple[InstrumentReference, ...],
        clock: MutableClock,
        *,
        auto_ack: bool = True,
    ) -> None:
        self._references = {item.symbol: item for item in references}
        self._clock = clock
        self._auto_ack = auto_ack
        self._event_handler = None
        self._lifecycle_handler = None
        self.subscribe_requests: list[str] = []
        self.unsubscribe_requests: list[str] = []
        self.stopped = False
        self.closed = False

    def start(self, event_handler, lifecycle_handler) -> None:
        self._event_handler = event_handler
        self._lifecycle_handler = lifecycle_handler

    def instrument_reference(
        self,
        symbol: str,
        session_date: date,
    ) -> InstrumentReference:
        reference = self._references[symbol]
        assert reference.session_date == session_date
        return reference

    def request_subscribe(self, symbol: str) -> None:
        self.subscribe_requests.append(symbol)
        if self._auto_ack:
            self.lifecycle(
                StreamLifecycleEventType.SUBSCRIBE_ACKED,
                symbol=symbol,
                reason="fake_pair_ack",
            )

    def request_unsubscribe(self, symbol: str) -> None:
        self.unsubscribe_requests.append(symbol)
        if self._auto_ack:
            self.lifecycle(
                StreamLifecycleEventType.UNSUBSCRIBE_ACKED,
                symbol=symbol,
                reason="fake_pair_ack",
            )

    def emit(self, envelope: EventEnvelope) -> None:
        assert self._event_handler is not None
        self._event_handler(envelope)

    def lifecycle(
        self,
        event_type: StreamLifecycleEventType,
        *,
        symbol: str | None = None,
        reason: str,
    ) -> None:
        assert self._lifecycle_handler is not None
        self._lifecycle_handler(
            StreamLifecycleEvent(
                event_type=event_type,
                occurred_at=self._clock.now(),
                reason=reason,
                symbol=symbol,
            )
        )

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 18, hour, minute, second, tzinfo=TAIPEI)


def reference(symbol: str) -> InstrumentReference:
    return InstrumentReference(
        symbol=symbol,
        exchange="TSE",
        session_date=SESSION_DATE,
        reference_price=dataset().references[0].reference_price,
        limit_up_price=dataset().references[0].limit_up_price,
        limit_down_price=dataset().references[0].limit_down_price,
        price_limit_applies=True,
        trading_unit_shares=1000,
        source_updated_at=SESSION_DATE,
    )


def dataset():
    return ReplayDatasetLoader().load(FIXTURE)


def discovery(
    symbol: str,
    observed_at: datetime,
    *,
    priority: int = 100,
    source: CandidateSource = CandidateSource.MANUAL,
) -> CandidateDiscovery:
    return CandidateDiscovery(
        symbol=symbol,
        source=source,
        rank_types=("PRICE_CHANGE",),
        best_rank=1 if source is CandidateSource.SCANNER else None,
        discovered_at=observed_at,
        expires_at=(
            observed_at + timedelta(minutes=1)
            if source is CandidateSource.SCANNER
            else None
        ),
        priority=priority,
    )


def build_runtime(
    *,
    queue_capacity: int = 64,
    max_symbols: int = 2,
    references: tuple[InstrumentReference, ...] | None = None,
    auto_ack: bool = True,
    background_worker: bool = False,
    required_stream_max_age: timedelta = timedelta(seconds=5),
) -> tuple[MomentumShadowRuntime, FakeMomentumStream, MutableClock]:
    clock = MutableClock(at(9, 6))
    available = references or dataset().references
    stream = FakeMomentumStream(available, clock, auto_ack=auto_ack)
    subscriptions = SubscriptionManager(
        SubscriptionPolicy(
            version="shadow_subscription_test_v0",
            capacity=SubscriptionCapacityConfig(
                account_subscription_limit=max_symbols * 2,
                reserved_headroom=0,
                mode=QuoteSubscriptionMode.TICK_BIDASK,
            ),
            ack_timeout=timedelta(seconds=5),
            retry_backoff=timedelta(0),
            minimum_dwell=timedelta(0),
        )
    )
    runtime = MomentumShadowRuntime(
        config=MomentumShadowRuntimeConfig(
            version="momentum_shadow_test_v0",
            session_id=SESSION_ID,
            session_date=SESSION_DATE,
            queue_capacity=queue_capacity,
            retention=timedelta(minutes=20),
            required_stream_max_age=required_stream_max_age,
            source_name="fake_tick_bidask",
            is_live_source=False,
            background_worker=background_worker,
        ),
        stream=stream,
        candidate_pool=CandidatePool(
            CandidatePoolConfig(
                version="shadow_pool_test_v0",
                grace_period=timedelta(seconds=10),
                scanner_min_observations=1,
            )
        ),
        subscriptions=subscriptions,
        clock=clock,
    )
    return runtime, stream, clock


def for_shadow(envelope: EventEnvelope) -> EventEnvelope:
    return replace(envelope, session_id=SESSION_ID)


def moved(
    envelope: EventEnvelope,
    *,
    event_at: datetime,
    sequence: int,
    event_id: str,
    tick_volume_lots: int | None = None,
    total_volume_lots: int | None = None,
) -> EventEnvelope:
    payload_changes = {
        "event_id": event_id,
        "event_time": event_at,
        "received_at": event_at,
        "ingress_sequence": sequence,
    }
    if tick_volume_lots is not None:
        payload_changes["tick_volume_lots"] = tick_volume_lots
    if total_volume_lots is not None:
        payload_changes["total_volume_lots"] = total_volume_lots
    payload = replace(envelope.payload, **payload_changes)
    return replace(
        envelope,
        event_id=event_id,
        session_id=SESSION_ID,
        event_at=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        source_identity=f"shadow-test:{event_id}",
        payload=payload,
    )


def subscribe_8039(
    runtime: MomentumShadowRuntime,
    clock: MutableClock,
) -> None:
    runtime.start()
    runtime.update_candidates(
        [discovery("8039", clock.now())],
        evaluated_at=clock.now(),
    )
    runtime.process_pending()


def test_enriched_8039_stream_reaches_accelerating_shadow_projection():
    replay = dataset()
    runtime, stream, clock = build_runtime()
    subscribe_8039(runtime, clock)

    for envelope in replay.events:
        clock.advance_to(envelope.received_at)
        stream.emit(for_shadow(envelope))
        runtime.process_pending()

    snapshot = runtime.snapshot()
    projection = runtime.projection("8039")

    assert snapshot.mode == "REALTIME_SHADOW_ALERT_ONLY"
    assert snapshot.covered_symbols == ("8039",)
    assert snapshot.health.state is DataHealthState.HEALTHY
    assert snapshot.counters.processed_events == len(replay.events)
    assert snapshot.counters.received_callback_events == len(replay.events)
    assert snapshot.counters.silent_drop_events == 0
    assert snapshot.counters.applied_ticks == 10
    assert snapshot.counters.applied_books == 1
    assert snapshot.counters.signal_evaluations == 10
    assert snapshot.counters.acceleration_signals == 1
    assert snapshot.subscription_mode is QuoteSubscriptionMode.TICK_BIDASK
    assert snapshot.subscription_max_symbols == 2
    assert snapshot.subscriptions_in_use == 2
    assert snapshot.subscription_ack_latency_ms == (("8039", 0.0),)
    assert snapshot.alert_count == 2
    assert snapshot.pending_alert_count == 2
    assert snapshot.miss_reason_by_symbol == ()
    assert projection is not None
    assert projection.current_stage is MomentumStage.ACCELERATING
    assert projection.signal_result.evidence_score == 90
    assert "external_ratio_rising" in {
        detail.rule
        for detail in projection.signal_result.details
        if not detail.passed
    }
    assert projection.entry_opportunity is not None
    assert projection.entry_opportunity.reasons == ("risk_gate_not_passed",)

    runtime.close()


def test_capacity_eviction_is_exposed_as_a_specific_miss_reason():
    refs = (reference("8039"), reference("2330"))
    runtime, stream, clock = build_runtime(
        max_symbols=1,
        references=refs,
    )
    runtime.start()
    runtime.update_candidates(
        [
            discovery(
                "8039",
                clock.now(),
                priority=100,
                source=CandidateSource.SCANNER,
            ),
            discovery(
                "2330",
                clock.now(),
                priority=10,
                source=CandidateSource.SCANNER,
            ),
        ],
        evaluated_at=clock.now(),
    )
    runtime.process_pending()

    snapshot = runtime.snapshot()

    assert stream.subscribe_requests == ["8039"]
    assert snapshot.capacity_evicted_symbols == ("2330",)
    assert runtime.classify_expected_symbol("2330") is (
        MissReason.CAPACITY_EVICTED
    )
    assert snapshot.miss_reason_counts == (
        (MissReason.CAPACITY_EVICTED, 1),
        (MissReason.DATA_INCOMPLETE, 1),
    )

    runtime.close()


def test_queue_overflow_rejects_new_event_and_blocks_data_health():
    replay = dataset()
    runtime, stream, clock = build_runtime(queue_capacity=1)
    subscribe_8039(runtime, clock)
    first, second = replay.events[:2]
    stream.emit(for_shadow(first))
    clock.advance_to(second.received_at)

    with pytest.raises(QueueOverflowError, match="queue full"):
        stream.emit(for_shadow(second))

    snapshot = runtime.snapshot()
    assert snapshot.queue_depth == 1
    assert snapshot.counters.enqueued_events == 1
    assert snapshot.counters.rejected_events == 1
    assert snapshot.health.state is DataHealthState.BLOCKED
    assert DataHealthReason.QUEUE_OVERFLOW in snapshot.health.reasons

    runtime.close()


def test_partial_subscription_rollback_failure_keeps_capacity_and_blocks_health():
    runtime, stream, clock = build_runtime(auto_ack=False, max_symbols=1)
    runtime.start()
    runtime.update_candidates(
        [discovery("8039", clock.now())],
        evaluated_at=clock.now(),
    )
    stream.lifecycle(
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED,
        symbol="8039",
        reason="paired_stream_partial_failure",
    )
    stream.lifecycle(
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED,
        symbol="8039",
        reason="provider_state_unknown",
    )
    runtime.process_pending()

    snapshot = runtime.snapshot()
    assert snapshot.consuming_symbols == ("8039",)
    assert snapshot.covered_symbols == ()
    assert snapshot.health.state is DataHealthState.BLOCKED
    assert DataHealthReason.SUBSCRIPTION_STATE_UNKNOWN in snapshot.health.reasons
    assert runtime.classify_expected_symbol("8039") is (
        MissReason.SUBSCRIPTION_NOT_ACKED
    )

    runtime.close()


def test_stale_pair_recovers_only_after_fresh_book_and_tick_evidence():
    replay = dataset()
    runtime, stream, clock = build_runtime()
    subscribe_8039(runtime, clock)
    clock.advance_to(at(9, 6, 6))

    assert runtime.check_staleness(evaluated_at=clock.now()) is True
    assert runtime.snapshot().connection_state is StreamConnectionState.RESYNCING
    assert runtime.snapshot().health.state is DataHealthState.BLOCKED

    book = moved(
        replay.events[-2],
        event_at=at(9, 6, 7),
        sequence=1,
        event_id="fresh-book",
    )
    tick = moved(
        replay.events[0],
        event_at=at(9, 6, 8),
        sequence=2,
        event_id="fresh-tick",
    )
    clock.advance_to(book.received_at)
    stream.emit(book)
    runtime.process_pending()
    assert runtime.snapshot().health.state is DataHealthState.BLOCKED

    clock.advance_to(tick.received_at)
    stream.emit(tick)
    runtime.process_pending()

    snapshot = runtime.snapshot()
    assert snapshot.health.state is DataHealthState.HEALTHY
    assert snapshot.health.reconnect_epoch == 1
    assert snapshot.connection_state is StreamConnectionState.RUNNING

    runtime.close()


def test_reconnect_requires_new_ack_and_fresh_pair_before_health_recovers():
    replay = dataset()
    runtime, stream, clock = build_runtime()
    subscribe_8039(runtime, clock)
    for envelope in replay.events:
        clock.advance_to(envelope.received_at)
        stream.emit(for_shadow(envelope))
        runtime.process_pending()

    clock.advance_to(at(9, 18, 1))
    stream.lifecycle(
        StreamLifecycleEventType.RECONNECTING,
        reason="network_down",
    )
    clock.advance_to(at(9, 18, 2))
    stream.lifecycle(
        StreamLifecycleEventType.RECONNECTED,
        reason="socket_reconnected",
    )
    runtime.process_pending()

    blocked = runtime.snapshot()
    assert blocked.health.state is DataHealthState.BLOCKED
    assert blocked.connection_state is StreamConnectionState.RESYNCING
    assert stream.subscribe_requests == ["8039", "8039"]

    fresh_book = moved(
        replay.events[-2],
        event_at=at(9, 18, 3),
        sequence=100,
        event_id="reconnect-book",
    )
    last_tick = replay.events[-1]
    fresh_tick = moved(
        last_tick,
        event_at=at(9, 18, 4),
        sequence=101,
        event_id="reconnect-gap-tick",
        tick_volume_lots=1,
        total_volume_lots=last_tick.payload.total_volume_lots + 2,
    )
    clock.advance_to(fresh_book.received_at)
    stream.emit(fresh_book)
    runtime.process_pending()
    assert runtime.snapshot().health.state is DataHealthState.BLOCKED

    clock.advance_to(fresh_tick.received_at)
    stream.emit(fresh_tick)
    runtime.process_pending()

    gap_blocked = runtime.snapshot()
    assert gap_blocked.health.state is DataHealthState.BLOCKED
    assert gap_blocked.health.gap_count == 1

    continuous_tick = moved(
        last_tick,
        event_at=at(9, 18, 5),
        sequence=102,
        event_id="reconnect-continuous-tick",
        tick_volume_lots=1,
        total_volume_lots=last_tick.payload.total_volume_lots + 3,
    )
    clock.advance_to(continuous_tick.received_at)
    stream.emit(continuous_tick)
    runtime.process_pending()

    recovered = runtime.snapshot()
    assert recovered.health.state is DataHealthState.HEALTHY
    assert recovered.health.reconnect_epoch == 1
    assert recovered.connection_state is StreamConnectionState.RUNNING
    assert recovered.counters.reconnect_count == 1

    runtime.close()


def test_close_stops_producer_then_drains_every_accepted_event():
    replay = dataset()
    runtime, stream, clock = build_runtime(queue_capacity=32)
    subscribe_8039(runtime, clock)
    for envelope in replay.events:
        clock.advance_to(envelope.received_at)
        stream.emit(for_shadow(envelope))

    runtime.close()
    snapshot = runtime.snapshot()

    assert stream.stopped is True
    assert stream.closed is True
    assert snapshot.running is False
    assert snapshot.connection_state is StreamConnectionState.STOPPED
    assert snapshot.queue_depth == 0
    assert snapshot.counters.processed_events == len(replay.events)
    assert snapshot.counters.processing_errors == 0


def test_background_worker_also_drains_before_close():
    replay = dataset()
    runtime, stream, clock = build_runtime(
        queue_capacity=32,
        background_worker=True,
        required_stream_max_age=timedelta(minutes=20),
    )
    subscribe_8039(runtime, clock)
    for envelope in replay.events:
        clock.advance_to(envelope.received_at)
        stream.emit(for_shadow(envelope))

    runtime.close()

    assert runtime.snapshot().counters.processed_events == len(replay.events)
    assert runtime.snapshot().queue_depth == 0


def test_background_worker_checks_staleness_without_external_polling():
    runtime, _, clock = build_runtime(background_worker=True)
    subscribe_8039(runtime, clock)
    clock.advance_to(at(9, 6, 6))

    deadline = monotonic() + 1
    while (
        runtime.snapshot().health.state is not DataHealthState.BLOCKED
        and monotonic() < deadline
    ):
        Event().wait(0.01)

    snapshot = runtime.snapshot()
    assert snapshot.health.state is DataHealthState.BLOCKED
    assert DataHealthReason.REQUIRED_STREAM_STALE in snapshot.health.reasons
    assert snapshot.connection_state is StreamConnectionState.RESYNCING

    runtime.close()


def test_shadow_runtime_has_no_order_execution_dependency():
    source = (
        Path(__file__).parents[1]
        / "runtime"
        / "momentum_shadow.py"
    ).read_text(encoding="utf-8")

    assert "from trading" not in source
    assert "import trading" not in source
    assert "Broker" not in source
    assert "place_order" not in source
