"""
Market Data Models

StockData 是系統的核心資料結構。
所有模組只認識 StockData，禁止直接依賴 Shioaji SDK。

責任定義：
    StockData = 「現在這檔股票市場上長怎樣」
    不是「系統對這檔股票知道的所有事情」

    Candidate、BuyScoreResult 等衍生資訊不放進 StockData。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class StockData:
    """代表單一股票的即時市場資料快照。"""

    symbol: str
    name: str

    timestamp: datetime  # 資料產生時間，用於 Data Health 判斷資料是否過期

    price: float
    open: float
    high: float
    low: float

    previous_close: float

    volume: int
    previous_day_volume: int

    vwap: float | None = None

    relative_volume: float | None = None
    # Relative Volume（RVOL）：今天到目前為止成交量 ÷ 過去 N 日同期平均成交量
    # 例如 RVOL = 2.4 代表今天同期成交量是平常的 2.4 倍
    # 比絕對量閾值（volume >= 100000）更有意義，因為盤中不同時段的成交節奏不同
    # ShioajiProvider 可填入 volume_ratio（今日累積量 ÷ 昨日成交量）。
    # 若要嚴格的「過去 N 日同期平均」RVOL，仍需另外用歷史資料計算。

    market: str | None = None  # 'TWSE' / 'TPEX'，未來 Scanner 可依市場分流處理

    # 未來可視需求增加：
    # bid: float | None = None
    # ask: float | None = None
    # first_5m_high: float | None = None
    # first_5m_low: float | None = None
    # first_5m_close: float | None = None
    # amount: float | None = None
    # ma5: float | None = None
    # ma20: float | None = None
    # atr: float | None = None


@dataclass(frozen=True)
class KBar:
    """由市場資料 Provider 回傳的一根 OHLCV K 棒。"""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class RealtimeQuoteUpdate:
    """資料來源推送的一筆即時成交或五檔最佳價更新。"""

    symbol: str
    kind: str  # "TICK" / "BIDASK"
    exchange_timestamp: datetime
    received_at: datetime
    last_price: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    bid_volume_lots: int | None = None
    ask_volume_lots: int | None = None
