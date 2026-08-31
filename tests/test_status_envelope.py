"""StatusEnvelope read model contracts (task170 R1) incl. the task147 44-scenario matrix.

Every fixture below is a TEST_FIXTURE projection of an *existing* authority shape;
none of them touches a provider, broker, Journal, or database.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from dashboard import status_envelope as se

NOW = datetime(2026, 8, 31, 14, 30, 0, tzinfo=se.TAIPEI)
FORMAL_17 = [
    "CURRENT_SNAPSHOT_UNIVERSE",
    "MANIFEST_NOT_RESEARCH_ELIGIBLE",
    "MANIFEST_ISSUES_PRESENT",
    "MISSING_UNIVERSE_CONTRACT",
    "MISSING_LISTING_CONTRACT",
    "MISSING_SESSION_CONTRACT",
    "MISSING_CALENDAR_CONTRACT",
    "MISSING_CLOSING_AUCTION_EVENT_CONTRACT",
    "MISSING_CORPORATE_ACTION_CONTRACT",
    "MISSING_REFERENCE_PRICE_CONTRACT",
    "MISSING_PRICE_LIMIT_CONTRACT",
    "MISSING_SPECIAL_REGIME_CONTRACT",
    "MISSING_COMPLETENESS_CONTRACT",
    "MISSING_EXECUTION_CALIBRATION_CONTRACT",
    "MISSING_SLIPPAGE_CALIBRATION_CONTRACT",
    "INVALID_VOLUME_CONTRACT",
    "INVALID_AMOUNT_CONTRACT",
]
NO_OVERNIGHT_11 = [
    "LIMIT_DOWN_NO_BID",
    "HALT",
    "STALE_BOOK",
    "NO_EXECUTABLE_LIQUIDITY",
    "MISSING_AUCTION_EVENT",
    "ZERO_AUCTION_MATCHABLE_VOLUME",
    "UNSUPPORTED_SESSION_REGIME",
    "SUBMIT_UNKNOWN",
    "RESIDUAL_PARTIAL",
    "RECOVERY_REQUIRED",
    "IDENTITY_MISMATCH",
]
SHA = "a" * 64


# --------------------------------------------------------------------------- fixtures
def readiness(
    *,
    platform: bool = True,
    data: bool = False,
    strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    ids = strategy_ids or []
    return {
        "platform": {
            "ready": platform,
            "status": "PLATFORM_READY" if platform else "PLATFORM_NOT_READY",
        },
        "data": {"ready": data, "status": "DATA_READY" if data else "DATA_NOT_READY"},
        "strategy": {
            "ready": bool(ids),
            "status": "STRATEGY_QUALIFIED" if ids else "NO_QUALIFYING_STRATEGY",
            "qualification_ids": ids,
            "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
        },
    }


def dataset_binding(codes: list[str]) -> dict[str, Any]:
    return {
        "available": True,
        "dataset_id": "dataset-TEST_FIXTURE",
        "manifest_digest": SHA,
        "formal_research_readiness": {
            "ready": not codes,
            "status": "DATA_READY" if not codes else "DATA_NOT_READY",
            "reason_codes": list(codes),
            "research_truth_snapshot_digest": SHA,
        },
    }


def kill(state: str = "DISENGAGED", revision: int = 3) -> dict[str, Any]:
    return {
        "control_state": state,
        "engaged": state != "DISENGAGED",
        "revision": revision,
        "reason": "TEST_FIXTURE" if state != "DISENGAGED" else None,
        "engaged_at": None,
        "last_transition_at": "2026-08-31T09:00:00+08:00",
        "last_actor_id": None,
        "last_operation_id": None,
        "durability": "POSTGRESQL",
        "restart_safe": True,
        "recovered": state != "RECOVERY_REQUIRED",
        "recovery_error": "journal digest mismatch" if state == "RECOVERY_REQUIRED" else None,
        "execution_boundary": "LOCAL_ONLY",
    }


def controller(state: str = "STOPPED", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "LOCAL_PAPER_SIMULATION",
        "execution_authority": False,
        "state": state,
        "decision": state,
        "message": "TEST_FIXTURE",
        "run_id": "run-TEST_FIXTURE" if state == "RUNNING" else None,
        "started_at": None,
        "last_checked_at": "2026-08-31T14:29:58+08:00",
        "last_action_at": None,
        "last_error": None,
        "last_intent": None,
        "last_exit_reason": None,
        "entries_submitted": 0,
        "config": None,
        "pipeline": {"snapshot_digest": SHA} if state == "RUNNING" else None,
        "effective_risk": None,
        "restart_behavior": "MANUAL_START_REQUIRED",
        "kill_switch": kill(),
        "notice": "TEST_FIXTURE",
    }
    payload.update(overrides)
    return payload


def session(health: str = "HEALTHY") -> dict[str, Any]:
    return {
        "quote_mode": "STREAMING",
        "streaming": health == "HEALTHY",
        "stream_health": health,
        "quote_queue_depth": 0,
        "quote_queue_capacity": 1024,
        "last_quote_received_at": "2026-08-31T13:29:59+08:00",
        "stream_error": None if health == "HEALTHY" else "TEST_FIXTURE ingress blocked",
    }


def no_overnight(
    state: str = "NORMAL",
    *,
    mode: str = "ENFORCING",
    revision: int = 8,
    stable_reasons: list[str] | None = None,
    breach_latched: bool | None = None,
    ack_available: bool | None = None,
    identity_mismatch: bool = False,
) -> dict[str, Any]:
    latched = (state == "OVERNIGHT_BREACH") if breach_latched is None else breach_latched
    return {
        "schema_version": "no_overnight_dashboard.v1",
        "status": {
            "mode": mode,
            "state": state,
            "revision": revision,
            "breach_latched": latched,
            "would_actions": [],
            "stable_reasons": list(stable_reasons or []),
            "flat_proof_mode": "STRICT" if state == "CONFIRMED_FLAT" else None,
            "evidence_snapshot_digest": SHA if state == "CONFIRMED_FLAT" else None,
        },
        "acknowledgement": {
            "available": latched if ack_available is None else ack_available,
            "required_phrase": f"確認 revision {revision} 違約" if latched else None,
            "acknowledged": False,
            "acknowledged_at": None,
            "acknowledged_by": None,
        },
        "apply_blockers": {
            "managed_exposure_count": 1 if latched else 0,
            "pending_entry_quantity": 0,
            "pending_exit_quantity": 0,
            "unresolved_execution_count": 0,
            "open_breach": latched,
            "identity_mismatch": identity_mismatch,
        },
        "settings_rotation": {"available": True, "reason": None},
        "evidence": {"execution_snapshot": None, "strict_flat": None},
        "exposures": {"managed": [], "excluded": []},
    }


def run(status: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-TEST_FIXTURE",
        "status": status,
        "config": {"cost_policy_snapshot": None},
        "config_digest": SHA,
        "dataset_id": "dataset-TEST_FIXTURE",
        "dataset_digest": SHA,
        "progress": 0,
        "progress_message": None,
        "created_at": "2026-08-31T14:00:00+08:00",
        "updated_at": "2026-08-31T14:29:00+08:00",
        "error_message": None,
        "result_digest": SHA if status == "COMPLETED" else None,
    }
    payload.update(overrides)
    return payload


def cost_snapshot(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": "tw-cost-policy-v1",
        "commission_rate": "0.001425",
        "slippage_bps": "3.5",
        "slippage_calibration_digest": SHA,
        "snapshot_digest": SHA,
    }
    payload.update(overrides)
    return payload


def comparison(verdict: str, diff: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "comparison_id": "cmp-TEST_FIXTURE",
        "baseline_run_id": "run-baseline",
        "challenger_run_id": "run-challenger",
        "comparable": verdict != "NOT_COMPARABLE",
        "verdict": verdict,
        "config_diff": diff or [],
        "message": "TEST_FIXTURE",
        "comparison_digest": SHA,
    }


def positive(envelope: dict[str, Any]) -> bool:
    return envelope["status"] in se.POSITIVE_STATES or envelope["status"] == "TERMINAL_SUCCESS"


# --------------------------------------------------------------------------- envelope shape
def test_envelope_has_required_b1_fields_and_stable_digest() -> None:
    first = se.formal_dataset_envelope(readiness(), now=NOW)
    later = se.formal_dataset_envelope(readiness(), now=NOW.replace(second=45))
    assert set(first) == se.ENVELOPE_KEYS
    for key in ("revision", "digest", "reason_codes", "as_of", "advisory", "allowed_actions"):
        assert key in first
    assert first["as_of"] == "2026-08-31T14:30:00+08:00"
    assert first["digest"] == later["digest"], "as_of must not perturb the digest"
    assert first["digest"] == se.envelope_digest(first)
    assert se.validate_status_envelope(first) == first
    assert json.loads(se.canonical_json(first)) == first


def test_validator_fails_closed_on_missing_key_wrong_type_unknown_enum_and_digest() -> None:
    base = se.kill_switch_envelope(kill(), now=NOW)
    missing = {k: v for k, v in base.items() if k != "revision"}
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope(missing)
    wrong_type = {**base, "revision": "3"}
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope(wrong_type)
    unknown_enum = {**base, "status": "GREEN"}
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope(unknown_enum)
    tampered = {**base, "reason_codes": ["HALT"]}
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope(tampered)
    bad_digest = {**base, "digest": "0" * 64}
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope(bad_digest)
    upgraded = dict(se.formal_dataset_envelope(readiness(), now=NOW))
    upgraded["status"], upgraded["status_glyph"], upgraded["status_label"] = "READY", "✓", "已就緒"
    upgraded["digest"] = se.envelope_digest(upgraded)
    with pytest.raises(se.StatusEnvelopeInvalid, match="blocking reason"):
        se.validate_status_envelope(upgraded)


def test_unknown_reason_code_is_kept_verbatim_and_never_green() -> None:
    envelope = se.formal_dataset_envelope(
        readiness(),
        now=NOW,
        selected_dataset=dataset_binding(["NEW_CODE_FROM_FUTURE"]),
        strategy_set_version_id="set-TEST_FIXTURE",
    )
    assert envelope["reason_codes"] == ["NEW_CODE_FROM_FUTURE"]
    reason = envelope["reasons"][0]
    assert reason["known"] is False and reason["title"] == "NEW_CODE_FROM_FUTURE"
    assert reason["a11y"] == "A-BLOCK" and envelope["status"] == "BLOCKED"


def test_blocking_reason_escalates_positive_state_instead_of_relaxing() -> None:
    halted = se.no_overnight_envelope(no_overnight("NORMAL", stable_reasons=["HALT"]), now=NOW)
    assert halted["status"] == "BLOCKED"
    critical = se.no_overnight_envelope(
        no_overnight("NORMAL", stable_reasons=["SUBMIT_UNKNOWN"]), now=NOW
    )
    assert critical["status"] == "CRITICAL" and critical["live_region"] == "assertive"


def test_set_builder_fails_closed_per_subject_and_validates_whole_set() -> None:
    def boom() -> dict[str, Any]:
        raise RuntimeError("projection unavailable")

    builders = {
        "backtest_platform": lambda: se.backtest_platform_envelope(readiness(), now=NOW),
        "formal_dataset": boom,
        "strategy_qualification": lambda: se.strategy_qualification_envelope(readiness(), now=NOW),
        "local_paper_runtime": lambda: se.local_paper_runtime_envelope(controller(), now=NOW),
        "quote_ingress": lambda: se.quote_ingress_envelope(session(), now=NOW),
        "kill_switch": lambda: se.kill_switch_envelope(kill(), now=NOW),
        "no_overnight": lambda: se.no_overnight_envelope(no_overnight(), now=NOW),
    }
    payload = se.build_status_envelope_set(builders, now=NOW)
    assert list(payload["envelopes"]) == list(se.SUBJECTS)
    unavailable = payload["envelopes"]["formal_dataset"]
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["reason_codes"] == ["FORMAL_DATASET_STATUS_UNAVAILABLE"]
    assert unavailable["reasons"][0]["known"] is True
    assert unavailable["identity"] == {"error_type": "RuntimeError"}
    assert unavailable["allowed_actions"] == ["reload_status"]
    shadow = payload["envelopes"]["market_shadow"]
    assert (
        shadow["status"] == "NOT_EVALUATED" and shadow["identity"]["error_type"] == "BuilderMissing"
    )
    assert se.validate_status_envelope_set(payload) == payload
    with pytest.raises(se.StatusEnvelopeInvalid):
        se.validate_status_envelope_set({**payload, "envelopes": {}})


def test_catalog_covers_formal_17_no_overnight_11_and_never_uses_live_trading_claims() -> None:
    for code in FORMAL_17 + NO_OVERNIGHT_11:
        assert code in se.REASON_CATALOG, code
    forbidden = ("可實盤", "穩賺", "已核准下單")
    for entry in list(se.REASON_CATALOG.values()) + list(se.ADVISORY_CATALOG.values()):
        assert not any(word in " ".join(entry) for word in forbidden)


def test_local_paper_advisories_own_cost_warning_and_mobile_read_only_policy() -> None:
    envelope = se.local_paper_runtime_envelope(controller(), now=NOW)
    advisory = {item["code"]: item for item in envelope["advisory"]}
    assert (
        "手續費以外的稅／滑價尚未模擬" in advisory["LOCAL_PAPER_TAX_SLIPPAGE_NOT_SIMULATED"]["text"]
    )
    assert advisory["MOBILE_READ_ONLY_MONITOR"]["a11y"] == "A-BLOCK"
    assert envelope["client_policy"] == {
        "mode": "READ_ONLY_MONITOR",
        "max_width_css_px": 700,
        "reason_code": "MOBILE_READ_ONLY_MONITOR",
    }
    assert se.validate_status_envelope(envelope) == envelope


# --------------------------------------------------------------------------- 44 scenarios
Scenario = tuple[str, Any, dict[str, Any]]


def _s(sid: str, builder: Any, **expect: Any) -> Scenario:
    return (sid, builder, expect)


SCENARIOS: list[Scenario] = [
    _s(
        "S02",
        lambda: se.strategy_qualification_envelope(readiness(), now=NOW),
        status="EMPTY",
        codes=["NO_QUALIFYING_STRATEGY"],
        allowed=["view_qualification_evidence"],
        blocked=["start_local_paper"],
    ),
    _s(
        "S03",
        lambda: se.build_status_envelope_set({}, now=NOW)["envelopes"]["kill_switch"],
        status="UNAVAILABLE",
        codes=["KILL_SWITCH_STATUS_UNAVAILABLE"],
        allowed=["reload_status"],
    ),
    _s(
        "S05",
        lambda: se.formal_dataset_envelope(
            readiness(),
            now=NOW,
            selected_dataset=dataset_binding([]),
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        status="READY",
        codes=[],
        allowed=["create_formal_backtest"],
    ),
    _s(
        "S06",
        lambda: se.formal_dataset_envelope(
            readiness(),
            now=NOW,
            selected_dataset=dataset_binding(FORMAL_17),
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        status="BLOCKED",
        codes=FORMAL_17,
        blocked=["create_formal_backtest"],
        allowed=["view_reasons"],
    ),
    _s(
        "S07",
        lambda: se.strategy_qualification_envelope(readiness(), now=NOW),
        status="EMPTY",
        codes=["NO_QUALIFYING_STRATEGY"],
    ),
    _s(
        "S08",
        lambda: se.strategy_qualification_envelope(readiness(strategy_ids=["q-1"]), now=NOW),
        status="READY",
        advisory=["QUALIFICATION_DISPLAY_ONLY"],
        allowed=["open_review_packet"],
        blocked=["start_local_paper"],
    ),
    _s(
        "S09",
        lambda: se.strategy_qualification_envelope(readiness(strategy_ids=["q-1"]), now=NOW),
        blocked=["start_local_paper"],
        not_allowed=["start_local_paper"],
    ),
    _s(
        "S10",
        lambda: se.local_paper_runtime_envelope(controller(), now=NOW),
        allowed=["start_automated_strategy", "check_preflight"],
    ),
    _s(
        "S11",
        lambda: se.backtest_run_envelope(run("QUEUED"), now=NOW),
        status="RUNNING",
        authority="QUEUED",
        allowed=["cancel_run"],
        blocked=["view_results"],
    ),
    _s(
        "S12",
        lambda: se.backtest_run_envelope(run("PREFLIGHT"), now=NOW),
        status="RUNNING",
        authority="PREFLIGHT",
        allowed=["cancel_run"],
    ),
    _s(
        "S13",
        lambda: se.backtest_run_envelope(
            run("RUNNING", progress=42, progress_message="2025-01"), now=NOW
        ),
        status="RUNNING",
        identity={"progress": "42", "progress_message": "2025-01"},
    ),
    _s(
        "S14",
        lambda: se.backtest_run_envelope(run("CANCELLING"), now=NOW),
        status="RUNNING",
        blocked=["cancel_run", "retry_run"],
        not_allowed=["cancel_run", "retry_run"],
    ),
    _s(
        "S15",
        lambda: se.backtest_run_envelope(run("CANCELLED"), now=NOW),
        status="TERMINAL_CANCELLED",
        allowed=["retry_run"],
    ),
    _s(
        "S16",
        lambda: se.backtest_run_envelope(run("FAILED", error_message="<b>boom</b>"), now=NOW),
        status="TERMINAL_FAILED",
        codes=["RUN_FAILED"],
        identity={"error_message": "<b>boom</b>"},
        allowed=["retry_run", "copy_diagnostics"],
    ),
    _s(
        "S16b",
        lambda: se.backtest_run_envelope(run("FAILED"), now=NOW),
        status="TERMINAL_FAILED",
        advisory=["RUN_PROGRESS_IS_SERVER_OWNED", "RUN_ERROR_MESSAGE_NOT_PROVIDED"],
    ),
    _s(
        "S17",
        lambda: se.backtest_run_envelope(run("CONTROL_POSTFLIGHT"), now=NOW),
        status="RUNNING",
        blocked=["view_results"],
        allowed=["view_progress"],
    ),
    _s(
        "S18",
        lambda: se.backtest_run_envelope(run("INVALID_CASH_ADMISSION_CONTROL"), now=NOW),
        status="BLOCKED",
        codes=["INVALID_CASH_ADMISSION_CONTROL"],
        blocked=["retry_run"],
    ),
    _s(
        "S19",
        lambda: se.backtest_run_envelope(run("COMPLETED"), now=NOW),
        status="TERMINAL_SUCCESS",
        advisory=["RUN_PROGRESS_IS_SERVER_OWNED", "COMPLETED_IS_NOT_QUALIFIED"],
        allowed=["view_results", "export_results", "compare_runs", "clone_run"],
        blocked=["start_local_paper"],
    ),
    _s(
        "S20",
        lambda: se.backtest_comparison_envelope(
            comparison("NOT_COMPARABLE", [{"field": "dataset_digest"}]), now=NOW
        ),
        status="BLOCKED",
        codes=["NOT_COMPARABLE"],
        blocked=["interpret_outcome_delta", "create_qualification_evidence"],
        identity={"config_diff_fields": "dataset_digest", "config_diff_count": 1},
    ),
    _s(
        "S21",
        lambda: se.backtest_comparison_envelope(comparison("NO_CLEAR_EVIDENCE"), now=NOW),
        status="DEGRADED",
        codes=["NO_CLEAR_EVIDENCE"],
        allowed=["view_trade_diff", "view_outcome_deltas"],
    ),
    _s(
        "S22",
        lambda: se.backtest_comparison_envelope(comparison("LIKELY_IMPROVED"), now=NOW),
        status="READY",
        advisory=["LIKELY_IMPROVED_NOT_CAUSAL"],
        blocked=["start_local_paper"],
    ),
    _s(
        "S23",
        lambda: se.cost_snapshot_envelope(cost_snapshot(slippage_bps=None), now=NOW),
        status="BLOCKED",
        codes=["MISSING_SLIPPAGE_CALIBRATION"],
        identity={"slippage_bps": None},
    ),
    _s(
        "S23b",
        lambda: se.cost_snapshot_envelope(None, now=NOW),
        status="BLOCKED",
        codes=["COST_POLICY_SNAPSHOT_MISSING"],
    ),
    _s(
        "S24",
        lambda: se.cost_snapshot_envelope(cost_snapshot(), now=NOW),
        status="READY",
        authority="COST_POLICY_SEALED",
        identity={"slippage_bps": "3.5", "snapshot_digest": SHA},
    ),
    _s(
        "S25",
        lambda: se.local_paper_runtime_envelope(controller("STOPPED"), now=NOW),
        status="EMPTY",
        advisory=[
            "EXECUTION_AUTHORITY_LOCAL_ONLY",
            "LOCAL_PAPER_TAX_SLIPPAGE_NOT_SIMULATED",
            "MOBILE_READ_ONLY_MONITOR",
            "STOPPED_IS_NOT_FLAT",
        ],
        allowed=["start_automated_strategy", "check_preflight"],
    ),
    _s(
        "S26",
        lambda: se.local_paper_runtime_envelope(controller("RUNNING"), now=NOW),
        status="RUNNING",
        identity={"run_id": "run-TEST_FIXTURE", "pipeline_snapshot_digest": SHA},
        allowed=["stop_automated_strategy", "view_run"],
    ),
    _s(
        "S28",
        lambda: se.quote_ingress_envelope(session("DEGRADED"), now=NOW),
        status="DEGRADED",
        codes=["STREAM_DEGRADED"],
        allowed=["cancel_order", "view_stream_details"],
        blocked=["submit_order"],
    ),
    _s(
        "S29",
        lambda: se.quote_ingress_envelope(session("BLOCKED"), now=NOW),
        status="CRITICAL",
        codes=["STREAM_BLOCKED"],
        allowed=["cancel_order", "open_stream_events"],
        blocked=["submit_order", "start_automated_strategy"],
        identity={"stream_error": "TEST_FIXTURE ingress blocked"},
    ),
    _s(
        "S30",
        lambda: se.kill_switch_envelope(kill("ENGAGED", 8), now=NOW),
        status="CRITICAL",
        codes=["KILL_SWITCH_ENGAGED"],
        revision=8,
        blocked=["start_automated_strategy"],
    ),
    _s(
        "S31",
        lambda: se.kill_switch_envelope(kill("RECOVERY_REQUIRED"), now=NOW),
        status="CRITICAL",
        codes=["KILL_SWITCH_RECOVERY_REQUIRED"],
        blocked=["start_automated_strategy", "request_kill_switch_reset"],
        identity={"recovery_error": "journal digest mismatch"},
    ),
    _s(
        "S32",
        lambda: se.unavailable_envelope(
            "no_overnight", now=NOW, reason_code="NO_OVERNIGHT_STATUS_UNAVAILABLE"
        ),
        status="UNAVAILABLE",
        codes=["NO_OVERNIGHT_STATUS_UNAVAILABLE"],
        allowed=["reload_status"],
        not_allowed=["acknowledge_breach_by_revision"],
    ),
    _s(
        "S33",
        lambda: se.no_overnight_envelope(no_overnight("NO_NEW_ENTRY"), now=NOW),
        status="DEGRADED",
        codes=["NO_NEW_ENTRY"],
        revision=8,
        blocked=["submit_entry_order"],
    ),
    _s(
        "S33b",
        lambda: se.no_overnight_envelope(no_overnight("NORMAL"), now=NOW),
        status="READY",
        codes=[],
    ),
    _s(
        "S33c",
        lambda: se.no_overnight_envelope(no_overnight("NORMAL", mode="DISABLED"), now=NOW),
        status="EMPTY",
    ),
    _s(
        "S34",
        lambda: se.no_overnight_envelope(no_overnight("CONFIRMED_FLAT"), now=NOW),
        status="READY",
        identity={"flat_proof_mode": "STRICT", "evidence_snapshot_digest": SHA},
    ),
    _s(
        "S35",
        lambda: se.no_overnight_envelope(no_overnight("OVERNIGHT_BREACH"), now=NOW),
        status="CRITICAL",
        codes=["OVERNIGHT_BREACH"],
        allowed=["view_no_overnight_evidence", "acknowledge_breach_by_revision"],
        identity={"breach_latched": True},
    ),
    _s(
        "S35b",
        lambda: se.no_overnight_envelope(
            no_overnight("OVERNIGHT_BREACH", stable_reasons=["IDENTITY_MISMATCH"]), now=NOW
        ),
        status="CRITICAL",
        not_allowed=["acknowledge_breach_by_revision"],
        blocked=["acknowledge_breach_by_revision"],
    ),
]
SCENARIOS += [
    _s(
        sid,
        lambda: se.market_shadow_envelope(now=NOW),
        status="NOT_EVALUATED",
        authority_class="PROPOSED_REQUIRED",
        codes=["SHADOW_READ_MODEL_NOT_WIRED"],
        identity={"execution_enabled": False},
        blocked=["start_shadow_session", "enable_execution"],
        not_allowed=["enable_execution"],
    )
    for sid in ("S36", "S37", "S38", "S39", "S40", "S41", "S42", "S43", "S44")
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[item[0] for item in SCENARIOS])
def test_scenario_matrix(scenario: Scenario) -> None:
    _sid, build, expect = scenario
    envelope = build()
    assert se.validate_status_envelope(envelope) == envelope
    if "status" in expect:
        assert envelope["status"] == expect["status"]
    if "authority" in expect:
        assert envelope["authority_status"] == expect["authority"]
    if "authority_class" in expect:
        assert envelope["authority"] == expect["authority_class"]
    if "codes" in expect:
        assert envelope["reason_codes"] == expect["codes"]
        assert [r["code"] for r in envelope["reasons"]] == expect["codes"]
    if "revision" in expect:
        assert envelope["revision"] == expect["revision"]
    if "advisory" in expect:
        assert [a["code"] for a in envelope["advisory"]] == expect["advisory"]
    if "allowed" in expect:
        assert envelope["allowed_actions"] == expect["allowed"]
    for action in expect.get("blocked", []):
        assert action in {b["action"] for b in envelope["blocked_actions"]}, action
    for action in expect.get("not_allowed", []):
        assert action not in envelope["allowed_actions"], action
    for key, value in expect.get("identity", {}).items():
        assert envelope["identity"][key] == value, key
    # Global floor (task147 §2.3 #1): blocking reasons never render positive.
    if any(r["a11y"] in {"A-BLOCK", "A-CRIT"} for r in envelope["reasons"]):
        assert not positive(envelope)
    # Never a live-trading CTA.
    assert not {"enable_execution", "submit_broker_order", "start_shadow_session"} & set(
        envelope["allowed_actions"]
    )


def test_client_only_scenarios_have_no_server_state() -> None:
    """S01/S04/S27 are client display states (task147 §2.1) and never appear server-side."""

    assert "LOADING" not in se.DISPLAY_STATES and "STALE" not in se.DISPLAY_STATES
    envelope = se.local_paper_runtime_envelope(controller(), now=NOW)
    assert "transport" not in envelope["identity"]


def test_canonical_decimal_vectors_and_signed_json_domain() -> None:
    assert [se.canonical_decimal_string(value) for value in (1.0, -0.0, 1e-7, 42)] == [
        "1",
        "0",
        "0.0000001",
        "42",
    ]
    vector = {
        "z": [None, True, 9_007_199_254_740_991, "中文", "emoji 😀"],
        "a": {"quote": 'a"b', "control": "line\nnext", "slash": "a\\b"},
    }
    canonical = se.canonical_json(vector)
    assert canonical == (
        '{"a":{"control":"line\\nnext","quote":"a\\"b","slash":"a\\\\b"},'
        '"z":[null,true,9007199254740991,"中文","emoji 😀"]}'
    )
    assert se.canonical_json(json.loads(canonical)) == canonical


@pytest.mark.parametrize(
    "value",
    [1.5, -0.0, float("nan"), float("inf"), 9_007_199_254_740_992, "\ud800"],
)
def test_signed_domain_rejects_float_negative_zero_unsafe_and_invalid_unicode(
    value: object,
) -> None:
    with pytest.raises(ValueError):
        se.canonical_json({"value": value})


@pytest.mark.parametrize(
    "build",
    [
        lambda: se.backtest_platform_envelope({"platform": {"ready": True}}, now=NOW),
        lambda: se.backtest_platform_envelope(
            {"platform": {"ready": True, "status": "PLATFORM_NOT_READY"}}, now=NOW
        ),
        lambda: se.formal_dataset_envelope(
            readiness(data=True),
            now=NOW,
            selected_dataset={**dataset_binding([]), "dataset_id": ""},
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        lambda: se.formal_dataset_envelope(
            readiness(data=True),
            now=NOW,
            selected_dataset={**dataset_binding([]), "manifest_digest": "A" * 64},
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        lambda: se.formal_dataset_envelope(
            readiness(data=True),
            now=NOW,
            selected_dataset={
                **dataset_binding([]),
                "formal_research_readiness": {
                    "ready": True,
                    "status": "DATA_READY",
                    "reason_codes": [],
                    "research_truth_snapshot_digest": None,
                },
            },
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        lambda: se.formal_dataset_envelope(
            readiness(data=True), now=NOW, selected_dataset=dataset_binding([])
        ),
        lambda: se.strategy_qualification_envelope(readiness(strategy_ids=["q", "q"]), now=NOW),
        lambda: se.strategy_qualification_envelope(readiness(strategy_ids=[""]), now=NOW),
        lambda: se.local_paper_runtime_envelope(controller("RUNNING", run_id=""), now=NOW),
        lambda: se.local_paper_runtime_envelope(controller("RUNNING", pipeline=None), now=NOW),
        lambda: se.local_paper_runtime_envelope(
            controller("RUNNING", pipeline={"snapshot_digest": "bad"}), now=NOW
        ),
        lambda: se.quote_ingress_envelope({**session(), "stream_health": None}, now=NOW),
        lambda: se.kill_switch_envelope({**kill(), "engaged": True}, now=NOW),
        lambda: se.kill_switch_envelope({**kill(), "revision": -1}, now=NOW),
        lambda: se.no_overnight_envelope(
            {
                **no_overnight("CONFIRMED_FLAT"),
                "status": {
                    **no_overnight("CONFIRMED_FLAT")["status"],
                    "flat_proof_mode": "",
                },
            },
            now=NOW,
        ),
        lambda: se.no_overnight_envelope(
            {
                **no_overnight("CONFIRMED_FLAT"),
                "status": {
                    **no_overnight("CONFIRMED_FLAT")["status"],
                    "evidence_snapshot_digest": "bad",
                },
            },
            now=NOW,
        ),
        lambda: se.backtest_run_envelope(run("RUNNING", run_id=""), now=NOW),
        lambda: se.backtest_run_envelope(run("COMPLETED", dataset_id=None), now=NOW),
        lambda: se.backtest_run_envelope(run("COMPLETED", config_digest=""), now=NOW),
        lambda: se.backtest_run_envelope(run("COMPLETED", result_digest="A" * 64), now=NOW),
        lambda: se.cost_snapshot_envelope(cost_snapshot(snapshot_digest="bad"), now=NOW),
        lambda: se.backtest_comparison_envelope(
            {**comparison("LIKELY_IMPROVED"), "comparison_id": ""}, now=NOW
        ),
        lambda: se.backtest_comparison_envelope(
            {**comparison("LIKELY_IMPROVED"), "comparison_digest": None}, now=NOW
        ),
        lambda: se.backtest_comparison_envelope(
            {**comparison("LIKELY_IMPROVED"), "comparable": False}, now=NOW
        ),
    ],
)
def test_positive_provenance_invariants_fail_closed(build: Any) -> None:
    with pytest.raises((ValueError, TypeError, KeyError)):
        build()


# --------------------------------------------------------------------------- inconsistency guards
@pytest.mark.parametrize(
    "build",
    [
        lambda: se.formal_dataset_envelope(
            readiness(data=True),
            now=NOW,
            selected_dataset={
                **dataset_binding([]),
                "formal_research_readiness": {
                    "ready": True,
                    "status": "DATA_READY",
                    "reason_codes": ["HALT"],
                    "research_truth_snapshot_digest": SHA,
                },
            },
            strategy_set_version_id="set-TEST_FIXTURE",
        ),
        lambda: se.formal_dataset_envelope(
            {"data": {"ready": True, "status": "DATA_NOT_READY"}}, now=NOW
        ),
        lambda: se.strategy_qualification_envelope(
            {
                "strategy": {
                    "ready": True,
                    "status": "STRATEGY_QUALIFIED",
                    "qualification_ids": [],
                    "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
                }
            },
            now=NOW,
        ),
        lambda: se.strategy_qualification_envelope(
            {
                "strategy": {
                    "ready": True,
                    "status": "STRATEGY_QUALIFIED",
                    "qualification_ids": ["q"],
                    "effect": "AUTO_PROMOTE",
                }
            },
            now=NOW,
        ),
        lambda: se.local_paper_runtime_envelope(controller(execution_authority=True), now=NOW),
        lambda: se.local_paper_runtime_envelope(controller("LIVE"), now=NOW),
        lambda: se.quote_ingress_envelope(session("GREEN"), now=NOW),
        lambda: se.kill_switch_envelope({**kill("ENGAGED"), "engaged": False}, now=NOW),
        lambda: se.kill_switch_envelope({**kill(), "execution_boundary": "BROKER"}, now=NOW),
        lambda: se.no_overnight_envelope({**no_overnight(), "schema_version": "x"}, now=NOW),
        lambda: se.no_overnight_envelope(no_overnight("PARTY"), now=NOW),
        lambda: se.backtest_run_envelope(run("COMPLETED", result_digest=None), now=NOW),
        lambda: se.backtest_run_envelope(run("DONE"), now=NOW),
        lambda: se.backtest_run_envelope(run("RUNNING", progress=True), now=NOW),
        lambda: se.backtest_comparison_envelope(
            {**comparison("NOT_COMPARABLE"), "comparable": True}, now=NOW
        ),
        lambda: se.backtest_comparison_envelope(comparison("NOT_COMPARABLE", []), now=NOW),
        lambda: se.cost_snapshot_envelope({"slippage_bps": "1"}, now=NOW),
    ],
)
def test_inconsistent_authority_projection_raises_instead_of_guessing(build: Any) -> None:
    with pytest.raises((ValueError, TypeError, KeyError)):
        build()
