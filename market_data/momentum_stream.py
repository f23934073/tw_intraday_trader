"""Ports and lifecycle events for the market-data-only Momentum stream."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Callable, Protocol, runtime_checkable

from market_data.events import EventEnvelope, InstrumentReference


class StreamLifecycleEventType(StrEnum):
    SUBSCRIBE_ACKED = "SUBSCRIBE_ACKED"
    SUBSCRIBE_FAILED = "SUBSCRIBE_FAILED"
    SUBSCRIBE_ROLLBACK_STARTED = "SUBSCRIBE_ROLLBACK_STARTED"
    SUBSCRIBE_ROLLBACK_FAILED = "SUBSCRIBE_ROLLBACK_FAILED"
    UNSUBSCRIBE_ACKED = "UNSUBSCRIBE_ACKED"
    UNSUBSCRIBE_FAILED = "UNSUBSCRIBE_FAILED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    RECONNECTED = "RECONNECTED"


class StreamConnectionState(StrEnum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    RESYNCING = "RESYNCING"


class StreamSubscriptionAction(StrEnum):
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    ROLLBACK = "ROLLBACK"


class StreamQuotePart(StrEnum):
    TICK = "TICK"
    BIDASK = "BIDASK"

def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class StreamLifecycleEvent:
    event_type: StreamLifecycleEventType
    occurred_at: datetime
    reason: str
    symbol: str | None = None
    raw_event_code: int | None = None
    raw_info: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "lifecycle occurred_at")
        if not self.reason.strip():
            raise ValueError("lifecycle reason must not be empty")
        if self.symbol is not None:
            normalized = self.symbol.strip().upper()
            if not normalized or normalized != self.symbol:
                raise ValueError("lifecycle symbol must be normalized")


@dataclass(frozen=True)
class QualificationBootstrapEvidence:
    """Provider evidence captured before the qualification Journal boundary."""

    reference: InstrumentReference
    instrument_name: str
    security_type: str
    instrument_source_identity: str
    captured_at: datetime
    received_at: datetime
    prior_session_date: date
    previous_close: Decimal
    previous_session_volume_lots: int
    snapshot_source_identity: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "bootstrap captured_at")
        _require_aware(self.received_at, "bootstrap received_at")
        if self.captured_at > self.received_at:
            raise ValueError("bootstrap capture cannot follow receipt")
        for value, name in (
            (self.instrument_name, "instrument_name"),
            (self.security_type, "security_type"),
            (self.instrument_source_identity, "instrument_source_identity"),
            (self.snapshot_source_identity, "snapshot_source_identity"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.previous_close <= 0:
            raise ValueError("previous_close must be positive")
        if self.previous_session_volume_lots < 0:
            raise ValueError("previous_session_volume_lots must be non-negative")


MarketEventHandler = Callable[[EventEnvelope], None]
LifecycleEventHandler = Callable[[StreamLifecycleEvent], None]


@runtime_checkable
class MomentumMarketDataStream(Protocol):
    """Driven port implemented by Shioaji and deterministic test adapters."""

    def start(
        self,
        event_handler: MarketEventHandler,
        lifecycle_handler: LifecycleEventHandler,
    ) -> None:
        """Install callbacks without subscribing any symbol."""

    def instrument_reference(
        self,
        symbol: str,
        session_date: date,
    ) -> InstrumentReference:
        """Return current-session contract limits for one stock."""

    def request_subscribe(self, symbol: str) -> None:
        """Request paired common-lot Tick and BidAsk streams."""

    def request_unsubscribe(self, symbol: str) -> None:
        """Request removal of both streams for one stock."""

    def stop(self) -> None:
        """Stop producers and clear callbacks without closing shared login."""

    def close(self) -> None:
        """Release resources owned by this adapter."""
