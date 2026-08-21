"""Shared bounded ingress with atomic sequence allocation and explicit gates."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from threading import Condition, RLock
from time import monotonic
from typing import Callable

from market_data.events import EventEnvelope
from market_data.health import DataHealth


class AdmissionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_OVERFLOW = "REJECTED_OVERFLOW"
    REJECTED_CLOSED = "REJECTED_CLOSED"
    REJECTED_CONTROL_TIMEOUT = "REJECTED_CONTROL_TIMEOUT"


@dataclass(frozen=True)
class LifecycleIngressMessage:
    event_id: str
    session_id: str
    event_type: str
    occurred_at: datetime
    ingress_sequence: int
    source_identity: str
    reason: str
    symbol: str | None = None
    raw_event_code: int | None = None
    raw_info: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.event_id, "event_id"),
            (self.session_id, "session_id"),
            (self.event_type, "event_type"),
            (self.source_identity, "source_identity"),
            (self.reason, "reason"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("lifecycle occurred_at must be timezone-aware")
        if self.ingress_sequence < 0:
            raise ValueError("lifecycle ingress_sequence must be non-negative")
        if self.symbol is not None:
            normalized = self.symbol.strip().upper()
            if not normalized or normalized != self.symbol:
                raise ValueError("lifecycle symbol must be normalized")


IngressMessage = EventEnvelope | LifecycleIngressMessage
MarketMessageFactory = Callable[[int], EventEnvelope]
LifecycleMessageFactory = Callable[[int], LifecycleIngressMessage]


@dataclass(frozen=True)
class OverflowIncident:
    status: AdmissionStatus
    message_class: str
    event_id: str
    source_identity: str
    ingress_sequence: int
    occurred_at: datetime
    queue_depth: int
    capacity: int


@dataclass(frozen=True)
class AdmissionResult:
    status: AdmissionStatus
    ingress_sequence: int
    message: IngressMessage
    incident: OverflowIncident | None = None

    @property
    def accepted(self) -> bool:
        return self.status is AdmissionStatus.ACCEPTED


@dataclass(frozen=True)
class IngressQueueSnapshot:
    capacity: int
    control_reserve: int
    queue_depth: int
    market_depth: int
    market_admission_open: bool
    control_admission_open: bool
    accepted_count: int
    rejected_overflow_count: int
    rejected_closed_count: int
    control_timeout_count: int
    last_sequence: int
    incidents: tuple[OverflowIncident, ...]


class BoundedIngressQueue:
    """One FIFO with a market limit and capacity reserved for control evidence."""

    def __init__(
        self,
        *,
        capacity: int,
        control_reserve: int,
        health: DataHealth,
    ) -> None:
        if capacity <= 1:
            raise ValueError("ingress capacity must be greater than one")
        if control_reserve <= 0 or control_reserve >= capacity:
            raise ValueError("control_reserve must be between zero and capacity")
        self._capacity = capacity
        self._control_reserve = control_reserve
        self._market_capacity = capacity - control_reserve
        self._health = health
        self._messages: deque[IngressMessage] = deque()
        self._market_depth = 0
        self._condition = Condition(RLock())
        self._last_sequence = 0
        self._market_admission_open = True
        self._control_admission_open = True
        self._accepted_count = 0
        self._rejected_overflow_count = 0
        self._rejected_closed_count = 0
        self._control_timeout_count = 0
        self._incidents: list[OverflowIncident] = []

    def admit_market(self, factory: MarketMessageFactory) -> AdmissionResult:
        with self._condition:
            sequence = self._allocate_sequence()
            envelope = factory(sequence)
            self._require_sequence(envelope, sequence)
            if not self._market_admission_open:
                self._rejected_closed_count += 1
                return AdmissionResult(
                    AdmissionStatus.REJECTED_CLOSED,
                    sequence,
                    envelope,
                )
            if (
                self._market_depth >= self._market_capacity
                or len(self._messages) >= self._capacity
            ):
                self._market_admission_open = False
                self._rejected_overflow_count += 1
                incident = self._incident(
                    AdmissionStatus.REJECTED_OVERFLOW,
                    envelope,
                    "MARKET",
                )
                self._incidents.append(incident)
                self._health.record_queue(
                    depth=len(self._messages),
                    occurred_at=envelope.received_at,
                    overflow=True,
                )
                return AdmissionResult(
                    AdmissionStatus.REJECTED_OVERFLOW,
                    sequence,
                    envelope,
                    incident,
                )
            self._messages.append(envelope)
            self._market_depth += 1
            self._accepted_count += 1
            self._record_depth(envelope.received_at)
            return AdmissionResult(AdmissionStatus.ACCEPTED, sequence, envelope)

    def admit_lifecycle(
        self,
        factory: LifecycleMessageFactory,
        *,
        timeout: float = 0,
    ) -> AdmissionResult:
        if timeout < 0:
            raise ValueError("control admission timeout must be non-negative")
        deadline = monotonic() + timeout
        with self._condition:
            while (
                self._control_admission_open
                and len(self._messages) >= self._capacity
            ):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    sequence = self._allocate_sequence()
                    message = factory(sequence)
                    self._require_sequence(message, sequence)
                    self._market_admission_open = False
                    self._control_admission_open = False
                    self._control_timeout_count += 1
                    incident = self._incident(
                        AdmissionStatus.REJECTED_CONTROL_TIMEOUT,
                        message,
                        "LIFECYCLE",
                    )
                    self._incidents.append(incident)
                    self._health.record_queue(
                        depth=len(self._messages),
                        occurred_at=message.occurred_at,
                        overflow=True,
                    )
                    return AdmissionResult(
                        AdmissionStatus.REJECTED_CONTROL_TIMEOUT,
                        sequence,
                        message,
                        incident,
                    )
                self._condition.wait(remaining)
            sequence = self._allocate_sequence()
            message = factory(sequence)
            self._require_sequence(message, sequence)
            if not self._control_admission_open:
                self._rejected_closed_count += 1
                return AdmissionResult(
                    AdmissionStatus.REJECTED_CLOSED,
                    sequence,
                    message,
                )
            self._messages.append(message)
            self._accepted_count += 1
            self._record_depth(message.occurred_at)
            return AdmissionResult(AdmissionStatus.ACCEPTED, sequence, message)

    def get(self, *, occurred_at: datetime) -> IngressMessage | None:
        with self._condition:
            message = self._messages.popleft() if self._messages else None
            if isinstance(message, EventEnvelope):
                self._market_depth -= 1
            self._record_depth(occurred_at)
            if message is not None:
                self._condition.notify_all()
            return message

    def drain(self, *, occurred_at: datetime) -> tuple[IngressMessage, ...]:
        with self._condition:
            messages = tuple(self._messages)
            self._messages.clear()
            self._market_depth = 0
            self._record_depth(occurred_at)
            self._condition.notify_all()
            return messages

    def close_market_admission(self) -> None:
        with self._condition:
            self._market_admission_open = False

    def close_all_admission(self) -> None:
        with self._condition:
            self._market_admission_open = False
            self._control_admission_open = False
            self._condition.notify_all()

    def snapshot(self) -> IngressQueueSnapshot:
        with self._condition:
            return IngressQueueSnapshot(
                capacity=self._capacity,
                control_reserve=self._control_reserve,
                queue_depth=len(self._messages),
                market_depth=self._market_depth,
                market_admission_open=self._market_admission_open,
                control_admission_open=self._control_admission_open,
                accepted_count=self._accepted_count,
                rejected_overflow_count=self._rejected_overflow_count,
                rejected_closed_count=self._rejected_closed_count,
                control_timeout_count=self._control_timeout_count,
                last_sequence=self._last_sequence,
                incidents=tuple(self._incidents),
            )

    def __len__(self) -> int:
        with self._condition:
            return len(self._messages)

    def _allocate_sequence(self) -> int:
        self._last_sequence += 1
        return self._last_sequence

    @staticmethod
    def _require_sequence(message: IngressMessage, expected: int) -> None:
        if message.ingress_sequence != expected:
            raise ValueError(
                "ingress factory must use the allocated sequence "
                f"{expected}; got {message.ingress_sequence}"
            )

    def _record_depth(self, occurred_at: datetime) -> None:
        self._health.record_queue(
            depth=len(self._messages),
            occurred_at=occurred_at,
        )

    def _incident(
        self,
        status: AdmissionStatus,
        message: IngressMessage,
        message_class: str,
    ) -> OverflowIncident:
        occurred_at = (
            message.received_at
            if isinstance(message, EventEnvelope)
            else message.occurred_at
        )
        return OverflowIncident(
            status=status,
            message_class=message_class,
            event_id=message.event_id,
            source_identity=message.source_identity,
            ingress_sequence=message.ingress_sequence,
            occurred_at=occurred_at,
            queue_depth=len(self._messages),
            capacity=self._capacity,
        )
