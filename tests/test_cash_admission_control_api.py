from __future__ import annotations

from fastapi.testclient import TestClient

from backtest.research_control import CashAdmissionControlNotAccepted
from dashboard import server


class _R5BacktestProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_cash_admission_control(self, **values):
        self.calls.append(dict(values))
        return (
            {
                "run_id": "run-r5-control",
                "config_digest": "a" * 64,
                "status": "QUEUED",
            },
            len(self.calls) > 1,
        )

    def summary(self, run_id: str):
        raise CashAdmissionControlNotAccepted(
            "R5_CONTROL_POSTFLIGHT_NOT_ACCEPTED"
        )


def test_r5_control_api_is_strict_csrf_protected_and_header_idempotent(
    monkeypatch,
) -> None:
    probe = _R5BacktestProbe()
    monkeypatch.setattr(server, "get_backtest_service", lambda: probe)
    monkeypatch.setattr(server, "_record_atomic_audit", lambda **values: None)
    client = TestClient(server.app)
    payload = {
        "request_schema_version": "cash-admission-control-request-v1",
        "control_contract_version": "cash-admission-control-v1",
        "preflight_digest": "b" * 64,
        "expected_registration_revision": 0,
        "actor_id": "reviewer",
        "change_note": "sealed R5 control",
    }

    no_csrf = client.post(
        "/api/backtests/runs/baseline-1/cash-admission-controls",
        headers={"Idempotency-Key": "r5-web-1"},
        json=payload,
    )
    assert no_csrf.status_code == 403

    unknown_sizing = client.post(
        "/api/backtests/runs/baseline-1/cash-admission-controls",
        headers={
            "Idempotency-Key": "r5-web-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={**payload, "starting_cash": "1", "position_fraction": "1"},
    )
    assert unknown_sizing.status_code == 422
    assert probe.calls == []

    created = client.post(
        "/api/backtests/runs/baseline-1/cash-admission-controls",
        headers={
            "Idempotency-Key": "r5-web-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json=payload,
    )
    assert created.status_code == 201
    assert created.json()["run"]["run_id"] == "run-r5-control"
    assert probe.calls[0]["baseline_run_id"] == "baseline-1"
    assert probe.calls[0]["idempotency_key"] == "r5-web-1"
    assert "starting_cash" not in probe.calls[0]
    assert "position_fraction" not in probe.calls[0]

    replay = client.post(
        "/api/backtests/runs/baseline-1/cash-admission-controls",
        headers={
            "Idempotency-Key": "r5-web-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True


def test_r5_performance_route_returns_conflict_before_postflight(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_backtest_service", lambda: _R5BacktestProbe())
    client = TestClient(server.app)

    response = client.get("/api/backtests/runs/run-r5-control/summary")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "R5_CONTROL_POSTFLIGHT_NOT_ACCEPTED"
