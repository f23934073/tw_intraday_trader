"""Frozen Decimal-only execution policy for Local Paper common-stock fills."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR
from enum import StrEnum

from market_data.models import (
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
)


FEE_POLICY_VERSION = "tw_stock_standard_v1"
ROUNDING_POLICY_VERSION = "twd_round_down_v1"
SLIPPAGE_POLICY_VERSION = "fixed_adverse_bps_v1"
PRICE_TICK_POLICY_VERSION = "tw_common_stock_tick_v1"
CALIBRATION_STATUS = "ASSUMPTION_NOT_LIVE_CALIBRATED"

COMMISSION_RATE = Decimal("0.001425")
MINIMUM_COMMISSION_TWD = Decimal("20")
SELL_TAX_RATE = Decimal("0.003")
MONEY_QUANTUM = Decimal("1")
_BPS_DENOMINATOR = Decimal("10000")


class ExecutionSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ReferenceSource(StrEnum):
    BEST_ASK = "BEST_ASK"
    BEST_BID = "BEST_BID"
    SNAPSHOT_COMPATIBILITY = "SNAPSHOT_COMPATIBILITY"


@dataclass(frozen=True)
class SlippageDecision:
    side: ExecutionSide
    reference_price: Decimal
    reference_source: ReferenceSource
    configured_slippage_bps: Decimal
    raw_adverse_price: Decimal
    adjusted_price: Decimal
    limit_price: Decimal
    limit_satisfied: bool
    realized_slippage_bps: Decimal
    slippage_policy_version: str = SLIPPAGE_POLICY_VERSION
    price_tick_policy_version: str = PRICE_TICK_POLICY_VERSION
    calibration_status: str = CALIBRATION_STATUS


@dataclass(frozen=True)
class FillAccountingDecision:
    side: ExecutionSide
    quantity_shares: int
    fill_price: Decimal
    reference_price: Decimal
    reference_source: ReferenceSource
    configured_slippage_bps: Decimal
    realized_slippage_bps: Decimal
    slippage_cost: Decimal
    gross_amount: Decimal
    commission: Decimal
    cumulative_order_commission: Decimal
    tax: Decimal
    cumulative_order_tax: Decimal
    net_cash_effect: Decimal
    fee_policy_version: str
    rounding_policy_version: str
    slippage_policy_version: str
    price_tick_policy_version: str
    instrument_descriptor_snapshot: dict[str, str]
    instrument_descriptor_digest: str


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _positive_decimal(value: object, field_name: str) -> Decimal:
    parsed = _decimal(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def common_stock_tick_size(price: object) -> Decimal:
    normalized = _positive_decimal(price, "price")
    if normalized < Decimal("10"):
        return Decimal("0.01")
    if normalized < Decimal("50"):
        return Decimal("0.05")
    if normalized < Decimal("100"):
        return Decimal("0.1")
    if normalized < Decimal("500"):
        return Decimal("0.5")
    if normalized < Decimal("1000"):
        return Decimal("1")
    return Decimal("5")


def is_valid_common_stock_tick(price: object) -> bool:
    try:
        normalized = _positive_decimal(price, "price")
    except ValueError:
        return False
    return normalized % common_stock_tick_size(normalized) == 0


def adverse_tick_ceiling(price: object) -> Decimal:
    normalized = _positive_decimal(price, "price")
    tick = common_stock_tick_size(normalized)
    candidate = (normalized / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    if not is_valid_common_stock_tick(candidate):
        return adverse_tick_ceiling(candidate + common_stock_tick_size(candidate))
    return candidate


def adverse_tick_floor(price: object) -> Decimal:
    normalized = _positive_decimal(price, "price")
    tick = common_stock_tick_size(normalized)
    candidate = (normalized / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    if candidate <= 0:
        raise ValueError("price floor must remain positive")
    if not is_valid_common_stock_tick(candidate):
        return adverse_tick_floor(candidate - common_stock_tick_size(candidate))
    return candidate


def decide_fixed_adverse_slippage(
    *,
    side: ExecutionSide | str,
    reference_price: object,
    reference_source: ReferenceSource | str,
    configured_slippage_bps: object,
    limit_price: object,
) -> SlippageDecision:
    normalized_side = ExecutionSide(side)
    normalized_source = ReferenceSource(reference_source)
    reference = _positive_decimal(reference_price, "reference_price")
    limit = _positive_decimal(limit_price, "limit_price")
    bps = _decimal(configured_slippage_bps, "configured_slippage_bps")
    if bps < 0 or bps > 100:
        raise ValueError("configured_slippage_bps must be between 0 and 100")
    if not is_valid_common_stock_tick(reference):
        raise ValueError("reference_price must be a valid common-stock tick")
    if not is_valid_common_stock_tick(limit):
        raise ValueError("limit_price must be a valid common-stock tick")

    rate = bps / _BPS_DENOMINATOR
    if normalized_side is ExecutionSide.BUY:
        raw_adverse = reference * (Decimal("1") + rate)
        adjusted = reference if bps == 0 else adverse_tick_ceiling(raw_adverse)
        limit_satisfied = adjusted <= limit
    else:
        raw_adverse = reference * (Decimal("1") - rate)
        if raw_adverse <= 0:
            raise ValueError("adverse SELL price must remain positive")
        adjusted = reference if bps == 0 else adverse_tick_floor(raw_adverse)
        limit_satisfied = adjusted >= limit
    realized_bps = abs(adjusted - reference) / reference * _BPS_DENOMINATOR
    return SlippageDecision(
        side=normalized_side,
        reference_price=reference,
        reference_source=normalized_source,
        configured_slippage_bps=bps,
        raw_adverse_price=raw_adverse,
        adjusted_price=adjusted,
        limit_price=limit,
        limit_satisfied=limit_satisfied,
        realized_slippage_bps=realized_bps,
    )


def _round_down_twd(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)


def cumulative_commission_for(cumulative_order_gross: object) -> Decimal:
    gross = _decimal(cumulative_order_gross, "cumulative_order_gross")
    if gross < 0:
        raise ValueError("cumulative_order_gross must not be negative")
    if gross == 0:
        return Decimal("0")
    return max(
        MINIMUM_COMMISSION_TWD,
        _round_down_twd(gross * COMMISSION_RATE),
    )


def decide_fill_accounting(
    *,
    slippage: SlippageDecision,
    quantity_shares: int,
    cumulative_order_gross_before: object = Decimal("0"),
    already_booked_commission: object = Decimal("0"),
    cumulative_order_tax_before: object = Decimal("0"),
    instrument_descriptor: LocalPaperInstrumentDescriptorV1,
) -> FillAccountingDecision:
    if not isinstance(slippage, SlippageDecision):
        raise ValueError("slippage must be a SlippageDecision")
    if (
        slippage.slippage_policy_version != SLIPPAGE_POLICY_VERSION
        or slippage.price_tick_policy_version != PRICE_TICK_POLICY_VERSION
        or slippage.calibration_status != CALIBRATION_STATUS
    ):
        raise ValueError("slippage policy identity is invalid")
    canonical_slippage = decide_fixed_adverse_slippage(
        side=slippage.side,
        reference_price=slippage.reference_price,
        reference_source=slippage.reference_source,
        configured_slippage_bps=slippage.configured_slippage_bps,
        limit_price=slippage.limit_price,
    )
    if canonical_slippage != slippage:
        raise ValueError("slippage decision integrity check failed")
    if isinstance(quantity_shares, bool) or not isinstance(quantity_shares, int):
        raise ValueError("quantity_shares must be a positive integer")
    if quantity_shares <= 0:
        raise ValueError("quantity_shares must be a positive integer")
    if not slippage.limit_satisfied:
        raise ValueError("slippage-adjusted price does not satisfy the limit")
    if (
        instrument_descriptor.normalized_product_class
        is not LocalPaperProductClass.COMMON_STOCK
    ):
        raise ValueError("UNSUPPORTED_COST_POLICY_SCOPE")
    if instrument_descriptor.exchange_raw not in {"TWSE", "TPEX", "TSE", "OTC"}:
        raise ValueError("UNSUPPORTED_COST_POLICY_SCOPE")

    previous_gross = _decimal(
        cumulative_order_gross_before,
        "cumulative_order_gross_before",
    )
    booked_commission = _decimal(
        already_booked_commission,
        "already_booked_commission",
    )
    previous_tax = _decimal(
        cumulative_order_tax_before,
        "cumulative_order_tax_before",
    )
    if previous_gross < 0 or booked_commission < 0 or previous_tax < 0:
        raise ValueError("cumulative accounting values must not be negative")

    gross = slippage.adjusted_price * quantity_shares
    cumulative_gross = previous_gross + gross
    cumulative_commission = cumulative_commission_for(cumulative_gross)
    commission = cumulative_commission - booked_commission
    if commission < 0:
        raise ValueError("already_booked_commission exceeds policy result")
    tax = (
        Decimal("0")
        if slippage.side is ExecutionSide.BUY
        else _round_down_twd(gross * SELL_TAX_RATE)
    )
    cumulative_tax = previous_tax + tax
    net_cash_effect = (
        -(gross + commission)
        if slippage.side is ExecutionSide.BUY
        else gross - commission - tax
    )
    if slippage.side is ExecutionSide.SELL and net_cash_effect < 0:
        raise ValueError("SELL net cash effect must not be negative")
    return FillAccountingDecision(
        side=slippage.side,
        quantity_shares=quantity_shares,
        fill_price=slippage.adjusted_price,
        reference_price=slippage.reference_price,
        reference_source=slippage.reference_source,
        configured_slippage_bps=slippage.configured_slippage_bps,
        realized_slippage_bps=slippage.realized_slippage_bps,
        slippage_cost=(
            abs(slippage.adjusted_price - slippage.reference_price)
            * quantity_shares
        ),
        gross_amount=gross,
        commission=commission,
        cumulative_order_commission=cumulative_commission,
        tax=tax,
        cumulative_order_tax=cumulative_tax,
        net_cash_effect=net_cash_effect,
        fee_policy_version=FEE_POLICY_VERSION,
        rounding_policy_version=ROUNDING_POLICY_VERSION,
        slippage_policy_version=slippage.slippage_policy_version,
        price_tick_policy_version=slippage.price_tick_policy_version,
        instrument_descriptor_snapshot=instrument_descriptor.to_dict(),
        instrument_descriptor_digest=instrument_descriptor.digest,
    )
