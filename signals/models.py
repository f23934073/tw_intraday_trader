"""Versioned contracts shared by Momentum signal, state, and entry policy.

The state machine consumes ``momentum_acceleration_confirmed`` instead of
matching a concrete signal family.  That keeps the 09:10 Opening-to-Limit-Up
handoff inside one episode and preserves the exact family/config provenance
needed by Replay.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class SignalFamily(StrEnum):
    OPENING_MOMENTUM = "OPENING_MOMENTUM"
    LIMIT_UP_MOMENTUM = "LIMIT_UP_MOMENTUM"


class MomentumSignal(StrEnum):
    NONE = "NONE"
    OPENING_MOMENTUM = "OPENING_MOMENTUM"
    BREAKOUT = "BREAKOUT"
    VOLUME_ACCELERATION = "VOLUME_ACCELERATION"
    MOMENTUM_ACCELERATION = "MOMENTUM_ACCELERATION"
    LIMIT_UP_MOMENTUM = "LIMIT_UP_MOMENTUM"


class MomentumStage(StrEnum):
    WATCH = "WATCH"
    STRONG = "STRONG"
    BREAKOUT = "BREAKOUT"
    ACCELERATING = "ACCELERATING"
    NEAR_LIMIT_UP = "NEAR_LIMIT_UP"
    LIMIT_TOUCHED = "LIMIT_TOUCHED"


class EpisodeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    DATA_BLOCKED = "DATA_BLOCKED"


class EntryMode(StrEnum):
    NORMAL = "NORMAL"
    MOMENTUM = "MOMENTUM"


class RiskGateStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class EntryOpportunityStatus(StrEnum):
    WAITING = "WAITING"
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


class EntryRiskLevel(StrEnum):
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class EvidenceStatus(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


class SignalEvaluationStatus(StrEnum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"


_STAGE_ORDER = {
    stage: index
    for index, stage in enumerate(
        (
            MomentumStage.WATCH,
            MomentumStage.STRONG,
            MomentumStage.BREAKOUT,
            MomentumStage.ACCELERATING,
            MomentumStage.NEAR_LIMIT_UP,
            MomentumStage.LIMIT_TOUCHED,
        )
    )
}


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class SignalDetail:
    rule: str
    status: EvidenceStatus
    passed: bool | None
    points_awarded: int
    points_possible: int
    observed_value: str | int | float | Decimal | None
    threshold: str | int | float | Decimal | None
    source_as_of: datetime | None = None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.rule, "rule")
        if not 0 <= self.points_awarded <= self.points_possible:
            raise ValueError("points_awarded must be within points_possible")
        if self.source_as_of is not None:
            _require_aware(self.source_as_of, "source_as_of")
        if self.status is EvidenceStatus.VALID and self.passed is None:
            raise ValueError("valid evidence must have a pass/fail result")
        if self.status is not EvidenceStatus.VALID and not self.missing_reason:
            raise ValueError("non-valid evidence must include a missing reason")


@dataclass(frozen=True)
class SignalResult:
    symbol: str
    as_of: datetime
    config_version: str
    feature_version: str
    signal_family: SignalFamily
    signal: MomentumSignal
    triggered_signals: tuple[MomentumSignal, ...]
    momentum_acceleration_confirmed: bool
    evidence_score: int
    evidence_max_score: int
    passed_rule_count: int
    total_rule_count: int
    coverage: float
    data_health: str
    evaluation_status: SignalEvaluationStatus = SignalEvaluationStatus.TRIGGERED
    details: tuple[SignalDetail, ...] = ()
    block_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.config_version, "config_version")
        _require_non_empty(self.feature_version, "feature_version")
        _require_non_empty(self.data_health, "data_health")
        _require_aware(self.as_of, "as_of")
        if self.evidence_max_score <= 0:
            raise ValueError("evidence_max_score must be positive")
        if not 0 <= self.evidence_score <= self.evidence_max_score:
            raise ValueError("evidence_score must be between 0 and evidence_max_score")
        if not 0 <= self.passed_rule_count <= self.total_rule_count:
            raise ValueError("passed_rule_count must be between 0 and total_rule_count")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("coverage must be between 0 and 1")
        if (
            self.evaluation_status is SignalEvaluationStatus.TRIGGERED
            and self.signal is MomentumSignal.NONE
        ):
            raise ValueError("triggered evaluation must expose a signal")

    @property
    def digest(self) -> str:
        payload = {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "config_version": self.config_version,
            "feature_version": self.feature_version,
            "signal_family": self.signal_family.value,
            "signal": self.signal.value,
            "triggered_signals": [item.value for item in self.triggered_signals],
            "momentum_acceleration_confirmed": (
                self.momentum_acceleration_confirmed
            ),
            "evidence_score": self.evidence_score,
            "evidence_max_score": self.evidence_max_score,
            "passed_rule_count": self.passed_rule_count,
            "total_rule_count": self.total_rule_count,
            "coverage": self.coverage,
            "data_health": self.data_health,
            "evaluation_status": self.evaluation_status.value,
            "details": [
                {
                    "rule": item.rule,
                    "status": item.status.value,
                    "passed": item.passed,
                    "points_awarded": item.points_awarded,
                    "points_possible": item.points_possible,
                    "observed_value": (
                        str(item.observed_value)
                        if item.observed_value is not None
                        else None
                    ),
                    "threshold": (
                        str(item.threshold)
                        if item.threshold is not None
                        else None
                    ),
                    "source_as_of": (
                        item.source_as_of.isoformat()
                        if item.source_as_of is not None
                        else None
                    ),
                    "missing_reason": item.missing_reason,
                }
                for item in self.details
            ],
            "block_reasons": list(self.block_reasons),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class StageTransition:
    occurred_at: datetime
    from_stage: MomentumStage
    to_stage: MomentumStage
    signal_family: SignalFamily
    config_version: str
    evidence_snapshot_id: str

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        _require_non_empty(self.config_version, "config_version")
        _require_non_empty(self.evidence_snapshot_id, "evidence_snapshot_id")
        if _STAGE_ORDER[self.to_stage] <= _STAGE_ORDER[self.from_stage]:
            raise ValueError("stage transitions must move forward")


@dataclass(frozen=True)
class EvidenceUpdate:
    occurred_at: datetime
    signal_family: SignalFamily
    config_version: str
    evidence_snapshot_id: str
    momentum_acceleration_confirmed: bool

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        _require_non_empty(self.config_version, "config_version")
        _require_non_empty(self.evidence_snapshot_id, "evidence_snapshot_id")


@dataclass(frozen=True)
class MomentumEpisode:
    episode_id: str
    symbol: str
    session_date: date
    status: EpisodeStatus
    created_at: datetime
    created_by_signal_family: SignalFamily
    created_by_config_version: str
    current_signal_family: SignalFamily
    current_config_version: str
    current_stage: MomentumStage
    highest_stage: MomentumStage
    breakout_level: Decimal | None = None
    first_seen_at: datetime | None = None
    peak_price: Decimal | None = None
    last_progress_at: datetime | None = None
    last_evaluated_at: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    cooldown_until: datetime | None = None
    transitions: tuple[StageTransition, ...] = ()
    evidence_updates: tuple[EvidenceUpdate, ...] = ()
    limit_touched_at: datetime | None = None
    limit_locked: bool | None = None
    limit_lock_evidence_as_of: datetime | None = None
    limit_locked_at: datetime | None = None
    limit_unlocked_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.episode_id, "episode_id")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(
            self.created_by_config_version,
            "created_by_config_version",
        )
        _require_non_empty(self.current_config_version, "current_config_version")
        _require_aware(self.created_at, "created_at")
        if self.created_at.date() != self.session_date:
            raise ValueError("created_at must belong to session_date")
        if _STAGE_ORDER[self.highest_stage] < _STAGE_ORDER[self.current_stage]:
            raise ValueError("highest_stage cannot be behind current_stage")
        for field_name in (
            "first_seen_at",
            "last_progress_at",
            "last_evaluated_at",
            "closed_at",
            "cooldown_until",
            "limit_touched_at",
            "limit_lock_evidence_as_of",
            "limit_locked_at",
            "limit_unlocked_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)
                if value.date() != self.session_date:
                    raise ValueError(f"{field_name} must belong to session_date")
        for value, field_name in (
            (self.breakout_level, "breakout_level"),
            (self.peak_price, "peak_price"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.first_seen_at is not None and self.first_seen_at > self.created_at:
            raise ValueError("first_seen_at cannot follow created_at")
        if (
            self.last_progress_at is not None
            and self.last_progress_at < self.created_at
        ):
            raise ValueError("last_progress_at cannot predate created_at")
        if (
            self.last_evaluated_at is not None
            and self.last_evaluated_at < self.created_at
        ):
            raise ValueError("last_evaluated_at cannot predate created_at")
        if self.status is EpisodeStatus.ACTIVE:
            if self.closed_at is not None or self.close_reason is not None:
                raise ValueError("active episode cannot have closure metadata")
        elif self.closed_at is None or not self.close_reason:
            raise ValueError("closed episode requires time and reason")
        if self.closed_at is not None and self.closed_at < self.created_at:
            raise ValueError("closed_at cannot predate created_at")
        if (
            self.cooldown_until is not None
            and self.closed_at is not None
            and self.cooldown_until < self.closed_at
        ):
            raise ValueError("cooldown_until cannot predate closed_at")
        if self.limit_locked is True and (
            self.limit_locked_at is None or self.limit_lock_evidence_as_of is None
        ):
            raise ValueError("locked state requires lock time and evidence time")
        if self.limit_unlocked_at is not None and self.limit_locked_at is None:
            raise ValueError("unlock time requires a previous lock time")
        if (
            self.limit_unlocked_at is not None
            and self.limit_locked_at is not None
            and self.limit_unlocked_at < self.limit_locked_at
        ):
            raise ValueError("unlock time cannot predate lock time")

    def with_evidence_update(self, update: EvidenceUpdate) -> MomentumEpisode:
        """Return a new episode projection without changing creation provenance."""
        if self.status is not EpisodeStatus.ACTIVE:
            raise ValueError("only an active episode accepts evidence")
        if update.occurred_at < self.created_at:
            raise ValueError("evidence update cannot predate the episode")
        if (
            self.evidence_updates
            and update.occurred_at < self.evidence_updates[-1].occurred_at
        ):
            raise ValueError("evidence updates must be chronological")
        return replace(
            self,
            current_signal_family=update.signal_family,
            current_config_version=update.config_version,
            evidence_updates=(*self.evidence_updates, update),
            last_evaluated_at=update.occurred_at,
        )

    def with_transition(self, transition: StageTransition) -> MomentumEpisode:
        """Append a forward stage transition with its own family/config source."""
        if self.status is not EpisodeStatus.ACTIVE:
            raise ValueError("only an active episode may advance stage")
        if transition.from_stage is not self.current_stage:
            raise ValueError("transition.from_stage must match current_stage")
        if transition.occurred_at < self.created_at:
            raise ValueError("stage transition cannot predate the episode")
        if (
            self.transitions
            and transition.occurred_at < self.transitions[-1].occurred_at
        ):
            raise ValueError("stage transitions must be chronological")
        return replace(
            self,
            current_signal_family=transition.signal_family,
            current_config_version=transition.config_version,
            current_stage=transition.to_stage,
            highest_stage=max(
                self.highest_stage,
                transition.to_stage,
                key=_STAGE_ORDER.__getitem__,
            ),
            transitions=(*self.transitions, transition),
            last_progress_at=transition.occurred_at,
            last_evaluated_at=transition.occurred_at,
        )

    def with_market_observation(
        self,
        *,
        occurred_at: datetime,
        price: Decimal,
    ) -> MomentumEpisode:
        if self.status is not EpisodeStatus.ACTIVE:
            raise ValueError("only an active episode accepts market observations")
        _require_aware(occurred_at, "occurred_at")
        if occurred_at < (self.last_evaluated_at or self.created_at):
            raise ValueError("market observations must be chronological")
        if price <= 0:
            raise ValueError("market observation price must be positive")
        peak_increased = self.peak_price is None or price > self.peak_price
        return replace(
            self,
            peak_price=(
                price if self.peak_price is None else max(self.peak_price, price)
            ),
            last_progress_at=(
                occurred_at if peak_increased else self.last_progress_at
            ),
            last_evaluated_at=occurred_at,
        )

    def close(
        self,
        *,
        status: EpisodeStatus,
        occurred_at: datetime,
        reason: str,
        cooldown_until: datetime | None,
    ) -> MomentumEpisode:
        if self.status is not EpisodeStatus.ACTIVE:
            raise ValueError("only an active episode may close")
        if status is EpisodeStatus.ACTIVE:
            raise ValueError("close status must be terminal")
        _require_aware(occurred_at, "occurred_at")
        if cooldown_until is not None:
            _require_aware(cooldown_until, "cooldown_until")
        _require_non_empty(reason, "reason")
        return replace(
            self,
            status=status,
            closed_at=occurred_at,
            close_reason=reason,
            cooldown_until=cooldown_until,
            last_evaluated_at=occurred_at,
        )

    @property
    def digest(self) -> str:
        payload = {
            "episode_id": self.episode_id,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by_signal_family": self.created_by_signal_family.value,
            "created_by_config_version": self.created_by_config_version,
            "current_signal_family": self.current_signal_family.value,
            "current_config_version": self.current_config_version,
            "current_stage": self.current_stage.value,
            "highest_stage": self.highest_stage.value,
            "breakout_level": _string_or_none(self.breakout_level),
            "first_seen_at": _datetime_or_none(self.first_seen_at),
            "peak_price": _string_or_none(self.peak_price),
            "last_progress_at": _datetime_or_none(self.last_progress_at),
            "last_evaluated_at": _datetime_or_none(self.last_evaluated_at),
            "closed_at": _datetime_or_none(self.closed_at),
            "close_reason": self.close_reason,
            "cooldown_until": _datetime_or_none(self.cooldown_until),
            "transitions": [
                {
                    "occurred_at": item.occurred_at.isoformat(),
                    "from_stage": item.from_stage.value,
                    "to_stage": item.to_stage.value,
                    "signal_family": item.signal_family.value,
                    "config_version": item.config_version,
                    "evidence_snapshot_id": item.evidence_snapshot_id,
                }
                for item in self.transitions
            ],
            "evidence_updates": [
                {
                    "occurred_at": item.occurred_at.isoformat(),
                    "signal_family": item.signal_family.value,
                    "config_version": item.config_version,
                    "evidence_snapshot_id": item.evidence_snapshot_id,
                    "momentum_acceleration_confirmed": (
                        item.momentum_acceleration_confirmed
                    ),
                }
                for item in self.evidence_updates
            ],
            "limit_touched_at": _datetime_or_none(self.limit_touched_at),
            "limit_locked": self.limit_locked,
            "limit_lock_evidence_as_of": _datetime_or_none(
                self.limit_lock_evidence_as_of
            ),
            "limit_locked_at": _datetime_or_none(self.limit_locked_at),
            "limit_unlocked_at": _datetime_or_none(self.limit_unlocked_at),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class MomentumEntryPolicyConfig:
    version: str
    enabled_signal_families: frozenset[SignalFamily]

    def __post_init__(self) -> None:
        _require_non_empty(self.version, "version")


@dataclass(frozen=True)
class EntryPolicyDecision:
    eligible: bool
    policy_version: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EntryOpportunity:
    mode: EntryMode
    status: EntryOpportunityStatus
    signal_id: str
    policy_version: str
    risk_decision_id: str | None
    risk_level: EntryRiskLevel
    position_size_cap: Decimal | None
    invalidation_price: Decimal | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.signal_id, "signal_id")
        _require_non_empty(self.policy_version, "policy_version")
        for value, field_name in (
            (self.position_size_cap, "position_size_cap"),
            (self.invalidation_price, "invalidation_price"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.status is EntryOpportunityStatus.AVAILABLE:
            if self.risk_decision_id is None:
                raise ValueError("available entry requires a risk decision id")
            if self.reasons:
                raise ValueError("available entry cannot have block reasons")


def evaluate_momentum_entry_policy(
    episode: MomentumEpisode,
    policy: MomentumEntryPolicyConfig,
    risk_gate_status: RiskGateStatus,
) -> EntryPolicyDecision:
    """Evaluate entry eligibility without coupling to a concrete signal class."""
    reasons: list[str] = []
    if episode.status is not EpisodeStatus.ACTIVE:
        reasons.append("episode_not_active")
    if _STAGE_ORDER[episode.current_stage] < _STAGE_ORDER[MomentumStage.ACCELERATING]:
        reasons.append("acceleration_not_confirmed")
    if episode.current_signal_family not in policy.enabled_signal_families:
        reasons.append("signal_family_not_enabled")
    if risk_gate_status is not RiskGateStatus.PASS:
        reasons.append("risk_gate_not_passed")
    return EntryPolicyDecision(
        eligible=not reasons,
        policy_version=policy.version,
        reasons=tuple(reasons),
    )


def evaluate_momentum_entry_opportunity(
    episode: MomentumEpisode,
    signal_id: str,
    policy: MomentumEntryPolicyConfig,
    risk_gate_status: RiskGateStatus,
    *,
    risk_decision_id: str | None = None,
    position_size_cap: Decimal | None = None,
    invalidation_price: Decimal | None = None,
) -> EntryOpportunity:
    """Produce presentation eligibility without importing a RiskGate adapter."""
    policy_decision = evaluate_momentum_entry_policy(
        episode,
        policy,
        risk_gate_status,
    )
    reasons = list(policy_decision.reasons)
    if risk_gate_status is RiskGateStatus.PASS and not risk_decision_id:
        reasons.append("risk_decision_id_missing")
    risk_blocked = (
        risk_gate_status is not RiskGateStatus.PASS or not risk_decision_id
    )
    non_risk_reasons = [
        reason for reason in reasons if not reason.startswith("risk_")
    ]
    if risk_blocked:
        status = EntryOpportunityStatus.BLOCKED
    elif non_risk_reasons:
        status = EntryOpportunityStatus.WAITING
    else:
        status = EntryOpportunityStatus.AVAILABLE
        reasons.clear()
    return EntryOpportunity(
        mode=EntryMode.MOMENTUM,
        status=status,
        signal_id=signal_id,
        policy_version=policy.version,
        risk_decision_id=risk_decision_id,
        risk_level=EntryRiskLevel.VERY_HIGH,
        position_size_cap=position_size_cap,
        invalidation_price=invalidation_price,
        reasons=tuple(reasons),
    )


def _datetime_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _string_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
