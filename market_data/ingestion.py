"""Ordered canonical event ingestion and explicit bounded queue behavior."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from threading import Lock

from market_data.events import (
    BidAskEvent,
    EventEnvelope,
    MarketStreamKind,
    ProjectionApplyStatus,
    StreamWatermark,
    TickEvent,
)
from market_data.health import (
    DataHealth,
    DataHealthReason,
    DataHealthState,
)
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore


class IngestStatus(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER_REJECTED = "OUT_OF_ORDER_REJECTED"
    SESSION_MISMATCH_REJECTED = "SESSION_MISMATCH_REJECTED"
    INVALID_REJECTED = "INVALID_REJECTED"
    APPLIED_HEALTH_BLOCKED = "APPLIED_HEALTH_BLOCKED"


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    event_id: str
    symbol: str
    stream_kind: MarketStreamKind
    previous_watermark: StreamWatermark | None
    new_watermark: StreamWatermark | None
    projection_applied: bool
    reason: str | None
    health_before: DataHealthState
    health_after: DataHealthState


class QueueOverflowError(RuntimeError):
    pass


class BoundedMarketEventQueue:
    """Rejects overflow explicitly and preserves already accepted events."""

    def __init__(self, capacity: int, health: DataHealth) -> None:
        if capacity <= 0:
            raise ValueError("queue capacity must be positive")
        self._capacity = capacity
        self._health = health
        self._events: deque[EventEnvelope] = deque()
        self._lock = Lock()

    def put(self, envelope: EventEnvelope) -> None:
        with self._lock:
            self._put_locked(envelope)

    def _put_locked(self, envelope: EventEnvelope) -> None:
        if len(self._events) >= self._capacity:
            self._health.record_queue(
                depth=len(self._events),
                occurred_at=envelope.received_at,
                overflow=True,
            )
            raise QueueOverflowError(
                f"market event queue full; rejected {envelope.event_id}"
            )
        self._events.append(envelope)
        self._health.record_queue(
            depth=len(self._events),
            occurred_at=envelope.received_at,
        )

    def get(self, *, occurred_at: datetime) -> EventEnvelope | None:
        with self._lock:
            event = self._events.popleft() if self._events else None
            self._health.record_queue(
                depth=len(self._events),
                occurred_at=occurred_at,
            )
            return event

    def drain(self, *, occurred_at: datetime) -> tuple[EventEnvelope, ...]:
        with self._lock:
            events = tuple(self._events)
            self._events.clear()
            self._health.record_queue(depth=0, occurred_at=occurred_at)
            return events

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


class MarketDataIngestor:
    """One session consumer with independent Tick and BidAsk watermarks."""

    def __init__(
        self,
        *,
        session_id: str,
        session_date: date,
        references: InstrumentReferenceStore,
        bars: IntradayBarStore,
        books: OrderBookStore,
        health: DataHealth,
    ) -> None:
        if not session_id.strip():
            raise ValueError("ingestor session_id must not be empty")
        stores = {
            references.session_date,
            bars.session_date,
            books.session_date,
            health.snapshot().session_date,
        }
        if stores != {session_date}:
            raise ValueError("ingestor stores must share one session_date")
        self._session_id = session_id
        self._session_date = session_date
        self._references = references
        self._bars = bars
        self._books = books
        self._health = health
        self._seen_event_ids: set[str] = set()
        self._watermarks: dict[
            tuple[str, MarketStreamKind], StreamWatermark
        ] = {}

    def begin_session(
        self,
        session_id: str,
        session_date: date,
        *,
        started_at: datetime,
    ) -> None:
        if not session_id.strip():
            raise ValueError("ingestor session_id must not be empty")
        self._session_id = session_id
        self._session_date = session_date
        self._references.begin_session(session_date)
        self._bars.begin_session(session_date)
        self._books.begin_session(session_date)
        self._health.begin_session(session_date, started_at=started_at)
        self._seen_event_ids.clear()
        self._watermarks.clear()

    def ingest(self, envelope: EventEnvelope) -> IngestResult:
        health_before = self._health.state
        key = (envelope.symbol, envelope.stream_kind)
        previous = self._watermarks.get(key)

        if (
            envelope.session_id != self._session_id
            or envelope.session_date != self._session_date
        ):
            self._health.record_invalid(
                DataHealthReason.SESSION_MISMATCH,
                occurred_at=envelope.received_at,
            )
            return self._result(
                envelope,
                IngestStatus.SESSION_MISMATCH_REJECTED,
                previous,
                previous,
                False,
                "event_session_does_not_match_ingestor",
                health_before,
            )
        if envelope.event_id in self._seen_event_ids:
            self._health.record_duplicate(envelope)
            return self._result(
                envelope,
                IngestStatus.DUPLICATE,
                previous,
                previous,
                False,
                "event_id_already_ingested",
                health_before,
            )
        if self._references.get(envelope.symbol) is None:
            self._health.record_invalid(
                DataHealthReason.INVALID_INSTRUMENT_REFERENCE,
                occurred_at=envelope.received_at,
            )
            return self._result(
                envelope,
                IngestStatus.INVALID_REJECTED,
                previous,
                previous,
                False,
                "instrument_reference_missing",
                health_before,
            )
        if previous is not None and envelope.watermark <= previous:
            self._health.record_out_of_order(envelope)
            return self._result(
                envelope,
                IngestStatus.OUT_OF_ORDER_REJECTED,
                previous,
                previous,
                False,
                "stream_watermark_not_monotonic",
                health_before,
            )

        if isinstance(envelope.payload, TickEvent):
            projection = self._bars.apply(envelope.payload)
        elif isinstance(envelope.payload, BidAskEvent):
            projection = self._books.apply(envelope.payload)
        else:
            raise TypeError("unsupported market event payload")

        if projection.status is ProjectionApplyStatus.DUPLICATE:
            self._health.record_duplicate(envelope)
            status = IngestStatus.DUPLICATE
        elif projection.status is ProjectionApplyStatus.OUT_OF_ORDER:
            self._health.record_out_of_order(envelope)
            status = IngestStatus.OUT_OF_ORDER_REJECTED
        elif projection.status is ProjectionApplyStatus.SESSION_MISMATCH:
            self._health.record_invalid(
                DataHealthReason.SESSION_MISMATCH,
                occurred_at=envelope.received_at,
            )
            status = IngestStatus.SESSION_MISMATCH_REJECTED
        elif projection.status is ProjectionApplyStatus.INVALID:
            self._health.record_invalid(
                DataHealthReason.INVALID_EVENT,
                occurred_at=envelope.received_at,
            )
            status = IngestStatus.INVALID_REJECTED
        else:
            self._seen_event_ids.add(envelope.event_id)
            self._watermarks[key] = envelope.watermark
            self._health.record_applied(envelope)
            status = IngestStatus.APPLIED
            if projection.status is ProjectionApplyStatus.APPLIED_WITH_GAP:
                self._health.record_invalid(
                    DataHealthReason.CUMULATIVE_VOLUME_GAP,
                    occurred_at=envelope.received_at,
                )
                status = IngestStatus.APPLIED_HEALTH_BLOCKED

        return self._result(
            envelope,
            status,
            previous,
            projection.new_watermark,
            projection.projection_applied,
            projection.reason,
            health_before,
        )

    def _result(
        self,
        envelope: EventEnvelope,
        status: IngestStatus,
        previous: StreamWatermark | None,
        new: StreamWatermark | None,
        applied: bool,
        reason: str | None,
        health_before: DataHealthState,
    ) -> IngestResult:
        return IngestResult(
            status=status,
            event_id=envelope.event_id,
            symbol=envelope.symbol,
            stream_kind=envelope.stream_kind,
            previous_watermark=previous,
            new_watermark=new,
            projection_applied=applied,
            reason=reason,
            health_before=health_before,
            health_after=self._health.state,
        )
