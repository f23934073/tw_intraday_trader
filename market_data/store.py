"""
Market Data Store

系統的市場資料中心。

每當收到新的 StockData（來自 Shioaji Tick、Snapshot 或 Replay），
都呼叫 store.update(stock)，Store 只保留每個 symbol 的最新快照。

其他模組（CandidateEngine、BuyScoreEngine、PositionMonitor）
統一從 Store 取最新資料，不再傳遞舊快照：

    stock = store.get(symbol)

這樣即使 Candidate 是 09:05 產生的，
評分時取的 StockData 仍然是當下最新的行情。

未來整合即時架構：

    Shioaji Tick
         ↓
    MarketDataProvider
         ↓
    MarketDataStore.update(stock)
         ↓
    ┌────────┬────────┐
  Candidate  Scoring  Position
  Engine     Engine   Monitor
"""

from market_data.models import StockData


class MarketDataStore:
    """
    持有每個 symbol 最新 StockData 的 in-memory store。

    設計原則：
    - 只保留最新快照（每個 symbol 只有一筆）
    - 寫入：update(stock)
    - 讀取：get(symbol) / get_all()
    - 不做任何 business logic
    """

    def __init__(self) -> None:
        self._stocks: dict[str, StockData] = {}

    def update(self, stock: StockData) -> None:
        """
        寫入或更新 symbol 的最新 StockData。

        若已存在則覆蓋（舊快照不保留）。
        未來可在此處加入 timestamp 檢查，拒絕寫入過舊的資料。
        """
        self._stocks[stock.symbol] = stock

    def get(self, symbol: str) -> StockData | None:
        """取得 symbol 的最新 StockData，若不存在回傳 None。"""
        return self._stocks.get(symbol)

    def get_all(self) -> list[StockData]:
        """取得所有 symbol 的最新 StockData 列表。"""
        return list(self._stocks.values())

    def __len__(self) -> int:
        return len(self._stocks)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._stocks
