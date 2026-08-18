"""Adapter from canonical market-data health reads to RiskGate input."""

from __future__ import annotations

from decimal import Decimal

from market_data.health import DataHealthSnapshot
from trading.risk import RiskSnapshot


def build_risk_snapshot(
    health: DataHealthSnapshot,
    *,
    market_open: bool,
    instrument_tradable: bool,
    available_cash: Decimal,
    current_position_shares: int,
    pending_buy_shares: int,
    pending_sell_shares: int,
    daily_realized_pnl: Decimal,
    same_side_pending_order: bool = False,
    book_age_seconds: int | None = None,
) -> RiskSnapshot:
    """Preserve canonical health state while callers supply portfolio evidence.

    This is a read-only translation seam.  It intentionally does not infer
    market status, book freshness, cash, positions, or pending orders from a
    provider or the legacy simulator.
    """

    return RiskSnapshot(
        data_health_state=health.state.value,
        market_open=market_open,
        instrument_tradable=instrument_tradable,
        available_cash=available_cash,
        current_position_shares=current_position_shares,
        pending_buy_shares=pending_buy_shares,
        pending_sell_shares=pending_sell_shares,
        daily_realized_pnl=daily_realized_pnl,
        same_side_pending_order=same_side_pending_order,
        book_age_seconds=book_age_seconds,
    )
