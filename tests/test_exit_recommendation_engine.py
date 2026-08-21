from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import (
    EXIT_POLICY_VERSION,
    build_trade_thesis,
    market_at,
    runtime_at,
)
from trading.exit_recommendation import (
    ExitPositionContext,
    ExitRecommendationEngine,
)
from trading.thesis_monitor import (
    MarketContextStatus,
    ThesisEvaluation,
    ThesisMarketContext,
    ThesisMonitor,
)
from trading.trade_management import (
    ExitAction,
    ExitReason,
    ExitRecommendationStatus,
    ThesisStatus,
    TimestampRole,
    TradeLifecycleState,
)


def evaluation(**changes: object) -> ThesisEvaluation:
    thesis = build_trade_thesis()
    context = ThesisMarketContext(
        thesis_id=thesis.thesis_id,
        trade_id=thesis.trade_id,
        session_id=thesis.draft.session_id,
        symbol=thesis.draft.symbol,
        source_event_id="tick-2330-093303",
        observed_at=market_at(9, 33, 3, "tick-2330-093303"),
        data_status=MarketContextStatus.READY,
        health_state="HEALTHY",
        highest_price_since_entry=Decimal("600.5"),
        post_entry_volume_shares=1100,
        volume_baseline_shares=Decimal("1000"),
        volume_sample_count=5,
        completed_bar_count=1,
        completed_bars_below_vwap=0,
        consecutive_completed_bars_below_vwap=0,
        consecutive_completed_bars_below_breakout=0,
    )
    return ThesisMonitor().evaluate(thesis, replace(context, **changes))


def position_context(
    thesis_evaluation: ThesisEvaluation,
    *,
    active_recommendation=None,
    **changes: object,
) -> ExitPositionContext:
    thesis = build_trade_thesis()
    event_time = thesis_evaluation.evaluated_at.value
    context = ExitPositionContext(
        session_id=thesis.draft.session_id,
        trade_id=thesis.trade_id,
        thesis_id=thesis.thesis_id,
        remaining_quantity_shares=1000,
        lifecycle_state=TradeLifecycleState.ACTIVE_POSITION,
        decided_at=runtime_at(
            event_time.hour,
            event_time.minute,
            event_time.second,
            f"decision-clock:{thesis_evaluation.source_event_id}",
            role=TimestampRole.EXIT_DECISION,
            microsecond=event_time.microsecond,
        ),
        active_recommendation=active_recommendation,
    )
    return replace(context, **changes)


@pytest.mark.parametrize(
    "thesis_evaluation",
    [
        pytest.param(evaluation(), id="valid"),
        pytest.param(
            evaluation(
                source_event_id="tick-2330-093403",
                observed_at=market_at(9, 34, 3, "tick-2330-093403"),
            ),
            id="warning",
        ),
        pytest.param(
            evaluation(data_status=MarketContextStatus.STALE),
            id="insufficient-data",
        ),
    ],
)
def test_non_invalid_thesis_produces_hold_without_recommendation(
    thesis_evaluation: ThesisEvaluation,
) -> None:
    result = ExitRecommendationEngine(EXIT_POLICY_VERSION).evaluate(
        thesis_evaluation,
        position_context(thesis_evaluation),
    )

    assert result.decision.action is ExitAction.HOLD
    assert result.decision.primary_reason is None
    assert result.decision.triggered_reasons == ()
    assert result.recommendation is None
    assert result.recommendation_changed is False


def test_hard_invalid_creates_thesis_invalid_recommendation() -> None:
    thesis_evaluation = evaluation(
        consecutive_completed_bars_below_breakout=1,
    )

    result = ExitRecommendationEngine(EXIT_POLICY_VERSION).evaluate(
        thesis_evaluation,
        position_context(thesis_evaluation),
    )

    assert result.decision.action is ExitAction.EXIT
    assert result.decision.primary_reason is ExitReason.THESIS_INVALID
    assert result.decision.triggered_reasons == (ExitReason.THESIS_INVALID,)
    assert result.recommendation is not None
    assert result.recommendation.status is ExitRecommendationStatus.ACTIVE
    assert result.recommendation.primary_reason is ExitReason.THESIS_INVALID
    assert result.recommendation.triggered_reasons == (ExitReason.THESIS_INVALID,)
    assert result.recommendation.first_trigger_decision_id == result.decision.decision_id
    assert result.recommendation_changed is True


def test_deadline_invalid_creates_time_decay_recommendation() -> None:
    thesis_evaluation = evaluation(
        source_event_id="tick-2330-093603",
        observed_at=market_at(9, 36, 3, "tick-2330-093603"),
    )

    result = ExitRecommendationEngine(EXIT_POLICY_VERSION).evaluate(
        thesis_evaluation,
        position_context(thesis_evaluation),
    )

    assert result.decision.primary_reason is ExitReason.TIME_DECAY
    assert result.decision.triggered_reasons == (ExitReason.TIME_DECAY,)
    assert result.recommendation is not None
    assert result.recommendation.primary_reason is ExitReason.TIME_DECAY


def test_exact_retry_reuses_decision_and_active_recommendation() -> None:
    thesis_evaluation = evaluation(
        consecutive_completed_bars_below_breakout=1,
    )
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)
    initial = engine.evaluate(
        thesis_evaluation,
        position_context(thesis_evaluation),
    )
    assert initial.recommendation is not None

    retried = engine.evaluate(
        thesis_evaluation,
        position_context(
            thesis_evaluation,
            active_recommendation=initial.recommendation,
        ),
    )

    assert retried.decision == initial.decision
    assert retried.recommendation == initial.recommendation
    assert retried.recommendation_changed is False


