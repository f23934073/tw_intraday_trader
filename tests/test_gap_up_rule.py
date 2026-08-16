"""Tests for GapUpRule."""

from datetime import datetime

import pytest

from candidate.rules import GapUpRule
from market_data.models import StockData

_TS = datetime(2026, 1, 1, 9, 5, 0)  # fixed timestamp for tests


def make_stock(
    symbol: str = "TEST",
    name: str = "Test",
    price: float = 103.0,
    open_: float = 103.0,
    high: float = 105.0,
    low: float = 102.0,
    previous_close: float = 100.0,
    volume: int = 200_000,
    previous_day_volume: int = 100_000,
    vwap: float | None = 102.0,
) -> StockData:
    return StockData(
        symbol=symbol,
        name=name,
        timestamp=_TS,
        price=price,
        open=open_,
        high=high,
        low=low,
        previous_close=previous_close,
        volume=volume,
        previous_day_volume=previous_day_volume,
        vwap=vwap,
    )


class TestGapUpRule:
    def setup_method(self):
        self.rule = GapUpRule(min_pct=2.0, max_pct=4.0)

    def test_gap_exactly_2_pct_matches(self):
        # open = previous_close * 1.02 → gap = 2%
        stock = make_stock(previous_close=100.0, open_=102.0)
        assert self.rule.match(stock) is True

    def test_gap_exactly_4_pct_matches(self):
        stock = make_stock(previous_close=100.0, open_=104.0)
        assert self.rule.match(stock) is True

    def test_gap_3_pct_matches(self):
        stock = make_stock(previous_close=100.0, open_=103.0)
        assert self.rule.match(stock) is True

    def test_gap_below_min_does_not_match(self):
        # 1% gap — below minimum
        stock = make_stock(previous_close=100.0, open_=101.0)
        assert self.rule.match(stock) is False

    def test_gap_above_max_does_not_match(self):
        # 5% gap — above maximum
        stock = make_stock(previous_close=100.0, open_=105.0)
        assert self.rule.match(stock) is False

    def test_zero_gap_does_not_match(self):
        stock = make_stock(previous_close=100.0, open_=100.0)
        assert self.rule.match(stock) is False

    def test_negative_gap_does_not_match(self):
        # Gap down
        stock = make_stock(previous_close=100.0, open_=98.0)
        assert self.rule.match(stock) is False

    def test_custom_thresholds(self):
        rule = GapUpRule(min_pct=1.0, max_pct=2.0)
        stock = make_stock(previous_close=100.0, open_=101.5)
        assert rule.match(stock) is True

    def test_zero_previous_close_does_not_crash(self):
        stock = make_stock(previous_close=0.0, open_=103.0)
        # Should not crash, should return False
        assert self.rule.match(stock) is False
