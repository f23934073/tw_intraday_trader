"""Tests for the session-local paper-simulation command service."""

import pytest

from market_data.provider import MockProvider
from simulation.service import (
    SimulationService,
    SimulationStateError,
)


def test_marketable_buy_creates_filled_order_and_position():
    service = SimulationService(MockProvider(), starting_cash=300_000)

    order, idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="manual-buy-3231",
    )

    assert idempotent is False
    assert order["status"] == "FILLED"
    assert order["filled_price"] == 105.5
    assert order["filled_quantity"] == 1_000
    assert service.session()["available_cash"] == 194_500.0
    position = service.positions()[0]
    assert position["symbol"] == "3231"
    assert position["name"] == "緯創"
    assert position["quantity"] == 1_000
    assert position["average_price"] == 105.5
    assert position["current_price"] == 105.5
    assert position["market_value"] == 105_500.0
    assert position["unrealized_pnl"] == 0.0
    assert position["unrealized_pnl_pct"] == 0.0
    assert position["realized_pnl"] == 0.0
    assert position["last_quote_at"] is not None


def test_same_idempotency_key_returns_original_order_without_second_fill():
    service = SimulationService(MockProvider(), starting_cash=300_000)

    first, first_idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="same-command",
    )
    duplicate, duplicate_idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="same-command",
    )

    assert first_idempotent is False
    assert duplicate_idempotent is True
    assert duplicate["order_id"] == first["order_id"]
    assert service.positions()[0]["quantity"] == 1_000
    assert service.session()["available_cash"] == 194_500.0


def test_non_marketable_order_stays_out_of_holdings_and_can_be_cancelled():
    service = SimulationService(MockProvider())
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=100.0,
        idempotency_key="pending-buy",
    )

    assert order["status"] == "SUBMITTED"
    assert service.positions() == []

    cancelled, idempotent = service.cancel_order(
        order["order_id"],
        "cancel-pending-buy",
    )
    repeated, repeated_idempotent = service.cancel_order(
        order["order_id"],
        "cancel-pending-buy",
    )

    assert idempotent is False
    assert cancelled["status"] == "CANCELLED"
    assert repeated_idempotent is True
    assert repeated["status"] == "CANCELLED"


def test_sell_cannot_exceed_holdings_and_realizes_pnl_after_fill():
    service = SimulationService(MockProvider(), starting_cash=300_000)
    service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="buy-before-sell",
    )

    rejected, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=2,
        limit_price=100.0,
        idempotency_key="oversell",
    )
    sold, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=100.0,
        idempotency_key="sell-all",
    )

    assert rejected["status"] == "REJECTED"
    assert rejected["reason"] == "可賣出持股不足"
    assert sold["status"] == "FILLED"
    assert service.positions() == []
    assert service.session()["available_cash"] == 300_000.0


def test_only_submitted_order_can_be_cancelled():
    service = SimulationService(MockProvider())
    filled, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="filled-buy",
    )

    with pytest.raises(SimulationStateError, match="只有已送出的委託可以取消"):
        service.cancel_order(filled["order_id"], "cancel-filled")
