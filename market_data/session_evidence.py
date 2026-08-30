"""Immutable server-owned execution evidence; this module performs no provider calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from trading.canonical_values import canonical_decimal_string
from trading.no_overnight import NoOvernightState


SERVER_EXECUTION_EVIDENCE_SCHEMA_VERSION = "server_execution_evidence.v1"


class SessionPhase(StrEnum):
    UNKNOWN = "UNKNOWN"
    CONTINUOUS = "CONTINUOUS"
    CLOSING_AUCTION = "CLOSING_AUCTION"
    CLOSED = "CLOSED"


class InstrumentStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    TRADING = "TRADING"
    HALTED = "HALTED"


class SpecialSessionRegime(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"


class GuardHealth(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    LOST = "LOST"


def _text(value: str, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha256(value: str, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _optional_positive(value: Decimal | None, name: str) -> None:
    if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value <= 0):
        raise ValueError(f"{name} must be a positive finite Decimal or null")


@dataclass(frozen=True)
class BidAskEvidence:
    source_as_of: datetime
    received_at: datetime
    best_bid_price: Decimal | None
    best_bid_quantity: int | None
    best_ask_price: Decimal | None
    best_ask_quantity: int | None

    def __post_init__(self) -> None:
        _aware(self.source_as_of, "bid_ask.source_as_of")
        _aware(self.received_at, "bid_ask.received_at")
        if self.received_at < self.source_as_of:
            raise ValueError("bid_ask receive time precedes source time")
        _optional_positive(self.best_bid_price, "bid_ask.best_bid_price")
        _optional_positive(self.best_ask_price, "bid_ask.best_ask_price")
        for name in ("best_bid_quantity", "best_ask_quantity"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"bid_ask.{name} must be a non-negative integer or null")

    def payload(self) -> dict[str, object]:
        return {
            "source_as_of": self.source_as_of.isoformat(),
            "received_at": self.received_at.isoformat(),
            "best_bid_price": None if self.best_bid_price is None else canonical_decimal_string(self.best_bid_price),
            "best_bid_quantity": self.best_bid_quantity,
            "best_ask_price": None if self.best_ask_price is None else canonical_decimal_string(self.best_ask_price),
            "best_ask_quantity": self.best_ask_quantity,
        }


@dataclass(frozen=True)
class ServerExecutionEvidenceSnapshot:
    """One complete immutable admission input captured and owned by the server."""

    captured_at: datetime
    received_at: datetime
    calendar_schema_version: str
    calendar_digest: str
    calendar_coverage_start: date
    calendar_coverage_end: date
    session_date: date
    session_phase: SessionPhase
    symbol: str
    instrument_status: InstrumentStatus
    tradable: bool | None
    pit_reference_price: Decimal | None
    pit_lower_limit_price: Decimal | None
    pit_upper_limit_price: Decimal | None
    pit_price_as_of: datetime | None
    special_session_regime: SpecialSessionRegime
    bid_ask: BidAskEvidence | None
    executable_book_policy_id: str | None
    book_staleness_policy_id: str | None
    max_book_age_milliseconds: int | None
    isolated_auction_event_id: str | None
    isolated_auction_event_at: datetime | None
    isolated_auction_price: Decimal | None
    isolated_auction_matchable_volume: int | None
    isolated_auction_volume_unit: str | None
    isolated_auction_event_digest: str | None
    execution_policy_digest: str | None
    cost_policy_digest: str | None
    no_overnight_state: NoOvernightState
    no_overnight_revision: int
    breach_latched: bool
    guard_identity: str | None
    guard_health: GuardHealth
    schema_version: str = SERVER_EXECUTION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _aware(self.captured_at, "captured_at")
        _aware(self.received_at, "received_at")
        if self.received_at < self.captured_at:
            raise ValueError("server receive time precedes capture time")
        object.__setattr__(self, "calendar_schema_version", _text(self.calendar_schema_version, "calendar_schema_version"))
        object.__setattr__(self, "calendar_digest", _sha256(self.calendar_digest, "calendar_digest"))
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        if not self.calendar_coverage_start <= self.session_date <= self.calendar_coverage_end:
            raise ValueError("session date is outside calendar coverage")
        if not isinstance(self.session_phase, SessionPhase):
            raise ValueError("session_phase is unsupported")
        if not isinstance(self.instrument_status, InstrumentStatus):
            raise ValueError("instrument_status is unsupported")
        if self.tradable is not None and type(self.tradable) is not bool:
            raise ValueError("tradable must be a boolean or null")
        for name in ("pit_reference_price", "pit_lower_limit_price", "pit_upper_limit_price"):
            _optional_positive(getattr(self, name), name)
        if self.pit_price_as_of is not None:
            _aware(self.pit_price_as_of, "pit_price_as_of")
        if not isinstance(self.special_session_regime, SpecialSessionRegime):
            raise ValueError("special_session_regime is unsupported")
        if (self.bid_ask is None) != (self.executable_book_policy_id is None):
            raise ValueError("BidAsk evidence and executable book identity must be present together")
        book_values = (self.book_staleness_policy_id, self.max_book_age_milliseconds)
        if self.bid_ask is None and any(value is not None for value in book_values):
            raise ValueError("book age policy requires BidAsk evidence")
        if self.bid_ask is not None:
            object.__setattr__(self, "executable_book_policy_id", _text(self.executable_book_policy_id, "executable_book_policy_id"))
            object.__setattr__(self, "book_staleness_policy_id", _text(self.book_staleness_policy_id, "book_staleness_policy_id"))
            if type(self.max_book_age_milliseconds) is not int or self.max_book_age_milliseconds <= 0:
                raise ValueError("max_book_age_milliseconds must be a positive integer")
        auction_values = (
            self.isolated_auction_event_id,
            self.isolated_auction_event_at,
            self.isolated_auction_price,
            self.isolated_auction_matchable_volume,
            self.isolated_auction_volume_unit,
            self.isolated_auction_event_digest,
        )
        if any(value is not None for value in auction_values) and not all(value is not None for value in auction_values):
            raise ValueError("isolated auction evidence must be complete or absent")
        if self.isolated_auction_event_id is not None:
            _text(self.isolated_auction_event_id, "isolated_auction_event_id")
            _aware(self.isolated_auction_event_at, "isolated_auction_event_at")
            _optional_positive(self.isolated_auction_price, "isolated_auction_price")
            if type(self.isolated_auction_matchable_volume) is not int or self.isolated_auction_matchable_volume < 0:
                raise ValueError("isolated_auction_matchable_volume must be non-negative")
            _text(self.isolated_auction_volume_unit, "isolated_auction_volume_unit")
            _sha256(self.isolated_auction_event_digest, "isolated_auction_event_digest")
        for name in ("execution_policy_digest", "cost_policy_digest"):
            value = getattr(self, name)
            if value is not None:
                _sha256(value, name)
        if type(self.no_overnight_revision) is not int or self.no_overnight_revision < 0:
            raise ValueError("no_overnight_revision must be non-negative")
        if not isinstance(self.no_overnight_state, NoOvernightState):
            raise ValueError("no_overnight_state is unsupported")
        if type(self.breach_latched) is not bool:
            raise ValueError("breach_latched must be a boolean")
        if self.breach_latched != (self.no_overnight_state is NoOvernightState.OVERNIGHT_BREACH):
            raise ValueError("breach latch does not match no-overnight state")
        if self.guard_identity is not None:
            _text(self.guard_identity, "guard_identity")
        if not isinstance(self.guard_health, GuardHealth):
            raise ValueError("guard_health is unsupported")
        if self.guard_health is GuardHealth.HEALTHY and self.guard_identity is None:
            raise ValueError("healthy guard requires identity")
        if self.schema_version != SERVER_EXECUTION_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("schema_version is unsupported")

    def canonical_payload(self) -> dict[str, object]:
        def decimal(value: Decimal | None) -> str | None:
            return None if value is None else canonical_decimal_string(value)

        return {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "calendar_schema_version": self.calendar_schema_version,
            "calendar_digest": self.calendar_digest,
            "calendar_coverage_start": self.calendar_coverage_start.isoformat(),
            "calendar_coverage_end": self.calendar_coverage_end.isoformat(),
            "session_date": self.session_date.isoformat(),
            "session_phase": self.session_phase.value,
            "symbol": self.symbol,
            "instrument_status": self.instrument_status.value,
            "tradable": self.tradable,
            "pit_reference_price": decimal(self.pit_reference_price),
            "pit_lower_limit_price": decimal(self.pit_lower_limit_price),
            "pit_upper_limit_price": decimal(self.pit_upper_limit_price),
            "pit_price_as_of": None if self.pit_price_as_of is None else self.pit_price_as_of.isoformat(),
            "special_session_regime": self.special_session_regime.value,
            "bid_ask": None if self.bid_ask is None else self.bid_ask.payload(),
            "executable_book_policy_id": self.executable_book_policy_id,
            "book_staleness_policy_id": self.book_staleness_policy_id,
            "max_book_age_milliseconds": self.max_book_age_milliseconds,
            "isolated_auction_event_id": self.isolated_auction_event_id,
            "isolated_auction_event_at": None if self.isolated_auction_event_at is None else self.isolated_auction_event_at.isoformat(),
            "isolated_auction_price": decimal(self.isolated_auction_price),
            "isolated_auction_matchable_volume": self.isolated_auction_matchable_volume,
            "isolated_auction_volume_unit": self.isolated_auction_volume_unit,
            "isolated_auction_event_digest": self.isolated_auction_event_digest,
            "execution_policy_digest": self.execution_policy_digest,
            "cost_policy_digest": self.cost_policy_digest,
            "no_overnight_state": self.no_overnight_state.value,
            "no_overnight_revision": self.no_overnight_revision,
            "breach_latched": self.breach_latched,
            "guard_identity": self.guard_identity,
            "guard_health": self.guard_health.value,
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(item.name for item in fields(cls))
