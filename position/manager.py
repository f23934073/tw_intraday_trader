"""
Position Manager

管理使用者目前持有的所有股票部位。

重要：Position 股票永遠必須持續監控。
即使它不在 Candidate Pool、Buy Score 很低，也不可停止監控。
"""

from position.models import Position


class PositionManager:
    """管理所有持倉的新增、刪除與查詢。"""

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def add(self, position: Position) -> None:
        """新增或更新持倉（以 symbol 為 key）。"""
        self.positions[position.symbol] = position

    def remove(self, symbol: str) -> None:
        """移除持倉（若不存在則靜默忽略）。"""
        self.positions.pop(symbol, None)

    def get(self, symbol: str) -> Position | None:
        """取得單一持倉，不存在時回傳 None。"""
        return self.positions.get(symbol)

    def get_all(self) -> list[Position]:
        """取得所有持倉列表。"""
        return list(self.positions.values())

    def __len__(self) -> int:
        return len(self.positions)
