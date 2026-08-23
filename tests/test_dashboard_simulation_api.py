"""Focused tests for the dashboard's local paper-simulation route contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier, Event, Lock, RLock
from time import sleep
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

import dashboard.server as server
from dashboard.service import DashboardService
from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MarketDataUsage, MockProvider
from runtime.composition import RuntimeComposition
from simulation.continuous_strategy import AutomatedStrategyConfig
from simulation.settings import JsonLocalPaperSettingsRepository


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def session_date(self) -> date:
        return self._now.date()


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
    def __init__(self, *, fail_on_start_call: int | None = None) -> None:
        super().__init__()
        self._stream_lock = Lock()
        self._handler = None
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_on_start_call = fail_on_start_call

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        with self._stream_lock:
            self.start_calls += 1
            if self.start_calls == self.fail_on_start_call:
                raise RuntimeError("stream start failed")
            if self._handler is not None and self._handler is not handler:
                raise RuntimeError("stream handler already registered")
            self._handler = handler
        sleep(0.05)

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        with self._stream_lock:
            self.stop_calls += 1
            self._handler = None


class ContentionObservingRLock:
    """Behavior-compatible RLock that exposes cross-thread contention."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.contended = Event()

    def __enter__(self):
        if not self._lock.acquire(blocking=False):
            self.contended.set()
            self._lock.acquire()
        return self

    def __exit__(self, *_args) -> None:
        self._lock.release()


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

    def engage_kill_switch(self, reason: str) -> dict:
        return {
            "state": "KILLED",
            "decision": "KILL_SWITCH_ENGAGED",
            "kill_switch": {"engaged": True, "reason": reason},
        }

    def reset_kill_switch(self) -> dict:
        return {
            "state": "STOPPED",
            "decision": "STOPPED",
            "kill_switch": {"engaged": False, "reason": None},
        }


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


def test_settings_page_api_persists_draft_and_applies_new_local_session(
    monkeypatch,
    tmp_path,
) -> None:
    provider = CountingStreamingProvider()
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", provider)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(
        server,
        "_local_paper_settings_repository",
        JsonLocalPaperSettingsRepository(tmp_path / "settings.json"),
    )
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app) as client:
        initial = client.get("/api/simulation/settings").json()
        old_session_id = initial["active_session_id"]
        token = initial["csrf_token"]
        drafted_response = client.put(
            "/api/simulation/settings",
            headers={"X-Strategy-CSRF": token},
            json={
                "revision": initial["revision"],
                "starting_cash_twd": "12000000",
                "max_daily_buy_notional_twd": "2500000",
                "commission_rate": "0.001425",
                "minimum_commission_twd": "20",
            },
        )
        drafted = drafted_response.json()
        before_apply = client.get("/api/simulation/session").json()
        applied_response = client.post(
            "/api/simulation/settings/apply",
            headers={"X-Strategy-CSRF": token},
            json={"revision": drafted["revision"], "confirm_reset": False},
        )
        applied = applied_response.json()
        after_apply = client.get("/api/simulation/session").json()
        active_composition = server.get_runtime_composition()
        active_session = active_composition.journal.session(
            applied["active_session_id"]
        )
        old_record_kinds = [
            result.record.kind
            for result in active_composition.journal.records(old_session_id)
        ]

    assert drafted_response.status_code == 200
    assert drafted["has_unapplied_changes"] is True
    assert before_apply["starting_cash"] == 10_000_000.0
    assert applied_response.status_code == 200
    assert applied["has_unapplied_changes"] is False
    assert after_apply["starting_cash"] == 12_000_000.0
    assert after_apply["max_daily_buy_notional"] == 2_500_000.0
    assert after_apply["commission_rate"] == 0.001425
    assert active_session is not None
    assert active_session.metadata["settings_schema"] == "local-paper-settings-v1"
    assert active_session.metadata["settings_revision"] == drafted["draft_settings_revision"]
    assert "local_paper_session_archive.v1" in old_record_kinds
    assert provider.start_calls == 2
    assert after_apply["streaming"] is True


