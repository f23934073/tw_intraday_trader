"""Tests for MarketDataStore."""

from datetime import datetime

from market_data.models import StockData
from market_data.store import MarketDataStore

_TS = datetime(2026, 1, 1, 9, 5, 0)


def make_stock(symbol: str = "TEST", price: float = 100.0) -> StockData:
    return StockData(
        symbol=symbol,
        name=symbol,
        timestamp=_TS,
        price=price,
        open=100.0,
        high=105.0,
        low=95.0,
        previous_close=98.0,
        volume=100_000,
        previous_day_volume=80_000,
    )


class TestMarketDataStore:
    def setup_method(self):
        self.store = MarketDataStore()

    def test_update_and_get(self):
        stock = make_stock("2330", price=980.0)
        self.store.update(stock)
        result = self.store.get("2330")
        assert result is not None
        assert result.symbol == "2330"
        assert result.price == 980.0

    def test_get_nonexistent_returns_none(self):
        assert self.store.get("9999") is None

    def test_update_overwrites_old_snapshot(self):
        """Store 應保留最新快照，舊快照自動覆蓋。"""
        old = make_stock("2330", price=970.0)
        new = make_stock("2330", price=985.0)
        self.store.update(old)
        self.store.update(new)
        result = self.store.get("2330")
        assert result is not None
        assert result.price == 985.0  # 舊快照被覆蓋

    def test_get_all_returns_all_symbols(self):
        self.store.update(make_stock("2330"))
        self.store.update(make_stock("2317"))
        self.store.update(make_stock("3231"))
        all_stocks = self.store.get_all()
        symbols = {s.symbol for s in all_stocks}
        assert symbols == {"2330", "2317", "3231"}

    def test_get_all_empty_store_returns_empty_list(self):
        assert self.store.get_all() == []

    def test_len(self):
        assert len(self.store) == 0
        self.store.update(make_stock("2330"))
        assert len(self.store) == 1
        self.store.update(make_stock("2317"))
        assert len(self.store) == 2
        # 更新同一 symbol 不增加數量
        self.store.update(make_stock("2330", price=999.0))
        assert len(self.store) == 2

    def test_contains(self):
        self.store.update(make_stock("2330"))
        assert "2330" in self.store
        assert "9999" not in self.store

    def test_multiple_updates_same_symbol_keeps_latest(self):
        """模擬 Tick 連續更新，確認 Store 只保留最新。"""
        prices = [100.0, 101.5, 99.8, 103.2]
        for p in prices:
            self.store.update(make_stock("2330", price=p))
        result = self.store.get("2330")
        assert result is not None
        assert result.price == 103.2
