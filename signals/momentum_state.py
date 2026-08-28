"""Family-neutral Momentum episode state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Callable, cast

from config.momentum import (
    LIMIT_LOCK_HYPOTHESIS_V0,
    MOMENTUM_STATE_HYPOTHESIS_V0,
    LimitLockPolicyConfig,
    MomentumStateMachineConfig,
)
from features.models import FeatureStatus, FeatureValue, IntradayFeatureSnapshot
from market_data.health import DataHealthState
from signals.models import (
    EpisodeStatus,
    EvidenceUpdate,
    MomentumEpisode,
    MomentumStage,
    SignalEvaluationStatus,
    SignalResult,
    StageTransition,
)


class LimitLockEvidenceStatus(StrEnum):
    LOCK_CONDITION = "LOCK_CONDITION"
    UNLOCK_CONDITION = "UNLOCK_CONDITION"
    UNKNOWN = "UNKNOWN"


class LimitLockTransition(StrEnum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LimitLockObservation:
    observed_at: datetime
    status: LimitLockEvidenceStatus
    evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "lock observed_at")
        if not self.evidence_id.strip():
            raise ValueError("lock evidence id must not be empty")


@dataclass(frozen=True)
class MomentumStateUpdate:
    symbol: str
    as_of: datetime
    previous_stage: MomentumStage
    current_stage: MomentumStage
    episode: MomentumEpisode | None
    evidence_snapshot_id: str
    episode_created: bool = False
    stage_advanced: bool = False
    episode_closed_status: EpisodeStatus | None = None
    limit_lock_transition: LimitLockTransition | None = None
    lock_evidence_id: str | None = None
    duplicate_ignored: bool = False
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("state update symbol must not be empty")
        if not self.evidence_snapshot_id.strip():
            raise ValueError("evidence snapshot id must not be empty")
        _require_aware(self.as_of, "state update as_of")

    @property
    def digest(self) -> str:
        payload = {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "previous_stage": self.previous_stage.value,
            "current_stage": self.current_stage.value,
            "episode_digest": self.episode.digest if self.episode else None,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "episode_created": self.episode_created,
            "stage_advanced": self.stage_advanced,
            "episode_closed_status": (
                self.episode_closed_status.value
                if self.episode_closed_status is not None
                else None
            ),
            "limit_lock_transition": (
                self.limit_lock_transition.value
                if self.limit_lock_transition is not None
                else None
            ),
            "lock_evidence_id": self.lock_evidence_id,
            "duplicate_ignored": self.duplicate_ignored,
            "reasons": list(self.reasons),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


_STAGE_ORDER = {
    stage: index
    for index, stage in enumerate(
        (
            MomentumStage.WATCH,
            MomentumStage.STRONG,
            MomentumStage.BREAKOUT,
            MomentumStage.ACCELERATING,
            MomentumStage.NEAR_LIMIT_UP,
            MomentumStage.LIMIT_TOUCHED,
        )
    )
}


class MomentumStateMachine:
    """Own one mutable session projection; episodes themselves stay immutable."""

    def __init__(
        self,
        session_date: date,
        *,
        config: MomentumStateMachineConfig = MOMENTUM_STATE_HYPOTHESIS_V0,
        lock_policy: LimitLockPolicyConfig = LIMIT_LOCK_HYPOTHESIS_V0,
    ) -> None:
        self._session_date = session_date
        self._config = config
        self._lock_policy = lock_policy
        self._active: dict[str, MomentumEpisode] = {}
        self._latest: dict[str, MomentumEpisode] = {}
        self._watch_stage: dict[str, MomentumStage] = {}
        self._cooldown_until: dict[str, datetime] = {}
        self._sequence: dict[str, int] = {}
        self._last_as_of: dict[str, datetime] = {}
        self._last_input_digest: dict[str, str] = {}
        self._invalidation_count: dict[str, int] = {}
        self._lock_candidate_started_at: dict[str, datetime] = {}

    @property
    def session_date(self) -> date:
        return self._session_date

    def begin_session(self, session_date: date) -> None:
        if session_date == self._session_date:
            return
        cast(Callable[..., None], getattr(self, "__init__"))(
            session_date,
            config=self._config,
            lock_policy=self._lock_policy,
        )

    def current_episode(self, symbol: str) -> MomentumEpisode | None:
        return self._active.get(symbol)

    def latest_episode(self, symbol: str) -> MomentumEpisode | None:
        return self._latest.get(symbol)

    def evaluate(
        self,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        *,
        lock_observation: LimitLockObservation | None = None,
    ) -> MomentumStateUpdate:
        self._validate_input(snapshot, signal, lock_observation)
        symbol = snapshot.symbol
        previous_stage = self._public_stage(symbol)
        input_digest = self._input_digest(snapshot, signal, lock_observation)
        if self._last_input_digest.get(symbol) == input_digest:
            return MomentumStateUpdate(
                symbol=symbol,
                as_of=snapshot.as_of,
                previous_stage=previous_stage,
                current_stage=previous_stage,
                episode=self._latest.get(symbol),
                evidence_snapshot_id=signal.digest,
                duplicate_ignored=True,
                reasons=("duplicate_evaluation",),
            )
        last_as_of = self._last_as_of.get(symbol)
        if last_as_of is not None and snapshot.as_of < last_as_of:
            raise ValueError("state evaluations must be chronological")
        self._last_as_of[symbol] = snapshot.as_of
        self._last_input_digest[symbol] = input_digest

        active = self._active.get(symbol)
        if active is None:
            update = self._evaluate_without_active(
                snapshot,
                signal,
                previous_stage,
                lock_observation,
            )
        else:
            update = self._evaluate_active(
                active,
                snapshot,
                signal,
                previous_stage,
                lock_observation,
            )
        return update

    def _evaluate_without_active(
        self,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        previous_stage: MomentumStage,
        lock_observation: LimitLockObservation | None,
    ) -> MomentumStateUpdate:
        symbol = snapshot.symbol
        healthy = self._data_healthy(snapshot, signal)
        strong = healthy and self._is_true(snapshot.price_above_vwap)
        base_stage = MomentumStage.STRONG if strong else MomentumStage.WATCH
        self._watch_stage[symbol] = base_stage
        reasons: list[str] = []
        cooldown_until = self._cooldown_until.get(symbol)
        if cooldown_until is not None and snapshot.as_of < cooldown_until:
            reasons.append(f"cooldown_until:{cooldown_until.isoformat()}")
        can_create = (
            not reasons
            and strong
            and self._is_true(snapshot.breakout)
            and snapshot.previous_intraday_high.status is FeatureStatus.VALID
            and snapshot.price.status is FeatureStatus.VALID
            and signal.evaluation_status
            is not SignalEvaluationStatus.OUTSIDE_WINDOW
        )
        if not can_create:
            if not healthy:
                reasons.append("data_health_not_healthy")
            return MomentumStateUpdate(
                symbol=symbol,
                as_of=snapshot.as_of,
                previous_stage=previous_stage,
                current_stage=base_stage,
                episode=self._latest.get(symbol),
                evidence_snapshot_id=signal.digest,
                stage_advanced=(
                    _STAGE_ORDER[base_stage] > _STAGE_ORDER[previous_stage]
                ),
                reasons=tuple(reasons),
            )

        assert isinstance(snapshot.previous_intraday_high.value, Decimal)
        assert isinstance(snapshot.price.value, Decimal)
        episode = MomentumEpisode(
            episode_id=self._next_episode_id(symbol),
            symbol=symbol,
            session_date=self._session_date,
            status=EpisodeStatus.ACTIVE,
            created_at=snapshot.as_of,
            created_by_signal_family=signal.signal_family,
            created_by_config_version=signal.config_version,
            current_signal_family=signal.signal_family,
            current_config_version=signal.config_version,
            current_stage=MomentumStage.STRONG,
            highest_stage=MomentumStage.STRONG,
            breakout_level=snapshot.previous_intraday_high.value,
            first_seen_at=snapshot.as_of,
            peak_price=snapshot.price.value,
            last_progress_at=snapshot.as_of,
            last_evaluated_at=snapshot.as_of,
        )
        episode = self._append_evidence(episode, signal)
        episode = self._advance(
            episode,
            MomentumStage.BREAKOUT,
            signal,
        )
        episode = self._advance_for_market(episode, snapshot, signal)
        episode, lock_transition = self._apply_lock_observation(
            episode,
            lock_observation,
        )
        self._active[symbol] = episode
        self._latest[symbol] = episode
        self._watch_stage[symbol] = episode.current_stage
        self._invalidation_count[symbol] = 0
        return MomentumStateUpdate(
            symbol=symbol,
            as_of=snapshot.as_of,
            previous_stage=previous_stage,
            current_stage=episode.current_stage,
            episode=episode,
            evidence_snapshot_id=signal.digest,
            episode_created=True,
            stage_advanced=True,
            limit_lock_transition=lock_transition,
            lock_evidence_id=(
                lock_observation.evidence_id
                if lock_transition is not None and lock_observation is not None
                else None
            ),
        )

    def _evaluate_active(
        self,
        episode: MomentumEpisode,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        previous_stage: MomentumStage,
        lock_observation: LimitLockObservation | None,
    ) -> MomentumStateUpdate:
        if not self._data_healthy(snapshot, signal):
            return self._close_episode(
                episode,
                snapshot,
                signal,
                EpisodeStatus.DATA_BLOCKED,
                "data_health_not_healthy",
                previous_stage,
            )
        assert isinstance(snapshot.price.value, Decimal)
        episode = episode.with_market_observation(
            occurred_at=snapshot.as_of,
            price=snapshot.price.value,
        )
        episode = self._append_evidence(episode, signal)
        invalidation_reasons = self._invalidation_reasons(episode, snapshot)
        if invalidation_reasons:
            count = self._invalidation_count.get(snapshot.symbol, 0) + 1
            self._invalidation_count[snapshot.symbol] = count
            if count >= self._config.invalidation_confirmation_observations:
                return self._close_episode(
                    episode,
                    snapshot,
                    signal,
                    EpisodeStatus.INVALIDATED,
                    "+".join(invalidation_reasons),
                    previous_stage,
                )
        else:
            self._invalidation_count[snapshot.symbol] = 0

        episode = self._advance_for_market(episode, snapshot, signal)
        episode, lock_transition = self._apply_lock_observation(
            episode,
            lock_observation,
        )
        last_progress_at = episode.last_progress_at or episode.created_at
        if snapshot.as_of - last_progress_at >= self._config.episode_ttl:
            return self._close_episode(
                episode,
                snapshot,
                signal,
                EpisodeStatus.EXPIRED,
                "episode_progress_ttl_elapsed",
                previous_stage,
            )
        self._active[snapshot.symbol] = episode
        self._latest[snapshot.symbol] = episode
        self._watch_stage[snapshot.symbol] = episode.current_stage
        return MomentumStateUpdate(
            symbol=snapshot.symbol,
            as_of=snapshot.as_of,
            previous_stage=previous_stage,
            current_stage=episode.current_stage,
            episode=episode,
            evidence_snapshot_id=signal.digest,
            stage_advanced=(
                _STAGE_ORDER[episode.current_stage]
                > _STAGE_ORDER[previous_stage]
            ),
            limit_lock_transition=lock_transition,
            lock_evidence_id=(
                lock_observation.evidence_id
                if lock_transition is not None and lock_observation is not None
                else None
            ),
            reasons=tuple(invalidation_reasons),
        )

    def _advance_for_market(
        self,
        episode: MomentumEpisode,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
    ) -> MomentumEpisode:
        distance = snapshot.distance_to_limit
        if (
            distance.status is FeatureStatus.VALID
            and isinstance(distance.value, Decimal)
            and distance.value <= 0
        ):
            episode = self._advance(
                episode,
                MomentumStage.LIMIT_TOUCHED,
                signal,
            )
            if episode.limit_touched_at is None:
                episode = replace(episode, limit_touched_at=snapshot.as_of)
            return episode
        if signal.momentum_acceleration_confirmed:
            episode = self._advance(
                episode,
                MomentumStage.ACCELERATING,
                signal,
            )
        if (
            _STAGE_ORDER[episode.current_stage]
            >= _STAGE_ORDER[MomentumStage.ACCELERATING]
            and distance.status is FeatureStatus.VALID
            and isinstance(distance.value, Decimal)
            and distance.value <= self._config.near_limit_distance
        ):
            episode = self._advance(
                episode,
                MomentumStage.NEAR_LIMIT_UP,
                signal,
            )
        return episode

    @staticmethod
    def _advance(
        episode: MomentumEpisode,
        target: MomentumStage,
        signal: SignalResult,
    ) -> MomentumEpisode:
        if _STAGE_ORDER[target] <= _STAGE_ORDER[episode.current_stage]:
            return episode
        return episode.with_transition(
            StageTransition(
                occurred_at=signal.as_of,
                from_stage=episode.current_stage,
                to_stage=target,
                signal_family=signal.signal_family,
                config_version=signal.config_version,
                evidence_snapshot_id=signal.digest,
            )
        )

    @staticmethod
    def _append_evidence(
        episode: MomentumEpisode,
        signal: SignalResult,
    ) -> MomentumEpisode:
        if (
            episode.evidence_updates
            and episode.evidence_updates[-1].evidence_snapshot_id == signal.digest
        ):
            return episode
        return episode.with_evidence_update(
            EvidenceUpdate(
                occurred_at=signal.as_of,
                signal_family=signal.signal_family,
                config_version=signal.config_version,
                evidence_snapshot_id=signal.digest,
                momentum_acceleration_confirmed=(
                    signal.momentum_acceleration_confirmed
                ),
            )
        )

    def _invalidation_reasons(
        self,
        episode: MomentumEpisode,
        snapshot: IntradayFeatureSnapshot,
    ) -> tuple[str, ...]:
        reasons = []
        price = snapshot.price.value
        if isinstance(price, Decimal):
            if episode.breakout_level is not None and price < episode.breakout_level:
                reasons.append("price_below_breakout_level")
            if (
                snapshot.vwap.status is FeatureStatus.VALID
                and isinstance(snapshot.vwap.value, Decimal)
                and price < snapshot.vwap.value
            ):
                reasons.append("price_below_vwap")
        if (
            snapshot.return_2m.status is FeatureStatus.VALID
            and isinstance(snapshot.return_2m.value, Decimal)
            and snapshot.return_2m.value < 0
        ):
            reasons.append("return_2m_negative")
        return tuple(reasons)

    def _close_episode(
        self,
        episode: MomentumEpisode,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        status: EpisodeStatus,
        reason: str,
        previous_stage: MomentumStage,
    ) -> MomentumStateUpdate:
        episode = self._append_evidence(episode, signal)
        cooldown_until = (
            snapshot.as_of + self._config.cooldown
            if status is EpisodeStatus.INVALIDATED
            else None
        )
        closed = episode.close(
            status=status,
            occurred_at=snapshot.as_of,
            reason=reason,
            cooldown_until=cooldown_until,
        )
        symbol = snapshot.symbol
        self._active.pop(symbol, None)
        self._latest[symbol] = closed
        if closed.cooldown_until is None:
            self._cooldown_until.pop(symbol, None)
        else:
            self._cooldown_until[symbol] = closed.cooldown_until
        self._watch_stage[symbol] = MomentumStage.WATCH
        self._invalidation_count[symbol] = 0
        self._lock_candidate_started_at.pop(symbol, None)
        return MomentumStateUpdate(
            symbol=symbol,
            as_of=snapshot.as_of,
            previous_stage=previous_stage,
            current_stage=closed.current_stage,
            episode=closed,
            evidence_snapshot_id=signal.digest,
            episode_closed_status=status,
            reasons=(reason,),
        )

    def _apply_lock_observation(
        self,
        episode: MomentumEpisode,
        observation: LimitLockObservation | None,
    ) -> tuple[MomentumEpisode, LimitLockTransition | None]:
        if observation is None or episode.limit_touched_at is None:
            return episode, None
        symbol = episode.symbol
        previous = episode.limit_locked
        if observation.status is LimitLockEvidenceStatus.UNKNOWN:
            self._lock_candidate_started_at.pop(symbol, None)
            updated = replace(
                episode,
                limit_locked=None,
                limit_lock_evidence_as_of=observation.observed_at,
            )
            transition = (
                LimitLockTransition.UNKNOWN if previous is not None else None
            )
            return updated, transition
        if observation.status is LimitLockEvidenceStatus.UNLOCK_CONDITION:
            self._lock_candidate_started_at.pop(symbol, None)
            updated = replace(
                episode,
                limit_locked=False,
                limit_lock_evidence_as_of=observation.observed_at,
                limit_unlocked_at=(
                    observation.observed_at
                    if previous is True
                    else episode.limit_unlocked_at
                ),
            )
            transition = (
                LimitLockTransition.UNLOCKED if previous is True else None
            )
            return updated, transition

        duration = self._lock_policy.confirmation_duration
        if duration is None:
            updated = replace(
                episode,
                limit_locked=None,
                limit_lock_evidence_as_of=observation.observed_at,
            )
            transition = (
                LimitLockTransition.UNKNOWN if previous is not None else None
            )
            return updated, transition
        started_at = self._lock_candidate_started_at.setdefault(
            symbol,
            observation.observed_at,
        )
        if observation.observed_at - started_at < duration:
            return episode, None
        if previous is True:
            return (
                replace(
                    episode,
                    limit_lock_evidence_as_of=observation.observed_at,
                ),
                None,
            )
        return (
            replace(
                episode,
                limit_locked=True,
                limit_lock_evidence_as_of=observation.observed_at,
                limit_locked_at=observation.observed_at,
                limit_unlocked_at=None,
            ),
            LimitLockTransition.LOCKED,
        )

    @staticmethod
    def _data_healthy(
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
    ) -> bool:
        return (
            snapshot.data_health is DataHealthState.HEALTHY
            and signal.data_health == DataHealthState.HEALTHY.value
        )

    @staticmethod
    def _is_true(value: FeatureValue) -> bool:
        return value.status is FeatureStatus.VALID and value.value is True

    def _public_stage(self, symbol: str) -> MomentumStage:
        active = self._active.get(symbol)
        if active is not None:
            return active.current_stage
        return self._watch_stage.get(symbol, MomentumStage.WATCH)

    def _next_episode_id(self, symbol: str) -> str:
        sequence = self._sequence.get(symbol, 0) + 1
        self._sequence[symbol] = sequence
        return f"{symbol}-{self._session_date:%Y%m%d}-{sequence:03d}"

    def _validate_input(
        self,
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        lock_observation: LimitLockObservation | None,
    ) -> None:
        if snapshot.symbol != signal.symbol:
            raise ValueError("feature and signal symbols must match")
        if snapshot.as_of != signal.as_of:
            raise ValueError("feature and signal as_of must match")
        if snapshot.as_of.date() != self._session_date:
            raise ValueError("state input does not belong to session")
        if snapshot.price.status is not FeatureStatus.VALID:
            raise ValueError("state input requires a valid current price")
        if lock_observation is not None:
            if lock_observation.observed_at > snapshot.as_of:
                raise ValueError("lock observation cannot use future data")
            if lock_observation.observed_at.date() != self._session_date:
                raise ValueError("lock observation does not belong to session")

    @staticmethod
    def _input_digest(
        snapshot: IntradayFeatureSnapshot,
        signal: SignalResult,
        observation: LimitLockObservation | None,
    ) -> str:
        payload = {
            "current_event_id": snapshot.current_event_id,
            "signal_digest": signal.digest,
            "lock_evidence_id": (
                observation.evidence_id if observation is not None else None
            ),
            "lock_status": observation.status.value if observation else None,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