def test_new_invalid_evidence_updates_one_recommendation_monotonically() -> None:
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)
    hard_invalid = evaluation(consecutive_completed_bars_below_breakout=1)
    initial = engine.evaluate(hard_invalid, position_context(hard_invalid))
    assert initial.recommendation is not None
    deadline_invalid = evaluation(
        source_event_id="tick-2330-093603",
        observed_at=market_at(9, 36, 3, "tick-2330-093603"),
    )

    updated = engine.evaluate(
        deadline_invalid,
        position_context(
            deadline_invalid,
            active_recommendation=initial.recommendation,
        ),
    )

    assert updated.recommendation is not None
    assert updated.recommendation.recommendation_id == (
        initial.recommendation.recommendation_id
    )
    assert updated.recommendation.first_trigger_decision_id == (
        initial.recommendation.first_trigger_decision_id
    )
    assert updated.recommendation.first_trigger_event_id == (
        initial.recommendation.first_trigger_event_id
    )
    assert updated.recommendation.latest_decision_id == updated.decision.decision_id
    assert updated.recommendation.triggered_reasons == (
        ExitReason.THESIS_INVALID,
        ExitReason.TIME_DECAY,
    )
    assert updated.recommendation.primary_reason is ExitReason.THESIS_INVALID
    assert updated.recommendation_changed is True


def test_same_reason_on_new_event_does_not_mutate_active_recommendation() -> None:
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)
    first_invalid = evaluation(consecutive_completed_bars_below_breakout=1)
    initial = engine.evaluate(first_invalid, position_context(first_invalid))
    assert initial.recommendation is not None
    next_invalid = evaluation(
        source_event_id="tick-2330-093304",
        observed_at=market_at(9, 33, 4, "tick-2330-093304"),
        consecutive_completed_bars_below_breakout=1,
    )

    repeated = engine.evaluate(
        next_invalid,
        position_context(
            next_invalid,
            active_recommendation=initial.recommendation,
        ),
    )

    assert repeated.decision.decision_id != initial.decision.decision_id
    assert repeated.recommendation == initial.recommendation
    assert repeated.recommendation_changed is False


def test_invalid_latch_preserves_existing_actionable_reason() -> None:
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)
    deadline_invalid = evaluation(
        source_event_id="tick-2330-093603",
        observed_at=market_at(9, 36, 3, "tick-2330-093603"),
    )
    initial = engine.evaluate(deadline_invalid, position_context(deadline_invalid))
    assert initial.recommendation is not None
    latched = evaluation(
        source_event_id="tick-2330-093604",
        observed_at=market_at(9, 36, 4, "tick-2330-093604"),
        prior_status=ThesisStatus.INVALID,
    )

    updated = engine.evaluate(
        latched,
        position_context(
            latched,
            active_recommendation=initial.recommendation,
        ),
    )

    assert updated.decision.triggered_reasons == (ExitReason.TIME_DECAY,)
    assert updated.recommendation is not None
    assert updated.recommendation.triggered_reasons == (ExitReason.TIME_DECAY,)
    assert updated.recommendation == initial.recommendation
    assert updated.recommendation_changed is False


def test_identity_time_and_active_recommendation_mismatches_fail_closed() -> None:
    thesis_evaluation = evaluation(consecutive_completed_bars_below_breakout=1)
    context = position_context(thesis_evaluation)
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)

    with pytest.raises(ValueError, match="trade_id does not match"):
        engine.evaluate(thesis_evaluation, replace(context, trade_id="other-trade"))
    with pytest.raises(ValueError, match="cannot predate"):
        engine.evaluate(
            thesis_evaluation,
            replace(
                context,
                decided_at=runtime_at(
                    9,
                    32,
                    59,
                    "decision-clock:before-evaluation",
                    role=TimestampRole.EXIT_DECISION,
                ),
            ),
        )

    first = engine.evaluate(thesis_evaluation, context)
    assert first.recommendation is not None
    with pytest.raises(ValueError, match="policy version does not match"):
        ExitRecommendationEngine("other-policy-v1").evaluate(
            thesis_evaluation,
            position_context(
                thesis_evaluation,
                active_recommendation=first.recommendation,
            ),
        )


def test_position_context_requires_open_active_quantity() -> None:
    thesis_evaluation = evaluation()

    with pytest.raises(ValueError, match="remaining_quantity_shares must be positive"):
        position_context(thesis_evaluation, remaining_quantity_shares=0)
    with pytest.raises(ValueError, match="ACTIVE_POSITION"):
        position_context(
            thesis_evaluation,
            lifecycle_state=TradeLifecycleState.CLOSED,
        )


def test_result_is_immutable_deterministic_and_has_no_execution_capability() -> None:
    thesis_evaluation = evaluation(consecutive_completed_bars_below_breakout=1)
    context = position_context(thesis_evaluation)
    engine = ExitRecommendationEngine(EXIT_POLICY_VERSION)

    results = tuple(engine.evaluate(thesis_evaluation, context) for _ in range(10))

    assert len(set(results)) == 1
    assert len({result.decision.decision_id for result in results}) == 1
    with pytest.raises(FrozenInstanceError):
        context.remaining_quantity_shares = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        results[0].recommendation = None  # type: ignore[misc]
    assert not hasattr(results[0], "order")
    assert not hasattr(results[0], "sell")
    assert not hasattr(results[0].recommendation, "urgency")


def test_engine_has_no_persistence_risk_position_or_execution_dependencies() -> None:
    module_path = Path(__file__).parents[1] / "trading" / "exit_recommendation.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert imported_roots.isdisjoint(
        {"market_data", "position", "simulation", "runtime", "dashboard"}
    )
    assert referenced_names.isdisjoint(
        {
            "Journal",
            "RiskGate",
            "Position",
            "Order",
            "Broker",
            "SimulationService",
            "datetime",
        }
    )
