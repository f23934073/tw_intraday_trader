"""Versioned configuration contracts for Momentum research.

Values named ``hypothesis_v0`` are deliberately not promoted strategy
parameters.  Unresolved live-market choices remain ``None`` and therefore
fail closed instead of selecting an undocumented fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from signals.models import (
    MomentumEntryPolicyConfig,
    MomentumSignal,
    SignalFamily,
)


class OpeningVolumeContextMode(StrEnum):
    HISTORICAL_ELAPSED_TIME_RVOL = "HISTORICAL_ELAPSED_TIME_RVOL"
    PREVIOUS_DAY_TOTAL_RATIO = "PREVIOUS_DAY_TOTAL_RATIO"
    HISTORICAL_OPENING_PROFILE_RVOL = "HISTORICAL_OPENING_PROFILE_RVOL"


class QuoteSubscriptionMode(StrEnum):
    QUOTE = "QUOTE"
    TICK_BIDASK = "TICK_BIDASK"


@dataclass(frozen=True)
class EvidenceWeight:
    rule: str
    points: int

    def __post_init__(self) -> None:
        if not self.rule.strip():
            raise ValueError("rule must not be empty")
        if self.points < 0:
            raise ValueError("points must be non-negative")


@dataclass(frozen=True)
class SignalFamilyHypothesisConfig:
    version: str
    signal_family: SignalFamily
    acceleration_signals: frozenset[MomentumSignal]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if not self.acceleration_signals:
            raise ValueError("acceleration_signals must not be empty")

    def confirms_acceleration(self, signal: MomentumSignal) -> bool:
        """Map family-specific output to a family-neutral domain semantic."""
        return signal in self.acceleration_signals


@dataclass(frozen=True)
class OpeningMomentumHypothesisConfig:
    family: SignalFamilyHypothesisConfig
    opening_volume_context_mode: OpeningVolumeContextMode | None
    min_return_2m: Decimal
    max_distance_to_limit: Decimal
    min_opening_volume_context: Decimal
    min_external_ratio: Decimal
    trigger_evidence_score: int
    weights: tuple[EvidenceWeight, ...]

    def __post_init__(self) -> None:
        _validate_evidence_config(
            trigger_evidence_score=self.trigger_evidence_score,
            weights=self.weights,
        )

    @property
    def runtime_ready(self) -> bool:
        return self.opening_volume_context_mode is not None

    @property
    def evidence_max_score(self) -> int:
        return sum(weight.points for weight in self.weights)


@dataclass(frozen=True)
class LimitUpMomentumHypothesisConfig:
    family: SignalFamilyHypothesisConfig
    min_return_2m: Decimal
    max_distance_to_limit: Decimal
    min_volume_acceleration_2m: Decimal
    min_external_ratio: Decimal
    trigger_evidence_score: int
    weights: tuple[EvidenceWeight, ...]

    def __post_init__(self) -> None:
        _validate_evidence_config(
            trigger_evidence_score=self.trigger_evidence_score,
            weights=self.weights,
        )

    @property
    def evidence_max_score(self) -> int:
        return sum(weight.points for weight in self.weights)


def _validate_evidence_config(
    *,
    trigger_evidence_score: int,
    weights: tuple[EvidenceWeight, ...],
) -> None:
    max_score = sum(weight.points for weight in weights)
    if max_score <= 0:
        raise ValueError("evidence weights must have a positive total")
    rules = tuple(weight.rule for weight in weights)
    if len(set(rules)) != len(rules):
        raise ValueError("evidence weight rules must be unique")
    if not 0 <= trigger_evidence_score <= max_score:
        raise ValueError("trigger_evidence_score must be within score range")


@dataclass(frozen=True)
class LimitLockPolicyConfig:
    version: str
    confirmation_duration: timedelta | None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if (
            self.confirmation_duration is not None
            and self.confirmation_duration <= timedelta(0)
        ):
            raise ValueError("confirmation_duration must be positive")

    @property
    def runtime_ready(self) -> bool:
        return self.confirmation_duration is not None


@dataclass(frozen=True)
class MomentumStateMachineConfig:
    version: str
    near_limit_distance: Decimal
    episode_ttl: timedelta
    cooldown: timedelta
    invalidation_confirmation_observations: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("state-machine version must not be empty")
        if not Decimal("0") <= self.near_limit_distance < Decimal("1"):
            raise ValueError("near-limit distance must be between zero and one")
        if self.episode_ttl <= timedelta(0):
            raise ValueError("episode TTL must be positive")
        if self.cooldown < timedelta(0):
            raise ValueError("cooldown cannot be negative")
        if self.invalidation_confirmation_observations <= 0:
            raise ValueError("invalidation confirmation must be positive")


@dataclass(frozen=True)
class SubscriptionCapacityConfig:
    account_subscription_limit: int
    reserved_headroom: int | None
    mode: QuoteSubscriptionMode | None

    def __post_init__(self) -> None:
        if self.account_subscription_limit <= 0:
            raise ValueError("account_subscription_limit must be positive")
        if self.reserved_headroom is not None and not (
            0 <= self.reserved_headroom < self.account_subscription_limit
        ):
            raise ValueError("reserved_headroom must fit within the account limit")

    @property
    def subscriptions_per_symbol(self) -> int | None:
        if self.mode is QuoteSubscriptionMode.QUOTE:
            return 1
        if self.mode is QuoteSubscriptionMode.TICK_BIDASK:
            return 2
        return None

    @property
    def max_symbols(self) -> int | None:
        per_symbol = self.subscriptions_per_symbol
        if self.reserved_headroom is None or per_symbol is None:
            return None
        usable = self.account_subscription_limit - self.reserved_headroom
        return usable // per_symbol


OPENING_MOMENTUM_HYPOTHESIS_V0 = OpeningMomentumHypothesisConfig(
    family=SignalFamilyHypothesisConfig(
        version="opening_momentum_hypothesis_v0",
        signal_family=SignalFamily.OPENING_MOMENTUM,
        acceleration_signals=frozenset({MomentumSignal.OPENING_MOMENTUM}),
    ),
    # Phase 0 research decision remains open; runtime must fail closed.
    opening_volume_context_mode=None,
    min_return_2m=Decimal("0.015"),
    max_distance_to_limit=Decimal("0.03"),
    min_opening_volume_context=Decimal("1.5"),
    min_external_ratio=Decimal("0.60"),
    trigger_evidence_score=70,
    weights=(
        EvidenceWeight("price_above_vwap", 15),
        EvidenceWeight("breakout", 20),
        EvidenceWeight("return_2m", 15),
        EvidenceWeight("distance_to_limit", 20),
        EvidenceWeight("opening_volume_context", 20),
        EvidenceWeight("external_ratio_rising", 10),
    ),
)


LIMIT_UP_MOMENTUM_HYPOTHESIS_V0 = LimitUpMomentumHypothesisConfig(
    family=SignalFamilyHypothesisConfig(
        version="limit_up_momentum_hypothesis_v0",
        signal_family=SignalFamily.LIMIT_UP_MOMENTUM,
        acceleration_signals=frozenset({MomentumSignal.LIMIT_UP_MOMENTUM}),
    ),
    min_return_2m=Decimal("0.015"),
    max_distance_to_limit=Decimal("0.03"),
    min_volume_acceleration_2m=Decimal("1.5"),
    min_external_ratio=Decimal("0.60"),
    trigger_evidence_score=70,
    weights=(
        EvidenceWeight("price_above_vwap", 15),
        EvidenceWeight("breakout", 20),
        EvidenceWeight("return_2m", 15),
        EvidenceWeight("distance_to_limit", 20),
        EvidenceWeight("volume_acceleration_2m", 20),
        EvidenceWeight("external_ratio_rising", 10),
    ),
)


MOMENTUM_ENTRY_HYPOTHESIS_V0 = MomentumEntryPolicyConfig(
    version="momentum_entry_hypothesis_v0",
    enabled_signal_families=frozenset(
        {
            SignalFamily.OPENING_MOMENTUM,
            SignalFamily.LIMIT_UP_MOMENTUM,
        }
    ),
)


LIMIT_LOCK_HYPOTHESIS_V0 = LimitLockPolicyConfig(
    version="limit_lock_hypothesis_v0",
    # Requires a labeled live book capture before selection.
    confirmation_duration=None,
)


MOMENTUM_STATE_HYPOTHESIS_V0 = MomentumStateMachineConfig(
    version="momentum_state_hypothesis_v0",
    near_limit_distance=Decimal("0.01"),
    episode_ttl=timedelta(minutes=10),
    cooldown=timedelta(minutes=2),
    invalidation_confirmation_observations=2,
)


SUBSCRIPTION_CAPACITY_PHASE0 = SubscriptionCapacityConfig(
    account_subscription_limit=200,
    # Headroom and Quote-vs-Tick+BidAsk mode require Phase 0 evidence/review.
    reserved_headroom=None,
    mode=None,
)
