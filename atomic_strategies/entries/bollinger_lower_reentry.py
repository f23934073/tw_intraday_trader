"""Atomic entry strategy: parameterized Bollinger lower-band re-entry."""

from __future__ import annotations

import hashlib
from datetime import time

from atomic_strategies.protocol import (
    AtomicEvaluationStatus,
    AtomicStrategyContext,
    AtomicStrategyEvaluation,
)
from strategy_catalog.domain import SessionPhase, StrategyRole
from strategy_catalog.drafts import StrategyTemplate
from strategy_catalog.parameter_schema import ParameterSchema, validate_entry_window


PARAMETER_SCHEMA = ParameterSchema(
    version="bollinger-lower-reentry-parameters-v1",
    fields={
        "bollinger_period": {
            "label": "Bollinger 週期",
            "help": "中軌與 population standard deviation 使用的完整一分鐘 Kbar 根數。",
            "type": "integer",
            "unit": "根",
            "minimum": 2,
            "maximum": 120,
            "default": 20,
        },
        "stddev_multiplier": {
            "label": "標準差倍數",
            "help": "下軌等於中軌減去此倍數的 population standard deviation。",
            "type": "decimal",
            "unit": "倍",
            "minimum": "0.1",
            "maximum": "10",
            "default": "2",
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
    cross_validators=(validate_entry_window,),
)


class BollingerLowerReentryEntryStrategy:
    template = StrategyTemplate(
        strategy_id="bollinger_lower_reentry_entry",
        display_name_zh_tw="Bollinger 下軌回歸",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"bollinger-lower-reentry-entry-kernel-v1"
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
                "feature_id": "bollinger_lower_reentry_v1",
                "parameters": {},
                "parameter_bindings": {
                    "bollinger_period": "bollinger_period",
                    "stddev_multiplier": "stddev_multiplier",
                },
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": (
                "bollinger_lower_reentry.backtest_kbar_1m_v1"
            ),
            "LOCAL_PAPER_TICK_BIDASK": (
                "bollinger_lower_reentry.local_paper_completed_kbar_v1"
            ),
        },
        description_zh_tw=(
            "上一根收盤在 Bollinger 下軌外，這一根完整一分鐘 Kbar 收盤回到下軌以上時觸發一次。"
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

        reentered = context.features.values.get("bollinger_lower_reentry_v1")
        if reentered is None:
            reason = context.features.missing_reasons.get(
                "bollinger_lower_reentry_v1",
                "Bollinger Bands 尚未完成暖機",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )
        if not isinstance(reentered, bool):
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                "Bollinger re-entry evidence 型別不正確",
            )

        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if reentered
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "收盤重新站回 Bollinger 下軌" if reentered else "本根沒有下軌回歸事件",
            observed={
                "reentered_lower_band": reentered,
                "bollinger_period": parameters["bollinger_period"],
                "stddev_multiplier": parameters["stddev_multiplier"],
            },
        )

    def _result(
        self,
        context: AtomicStrategyContext,
        status: AtomicEvaluationStatus,
        reason: str,
        *,
        observed=None,
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
