"""Atomic entry strategy: price breaks the prior intraday high."""

from __future__ import annotations

import hashlib
from datetime import time
from decimal import Decimal
from typing import Any, Mapping

from atomic_strategies.protocol import (
    AtomicEvaluationStatus,
    AtomicStrategyContext,
    AtomicStrategyEvaluation,
)
from strategy_catalog.domain import SessionPhase, StrategyRole
from strategy_catalog.drafts import StrategyTemplate
from strategy_catalog.parameter_schema import ParameterSchema, validate_entry_window


PARAMETER_SCHEMA = ParameterSchema(
    version="breakout-previous-high-parameters-v1",
    fields={
        "buffer_bps": {
            "label": "突破緩衝",
            "type": "decimal",
            "unit": "bps",
            "minimum": "0",
            "maximum": "500",
            "default": "0",
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:02",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "12:45",
        },
    },
    cross_validators=(validate_entry_window,),
)


class BreakoutPreviousHighEntryStrategy:
    template = StrategyTemplate(
        strategy_id="breakout_previous_high_entry",
        display_name_zh_tw="突破盤中前高",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(b"breakout-previous-high-entry-kernel-v1").hexdigest(),
        parameter_schema=PARAMETER_SCHEMA,
        required_capabilities=("OHLCV", "KBAR_INTRADAY", "KBAR_1M", "SESSION_BOUNDARIES"),
        feature_requirements=(
            {"feature_id": "previous_intraday_high_v1", "parameters": {}},
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "breakout_previous_high.backtest_kbar_1m_v1",
            "LOCAL_PAPER_TICK_BIDASK": (
                "breakout_previous_high.local_paper_tick_bidask_v1"
            ),
        },
        description_zh_tw=(
            "完整一分鐘 Kbar 收盤價突破本 session 先前已完成 Kbar 高點時觸發。"
        ),
    )

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation:
        parameters = self.template.validate_parameters(context.parameters)
        event_time = context.event_at.timetz().replace(tzinfo=None)
        start = time.fromisoformat(str(parameters["entry_window_start"]))
        end = time.fromisoformat(str(parameters["entry_window_end"]))
        if not start <= event_time < end:
            return self._result(context, AtomicEvaluationStatus.BLOCKED, "不在允許進場時間")
        raw_previous_high = context.features.values.get("previous_intraday_high_v1")
        if raw_previous_high is None:
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                "session 尚無前一個已完成高點",
            )
        price = Decimal(context.current_price)
        previous_high = Decimal(str(raw_previous_high))
        buffer_bps = Decimal(str(parameters["buffer_bps"]))
        threshold_price = previous_high * (Decimal("1") + buffer_bps / Decimal("10000"))
        triggered = price > threshold_price
        return self._result(
            context,
            AtomicEvaluationStatus.TRIGGERED if triggered else AtomicEvaluationStatus.NOT_TRIGGERED,
            "收盤價突破盤中前高" if triggered else "收盤價尚未突破盤中前高門檻",
            observed={"price": str(price), "previous_high": str(previous_high)},
            threshold={"breakout_price": str(threshold_price), "buffer_bps": str(buffer_bps)},
        )

    def _result(
        self,
        context: AtomicStrategyContext,
        status: AtomicEvaluationStatus,
        reason: str,
        *,
        observed: Mapping[str, Any] | None = None,
        threshold: Mapping[str, Any] | None = None,
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
