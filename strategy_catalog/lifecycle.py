"""Append-only lifecycle transition rules for strategy versions."""

from __future__ import annotations

from enum import StrEnum


class StrategyLifecycleStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    REVIEWED = "REVIEWED"
    BACKTESTED = "BACKTESTED"
    PAPER_APPROVED = "PAPER_APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


_ALLOWED_TRANSITIONS: dict[StrategyLifecycleStatus, frozenset[StrategyLifecycleStatus]] = {
    StrategyLifecycleStatus.PUBLISHED: frozenset(
        {StrategyLifecycleStatus.REVIEWED, StrategyLifecycleStatus.RETIRED}
    ),
    StrategyLifecycleStatus.REVIEWED: frozenset(
        {StrategyLifecycleStatus.BACKTESTED, StrategyLifecycleStatus.RETIRED}
    ),
    StrategyLifecycleStatus.BACKTESTED: frozenset(
        {StrategyLifecycleStatus.PAPER_APPROVED, StrategyLifecycleStatus.RETIRED}
    ),
    StrategyLifecycleStatus.PAPER_APPROVED: frozenset(
        {StrategyLifecycleStatus.ACTIVE, StrategyLifecycleStatus.RETIRED}
    ),
    StrategyLifecycleStatus.ACTIVE: frozenset({StrategyLifecycleStatus.PAUSED}),
    StrategyLifecycleStatus.PAUSED: frozenset(
        {StrategyLifecycleStatus.ACTIVE, StrategyLifecycleStatus.RETIRED}
    ),
    StrategyLifecycleStatus.RETIRED: frozenset(),
}


def ensure_lifecycle_transition(
    current: StrategyLifecycleStatus,
    target: StrategyLifecycleStatus,
) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"不合法的策略版本狀態轉移：{current.value} -> {target.value}")
