"""Contracts for registering date-effective data before it reaches the Web UI."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.sqlite_repository import SQLiteBacktestRepository
from scripts.import_backtest_dataset import import_dataset
from tests.test_backtest_core import _bars


def test_imported_date_effective_dataset_is_ready_for_web_selection() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "bars.jsonl"
        path.write_text("".join(json.dumps(bar.to_dict()) + "\n" for bar in _bars()), encoding="utf-8")
        catalog = HistoricalDatasetCatalog(root / "datasets")
        repository = SQLiteBacktestRepository(root / "backtest.sqlite3")
        try:
            manifest = import_dataset(
                bars_path=path,
                source="fixture-date-effective-v1",
                universe_scope="DATE_EFFECTIVE",
                research_eligible=True,
                catalog=catalog,
                repository=repository,
            )
            stored = repository.get_dataset(str(manifest["dataset_id"]))

            assert stored["status"] == "READY"
            assert stored["research_eligible"] is True
            assert catalog.load_bars(str(manifest["dataset_id"]))
            with pytest.raises(ValueError, match="DATE_EFFECTIVE"):
                import_dataset(
                    bars_path=path,
                    source="fixture-invalid",
                    universe_scope="IMPORTED",
                    research_eligible=True,
                    catalog=catalog,
                    repository=repository,
                )
        finally:
            repository.close()
