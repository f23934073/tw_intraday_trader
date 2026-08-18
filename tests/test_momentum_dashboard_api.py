from __future__ import annotations

import pytest
from fastapi import HTTPException

import dashboard.server as server


def reset_momentum_service(monkeypatch) -> None:
    monkeypatch.setattr(server, "_momentum_service", None)


def test_momentum_snapshot_does_not_build_runtime_composition(monkeypatch):
    reset_momentum_service(monkeypatch)

    def fail_if_called():
        raise AssertionError("Momentum local read must not build Provider runtime")

    monkeypatch.setattr(server, "get_runtime_composition", fail_if_called)

    snapshot = server.momentum_dashboard_snapshot()

    assert snapshot["source"]["is_live"] is False
    assert snapshot["items"][0]["current_stage"] == "ACCELERATING"


def test_momentum_ack_route_updates_server_owned_projection(monkeypatch):
    reset_momentum_service(monkeypatch)
    initial = server.momentum_dashboard_snapshot()
    alert_id = initial["alerts"][0]["alert_id"]

    acknowledged = server.acknowledge_momentum_alert(alert_id)
    reread = server.momentum_dashboard_snapshot()

    assert acknowledged["summary"]["pending_alert_count"] == 1
    assert reread["summary"]["pending_alert_count"] == 1
    assert reread["alerts"][0]["acknowledged_at"] is not None


def test_momentum_symbol_and_alert_routes_return_404_for_unknown(monkeypatch):
    reset_momentum_service(monkeypatch)

    with pytest.raises(HTTPException) as symbol_error:
        server.momentum_symbol_projection("2330")
    with pytest.raises(HTTPException) as alert_error:
        server.acknowledge_momentum_alert("missing-alert")

    assert symbol_error.value.status_code == 404
    assert alert_error.value.status_code == 404
