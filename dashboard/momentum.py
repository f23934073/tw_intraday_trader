"""Replay-backed Momentum Dashboard projection with no provider side effects."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from config.momentum import MOMENTUM_ENTRY_HYPOTHESIS_V0
from features.engine import FeatureEngine
from features.models import FeatureEvaluationContext, FeatureValue
from market_data.events import TickEvent
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader
from signals.models import (
    EntryOpportunity,
    EvidenceUpdate,
    MomentumEpisode,
    RiskGateStatus,
    SignalDetail,
    StageTransition,
    evaluate_momentum_entry_opportunity,
)
from signals.momentum import MomentumSignalEngine
from signals.momentum_state import MomentumStateMachine
from signals.projection import (
    MomentumAlert,
    MomentumProjection,
    MomentumProjectionStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOMENTUM_REPLAY = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "8039_2026-08-18_phase3_enriched_replay.json"
)
TAIPEI = ZoneInfo("Asia/Taipei")

_STAGE_LABELS = {
    "WATCH": "觀察",
    "STRONG": "強勢",
    "BREAKOUT": "突破",
    "ACCELERATING": "加速",
    "NEAR_LIMIT_UP": "逼近漲停",
    "LIMIT_TOUCHED": "碰觸漲停",
}
_FAMILY_LABELS = {
    "OPENING_MOMENTUM": "開盤動能",
    "LIMIT_UP_MOMENTUM": "漲停加速",
}
_ENTRY_STATUS_LABELS = {
    "WAITING": "等待條件",
    "AVAILABLE": "可評估進場",
    "BLOCKED": "風險條件阻擋",
}
_ALERT_LABELS = {
    "BREAKOUT": "突破前高",
    "ACCELERATING": "強勢突破加速",
    "NEAR_LIMIT_UP": "正在逼近漲停",
    "LIMIT_TOUCHED": "已碰觸漲停",
    "LOCKED": "漲停鎖定",
    "UNLOCKED": "漲停已打開",
    "UNKNOWN": "五檔狀態不明",
    "INVALIDATED": "加速態勢失效",
    "EXPIRED": "加速 episode 到期",
    "DATA_BLOCKED": "行情資料阻擋",
}
_REASON_LABELS = {
    "risk_gate_not_passed": "RiskGate 尚未通過",
    "risk_decision_id_missing": "缺少可稽核的 RiskDecision",
    "episode_not_active": "目前 episode 已結束",
    "acceleration_not_confirmed": "尚未確認加速",
    "signal_family_not_enabled": "目前訊號 family 未開放 Momentum Entry",
}


class MomentumDashboardService:
    """Own one deterministic Replay projection and acknowledgement state."""

    def __init__(
        self,
        dataset_path: Path = DEFAULT_MOMENTUM_REPLAY,
        *,
        symbol_names: Mapping[str, str] | None = None,
    ) -> None:
        self._lock = RLock()
        self._dataset_path = dataset_path
        self._symbol_names = {"8039": "台虹", **(symbol_names or {})}
        self._dataset = ReplayDatasetLoader().load(dataset_path)
        self._references = {
            reference.symbol: reference for reference in self._dataset.references
        }
        self._store = MomentumProjectionStore(
            self._dataset.manifest.session_date
        )
        self._last_event_at: datetime | None = None
        self._build_projection()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [
                self._serialize_projection(projection)
                for projection in self._store.all()
            ]
            alerts = [
                self._serialize_alert(alert)
                for projection in self._store.all()
                for alert in self._store.alerts_for(projection.symbol)
            ]
            pending_count = sum(
                alert["acknowledged_at"] is None for alert in alerts
            )
            return {
                "status": "fixture",
                "mode": "REPLAY_ALERT_ONLY",
                "source": {
                    "dataset_id": self._dataset.manifest.dataset_id,
                    "schema_version": self._dataset.manifest.schema_version,
                    "content_sha256": self._dataset.manifest.content_sha256,
                    "fixture": self._dataset_path.name,
                    "session_date": (
                        self._dataset.manifest.session_date.isoformat()
                    ),
                    "as_of": (
                        self._last_event_at.isoformat()
                        if self._last_event_at is not None
                        else None
                    ),
                    "is_live": False,
                    "aggressor_mapping": "fixture_verified",
                },
                "summary": {
                    "symbol_count": len(items),
                    "active_episode_count": sum(
                        item["episode"]["status"] == "ACTIVE"
                        for item in items
                        if item["episode"] is not None
                    ),
                    "pending_alert_count": pending_count,
                    "projection_digest": self._store.digest,
                },
                "items": items,
                "alerts": alerts,
                "disclaimer": (
                    "Evidence Score 代表 hypothesis_v0 規則證據成立程度，"
                    "不代表漲停機率，也不是買進指令。"
                ),
                "notice": (
                    "目前顯示 immutable Replay fixture；Dashboard polling "
                    "只讀本機 projection，不會連線即時行情或"
                    "送出委託。"
                ),
            }

    def symbol(self, symbol: str) -> dict[str, Any]:
        normalized = symbol.strip()
        with self._lock:
            projection = self._store.get(normalized)
            if projection is None:
                raise KeyError(f"Momentum projection 沒有：{normalized}")
            return self._serialize_projection(projection)

    def acknowledge(
        self,
        alert_id: str,
        *,
        acknowledged_at: datetime | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._store.acknowledge(
                alert_id,
                acknowledged_at=acknowledged_at or datetime.now(TAIPEI),
            )
            return self.snapshot()

    def _build_projection(self) -> None:
        references = InstrumentReferenceStore(
            self._dataset.manifest.session_date
        )
        for reference in self._dataset.references:
            references.put(reference)
        bars = IntradayBarStore(
            self._dataset.manifest.session_date,
            retention=timedelta(minutes=20),
        )
        books = OrderBookStore(
            self._dataset.manifest.session_date,
            retention=timedelta(minutes=20),
        )
        if not self._dataset.events:
            raise ValueError("Momentum Dashboard Replay requires events")
        tick_coverage_started_at = next(
            (
                envelope.payload.event_time
                for envelope in self._dataset.events
                if isinstance(envelope.payload, TickEvent)
            ),
            None,
        )
        if tick_coverage_started_at is None:
            raise ValueError("Momentum Dashboard Replay requires Tick events")
        started_at = self._dataset.events[0].received_at
        health = DataHealth(
            self._dataset.manifest.session_date,
            started_at=started_at,
        )
        health.mark_ready(
            occurred_at=started_at,
            evidence="dashboard_replay_manifest_validated",
        )
        ingestor = MarketDataIngestor(
            session_id=self._dataset.manifest.session_id,
            session_date=self._dataset.manifest.session_date,
            references=references,
            bars=bars,
            books=books,
            health=health,
        )
        feature_engine = FeatureEngine(
            references=references,
            bars=bars,
            books=books,
        )
        signal_engine = MomentumSignalEngine()
        state_machine = MomentumStateMachine(
            self._dataset.manifest.session_date
        )
        for envelope in self._dataset.events:
            result = ingestor.ingest(envelope)
            self._last_event_at = envelope.event_at
            if not result.projection_applied:
                continue
            if not isinstance(envelope.payload, TickEvent):
                continue
            feature = feature_engine.evaluate(
                envelope.payload,
                FeatureEvaluationContext(
                    data_health=health.snapshot(),
                    tick_coverage_started_at=tick_coverage_started_at,
                    aggressor_mapping_verified=True,
                ),
            )
            signal = signal_engine.evaluate(feature)
            state = state_machine.evaluate(feature, signal)
            entry = None
            if state.episode is not None:
                entry = evaluate_momentum_entry_opportunity(
                    state.episode,
                    signal.digest,
                    MOMENTUM_ENTRY_HYPOTHESIS_V0,
                    RiskGateStatus.UNAVAILABLE,
                )
            self._store.apply(
                feature,
                signal,
                state,
                entry_opportunity=entry,
            )

    def _serialize_projection(
        self,
        projection: MomentumProjection,
    ) -> dict[str, Any]:
        feature = projection.feature_snapshot
        signal = projection.signal_result
        reference = self._references[projection.symbol]
        return {
            "symbol": projection.symbol,
            "name": self._symbol_names.get(projection.symbol, ""),
            "as_of": projection.as_of.isoformat(),
            "current_stage": projection.current_stage.value,
            "current_stage_label": _STAGE_LABELS[
                projection.current_stage.value
            ],
            "highest_stage": projection.highest_stage.value,
            "highest_stage_label": _STAGE_LABELS[
                projection.highest_stage.value
            ],
            "market": {
                "price": _number(feature.price.value),
                "vwap": _number(feature.vwap.value),
                "previous_intraday_high": _number(
                    feature.previous_intraday_high.value
                ),
                "limit_up_price": _number(reference.limit_up_price),
                "distance_to_limit_pct": _percent_value(
                    feature.distance_to_limit
                ),
                "return_2m_pct": _percent_value(feature.return_2m),
                "volume_acceleration_2m": _number(
                    feature.volume_acceleration_2m.value
                ),
                "external_ratio_pct": _percent_value(
                    feature.external_ratio_session
                ),
                "bid_ask_ratio_5": _number(
                    feature.bid_ask_ratio_5.value
                ),
            },
            "signal": {
                "family": signal.signal_family.value,
                "family_label": _FAMILY_LABELS[signal.signal_family.value],
                "signal": signal.signal.value,
                "evaluation_status": signal.evaluation_status.value,
                "evidence_score": signal.evidence_score,
                "evidence_max_score": signal.evidence_max_score,
                "passed_rule_count": signal.passed_rule_count,
                "total_rule_count": signal.total_rule_count,
                "coverage": signal.coverage,
                "config_version": signal.config_version,
                "feature_version": signal.feature_version,
                "data_health": signal.data_health,
                "block_reasons": list(signal.block_reasons),
                "details": [
                    _serialize_detail(detail) for detail in signal.details
                ],
                "digest": signal.digest,
            },
            "episode": _serialize_episode(projection.episode),
            "entry_opportunity": _serialize_entry(
                projection.entry_opportunity
            ),
            "alert_ids": list(projection.alert_ids),
            "projection_digest": projection.digest,
        }

    def _serialize_alert(self, alert: MomentumAlert) -> dict[str, Any]:
        name = self._symbol_names.get(alert.symbol, "")
        label = _ALERT_LABELS.get(
            alert.stage_or_lock_transition,
            alert.stage_or_lock_transition,
        )
        display_symbol = f"{alert.symbol} {name}".strip()
        return {
            "alert_id": alert.alert_id,
            "symbol": alert.symbol,
            "name": name,
            "episode_id": alert.episode_id,
            "event_type": alert.event_type.value,
            "stage_or_lock_transition": alert.stage_or_lock_transition,
            "event_label": label,
            "headline": f"{display_symbol}：{label}",
            "occurred_at": alert.occurred_at.isoformat(),
            "signal_family": alert.signal_family.value,
            "config_version": alert.config_version,
            "evidence_snapshot_id": alert.evidence_snapshot_id,
            "acknowledged_at": (
                alert.acknowledged_at.isoformat()
                if alert.acknowledged_at is not None
                else None
            ),
        }


def _serialize_detail(detail: SignalDetail) -> dict[str, Any]:
    return {
        "rule": detail.rule,
        "status": detail.status.value,
        "passed": detail.passed,
        "points_awarded": detail.points_awarded,
        "points_possible": detail.points_possible,
        "observed_value": (
            str(detail.observed_value)
            if detail.observed_value is not None
            else None
        ),
        "threshold": (
            str(detail.threshold) if detail.threshold is not None else None
        ),
        "source_as_of": (
            detail.source_as_of.isoformat()
            if detail.source_as_of is not None
            else None
        ),
        "missing_reason": detail.missing_reason,
    }


def _serialize_episode(
    episode: MomentumEpisode | None,
) -> dict[str, Any] | None:
    if episode is None:
        return None
    return {
        "episode_id": episode.episode_id,
        "status": episode.status.value,
        "created_at": episode.created_at.isoformat(),
        "created_by_signal_family": episode.created_by_signal_family.value,
        "created_by_signal_family_label": _FAMILY_LABELS[
            episode.created_by_signal_family.value
        ],
        "created_by_config_version": episode.created_by_config_version,
        "current_signal_family": episode.current_signal_family.value,
        "current_signal_family_label": _FAMILY_LABELS[
            episode.current_signal_family.value
        ],
        "current_config_version": episode.current_config_version,
        "breakout_level": _number(episode.breakout_level),
        "first_seen_at": _timestamp(episode.first_seen_at),
        "peak_price": _number(episode.peak_price),
        "last_progress_at": _timestamp(episode.last_progress_at),
        "closed_at": _timestamp(episode.closed_at),
        "close_reason": episode.close_reason,
        "cooldown_until": _timestamp(episode.cooldown_until),
        "limit_touched_at": _timestamp(episode.limit_touched_at),
        "limit_locked": episode.limit_locked,
        "limit_lock_evidence_as_of": _timestamp(
            episode.limit_lock_evidence_as_of
        ),
        "limit_locked_at": _timestamp(episode.limit_locked_at),
        "limit_unlocked_at": _timestamp(episode.limit_unlocked_at),
        "transitions": [
            _serialize_transition(transition)
            for transition in episode.transitions
        ],
        "evidence_updates": [
            _serialize_evidence(evidence)
            for evidence in episode.evidence_updates
        ],
        "digest": episode.digest,
    }


def _serialize_transition(transition: StageTransition) -> dict[str, Any]:
    return {
        "occurred_at": transition.occurred_at.isoformat(),
        "from_stage": transition.from_stage.value,
        "from_stage_label": _STAGE_LABELS[transition.from_stage.value],
        "to_stage": transition.to_stage.value,
        "to_stage_label": _STAGE_LABELS[transition.to_stage.value],
        "signal_family": transition.signal_family.value,
        "signal_family_label": _FAMILY_LABELS[transition.signal_family.value],
        "config_version": transition.config_version,
        "evidence_snapshot_id": transition.evidence_snapshot_id,
    }


def _serialize_evidence(evidence: EvidenceUpdate) -> dict[str, Any]:
    return {
        "occurred_at": evidence.occurred_at.isoformat(),
        "signal_family": evidence.signal_family.value,
        "signal_family_label": _FAMILY_LABELS[evidence.signal_family.value],
        "config_version": evidence.config_version,
        "evidence_snapshot_id": evidence.evidence_snapshot_id,
        "momentum_acceleration_confirmed": (
            evidence.momentum_acceleration_confirmed
        ),
    }


def _serialize_entry(
    entry: EntryOpportunity | None,
) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "mode": entry.mode.value,
        "status": entry.status.value,
        "status_label": _ENTRY_STATUS_LABELS[entry.status.value],
        "signal_id": entry.signal_id,
        "policy_version": entry.policy_version,
        "risk_decision_id": entry.risk_decision_id,
        "risk_level": entry.risk_level.value,
        "position_size_cap": _number(entry.position_size_cap),
        "invalidation_price": _number(entry.invalidation_price),
        "reasons": list(entry.reasons),
        "reason_labels": [
            _REASON_LABELS.get(reason, reason) for reason in entry.reasons
        ],
    }


def _percent_value(feature: FeatureValue) -> float | None:
    value = feature.value
    if isinstance(value, Decimal):
        return float(value * Decimal("100"))
    return None


def _number(value: object) -> int | float | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