def test_settings_apply_waits_for_old_runtime_command_and_rechecks_blockers(
    monkeypatch,
    tmp_path,
) -> None:
    lifecycle_lock = ContentionObservingRLock()
    repository = JsonLocalPaperSettingsRepository(tmp_path / "settings.json")
    monkeypatch.setattr(server, "_runtime_composition_lock", lifecycle_lock)
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(server, "_local_paper_settings_repository", repository)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    command_entered = Event()
    release_command = Event()
    with TestClient(server.app) as client:
        initial = client.get("/api/simulation/settings").json()
        drafted = client.put(
            "/api/simulation/settings",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={
                "revision": initial["revision"],
                "starting_cash_twd": "12000000",
                "max_daily_buy_notional_twd": "2500000",
                "commission_rate": "0.001425",
                "minimum_commission_twd": "20",
            },
        ).json()
        old_session_id = initial["active_session_id"]
        old_composition = server.get_runtime_composition()
        original_submit = old_composition.local_paper_commands.submit_order

        def paused_submit(**kwargs):
            command_entered.set()
            if not release_command.wait(timeout=2):
                raise AssertionError("timed out waiting to release old runtime command")
            return original_submit(**kwargs)

        monkeypatch.setattr(
            old_composition.local_paper_commands,
            "submit_order",
            paused_submit,
        )
        lifecycle_lock.contended.clear()

        with ThreadPoolExecutor(max_workers=2) as executor:
            order_future = executor.submit(
                client.post,
                "/api/simulation/orders",
                json={
                    "symbol": "3231",
                    "side": "BUY",
                    "quantity_shares": 1_000,
                    "limit_price": "106",
                    "idempotency_key": "settings-apply-runtime-lease",
                },
            )
            assert command_entered.wait(timeout=1)
            apply_future = executor.submit(
                client.post,
                "/api/simulation/settings/apply",
                headers={"X-Strategy-CSRF": initial["csrf_token"]},
                json={
                    "revision": drafted["revision"],
                    "confirm_reset": False,
                },
            )
            apply_waited_for_command = lifecycle_lock.contended.wait(timeout=1)
            release_command.set()
            order_response = order_future.result(timeout=2)
            apply_response = apply_future.result(timeout=2)

        assert apply_waited_for_command is True
        assert order_response.status_code == 201
        assert order_response.json()["order"]["status"] == "FILLED"
        assert apply_response.status_code == 409
        assert "確認重建模擬帳戶" in apply_response.json()["detail"]
        assert server.get_runtime_composition() is old_composition
        assert all(
            result.record.kind != "local_paper_session_archive.v1"
            for result in old_composition.journal.records(old_session_id)
        )

        confirmed_response = client.post(
            "/api/simulation/settings/apply",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={
                "revision": drafted["revision"],
                "confirm_reset": True,
            },
        )
        old_record_kinds = [
            result.record.kind
            for result in old_composition.journal.records(old_session_id)
        ]

    assert confirmed_response.status_code == 200
    assert old_record_kinds[-1] == "local_paper_session_archive.v1"


def test_settings_api_rejects_sub_cent_minimum_commission(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(
        server,
        "_local_paper_settings_repository",
        JsonLocalPaperSettingsRepository(tmp_path / "settings.json"),
    )
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app) as client:
        initial = client.get("/api/simulation/settings").json()
        response = client.put(
            "/api/simulation/settings",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={
                "revision": initial["revision"],
                "starting_cash_twd": "10000000",
                "max_daily_buy_notional_twd": "2000000",
                "commission_rate": "0.001425",
                "minimum_commission_twd": "0.001",
            },
        )

    assert response.status_code == 422
    assert "0.01 元為單位" in response.json()["detail"]


@pytest.mark.parametrize(
    "failure_stage",
    ["replacement", "activation", "archive"],
)
def test_settings_apply_failure_keeps_exact_old_runtime_live(
    monkeypatch,
    tmp_path,
    failure_stage,
) -> None:
    repository = JsonLocalPaperSettingsRepository(tmp_path / "settings.json")
    provider = CountingStreamingProvider()
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", provider)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(server, "_local_paper_settings_repository", repository)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app, raise_server_exceptions=False) as client:
        initial = client.get("/api/simulation/settings").json()
        drafted = client.put(
            "/api/simulation/settings",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={
                "revision": initial["revision"],
                "starting_cash_twd": "11000000",
                "max_daily_buy_notional_twd": "2100000",
                "commission_rate": "0.001425",
                "minimum_commission_twd": "20",
            },
        ).json()
        current = server.get_runtime_composition()
        old_simulation = current.simulation_service
        close_calls = 0
        original_close = old_simulation.close

        def track_old_close() -> None:
            nonlocal close_calls
            close_calls += 1
            original_close()

        monkeypatch.setattr(old_simulation, "close", track_old_close)
        if failure_stage == "replacement":
            monkeypatch.setattr(
                server,
                "_replacement_composition",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("replacement failed")
                ),
            )
        elif failure_stage == "activation":
            monkeypatch.setattr(
                repository,
                "activate_draft",
                lambda **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("activation failed")
                ),
            )
        else:
            original_append = current.journal.append

            def fail_archive(record):
                if record.kind == "local_paper_session_archive.v1":
                    raise RuntimeError("archive failed")
                return original_append(record)

            monkeypatch.setattr(current.journal, "append", fail_archive)

        response = client.post(
            "/api/simulation/settings/apply",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={"revision": drafted["revision"], "confirm_reset": False},
        )

        assert response.status_code == 500
        assert server._composition is current
        assert server._simulation_service is old_simulation
        assert close_calls == 0
        assert old_simulation.session()["starting_cash"] == 10_000_000.0
        assert provider.start_calls == (
            1 if failure_stage == "replacement" else 3
        )
        assert provider._handler.__self__ is old_simulation
        assert repository.load().active_session_id == initial["active_session_id"]


