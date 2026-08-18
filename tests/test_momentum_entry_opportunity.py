from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from config.momentum import MOMENTUM_ENTRY_HYPOTHESIS_V0
from signals.models import (
    EntryOpportunityStatus,
    EpisodeStatus,
    MomentumEpisode,
    MomentumStage,
    RiskGateStatus,
    SignalFamily,
    evaluate_momentum_entry_opportunity,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def accelerated_episode() -> MomentumEpisode:
    as_of = datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI)
    return MomentumEpisode(
        episode_id="8039-20260818-001",
        symbol="8039",
        session_date=date(2026, 8, 18),
        status=EpisodeStatus.ACTIVE,
        created_at=as_of,
        created_by_signal_family=SignalFamily.OPENING_MOMENTUM,
        created_by_config_version="opening_momentum_hypothesis_v0",
        current_signal_family=SignalFamily.OPENING_MOMENTUM,
        current_config_version="opening_momentum_hypothesis_v0",
        current_stage=MomentumStage.ACCELERATING,
        highest_stage=MomentumStage.ACCELERATING,
        breakout_level=Decimal("275"),
        first_seen_at=as_of,
        peak_price=Decimal("278"),
        last_evaluated_at=as_of,
    )


def test_risk_unavailable_is_blocked_not_available():
    opportunity = evaluate_momentum_entry_opportunity(
        accelerated_episode(),
        "signal-1",
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.UNAVAILABLE,
    )

    assert opportunity.status is EntryOpportunityStatus.BLOCKED
    assert "risk_gate_not_passed" in opportunity.reasons


def test_risk_pass_requires_auditable_decision_id():
    opportunity = evaluate_momentum_entry_opportunity(
        accelerated_episode(),
        "signal-1",
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.PASS,
    )

    assert opportunity.status is EntryOpportunityStatus.BLOCKED
    assert opportunity.reasons == ("risk_decision_id_missing",)


def test_supported_acceleration_and_risk_pass_make_entry_available():
    opportunity = evaluate_momentum_entry_opportunity(
        accelerated_episode(),
        "signal-1",
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.PASS,
        risk_decision_id="risk-decision-1",
        position_size_cap=Decimal("50000"),
        invalidation_price=Decimal("275"),
    )

    assert opportunity.status is EntryOpportunityStatus.AVAILABLE
    assert opportunity.reasons == ()
    assert opportunity.position_size_cap == Decimal("50000")
    assert opportunity.invalidation_price == Decimal("275")


def test_unsupported_family_waits_even_when_risk_passes():
    episode = replace(
        accelerated_episode(),
        current_signal_family=SignalFamily.LIMIT_UP_MOMENTUM,
    )
    opening_only = replace(
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        version="opening-only-test",
        enabled_signal_families=frozenset(
            {SignalFamily.OPENING_MOMENTUM}
        ),
    )
    opportunity = evaluate_momentum_entry_opportunity(
        episode,
        "signal-1",
        opening_only,
        RiskGateStatus.PASS,
        risk_decision_id="risk-decision-1",
    )

    assert opportunity.status is EntryOpportunityStatus.WAITING
    assert opportunity.reasons == ("signal_family_not_enabled",)


def test_inactive_or_pre_acceleration_episode_waits():
    base = accelerated_episode()
    breakout = replace(
        base,
        current_stage=MomentumStage.BREAKOUT,
        highest_stage=MomentumStage.BREAKOUT,
    )
    opportunity = evaluate_momentum_entry_opportunity(
        breakout,
        "signal-1",
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.PASS,
        risk_decision_id="risk-decision-1",
    )

    assert opportunity.status is EntryOpportunityStatus.WAITING
    assert opportunity.reasons == ("acceleration_not_confirmed",)


def test_closed_episode_waits_even_when_risk_passes():
    base = accelerated_episode()
    inactive = replace(
        base,
        status=EpisodeStatus.INVALIDATED,
        closed_at=base.created_at,
        close_reason="false_breakout",
    )
    opportunity = evaluate_momentum_entry_opportunity(
        inactive,
        "signal-1",
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.PASS,
        risk_decision_id="risk-decision-1",
    )

    assert opportunity.status is EntryOpportunityStatus.WAITING
    assert opportunity.reasons == ("episode_not_active",)
