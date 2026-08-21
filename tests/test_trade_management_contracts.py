import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import (
    EXIT_POLICY_VERSION,
    SESSION_ID,
    build_exit_recommendation,
    build_replay_verification,
    build_trade_outcome,
    build_trade_thesis,
    runtime_at,
    sha256,
)
from trading.trade_management import (
    DECISION_LIFECYCLE_TRANSITIONS,
    EXIT_CATEGORY_PRIORITY,
    CompletionPolicy,
    ComparisonOperator,
    ORDER_LIFECYCLE_TRANSITIONS,
    TRADE_LIFECYCLE_TRANSITIONS,
    DecisionLifecycleState,
    EntryEvidenceStatus,
    EvidenceValue,
    EvidenceValueKind,
    ExitAction,
    ExitCategory,
    ExitDecision,
    ExitReason,
    ExitRecommendationStatus,
    ExpectedConditionKind,
    InvalidConditionKind,
    OrderLifecycleState,
    PnlBasis,
    PriceReference,
    ReplayDivergence,
    ReplayOutput,
    ReplayVerification,
    ThesisStatus,
    ThesisType,
    TimestampPrecision,
    TimestampRole,
    TimestampSource,
    TradeSide,
    TradeLifecycleState,
    TradeTimestamp,
    VolumeBaselineKind,
    VolumeUnit,
    build_exit_decision_id,
    build_exit_recommendation_id,
    build_trade_id,
)


def test_timestamp_contract_freezes_timezone_precision_source_and_role():
    timestamp = runtime_at(
        9,
        31,
        3,
        "simulation-clock:fill-001",
        role=TimestampRole.FILL,
    )

    assert timestamp.isoformat == "2026-08-20T09:31:03.000000+08:00"
    assert timestamp.precision.value == "MICROSECOND"
    assert timestamp.source is TimestampSource.SIMULATION_CLOCK
    assert timestamp.source_identity == "simulation-clock:fill-001"


def test_timestamp_contract_rejects_naive_non_taipei_and_wrong_source():
    with pytest.raises(ValueError, match="timezone-aware"):
        TradeTimestamp(
            role=TimestampRole.SIGNAL,
            value=datetime(2026, 8, 20, 9, 30),
            source=TimestampSource.STRATEGY_RUNTIME,
            source_identity="strategy-clock",
        )

    with pytest.raises(ValueError, match="Asia/Taipei"):
        TradeTimestamp(
            role=TimestampRole.SIGNAL,
            value=datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc),
            source=TimestampSource.STRATEGY_RUNTIME,
            source_identity="strategy-clock",
        )

    with pytest.raises(ValueError, match="invalid for FILL"):
        runtime_at(
            9,
            31,
            3,
            "strategy-clock:fill-001",
            role=TimestampRole.FILL,
        ).__class__(
            role=TimestampRole.FILL,
            value=runtime_at(
                9,
                31,
                3,
                "strategy-clock:fill-001",
                role=TimestampRole.FILL,
            ).value,
            source=TimestampSource.STRATEGY_RUNTIME,
            source_identity="strategy-clock:fill-001",
        )


def test_trade_thesis_starts_only_at_first_fill_and_is_immutable():
    thesis = build_trade_thesis()

    assert thesis.thesis_start_at is thesis.filled_at
    assert thesis.filled_at.value > thesis.draft.signal_at.value
    assert thesis.draft.strategy_version != thesis.draft.thesis_version
    assert thesis.trade_id == build_trade_id(SESSION_ID, thesis.opening_fill_id)

    with pytest.raises(FrozenInstanceError):
        thesis.trade_id = "different"  # type: ignore[misc]


