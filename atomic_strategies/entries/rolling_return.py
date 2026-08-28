"""Atomic entry strategy: parameterized completed-Kbar rolling return."""

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
    version="rolling-return-parameters-v1",
    fields={
        "window_minutes": {
            "label": "計算區間",
            "help": "使用目前完整 1 分 K 收盤價，和指定分鐘前的完整 Kbar 收盤價計算報酬。",
            "type": "integer",
            "unit": "分鐘",
            "minimum": 1,
            "maximum": 30,
            "default": 2,
        },
        "minimum_return_pct": {
            "label": "最低報酬率",
            "help": "滾動報酬率大於或等於此百分比時觸發。",
            "type": "decimal",
            "unit": "%",
            "minimum": "0.1",
            "maximum": "20",
            "default": "1.5",
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


class RollingReturnEntryStrategy:
    allow_legacy_backtest_only_template = True
    template = StrategyTemplate(
        strategy_id="rolling_return_entry",
        display_name_zh_tw="滾動報酬突破",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"rolling-return-entry-kernel-v1"
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
                "feature_id": "rolling_return_v1",
                "parameters": {},
                "parameter_bindings": {"window_minutes": "window_minutes"},
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "rolling_return.backtest_kbar_1m_v1",
            "LOCAL_PAPER_TICK_BIDASK": (
                "rolling_return.local_paper_completed_kbar_v1"
            ),
        },
        description_zh_tw=(
            "目前完整 1 分 K 收盤價相對 N 分鐘前完整 Kbar 的報酬率達門檻時觸發。"
        ),
    )

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation:
        parameters = self.template.validate_parameters(context.parameters)
        event_time = context.event_at.timetz().replace(tzinfo=None)
        start = time.fromisoformat(str(parameters["entry_window_start"]))
        end = time.fromisoformat(str(parameters["entry_window_end"]))
        if not start <= event_time < end:
            return self._result(context, AtomicEvaluationStatus.BLOCKED, "不在允許進場時間")

        raw_return = context.features.values.get("rolling_return_v1")
        if raw_return is None:
            reason = context.features.missing_reasons.get(
                "rolling_return_v1",
                "rolling return 尚未完成暖機",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )

        rolling_return = Decimal(str(raw_return))
        minimum_return_pct = Decimal(str(parameters["minimum_return_pct"]))
        threshold_ratio = minimum_return_pct / Decimal("100")
        triggered = rolling_return >= threshold_ratio
        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if triggered
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "滾動報酬達到門檻" if triggered else "滾動報酬尚未達門檻",
            observed={
                "window_minutes": parameters["window_minutes"],
                "rolling_return_ratio": str(rolling_return),
                "rolling_return_pct": str(rolling_return * Decimal("100")),
            },
            threshold={
                "minimum_return_pct": str(minimum_return_pct),
                "minimum_return_ratio": str(threshold_ratio),
            },
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
