"""
Candidate Rules — 選股邏輯池

每個 Rule 回答：「這檔股票值得進入候選觀察池嗎？」
符合任一 Rule 即可進入 Candidate Pool。

threshold 參數統一從 config.settings 取得，避免 magic number 散落。
"""

from market_data.models import StockData
from config import settings


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------


class CandidateRule:
    """Candidate Rule 基礎類別。"""

    name: str

    def match(self, stock: StockData) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class GapUpRule(CandidateRule):
    """
    開盤跳空 Rule。

    條件：今日開盤價相對昨日收盤價的漲幅介於 [min_pct, max_pct]。
    預設：+2% ~ +4%（甜蜜區間，太大可能追高，太小不夠強）。
    """

    name = "gap_up"

    def __init__(
        self,
        min_pct: float = settings.GAP_UP_MIN_PCT,
        max_pct: float = settings.GAP_UP_MAX_PCT,
    ) -> None:
        self.min_pct = min_pct
        self.max_pct = max_pct

    def match(self, stock: StockData) -> bool:
        if stock.previous_close <= 0:
            return False

        gap_pct = (
            (stock.open - stock.previous_close)
            / stock.previous_close
            * 100
        )

        return self.min_pct <= gap_pct <= self.max_pct


class HighVolumeRule(CandidateRule):
    """
    成交量絕對值 Rule。

    [MVP Only / Deprecated]
    盤中不能單純用絕對成交量判斷，09:05 的十萬股 vs 12:30 的十萬股意義完全不同。
    建議改用 RelativeVolumeRule（RVOL），此 Rule 保留供測試與向下相容用。

    條件：今日成交量 >= 指定最小量（預設 100,000 股）。
    """

    name = "high_volume"

    def __init__(
        self,
        min_volume: int = settings.HIGH_VOLUME_MIN,
    ) -> None:
        self.min_volume = min_volume

    def match(self, stock: StockData) -> bool:
        return stock.volume >= self.min_volume


class RelativeVolumeRule(CandidateRule):
    """
    Relative Volume（RVOL）Rule。

    條件：stock.relative_volume >= min_ratio

    RVOL 定義：
        今天 HH:MM:SS 之前的累積成交量
        ÷
        過去 N 日同一時段的平均累積成交量

    例如 09:30 RVOL = 2.4：
        今天開盤到 09:30 的量，是過去 20 日同期的 2.4 倍。

    比 HighVolumeRule 更準確，因為考慮了盤中時段差異。

    注意：
        MockProvider 目前不提供 relative_volume（回傳 None）。
        股票的 relative_volume 需要歷史資料才能計算。
        若 stock.relative_volume is None → 不符合（直接 False）。
    """

    name = "relative_volume"

    def __init__(
        self,
        min_ratio: float = settings.RELATIVE_VOLUME_MIN_RATIO,
    ) -> None:
        self.min_ratio = min_ratio

    def match(self, stock: StockData) -> bool:
        if stock.relative_volume is None:
            return False

        return stock.relative_volume >= self.min_ratio
