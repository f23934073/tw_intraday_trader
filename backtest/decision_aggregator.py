"""Deterministic aggregation of independently evaluated strategies."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable

from backtest.domain import (
    AggregationPolicy,
    EvaluationStatus,
    StrategyEvaluation,
    StrategySide,
    TradeDecision,
)


class DecisionAggregator:
    def aggregate(
        self,
        *,
        symbol: str,
        event_at: datetime,
        side: StrategySide,
        policy: AggregationPolicy,
        minimum_trigger_count: int,
        selected_strategy_ids: tuple[str, ...],
        priority_order: tuple[str, ...],
        evaluations: Iterable[StrategyEvaluation],
        strategy_set_digest: str,
    ) -> TradeDecision | None:
        items = tuple(evaluations)
        by_id = {item.strategy_id: item for item in items}
        selected = tuple(by_id[item] for item in selected_strategy_ids if item in by_id)
        triggered = tuple(item for item in selected if item.status is EvaluationStatus.TRIGGERED)
        if not self._matches(policy, minimum_trigger_count, selected, triggered):
            return None
        primary = self._primary(triggered, priority_order)
        identity = "|".join(
            (symbol, event_at.isoformat(), side.value, strategy_set_digest)
        )
        decision_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        return TradeDecision(
            decision_id=decision_id,
            symbol=symbol,
            side=side,
            event_at=event_at,
            policy=policy,
            triggered_strategy_ids=tuple(item.strategy_id for item in triggered),
            primary_strategy_id=primary.strategy_id,
            evaluations=items,
        )

    @staticmethod
    def _matches(
        policy: AggregationPolicy,
        minimum_trigger_count: int,
        selected: tuple[StrategyEvaluation, ...],
        triggered: tuple[StrategyEvaluation, ...],
    ) -> bool:
        if not selected:
            return False
        if policy is AggregationPolicy.ANY:
            return bool(triggered)
        if policy is AggregationPolicy.ALL:
            return len(triggered) == len(selected)
        return len(triggered) >= minimum_trigger_count

    @staticmethod
    def _primary(
        triggered: tuple[StrategyEvaluation, ...],
        priority_order: tuple[str, ...],
    ) -> StrategyEvaluation:
        priority = {strategy_id: index for index, strategy_id in enumerate(priority_order)}
        return sorted(
            triggered,
            key=lambda value: (priority.get(value.strategy_id, len(priority)), value.strategy_id),
        )[0]
