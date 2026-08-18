"""Contracts for database-checkpointed, resumable historical downloads."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.historical_download import ResumableHistoricalDownloader
from backtest.historical_download import (
    HistoricalDownloadPaused,
    _encode_partition,
    _resume_state,
)
from backtest.dataset import HistoricalInstrument
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MarketDataLimitReached, MockProvider


class _FailOnceMockProvider(MockProvider):
    def __init__(self, fail_symbol: str) -> None:
        super().__init__()
        self.fail_symbol = fail_symbol
        self.failed = False
        self.calls: Counter[str] = Counter()

    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        self.calls[symbol] += 1
        if symbol == self.fail_symbol and not self.failed:
            self.failed = True
            raise RuntimeError("fixture transient provider failure")
        return super().get_kbars(symbol, start, end)


class _QuotaMockProvider(_FailOnceMockProvider):
    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        self.calls[symbol] += 1
        if symbol == self.fail_symbol:
            raise MarketDataLimitReached("Shioaji 歷史行情剩餘流量不足")
        return MockProvider.get_kbars(self, symbol, start, end)


class _EmptyMockProvider(MockProvider):
    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        return []


def test_downloader_checkpoints_symbols_and_registers_ready_dataset() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        downloader = ResumableHistoricalDownloader(
            provider=MockProvider(),
            repository=repository,
            catalog=catalog,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2330", "2317"),
                end_date=date(2026, 1, 5),
            )
            manifest = downloader.run(str(job["job_id"]))
            stored_job = repository.get_job(str(job["job_id"]))
            partitions = repository.list_history_partitions(str(job["job_id"]))

            assert stored_job["status"] == "COMPLETED"
            assert stored_job["resource_id"] == manifest["dataset_id"]
            assert [item["symbol"] for item in partitions] == ["2317", "2330"]
            assert all(item["bar_count"] > 0 for item in partitions)
            assert repository.get_dataset(str(manifest["dataset_id"]))["status"] == "READY"
            assert len(catalog.load_bars(str(manifest["dataset_id"]))) == manifest["bar_count"]
        finally:
            repository.close()


def test_resume_skips_database_partitions_completed_before_provider_failure() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _FailOnceMockProvider("2330")
        downloader = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])
            with pytest.raises(RuntimeError, match="transient provider failure"):
                downloader.run(job_id)

            assert repository.get_job(job_id)["status"] == "FAILED"
            assert [item["symbol"] for item in repository.list_history_partitions(job_id)] == ["2317"]
            completed_symbol_calls = provider.calls["2317"]

            manifest = downloader.run(job_id)

            assert provider.calls["2317"] == completed_symbol_calls
            assert repository.get_job(job_id)["status"] == "COMPLETED"
            assert set(manifest["observed_symbols"]) == {"2317", "2330"}
        finally:
            repository.close()


def test_quota_limit_pauses_job_without_checkpointing_partial_symbol() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _QuotaMockProvider("2330")
        downloader = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])

            with pytest.raises(HistoricalDownloadPaused, match="剩餘流量不足"):
                downloader.run(job_id)

            stored_job = repository.get_job(job_id)
            assert stored_job["status"] == "PAUSED"
            assert "額度" in stored_job["progress_message"]
            assert [
                item["symbol"]
                for item in repository.list_history_partitions(job_id)
            ] == ["2317"]
        finally:
            repository.close()


def test_empty_full_history_pauses_without_saving_zero_partition() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        downloader = ResumableHistoricalDownloader(
            provider=_EmptyMockProvider(),
            repository=repository,
            catalog=catalog,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2330",),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])

            with pytest.raises(HistoricalDownloadPaused, match="空 Kbar"):
                downloader.run(job_id)

            assert repository.get_job(job_id)["status"] == "PAUSED"
            assert repository.list_history_partitions(job_id) == []
        finally:
            repository.close()


def test_resume_replays_every_partition_after_legacy_empty_checkpoint() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _FailOnceMockProvider("never")
        downloader = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330", "2603"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])
            request = repository.get_job(job_id)["request"]
            instruments = {
                item.symbol: item
                for item in catalog.provider_instruments(
                    provider,
                    symbols=("2317", "2330", "2603"),
                )
            }
            start = date.fromisoformat(str(request["start_date"]))
            end = date.fromisoformat(str(request["end_date"]))
            valid = catalog.fetch_provider_bars(
                provider,
                instrument=instruments["2317"],
                start=start,
                end=end,
            )
            partial = catalog.fetch_provider_bars(
                provider,
                instrument=instruments["2603"],
                start=end,
                end=end,
            )
            repository.upsert_history_partition(
                _encode_partition(
                    job_id=job_id,
                    instrument=instruments["2317"],
                    bars=valid,
                    error_message=None,
                )
            )
            repository.upsert_history_partition(
                _encode_partition(
                    job_id=job_id,
                    instrument=instruments["2330"],
                    bars=(),
                    error_message="資料來源未回傳 Kbar",
                )
            )
            repository.upsert_history_partition(
                _encode_partition(
                    job_id=job_id,
                    instrument=instruments["2603"],
                    bars=partial,
                    error_message=None,
                )
            )
            provider.calls.clear()

            manifest = downloader.run(job_id)
            partitions = {
                item["symbol"]: item
                for item in repository.list_history_partitions(job_id)
            }

            assert provider.calls["2317"] == 0
            assert provider.calls["2330"] > 0
            assert provider.calls["2603"] > 0
            assert partitions["2330"]["bar_count"] > 0
            assert partitions["2603"]["bar_count"] > len(partial)
            assert all(item["error_message"] is None for item in partitions.values())
            assert set(manifest["observed_symbols"]) == {"2317", "2330", "2603"}
        finally:
            repository.close()


def test_resume_detects_legacy_consecutive_one_year_truncation() -> None:
    instruments = tuple(
        HistoricalInstrument(symbol=f"TEST{index}", name="Test", market="TWSE")
        for index in range(10)
    )
    partitions = [
        {
            "symbol": instrument.symbol,
            "bar_count": 100,
            "error_message": None,
            "start_date": "2023-08-21" if index < 5 else "2025-08-18",
        }
        for index, instrument in enumerate(instruments)
    ]

    completed, retry_from = _resume_state(
        instruments,
        partitions,
        requested_start=date(2023, 8, 19),
        requested_end=date(2026, 8, 18),
    )

    assert completed == {f"TEST{index}" for index in range(5)}
    assert retry_from == "TEST5"
