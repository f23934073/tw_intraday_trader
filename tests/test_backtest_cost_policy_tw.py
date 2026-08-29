"""Formal Taiwan commission, tax, and slippage contract tests."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backtest.cost_policy_tw import (
    build_cost_policy_snapshot,
    calculate_costs,
    cost_policy_readiness_reason,
    day_trade_sell_stt_rate,
    verify_cost_policy_snapshot,
)


FIXTURE = Path("tests/fixtures/backtest/tw_execution_v1/cost_policy_dates.json")


def test_cost_policy_fixture_is_sealed_and_date_effective() -> None:
    fixture = json.loads(FIXTURE.read_text())
    snapshot = verify_cost_policy_snapshot(fixture["cost_policy_snapshot"])
    fill = fixture["fill_input"]

    assert snapshot == build_cost_policy_snapshot(
        min_commission_twd="20",
        slippage_bps="5",
        slippage_calibration_digest="b" * 64,
    )
    for case in fixture["cases"]:
        trade_date = date.fromisoformat(case["sell_trade_date"])
        costs = calculate_costs(
            pre_cost_price=fill["pre_cost_price"],
            post_cost_price=fill["post_cost_price"],
            shares=fill["shares"],
            side=fill["side"],
            trade_date=trade_date,
            is_day_trade=fill["is_day_trade"],
            cost_policy_snapshot=snapshot,
        )
        assert str(day_trade_sell_stt_rate(trade_date)) == case["expected_sell_stt_rate"]
        assert costs.to_dict() == case["expected_cost_breakdown"]


def test_commission_minimum_and_whole_twd_rounding_are_decimal_only() -> None:
    snapshot = build_cost_policy_snapshot(slippage_bps="0", slippage_calibration_digest="c" * 64)
    buy = calculate_costs(
        pre_cost_price="10",
        post_cost_price="10",
        shares=1000,
        side="ENTRY",
        trade_date=date(2026, 8, 28),
        is_day_trade=False,
        cost_policy_snapshot=snapshot,
    )
    sell = calculate_costs(
        pre_cost_price="10",
        post_cost_price="10",
        shares=1000,
        side="EXIT",
        trade_date=date(2026, 8, 28),
        is_day_trade=False,
        cost_policy_snapshot=snapshot,
    )

    assert buy.commission == Decimal("20")
    assert buy.tax == Decimal("0")
    assert sell.commission == Decimal("20")
    assert sell.tax == Decimal("30")


def test_missing_or_drifted_slippage_calibration_never_falls_back() -> None:
    unknown = build_cost_policy_snapshot()
    assert cost_policy_readiness_reason(unknown) == "MISSING_SLIPPAGE_CALIBRATION"
    with pytest.raises(ValueError, match="MISSING_SLIPPAGE_CALIBRATION"):
        calculate_costs(
            pre_cost_price="100",
            post_cost_price="100",
            shares=1000,
            side="ENTRY",
            trade_date=date(2026, 8, 28),
            is_day_trade=False,
            cost_policy_snapshot=unknown,
        )

    drifted = dict(
        build_cost_policy_snapshot(slippage_bps="5", slippage_calibration_digest="d" * 64)
    )
    drifted["slippage_bps"] = "0"
    with pytest.raises(ValueError, match="snapshot_digest"):
        verify_cost_policy_snapshot(drifted)
