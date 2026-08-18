"""Contracts for immutable, after-close incremental Kbar synchronization."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService, IncrementalSyncDeferred
from backtest.dataset import HistoricalDatasetCatalog
from backtest.historical_download import (
    HistoricalDownloadPaused,
    IncrementalHistoricalSync,
    ResumableHistoricalDownloader,
)
from backtest.scheduler import AfterCloseIncrementalScheduler
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MarketDataLimitReached, MockProvider


TAIPEI = ZoneInfo("Asia/Taipei")


class _RecordingMockProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.kbar_requests: dict[str, list[tuple[date, date]]] = defaultdict(list)

    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        self.kbar_requests[symbol].append((start, end))
        return super().get_kbars(symbol, start, end)


class _QuotaMockProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.exhausted = False

    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        if self.exhausted:
            raise MarketDataLimitReached("fixture quota exhausted")
        return super().get_kbars(symbol, start, end)


def test_incremental_sync_creates_parent_delta_version_and_is_session_idempotent() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _RecordingMockProvider()
        try:
            full = ResumableHistoricalDownloader(
                provider=provider,
                repository=repository,
                catalog=catalog,
            )
            seed_job = full.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            base = full.run(str(seed_job["job_id"]))
            base_bars = catalog.load_bars(str(base["dataset_id"]))
            provider.kbar_requests.clear()

            sync = IncrementalHistoricalSync(
                provider=provider,
                repository=repository,
                catalog=catalog,
            )
            job, created = sync.create_job(
                base_dataset_id=str(base["dataset_id"]),
                session_date=date(2026, 1, 6),
                overlap_days=1,
            )
            child = sync.run(str(job["job_id"]))

            assert created is True
            assert child["storage_format"] == "JSONL_DELTA_V1"
            assert child["parent_dataset_id"] == base["dataset_id"]
            assert child["delta_bar_count"] == 2
            assert child["bar_count"] == base["bar_count"] + 2
            assert len(catalog.load_bars(str(child["dataset_id"]))) == child["bar_count"]
            assert catalog.load_bars(str(base["dataset_id"])) == base_bars
            assert provider.kbar_requests == {
                "2317": [(date(2026, 1, 5), date(2026, 1, 6))],
                "2330": [(date(2026, 1, 5), date(2026, 1, 6))],
            }

            same_job, created_again = sync.create_job(
                base_dataset_id=str(base["dataset_id"]),
                session_date=date(2026, 1, 6),
                overlap_days=1,
            )
            same_manifest = sync.run(str(same_job["job_id"]))

            assert created_again is False
            assert same_job["job_id"] == job["job_id"]
            assert same_manifest["dataset_id"] == child["dataset_id"]
            assert provider.kbar_requests == {
                "2317": [(date(2026, 1, 5), date(2026, 1, 6))],
                "2330": [(date(2026, 1, 5), date(2026, 1, 6))],
            }
        finally:
            repository.close()


def test_incremental_sync_with_no_new_bars_reuses_base_without_empty_dataset() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _RecordingMockProvider()
        try:
            full = ResumableHistoricalDownloader(
                provider=provider,
                repository=repository,
                catalog=catalog,
            )
            seed_job = full.create_job(
                years=1,
                symbols=("2330",),
                end_date=date(2026, 1, 5),
            )
            base = full.run(str(seed_job["job_id"]))
            datasets_before = {item["dataset_id"] for item in repository.list_datasets()}

            sync = IncrementalHistoricalSync(
                provider=provider,
                repository=repository,
                catalog=catalog,
            )
            job, _ = sync.create_job(
                base_dataset_id=str(base["dataset_id"]),
                session_date=date(2026, 1, 5),
                overlap_days=1,
            )
            result = sync.run(str(job["job_id"]))
            stored_job = repository.get_job(str(job["job_id"]))

            assert result["dataset_id"] == base["dataset_id"]
            assert stored_job["status"] == "COMPLETED"
            assert stored_job["resource_id"] == base["dataset_id"]
            assert "沒有新 Kbar" in stored_job["progress_message"]
            assert {item["dataset_id"] for item in repository.list_datasets()} == datasets_before
        finally:
            repository.close()


def test_incremental_sync_pauses_instead_of_completing_on_provider_quota() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _QuotaMockProvider()
        full = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        try:
            seed_job = full.create_job(
                years=1,
                symbols=("2330",),
                end_date=date(2026, 1, 5),
            )
            base = full.run(str(seed_job["job_id"]))
            provider.exhausted = True
            sync = IncrementalHistoricalSync(
                provider=provider,
                repository=repository,
                catalog=catalog,
            )
            job, _ = sync.create_job(
                base_dataset_id=str(base["dataset_id"]),
                session_date=date(2026, 1, 6),
                overlap_days=1,
            )
            job_id = str(job["job_id"])

            with pytest.raises(HistoricalDownloadPaused, match="quota exhausted"):
                sync.run(job_id)

            assert repository.get_job(job_id)["status"] == "PAUSED"
            assert repository.list_history_partitions(job_id) == []
        finally:
            repository.close()


def test_after_close_scheduler_uses_taipei_time_and_triggers_once_per_session() -> None:
    calls: list[date] = []

    def trigger(session_date: date) -> dict[str, object]:
        calls.append(session_date)
        return {
            "job": {"job_id": f"dataset-incremental-{session_date:%Y%m%d}"},
            "created": True,
        }

    scheduler = AfterCloseIncrementalScheduler(
        trigger=trigger,
        close_time=time(14, 30),
        poll_seconds=60,
    )

    before = scheduler.run_due(datetime(2026, 8, 18, 14, 29, tzinfo=TAIPEI))
    due = scheduler.run_due(datetime(2026, 8, 18, 14, 30, tzinfo=TAIPEI))
    repeated = scheduler.run_due(datetime(2026, 8, 18, 15, 0, tzinfo=TAIPEI))
    weekend = scheduler.run_due(datetime(2026, 8, 22, 15, 0, tzinfo=TAIPEI))

    assert before["state"] == "WAITING_FOR_CLOSE"
    assert due["state"] == "SUBMITTED"
    assert repeated["state"] == "SUBMITTED"
    assert weekend["state"] == "WAITING_FOR_TRADING_DAY"
    assert calls == [date(2026, 8, 18)]


def test_scheduler_retries_deferred_session_instead_of_marking_it_submitted() -> None:
    attempts = 0

    def trigger(session_date: date) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IncrementalSyncDeferred(
                "等待初始下載",
                scheduler_state="BLOCKED_BY_ACTIVE_JOB",
                job_id="dataset-download-active",
            )
        return {
            "job": {"job_id": f"dataset-incremental-{session_date:%Y%m%d}"},
            "created": True,
        }

    scheduler = AfterCloseIncrementalScheduler(
        trigger=trigger,
        close_time=time(14, 30),
        poll_seconds=60,
    )
    now = datetime(2026, 8, 18, 15, 0, tzinfo=TAIPEI)

    deferred = scheduler.run_due(now)
    submitted = scheduler.run_due(now)

    assert deferred["state"] == "BLOCKED_BY_ACTIVE_JOB"
    assert submitted["state"] == "SUBMITTED"
    assert attempts == 2


def test_scheduler_resubmits_failed_durable_job_for_same_session() -> None:
    calls = 0
    durable_status = "FAILED"

    def trigger(session_date: date) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "job": {"job_id": f"dataset-incremental-{session_date:%Y%m%d}"},
            "created": calls == 1,
        }

    scheduler = AfterCloseIncrementalScheduler(
        trigger=trigger,
        close_time=time(14, 30),
        poll_seconds=60,
        job_status=lambda job_id: {
            "job_id": job_id,
            "status": durable_status,
            "progress_message": "fixture failed",
        },
    )
    now = datetime(2026, 8, 18, 15, 0, tzinfo=TAIPEI)

    scheduler.run_due(now)
    retried = scheduler.run_due(now)
    durable_status = "COMPLETED"
    completed = scheduler.run_due(now)

    assert retried["state"] == "SUBMITTED"
    assert completed["state"] == "COMPLETED"
    assert calls == 2


def test_application_service_submits_incremental_job_and_returns_same_session_job() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = MockProvider()
        full = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        seed_job = full.create_job(
            years=1,
            symbols=("2330",),
            end_date=date(2026, 1, 5),
        )
        full.run(str(seed_job["job_id"]))
        service = BacktestApplicationService(
            provider,
            repository=repository,
            catalog=catalog,
            workers=1,
        )
        try:
            submitted = service.start_incremental_sync(
                date(2026, 1, 6),
                overlap_days=1,
            )
            job_id = str(submitted["job"]["job_id"])
            completed = _wait_for_job(repository, job_id)
            repeated = service.start_incremental_sync(
                date(2026, 1, 6),
                overlap_days=1,
            )

            assert submitted["created"] is True
            assert completed["status"] == "COMPLETED"
            assert repeated["created"] is False
            assert repeated["job"]["job_id"] == job_id
        finally:
            service.close()


def test_application_service_defers_when_full_download_is_active() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository.create_job(
            {
                "job_id": "dataset-download-active",
                "kind": "DATASET_DOWNLOAD",
                "status": "RUNNING",
                "request": {},
                "created_at": datetime.now(TAIPEI).isoformat(),
            }
        )
        service = BacktestApplicationService(
            MockProvider(),
            repository=repository,
            catalog=catalog,
            workers=1,
        )
        try:
            try:
                service.start_incremental_sync(date(2026, 1, 6), overlap_days=1)
            except IncrementalSyncDeferred as error:
                assert error.scheduler_state == "BLOCKED_BY_ACTIVE_JOB"
                assert error.job_id == "dataset-download-active"
            else:
                raise AssertionError("active full download must block incremental sync")
        finally:
            service.close()


def test_application_service_does_not_refetch_when_base_already_covers_session() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _RecordingMockProvider()
        full = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        seed_job = full.create_job(
            years=1,
            symbols=("2330",),
            end_date=date(2026, 1, 5),
        )
        base = full.run(str(seed_job["job_id"]))
        provider.kbar_requests.clear()
        service = BacktestApplicationService(
            provider,
            repository=repository,
            catalog=catalog,
            workers=1,
        )
        try:
            result = service.start_incremental_sync(
                date(2026, 1, 5),
                overlap_days=1,
            )

            assert result["job"]["status"] == "COMPLETED"
            assert result["job"]["resource_id"] == base["dataset_id"]
            assert provider.kbar_requests == {}
        finally:
            service.close()


def _wait_for_job(
    repository: SQLiteBacktestRepository,
    job_id: str,
) -> dict[str, object]:
    import time as time_module

    for _ in range(100):
        job = repository.get_job(job_id)
        if job["status"] in {"COMPLETED", "FAILED", "PAUSED"}:
            return job
        time_module.sleep(0.01)
    raise AssertionError("incremental sync worker did not finish")
