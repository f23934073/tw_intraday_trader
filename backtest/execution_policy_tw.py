"""Deterministic Taiwan execution policy for ``backtest-engine-v3-tw``.

This module owns policy facts and pure calculations only. The engine consumes
the immutable snapshot and never falls back when PIT or calibration evidence is
missing, unknown, or digest-drifted.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Mapping

from backtest.domain import (
    ENGINE_V3_TW,
    EXECUTION_POLICY_CONTRACT_VERSION,
    FORMAL_SPECIAL_REGIME_REASONS,
    FormalEvidenceError,
    HistoricalBar,
    MarketPhase,
    decimal,
    digest,
    is_sha256_hex,
    verify_contract_snapshot,
)

__all__ = [
    "BOARD_LOT_SHARES",
    "PRICE_LIMIT_RATIO",
    "TICK_BANDS",
    "SUPPORTED_SESSION_REGIMES",
    "SPECIAL_REGIME_REASON_BY_REGIME",
    "tick_size",
    "is_on_tick",
    "formal_bar_reason",
    "require_formal_bar",
    "special_regime_reason",
    "locked_limit_reason",
    "adverse_tick_price",
    "available_shares",
    "has_verified_auction_contract",
    "execution_policy_readiness_reason",
    "build_execution_policy_snapshot",
    "verify_execution_policy_snapshot",
]


BOARD_LOT_SHARES = 1_000
PRICE_LIMIT_RATIO = Decimal("0.10")
DEFAULT_MAX_PARTICIPATION_RATE = Decimal("0.05")

# (upper_bound_exclusive, tick). ``None`` is the open top band.
TICK_BANDS: tuple[tuple[Decimal | None, Decimal], ...] = (
    (Decimal("10"), Decimal("0.01")),
    (Decimal("50"), Decimal("0.05")),
    (Decimal("100"), Decimal("0.1")),
    (Decimal("500"), Decimal("0.5")),
    (Decimal("1000"), Decimal("1")),
    (None, Decimal("5")),
)

SUPPORTED_SESSION_REGIMES = frozenset({"REGULAR"})
SPECIAL_REGIME_REASON_BY_REGIME: Mapping[str, str] = {
    "IPO_NO_LIMIT_WINDOW": "UNSUPPORTED_IPO_NO_LIMIT_WINDOW",
    "DISPOSITION_PERIODIC_AUCTION": "UNSUPPORTED_DISPOSITION_PERIODIC_AUCTION",
}

_SNAPSHOT_KEYS = {
    "contract_version",
    "engine_identity",
    "board_lot_shares",
    "price_limit_ratio",
    "tick_bands",
    "supported_session_regimes",
    "special_regime_reasons",
    "fill_rule",
    "auction_close_rule",
    "max_participation_rate",
    "participation_calibration_digest",
    "bar_volume_unit",
    "partial_fill_rule",
    "locked_limit_rule",
    "residual_rule",
    "no_fallback_fill",
    "snapshot_digest",
}


def tick_size(price: Decimal | int | float | str) -> Decimal:
    """Return the minimum tick for a positive TWSE/TPEx common-stock price."""

    value = decimal(price)
    if not value.is_finite() or value <= 0:
        raise ValueError("price 必須大於 0")
    for upper, tick in TICK_BANDS:
        if upper is None or value < upper:
            return tick
    raise AssertionError("tick band table is not exhaustive")


def is_on_tick(price: Decimal | int | float | str) -> bool:
    value = decimal(price)
    return value % tick_size(value) == 0


def formal_bar_reason(bar: HistoricalBar) -> str | None:
    """Return why a bar is unavailable to formal execution, if any."""

    missing = [
        name
        for name in (
            "market_phase",
            "session_regime",
            "reference_price",
            "lower_limit_price",
            "upper_limit_price",
        )
        if getattr(bar, name) is None
    ]
    if missing:
        return "MISSING_FORMAL_BAR_FIELDS:" + ",".join(missing)
    try:
        MarketPhase(str(bar.market_phase))
    except ValueError:
        return "UNKNOWN_MARKET_PHASE"
    regime_reason = special_regime_reason(bar)
    if regime_reason is not None:
        return regime_reason
    assert bar.lower_limit_price is not None
    assert bar.upper_limit_price is not None
    if any(
        price < bar.lower_limit_price or price > bar.upper_limit_price
        for price in (bar.open, bar.high, bar.low, bar.close)
    ):
        return "PRICE_OUTSIDE_PIT_LIMITS"
    if any(
        not is_on_tick(price)
        for price in (
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.lower_limit_price,
            bar.upper_limit_price,
        )
    ):
        return "PRICE_OFF_TICK"
    return None


def require_formal_bar(bar: HistoricalBar) -> None:
    reason = formal_bar_reason(bar)
    if reason is not None:
        raise FormalEvidenceError(f"formal v3 bar unavailable: {reason}")


def special_regime_reason(bar: HistoricalBar) -> str | None:
    regime = bar.session_regime
    if regime is None:
        return "MISSING_SESSION_REGIME"
    if regime in SUPPORTED_SESSION_REGIMES:
        return None
    reason = SPECIAL_REGIME_REASON_BY_REGIME.get(regime, "UNKNOWN_SESSION_REGIME")
    assert reason in FORMAL_SPECIAL_REGIME_REASONS
    return reason


def locked_limit_reason(bar: HistoricalBar, *, side: str) -> str | None:
    """Return the side-specific locked-limit reason, never infer liquidity."""

    side = side.upper()
    if side not in {"ENTRY", "EXIT"}:
        raise ValueError("side must be ENTRY or EXIT")
    require_formal_bar(bar)
    assert bar.lower_limit_price is not None
    assert bar.upper_limit_price is not None
    if side == "ENTRY" and all(
        price == bar.upper_limit_price for price in (bar.open, bar.high, bar.low, bar.close)
    ):
        return "LOCKED_LIMIT_UP"
    if side == "EXIT" and all(
        price == bar.lower_limit_price for price in (bar.open, bar.high, bar.low, bar.close)
    ):
        return "LOCKED_LIMIT_DOWN"
    return None


def adverse_tick_price(
    price: Decimal | str,
    *,
    side: str,
    slippage_bps: Decimal | str,
    lower_limit_price: Decimal | str,
    upper_limit_price: Decimal | str,
) -> Decimal | None:
    """Apply adverse slippage and round outward to a valid tick/price limit."""

    raw = decimal(price)
    bps = decimal(slippage_bps)
    lower = decimal(lower_limit_price)
    upper = decimal(upper_limit_price)
    if bps < 0:
        raise ValueError("slippage_bps 不可小於 0")
    side = side.upper()
    if side == "ENTRY":
        candidate = raw * (Decimal("1") + bps / Decimal("10000"))
        rounding = ROUND_CEILING
    elif side == "EXIT":
        candidate = raw * (Decimal("1") - bps / Decimal("10000"))
        rounding = ROUND_FLOOR
    else:
        raise ValueError("side must be ENTRY or EXIT")
    for _ in range(2):
        tick = tick_size(candidate)
        candidate = (candidate / tick).to_integral_value(rounding=rounding) * tick
    if candidate < lower or candidate > upper:
        return None
    return candidate


def available_shares(bar: HistoricalBar, execution_policy_snapshot: Mapping[str, Any]) -> int:
    """Return the board-lot-floored quantity observable on this bar."""

    snapshot = verify_execution_policy_snapshot(execution_policy_snapshot)
    reason = execution_policy_readiness_reason(snapshot)
    if reason is not None:
        raise FormalEvidenceError(reason)
    units = Decimal(bar.volume)
    if snapshot["bar_volume_unit"] == "COMMON_LOTS":
        units *= BOARD_LOT_SHARES
    rate = Decimal(str(snapshot["max_participation_rate"]))
    raw = units * rate
    return int(raw // BOARD_LOT_SHARES) * BOARD_LOT_SHARES


def has_verified_auction_contract(research_truth_snapshot: Mapping[str, Any]) -> bool:
    """Require explicit auction-only price and volume semantics."""

    contract = research_truth_snapshot.get("closing_auction_event_contract")
    if not isinstance(contract, Mapping):
        return False
    return (
        contract.get("status") == "VERIFIED"
        and contract.get("price_semantics") == "AUCTION_ONLY"
        and contract.get("volume_semantics") == "AUCTION_ONLY"
    )


def execution_policy_readiness_reason(snapshot: Mapping[str, Any]) -> str | None:
    rate = snapshot.get("max_participation_rate")
    calibration = snapshot.get("participation_calibration_digest")
    if rate is None or calibration is None:
        return "MISSING_PARTICIPATION_CALIBRATION"
    try:
        parsed_rate = decimal(rate)
    except Exception:
        return "UNKNOWN_PARTICIPATION_POLICY"
    if not parsed_rate.is_finite() or not Decimal("0") < parsed_rate <= Decimal("1"):
        return "UNKNOWN_PARTICIPATION_POLICY"
    if not is_sha256_hex(str(calibration)):
        return "UNKNOWN_PARTICIPATION_CALIBRATION"
    return None


def build_execution_policy_snapshot(
    *,
    max_participation_rate: Decimal | int | float | str | None = (DEFAULT_MAX_PARTICIPATION_RATE),
    participation_calibration_digest: str | None = None,
    bar_volume_unit: str = "SHARES",
) -> dict[str, Any]:
    """Build the v1 execution snapshot; absent calibration remains UNKNOWN."""

    if bar_volume_unit not in {"SHARES", "COMMON_LOTS"}:
        raise ValueError("bar_volume_unit 必須是 SHARES 或 COMMON_LOTS")
    rate = None if max_participation_rate is None else str(decimal(max_participation_rate))
    body: dict[str, Any] = {
        "contract_version": EXECUTION_POLICY_CONTRACT_VERSION,
        "engine_identity": ENGINE_V3_TW,
        "board_lot_shares": BOARD_LOT_SHARES,
        "price_limit_ratio": str(PRICE_LIMIT_RATIO),
        "tick_bands": [
            {
                "upper_bound_exclusive": None if upper is None else str(upper),
                "tick": str(tick),
            }
            for upper, tick in TICK_BANDS
        ],
        "supported_session_regimes": sorted(SUPPORTED_SESSION_REGIMES),
        "special_regime_reasons": dict(sorted(SPECIAL_REGIME_REASON_BY_REGIME.items())),
        "fill_rule": "signal-bar-N-fills-N+1-or-later-after-quantity-observation",
        "auction_close_rule": "closing-auction-only-with-dataset-auction-event-proof",
        "max_participation_rate": rate,
        "participation_calibration_digest": participation_calibration_digest,
        "bar_volume_unit": bar_volume_unit,
        "partial_fill_rule": "FILL_OBSERVED_BOARD_LOTS_AND_RECORD_RESIDUAL",
        "locked_limit_rule": "UNFILLED_NO_FALLBACK",
        "residual_rule": "OVERNIGHT_BREACH_IF_UNRESOLVED_AT_SESSION_END",
        "no_fallback_fill": True,
    }
    return {**body, "snapshot_digest": digest(body)}


def verify_execution_policy_snapshot(
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    verified = verify_contract_snapshot(
        snapshot,
        label="execution_policy_snapshot",
        expected_contract_version=EXECUTION_POLICY_CONTRACT_VERSION,
    )
    if set(verified) != _SNAPSHOT_KEYS:
        raise ValueError("execution_policy_snapshot 欄位未知或缺漏")
    if verified.get("engine_identity") != ENGINE_V3_TW:
        raise ValueError("execution_policy_snapshot engine_identity 不符")
    expected = build_execution_policy_snapshot(
        max_participation_rate=verified["max_participation_rate"],
        participation_calibration_digest=verified["participation_calibration_digest"],
        bar_volume_unit=str(verified["bar_volume_unit"]),
    )
    if verified != expected:
        raise ValueError("execution_policy_snapshot policy 值未知")
    return verified
