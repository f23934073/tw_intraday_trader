from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backtest.migrations import migration_files
from backtest.sqlite_postgres_migration import (
    TABLE_SPECS,
    _read_only_sqlite,
    _rows_digest,
    _source_fingerprint,
    _stale_running_job_ids,
    _transform_source_row,
)
from backtest.sqlite_repository import SQLiteBacktestRepository


def test_backtest_forward_migrations_include_logical_schema_move() -> None:
    assert [path.name for path in migration_files()] == [
        "001_backtest_core.sql",
        "002_strategy_catalog.sql",
        "003_resumable_history_download.sql",
        "004_backtest_schema.sql",
        "005_atomic_strategy_platform.sql",
        "006_atomic_strategy_web_management.sql",
        "007_atomic_strategy_audit_contract.sql",
        "008_backtest_qualification.sql",
        "009_backtest_experiment_families.sql",
        "010_backtest_experiment_family_identity.sql",
    ]
    assert [spec.name for spec in TABLE_SPECS] == [
        "backtest_datasets",
        "strategy_definitions",
        "backtest_jobs",
        "backtest_history_partitions",
        "backtest_runs",
        "backtest_results",
        "backtest_decisions",
        "backtest_trades",
        "backtest_daily_equity",
        "backtest_comparisons",
    ]


def test_only_stale_running_job_is_reconciled_and_checkpoint_is_preserved(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backtest.sqlite3"
    repository = SQLiteBacktestRepository(path)
    try:
        for job_id, status in (
            ("stale-running", "RUNNING"),
            ("recent-running", "RUNNING"),
            ("already-paused", "PAUSED"),
        ):
            repository.create_job(
                {
                    "job_id": job_id,
                    "kind": "DATASET_DOWNLOAD",
                    "status": status,
                    "request": {"years": 3},
                    "progress": 0.25,
                    "progress_message": "已保存 2/8 檔",
                    "created_at": "2026-08-21T08:00:00+08:00",
                }
            )
        repository._connection.execute(
            "UPDATE backtest_jobs SET updated_at = ? WHERE job_id = ?",
            ("2026-08-21T08:00:00+08:00", "stale-running"),
        )
        repository._connection.execute(
            "UPDATE backtest_jobs SET updated_at = ? WHERE job_id != ?",
            ("2026-08-21T09:50:00+08:00", "stale-running"),
        )
        repository._connection.commit()
    finally:
        repository.close()

    with _read_only_sqlite(path) as source:
        stale = _stale_running_job_ids(
            source,
            datetime.fromisoformat("2026-08-21T09:30:00+08:00"),
        )
        assert stale == frozenset({"stale-running"})
        rows = {
            row["job_id"]: dict(row)
            for row in source.execute("SELECT * FROM backtest_jobs")
        }

    spec = next(spec for spec in TABLE_SPECS if spec.name == "backtest_jobs")
    transformed = _transform_source_row(spec, rows["stale-running"], stale)
    assert transformed["status"] == "PAUSED"
    assert transformed["progress"] == 0.25
    assert "已保存 2/8 檔" in transformed["progress_message"]
    assert _transform_source_row(spec, rows["already-paused"], stale)["status"] == "PAUSED"
    assert _transform_source_row(spec, rows["recent-running"], stale)["status"] == "RUNNING"


def test_verification_digest_normalizes_json_timestamp_and_bytea() -> None:
    dataset_spec = next(
        spec for spec in TABLE_SPECS if spec.name == "backtest_datasets"
    )
    source_dataset = {
        "dataset_id": "dataset-1",
        "status": "READY",
        "manifest_json": '{"symbols":["2330"], "version":1}',
        "created_at": "2026-08-21T09:00:00+08:00",
        "updated_at": "2026-08-21T09:01:00+08:00",
    }
    destination_dataset = {
        **source_dataset,
        "manifest_json": {"version": 1, "symbols": ["2330"]},
    }
    assert _rows_digest(dataset_spec, iter([source_dataset])) == _rows_digest(
        dataset_spec,
        iter([destination_dataset]),
    )

    partition_spec = next(
        spec for spec in TABLE_SPECS if spec.name == "backtest_history_partitions"
    )
    source_partition = {
        "job_id": "job-1",
        "symbol": "2330",
        "name": "台積電",
        "market": "TSE",
        "start_date": "2026-08-20",
        "end_date": "2026-08-21",
        "bar_count": 2,
        "bars_sha256": "payload-digest",
        "bars_payload": b"compressed-bars",
        "error_message": None,
        "created_at": "2026-08-21T09:00:00+08:00",
        "updated_at": "2026-08-21T09:01:00+08:00",
    }
    destination_partition = {
        **source_partition,
        "bars_payload": memoryview(b"compressed-bars"),
        "created_at": datetime(2026, 8, 21, 1, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 21, 1, 1, tzinfo=timezone.utc),
    }
    assert _rows_digest(partition_spec, iter([source_partition])) == _rows_digest(
        partition_spec,
        iter([destination_partition]),
    )


def test_source_fingerprint_ignores_empty_wal_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "backtest.sqlite3"
    path.write_bytes(b"sqlite-main")
    wal_path = Path(f"{path}-wal")
    wal_path.write_bytes(b"")

    before = _source_fingerprint(path)
    wal_path.unlink()

    assert _source_fingerprint(path) == before
