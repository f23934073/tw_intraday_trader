from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import dashboard.server as server
from dashboard.momentum import UnavailableMomentumDashboardService


class FakeMomentumService:
    def __init__(self) -> None:
        self._acknowledged = False

    def snapshot(self) -> dict:
        return {
            "status": "live",
            "source": {"is_live": True},
            "summary": {"pending_alert_count": 0 if self._acknowledged else 1},
            "items": [{"symbol": "8039"}],
            "alerts": [] if self._acknowledged else [{"alert_id": "alert-1"}],
        }

    def acknowledge(self, alert_id: str) -> dict:
        if alert_id != "alert-1":
            raise KeyError(alert_id)
        self._acknowledged = True
        return self.snapshot()

    def symbol(self, symbol: str) -> dict:
        if symbol.strip() != "8039":
            raise KeyError(symbol)
        return {"symbol": "8039"}

    def close(self) -> None:
        return None


class FakeWebSocket:
    def __init__(self, *, origin: str | None = None) -> None:
        self.headers = {"host": "testserver"}
        if origin is not None:
            self.headers["origin"] = origin
        self.accepted = False
        self.sent: list[dict] = []
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.close_code = code


@pytest.fixture(autouse=True)
def isolate_momentum_stream_hub(monkeypatch):
    current = getattr(server, "_momentum_stream_hub", None)
    if current is not None:
        current.close()
    monkeypatch.setattr(server, "_momentum_stream_hub", None, raising=False)
    yield
    current = getattr(server, "_momentum_stream_hub", None)
    if current is not None:
        current.close()


def test_momentum_snapshot_reports_unavailable_without_building_provider(monkeypatch):
    monkeypatch.setattr(
        server,
        "_momentum_service",
        UnavailableMomentumDashboardService("credentials unavailable"),
    )

    def fail_if_called():
        raise AssertionError("unavailable Momentum must not build Provider runtime")

    monkeypatch.setattr(server, "get_runtime_composition", fail_if_called)

    snapshot = server.momentum_dashboard_snapshot()

    assert snapshot["status"] == "unavailable"
    assert snapshot["source"]["is_live"] is False
    assert snapshot["items"] == []
    assert snapshot["stream"]["enabled"] is True


def test_momentum_api_routes_use_server_owned_live_projection(monkeypatch):
    service = FakeMomentumService()
    monkeypatch.setattr(server, "_momentum_service", service)
    initial = server.momentum_dashboard_snapshot()

    acknowledged = server.acknowledge_momentum_alert("alert-1")
    reread = server.momentum_dashboard_snapshot()

    assert initial["source"]["is_live"] is True
    assert initial["stream"]["revision"] == 1
    assert acknowledged["summary"]["pending_alert_count"] == 0
    assert acknowledged["stream"]["revision"] == 2
    assert reread["summary"]["pending_alert_count"] == 0
    assert server.momentum_symbol_projection("8039") == {"symbol": "8039"}


def test_momentum_symbol_and_alert_routes_return_404_for_unknown(monkeypatch):
    monkeypatch.setattr(server, "_momentum_service", FakeMomentumService())

    with pytest.raises(HTTPException) as symbol_error:
        server.momentum_symbol_projection("2330")
    with pytest.raises(HTTPException) as alert_error:
        server.acknowledge_momentum_alert("missing-alert")

    assert symbol_error.value.status_code == 404
    assert alert_error.value.status_code == 404


def test_momentum_websocket_rejects_stale_process_cursor(monkeypatch):
    monkeypatch.setattr(server, "_momentum_service", FakeMomentumService())
    snapshot = server.momentum_dashboard_snapshot()
    websocket = FakeWebSocket(origin="http://testserver")

    asyncio.run(
        server.momentum_dashboard_stream(
            websocket,
            stream_id="previous-process",
            since_revision=snapshot["stream"]["revision"],
        )
    )

    assert websocket.accepted is True
    assert websocket.sent[0]["type"] == "resync_required"
    assert websocket.sent[0]["reason"] == "STREAM_CHANGED"
    assert websocket.close_code == 1012


def test_momentum_websocket_rejects_cross_origin_before_accept(monkeypatch):
    monkeypatch.setattr(server, "_momentum_service", FakeMomentumService())
    websocket = FakeWebSocket(origin="https://outside.example")

    asyncio.run(
        server.momentum_dashboard_stream(
            websocket,
            stream_id="unused",
            since_revision=0,
        )
    )

    assert websocket.accepted is False
    assert websocket.sent == []
    assert websocket.close_code == 1008


def test_momentum_feature_flag_falls_back_to_http_without_starting_hub(monkeypatch):
    monkeypatch.setattr(server, "_momentum_service", FakeMomentumService())
    monkeypatch.setattr(
        server,
        "MOMENTUM_STREAM_CONFIG",
        replace(server.MOMENTUM_STREAM_CONFIG, enabled=False),
    )
    websocket = FakeWebSocket(origin="http://testserver")

    snapshot = server.momentum_dashboard_snapshot()
    asyncio.run(
        server.momentum_dashboard_stream(
            websocket,
            stream_id="unused",
            since_revision=0,
        )
    )

    assert snapshot["stream"]["enabled"] is False
    assert server._momentum_stream_hub is None
    assert websocket.accepted is False
    assert websocket.close_code == 1008


def test_momentum_websocket_transport_upgrades_and_sends_ready(monkeypatch):
    service = FakeMomentumService()
    monkeypatch.setattr(server, "_momentum_service", service)
    monkeypatch.setattr(
        server,
        "MOMENTUM_STREAM_CONFIG",
        replace(server.MOMENTUM_STREAM_CONFIG, heartbeat_seconds=0.05),
    )
    client = TestClient(server.app)
    try:
        snapshot = client.get("/api/dashboard/momentum").json()
        stream = snapshot["stream"]
        service._acknowledged = True
        assert server.get_momentum_stream_hub().capture_now() is True
        with client.websocket_connect(
            "/ws/dashboard/momentum"
            f"?stream_id={stream['stream_id']}"
            f"&since_revision={stream['revision']}",
            headers={"origin": "http://testserver"},
        ) as websocket:
            ready = websocket.receive_json()
            delta = websocket.receive_json()

        assert ready == {
            "schema_version": "momentum_dashboard_stream_v1",
            "type": "ready",
            "stream_id": stream["stream_id"],
            "current_revision": stream["revision"] + 1,
            "heartbeat_seconds": 0.05,
        }
        assert delta["type"] == "delta"
        assert delta["base_revision"] == stream["revision"]
        assert delta["revision"] == stream["revision"] + 1
    finally:
        client.close()
