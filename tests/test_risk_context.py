from datetime import date, datetime
from decimal import Decimal

import pytest

from market_data.health import DataHealth, DataHealthReason, DataHealthState
from runtime.risk_context import build_risk_snapshot
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskDecisionStatus,
    RiskGate,
    RiskPolicy,
    RiskReason,
)


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")


def health_snapshot(state: DataHealthState):
    health = DataHealth(date(2026, 8, 18), started_at=AT)
    if state is DataHealthState.HEALTHY:
        health.mark_ready(occurred_at=AT, evidence="fixture_ready")
    elif state is DataHealthState.DEGRADED:
        health.record_invalid(
            DataHealthReason.SOURCE_CLOCK_SKEW,
            occurred_at=AT,
            blocked=False,
        )
    elif state is DataHealthState.BLOCKED:
        health.record_invalid(
            DataHealthReason.QUEUE_OVERFLOW,
            occurred_at=AT,
        )
    return health.snapshot()


def context(state: DataHealthState):
    return build_risk_snapshot(
        health_snapshot(state),
        market_open=True,
        instrument_tradable=True,
        available_cash=Decimal("300000"),
        current_position_shares=1000,
        pending_buy_shares=0,
        pending_sell_shares=0,
        daily_realized_pnl=Decimal("0"),
        same_side_pending_order=False,
        book_age_seconds=3,
    )


def command() -> OrderCommand:
    return OrderCommand(
        command_id="risk-context-command-1",
        session_id="risk-context-20260818",
        origin=CommandOrigin.MANUAL_WEB,
        symbol="2330",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("100"),
        idempotency_key="risk-context-browser-1",
        requested_at=AT,
    )


def gate() -> RiskGate:
    return RiskGate(
        RiskPolicy(
            version="risk-v1",
            allow_strategy_origin=False,
            max_order_notional=Decimal("200000"),
            max_position_notional=Decimal("300000"),
            max_daily_loss=Decimal("50000"),
        )
    )


def test_risk_context_preserves_canonical_health_and_caller_evidence() -> None:
    snapshot = context(DataHealthState.HEALTHY)

    assert snapshot.data_health_state == "HEALTHY"
    assert snapshot.available_cash == Decimal("300000")
    assert snapshot.current_position_shares == 1000
    assert snapshot.book_age_seconds == 3


@pytest.mark.parametrize(
    "state",
    [
        DataHealthState.STARTING,
        DataHealthState.DEGRADED,
        DataHealthState.BLOCKED,
    ],
)
def test_non_healthy_canonical_health_blocks_new_command(
    state: DataHealthState,
) -> None:
    decision = gate().evaluate(command(), context(state), evaluated_at=AT)

    assert decision.status is RiskDecisionStatus.BLOCKED
    assert RiskReason.DATA_HEALTH_UNHEALTHY in decision.reasons


def test_healthy_canonical_health_keeps_approved_command_eligible() -> None:
    decision = gate().evaluate(
        command(),
        context(DataHealthState.HEALTHY),
        evaluated_at=AT,
    )

    assert decision.status is RiskDecisionStatus.APPROVED
