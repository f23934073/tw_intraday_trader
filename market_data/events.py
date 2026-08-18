"""Normalized market-data contracts for deterministic Momentum processing.

These models preserve source time, receipt time, explicit lot units, and
current-session contract limits.  Existing snapshot and paper-simulation
models remain unchanged while later phases migrate realtime processing to
these richer events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class AggressorSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class MarketEventSource(StrEnum):
    QUOTE = "QUOTE"
    TICK = "TICK"
    BIDASK = "BIDASK"
    REPLAY = "REPLAY"


class MarketStreamKind(StrEnum):
    TICK = "TICK"
    BIDASK = "BIDASK"


class ProjectionApplyStatus(StrEnum):
    APPLIED = "APPLIED"
    APPLIED_WITH_GAP = "APPLIED_WITH_GAP"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    INVALID = "INVALID"


@dataclass(frozen=True, order=True)
class StreamWatermark:
    event_time: datetime
    ingress_sequence: int

    def __post_init__(self) -> None:
        _require_aware(self.event_time, "watermark event_time")
        if self.ingress_sequence < 0:
            raise ValueError("watermark ingress_sequence must be non-negative")


@dataclass(frozen=True)
class ProjectionApplyResult:
    status: ProjectionApplyStatus
    event_id: str
    symbol: str
    stream_kind: MarketStreamKind
    previous_watermark: StreamWatermark | None
    new_watermark: StreamWatermark | None
    reason: str | None = None

    @property
    def projection_applied(self) -> bool:
        return self.status in {
            ProjectionApplyStatus.APPLIED,
            ProjectionApplyStatus.APPLIED_WITH_GAP,
        }


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_positive(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True)
class InstrumentReference:
    symbol: str
    exchange: str
    session_date: date
    reference_price: Decimal
    limit_up_price: Decimal | None
    limit_down_price: Decimal | None
    price_limit_applies: bool
    trading_unit_shares: int
    source_updated_at: date | None

    def __post_init__(self) -> None:
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.exchange, "exchange")
        _require_positive(self.reference_price, "reference_price")
        if self.trading_unit_shares <= 0:
            raise ValueError("trading_unit_shares must be positive")
        if self.price_limit_applies:
            if self.limit_up_price is None or self.limit_down_price is None:
                raise ValueError("price-limited instruments require both limit prices")
            _require_positive(self.limit_up_price, "limit_up_price")
            _require_positive(self.limit_down_price, "limit_down_price")
            if not self.limit_down_price < self.reference_price < self.limit_up_price:
                raise ValueError("limit prices must bracket the reference price")

    @property
    def eligible_for_limit_up_momentum(self) -> bool:
        return (
            self.price_limit_applies
            and self.limit_up_price is not None
            and self.source_updated_at == self.session_date
        )


@dataclass(frozen=True)
class TickEvent:
    event_id: str
    source: MarketEventSource
    symbol: str
    session_date: date
    event_time: datetime
    received_at: datetime
    ingress_sequence: int
    price: Decimal
    tick_volume_lots: int
    total_volume_lots: int
    average_price: Decimal | None
    intraday_high: Decimal
    intraday_low: Decimal
    raw_tick_type: int
    aggressor_side: AggressorSide
    buy_aggressor_total_lots: int | None
    sell_aggressor_total_lots: int | None
    suspended: bool
    simulated_trade: bool
    intraday_odd: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.symbol, "symbol")
        _require_aware(self.event_time, "event_time")
        _require_aware(self.received_at, "received_at")
        if self.event_time.date() != self.session_date:
            raise ValueError("event_time must belong to session_date")
        if self.ingress_sequence < 0:
            raise ValueError("ingress_sequence must be non-negative")
        for value, field_name in (
            (self.price, "price"),
            (self.intraday_high, "intraday_high"),
            (self.intraday_low, "intraday_low"),
        ):
            _require_positive(value, field_name)
        if self.average_price is not None:
            _require_positive(self.average_price, "average_price")
        if self.intraday_low > self.intraday_high:
            raise ValueError("intraday_low cannot exceed intraday_high")
        if not self.intraday_low <= self.price <= self.intraday_high:
            raise ValueError("price must be within intraday low/high")
        if self.tick_volume_lots < 0 or self.total_volume_lots < 0:
            raise ValueError("lot volumes must be non-negative")
        if self.tick_volume_lots > self.total_volume_lots:
            raise ValueError("tick volume cannot exceed cumulative volume")
        for value, field_name in (
            (self.buy_aggressor_total_lots, "buy_aggressor_total_lots"),
            (self.sell_aggressor_total_lots, "sell_aggressor_total_lots"),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class BidAskEvent:
    event_id: str
    source: MarketEventSource
    symbol: str
    session_date: date
    event_time: datetime
    received_at: datetime
    ingress_sequence: int
    bid_prices: tuple[Decimal, ...]
    bid_volume_lots: tuple[int, ...]
    ask_prices: tuple[Decimal, ...]
    ask_volume_lots: tuple[int, ...]
    suspended: bool
    simulated_trade: bool
    intraday_odd: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.symbol, "symbol")
        _require_aware(self.event_time, "event_time")
        _require_aware(self.received_at, "received_at")
        if self.event_time.date() != self.session_date:
            raise ValueError("event_time must belong to session_date")
        if self.ingress_sequence < 0:
            raise ValueError("ingress_sequence must be non-negative")
        if len(self.bid_prices) != len(self.bid_volume_lots):
            raise ValueError("bid price/volume lengths must match")
        if len(self.ask_prices) != len(self.ask_volume_lots):
            raise ValueError("ask price/volume lengths must match")
        if len(self.bid_prices) > 5 or len(self.ask_prices) > 5:
            raise ValueError("book events support at most five levels per side")
        if any(price <= 0 for price in (*self.bid_prices, *self.ask_prices)):
            raise ValueError("book prices must be positive")
        if any(volume < 0 for volume in (*self.bid_volume_lots, *self.ask_volume_lots)):
            raise ValueError("book volumes must be non-negative")

    @property
    def best_bid(self) -> Decimal | None:
        return self.bid_prices[0] if self.bid_prices else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.ask_prices[0] if self.ask_prices else None

    @property
    def is_crossed(self) -> bool:
        return (
            self.best_bid is not None
            and self.best_ask is not None
            and self.best_bid > self.best_ask
        )

    @property
    def is_locked(self) -> bool:
        return (
            self.best_bid is not None
            and self.best_ask is not None
            and self.best_bid == self.best_ask
        )


MarketEventPayload = TickEvent | BidAskEvent


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    schema_version: str
    session_id: str
    session_date: date
    source: MarketEventSource
    source_mode: str
    stream_kind: MarketStreamKind
    symbol: str
    event_at: datetime
    received_at: datetime
    ingress_sequence: int
    source_identity: str
    payload: MarketEventPayload
    raw_capture_id: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.event_id, "event_id"),
            (self.schema_version, "schema_version"),
            (self.session_id, "session_id"),
            (self.source_mode, "source_mode"),
            (self.symbol, "symbol"),
            (self.source_identity, "source_identity"),
        ):
            _require_non_empty(value, name)
        _require_aware(self.event_at, "event_at")
        _require_aware(self.received_at, "received_at")
        if self.ingress_sequence < 0:
            raise ValueError("ingress_sequence must be non-negative")
        if isinstance(self.payload, TickEvent):
            expected_stream = MarketStreamKind.TICK
        elif isinstance(self.payload, BidAskEvent):
            expected_stream = MarketStreamKind.BIDASK
        else:
            raise TypeError("unsupported market event payload")
        if self.stream_kind is not expected_stream:
            raise ValueError("stream_kind does not match payload type")
        matching_fields = {
            "event_id": self.payload.event_id,
            "session_date": self.payload.session_date,
            "source": self.payload.source,
            "symbol": self.payload.symbol,
            "event_at": self.payload.event_time,
            "received_at": self.payload.received_at,
            "ingress_sequence": self.payload.ingress_sequence,
        }
        envelope_fields = {
            "event_id": self.event_id,
            "session_date": self.session_date,
            "source": self.source,
            "symbol": self.symbol,
            "event_at": self.event_at,
            "received_at": self.received_at,
            "ingress_sequence": self.ingress_sequence,
        }
        mismatches = [
            name
            for name, value in matching_fields.items()
            if envelope_fields[name] != value
        ]
        if mismatches:
            raise ValueError(
                "envelope fields do not match payload: " + ", ".join(mismatches)
            )

    @property
    def watermark(self) -> StreamWatermark:
        return StreamWatermark(self.event_at, self.ingress_sequence)
