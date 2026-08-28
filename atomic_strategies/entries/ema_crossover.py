"""Atomic entry strategy: parameterized EMA cross-up."""

from __future__ import annotations

import hashlib
from datetime import time
from typing import Any, Mapping

from atomic_strategies.protocol import (
    AtomicEvaluationStatus,
    AtomicStrategyContext,
    AtomicStrategyEvaluation,
)
from strategy_catalog.domain import SessionPhase, StrategyRole
from strategy_catalog.drafts import StrategyTemplate
from strategy_catalog.parameter_schema import ParameterSchema, validate_entry_window


def _validate_ema_parameters(parameters: Mapping[str, Any]) -> None:
    validate_entry_window(parameters)
    if int(parameters["fast_period"]) >= int(parameters["slow_period"]):
        raise ValueError("fast_period 必須小於 slow_period")


PARAMETER_SCHEMA = ParameterSchema(
    version="ema-crossover-parameters-v1",
    fields={
        "fast_period": {
            "label": "快速 EMA 週期",
            "help": "快速 EMA 使用的完整一分鐘 Kbar 根數。",
            "type": "integer",
            "unit": "根",
            "minimum": 2,
            "maximum": 60,
            "default": 5,
        },
        "slow_period": {
            "label": "慢速 EMA 週期",
            "help": "慢速 EMA 使用的完整一分鐘 Kbar 根數，必須大於快速週期。",
            "type": "integer",
            "unit": "根",
            "minimum": 3,
            "maximum": 120,
            "default": 20,
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:20",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "12:45",
        },
    },
    cross_validators=(_validate_ema_parameters,),
)


class EmaCrossoverEntryStrategy:
    template = StrategyTemplate(
        strategy_id="ema_crossover_entry",
        display_name_zh_tw="EMA 黃金交叉",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"ema-crossover-entry-kernel-v1"
        ).hexdigest(),
        parameter_schema=PARAMETER_SCHEMA,
        required_capabilities=(
            "OHLCV",
            "KBAR_INTRADAY",
            "KBAR_1M",
            "SESSION_BOUNDARIES",
        ),
        feature_requirements=(
            {
                "feature_id": "ema_cross_up_v1",
                "parameters": {},
                "parameter_bindings": {
                    "fast_period": "fast_period",
                    "slow_period": "slow_period",
                },
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "ema_crossover.backtest_kbar_1m_v1",
            "LOCAL_PAPER_TICK_BIDASK": (
                "ema_crossover.local_paper_completed_kbar_v1"
            ),
        },
        description_zh_tw=(
            "快速 EMA 從下方穿越慢速 EMA 的當根完整一分鐘 Kbar 觸發一次。"
        ),
    )

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation:
        parameters = self.template.validate_parameters(context.parameters)
        event_time = context.event_at.timetz().replace(tzinfo=None)
        start = time.fromisoformat(str(parameters["entry_window_start"]))
        end = time.fromisoformat(str(parameters["entry_window_end"]))
        if not start <= event_time < end:
            return self._result(
                context,
                AtomicEvaluationStatus.BLOCKED,
                "不在允許進場時間",
            )

        crossing = context.features.values.get("ema_cross_up_v1")
        if crossing is None:
            reason = context.features.missing_reasons.get(
                "ema_cross_up_v1",
                "EMA 尚未完成暖機",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )
        if not isinstance(crossing, bool):
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                "EMA crossover evidence 型別不正確",
            )

        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if crossing
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "快速 EMA 向上穿越慢速 EMA" if crossing else "本根沒有 EMA 向上穿越",
            observed={
                "crossed_up": crossing,
                "fast_period": parameters["fast_period"],
                "slow_period": parameters["slow_period"],
            },
        )

    def _result(
        self,
        context: AtomicStrategyContext,
        status: AtomicEvaluationStatus,
        reason: str,
        *,
        observed: Mapping[str, Any] | None = None,
    ) -> AtomicStrategyEvaluation:
        return AtomicStrategyEvaluation(
            strategy_id=self.template.strategy_id,
            strategy_version_id=context.strategy_version_id,
            status=status,
            symbol=context.symbol,
            event_at=context.event_at,
            reason=reason,
            observed=observed or {},
        )
