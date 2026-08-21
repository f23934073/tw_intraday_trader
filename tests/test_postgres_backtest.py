from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_DSN,
    reason="requires explicit TEST_POSTGRES_DSN",
)

from backtest.sqlite_postgres_migration import (  # noqa: E402
    migrate_sqlite_to_postgres,
)
from backtest.sqlite_repository import SQLiteBacktestRepository  # noqa: E402


_DROP_BACKTEST = """
DROP SCHEMA IF EXISTS backtest CASCADE;
DROP TABLE IF EXISTS
    public.backtest_history_partitions,
    public.backtest_results,
    public.backtest_decisions,
    public.backtest_trades,
    public.backtest_daily_equity,
    public.backtest_comparisons,
    public.strategy_definitions,
    public.backtest_runs,
    public.backtest_datasets,
    public.backtest_jobs,
    public.backtest_schema_migrations
CASCADE
"""


def test_sqlite_copy_is_idempotent_verified_and_reconciles_only_stale_job(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backtest.sqlite3"
    repository = SQLiteBacktestRepository(sqlite_path)
    try:
        for job_id, status, updated_at in (
            ("stale-running", "RUNNING", "2026-08-20T09:00:00+08:00"),
            ("active-paused", "PAUSED", "2026-08-21T09:00:00+08:00"),
        ):
            repository.create_job(
                {
                    "job_id": job_id,
                    "kind": "DATASET_DOWNLOAD",
                    "status": status,
                    "request": {"symbols": ["2330"]},
                    "progress": 0.5,
                    "progress_message": "已保存 1/2 檔",
                    "created_at": "2026-08-20T08:00:00+08:00",
                }
            )
            repository._connection.execute(
                "UPDATE backtest_jobs SET updated_at = ? WHERE job_id = ?",
                (updated_at, job_id),
            )
        repository.upsert_history_partition(
            {
                "job_id": "active-paused",
                "symbol": "2330",
                "name": "台積電",
                "market": "TSE",
                "start_date": "2026-08-20",
                "end_date": "2026-08-21",
                "bar_count": 2,
                "bars_sha256": "bars-digest",
                "bars_payload": b"compressed-bars",
                "created_at": "2026-08-21T09:00:00+08:00",
            }
        )
        repository._connection.commit()
    finally:
        repository.close()

    connection = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with connection.cursor() as cursor:
            cursor.execute(_DROP_BACKTEST)
        connection.commit()

        first = migrate_sqlite_to_postgres(
            sqlite_path=sqlite_path,
            postgres_connection=connection,
            stale_minutes=30,
            now=datetime.fromisoformat("2026-08-21T10:00:00+08:00"),
        )
        second = migrate_sqlite_to_postgres(
            sqlite_path=sqlite_path,
            postgres_connection=connection,
            stale_minutes=30,
            now=datetime.fromisoformat("2026-08-21T10:00:00+08:00"),
        )

        assert first.verified is True
        assert second.verified is True
        assert first.reconciled_stale_job_ids == ("stale-running",)
        assert first.tables == second.tables
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, status, progress, progress_message
                FROM backtest.backtest_jobs
                ORDER BY job_id
                """
            )
            rows = cursor.fetchall()
            assert rows[0][:3] == ("active-paused", "PAUSED", 0.5)
            assert rows[1][:3] == ("stale-running", "PAUSED", 0.5)
            assert "stale RUNNING" in rows[1][3]
            cursor.execute(
                """
                SELECT bars_sha256, bars_payload
                FROM backtest.backtest_history_partitions
                WHERE job_id = 'active-paused' AND symbol = '2330'
                """
            )
            assert cursor.fetchone() == ("bars-digest", b"compressed-bars")
            cursor.execute(
                """
                SELECT
                    to_regclass('public.backtest_jobs'),
                    to_regclass('backtest.backtest_jobs'),
                    to_regclass('backtest.backtest_history_partitions')
                """
            )
            assert cursor.fetchone() == (
                None,
                "backtest.backtest_jobs",
                "backtest.backtest_history_partitions",
            )

        source = sqlite3.connect(sqlite_path)
        try:
            assert source.execute(
                "SELECT status FROM backtest_jobs WHERE job_id = 'stale-running'"
            ).fetchone()[0] == "RUNNING"
        finally:
            source.close()
    finally:
        with connection.cursor() as cursor:
            cursor.execute(_DROP_BACKTEST)
        connection.commit()
        connection.close()
