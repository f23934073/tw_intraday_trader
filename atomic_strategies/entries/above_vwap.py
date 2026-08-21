"""Atomic entry strategy: price is above the completed-session VWAP."""

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
    version="above-vwap-parameters-v1",
    fields={
        "minimum_distance_bps": {
            "label": "高於 VWAP 的最小距離",
            "type": "decimal",
            "unit": "bps",
            "minimum": "0",
            "maximum": "500",
            "default": "0",
        },
        "entry_window_start": {
            "label": "最早進場時間",
            "type": "time",
            "default": "09:01",
        },
        "entry_window_end": {
            "label": "最晚進場時間",
            "type": "time",
            "default": "12:45",
        },
    },
    cross_validators=(validate_entry_window,),
)


class AboveVwapEntryStrategy:
    template = StrategyTemplate(
        strategy_id="above_vwap_entry",
        display_name_zh_tw="站上 VWAP",
        role=StrategyRole.ENTRY,
        session_phase=SessionPhase.INTRADAY,
        implementation_version="v1",
        implementation_digest=hashlib.sha256(b"above-vwap-entry-kernel-v1").hexdigest(),
        parameter_schema=PARAMETER_SCHEMA,
        required_capabilities=("OHLCV", "KBAR_INTRADAY_1M"),
        feature_requirements=({"feature_id": "vwap_session_v1", "parameters": {}},),
        runtime_bindings={"BACKTEST_KBAR_1M": "above_vwap.backtest_kbar_1m_v1"},
        description_zh_tw="完整一分鐘 Kbar 收盤價高於當日已完成資料 VWAP 時觸發。",
    )

    def evaluate(self, context: AtomicStrategyContext) -> AtomicStrategyEvaluation:
        parameters = self.template.validate_parameters(context.parameters)
        event_time = context.event_at.timetz().replace(tzinfo=None)
        start = time.fromisoformat(str(parameters["entry_window_start"]))
        end = time.fromisoformat(str(parameters["entry_window_end"]))
        if not start <= event_time < end:
            return self._result(context, AtomicEvaluationStatus.BLOCKED, "不在允許進場時間")
        raw_vwap = context.features.values.get("vwap_session_v1")
        if raw_vwap is None:
            return self._result(
                context,
                AtomicEvaluationStatus.INSUFFICIENT_DATA,
                "尚無有效 session VWAP",
            )
        price = Decimal(context.current_price)
        vwap = Decimal(str(raw_vwap))
        minimum_distance_bps = Decimal(str(parameters["minimum_distance_bps"]))
        threshold = vwap * (Decimal("1") + minimum_distance_bps / Decimal("10000"))
        triggered = price > threshold
        return self._result(
            context,
            AtomicEvaluationStatus.TRIGGERED if triggered else AtomicEvaluationStatus.NOT_TRIGGERED,
            "收盤價站上 VWAP" if triggered else "收盤價尚未站上 VWAP 門檻",
            observed={"price": str(price), "vwap": str(vwap)},
            threshold={"minimum_price": str(threshold), "minimum_distance_bps": str(minimum_distance_bps)},
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