def test_settings_apply_stream_handoff_failure_reactivates_old_runtime(
    monkeypatch,
    tmp_path,
) -> None:
    repository = JsonLocalPaperSettingsRepository(tmp_path / "settings.json")
    provider = CountingStreamingProvider(fail_on_start_call=2)
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", provider)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(server, "_automated_strategy_controller", None)
    monkeypatch.setattr(server, "_local_paper_settings_repository", repository)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app, raise_server_exceptions=False) as client:
        initial = client.get("/api/simulation/settings").json()
        drafted = client.put(
            "/api/simulation/settings",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={
                "revision": initial["revision"],
                "starting_cash_twd": "11000000",
                "max_daily_buy_notional_twd": "2100000",
                "commission_rate": "0.001425",
                "minimum_commission_twd": "20",
            },
        ).json()
        current = server.get_runtime_composition()
        old_simulation = current.simulation_service
        old_simulation.watch_quote(owner_id="handoff-test", symbol="3231")
        quote_at = datetime.now(ZoneInfo("Asia/Taipei"))
        old_simulation.receive_quote_update(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=quote_at,
                received_at=quote_at,
                bid_price=105.0,
                ask_price=105.5,
                bid_volume_lots=10,
                ask_volume_lots=12,
            )
        )
        for _ in range(50):
            quote_before_handoff = old_simulation.quote_watch_status(
                owner_id="handoff-test",
                symbol="3231",
            )
            if quote_before_handoff["bid_price"] == "105.0":
                break
            sleep(0.01)
        assert quote_before_handoff["bid_price"] == "105.0"
        response = client.post(
            "/api/simulation/settings/apply",
            headers={"X-Strategy-CSRF": initial["csrf_token"]},
            json={"revision": drafted["revision"], "confirm_reset": False},
        )

        assert response.status_code == 500
        assert server._composition is current
        assert server._simulation_service is old_simulation
        assert old_simulation.session()["streaming"] is True
        assert old_simulation.session()["subscribed_symbols"] == ["3231"]
        assert old_simulation.session()["watched_symbols"] == ["3231"]
        quote_after_rollback = old_simulation.quote_watch_status(
            owner_id="handoff-test",
            symbol="3231",
        )
        assert quote_after_rollback["bid_price"] == quote_before_handoff["bid_price"]
        assert quote_after_rollback["ask_price"] == quote_before_handoff["ask_price"]
        assert (
            quote_after_rollback["book_received_at"]
            == quote_before_handoff["book_received_at"]
        )
        assert provider.start_calls == 3
        assert provider._handler.__self__ is old_simulation
        assert repository.load().active_session_id == initial["active_session_id"]
        assert all(
            result.record.kind != "local_paper_session_archive.v1"
            for result in current.journal.records(initial["active_session_id"])
        )


def test_submit_simulation_order_route_accepts_odd_lot_shares(monkeypatch) -> None:
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    payload = server.submit_simulation_order(
        server.SimulationOrderRequest(
            symbol="3231",
            side="BUY",
            quantity_shares=125,
            limit_price=106.0,
            idempotency_key="route-odd-lot-buy",
        ),
        Response(),
    )

    assert payload["order"]["status"] == "FILLED"
    assert payload["order"]["quantity_shares"] == 125
    assert server.simulation_positions()["positions"][0]["quantity"] == 125


def test_submit_simulation_order_http_rejects_boolean_share_quantity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app) as client:
        response = client.post(
            "/api/simulation/orders",
            json={
                "symbol": "3231",
                "side": "BUY",
                "quantity_shares": True,
                "limit_price": 106,
                "idempotency_key": "reject-boolean-share-quantity",
            },
        )

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "quantity_shares"]
        and error["type"] == "int_type"
        for error in response.json()["detail"]
    )


