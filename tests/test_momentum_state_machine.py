from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from config.momentum import LimitLockPolicyConfig
from features.engine import FeatureEngine
from features.models import FeatureEvaluationContext, FeatureValue
from market_data.events import TickEvent
from market_data.health import DataHealth, DataHealthState
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader
from signals.models import (
    EpisodeStatus,
    MomentumSignal,
    MomentumStage,
    SignalEvaluationStatus,
    SignalFamily,
)
from signals.momentum import MomentumSignalEngine
from signals.momentum_state import (
    LimitLockEvidenceStatus,
    LimitLockObservation,
    LimitLockTransition,
    MomentumStateMachine,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "8039_2026-08-18_phase3_enriched_replay.json"
)


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.fromisoformat(
        f"2026-08-18T{hour:02d}:{minute:02d}:{second:02d}+08:00"
    )


def enriched_pair():
    dataset = ReplayDatasetLoader().load(FIXTURE)
    references = InstrumentReferenceStore(dataset.manifest.session_date)
    for reference in dataset.references:
        references.put(reference)
    bars = IntradayBarStore(
        dataset.manifest.session_date,
        retention=timedelta(minutes=20),
    )
    books = OrderBookStore(
        dataset.manifest.session_date,
        retention=timedelta(minutes=20),
    )
    start = dataset.events[0].received_at
    health = DataHealth(dataset.manifest.session_date, started_at=start)
    health.mark_ready(occurred_at=start, evidence="phase4_fixture")
    ingestor = MarketDataIngestor(
        session_id=dataset.manifest.session_id,
        session_date=dataset.manifest.session_date,
        references=references,
        bars=bars,
        books=books,
        health=health,
    )
    current = None
    for envelope in dataset.events:
        assert ingestor.ingest(envelope).projection_applied
        if isinstance(envelope.payload, TickEvent):
            current = envelope.payload
    assert current is not None
    snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=at(9, 6),
            aggressor_mapping_verified=True,
        ),
    )
    return snapshot, MomentumSignalEngine().evaluate(snapshot)


def move_pair(
    snapshot,
    signal,
    as_of: datetime,
    *,
    price: Decimal | None = None,
    vwap: Decimal | None = None,
    return_2m: Decimal | None = None,
    distance: Decimal | None = None,
    acceleration: bool | None = None,
):
    feature = replace(
        snapshot,
        as_of=as_of,
        current_event_id=f"event-{as_of.isoformat()}",
        price=_feature_at(snapshot.price, as_of, price),
        vwap=_feature_at(snapshot.vwap, as_of, vwap),
        return_2m=_feature_at(snapshot.return_2m, as_of, return_2m),
        distance_to_limit=_feature_at(
            snapshot.distance_to_limit,
            as_of,
            distance,
        ),
    )
    if price is not None and vwap is not None:
        feature = replace(
            feature,
            price_above_vwap=_feature_at(
                snapshot.price_above_vwap,
                as_of,
                price > vwap,
            ),
        )
    result = replace(
        signal,
        as_of=as_of,
        momentum_acceleration_confirmed=(
            signal.momentum_acceleration_confirmed
            if acceleration is None
            else acceleration
        ),
    )
    return feature, result


def _feature_at(
    original: FeatureValue,
    as_of: datetime,
    value,
) -> FeatureValue:
    return replace(
        original,
        value=original.value if value is None else value,
        source_as_of=as_of,
    )


def test_enriched_8039_creates_one_accelerating_episode():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())

    update = machine.evaluate(snapshot, signal)
    episode = update.episode

    assert episode is not None
    assert update.episode_created is True
    assert update.previous_stage is MomentumStage.WATCH
    assert update.current_stage is MomentumStage.ACCELERATING
    assert episode.episode_id == "8039-20260818-001"
    assert episode.breakout_level == Decimal("275")
    assert episode.peak_price == Decimal("278")
    assert [item.to_stage for item in episode.transitions] == [
        MomentumStage.BREAKOUT,
        MomentumStage.ACCELERATING,
    ]
    assert len(episode.evidence_updates) == 1


