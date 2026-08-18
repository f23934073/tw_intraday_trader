"""Phase 0 tests for Momentum family, episode, and entry contracts."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from config.momentum import (
    LIMIT_LOCK_HYPOTHESIS_V0,
    LIMIT_UP_MOMENTUM_HYPOTHESIS_V0,
    MOMENTUM_ENTRY_HYPOTHESIS_V0,
    MOMENTUM_STATE_HYPOTHESIS_V0,
    OPENING_MOMENTUM_HYPOTHESIS_V0,
    SUBSCRIPTION_CAPACITY_PHASE0,
)
from signals.models import (
    EpisodeStatus,
    EvidenceStatus,
    EvidenceUpdate,
    MomentumEntryPolicyConfig,
    MomentumEpisode,
    MomentumSignal,
    MomentumStage,
    RiskGateStatus,
    SignalFamily,
    SignalDetail,
    SignalResult,
    StageTransition,
    evaluate_momentum_entry_policy,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 18, hour, minute, second, tzinfo=TAIPEI)


def opening_breakout_episode() -> MomentumEpisode:
    return MomentumEpisode(
        episode_id="8039-20260818-001",
        symbol="8039",
        session_date=SESSION_DATE,
        status=EpisodeStatus.ACTIVE,
        created_at=at(9, 5),
        created_by_signal_family=SignalFamily.OPENING_MOMENTUM,
        created_by_config_version="opening_momentum_hypothesis_v0",
        current_signal_family=SignalFamily.OPENING_MOMENTUM,
        current_config_version="opening_momentum_hypothesis_v0",
        current_stage=MomentumStage.BREAKOUT,
        highest_stage=MomentumStage.BREAKOUT,
    )


def test_each_family_maps_its_signal_to_the_same_acceleration_semantic():
    opening = OPENING_MOMENTUM_HYPOTHESIS_V0.family
    post_warmup = LIMIT_UP_MOMENTUM_HYPOTHESIS_V0.family

    assert opening.confirms_acceleration(MomentumSignal.OPENING_MOMENTUM)
    assert post_warmup.confirms_acceleration(MomentumSignal.LIMIT_UP_MOMENTUM)
    assert not opening.confirms_acceleration(MomentumSignal.LIMIT_UP_MOMENTUM)
    assert not post_warmup.confirms_acceleration(MomentumSignal.OPENING_MOMENTUM)


def test_signal_result_exposes_family_neutral_acceleration_confirmation():
    detail = SignalDetail(
        rule="breakout",
        status=EvidenceStatus.VALID,
        passed=True,
        points_awarded=20,
        points_possible=20,
        observed_value="278 > 275",
        threshold="price > previous_intraday_high",
        source_as_of=at(9, 6),
    )
    result = SignalResult(
        symbol="8039",
        as_of=at(9, 6),
        config_version="opening_momentum_hypothesis_v0",
        feature_version="intraday_features_v0",
        signal_family=SignalFamily.OPENING_MOMENTUM,
        signal=MomentumSignal.OPENING_MOMENTUM,
        triggered_signals=(MomentumSignal.BREAKOUT, MomentumSignal.OPENING_MOMENTUM),
        momentum_acceleration_confirmed=True,
        evidence_score=80,
        evidence_max_score=100,
        passed_rule_count=5,
        total_rule_count=6,
        coverage=1.0,
        data_health="HEALTHY",
        details=(detail,),
    )

    assert result.momentum_acceleration_confirmed is True
    assert result.details == (detail,)


def test_opening_can_advance_breakout_episode_to_accelerating():
    episode = opening_breakout_episode()
    transition = StageTransition(
        occurred_at=at(9, 6),
        from_stage=MomentumStage.BREAKOUT,
        to_stage=MomentumStage.ACCELERATING,
        signal_family=SignalFamily.OPENING_MOMENTUM,
        config_version="opening_momentum_hypothesis_v0",
        evidence_snapshot_id="evidence-090600",
    )

    accelerated = episode.with_transition(transition)

    assert accelerated.current_stage is MomentumStage.ACCELERATING
    assert accelerated.current_signal_family is SignalFamily.OPENING_MOMENTUM
    assert accelerated.transitions == (transition,)


def test_0910_handoff_preserves_creation_and_transition_provenance():
    episode = opening_breakout_episode().with_transition(
        StageTransition(
            occurred_at=at(9, 6),
            from_stage=MomentumStage.BREAKOUT,
            to_stage=MomentumStage.ACCELERATING,
            signal_family=SignalFamily.OPENING_MOMENTUM,
            config_version="opening_momentum_hypothesis_v0",
            evidence_snapshot_id="evidence-opening",
        )
    )
    handoff = EvidenceUpdate(
        occurred_at=at(9, 10),
        signal_family=SignalFamily.LIMIT_UP_MOMENTUM,
        config_version="limit_up_momentum_hypothesis_v0",
        evidence_snapshot_id="evidence-post-warmup",
        momentum_acceleration_confirmed=True,
    )

    updated = episode.with_evidence_update(handoff)

    assert updated.episode_id == episode.episode_id
    assert updated.created_by_signal_family is SignalFamily.OPENING_MOMENTUM
    assert updated.created_by_config_version == "opening_momentum_hypothesis_v0"
    assert updated.current_signal_family is SignalFamily.LIMIT_UP_MOMENTUM
    assert updated.current_config_version == "limit_up_momentum_hypothesis_v0"
    assert updated.current_stage is MomentumStage.ACCELERATING
    assert updated.transitions == episode.transitions
    assert updated.evidence_updates == (handoff,)


def test_momentum_entry_accepts_opening_family_when_policy_and_risk_pass():
    accelerated = opening_breakout_episode().with_transition(
        StageTransition(
            occurred_at=at(9, 6),
            from_stage=MomentumStage.BREAKOUT,
            to_stage=MomentumStage.ACCELERATING,
            signal_family=SignalFamily.OPENING_MOMENTUM,
            config_version="opening_momentum_hypothesis_v0",
            evidence_snapshot_id="evidence-opening",
        )
    )

    decision = evaluate_momentum_entry_policy(
        accelerated,
        MOMENTUM_ENTRY_HYPOTHESIS_V0,
        RiskGateStatus.PASS,
    )

    assert decision.eligible is True
    assert decision.reasons == ()


def test_momentum_entry_reports_policy_and_risk_reasons_independently():
    accelerated = opening_breakout_episode().with_transition(
        StageTransition(
            occurred_at=at(9, 6),
            from_stage=MomentumStage.BREAKOUT,
            to_stage=MomentumStage.ACCELERATING,
            signal_family=SignalFamily.OPENING_MOMENTUM,
            config_version="opening_momentum_hypothesis_v0",
            evidence_snapshot_id="evidence-opening",
        )
    )
    limit_only_policy = MomentumEntryPolicyConfig(
        version="limit_only_test",
        enabled_signal_families=frozenset({SignalFamily.LIMIT_UP_MOMENTUM}),
    )

    decision = evaluate_momentum_entry_policy(
        accelerated,
        limit_only_policy,
        RiskGateStatus.BLOCKED,
    )

    assert decision.eligible is False
    assert decision.reasons == (
        "signal_family_not_enabled",
        "risk_gate_not_passed",
    )


def test_phase0_unresolved_runtime_choices_fail_closed():
    assert OPENING_MOMENTUM_HYPOTHESIS_V0.runtime_ready is False
    assert LIMIT_LOCK_HYPOTHESIS_V0.runtime_ready is False
    assert SUBSCRIPTION_CAPACITY_PHASE0.max_symbols is None
    assert LIMIT_UP_MOMENTUM_HYPOTHESIS_V0.evidence_max_score == 100
    assert MOMENTUM_STATE_HYPOTHESIS_V0.version == "momentum_state_hypothesis_v0"
    assert MOMENTUM_STATE_HYPOTHESIS_V0.near_limit_distance == Decimal("0.01")


def test_transition_rejects_non_forward_stage_change():
    with pytest.raises(ValueError, match="move forward"):
        StageTransition(
            occurred_at=at(9, 7),
            from_stage=MomentumStage.ACCELERATING,
            to_stage=MomentumStage.BREAKOUT,
            signal_family=SignalFamily.OPENING_MOMENTUM,
            config_version="opening_momentum_hypothesis_v0",
            evidence_snapshot_id="bad-transition",
        )


def test_episode_rejects_evidence_from_before_creation():
    episode = opening_breakout_episode()
    update = EvidenceUpdate(
        occurred_at=episode.created_at - timedelta(seconds=1),
        signal_family=SignalFamily.OPENING_MOMENTUM,
        config_version="opening_momentum_hypothesis_v0",
        evidence_snapshot_id="stale-evidence",
        momentum_acceleration_confirmed=False,
    )

    with pytest.raises(ValueError, match="cannot predate"):
        episode.with_evidence_update(update)


def test_limit_lock_true_requires_timestamped_book_evidence():
    with pytest.raises(ValueError, match="requires lock time"):
        replace(
            opening_breakout_episode(),
            limit_touched_at=at(9, 8),
            limit_locked=True,
        )


def test_non_valid_evidence_requires_an_explicit_reason():
    with pytest.raises(ValueError, match="missing reason"):
        SignalDetail(
            rule="external_ratio_rising",
            status=EvidenceStatus.UNVERIFIED,
            passed=None,
            points_awarded=0,
            points_possible=10,
            observed_value=None,
            threshold=Decimal("0.60"),
        )