def test_raw_strategy_intent_http_route_is_not_exposed(monkeypatch) -> None:
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", MockProvider())
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)
    monkeypatch.setattr(
        server.backtest_settings,
        "BACKTEST_INCREMENTAL_SYNC_ENABLED",
        False,
    )

    with TestClient(server.app) as client:
        response = client.post(
            "/api/simulation/strategy-intents",
            json={
                "intent_id": "reject-boolean-strategy-share-quantity",
                "strategy_id": "opening_range_breakout",
                "strategy_version": "opening_range_breakout_entry_v1",
                "symbol": "3231",
                "side": "BUY",
                "quantity_shares": True,
                "limit_price": "106",
                "signaled_at": "2026-08-22T10:00:00+08:00",
            },
        )

    assert response.status_code == 404


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


def test_raw_strategy_intent_http_cannot_bypass_exact_set_activation(monkeypatch):
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
    with TestClient(server.app) as client:
        first = client.post("/api/simulation/strategy-intents", json=payload)
        repeated = client.post("/api/simulation/strategy-intents", json=payload)
        projection = client.get("/api/simulation/projection")

    assert first.status_code == 404
    assert repeated.status_code == 404
    assert projection.status_code == 200
    assert projection.json()["positions"] == []
    assert projection.json()["orders"] == []


def test_automated_strategy_control_routes_require_explicit_risk_parameters(monkeypatch):
    controller = FakeAutomatedStrategyController()
    monkeypatch.setattr(server, "get_automated_strategy_controller", lambda: controller)
    response = Response()
    http_request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [(b"host", b"testserver")],
        }
    )

    started = server.start_automated_strategy(
        server.AutomatedStrategyStartRequest(
            entry_strategy_set_version_id="paper-entry-set-v1",
            stop_loss_pct="1.5",
            take_profit_pct="3",
            max_daily_loss="50000",
            actor_id="local-operator",
            activation_idempotency_key="api-start-1",
        ),
        response,
        http_request,
        server._atomic_strategy_csrf_token,
    )
    status_payload = server.automated_strategy_status()
    stopped = server.stop_automated_strategy(
        http_request,
        server._atomic_strategy_csrf_token,
    )

    assert started == {"state": "RUNNING", "decision": "STARTED"}
    assert response.status_code == 201
    assert controller.received is not None
    assert controller.received.entry_strategy_set_version_id == "paper-entry-set-v1"
    assert controller.received.stop_loss_pct == Decimal("1.5")
    assert controller.received.take_profit_pct == Decimal("3")
    assert controller.received.max_daily_loss == Decimal("50000")
    assert status_payload["decision"] == "WAITING_SIGNAL"
    assert stopped["state"] == "STOPPED"
    assert controller.stopped is True


def test_automated_strategy_mutations_require_csrf_and_exact_origin(monkeypatch):
    controller = FakeAutomatedStrategyController()
    monkeypatch.setattr(server, "get_automated_strategy_controller", lambda: controller)
    client = TestClient(server.app)
    token = client.get("/api/atomic-strategies/capabilities").json()["csrf_token"]
    payload = {
        "entry_strategy_set_version_id": "paper-entry-set-v1",
        "stop_loss_pct": "1.5",
        "take_profit_pct": "3",
        "max_daily_loss": "50000",
        "actor_id": "local-operator",
        "activation_idempotency_key": "api-start-csrf-1",
    }

    assert client.post(
        "/api/simulation/automated-strategy/start", json=payload
    ).status_code == 403
    assert client.post(
        "/api/simulation/automated-strategy/start",
        headers={
            "X-Strategy-CSRF": token,
            "Origin": "https://testserver:4443",
        },
        json=payload,
    ).status_code == 403
    assert client.post(
        "/api/simulation/automated-strategy/start",
        headers={"X-Strategy-CSRF": token},
        json=payload,
    ).status_code == 201
    assert client.post(
        "/api/simulation/automated-strategy/stop"
    ).status_code == 403
    assert client.post(
        "/api/simulation/automated-strategy/kill-switch",
        headers={"X-Strategy-CSRF": token},
        json={"reason": "operator test"},
    ).json()["state"] == "KILLED"
    assert client.post(
        "/api/simulation/automated-strategy/kill-switch/reset",
        headers={"X-Strategy-CSRF": token},
    ).json()["state"] == "STOPPED"
