"""Immutable provider-neutral contracts for post-close institutional flow data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class InstitutionalMarket(StrEnum):
    TWSE = "TWSE"
    TPEX = "TPEX"


class CorrectionPolicy(StrEnum):
    ORIGINAL_TRADES = "ORIGINAL_TRADES"
    CORRECTED_ACCOUNTS = "CORRECTED_ACCOUNTS"


class PartitionStatus(StrEnum):
    RAW_CAPTURED = "RAW_CAPTURED"
    NORMALIZED = "NORMALIZED"
    VALIDATED = "VALIDATED"
    QUARANTINED = "QUARANTINED"


PARTITION_STATUS_V1_VALUES = tuple(status.value for status in PartitionStatus)


class TradeCategory(StrEnum):
    REGULAR = "REGULAR"
    ODD_LOT = "ODD_LOT"
    AFTER_HOURS_FIXED_PRICE = "AFTER_HOURS_FIXED_PRICE"
    BLOCK = "BLOCK"
    AUCTION = "AUCTION"
    TENDER = "TENDER"


class ScopeCompatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    SCOPE_INCOMPATIBLE = "SCOPE_INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


def _require_int(value: object, field_name: str, *, non_negative: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if non_negative and value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_optional_component(
    values: tuple[int | None, int | None, int | None],
    field_name: str,
) -> None:
    present = tuple(value is not None for value in values)
    if any(present) and not all(present):
        raise ValueError(f"{field_name} values must be all present or all absent")
    if all(present):
        _require_int(values[0], f"{field_name}_buy_shares", non_negative=True)
        _require_int(values[1], f"{field_name}_sell_shares", non_negative=True)
        _require_int(values[2], f"{field_name}_net_shares")


@dataclass(frozen=True)
class TradeScope:
    """An exhaustive trade-category and correction-policy contract."""

    scope_id: str
    included_categories: frozenset[TradeCategory]
    excluded_categories: frozenset[TradeCategory]
    correction_policy: CorrectionPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "scope_id", _require_non_empty(self.scope_id, "scope_id")
        )
        included = frozenset(TradeCategory(value) for value in self.included_categories)
        excluded = frozenset(TradeCategory(value) for value in self.excluded_categories)
        if included & excluded:
            raise ValueError("trade scope categories must not overlap")
        if included | excluded != frozenset(TradeCategory):
            raise ValueError(
                "trade scope must classify every trade category exactly once"
            )
        object.__setattr__(self, "included_categories", included)
        object.__setattr__(self, "excluded_categories", excluded)
        object.__setattr__(
            self,
            "correction_policy",
            CorrectionPolicy(self.correction_policy),
        )


@dataclass(frozen=True)
class ScopeCompatibilityDecision:
    """Feature-level eligibility decision for one numerator/denominator pair."""

    status: ScopeCompatibility
    numerator_scope_id: str | None
    denominator_scope_id: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        status = ScopeCompatibility(self.status)
        object.__setattr__(self, "status", status)
        for field_name in ("numerator_scope_id", "denominator_scope_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_non_empty(value, field_name),
                )
        reasons = tuple(
            dict.fromkeys(code.strip() for code in self.reason_codes if code.strip())
        )
        object.__setattr__(
            self,
            "reason_codes",
            reasons,
        )
        both_scopes_present = (
            self.numerator_scope_id is not None
            and self.denominator_scope_id is not None
        )
        if status is ScopeCompatibility.COMPATIBLE and (
            not both_scopes_present or reasons
        ):
            raise ValueError(
                "compatible scope compatibility requires two scopes and no reasons"
            )
        if status is ScopeCompatibility.SCOPE_INCOMPATIBLE and (
            not both_scopes_present or not reasons
        ):
            raise ValueError(
                "incompatible scope compatibility requires two scopes and reasons"
            )
        if status is ScopeCompatibility.UNKNOWN and not reasons:
            raise ValueError("unknown scope compatibility requires a reason")


@dataclass(frozen=True)
class InstitutionalFlowDaily:
    """One normalized market/symbol/session institutional-flow observation."""

    partition_id: str
    market: InstitutionalMarket
    symbol: str
    session_date: date

    foreign_ex_dealer_buy_shares: int
    foreign_ex_dealer_sell_shares: int
    foreign_ex_dealer_net_shares: int
    foreign_dealer_buy_shares: int | None
    foreign_dealer_sell_shares: int | None
    foreign_dealer_net_shares: int | None

    investment_trust_buy_shares: int
    investment_trust_sell_shares: int
    investment_trust_net_shares: int
    dealer_proprietary_buy_shares: int | None
    dealer_proprietary_sell_shares: int | None
    dealer_proprietary_net_shares: int | None
    dealer_hedge_buy_shares: int | None
    dealer_hedge_sell_shares: int | None
    dealer_hedge_net_shares: int | None
    dealer_total_buy_shares: int
    dealer_total_sell_shares: int
    dealer_total_net_shares: int
    published_total_net_shares: int

    trade_scope_id: str
    correction_policy: CorrectionPolicy
    raw_artifact_id: str
    raw_sha256: str
    retrieved_at: datetime
    first_observed_at: datetime
    usable_from_session: date

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "partition_id",
            _require_non_empty(self.partition_id, "partition_id"),
        )
        object.__setattr__(self, "market", InstitutionalMarket(self.market))
        object.__setattr__(
            self,
            "symbol",
            _require_non_empty(self.symbol, "symbol").upper(),
        )
        object.__setattr__(
            self,
            "trade_scope_id",
            _require_non_empty(self.trade_scope_id, "trade_scope_id"),
        )
        object.__setattr__(
            self,
            "correction_policy",
            CorrectionPolicy(self.correction_policy),
        )
        object.__setattr__(
            self,
            "raw_artifact_id",
            _require_non_empty(self.raw_artifact_id, "raw_artifact_id"),
        )
        _require_sha256(self.raw_sha256, "raw_sha256")
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_aware(self.first_observed_at, "first_observed_at")
        if self.first_observed_at > self.retrieved_at:
            raise ValueError("first_observed_at cannot be after retrieved_at")
        if self.usable_from_session <= self.session_date:
            raise ValueError("usable_from_session must be after session_date")

        for field_name in (
            "foreign_ex_dealer_buy_shares",
            "foreign_ex_dealer_sell_shares",
            "investment_trust_buy_shares",
            "investment_trust_sell_shares",
            "dealer_total_buy_shares",
            "dealer_total_sell_shares",
        ):
            _require_int(getattr(self, field_name), field_name, non_negative=True)
        for field_name in (
            "foreign_ex_dealer_net_shares",
            "investment_trust_net_shares",
            "dealer_total_net_shares",
            "published_total_net_shares",
        ):
            _require_int(getattr(self, field_name), field_name)
        _require_optional_component(
            (
                self.foreign_dealer_buy_shares,
                self.foreign_dealer_sell_shares,
                self.foreign_dealer_net_shares,
            ),
            "foreign_dealer",
        )
        _require_optional_component(
            (
                self.dealer_proprietary_buy_shares,
                self.dealer_proprietary_sell_shares,
                self.dealer_proprietary_net_shares,
            ),
            "dealer_proprietary",
        )
        _require_optional_component(
            (
                self.dealer_hedge_buy_shares,
                self.dealer_hedge_sell_shares,
                self.dealer_hedge_net_shares,
            ),
            "dealer_hedge",
        )


@dataclass(frozen=True)
class InstitutionalPartitionManifest:
    """Bounded identity and integrity metadata for one normalized partition."""

    partition_id: str
    market: InstitutionalMarket
    session_date: date
    source_product: str
    trade_scope_id: str
    correction_policy: CorrectionPolicy
    response_scope_note: str
    raw_artifact_id: str
    raw_sha256: str
    normalized_sha256: str
    retrieved_at: datetime
    first_observed_at: datetime
    usable_from_session: date
    source_row_count: int
    normalized_row_count: int
    status: PartitionStatus

    def __post_init__(self) -> None:
        for field_name in (
            "partition_id",
            "source_product",
            "trade_scope_id",
            "response_scope_note",
            "raw_artifact_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "market", InstitutionalMarket(self.market))
        object.__setattr__(
            self,
            "correction_policy",
            CorrectionPolicy(self.correction_policy),
        )
        object.__setattr__(self, "status", PartitionStatus(self.status))
        _require_sha256(self.raw_sha256, "raw_sha256")
        _require_sha256(self.normalized_sha256, "normalized_sha256")
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_aware(self.first_observed_at, "first_observed_at")
        if self.first_observed_at > self.retrieved_at:
            raise ValueError("first_observed_at cannot be after retrieved_at")
        if self.usable_from_session <= self.session_date:
            raise ValueError("usable_from_session must be after session_date")
        _require_int(self.source_row_count, "source_row_count", non_negative=True)
        _require_int(
            self.normalized_row_count,
            "normalized_row_count",
            non_negative=True,
        )
