from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "8039_2026-08-18_phase3_enriched_replay.json"
)
SCRIPT = PROJECT_ROOT / "scripts" / "replay_momentum_signal.py"


def run_replay() -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(FIXTURE),
            "--tick-coverage-started-at",
            "2026-08-18T09:06:00+08:00",
            "--aggressor-mapping-verified",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_replay_cli_exposes_signal_state_alert_and_blocked_entry():
    payload = run_replay()
    last = payload["last_observation"]

    assert payload["execution_mode"] == "REPLAY_ALERT_ONLY"
    assert last["signal"] == "LIMIT_UP_MOMENTUM"
    assert last["evidence_score"] == 100
    assert last["state"]["current_stage"] == "ACCELERATING"
    assert last["state"]["episode"]["episode_id"] == "8039-20260818-001"
    assert last["state"]["episode"]["created_by_signal_family"] == (
        "OPENING_MOMENTUM"
    )
    assert last["state"]["episode"]["current_signal_family"] == (
        "LIMIT_UP_MOMENTUM"
    )
    assert [
        transition["to_stage"]
        for transition in last["state"]["episode"]["transitions"]
    ] == ["BREAKOUT", "ACCELERATING"]
    assert last["entry_opportunity"]["status"] == "BLOCKED"
    assert last["entry_opportunity"]["reasons"] == [
        "risk_gate_not_passed"
    ]

    assert [alert["stage_or_lock_transition"] for alert in payload["alerts"]] == [
        "BREAKOUT",
        "ACCELERATING",
    ]
    assert payload["pending_alert_count"] == 2


def test_replay_cli_output_digest_is_deterministic():
    first = run_replay()
    second = run_replay()

    assert first["projection_digest"] == second["projection_digest"]
    assert first["last_observation"]["state"]["digest"] == (
        second["last_observation"]["state"]["digest"]
    )
