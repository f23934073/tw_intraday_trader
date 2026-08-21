"""Immutable Trade Management contracts for PR-TM-001.

This module freezes identities, timestamps, lifecycle states, thesis metadata,
exit provenance, and Replay verification metadata.  It deliberately contains
no monitor, order routing, risk-gate, Journal, or broker behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from zoneinfo import ZoneInfo

from trading.canonical_values import canonical_decimal_string


TRADE_MANAGEMENT_SCHEMA_VERSION = "trade-management-v1"
TRADE_MANAGEMENT_SERIALIZER_VERSION = "trade-management-json-v1"
TRADE_MANAGEMENT_ID_VERSION = "trade-management-id-v1"
LIVE_ENTRY_DECISION_BUILDER_VERSION = "live-entry-decision-builder-v1"
TRADE_TIMEZONE = "Asia/Taipei"
TAIPEI = ZoneInfo(TRADE_TIMEZONE)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_schema(value: str) -> None:
    if value != TRADE_MANAGEMENT_SCHEMA_VERSION:
        raise ValueError(f"unsupported trade management schema: {value}")


def _require_finite_decimal(value: Decimal, field_name: str) -> None:
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _require_sha256(value: str, field_name: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _require_unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _derive_id(prefix: str, *parts: str) -> str:
    for index, part in enumerate(parts):
        _require_non_empty(part, f"identity part {index}")
    canonical = json.dumps(
        [TRADE_MANAGEMENT_ID_VERSION, *parts],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"{prefix}_{digest}"


def build_thesis_id(
    session_id: str,
    decision_id: str,
    thesis_type: "ThesisType",
    thesis_version: str,
) -> str:
    """Return the retry-stable identity for one thesis draft."""

    return _derive_id(
        "thesis_v1",
        session_id,
        decision_id,
        thesis_type.value,
        thesis_version,
    )


def build_trade_id(session_id: str, opening_fill_id: str) -> str:
    """Return the identity created by the first non-zero opening fill."""

    return _derive_id("trade_v1", session_id, opening_fill_id)


def build_exit_decision_id(
    session_id: str,
    trade_id: str,
    source_event_id: str,
    exit_policy_version: str,
    evaluation_digest: str,
) -> str:
    """Return a per-event exit-decision identity."""

    _require_sha256(evaluation_digest, "evaluation_digest")
    return _derive_id(
        "exit_decision_v1",
        session_id,
        trade_id,
        source_event_id,
        exit_policy_version,
        evaluation_digest,
    )


def build_exit_recommendation_id(
    session_id: str,
    trade_id: str,
    exit_policy_version: str,
) -> str:
    """Return the sole liquidation-cycle recommendation identity for a trade."""

    return _derive_id(
        "exit_recommendation_v1",
        session_id,
        trade_id,
        exit_policy_version,
        "liquidation-cycle-1",
    )


class TimestampRole(StrEnum):
    MARKET_EVENT = "MARKET_EVENT"
    SIGNAL = "SIGNAL"
    DECISION = "DECISION"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    FILL = "FILL"
    EXIT_DECISION = "EXIT_DECISION"


class TimestampSource(StrEnum):
    CANONICAL_MARKET_EVENT = "CANONICAL_MARKET_EVENT"
    STRATEGY_RUNTIME = "STRATEGY_RUNTIME"
    SIMULATION_CLOCK = "SIMULATION_CLOCK"
    BROKER_EVENT = "BROKER_EVENT"


class TimestampPrecision(StrEnum):
    MICROSECOND = "MICROSECOND"


_ALLOWED_TIMESTAMP_SOURCES = {
    TimestampRole.MARKET_EVENT: frozenset(
        {TimestampSource.CANONICAL_MARKET_EVENT}
    ),
    TimestampRole.SIGNAL: frozenset(
        {
            TimestampSource.CANONICAL_MARKET_EVENT,
            TimestampSource.STRATEGY_RUNTIME,
            TimestampSource.SIMULATION_CLOCK,
        }
    ),
    TimestampRole.DECISION: frozenset(
        {
            TimestampSource.STRATEGY_RUNTIME,
            TimestampSource.SIMULATION_CLOCK,
        }
    ),
    TimestampRole.ORDER_SUBMITTED: frozenset(
        {
            TimestampSource.STRATEGY_RUNTIME,
            TimestampSource.SIMULATION_CLOCK,
            TimestampSource.BROKER_EVENT,
        }
    ),
    TimestampRole.FILL: frozenset(
        {
            TimestampSource.CANONICAL_MARKET_EVENT,
            TimestampSource.SIMULATION_CLOCK,
            TimestampSource.BROKER_EVENT,
        }
    ),
    TimestampRole.EXIT_DECISION: frozenset(
        {
            TimestampSource.STRATEGY_RUNTIME,
            TimestampSource.SIMULATION_CLOCK,
        }
    ),
}


@dataclass(frozen=True)
class TradeTimestamp:
    role: TimestampRole
    value: datetime
    source: TimestampSource
    source_identity: str
    precision: TimestampPrecision = TimestampPrecision.MICROSECOND

    def __post_init__(self) -> None:
        if self.value.tzinfo is None or self.value.utcoffset() is None:
            raise ValueError("timestamp value must be timezone-aware")
        if getattr(self.value.tzinfo, "key", None) != TRADE_TIMEZONE:
            raise ValueError(f"timestamp value must use {TRADE_TIMEZONE}")
        _require_non_empty(self.source_identity, "source_identity")
        if self.source not in _ALLOWED_TIMESTAMP_SOURCES[self.role]:
            raise ValueError(
                f"timestamp source {self.source.value} is invalid for {self.role.value}"
            )

    @property
    def isoformat(self) -> str:
        return self.value.isoformat(timespec="microseconds")


class ThesisType(StrEnum):
    ORB_BREAKOUT = "ORB_BREAKOUT"


class ThesisStatus(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TradeSide(StrEnum):
    LONG = "LONG"


class EntryEvidenceStatus(StrEnum):
    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EvidenceValueKind(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    NULL = "NULL"


@dataclass(frozen=True)
class EvidenceValue:
    name: str
    kind: EvidenceValueKind
    value: str | None

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "evidence value name")
        if self.kind is EvidenceValueKind.NULL:
            if self.value is not None:
                raise ValueError("NULL evidence value must be null")
            return
        if self.value is None:
            raise ValueError("non-NULL evidence value must not be null")
        if self.kind is EvidenceValueKind.DECIMAL:
            try:
                decimal_value = Decimal(self.value)
            except InvalidOperation as error:
                raise ValueError("DECIMAL evidence value must be numeric") from error
            _require_finite_decimal(decimal_value, "evidence decimal")
            if canonical_decimal_string(decimal_value) != self.value:
                raise ValueError(
                    "DECIMAL evidence value must use canonical notation"
                )
        elif self.kind is EvidenceValueKind.INTEGER:
            try:
                integer_value = int(self.value)
            except ValueError as error:
                raise ValueError("INTEGER evidence value must be integral") from error
            if str(integer_value) != self.value:
                raise ValueError("INTEGER evidence value must use canonical notation")
        elif self.kind is EvidenceValueKind.BOOLEAN and self.value not in {
            "true",
            "false",
        }:
            raise ValueError("BOOLEAN evidence value must be true or false")


@dataclass(frozen=True)
class EntryEvidence:
    evidence_id: str
    kind: str
    source_component: str
    source_version: str
    status: EntryEvidenceStatus
    observed: tuple[EvidenceValue, ...]
    threshold: tuple[EvidenceValue, ...]
    market_event_id: str
    observed_at: TradeTimestamp

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.evidence_id, "evidence_id"),
            (self.kind, "entry evidence kind"),
            (self.source_component, "source_component"),
            (self.source_version, "source_version"),
            (self.market_event_id, "market_event_id"),
        ):
            _require_non_empty(value, field_name)
        for values, field_name in (
            (self.observed, "observed"),
            (self.threshold, "threshold"),
        ):
            names = tuple(item.name for item in values)
            _require_unique_strings(names, field_name)
        if self.observed_at.role not in {
            TimestampRole.MARKET_EVENT,
            TimestampRole.SIGNAL,
        }:
            raise ValueError("observed_at must be a market-event or signal timestamp")


def build_live_entry_decision_input_digest(
    *,
    builder_version: str,
    session_id: str,
    symbol: str,
    side: TradeSide,
    strategy_id: str,
    strategy_version: str,
    signal_at: TradeTimestamp,
    decided_at: TradeTimestamp,
    score: Decimal,
    matched_rules: tuple[str, ...],
    market_context_digest: str,
    entry_evidence: tuple[EntryEvidence, ...],
) -> str:
    def timestamp(value: TradeTimestamp) -> dict[str, str]:
        return {
            "role": value.role.value,
            "value": value.isoformat,
            "source": value.source.value,
            "source_identity": value.source_identity,
            "precision": value.precision.value,
        }

    def evidence_value(value: EvidenceValue) -> dict[str, str | None]:
        return {
            "name": value.name,
            "kind": value.kind.value,
            "value": value.value,
        }

    payload = {
        "contract": "live-entry-decision-v1",
        "builder_version": builder_version,
        "session_id": session_id,
        "symbol": symbol,
        "side": side.value,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "signal_at": timestamp(signal_at),
        "decided_at": timestamp(decided_at),
        "score": canonical_decimal_string(score),
        "matched_rules": list(matched_rules),
        "market_context_digest": market_context_digest,
        "entry_evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "source_component": item.source_component,
                "source_version": item.source_version,
                "status": item.status.value,
                "observed": [evidence_value(value) for value in item.observed],
                "threshold": [evidence_value(value) for value in item.threshold],
                "market_event_id": item.market_event_id,
                "observed_at": timestamp(item.observed_at),
            }
            for item in entry_evidence
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def build_live_entry_decision_id(input_digest: str) -> str:
    """Return the content-bound identity for one live entry intent."""

    _require_sha256(input_digest, "entry decision input_digest")
    return _derive_id("entry_decision_v1", input_digest)


@dataclass(frozen=True)
class LiveEntryDecision:
    decision_id: str
    builder_version: str
    session_id: str
    symbol: str
    side: TradeSide
    strategy_id: str
    strategy_version: str
    signal_at: TradeTimestamp
    decided_at: TradeTimestamp
    score: Decimal
    matched_rules: tuple[str, ...]
    market_context_digest: str
    entry_evidence: tuple[EntryEvidence, ...]
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.builder_version != LIVE_ENTRY_DECISION_BUILDER_VERSION:
            raise ValueError("unsupported live EntryDecision builder version")
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.symbol, "symbol"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
        ):
            _require_non_empty(value, field_name)
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        if self.signal_at.role is not TimestampRole.SIGNAL:
            raise ValueError("signal_at must use the SIGNAL role")
        if self.decided_at.role is not TimestampRole.DECISION:
            raise ValueError("decided_at must use the DECISION role")
        if self.decided_at.value < self.signal_at.value:
            raise ValueError("entry decision cannot predate signal")
        _require_finite_decimal(self.score, "entry score")
        if self.score < 0:
            raise ValueError("entry score must not be negative")
        if not self.matched_rules:
            raise ValueError("matched_rules must not be empty")
        for rule in self.matched_rules:
            _require_non_empty(rule, "matched rule")
        _require_unique_strings(self.matched_rules, "matched_rules")
        if self.matched_rules != tuple(sorted(self.matched_rules)):
            raise ValueError("matched_rules must use canonical order")
        _require_sha256(self.market_context_digest, "market_context_digest")
        if not self.entry_evidence:
            raise ValueError("entry_evidence must not be empty")
        evidence_ids = tuple(item.evidence_id for item in self.entry_evidence)
        _require_unique_strings(evidence_ids, "entry evidence ids")
        if evidence_ids != tuple(sorted(evidence_ids)):
            raise ValueError("entry_evidence must use canonical order")
        if any(
            item.source_version != self.strategy_version
            for item in self.entry_evidence
        ):
            raise ValueError("entry evidence version must match strategy_version")
        if any(item.observed_at.value > self.decided_at.value for item in self.entry_evidence):
            raise ValueError("entry evidence cannot postdate decision")
        if self.decision_id != build_live_entry_decision_id(self.input_digest):
            raise ValueError("decision_id does not match deterministic content")

    @property
    def input_digest(self) -> str:
        return build_live_entry_decision_input_digest(
            builder_version=self.builder_version,
            session_id=self.session_id,
            symbol=self.symbol,
            side=self.side,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            signal_at=self.signal_at,
            decided_at=self.decided_at,
            score=self.score,
            matched_rules=self.matched_rules,
            market_context_digest=self.market_context_digest,
            entry_evidence=self.entry_evidence,
        )


class CompletionPolicy(StrEnum):
    ALL = "ALL"


class ComparisonOperator(StrEnum):
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"


class ExpectedConditionKind(StrEnum):
    NEW_HIGH_EXTENSION = "NEW_HIGH_EXTENSION"
    POST_ENTRY_VOLUME_EXPANSION = "POST_ENTRY_VOLUME_EXPANSION"
    HOLD_ABOVE_VWAP = "HOLD_ABOVE_VWAP"


class InvalidConditionKind(StrEnum):
    BREAKOUT_LEVEL_LOST = "BREAKOUT_LEVEL_LOST"
    VWAP_CONFIRMATION_LOST = "VWAP_CONFIRMATION_LOST"
    SESSION_DATA_BLOCKED = "SESSION_DATA_BLOCKED"


class PriceReference(StrEnum):
    ENTRY_REFERENCE_PRICE = "ENTRY_REFERENCE_PRICE"
    BREAKOUT_LEVEL = "BREAKOUT_LEVEL"


class VolumeBaselineKind(StrEnum):
    OPENING_RANGE_MEDIAN = "OPENING_RANGE_MEDIAN"
    HISTORICAL_SAME_TIME_MEDIAN = "HISTORICAL_SAME_TIME_MEDIAN"
    FROZEN_PRECOMPUTED = "FROZEN_PRECOMPUTED"


class VolumeUnit(StrEnum):
    SHARES = "SHARES"


@dataclass(frozen=True)
class NewHighExtensionSpec:
    reference: PriceReference
    buffer: Decimal
    comparison: ComparisonOperator = ComparisonOperator.GREATER_THAN
    kind: ExpectedConditionKind = field(
        default=ExpectedConditionKind.NEW_HIGH_EXTENSION,
        init=False,
    )

    def __post_init__(self) -> None:
        _require_finite_decimal(self.buffer, "new-high buffer")
        if self.buffer < 0:
            raise ValueError("new-high buffer must not be negative")
        if self.comparison is not ComparisonOperator.GREATER_THAN:
            raise ValueError("new-high extension must use strict greater-than")


@dataclass(frozen=True)
class PostEntryVolumeExpansionSpec:
    baseline_kind: VolumeBaselineKind
    ratio: Decimal
    minimum_samples: int
    volume_unit: VolumeUnit = VolumeUnit.SHARES
    comparison: ComparisonOperator = ComparisonOperator.GREATER_THAN_OR_EQUAL
    kind: ExpectedConditionKind = field(
        default=ExpectedConditionKind.POST_ENTRY_VOLUME_EXPANSION,
        init=False,
    )

    def __post_init__(self) -> None:
        _require_finite_decimal(self.ratio, "volume expansion ratio")
        if self.ratio <= 0:
            raise ValueError("volume expansion ratio must be positive")
        if self.minimum_samples <= 0:
            raise ValueError("volume minimum_samples must be positive")
        if self.comparison is not ComparisonOperator.GREATER_THAN_OR_EQUAL:
            raise ValueError("volume expansion must use greater-than-or-equal")


@dataclass(frozen=True)
class HoldAboveVwapSpec:
    allowed_completed_bars_below: int
    comparison: ComparisonOperator = ComparisonOperator.GREATER_THAN_OR_EQUAL
    kind: ExpectedConditionKind = field(
        default=ExpectedConditionKind.HOLD_ABOVE_VWAP,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.allowed_completed_bars_below < 0:
            raise ValueError("allowed_completed_bars_below must not be negative")
        if self.comparison is not ComparisonOperator.GREATER_THAN_OR_EQUAL:
            raise ValueError("VWAP hold must use greater-than-or-equal")


ExpectedConditionSpec = (
    NewHighExtensionSpec
    | PostEntryVolumeExpansionSpec
    | HoldAboveVwapSpec
)


@dataclass(frozen=True)
class BreakoutLevelLostSpec:
    breakout_level: Decimal
    confirmation_completed_bars: int = 1
    comparison: ComparisonOperator = ComparisonOperator.LESS_THAN
    kind: InvalidConditionKind = field(
        default=InvalidConditionKind.BREAKOUT_LEVEL_LOST,
        init=False,
    )

    def __post_init__(self) -> None:
        _require_finite_decimal(self.breakout_level, "breakout_level")
        if self.breakout_level <= 0:
            raise ValueError("breakout_level must be positive")
        if self.confirmation_completed_bars <= 0:
            raise ValueError("breakout confirmation must be positive")
        if self.comparison is not ComparisonOperator.LESS_THAN:
            raise ValueError("breakout loss must use strict less-than")


@dataclass(frozen=True)
class VwapConfirmationLostSpec:
    confirmation_completed_bars: int = 1
    comparison: ComparisonOperator = ComparisonOperator.LESS_THAN
    kind: InvalidConditionKind = field(
        default=InvalidConditionKind.VWAP_CONFIRMATION_LOST,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.confirmation_completed_bars <= 0:
            raise ValueError("VWAP confirmation must be positive")
        if self.comparison is not ComparisonOperator.LESS_THAN:
            raise ValueError("VWAP loss must use strict less-than")


@dataclass(frozen=True)
class SessionDataBlockedSpec:
    blocked_health_states: tuple[str, ...] = ("BLOCKED",)
    block_on_session_mismatch: bool = True
    kind: InvalidConditionKind = field(
        default=InvalidConditionKind.SESSION_DATA_BLOCKED,
        init=False,
    )

    def __post_init__(self) -> None:
        if not self.blocked_health_states:
            raise ValueError("blocked_health_states must not be empty")
        for state in self.blocked_health_states:
            _require_non_empty(state, "blocked health state")
        _require_unique_strings(self.blocked_health_states, "blocked_health_states")


InvalidConditionSpec = (
    BreakoutLevelLostSpec
    | VwapConfirmationLostSpec
    | SessionDataBlockedSpec
)


@dataclass(frozen=True)
class ExpectedBehaviorPolicy:
    policy_id: str
    version: str
    observation_window: timedelta
    warning_after: timedelta | None
    completion_policy: CompletionPolicy
    conditions: tuple[ExpectedConditionSpec, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.version, "expected behavior version")
        if self.observation_window <= timedelta(0):
            raise ValueError("observation_window must be positive")
        if self.warning_after is not None and not (
            timedelta(0) <= self.warning_after < self.observation_window
        ):
            raise ValueError("warning_after must be within observation_window")
        kinds = tuple(condition.kind.value for condition in self.conditions)
        if not kinds:
            raise ValueError("expected behavior conditions must not be empty")
        _require_unique_strings(kinds, "expected behavior condition kinds")


_ORB_EXPECTED_CONDITION_ORDER = (
    ExpectedConditionKind.NEW_HIGH_EXTENSION,
    ExpectedConditionKind.POST_ENTRY_VOLUME_EXPANSION,
    ExpectedConditionKind.HOLD_ABOVE_VWAP,
)
_ORB_INVALID_CONDITION_ORDER = (
    InvalidConditionKind.BREAKOUT_LEVEL_LOST,
    InvalidConditionKind.VWAP_CONFIRMATION_LOST,
    InvalidConditionKind.SESSION_DATA_BLOCKED,
)


@dataclass(frozen=True)
class TradeThesisDraft:
    thesis_id: str
    session_id: str
    symbol: str
    side: TradeSide
    strategy_id: str
    strategy_version: str
    thesis_type: ThesisType
    thesis_version: str
    decision_id: str
    signal_at: TradeTimestamp
    created_at: TradeTimestamp
    entry_evidence: tuple[EntryEvidence, ...]
    expected_behavior: ExpectedBehaviorPolicy
    invalid_conditions: tuple[InvalidConditionSpec, ...]
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.symbol, "symbol"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.thesis_version, "thesis_version"),
            (self.decision_id, "decision_id"),
        ):
            _require_non_empty(value, field_name)
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        expected_thesis_id = build_thesis_id(
            self.session_id,
            self.decision_id,
            self.thesis_type,
            self.thesis_version,
        )
        if self.thesis_id != expected_thesis_id:
            raise ValueError("thesis_id does not match deterministic identity")
        if self.signal_at.role is not TimestampRole.SIGNAL:
            raise ValueError("signal_at must use the SIGNAL role")
        if self.created_at.role is not TimestampRole.DECISION:
            raise ValueError("created_at must use the DECISION role")
        if self.created_at.value < self.signal_at.value:
            raise ValueError("created_at cannot predate signal_at")
        if not self.entry_evidence:
            raise ValueError("entry_evidence must not be empty")
        evidence_ids = tuple(item.evidence_id for item in self.entry_evidence)
        _require_unique_strings(evidence_ids, "entry evidence ids")
        if any(item.observed_at.value > self.created_at.value for item in self.entry_evidence):
            raise ValueError("entry evidence cannot postdate thesis creation")
        if self.expected_behavior.version != self.thesis_version:
            raise ValueError("expected behavior version must match thesis_version")
        expected_kinds = tuple(
            condition.kind for condition in self.expected_behavior.conditions
        )
        invalid_kinds = tuple(
            condition.kind for condition in self.invalid_conditions
        )
        if self.thesis_type is ThesisType.ORB_BREAKOUT:
            if expected_kinds != _ORB_EXPECTED_CONDITION_ORDER:
                raise ValueError(
                    "ORB_BREAKOUT expected conditions must use canonical order"
                )
            if invalid_kinds != _ORB_INVALID_CONDITION_ORDER:
                raise ValueError(
                    "ORB_BREAKOUT invalid conditions must use canonical order"
                )


@dataclass(frozen=True)
class TradeThesis:
    thesis_id: str
    trade_id: str
    draft: TradeThesisDraft
    opening_order_id: str
    opening_fill_id: str
    entry_reference_price: Decimal
    filled_at: TradeTimestamp
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.thesis_id != self.draft.thesis_id:
            raise ValueError("thesis_id must match draft")
        for value, field_name in (
            (self.opening_order_id, "opening_order_id"),
            (self.opening_fill_id, "opening_fill_id"),
        ):
            _require_non_empty(value, field_name)
        if self.trade_id != build_trade_id(
            self.draft.session_id,
            self.opening_fill_id,
        ):
            raise ValueError("trade_id does not match first opening fill identity")
        _require_finite_decimal(self.entry_reference_price, "entry_reference_price")
        if self.entry_reference_price <= 0:
            raise ValueError("entry_reference_price must be positive")
        if self.filled_at.role is not TimestampRole.FILL:
            raise ValueError("filled_at must use the FILL role")
        if self.filled_at.value < self.draft.signal_at.value:
            raise ValueError("filled_at cannot predate signal_at")

    @property
    def thesis_start_at(self) -> TradeTimestamp:
        """The first exposure fill is the sole Thesis clock origin."""

        return self.filled_at


class DecisionLifecycleState(StrEnum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    THESIS_DRAFTED = "THESIS_DRAFTED"
    THESIS_ACTIVE = "THESIS_ACTIVE"
    EXIT_RECOMMENDATION_ACTIVE = "EXIT_RECOMMENDATION_ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class OrderLifecycleState(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class TradeLifecycleState(StrEnum):
    PENDING_ENTRY = "PENDING_ENTRY"
    ACTIVE_POSITION = "ACTIVE_POSITION"
    EXIT_IN_PROGRESS = "EXIT_IN_PROGRESS"
    CLOSED = "CLOSED"
    ENTRY_TERMINATED = "ENTRY_TERMINATED"


DECISION_LIFECYCLE_TRANSITIONS = frozenset(
    {
        (DecisionLifecycleState.SIGNAL_CREATED, DecisionLifecycleState.THESIS_DRAFTED),
        (DecisionLifecycleState.SIGNAL_CREATED, DecisionLifecycleState.TERMINATED),
        (DecisionLifecycleState.THESIS_DRAFTED, DecisionLifecycleState.THESIS_ACTIVE),
        (DecisionLifecycleState.THESIS_DRAFTED, DecisionLifecycleState.TERMINATED),
        (
            DecisionLifecycleState.THESIS_ACTIVE,
            DecisionLifecycleState.EXIT_RECOMMENDATION_ACTIVE,
        ),
        (
            DecisionLifecycleState.EXIT_RECOMMENDATION_ACTIVE,
            DecisionLifecycleState.COMPLETED,
        ),
    }
)

ORDER_LIFECYCLE_TRANSITIONS = frozenset(
    {
        (OrderLifecycleState.CREATED, OrderLifecycleState.SUBMITTED),
        (OrderLifecycleState.SUBMITTED, OrderLifecycleState.PENDING),
        (OrderLifecycleState.SUBMITTED, OrderLifecycleState.PARTIALLY_FILLED),
        (OrderLifecycleState.SUBMITTED, OrderLifecycleState.FILLED),
        (OrderLifecycleState.SUBMITTED, OrderLifecycleState.REJECTED),
        (OrderLifecycleState.SUBMITTED, OrderLifecycleState.RECOVERY_REQUIRED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.PARTIALLY_FILLED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.FILLED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.CANCELLED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.REJECTED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.EXPIRED),
        (OrderLifecycleState.PENDING, OrderLifecycleState.RECOVERY_REQUIRED),
        (
            OrderLifecycleState.PARTIALLY_FILLED,
            OrderLifecycleState.PARTIALLY_FILLED,
        ),
        (OrderLifecycleState.PARTIALLY_FILLED, OrderLifecycleState.FILLED),
        (OrderLifecycleState.PARTIALLY_FILLED, OrderLifecycleState.CANCELLED),
        (OrderLifecycleState.PARTIALLY_FILLED, OrderLifecycleState.EXPIRED),
        (
            OrderLifecycleState.PARTIALLY_FILLED,
            OrderLifecycleState.RECOVERY_REQUIRED,
        ),
    }
)

TRADE_LIFECYCLE_TRANSITIONS = frozenset(
    {
        (TradeLifecycleState.PENDING_ENTRY, TradeLifecycleState.ACTIVE_POSITION),
        (TradeLifecycleState.PENDING_ENTRY, TradeLifecycleState.ENTRY_TERMINATED),
        (TradeLifecycleState.ACTIVE_POSITION, TradeLifecycleState.EXIT_IN_PROGRESS),
        (TradeLifecycleState.ACTIVE_POSITION, TradeLifecycleState.CLOSED),
        (TradeLifecycleState.EXIT_IN_PROGRESS, TradeLifecycleState.CLOSED),
    }
)

DECISION_TERMINAL_STATES = frozenset(
    {DecisionLifecycleState.COMPLETED, DecisionLifecycleState.TERMINATED}
)
ORDER_TERMINAL_STATES = frozenset(
    {
        OrderLifecycleState.FILLED,
        OrderLifecycleState.CANCELLED,
        OrderLifecycleState.REJECTED,
        OrderLifecycleState.EXPIRED,
        OrderLifecycleState.RECOVERY_REQUIRED,
    }
)
TRADE_TERMINAL_STATES = frozenset(
    {TradeLifecycleState.CLOSED, TradeLifecycleState.ENTRY_TERMINATED}
)


class ExitCategory(StrEnum):
    EMERGENCY_RISK = "EMERGENCY_RISK"
    THESIS_INVALID = "THESIS_INVALID"
    TIME_EXPIRED = "TIME_EXPIRED"
    TAKE_PROFIT = "TAKE_PROFIT"


EXIT_CATEGORY_PRIORITY = (
    ExitCategory.EMERGENCY_RISK,
    ExitCategory.THESIS_INVALID,
    ExitCategory.TIME_EXPIRED,
    ExitCategory.TAKE_PROFIT,
)


class ExitReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    ATR_STOP = "ATR_STOP"
    END_OF_DAY = "END_OF_DAY"
    THESIS_INVALID = "THESIS_INVALID"
    TIME_DECAY = "TIME_DECAY"
    TAKE_PROFIT = "TAKE_PROFIT"
    RISK_GATE = "RISK_GATE"
    MANUAL = "MANUAL"


class ExitAction(StrEnum):
    HOLD = "HOLD"
    EXIT = "EXIT"


class ExitRecommendationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED_ON_CLOSE = "RESOLVED_ON_CLOSE"


class PnlBasis(StrEnum):
    GROSS_SIMULATED = "GROSS_SIMULATED"
    NET = "NET"


@dataclass(frozen=True)
class ExitDecision:
    decision_id: str
    session_id: str
    trade_id: str
    thesis_id: str
    action: ExitAction
    primary_reason: ExitReason | None
    triggered_reasons: tuple[ExitReason, ...]
    decided_at: TradeTimestamp
    source_event_id: str
    exit_policy_version: str
    evaluation_digest: str
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
            (self.source_event_id, "source_event_id"),
            (self.exit_policy_version, "exit_policy_version"),
        ):
            _require_non_empty(value, field_name)
        _require_sha256(self.evaluation_digest, "evaluation_digest")
        if self.decision_id != build_exit_decision_id(
            self.session_id,
            self.trade_id,
            self.source_event_id,
            self.exit_policy_version,
            self.evaluation_digest,
        ):
            raise ValueError("decision_id does not match deterministic identity")
        if self.decided_at.role is not TimestampRole.EXIT_DECISION:
            raise ValueError("decided_at must use the EXIT_DECISION role")
        if len(self.triggered_reasons) != len(set(self.triggered_reasons)):
            raise ValueError("triggered_reasons must not contain duplicates")
        if self.action is ExitAction.HOLD:
            if self.primary_reason is not None or self.triggered_reasons:
                raise ValueError("HOLD decision cannot contain exit reasons")
        elif (
            self.primary_reason is None
            or self.primary_reason not in self.triggered_reasons
        ):
            raise ValueError("EXIT decision requires a primary triggered reason")


@dataclass(frozen=True)
class ExitRecommendation:
    recommendation_id: str
    session_id: str
    trade_id: str
    thesis_id: str
    exit_policy_version: str
    status: ExitRecommendationStatus
    first_trigger_decision_id: str
    first_trigger_event_id: str
    latest_decision_id: str
    latest_evidence_event_id: str
    primary_reason: ExitReason
    triggered_reasons: tuple[ExitReason, ...]
    created_at: TradeTimestamp
    updated_at: TradeTimestamp
    resolved_at: TradeTimestamp | None = None
    closing_fill_id: str | None = None
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
            (self.exit_policy_version, "exit_policy_version"),
            (self.first_trigger_decision_id, "first_trigger_decision_id"),
            (self.first_trigger_event_id, "first_trigger_event_id"),
            (self.latest_decision_id, "latest_decision_id"),
            (self.latest_evidence_event_id, "latest_evidence_event_id"),
        ):
            _require_non_empty(value, field_name)
        if self.recommendation_id != build_exit_recommendation_id(
            self.session_id,
            self.trade_id,
            self.exit_policy_version,
        ):
            raise ValueError("recommendation_id does not match trade identity")
        if len(self.triggered_reasons) != len(set(self.triggered_reasons)):
            raise ValueError("triggered_reasons must not contain duplicates")
        if self.primary_reason not in self.triggered_reasons:
            raise ValueError("primary_reason must be included in triggered_reasons")
        for timestamp, field_name in (
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            if timestamp.role is not TimestampRole.EXIT_DECISION:
                raise ValueError(f"{field_name} must use the EXIT_DECISION role")
        if self.updated_at.value < self.created_at.value:
            raise ValueError("updated_at cannot predate created_at")
        if self.status is ExitRecommendationStatus.ACTIVE:
            if self.resolved_at is not None or self.closing_fill_id is not None:
                raise ValueError("ACTIVE recommendation cannot have close metadata")
            return
        if self.resolved_at is None or self.closing_fill_id is None:
            raise ValueError("resolved recommendation requires close metadata")
        if self.resolved_at.role is not TimestampRole.FILL:
            raise ValueError("resolved_at must use the FILL role")
        _require_non_empty(self.closing_fill_id, "closing_fill_id")
        if self.resolved_at.value < self.updated_at.value:
            raise ValueError("resolved_at cannot predate updated_at")


@dataclass(frozen=True)
class ExitLeg:
    fill_id: str
    order_id: str
    exit_recommendation_id: str | None
    reason: ExitReason
    quantity_shares: int
    fill_price: Decimal
    filled_at: TradeTimestamp

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.fill_id, "fill_id"),
            (self.order_id, "order_id"),
        ):
            _require_non_empty(value, field_name)
        if self.exit_recommendation_id is not None:
            _require_non_empty(
                self.exit_recommendation_id,
                "exit_recommendation_id",
            )
        if self.quantity_shares <= 0:
            raise ValueError("quantity_shares must be positive")
        _require_finite_decimal(self.fill_price, "fill_price")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be positive")
        if self.filled_at.role is not TimestampRole.FILL:
            raise ValueError("filled_at must use the FILL role")


@dataclass(frozen=True)
class TradeOutcome:
    trade_id: str
    exit_legs: tuple[ExitLeg, ...]
    initiating_exit_reason: ExitReason
    closing_exit_reason: ExitReason
    realized_pnl: Decimal
    pnl_basis: PnlBasis
    closed_at: TradeTimestamp
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_non_empty(self.trade_id, "trade_id")
        if not self.exit_legs:
            raise ValueError("exit_legs must not be empty")
        fill_ids = tuple(leg.fill_id for leg in self.exit_legs)
        _require_unique_strings(fill_ids, "exit leg fill ids")
        times = tuple(leg.filled_at.value for leg in self.exit_legs)
        if times != tuple(sorted(times)):
            raise ValueError("exit_legs must be chronological")
        if self.initiating_exit_reason is not self.exit_legs[0].reason:
            raise ValueError("initiating_exit_reason must match first exit leg")
        if self.closing_exit_reason is not self.exit_legs[-1].reason:
            raise ValueError("closing_exit_reason must match final exit leg")
        _require_finite_decimal(self.realized_pnl, "realized_pnl")
        if self.closed_at.role is not TimestampRole.FILL:
            raise ValueError("closed_at must use the FILL role")
        if self.closed_at.value != self.exit_legs[-1].filled_at.value:
            raise ValueError("closed_at must equal the final exit fill time")


@dataclass(frozen=True)
class ReplayRunIdentity:
    manifest_sha256: str
    canonical_event_schema_version: str
    strategy_id: str
    strategy_version: str
    thesis_type: ThesisType
    thesis_version: str
    exit_policy_version: str
    guard_policy_version: str
    fill_model_version: str
    code_identity: str
    serializer_version: str = TRADE_MANAGEMENT_SERIALIZER_VERSION
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.manifest_sha256, "manifest_sha256")
        for value, field_name in (
            (self.canonical_event_schema_version, "canonical_event_schema_version"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.thesis_version, "thesis_version"),
            (self.exit_policy_version, "exit_policy_version"),
            (self.guard_policy_version, "guard_policy_version"),
            (self.fill_model_version, "fill_model_version"),
            (self.code_identity, "code_identity"),
        ):
            _require_non_empty(value, field_name)
        if self.serializer_version != TRADE_MANAGEMENT_SERIALIZER_VERSION:
            raise ValueError("unsupported Replay serializer version")

    @property
    def digest(self) -> str:
        payload = {
            "manifest_sha256": self.manifest_sha256,
            "canonical_event_schema_version": self.canonical_event_schema_version,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "thesis_type": self.thesis_type.value,
            "thesis_version": self.thesis_version,
            "exit_policy_version": self.exit_policy_version,
            "guard_policy_version": self.guard_policy_version,
            "fill_model_version": self.fill_model_version,
            "code_identity": self.code_identity,
            "serializer_version": self.serializer_version,
            "schema_version": self.schema_version,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ReplayOutput:
    input_digest: str
    run_identity_digest: str
    strategy_version: str
    thesis_version: str
    decision_digest: str
    journal_digest: str
    final_state_digest: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.input_digest, "input_digest"),
            (self.run_identity_digest, "run_identity_digest"),
            (self.decision_digest, "decision_digest"),
            (self.journal_digest, "journal_digest"),
            (self.final_state_digest, "final_state_digest"),
        ):
            _require_sha256(value, field_name)
        _require_non_empty(self.strategy_version, "strategy_version")
        _require_non_empty(self.thesis_version, "thesis_version")

    @property
    def digest(self) -> str:
        payload = {
            "input_digest": self.input_digest,
            "run_identity_digest": self.run_identity_digest,
            "strategy_version": self.strategy_version,
            "thesis_version": self.thesis_version,
            "decision_digest": self.decision_digest,
            "journal_digest": self.journal_digest,
            "final_state_digest": self.final_state_digest,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ReplayDivergence:
    expected_output_digest: str
    actual_output_digest: str
    first_differing_event_id: str
    first_differing_sequence: int

    def __post_init__(self) -> None:
        _require_sha256(self.expected_output_digest, "expected_output_digest")
        _require_sha256(self.actual_output_digest, "actual_output_digest")
        if self.expected_output_digest == self.actual_output_digest:
            raise ValueError("divergence digests must differ")
        _require_non_empty(self.first_differing_event_id, "first_differing_event_id")
        if self.first_differing_sequence <= 0:
            raise ValueError("first_differing_sequence must be positive")


@dataclass(frozen=True)
class ReplayVerification:
    run_identity: ReplayRunIdentity
    output: ReplayOutput
    divergence: ReplayDivergence | None = None
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.output.input_digest != self.run_identity.manifest_sha256:
            raise ValueError("Replay input_digest must match manifest_sha256")
        if self.output.run_identity_digest != self.run_identity.digest:
            raise ValueError("Replay output must bind to run identity digest")
        if self.output.strategy_version != self.run_identity.strategy_version:
            raise ValueError("Replay strategy versions must match")
        if self.output.thesis_version != self.run_identity.thesis_version:
            raise ValueError("Replay thesis versions must match")
        if (
            self.divergence is not None
            and self.divergence.actual_output_digest != self.output.digest
        ):
            raise ValueError("Replay divergence must bind to actual output digest")
