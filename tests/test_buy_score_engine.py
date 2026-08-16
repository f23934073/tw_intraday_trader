"""Tests for BuyScoreEngine."""

from datetime import datetime

from scoring.engine import BuyScoreEngine
from scoring.rules import AboveVWAPRule, GapScoreRule
from market_data.models import StockData

_TS = datetime(2026, 1, 1, 9, 5, 0)


def make_stock(
    symbol: str = "TEST",
    price: float = 103.0,
    open_: float = 103.0,
    previous_close: float = 100.0,
    volume: int = 200_000,
    previous_day_volume: int = 100_000,
    vwap: float | None = 102.0,
) -> StockData:
    return StockData(
        symbol=symbol,
        name=symbol,
        timestamp=_TS,
        price=price,
        open=open_,
        high=price + 2,
        low=price - 2,
        previous_close=previous_close,
        volume=volume,
        previous_day_volume=previous_day_volume,
        vwap=vwap,
    )


class TestBuyScoreEngine:
    def setup_method(self):
        self.engine = BuyScoreEngine(
            rules=[
                GapScoreRule(min_pct=2.0, max_pct=4.0),
                AboveVWAPRule(),
            ]
        )

    def test_both_rules_give_full_score(self):
        # Gap = 3% ✓, price(103) > vwap(102) ✓
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=102.0)
        result = self.engine.calculate(stock)
        assert result.total_score == 40  # 20 + 20
        assert result.symbol == stock.symbol

    def test_only_gap_matches(self):
        # Gap = 3% ✓, price(103) < vwap(104) ✗
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=104.0)
        result = self.engine.calculate(stock)
        assert result.total_score == 20

    def test_only_vwap_matches(self):
        # Gap = 0% ✗, price(103) > vwap(102) ✓
        stock = make_stock(price=103.0, open_=100.0, previous_close=100.0, vwap=102.0)
        result = self.engine.calculate(stock)
        assert result.total_score == 20

    def test_no_rule_matches_gives_zero(self):
        # Gap = 0% ✗, price(99) < vwap(102) ✗
        stock = make_stock(price=99.0, open_=100.0, previous_close=100.0, vwap=102.0)
        result = self.engine.calculate(stock)
        assert result.total_score == 0

    def test_result_has_score_breakdown(self):
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=102.0)
        result = self.engine.calculate(stock)
        # Must have details for every rule
        assert len(result.details) == 2
        rule_names = {d.rule for d in result.details}
        assert "gap_score" in rule_names
        assert "above_vwap" in rule_names

    def test_breakdown_scores_sum_to_total(self):
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=102.0)
        result = self.engine.calculate(stock)
        assert sum(d.score for d in result.details) == result.total_score

    def test_vwap_none_above_vwap_gives_zero(self):
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=None)
        result = self.engine.calculate(stock)
        # Gap matches (20), AboveVWAP should give 0 (vwap is None)
        assert result.total_score == 20

    def test_no_rules_engine_gives_zero(self):
        engine = BuyScoreEngine(rules=[])
        stock = make_stock(price=103.0, open_=103.0, previous_close=100.0, vwap=102.0)
        result = engine.calculate(stock)
        assert result.total_score == 0
        assert result.details == []
