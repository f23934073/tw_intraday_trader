from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from fastapi.testclient import TestClient

import dashboard.server as server
from runtime.no_overnight import NoOvernightBreachConflict


class BreachControllerProbe:
    config = SimpleNamespace(timezone="Asia/Taipei")

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.conflict: str | None = None

    def status(self) -> dict[str, object]:
        return {
            "mode": "ENFORCING",
            "enforcing": True,
            "state": "NORMAL",
            "breach": {
                "schema_version": "no_overnight_breach_status_v1",
                "breach_id": "breach-1",
                "open": True,
                "breach_revision": 2,
                "reconciliation_digest": "e" * 64,
                "resolved": True,
                "acknowledged": False,
            },
        }

    def acknowledge_breach(self, **kwargs) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        if self.conflict is not None:
            raise NoOvernightBreachConflict(self.conflict, "stale breach evidence")
        return {
            **self.status()["breach"],
            "acknowledged": True,
            "acknowledged_by": kwargs["actor_id"],
            "idempotent": False,
        }


class FixedClock:
    def now(self) -> datetime:
        return datetime.fromisoformat("2026-08-25T09:06:00+08:00")


def _composition(controller: BreachControllerProbe) -> SimpleNamespace:
    return SimpleNamespace(
        no_overnight_controller=controller,
        clock=FixedClock(),
    )


def test_breach_acknowledgement_requires_local_csrf_and_strict_body(
    monkeypatch,
) -> None:
    controller = BreachControllerProbe()
    monkeypatch.setattr(
        server,
        "get_runtime_composition",
        lambda: _composition(controller),
    )
    client = TestClient(server.app)
    payload = {
        "breach_revision": 2,
        "reconciliation_digest": "e" * 64,
        "actor_id": "local-operator",
    }

    missing_csrf = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={"Idempotency-Key": "breach-api-ack-1"},
        json=payload,
    )
    hostile_origin = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
            "Origin": "https://evil.example",
        },
        json=payload,
    )
    unknown_field = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={**payload, "clear_breach": True},
    )
    missing_idempotency = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={"X-Strategy-CSRF": server._atomic_strategy_csrf_token},
        json=payload,
    )
    bool_revision = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={**payload, "breach_revision": True},
    )
    uppercase_digest = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={**payload, "reconciliation_digest": "E" * 64},
    )
    whitespace_actor = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={**payload, "actor_id": "   "},
    )
    accepted = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-ack-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json=payload,
    )

    assert missing_csrf.status_code == 403
    assert hostile_origin.status_code == 403
    assert unknown_field.status_code == 422
    assert missing_idempotency.status_code == 422
    assert bool_revision.status_code == 422
    assert uppercase_digest.status_code == 422
    assert whitespace_actor.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["breach"]["acknowledged"] is True
    assert controller.calls[0]["breach_id"] == "breach-1"
    assert controller.calls[0]["breach_revision"] == 2
    assert controller.calls[0]["reconciliation_digest"] == "e" * 64
    assert controller.calls[0]["actor_id"] == "local-operator"
    assert controller.calls[0]["idempotency_key"] == "breach-api-ack-1"


def test_stale_breach_ack_returns_409_without_retrying_controller(monkeypatch) -> None:
    controller = BreachControllerProbe()
    controller.conflict = "STALE_BREACH_REVISION"
    monkeypatch.setattr(
        server,
        "get_runtime_composition",
        lambda: _composition(controller),
    )
    client = TestClient(server.app)

    response = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/acknowledge",
        headers={
            "Idempotency-Key": "breach-api-stale-1",
            "X-Strategy-CSRF": server._atomic_strategy_csrf_token,
        },
        json={
            "breach_revision": 1,
            "reconciliation_digest": "d" * 64,
            "actor_id": "local-operator",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_BREACH_REVISION"
    assert len(controller.calls) == 1


def test_no_clear_breach_route_exists(monkeypatch) -> None:
    controller = BreachControllerProbe()
    monkeypatch.setattr(
        server,
        "get_runtime_composition",
        lambda: _composition(controller),
    )
    client = TestClient(server.app)

    response = client.post(
        "/api/simulation/no-overnight/breaches/breach-1/clear",
        headers={"X-Strategy-CSRF": server._atomic_strategy_csrf_token},
        json={},
    )

    assert response.status_code == 404
    assert controller.calls == []
