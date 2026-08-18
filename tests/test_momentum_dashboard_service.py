from __future__ import annotations

from datetime import datetime

import pytest

from dashboard.momentum import MomentumDashboardService


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.fromisoformat(
        f"2026-08-18T{hour:02d}:{minute:02d}:{second:02d}+08:00"
    )


def test_dashboard_projection_exposes_truthful_replay_source_and_signal():
    snapshot = MomentumDashboardService().snapshot()
    item = snapshot["items"][0]

    assert snapshot["status"] == "fixture"
    assert snapshot["mode"] == "REPLAY_ALERT_ONLY"
    assert snapshot["source"]["is_live"] is False
    assert snapshot["source"]["fixture"].endswith("enriched_replay.json")
    assert len(snapshot["source"]["content_sha256"]) == 64
    assert snapshot["summary"]["active_episode_count"] == 1
    assert snapshot["summary"]["pending_alert_count"] == 2

    assert item["symbol"] == "8039"
    assert item["name"] == "台虹"
    assert item["current_stage"] == "ACCELERATING"
    assert item["current_stage_label"] == "加速"
    assert item["market"]["price"] == 278.0
    assert item["market"]["limit_up_price"] == 284.5
    assert item["market"]["distance_to_limit_pct"] == pytest.approx(
        2.3381294964
    )
    assert item["signal"]["evidence_score"] == 100
    assert item["signal"]["evidence_max_score"] == 100
    assert item["signal"]["config_version"] == (
        "limit_up_momentum_hypothesis_v0"
    )
    assert item["entry_opportunity"]["status"] == "BLOCKED"
    assert item["entry_opportunity"]["reason_labels"] == [
        "RiskGate 尚未通過"
    ]


def test_dashboard_projection_preserves_opening_to_limit_family_provenance():
    episode = MomentumDashboardService().snapshot()["items"][0]["episode"]

    assert episode["episode_id"] == "8039-20260818-001"
    assert episode["created_by_signal_family"] == "OPENING_MOMENTUM"
    assert episode["current_signal_family"] == "LIMIT_UP_MOMENTUM"
    assert [item["to_stage"] for item in episode["transitions"]] == [
        "BREAKOUT",
        "ACCELERATING",
    ]
    assert episode["evidence_updates"][0]["signal_family"] == (
        "OPENING_MOMENTUM"
    )
    assert episode["evidence_updates"][-1]["signal_family"] == (
        "LIMIT_UP_MOMENTUM"
    )


def test_acknowledgement_is_idempotent_and_suppresses_pending_count():
    service = MomentumDashboardService()
    initial = service.snapshot()
    alert_id = initial["alerts"][0]["alert_id"]

    acknowledged = service.acknowledge(
        alert_id,
        acknowledged_at=at(9, 18, 1),
    )
    repeated = service.acknowledge(
        alert_id,
        acknowledged_at=at(9, 18, 2),
    )

    assert acknowledged["summary"]["pending_alert_count"] == 1
    assert repeated["summary"]["pending_alert_count"] == 1
    assert repeated["alerts"][0]["acknowledged_at"] == at(9, 18, 1).isoformat()


def test_symbol_lookup_and_unknown_alert_fail_closed():
    service = MomentumDashboardService()

    assert service.symbol(" 8039 ")["current_stage"] == "ACCELERATING"
    with pytest.raises(KeyError, match="沒有"):
        service.symbol("2330")
    with pytest.raises(KeyError, match="unknown"):
        service.acknowledge("missing-alert", acknowledged_at=at(9, 20))
