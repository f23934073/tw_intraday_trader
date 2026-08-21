from datetime import datetime
from decimal import Decimal

import pytest

from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskDecisionStatus,
    RiskGate,
    RiskPolicy,
    RiskReason,
    RiskSnapshot,
)


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
POLICY = RiskPolicy(
    version="risk-v1",
    allow_strategy_origin=False,
    max_order_notional=Decimal("200000"),
    max_position_notional=Decimal("300000"),
    max_daily_loss=Decimal("50000"),
)


def command(
    *,
    origin: CommandOrigin = CommandOrigin.MANUAL_WEB,
    side: CommandSide = CommandSide.BUY,
    quantity: int = 1000,
    price: str = "100",
) -> OrderCommand:
    return OrderCommand(
        command_id="command-1",
        session_id="session-1",
        origin=origin,
        symbol="2330",
        side=side,
        quantity_shares=quantity,
        limit_price=Decimal(price),
        idempotency_key="browser-1",
        requested_at=AT,
        strategy_id=("strategy-1" if origin is CommandOrigin.STRATEGY_AUTOMATED else None),
        strategy_version=(
            "strategy-1-v1" if origin is CommandOrigin.STRATEGY_AUTOMATED else None
        ),
    )


def snapshot(**changes: object) -> RiskSnapshot:
    values: dict[str, object] = {
        "data_health_state": "HEALTHY",
        "market_open": True,
        "instrument_tradable": True,
        "available_cash": Decimal("250000"),
        "current_position_shares": 0,
        "pending_buy_shares": 0,
        "pending_sell_shares": 0,
        "daily_realized_pnl": Decimal("0"),
    }
    values.update(changes)
    return RiskSnapshot(**values)


def test_healthy_manual_buy_is_approved_with_policy_version() -> None:
    decision = RiskGate(POLICY).evaluate(command(), snapshot(), evaluated_at=AT)

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.approved_quantity_shares == 1000
    assert decision.policy_version == "risk-v1"
    assert decision.reasons == ()


def test_unhealthy_data_and_strategy_origin_are_blocked() -> None:
    decision = RiskGate(POLICY).evaluate(
        command(origin=CommandOrigin.STRATEGY_AUTOMATED),
        snapshot(data_health_state="BLOCKED"),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.BLOCKED
    assert decision.reasons == (
        RiskReason.DATA_HEALTH_UNHEALTHY,
        RiskReason.STRATEGY_ORIGIN_DISABLED,
    )


def test_entry_only_guards_do_not_block_risk_reducing_sell() -> None:
    decision = RiskGate(POLICY).evaluate(
        command(
            origin=CommandOrigin.STRATEGY_AUTOMATED,
            side=CommandSide.SELL,
            quantity=3000,
            price="100",
        ),
        snapshot(
            current_position_shares=3000,
            daily_realized_pnl=Decimal("-50000"),
        ),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.approved_quantity_shares == 3000
    assert decision.reasons == ()


def test_entry_only_guards_still_block_or_reject_buy() -> None:
    decision = RiskGate(POLICY).evaluate(
        command(
            origin=CommandOrigin.STRATEGY_AUTOMATED,
            side=CommandSide.BUY,
            quantity=3000,
            price="100",
        ),
        snapshot(
            available_cash=Decimal("500000"),
            daily_realized_pnl=Decimal("-50000"),
        ),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.BLOCKED
    assert decision.reasons == (
        RiskReason.DAILY_LOSS_LIMIT,
        RiskReason.STRATEGY_ORIGIN_DISABLED,
    )

def test_cash_position_and_pending_constraints_reject_manual_buy() -> None:
    decision = RiskGate(POLICY).evaluate(
        command(quantity=3000, price="100"),
        snapshot(available_cash=Decimal("100000"), same_side_pending_order=True),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.BLOCKED
    assert RiskReason.PENDING_ORDER_DUPLICATE in decision.reasons


def test_sell_cannot_exceed_position_after_pending_sells() -> None:
    decision = RiskGate(POLICY).evaluate(
        command(side=CommandSide.SELL, quantity=1000),
        snapshot(current_position_shares=1000, pending_sell_shares=500),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.reasons == (RiskReason.INSUFFICIENT_POSITION,)


def test_fresh_book_policy_blocks_missing_or_stale_book() -> None:
    policy = RiskPolicy(
        version="risk-book-v1",
        allow_strategy_origin=False,
        max_order_notional=Decimal("200000"),
        max_position_notional=Decimal("300000"),
        max_daily_loss=Decimal("50000"),
        require_fresh_book=True,
        max_book_age_seconds=5,
    )

    missing = RiskGate(policy).evaluate(command(), snapshot(), evaluated_at=AT)
    stale = RiskGate(policy).evaluate(
        command(), snapshot(book_age_seconds=6), evaluated_at=AT
    )

    assert missing.reasons == (RiskReason.BOOK_UNAVAILABLE,)
    assert stale.reasons == (RiskReason.BOOK_STALE,)


def test_command_requires_normalized_symbol_and_aware_time() -> None:
    with pytest.raises(ValueError, match="symbol must be normalized"):
        command().__class__(
            **{**command().__dict__, "symbol": " 2330"}
        )
