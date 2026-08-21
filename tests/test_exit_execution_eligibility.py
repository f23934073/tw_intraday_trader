from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import (
    build_exit_recommendation,
    build_trade_outcome,
)
from trading.risk import (
    CommandOrigin,
    CommandSide,
    ExecutionEligibilityStatus,
    ExitEligibilityContext,
    OrderCommand,
    RiskDecisionStatus,
    RiskGate,
    RISK_GATE_VERSION,
    RiskPolicy,
    RiskReason,
    RiskSnapshot,
)
from trading.trade_management import ExitRecommendationStatus


POLICY = RiskPolicy(
    version="risk-v1",
    allow_strategy_origin=False,
    max_order_notional=Decimal("200000"),
    max_position_notional=Decimal("300000"),
    max_daily_loss=Decimal("50000"),
)


def snapshot(**changes: object) -> RiskSnapshot:
    values: dict[str, object] = {
        "data_health_state": "HEALTHY",
        "market_open": True,
        "instrument_tradable": True,
        "available_cash": Decimal("0"),
        "current_position_shares": 1000,
        "pending_buy_shares": 0,
        "pending_sell_shares": 0,
        "daily_realized_pnl": Decimal("-999999"),
        "same_side_pending_order": False,
        "book_age_seconds": 0,
    }
    values.update(changes)
    return RiskSnapshot(**values)


def context(**changes: object) -> ExitEligibilityContext:
    recommendation = build_exit_recommendation()
    values: dict[str, object] = {
        "snapshot_id": "risk-snapshot:tick-2330-093502",
        "session_id": recommendation.session_id,
        "trade_id": recommendation.trade_id,
        "thesis_id": recommendation.thesis_id,
        "snapshot": snapshot(),
        "evaluated_at": recommendation.updated_at.value,
    }
    values.update(changes)
    return ExitEligibilityContext(**values)


def test_active_recommendation_is_eligible_for_available_position() -> None:
    recommendation = build_exit_recommendation()

    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(),
    )

    assert eligibility.status is ExecutionEligibilityStatus.ELIGIBLE
    assert eligibility.reasons == ()
    assert eligibility.eligible_quantity_shares == 1000
    assert eligibility.recommendation_id == recommendation.recommendation_id
    assert eligibility.gate_version == RISK_GATE_VERSION
    assert eligibility.policy_version == POLICY.version
    assert not hasattr(eligibility, "command")


@pytest.mark.parametrize(
    ("snapshot_changes", "reason"),
    [
        ({"data_health_state": "BLOCKED"}, RiskReason.DATA_HEALTH_UNHEALTHY),
        ({"market_open": False}, RiskReason.MARKET_CLOSED),
        ({"instrument_tradable": False}, RiskReason.INSTRUMENT_NOT_TRADABLE),
        ({"same_side_pending_order": True}, RiskReason.PENDING_ORDER_DUPLICATE),
    ],
)
def test_operational_risk_can_block_exit_eligibility(
    snapshot_changes: dict[str, object],
    reason: RiskReason,
) -> None:
    recommendation = build_exit_recommendation()

    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(snapshot=snapshot(**snapshot_changes)),
    )

    assert eligibility.status is ExecutionEligibilityStatus.BLOCKED
    assert reason in eligibility.reasons
    assert eligibility.eligible_quantity_shares == 0


def test_fresh_book_policy_blocks_missing_and_stale_snapshot() -> None:
    policy = replace(POLICY, require_fresh_book=True, max_book_age_seconds=5)
    recommendation = build_exit_recommendation()

    missing = RiskGate(policy).evaluate_exit_recommendation(
        recommendation,
        context(snapshot=snapshot(book_age_seconds=None)),
    )
    stale = RiskGate(policy).evaluate_exit_recommendation(
        recommendation,
        context(snapshot=snapshot(book_age_seconds=6)),
    )

    assert missing.reasons == (RiskReason.BOOK_UNAVAILABLE,)
    assert stale.reasons == (RiskReason.BOOK_STALE,)


def test_position_already_reserved_or_closed_is_ineligible() -> None:
    recommendation = build_exit_recommendation()

    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(
            snapshot=snapshot(
                current_position_shares=1000,
                pending_sell_shares=1000,
            )
        ),
    )

    assert eligibility.status is ExecutionEligibilityStatus.INELIGIBLE
    assert eligibility.reasons == (RiskReason.INSUFFICIENT_POSITION,)
    assert eligibility.eligible_quantity_shares == 0


