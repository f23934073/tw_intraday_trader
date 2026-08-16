"""
Exit Rules — 出場邏輯池

回答：已經持有股票後，什麼時候應該退出？

第一版只做最容易理解的兩個：
- StopLossRule：停損
- TakeProfitRule：停利

未來可增加：
- VWAPBreakdownRule（跌破 VWAP）
- MomentumReverseRule
- TrailingStopRule
- OpeningRangeBreakdownRule
- VolumeDeclineRule
"""

from market_data.models import StockData
from position.models import Position
from config import settings


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------


class ExitRule:
    """Exit Rule 基礎類別。"""

    name: str

    def should_exit(
        self,
        position: Position,
        stock: StockData,
    ) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class StopLossRule(ExitRule):
    """
    停損 Rule。

    當現價相對進場價的跌幅超過 percent 時，觸發停損。
    例如：percent=0.02 → 跌超過 2% 時出場。
    """

    name = "stop_loss"

    def __init__(
        self,
        percent: float = settings.STOP_LOSS_PCT,
    ) -> None:
        self.percent = percent

    def should_exit(
        self,
        position: Position,
        stock: StockData,
    ) -> bool:
        pnl_pct = (
            stock.price - position.entry_price
        ) / position.entry_price

        return pnl_pct <= -self.percent


class TakeProfitRule(ExitRule):
    """
    停利 Rule。

    當現價相對進場價的漲幅超過 percent 時，觸發停利。
    例如：percent=0.03 → 漲超過 3% 時出場。
    """

    name = "take_profit"

    def __init__(
        self,
        percent: float = settings.TAKE_PROFIT_PCT,
    ) -> None:
        self.percent = percent

    def should_exit(
        self,
        position: Position,
        stock: StockData,
    ) -> bool:
        pnl_pct = (
            stock.price - position.entry_price
        ) / position.entry_price

        return pnl_pct >= self.percent
