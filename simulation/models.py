"""本機紙上模擬使用的訂單與持倉資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from market_data.models import LocalPaperInstrumentDescriptorV1
from trading.exposure import (
    ExecutionReasonCategory,
    ExposureIdentity,
    PositionAction,
)
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
    quantity_shares: int
    limit_price: Decimal
    status: OrderStatus
    submitted_at: datetime
    updated_at: datetime
    filled_price: Decimal | None = None
    filled_quantity: int = 0
    filled_notional: Decimal = Decimal("0")
    filled_commission: Decimal = Decimal("0")
    filled_tax: Decimal = Decimal("0")
    filled_slippage_cost: Decimal = Decimal("0")
    last_fill_price: Decimal | None = None
    last_fill_quantity: int = 0
    last_fill_commission: Decimal = Decimal("0")
    last_fill_tax: Decimal = Decimal("0")
    last_reference_price: Decimal | None = None
    last_reference_source: str | None = None
    configured_slippage_bps: Decimal | None = None
    last_realized_slippage_bps: Decimal | None = None
    last_slippage_cost: Decimal = Decimal("0")
    last_net_cash_effect: Decimal | None = None
    fee_policy_version: str | None = None
    rounding_policy_version: str | None = None
    slippage_policy_version: str | None = None
    price_tick_policy_version: str | None = None
    instrument_descriptor: LocalPaperInstrumentDescriptorV1 | None = None
    waiting_reason: str | None = None
    fill_sequence: int = 0
    reason: str | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    attempt: int = 1
    predecessor_order_id: str | None = None
    timeout_at: datetime | None = None
    expires_at: datetime | None = None
    exposure: ExposureIdentity | None = None
    position_action: PositionAction | None = None
    target_exposure_id: str | None = None
    execution_reason_category: ExecutionReasonCategory | None = None
    execution_reason_code: str | None = None

    @property
    def quantity(self) -> int:
        """內部以股數表示成交與持倉數量。"""
        return self.quantity_shares

    @property
    def lots(self) -> int | None:
        """Legacy whole-lot projection; odd-lot orders have no exact lot value."""
        if self.quantity_shares % 1_000 != 0:
            return None
        return self.quantity_shares // 1_000

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
    commission_cost: Decimal = Decimal("0")
    owner_strategy_id: str | None = None
    owner_strategy_version: str | None = None
    exposure: ExposureIdentity | None = None
