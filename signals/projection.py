"""In-memory Momentum read model and alert deduplication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Callable, cast

from features.models import IntradayFeatureSnapshot
from signals.models import (
    EntryOpportunity,
    EpisodeStatus,
    MomentumEpisode,
    MomentumStage,
    SignalFamily,
    SignalResult,
)
from signals.momentum_state import (
    LimitLockTransition,
    MomentumStateUpdate,
)


class MomentumAlertEventType(StrEnum):
    STAGE_ADVANCED = "STAGE_ADVANCED"
    LIMIT_TOUCHED = "LIMIT_TOUCHED"
    LIMIT_LOCKED = "LIMIT_LOCKED"
    LIMIT_UNLOCKED = "LIMIT_UNLOCKED"
    LIMIT_LOCK_UNKNOWN = "LIMIT_LOCK_UNKNOWN"
    EPISODE_INVALIDATED = "EPISODE_INVALIDATED"
    EPISODE_EXPIRED = "EPISODE_EXPIRED"
    DATA_BLOCKED = "DATA_BLOCKED"


@dataclass(frozen=True)
class MomentumAlert:
    alert_id: str
    session_date: date
    symbol: str
    episode_id: str
    event_type: MomentumAlertEventType
    stage_or_lock_transition: str
    occurred_at: datetime
    signal_family: SignalFamily
    config_version: str
    evidence_snapshot_id: str
    acknowledged_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.alert_id, "alert_id"),
            (self.symbol, "symbol"),
            (self.episode_id, "episode_id"),
            (self.stage_or_lock_transition, "stage_or_lock_transition"),
            (self.config_version, "config_version"),
            (self.evidence_snapshot_id, "evidence_snapshot_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        _require_aware(self.occurred_at, "alert occurred_at")
        if self.acknowledged_at is not None:
            _require_aware(self.acknowledged_at, "alert acknowledged_at")
            if self.acknowledged_at < self.occurred_at:
                raise ValueError("alert acknowledgement cannot predate alert")

    @property
    def dedup_identity(self) -> tuple[object, ...]:
        return (
            self.session_date,
            self.symbol,
            self.episode_id,
            self.event_type,
            self.stage_or_lock_transition,
        )


@dataclass(frozen=True)
class MomentumProjection:
    symbol: str
    as_of: datetime
    current_stage: MomentumStage
    highest_stage: MomentumStage
    episode: MomentumEpisode | None
    feature_snapshot: IntradayFeatureSnapshot
    signal_result: SignalResult
    entry_opportunity: EntryOpportunity | None
    alert_ids: tuple[str, ...]

    @property
    def digest(self) -> str:
        payload = {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "current_stage": self.current_stage.value,
            "highest_stage": self.highest_stage.value,
            "episode_digest": self.episode.digest if self.episode else None,
            "current_event_id": self.feature_snapshot.current_event_id,
            "signal_digest": self.signal_result.digest,
            "entry": _entry_payload(self.entry_opportunity),
            "alert_ids": list(self.alert_ids),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class MomentumProjectionStore:
    """Store read models and suppress alerts by domain identity."""

    def __init__(self, session_date: date) -> None:
        self._session_date = session_date
        self._projections: dict[str, MomentumProjection] = {}
        self._alerts: dict[str, MomentumAlert] = {}
        self._alert_ids_by_symbol: dict[str, list[str]] = {}
        self._dedup_identities: set[tuple[object, ...]] = set()
        self._suppressed_alert_count = 0

    @property
    def suppressed_alert_count(self) -> int:
        return self._suppressed_alert_count

    def begin_session(self, session_date: date) -> None:
        if session_date == self._session_date:
            return
        cast(Callable[[date], None], getattr(self, "__init__"))(session_date)

    def apply(
        self,
        feature_snapshot: IntradayFeatureSnapshot,
        signal_result: SignalResult,
        state_update: MomentumStateUpdate,
        *,
        entry_opportunity: EntryOpportunity | None = None,
    ) -> MomentumProjection:
        self._validate_apply(feature_snapshot, signal_result, state_update)
        if not state_update.duplicate_ignored:
            for alert in self._alerts_for_update(state_update):
                if alert.dedup_identity in self._dedup_identities:
                    self._suppressed_alert_count += 1
                    continue
                self._dedup_identities.add(alert.dedup_identity)
                self._alerts[alert.alert_id] = alert
                self._alert_ids_by_symbol.setdefault(alert.symbol, []).append(
                    alert.alert_id
                )

        episode = state_update.episode
        highest_stage = (
            episode.highest_stage if episode is not None else state_update.current_stage
        )
        projection = MomentumProjection(
            symbol=feature_snapshot.symbol,
            as_of=feature_snapshot.as_of,
            current_stage=state_update.current_stage,
            highest_stage=highest_stage,
            episode=episode,
            feature_snapshot=feature_snapshot,
            signal_result=signal_result,
            entry_opportunity=entry_opportunity,
            alert_ids=tuple(
                self._alert_ids_by_symbol.get(feature_snapshot.symbol, ())
            ),
        )
        self._projections[feature_snapshot.symbol] = projection
        return projection

    def get(self, symbol: str) -> MomentumProjection | None:
        return self._projections.get(symbol)

    def all(self) -> tuple[MomentumProjection, ...]:
        return tuple(self._projections[key] for key in sorted(self._projections))

    def alerts_for(self, symbol: str) -> tuple[MomentumAlert, ...]:
        return tuple(
            self._alerts[alert_id]
            for alert_id in self._alert_ids_by_symbol.get(symbol, ())
        )

    def pending_alerts(self) -> tuple[MomentumAlert, ...]:
        return tuple(
            self._alerts[key]
            for key in sorted(self._alerts)
            if self._alerts[key].acknowledged_at is None
        )

    def acknowledge(self, alert_id: str, *, acknowledged_at: datetime) -> None:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise KeyError(f"unknown Momentum alert: {alert_id}")
        _require_aware(acknowledged_at, "acknowledged_at")
        if acknowledged_at < alert.occurred_at:
            raise ValueError("alert acknowledgement cannot predate alert")
        if alert.acknowledged_at is not None:
            return
        self._alerts[alert_id] = replace(
            alert,
            acknowledged_at=acknowledged_at,
        )

    @property
    def digest(self) -> str:
        payload = {
            "session_date": self._session_date.isoformat(),
            "projections": [item.digest for item in self.all()],
            "alerts": [
                {
                    "alert_id": item.alert_id,
                    "identity": [str(value) for value in item.dedup_identity],
                    "occurred_at": item.occurred_at.isoformat(),
                    "signal_family": item.signal_family.value,
                    "config_version": item.config_version,
                    "evidence_snapshot_id": item.evidence_snapshot_id,
                    "acknowledged_at": (
                        item.acknowledged_at.isoformat()
                        if item.acknowledged_at is not None
                        else None
                    ),
                }
                for item in sorted(
                    self._alerts.values(),
                    key=lambda value: value.alert_id,
                )
            ],
            "suppressed_alert_count": self._suppressed_alert_count,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _alerts_for_update(
        self,
        update: MomentumStateUpdate,
    ) -> tuple[MomentumAlert, ...]:
        episode = update.episode
        if episode is None:
            return ()
        specs: list[tuple[MomentumAlertEventType, str, str]] = []
        if update.stage_advanced and _stage_is_alertable(update.current_stage):
            event_type = (
                MomentumAlertEventType.LIMIT_TOUCHED
                if update.current_stage is MomentumStage.LIMIT_TOUCHED
                else MomentumAlertEventType.STAGE_ADVANCED
            )
            specs.append(
                (event_type, update.current_stage.value, update.evidence_snapshot_id)
            )
        if update.episode_closed_status is not None:
            specs.append(
                (
                    _closed_event_type(update.episode_closed_status),
                    update.episode_closed_status.value,
                    update.evidence_snapshot_id,
                )
            )
        if update.limit_lock_transition is not None:
            specs.append(
                (
                    _lock_event_type(update.limit_lock_transition),
                    update.limit_lock_transition.value,
                    update.lock_evidence_id or update.evidence_snapshot_id,
                )
            )
        return tuple(
            self._build_alert(episode, update.as_of, *spec)
            for spec in specs
        )

    @staticmethod
    def _build_alert(
        episode: MomentumEpisode,
        occurred_at: datetime,
        event_type: MomentumAlertEventType,
        stage_or_lock_transition: str,
        evidence_snapshot_id: str,
    ) -> MomentumAlert:
        identity = (
            episode.session_date.isoformat(),
            episode.symbol,
            episode.episode_id,
            event_type.value,
            stage_or_lock_transition,
        )
        alert_id = hashlib.sha256(
            "|".join(identity).encode()
        ).hexdigest()
        return MomentumAlert(
            alert_id=alert_id,
            session_date=episode.session_date,
            symbol=episode.symbol,
            episode_id=episode.episode_id,
            event_type=event_type,
            stage_or_lock_transition=stage_or_lock_transition,
            occurred_at=occurred_at,
            signal_family=episode.current_signal_family,
            config_version=episode.current_config_version,
            evidence_snapshot_id=evidence_snapshot_id,
        )

    def _validate_apply(
        self,
        feature: IntradayFeatureSnapshot,
        signal: SignalResult,
        state: MomentumStateUpdate,
    ) -> None:
        if feature.as_of.date() != self._session_date:
            raise ValueError("projection input does not belong to session")
        if not (feature.symbol == signal.symbol == state.symbol):
            raise ValueError("projection symbols must match")
        if not (feature.as_of == signal.as_of == state.as_of):
            raise ValueError("projection as_of values must match")
        if state.evidence_snapshot_id != signal.digest:
            raise ValueError("projection state evidence must match signal")


def _closed_event_type(status: EpisodeStatus) -> MomentumAlertEventType:
    mapping = {
        EpisodeStatus.INVALIDATED: MomentumAlertEventType.EPISODE_INVALIDATED,
        EpisodeStatus.EXPIRED: MomentumAlertEventType.EPISODE_EXPIRED,
        EpisodeStatus.DATA_BLOCKED: MomentumAlertEventType.DATA_BLOCKED,
    }
    try:
        return mapping[status]
    except KeyError as error:
        raise ValueError("active episode is not a closure event") from error


def _lock_event_type(
    transition: LimitLockTransition,
) -> MomentumAlertEventType:
    return {
        LimitLockTransition.LOCKED: MomentumAlertEventType.LIMIT_LOCKED,
        LimitLockTransition.UNLOCKED: MomentumAlertEventType.LIMIT_UNLOCKED,
        LimitLockTransition.UNKNOWN: MomentumAlertEventType.LIMIT_LOCK_UNKNOWN,
    }[transition]


def _stage_is_alertable(stage: MomentumStage) -> bool:
    return stage in {
        MomentumStage.BREAKOUT,
        MomentumStage.ACCELERATING,
        MomentumStage.NEAR_LIMIT_UP,
        MomentumStage.LIMIT_TOUCHED,
    }


def _entry_payload(entry: EntryOpportunity | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "mode": entry.mode.value,
        "status": entry.status.value,
        "signal_id": entry.signal_id,
        "policy_version": entry.policy_version,
        "risk_decision_id": entry.risk_decision_id,
        "risk_level": entry.risk_level.value,
        "position_size_cap": (
            str(entry.position_size_cap)
            if entry.position_size_cap is not None
            else None
        ),
        "invalidation_price": (
            str(entry.invalidation_price)
            if entry.invalidation_price is not None
            else None
        ),
        "reasons": list(entry.reasons),
    }


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
