"""本機紙上模擬的共用下單指令與投影服務。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from queue import Full, Queue
from threading import RLock, Thread
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_data.models import RealtimeQuoteUpdate, StockData
from market_data.provider import MarketDataProvider
from runtime.clock import Clock, SystemClock
from simulation.execution_policy import EXECUTABLE_BOOK_MAX_AGE_SECONDS
from simulation.models import (
    OrderSide,
    OrderStatus,
    SimulationOrder,
    SimulationPosition,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DEFAULT_STARTING_CASH = Decimal("10000000")
_DEFAULT_QUOTE_QUEUE_CAPACITY = 1_024
_DEFAULT_PENDING_TIMEOUT_SECONDS = 30
_DEFAULT_ORDER_EXPIRY_SECONDS = 120
_DEFAULT_MAX_RETRY_ATTEMPTS = 3
_ACTIVE_ORDER_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTED,
        OrderStatus.PENDING,
        OrderStatus.PARTIALLY_FILLED,
    }
)


@dataclass
class _QuoteState:
    """合併 snapshot、Tick 與 BidAsk，但分開維持兩條 stream 的順序。"""

    snapshot: StockData | None = None
    last_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    last_trade_at: datetime | None = None
    book_at: datetime | None = None
    received_at: datetime | None = None
    book_received_at: datetime | None = None
    bid_available_quantity: int | None = None
    ask_available_quantity: int | None = None


class SimulationValidationError(ValueError):
    """不符合本機紙上模擬下單規則。"""


class SimulationStateError(ValueError):
    """目前委託狀態無法執行要求的操作。"""


class SimulationService:
    """提供瀏覽器與未來策略程式共用的本機紙上模擬指令入口。

    服務狀態只存在 Web process 記憶體中。它刻意不連線至券商帳務或下單 API，
    因此不是 Shioaji Simulation 的替代品。
    """

    mode = "LOCAL_PAPER_SIMULATION"
    label = "本機紙上模擬（非 Shioaji）"

    def __init__(
        self,
        provider: MarketDataProvider,
        starting_cash: Decimal | float | int = _DEFAULT_STARTING_CASH,
        *,
        quote_queue_capacity: int = _DEFAULT_QUOTE_QUEUE_CAPACITY,
        max_book_age_seconds: int = EXECUTABLE_BOOK_MAX_AGE_SECONDS,
        pending_timeout_seconds: int = _DEFAULT_PENDING_TIMEOUT_SECONDS,
        order_expiry_seconds: int = _DEFAULT_ORDER_EXPIRY_SECONDS,
        max_retry_attempts: int = _DEFAULT_MAX_RETRY_ATTEMPTS,
        clock: Clock | None = None,
    ) -> None:
        normalized_starting_cash = self._money(starting_cash, "starting_cash")
        if normalized_starting_cash <= 0:
            raise ValueError("starting_cash 必須是大於 0 的有限數字")
        if (
            isinstance(quote_queue_capacity, bool)
            or not isinstance(quote_queue_capacity, int)
            or quote_queue_capacity <= 0
        ):
            raise ValueError("quote_queue_capacity 必須是大於 0 的整數")
        if (
            isinstance(max_book_age_seconds, bool)
            or not isinstance(max_book_age_seconds, int)
            or max_book_age_seconds <= 0
        ):
            raise ValueError("max_book_age_seconds 必須是大於 0 的整數")
        for value, field_name in (
            (pending_timeout_seconds, "pending_timeout_seconds"),
            (order_expiry_seconds, "order_expiry_seconds"),
            (max_retry_attempts, "max_retry_attempts"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必須是大於 0 的整數")

        self._provider = provider
        self._clock = clock or SystemClock()
        provider_identity = getattr(provider, "environment_identity", None)
        self._provider_identity = (
            str(provider_identity).strip()
            if provider_identity is not None
            else f"{type(provider).__module__}.{type(provider).__qualname__}"
        )
        if not self._provider_identity:
            raise ValueError("provider identity must not be empty")
        self._starting_cash = normalized_starting_cash
        self._cash = normalized_starting_cash
        self._max_book_age_seconds = max_book_age_seconds
        self._pending_timeout_seconds = pending_timeout_seconds
        self._order_expiry_seconds = order_expiry_seconds
        self._max_retry_attempts = max_retry_attempts
        self._trading_date = self._clock.session_date()
        self._opening_equity = normalized_starting_cash
        self._opening_realized_pnl = Decimal("0")
        self._orders: dict[str, SimulationOrder] = {}
        self._order_ids_by_key: dict[str, str] = {}
        self._cancel_order_ids_by_key: dict[str, str] = {}
        self._reserved_buy_notional_by_order: dict[str, Decimal] = {}
        self._positions: dict[str, SimulationPosition] = {}
        self._quotes: dict[str, _QuoteState] = {}
        self._realized_pnl_by_symbol: dict[str, Decimal] = {}
        self._alerts: list[dict[str, Any]] = []
        self._lock = RLock()
        self._stream_capable = provider.supports_streaming_quotes()
        self._streaming_enabled = False
        self._stream_error: str | None = None
        self._quote_ingress_blocked = False
        self._subscribed_symbols: set[str] = set()
        self._quote_updates: Queue[RealtimeQuoteUpdate | None] = Queue(
            maxsize=quote_queue_capacity
        )
        self._quote_worker: Thread | None = None
        self._terminal_order_handler: Callable[[dict[str, Any]], None] | None = None
        self._daily_baseline_handler: Callable[[dict[str, Any]], None] | None = None
        self._pending_daily_baselines: list[dict[str, Any]] = []

        if self._stream_capable:
            self._quote_worker = Thread(
                target=self._run_quote_worker,
                name="simulation-quote-worker",
                daemon=True,
            )
            self._quote_worker.start()
            try:
                self._provider.start_quote_stream(self.receive_quote_update)
                self._streaming_enabled = True
            except Exception as error:
                self._stream_error = f"無法啟動 Shioaji Tick／BidAsk：{error}"
                self._quote_updates.put(None)
                self._quote_worker.join(timeout=1)
                self._quote_worker = None

    @property
    def starting_cash(self) -> Decimal:
        """Expose immutable starting cash for the command facade and Journal."""
        return self._starting_cash

    @property
    def requires_fresh_book(self) -> bool:
        return self._stream_capable

    @property
    def max_book_age_seconds(self) -> int:
        return self._max_book_age_seconds

    @property
    def max_retry_attempts(self) -> int:
        return self._max_retry_attempts

    def set_terminal_order_handler(
        self,
        handler: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        """Register the local Journal bridge for orders completed after submit."""
        with self._lock:
            self._terminal_order_handler = handler

    def set_daily_baseline_handler(
        self,
        handler: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        """Register the Journal bridge for a newly frozen trading-day baseline."""
        with self._lock:
            self._daily_baseline_handler = handler

    def daily_baseline(self) -> dict[str, Any]:
        """Return the currently frozen trading-day risk baseline."""
        self._roll_trading_day()
        with self._lock:
            return self._daily_baseline_payload()

    def session(self) -> dict[str, Any]:
        """回傳不會觸發 Provider 或券商呼叫的 session 中繼資料。"""
        self._roll_trading_day()
        with self._lock:
            market_value = self._market_value()
            reserved_cash = self._reserved_cash()
            available_cash = self._cash - reserved_cash
            received_times = [
                quote.received_at
                for quote in self._quotes.values()
                if quote.received_at is not None
            ]
            label = (
                "本機紙上模擬（Shioaji 即時行情）"
                if self._stream_capable
                else self.label
            )
            notice = (
                "委託、持倉與交易日風控基準由本機 Journal checkpoint 管理；"
                "行情來自 Shioaji Tick／BidAsk，不會送出 Shioaji 或真實券商委託。"
                if self._stream_capable
                else "委託、持倉與交易日風控基準由本機 Journal checkpoint 管理；"
                "不會送出 Shioaji 或真實券商委託。"
            )
            return {
                "mode": self.mode,
                "label": label,
                "ordering_enabled": True,
                "starting_cash": float(self._starting_cash),
                "trading_date": self._trading_date.isoformat(),
                "opening_equity": float(self._opening_equity),
                "daily_loss_includes_unrealized": True,
                "available_cash": float(available_cash),
                "reserved_cash": float(reserved_cash),
                "market_value": float(market_value),
                "equity": float(self._cash + market_value),
                "quote_mode": (
                    "SHIOAJI_TICK_BIDASK" if self._stream_capable else "SNAPSHOT"
                ),
                "streaming": self._streaming_enabled,
                "stream_health": self._stream_health(),
                "quote_queue_depth": self._quote_updates.qsize(),
                "quote_queue_capacity": self._quote_updates.maxsize,
                "subscribed_symbols": sorted(self._subscribed_symbols),
                "last_quote_received_at": (
                    max(received_times).isoformat() if received_times else None
                ),
                "stream_error": self._stream_error,
                "notice": notice,
            }

    def projection(self) -> dict[str, Any]:
        """回傳瀏覽器可直接讀取的本機訂單、持倉與 session 投影。"""
        self.reconcile_orders()
        return {
            "session": self.session(),
            "orders": self.orders(),
            "positions": self.positions(),
            "alerts": self.alerts(),
        }

    def orders(self) -> list[dict[str, Any]]:
        """讀取委託投影，不會呼叫資料來源。"""
        with self._lock:
            orders = sorted(
                self._orders.values(),
                key=lambda order: order.submitted_at,
                reverse=True,
            )
            return [self._order_payload(order) for order in orders]

    def alerts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(alert) for alert in reversed(self._alerts)]

    def restore_state(
        self,
        *,
        cash: Decimal,
        positions: list[dict[str, Any]],
        realized_pnl_by_symbol: dict[str, Decimal],
        order_states: list[dict[str, Any]],
        daily_baseline: dict[str, Any] | None = None,
    ) -> None:
        """Restore one checkpoint-verified local-paper projection before use."""

        with self._lock:
            if self._orders or self._positions or self._cash != self._starting_cash:
                raise SimulationStateError("本機模擬已有狀態，禁止重複復原")
            self._cash = self._money(cash, "restored.cash")
            self._realized_pnl_by_symbol = {
                self._normalize_symbol(symbol): self._money(value, "restored.realized_pnl")
                for symbol, value in realized_pnl_by_symbol.items()
            }
            for raw in positions:
                symbol = self._normalize_symbol(str(raw["symbol"]))
                position = SimulationPosition(
                    symbol=symbol,
                    name=str(raw["name"]),
                    quantity=int(raw["quantity"]),
                    average_price=self._money(raw["average_price"], "restored.average_price"),
                    owner_origin=str(raw.get("owner_origin") or "MANUAL_WEB"),
                    owner_strategy_id=(
                        str(raw["owner_strategy_id"])
                        if raw.get("owner_strategy_id") is not None
                        else None
                    ),
                    owner_strategy_version=(
                        str(raw["owner_strategy_version"])
                        if raw.get("owner_strategy_version") is not None
                        else None
                    ),
                )
                self._positions[symbol] = position
                self._quotes.setdefault(symbol, _QuoteState())
            for raw in order_states:
                order = SimulationOrder(
                    order_id=str(raw["order_id"]),
                    idempotency_key=str(raw["idempotency_key"]),
                    origin=str(raw["origin"]),
                    strategy_id=(
                        str(raw["strategy_id"])
                        if raw.get("strategy_id") is not None
                        else None
                    ),
                    strategy_version=(
                        str(raw["strategy_version"])
                        if raw.get("strategy_version") is not None
                        else None
                    ),
                    symbol=self._normalize_symbol(str(raw["symbol"])),
                    name=str(raw["name"]),
                    side=OrderSide(str(raw["side"])),
                    quantity_shares=self._restored_quantity_shares(raw),
                    limit_price=self._money(raw["limit_price"], "restored.limit_price"),
                    status=OrderStatus(str(raw["status"])),
                    submitted_at=datetime.fromisoformat(str(raw["submitted_at"])),
                    updated_at=datetime.fromisoformat(str(raw["updated_at"])),
                    filled_price=(
                        self._money(raw["filled_price"], "restored.filled_price")
                        if raw.get("filled_price") is not None
                        else None
                    ),
                    filled_quantity=int(raw.get("filled_quantity") or 0),
                    filled_notional=self._money(
                        raw.get("filled_amount") or 0,
                        "restored.filled_amount",
                    ),
                    last_fill_price=(
                        self._money(raw["last_fill_price"], "restored.last_fill_price")
                        if raw.get("last_fill_price") is not None
                        else None
                    ),
                    last_fill_quantity=int(raw.get("last_fill_quantity") or 0),
                    fill_sequence=int(raw.get("fill_sequence") or 0),
                    reason=(str(raw["reason"]) if raw.get("reason") is not None else None),
                    attempt=int(raw.get("attempt") or 1),
                    predecessor_order_id=(
                        str(raw["predecessor_order_id"])
                        if raw.get("predecessor_order_id") is not None
                        else None
                    ),
                    timeout_at=(
                        datetime.fromisoformat(str(raw["timeout_at"]))
                        if raw.get("timeout_at") is not None
                        else None
                    ),
                    expires_at=(
                        datetime.fromisoformat(str(raw["expires_at"]))
                        if raw.get("expires_at") is not None
                        else None
                    ),
                )
                self._orders[order.order_id] = order
                self._order_ids_by_key[order.idempotency_key] = order.order_id
                self._quotes.setdefault(order.symbol, _QuoteState())
                if order.status in _ACTIVE_ORDER_STATUSES and order.side is OrderSide.BUY:
                    self._reserved_buy_notional_by_order[order.order_id] = (
                        order.remaining_quantity * order.limit_price
                    )
                recovered_alert = {
                    "ORDER_TIMEOUT": "ORDER_TIMEOUT_CANCELLED",
                    "ORDER_EXPIRED": "ORDER_EXPIRED",
                    "COMMAND_ACKNOWLEDGEMENT_MISSING": "RECOVERY_REQUIRED",
                }.get(order.reason or "")
                if recovered_alert is not None:
                    self._alerts.append(
                        {
                            "alert_id": f"{recovered_alert}:{order.order_id}:restored",
                            "code": recovered_alert,
                            "severity": "HIGH",
                            "order_id": order.order_id,
                            "symbol": order.symbol,
                            "message": f"{order.symbol} 委託復原狀態：{order.reason}",
                            "created_at": order.updated_at.isoformat(),
                            "acknowledged": False,
                        }
                    )
            latest = order_states[-1] if order_states else None
            if daily_baseline is not None:
                restored_date = date.fromisoformat(
                    str(daily_baseline["trading_date"])
                )
                if restored_date > self._clock.session_date():
                    raise SimulationStateError("交易日風控基準不可晚於目前交易日")
                if daily_baseline.get("includes_unrealized_pnl") is not True:
                    raise SimulationStateError("交易日風控基準未凍結未實現損益政策")
                self._trading_date = restored_date
                self._opening_equity = self._money(
                    daily_baseline["opening_equity"],
                    "restored.opening_equity",
                )
                self._opening_realized_pnl = self._money(
                    daily_baseline.get("opening_realized_pnl") or 0,
                    "restored.opening_realized_pnl",
                )
            elif latest and latest.get("trading_date") == self._trading_date.isoformat():
                self._opening_equity = self._money(
                    latest.get("opening_equity"),
                    "restored.opening_equity",
                )
                self._opening_realized_pnl = sum(
                    self._realized_pnl_by_symbol.values(),
                    Decimal("0"),
                )
            else:
                self._opening_equity = self._cash + self._market_value()
                self._opening_realized_pnl = sum(
                    self._realized_pnl_by_symbol.values(),
                    Decimal("0"),
                )
        self._sync_quote_subscriptions()

    def reconcile_orders(self) -> None:
        """Apply deterministic timeout/expiry transitions using the injected clock."""

        changed = False
        notifications: list[dict[str, Any]] = []
        with self._lock:
            now = self._now()
            for order in self._orders.values():
                if order.status not in _ACTIVE_ORDER_STATUSES:
                    continue
                if order.expires_at is not None and now >= order.expires_at:
                    self._end_order(
                        order,
                        status=OrderStatus.EXPIRED,
                        reason="ORDER_EXPIRED",
                        alert_code="ORDER_EXPIRED",
                        alert_message=f"{order.symbol} 委託已到期，未成交餘量停止撮合",
                    )
                    notifications.append(self._order_payload(order))
                    changed = True
                elif order.timeout_at is not None and now >= order.timeout_at:
                    self._end_order(
                        order,
                        status=OrderStatus.CANCELLED,
                        reason="ORDER_TIMEOUT",
                        alert_code="ORDER_TIMEOUT_CANCELLED",
                        alert_message=f"{order.symbol} 委託逾時，已取消未成交餘量",
                    )
                    notifications.append(self._order_payload(order))
                    changed = True
        for payload in notifications:
            self._notify_terminal_order(payload)
        if changed:
            self._sync_quote_subscriptions()

    def positions(self) -> list[dict[str, Any]]:
        """讀取由已成交委託建立的持倉投影，不會呼叫資料來源。"""
        self._roll_trading_day()
        with self._lock:
            positions: list[dict[str, Any]] = []
            for position in sorted(self._positions.values(), key=lambda item: item.symbol):
                quote = self._quote_for(position)
                current_price = self._current_price(position)
                market_value = position.quantity * current_price
                unrealized_pnl = position.quantity * (current_price - position.average_price)
                quote_at = None
                if quote is not None:
                    quote_at = quote.received_at
                    if quote_at is None and quote.snapshot is not None:
                        quote_at = quote.snapshot.timestamp
                positions.append(
                    {
                        "symbol": position.symbol,
                        "name": position.name,
                        "quantity": position.quantity,
                        "average_price": float(position.average_price),
                        "current_price": float(current_price),
                        "market_value": float(market_value),
                        "unrealized_pnl": float(unrealized_pnl),
                        "unrealized_pnl_pct": float(
                            unrealized_pnl / (position.quantity * position.average_price) * 100
                            if position.average_price > 0
                            else Decimal("0")
                        ),
                        "realized_pnl": float(
                            self._realized_pnl_by_symbol.get(
                                position.symbol, Decimal("0")
                            )
                        ),
                        "owner_origin": position.owner_origin,
                        "owner_strategy_id": position.owner_strategy_id,
                        "owner_strategy_version": position.owner_strategy_version,
                        "bid_price": float(quote.bid_price) if quote and quote.bid_price else None,
                        "ask_price": float(quote.ask_price) if quote and quote.ask_price else None,
                        "last_quote_at": quote_at.isoformat() if quote_at else None,
                        "quote_received_at": (
                            quote.received_at.isoformat()
                            if quote and quote.received_at
                            else None
                        ),
                        "book_received_at": (
                            quote.book_received_at.isoformat()
                            if quote and quote.book_received_at
                            else None
                        ),
                        "quote_source": (
                            "SHIOAJI_TICK_BIDASK"
                            if quote and quote.received_at
                            else "SNAPSHOT"
                        ),
                    }
                )
            return positions

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        quantity_shares: int | None = None,
        lots: int | None = None,
        origin: str = "MANUAL_WEB",
        strategy_id: str | None = None,
        strategy_version: str | None = None,
        attempt: int = 1,
        predecessor_order_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """接受限價委託；串流模式以賣一／買一，本機模式以 snapshot 撮合。"""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_quantity_shares = self._resolve_quantity_shares(
            quantity_shares=quantity_shares,
            lots=lots,
        )
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        normalized_origin = str(origin).strip().upper()
        normalized_strategy_id = self._optional_identity(strategy_id)
        normalized_strategy_version = self._optional_identity(strategy_version)
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
            raise SimulationValidationError("委託 attempt 必須是大於 0 的整數")
        if attempt > self._max_retry_attempts:
            raise SimulationValidationError("委託重試次數已達上限")
        normalized_predecessor = self._optional_identity(predecessor_order_id)
        if (attempt == 1) != (normalized_predecessor is None):
            raise SimulationValidationError("委託 predecessor 與 attempt 不一致")
        if normalized_origin == "STRATEGY_AUTOMATED":
            if normalized_strategy_id is None or normalized_strategy_version is None:
                raise SimulationValidationError("自動策略委託缺少策略歸屬")
        elif normalized_strategy_id is not None or normalized_strategy_version is not None:
            raise SimulationValidationError("手動委託不可帶入自動策略歸屬")

        self._roll_trading_day()
        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id]), True

            if self._stream_capable:
                stock_symbol, stock_name = self._get_stock_identity(normalized_symbol)
                self._quotes.setdefault(stock_symbol, _QuoteState())
            else:
                stock = self._get_stock(normalized_symbol)
                stock_symbol, stock_name = stock.symbol, stock.name
                self._quotes.setdefault(
                    stock_symbol,
                    _QuoteState(snapshot=stock),
                ).snapshot = stock
            now = self._now()
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=normalized_origin,
                symbol=stock_symbol,
                name=stock_name,
                side=normalized_side,
                quantity_shares=normalized_quantity_shares,
                limit_price=normalized_price,
                status=OrderStatus.SUBMITTED,
                submitted_at=now,
                updated_at=now,
                strategy_id=normalized_strategy_id,
                strategy_version=normalized_strategy_version,
                attempt=attempt,
                predecessor_order_id=normalized_predecessor,
                timeout_at=now + timedelta(seconds=self._pending_timeout_seconds),
                expires_at=now + timedelta(seconds=self._order_expiry_seconds),
            )
            self._orders[order.order_id] = order
            self._order_ids_by_key[normalized_key] = order.order_id

            if normalized_side is OrderSide.BUY:
                position = self._positions.get(order.symbol)
                if position is not None and not self._same_owner(order, position):
                    self._reject(order, "持倉歸屬衝突，禁止合併部位")
                conflicting_pending = next(
                    (
                        existing
                        for existing in self._orders.values()
                        if existing.order_id != order.order_id
                        and existing.symbol == order.symbol
                        and existing.side is OrderSide.BUY
                        and existing.status in _ACTIVE_ORDER_STATUSES
                        and not self._same_order_owner(order, existing)
                    ),
                    None,
                )
                if (
                    order.status is OrderStatus.SUBMITTED
                    and conflicting_pending is not None
                ):
                    self._reject(
                        order,
                        "同股票已有不同歸屬的買進委託，禁止跨 owner 保留或合併",
                    )
                reserved = order.quantity * order.limit_price
                if order.status is OrderStatus.SUBMITTED and reserved > self._available_cash():
                    self._reject(order, "可用虛擬現金不足")
                elif order.status is OrderStatus.SUBMITTED:
                    self._reserved_buy_notional_by_order[order.order_id] = reserved
            else:
                position = self._positions.get(order.symbol)
                if (
                    normalized_origin == "STRATEGY_AUTOMATED"
                    and position is not None
                    and not self._same_owner(order, position)
                ):
                    self._reject(order, "自動策略不可賣出不屬於該策略的持倉")
                elif order.quantity > self._available_to_sell(
                    order.symbol,
                    exclude_order_id=order.order_id,
                ):
                    self._reject(order, "可賣出持股不足")

            if order.status is OrderStatus.SUBMITTED:
                execution_price = (
                    self._stream_execution_price(order, self._quotes[stock_symbol])
                    if self._stream_capable
                    else self._stock_price(stock)
                )
                if (
                    execution_price is not None
                    and self._is_marketable_price(order, execution_price)
                ):
                    fill_quantity = (
                        self._book_fill_quantity(order, self._quotes[stock_symbol])
                        if self._stream_capable
                        else order.remaining_quantity
                    )
                    if fill_quantity > 0:
                        executed_quantity = self._fill(
                            order,
                            execution_price,
                            fill_quantity=fill_quantity,
                        )
                        if self._stream_capable and executed_quantity > 0:
                            self._consume_book_quantity(
                                order,
                                self._quotes[stock_symbol],
                                executed_quantity,
                            )

            if order.status is OrderStatus.SUBMITTED:
                order.status = OrderStatus.PENDING
                order.updated_at = self._now()

            payload = self._order_payload(order)

        self._sync_quote_subscriptions()
        return payload, False

    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """取消尚未成交的本機限價委託。"""
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            previous_order_id = self._cancel_order_ids_by_key.get(normalized_key)
            if previous_order_id is not None:
                return self._order_payload(self._orders[previous_order_id]), True

            order = self._orders.get(order_id)
            if order is None:
                raise SimulationValidationError("找不到委託")
            if order.status not in _ACTIVE_ORDER_STATUSES:
                raise SimulationStateError("只有已送出的委託可以取消")

            order.status = OrderStatus.CANCELLED
            order.reason = "OPERATOR_CANCELLED"
            order.updated_at = self._now()
            self._reserved_buy_notional_by_order.pop(order.order_id, None)
            self._cancel_order_ids_by_key[normalized_key] = order.order_id
            payload = self._order_payload(order)

        self._sync_quote_subscriptions()
        return payload, False

    def refresh_quotes(self) -> None:
        """Mock fallback 才查 snapshot；Shioaji 串流模式不輪詢行情 API。"""
        if self._stream_capable:
            self._sync_quote_subscriptions()
            return

        notifications: list[dict[str, Any]] = []
        with self._lock:
            symbols = {
                *self._positions,
                *(
                    order.symbol
                    for order in self._orders.values()
                    if order.status in _ACTIVE_ORDER_STATUSES
                ),
            }

        quotes: dict[str, StockData] = {}
        for symbol in symbols:
            try:
                quotes[symbol] = self._get_stock(symbol)
            except SimulationValidationError:
                continue

        with self._lock:
            for symbol, quote in quotes.items():
                self._quotes.setdefault(symbol, _QuoteState(snapshot=quote)).snapshot = quote
            for order in self._orders.values():
                quote = quotes.get(order.symbol)
                if (
                    quote is not None
                    and order.status in _ACTIVE_ORDER_STATUSES
                    and self._is_marketable_price(order, self._stock_price(quote))
                ):
                    self._fill(
                        order,
                        self._stock_price(quote),
                    )
                    notifications.append(self._order_payload(order))
        for payload in notifications:
            self._notify_terminal_order(payload)

    def receive_quote_update(self, update: RealtimeQuoteUpdate) -> None:
        """供 Provider callback 快速排入背景 worker，不在 callback thread 撮合。"""
        with self._lock:
            enabled = self._streaming_enabled and not self._quote_ingress_blocked
        if not enabled:
            return
        try:
            self._quote_updates.put_nowait(update)
        except Full:
            with self._lock:
                self._quote_ingress_blocked = True
                self._stream_error = "即時行情佇列已滿，已停止接受新的模擬委託"

    def close(self) -> None:
        """停止行情訂閱並依序處理已排入的 quote updates。"""
        if not self._stream_capable:
            return
        try:
            self._provider.stop_quote_stream()
        finally:
            self._streaming_enabled = False
            with self._lock:
                self._subscribed_symbols.clear()
            worker = self._quote_worker
            if worker is not None:
                try:
                    self._quote_updates.put(None, timeout=2)
                except Full:
                    self._stream_error = "即時行情 worker 無法排入關閉訊號"
                    return
                worker.join(timeout=5)
                if worker.is_alive():
                    self._stream_error = "即時行情 worker 未在關閉期限內排空佇列"
                else:
                    self._quote_worker = None

    def _get_stock(self, symbol: str) -> StockData:
        try:
            stock = self._provider.get_stock(symbol)
        except KeyError as error:
            raise SimulationValidationError(f"找不到股票：{symbol}") from error

        if not math.isfinite(stock.price) or stock.price <= 0:
            raise SimulationValidationError(f"{symbol} 沒有可用的正確報價")
        return stock

    def _get_stock_identity(self, symbol: str) -> tuple[str, str]:
        try:
            canonical_symbol, name = self._provider.get_stock_identity(symbol)
        except KeyError as error:
            raise SimulationValidationError(f"找不到股票：{symbol}") from error
        normalized_symbol = str(canonical_symbol).strip().upper()
        normalized_name = str(name).strip()
        if not normalized_symbol or not normalized_name:
            raise SimulationValidationError(f"找不到股票：{symbol}")
        return normalized_symbol, normalized_name

    @staticmethod
    def _is_marketable_price(order: SimulationOrder, execution_price: Decimal) -> bool:
        return (
            order.limit_price >= execution_price
            if order.side is OrderSide.BUY
            else order.limit_price <= execution_price
        )

    def _stream_execution_price(
        self,
        order: SimulationOrder,
        quote: _QuoteState,
    ) -> Decimal | None:
        if quote.book_received_at is None or quote.book_at is None:
            return None
        age = (self._now() - quote.book_received_at).total_seconds()
        if age < 0 or age > self._max_book_age_seconds:
            return None
        return quote.ask_price if order.side is OrderSide.BUY else quote.bid_price

    @staticmethod
    def _book_fill_quantity(order: SimulationOrder, quote: _QuoteState) -> int:
        available = (
            quote.ask_available_quantity
            if order.side is OrderSide.BUY
            else quote.bid_available_quantity
        )
        if available is None:
            return order.remaining_quantity
        return min(order.remaining_quantity, available)

    @staticmethod
    def _consume_book_quantity(
        order: SimulationOrder,
        quote: _QuoteState,
        quantity: int,
    ) -> int:
        if order.side is OrderSide.BUY and quote.ask_available_quantity is not None:
            quote.ask_available_quantity = max(0, quote.ask_available_quantity - quantity)
        elif order.side is OrderSide.SELL and quote.bid_available_quantity is not None:
            quote.bid_available_quantity = max(0, quote.bid_available_quantity - quantity)

    def _available_to_sell(
        self,
        symbol: str,
        exclude_order_id: str | None = None,
    ) -> int:
        position = self._positions.get(symbol)
        held_quantity = position.quantity if position else 0
        pending_quantity = sum(
            order.remaining_quantity
            for order in self._orders.values()
            if (
                order.symbol == symbol
                and order.side is OrderSide.SELL
                and order.status in _ACTIVE_ORDER_STATUSES
                and order.order_id != exclude_order_id
            )
        )
        return held_quantity - pending_quantity

    def _fill(
        self,
        order: SimulationOrder,
        fill_price: Decimal,
        *,
        fill_quantity: int | None = None,
    ) -> None:
        """在 lock 內以已驗證的 snapshot／買一／賣一完成本機紙上成交。"""
        quantity = min(fill_quantity or order.remaining_quantity, order.remaining_quantity)
        if quantity <= 0:
            return 0
        if order.side is OrderSide.BUY:
            fill_amount = quantity * fill_price
            if fill_amount > self._cash:
                self._reject(
                    order,
                    "目前報價造成可用虛擬現金不足",
                )
                return 0

            position = self._positions.get(order.symbol)
            if position is None:
                self._positions[order.symbol] = SimulationPosition(
                    symbol=order.symbol,
                    name=order.name,
                    quantity=quantity,
                    average_price=fill_price,
                    owner_origin=order.origin,
                    owner_strategy_id=order.strategy_id,
                    owner_strategy_version=order.strategy_version,
                )
            else:
                if not self._same_owner(order, position):
                    self._reject(order, "成交時持倉歸屬衝突，禁止跨 owner 合併")
                    return 0
                total_quantity = position.quantity + quantity
                position.average_price = (
                    position.average_price * position.quantity
                    + fill_price * quantity
                ) / total_quantity
                position.quantity = total_quantity
            self._cash -= fill_amount
        else:
            position = self._positions.get(order.symbol)
            if position is None or position.quantity < quantity:
                self._reject(
                    order,
                    "可賣出持股不足",
                )
                return 0

            realized_pnl = (fill_price - position.average_price) * quantity
            self._realized_pnl_by_symbol[order.symbol] = (
                self._realized_pnl_by_symbol.get(order.symbol, Decimal("0"))
                + realized_pnl
            )
            position.quantity -= quantity
            self._cash += quantity * fill_price
            if position.quantity == 0:
                del self._positions[order.symbol]

        order.filled_notional += fill_price * quantity
        order.filled_quantity += quantity
        order.filled_price = order.filled_notional / order.filled_quantity
        order.last_fill_price = fill_price
        order.last_fill_quantity = quantity
        order.fill_sequence += 1
        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED
            self._reserved_buy_notional_by_order.pop(order.order_id, None)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
            if order.side is OrderSide.BUY:
                self._reserved_buy_notional_by_order[order.order_id] = (
                    order.remaining_quantity * order.limit_price
                )
        now = self._now()
        order.updated_at = (
            now
            if now > order.updated_at
            else order.updated_at + timedelta(microseconds=1)
        )
        return quantity

    def _reject(
        self,
        order: SimulationOrder,
        reason: str,
    ) -> None:
        order.status = OrderStatus.REJECTED
        order.reason = reason
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        order.updated_at = self._now()

    def _end_order(
        self,
        order: SimulationOrder,
        *,
        status: OrderStatus,
        reason: str,
        alert_code: str,
        alert_message: str,
    ) -> None:
        order.status = status
        order.reason = reason
        order.updated_at = self._now()
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        self._alerts.append(
            {
                "alert_id": f"{alert_code}:{order.order_id}:{order.updated_at.isoformat()}",
                "code": alert_code,
                "severity": "HIGH",
                "order_id": order.order_id,
                "symbol": order.symbol,
                "message": alert_message,
                "created_at": order.updated_at.isoformat(),
                "acknowledged": False,
            }
        )

    def _notify_terminal_order(self, payload: dict[str, Any]) -> None:
        with self._lock:
            handler = self._terminal_order_handler
        if handler is None:
            return
        try:
            handler(payload)
        except Exception as error:
            with self._lock:
                self._quote_ingress_blocked = True
                self._stream_error = (
                    "模擬成交 Journal 寫入失敗，已停止接受新的模擬委託："
                    f"{type(error).__name__}"
                )

    def _quote_for(self, position: SimulationPosition) -> _QuoteState | None:
        return self._quotes.get(position.symbol)

    def _current_price(self, position: SimulationPosition) -> Decimal:
        quote = self._quote_for(position)
        if quote is None:
            return position.average_price
        if quote.last_price is not None:
            return quote.last_price
        if quote.snapshot is not None:
            return self._stock_price(quote.snapshot)
        return position.average_price

    def _run_quote_worker(self) -> None:
        while True:
            update = self._quote_updates.get()
            if update is None:
                return
            subscriptions_changed = self._apply_quote_update(update)
            if subscriptions_changed:
                self._sync_quote_subscriptions()

    def _apply_quote_update(self, update: RealtimeQuoteUpdate) -> bool:
        self._roll_trading_day()
        notifications: list[dict[str, Any]] = []
        with self._lock:
            if self._quote_ingress_blocked:
                return False
            desired_symbols = self._desired_quote_symbols()
            if update.symbol not in desired_symbols:
                return False
            quote = self._quotes.get(update.symbol)
            if quote is None:
                return False

            if update.kind == "TICK":
                if quote.last_trade_at and update.exchange_timestamp < quote.last_trade_at:
                    return False
                quote.last_price = self._optional_money(update.last_price)
                quote.last_trade_at = update.exchange_timestamp
            elif update.kind == "BIDASK":
                if quote.book_at and update.exchange_timestamp < quote.book_at:
                    return False
                quote.bid_price = self._optional_money(update.bid_price)
                quote.ask_price = self._optional_money(update.ask_price)
                quote.book_at = update.exchange_timestamp
                quote.book_received_at = update.received_at
                quote.bid_available_quantity = (
                    update.bid_volume_lots * 1_000
                    if update.bid_volume_lots is not None
                    else None
                )
                quote.ask_available_quantity = (
                    update.ask_volume_lots * 1_000
                    if update.ask_volume_lots is not None
                    else None
                )
            else:
                return False

            quote.received_at = max(
                quote.received_at or update.received_at,
                update.received_at,
            )
            filled = False
            if update.kind == "BIDASK":
                for order in self._orders.values():
                    if order.symbol != update.symbol or order.status not in _ACTIVE_ORDER_STATUSES:
                        continue
                    execution_price = self._stream_execution_price(order, quote)
                    if (
                        execution_price is not None
                        and self._is_marketable_price(order, execution_price)
                    ):
                        fill_quantity = self._book_fill_quantity(order, quote)
                        if fill_quantity > 0:
                            executed_quantity = self._fill(
                                order,
                                execution_price,
                                fill_quantity=fill_quantity,
                            )
                            if executed_quantity > 0:
                                self._consume_book_quantity(
                                    order,
                                    quote,
                                    executed_quantity,
                                )
                            notifications.append(self._order_payload(order))
                            filled = True
        for payload in notifications:
            self._notify_terminal_order(payload)
        return filled

    def _desired_quote_symbols(self) -> set[str]:
        return {
            *self._positions,
            *(
                order.symbol
                for order in self._orders.values()
                if order.status in _ACTIVE_ORDER_STATUSES
            ),
        }

    def _sync_quote_subscriptions(self) -> None:
        if not self._streaming_enabled:
            return
        with self._lock:
            if self._quote_ingress_blocked:
                return
            desired_symbols = self._desired_quote_symbols()
        try:
            subscribed = self._provider.sync_quote_subscriptions(desired_symbols)
        except Exception as error:
            with self._lock:
                self._stream_error = f"Shioaji 即時行情訂閱失敗：{error}"
            return
        with self._lock:
            self._subscribed_symbols = set(subscribed)
            self._stream_error = None

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise SimulationValidationError("請輸入股票代碼")
        return normalized

    @staticmethod
    def _normalize_side(side: str) -> OrderSide:
        try:
            return OrderSide(str(side).strip().upper())
        except ValueError as error:
            raise SimulationValidationError("交易方向只支援 BUY 或 SELL") from error

    @staticmethod
    def _normalize_lots(lots: int) -> int:
        if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
            raise SimulationValidationError("張數必須是大於 0 的整數")
        return lots

    @staticmethod
    def _normalize_quantity_shares(quantity_shares: int) -> int:
        if (
            isinstance(quantity_shares, bool)
            or not isinstance(quantity_shares, int)
            or quantity_shares <= 0
        ):
            raise SimulationValidationError("股數必須是大於 0 的整數")
        return quantity_shares

    @classmethod
    def _resolve_quantity_shares(
        cls,
        *,
        quantity_shares: int | None,
        lots: int | None,
    ) -> int:
        if quantity_shares is not None and lots is not None:
            raise SimulationValidationError("股數與張數不可同時提供")
        if quantity_shares is not None:
            return cls._normalize_quantity_shares(quantity_shares)
        if lots is not None:
            return cls._normalize_lots(lots) * 1_000
        raise SimulationValidationError("請輸入股數")

    @classmethod
    def _restored_quantity_shares(cls, raw: dict[str, Any]) -> int:
        if raw.get("quantity_shares") is not None:
            quantity = int(raw["quantity_shares"])
        elif raw.get("quantity") is not None:
            quantity = int(raw["quantity"])
        else:
            quantity = int(raw["lots"]) * 1_000
        return cls._normalize_quantity_shares(quantity)

    @staticmethod
    def _normalize_price(limit_price: Decimal | float | int | str) -> Decimal:
        try:
            normalized = Decimal(str(limit_price))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise SimulationValidationError("限價必須是數字") from error
        if not normalized.is_finite() or normalized <= 0:
            raise SimulationValidationError("限價必須是大於 0 的有限數字")
        return normalized

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        normalized = str(idempotency_key).strip()
        if not normalized:
            raise SimulationValidationError("缺少冪等識別碼")
        if len(normalized) > 128:
            raise SimulationValidationError("冪等識別碼過長")
        return normalized

    @staticmethod
    def _optional_identity(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise SimulationValidationError("策略歸屬識別不可為空")
        return normalized

    @staticmethod
    def _same_owner(order: SimulationOrder, position: SimulationPosition) -> bool:
        if order.origin != position.owner_origin:
            return False
        if order.origin != "STRATEGY_AUTOMATED":
            return True
        return order.strategy_id == position.owner_strategy_id

    @staticmethod
    def _same_order_owner(left: SimulationOrder, right: SimulationOrder) -> bool:
        if left.origin != right.origin:
            return False
        if left.origin != "STRATEGY_AUTOMATED":
            return True
        return left.strategy_id == right.strategy_id

    def _now(self) -> datetime:
        return self._clock.now().astimezone(_TAIPEI)

    def _market_value(self) -> Decimal:
        return sum(
            (
                position.quantity * self._current_price(position)
                for position in self._positions.values()
            ),
            Decimal("0"),
        )

    def _ensure_trading_day(self) -> None:
        trading_date = self._clock.session_date()
        if trading_date == self._trading_date:
            return
        self._opening_equity = self._cash + self._market_value()
        self._opening_realized_pnl = sum(
            self._realized_pnl_by_symbol.values(),
            Decimal("0"),
        )
        self._trading_date = trading_date
        self._pending_daily_baselines.append(self._daily_baseline_payload())

    def _roll_trading_day(self) -> None:
        with self._lock:
            self._ensure_trading_day()
            notifications = self._pending_daily_baselines
            self._pending_daily_baselines = []
            handler = self._daily_baseline_handler
        if handler is None:
            return
        for payload in notifications:
            try:
                handler(payload)
            except Exception as error:
                with self._lock:
                    self._quote_ingress_blocked = True
                    self._stream_error = (
                        "交易日風控基準 Journal 寫入失敗，已停止接受新的模擬委託："
                        f"{type(error).__name__}"
                    )

    def _daily_baseline_payload(self) -> dict[str, Any]:
        return {
            "trading_date": self._trading_date.isoformat(),
            "opening_equity": str(self._opening_equity),
            "opening_realized_pnl": str(self._opening_realized_pnl),
            "includes_unrealized_pnl": True,
            "created_at": self._now().isoformat(),
        }

    def _order_payload(self, order: SimulationOrder) -> dict[str, Any]:
        quote = self._quotes.get(order.symbol)
        waiting_reason = None
        if order.status in _ACTIVE_ORDER_STATUSES and self._stream_capable:
            if quote is None or quote.book_received_at is None:
                waiting_reason = "WAITING_FOR_FIRST_BIDASK"
            elif self._stream_execution_price(order, quote) is None:
                waiting_reason = "WAITING_FOR_FRESH_BIDASK"
            else:
                waiting_reason = "LIMIT_NOT_REACHED"
        return {
            "order_id": order.order_id,
            "idempotency_key": order.idempotency_key,
            "origin": order.origin,
            "strategy_id": order.strategy_id,
            "strategy_version": order.strategy_version,
            "symbol": order.symbol,
            "name": order.name,
            "side": order.side.value,
            "lots": order.lots,
            "quantity_shares": order.quantity_shares,
            "quantity": order.quantity,
            "remaining_quantity": order.remaining_quantity,
            "limit_price": float(order.limit_price),
            "estimated_amount": float(order.quantity * order.limit_price),
            "status": order.status.value,
            "submitted_at": order.submitted_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "filled_price": float(order.filled_price) if order.filled_price is not None else None,
            "filled_quantity": order.filled_quantity,
            "last_fill_price": (
                float(order.last_fill_price)
                if order.last_fill_price is not None
                else None
            ),
            "last_fill_quantity": order.last_fill_quantity,
            "fill_sequence": order.fill_sequence,
            "filled_amount": (
                float(order.filled_notional)
                if order.filled_quantity > 0
                else None
            ),
            "attempt": order.attempt,
            "predecessor_order_id": order.predecessor_order_id,
            "timeout_at": order.timeout_at.isoformat() if order.timeout_at else None,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
            "trading_date": self._trading_date.isoformat(),
            "opening_equity": float(self._opening_equity),
            "reason": order.reason,
            "waiting_reason": waiting_reason,
            "bid_price": (
                float(quote.bid_price)
                if quote is not None and quote.bid_price is not None
                else None
            ),
            "ask_price": (
                float(quote.ask_price)
                if quote is not None and quote.ask_price is not None
                else None
            ),
            "last_quote_at": (
                quote.book_at.isoformat()
                if quote is not None and quote.book_at is not None
                else None
            ),
            "quote_received_at": (
                quote.book_received_at.isoformat()
                if quote is not None and quote.book_received_at is not None
                else None
            ),
            "fill_source": "paper_simulation",
            "provider_identity": self._provider_identity,
            "execution_authority": False,
        }

    def risk_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return local-only evidence for the command facade without provider I/O."""
        normalized_symbol = self._normalize_symbol(symbol)
        self._roll_trading_day()
        with self._lock:
            position = self._positions.get(normalized_symbol)
            pending = [
                order
                for order in self._orders.values()
                if order.symbol == normalized_symbol and order.status in _ACTIVE_ORDER_STATUSES
            ]
            quote = self._quotes.get(normalized_symbol)
            book_age = None
            if quote is not None and quote.book_received_at is not None:
                book_age = max(
                    0,
                    int((self._now() - quote.book_received_at).total_seconds()),
                )
            return {
                "data_health_state": (
                    "BLOCKED"
                    if self._quote_ingress_blocked
                    or (self._stream_capable and not self._streaming_enabled)
                    else "HEALTHY"
                ),
                "available_cash": self._available_cash(),
                "current_position_shares": position.quantity if position else 0,
                "pending_buy_shares": sum(
                    order.quantity for order in pending if order.side is OrderSide.BUY
                ),
                "pending_sell_shares": sum(
                    order.quantity for order in pending if order.side is OrderSide.SELL
                ),
                "daily_realized_pnl": sum(
                    self._realized_pnl_by_symbol.values(),
                    Decimal("0"),
                )
                - self._opening_realized_pnl,
                "daily_loss": max(
                    Decimal("0"),
                    self._opening_equity - (self._cash + self._market_value()),
                ),
                "book_age_seconds": book_age,
            }

    def order_for_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            order_id = self._order_ids_by_key.get(normalized_key)
            return self._order_payload(self._orders[order_id]) if order_id else None

    def cancel_order_for_idempotency_key(
        self,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            order_id = self._cancel_order_ids_by_key.get(normalized_key)
            return self._order_payload(self._orders[order_id]) if order_id else None

    def record_risk_rejection(
        self,
        *,
        symbol: str,
        side: str,
        quantity_shares: int,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        reason: str,
        origin: str = "MANUAL_WEB",
    ) -> dict[str, Any]:
        """Project a RiskGate rejection without calling a broker or quote stream."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_quantity_shares = self._normalize_quantity_shares(quantity_shares)
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id])
            if self._stream_capable:
                stock_symbol, stock_name = self._get_stock_identity(normalized_symbol)
            else:
                stock = self._get_stock(normalized_symbol)
                stock_symbol, stock_name = stock.symbol, stock.name
            now = self._now()
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=origin,
                symbol=stock_symbol,
                name=stock_name,
                side=normalized_side,
                quantity_shares=normalized_quantity_shares,
                limit_price=normalized_price,
                status=OrderStatus.REJECTED,
                submitted_at=now,
                updated_at=now,
                reason=reason,
            )
            self._orders[order.order_id] = order
            self._order_ids_by_key[normalized_key] = order.order_id
            return self._order_payload(order)

    def _reserved_cash(self) -> Decimal:
        return sum(self._reserved_buy_notional_by_order.values(), Decimal("0"))

    def _available_cash(self) -> Decimal:
        return self._cash - self._reserved_cash()

    def _stream_health(self) -> str:
        if self._quote_ingress_blocked:
            return "BLOCKED"
        if self._stream_capable and not self._streaming_enabled:
            return "DEGRADED"
        return "HEALTHY"

    @staticmethod
    def _money(value: Decimal | float | int | str, field_name: str) -> Decimal:
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f"{field_name} 必須是數字") from error
        if not normalized.is_finite():
            raise ValueError(f"{field_name} 必須是有限數字")
        return normalized

    @classmethod
    def _optional_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            normalized = cls._money(value, "quote")
        except ValueError:
            return None
        return normalized if normalized > 0 else None

    @classmethod
    def _stock_price(cls, stock: StockData) -> Decimal:
        return cls._money(stock.price, "stock.price")
