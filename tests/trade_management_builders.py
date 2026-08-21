"""Deterministic builders shared by Trade Management contract tests."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from trading.trade_management import (
    BreakoutLevelLostSpec,
    CompletionPolicy,
    EntryEvidence,
    EntryEvidenceStatus,
    EvidenceValue,
    EvidenceValueKind,
    ExitLeg,
    ExitReason,
    ExitRecommendation,
    ExitRecommendationStatus,
    ExpectedBehaviorPolicy,
    HoldAboveVwapSpec,
    NewHighExtensionSpec,
    PnlBasis,
    PostEntryVolumeExpansionSpec,
    PriceReference,
    ReplayOutput,
    ReplayRunIdentity,
    ReplayVerification,
    SessionDataBlockedSpec,
    ThesisType,
    TimestampRole,
    TimestampSource,
    TradeOutcome,
    TradeSide,
    TradeThesis,
    TradeThesisDraft,
    TradeTimestamp,
    VolumeBaselineKind,
    VwapConfirmationLostSpec,
    build_exit_recommendation_id,
    build_thesis_id,
    build_trade_id,
    TAIPEI,
)


SESSION_ID = "session-20260820"
ENTRY_DECISION_ID = "entry-decision-001"
STRATEGY_VERSION = "opening_range_breakout_entry_v1"
THESIS_VERSION = "orb-breakout-v1"
EXIT_POLICY_VERSION = "exit-policy-v1"


def sha256(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def at(
    hour: int,
    minute: int,
    second: int = 0,
    microsecond: int = 0,
    *,
    role: TimestampRole,
    source: TimestampSource,
    source_identity: str,
) -> TradeTimestamp:
    return TradeTimestamp(
        role=role,
        value=datetime(
            2026,
            8,
            20,
            hour,
            minute,
            second,
            microsecond,
            tzinfo=TAIPEI,
        ),
        source=source,
        source_identity=source_identity,
    )


def market_at(
    hour: int,
    minute: int,
    second: int,
    event_id: str,
    *,
    role: TimestampRole = TimestampRole.MARKET_EVENT,
) -> TradeTimestamp:
    return at(
        hour,
        minute,
        second,
        role=role,
        source=TimestampSource.CANONICAL_MARKET_EVENT,
        source_identity=event_id,
    )


def runtime_at(
    hour: int,
    minute: int,
    second: int,
    identity: str,
    *,
    role: TimestampRole,
    microsecond: int = 0,
) -> TradeTimestamp:
    return at(
        hour,
        minute,
        second,
        microsecond,
        role=role,
        source=TimestampSource.SIMULATION_CLOCK,
        source_identity=identity,
    )


def build_trade_thesis() -> TradeThesis:
    signal_at = market_at(
        9,
        30,
        0,
        "tick-2330-093000",
        role=TimestampRole.SIGNAL,
    )
    created_at = runtime_at(
        9,
        30,
        0,
        "strategy-clock:entry-decision-001",
        role=TimestampRole.DECISION,
        microsecond=100000,
    )
    evidence = EntryEvidence(
        evidence_id="evidence-breakout-001",
        kind="OPENING_RANGE_BREAKOUT",
        source_component="backtest.strategies.opening_range_breakout_entry_v1",
        source_version=STRATEGY_VERSION,
        status=EntryEvidenceStatus.MATCHED,
        observed=(
            EvidenceValue(
                name="last_price",
                kind=EvidenceValueKind.DECIMAL,
                value="600.5",
            ),
            EvidenceValue(
                name="completed_bar",
                kind=EvidenceValueKind.BOOLEAN,
                value="true",
            ),
        ),
        threshold=(
            EvidenceValue(
                name="breakout_level",
                kind=EvidenceValueKind.DECIMAL,
                value="600",
            ),
        ),
        market_event_id="tick-2330-093000",
        observed_at=market_at(9, 30, 0, "tick-2330-093000"),
    )
    expected_behavior = ExpectedBehaviorPolicy(
        policy_id="orb-breakout-expected-v1",
        version=THESIS_VERSION,
        observation_window=timedelta(minutes=5),
        warning_after=timedelta(minutes=3),
        completion_policy=CompletionPolicy.ALL,
        conditions=(
            NewHighExtensionSpec(
                reference=PriceReference.BREAKOUT_LEVEL,
                buffer=Decimal("0.5"),
            ),
            PostEntryVolumeExpansionSpec(
                baseline_kind=VolumeBaselineKind.OPENING_RANGE_MEDIAN,
                ratio=Decimal("1.2"),
                minimum_samples=5,
            ),
            HoldAboveVwapSpec(allowed_completed_bars_below=0),
        ),
    )
    thesis_id = build_thesis_id(
        SESSION_ID,
        ENTRY_DECISION_ID,
        ThesisType.ORB_BREAKOUT,
        THESIS_VERSION,
    )
    draft = TradeThesisDraft(
        thesis_id=thesis_id,
        session_id=SESSION_ID,
        symbol="2330",
        side=TradeSide.LONG,
        strategy_id="opening_range_breakout_entry",
        strategy_version=STRATEGY_VERSION,
        thesis_type=ThesisType.ORB_BREAKOUT,
        thesis_version=THESIS_VERSION,
        decision_id=ENTRY_DECISION_ID,
        signal_at=signal_at,
        created_at=created_at,
        entry_evidence=(evidence,),
        expected_behavior=expected_behavior,
        invalid_conditions=(
            BreakoutLevelLostSpec(breakout_level=Decimal("600")),
            VwapConfirmationLostSpec(confirmation_completed_bars=1),
            SessionDataBlockedSpec(
                blocked_health_states=("BLOCKED", "SESSION_MISMATCH"),
            ),
        ),
    )
    opening_fill_id = "fill-entry-001"
    return TradeThesis(
        thesis_id=thesis_id,
        trade_id=build_trade_id(SESSION_ID, opening_fill_id),
        draft=draft,
        opening_order_id="order-entry-001",
        opening_fill_id=opening_fill_id,
        entry_reference_price=Decimal("600.5"),
        filled_at=market_at(
            9,
            31,
            3,
            "tick-2330-093103",
            role=TimestampRole.FILL,
        ),
    )


def build_exit_recommendation() -> ExitRecommendation:
    thesis = build_trade_thesis()
    recommendation_id = build_exit_recommendation_id(
        SESSION_ID,
        thesis.trade_id,
        EXIT_POLICY_VERSION,
    )
    created_at = runtime_at(
        9,
        35,
        2,
        "replay-clock:tick-2330-093502",
        role=TimestampRole.EXIT_DECISION,
    )
    return ExitRecommendation(
        recommendation_id=recommendation_id,
        session_id=SESSION_ID,
        trade_id=thesis.trade_id,
        thesis_id=thesis.thesis_id,
        exit_policy_version=EXIT_POLICY_VERSION,
        status=ExitRecommendationStatus.ACTIVE,
        first_trigger_decision_id="exit-decision-001",
        first_trigger_event_id="tick-2330-093502",
        latest_decision_id="exit-decision-001",
        latest_evidence_event_id="tick-2330-093502",
        primary_reason=ExitReason.THESIS_INVALID,
        triggered_reasons=(ExitReason.THESIS_INVALID,),
        created_at=created_at,
        updated_at=created_at,
    )


def build_trade_outcome() -> TradeOutcome:
    thesis = build_trade_thesis()
    recommendation_id = build_exit_recommendation_id(
        SESSION_ID,
        thesis.trade_id,
        EXIT_POLICY_VERSION,
    )
    legs = (
        ExitLeg(
            fill_id="fill-exit-001",
            order_id="order-exit-001",
            exit_recommendation_id=recommendation_id,
            reason=ExitReason.TAKE_PROFIT,
            quantity_shares=300,
            fill_price=Decimal("620"),
            filled_at=market_at(
                9,
                34,
                0,
                "tick-2330-093400",
                role=TimestampRole.FILL,
            ),
        ),
        ExitLeg(
            fill_id="fill-exit-002",
            order_id="order-exit-002",
            exit_recommendation_id=recommendation_id,
            reason=ExitReason.THESIS_INVALID,
            quantity_shares=400,
            fill_price=Decimal("610"),
            filled_at=market_at(
                9,
                36,
                0,
                "tick-2330-093600",
                role=TimestampRole.FILL,
            ),
        ),
        ExitLeg(
            fill_id="fill-exit-003",
            order_id="order-exit-003",
            exit_recommendation_id=recommendation_id,
            reason=ExitReason.TIME_DECAY,
            quantity_shares=300,
            fill_price=Decimal("605"),
            filled_at=market_at(
                9,
                37,
                0,
                "tick-2330-093700",
                role=TimestampRole.FILL,
            ),
        ),
    )
    return TradeOutcome(
        trade_id=thesis.trade_id,
        exit_legs=legs,
        initiating_exit_reason=ExitReason.TAKE_PROFIT,
        closing_exit_reason=ExitReason.TIME_DECAY,
        realized_pnl=Decimal("11000"),
        pnl_basis=PnlBasis.GROSS_SIMULATED,
        closed_at=legs[-1].filled_at,
    )


def build_replay_verification() -> ReplayVerification:
    run_identity = ReplayRunIdentity(
        manifest_sha256=sha256("ticks-20260820-2330"),
        canonical_event_schema_version="market-event-v1",
        strategy_id="opening_range_breakout_entry",
        strategy_version=STRATEGY_VERSION,
        thesis_type=ThesisType.ORB_BREAKOUT,
        thesis_version=THESIS_VERSION,
        exit_policy_version=EXIT_POLICY_VERSION,
        guard_policy_version="guard-policy-v1",
        fill_model_version="local-paper-fill-model-v1",
        code_identity="git:pr-tm-001-fixture",
    )
    output = ReplayOutput(
        input_digest=run_identity.manifest_sha256,
        run_identity_digest=run_identity.digest,
        strategy_version=run_identity.strategy_version,
        thesis_version=run_identity.thesis_version,
        decision_digest=sha256("decision-stream"),
        journal_digest=sha256("journal-stream"),
        final_state_digest=sha256("final-state"),
    )
    return ReplayVerification(run_identity=run_identity, output=output)
