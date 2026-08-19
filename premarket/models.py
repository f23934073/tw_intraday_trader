"""Provider-neutral contracts for TAIFEX night-session evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class ContractIdentityStatus(StrEnum):
    RESOLVED_AS_OF_QUERY = "RESOLVED_AS_OF_QUERY"
    RESOLVED_HISTORICALLY = "RESOLVED_HISTORICALLY"
    UNRESOLVED = "UNRESOLVED"


class CompletenessStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ContextHealth(StrEnum):
    READY = "READY"
    PENDING = "PENDING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class QualificationStatus(StrEnum):
    CAPTURED_UNQUALIFIED = "CAPTURED_UNQUALIFIED"
    INVALID = "INVALID"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


@dataclass(frozen=True)
class SessionWindow:
    trading_date: date
    start: datetime
    end: datetime
    query_not_before: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start, "session start")
        _require_aware(self.end, "session end")
        _require_aware(self.query_not_before, "query_not_before")
        if not self.start < self.end <= self.query_not_before:
            raise ValueError("invalid TAIFEX night-session window")


@dataclass(frozen=True)
class ContractIdentity:
    status: ContractIdentityStatus
    resolution_method: str
    resolved_contract_code: str | None = None
    delivery_month: str | None = None
    last_trading_date: date | None = None

    def __post_init__(self) -> None:
        if not self.resolution_method.strip():
            raise ValueError("contract resolution method is required")
        if self.status is ContractIdentityStatus.UNRESOLVED and self.resolved_contract_code is not None:
            raise ValueError("unresolved contract identity cannot contain a contract code")
        if self.status is not ContractIdentityStatus.UNRESOLVED and not self.resolved_contract_code:
            raise ValueError("resolved contract identity requires a contract code")


@dataclass(frozen=True)
class NightBar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "bar timestamp")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("night-session OHLC must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("night-session OHLC is inconsistent")
        if self.volume < 0:
            raise ValueError("night-session volume cannot be negative")


@dataclass(frozen=True)
class HistoricalTick:
    timestamp: datetime
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "historical tick timestamp")
        if self.close <= 0:
            raise ValueError("historical tick close must be positive")
        if self.volume < 0:
            raise ValueError("historical tick volume cannot be negative")


@dataclass(frozen=True)
class SourceObservation:
    trading_date: date
    contract_identity: ContractIdentity
    bars: tuple[NightBar, ...]
    queried_at: datetime
    received_at: datetime
    provider_reference_price: Decimal | None
    provider_reference_updated_at: datetime | None
    provider_reference_source: str | None
    completeness_status: CompletenessStatus
    completeness_evidence: tuple[str, ...]
    source: str
    raw_source_digest: str
    raw_source_json: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.queried_at, "queried_at")
        _require_aware(self.received_at, "received_at")
        if self.provider_reference_updated_at is not None:
            _require_aware(self.provider_reference_updated_at, "provider_reference_updated_at")
        if self.provider_reference_price is not None and self.provider_reference_price <= 0:
            raise ValueError("provider reference price must be positive")
        if not self.source.strip():
            raise ValueError("source is required")
        if len(self.raw_source_digest) != 64:
            raise ValueError("raw source digest must be SHA256")
        if self.raw_source_json is not None:
            try:
                json.loads(self.raw_source_json)
            except json.JSONDecodeError as error:
                raise ValueError("raw source payload must be valid JSON") from error
            actual_digest = hashlib.sha256(self.raw_source_json.encode("utf-8")).hexdigest()
            if actual_digest != self.raw_source_digest:
                raise ValueError("raw source payload digest does not match")


@dataclass(frozen=True)
class RawSourceArtifact:
    schema_version: str
    source: str
    raw_source_digest: str
    captured_at: datetime
    payload_json: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        if not self.schema_version.strip() or not self.source.strip():
            raise ValueError("raw source schema and source are required")
        try:
            json.loads(self.payload_json)
        except json.JSONDecodeError as error:
            raise ValueError("raw source artifact payload must be valid JSON") from error
        actual_digest = hashlib.sha256(self.payload_json.encode("utf-8")).hexdigest()
        if actual_digest != self.raw_source_digest:
            raise ValueError("raw source artifact digest does not match payload")


@dataclass(frozen=True)
class QualificationCapture:
    trading_date: date
    contract_identity: ContractIdentity
    bars: tuple[NightBar, ...]
    ticks: tuple[HistoricalTick, ...]
    captured_at: datetime
    source: str
    raw_source_digest: str
    raw_source_json: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "qualification captured_at")
        if not self.source.strip():
            raise ValueError("qualification source is required")
        try:
            json.loads(self.raw_source_json)
        except json.JSONDecodeError as error:
            raise ValueError("qualification raw source payload must be valid JSON") from error
        actual_digest = hashlib.sha256(self.raw_source_json.encode("utf-8")).hexdigest()
        if actual_digest != self.raw_source_digest:
            raise ValueError("qualification raw source digest does not match")


@dataclass(frozen=True)
class QualificationReport:
    schema_version: str
    qualification_id: str
    qualification_digest: str
    trading_date: date
    contract_identity: ContractIdentity
    session_start: datetime
    session_end: datetime
    captured_at: datetime
    source: str
    raw_source_digest: str
    kbar_count: int
    tick_count: int
    kbar_first_at: datetime | None
    kbar_last_at: datetime | None
    tick_first_at: datetime | None
    tick_last_at: datetime | None
    field_deltas: tuple[tuple[str, Decimal], ...]
    status: QualificationStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TaifexNightContextArtifact:
    schema_version: str
    readiness_predicate_version: str
    artifact_id: str
    context_digest: str
    trading_date: date
    timezone: str
    product_root: str
    contract_alias: str
    contract_identity: ContractIdentity
    session_start: datetime
    session_end: datetime
    query_not_before: datetime
    queried_at: datetime
    received_at: datetime
    provider_reference_price: Decimal | None
    provider_reference_updated_at: datetime | None
    provider_reference_source: str | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    first_event_at: datetime
    last_event_at: datetime
    session_move_pct: Decimal
    session_range_pct: Decimal
    provider_reference_change_pct: Decimal | None
    close_location: Decimal | None
    completeness_status: CompletenessStatus
    completeness_evidence: tuple[str, ...]
    health: ContextHealth
    reasons: tuple[str, ...]
    source: str
    raw_source_digest: str


@dataclass(frozen=True)
class ReconciliationObservation:
    source: str
    raw_source_digest: str
    taifex_trading_date: date
    contract_code: str
    reconciled_at: datetime
    taifex_settlement_price: Decimal | None = None
    taifex_open: Decimal | None = None
    taifex_high: Decimal | None = None
    taifex_low: Decimal | None = None
    taifex_close: Decimal | None = None
    taifex_volume: int | None = None
    taifex_delivery_month: str | None = None
    taifex_volume_basis: str | None = None
    comparable_fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")
    comparison_limitations: tuple[str, ...] = ()
    raw_source_json: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.reconciled_at, "reconciled_at")
        if not self.source.strip() or not self.contract_code.strip():
            raise ValueError("reconciliation source and contract code are required")
        if len(self.raw_source_digest) != 64:
            raise ValueError("reconciliation raw source digest must be SHA256")
        if self.raw_source_json is not None:
            try:
                json.loads(self.raw_source_json)
            except json.JSONDecodeError as error:
                raise ValueError("reconciliation raw source payload must be valid JSON") from error
            actual_digest = hashlib.sha256(self.raw_source_json.encode("utf-8")).hexdigest()
            if actual_digest != self.raw_source_digest:
                raise ValueError("reconciliation raw source payload digest does not match")
        prices = (
            self.taifex_settlement_price,
            self.taifex_open,
            self.taifex_high,
            self.taifex_low,
            self.taifex_close,
        )
        if any(value is not None and value <= 0 for value in prices):
            raise ValueError("TAIFEX reconciliation prices must be positive")
        if self.taifex_volume is not None and self.taifex_volume < 0:
            raise ValueError("TAIFEX reconciliation volume cannot be negative")
        if self.taifex_delivery_month is not None and (
            len(self.taifex_delivery_month) != 6
            or not self.taifex_delivery_month.isdigit()
        ):
            raise ValueError("TAIFEX delivery month must be YYYYMM")
        if self.taifex_volume_basis is not None and not self.taifex_volume_basis.strip():
            raise ValueError("TAIFEX volume basis cannot be blank")
        allowed_fields = {"open", "high", "low", "close", "volume"}
        if (
            not self.comparable_fields
            or len(set(self.comparable_fields)) != len(self.comparable_fields)
            or any(field not in allowed_fields for field in self.comparable_fields)
        ):
            raise ValueError("reconciliation comparable fields are invalid")
        if (
            len(set(self.comparison_limitations)) != len(self.comparison_limitations)
            or any(not reason.strip() for reason in self.comparison_limitations)
        ):
            raise ValueError("reconciliation comparison limitations are invalid")


@dataclass(frozen=True)
class TaifexNightReconciliationArtifact:
    schema_version: str
    reconciliation_id: str
    reconciliation_digest: str
    context_artifact_id: str
    context_digest: str
    source: str
    raw_source_digest: str
    taifex_trading_date: date
    contract_code: str
    taifex_settlement_price: Decimal | None
    taifex_open: Decimal | None
    taifex_high: Decimal | None
    taifex_low: Decimal | None
    taifex_close: Decimal | None
    taifex_volume: int | None
    taifex_delivery_month: str | None
    taifex_volume_basis: str | None
    comparable_fields: tuple[str, ...]
    comparison_limitations: tuple[str, ...]
    field_deltas: tuple[tuple[str, Decimal], ...]
    status: ReconciliationStatus
    reasons: tuple[str, ...]
    reconciled_at: datetime
