"""Recorder port and in-memory adapter for canonical ingress evidence."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Protocol, runtime_checkable

from market_data.events import EventEnvelope
from market_data.ingestion import IngestResult
from market_data.ingress import LifecycleIngressMessage


@dataclass(frozen=True)
class RecordedMarketEvent:
    record_index: int
    envelope: EventEnvelope


@dataclass(frozen=True)
class RecordedLifecycleEvent:
    record_index: int
    message: LifecycleIngressMessage


RecordedIngress = RecordedMarketEvent | RecordedLifecycleEvent


@dataclass(frozen=True)
class RecordedDisposition:
    record_index: int
    result: IngestResult


@runtime_checkable
class MarketEventRecorder(Protocol):
    def record_market(
        self,
        *,
        record_index: int,
        envelope: EventEnvelope,
    ) -> None:
        """Persist the full envelope before semantic ingestion."""

    def record_lifecycle(
        self,
        *,
        record_index: int,
        message: LifecycleIngressMessage,
    ) -> None:
        """Persist lifecycle evidence in the same dequeue order."""

    def record_disposition(
        self,
        *,
        record_index: int,
        result: IngestResult,
    ) -> None:
        """Persist the deterministic result for one recorded market event."""


class InMemoryMarketEventRecorder:
    """Thread-safe evidence adapter used by slice tests and shadow wiring."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: list[RecordedIngress] = []
        self._dispositions: list[RecordedDisposition] = []

    def record_market(
        self,
        *,
        record_index: int,
        envelope: EventEnvelope,
    ) -> None:
        with self._lock:
            self._require_next_index(record_index)
            self._records.append(RecordedMarketEvent(record_index, envelope))

    def record_lifecycle(
        self,
        *,
        record_index: int,
        message: LifecycleIngressMessage,
    ) -> None:
        with self._lock:
            self._require_next_index(record_index)
            self._records.append(RecordedLifecycleEvent(record_index, message))

    def record_disposition(
        self,
        *,
        record_index: int,
        result: IngestResult,
    ) -> None:
        with self._lock:
            if record_index < 0 or record_index >= len(self._records):
                raise ValueError("disposition record_index has no ingress record")
            self._dispositions.append(RecordedDisposition(record_index, result))

    @property
    def records(self) -> tuple[RecordedIngress, ...]:
        with self._lock:
            return tuple(self._records)

    @property
    def market_records(self) -> tuple[RecordedMarketEvent, ...]:
        with self._lock:
            return tuple(
                item
                for item in self._records
                if isinstance(item, RecordedMarketEvent)
            )

    @property
    def lifecycle_records(self) -> tuple[RecordedLifecycleEvent, ...]:
        with self._lock:
            return tuple(
                item
                for item in self._records
                if isinstance(item, RecordedLifecycleEvent)
            )

    @property
    def disposition_records(self) -> tuple[RecordedDisposition, ...]:
        with self._lock:
            return tuple(self._dispositions)

    def _require_next_index(self, record_index: int) -> None:
        if record_index != len(self._records):
            raise ValueError(
                "recorder index must be contiguous; "
                f"expected {len(self._records)}, got {record_index}"
            )
