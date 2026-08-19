"""Long-lived, market-data-only runtime for realtime Momentum shadowing."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from threading import Event, RLock, Thread

from candidate.pool import (
    CandidatePool,
    CandidatePoolDecision,
)
from candidate.sources import CandidateDiscovery
from config.momentum import (
    MOMENTUM_ENTRY_HYPOTHESIS_V0,
    QuoteSubscriptionMode,
)
from features.engine import FeatureEngine
from features.models import FeatureEvaluationContext
from market_data.events import EventEnvelope, MarketStreamKind, TickEvent
from market_data.health import (
    DataHealth,
    DataHealthReason,
    DataHealthSnapshot,
    DataHealthState,
)
from market_data.ingestion import (
    BoundedMarketEventQueue,
    IngestStatus,
    MarketDataIngestor,
    QueueOverflowError,
)
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.momentum_stream import (
    MomentumMarketDataStream,
    StreamConnectionState,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.order_book_store import OrderBookStore
from market_data.subscriptions import (
    MissReason,
    SubscriptionDecision,
    SubscriptionManager,
)
from runtime.clock import Clock, SystemClock
from signals.models import (
    EpisodeStatus,
    RiskGateStatus,
    SignalEvaluationStatus,
    evaluate_momentum_entry_opportunity,
)
from signals.momentum import MomentumSignalEngine
from signals.momentum_state import MomentumStateMachine
from signals.projection import (
    MomentumAlert,
    MomentumProjection,
    MomentumProjectionStore,
)


@dataclass(frozen=True)
class MomentumShadowRuntimeConfig:
    version: str
    session_id: str
    session_date: date
    queue_capacity: int
    retention: timedelta
    required_stream_max_age: timedelta
    source_name: str
    is_live_source: bool
    worker_poll_interval: float = 0.05
    background_worker: bool = True
    aggressor_mapping_verified: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Shadow runtime version must not be empty")
        if not self.session_id.strip():
            raise ValueError("Shadow runtime session_id must not be empty")
        if self.queue_capacity <= 0:
            raise ValueError("Shadow queue capacity must be positive")
        if self.retention < timedelta(minutes=20):
            raise ValueError("Shadow retention must be at least 20 minutes")
        if self.required_stream_max_age <= timedelta(0):
            raise ValueError("required_stream_max_age must be positive")
        if not self.source_name.strip():
            raise ValueError("Shadow source_name must not be empty")
        if self.worker_poll_interval <= 0:
            raise ValueError("worker_poll_interval must be positive")


@dataclass(frozen=True)
class MomentumShadowCounters:
    received_callback_events: int
    enqueued_events: int
    rejected_events: int
    silent_drop_events: int
    processed_events: int
    applied_ticks: int
    applied_books: int
    projection_updates: int
    signal_evaluations: int
    acceleration_signals: int
    insufficient_data_evaluations: int
    processing_errors: int
    reconnect_count: int
    latest_source_lag_ms: float | None
    max_source_lag_ms: float | None


@dataclass(frozen=True)
class MomentumShadowSnapshot:
    mode: str
    config_version: str
    source_name: str
    is_live_source: bool
    session_id: str
    session_date: date
    running: bool
    connection_state: StreamConnectionState
    health: DataHealthSnapshot
    queue_capacity: int
    queue_depth: int
    subscription_mode: QuoteSubscriptionMode
    subscription_max_symbols: int
    subscriptions_in_use: int
    subscription_event_count: int
    subscription_ack_latency_ms: tuple[tuple[str, float], ...]
    covered_symbols: tuple[str, ...]
    consuming_symbols: tuple[str, ...]
    discovered_symbols: tuple[str, ...]
    admitted_symbols: tuple[str, ...]
    capacity_evicted_symbols: tuple[str, ...]
    miss_reason_by_symbol: tuple[tuple[str, MissReason], ...]
    miss_reason_counts: tuple[tuple[MissReason, int], ...]
    counters: MomentumShadowCounters
    projection_count: int
    data_complete_symbol_count: int
    signal_emitted_symbol_count: int
    active_episode_count: int
    alert_count: int
    pending_alert_count: int
    suppressed_alert_count: int
    projection_digest: str
    runtime_errors: tuple[str, ...]
    adapter_callback_errors: tuple[str, ...]


@dataclass(frozen=True)
class MomentumShadowReadView:
    """One process-lock capture for dashboard serialization."""

    snapshot: MomentumShadowSnapshot
    projections: tuple[tuple[str, MomentumProjection | None], ...]
    miss_reason_by_symbol: tuple[tuple[str, MissReason], ...]
    pending_alerts: tuple[MomentumAlert, ...]


class MomentumShadowRuntime:
    """Compose discovery, subscriptions, ingestion, features, and alerts.

    Provider callbacks only enqueue immutable events. All domain processing is
    serialized by this application service, and Entry remains blocked because
    no RiskGate decision is supplied in Shadow mode.
    """

    def __init__(
        self,
        *,
        config: MomentumShadowRuntimeConfig,
        stream: MomentumMarketDataStream,
        candidate_pool: CandidatePool,
        subscriptions: SubscriptionManager,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._stream = stream
        self._candidate_pool = candidate_pool
        self._subscriptions = subscriptions
        self._clock = clock or SystemClock()
        if subscriptions.policy.mode is not QuoteSubscriptionMode.TICK_BIDASK:
            raise ValueError("Phase 6 Shadow requires explicit Tick+BidAsk mode")

        started_at = self._clock.now()
        if started_at.date() != config.session_date:
            raise ValueError("Shadow clock must belong to configured session_date")
        self._references = InstrumentReferenceStore(config.session_date)
        self._bars = IntradayBarStore(
            config.session_date,
            retention=config.retention,
        )
        self._books = OrderBookStore(
            config.session_date,
            retention=config.retention,
        )
        self._health = DataHealth(config.session_date, started_at=started_at)
        self._queue = BoundedMarketEventQueue(
            config.queue_capacity,
            self._health,
        )
        self._ingestor = MarketDataIngestor(
            session_id=config.session_id,
            session_date=config.session_date,
            references=self._references,
            bars=self._bars,
            books=self._books,
            health=self._health,
        )
        self._features = FeatureEngine(
            references=self._references,
            bars=self._bars,
            books=self._books,
        )
        self._signals = MomentumSignalEngine()
        self._states = MomentumStateMachine(config.session_date)
        self._projections = MomentumProjectionStore(config.session_date)

        self._state_lock = RLock()
        self._process_lock = RLock()
        self._wake = Event()
        self._lifecycle_events: deque[StreamLifecycleEvent] = deque()
        self._worker: Thread | None = None
        self._running = False
        self._closed = False
        self._stop_requested = False
        self._connection_state = StreamConnectionState.STOPPED
        self._latest_pool_decision: CandidatePoolDecision | None = None
        self._latest_subscription_decision: SubscriptionDecision | None = None
        self._coverage_acked_at: dict[str, datetime] = {}
        self._tick_coverage_started_at: dict[str, datetime] = {}
        self._latest_data_complete: dict[str, bool] = {}
        self._latest_signal_emitted: dict[str, bool] = {}
        self._resync_epoch = 0
        self._resync_started_at: datetime | None = None
        self._resync_seen: dict[str, set[MarketStreamKind]] = {}
        self._runtime_errors: list[str] = []
        self._received_callback_events = 0
        self._enqueued_events = 0
        self._rejected_events = 0
        self._processed_events = 0
        self._applied_ticks = 0
        self._applied_books = 0
        self._projection_updates = 0
        self._signal_evaluations = 0
        self._acceleration_signals = 0
        self._insufficient_data_evaluations = 0
        self._processing_errors = 0
        self._reconnect_count = 0
        self._latest_source_lag_ms: float | None = None
        self._max_source_lag_ms: float | None = None

    def projection(self, symbol: str) -> MomentumProjection | None:
        with self._process_lock:
            return self._projections.get(symbol.strip().upper())

    def pending_alerts(self) -> tuple[MomentumAlert, ...]:
        with self._process_lock:
            return self._projections.pending_alerts()

    def acknowledge_alert(
        self,
        alert_id: str,
        *,
        acknowledged_at: datetime,
    ) -> None:
        """Acknowledge a local Shadow alert without emitting an external action."""
        self._require_aware(acknowledged_at)
        with self._process_lock:
            self._projections.acknowledge(
                alert_id,
                acknowledged_at=acknowledged_at,
            )

    def start(self) -> None:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("Momentum Shadow runtime is closed")
            if self._running:
                return
            self._stop_requested = False
        self._stream.start(self._on_market_event, self._on_lifecycle_event)
        with self._state_lock:
            self._running = True
            self._connection_state = StreamConnectionState.RUNNING
            if self._config.background_worker:
                self._worker = Thread(
                    target=self._worker_loop,
                    name="momentum-shadow-worker",
                    daemon=True,
                )
                self._worker.start()

    def update_candidates(
        self,
        discoveries: tuple[CandidateDiscovery, ...]
        | list[CandidateDiscovery],
        *,
        evaluated_at: datetime,
    ) -> SubscriptionDecision:
        self._require_started()
        with self._process_lock:
            active = self._active_episode_symbols()
            pool_decision = self._candidate_pool.ingest(
                discoveries,
                evaluated_at=evaluated_at,
                active_episode_symbols=active,
            )
            decision = self._subscriptions.reconcile(
                pool_decision.entries,
                evaluated_at=evaluated_at,
                active_episode_symbols=active,
            )
            with self._state_lock:
                self._latest_pool_decision = pool_decision
                self._latest_subscription_decision = decision
            self._execute_subscription_decision(decision)
            return decision

    def process_pending(self, *, max_events: int | None = None) -> int:
        if max_events is not None and max_events <= 0:
            raise ValueError("max_events must be positive")
        processed = 0
        with self._process_lock:
            while max_events is None or processed < max_events:
                lifecycle = self._pop_lifecycle()
                if lifecycle is not None:
                    self._process_lifecycle(lifecycle)
                    processed += 1
                    continue
                envelope = self._queue.get(occurred_at=self._clock.now())
                if envelope is None:
                    break
                self._process_market_event(envelope)
                processed += 1
        return processed

    def check_staleness(self, *, evaluated_at: datetime) -> bool:
        """Block on missing/stale paired streams and require fresh pair evidence."""
        self._require_aware(evaluated_at)
        self.process_pending()
        with self._process_lock:
            return self._check_staleness(evaluated_at)

    def _check_staleness(self, evaluated_at: datetime) -> bool:
        if self._connection_state not in {
            StreamConnectionState.RUNNING,
            StreamConnectionState.RESYNCING,
        }:
            return False
        covered = self._subscriptions.covered_symbols
        if not covered:
            return False
        snapshot = self._health.snapshot()
        evaluated_at = max(evaluated_at, snapshot.as_of)
        stream_health = {
            (item.symbol, item.stream_kind): item for item in snapshot.streams
        }
        stale = False
        for symbol in covered:
            acked_at = self._coverage_acked_at.get(symbol)
            for stream_kind in (MarketStreamKind.TICK, MarketStreamKind.BIDASK):
                item = stream_health.get((symbol, stream_kind))
                last_received = item.last_received_at if item is not None else None
                if last_received is None:
                    if (
                        acked_at is not None
                        and evaluated_at - acked_at
                        > self._config.required_stream_max_age
                    ):
                        stale = True
                elif (
                    evaluated_at - last_received
                    > self._config.required_stream_max_age
                ):
                    stale = True
        if not stale:
            return False
        if self._connection_state is not StreamConnectionState.RESYNCING:
            self._health.mark_required_stream_stale(occurred_at=evaluated_at)
            self._begin_resync(evaluated_at)
        return True

    def classify_expected_symbol(self, symbol: str) -> MissReason | None:
        with self._process_lock:
            return self._classify_expected_symbol(symbol)

    def _classify_expected_symbol(self, symbol: str) -> MissReason | None:
        normalized = str(symbol).strip().upper()
        with self._state_lock:
            pool = self._latest_pool_decision
            subscription = self._latest_subscription_decision
            data_complete = self._latest_data_complete.get(normalized, False)
            signal_emitted = self._latest_signal_emitted.get(normalized, False)
        discovered = frozenset(
            item.symbol for item in pool.entries
        ) if pool is not None else frozenset()
        admitted = frozenset(
            pool.admitted_symbols
        ) if pool is not None else frozenset()
        evicted = frozenset(
            subscription.capacity_evicted_symbols
        ) if subscription is not None else frozenset()
        return self._subscriptions.classify_miss(
            normalized,
            discovered_symbols=discovered,
            admitted_symbols=admitted,
            capacity_evicted_symbols=evicted,
            data_complete=data_complete,
            signal_emitted=signal_emitted,
        )

    def snapshot(self) -> MomentumShadowSnapshot:
        with self._process_lock:
            return self._build_snapshot()

    def read_view(
        self,
        expected_symbols: tuple[str, ...] | list[str],
    ) -> MomentumShadowReadView:
        """Capture runtime metadata, rows, misses, and alerts atomically."""
        normalized = tuple(
            dict.fromkeys(
                str(symbol).strip().upper()
                for symbol in expected_symbols
                if str(symbol).strip()
            )
        )
        with self._process_lock:
            projections = tuple(
                (symbol, self._projections.get(symbol))
                for symbol in normalized
            )
            misses = tuple(
                (symbol, reason)
                for symbol, projection in projections
                if projection is None
                and (
                    reason := self._classify_expected_symbol(symbol)
                ) is not None
            )
            return MomentumShadowReadView(
                snapshot=self._build_snapshot(),
                projections=projections,
                miss_reason_by_symbol=misses,
                pending_alerts=self._projections.pending_alerts(),
            )

    def _build_snapshot(self) -> MomentumShadowSnapshot:
        with self._state_lock:
            pool = self._latest_pool_decision
            subscription = self._latest_subscription_decision
            running = self._running
            connection = self._connection_state
            runtime_errors = tuple(self._runtime_errors)
            received_callback_events = self._received_callback_events
            counters = MomentumShadowCounters(
                received_callback_events=received_callback_events,
                enqueued_events=self._enqueued_events,
                rejected_events=self._rejected_events,
                silent_drop_events=(
                    received_callback_events
                    - self._enqueued_events
                    - self._rejected_events
                ),
                processed_events=self._processed_events,
                applied_ticks=self._applied_ticks,
                applied_books=self._applied_books,
                projection_updates=self._projection_updates,
                signal_evaluations=self._signal_evaluations,
                acceleration_signals=self._acceleration_signals,
                insufficient_data_evaluations=(
                    self._insufficient_data_evaluations
                ),
                processing_errors=self._processing_errors,
                reconnect_count=self._reconnect_count,
                latest_source_lag_ms=self._latest_source_lag_ms,
                max_source_lag_ms=self._max_source_lag_ms,
            )
        discovered = tuple(
            sorted(item.symbol for item in pool.entries)
        ) if pool is not None else ()
        admitted = pool.admitted_symbols if pool is not None else ()
        evicted = (
            subscription.capacity_evicted_symbols
            if subscription is not None
            else ()
        )
        misses = tuple(
            (symbol, reason)
            for symbol in discovered
            if (reason := self._classify_expected_symbol(symbol)) is not None
        )
        miss_counts = Counter(reason for _, reason in misses)
        projections = self._projections.all()
        alerts = tuple(
            alert
            for projection in projections
            for alert in self._projections.alerts_for(projection.symbol)
        )
        ack_latency = tuple(
            (
                record.symbol,
                (record.acked_at - record.requested_at).total_seconds() * 1000,
            )
            for record in self._subscriptions.records
            if record.acked_at is not None and record.requested_at is not None
        )
        adapter_errors = tuple(
            str(value)
            for value in getattr(self._stream, "callback_errors", ())
        )
        return MomentumShadowSnapshot(
            mode="REALTIME_SHADOW_ALERT_ONLY",
            config_version=self._config.version,
            source_name=self._config.source_name,
            is_live_source=self._config.is_live_source,
            session_id=self._config.session_id,
            session_date=self._config.session_date,
            running=running,
            connection_state=connection,
            health=self._health.snapshot(),
            queue_capacity=self._config.queue_capacity,
            queue_depth=len(self._queue),
            subscription_mode=self._subscriptions.policy.mode,
            subscription_max_symbols=self._subscriptions.policy.max_symbols,
            subscriptions_in_use=self._subscriptions.subscriptions_in_use,
            subscription_event_count=len(self._subscriptions.events),
            subscription_ack_latency_ms=ack_latency,
            covered_symbols=tuple(sorted(self._subscriptions.covered_symbols)),
            consuming_symbols=tuple(
                sorted(self._subscriptions.consuming_symbols)
            ),
            discovered_symbols=discovered,
            admitted_symbols=admitted,
            capacity_evicted_symbols=evicted,
            miss_reason_by_symbol=misses,
            miss_reason_counts=tuple(
                (reason, miss_counts[reason])
                for reason in MissReason
                if miss_counts[reason]
            ),
            counters=counters,
            projection_count=len(projections),
            data_complete_symbol_count=sum(
                self._latest_data_complete.get(symbol, False)
                for symbol in discovered
            ),
            signal_emitted_symbol_count=sum(
                self._latest_signal_emitted.get(symbol, False)
                for symbol in discovered
            ),
            active_episode_count=sum(
                item.episode is not None
                and item.episode.status is EpisodeStatus.ACTIVE
                for item in projections
            ),
            alert_count=len(alerts),
            pending_alert_count=len(self._projections.pending_alerts()),
            suppressed_alert_count=self._projections.suppressed_alert_count,
            projection_digest=self._projections.digest,
            runtime_errors=runtime_errors,
            adapter_callback_errors=adapter_errors,
        )

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            was_running = self._running
        if was_running:
            try:
                self._stream.stop()
            except Exception as error:
                self._record_runtime_error("stop", error)
            with self._state_lock:
                self._stop_requested = True
            self._wake.set()
            worker = self._worker
            if worker is not None:
                worker.join(timeout=5)
                if worker.is_alive():
                    raise RuntimeError("Momentum Shadow worker did not drain")
            self.process_pending()
        self._bars.finalize_session()
        self._books.finalize_session()
        self._stream.close()
        with self._state_lock:
            self._running = False
            self._closed = True
            self._connection_state = StreamConnectionState.STOPPED

    def _on_market_event(self, envelope: EventEnvelope) -> None:
        with self._state_lock:
            self._received_callback_events += 1
        try:
            self._queue.put(envelope)
        except QueueOverflowError:
            with self._state_lock:
                self._rejected_events += 1
            self._wake.set()
            raise
        with self._state_lock:
            self._enqueued_events += 1
        self._wake.set()

    def _on_lifecycle_event(self, event: StreamLifecycleEvent) -> None:
        with self._state_lock:
            self._lifecycle_events.append(event)
        self._wake.set()

    def _worker_loop(self) -> None:
        while True:
            try:
                self.process_pending()
            except Exception as error:
                self._record_runtime_error("worker", error)
            with self._state_lock:
                stop = self._stop_requested
                lifecycle_pending = bool(self._lifecycle_events)
            if not stop:
                try:
                    with self._process_lock:
                        self._check_staleness(self._clock.now())
                except Exception as error:
                    self._record_runtime_error("staleness", error)
            if stop and not lifecycle_pending and len(self._queue) == 0:
                return
            self._wake.wait(self._config.worker_poll_interval)
            self._wake.clear()

    def _pop_lifecycle(self) -> StreamLifecycleEvent | None:
        with self._state_lock:
            return self._lifecycle_events.popleft() if self._lifecycle_events else None

    def _process_lifecycle(self, event: StreamLifecycleEvent) -> None:
        event_type = event.event_type
        symbol = event.symbol
        try:
            if event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED:
                assert symbol is not None
                self._subscriptions.ack_subscribe(
                    symbol,
                    occurred_at=event.occurred_at,
                )
                self._coverage_acked_at[symbol] = event.occurred_at
                if self._health.state is DataHealthState.STARTING:
                    self._health.mark_ready(
                        occurred_at=event.occurred_at,
                        evidence="paired_tick_bidask_subscription_ack",
                    )
            elif event_type is StreamLifecycleEventType.SUBSCRIBE_FAILED:
                assert symbol is not None
                self._subscriptions.fail_subscribe(
                    symbol,
                    occurred_at=event.occurred_at,
                    reason=event.reason,
                )
            elif event_type is (
                StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED
            ):
                assert symbol is not None
                self._subscriptions.begin_subscribe_rollback(
                    symbol,
                    occurred_at=event.occurred_at,
                    reason=event.reason,
                )
            elif event_type is (
                StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED
            ):
                assert symbol is not None
                self._subscriptions.fail_unsubscribe(
                    symbol,
                    occurred_at=event.occurred_at,
                    reason=event.reason,
                )
                self._health.record_invalid(
                    DataHealthReason.SUBSCRIPTION_STATE_UNKNOWN,
                    occurred_at=event.occurred_at,
                )
            elif event_type is StreamLifecycleEventType.UNSUBSCRIBE_ACKED:
                assert symbol is not None
                self._subscriptions.ack_unsubscribe(
                    symbol,
                    occurred_at=event.occurred_at,
                )
                self._coverage_acked_at.pop(symbol, None)
                self._tick_coverage_started_at.pop(symbol, None)
            elif event_type is StreamLifecycleEventType.UNSUBSCRIBE_FAILED:
                assert symbol is not None
                self._subscriptions.fail_unsubscribe(
                    symbol,
                    occurred_at=event.occurred_at,
                    reason=event.reason,
                )
            elif event_type in {
                StreamLifecycleEventType.DISCONNECTED,
                StreamLifecycleEventType.RECONNECTING,
            }:
                if self._subscriptions.consuming_symbols:
                    self._subscriptions.mark_disconnected(
                        occurred_at=event.occurred_at,
                    )
                self._health.mark_provider_disconnected(
                    occurred_at=event.occurred_at,
                )
                self._connection_state = (
                    StreamConnectionState.RECONNECTING
                    if event_type is StreamLifecycleEventType.RECONNECTING
                    else StreamConnectionState.DISCONNECTED
                )
                self._tick_coverage_started_at.clear()
            elif event_type is StreamLifecycleEventType.RECONNECTED:
                if self._subscriptions.consuming_symbols:
                    self._subscriptions.mark_disconnected(
                        occurred_at=event.occurred_at,
                    )
                self._reconnect_count += 1
                self._begin_resync(event.occurred_at)
                self._reconcile_after_reconnect(event.occurred_at)
        except Exception as error:
            self._record_runtime_error(event_type.value, error)

    def _process_market_event(self, envelope: EventEnvelope) -> None:
        try:
            result = self._ingestor.ingest(envelope)
            with self._state_lock:
                self._processed_events += 1
                source_lag_ms = (
                    envelope.received_at - envelope.event_at
                ).total_seconds() * 1000
                self._latest_source_lag_ms = source_lag_ms
                self._max_source_lag_ms = max(
                    source_lag_ms,
                    self._max_source_lag_ms
                    if self._max_source_lag_ms is not None
                    else source_lag_ms,
                )
            if not result.projection_applied:
                return
            if envelope.stream_kind is MarketStreamKind.TICK:
                with self._state_lock:
                    self._applied_ticks += 1
            else:
                with self._state_lock:
                    self._applied_books += 1
            if result.status is IngestStatus.APPLIED:
                self._record_resync_evidence(envelope)
            if not isinstance(envelope.payload, TickEvent):
                return
            self._tick_coverage_started_at.setdefault(
                envelope.symbol,
                envelope.event_at,
            )
            feature = self._features.evaluate(
                envelope.payload,
                FeatureEvaluationContext(
                    data_health=self._health.snapshot(),
                    tick_coverage_started_at=(
                        self._tick_coverage_started_at.get(envelope.symbol)
                    ),
                    aggressor_mapping_verified=(
                        self._config.aggressor_mapping_verified
                    ),
                ),
            )
            signal = self._signals.evaluate(feature)
            state = self._states.evaluate(feature, signal)
            entry = None
            if state.episode is not None:
                entry = evaluate_momentum_entry_opportunity(
                    state.episode,
                    signal.digest,
                    MOMENTUM_ENTRY_HYPOTHESIS_V0,
                    RiskGateStatus.UNAVAILABLE,
                )
            self._projections.apply(
                feature,
                signal,
                state,
                entry_opportunity=entry,
            )
            with self._state_lock:
                self._projection_updates += 1
                self._signal_evaluations += 1
                if signal.momentum_acceleration_confirmed:
                    self._acceleration_signals += 1
                if signal.evaluation_status is (
                    SignalEvaluationStatus.INSUFFICIENT_DATA
                ):
                    self._insufficient_data_evaluations += 1
                self._latest_data_complete[envelope.symbol] = (
                    feature.required_inputs_valid
                )
                self._latest_signal_emitted[envelope.symbol] = (
                    signal.evaluation_status is SignalEvaluationStatus.TRIGGERED
                    and signal.momentum_acceleration_confirmed
                )
        except Exception as error:
            with self._state_lock:
                self._processing_errors += 1
            self._record_runtime_error("market_event", error)
            try:
                self._health.record_invalid(
                    DataHealthReason.INVALID_EVENT,
                    occurred_at=envelope.received_at,
                )
            except ValueError:
                pass

    def _record_resync_evidence(self, envelope: EventEnvelope) -> None:
        if self._connection_state is not StreamConnectionState.RESYNCING:
            return
        if (
            self._resync_started_at is None
            or envelope.received_at < self._resync_started_at
            or envelope.symbol not in self._subscriptions.covered_symbols
        ):
            return
        self._resync_seen.setdefault(envelope.symbol, set()).add(
            envelope.stream_kind
        )
        covered = self._subscriptions.covered_symbols
        required = {MarketStreamKind.TICK, MarketStreamKind.BIDASK}
        if covered and all(
            required <= self._resync_seen.get(symbol, set())
            for symbol in covered
        ):
            self._health.recover(
                reconnect_epoch=self._resync_epoch,
                occurred_at=envelope.received_at,
                evidence="fresh_tick_and_bidask_for_all_covered_symbols",
            )
            self._connection_state = StreamConnectionState.RUNNING

    def _begin_resync(self, occurred_at: datetime) -> None:
        self._resync_epoch += 1
        self._resync_started_at = occurred_at
        self._resync_seen.clear()
        self._connection_state = StreamConnectionState.RESYNCING

    def _reconcile_after_reconnect(self, occurred_at: datetime) -> None:
        pool = self._candidate_pool.evaluate(
            evaluated_at=occurred_at,
            active_episode_symbols=self._active_episode_symbols(),
        )
        decision = self._subscriptions.reconcile(
            pool.entries,
            evaluated_at=occurred_at,
            active_episode_symbols=self._active_episode_symbols(),
        )
        self._latest_pool_decision = pool
        self._latest_subscription_decision = decision
        self._execute_subscription_decision(decision)

    def _execute_subscription_decision(
        self,
        decision: SubscriptionDecision,
    ) -> None:
        for symbol in decision.unsubscribe_symbols:
            try:
                self._stream.request_unsubscribe(symbol)
            except Exception as error:
                self._subscriptions.fail_unsubscribe(
                    symbol,
                    occurred_at=decision.evaluated_at,
                    reason=f"provider_request_failed:{type(error).__name__}",
                )
                self._record_runtime_error("unsubscribe", error)
        for symbol in decision.request_symbols:
            try:
                reference = self._stream.instrument_reference(
                    symbol,
                    self._config.session_date,
                )
                self._references.put(reference)
                if not reference.eligible_for_limit_up_momentum:
                    raise ValueError(
                        f"{symbol} lacks current-session price-limit evidence"
                    )
                self._stream.request_subscribe(symbol)
            except Exception as error:
                self._subscriptions.fail_subscribe(
                    symbol,
                    occurred_at=decision.evaluated_at,
                    reason=f"provider_request_failed:{type(error).__name__}",
                )
                self._record_runtime_error("subscribe", error)

    def _active_episode_symbols(self) -> frozenset[str]:
        return frozenset(
            item.symbol
            for item in self._projections.all()
            if item.episode is not None
            and item.episode.status is EpisodeStatus.ACTIVE
        )

    def _record_runtime_error(self, context: str, error: Exception) -> None:
        with self._state_lock:
            self._runtime_errors.append(
                f"{context}:{type(error).__name__}:{error}"
            )

    def _require_started(self) -> None:
        with self._state_lock:
            if not self._running:
                raise RuntimeError("Momentum Shadow runtime is not started")

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Shadow timestamps must be timezone-aware")
