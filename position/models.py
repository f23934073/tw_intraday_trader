"""Position 資料模型。"""

from dataclasses import dataclass


@dataclass
class Position:
    """
    使用者目前持有的單一股票部位。

    第一版由使用者手動輸入，不自動下單。
    """

    symbol: str
    entry_price: float
    quantity: int
