#!/usr/bin/env python3
"""Print deterministic Momentum signal observations from an immutable Replay."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from features.engine import FeatureEngine
from features.models import FeatureEvaluationContext
from market_data.events import TickEvent
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader
from signals.momentum import MomentumSignalEngine
from signals.models import (
    RiskGateStatus,
    evaluate_momentum_entry_opportunity,
)
from signals.momentum_state import MomentumStateMachine
from signals.projection import MomentumProjectionStore
from config.momentum import MOMENTUM_ENTRY_HYPOTHESIS_V0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a market-data-only Momentum replay fixture.",
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--tick-coverage-started-at",
        type=_aware_datetime,
        required=True,
        help="Explicit ISO-8601 start of continuous Tick coverage.",
    )
    parser.add_argument(
        "--aggressor-mapping-verified",
        action="store_true",
        help="Count external-ratio evidence only for a separately verified mapping.",
    )
    arguments = parser.parse_args()

    dataset = ReplayDatasetLoader().load(arguments.dataset)
    started_at = (
        dataset.events[0].received_at
        if dataset.events
        else arguments.tick_coverage_started_at
    )
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
    health = DataHealth(dataset.manifest.session_date, started_at=started_at)
    health.mark_ready(
        occurred_at=started_at,
        evidence="replay_manifest_and_reference_validated",
    )
    ingestor = MarketDataIngestor(
        session_id=dataset.manifest.session_id,
        session_date=dataset.manifest.session_date,
        references=references,
        bars=bars,
        books=books,
        health=health,
    )
    features = FeatureEngine(references=references, bars=bars, books=books)
    signals = MomentumSignalEngine()
    state_machine = MomentumStateMachine(dataset.manifest.session_date)
    projections = MomentumProjectionStore(dataset.manifest.session_date)
    observations = []
    for envelope in dataset.events:
        ingest_result = ingestor.ingest(envelope)
        if not ingest_result.projection_applied:
            continue
        if not isinstance(envelope.payload, TickEvent):
            continue
        snapshot = features.evaluate(
            envelope.payload,
            FeatureEvaluationContext(
                data_health=health.snapshot(),
                tick_coverage_started_at=arguments.tick_coverage_started_at,
                aggressor_mapping_verified=(
                    arguments.aggressor_mapping_verified
                ),
            ),
        )
        result = signals.evaluate(snapshot)
        state_update = state_machine.evaluate(snapshot, result)
        entry_opportunity = None
        if state_update.episode is not None:
            entry_opportunity = evaluate_momentum_entry_opportunity(
                state_update.episode,
                result.digest,
                MOMENTUM_ENTRY_HYPOTHESIS_V0,
                RiskGateStatus.UNAVAILABLE,
            )
        projections.apply(
            snapshot,
            result,
            state_update,
            entry_opportunity=entry_opportunity,
        )
        observations.append(
            _serialize(result, state_update, entry_opportunity)
        )

    alerts = tuple(
        alert
        for projection in projections.all()
        for alert in projections.alerts_for(projection.symbol)
    )

    payload = {
        "dataset_id": dataset.manifest.dataset_id,
        "content_sha256": dataset.manifest.content_sha256,
        "execution_mode": "REPLAY_ALERT_ONLY",
        "disclaimer": (
            "Evidence Score counts hypothesis_v0 rules; it is not a "
            "limit-up probability."
        ),
        "observations": observations,
        "last_observation": observations[-1] if observations else None,
        "alerts": [_serialize_alert(alert) for alert in alerts],
        "pending_alert_count": len(projections.pending_alerts()),
        "projection_digest": projections.digest,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _serialize(result, state_update, entry_opportunity) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "as_of": result.as_of.isoformat(),
        "signal_family": result.signal_family.value,
        "signal": result.signal.value,
        "evaluation_status": result.evaluation_status.value,
        "evidence_score": result.evidence_score,
        "evidence_max_score": result.evidence_max_score,
        "momentum_acceleration_confirmed": (
            result.momentum_acceleration_confirmed
        ),
        "data_health": result.data_health,
        "block_reasons": list(result.block_reasons),
        "details": [
            {
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
                "missing_reason": detail.missing_reason,
            }
            for detail in result.details
        ],
        "signal_digest": result.digest,
        "state": {
            "previous_stage": state_update.previous_stage.value,
            "current_stage": state_update.current_stage.value,
            "episode_created": state_update.episode_created,
            "stage_advanced": state_update.stage_advanced,
            "episode_closed_status": (
                state_update.episode_closed_status.value
                if state_update.episode_closed_status is not None
                else None
            ),
            "limit_lock_transition": (
                state_update.limit_lock_transition.value
                if state_update.limit_lock_transition is not None
                else None
            ),
            "reasons": list(state_update.reasons),
            "episode": _serialize_episode(state_update.episode),
            "digest": state_update.digest,
        },
        "entry_opportunity": _serialize_entry(entry_opportunity),
    }


def _serialize_episode(episode) -> dict[str, object] | None:
    if episode is None:
        return None
    return {
        "episode_id": episode.episode_id,
        "status": episode.status.value,
        "created_at": episode.created_at.isoformat(),
        "created_by_signal_family": episode.created_by_signal_family.value,
        "created_by_config_version": episode.created_by_config_version,
        "current_signal_family": episode.current_signal_family.value,
        "current_config_version": episode.current_config_version,
        "current_stage": episode.current_stage.value,
        "highest_stage": episode.highest_stage.value,
        "breakout_level": (
            str(episode.breakout_level)
            if episode.breakout_level is not None
            else None
        ),
        "peak_price": (
            str(episode.peak_price) if episode.peak_price is not None else None
        ),
        "last_progress_at": (
            episode.last_progress_at.isoformat()
            if episode.last_progress_at is not None
            else None
        ),
        "closed_at": (
            episode.closed_at.isoformat()
            if episode.closed_at is not None
            else None
        ),
        "close_reason": episode.close_reason,
        "cooldown_until": (
            episode.cooldown_until.isoformat()
            if episode.cooldown_until is not None
            else None
        ),
        "limit_touched_at": (
            episode.limit_touched_at.isoformat()
            if episode.limit_touched_at is not None
            else None
        ),
        "limit_locked": episode.limit_locked,
        "limit_locked_at": (
            episode.limit_locked_at.isoformat()
            if episode.limit_locked_at is not None
            else None
        ),
        "limit_unlocked_at": (
            episode.limit_unlocked_at.isoformat()
            if episode.limit_unlocked_at is not None
            else None
        ),
        "transition_count": len(episode.transitions),
        "evidence_update_count": len(episode.evidence_updates),
        "transitions": [
            {
                "occurred_at": transition.occurred_at.isoformat(),
                "from_stage": transition.from_stage.value,
                "to_stage": transition.to_stage.value,
                "signal_family": transition.signal_family.value,
                "config_version": transition.config_version,
                "evidence_snapshot_id": transition.evidence_snapshot_id,
            }
            for transition in episode.transitions
        ],
        "evidence_updates": [
            {
                "occurred_at": evidence.occurred_at.isoformat(),
                "signal_family": evidence.signal_family.value,
                "config_version": evidence.config_version,
                "evidence_snapshot_id": evidence.evidence_snapshot_id,
                "momentum_acceleration_confirmed": (
                    evidence.momentum_acceleration_confirmed
                ),
            }
            for evidence in episode.evidence_updates
        ],
        "digest": episode.digest,
    }


def _serialize_entry(entry) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "mode": entry.mode.value,
        "status": entry.status.value,
        "risk_level": entry.risk_level.value,
        "policy_version": entry.policy_version,
        "risk_decision_id": entry.risk_decision_id,
        "reasons": list(entry.reasons),
    }


def _serialize_alert(alert) -> dict[str, object]:
    return {
        "alert_id": alert.alert_id,
        "symbol": alert.symbol,
        "episode_id": alert.episode_id,
        "event_type": alert.event_type.value,
        "stage_or_lock_transition": alert.stage_or_lock_transition,
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


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone offset")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