def test_lifecycle_state_machines_and_transitions_remain_separate():
    assert tuple(DecisionLifecycleState) == (
        DecisionLifecycleState.SIGNAL_CREATED,
        DecisionLifecycleState.THESIS_DRAFTED,
        DecisionLifecycleState.THESIS_ACTIVE,
        DecisionLifecycleState.EXIT_RECOMMENDATION_ACTIVE,
        DecisionLifecycleState.COMPLETED,
        DecisionLifecycleState.TERMINATED,
    )
    assert tuple(OrderLifecycleState) == (
        OrderLifecycleState.CREATED,
        OrderLifecycleState.SUBMITTED,
        OrderLifecycleState.PENDING,
        OrderLifecycleState.PARTIALLY_FILLED,
        OrderLifecycleState.FILLED,
        OrderLifecycleState.CANCELLED,
        OrderLifecycleState.REJECTED,
        OrderLifecycleState.EXPIRED,
        OrderLifecycleState.RECOVERY_REQUIRED,
    )
    assert tuple(TradeLifecycleState) == (
        TradeLifecycleState.PENDING_ENTRY,
        TradeLifecycleState.ACTIVE_POSITION,
        TradeLifecycleState.EXIT_IN_PROGRESS,
        TradeLifecycleState.CLOSED,
        TradeLifecycleState.ENTRY_TERMINATED,
    )
    assert (
        DecisionLifecycleState.THESIS_DRAFTED,
        DecisionLifecycleState.THESIS_ACTIVE,
    ) in DECISION_LIFECYCLE_TRANSITIONS
    assert (
        OrderLifecycleState.PENDING,
        OrderLifecycleState.PARTIALLY_FILLED,
    ) in ORDER_LIFECYCLE_TRANSITIONS
    assert (
        TradeLifecycleState.EXIT_IN_PROGRESS,
        TradeLifecycleState.CLOSED,
    ) in TRADE_LIFECYCLE_TRANSITIONS


def test_wire_enums_are_frozen():
    expected_values = {
        TimestampRole: (
            "MARKET_EVENT",
            "SIGNAL",
            "DECISION",
            "ORDER_SUBMITTED",
            "FILL",
            "EXIT_DECISION",
        ),
        TimestampSource: (
            "CANONICAL_MARKET_EVENT",
            "STRATEGY_RUNTIME",
            "SIMULATION_CLOCK",
            "BROKER_EVENT",
        ),
        TimestampPrecision: ("MICROSECOND",),
        ThesisType: ("ORB_BREAKOUT",),
        ThesisStatus: ("VALID", "WARNING", "INVALID", "INSUFFICIENT_DATA"),
        TradeSide: ("LONG",),
        EntryEvidenceStatus: ("MATCHED", "NOT_MATCHED", "INSUFFICIENT_DATA"),
        EvidenceValueKind: ("DECIMAL", "INTEGER", "BOOLEAN", "TEXT", "NULL"),
        CompletionPolicy: ("ALL",),
        ComparisonOperator: (
            "GREATER_THAN",
            "GREATER_THAN_OR_EQUAL",
            "LESS_THAN",
        ),
        ExpectedConditionKind: (
            "NEW_HIGH_EXTENSION",
            "POST_ENTRY_VOLUME_EXPANSION",
            "HOLD_ABOVE_VWAP",
        ),
        InvalidConditionKind: (
            "BREAKOUT_LEVEL_LOST",
            "VWAP_CONFIRMATION_LOST",
            "SESSION_DATA_BLOCKED",
        ),
        PriceReference: ("ENTRY_REFERENCE_PRICE", "BREAKOUT_LEVEL"),
        VolumeBaselineKind: (
            "OPENING_RANGE_MEDIAN",
            "HISTORICAL_SAME_TIME_MEDIAN",
            "FROZEN_PRECOMPUTED",
        ),
        VolumeUnit: ("SHARES",),
        DecisionLifecycleState: (
            "SIGNAL_CREATED",
            "THESIS_DRAFTED",
            "THESIS_ACTIVE",
            "EXIT_RECOMMENDATION_ACTIVE",
            "COMPLETED",
            "TERMINATED",
        ),
        OrderLifecycleState: (
            "CREATED",
            "SUBMITTED",
            "PENDING",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
            "RECOVERY_REQUIRED",
        ),
        TradeLifecycleState: (
            "PENDING_ENTRY",
            "ACTIVE_POSITION",
            "EXIT_IN_PROGRESS",
            "CLOSED",
            "ENTRY_TERMINATED",
        ),
        ExitCategory: (
            "EMERGENCY_RISK",
            "THESIS_INVALID",
            "TIME_EXPIRED",
            "TAKE_PROFIT",
        ),
        ExitReason: (
            "STOP_LOSS",
            "ATR_STOP",
            "END_OF_DAY",
            "THESIS_INVALID",
            "TIME_DECAY",
            "TAKE_PROFIT",
            "RISK_GATE",
            "MANUAL",
        ),
        ExitAction: ("HOLD", "EXIT"),
        ExitRecommendationStatus: ("ACTIVE", "RESOLVED_ON_CLOSE"),
        PnlBasis: ("GROSS_SIMULATED", "NET"),
    }
    for enum_type, expected in expected_values.items():
        assert tuple(item.value for item in enum_type) == expected
    assert EXIT_CATEGORY_PRIORITY == tuple(ExitCategory)


