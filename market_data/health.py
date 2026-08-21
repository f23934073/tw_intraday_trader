"""Framework-free market-data health state and evidence counters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from threading import RLock

from market_data.events import EventEnvelope, MarketStreamKind


class DataHealthState(StrEnum):
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class DataHealthReason(StrEnum):
    OUT_OF_ORDER = "OUT_OF_ORDER"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    INVALID_EVENT = "INVALID_EVENT"
    INVALID_INSTRUMENT_REFERENCE = "INVALID_INSTRUMENT_REFERENCE"
    CUMULATIVE_VOLUME_GAP = "CUMULATIVE_VOLUME_GAP"
    QUEUE_OVERFLOW = "QUEUE_OVERFLOW"
    RECORDER_FAILURE = "RECORDER_FAILURE"
    SOURCE_CLOCK_SKEW = "SOURCE_CLOCK_SKEW"
    REQUIRED_STREAM_STALE = "REQUIRED_STREAM_STALE"
    PROVIDER_DISCONNECTED = "PROVIDER_DISCONNECTED"
    SUBSCRIPTION_STATE_UNKNOWN = "SUBSCRIPTION_STATE_UNKNOWN"


@dataclass(frozen=True)
class StreamHealth:
    symbol: str
    stream_kind: MarketStreamKind
    last_event_at: datetime | None = None
    last_received_at: datetime | None = None
    applied_count: int = 0
    duplicate_count: int = 0
    out_of_order_count: int = 0


@dataclass(frozen=True)
class DataHealthSnapshot:
    session_date: date
    state: DataHealthState
    reasons: tuple[DataHealthReason, ...]
    streams: tuple[StreamHealth, ...]
    queue_depth: int
    queue_high_watermark: int
    queue_overflow_count: int
    session_mismatch_count: int
    invalid_count: int
    gap_count: int
    source_clock_skew_count: int
    reconnect_epoch: int
    resync_verified_at: datetime | None
    as_of: datetime

    @property
    def digest(self) -> str:
        payload = {
            "session_date": self.session_date.isoformat(),
            "state": self.state.value,
            "reasons": [reason.value for reason in self.reasons],
            "streams": [
                {
                    "symbol": stream.symbol,
                    "stream_kind": stream.stream_kind.value,
                    "last_event_at": (
                        stream.last_event_at.isoformat()
                        if stream.last_event_at is not None
                        else None
                    ),
                    "last_received_at": (
                        stream.last_received_at.isoformat()
                        if stream.last_received_at is not None
                        else None
                    ),
                    "applied_count": stream.applied_count,
                    "duplicate_count": stream.duplicate_count,
                    "out_of_order_count": stream.out_of_order_count,
                }
                for stream in self.streams
            ],
            "queue_depth": self.queue_depth,
            "queue_high_watermark": self.queue_high_watermark,
            "queue_overflow_count": self.queue_overflow_count,
            "session_mismatch_count": self.session_mismatch_count,
            "invalid_count": self.invalid_count,
            "gap_count": self.gap_count,
            "source_clock_skew_count": self.source_clock_skew_count,
            "reconnect_epoch": self.reconnect_epoch,
            "resync_verified_at": (
                self.resync_verified_at.isoformat()
                if self.resync_verified_at is not None
                else None
            ),
            "as_of": self.as_of.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class DataHealth:
    """State changes require explicit evidence; new events do not auto-recover."""

    def __init__(self, session_date: date, *, started_at: datetime) -> None:
        self._require_aware(started_at)
        self._lock = RLock()
        self._session_date = session_date
        self._state = DataHealthState.STARTING
        self._reasons: set[DataHealthReason] = set()
        self._streams: dict[tuple[str, MarketStreamKind], StreamHealth] = {}
        self._queue_depth = 0
        self._queue_high_watermark = 0
        self._queue_overflow_count = 0
        self._session_mismatch_count = 0
        self._invalid_count = 0
        self._gap_count = 0
        self._source_clock_skew_count = 0
        self._reconnect_epoch = 0
        self._resync_verified_at: datetime | None = None
        self._as_of = started_at

    @property
    def state(self) -> DataHealthState:
        with self._lock:
            return self._state

    def begin_session(self, session_date: date, *, started_at: datetime) -> None:
        with self._lock:
            self.__init__(session_date, started_at=started_at)

    def mark_ready(self, *, occurred_at: datetime, evidence: str) -> None:
        with self._lock:
            self._advance_time(occurred_at)
            if not evidence.strip():
                raise ValueError("ready evidence must not be empty")
            if self._state is DataHealthState.BLOCKED:
                raise ValueError("blocked health requires verified recovery")
            self._state = DataHealthState.HEALTHY
            self._reasons.clear()
            self._resync_verified_at = occurred_at

    def record_applied(self, envelope: EventEnvelope) -> None:
        with self._lock:
            self._advance_time(envelope.received_at)
            key = (envelope.symbol, envelope.stream_kind)
            current = self._streams.get(
                key,
                StreamHealth(envelope.symbol, envelope.stream_kind),
            )
            self._streams[key] = replace(
                current,
                last_event_at=envelope.event_at,
                last_received_at=envelope.received_at,
                applied_count=current.applied_count + 1,
            )
            if envelope.received_at < envelope.event_at:
                self._source_clock_skew_count += 1
                self._degrade(DataHealthReason.SOURCE_CLOCK_SKEW)

    def record_duplicate(self, envelope: EventEnvelope) -> None:
        with self._lock:
            self._advance_time(envelope.received_at)
            key = (envelope.symbol, envelope.stream_kind)
            current = self._streams.get(
                key,
                StreamHealth(envelope.symbol, envelope.stream_kind),
            )
            self._streams[key] = replace(
                current,
                duplicate_count=current.duplicate_count + 1,
            )

    def record_out_of_order(self, envelope: EventEnvelope) -> None:
        with self._lock:
            self._advance_time(envelope.received_at)
            key = (envelope.symbol, envelope.stream_kind)
            current = self._streams.get(
                key,
                StreamHealth(envelope.symbol, envelope.stream_kind),
            )
            self._streams[key] = replace(
                current,
                out_of_order_count=current.out_of_order_count + 1,
            )
            self._degrade(DataHealthReason.OUT_OF_ORDER)

    def record_invalid(
        self,
        reason: DataHealthReason,
        *,
        occurred_at: datetime,
        blocked: bool = True,
    ) -> None:
        with self._lock:
            self._advance_time(occurred_at)
            self._invalid_count += 1
            if reason is DataHealthReason.SESSION_MISMATCH:
                self._session_mismatch_count += 1
            if reason is DataHealthReason.CUMULATIVE_VOLUME_GAP:
                self._gap_count += 1
            if blocked:
                self._block(reason)
            else:
                self._degrade(reason)

    def record_queue(
        self,
        *,
        depth: int,
        occurred_at: datetime,
        overflow: bool = False,
    ) -> None:
        self._require_aware(occurred_at)
        with self._lock:
            if depth < 0:
                raise ValueError("queue depth cannot be negative")
            self._queue_depth = depth
            self._queue_high_watermark = max(self._queue_high_watermark, depth)
            if overflow:
                self._queue_overflow_count += 1
                self._block(DataHealthReason.QUEUE_OVERFLOW)

    def mark_required_stream_stale(self, *, occurred_at: datetime) -> None:
        with self._lock:
            self._advance_time(occurred_at)
            self._block(DataHealthReason.REQUIRED_STREAM_STALE)

    def mark_provider_disconnected(self, *, occurred_at: datetime) -> None:
        """Block signals without moving consumer event time ahead of its queue."""
        self._require_aware(occurred_at)
        with self._lock:
            self._block(DataHealthReason.PROVIDER_DISCONNECTED)

    def recover(
        self,
        *,
        reconnect_epoch: int,
        occurred_at: datetime,
        evidence: str,
    ) -> None:
        with self._lock:
            self._advance_time(occurred_at)
            if reconnect_epoch <= self._reconnect_epoch:
                raise ValueError("recovery requires a newer reconnect epoch")
            if not evidence.strip():
                raise ValueError("recovery evidence must not be empty")
            self._reconnect_epoch = reconnect_epoch
            self._state = DataHealthState.HEALTHY
            self._reasons.clear()
            self._resync_verified_at = occurred_at

    def snapshot(self) -> DataHealthSnapshot:
        with self._lock:
            streams = tuple(
                self._streams[key]
                for key in sorted(
                    self._streams,
                    key=lambda value: (value[0], value[1].value),
                )
            )
            return DataHealthSnapshot(
                session_date=self._session_date,
                state=self._state,
                reasons=tuple(sorted(self._reasons, key=lambda item: item.value)),
                streams=streams,
                queue_depth=self._queue_depth,
                queue_high_watermark=self._queue_high_watermark,
                queue_overflow_count=self._queue_overflow_count,
                session_mismatch_count=self._session_mismatch_count,
                invalid_count=self._invalid_count,
                gap_count=self._gap_count,
                source_clock_skew_count=self._source_clock_skew_count,
                reconnect_epoch=self._reconnect_epoch,
                resync_verified_at=self._resync_verified_at,
                as_of=self._as_of,
            )

    def _degrade(self, reason: DataHealthReason) -> None:
        self._reasons.add(reason)
        if self._state is not DataHealthState.BLOCKED:
            self._state = DataHealthState.DEGRADED

    def _block(self, reason: DataHealthReason) -> None:
        self._reasons.add(reason)
        self._state = DataHealthState.BLOCKED

    def _advance_time(self, value: datetime) -> None:
        self._require_aware(value)
        if value < self._as_of:
            raise ValueError("DataHealth time cannot move backward")
        self._as_of = value

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("DataHealth timestamps must be timezone-aware")
