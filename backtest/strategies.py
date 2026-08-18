"""Versioned, bar-compatible entry and exit strategies for historical runs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backtest.domain import (
    EvaluationStatus,
    HistoricalBar,
    StrategyDefinition,
    StrategyEvaluation,
    StrategySide,
)
from strategy_catalog.domain import SessionPhase


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    bar: HistoricalBar
    previous_close: Decimal | None
    session_open: Decimal
    session_high_before: Decimal | None
    vwap: Decimal | None
    cumulative_volume: int
    bars_seen: int
    is_last_bar: bool
    entry_price: Decimal | None = None


class BacktestStrategy(Protocol):
    definition: StrategyDefinition

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        ...


def _evaluation(
    definition: StrategyDefinition,
    context: StrategyContext,
    status: EvaluationStatus,
    reason: str,
    *,
    observed: dict[str, object] | None = None,
    threshold: dict[str, object] | None = None,
) -> StrategyEvaluation:
    return StrategyEvaluation(
        strategy_id=definition.strategy_id,
        strategy_name=definition.display_name_zh_tw,
        strategy_version=definition.version,
        side=definition.side,
        status=status,
        symbol=context.symbol,
        event_at=context.bar.timestamp,
        reason=reason,
        observed=observed or {},
        threshold=threshold or dict(definition.parameters),
    )


class GapVwapEntryStrategy:
    definition = StrategyDefinition(
        strategy_id="legacy_gap_volume_vwap_entry_v1",
        display_name_zh_tw="跳空＋VWAP 買入策略",
        side=StrategySide.ENTRY,
        version="v1",
        session_phase=SessionPhase.OPENING,
        description_zh_tw="開盤後以跳空、成交量與 VWAP 證據判斷是否進入買入決策。",
        execution_binding="backtest.legacy_gap_volume_vwap_entry_v1",
        parameters={
            "gap_up_min_pct": "0.02",
            "gap_up_max_pct": "0.04",
            "high_volume_min_shares": 100_000,
            "candidate_policy": "GAP_UP_OR_HIGH_VOLUME",
            "buy_score_threshold": 40,
            "require_close_above_vwap": True,
        },
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if context.previous_close is None or context.previous_close <= 0:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "缺少前一交易日收盤價，無法計算跳空",
            )
        if context.vwap is None or context.vwap <= 0:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "缺少可計算的 VWAP",
            )
        gap_pct = (context.session_open - context.previous_close) / context.previous_close
        gap_up = Decimal("0.02") <= gap_pct <= Decimal("0.04")
        high_volume = context.cumulative_volume >= 100_000
        candidate_matched = gap_up or high_volume
        # The current binary BuyScore requires both the GapScore and
        # AboveVWAP score.  HighVolume admits a symbol into the candidate pool,
        # but cannot independently turn a 0/40 candidate into an entry.
        triggered = candidate_matched and gap_up and context.bar.close > context.vwap
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "Candidate（跳空或高成交量）且 BuyScore 40/40"
            if triggered
            else "Candidate／GapScore／AboveVWAP 未同時達到 BuyScore 40/40",
            observed={
                "gap_pct": float(gap_pct * Decimal("100")),
                "gap_up": gap_up,
                "cumulative_volume": context.cumulative_volume,
                "high_volume": high_volume,
                "candidate_matched": candidate_matched,
                "close": float(context.bar.close),
                "vwap": float(context.vwap),
            },
            threshold={
                "gap_up_pct": [2.0, 4.0],
                "high_volume_min_shares": 100_000,
                "candidate_policy": "GAP_UP_OR_HIGH_VOLUME",
                "buy_score_threshold": 40,
                "close_strictly_above_vwap": True,
            },
        )


class MomentumBreakoutEntryStrategy:
    """Explicit bar-compatible Momentum version, not a claim of live L1 parity."""

    definition = StrategyDefinition(
        strategy_id="momentum_breakout_entry_v1",
        display_name_zh_tw="盤中突破動能買入策略",
        side=StrategySide.ENTRY,
        version="v1",
        session_phase=SessionPhase.INTRADAY,
        description_zh_tw="盤中收盤價突破已形成的當日高點後產生買入訊號。",
        execution_binding="backtest.momentum_breakout_entry_v1",
        parameters={"min_bars": 3, "breakout_pct": "0.001"},
        code_identity="bar-compatible-momentum-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if context.bars_seen < 3 or context.session_high_before is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "至少需要三根已完成 Kbar 才能評估盤中突破",
                observed={"bars_seen": context.bars_seen},
                threshold={"min_bars": 3},
            )
        threshold_price = context.session_high_before * Decimal("1.001")
        triggered = context.bar.close >= threshold_price
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "收盤突破前高 0.1%" if triggered else "尚未突破前高 0.1%",
            observed={
                "close": float(context.bar.close),
                "session_high_before": float(context.session_high_before),
            },
            threshold={"breakout_price": float(threshold_price)},
        )


class StopLossExitStrategy:
    definition = StrategyDefinition(
        strategy_id="stop_loss_exit_v1",
        display_name_zh_tw="停損策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.POSITION_LIFECYCLE,
        description_zh_tw="持倉 Kbar 低點觸及進場價下方 2% 時產生停損訊號。",
        execution_binding="backtest.stop_loss_exit_v1",
        parameters={"stop_loss_pct": "0.02"},
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if context.entry_price is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.BLOCKED,
                "尚未建立持倉，不能評估停損",
            )
        stop_price = context.entry_price * Decimal("0.98")
        triggered = context.bar.low <= stop_price
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "Kbar 低點觸及停損價" if triggered else "尚未觸及停損價",
            observed={"low": float(context.bar.low), "entry_price": float(context.entry_price)},
            threshold={"stop_price": float(stop_price), "stop_loss_pct": 2.0},
        )


class TakeProfitExitStrategy:
    definition = StrategyDefinition(
        strategy_id="take_profit_exit_v1",
        display_name_zh_tw="停利策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.POSITION_LIFECYCLE,
        description_zh_tw="持倉 Kbar 高點觸及進場價上方 3% 時產生停利訊號。",
        execution_binding="backtest.take_profit_exit_v1",
        parameters={"take_profit_pct": "0.03"},
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if context.entry_price is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.BLOCKED,
                "尚未建立持倉，不能評估停利",
            )
        take_price = context.entry_price * Decimal("1.03")
        triggered = context.bar.high >= take_price
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "Kbar 高點觸及停利價" if triggered else "尚未觸及停利價",
            observed={"high": float(context.bar.high), "entry_price": float(context.entry_price)},
            threshold={"take_price": float(take_price), "take_profit_pct": 3.0},
        )


class EndOfDayExitStrategy:
    definition = StrategyDefinition(
        strategy_id="end_of_day_exit_v1",
        display_name_zh_tw="收盤前強制平倉策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.END_OF_DAY,
        description_zh_tw="在每個標的最後一根 Kbar 產生收盤前強制平倉訊號。",
        execution_binding="backtest.end_of_day_exit_v1",
        parameters={"force_close": True},
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if context.is_last_bar else EvaluationStatus.NOT_TRIGGERED,
            "本交易日最後一根 Kbar，建立收盤強制平倉" if context.is_last_bar else "尚未到收盤",
            observed={"is_last_bar": context.is_last_bar},
            threshold={"force_close": True},
        )


class StrategyRegistry:
    """Only registered, server-side strategy implementations are executable."""

    def __init__(self) -> None:
        strategies: tuple[BacktestStrategy, ...] = (
            GapVwapEntryStrategy(),
            MomentumBreakoutEntryStrategy(),
            StopLossExitStrategy(),
            TakeProfitExitStrategy(),
            EndOfDayExitStrategy(),
        )
        self._strategies = {strategy.definition.strategy_id: strategy for strategy in strategies}

    def definitions(self) -> tuple[StrategyDefinition, ...]:
        return tuple(
            sorted(
                (strategy.definition for strategy in self._strategies.values()),
                key=lambda definition: (definition.side.value, definition.strategy_id),
            )
        )

    def definition(self, strategy_id: str) -> StrategyDefinition:
        try:
            return self._strategies[strategy_id].definition
        except KeyError as error:
            raise ValueError(f"未註冊的回測策略：{strategy_id}") from error

    def evaluate(self, strategy_id: str, context: StrategyContext) -> StrategyEvaluation:
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise ValueError(f"未註冊的回測策略：{strategy_id}")
        return strategy.evaluate(context)
