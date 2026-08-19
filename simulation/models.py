"""本機紙上模擬使用的訂單與持倉資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class OrderSide(StrEnum):
    """本機紙上模擬支援的多頭交易方向。"""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    """本機紙上模擬的精簡委託生命週期。"""

    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


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
    reason: str | None = None

    @property
    def quantity(self) -> int:
        """內部以股數表示成交與持倉數量。"""
        return self.lots * 1_000


@dataclass
class SimulationPosition:
    """由本機已成交委託推導出的多頭持倉。"""

    symbol: str
    name: str
    quantity: int
    average_price: Decimal
