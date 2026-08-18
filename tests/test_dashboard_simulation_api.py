"""Focused tests for the dashboard's local paper-simulation route contracts."""

from fastapi import Response

import dashboard.server as server
from market_data.provider import MockProvider


def test_dashboard_snapshot_contains_session_local_simulation_projection(monkeypatch):
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    snapshot = server.dashboard_snapshot()

    assert snapshot["simulation"]["session"]["mode"] == "LOCAL_PAPER_SIMULATION"
    assert snapshot["simulation"]["orders"] == []
    assert snapshot["simulation"]["positions"] == []


def test_submit_simulation_order_route_returns_local_filled_order(monkeypatch):
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    response = Response()

    payload = server.submit_simulation_order(
        server.SimulationOrderRequest(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price=106.0,
            idempotency_key="route-buy",
        ),
        response,
    )

    assert payload["idempotent"] is False
    assert payload["order"]["status"] == "FILLED"
    assert server.simulation_positions()["positions"][0]["symbol"] == "3231"


def test_simulation_projection_route_returns_one_local_read_model(monkeypatch):
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    projection = server.simulation_projection()

    assert projection["session"]["quote_mode"] == "SNAPSHOT"
    assert projection["orders"] == []
    assert projection["positions"] == []
