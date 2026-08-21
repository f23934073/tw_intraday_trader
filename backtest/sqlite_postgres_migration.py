"""Non-destructive, resumable SQLite-to-PostgreSQL Backtest copy."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backtest.domain import canonical_json
from backtest.migrations import apply_migrations


class BacktestMigrationVerificationError(RuntimeError):
    """The destination does not exactly match the transformed source snapshot."""


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    json_columns: frozenset[str] = frozenset()
    timestamp_columns: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TableVerification:
    table: str
    source_rows: int
    destination_rows: int
    source_digest: str
    destination_digest: str
    verified: bool


@dataclass(frozen=True)
class BacktestMigrationReport:
    source_path: str
    source_size_bytes: int
    source_sha256: str
    reconciled_stale_job_ids: tuple[str, ...]
    tables: tuple[TableVerification, ...]
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "reconciled_stale_job_ids": list(self.reconciled_stale_job_ids),
            "tables": [asdict(table) for table in self.tables],
        }


TABLE_SPECS = (
    TableSpec(
        "backtest_datasets",
        ("dataset_id", "status", "manifest_json", "created_at", "updated_at"),
        ("dataset_id",),
        frozenset({"manifest_json"}),
    ),
    TableSpec(
        "strategy_definitions",
        (
            "strategy_id",
            "version",
            "role",
            "side",
            "session_phase",
            "status",
            "display_name_zh_tw",
            "execution_binding",
            "source",
            "definition_digest",
            "definition_json",
            "created_at",
            "updated_at",
        ),
        ("strategy_id", "version"),
        frozenset({"definition_json"}),
        frozenset({"created_at", "updated_at"}),
    ),
    TableSpec(
        "backtest_jobs",
        (
            "job_id",
            "kind",
            "status",
            "request_json",
            "resource_id",
            "progress",
            "progress_message",
            "created_at",
            "updated_at",
            "error_message",
        ),
        ("job_id",),
        frozenset({"request_json"}),
    ),
    TableSpec(
        "backtest_history_partitions",
        (
            "job_id",
            "symbol",
            "name",
            "market",
            "start_date",
            "end_date",
            "bar_count",
            "bars_sha256",
            "bars_payload",
            "error_message",
            "created_at",
            "updated_at",
        ),
        ("job_id", "symbol"),
        timestamp_columns=frozenset({"created_at", "updated_at"}),
    ),
    TableSpec(
        "backtest_runs",
        (
            "run_id",
            "idempotency_key",
            "status",
            "config_json",
            "config_digest",
            "dataset_id",
            "dataset_digest",
            "progress",
            "progress_message",
            "created_at",
            "updated_at",
            "error_message",
            "result_digest",
        ),
        ("run_id",),
        frozenset({"config_json"}),
    ),
    TableSpec(
        "backtest_results",
        ("run_id", "result_json", "summary_json", "created_at"),
        ("run_id",),
        frozenset({"result_json", "summary_json"}),
    ),
    TableSpec(
        "backtest_decisions",
        ("run_id", "decision_id", "symbol", "event_at", "side", "payload_json"),
        ("run_id", "decision_id"),
        frozenset({"payload_json"}),
    ),
    TableSpec(
        "backtest_trades",
        (
            "run_id",
            "trade_id",
            "symbol",
            "entry_at",
            "exit_at",
            "net_pnl",
            "payload_json",
        ),
        ("run_id", "trade_id"),
        frozenset({"payload_json"}),
    ),
    TableSpec(
        "backtest_daily_equity",
        ("run_id", "session_date", "equity", "payload_json"),
        ("run_id", "session_date"),
        frozenset({"payload_json"}),
    ),
    TableSpec(
        "backtest_comparisons",
        (
            "comparison_id",
            "baseline_run_id",
            "challenger_run_id",
            "payload_json",
            "created_at",
        ),
        ("comparison_id",),
        frozenset({"payload_json"}),
    ),
)


def migrate_sqlite_to_postgres(
    *,
    sqlite_path: Path,
    postgres_connection: Any,
    stale_minutes: int = 30,
    batch_size: int = 100,
    now: datetime | None = None,
    report_progress: Callable[[str], None] | None = None,
) -> BacktestMigrationReport:
    """Copy one stable SQLite snapshot, then verify every destination table."""

    if stale_minutes <= 0:
        raise ValueError("stale_minutes must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    source_path = sqlite_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source_path}")
    progress = report_progress or (lambda _message: None)
    source_fingerprint = _source_fingerprint(source_path)
    snapshot_sha256 = _file_sha256(source_path)
    snapshot_size = source_path.stat().st_size
    cutoff = _aware(now or datetime.now().astimezone()) - timedelta(minutes=stale_minutes)

    apply_migrations(postgres_connection)
    _set_backtest_search_path(postgres_connection)

    with _read_only_sqlite(source_path) as source:
        _validate_source_schema(source)
        stale_job_ids = _stale_running_job_ids(source, cutoff)
        progress(
            f"source snapshot ready; stale RUNNING jobs={len(stale_job_ids)}"
        )
        for spec in TABLE_SPECS:
            source_cursor = source.execute(_select_sql(spec, schema=None))
            copied = 0
            while rows := source_cursor.fetchmany(batch_size):
                mappings = [
                    _transform_source_row(spec, dict(row), stale_job_ids)
                    for row in rows
                ]
                _insert_rows(postgres_connection, spec, mappings)
                copied += len(mappings)
                progress(f"copied {spec.name}: {copied} rows")

        verifications = tuple(
            _verify_table(source, postgres_connection, spec, stale_job_ids)
            for spec in TABLE_SPECS
        )

    if _source_fingerprint(source_path) != source_fingerprint:
        raise BacktestMigrationVerificationError(
            "SQLite source changed while it was being copied; destination was not cut over"
        )
    if not all(item.verified for item in verifications):
        failed = ", ".join(item.table for item in verifications if not item.verified)
        raise BacktestMigrationVerificationError(
            f"PostgreSQL verification failed for: {failed}"
        )
    return BacktestMigrationReport(
        source_path=str(source_path),
        source_size_bytes=snapshot_size,
        source_sha256=snapshot_sha256,
        reconciled_stale_job_ids=tuple(sorted(stale_job_ids)),
        tables=verifications,
        verified=True,
    )


def _set_backtest_search_path(connection: Any) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO backtest, public")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


@contextmanager
def _read_only_sqlite(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _validate_source_schema(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    available = {str(row[0]) for row in rows}
    missing = {spec.name for spec in TABLE_SPECS} - available
    if missing:
        raise ValueError(f"SQLite source is missing tables: {', '.join(sorted(missing))}")
    for spec in TABLE_SPECS:
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({spec.name})").fetchall()
        }
        missing_columns = set(spec.columns) - columns
        if missing_columns:
            raise ValueError(
                f"SQLite source table {spec.name} is missing columns: "
                f"{', '.join(sorted(missing_columns))}"
            )


def _stale_running_job_ids(
    connection: sqlite3.Connection,
    cutoff: datetime,
) -> frozenset[str]:
    rows = connection.execute(
        "SELECT job_id, updated_at FROM backtest_jobs WHERE status = 'RUNNING'"
    ).fetchall()
    return frozenset(
        str(row["job_id"])
        for row in rows
        if _aware(datetime.fromisoformat(str(row["updated_at"]))) < cutoff
    )


def _transform_source_row(
    spec: TableSpec,
    row: dict[str, Any],
    stale_job_ids: frozenset[str],
) -> dict[str, Any]:
    if spec.name == "backtest_jobs" and row["job_id"] in stale_job_ids:
        previous_message = str(row.get("progress_message") or "").strip()
        prefix = "PostgreSQL 搬遷：stale RUNNING 已轉為 PAUSED"
        row["status"] = "PAUSED"
        row["progress_message"] = (
            f"{prefix}；{previous_message}" if previous_message else prefix
        )
    return row


def _insert_rows(
    connection: Any,
    spec: TableSpec,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        return
    columns = ", ".join(spec.columns)
    placeholders = ", ".join(
        "CAST(%s AS JSONB)" if column in spec.json_columns else "%s"
        for column in spec.columns
    )
    keys = ", ".join(spec.key_columns)
    sql = (
        f"INSERT INTO backtest.{spec.name} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({keys}) DO NOTHING"
    )
    values = [
        tuple(_postgres_value(spec, column, row[column]) for column in spec.columns)
        for row in rows
    ]
    try:
        with connection.cursor() as cursor:
            cursor.executemany(sql, values)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _postgres_value(spec: TableSpec, column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in spec.timestamp_columns:
        return _aware(datetime.fromisoformat(str(value)))
    if column == "bars_payload":
        return bytes(value)
    return value


def _verify_table(
    source: sqlite3.Connection,
    destination: Any,
    spec: TableSpec,
    stale_job_ids: frozenset[str],
) -> TableVerification:
    source_rows = (
        _transform_source_row(spec, dict(row), stale_job_ids)
        for row in source.execute(_select_sql(spec, schema=None))
    )
    with destination.cursor() as cursor:
        cursor.execute(_select_sql(spec, schema="backtest"))
        destination_rows = (
            dict(row)
            if isinstance(row, Mapping)
            else dict(zip(spec.columns, row, strict=True))
            for row in cursor
        )
        source_count, source_digest = _rows_digest(spec, source_rows)
        destination_count, destination_digest = _rows_digest(spec, destination_rows)
    return TableVerification(
        table=spec.name,
        source_rows=source_count,
        destination_rows=destination_count,
        source_digest=source_digest,
        destination_digest=destination_digest,
        verified=(
            source_count == destination_count
            and source_digest == destination_digest
        ),
    )


def _select_sql(
    spec: TableSpec,
    *,
    schema: str | None,
) -> str:
    table = f"{schema}.{spec.name}" if schema else spec.name
    return (
        f"SELECT {', '.join(spec.columns)} FROM {table} "
        f"ORDER BY {', '.join(spec.key_columns)}"
    )


def _rows_digest(
    spec: TableSpec,
    rows: Iterator[Mapping[str, Any]],
) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        normalized = {
            column: _normalized_value(spec, column, row[column])
            for column in spec.columns
        }
        digest.update(canonical_json(normalized).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def _normalized_value(spec: TableSpec, column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in spec.json_columns:
        return value if isinstance(value, (dict, list)) else json.loads(value)
    if column in spec.timestamp_columns:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return _aware(parsed).astimezone(timezone.utc).isoformat()
    if column == "bars_payload":
        payload = bytes(value)
        return {"length": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprint(path: Path) -> tuple[tuple[str, int, str], ...]:
    files = (path, Path(f"{path}-wal"))
    fingerprints: list[tuple[str, int, str]] = []
    for candidate in files:
        if not candidate.exists():
            continue
        size = candidate.stat().st_size
        # SQLite may create/remove an empty WAL merely by opening and closing
        # the last connection.  It contains no committed pages and must not be
        # treated as a source-data mutation.
        if candidate != path and size == 0:
            continue
        fingerprints.append((candidate.name, size, _file_sha256(candidate)))
    return tuple(fingerprints)
