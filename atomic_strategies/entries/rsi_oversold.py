"""Atomic entry strategy: parameterized Wilder RSI oversold condition."""

from __future__ import annotations

import hashlib
from datetime import time
from decimal import Decimal

from atomic_strategies.protocol import (
    AtomicEvaluationStatus,
    AtomicStrategyContext,
    AtomicStrategyEvaluation,
)
from strategy_catalog.domain import SessionPhase, StrategyRole
from strategy_catalog.drafts import StrategyTemplate
from strategy_catalog.parameter_schema import ParameterSchema, validate_entry_window


PARAMETER_SCHEMA = ParameterSchema(
    version="rsi-oversold-parameters-v1",
    fields={
        "rsi_period": {
            "label": "RSI 週期",
            "help": "Wilder RSI 使用的完整一分鐘 Kbar 差分數。",
            "type": "integer",
            "unit": "根差分",
            "minimum": 2,
            "maximum": 120,
            "default": 14,
        },
        "oversold_threshold": {
            "label": "超賣門檻",
            "help": "目前 RSI 等於或低於此值時觸發。",
            "type": "decimal",
            "unit": "RSI",
            "minimum": "0",
            "maximum": "50",
            "default": "30",
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:15",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "12:45",
        },
    },
    cross_validators=(validate_entry_window,),
)


class RsiOversoldEntryStrategy:
    template = StrategyTemplate(
        strategy_id="rsi_oversold_entry",
        display_name_zh_tw="RSI 超賣",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"rsi-oversold-entry-kernel-v1"
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
                "feature_id": "wilder_rsi_v1",
                "parameters": {},
                "parameter_bindings": {"rsi_period": "rsi_period"},
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "rsi_oversold.backtest_kbar_1m_v1",
            "LOCAL_PAPER_TICK_BIDASK": (
                "rsi_oversold.local_paper_completed_kbar_v1"
            ),
        },
        description_zh_tw=(
            "目前完整一分鐘 Kbar 的 Wilder RSI 等於或低於門檻時觸發。"
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

        raw_rsi = context.features.values.get("wilder_rsi_v1")
        if raw_rsi is None:
            reason = context.features.missing_reasons.get(
                "wilder_rsi_v1",
                "RSI 尚未完成暖機",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )

        rsi = Decimal(str(raw_rsi))
        threshold = Decimal(str(parameters["oversold_threshold"]))
        triggered = rsi <= threshold
        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if triggered
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "RSI 位於超賣區" if triggered else "RSI 尚未進入超賣區",
            observed={
                "rsi": str(rsi),
                "rsi_period": parameters["rsi_period"],
            },
            threshold={"oversold_threshold": str(threshold)},
        )

    def _result(
        self,
        context: AtomicStrategyContext,
        status: AtomicEvaluationStatus,
        reason: str,
        *,
        observed=None,
        threshold=None,
    ) -> AtomicStrategyEvaluation:
        return AtomicStrategyEvaluation(
            strategy_id=self.template.strategy_id,
            strategy_version_id=context.strategy_version_id,
            status=status,
            symbol=context.symbol,
            event_at=context.event_at,
            reason=reason,
            observed=observed or {},
            threshold=threshold or {},
        )
