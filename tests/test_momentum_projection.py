from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from config.momentum import LimitLockPolicyConfig
from market_data.health import DataHealthState
from signals.models import (
    EpisodeStatus,
    MomentumSignal,
    MomentumStage,
    SignalEvaluationStatus,
    SignalFamily,
)
from signals.momentum_state import (
    LimitLockEvidenceStatus,
    LimitLockObservation,
    MomentumStateMachine,
)
from signals.projection import (
    MomentumAlertEventType,
    MomentumProjectionStore,
)
from tests.test_momentum_state_machine import at, enriched_pair, move_pair


def test_one_evaluation_jump_emits_only_final_accelerating_alert():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())

    update = machine.evaluate(feature, signal)
    projection = store.apply(feature, signal, update)
    alerts = store.alerts_for(feature.symbol)

    assert update.current_stage is MomentumStage.ACCELERATING
    assert len(update.episode.transitions) == 2
    assert projection.alert_ids == (alerts[0].alert_id,)
    assert len(alerts) == 1
    assert alerts[0].event_type is MomentumAlertEventType.STAGE_ADVANCED
    assert alerts[0].stage_or_lock_transition == "ACCELERATING"


def test_alert_identity_deduplicates_and_acknowledgement_survives_replay():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    update = machine.evaluate(feature, signal)

    first = store.apply(feature, signal, update)
    replayed = store.apply(feature, signal, update)

    assert replayed.alert_ids == first.alert_ids
    assert len(store.alerts_for(feature.symbol)) == 1
    assert store.suppressed_alert_count == 1

    alert_id = first.alert_ids[0]
    store.acknowledge(alert_id, acknowledged_at=at(9, 18, 1))
    duplicate = machine.evaluate(feature, signal)
    store.apply(feature, signal, duplicate)

    assert duplicate.duplicate_ignored is True
    assert store.pending_alerts() == ()
    assert store.alerts_for(feature.symbol)[0].acknowledged_at == at(9, 18, 1)
    with pytest.raises(ValueError, match="cannot predate"):
        store.acknowledge(alert_id, acknowledged_at=at(9, 17, 59))


def test_0910_family_handoff_updates_projection_without_duplicate_alert():
    feature, signal = enriched_pair()
    opening_feature, opening_signal = move_pair(feature, signal, at(9, 6))
    opening_signal = replace(
        opening_signal,
        signal_family=SignalFamily.OPENING_MOMENTUM,
        config_version="opening_momentum_hypothesis_v0",
        signal=MomentumSignal.OPENING_MOMENTUM,
        triggered_signals=(
            MomentumSignal.BREAKOUT,
            MomentumSignal.OPENING_MOMENTUM,
        ),
    )
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    opened = machine.evaluate(opening_feature, opening_signal)
    store.apply(opening_feature, opening_signal, opened)

    handoff_feature, handoff_signal = move_pair(feature, signal, at(9, 10))
    handoff = machine.evaluate(handoff_feature, handoff_signal)
    projection = store.apply(handoff_feature, handoff_signal, handoff)

    assert len(store.alerts_for(feature.symbol)) == 1
    assert projection.episode is not None
    assert projection.episode.episode_id == opened.episode.episode_id
    assert projection.episode.current_signal_family is SignalFamily.LIMIT_UP_MOMENTUM
    assert projection.episode.created_by_signal_family is SignalFamily.OPENING_MOMENTUM


def test_touch_lock_unlock_and_unknown_emit_distinct_alerts():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(
        feature.as_of.date(),
        lock_policy=LimitLockPolicyConfig(
            version="lock-test-v1",
            confirmation_duration=timedelta(seconds=2),
        ),
    )
    store = MomentumProjectionStore(feature.as_of.date())

    initial = machine.evaluate(feature, signal)
    store.apply(feature, signal, initial)
    near_feature, near_signal = move_pair(
        feature,
        signal,
        at(9, 18, 30),
        price=Decimal("282"),
        distance=Decimal("0.009"),
    )
    near = machine.evaluate(near_feature, near_signal)
    store.apply(near_feature, near_signal, near)
    touch_feature, touch_signal = move_pair(
        feature,
        signal,
        at(9, 19),
        price=Decimal("284.5"),
        distance=Decimal("0"),
    )
    touched = machine.evaluate(touch_feature, touch_signal)
    store.apply(touch_feature, touch_signal, touched)

    observations = (
        (at(9, 19, 1), LimitLockEvidenceStatus.LOCK_CONDITION, "lock-1"),
        (at(9, 19, 3), LimitLockEvidenceStatus.LOCK_CONDITION, "lock-2"),
        (at(9, 19, 4), LimitLockEvidenceStatus.UNLOCK_CONDITION, "unlock"),
        (at(9, 19, 5), LimitLockEvidenceStatus.UNKNOWN, "unknown"),
    )
    for observed_at, status, evidence_id in observations:
        observed_feature, observed_signal = move_pair(
            touch_feature,
            touch_signal,
            observed_at,
        )
        update = machine.evaluate(
            observed_feature,
            observed_signal,
            lock_observation=LimitLockObservation(
                observed_at=observed_at,
                status=status,
                evidence_id=evidence_id,
            ),
        )
        store.apply(observed_feature, observed_signal, update)

    alerts = store.alerts_for(feature.symbol)
    assert [item.event_type for item in alerts] == [
        MomentumAlertEventType.STAGE_ADVANCED,
        MomentumAlertEventType.STAGE_ADVANCED,
        MomentumAlertEventType.LIMIT_TOUCHED,
        MomentumAlertEventType.LIMIT_LOCKED,
        MomentumAlertEventType.LIMIT_UNLOCKED,
        MomentumAlertEventType.LIMIT_LOCK_UNKNOWN,
    ]
    assert [item.evidence_snapshot_id for item in alerts[-3:]] == [
        "lock-2",
        "unlock",
        "unknown",
    ]


