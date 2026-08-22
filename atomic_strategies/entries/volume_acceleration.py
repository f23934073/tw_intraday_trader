"""Atomic entry strategy: parameterized completed-Kbar volume acceleration."""

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


def _validate_volume_parameters(parameters: Mapping[str, Any]) -> None:
    validate_entry_window(parameters)
    if int(parameters["minimum_complete_baseline_windows"]) > int(
        parameters["baseline_window_count"]
    ):
        raise ValueError(
            "minimum_complete_baseline_windows 不可大於 baseline_window_count"
        )


PARAMETER_SCHEMA = ParameterSchema(
    version="volume-acceleration-parameters-v1",
    fields={
        "window_minutes": {
            "label": "成交量計算區間",
            "help": "目前與基準都使用不重疊的完整 1 分 Kbar 視窗。",
            "type": "integer",
            "unit": "分鐘",
            "minimum": 1,
            "maximum": 30,
            "default": 2,
        },
        "baseline_window_count": {
            "label": "基準視窗數",
            "type": "integer",
            "unit": "個",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
        "minimum_complete_baseline_windows": {
            "label": "最少完整基準視窗",
            "help": (
                "只允許最舊端因開盤暖機不足而缺少視窗；"
                "中間缺少任何 1 分 Kbar 時不計算訊號。"
            ),
            "type": "integer",
            "unit": "個",
            "minimum": 1,
            "maximum": 10,
            "default": 4,
        },
        "baseline_method": {
            "label": "基準算法",
            "type": "string",
            "enum": ["MEDIAN"],
            "default": "MEDIAN",
        },
        "minimum_acceleration_ratio": {
            "label": "最低量能加速倍數",
            "help": "目前視窗成交量除以先前完整視窗成交量中位數。",
            "type": "decimal",
            "unit": "倍",
            "minimum": "0.1",
            "maximum": "20",
            "default": "1.5",
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:10",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "12:45",
        },
    },
    cross_validators=(_validate_volume_parameters,),
)


class VolumeAccelerationEntryStrategy:
    template = StrategyTemplate(
        strategy_id="volume_acceleration_entry",
        display_name_zh_tw="成交量加速",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"volume-acceleration-entry-kernel-v1"
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
                "feature_id": "rolling_volume_ratio_v1",
                "parameters": {},
                "parameter_bindings": {
                    "window_minutes": "window_minutes",
                    "baseline_window_count": "baseline_window_count",
                    "minimum_complete_baseline_windows": (
                        "minimum_complete_baseline_windows"
                    ),
                    "baseline_method": "baseline_method",
                },
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "volume_acceleration.backtest_kbar_1m_v1",
        },
        description_zh_tw=(
            "目前 N 分鐘成交量相對先前不重疊完整視窗中位數達門檻時觸發。"
        ),
    )

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation:
        parameters = self.template.validate_parameters(context.parameters)
        event_time = context.event_at.timetz().replace(tzinfo=None)
        start = time.fromisoformat(str(parameters["entry_window_start"]))
        end = time.fromisoformat(str(parameters["entry_window_end"]))
        if not start <= event_time < end:
            return self._result(context, AtomicEvaluationStatus.BLOCKED, "不在允許進場時間")

        raw_ratio = context.features.values.get("rolling_volume_ratio_v1")
        if raw_ratio is None:
            reason = context.features.missing_reasons.get(
                "rolling_volume_ratio_v1",
                "volume acceleration 尚未完成暖機",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )

        ratio = Decimal(str(raw_ratio))
        threshold = Decimal(str(parameters["minimum_acceleration_ratio"]))
        triggered = ratio >= threshold
        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if triggered
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "成交量加速達到門檻" if triggered else "成交量加速尚未達門檻",
            observed={
                "window_minutes": parameters["window_minutes"],
                "volume_acceleration_ratio": str(ratio),
            },
            threshold={"minimum_acceleration_ratio": str(threshold)},
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
