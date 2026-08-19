"""本機紙上模擬的共用下單指令與投影服務。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from queue import Full, Queue
from threading import RLock, Thread
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_data.models import RealtimeQuoteUpdate, StockData
from market_data.provider import MarketDataProvider
from simulation.models import (
    OrderSide,
    OrderStatus,
    SimulationOrder,
    SimulationPosition,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DEFAULT_STARTING_CASH = Decimal("10000000")
_RECENT_BOOK_SECONDS = 15.0
_DEFAULT_QUOTE_QUEUE_CAPACITY = 1_024


@dataclass
class _QuoteState:
    """合併 snapshot、Tick 與 BidAsk，但分開維持兩條 stream 的順序。"""

    snapshot: StockData
    last_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    last_trade_at: datetime | None = None
    book_at: datetime | None = None
    received_at: datetime | None = None
    book_received_at: datetime | None = None


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

        self._provider = provider
        self._starting_cash = normalized_starting_cash
        self._cash = normalized_starting_cash
        self._orders: dict[str, SimulationOrder] = {}
        self._order_ids_by_key: dict[str, str] = {}
        self._cancel_order_ids_by_key: dict[str, str] = {}
        self._reserved_buy_notional_by_order: dict[str, Decimal] = {}
        self._positions: dict[str, SimulationPosition] = {}
        self._quotes: dict[str, _QuoteState] = {}
        self._realized_pnl_by_symbol: dict[str, Decimal] = {}
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

    def session(self) -> dict[str, Any]:
        """回傳不會觸發 Provider 或券商呼叫的 session 中繼資料。"""
        with self._lock:
            market_value = sum(
                (
                    position.quantity * self._current_price(position)
                    for position in self._positions.values()
                ),
                Decimal("0"),
            )
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
                "委託與持倉只存在本機記憶體；行情來自 Shioaji Tick／BidAsk，"
                "不會送出 Shioaji 或真實券商委託。"
                if self._stream_capable
                else "本機紙上模擬，重啟後委託與持倉會清空；"
                "不會送出 Shioaji 或真實券商委託。"
            )
            return {
                "mode": self.mode,
                "label": label,
                "ordering_enabled": True,
                "starting_cash": float(self._starting_cash),
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
        return {
            "session": self.session(),
            "orders": self.orders(),
            "positions": self.positions(),
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

    def positions(self) -> list[dict[str, Any]]:
        """讀取由已成交委託建立的持倉投影，不會呼叫資料來源。"""
        with self._lock:
            positions: list[dict[str, Any]] = []
            for position in sorted(self._positions.values(), key=lambda item: item.symbol):
                quote = self._quote_for(position)
                current_price = self._current_price(position)
                market_value = position.quantity * current_price
                unrealized_pnl = position.quantity * (current_price - position.average_price)
                quote_at = (
                    quote.received_at or quote.snapshot.timestamp
                    if quote is not None
                    else None
                )
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
                        "bid_price": float(quote.bid_price) if quote and quote.bid_price else None,
                        "ask_price": float(quote.ask_price) if quote and quote.ask_price else None,
                        "last_quote_at": quote_at.isoformat() if quote_at else None,
                        "quote_received_at": (
                            quote.received_at.isoformat()
                            if quote and quote.received_at
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
        lots: int,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        origin: str = "MANUAL_WEB",
    ) -> tuple[dict[str, Any], bool]:
        """接受限價委託；串流模式以賣一／買一，本機模式以 snapshot 撮合。"""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_lots = self._normalize_lots(lots)
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_idempotency_key(idempotency_key)

        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id]), True

            stock = self._get_stock(normalized_symbol)
            self._quotes.setdefault(stock.symbol, _QuoteState(snapshot=stock)).snapshot = stock
            now = datetime.now(_TAIPEI)
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=origin,
                symbol=stock.symbol,
                name=stock.name,
                side=normalized_side,
                lots=normalized_lots,
                limit_price=normalized_price,
                status=OrderStatus.SUBMITTED,
                submitted_at=now,
                updated_at=now,
            )
            self._orders[order.order_id] = order
            self._order_ids_by_key[normalized_key] = order.order_id

            if normalized_side is OrderSide.BUY:
                reserved = order.quantity * order.limit_price
                if reserved > self._available_cash():
                    self._reject(order, "可用虛擬現金不足")
                else:
                    self._reserved_buy_notional_by_order[order.order_id] = reserved
            else:
                if order.quantity > self._available_to_sell(
                    order.symbol,
                    exclude_order_id=order.order_id,
                ):
                    self._reject(order, "可賣出持股不足")

            if order.status is OrderStatus.SUBMITTED:
                execution_price = (
                    self._stream_execution_price(order, self._quotes[stock.symbol])
                    if self._stream_capable
                    else self._stock_price(stock)
                )
                if (
                    execution_price is not None
                    and self._is_marketable_price(order, execution_price)
                ):
                    self._fill(order, execution_price)

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
            if order.status is not OrderStatus.SUBMITTED:
                raise SimulationStateError("只有已送出的委託可以取消")

            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now(_TAIPEI)
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

        with self._lock:
            symbols = {
                *self._positions,
                *(
                    order.symbol
                    for order in self._orders.values()
                    if order.status is OrderStatus.SUBMITTED
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
                    and order.status is OrderStatus.SUBMITTED
                    and self._is_marketable_price(order, self._stock_price(quote))
                ):
                    self._fill(order, self._stock_price(quote))

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

    @staticmethod
    def _is_marketable_price(order: SimulationOrder, execution_price: Decimal) -> bool:
        return (
            order.limit_price >= execution_price
            if order.side is OrderSide.BUY
            else order.limit_price <= execution_price
        )

    @staticmethod
    def _stream_execution_price(
        order: SimulationOrder,
        quote: _QuoteState,
    ) -> Decimal | None:
        if quote.book_received_at is None or quote.book_at is None:
            return None
        age = (datetime.now(_TAIPEI) - quote.book_received_at).total_seconds()
        if age > _RECENT_BOOK_SECONDS:
            return None
        return quote.ask_price if order.side is OrderSide.BUY else quote.bid_price

    def _available_to_sell(
        self,
        symbol: str,
        exclude_order_id: str | None = None,
    ) -> int:
        position = self._positions.get(symbol)
        held_quantity = position.quantity if position else 0
        pending_quantity = sum(
            order.quantity
            for order in self._orders.values()
            if (
                order.symbol == symbol
                and order.side is OrderSide.SELL
                and order.status is OrderStatus.SUBMITTED
                and order.order_id != exclude_order_id
            )
        )
        return held_quantity - pending_quantity

    def _fill(self, order: SimulationOrder, fill_price: Decimal) -> None:
        """在 lock 內以已驗證的 snapshot／買一／賣一完成本機紙上成交。"""
        if order.side is OrderSide.BUY:
            fill_amount = order.quantity * fill_price
            if fill_amount > self._cash:
                self._reject(order, "目前報價造成可用虛擬現金不足")
                return

            position = self._positions.get(order.symbol)
            if position is None:
                self._positions[order.symbol] = SimulationPosition(
                    symbol=order.symbol,
                    name=order.name,
                    quantity=order.quantity,
                    average_price=fill_price,
                )
            else:
                total_quantity = position.quantity + order.quantity
                position.average_price = (
                    position.average_price * position.quantity
                    + fill_price * order.quantity
                ) / total_quantity
                position.quantity = total_quantity
            self._cash -= fill_amount
        else:
            position = self._positions.get(order.symbol)
            if position is None or position.quantity < order.quantity:
                self._reject(order, "可賣出持股不足")
                return

            realized_pnl = (fill_price - position.average_price) * order.quantity
            self._realized_pnl_by_symbol[order.symbol] = (
                self._realized_pnl_by_symbol.get(order.symbol, Decimal("0"))
                + realized_pnl
            )
            position.quantity -= order.quantity
            self._cash += order.quantity * fill_price
            if position.quantity == 0:
                del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        order.updated_at = datetime.now(_TAIPEI)

    def _reject(self, order: SimulationOrder, reason: str) -> None:
        order.status = OrderStatus.REJECTED
        order.reason = reason
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        order.updated_at = datetime.now(_TAIPEI)

    def _quote_for(self, position: SimulationPosition) -> _QuoteState | None:
        return self._quotes.get(position.symbol)

    def _current_price(self, position: SimulationPosition) -> Decimal:
        quote = self._quote_for(position)
        if quote is None:
            return position.average_price
        return quote.last_price or self._stock_price(quote.snapshot)

    def _run_quote_worker(self) -> None:
        while True:
            update = self._quote_updates.get()
            if update is None:
                return
            subscriptions_changed = self._apply_quote_update(update)
            if subscriptions_changed:
                self._sync_quote_subscriptions()

    def _apply_quote_update(self, update: RealtimeQuoteUpdate) -> bool:
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
            else:
                return False

            quote.received_at = max(
                quote.received_at or update.received_at,
                update.received_at,
            )
            filled = False
            if update.kind == "BIDASK":
                for order in self._orders.values():
                    if order.symbol != update.symbol or order.status is not OrderStatus.SUBMITTED:
                        continue
                    execution_price = self._stream_execution_price(order, quote)
                    if (
                        execution_price is not None
                        and self._is_marketable_price(order, execution_price)
                    ):
                        self._fill(order, execution_price)
                        filled = True
            return filled

    def _desired_quote_symbols(self) -> set[str]:
        return {
            *self._positions,
            *(
                order.symbol
                for order in self._orders.values()
                if order.status is OrderStatus.SUBMITTED
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
    def _order_payload(order: SimulationOrder) -> dict[str, Any]:
        return {
            "order_id": order.order_id,
            "origin": order.origin,
            "symbol": order.symbol,
            "name": order.name,
            "side": order.side.value,
            "lots": order.lots,
            "quantity": order.quantity,
            "limit_price": float(order.limit_price),
            "estimated_amount": float(order.quantity * order.limit_price),
            "status": order.status.value,
            "submitted_at": order.submitted_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "filled_price": float(order.filled_price) if order.filled_price is not None else None,
            "filled_quantity": order.filled_quantity,
            "filled_amount": (
                float(order.filled_price * order.filled_quantity)
                if order.filled_price is not None
                else None
            ),
            "reason": order.reason,
        }

    def risk_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return local-only evidence for the command facade without provider I/O."""
        normalized_symbol = self._normalize_symbol(symbol)
        with self._lock:
            position = self._positions.get(normalized_symbol)
            pending = [
                order
                for order in self._orders.values()
                if order.symbol == normalized_symbol and order.status is OrderStatus.SUBMITTED
            ]
            quote = self._quotes.get(normalized_symbol)
            book_age = None
            if quote is not None and quote.book_received_at is not None:
                book_age = max(
                    0,
                    int((datetime.now(_TAIPEI) - quote.book_received_at).total_seconds()),
                )
            return {
                "data_health_state": "BLOCKED" if self._quote_ingress_blocked else "HEALTHY",
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
        lots: int,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        reason: str,
        origin: str = "MANUAL_WEB",
    ) -> dict[str, Any]:
        """Project a RiskGate rejection without calling a broker or quote stream."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_lots = self._normalize_lots(lots)
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id])
            stock = self._get_stock(normalized_symbol)
            now = datetime.now(_TAIPEI)
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=origin,
                symbol=stock.symbol,
                name=stock.name,
                side=normalized_side,
                lots=normalized_lots,
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
