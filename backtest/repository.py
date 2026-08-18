"""Repository port plus shared JSON-record implementation for backtest history."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from threading import RLock
from typing import Any, Iterator, Mapping, Protocol

from backtest.domain import canonical_json


class BacktestRepository(Protocol):
    def upsert_strategy_definition(self, definition: Mapping[str, Any]) -> bool:
        ...

    def list_strategy_definitions(
        self,
        *,
        role: str | None = None,
        session_phase: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def create_job(self, record: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def create_job_once(
        self,
        record: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        ...

    def get_job(self, job_id: str) -> dict[str, Any]:
        ...

    def list_jobs(self) -> list[dict[str, Any]]:
        ...

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        ...

    def upsert_dataset(self, manifest: Mapping[str, Any], status: str) -> None:
        ...

    def list_datasets(self) -> list[dict[str, Any]]:
        ...

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        ...

    def upsert_history_partition(self, partition: Mapping[str, Any]) -> None:
        ...

    def list_history_partitions(self, job_id: str) -> list[dict[str, Any]]:
        ...

    def iter_history_partition_payloads(self, job_id: str) -> Iterator[dict[str, Any]]:
        ...

    def create_run(self, record: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        ...

    def get_run(self, run_id: str) -> dict[str, Any]:
        ...

    def list_runs(self) -> list[dict[str, Any]]:
        ...

    def update_run(self, run_id: str, **changes: Any) -> dict[str, Any]:
        ...

    def save_result(self, run_id: str, result: Mapping[str, Any]) -> None:
        ...

    def get_result(self, run_id: str) -> dict[str, Any]:
        ...

    def save_comparison(self, comparison: Mapping[str, Any]) -> None:
        ...

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        ...


class _JsonBacktestRepository:
    """Shared DB-API implementation; data fields stay queryable by run/id.

    The immutable full projections are JSON/JSONB payloads while decisions,
    trades, and daily equity also have their own rows for bounded API reads.
    """

    def __init__(
        self,
        connection: Any,
        *,
        placeholder: str,
        json_type: str,
        blob_type: str,
    ) -> None:
        self._connection = connection
        self._placeholder = placeholder
        self._json_type = json_type
        self._blob_type = blob_type
        self._lock = RLock()
        self._apply_schema()

    def close(self) -> None:
        self._connection.close()

    def upsert_strategy_definition(self, definition: Mapping[str, Any]) -> bool:
        """Insert an immutable strategy version, rejecting digest drift."""

        required = ("strategy_id", "version", "role", "session_phase", "definition_digest")
        missing = [field for field in required if not definition.get(field)]
        if missing:
            raise ValueError(f"策略定義缺少欄位：{', '.join(missing)}")
        strategy_id = str(definition["strategy_id"])
        version = str(definition["version"])
        with self._transaction() as cursor:
            self._execute(
                cursor,
                "SELECT definition_digest FROM strategy_definitions WHERE strategy_id = ? AND version = ?",
                (strategy_id, version),
            )
            existing = cursor.fetchone()
            if existing is not None:
                row = self._row(cursor, existing)
                if row["definition_digest"] != definition["definition_digest"]:
                    raise ValueError(
                        f"策略版本已存在且內容不同：{strategy_id}:{version}；請建立新版本"
                    )
                return False
            now = _now()
            self._execute(
                cursor,
                """
                INSERT INTO strategy_definitions (
                    strategy_id, version, role, side, session_phase, status,
                    display_name_zh_tw, execution_binding, source,
                    definition_digest, definition_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id,
                    version,
                    str(definition["role"]),
                    definition.get("side"),
                    str(definition["session_phase"]),
                    str(definition.get("status", "ACTIVE")),
                    str(definition.get("display_name_zh_tw", strategy_id)),
                    str(definition.get("execution_binding") or ""),
                    str(definition.get("source", "DATABASE")),
                    str(definition["definition_digest"]),
                    _json(dict(definition)),
                    now,
                    now,
                ),
            )
            return True

    def list_strategy_definitions(
        self,
        *,
        role: str | None = None,
        session_phase: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (("role", role), ("session_phase", session_phase), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._cursor() as cursor:
            self._execute(
                cursor,
                "SELECT definition_json FROM strategy_definitions"
                f"{where} ORDER BY role, session_phase, strategy_id, version",
                values,
            )
            return [_decode_json(raw[0] if not isinstance(raw, Mapping) else raw["definition_json"]) for raw in cursor.fetchall()]

    def create_job(self, record: Mapping[str, Any]) -> dict[str, Any]:
        with self._transaction() as cursor:
            self._execute(
                cursor,
                """
                INSERT INTO backtest_jobs (
                    job_id, kind, status, request_json, resource_id, progress,
                    progress_message, created_at, updated_at, error_message
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL)
                """,
                (
                    record["job_id"],
                    record["kind"],
                    record["status"],
                    _json(record["request"]),
                    record.get("progress", 0.0),
                    record.get("progress_message", "已建立工作"),
                    record["created_at"],
                    record["created_at"],
                ),
            )
            self._execute(cursor, "SELECT * FROM backtest_jobs WHERE job_id = ?", (record["job_id"],))
            return self._job_payload(self._row(cursor, cursor.fetchone()))

    def create_job_once(
        self,
        record: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim a deterministic job id across scheduler processes."""

        with self._transaction() as cursor:
            self._execute(
                cursor,
                """
                INSERT INTO backtest_jobs (
                    job_id, kind, status, request_json, resource_id, progress,
                    progress_message, created_at, updated_at, error_message
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL)
                ON CONFLICT(job_id) DO NOTHING
                """,
                (
                    record["job_id"],
                    record["kind"],
                    record["status"],
                    _json(record["request"]),
                    record.get("progress", 0.0),
                    record.get("progress_message", "已建立工作"),
                    record["created_at"],
                    record["created_at"],
                ),
            )
            created = cursor.rowcount == 1
            self._execute(cursor, "SELECT * FROM backtest_jobs WHERE job_id = ?", (record["job_id"],))
            return self._job_payload(self._row(cursor, cursor.fetchone())), created

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_jobs WHERE job_id = ?", (job_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到背景工作：{job_id}")
            return self._job_payload(self._row(cursor, raw))

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_jobs ORDER BY updated_at DESC")
            return [self._job_payload(self._row(cursor, raw)) for raw in cursor.fetchall()]

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"status", "resource_id", "progress", "progress_message", "error_message"}
        invalid = set(changes) - allowed
        if invalid:
            raise ValueError(f"不可更新背景工作欄位：{', '.join(sorted(invalid))}")
        fields = [f"{key} = ?" for key in changes]
        values = list(changes.values())
        fields.append("updated_at = ?")
        values.append(_now())
        values.append(job_id)
        with self._transaction() as cursor:
            self._execute(cursor, f"UPDATE backtest_jobs SET {', '.join(fields)} WHERE job_id = ?", values)
            if cursor.rowcount == 0:
                raise KeyError(f"找不到背景工作：{job_id}")
            self._execute(cursor, "SELECT * FROM backtest_jobs WHERE job_id = ?", (job_id,))
            return self._job_payload(self._row(cursor, cursor.fetchone()))

    def upsert_dataset(self, manifest: Mapping[str, Any], status: str) -> None:
        payload = _json(manifest)
        with self._transaction() as cursor:
            self._execute(
                cursor,
                """
                INSERT INTO backtest_datasets (dataset_id, status, manifest_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    status = excluded.status,
                    manifest_json = excluded.manifest_json,
                    updated_at = excluded.updated_at
                """,
                (
                    manifest["dataset_id"],
                    status,
                    payload,
                    manifest["created_at"],
                    _now(),
                ),
            )

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_datasets ORDER BY created_at DESC")
            return [self._dataset_payload(self._row(cursor, raw)) for raw in cursor.fetchall()]

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_datasets WHERE dataset_id = ?", (dataset_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到歷史資料集：{dataset_id}")
            return self._dataset_payload(self._row(cursor, raw))

    def upsert_history_partition(self, partition: Mapping[str, Any]) -> None:
        """Checkpoint one complete symbol atomically for safe CLI resume."""

        with self._transaction() as cursor:
            self._execute(
                cursor,
                """
                INSERT INTO backtest_history_partitions (
                    job_id, symbol, name, market, start_date, end_date,
                    bar_count, bars_sha256, bars_payload, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, symbol) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    bar_count = excluded.bar_count,
                    bars_sha256 = excluded.bars_sha256,
                    bars_payload = excluded.bars_payload,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    partition["job_id"],
                    partition["symbol"],
                    partition.get("name", ""),
                    partition.get("market", ""),
                    partition.get("start_date"),
                    partition.get("end_date"),
                    int(partition["bar_count"]),
                    partition["bars_sha256"],
                    partition["bars_payload"],
                    partition.get("error_message"),
                    partition.get("created_at", _now()),
                    _now(),
                ),
            )

    def list_history_partitions(self, job_id: str) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            self._execute(
                cursor,
                """
                SELECT job_id, symbol, name, market, start_date, end_date,
                       bar_count, bars_sha256, error_message, created_at, updated_at
                FROM backtest_history_partitions
                WHERE job_id = ?
                ORDER BY symbol
                """,
                (job_id,),
            )
            return [self._history_partition_payload(self._row(cursor, raw)) for raw in cursor.fetchall()]

    def iter_history_partition_payloads(self, job_id: str) -> Iterator[dict[str, Any]]:
        """Yield one compressed symbol at a time instead of loading all blobs."""

        with self._cursor() as cursor:
            self._execute(
                cursor,
                """
                SELECT job_id, symbol, name, market, start_date, end_date,
                       bar_count, bars_sha256, bars_payload, error_message,
                       created_at, updated_at
                FROM backtest_history_partitions
                WHERE job_id = ?
                ORDER BY symbol
                """,
                (job_id,),
            )
            while True:
                rows = cursor.fetchmany(1)
                if not rows:
                    return
                row = self._history_partition_payload(self._row(cursor, rows[0]))
                row["bars_payload"] = bytes(row["bars_payload"])
                yield row

    def create_run(self, record: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._transaction() as cursor:
            self._execute(
                cursor,
                "SELECT * FROM backtest_runs WHERE idempotency_key = ?",
                (record["idempotency_key"],),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return self._run_payload(self._row(cursor, existing)), True
            self._execute(
                cursor,
                """
                INSERT INTO backtest_runs (
                    run_id, idempotency_key, status, config_json, config_digest,
                    dataset_id, dataset_digest, progress, progress_message,
                    created_at, updated_at, error_message, result_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    record["run_id"],
                    record["idempotency_key"],
                    record["status"],
                    _json(record["config"]),
                    record["config_digest"],
                    record["dataset_id"],
                    record["dataset_digest"],
                    0.0,
                    "已建立回測工作",
                    record["created_at"],
                    record["created_at"],
                ),
            )
            self._execute(cursor, "SELECT * FROM backtest_runs WHERE run_id = ?", (record["run_id"],))
            return self._run_payload(self._row(cursor, cursor.fetchone())), False

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到回測工作：{run_id}")
            return self._run_payload(self._row(cursor, raw))

    def list_runs(self) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT * FROM backtest_runs ORDER BY created_at DESC")
            return [self._run_payload(self._row(cursor, raw)) for raw in cursor.fetchall()]

    def update_run(self, run_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"status", "progress", "progress_message", "error_message", "result_digest"}
        invalid = set(changes) - allowed
        if invalid:
            raise ValueError(f"不可更新回測欄位：{', '.join(sorted(invalid))}")
        if not changes:
            return self.get_run(run_id)
        fields = [f"{key} = ?" for key in changes]
        values = list(changes.values())
        fields.append("updated_at = ?")
        values.append(_now())
        values.append(run_id)
        with self._transaction() as cursor:
            self._execute(cursor, f"UPDATE backtest_runs SET {', '.join(fields)} WHERE run_id = ?", values)
            if cursor.rowcount == 0:
                raise KeyError(f"找不到回測工作：{run_id}")
            self._execute(cursor, "SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,))
            return self._run_payload(self._row(cursor, cursor.fetchone()))

    def save_result(self, run_id: str, result: Mapping[str, Any]) -> None:
        summary = result["summary"]
        with self._transaction() as cursor:
            self._execute(cursor, "SELECT 1 FROM backtest_runs WHERE run_id = ?", (run_id,))
            if cursor.fetchone() is None:
                raise KeyError(f"找不到回測工作：{run_id}")
            # A completed run is an audit record.  Retrying or changing a
            # strategy must create a new run instead of silently replacing its
            # fills, decisions, or result digest.
            self._execute(cursor, "SELECT 1 FROM backtest_results WHERE run_id = ?", (run_id,))
            if cursor.fetchone() is not None:
                raise ValueError(f"回測結果已封存，不能覆寫：{run_id}")
            self._execute(
                cursor,
                """
                INSERT INTO backtest_results (run_id, result_json, summary_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, _json(result), _json(summary), _now()),
            )
            for decision in result.get("decisions", []):
                self._execute(
                    cursor,
                    "INSERT INTO backtest_decisions (run_id, decision_id, symbol, event_at, side, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        decision["decision_id"],
                        decision["symbol"],
                        decision["event_at"],
                        decision["side"],
                        _json(decision),
                    ),
                )
            for trade in result.get("trades", []):
                self._execute(
                    cursor,
                    "INSERT INTO backtest_trades (run_id, trade_id, symbol, entry_at, exit_at, net_pnl, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        trade["trade_id"],
                        trade["symbol"],
                        trade["entry"]["filled_at"],
                        trade["exit"]["filled_at"],
                        trade["net_pnl"],
                        _json(trade),
                    ),
                )
            for point in result.get("daily_equity", []):
                self._execute(
                    cursor,
                    "INSERT INTO backtest_daily_equity (run_id, session_date, equity, payload_json) VALUES (?, ?, ?, ?)",
                    (run_id, point["date"], point["equity"], _json(point)),
                )

    def get_result(self, run_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT result_json FROM backtest_results WHERE run_id = ?", (run_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"回測工作尚未產生結果：{run_id}")
            value = self._row(cursor, raw)["result_json"]
        return _decode_json(value)

    def list_trades(self, run_id: str, *, offset: int = 0, limit: int = 100) -> tuple[list[dict[str, Any]], int]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT COUNT(*) AS total FROM backtest_trades WHERE run_id = ?", (run_id,))
            total = int(self._row(cursor, cursor.fetchone())["total"])
            self._execute(
                cursor,
                "SELECT payload_json FROM backtest_trades WHERE run_id = ? ORDER BY entry_at LIMIT ? OFFSET ?",
                (run_id, limit, offset),
            )
            rows = [_decode_json(self._row(cursor, raw)["payload_json"]) for raw in cursor.fetchall()]
        return rows, total

    def save_comparison(self, comparison: Mapping[str, Any]) -> None:
        with self._transaction() as cursor:
            self._execute(
                cursor,
                """
                INSERT INTO backtest_comparisons (comparison_id, baseline_run_id, challenger_run_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(comparison_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (
                    comparison["comparison_id"],
                    comparison["baseline_run_id"],
                    comparison["challenger_run_id"],
                    _json(comparison),
                    _now(),
                ),
            )

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            self._execute(cursor, "SELECT payload_json FROM backtest_comparisons WHERE comparison_id = ?", (comparison_id,))
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(f"找不到回測比較：{comparison_id}")
            return _decode_json(self._row(cursor, raw)["payload_json"])

    def _apply_schema(self) -> None:
        schema = _SCHEMA.replace("{json_type}", self._json_type).replace("{blob_type}", self._blob_type)
        with self._transaction() as cursor:
            for statement in schema.split(";\n"):
                if statement.strip():
                    self._execute(cursor, statement)

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def _execute(self, cursor: Any, sql: str, values: Any = ()) -> None:
        cursor.execute(sql.replace("?", self._placeholder), values)

    @staticmethod
    def _row(cursor: Any, raw: Any) -> dict[str, Any]:
        if isinstance(raw, Mapping):
            return dict(raw)
        return {column[0]: raw[index] for index, column in enumerate(cursor.description)}

    def _row_from_raw(self, raw: Any, cursor: Any) -> dict[str, Any]:
        return self._row(cursor, raw)

    @staticmethod
    def _dataset_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        payload = _decode_json(row["manifest_json"])
        return {**payload, "status": row["status"], "updated_at": row["updated_at"]}

    @staticmethod
    def _history_partition_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "job_id": row["job_id"],
            "symbol": row["symbol"],
            "name": row["name"],
            "market": row["market"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "bar_count": int(row["bar_count"]),
            "bars_sha256": row["bars_sha256"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "bars_payload" in row:
            payload["bars_payload"] = row["bars_payload"]
        return payload

    @staticmethod
    def _run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "config": _decode_json(row["config_json"]),
            "config_digest": row["config_digest"],
            "dataset_id": row["dataset_id"],
            "dataset_digest": row["dataset_digest"],
            "progress": float(row["progress"]),
            "progress_message": row["progress_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_message": row["error_message"],
            "result_digest": row["result_digest"],
        }

    @staticmethod
    def _job_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "status": row["status"],
            "request": _decode_json(row["request_json"]),
            "resource_id": row["resource_id"],
            "progress": float(row["progress"]),
            "progress_message": row["progress_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_message": row["error_message"],
        }


def _json(value: Any) -> str:
    return canonical_json(value)


def _decode_json(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else json.loads(value)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_datasets (
    dataset_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json {json_type} NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_definitions (
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    role TEXT NOT NULL,
    side TEXT NULL,
    session_phase TEXT NOT NULL,
    status TEXT NOT NULL,
    display_name_zh_tw TEXT NOT NULL,
    execution_binding TEXT NOT NULL,
    source TEXT NOT NULL,
    definition_digest TEXT NOT NULL,
    definition_json {json_type} NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (strategy_id, version)
);
CREATE TABLE IF NOT EXISTS backtest_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json {json_type} NOT NULL,
    resource_id TEXT NULL,
    progress REAL NOT NULL,
    progress_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NULL
);
CREATE TABLE IF NOT EXISTS backtest_history_partitions (
    job_id TEXT NOT NULL REFERENCES backtest_jobs(job_id),
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    start_date TEXT NULL,
    end_date TEXT NULL,
    bar_count INTEGER NOT NULL,
    bars_sha256 TEXT NOT NULL,
    bars_payload {blob_type} NOT NULL,
    error_message TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (job_id, symbol)
);
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    config_json {json_type} NOT NULL,
    config_digest TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_digest TEXT NOT NULL,
    progress REAL NOT NULL,
    progress_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NULL,
    result_digest TEXT NULL
);
CREATE TABLE IF NOT EXISTS backtest_results (
    run_id TEXT PRIMARY KEY REFERENCES backtest_runs(run_id),
    result_json {json_type} NOT NULL,
    summary_json {json_type} NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtest_decisions (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    decision_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_at TEXT NOT NULL,
    side TEXT NOT NULL,
    payload_json {json_type} NOT NULL,
    PRIMARY KEY (run_id, decision_id)
);
CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_at TEXT NOT NULL,
    exit_at TEXT NOT NULL,
    net_pnl REAL NOT NULL,
    payload_json {json_type} NOT NULL,
    PRIMARY KEY (run_id, trade_id)
);
CREATE TABLE IF NOT EXISTS backtest_daily_equity (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    session_date TEXT NOT NULL,
    equity REAL NOT NULL,
    payload_json {json_type} NOT NULL,
    PRIMARY KEY (run_id, session_date)
);
CREATE TABLE IF NOT EXISTS backtest_comparisons (
    comparison_id TEXT PRIMARY KEY,
    baseline_run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    challenger_run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    payload_json {json_type} NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS backtest_runs_created_index ON backtest_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS strategy_definitions_role_phase_index ON strategy_definitions (role, session_phase, status);
CREATE INDEX IF NOT EXISTS backtest_jobs_created_index ON backtest_jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS backtest_history_partitions_job_symbol_index ON backtest_history_partitions (job_id, symbol);
CREATE INDEX IF NOT EXISTS backtest_decisions_run_event_index ON backtest_decisions (run_id, event_at);
CREATE INDEX IF NOT EXISTS backtest_trades_run_entry_index ON backtest_trades (run_id, entry_at);
"""
