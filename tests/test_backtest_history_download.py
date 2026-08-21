"""Contracts for database-checkpointed, resumable historical downloads."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.historical_download import ResumableHistoricalDownloader
from backtest.historical_download import (
    HistoricalDownloadPaused,
    _LEGACY_TRANSIENT_EMPTY,
    _encode_partition,
    _retry_symbol_from_job,
    _resume_state,
)
from backtest.dataset import HistoricalInstrument
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.models import KBar
from market_data.provider import (
    MarketDataLimitReached,
    MarketDataTemporarilyUnavailable,
    MockProvider,
)


TAIPEI = ZoneInfo("Asia/Taipei")


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


class _EmptyForSymbolMockProvider(MockProvider):
    def __init__(self, empty_symbol: str) -> None:
        super().__init__()
        self.empty_symbol = empty_symbol

    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        if symbol == self.empty_symbol:
            return []
        return super().get_kbars(symbol, start, end)


class _TemporaryOnceMockProvider(_FailOnceMockProvider):
    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        self.calls[symbol] += 1
        if symbol == self.fail_symbol and not self.failed:
            self.failed = True
            raise MarketDataTemporarilyUnavailable("fixture Kbar timeout")
        return MockProvider.get_kbars(self, symbol, start, end)


class _MappingErrorMockProvider(MockProvider):
    def __init__(self, missing_symbol: str) -> None:
        super().__init__()
        self.missing_symbol = missing_symbol

    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        if symbol == self.missing_symbol:
            raise KeyError("fixture symbol mapping missing")
        return super().get_kbars(symbol, start, end)


class _UtcKbarProvider(MockProvider):
    def get_kbars(self, symbol: str, start: date, end: date):  # type: ignore[no-untyped-def]
        return [
            KBar(
                timestamp=datetime(2026, 1, 1, 1, minute, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1,
            )
            for minute in (0, 1)
        ]


def test_provider_bars_receive_taipei_session_dates_before_daily_derivation() -> None:
    with TemporaryDirectory() as directory:
        catalog = HistoricalDatasetCatalog(Path(directory) / "datasets")
        bars = catalog.fetch_provider_bars(
            _UtcKbarProvider(),
            instrument=HistoricalInstrument(symbol="2330", name="台積電", market="TWSE"),
            start=date(2026, 1, 1),
            end=date(2026, 1, 1),
        )
        parent = catalog.create_imported_dataset(bars=bars, source="utc-fixture")

        assert {bar.session_date for bar in bars} == {date(2026, 1, 1)}
        child = catalog.create_derived_daily_dataset(
            dataset_id="dataset-derived-provider-session-date",
            base_dataset_id=parent.dataset_id,
            completion_proofs={("2330", date(2026, 1, 1)): "proof"},
            session_contract={"version": "fixture-calendar-v1"},
            price_adjustment_policy="RAW",
            corporate_action_adjusted=False,
            volume_contract={"scope": "REGULAR_SESSION", "unit": "COMMON_LOT"},
        )

        daily_bar = catalog.load_bars(child.dataset_id)[0]
        assert daily_bar.session_date == date(2026, 1, 1)
        assert bars[0].timestamp == datetime(2026, 1, 1, 9, 0, tzinfo=TAIPEI)
        assert daily_bar.session_open_at == bars[0].timestamp


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
            assert "rate limit" in stored_job["progress_message"]
            assert "[RATE_LIMITED]" in str(stored_job["error_message"])
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


def test_explicit_coverage_scan_records_empty_observation_and_continues() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        downloader = ResumableHistoricalDownloader(
            provider=_EmptyForSymbolMockProvider("2317"),
            repository=repository,
            catalog=catalog,
            coverage_scan_mode=True,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])

            manifest = downloader.run(job_id)
            partitions = {
                item["symbol"]: item
                for item in repository.list_history_partitions(job_id)
            }

            assert repository.get_job(job_id)["status"] == "COMPLETED"
            assert partitions["2317"]["bar_count"] == 0
            assert partitions["2317"]["error_message"] == (
                "[PRICE_DATA_UNAVAILABLE] PROVIDER_EMPTY_KBAR"
            )
            assert partitions["2330"]["bar_count"] > 0
            assert manifest["requested_symbols"] == ["2317", "2330"]
            assert manifest["observed_symbols"] == ["2330"]
            assert manifest["universe_scope"] == "CURRENT_SNAPSHOT"
            assert manifest["research_eligible"] is False
            assert "2317: [PRICE_DATA_UNAVAILABLE] PROVIDER_EMPTY_KBAR" in manifest[
                "issues"
            ]
        finally:
            repository.close()


def test_coverage_scan_records_temporary_failure_and_continues() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        downloader = ResumableHistoricalDownloader(
            provider=_TemporaryOnceMockProvider("2317"),
            repository=repository,
            catalog=catalog,
            coverage_scan_mode=True,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])

            manifest = downloader.run(job_id)
            partitions = {
                item["symbol"]: item
                for item in repository.list_history_partitions(job_id)
            }

            assert partitions["2317"]["bar_count"] == 0
            assert partitions["2317"]["error_message"] == (
                "[TEMPORARY_FETCH_FAILURE] fixture Kbar timeout"
            )
            assert partitions["2330"]["bar_count"] > 0
            assert manifest["research_eligible"] is False
        finally:
            repository.close()


def test_coverage_scan_records_mapping_failure_and_continues() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        downloader = ResumableHistoricalDownloader(
            provider=_MappingErrorMockProvider("2317"),
            repository=repository,
            catalog=catalog,
            coverage_scan_mode=True,
        )
        try:
            job = downloader.create_job(
                years=1,
                symbols=("2317", "2330"),
                end_date=date(2026, 1, 5),
            )
            job_id = str(job["job_id"])

            downloader.run(job_id)
            partitions = {
                item["symbol"]: item
                for item in repository.list_history_partitions(job_id)
            }

            assert partitions["2317"]["bar_count"] == 0
            assert partitions["2317"]["error_message"] == (
                "[SYMBOL_MAPPING_ERROR] 'fixture symbol mapping missing'"
            )
            assert partitions["2330"]["bar_count"] > 0
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


def test_resume_accepts_legitimate_shared_one_year_provider_coverage() -> None:
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
    )

    assert completed == {f"TEST{index}" for index in range(10)}
    assert retry_from is None


def test_resume_retries_exact_symbol_and_still_repairs_legacy_empty_tail() -> None:
    instruments = tuple(
        HistoricalInstrument(symbol=f"TEST{index}", name="Test", market="TWSE")
        for index in range(4)
    )
    partitions = [
        {
            "symbol": instrument.symbol,
            "bar_count": 0 if index == 3 else 100,
            "error_message": _LEGACY_TRANSIENT_EMPTY if index == 3 else None,
            "start_date": None if index == 3 else "2025-08-18",
        }
        for index, instrument in enumerate(instruments)
    ]

    completed, retry_from = _resume_state(
        instruments,
        partitions,
        retry_symbol="TEST1",
    )

    assert completed == {"TEST0", "TEST2"}
    assert retry_from == "TEST1"


def test_legacy_timeout_job_recovers_next_symbol_from_saved_progress() -> None:
    instruments = tuple(
        HistoricalInstrument(symbol=f"TEST{index}", name="Test", market="TWSE")
        for index in range(10)
    )

    retry_symbol = _retry_symbol_from_job(
        {
            "status": "FAILED",
            "progress": 0.4,
            "progress_message": "下載失敗；可用同一 job id 接續（已保存 4 檔）",
            "error_message": "Timeout Topic: api/v1/data/kbars",
        },
        instruments,
    )

    assert retry_symbol == "TEST4"


def test_temporary_provider_error_pauses_and_retries_stale_partition() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        provider = _TemporaryOnceMockProvider("2330")
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

            with pytest.raises(HistoricalDownloadPaused, match="fixture Kbar timeout"):
                downloader.run(job_id)

            paused_job = repository.get_job(job_id)
            assert paused_job["status"] == "PAUSED"
            assert "[RETRY_SYMBOL=2330]" in str(paused_job["error_message"])

            instrument = HistoricalInstrument(symbol="2330", name="台積電", market="TWSE")
            stale = catalog.fetch_provider_bars(
                MockProvider(),
                instrument=instrument,
                start=date(2026, 1, 5),
                end=date(2026, 1, 5),
            )
            repository.upsert_history_partition(
                _encode_partition(
                    job_id=job_id,
                    instrument=instrument,
                    bars=stale,
                    error_message=None,
                )
            )
            completed_symbol_calls = provider.calls["2317"]
            failed_symbol_calls = provider.calls["2330"]

            manifest = downloader.run(job_id)

            assert provider.calls["2317"] == completed_symbol_calls
            assert provider.calls["2330"] > failed_symbol_calls
            assert repository.get_job(job_id)["status"] == "COMPLETED"
            assert set(manifest["observed_symbols"]) == {"2317", "2330"}
        finally:
            repository.close()
