"""Deterministic long-only Kbar backtest engine with next-bar execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Iterable

from backtest.decision_aggregator import DecisionAggregator
from backtest.daily_features import DailySmaFeatureState
from backtest.domain import (
    BacktestRunConfig,
    ClosedTrade,
    HistoricalBar,
    HistoricalFill,
    ExecutionHorizon,
    StrategyEvaluation,
    StrategySide,
    TradeDecision,
    digest,
    lot_floor,
)
from backtest.features import BarFeatureState, PositionStrategyContext
from backtest.strategies import StrategyContext, StrategyRegistry


ProgressCallback = Callable[[float, str], None]
Cancelled = Callable[[], bool]


class BacktestCancelled(RuntimeError):
    """Raised only at deterministic event boundaries when a run is cancelled."""


@dataclass
class _DayState:
    session_open: Decimal
    cumulative_volume: int = 0
    cumulative_amount: Decimal = Decimal("0")
    session_high: Decimal | None = None
    bars_seen: int = 0
    entered_today: bool = False

    def update(self, bar: HistoricalBar) -> Decimal:
        self.cumulative_volume += bar.volume
        self.cumulative_amount += (bar.amount or bar.close * bar.volume)
        self.bars_seen += 1
        self.session_high = bar.high if self.session_high is None else max(self.session_high, bar.high)
        if self.cumulative_volume <= 0:
            return bar.close
        return self.cumulative_amount / self.cumulative_volume


@dataclass
class _PendingOrder:
    order_id: str
    decision: TradeDecision
    side: StrategySide
    shares: int | None
    created_at: datetime
    entry_signal_atr: Decimal | None = None
    execution_horizon: ExecutionHorizon | None = None
    created_session_date: date | None = None
    status: str = "SUBMITTED"


@dataclass
class _Position:
    symbol: str
    name: str
    shares: int
    entry_fill: HistoricalFill
    entry_decision: TradeDecision
    entry_event_at: datetime
    entry_event_index: int
    entry_signal_atr: Decimal | None = None


@dataclass(frozen=True)
class DailyEquityPoint:
    session_date: date
    equity: Decimal
    cash: Decimal
    market_value: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.session_date.isoformat(),
            "equity": float(self.equity),
            "cash": float(self.cash),
            "market_value": float(self.market_value),
        }


@dataclass
class BacktestEngineResult:
    decisions: list[TradeDecision] = field(default_factory=list)
    fills: list[HistoricalFill] = field(default_factory=list)
    trades: list[ClosedTrade] = field(default_factory=list)
    orders: list[dict[str, object]] = field(default_factory=list)
    daily_equity: list[DailyEquityPoint] = field(default_factory=list)
    strategy_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    unresolved_positions: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "decisions": [item.to_dict() for item in self.decisions],
            "fills": [item.to_dict() for item in self.fills],
            "trades": [item.to_dict() for item in self.trades],
            "orders": self.orders,
            "daily_equity": [item.to_dict() for item in self.daily_equity],
            "strategy_counts": self.strategy_counts,
            "unresolved_positions": self.unresolved_positions,
        }


class HistoricalBacktestEngine:
    """Runs registered strategies without importing FastAPI, providers, or DB code."""

    def __init__(
        self,
        registry: StrategyRegistry | None = None,
        aggregator: DecisionAggregator | None = None,
    ) -> None:
        self._registry = registry or StrategyRegistry()
        self._aggregator = aggregator or DecisionAggregator()

    def run(
        self,
        *,
        config: BacktestRunConfig,
        bars: Iterable[HistoricalBar],
        progress: ProgressCallback | None = None,
        cancelled: Cancelled | None = None,
    ) -> BacktestEngineResult:
        ordered = sorted(bars, key=lambda item: (item.timestamp, item.symbol))
        if not ordered:
            raise ValueError("回測資料集沒有任何 Kbar")
        self._validate_strategy_set(config)
        by_session: dict[date, list[HistoricalBar]] = {}
        selected_strategy_ids = set(config.strategy_set.entry_strategy_ids) | set(
            config.strategy_set.exit_strategy_ids
        )
        uses_daily_features = any(
            "KBAR_DAILY" in self._registry.definition(strategy_id).required_capabilities
            for strategy_id in selected_strategy_ids
        )
        for bar in ordered:
            if uses_daily_features and (
                bar.session_date is None or bar.session_open_at is None
            ):
                raise ValueError(
                    "daily SMA strategy requires resolved session_date and "
                    "session_open_at on every Kbar"
                )
            session_date = bar.session_date or bar.timestamp.date()
            by_session.setdefault(session_date, []).append(bar)

        result = BacktestEngineResult()
        cash = config.starting_cash
        positions: dict[str, _Position] = {}
        pending: dict[str, _PendingOrder] = {}
        daily_feature_states: dict[str, DailySmaFeatureState] = {}
        previous_close: dict[str, Decimal] = {}
        last_prices: dict[str, Decimal] = {}
        terminal_timestamp_by_symbol = {
            symbol: max(item.timestamp for item in ordered if item.symbol == symbol)
            for symbol in {item.symbol for item in ordered}
        }
        sessions = sorted(by_session)
        all_events = len(ordered)
        processed_events = 0

        for session_index, session_date in enumerate(sessions, start=1):
            self._raise_if_cancelled(cancelled)
            session_bars = by_session[session_date]
            last_timestamp_by_symbol = {
                symbol: max(item.timestamp for item in session_bars if item.symbol == symbol)
                for symbol in {item.symbol for item in session_bars}
            }
            day_states: dict[str, _DayState] = {}
            feature_states: dict[str, BarFeatureState] = {}
            symbol_event_indexes: dict[str, int] = {}
            for global_index, bar in enumerate(session_bars):
                processed_events += 1
                if processed_events % 128 == 0:
                    self._raise_if_cancelled(cancelled)
                    if progress is not None:
                        progress(processed_events / all_events, f"正在回測 {session_date.isoformat()} {bar.symbol}")

                symbol_event_indexes[bar.symbol] = symbol_event_indexes.get(bar.symbol, 0) + 1
                last_prices[bar.symbol] = bar.close
                cash = self._fill_pending_if_due(
                    pending=pending,
                    positions=positions,
                    last_prices=last_prices,
                    cash=cash,
                    bar=bar,
                    symbol_event_index=symbol_event_indexes[bar.symbol],
                    config=config,
                    result=result,
                )

                state = day_states.get(bar.symbol)
                if state is None:
                    state = _DayState(session_open=bar.open)
                    day_states[bar.symbol] = state
                session_high_before = state.session_high
                vwap = state.update(bar)
                feature_state = feature_states.get(bar.symbol)
                if feature_state is None:
                    feature_state = BarFeatureState(bar.symbol, session_date)
                    feature_states[bar.symbol] = feature_state
                previous_features = feature_state.current
                features = feature_state.apply(bar)
                previous_daily_features = None
                daily_features = None
                if uses_daily_features:
                    daily_state = daily_feature_states.get(bar.symbol)
                    if daily_state is None:
                        daily_state = DailySmaFeatureState(bar.symbol)
                        daily_feature_states[bar.symbol] = daily_state
                    previous_daily_features = daily_state.current
                    daily_features = daily_state.apply(bar)
                position = positions.get(bar.symbol)
                position_context = None
                if position is not None:
                    fixed_atr_stop = (
                        position.entry_fill.price - Decimal("1.5") * position.entry_signal_atr
                        if position.entry_signal_atr is not None
                        else None
                    )
                    position_context = PositionStrategyContext(
                        entry_fill_price=position.entry_fill.price,
                        entry_fill_at=position.entry_fill.filled_at,
                        entry_event_index=position.entry_event_index,
                        bars_held_completed=(
                            symbol_event_indexes[bar.symbol] - position.entry_event_index + 1
                        ),
                        entry_signal_atr=position.entry_signal_atr,
                        fixed_atr_stop_price=fixed_atr_stop,
                    )
                context = StrategyContext(
                    symbol=bar.symbol,
                    bar=bar,
                    previous_close=previous_close.get(bar.symbol),
                    session_open=state.session_open,
                    session_high_before=session_high_before,
                    vwap=vwap,
                    cumulative_volume=state.cumulative_volume,
                    bars_seen=state.bars_seen,
                    is_last_bar=bar.timestamp == last_timestamp_by_symbol[bar.symbol],
                    entry_price=(position.entry_fill.price if position is not None else None),
                    features=features,
                    previous_features=previous_features,
                    position=position_context,
                    daily_features=daily_features,
                    previous_daily_features=previous_daily_features,
                    resolved_session_date=bar.session_date,
                    is_terminal_dataset_bar=(
                        bar.timestamp == terminal_timestamp_by_symbol[bar.symbol]
                    ),
                )
                if position is not None:
                    cash = self._evaluate_exit(
                        context=context,
                        position=position,
                        pending=pending,
                        positions=positions,
                        cash=cash,
                        config=config,
                        result=result,
                        event_index=symbol_event_indexes[bar.symbol],
                    )
                elif bar.symbol not in pending and not state.entered_today:
                    decision = self._evaluate_decision(
                        context=context,
                        config=config,
                        side=StrategySide.ENTRY,
                        result=result,
                    )
                    if decision is not None:
                        result.decisions.append(decision)
                        pending[bar.symbol] = _PendingOrder(
                        order_id=self._order_id(
                            decision,
                            StrategySide.ENTRY,
                            (
                                "DAILY_NEXT_BAR_OPEN"
                                if decision.execution_horizon is ExecutionHorizon.DAILY_NEXT_BAR
                                else "NEXT_BAR_OPEN"
                            ),
                        ),
                            decision=decision,
                            side=StrategySide.ENTRY,
                            shares=None,
                            created_at=bar.timestamp,
                            entry_signal_atr=features.atr,
                            execution_horizon=decision.execution_horizon,
                            created_session_date=bar.session_date,
                        )
                        result.orders.append(
                            self._order_payload(pending[bar.symbol], status="SUBMITTED")
                        )
                        state.entered_today = True

            for bar in session_bars:
                previous_close[bar.symbol] = bar.close
            market_value = sum(
                position.shares * last_prices[position.symbol]
                for position in positions.values()
                if position.symbol in last_prices
            )
            result.daily_equity.append(
                DailyEquityPoint(session_date, cash + market_value, cash, market_value)
            )
            if progress is not None:
                progress(session_index / len(sessions), f"已完成 {session_date.isoformat()}")

        for order in tuple(pending.values()):
            if order.execution_horizon is ExecutionHorizon.DAILY_NEXT_BAR:
                self._replace_order_status(
                    result,
                    order.order_id,
                    "UNFILLED_END_OF_DATA",
                    "資料結束前沒有下一個有效日 Kbar 可成交",
                )
        for position in positions.values():
            result.unresolved_positions.append(
                {
                    "symbol": position.symbol,
                    "shares": position.shares,
                    "entry_decision_id": position.entry_decision.decision_id,
                    "reason": "已選賣出策略未於資料結束前平倉",
                }
            )
        return result

    def _validate_strategy_set(self, config: BacktestRunConfig) -> None:
        if config.engine_version not in {"backtest-engine-v1", "backtest-engine-v2"}:
            raise ValueError(f"不支援的回測引擎版本：{config.engine_version}")
        experimental_strategy_ids = {
            "opening_range_breakout_entry_v1",
            "ema_crossover_entry_v1",
            "rsi_bollinger_reversion_entry_v0",
            "atr_stop_exit_v1",
            "time_stop_exit_v1",
            "sma_20_60_golden_cross_entry_v1",
            "sma_20_60_death_cross_exit_v1",
        }
        selected = set(config.strategy_set.entry_strategy_ids) | set(
            config.strategy_set.exit_strategy_ids
        )
        if config.engine_version == "backtest-engine-v1" and selected & experimental_strategy_ids:
            raise ValueError("backtest-engine-v1 不支援新的歷史 feature 策略")
        for strategy_id in config.strategy_set.entry_strategy_ids:
            if self._registry.definition(strategy_id).side is not StrategySide.ENTRY:
                raise ValueError(f"{strategy_id} 不是買入策略")
        for strategy_id in config.strategy_set.exit_strategy_ids:
            if self._registry.definition(strategy_id).side is not StrategySide.EXIT:
                raise ValueError(f"{strategy_id} 不是賣出策略")

    def _evaluate_decision(
        self,
        *,
        context: StrategyContext,
        config: BacktestRunConfig,
        side: StrategySide,
        result: BacktestEngineResult,
    ) -> TradeDecision | None:
        if side is StrategySide.ENTRY:
            ids = config.strategy_set.entry_strategy_ids
            policy = config.strategy_set.entry_policy
            minimum = config.strategy_set.entry_min_trigger_count
        else:
            ids = config.strategy_set.exit_strategy_ids
            policy = config.strategy_set.exit_policy
            minimum = config.strategy_set.exit_min_trigger_count
        evaluations = tuple(self._registry.evaluate(strategy_id, context) for strategy_id in ids)
        self._record_evaluations(result, evaluations)
        return self._aggregator.aggregate(
            symbol=context.symbol,
            event_at=context.bar.timestamp,
            side=side,
            policy=policy,
            minimum_trigger_count=minimum,
            selected_strategy_ids=ids,
            priority_order=config.strategy_set.priority_order,
            evaluations=evaluations,
            strategy_set_digest=config.strategy_set.snapshot_digest,
        )

    @staticmethod
    def _record_evaluations(
        result: BacktestEngineResult,
        evaluations: tuple[StrategyEvaluation, ...],
    ) -> None:
        for evaluation in evaluations:
            counters = result.strategy_counts.setdefault(
                evaluation.strategy_id,
                {"evaluated": 0, "triggered": 0, "blocked": 0, "insufficient_data": 0},
            )
            counters["evaluated"] += 1
            if evaluation.status.value == "TRIGGERED":
                counters["triggered"] += 1
            elif evaluation.status.value == "BLOCKED":
                counters["blocked"] += 1
            elif evaluation.status.value == "INSUFFICIENT_DATA":
                counters["insufficient_data"] += 1

    def _evaluate_exit(
        self,
        *,
        context: StrategyContext,
        position: _Position,
        pending: dict[str, _PendingOrder],
        positions: dict[str, _Position],
        cash: Decimal,
        config: BacktestRunConfig,
        result: BacktestEngineResult,
        event_index: int,
    ) -> Decimal:
        # A daily signal is evaluated at a completed session close, while its
        # corresponding entry filled at that same session's open.  It is
        # therefore valid to evaluate an exit after a DAILY_NEXT_BAR_OPEN fill
        # even when this session only contains a single daily bar.  Preserve
        # the legacy first-bar guard for intraday next-bar fills.
        if context.symbol in pending or (
            event_index <= position.entry_event_index
            and position.entry_fill.source != "DAILY_NEXT_BAR_OPEN"
        ):
            return cash
        decision = self._evaluate_decision(
            context=context,
            config=config,
            side=StrategySide.EXIT,
            result=result,
        )
        if decision is None:
            return cash
        result.decisions.append(decision)
        if (
            decision.execution_horizon is ExecutionHorizon.SESSION_CLOSE
            or (decision.execution_horizon is None and context.is_last_bar)
        ):
            fill = self._make_fill(
                decision=decision,
                bar=context.bar,
                shares=position.shares,
                side=StrategySide.EXIT,
                config=config,
                source="EOD_CLOSE",
            )
            result.fills.append(fill)
            result.orders.append(
                {
                    "order_id": self._order_id(decision, StrategySide.EXIT, "EOD_CLOSE"),
                    "decision_id": decision.decision_id,
                    "symbol": context.symbol,
                    "side": "EXIT",
                    "status": "FILLED",
                    "created_at": context.bar.timestamp.isoformat(),
                    "filled_at": fill.filled_at.isoformat(),
                    "shares": position.shares,
                    "reason": "交易日最後一根 Kbar 以收盤價強制平倉",
                }
            )
            return self._close_position(positions, position, decision, fill, cash, result)
        pending[context.symbol] = _PendingOrder(
            order_id=self._order_id(decision, StrategySide.EXIT, "NEXT_BAR_OPEN"),
            decision=decision,
            side=StrategySide.EXIT,
            shares=position.shares,
            created_at=context.bar.timestamp,
            execution_horizon=decision.execution_horizon,
            created_session_date=context.resolved_session_date,
        )
        result.orders.append(self._order_payload(pending[context.symbol], status="SUBMITTED"))
        return cash

    def _fill_pending_if_due(
        self,
        *,
        pending: dict[str, _PendingOrder],
        positions: dict[str, _Position],
        last_prices: dict[str, Decimal],
        cash: Decimal,
        bar: HistoricalBar,
        symbol_event_index: int,
        config: BacktestRunConfig,
        result: BacktestEngineResult,
    ) -> Decimal:
        order = pending.get(bar.symbol)
        if order is None or bar.timestamp <= order.created_at:
            return cash
        if order.execution_horizon is ExecutionHorizon.DAILY_NEXT_BAR:
            if (
                bar.session_date is None
                or order.created_session_date is None
                or bar.session_date <= order.created_session_date
            ):
                return cash
        if order.side is StrategySide.ENTRY:
            equity = cash + sum(
                position.shares * last_prices.get(position.symbol, position.entry_fill.price)
                for position in positions.values()
            )
            candidate_shares = lot_floor(
                equity * config.position_fraction / bar.open,
                config.min_lot_shares,
            )
            fill = self._make_fill(
                decision=order.decision,
                bar=bar,
                shares=candidate_shares,
                side=StrategySide.ENTRY,
                config=config,
                source=(
                    "DAILY_NEXT_BAR_OPEN"
                    if order.execution_horizon is ExecutionHorizon.DAILY_NEXT_BAR
                    else "NEXT_BAR_OPEN"
                ),
                filled_at=self._fill_time(bar, order.execution_horizon),
            )
            total = fill.price * fill.shares + fill.total_cost
            if fill.shares <= 0 or total > cash:
                pending.pop(bar.symbol, None)
                self._replace_order_status(result, order.order_id, "REJECTED", "可用資金不足以買入一張")
                return cash
            cash -= total
            positions[bar.symbol] = _Position(
                symbol=bar.symbol,
                name=bar.name,
                shares=fill.shares,
                entry_fill=fill,
                entry_decision=order.decision,
                entry_event_at=fill.filled_at,
                entry_event_index=symbol_event_index,
                entry_signal_atr=order.entry_signal_atr,
            )
            result.fills.append(fill)
            pending.pop(bar.symbol, None)
            self._replace_order_status(result, order.order_id, "FILLED", "下一根 Kbar 開盤成交", fill)
            return cash

        position = positions.get(bar.symbol)
        if position is None:
            pending.pop(bar.symbol, None)
            self._replace_order_status(result, order.order_id, "CANCELLED", "持倉已不存在")
            return cash
        fill = self._make_fill(
            decision=order.decision,
            bar=bar,
            shares=position.shares,
            side=StrategySide.EXIT,
            config=config,
            source=(
                "DAILY_NEXT_BAR_OPEN"
                if order.execution_horizon is ExecutionHorizon.DAILY_NEXT_BAR
                else "NEXT_BAR_OPEN"
            ),
            filled_at=self._fill_time(bar, order.execution_horizon),
        )
        result.fills.append(fill)
        pending.pop(bar.symbol, None)
        self._replace_order_status(result, order.order_id, "FILLED", "下一根 Kbar 開盤成交", fill)
        return self._close_position(positions, position, order.decision, fill, cash, result)

    @staticmethod
    def _replace_order_status(
        result: BacktestEngineResult,
        order_id: str,
        status: str,
        reason: str,
        fill: HistoricalFill | None = None,
    ) -> None:
        for order in result.orders:
            if order.get("order_id") != order_id:
                continue
            order["status"] = status
            order["reason"] = reason
            if fill is not None:
                order["filled_at"] = fill.filled_at.isoformat()
                order["fill"] = fill.to_dict()
            return

    @staticmethod
    def _order_payload(order: _PendingOrder, *, status: str) -> dict[str, object]:
        value: dict[str, object] = {
            "order_id": order.order_id,
            "decision_id": order.decision.decision_id,
            "symbol": order.decision.symbol,
            "side": order.side.value,
            "status": status,
            "created_at": order.created_at.isoformat(),
            "shares": order.shares,
            "primary_strategy_id": order.decision.primary_strategy_id,
            "triggered_strategy_ids": list(order.decision.triggered_strategy_ids),
        }
        if order.execution_horizon is not None:
            value["execution_horizon"] = order.execution_horizon.value
        return value

    @staticmethod
    def _fill_time(
        bar: HistoricalBar,
        execution_horizon: ExecutionHorizon | None,
    ) -> datetime:
        if execution_horizon is not ExecutionHorizon.DAILY_NEXT_BAR:
            return bar.timestamp
        if bar.session_open_at is None:
            raise ValueError("daily next-bar fill requires session_open_at")
        return bar.session_open_at

    @staticmethod
    def _make_fill(
        *,
        decision: TradeDecision,
        bar: HistoricalBar,
        shares: int,
        side: StrategySide,
        config: BacktestRunConfig,
        source: str,
        filled_at: datetime | None = None,
    ) -> HistoricalFill:
        fill_time = filled_at or bar.timestamp
        slippage = config.slippage_bps / Decimal("10000")
        raw_price = bar.close if source == "EOD_CLOSE" else bar.open
        price = raw_price * (Decimal("1") + slippage if side is StrategySide.ENTRY else Decimal("1") - slippage)
        gross = price * shares
        commission = gross * config.commission_rate
        tax = gross * config.sell_tax_rate if side is StrategySide.EXIT else Decimal("0")
        fill_identity = {
            "decision_id": decision.decision_id,
            "symbol": bar.symbol,
            "side": side.value,
            "filled_at": fill_time.isoformat(),
            "shares": shares,
            "source": source,
        }
        return HistoricalFill(
            fill_id=f"fill-{digest(fill_identity)[:24]}",
            decision_id=decision.decision_id,
            symbol=bar.symbol,
            side=side,
            filled_at=fill_time,
            price=price,
            shares=shares,
            commission=commission,
            tax=tax,
            source=source,
        )

    @staticmethod
    def _close_position(
        positions: dict[str, _Position],
        position: _Position,
        exit_decision: TradeDecision,
        exit_fill: HistoricalFill,
        cash: Decimal,
        result: BacktestEngineResult,
    ) -> Decimal:
        proceeds = exit_fill.price * exit_fill.shares - exit_fill.total_cost
        gross_pnl = (exit_fill.price - position.entry_fill.price) * position.shares
        net_pnl = gross_pnl - position.entry_fill.total_cost - exit_fill.total_cost
        holding = max(0, int((exit_fill.filled_at - position.entry_fill.filled_at).total_seconds() // 60))
        trade_identity = {
            "entry_decision_id": position.entry_decision.decision_id,
            "exit_decision_id": exit_decision.decision_id,
            "entry_fill_id": position.entry_fill.fill_id,
            "exit_fill_id": exit_fill.fill_id,
        }
        result.trades.append(
            ClosedTrade(
                trade_id=f"trade-{digest(trade_identity)[:24]}",
                symbol=position.symbol,
                name=position.name,
                entry_decision=position.entry_decision,
                exit_decision=exit_decision,
                entry_fill=position.entry_fill,
                exit_fill=exit_fill,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                holding_minutes=holding,
            )
        )
        positions.pop(position.symbol, None)
        return cash + proceeds

    @staticmethod
    def _raise_if_cancelled(cancelled: Cancelled | None) -> None:
        if cancelled is not None and cancelled():
            raise BacktestCancelled("回測工作已取消")

    @staticmethod
    def _order_id(decision: TradeDecision, side: StrategySide, source: str) -> str:
        order_identity = {
            "decision_id": decision.decision_id,
            "symbol": decision.symbol,
            "side": side.value,
            "source": source,
        }
        return f"order-{digest(order_identity)[:24]}"
