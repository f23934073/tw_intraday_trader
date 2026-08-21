"""Focused tests for the dashboard's local paper-simulation route contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier, Lock
from time import sleep
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import Response
from fastapi.testclient import TestClient

import dashboard.server as server
from dashboard.service import DashboardService
from market_data.provider import MarketDataUsage, MockProvider
from simulation.continuous_strategy import AutomatedStrategyConfig


class FakeChangingSimulationProjection:
    def __init__(self) -> None:
        self.current_price = 105.5

    def projection(self) -> dict:
        return {
            "session": {"mode": "LOCAL_PAPER_SIMULATION"},
            "orders": [],
            "positions": [
                {
                    "symbol": "3231",
                    "current_price": self.current_price,
                    "bid_price": self.current_price - 0.5,
                    "ask_price": self.current_price + 0.5,
                    "unrealized_pnl": (self.current_price - 105.5) * 1_000,
                }
            ],
        }


class CountingStreamingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self._stream_lock = Lock()
        self._handler = None
        self.start_calls = 0

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        with self._stream_lock:
            self.start_calls += 1
            if self._handler is not None and self._handler is not handler:
                raise RuntimeError("stream handler already registered")
            self._handler = handler
        sleep(0.05)

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        with self._stream_lock:
            self._handler = None


class FakeAutomatedStrategyController:
    def __init__(self) -> None:
        self.received: AutomatedStrategyConfig | None = None
        self.stopped = False

    def start(self, config: AutomatedStrategyConfig) -> dict:
        self.received = config
        return {"state": "RUNNING", "decision": "STARTED"}

    def stop(self) -> dict:
        self.stopped = True
        return {"state": "STOPPED", "decision": "STOPPED"}

    def status(self) -> dict:
        return {"state": "RUNNING", "decision": "WAITING_SIGNAL"}


class ExhaustedUsageProvider(MockProvider):
    def market_data_usage(self) -> MarketDataUsage:
        return MarketDataUsage(
            connections=1,
            bytes_used=529_961_576,
            limit_bytes=524_288_000,
            remaining_bytes=-5_673_576,
        )


def test_dashboard_snapshot_contains_session_local_simulation_projection(monkeypatch):
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    snapshot = server.dashboard_snapshot()

    assert snapshot["premarket_context"]["status"] in {
        "READY",
        "PENDING",
        "NOT_APPLICABLE",
        "DEGRADED",
        "UNAVAILABLE",
    }
    assert snapshot["simulation"]["session"]["mode"] == "LOCAL_PAPER_SIMULATION"
    assert snapshot["simulation"]["orders"] == []
    assert snapshot["simulation"]["positions"] == []


def test_provider_usage_route_exposes_exhausted_allowance(monkeypatch) -> None:
    service = DashboardService(ExhaustedUsageProvider())
    monkeypatch.setattr(server, "get_dashboard_service", lambda: service)

    payload = server.provider_usage_status()

    assert payload["provider"] == "ExhaustedUsageProvider"
    assert payload["supported"] is True
    assert payload["exhausted"] is True
    assert payload["remaining_bytes"] == -5_673_576


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


def test_cancelled_simulation_order_route_can_create_bounded_retry(monkeypatch):
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    submitted = server.submit_simulation_order(
        server.SimulationOrderRequest(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price=100.0,
            idempotency_key="route-retry-source",
        ),
        Response(),
    )["order"]
    cancelled = server.cancel_simulation_order(
        submitted["order_id"],
        server.SimulationCancelRequest(idempotency_key="route-retry-cancel"),
        Response(),
    )["order"]
    retried = server.retry_simulation_order(
        submitted["order_id"],
        server.SimulationRetryRequest(idempotency_key="route-retry-successor"),
        Response(),
    )["order"]

    assert submitted["status"] == "PENDING"
    assert cancelled["status"] == "CANCELLED"
    assert retried["status"] == "PENDING"
    assert retried["attempt"] == 2
    assert retried["predecessor_order_id"] == submitted["order_id"]


def test_simulation_projection_route_returns_one_local_read_model(monkeypatch):
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    projection = server.simulation_projection()

    assert projection["session"]["quote_mode"] == "SNAPSHOT"
    assert projection["orders"] == []
    assert projection["positions"] == []


def test_runtime_composition_is_constructed_once_under_concurrent_first_access(
    monkeypatch,
):
    provider = CountingStreamingProvider()
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", provider)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    with ThreadPoolExecutor(max_workers=8) as executor:
        compositions = list(
            executor.map(lambda _: server.get_runtime_composition(), range(8))
        )

    try:
        assert all(item is compositions[0] for item in compositions)
        assert provider.start_calls == 1
        assert compositions[0].simulation_service.session()["streaming"] is True
    finally:
        compositions[0].close()


def test_automated_controller_is_constructed_once_under_concurrent_first_access(
    monkeypatch,
) -> None:
    start = Barrier(2)
    constructed: list[object] = []
    composition = SimpleNamespace(strategy_paper_flow=object(), clock=object())
    simulation = SimpleNamespace(projection=lambda: {})
    momentum = SimpleNamespace(snapshot=lambda: {})

    def build_controller(**_kwargs):
        instance = object()
        constructed.append(instance)
        sleep(0.05)
        return instance

    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(server, "get_runtime_composition", lambda: composition)
    monkeypatch.setattr(server, "get_simulation_service", lambda: simulation)
    monkeypatch.setattr(server, "get_momentum_dashboard_service", lambda: momentum)
    monkeypatch.setattr(server, "ContinuousPaperStrategyController", build_controller)

    def first_access():
        start.wait()
        return server.get_automated_strategy_controller()

    with ThreadPoolExecutor(max_workers=2) as executor:
        controllers = list(executor.map(lambda _: first_access(), range(2)))

    assert len(constructed) == 1
    assert controllers[0] is controllers[1]


def test_simulation_websocket_pushes_changed_position_projection(monkeypatch):
    service = FakeChangingSimulationProjection()
    monkeypatch.setattr(server, "get_simulation_service", lambda: service)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )
    monkeypatch.setattr(server, "SIMULATION_STREAM_SAMPLE_SECONDS", 0.01)
    monkeypatch.setattr(server, "SIMULATION_STREAM_HEARTBEAT_SECONDS", 0.05)

    with TestClient(server.app) as client:
        with client.websocket_connect(
            server.SIMULATION_STREAM_PATH,
            headers={"origin": "http://testserver"},
        ) as websocket:
            initial = websocket.receive_json()
            service.current_price = 106.0
            updated = websocket.receive_json()

    assert initial["schema_version"] == "simulation_projection_stream_v1"
    assert initial["type"] == "simulation_projection"
    assert initial["revision"] == 1
    assert initial["projection"]["positions"][0]["current_price"] == 105.5
    assert updated["type"] == "simulation_projection"
    assert updated["revision"] == 2
    assert updated["projection"]["positions"][0]["current_price"] == 106.0
    assert updated["projection"]["positions"][0]["unrealized_pnl"] == 500.0


def test_health_routes_report_local_simulation_without_account_access(monkeypatch):
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    response = Response()

    liveness = server.healthz()
    readiness = server.readyz(response)

    assert liveness == {
        "status": "ok",
        "mode": "LOCAL_PAPER_SIMULATION",
        "stream_health": "HEALTHY",
    }
    assert response.status_code == 200
    assert readiness["status"] == "ready"
    assert readiness["quote_queue_capacity"] == 1_024


def test_strategy_intent_route_completes_a_local_paper_round_trip(monkeypatch):
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    buy = server.submit_simulation_strategy_intent(
        server.SimulationStrategyIntentRequest(
            intent_id="api-orb-entry-3231",
            strategy_id="opening_range_breakout",
            strategy_version="opening_range_breakout_entry_v1",
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            signaled_at=datetime.fromisoformat("2026-08-21T10:30:00+08:00"),
        ),
        Response(),
    )
    sell = server.submit_simulation_strategy_intent(
        server.SimulationStrategyIntentRequest(
            intent_id="api-orb-exit-3231",
            strategy_id="opening_range_breakout",
            strategy_version="opening_range_breakout_exit_v1",
            symbol="3231",
            side="SELL",
            lots=1,
            limit_price="105",
            signaled_at=datetime.fromisoformat("2026-08-21T10:31:00+08:00"),
        ),
        Response(),
    )

    assert buy["order"]["status"] == "FILLED"
    assert sell["order"]["status"] == "FILLED"
    assert buy["order"]["origin"] == "STRATEGY_AUTOMATED"
    assert server.simulation_positions()["positions"] == []


def test_strategy_intent_http_round_trip_and_retry(monkeypatch):
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )
    signal_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    payload = {
        "intent_id": "http-orb-entry-3231",
        "strategy_id": "opening_range_breakout",
        "strategy_version": "opening_range_breakout_entry_v1",
        "symbol": "3231",
        "side": "BUY",
        "lots": 1,
        "limit_price": "106",
        "signaled_at": signal_at,
    }
    exit_payload = {
        **payload,
        "intent_id": "http-orb-exit-3231",
        "strategy_version": "opening_range_breakout_exit_v1",
        "side": "SELL",
        "limit_price": "105",
    }

    with TestClient(server.app) as client:
        first = client.post("/api/simulation/strategy-intents", json=payload)
        repeated = client.post("/api/simulation/strategy-intents", json=payload)
        sold = client.post(
            "/api/simulation/strategy-intents",
            json=exit_payload,
        )
        projection = client.get("/api/simulation/projection")

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert sold.status_code == 201
    assert projection.status_code == 200
    assert repeated.json()["order_idempotent"] is True
    assert repeated.json()["order"]["order_id"] == first.json()["order"]["order_id"]
    assert sold.json()["order"]["status"] == "FILLED"
    assert sold.json()["order"]["origin"] == "STRATEGY_AUTOMATED"
    assert projection.json()["positions"] == []
    assert len(projection.json()["orders"]) == 2


def test_automated_strategy_control_routes_require_explicit_risk_parameters(monkeypatch):
    controller = FakeAutomatedStrategyController()
    monkeypatch.setattr(server, "get_automated_strategy_controller", lambda: controller)
    response = Response()

    started = server.start_automated_strategy(
        server.AutomatedStrategyStartRequest(
            stop_loss_pct="1.5",
            take_profit_pct="3",
            max_daily_loss="50000",
        ),
        response,
    )
    status_payload = server.automated_strategy_status()
    stopped = server.stop_automated_strategy()

    assert started == {"state": "RUNNING", "decision": "STARTED"}
    assert response.status_code == 201
    assert controller.received is not None
    assert controller.received.stop_loss_pct == Decimal("1.5")
    assert controller.received.take_profit_pct == Decimal("3")
    assert controller.received.max_daily_loss == Decimal("50000")
    assert status_payload["decision"] == "WAITING_SIGNAL"
    assert stopped["state"] == "STOPPED"
    assert controller.stopped is True
