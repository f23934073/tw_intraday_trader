"""Versioned, bar-compatible entry and exit strategies for historical runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from backtest.domain import (
    ExecutionHorizon,
    EvaluationStatus,
    HistoricalBar,
    StrategyDefinition,
    StrategyEvaluation,
    StrategySide,
)
from backtest.daily_features import DailySmaFeatureSnapshot
from backtest.features import BarFeatureSnapshot, PositionStrategyContext
from strategy_catalog.domain import SessionPhase, StrategyStatus


_INTRADAY_1M_CAPABILITIES = (
    "OHLCV",
    "KBAR_INTRADAY",
    "KBAR_1M",
    "SESSION_BOUNDARIES",
)


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
    features: BarFeatureSnapshot | None = None
    previous_features: BarFeatureSnapshot | None = None
    position: PositionStrategyContext | None = None
    daily_features: DailySmaFeatureSnapshot | None = None
    previous_daily_features: DailySmaFeatureSnapshot | None = None
    resolved_session_date: date | None = None
    is_terminal_dataset_bar: bool = False


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
    execution_horizon: ExecutionHorizon | None = None,
) -> StrategyEvaluation:
    if execution_horizon is None:
        raw_horizon = definition.parameters.get("execution_horizon")
        if raw_horizon is not None:
            execution_horizon = ExecutionHorizon(str(raw_horizon))
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
        execution_horizon=execution_horizon,
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


class OpeningRangeBreakoutEntryStrategy:
    definition = StrategyDefinition(
        strategy_id="opening_range_breakout_entry_v1",
        display_name_zh_tw="開盤區間突破買入策略",
        side=StrategySide.ENTRY,
        version="v1",
        session_phase=SessionPhase.OPENING,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="使用完整 09:00～09:14 一分鐘 Kbar 區間，於上午突破時產生買入訊號。",
        execution_binding="backtest.opening_range_breakout_entry_v1",
        required_capabilities=_INTRADAY_1M_CAPABILITIES,
        parameters={
            "opening_range_minutes": 15,
            "breakout_buffer_pct": "0.001",
            "entry_window_start": "09:15",
            "entry_window_end": "11:00",
            "require_complete_opening_range": True,
        },
        tags=("一分K", "突破", "實驗中"),
        code_identity="opening-range-breakout-entry-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        features = context.features
        minute = (context.bar.timestamp.hour, context.bar.timestamp.minute)
        if features is None or features.opening_range_status != "COMPLETE":
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "09:00～09:14 開盤區間的一分鐘 Kbar 不完整",
                observed={
                    "opening_range_status": features.opening_range_status if features else "MISSING",
                    "opening_bar_count": features.opening_bar_count if features else 0,
                },
            )
        if minute < (9, 15):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "開盤區間尚未完成",
                observed={"opening_bar_count": features.opening_bar_count},
            )
        if minute >= (11, 0):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.NOT_TRIGGERED,
                "已超過開盤區間突破進場時間",
                observed={"window": "09:15-11:00"},
            )
        assert features.opening_range_high is not None
        assert features.opening_range_low is not None
        breakout_price = features.opening_range_high * Decimal("1.001")
        triggered = context.bar.close >= breakout_price
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "收盤價突破完整開盤區間" if triggered else "收盤價尚未突破完整開盤區間",
            observed={
                "opening_range_high": float(features.opening_range_high),
                "opening_range_low": float(features.opening_range_low),
                "opening_bar_count": features.opening_bar_count,
                "close": float(context.bar.close),
                "window": "09:15-11:00",
            },
            threshold={"breakout_price": float(breakout_price), "buffer_pct": 0.1},
        )


class EmaCrossoverEntryStrategy:
    definition = StrategyDefinition(
        strategy_id="ema_crossover_entry_v1",
        display_name_zh_tw="EMA 黃金交叉買入策略",
        side=StrategySide.ENTRY,
        version="v1",
        session_phase=SessionPhase.INTRADAY,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="當 session 內 EMA(5) 由下往上穿越 EMA(20) 時產生買入訊號。",
        execution_binding="backtest.ema_crossover_entry_v1",
        required_capabilities=_INTRADAY_1M_CAPABILITIES,
        parameters={
            "fast_period": 5,
            "slow_period": 20,
            "reset_each_session": True,
            "entry_window_end": "12:45",
        },
        tags=("一分K", "趨勢", "實驗中"),
        code_identity="ema-crossover-entry-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if (context.bar.timestamp.hour, context.bar.timestamp.minute) >= (12, 45):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.NOT_TRIGGERED,
                "已超過 EMA 進場時間",
            )
        current = context.features
        previous = context.previous_features
        values = (
            current.ema_fast if current else None,
            current.ema_slow if current else None,
            previous.ema_fast if previous else None,
            previous.ema_slow if previous else None,
        )
        if any(value is None for value in values):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "EMA(5)／EMA(20) 尚未完成 current 與 previous warm-up",
                observed={"bars_seen": current.bars_seen if current else 0},
            )
        assert current is not None and previous is not None
        assert current.ema_fast is not None and current.ema_slow is not None
        assert previous.ema_fast is not None and previous.ema_slow is not None
        triggered = previous.ema_fast <= previous.ema_slow and current.ema_fast > current.ema_slow
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "EMA(5) 向上穿越 EMA(20)" if triggered else "本根 Kbar 未發生 EMA 向上交叉",
            observed={
                "previous_fast": float(previous.ema_fast),
                "previous_slow": float(previous.ema_slow),
                "current_fast": float(current.ema_fast),
                "current_slow": float(current.ema_slow),
            },
        )


class RsiBollingerReversionEntryStrategy:
    definition = StrategyDefinition(
        strategy_id="rsi_bollinger_reversion_entry_v0",
        display_name_zh_tw="RSI／布林通道均值回歸買入策略",
        side=StrategySide.ENTRY,
        version="v0",
        session_phase=SessionPhase.INTRADAY,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="前一根超賣且跌出布林下軌，本根收回下軌時產生研究用買入訊號。",
        execution_binding="backtest.rsi_bollinger_reversion_entry_v0",
        required_capabilities=_INTRADAY_1M_CAPABILITIES,
        parameters={
            "rsi_period": 14,
            "rsi_oversold": 30,
            "bollinger_period": 20,
            "bollinger_stddev": 2,
            "confirmation": "REENTER_LOWER_BAND",
            "reset_each_session": True,
            "entry_window_end": "12:45",
        },
        tags=("一分K", "均值回歸", "實驗中"),
        code_identity="rsi-bollinger-reversion-entry-v0",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        if (context.bar.timestamp.hour, context.bar.timestamp.minute) >= (12, 45):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.NOT_TRIGGERED,
                "已超過均值回歸進場時間",
            )
        current = context.features
        previous = context.previous_features
        if (
            current is None
            or previous is None
            or current.bollinger_lower is None
            or previous.bollinger_lower is None
            or previous.rsi is None
        ):
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "RSI 或 Bollinger Bands 尚未完成 warm-up",
                observed={"bars_seen": current.bars_seen if current else 0},
            )
        previous_close = previous.close
        oversold_outside = previous_close < previous.bollinger_lower and previous.rsi <= Decimal(30)
        reentered = context.bar.close >= current.bollinger_lower
        triggered = oversold_outside and reentered
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "超賣後收回布林下軌" if triggered else "尚未同時滿足前根超賣出軌與本根收回",
            observed={
                "previous_close": float(previous_close),
                "previous_lower_band": float(previous.bollinger_lower),
                "previous_rsi": float(previous.rsi),
                "current_close": float(context.bar.close),
                "current_lower_band": float(current.bollinger_lower),
            },
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


class AtrStopExitStrategy:
    definition = StrategyDefinition(
        strategy_id="atr_stop_exit_v1",
        display_name_zh_tw="ATR 固定停損策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.POSITION_LIFECYCLE,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="以 entry signal bar 的 ATR 固定計算停損價，觸及後於下一根 Kbar 開盤退出。",
        execution_binding="backtest.atr_stop_exit_v1",
        required_capabilities=_INTRADAY_1M_CAPABILITIES,
        parameters={
            "atr_period": 14,
            "atr_multiplier": "1.5",
            "atr_reference": "ENTRY_SIGNAL_BAR",
            "execution_model": "NEXT_BAR_OPEN",
        },
        tags=("一分K", "風險", "實驗中"),
        code_identity="atr-stop-exit-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        position = context.position
        if position is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.BLOCKED,
                "尚未建立持倉，不能評估 ATR 停損",
            )
        if position.entry_signal_atr is None or position.fixed_atr_stop_price is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.INSUFFICIENT_DATA,
                "Entry signal bar 缺少完成 warm-up 的 ATR",
            )
        triggered = context.bar.low <= position.fixed_atr_stop_price
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "Kbar 低點觸及固定 ATR 停損價" if triggered else "尚未觸及固定 ATR 停損價",
            observed={
                "low": float(context.bar.low),
                "entry_fill_price": float(position.entry_fill_price),
                "entry_signal_atr": float(position.entry_signal_atr),
            },
            threshold={
                "stop_price": float(position.fixed_atr_stop_price),
                "atr_multiplier": 1.5,
            },
        )


class TimeStopExitStrategy:
    definition = StrategyDefinition(
        strategy_id="time_stop_exit_v1",
        display_name_zh_tw="持倉時間退出策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.POSITION_LIFECYCLE,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="持倉第 12 根完整一分鐘 Kbar 結束時產生退出訊號。",
        execution_binding="backtest.time_stop_exit_v1",
        required_capabilities=_INTRADAY_1M_CAPABILITIES,
        parameters={
            "max_completed_holding_bars": 12,
            "bar_interval_seconds": 60,
            "execution_model": "NEXT_BAR_OPEN",
        },
        tags=("一分K", "時間退出", "實驗中"),
        code_identity="time-stop-exit-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        position = context.position
        if position is None:
            return _evaluation(
                self.definition,
                context,
                EvaluationStatus.BLOCKED,
                "尚未建立持倉，不能評估持倉時間",
            )
        triggered = position.bars_held_completed >= 12
        return _evaluation(
            self.definition,
            context,
            EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
            "已完成第 12 根持倉 Kbar" if triggered else "尚未達 12 根完整持倉 Kbar",
            observed={"bars_held_completed": position.bars_held_completed},
            threshold={"max_completed_holding_bars": 12},
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


_DAILY_SMA_CAPABILITIES = ("OHLCV", "KBAR_DAILY")


def _daily_sma_evaluation(
    definition: StrategyDefinition,
    context: StrategyContext,
    *,
    upward: bool,
) -> StrategyEvaluation:
    current = context.daily_features
    previous = context.previous_daily_features
    values = (
        current.sma20 if current else None,
        current.sma60 if current else None,
        previous.sma20 if previous else None,
        previous.sma60 if previous else None,
    )
    if any(value is None for value in values):
        return _evaluation(
            definition,
            context,
            EvaluationStatus.INSUFFICIENT_DATA,
            "SMA20／SMA60 尚未完成 current 與 previous warm-up",
            observed={
                "daily_bars_seen": current.daily_bars_seen if current else 0,
                "resolved_session_date": (
                    context.resolved_session_date.isoformat()
                    if context.resolved_session_date is not None
                    else None
                ),
            },
        )
    assert current is not None and previous is not None
    assert current.sma20 is not None and current.sma60 is not None
    assert previous.sma20 is not None and previous.sma60 is not None
    triggered = (
        previous.sma20 <= previous.sma60 and current.sma20 > current.sma60
        if upward
        else previous.sma20 >= previous.sma60 and current.sma20 < current.sma60
    )
    return _evaluation(
        definition,
        context,
        EvaluationStatus.TRIGGERED if triggered else EvaluationStatus.NOT_TRIGGERED,
        "SMA20 向上穿越 SMA60" if upward and triggered
        else "SMA20 向下跌破 SMA60" if not upward and triggered
        else "本日未發生 SMA20／SMA60 交叉",
        observed={
            "previous_sma20": str(previous.sma20),
            "previous_sma60": str(previous.sma60),
            "current_sma20": str(current.sma20),
            "current_sma60": str(current.sma60),
            "daily_bars_seen": current.daily_bars_seen,
            "resolved_session_date": current.resolved_session_date.isoformat(),
            "feature_input_digest": current.input_digest,
            "cross_direction": "UP" if upward else "DOWN",
        },
    )


class Sma2060GoldenCrossEntryStrategy:
    definition = StrategyDefinition(
        strategy_id="sma_20_60_golden_cross_entry_v1",
        display_name_zh_tw="日K SMA20／SMA60 黃金交叉買入策略",
        side=StrategySide.ENTRY,
        version="v1",
        session_phase=SessionPhase.END_OF_DAY,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="完整日 K 收盤後，SMA20 由下往上穿越 SMA60 時建立隔日開盤買入訊號。",
        execution_binding="backtest.sma_20_60_golden_cross_entry_v1",
        required_capabilities=_DAILY_SMA_CAPABILITIES,
        parameters={
            "fast_period": 20,
            "slow_period": 60,
            "ma_type": "SMA",
            "bar_resolution": "DAILY",
            "price_field": "CLOSE",
            "price_adjustment_policy": "RAW",
            "signal_as_of": "COMPLETED_DAILY_CLOSE",
            "execution_horizon": "DAILY_NEXT_BAR",
            "feature_version": "daily-sma-features-v1",
        },
        tags=("日K", "均線", "研究中"),
        code_identity="daily-sma-20-60-golden-cross-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        return _daily_sma_evaluation(self.definition, context, upward=True)


class Sma2060DeathCrossExitStrategy:
    definition = StrategyDefinition(
        strategy_id="sma_20_60_death_cross_exit_v1",
        display_name_zh_tw="日K SMA20／SMA60 死亡交叉退出策略",
        side=StrategySide.EXIT,
        version="v1",
        session_phase=SessionPhase.END_OF_DAY,
        status=StrategyStatus.EXPERIMENTAL,
        description_zh_tw="完整日 K 收盤後，SMA20 由上往下跌破 SMA60 時建立隔日開盤退出訊號。",
        execution_binding="backtest.sma_20_60_death_cross_exit_v1",
        required_capabilities=_DAILY_SMA_CAPABILITIES,
        parameters={
            "fast_period": 20,
            "slow_period": 60,
            "ma_type": "SMA",
            "bar_resolution": "DAILY",
            "price_field": "CLOSE",
            "price_adjustment_policy": "RAW",
            "signal_as_of": "COMPLETED_DAILY_CLOSE",
            "execution_horizon": "DAILY_NEXT_BAR",
            "feature_version": "daily-sma-features-v1",
        },
        tags=("日K", "均線", "研究中"),
        code_identity="daily-sma-20-60-death-cross-v1",
    )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        return _daily_sma_evaluation(self.definition, context, upward=False)


class StrategyRegistry:
    """Only registered, server-side strategy implementations are executable."""

    def __init__(self, additional_strategies: tuple[BacktestStrategy, ...] = ()) -> None:
        builtin_strategies: tuple[BacktestStrategy, ...] = (
            GapVwapEntryStrategy(),
            MomentumBreakoutEntryStrategy(),
            OpeningRangeBreakoutEntryStrategy(),
            EmaCrossoverEntryStrategy(),
            RsiBollingerReversionEntryStrategy(),
            StopLossExitStrategy(),
            TakeProfitExitStrategy(),
            AtrStopExitStrategy(),
            TimeStopExitStrategy(),
            EndOfDayExitStrategy(),
            Sma2060GoldenCrossEntryStrategy(),
            Sma2060DeathCrossExitStrategy(),
        )
        strategies = builtin_strategies + tuple(additional_strategies)
        self._strategies = {
            str(getattr(strategy, "selection_id", strategy.definition.strategy_id)): strategy
            for strategy in strategies
        }
        if len(self._strategies) != len(strategies):
            raise ValueError("回測策略 selection identity 不可重複")

    def definitions(self) -> tuple[StrategyDefinition, ...]:
        return tuple(
            sorted(
                (strategy.definition for strategy in self._strategies.values()),
                key=lambda definition: (
                    definition.side.value,
                    definition.status is not StrategyStatus.ACTIVE,
                    definition.strategy_id,
                ),
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
