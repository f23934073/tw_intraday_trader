from dataclasses import replace
from decimal import Decimal

import pytest

from market_data.models import (
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
)
from simulation.execution_costs import (
    ExecutionSide,
    ReferenceSource,
    adverse_tick_ceiling,
    adverse_tick_floor,
    common_stock_tick_size,
    decide_fill_accounting,
    decide_fixed_adverse_slippage,
    is_valid_common_stock_tick,
)


def common_stock() -> LocalPaperInstrumentDescriptorV1:
    return LocalPaperInstrumentDescriptorV1(
        symbol="2330",
        exchange_raw="TSE",
        security_type_raw="STK",
        product_category_raw="24",
        normalized_product_class=LocalPaperProductClass.COMMON_STOCK,
        source_identity="fixture:shioaji-1.7.2:TSE:STK:24:2330",
    )


@pytest.mark.parametrize(
    ("price", "tick"),
    [
        ("9.99", "0.01"),
        ("10", "0.05"),
        ("49.95", "0.05"),
        ("50", "0.1"),
        ("99.9", "0.1"),
        ("100", "0.5"),
        ("499.5", "0.5"),
        ("500", "1"),
        ("999", "1"),
        ("1000", "5"),
    ],
)
def test_common_stock_tick_tiers(price: str, tick: str) -> None:
    assert common_stock_tick_size(Decimal(price)) == Decimal(tick)
    assert is_valid_common_stock_tick(Decimal(price)) is True


@pytest.mark.parametrize("price", ["10.01", "49.99", "50.05", "100.1", "999.5", "1001"])
def test_invalid_common_stock_ticks_are_rejected(price: str) -> None:
    assert is_valid_common_stock_tick(Decimal(price)) is False


@pytest.mark.parametrize(
    ("raw", "ceiling", "floor"),
    [
        ("9.999", "10", "9.99"),
        ("10.01", "10.05", "10"),
        ("49.99", "50", "49.95"),
        ("50.05", "50.1", "50"),
        ("99.95", "100", "99.9"),
        ("100.05", "100.5", "100"),
        ("499.75", "500", "499.5"),
        ("500.5", "501", "500"),
        ("999.5", "1000", "999"),
        ("1001", "1005", "1000"),
    ],
)
def test_adverse_tick_rounding_crosses_tiers_safely(
    raw: str,
    ceiling: str,
    floor: str,
) -> None:
    assert adverse_tick_ceiling(Decimal(raw)) == Decimal(ceiling)
    assert adverse_tick_floor(Decimal(raw)) == Decimal(floor)


@pytest.mark.parametrize("bps", ["0", "1", "5", "100"])
def test_buy_and_sell_adverse_slippage_is_deterministic(bps: str) -> None:
    buy = decide_fixed_adverse_slippage(
        side="BUY",
        reference_price=Decimal("100"),
        reference_source="BEST_ASK",
        configured_slippage_bps=Decimal(bps),
        limit_price=Decimal("105"),
    )
    sell = decide_fixed_adverse_slippage(
        side="SELL",
        reference_price=Decimal("100"),
        reference_source="BEST_BID",
        configured_slippage_bps=Decimal(bps),
        limit_price=Decimal("95"),
    )
    assert is_valid_common_stock_tick(buy.adjusted_price)
    assert is_valid_common_stock_tick(sell.adjusted_price)
    assert buy.adjusted_price >= buy.reference_price
    assert sell.adjusted_price <= sell.reference_price
    if bps == "0":
        assert buy.adjusted_price == sell.adjusted_price == Decimal("100")


def test_slippage_adjusted_limit_miss_stays_an_explicit_non_fill_decision() -> None:
    buy = decide_fixed_adverse_slippage(
        side="BUY",
        reference_price="100",
        reference_source="BEST_ASK",
        configured_slippage_bps="5",
        limit_price="100",
    )
    sell = decide_fixed_adverse_slippage(
        side="SELL",
        reference_price="110",
        reference_source="BEST_BID",
        configured_slippage_bps="5",
        limit_price="110",
    )
    assert buy.adjusted_price == Decimal("100.5")
    assert sell.adjusted_price == Decimal("109.5")
    assert buy.limit_satisfied is sell.limit_satisfied is False
    with pytest.raises(ValueError, match="does not satisfy"):
        decide_fill_accounting(
            slippage=buy,
            quantity_shares=100,
            instrument_descriptor=common_stock(),
        )