def test_episode_closure_emits_one_reason_specific_alert():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    opened = machine.evaluate(feature, signal)
    store.apply(feature, signal, opened)
    bad_feature, bad_signal = move_pair(
        feature,
        signal,
        at(9, 19),
        price=Decimal("274"),
        vwap=Decimal("275"),
        return_2m=Decimal("-0.01"),
        acceleration=False,
    )
    bad_signal = replace(
        bad_signal,
        signal=MomentumSignal.NONE,
        triggered_signals=(),
        evaluation_status=SignalEvaluationStatus.NOT_TRIGGERED,
    )
    pending = machine.evaluate(bad_feature, bad_signal)
    store.apply(bad_feature, bad_signal, pending)
    final_feature, final_signal = move_pair(
        bad_feature,
        bad_signal,
        at(9, 19, 1),
    )
    closed = machine.evaluate(final_feature, final_signal)
    store.apply(final_feature, final_signal, closed)

    assert closed.episode_closed_status is EpisodeStatus.INVALIDATED
    assert [item.event_type for item in store.alerts_for(feature.symbol)] == [
        MomentumAlertEventType.STAGE_ADVANCED,
        MomentumAlertEventType.EPISODE_INVALIDATED,
    ]


def test_data_block_alert_and_ten_run_projection_digest_are_deterministic():
    digests = []
    for _ in range(10):
        feature, signal = enriched_pair()
        machine = MomentumStateMachine(feature.as_of.date())
        store = MomentumProjectionStore(feature.as_of.date())
        opened = machine.evaluate(feature, signal)
        store.apply(feature, signal, opened)
        blocked_feature, blocked_signal = move_pair(
            feature,
            signal,
            at(9, 19),
        )
        blocked_feature = replace(
            blocked_feature,
            data_health=DataHealthState.BLOCKED,
        )
        blocked_signal = replace(
            blocked_signal,
            data_health=DataHealthState.BLOCKED.value,
            evaluation_status=SignalEvaluationStatus.INSUFFICIENT_DATA,
        )
        blocked = machine.evaluate(blocked_feature, blocked_signal)
        store.apply(blocked_feature, blocked_signal, blocked)
        digests.append(store.digest)

        assert store.alerts_for(feature.symbol)[-1].event_type is (
            MomentumAlertEventType.DATA_BLOCKED
        )

    assert len(set(digests)) == 1


def test_episode_ttl_emits_expired_alert_with_closing_evidence():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    opened = machine.evaluate(feature, signal)
    store.apply(feature, signal, opened)
    expired_feature, expired_signal = move_pair(
        feature,
        signal,
        at(9, 28),
    )

    expired = machine.evaluate(expired_feature, expired_signal)
    store.apply(expired_feature, expired_signal, expired)

    assert expired.episode_closed_status is EpisodeStatus.EXPIRED
    assert expired.episode is not None
    assert expired.episode.cooldown_until is None
    assert expired.episode.evidence_updates[-1].evidence_snapshot_id == (
        expired_signal.digest
    )
    assert store.alerts_for(feature.symbol)[-1].event_type is (
        MomentumAlertEventType.EPISODE_EXPIRED
    )

    restart_feature, restart_signal = move_pair(
        feature,
        signal,
        at(9, 28, 1),
    )
    restarted = machine.evaluate(restart_feature, restart_signal)

    assert restarted.episode_created is True
    assert restarted.episode is not None
    assert restarted.episode.episode_id == "8039-20260818-002"


def test_projection_rejects_state_from_a_different_signal_evidence():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    update = machine.evaluate(feature, signal)
    mismatched_signal = replace(signal, evidence_score=99)

    with pytest.raises(ValueError, match="state evidence"):
        store.apply(feature, mismatched_signal, update)


def test_new_session_resets_projection_and_state_memory():
    feature, signal = enriched_pair()
    machine = MomentumStateMachine(feature.as_of.date())
    store = MomentumProjectionStore(feature.as_of.date())
    update = machine.evaluate(feature, signal)
    store.apply(feature, signal, update)

    next_session = feature.as_of.date() + timedelta(days=1)
    machine.begin_session(next_session)
    store.begin_session(next_session)

    assert machine.session_date == next_session
    assert machine.latest_episode(feature.symbol) is None
    assert store.all() == ()
    assert store.pending_alerts() == ()
