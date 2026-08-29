"""HTTP contracts for the standalone historical-backtest workspace."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Response

import dashboard.server as server
from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MockProvider
from tests.test_backtest_core import _bars


class _SchedulerProbe:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "state": "WAITING_FOR_CLOSE",
            "timezone": "Asia/Taipei",
            "close_time": "14:30",
        }


def test_backtest_routes_execute_without_starting_simulation(monkeypatch) -> None:
    """The backtest API composes directly with a provider, not RuntimeComposition."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        manifest = catalog.create_imported_dataset(
            bars=_bars(),
            source="fixture",
            universe_scope="DATE_EFFECTIVE",
            research_eligible=True,
        )
        repository.upsert_dataset(manifest.to_dict(), "READY")
        service = BacktestApplicationService(
            MockProvider(),
            repository=repository,
            catalog=catalog,
            workers=1,
        )
        monkeypatch.setattr(server, "_backtest_service", service)
        monkeypatch.setattr(server, "_composition", None)
        monkeypatch.setattr(server, "_simulation_service", None)
        try:
            capabilities = server.backtest_capabilities()
            assert capabilities["enabled"] is True
            assert capabilities["readiness"] == {
                "platform": {"ready": True, "status": "PLATFORM_READY"},
                "data": {"ready": False, "status": "DATA_NOT_READY"},
                "strategy": {
                    "ready": False,
                    "status": "NO_QUALIFYING_STRATEGY",
                    "qualification_ids": [],
                    "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
                },
            }
            strategy_payload = server.backtest_strategies()
            definitions = strategy_payload["strategies"]
            assert {item["side"] for item in definitions} == {"ENTRY", "EXIT"}
            assert all(item["backtest_executable"] for item in definitions)
            assert (
                next(item for item in definitions if item["side"] == "ENTRY")["strategy_id"]
                == "legacy_gap_volume_vwap_entry_v1"
            )
            assert strategy_payload["selection"]["mode"] == "SINGLE_OR_MULTI"
            created = server.create_backtest_run(
                server.BacktestRunRequest(
                    dataset_id=manifest.dataset_id,
                    entry_strategy_ids=["legacy_gap_volume_vwap_entry_v1"],
                    exit_strategy_ids=["end_of_day_exit_v1"],
                    priority_order=["end_of_day_exit_v1", "legacy_gap_volume_vwap_entry_v1"],
                    minimum_oos_trades=1,
                    idempotency_key="backtest-api-route-test",
                ),
                Response(),
            )
            run_id = created["run"]["run_id"]
            _wait_for_completed(service, run_id)

            summary = server.backtest_summary(run_id)
            assert summary["full"]["closed_trades"] == 1
            assert server.backtest_drawdown(run_id)["drawdown"]
            trade = server.backtest_trades(run_id)["trades"][0]
            chart = server.backtest_trade_chart(run_id, trade["trade_id"])
            assert chart["markers"][0]["side"] == "ENTRY"
            export = server.export_backtest_trades(run_id)
            assert b"trade_id" in export.body

            multi = server.create_backtest_run(
                server.BacktestRunRequest(
                    dataset_id=manifest.dataset_id,
                    entry_strategy_ids=[
                        "legacy_gap_volume_vwap_entry_v1",
                        "momentum_breakout_entry_v1",
                    ],
                    exit_strategy_ids=["take_profit_exit_v1", "end_of_day_exit_v1"],
                    entry_policy="ANY",
                    exit_policy="ANY",
                    priority_order=[
                        "take_profit_exit_v1",
                        "end_of_day_exit_v1",
                        "legacy_gap_volume_vwap_entry_v1",
                        "momentum_breakout_entry_v1",
                    ],
                    minimum_oos_trades=1,
                    idempotency_key="backtest-api-multi-strategy-test",
                ),
                Response(),
            )
            multi_run = _wait_for_completed(service, multi["run"]["run_id"])
            assert len(multi_run["config"]["strategy_set"]["entry_strategy_ids"]) == 2
            assert len(multi_run["config"]["strategy_set"]["exit_strategy_ids"]) == 2
            assert (
                server.BacktestRunRequest(
                    dataset_id=manifest.dataset_id,
                    entry_strategy_ids=["legacy_gap_volume_vwap_entry_v1"],
                    exit_strategy_ids=["end_of_day_exit_v1"],
                    engine_version="backtest-engine-v3-tw",
                    idempotency_key="formal-v3-schema-contract",
                ).engine_version
                == "backtest-engine-v3-tw"
            )
        finally:
            service.close()
            monkeypatch.setattr(server, "_backtest_service", None)


def test_lifespan_starts_and_stops_incremental_scheduler(monkeypatch) -> None:
    scheduler = _SchedulerProbe()
    monkeypatch.setattr(server, "_incremental_scheduler", scheduler)
    monkeypatch.setattr(server, "_backtest_service", None)
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", None)

    async def exercise() -> None:
        async with server.lifespan(server.app):
            assert scheduler.started is True
            assert scheduler.stopped is False

    asyncio.run(exercise())

    assert scheduler.stopped is True


def test_incremental_sync_status_route_is_read_only(monkeypatch) -> None:
    scheduler = _SchedulerProbe()

    class _BacktestProbe:
        @staticmethod
        def latest_incremental_job() -> dict[str, object]:
            return {"job_id": "dataset-incremental-20260818", "status": "COMPLETED"}

    monkeypatch.setattr(server, "_incremental_scheduler", scheduler)
    monkeypatch.setattr(server, "_backtest_service", _BacktestProbe())

    payload = server.backtest_incremental_sync_status()

    assert payload["schedule"]["state"] == "WAITING_FOR_CLOSE"
    assert payload["latest_job"]["status"] == "COMPLETED"


def _wait_for_completed(service: BacktestApplicationService, run_id: str) -> dict[str, object]:
    for _ in range(100):
        run = service.get_run(run_id)
        if run["status"] in {"COMPLETED", "FAILED"}:
            assert run["status"] == "COMPLETED", run["error_message"]
            return run
        time.sleep(0.01)
    raise AssertionError("backtest route worker did not finish")