def test_opening_to_limit_handoff_preserves_episode_without_stage_transition():
    snapshot, signal = enriched_pair()
    opening_feature, opening_signal = move_pair(snapshot, signal, at(9, 6))
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
    machine = MomentumStateMachine(snapshot.as_of.date())
    opened = machine.evaluate(opening_feature, opening_signal)
    assert opened.episode is not None
    transition_count = len(opened.episode.transitions)

    handoff_feature, handoff_signal = move_pair(snapshot, signal, at(9, 10))
    handed_off = machine.evaluate(handoff_feature, handoff_signal)
    episode = handed_off.episode

    assert episode is not None
    assert episode.episode_id == opened.episode.episode_id
    assert episode.created_by_signal_family is SignalFamily.OPENING_MOMENTUM
    assert episode.current_signal_family is SignalFamily.LIMIT_UP_MOMENTUM
    assert len(episode.transitions) == transition_count
    assert len(episode.evidence_updates) == 2
    assert handed_off.stage_advanced is False


def test_limit_touch_lock_unlock_and_unknown_are_separate_from_stage():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(
        snapshot.as_of.date(),
        lock_policy=LimitLockPolicyConfig(
            version="lock-test-v1",
            confirmation_duration=timedelta(seconds=2),
        ),
    )
    machine.evaluate(snapshot, signal)
    near_feature, near_signal = move_pair(
        snapshot,
        signal,
        at(9, 18, 30),
        price=Decimal("282"),
        distance=Decimal("0.009"),
    )
    near = machine.evaluate(near_feature, near_signal)
    assert near.current_stage is MomentumStage.NEAR_LIMIT_UP

    touch_feature, touch_signal = move_pair(
        snapshot,
        signal,
        at(9, 19),
        price=Decimal("284.5"),
        distance=Decimal("0"),
    )
    touched = machine.evaluate(touch_feature, touch_signal)
    assert touched.episode is not None
    assert touched.current_stage is MomentumStage.LIMIT_TOUCHED
    assert touched.episode.limit_touched_at == at(9, 19)
    assert touched.episode.limit_locked is None

    first_feature, first_signal = move_pair(
        touch_feature,
        touch_signal,
        at(9, 19, 1),
    )
    first_lock = machine.evaluate(
        first_feature,
        first_signal,
        lock_observation=LimitLockObservation(
            observed_at=at(9, 19, 1),
            status=LimitLockEvidenceStatus.LOCK_CONDITION,
            evidence_id="book-lock-1",
        ),
    )
    assert first_lock.episode is not None
    assert first_lock.episode.limit_locked is None

    lock_feature, lock_signal = move_pair(
        touch_feature,
        touch_signal,
        at(9, 19, 3),
    )
    locked = machine.evaluate(
        lock_feature,
        lock_signal,
        lock_observation=LimitLockObservation(
            observed_at=at(9, 19, 3),
            status=LimitLockEvidenceStatus.LOCK_CONDITION,
            evidence_id="book-lock-2",
        ),
    )
    assert locked.episode is not None
    assert locked.limit_lock_transition is LimitLockTransition.LOCKED
    assert locked.episode.limit_locked is True
    assert locked.episode.limit_locked_at == at(9, 19, 3)

    unlock_feature, unlock_signal = move_pair(
        touch_feature,
        touch_signal,
        at(9, 19, 4),
        price=Decimal("284"),
        distance=Decimal("0.0018"),
    )
    unlocked = machine.evaluate(
        unlock_feature,
        unlock_signal,
        lock_observation=LimitLockObservation(
            observed_at=at(9, 19, 4),
            status=LimitLockEvidenceStatus.UNLOCK_CONDITION,
            evidence_id="book-unlock",
        ),
    )
    assert unlocked.episode is not None
    assert unlocked.limit_lock_transition is LimitLockTransition.UNLOCKED
    assert unlocked.episode.limit_locked is False
    assert unlocked.episode.limit_unlocked_at == at(9, 19, 4)
    assert unlocked.current_stage is MomentumStage.LIMIT_TOUCHED

    unknown_feature, unknown_signal = move_pair(
        touch_feature,
        touch_signal,
        at(9, 19, 5),
    )
    unknown = machine.evaluate(
        unknown_feature,
        unknown_signal,
        lock_observation=LimitLockObservation(
            observed_at=at(9, 19, 5),
            status=LimitLockEvidenceStatus.UNKNOWN,
            evidence_id="book-stale",
        ),
    )
    assert unknown.episode is not None
    assert unknown.limit_lock_transition is LimitLockTransition.UNKNOWN
    assert unknown.episode.limit_locked is None
    assert unknown.episode.limit_unlocked_at == at(9, 19, 4)
    assert unknown.current_stage is MomentumStage.LIMIT_TOUCHED


