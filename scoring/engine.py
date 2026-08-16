"""
Buy Score Engine

只對 Candidate Pool 內的股票評分，不掃描全市場。
計算結果保留完整 breakdown，讓使用者可以理解評分原因。
"""

from market_data.models import StockData
from scoring.models import BuyScoreResult, ScoreDetail
from scoring.rules import ScoreRule


class BuyScoreEngine:
    """
    對 Candidate Pool 中的每一檔股票計算買入評分。

    設計原則：
    - 只對已進入 Candidate Pool 的股票評分（由 app.py 保證）
    - 評分結果必須包含 breakdown，不可只回一個數字
    """

    def __init__(self, rules: list[ScoreRule]) -> None:
        self.rules = rules

    def calculate(self, stock: StockData) -> BuyScoreResult:
        """
        計算單一股票的買入評分。

        Args:
            stock: 已在 Candidate Pool 中的股票資料。

        Returns:
            BuyScoreResult，包含 total_score 與各 Rule 的 ScoreDetail。
        """
        details: list[ScoreDetail] = []
        total = 0

        for rule in self.rules:
            s = rule.score(stock)
            total += s
            details.append(
                ScoreDetail(
                    rule=rule.name,
                    score=s,
                    max_score=rule.max_score,
                )
            )

        return BuyScoreResult(
            symbol=stock.symbol,
            total_score=total,
            details=details,
        )
