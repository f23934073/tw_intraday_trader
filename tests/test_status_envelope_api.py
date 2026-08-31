"""Route contracts for the server-owned StatusEnvelope set (task170 R1)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import dashboard.server as server
from dashboard import status_envelope as se
from market_data.provider import MockProvider
from tests.test_status_envelope import FORMAL_17, SHA, comparison, dataset_binding, readiness, run


class FakeBacktestService:
    """Read-only stand-in for BacktestApplicationService; records every call."""

    def __init__(self, *, codes: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self.codes = codes if codes is not None else list(FORMAL_17)
        self.runs: dict[str, dict[str, Any]] = {}
        self.comparisons: dict[str, dict[str, Any]] = {}

    def capabilities(self) -> dict[str, Any]:
        self.calls.append("capabilities")
        return {"enabled": True, "readiness": readiness()}

    def atomic_backtest_dataset_status(
        self, *, strategy_set_version_id: str, baseline_run_id: Any
    ) -> dict[str, Any]:
        self.calls.append(f"atomic:{strategy_set_version_id}:{baseline_run_id}")
        return dataset_binding(self.codes)

    def get_run(self, run_id: str) -> dict[str, Any]:
        self.calls.append(f"get_run:{run_id}")
        if run_id not in self.runs:
            raise KeyError(run_id)
        return self.runs[run_id]

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        self.calls.append(f"get_comparison:{comparison_id}")
        if comparison_id not in self.comparisons:
            raise KeyError(comparison_id)
        return self.comparisons[comparison_id]

    def __getattr__(self, name: str) -> Any:  # any other (mutating) call is a contract breach
        raise AssertionError(f"unexpected backtest service call: {name}")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeBacktestService]:
    fake = FakeBacktestService()
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(server, "_backtest_service", fake)
    return TestClient(server.app), fake


def test_status_envelope_set_is_exact_server_owned_and_read_only(client) -> None:
    http, fake = client
    response = http.get("/api/dashboard/status-envelopes")
    assert response.status_code == 200
    payload = response.json()
    assert se.validate_status_envelope_set(payload) == payload
    envelopes = payload["envelopes"]
    assert list(envelopes) == list(se.SUBJECTS)
    assert envelopes["formal_dataset"]["status"] == "BLOCKED"
    assert envelopes["formal_dataset"]["reason_codes"] == ["REASON_CODES_REQUIRE_DATASET_SCOPE"]
    assert [a["code"] for a in envelopes["formal_dataset"]["advisory"]] == [
        "REASON_CODES_REQUIRE_DATASET_SCOPE"
    ]
    assert envelopes["local_paper_runtime"]["status"] == "EMPTY"
    assert envelopes["local_paper_runtime"]["authority_status"] == "STOPPED"
    local_paper = envelopes["local_paper_runtime"]
    assert [item["code"] for item in local_paper["advisory"]][:3] == [
        "EXECUTION_AUTHORITY_LOCAL_ONLY",
        "LOCAL_PAPER_TAX_SLIPPAGE_NOT_SIMULATED",
        "MOBILE_READ_ONLY_MONITOR",
    ]
    assert local_paper["client_policy"] == se.MOBILE_READ_ONLY_POLICY
    assert envelopes["kill_switch"]["authority_status"] == "DISENGAGED"
    assert envelopes["market_shadow"]["status"] == "NOT_EVALUATED"
    assert envelopes["market_shadow"]["authority"] == "PROPOSED_REQUIRED"
    for envelope in envelopes.values():
        assert "enable_execution" not in envelope["allowed_actions"]
    assert fake.calls == ["capabilities"], "readiness is read once and no mutation is issued"
    assert http.post("/api/dashboard/status-envelopes").status_code == 405


def test_selected_dataset_scope_projects_exact_reason_codes(client) -> None:
    http, fake = client
    payload = http.get(
        "/api/dashboard/status-envelopes", params={"strategy_set_version_id": "set-TEST_FIXTURE"}
    ).json()
    formal = payload["envelopes"]["formal_dataset"]
    assert formal["reason_codes"] == FORMAL_17
    assert all(reason["known"] for reason in formal["reasons"])
    assert formal["identity"]["research_truth_snapshot_digest"] == SHA
    assert formal["advisory"] == []
    assert "atomic:set-TEST_FIXTURE:None" in fake.calls


def test_source_failure_is_unavailable_never_zero_or_ready(client, monkeypatch) -> None:
    http, _fake = client
    composition = server.get_runtime_composition()

    def boom() -> dict[str, Any]:
        raise RuntimeError("kill switch projection unavailable")

    monkeypatch.setattr(composition.kill_switch, "status", boom)
    response = http.get("/api/dashboard/status-envelopes")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "STATUS_ENVELOPE_UNAVAILABLE"


def test_no_overnight_503_maps_to_its_typed_reason_code(client, monkeypatch) -> None:
    http, _fake = client

    def unavailable() -> dict[str, Any]:
        raise server._no_overnight_status_unavailable("status envelope is invalid")

    monkeypatch.setattr(server, "_no_overnight_dashboard_payload", unavailable)
    response = http.get("/api/dashboard/status-envelopes")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "STATUS_ENVELOPE_UNAVAILABLE"


def test_invalid_set_is_503_with_typed_code(client, monkeypatch) -> None:
    http, _fake = client

    def invalid(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise se.StatusEnvelopeInvalid("envelope keys are not exact")

    monkeypatch.setattr(server, "build_status_envelope_set", invalid)
    response = http.get("/api/dashboard/status-envelopes")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "STATUS_ENVELOPE_UNAVAILABLE"


def test_status_envelopes_reject_proxy_forwarding_headers(client) -> None:
    http, _fake = client
    response = http.get(
        "/api/dashboard/status-envelopes", headers={"X-Forwarded-For": "203.0.113.9"}
    )
    assert response.status_code == 403


def test_backtest_run_and_comparison_entity_routes(client) -> None:
    http, fake = client
    fake.runs["run-1"] = run("FAILED", run_id="run-1", error_message="engine exploded")
    fake.runs["run-2"] = run(
        "COMPLETED",
        run_id="run-2",
        config={"cost_policy_snapshot": {"slippage_bps": None, "snapshot_digest": SHA}},
    )
    fake.comparisons["cmp-1"] = {
        **comparison("NOT_COMPARABLE", [{"field": "cost_snapshot"}]),
        "comparison_id": "cmp-1",
    }

    failed = http.get("/api/dashboard/status-envelopes/backtest-runs/run-1").json()
    assert list(failed["envelopes"]) == ["backtest_run", "cost_snapshot"]
    assert failed["envelopes"]["backtest_run"]["status"] == "TERMINAL_FAILED"
    assert failed["envelopes"]["backtest_run"]["identity"]["error_message"] == "engine exploded"
    assert failed["envelopes"]["cost_snapshot"]["reason_codes"] == ["COST_POLICY_SNAPSHOT_MISSING"]

    completed = http.get("/api/dashboard/status-envelopes/backtest-runs/run-2").json()
    assert completed["envelopes"]["backtest_run"]["status"] == "TERMINAL_SUCCESS"
    assert completed["envelopes"]["cost_snapshot"]["reason_codes"] == [
        "MISSING_SLIPPAGE_CALIBRATION"
    ]
    assert completed["envelopes"]["cost_snapshot"]["identity"]["slippage_bps"] is None

    compared = http.get("/api/dashboard/status-envelopes/backtest-comparisons/cmp-1").json()
    assert compared["envelopes"]["backtest_comparison"]["status"] == "BLOCKED"
    assert (
        compared["envelopes"]["backtest_comparison"]["identity"]["config_diff_fields"]
        == "cost_snapshot"
    )

    missing = http.get("/api/dashboard/status-envelopes/backtest-runs/run-404")
    assert missing.status_code >= 400


def test_entity_routes_reject_authority_identity_mismatch(client) -> None:
    http, fake = client
    fake.runs["route-run"] = run("RUNNING", run_id="different-run")
    fake.comparisons["route-comparison"] = comparison("NO_CLEAR_EVIDENCE")

    run_response = http.get("/api/dashboard/status-envelopes/backtest-runs/route-run")
    comparison_response = http.get(
        "/api/dashboard/status-envelopes/backtest-comparisons/route-comparison"
    )

    assert run_response.status_code == 503
    assert comparison_response.status_code == 503
    assert run_response.json()["detail"]["code"] == "STATUS_ENVELOPE_UNAVAILABLE"
    assert comparison_response.json()["detail"]["code"] == "STATUS_ENVELOPE_UNAVAILABLE"
