"""
Buy Score Rules — 買股評分邏輯池

每個 Rule 回答：「這檔已進入候選池的股票，現在有多值得買？」
分數越高代表買入訊號越強。

第一版使用 binary scoring（全或無）。
未來可改為漸進式（e.g. VWAP 偏離越多 → 分越高）。
"""

from market_data.models import StockData
from config import settings


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------


class ScoreRule:
    """Score Rule 基礎類別。"""

    name: str
    max_score: int

    def score(self, stock: StockData) -> int:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class AboveVWAPRule(ScoreRule):
    """
    價格在 VWAP 之上。

    VWAP（成交量加權平均價）是盤中多空分界線的重要指標。
    價格站上 VWAP 代表多方佔優。
    """

    name = "above_vwap"
    max_score = settings.ABOVE_VWAP_MAX_SCORE

    def score(self, stock: StockData) -> int:
        if stock.vwap is None:
            return 0

        if stock.price > stock.vwap:
            return self.max_score

        return 0


class GapScoreRule(ScoreRule):
    """
    開盤跳空評分。

    開盤在甜蜜區間（+2% ~ +4%）跳空，代表有方向性但不過度追高。
    threshold 從 config.settings 取得，與 GapUpRule 共用同一組設定值。
    """

    name = "gap_score"
    max_score = settings.GAP_SCORE_MAX_SCORE

    def __init__(
        self,
        min_pct: float = settings.GAP_UP_MIN_PCT,
        max_pct: float = settings.GAP_UP_MAX_PCT,
    ) -> None:
        self.min_pct = min_pct
        self.max_pct = max_pct

    def score(self, stock: StockData) -> int:
        if stock.previous_close <= 0:
            return 0

        gap_pct = (
            (stock.open - stock.previous_close)
            / stock.previous_close
            * 100
        )

        if self.min_pct <= gap_pct <= self.max_pct:
            return self.max_score

        return 0
