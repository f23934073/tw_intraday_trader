"""Tests for PositionManager."""

import pytest

from position.manager import PositionManager
from position.models import Position


class TestPositionManager:
    def setup_method(self):
        self.manager = PositionManager()

    def test_add_and_get_position(self):
        pos = Position(symbol="2317", entry_price=205.0, quantity=1000)
        self.manager.add(pos)
        result = self.manager.get("2317")
        assert result is not None
        assert result.symbol == "2317"
        assert result.entry_price == 205.0
        assert result.quantity == 1000

    def test_get_nonexistent_returns_none(self):
        assert self.manager.get("9999") is None

    def test_remove_position(self):
        pos = Position(symbol="2317", entry_price=205.0, quantity=1000)
        self.manager.add(pos)
        self.manager.remove("2317")
        assert self.manager.get("2317") is None

    def test_remove_nonexistent_does_not_crash(self):
        # Should silently ignore
        self.manager.remove("9999")

    def test_add_overwrites_existing(self):
        pos1 = Position(symbol="2317", entry_price=200.0, quantity=1000)
        pos2 = Position(symbol="2317", entry_price=210.0, quantity=500)
        self.manager.add(pos1)
        self.manager.add(pos2)
        result = self.manager.get("2317")
        assert result is not None
        assert result.entry_price == 210.0
        assert result.quantity == 500

    def test_get_all_returns_all_positions(self):
        self.manager.add(Position("2317", 205.0, 1000))
        self.manager.add(Position("2330", 980.0, 100))
        all_pos = self.manager.get_all()
        symbols = {p.symbol for p in all_pos}
        assert symbols == {"2317", "2330"}
        assert len(all_pos) == 2

    def test_get_all_empty_manager_returns_empty_list(self):
        assert self.manager.get_all() == []

    def test_len_reflects_position_count(self):
        assert len(self.manager) == 0
        self.manager.add(Position("2317", 205.0, 1000))
        assert len(self.manager) == 1
        self.manager.add(Position("2330", 980.0, 100))
        assert len(self.manager) == 2
        self.manager.remove("2317")
        assert len(self.manager) == 1
