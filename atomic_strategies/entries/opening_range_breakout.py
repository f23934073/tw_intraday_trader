"""Atomic entry strategy: parameterized opening-range breakout (ORB)."""

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


def _validate_orb_parameters(parameters: Mapping[str, Any]) -> None:
    validate_entry_window(parameters)
    opening_range_minutes = int(parameters["opening_range_minutes"])
    earliest = time(hour=9, minute=opening_range_minutes)
    entry_start = time.fromisoformat(str(parameters["entry_window_start"]))
    if entry_start < earliest:
        raise ValueError("entry_window_start 不可早於開盤區間完成時間")


PARAMETER_SCHEMA = ParameterSchema(
    version="opening-range-breakout-parameters-v1",
    fields={
        "opening_range_minutes": {
            "label": "開盤區間長度",
            "help": "從 09:00 起使用連續、完整的一分鐘 Kbar 建立開盤區間。",
            "type": "integer",
            "unit": "分鐘",
            "minimum": 5,
            "maximum": 30,
            "default": 15,
        },
        "breakout_buffer_pct": {
            "label": "突破緩衝",
            "help": "現價高於開盤區間最高價加上此百分比時觸發。",
            "type": "decimal",
            "unit": "%",
            "minimum": "0",
            "maximum": "5",
            "default": "0.1",
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:15",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "11:00",
        },
    },
    cross_validators=(_validate_orb_parameters,),
)


class OpeningRangeBreakoutEntryStrategy:
    template = StrategyTemplate(
        strategy_id="opening_range_breakout_entry",
        display_name_zh_tw="開盤區間突破 ORB",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.OPENING,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(
            b"opening-range-breakout-entry-kernel-v1"
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
                "feature_id": "opening_range_high_v1",
                "parameters": {},
                "parameter_bindings": {
                    "opening_range_minutes": "opening_range_minutes"
                },
            },
        ),
        runtime_bindings={
            "BACKTEST_KBAR_1M": "opening_range_breakout.backtest_kbar_1m_v1",
            "LOCAL_PAPER_TICK_BIDASK": (
                "opening_range_breakout.local_paper_completed_kbar_v1"
            ),
        },
        description_zh_tw=(
            "現價突破從 09:00 起 N 根連續完整一分鐘 Kbar 的最高價與緩衝時觸發。"
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

        raw_opening_high = context.features.values.get("opening_range_high_v1")
        if raw_opening_high is None:
            reason = context.features.missing_reasons.get(
                "opening_range_high_v1",
                "開盤區間尚未完整",
            )
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                reason,
            )

        opening_high = Decimal(str(raw_opening_high))
        current_price = Decimal(str(context.current_price))
        buffer_pct = Decimal(str(parameters["breakout_buffer_pct"]))
        breakout_price = opening_high * (
            Decimal("1") + buffer_pct / Decimal("100")
        )
        triggered = current_price > breakout_price
        return self._result(
            context,
            (
                AtomicEvaluationStatus.TRIGGERED
                if triggered
                else AtomicEvaluationStatus.NOT_TRIGGERED
            ),
            "價格突破開盤區間" if triggered else "價格尚未突破開盤區間",
            observed={
                "current_price": str(current_price),
                "opening_range_high": str(opening_high),
                "opening_range_minutes": parameters["opening_range_minutes"],
            },
            threshold={
                "breakout_price": str(breakout_price),
                "breakout_buffer_pct": str(buffer_pct),
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
