"""Runtime-neutral atomic strategy evaluation protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol

from features.specifications import NormalizedFeatureSnapshot
from strategy_catalog.drafts import StrategyTemplate


class AtomicEvaluationStatus(StrEnum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class AtomicStrategyContext:
    strategy_version_id: str
    symbol: str
    event_at: datetime
    current_price: str
    parameters: Mapping[str, Any]
    features: NormalizedFeatureSnapshot


@dataclass(frozen=True)
class AtomicStrategyEvaluation:
    strategy_id: str
    strategy_version_id: str
    status: AtomicEvaluationStatus
    symbol: str
    event_at: datetime
    reason: str
    observed: Mapping[str, Any] = field(default_factory=dict)
    threshold: Mapping[str, Any] = field(default_factory=dict)


class AtomicStrategy(Protocol):
    template: StrategyTemplate

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation: ...