@pytest.mark.parametrize("raw", ("100.0", "100.00", "-0", "-0.00", "1E+2"))
def test_decimal_entry_evidence_rejects_noncanonical_wire_values(raw: str):
    with pytest.raises(ValueError, match="canonical notation"):
        EvidenceValue(
            name="last_price",
            kind=EvidenceValueKind.DECIMAL,
            value=raw,
        )


@pytest.mark.parametrize("raw", ("0", "100", "100.5", "0.001"))
def test_decimal_entry_evidence_accepts_canonical_wire_values(raw: str):
    assert EvidenceValue(
        name="last_price",
        kind=EvidenceValueKind.DECIMAL,
        value=raw,
    ).value == raw


def test_orb_condition_order_is_part_of_the_frozen_contract():
    thesis = build_trade_thesis()
    reordered = replace(
        thesis.draft.expected_behavior,
        conditions=tuple(reversed(thesis.draft.expected_behavior.conditions)),
    )

    with pytest.raises(ValueError, match="canonical order"):
        replace(thesis.draft, expected_behavior=reordered)


def test_trade_id_is_bound_to_first_opening_fill():
    first = build_trade_id(SESSION_ID, "opening-fill-001")

    assert first == build_trade_id(SESSION_ID, "opening-fill-001")
    assert first != build_trade_id(SESSION_ID, "opening-fill-002")


def test_exit_decisions_are_per_event_but_recommendation_is_per_trade():
    thesis = build_trade_thesis()
    evaluation_digest = sha256("thesis-invalid")
    first_decision_id = build_exit_decision_id(
        SESSION_ID,
        thesis.trade_id,
        "tick-600",
        EXIT_POLICY_VERSION,
        evaluation_digest,
    )
    second_decision_id = build_exit_decision_id(
        SESSION_ID,
        thesis.trade_id,
        "tick-599",
        EXIT_POLICY_VERSION,
        evaluation_digest,
    )
    recommendation_ids = {
        build_exit_recommendation_id(
            SESSION_ID,
            thesis.trade_id,
            EXIT_POLICY_VERSION,
        )
        for _source_event in ("tick-600", "tick-599", "tick-598")
    }

    assert first_decision_id != second_decision_id
    assert len(recommendation_ids) == 1


def test_exit_decision_contract_rejects_reasonless_exit():
    thesis = build_trade_thesis()
    evaluation_digest = sha256("reasonless")
    decision_id = build_exit_decision_id(
        SESSION_ID,
        thesis.trade_id,
        "tick-2330-093502",
        EXIT_POLICY_VERSION,
        evaluation_digest,
    )

    with pytest.raises(ValueError, match="primary triggered reason"):
        ExitDecision(
            decision_id=decision_id,
            session_id=SESSION_ID,
            trade_id=thesis.trade_id,
            thesis_id=thesis.thesis_id,
            action=ExitAction.EXIT,
            primary_reason=None,
            triggered_reasons=(),
            decided_at=runtime_at(
                9,
                35,
                2,
                "replay-clock:tick-2330-093502",
                role=TimestampRole.EXIT_DECISION,
            ),
            source_event_id="tick-2330-093502",
            exit_policy_version=EXIT_POLICY_VERSION,
            evaluation_digest=evaluation_digest,
        )


def test_active_recommendation_requires_one_stable_trade_identity():
    recommendation = build_exit_recommendation()
    updated = replace(
        recommendation,
        latest_decision_id="exit-decision-002",
        latest_evidence_event_id="tick-2330-093503",
        triggered_reasons=(ExitReason.STOP_LOSS, ExitReason.THESIS_INVALID),
        primary_reason=ExitReason.STOP_LOSS,
        updated_at=runtime_at(
            9,
            35,
            3,
            "replay-clock:tick-2330-093503",
            role=TimestampRole.EXIT_DECISION,
        ),
    )

    assert recommendation.status is ExitRecommendationStatus.ACTIVE
    assert updated.recommendation_id == recommendation.recommendation_id
    assert updated.primary_reason is ExitReason.STOP_LOSS


