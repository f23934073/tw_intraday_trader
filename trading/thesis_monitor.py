"""Pure, status-only Trade Thesis evaluation for PR-TM-003.

Window aggregation belongs to the upstream canonical market projection.  This
module accepts immutable evidence, evaluates the frozen thesis rules, and
returns immutable evidence.  It has no persistence or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from trading.canonical_values import canonical_decimal_string
from trading.trade_management import (
    BreakoutLevelLostSpec,
    EvidenceValue,
    EvidenceValueKind,
    ExpectedConditionKind,
    HoldAboveVwapSpec,
    InvalidConditionKind,
    NewHighExtensionSpec,
    PostEntryVolumeExpansionSpec,
    PriceReference,
    SessionDataBlockedSpec,
    ThesisStatus,
    TimestampRole,
    TradeThesis,
    TradeTimestamp,
    TRADE_MANAGEMENT_SCHEMA_VERSION,
    VwapConfirmationLostSpec,
)


THESIS_MONITOR_ID_VERSION = "thesis-monitor-id-v1"


class MarketContextStatus(StrEnum):
    READY = "READY"
    MISSING = "MISSING"
    STALE = "STALE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    SESSION_MISMATCH = "SESSION_MISMATCH"


class ConditionOutcome(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ThesisReasonCode(StrEnum):
    ALL_EXPECTED_BEHAVIOR_MET = "ALL_EXPECTED_BEHAVIOR_MET"
    EXPECTED_BEHAVIOR_PENDING = "EXPECTED_BEHAVIOR_PENDING"
    EXPECTED_BEHAVIOR_WARNING = "EXPECTED_BEHAVIOR_WARNING"
    EXPECTED_BEHAVIOR_EXPIRED = "EXPECTED_BEHAVIOR_EXPIRED"
    BREAKOUT_LEVEL_LOST = "BREAKOUT_LEVEL_LOST"
    VWAP_CONFIRMATION_LOST = "VWAP_CONFIRMATION_LOST"
    SESSION_DATA_BLOCKED = "SESSION_DATA_BLOCKED"
    MARKET_DATA_MISSING = "MARKET_DATA_MISSING"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_DATA_OUT_OF_ORDER = "MARKET_DATA_OUT_OF_ORDER"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    REQUIRED_INPUT_MISSING = "REQUIRED_INPUT_MISSING"
    OBSERVED_BEFORE_FILL = "OBSERVED_BEFORE_FILL"
    INVALID_LATCHED = "INVALID_LATCHED"


ConditionKind = ExpectedConditionKind | InvalidConditionKind


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_optional_decimal(value: Decimal | None, field_name: str) -> None:
    if value is not None and not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _require_optional_count(value: int | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True)
class ThesisMarketContext:
    """Immutable, upstream-aggregated evidence for one thesis observation."""

    thesis_id: str
    trade_id: str
    session_id: str
    symbol: str
    source_event_id: str
    observed_at: TradeTimestamp
    data_status: MarketContextStatus
    health_state: str
    highest_price_since_entry: Decimal | None
    post_entry_volume_shares: int | None
    volume_baseline_shares: Decimal | None
    volume_sample_count: int | None
    completed_bar_count: int
    completed_bars_below_vwap: int | None
    consecutive_completed_bars_below_vwap: int | None
    consecutive_completed_bars_below_breakout: int | None
    prior_status: ThesisStatus | None = None
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_MANAGEMENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported trade management schema: {self.schema_version}")
        for value, field_name in (
            (self.thesis_id, "thesis_id"),
            (self.trade_id, "trade_id"),
            (self.session_id, "session_id"),
            (self.symbol, "symbol"),
            (self.source_event_id, "source_event_id"),
            (self.health_state, "health_state"),
        ):
            _require_non_empty(value, field_name)
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        if self.observed_at.role is not TimestampRole.MARKET_EVENT:
            raise ValueError("observed_at must use the MARKET_EVENT role")
        if self.observed_at.source_identity != self.source_event_id:
            raise ValueError("source_event_id must match observed_at source identity")
        for value, field_name in (
            (self.highest_price_since_entry, "highest_price_since_entry"),
            (self.volume_baseline_shares, "volume_baseline_shares"),
        ):
            _require_optional_decimal(value, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")
        for value, field_name in (
            (self.post_entry_volume_shares, "post_entry_volume_shares"),
            (self.volume_sample_count, "volume_sample_count"),
            (self.completed_bar_count, "completed_bar_count"),
            (self.completed_bars_below_vwap, "completed_bars_below_vwap"),
            (
                self.consecutive_completed_bars_below_vwap,
                "consecutive_completed_bars_below_vwap",
            ),
            (
                self.consecutive_completed_bars_below_breakout,
                "consecutive_completed_bars_below_breakout",
            ),
        ):
            _require_optional_count(value, field_name)
        if (
            self.highest_price_since_entry is not None
            and self.highest_price_since_entry <= 0
        ):
            raise ValueError("highest_price_since_entry must be positive")
        for value, field_name in (
            (self.completed_bars_below_vwap, "completed_bars_below_vwap"),
            (
                self.consecutive_completed_bars_below_vwap,
                "consecutive_completed_bars_below_vwap",
            ),
            (
                self.consecutive_completed_bars_below_breakout,
                "consecutive_completed_bars_below_breakout",
            ),
        ):
            if value is not None and value > self.completed_bar_count:
                raise ValueError(f"{field_name} cannot exceed completed_bar_count")


@dataclass(frozen=True)
class ThesisConditionEvaluation:
    kind: ConditionKind
    outcome: ConditionOutcome
    observed: tuple[EvidenceValue, ...]
    threshold: tuple[EvidenceValue, ...]

    def __post_init__(self) -> None:
        for values, field_name in (
            (self.observed, "observed"),
            (self.threshold, "threshold"),
        ):
            names = tuple(value.name for value in values)
            if len(names) != len(set(names)):
                raise ValueError(f"{field_name} evidence names must be unique")
        if isinstance(self.kind, ExpectedConditionKind) and self.outcome in {
            ConditionOutcome.TRIGGERED,
            ConditionOutcome.NOT_TRIGGERED,
        }:
            raise ValueError("expected condition cannot use invalid-condition outcome")
        if isinstance(self.kind, InvalidConditionKind) and self.outcome in {
            ConditionOutcome.SATISFIED,
            ConditionOutcome.UNSATISFIED,
        }:
            raise ValueError("invalid condition cannot use expected-condition outcome")


@dataclass(frozen=True)
class ThesisEvaluation:
    evaluation_id: str
    thesis_id: str
    trade_id: str
    source_event_id: str
    evaluated_at: TradeTimestamp
    status: ThesisStatus
    reason_codes: tuple[ThesisReasonCode, ...]
    conditions: tuple[ThesisConditionEvaluation, ...]
    input_digest: str
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_MANAGEMENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported trade management schema: {self.schema_version}")
        for value, field_name in (
            (self.evaluation_id, "evaluation_id"),
            (self.thesis_id, "thesis_id"),
            (self.trade_id, "trade_id"),
            (self.source_event_id, "source_event_id"),
        ):
            _require_non_empty(value, field_name)
        if len(self.input_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_digest
        ):
            raise ValueError("input_digest must be a lowercase SHA-256 hex digest")
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must not contain duplicates")


def _timedelta_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _decimal_value(name: str, value: Decimal | None) -> EvidenceValue:
    if value is None:
        return EvidenceValue(name=name, kind=EvidenceValueKind.NULL, value=None)
    return EvidenceValue(
        name=name,
        kind=EvidenceValueKind.DECIMAL,
        value=canonical_decimal_string(value),
    )


def _integer_value(name: str, value: int | None) -> EvidenceValue:
    if value is None:
        return EvidenceValue(name=name, kind=EvidenceValueKind.NULL, value=None)
    return EvidenceValue(
        name=name,
        kind=EvidenceValueKind.INTEGER,
        value=str(value),
    )


def _text_value(name: str, value: str) -> EvidenceValue:
    return EvidenceValue(name=name, kind=EvidenceValueKind.TEXT, value=value)


def _optional_decimal_wire(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal_string(value)


def _condition_spec_wire(condition: object) -> dict[str, object]:
    if isinstance(condition, NewHighExtensionSpec):
        return {
            "kind": condition.kind.value,
            "reference": condition.reference.value,
            "buffer": canonical_decimal_string(condition.buffer),
            "comparison": condition.comparison.value,
        }
    if isinstance(condition, PostEntryVolumeExpansionSpec):
        return {
            "kind": condition.kind.value,
            "baseline_kind": condition.baseline_kind.value,
            "ratio": canonical_decimal_string(condition.ratio),
            "minimum_samples": condition.minimum_samples,
            "volume_unit": condition.volume_unit.value,
            "comparison": condition.comparison.value,
        }
    if isinstance(condition, HoldAboveVwapSpec):
        return {
            "kind": condition.kind.value,
            "allowed_completed_bars_below": condition.allowed_completed_bars_below,
            "comparison": condition.comparison.value,
        }
    if isinstance(condition, BreakoutLevelLostSpec):
        return {
            "kind": condition.kind.value,
            "breakout_level": canonical_decimal_string(condition.breakout_level),
            "confirmation_completed_bars": condition.confirmation_completed_bars,
            "comparison": condition.comparison.value,
        }
    if isinstance(condition, VwapConfirmationLostSpec):
        return {
            "kind": condition.kind.value,
            "confirmation_completed_bars": condition.confirmation_completed_bars,
            "comparison": condition.comparison.value,
        }
    if isinstance(condition, SessionDataBlockedSpec):
        return {
            "kind": condition.kind.value,
            "blocked_health_states": list(condition.blocked_health_states),
            "block_on_session_mismatch": condition.block_on_session_mismatch,
        }
    raise TypeError(f"unsupported thesis condition: {type(condition).__name__}")


def _input_digest(thesis: TradeThesis, market: ThesisMarketContext) -> str:
    payload = {
        "version": THESIS_MONITOR_ID_VERSION,
        "thesis_id": thesis.thesis_id,
        "trade_id": thesis.trade_id,
        "thesis_version": thesis.draft.thesis_version,
        "entry_reference_price": canonical_decimal_string(
            thesis.entry_reference_price
        ),
        "filled_at": thesis.filled_at.isoformat,
        "expected_behavior": {
            "policy_id": thesis.draft.expected_behavior.policy_id,
            "version": thesis.draft.expected_behavior.version,
            "observation_window_microseconds": _timedelta_microseconds(
                thesis.draft.expected_behavior.observation_window
            ),
            "warning_after_microseconds": (
                None
                if thesis.draft.expected_behavior.warning_after is None
                else _timedelta_microseconds(
                    thesis.draft.expected_behavior.warning_after
                )
            ),
            "conditions": [
                _condition_spec_wire(condition)
                for condition in thesis.draft.expected_behavior.conditions
            ],
        },
        "invalid_conditions": [
            _condition_spec_wire(condition)
            for condition in thesis.draft.invalid_conditions
        ],
        "market": {
            "thesis_id": market.thesis_id,
            "trade_id": market.trade_id,
            "session_id": market.session_id,
            "symbol": market.symbol,
            "source_event_id": market.source_event_id,
            "observed_at": market.observed_at.isoformat,
            "data_status": market.data_status.value,
            "health_state": market.health_state,
            "highest_price_since_entry": _optional_decimal_wire(
                market.highest_price_since_entry
            ),
            "post_entry_volume_shares": market.post_entry_volume_shares,
            "volume_baseline_shares": _optional_decimal_wire(
                market.volume_baseline_shares
            ),
            "volume_sample_count": market.volume_sample_count,
            "completed_bar_count": market.completed_bar_count,
            "completed_bars_below_vwap": market.completed_bars_below_vwap,
            "consecutive_completed_bars_below_vwap": (
                market.consecutive_completed_bars_below_vwap
            ),
            "consecutive_completed_bars_below_breakout": (
                market.consecutive_completed_bars_below_breakout
            ),
            "prior_status": (
                None if market.prior_status is None else market.prior_status.value
            ),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _build_evaluation_id(
    thesis: TradeThesis,
    market: ThesisMarketContext,
    input_digest: str,
) -> str:
    encoded = json.dumps(
        [
            THESIS_MONITOR_ID_VERSION,
            thesis.thesis_id,
            thesis.trade_id,
            market.source_event_id,
            input_digest,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return f"thesis_evaluation_v1_{hashlib.sha256(encoded).hexdigest()}"


def _breakout_level(thesis: TradeThesis) -> Decimal:
    for condition in thesis.draft.invalid_conditions:
        if isinstance(condition, BreakoutLevelLostSpec):
            return condition.breakout_level
    raise ValueError("ORB thesis requires a breakout-level invalid condition")


class ThesisMonitor:
    """Evaluate one immutable thesis/context pair without side effects."""

    __slots__ = ()

    def evaluate(
        self,
        thesis: TradeThesis,
        market: ThesisMarketContext,
    ) -> ThesisEvaluation:
        self._validate_identity(thesis, market)
        input_digest = _input_digest(thesis, market)

        if market.prior_status is ThesisStatus.INVALID:
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INVALID,
                (ThesisReasonCode.INVALID_LATCHED,),
                (),
            )
        if market.observed_at.value < thesis.thesis_start_at.value:
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INSUFFICIENT_DATA,
                (ThesisReasonCode.OBSERVED_BEFORE_FILL,),
                (),
            )

        context_reason = {
            MarketContextStatus.MISSING: ThesisReasonCode.MARKET_DATA_MISSING,
            MarketContextStatus.STALE: ThesisReasonCode.MARKET_DATA_STALE,
            MarketContextStatus.OUT_OF_ORDER: (
                ThesisReasonCode.MARKET_DATA_OUT_OF_ORDER
            ),
            MarketContextStatus.SESSION_MISMATCH: ThesisReasonCode.SESSION_MISMATCH,
        }.get(market.data_status)
        if context_reason is not None:
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INSUFFICIENT_DATA,
                (context_reason,),
                (),
            )

        session_rule = next(
            (
                condition
                for condition in thesis.draft.invalid_conditions
                if isinstance(condition, SessionDataBlockedSpec)
            ),
            None,
        )
        if (
            session_rule is not None
            and market.health_state in session_rule.blocked_health_states
        ):
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INSUFFICIENT_DATA,
                (ThesisReasonCode.SESSION_DATA_BLOCKED,),
                (),
            )

        conditions = self._evaluate_conditions(thesis, market)
        if any(
            condition.outcome is ConditionOutcome.INSUFFICIENT_DATA
            for condition in conditions
        ):
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INSUFFICIENT_DATA,
                (ThesisReasonCode.REQUIRED_INPUT_MISSING,),
                conditions,
            )

        triggered_reasons: list[ThesisReasonCode] = []
        for condition in conditions:
            if condition.outcome is not ConditionOutcome.TRIGGERED:
                continue
            if condition.kind is InvalidConditionKind.BREAKOUT_LEVEL_LOST:
                triggered_reasons.append(ThesisReasonCode.BREAKOUT_LEVEL_LOST)
            elif condition.kind is InvalidConditionKind.VWAP_CONFIRMATION_LOST:
                triggered_reasons.append(ThesisReasonCode.VWAP_CONFIRMATION_LOST)
        if triggered_reasons:
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.INVALID,
                tuple(triggered_reasons),
                conditions,
            )

        expected = tuple(
            condition
            for condition in conditions
            if isinstance(condition.kind, ExpectedConditionKind)
        )
        if all(
            condition.outcome is ConditionOutcome.SATISFIED
            for condition in expected
        ):
            return self._result(
                thesis,
                market,
                input_digest,
                ThesisStatus.VALID,
                (ThesisReasonCode.ALL_EXPECTED_BEHAVIOR_MET,),
                conditions,
            )

        elapsed = market.observed_at.value - thesis.thesis_start_at.value
        policy = thesis.draft.expected_behavior
        if elapsed >= policy.observation_window:
            status = ThesisStatus.INVALID
            reason = ThesisReasonCode.EXPECTED_BEHAVIOR_EXPIRED
        elif policy.warning_after is not None and elapsed >= policy.warning_after:
            status = ThesisStatus.WARNING
            reason = ThesisReasonCode.EXPECTED_BEHAVIOR_WARNING
        else:
            status = ThesisStatus.VALID
            reason = ThesisReasonCode.EXPECTED_BEHAVIOR_PENDING
        return self._result(
            thesis,
            market,
            input_digest,
            status,
            (reason,),
            conditions,
        )

    @staticmethod
    def _validate_identity(
        thesis: TradeThesis,
        market: ThesisMarketContext,
    ) -> None:
        expected = {
            "thesis_id": thesis.thesis_id,
            "trade_id": thesis.trade_id,
            "session_id": thesis.draft.session_id,
            "symbol": thesis.draft.symbol,
        }
        for field_name, expected_value in expected.items():
            if getattr(market, field_name) != expected_value:
                raise ValueError(f"market {field_name} does not match thesis")

    @staticmethod
    def _result(
        thesis: TradeThesis,
        market: ThesisMarketContext,
        input_digest: str,
        status: ThesisStatus,
        reason_codes: tuple[ThesisReasonCode, ...],
        conditions: tuple[ThesisConditionEvaluation, ...],
    ) -> ThesisEvaluation:
        return ThesisEvaluation(
            evaluation_id=_build_evaluation_id(thesis, market, input_digest),
            thesis_id=thesis.thesis_id,
            trade_id=thesis.trade_id,
            source_event_id=market.source_event_id,
            evaluated_at=market.observed_at,
            status=status,
            reason_codes=reason_codes,
            conditions=conditions,
            input_digest=input_digest,
        )

    @staticmethod
    def _evaluate_conditions(
        thesis: TradeThesis,
        market: ThesisMarketContext,
    ) -> tuple[ThesisConditionEvaluation, ...]:
        breakout_level = _breakout_level(thesis)
        evaluations: list[ThesisConditionEvaluation] = []
        for condition in thesis.draft.expected_behavior.conditions:
            if isinstance(condition, NewHighExtensionSpec):
                reference = (
                    thesis.entry_reference_price
                    if condition.reference is PriceReference.ENTRY_REFERENCE_PRICE
                    else breakout_level
                )
                threshold = reference + condition.buffer
                observed = market.highest_price_since_entry
                outcome = (
                    ConditionOutcome.INSUFFICIENT_DATA
                    if observed is None
                    else (
                        ConditionOutcome.SATISFIED
                        if observed > threshold
                        else ConditionOutcome.UNSATISFIED
                    )
                )
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=outcome,
                        observed=(_decimal_value("highest_price_since_entry", observed),),
                        threshold=(_decimal_value("required_price", threshold),),
                    )
                )
            elif isinstance(condition, PostEntryVolumeExpansionSpec):
                observed_volume = market.post_entry_volume_shares
                baseline = market.volume_baseline_shares
                samples = market.volume_sample_count
                if observed_volume is None or baseline is None or baseline <= 0 or samples is None:
                    outcome = ConditionOutcome.INSUFFICIENT_DATA
                elif (
                    samples >= condition.minimum_samples
                    and observed_volume >= baseline * condition.ratio
                ):
                    outcome = ConditionOutcome.SATISFIED
                else:
                    outcome = ConditionOutcome.UNSATISFIED
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=outcome,
                        observed=(
                            _integer_value("post_entry_volume_shares", observed_volume),
                            _decimal_value("volume_baseline_shares", baseline),
                            _integer_value("volume_sample_count", samples),
                        ),
                        threshold=(
                            _decimal_value("minimum_volume_ratio", condition.ratio),
                            _integer_value(
                                "minimum_volume_samples",
                                condition.minimum_samples,
                            ),
                        ),
                    )
                )
            elif isinstance(condition, HoldAboveVwapSpec):
                below = market.completed_bars_below_vwap
                if market.completed_bar_count == 0 or below is None:
                    outcome = ConditionOutcome.INSUFFICIENT_DATA
                elif below <= condition.allowed_completed_bars_below:
                    outcome = ConditionOutcome.SATISFIED
                else:
                    outcome = ConditionOutcome.UNSATISFIED
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=outcome,
                        observed=(_integer_value("completed_bars_below_vwap", below),),
                        threshold=(
                            _integer_value(
                                "allowed_completed_bars_below",
                                condition.allowed_completed_bars_below,
                            ),
                        ),
                    )
                )

        for condition in thesis.draft.invalid_conditions:
            if isinstance(condition, BreakoutLevelLostSpec):
                count = market.consecutive_completed_bars_below_breakout
                if market.completed_bar_count == 0 or count is None:
                    outcome = ConditionOutcome.INSUFFICIENT_DATA
                elif count >= condition.confirmation_completed_bars:
                    outcome = ConditionOutcome.TRIGGERED
                else:
                    outcome = ConditionOutcome.NOT_TRIGGERED
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=outcome,
                        observed=(
                            _integer_value(
                                "consecutive_completed_bars_below_breakout",
                                count,
                            ),
                        ),
                        threshold=(
                            _integer_value(
                                "confirmation_completed_bars",
                                condition.confirmation_completed_bars,
                            ),
                            _decimal_value("breakout_level", condition.breakout_level),
                        ),
                    )
                )
            elif isinstance(condition, VwapConfirmationLostSpec):
                count = market.consecutive_completed_bars_below_vwap
                if market.completed_bar_count == 0 or count is None:
                    outcome = ConditionOutcome.INSUFFICIENT_DATA
                elif count >= condition.confirmation_completed_bars:
                    outcome = ConditionOutcome.TRIGGERED
                else:
                    outcome = ConditionOutcome.NOT_TRIGGERED
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=outcome,
                        observed=(
                            _integer_value(
                                "consecutive_completed_bars_below_vwap",
                                count,
                            ),
                        ),
                        threshold=(
                            _integer_value(
                                "confirmation_completed_bars",
                                condition.confirmation_completed_bars,
                            ),
                        ),
                    )
                )
            elif isinstance(condition, SessionDataBlockedSpec):
                evaluations.append(
                    ThesisConditionEvaluation(
                        kind=condition.kind,
                        outcome=ConditionOutcome.NOT_TRIGGERED,
                        observed=(_text_value("health_state", market.health_state),),
                        threshold=tuple(
                            _text_value(f"blocked_health_state_{index}", state)
                            for index, state in enumerate(
                                condition.blocked_health_states
                            )
                        ),
                    )
                )
        return tuple(evaluations)