def test_unresolved_lock_policy_never_claims_locked():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())
    machine.evaluate(snapshot, signal)
    touch_feature, touch_signal = move_pair(
        snapshot,
        signal,
        at(9, 19),
        price=Decimal("284.5"),
        distance=Decimal("0"),
    )
    machine.evaluate(touch_feature, touch_signal)
    later_feature, later_signal = move_pair(
        touch_feature,
        touch_signal,
        at(9, 19, 10),
    )
    update = machine.evaluate(
        later_feature,
        later_signal,
        lock_observation=LimitLockObservation(
            observed_at=at(9, 19, 10),
            status=LimitLockEvidenceStatus.LOCK_CONDITION,
            evidence_id="unreviewed-lock",
        ),
    )

    assert update.episode is not None
    assert update.episode.limit_locked is None
    assert update.limit_lock_transition is None


def test_false_breakout_requires_confirmation_then_cooldown_and_new_episode():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())
    first = machine.evaluate(snapshot, signal)
    assert first.episode is not None

    bad_feature, bad_signal = move_pair(
        snapshot,
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
    assert pending.episode is not None
    assert pending.episode.status is EpisodeStatus.ACTIVE

    bad_feature_2, bad_signal_2 = move_pair(
        bad_feature,
        bad_signal,
        at(9, 19, 1),
    )
    closed = machine.evaluate(bad_feature_2, bad_signal_2)
    assert closed.episode is not None
    assert closed.previous_stage is MomentumStage.ACCELERATING
    assert closed.current_stage is MomentumStage.WATCH
    assert closed.episode.status is EpisodeStatus.INVALIDATED
    assert closed.episode.current_stage is MomentumStage.ACCELERATING
    assert closed.episode.cooldown_until == at(9, 21, 1)

    rebound_feature, rebound_signal = move_pair(
        snapshot,
        signal,
        at(9, 20),
    )
    cooldown = machine.evaluate(rebound_feature, rebound_signal)
    assert cooldown.episode_created is False
    assert cooldown.episode is not None
    assert cooldown.episode.episode_id == "8039-20260818-001"
    assert any(reason.startswith("cooldown_until:") for reason in cooldown.reasons)

    reset_feature, reset_signal = move_pair(
        snapshot,
        signal,
        at(9, 21, 2),
    )
    reset = machine.evaluate(reset_feature, reset_signal)
    assert reset.episode_created is True
    assert reset.episode is not None
    assert reset.episode.episode_id == "8039-20260818-002"


def test_data_health_block_closes_active_episode_immediately():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())
    machine.evaluate(snapshot, signal)
    blocked_feature, blocked_signal = move_pair(
        snapshot,
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

    update = machine.evaluate(blocked_feature, blocked_signal)

    assert update.episode is not None
    assert update.previous_stage is MomentumStage.ACCELERATING
    assert update.current_stage is MomentumStage.WATCH
    assert update.episode.status is EpisodeStatus.DATA_BLOCKED
    assert update.episode.current_stage is MomentumStage.ACCELERATING
    assert update.episode.evidence_updates[-1].evidence_snapshot_id == (
        blocked_signal.digest
    )
    assert update.episode_closed_status is EpisodeStatus.DATA_BLOCKED


def test_episode_ttl_closes_public_stage_without_rewriting_episode_history():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())
    machine.evaluate(snapshot, signal)
    expired_feature, expired_signal = move_pair(
        snapshot,
        signal,
        at(9, 28),
    )

    update = machine.evaluate(expired_feature, expired_signal)

    assert update.episode is not None
    assert update.previous_stage is MomentumStage.ACCELERATING
    assert update.current_stage is MomentumStage.WATCH
    assert update.episode.status is EpisodeStatus.EXPIRED
    assert update.episode.current_stage is MomentumStage.ACCELERATING
    assert update.episode.highest_stage is MomentumStage.ACCELERATING
    assert update.episode_closed_status is EpisodeStatus.EXPIRED


def test_exact_duplicate_is_idempotent_and_out_of_order_is_rejected():
    snapshot, signal = enriched_pair()
    machine = MomentumStateMachine(snapshot.as_of.date())
    first = machine.evaluate(snapshot, signal)
    duplicate = machine.evaluate(snapshot, signal)

    assert duplicate.duplicate_ignored is True
    assert duplicate.episode is not None
    assert first.episode is not None
    assert duplicate.episode.digest == first.episode.digest

    old_feature, old_signal = move_pair(snapshot, signal, at(9, 17, 59))
    with pytest.raises(ValueError, match="chronological"):
        machine.evaluate(old_feature, old_signal)
