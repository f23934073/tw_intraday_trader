#!/usr/bin/env python3
"""Read-only durable-state audit for the completed R5 authoritative control."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg

from config import backtest as backtest_settings


BASELINE_RUN_ID = "run-91ad87981676414da87b928398fa43c9"
CONTROL_RUN_ID = "run-4de8112d3a154148a1af93fc86a26f83"


def main() -> int:
    output: dict[str, object] = {}
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM backtest.backtest_schema_migrations
                WHERE version = %s
                """,
                ("014_cash_admission_controls.sql",),
            )
            output["migration_014_count"] = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT current_revision, status
                FROM backtest.backtest_cash_admission_control_heads
                WHERE baseline_run_id = %s AND contract_version = %s
                """,
                (BASELINE_RUN_ID, "cash-admission-control-v1"),
            )
            output["head"] = cursor.fetchone()
            cursor.execute(
                """
                SELECT revision, control_run_id, status, preflight_digest,
                       sizing_digest, research_control_snapshot_digest,
                       postflight_digest, postflight_json->>'verdict',
                       postflight_json->'diagnostics'
                FROM backtest.backtest_cash_admission_control_registrations
                WHERE baseline_run_id = %s
                """,
                (BASELINE_RUN_ID,),
            )
            registration = cursor.fetchone()
            output["registration"] = {
                "revision": registration[0],
                "control_run_id": registration[1],
                "status": registration[2],
                "preflight_digest": registration[3],
                "sizing_digest": registration[4],
                "snapshot_digest": registration[5],
                "postflight_digest": registration[6],
                "verdict": registration[7],
                "diagnostics": registration[8],
            }
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM backtest.backtest_cash_admission_control_operations
                WHERE baseline_run_id = %s
                """,
                (BASELINE_RUN_ID,),
            )
            output["operation_count"] = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT status, progress, progress_message, error_message,
                       result_digest, config_digest, dataset_id, dataset_digest
                FROM backtest.backtest_runs
                WHERE run_id = %s
                """,
                (CONTROL_RUN_ID,),
            )
            run = cursor.fetchone()
            output["run"] = {
                "status": run[0],
                "progress": str(run[1]),
                "progress_message": run[2],
                "error_message": run[3],
                "result_digest": run[4],
                "config_digest": run[5],
                "dataset_id": run[6],
                "dataset_digest": run[7],
            }
            counts: dict[str, int] = {}
            for name, query in (
                (
                    "result_rows",
                    "SELECT COUNT(*) FROM backtest.backtest_results WHERE run_id = %s",
                ),
                (
                    "result_chunks",
                    "SELECT COUNT(*) FROM backtest.backtest_result_chunks WHERE run_id = %s",
                ),
                (
                    "trade_rows",
                    "SELECT COUNT(*) FROM backtest.backtest_trades WHERE run_id = %s",
                ),
                (
                    "daily_equity_rows",
                    "SELECT COUNT(*) FROM backtest.backtest_daily_equity WHERE run_id = %s",
                ),
            ):
                cursor.execute(query, (CONTROL_RUN_ID,))
                counts[name] = cursor.fetchone()[0]
            output["published_result_counts"] = counts
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM backtest.backtest_runs
                WHERE status = ANY(%s)
                """,
                (
                    [
                        "QUEUED",
                        "PREFLIGHT",
                        "RUNNING",
                        "CANCELLING",
                        "CONTROL_POSTFLIGHT",
                    ],
                ),
            )
            output["active_run_count"] = cursor.fetchone()[0]
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