def test_partial_pending_sell_only_exposes_unreserved_quantity() -> None:
    recommendation = build_exit_recommendation()

    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(
            snapshot=snapshot(
                current_position_shares=1000,
                pending_sell_shares=300,
            )
        ),
    )

    assert eligibility.status is ExecutionEligibilityStatus.ELIGIBLE
    assert eligibility.eligible_quantity_shares == 700


def test_entry_only_account_limits_do_not_affect_exit_eligibility() -> None:
    recommendation = build_exit_recommendation()

    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(
            snapshot=snapshot(
                available_cash=Decimal("0"),
                pending_buy_shares=999999,
                daily_realized_pnl=Decimal("-999999"),
            )
        ),
    )

    assert eligibility.status is ExecutionEligibilityStatus.ELIGIBLE
    assert eligibility.reasons == ()


def test_resolved_recommendation_and_identity_or_time_mismatch_fail_closed() -> None:
    recommendation = build_exit_recommendation()
    outcome = build_trade_outcome()
    resolved = replace(
        recommendation,
        status=ExitRecommendationStatus.RESOLVED_ON_CLOSE,
        resolved_at=outcome.closed_at,
        closing_fill_id=outcome.exit_legs[-1].fill_id,
    )
    gate = RiskGate(POLICY)

    with pytest.raises(ValueError, match="ACTIVE"):
        gate.evaluate_exit_recommendation(resolved, context())
    with pytest.raises(ValueError, match="trade_id does not match"):
        gate.evaluate_exit_recommendation(
            recommendation,
            context(trade_id="other-trade"),
        )
    with pytest.raises(ValueError, match="cannot predate"):
        gate.evaluate_exit_recommendation(
            recommendation,
            context(
                evaluated_at=recommendation.updated_at.value
                - timedelta(microseconds=1)
            ),
        )


def test_same_input_has_one_immutable_eligibility_identity() -> None:
    recommendation = build_exit_recommendation()
    eligibility_context = context()
    gate = RiskGate(POLICY)

    results = tuple(
        gate.evaluate_exit_recommendation(recommendation, eligibility_context)
        for _ in range(10)
    )

    assert len(set(results)) == 1
    assert len({result.eligibility_id for result in results}) == 1
    assert len({result.input_digest for result in results}) == 1
    with pytest.raises(FrozenInstanceError):
        results[0].eligible_quantity_shares = 0  # type: ignore[misc]


def test_decimal_scale_variants_share_one_canonical_eligibility_identity() -> None:
    recommendation = build_exit_recommendation()
    gate = RiskGate(POLICY)

    first = gate.evaluate_exit_recommendation(
        recommendation,
        context(
            snapshot=snapshot(
                available_cash=Decimal("0.0"),
                daily_realized_pnl=Decimal("-999999.00"),
            )
        ),
    )
    second = gate.evaluate_exit_recommendation(
        recommendation,
        context(
            snapshot=snapshot(
                available_cash=Decimal("0.00"),
                daily_realized_pnl=Decimal("-999999.0"),
            )
        ),
    )

    assert first.input_digest == second.input_digest
    assert first.eligibility_id == second.eligibility_id


def test_execution_eligibility_wire_status_values_are_frozen() -> None:
    assert tuple(item.value for item in ExecutionEligibilityStatus) == (
        "ELIGIBLE",
        "BLOCKED",
        "INELIGIBLE",
    )


def test_existing_command_gate_and_eligibility_remain_separate() -> None:
    recommendation = build_exit_recommendation()
    eligibility = RiskGate(POLICY).evaluate_exit_recommendation(
        recommendation,
        context(),
    )
    command = OrderCommand(
        command_id="manual-sell-1",
        session_id=recommendation.session_id,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="2330",
        side=CommandSide.SELL,
        quantity_shares=eligibility.eligible_quantity_shares,
        limit_price=Decimal("600"),
        idempotency_key="manual-sell-1",
        requested_at=eligibility.evaluated_at,
    )
    command_decision = RiskGate(POLICY).evaluate(
        command,
        context().snapshot,
        evaluated_at=eligibility.evaluated_at,
    )

    assert eligibility.status is ExecutionEligibilityStatus.ELIGIBLE
    assert command_decision.status is RiskDecisionStatus.APPROVED
    assert not hasattr(eligibility, "order_command")


def test_risk_module_has_no_journal_application_position_or_broker_dependency() -> None:
    module_path = Path(__file__).parents[1] / "trading" / "risk.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(
        {"dashboard", "market_data", "position", "runtime", "simulation"}
    )
    source = module_path.read_text(encoding="utf-8")
    assert "trading.journal" not in source
    assert "trading.application" not in source
    assert "submit(" not in source
