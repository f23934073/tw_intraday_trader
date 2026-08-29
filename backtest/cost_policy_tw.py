"""Decimal-only Taiwan cost policy for formal v3 historical fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Mapping

from backtest.domain import (
    COST_POLICY_CONTRACT_VERSION,
    decimal,
    digest,
    is_sha256_hex,
    verify_contract_snapshot,
)

__all__ = [
    "MAX_COMMISSION_RATE",
    "STANDARD_SELL_STT_RATE",
    "DAY_TRADE_SELL_STT_RATE",
    "DAY_TRADE_STT_REDUCTION_LAST_DATE",
    "CostBreakdown",
    "day_trade_sell_stt_rate",
    "cost_policy_readiness_reason",
    "calculate_costs",
    "build_cost_policy_snapshot",
    "verify_cost_policy_snapshot",
]


MAX_COMMISSION_RATE = Decimal("0.001425")
STANDARD_SELL_STT_RATE = Decimal("0.003")
DAY_TRADE_SELL_STT_RATE = Decimal("0.0015")
DAY_TRADE_STT_REDUCTION_LAST_DATE = date(2027, 12, 31)

_SNAPSHOT_KEYS = {
    "contract_version",
    "commission_rate",
    "commission_rate_ceiling",
    "min_commission_twd",
    "commission_sides",
    "commission_rounding",
    "securities_transaction_tax",
    "slippage_bps",
    "slippage_calibration_digest",
    "slippage_rule",
    "no_fixed_bps_fallback",
    "snapshot_digest",
}


def day_trade_sell_stt_rate(trade_date: date) -> Decimal:
    if not isinstance(trade_date, date):
        raise TypeError("trade_date 必須是 datetime.date")
    if trade_date <= DAY_TRADE_STT_REDUCTION_LAST_DATE:
        return DAY_TRADE_SELL_STT_RATE
    return STANDARD_SELL_STT_RATE


def cost_policy_readiness_reason(snapshot: Mapping[str, Any]) -> str | None:
    slippage_bps = snapshot.get("slippage_bps")
    calibration = snapshot.get("slippage_calibration_digest")
    if slippage_bps is None or calibration is None:
        return "MISSING_SLIPPAGE_CALIBRATION"
    try:
        parsed = decimal(slippage_bps)
    except Exception:
        return "UNKNOWN_SLIPPAGE_POLICY"
    if not parsed.is_finite() or parsed < 0:
        return "UNKNOWN_SLIPPAGE_POLICY"
    if not is_sha256_hex(str(calibration)):
        return "UNKNOWN_SLIPPAGE_CALIBRATION"
    return None


@dataclass(frozen=True)
class CostBreakdown:
    commission: Decimal
    tax: Decimal
    slippage: Decimal
    tax_rate: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.tax + self.slippage

    def to_dict(self) -> dict[str, str]:
        return {
            "commission": str(self.commission),
            "tax": str(self.tax),
            "slippage": str(self.slippage),
            "tax_rate": str(self.tax_rate),
            "total": str(self.total),
        }


def calculate_costs(
    *,
    pre_cost_price: Decimal | str,
    post_cost_price: Decimal | str,
    shares: int,
    side: str,
    trade_date: date,
    is_day_trade: bool,
    cost_policy_snapshot: Mapping[str, Any],
) -> CostBreakdown:
    """Calculate integer-TWD commission/tax and explicit adverse slippage."""

    snapshot = verify_cost_policy_snapshot(cost_policy_snapshot)
    reason = cost_policy_readiness_reason(snapshot)
    if reason is not None:
        raise ValueError(reason)
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("shares 必須是正整數")
    side = side.upper()
    if side not in {"ENTRY", "EXIT"}:
        raise ValueError("side must be ENTRY or EXIT")
    pre = decimal(pre_cost_price)
    post = decimal(post_cost_price)
    if pre <= 0 or post <= 0:
        raise ValueError("fill price 必須大於 0")
    gross = post * shares
    commission = (gross * Decimal(str(snapshot["commission_rate"]))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    commission = max(commission, Decimal(str(snapshot["min_commission_twd"])))
    tax_rate = (
        day_trade_sell_stt_rate(trade_date)
        if side == "EXIT" and is_day_trade
        else STANDARD_SELL_STT_RATE
        if side == "EXIT"
        else Decimal("0")
    )
    tax = (gross * tax_rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
    slippage = (abs(post - pre) * shares).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return CostBreakdown(
        commission=commission,
        tax=tax,
        slippage=slippage,
        tax_rate=tax_rate,
    )


def build_cost_policy_snapshot(
    *,
    commission_rate: Decimal | int | float | str = MAX_COMMISSION_RATE,
    min_commission_twd: Decimal | int | float | str = Decimal("20"),
    slippage_bps: Decimal | int | float | str | None = None,
    slippage_calibration_digest: str | None = None,
) -> dict[str, Any]:
    """Build a sealed cost policy; absent calibration remains fail-closed."""

    rate = decimal(commission_rate)
    if rate < 0 or rate > MAX_COMMISSION_RATE:
        raise ValueError(f"commission_rate 必須介於 0 與法定上限 {MAX_COMMISSION_RATE} 之間")
    floor = decimal(min_commission_twd)
    if floor < 0:
        raise ValueError("min_commission_twd 不可小於 0")
    parsed_slippage = None if slippage_bps is None else str(decimal(slippage_bps))
    body: dict[str, Any] = {
        "contract_version": COST_POLICY_CONTRACT_VERSION,
        "commission_rate": str(rate),
        "commission_rate_ceiling": str(MAX_COMMISSION_RATE),
        "min_commission_twd": str(floor),
        "commission_sides": ["BUY", "SELL"],
        "commission_rounding": "ROUND_HALF_UP_WHOLE_TWD",
        "securities_transaction_tax": {
            "taxed_side": "SELL",
            "standard_rate": str(STANDARD_SELL_STT_RATE),
            "day_trade_reduced_rate": str(DAY_TRADE_SELL_STT_RATE),
            "day_trade_reduction_last_date": (DAY_TRADE_STT_REDUCTION_LAST_DATE.isoformat()),
            "rounding": "ROUND_DOWN_WHOLE_TWD",
        },
        "slippage_bps": parsed_slippage,
        "slippage_calibration_digest": slippage_calibration_digest,
        "slippage_rule": "ADVERSE_PRICE_THEN_OUTWARD_TICK",
        "no_fixed_bps_fallback": True,
    }
    return {**body, "snapshot_digest": digest(body)}


def verify_cost_policy_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    verified = verify_contract_snapshot(
        snapshot,
        label="cost_policy_snapshot",
        expected_contract_version=COST_POLICY_CONTRACT_VERSION,
    )
    if set(verified) != _SNAPSHOT_KEYS:
        raise ValueError("cost_policy_snapshot 欄位未知或缺漏")
    expected = build_cost_policy_snapshot(
        commission_rate=verified["commission_rate"],
        min_commission_twd=verified["min_commission_twd"],
        slippage_bps=verified["slippage_bps"],
        slippage_calibration_digest=verified["slippage_calibration_digest"],
    )
    if verified != expected:
        raise ValueError("cost_policy_snapshot policy 值未知")
    return verified
