from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import (
    BacktestRunConfig,
    HistoricalBar,
    StrategySetSnapshot,
)
from backtest.engine import BacktestCancelled
from backtest.run_control import DurableRunControlProbe, ThrottledProgressReporter
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyRegistry


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _Repository:
    def __init__(self) -> None:
        self.status = "RUNNING"
        self.reads = 0
        self.writes: list[dict[str, object]] = []
        self.read_error: Exception | None = None

    def get_run(self, run_id: str):
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return {"run_id": run_id, "status": self.status}

    def update_run(self, run_id: str, **changes):
        self.writes.append({"run_id": run_id, **changes})
        return self.writes[-1]


class _WorkerRepository:
    def __init__(self, run: dict, dataset: dict) -> None:
        self.run = dict(run)
        self.dataset = dict(dataset)
        self.writes: list[dict[str, object]] = []
        self.transitions: list[dict[str, object]] = []
        self.cancel_before_first_transition = False
        self.terminal_failures_remaining = 0

    def get_run(self, run_id: str):
        assert run_id == self.run["run_id"]
        return dict(self.run)

    def get_dataset(self, dataset_id: str):
        assert dataset_id == self.dataset["dataset_id"]
        return dict(self.dataset)

    def update_run(self, run_id: str, **changes):
        assert run_id == self.run["run_id"]
        if "status" in changes and self.terminal_failures_remaining:
            self.terminal_failures_remaining -= 1
            raise RuntimeError("postgres is restarting")
        self.writes.append({"run_id": run_id, **changes})
        self.run.update(changes)
        return dict(self.run)

    def transition_run_status(
        self,
        run_id: str,
        *,
        expected_statuses: tuple[str, ...],
        status: str,
        progress_message: str,
    ):
        assert run_id == self.run["run_id"]
        if self.cancel_before_first_transition:
            self.run["status"] = "CANCELLING"
            self.cancel_before_first_transition = False
        changed = self.run["status"] in expected_statuses
        self.transitions.append(
            {
                "expected_statuses": expected_statuses,
                "status": status,
                "changed": changed,
            }
        )
        if changed:
            self.run.update(status=status, progress_message=progress_message)
        return dict(self.run), changed

    def save_result(self, run_id: str, result: dict) -> None:
        raise AssertionError("terminal error worker 不可保存 result")


class _TerminalEngine:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, *, progress, **kwargs):
        progress(0.20, "durable progress")
        progress(0.201, "pending terminal progress")
        raise self.error


def _worker_service(tmp_path, error: Exception):
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    bar = HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(2026, 8, 21, 9, 1, tzinfo=ZoneInfo("Asia/Taipei")),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=10_000,
    )
    manifest = catalog.create_imported_dataset(
        bars=(bar,),
        source="WORKER_CONTROL_TEST",
    )
    config = BacktestRunConfig(
        dataset_id=manifest.dataset_id,
        dataset_digest=manifest.manifest_digest,
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("end_of_day_exit_v1",),
        ),
        minimum_oos_trades=1,
    )
    run = {
        "run_id": "worker-control-run",
        "status": "QUEUED",
        "config": config.to_dict(),
    }
    repository = _WorkerRepository(
        run,
        manifest.to_dict() | {"status": "READY"},
    )
    service = object.__new__(BacktestApplicationService)
    service._repository = repository
    service._catalog = catalog
    service._registry = StrategyRegistry()
    service._engine = _TerminalEngine(error)
    return service, repository


def test_durable_control_probe_is_time_bounded_and_fail_closed() -> None:
    repository = _Repository()
    clock = _Clock()
    probe = DurableRunControlProbe(repository, "run-1", clock=clock)

    for _ in range(10_000):
        assert probe() is False
    assert repository.reads == 1

    repository.status = "CANCELLING"
    clock.value = 0.999
    assert probe() is False
    assert repository.reads == 1
    clock.value = 1.0
    assert probe() is True
    assert repository.reads == 2

    repository.read_error = RuntimeError("postgres unavailable")
    clock.value = 2.0
    with pytest.raises(RuntimeError, match="postgres unavailable"):
        probe()