def test_recommendation_resolves_only_with_final_fill_metadata():
    recommendation = build_exit_recommendation()
    resolved_at = runtime_at(
        9,
        37,
        0,
        "simulation-clock:closing-fill-001",
        role=TimestampRole.FILL,
    )

    resolved = replace(
        recommendation,
        status=ExitRecommendationStatus.RESOLVED_ON_CLOSE,
        resolved_at=resolved_at,
        closing_fill_id="closing-fill-001",
    )
    assert resolved.status is ExitRecommendationStatus.RESOLVED_ON_CLOSE

    with pytest.raises(ValueError, match="close metadata"):
        replace(
            recommendation,
            status=ExitRecommendationStatus.RESOLVED_ON_CLOSE,
        )


def test_partial_exit_legs_keep_independent_reasons_until_close():
    outcome = build_trade_outcome()

    assert [leg.quantity_shares for leg in outcome.exit_legs] == [300, 400, 300]
    assert [leg.reason for leg in outcome.exit_legs] == [
        ExitReason.TAKE_PROFIT,
        ExitReason.THESIS_INVALID,
        ExitReason.TIME_DECAY,
    ]
    assert outcome.initiating_exit_reason is ExitReason.TAKE_PROFIT
    assert outcome.closing_exit_reason is ExitReason.TIME_DECAY


def test_replay_output_binds_input_versions_and_decision_digest():
    verification = build_replay_verification()

    assert verification.output.input_digest == verification.run_identity.manifest_sha256
    assert verification.output.strategy_version == verification.run_identity.strategy_version
    assert verification.output.thesis_version == verification.run_identity.thesis_version
    assert len(verification.output.decision_digest) == 64
    assert len(verification.output.digest) == 64

    mismatched = ReplayOutput(
        input_digest=sha256("different-input"),
        run_identity_digest=verification.run_identity.digest,
        strategy_version=verification.run_identity.strategy_version,
        thesis_version=verification.run_identity.thesis_version,
        decision_digest=sha256("decisions"),
        journal_digest=sha256("journal"),
        final_state_digest=sha256("state"),
    )
    with pytest.raises(ValueError, match="input_digest"):
        ReplayVerification(
            run_identity=verification.run_identity,
            output=mismatched,
        )


def test_replay_divergence_identifies_first_difference_and_actual_output():
    verification = build_replay_verification()
    divergence = ReplayDivergence(
        expected_output_digest=sha256("expected-output"),
        actual_output_digest=verification.output.digest,
        first_differing_event_id="tick-2330-093502",
        first_differing_sequence=42,
    )

    with_divergence = ReplayVerification(
        run_identity=verification.run_identity,
        output=verification.output,
        divergence=divergence,
    )
    assert with_divergence.divergence is divergence

    with pytest.raises(ValueError, match="actual output digest"):
        ReplayVerification(
            run_identity=verification.run_identity,
            output=verification.output,
            divergence=replace(
                divergence,
                actual_output_digest=sha256("different-actual"),
            ),
        )


def test_contract_modules_have_no_runtime_or_execution_dependencies():
    root = Path(__file__).parents[1]
    forbidden_roots = {
        "dashboard",
        "market_data",
        "position",
        "runtime",
        "simulation",
    }
    for relative_path in (
        "trading/trade_management.py",
        "trading/trade_management_serialization.py",
    ):
        tree = ast.parse((root / relative_path).read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert imported_roots.isdisjoint(forbidden_roots)


def test_phase_zero_exposes_no_monitor_or_execution_service():
    import trading.trade_management as contracts

    assert not hasattr(contracts, "ThesisMonitor")
    assert not hasattr(contracts, "RiskGate")
    assert not hasattr(contracts, "OrderApplicationService")
    assert not hasattr(contracts, "ReplayEngine")
    assert tuple(ThesisType) == (ThesisType.ORB_BREAKOUT,)
