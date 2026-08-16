"""Tests for StopLossRule and TakeProfitRule."""

from datetime import datetime

from position.exit_rules import StopLossRule, TakeProfitRule
from position.models import Position
from market_data.models import StockData

_TS = datetime(2026, 1, 1, 9, 5, 0)


def make_stock(symbol: str = "TEST", price: float = 200.0) -> StockData:
    return StockData(
        symbol=symbol,
        name=symbol,
        timestamp=_TS,
        price=price,
        open=200.0,
        high=205.0,
        low=195.0,
        previous_close=198.0,
        volume=100_000,
        previous_day_volume=80_000,
        vwap=200.0,
    )


class TestStopLossRule:
    def setup_method(self):
        self.rule = StopLossRule(percent=0.02)  # -2%
        self.position = Position(symbol="TEST", entry_price=200.0, quantity=1000)

    def test_no_exit_when_holding_steady(self):
        stock = make_stock(price=200.0)
        assert self.rule.should_exit(self.position, stock) is False

    def test_no_exit_when_profitable(self):
        stock = make_stock(price=206.0)  # +3%
        assert self.rule.should_exit(self.position, stock) is False

    def test_no_exit_when_loss_below_threshold(self):
        stock = make_stock(price=197.0)  # -1.5%
        assert self.rule.should_exit(self.position, stock) is False

    def test_exit_when_loss_equals_threshold(self):
        stock = make_stock(price=196.0)  # exactly -2%
        assert self.rule.should_exit(self.position, stock) is True

    def test_exit_when_loss_exceeds_threshold(self):
        stock = make_stock(price=190.0)  # -5%
        assert self.rule.should_exit(self.position, stock) is True

    def test_custom_percent(self):
        rule = StopLossRule(percent=0.05)  # -5%
        stock = make_stock(price=192.0)   # -4% → no exit
        assert rule.should_exit(self.position, stock) is False
        stock2 = make_stock(price=189.0)  # -5.5% → exit
        assert rule.should_exit(self.position, stock2) is True


class TestTakeProfitRule:
    def setup_method(self):
        self.rule = TakeProfitRule(percent=0.03)  # +3%
        self.position = Position(symbol="TEST", entry_price=200.0, quantity=1000)

    def test_no_exit_when_holding_steady(self):
        stock = make_stock(price=200.0)
        assert self.rule.should_exit(self.position, stock) is False

    def test_no_exit_when_in_loss(self):
        stock = make_stock(price=195.0)  # -2.5%
        assert self.rule.should_exit(self.position, stock) is False

    def test_no_exit_when_profit_below_threshold(self):
        stock = make_stock(price=204.0)  # +2%
        assert self.rule.should_exit(self.position, stock) is False

    def test_exit_when_profit_equals_threshold(self):
        stock = make_stock(price=206.0)  # exactly +3%
        assert self.rule.should_exit(self.position, stock) is True

    def test_exit_when_profit_exceeds_threshold(self):
        stock = make_stock(price=212.0)  # +6%
        assert self.rule.should_exit(self.position, stock) is True

    def test_custom_percent(self):
        rule = TakeProfitRule(percent=0.05)  # +5%
        stock = make_stock(price=208.0)      # +4% → no exit
        assert rule.should_exit(self.position, stock) is False
        stock2 = make_stock(price=211.0)     # +5.5% → exit
        assert rule.should_exit(self.position, stock2) is True
