"""Contracts for bounded exploratory datasets built from resumable checkpoints."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog, HistoricalInstrument
from backtest.domain import HistoricalBar
from backtest.exploratory_pilot import ExploratoryPilotBuilder
from backtest.historical_download import _encode_partition
from backtest.sqlite_repository import SQLiteBacktestRepository


TAIPEI = ZoneInfo("Asia/Taipei")


def _bars(symbol: str, start: date, end: date) -> tuple[HistoricalBar, ...]:
    pilot_end = date(2024, 12, 31)
    sessions = tuple(
        dict.fromkeys((start, pilot_end, end))
        if start <= pilot_end <= end
        else dict.fromkeys((start, end))
    )
    return tuple(
        HistoricalBar(
            symbol=symbol,
            name=symbol,
            market="TWSE" if symbol != "6488" else "TPEX",
            timestamp=datetime(session.year, session.month, session.day, 9, minute, tzinfo=TAIPEI),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1,
            session_date=session,
        )
        for session in sessions
        for minute in (0, 1)
    )


def _fixture() -> tuple[TemporaryDirectory[str], SQLiteBacktestRepository, HistoricalDatasetCatalog, str]:
    directory: TemporaryDirectory[str] = TemporaryDirectory()
    root = Path(directory.name)
    repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
    catalog = HistoricalDatasetCatalog(root / "datasets")
    job_id = "dataset-download-pilot-fixture"
    instruments = (
        HistoricalInstrument("2317", "2317", "TWSE"),
        HistoricalInstrument("2330", "2330", "TWSE"),
        HistoricalInstrument("6488", "6488", "TPEX"),
        HistoricalInstrument("9999", "9999", "TWSE"),
    )
    repository.create_job(
        {
            "job_id": job_id,
            "kind": "DATASET_DOWNLOAD",
            "status": "PAUSED",
            "request": {
                "provider": "ShioajiProvider",
                "start_date": "2023-08-19",
                "end_date": "2026-08-18",
                "instruments": [item.to_dict() for item in instruments],
            },
            "progress": 0.75,
            "progress_message": "fixture paused",
            "created_at": datetime.now(TAIPEI).isoformat(),
        }
    )
    for symbol in ("2317", "2330", "6488"):
        repository.upsert_history_partition(
            _encode_partition(
                job_id=job_id,
                instrument=next(item for item in instruments if item.symbol == symbol),
                bars=_bars(symbol, date(2023, 8, 21), date(2026, 8, 18)),
                error_message=None,
            )
        )
    repository.upsert_history_partition(
        _encode_partition(
            job_id=job_id,
            instrument=instruments[-1],
            bars=(),
            error_message="[PRICE_DATA_UNAVAILABLE] PROVIDER_EMPTY_KBAR",
        )
    )
    return directory, repository, catalog, job_id


def test_plan_uses_only_nonempty_endpoint_covered_partitions() -> None:
    directory, repository, catalog, job_id = _fixture()
    try:
        plan = ExploratoryPilotBuilder(repository=repository, catalog=catalog).plan(
            job_id=job_id,
            start_date=date(2023, 8, 21),
            end_date=date(2024, 12, 31),
            symbol_limit=2,
        )

        assert plan.eligible_symbols == ("2317", "2330", "6488")
        assert plan.selected_symbols == ("2317", "6488")
        assert plan.rejected_counts == {
            "empty": 0,
            "provider_error": 1,
            "endpoint_coverage": 0,
        }
        assert plan.to_dict()["formal_holdout_allowed"] is False
    finally:
        repository.close()
        directory.cleanup()


def test_materialize_clips_dates_and_keeps_source_job_paused() -> None:
    directory, repository, catalog, job_id = _fixture()
    try:
        builder = ExploratoryPilotBuilder(repository=repository, catalog=catalog)
        plan = builder.plan(
            job_id=job_id,
            start_date=date(2023, 8, 21),
            end_date=date(2024, 12, 31),
            symbol_limit=3,
            symbols=("2330", "6488"),
        )
        manifest = builder.materialize(plan)
        bars = catalog.load_bars(manifest.dataset_id)

        assert manifest.research_eligible is False
        assert manifest.end_date == "2024-12-31"
        assert manifest.requested_symbols == ("2330", "6488")
        assert {bar.symbol for bar in bars} == {"2330", "6488"}
        assert max((bar.session_date or bar.timestamp.date()) for bar in bars) == date(2024, 12, 31)
        assert "FORMAL_VALIDATION_PROHIBITED" in manifest.issues
        assert "FORMAL_HOLDOUT_PROHIBITED" in manifest.issues
        assert repository.get_job(job_id)["status"] == "PAUSED"
        assert repository.get_dataset(manifest.dataset_id)["status"] == "READY"
    finally:
        repository.close()
        directory.cleanup()


def test_pilot_refuses_dates_after_the_frozen_in_sample_ceiling() -> None:
    directory, repository, catalog, job_id = _fixture()
    try:
        with pytest.raises(ValueError, match="2024-12-31"):
            ExploratoryPilotBuilder(repository=repository, catalog=catalog).plan(
                job_id=job_id,
                start_date=date(2023, 8, 21),
                end_date=date(2025, 1, 1),
                symbol_limit=1,
            )
    finally:
        repository.close()
        directory.cleanup()


def test_materialize_rechecks_endpoint_coverage_from_the_payload() -> None:
    directory, repository, catalog, job_id = _fixture()
    try:
        instrument = HistoricalInstrument("2330", "2330", "TWSE")
        partition = _encode_partition(
            job_id=job_id,
            instrument=instrument,
            bars=_bars("2330", date(2023, 8, 21), date(2023, 8, 21)),
            error_message=None,
        )
        partition["end_date"] = "2026-08-18"
        repository.upsert_history_partition(partition)
        builder = ExploratoryPilotBuilder(repository=repository, catalog=catalog)
        plan = builder.plan(
            job_id=job_id,
            start_date=date(2023, 8, 21),
            end_date=date(2024, 12, 31),
            symbol_limit=1,
            symbols=("2330",),
        )

        with pytest.raises(ValueError, match="payload 未通過"):
            builder.materialize(plan)
    finally:
        repository.close()
        directory.cleanup()


def test_explicit_symbols_must_all_pass_the_coverage_gate() -> None:
    directory, repository, catalog, job_id = _fixture()
    try:
        with pytest.raises(ValueError, match="9999"):
            ExploratoryPilotBuilder(repository=repository, catalog=catalog).plan(
                job_id=job_id,
                start_date=date(2023, 8, 21),
                end_date=date(2024, 12, 31),
                symbol_limit=2,
                symbols=("2330", "9999"),
            )
    finally:
        repository.close()
        directory.cleanup()
