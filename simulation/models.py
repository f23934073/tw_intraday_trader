"""本機紙上模擬使用的訂單與持倉資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading.trade_management import OrderLifecycleState


class OrderSide(StrEnum):
    """本機紙上模擬支援的多頭交易方向。"""

    BUY = "BUY"
    SELL = "SELL"


OrderStatus = OrderLifecycleState


@dataclass
class SimulationOrder:
    """一筆由網頁或未來策略程式送出的本機模擬委託。"""

    order_id: str
    idempotency_key: str
    origin: str
    symbol: str
    name: str
    side: OrderSide
    lots: int
    limit_price: Decimal
    status: OrderStatus
    submitted_at: datetime
    updated_at: datetime
    filled_price: Decimal | None = None
    filled_quantity: int = 0
    filled_notional: Decimal = Decimal("0")
    last_fill_price: Decimal | None = None
    last_fill_quantity: int = 0
    fill_sequence: int = 0
    reason: str | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    attempt: int = 1
    predecessor_order_id: str | None = None
    timeout_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def quantity(self) -> int:
        """內部以股數表示成交與持倉數量。"""
        return self.lots * 1_000

    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity


@dataclass
class SimulationPosition:
    """由本機已成交委託推導出的多頭持倉。"""

    symbol: str
    name: str
    quantity: int
    average_price: Decimal
    owner_origin: str
    owner_strategy_id: str | None = None
    owner_strategy_version: str | None = None