def test_progress_reporter_is_bounded_by_time_or_delta_and_flushes() -> None:
    repository = _Repository()
    clock = _Clock()
    reporter = ThrottledProgressReporter(
        repository,
        "run-1",
        interval_seconds=1.0,
        minimum_delta=0.10,
        clock=clock,
    )

    for index in range(1, 1_001):
        reporter(index / 10_000, f"bar {index}")
    assert len(repository.writes) == 1

    reporter(0.101, "crossed delta")
    assert len(repository.writes) == 2
    reporter(0.102, "pending terminal progress")
    reporter.flush()
    assert len(repository.writes) == 3
    assert repository.writes[-1]["progress"] == pytest.approx(0.102)

    reporter(0.103, "pending by time")
    clock.value = 1.0
    reporter(0.104, "time boundary")
    assert len(repository.writes) == 4


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (BacktestCancelled("cancelled at deterministic boundary"), "CANCELLED"),
        (RuntimeError("engine failed"), "FAILED"),
    ),
)
def test_worker_flushes_pending_progress_before_terminal_status(
    tmp_path,
    error: Exception,
    expected_status: str,
) -> None:
    service, repository = _worker_service(tmp_path, error)

    service._run_backtest("worker-control-run")

    assert repository.run["status"] == expected_status
    assert repository.run["progress"] == pytest.approx(0.201)
    pending_write_index = next(
        index
        for index, write in enumerate(repository.writes)
        if write.get("progress") == pytest.approx(0.201)
    )
    terminal_write_index = next(
        index
        for index, write in enumerate(repository.writes)
        if write.get("status") == expected_status
    )
    assert pending_write_index < terminal_write_index


def test_worker_retries_terminal_status_after_transient_database_restart(
    tmp_path,
    monkeypatch,
) -> None:
    service, repository = _worker_service(tmp_path, RuntimeError("engine failed"))
    repository.terminal_failures_remaining = 3
    delays: list[float] = []
    monkeypatch.setattr("backtest.application.sleep", delays.append)

    service._run_backtest("worker-control-run")

    assert repository.run["status"] == "FAILED"
    assert repository.run["error_message"] == "engine failed"
    assert delays == [0.1, 0.25, 0.5]


def test_worker_status_cas_preserves_cancellation_committed_before_preflight(
    tmp_path,
) -> None:
    service, repository = _worker_service(
        tmp_path,
        RuntimeError("engine must not run"),
    )
    repository.cancel_before_first_transition = True

    service._run_backtest("worker-control-run")

    assert repository.transitions == [
        {
            "expected_statuses": ("QUEUED",),
            "status": "PREFLIGHT",
            "changed": False,
        }
    ]
    assert repository.run["status"] == "CANCELLED"
    assert all(write.get("status") != "PREFLIGHT" for write in repository.writes)
    assert all(write.get("status") != "RUNNING" for write in repository.writes)


def test_sqlite_status_cas_rejects_stale_worker_transition(tmp_path) -> None:
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    try:
        repository.create_run(
            {
                "run_id": "sqlite-worker-cas",
                "idempotency_key": "sqlite-worker-cas-create",
                "status": "QUEUED",
                "config": {"contract": "worker-cas-test"},
                "config_digest": "worker-cas-config-digest",
                "dataset_id": "dataset-worker-cas",
                "dataset_digest": "dataset-worker-cas-digest",
                "created_at": "2026-08-21T09:00:00+08:00",
            }
        )
        repository.update_run(
            "sqlite-worker-cas",
            status="CANCELLING",
            progress_message="cancel accepted",
        )

        current, changed = repository.transition_run_status(
            "sqlite-worker-cas",
            expected_statuses=("QUEUED",),
            status="PREFLIGHT",
            progress_message="worker preflight",
        )

        assert changed is False
        assert current["status"] == "CANCELLING"
        assert repository.get_run("sqlite-worker-cas")["status"] == "CANCELLING"
    finally:
        repository.close()
