"""Fail-close the one fresh-r3 job created before the PREPARED gate existed.

This repair is metadata-only.  It never constructs a market-data provider and
never selects a history partition payload.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.application import BacktestApplicationService
from backtest.domain import canonical_json
from backtest.postgres_repository import PostgresBacktestRepository


JOB_ID = "dataset-download-r3-e9981217a1d36c213e121db3ebaa26e7"
TARGET_DATASET_ID = "dataset-r3-e9981217a1d36c213e121db3ebaa26e7"
EXPECTED_REQUEST_DIGEST = (
    "f04d7e78ba5c79390bf471c53741efbadf061aafd89abe5682654a9594047256"
)
LEGACY_KIND = "DATASET_DOWNLOAD"
LEGACY_STATUS = "QUEUED"
PREPARED_KIND = "PRICE_COVERAGE_PREPARED"
PREPARED_STATUS = "PREPARED"
PREPARED_MESSAGE = (
    "Fresh r3 prepared; generic Kbar resume prohibited; dedicated activation required"
)


def _request_digest(request: object) -> str:
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


def main() -> None:
    repository = BacktestApplicationService._build_repository()
    try:
        if not isinstance(repository, PostgresBacktestRepository):
            raise RuntimeError("r3 quarantine requires the configured PostgreSQL authority")
        pool = repository.connection_pool
        if pool is None:
            raise RuntimeError("r3 quarantine requires a PostgreSQL connection pool")
        with pool.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL search_path TO backtest, public")
                    cursor.execute(
                        """
                        SELECT job_id, kind, status, request_json, resource_id,
                               progress, progress_message, created_at, updated_at,
                               error_message
                        FROM backtest_jobs
                        WHERE job_id = %s
                        FOR UPDATE
                        """,
                        (JOB_ID,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("fresh r3 job is missing")
                    columns = [description.name for description in cursor.description]
                    job = dict(zip(columns, row, strict=True))
                    request = job["request_json"]
                    if _request_digest(request) != EXPECTED_REQUEST_DIGEST:
                        raise RuntimeError("fresh r3 request digest drifted")
                    if request.get("target_dataset_id") != TARGET_DATASET_ID:
                        raise RuntimeError("fresh r3 target Dataset identity drifted")
                    if request.get("lineage_mode") != "FRESH_R3_NO_CHECKPOINT_REUSE":
                        raise RuntimeError("fresh r3 lineage mode drifted")
                    cursor.execute(
                        "SELECT COUNT(*) FROM backtest_history_partitions WHERE job_id = %s",
                        (JOB_ID,),
                    )
                    if int(cursor.fetchone()[0]) != 0:
                        raise RuntimeError("fresh r3 already has history partitions")
                    cursor.execute(
                        "SELECT COUNT(*) FROM backtest_datasets WHERE dataset_id = %s",
                        (TARGET_DATASET_ID,),
                    )
                    if int(cursor.fetchone()[0]) != 0:
                        raise RuntimeError("fresh r3 target Dataset already exists")

                    already_prepared = (
                        job["kind"] == PREPARED_KIND
                        and job["status"] == PREPARED_STATUS
                        and job["progress_message"] == PREPARED_MESSAGE
                    )
                    if not already_prepared:
                        if (
                            job["kind"] != LEGACY_KIND
                            or job["status"] != LEGACY_STATUS
                            or float(job["progress"]) != 0.0
                            or job["resource_id"] is not None
                            or job["error_message"] is not None
                        ):
                            raise RuntimeError("fresh r3 is not in the exact legacy untouched state")
                        cursor.execute(
                            """
                            UPDATE backtest_jobs
                            SET kind = %s,
                                status = %s,
                                progress_message = %s,
                                updated_at = CURRENT_TIMESTAMP::text
                            WHERE job_id = %s
                              AND kind = %s
                              AND status = %s
                              AND progress = 0
                              AND resource_id IS NULL
                              AND error_message IS NULL
                            """,
                            (
                                PREPARED_KIND,
                                PREPARED_STATUS,
                                PREPARED_MESSAGE,
                                JOB_ID,
                                LEGACY_KIND,
                                LEGACY_STATUS,
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError("fresh r3 quarantine compare-and-set failed")

                    cursor.execute(
                        """
                        SELECT job_id, kind, status, request_json, resource_id,
                               progress, progress_message, created_at, updated_at,
                               error_message
                        FROM backtest_jobs
                        WHERE job_id = %s
                        """,
                        (JOB_ID,),
                    )
                    final_row = cursor.fetchone()
                    final_columns = [description.name for description in cursor.description]
                    final = dict(zip(final_columns, final_row, strict=True))
                    if (
                        final["kind"] != PREPARED_KIND
                        or final["status"] != PREPARED_STATUS
                        or float(final["progress"]) != 0.0
                        or final["progress_message"] != PREPARED_MESSAGE
                        or final["resource_id"] is not None
                        or final["error_message"] is not None
                        or _request_digest(final["request_json"])
                        != EXPECTED_REQUEST_DIGEST
                    ):
                        raise RuntimeError("fresh r3 quarantine postflight failed")
        print(
            json.dumps(
                {
                    "historical_payload_read": False,
                    "job_id": JOB_ID,
                    "job_kind": PREPARED_KIND,
                    "job_status": PREPARED_STATUS,
                    "partition_count": 0,
                    "provider_built": False,
                    "request_digest": EXPECTED_REQUEST_DIGEST,
                    "status": "IDEMPOTENT_REPLAY" if already_prepared else "QUARANTINED",
                    "target_dataset_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
