"""Tests for CandidateEngine."""

from datetime import datetime

from candidate.engine import CandidateEngine
from candidate.models import CandidateSource
from candidate.rules import GapUpRule, HighVolumeRule
from market_data.models import StockData

_TS = datetime(2026, 1, 1, 9, 5, 0)


def make_stock(
    symbol: str = "TEST",
    price: float = 103.0,
    open_: float = 103.0,
    previous_close: float = 100.0,
    volume: int = 200_000,
    previous_day_volume: int = 100_000,
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
        vwap=None,
    )


class TestCandidateEngine:
    def setup_method(self):
        self.engine = CandidateEngine(
            rules=[
                GapUpRule(min_pct=2.0, max_pct=4.0),
                HighVolumeRule(min_volume=100_000),
            ]
        )

    def test_matching_stock_is_candidate(self):
        stock = make_stock(previous_close=100.0, open_=103.0, volume=50_000)
        results = self.engine.scan([stock])
        assert len(results) == 1
        assert results[0].symbol == stock.symbol

    def test_candidate_has_no_stock_field(self):
        """Candidate 不應保存 StockData 快照。"""
        stock = make_stock(previous_close=100.0, open_=103.0, volume=50_000)
        results = self.engine.scan([stock])
        assert not hasattr(results[0], "stock")

    def test_candidate_source_is_auto_enum(self):
        stock = make_stock(previous_close=100.0, open_=103.0, volume=50_000)
        results = self.engine.scan([stock])
        assert CandidateSource.AUTO in results[0].sources

    def test_candidate_sources_is_set(self):
        stock = make_stock(previous_close=100.0, open_=103.0, volume=50_000)
        results = self.engine.scan([stock])
        assert isinstance(results[0].sources, set)

    def test_stock_matching_high_volume_is_candidate(self):
        stock = make_stock(previous_close=100.0, open_=100.0, volume=150_000)
        results = self.engine.scan([stock])
        assert len(results) == 1
        assert "high_volume" in results[0].matched_rules

    def test_stock_matching_both_rules_has_both_in_matched(self):
        stock = make_stock(previous_close=100.0, open_=103.0, volume=150_000)
        results = self.engine.scan([stock])
        assert len(results) == 1
        assert "gap_up" in results[0].matched_rules
        assert "high_volume" in results[0].matched_rules

    def test_stock_matching_no_rule_is_excluded(self):
        stock = make_stock(previous_close=100.0, open_=100.0, volume=10_000)
        results = self.engine.scan([stock])
        assert len(results) == 0

    def test_empty_market_returns_empty(self):
        results = self.engine.scan([])
        assert results == []

    def test_multiple_stocks_filtered_correctly(self):
        s1 = make_stock("AAA", previous_close=100.0, open_=103.0, volume=50_000)
        s2 = make_stock("BBB", previous_close=100.0, open_=100.0, volume=200_000)
        s3 = make_stock("CCC", previous_close=100.0, open_=100.0, volume=5_000)

        results = self.engine.scan([s1, s2, s3])
        symbols = [r.symbol for r in results]

        assert "AAA" in symbols
        assert "BBB" in symbols
        assert "CCC" not in symbols
        assert len(results) == 2

    def test_no_rules_engine_returns_empty(self):
        engine = CandidateEngine(rules=[])
        stock = make_stock(previous_close=100.0, open_=103.0, volume=200_000)
        results = engine.scan([stock])
        assert results == []
