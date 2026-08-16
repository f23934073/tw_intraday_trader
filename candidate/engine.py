from candidate.models import Candidate, CandidateSource
from candidate.rules import CandidateRule
from market_data.models import StockData


class CandidateEngine:
    """
    Candidate Engine 接收市場股票清單，套用所有 Rule，
    回傳符合條件的 Candidate 列表。

    回傳的 Candidate 只保存 symbol，不保存 StockData 快照。
    評分時請從 MarketDataStore 取得最新行情。
    """

    def __init__(self, rules: list[CandidateRule]) -> None:
        self.rules = rules

    def scan(self, stocks: list[StockData]) -> list[Candidate]:
        """
        掃描所有股票，回傳符合至少一個 Rule 的 Candidate 列表。

        Args:
            stocks: 全市場（或指定範圍）的股票資料列表。

        Returns:
            符合條件的 Candidate 列表，source=AUTO。
        """
        results: list[Candidate] = []

        for stock in stocks:
            matched: list[str] = []

            for rule in self.rules:
                if rule.match(stock):
                    matched.append(rule.name)

            if matched:
                results.append(
                    Candidate(
                        symbol=stock.symbol,
                        sources={CandidateSource.AUTO},
                        matched_rules=matched,
                    )
                )

        return results