def test_golden_accounting_example_matches_frozen_policy() -> None:
    buy_slippage = decide_fixed_adverse_slippage(
        side=ExecutionSide.BUY,
        reference_price="100",
        reference_source=ReferenceSource.BEST_ASK,
        configured_slippage_bps="5",
        limit_price="100.5",
    )
    buy = decide_fill_accounting(
        slippage=buy_slippage,
        quantity_shares=100,
        instrument_descriptor=common_stock(),
    )
    assert buy.fill_price == Decimal("100.5")
    assert buy.gross_amount == Decimal("10050.0")
    assert buy.commission == Decimal("20")
    assert buy.tax == Decimal("0")
    assert buy.net_cash_effect == Decimal("-10070.0")

    sell_slippage = decide_fixed_adverse_slippage(
        side=ExecutionSide.SELL,
        reference_price="110",
        reference_source=ReferenceSource.BEST_BID,
        configured_slippage_bps="5",
        limit_price="109.5",
    )
    sell = decide_fill_accounting(
        slippage=sell_slippage,
        quantity_shares=100,
        instrument_descriptor=common_stock(),
    )
    assert sell.fill_price == Decimal("109.5")
    assert sell.gross_amount == Decimal("10950.0")
    assert sell.commission == Decimal("20")
    assert sell.tax == Decimal("32")
    assert sell.net_cash_effect == Decimal("10898.0")
    realized_pnl = (
        (sell.fill_price - buy.fill_price) * 100
        - buy.commission
        - sell.commission
        - sell.tax
    )
    assert realized_pnl == Decimal("828.0")


def test_partial_fill_commission_is_cumulative_delta_and_tax_is_per_fill() -> None:
    slippage = decide_fixed_adverse_slippage(
        side="SELL",
        reference_price="100",
        reference_source="BEST_BID",
        configured_slippage_bps="0",
        limit_price="100",
    )
    first = decide_fill_accounting(
        slippage=slippage,
        quantity_shares=100,
        instrument_descriptor=common_stock(),
    )
    second = decide_fill_accounting(
        slippage=slippage,
        quantity_shares=100,
        cumulative_order_gross_before=first.gross_amount,
        already_booked_commission=first.cumulative_order_commission,
        cumulative_order_tax_before=first.cumulative_order_tax,
        instrument_descriptor=common_stock(),
    )
    assert first.commission == Decimal("20")
    assert second.commission == Decimal("8")
    assert first.tax == second.tax == Decimal("30")
    assert second.cumulative_order_tax == Decimal("60")


def test_sell_accounting_rejects_negative_net_cash_effect() -> None:
    slippage = decide_fixed_adverse_slippage(
        side="SELL",
        reference_price="1",
        reference_source="BEST_BID",
        configured_slippage_bps="0",
        limit_price="1",
    )

    with pytest.raises(ValueError, match="net cash effect"):
        decide_fill_accounting(
            slippage=slippage,
            quantity_shares=1,
            instrument_descriptor=common_stock(),
        )


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1"])
def test_invalid_decimal_policy_inputs_fail_closed(bad: str) -> None:
    with pytest.raises(ValueError):
        decide_fixed_adverse_slippage(
            side="BUY",
            reference_price=bad,
            reference_source="BEST_ASK",
            configured_slippage_bps="5",
            limit_price="100",
        )


def test_accounting_rejects_a_forged_slippage_decision() -> None:
    slippage = decide_fixed_adverse_slippage(
        side="BUY",
        reference_price="100",
        reference_source="BEST_ASK",
        configured_slippage_bps="5",
        limit_price="100.5",
    )

    with pytest.raises(ValueError, match="integrity"):
        decide_fill_accounting(
            slippage=replace(slippage, adjusted_price=Decimal("100")),
            quantity_shares=100,
            instrument_descriptor=common_stock(),
        )


@pytest.mark.parametrize(
    "product_class",
    [LocalPaperProductClass.UNKNOWN, LocalPaperProductClass.UNSUPPORTED],
)
def test_unknown_or_unsupported_product_cannot_get_accounting_decision(
    product_class: LocalPaperProductClass,
) -> None:
    descriptor = LocalPaperInstrumentDescriptorV1(
        symbol="0050",
        exchange_raw="TSE",
        security_type_raw="ETF",
        product_category_raw="00",
        normalized_product_class=product_class,
        source_identity="fixture:TSE:ETF:0050",
    )
    slippage = decide_fixed_adverse_slippage(
        side="BUY",
        reference_price="100",
        reference_source="BEST_ASK",
        configured_slippage_bps="0",
        limit_price="100",
    )
    with pytest.raises(ValueError, match="UNSUPPORTED_COST_POLICY_SCOPE"):
        decide_fill_accounting(
            slippage=slippage,
            quantity_shares=100,
            instrument_descriptor=descriptor,
        )
