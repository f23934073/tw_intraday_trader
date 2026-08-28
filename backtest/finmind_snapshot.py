"""Consistent, content-addressed plans for FinMind backtest snapshots.

This module is deliberately read-only with respect to the acquisition store.
It creates a SQLite online backup, validates the copied evidence, produces the
G1 plan artifact, and exposes G2 per-symbol streams to the existing Dataset
catalog. PostgreSQL registration remains behind a later gate.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from itertools import groupby
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from backtest.domain import HistoricalBar, canonical_json
from backtest.finmind_history import (
    SOURCE,
    SOURCE_VERSION,
    TAIPEI,
    VOLUME_UNIT,
    FinMindResponse,
    normalize_kbar_response,
    trading_dates_from_response,
)
from backtest.finmind_source_repair import (
    RepairResolution,
    load_repair_resolution,
)


PLAN_SCHEMA_VERSION = "finmind-backtest-snapshot-plan-v1"
REFERENCE_DATASET = "TaiwanStockInfo"
REFERENCE_MAPPING_CONTRACT = "FINMIND_CURRENT_LISTING_REFERENCE_V1"
AMOUNT_KIND = "DERIVED_CLOSE_X_VOLUME_PROXY"
VWAP_SEMANTIC = "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY"
DATASET_ID_PREFIX = "dataset-finmind-sponsor-sha256-"
DATASET_ISSUES = (
    "AMOUNT_DERIVED_PROXY",
    "CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",
    "PARTIAL_MARKET_UNIVERSE",
    "RAW_PRICE_UNADJUSTED",
    "REFERENCE_METADATA_CURRENT_NOT_PIT",
)
_REQUIRED_TABLE_COLUMNS = {
    "finmind_history_jobs": {
        "job_id",
        "source",
        "source_version",
        "start_date",
        "end_date",
        "symbols_json",
        "trading_dates_json",
        "calendar_raw_sha256",
        "calendar_raw_payload",
        "volume_unit",
    },
    "finmind_history_partitions": {
        "job_id",
        "symbol",
        "session_date",
        "status",
        "bar_count",
        "first_event_at",
        "last_event_at",
        "raw_sha256",
        "raw_payload",
        "canonical_sha256",
    },
}


class FinMindSnapshotError(ValueError):
    """The copied acquisition evidence cannot produce a safe snapshot plan."""


class FinMindSnapshotConflict(FinMindSnapshotError):
    """Two durable rows disagree about one semantic identity."""


@dataclass(frozen=True)
class FinMindSnapshotPlan:
    """Immutable projections saved by the G1 planning command."""

    identity: Mapping[str, Any]
    plan_identity_digest: str
    handoff_evidence: Mapping[str, Any]
    handoff_evidence_digest: str
    selection_audit: Mapping[str, Any]
    selection_audit_digest: str
    locators: Mapping[str, Any]
    operation_audit: Mapping[str, Any]
    operation_audit_digest: str
    schema_version: str = PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return json.loads(
            canonical_json(
                {
                    "schema_version": self.schema_version,
                    "identity": self.identity,
                    "plan_identity_digest": self.plan_identity_digest,
                    "handoff_evidence": self.handoff_evidence,
                    "handoff_evidence_digest": self.handoff_evidence_digest,
                    "selection_audit": self.selection_audit,
                    "selection_audit_digest": self.selection_audit_digest,
                    "locators": self.locators,
                    "operation_audit": self.operation_audit,
                    "operation_audit_digest": self.operation_audit_digest,
                }
            )
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FinMindSnapshotPlan":
        required = {
            "schema_version",
            "identity",
            "plan_identity_digest",
            "handoff_evidence",
            "handoff_evidence_digest",
            "selection_audit",
            "selection_audit_digest",
            "locators",
            "operation_audit",
            "operation_audit_digest",
        }
        if set(value) != required:
            raise FinMindSnapshotError("snapshot plan fields do not match schema")
        if value.get("schema_version") != PLAN_SCHEMA_VERSION:
            raise FinMindSnapshotError("unsupported snapshot plan schema_version")
        mappings: dict[str, Mapping[str, Any]] = {}
        for field in (
            "identity",
            "handoff_evidence",
            "selection_audit",
            "locators",
            "operation_audit",
        ):
            candidate = value.get(field)
            if not isinstance(candidate, Mapping):
                raise FinMindSnapshotError(f"snapshot plan {field} must be an object")
            mappings[field] = json.loads(canonical_json(candidate))
        plan = cls(
            identity=mappings["identity"],
            plan_identity_digest=str(value["plan_identity_digest"]),
            handoff_evidence=mappings["handoff_evidence"],
            handoff_evidence_digest=str(value["handoff_evidence_digest"]),
            selection_audit=mappings["selection_audit"],
            selection_audit_digest=str(value["selection_audit_digest"]),
            locators=mappings["locators"],
            operation_audit=mappings["operation_audit"],
            operation_audit_digest=str(value["operation_audit_digest"]),
        )
        plan.verify_digests()
        return plan

    def verify_digests(self) -> None:
        checks = (
            ("plan identity", self.identity, self.plan_identity_digest),
            ("handoff evidence", self.handoff_evidence, self.handoff_evidence_digest),
            ("selection audit", self.selection_audit, self.selection_audit_digest),
            ("operation audit", self.operation_audit, self.operation_audit_digest),
        )
        for label, projection, expected in checks:
            observed = _digest(projection)
            if observed != expected:
                raise FinMindSnapshotError(f"snapshot plan {label} digest mismatch")


@dataclass(frozen=True)
class _Job:
    job_id: str
    symbols: tuple[str, ...]
    contract: Mapping[str, Any]


@dataclass(frozen=True)
class _Inspection:
    contract: Mapping[str, Any]
    compatible_jobs: tuple[_Job, ...]
    excluded_jobs: tuple[Mapping[str, Any], ...]
    included_partitions: tuple[Mapping[str, Any], ...]
    included_symbols: tuple[str, ...]
    excluded_symbols: tuple[Mapping[str, Any], ...]
    counts: Mapping[str, int]
    snapshot_identity_at: str
    canonical_payload_bytes: int


class FinMindSemanticSnapshotReader:
    """Read and verify one copied FinMind acquisition database."""

    def __init__(self, snapshot_path: Path) -> None:
        self._snapshot_path = Path(snapshot_path)

    @staticmethod
    def backup_source(
        source_path: Path,
        snapshot_path: Path,
        *,
        on_published: Callable[[Path], None] | None = None,
    ) -> Path:
        """Publish one SQLite online backup without overwriting prior evidence."""

        source = Path(source_path)
        destination = Path(snapshot_path)
        if not source.is_file():
            raise FinMindSnapshotError(f"FinMind source SQLite does not exist: {source}")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.tmp"
        )
        source_connection: sqlite3.Connection | None = None
        target_connection: sqlite3.Connection | None = None
        try:
            try:
                source_connection = _connect_read_only(source)
                target_connection = sqlite3.connect(temporary)
                source_connection.backup(target_connection)
                target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                target_connection.commit()
                target_connection.close()
                target_connection = None
                os.link(temporary, destination)
                if on_published is not None:
                    on_published(destination)
            finally:
                if target_connection is not None:
                    target_connection.close()
                if source_connection is not None:
                    source_connection.close()
        except BaseException:
            if _paths_share_inode(temporary, destination):
                destination.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def inspect(self) -> _Inspection:
        """Validate job compatibility, partitions, and complete-symbol selection."""

        connection = _connect_read_only(self._snapshot_path)
        try:
            _verify_schema(connection)
            jobs, excluded_jobs = _load_compatible_jobs(connection)
            return _inspect_partitions(connection, jobs, excluded_jobs)
        finally:
            connection.close()

    @contextmanager
    def open_symbol_bar_streams(
        self,
        plan: FinMindSnapshotPlan,
    ) -> Iterator[tuple[Iterator[HistoricalBar], ...]]:
        """Open validated per-symbol streams for the catalog's bounded merge."""

        plan.verify_digests()
        identity = plan.identity
        raw_partitions = identity.get("included_partitions")
        selection = identity.get("selection")
        reference = identity.get("reference")
        if not isinstance(raw_partitions, list):
            raise FinMindSnapshotError("snapshot plan included_partitions is invalid")
        if not isinstance(selection, Mapping) or not isinstance(reference, Mapping):
            raise FinMindSnapshotError("snapshot plan selection/reference is invalid")
        raw_symbols = selection.get("included_symbols")
        raw_mapping = reference.get("mapping")
        if not isinstance(raw_symbols, list) or not isinstance(raw_mapping, list):
            raise FinMindSnapshotError("snapshot plan symbol/reference mapping is invalid")
        symbols = tuple(str(value) for value in raw_symbols)
        if not symbols or tuple(sorted(set(symbols))) != symbols:
            raise FinMindSnapshotError("snapshot plan included symbols are not canonical")
        reference_by_symbol: dict[str, tuple[str, str]] = {}
        for item in raw_mapping:
            if not isinstance(item, Mapping):
                raise FinMindSnapshotError("snapshot plan reference row is invalid")
            symbol = str(item.get("symbol") or "")
            name = str(item.get("name") or "")
            market = str(item.get("market") or "")
            if symbol in reference_by_symbol or not name or not market:
                raise FinMindSnapshotError("snapshot plan reference mapping is invalid")
            reference_by_symbol[symbol] = (name, market)
        if set(reference_by_symbol) != set(symbols):
            raise FinMindSnapshotError("snapshot plan reference coverage is incomplete")

        partitions_by_symbol: dict[str, list[Mapping[str, Any]]] = {
            symbol: [] for symbol in symbols
        }
        previous_identity: tuple[str, str] | None = None
        for item in raw_partitions:
            if not isinstance(item, Mapping):
                raise FinMindSnapshotError("snapshot plan partition row is invalid")
            symbol = str(item.get("symbol") or "")
            session_text = str(item.get("session_date") or "")
            identity_key = (symbol, session_text)
            if symbol not in partitions_by_symbol or (
                previous_identity is not None and identity_key <= previous_identity
            ):
                raise FinMindSnapshotError("snapshot plan partition order is invalid")
            previous_identity = identity_key
            partitions_by_symbol[symbol].append(item)

        connection = _connect_read_only(self._snapshot_path)
        try:
            _verify_schema(connection)
            streams = tuple(
                self._iter_symbol_bars(
                    connection,
                    symbol=symbol,
                    partitions=partitions_by_symbol[symbol],
                    name=reference_by_symbol[symbol][0],
                    market=reference_by_symbol[symbol][1],
                )
                for symbol in symbols
            )
            yield streams
        finally:
            connection.close()

    @staticmethod
    def _iter_symbol_bars(
        connection: sqlite3.Connection,
        *,
        symbol: str,
        partitions: Sequence[Mapping[str, Any]],
        name: str,
        market: str,
    ) -> Iterator[HistoricalBar]:
        previous_timestamp: datetime | None = None
        for partition in partitions:
            session_text = str(partition.get("session_date") or "")
            try:
                session_date = date.fromisoformat(session_text)
            except ValueError as error:
                raise FinMindSnapshotError(
                    f"invalid planned session date: {symbol}/{session_text}"
                ) from error
            raw_job_ids = partition.get("contributing_job_ids")
            if not isinstance(raw_job_ids, list) or not raw_job_ids:
                raise FinMindSnapshotError(
                    f"missing partition lineage: {symbol}/{session_text}"
                )
            job_ids = tuple(str(value) for value in raw_job_ids)
            if tuple(sorted(set(job_ids))) != job_ids:
                raise FinMindSnapshotError(
                    f"non-canonical partition lineage: {symbol}/{session_text}"
                )
            planned_repair_lineage = partition.get("repair_lineage", [])
            if not isinstance(planned_repair_lineage, list):
                raise FinMindSnapshotError(
                    f"invalid repair lineage: {symbol}/{session_text}"
                )
            selected_bars: tuple[HistoricalBar, ...] | None = None
            observed_repair_lineage: list[Mapping[str, str]] = []
            for job_id in job_ids:
                row = connection.execute(
                    """
                    SELECT job_id, symbol, session_date, status, bar_count,
                           first_event_at, last_event_at, raw_sha256, raw_payload,
                           canonical_sha256
                    FROM finmind_history_partitions
                    WHERE job_id = ? AND symbol = ? AND session_date = ?
                    """,
                    (job_id, symbol, session_text),
                ).fetchone()
                if row is None:
                    raise FinMindSnapshotError(
                        f"planned partition is missing: {job_id}/{symbol}/{session_text}"
                    )
                resolution = load_repair_resolution(
                    connection,
                    job_id=job_id,
                    symbol=symbol,
                    session_date=session_date,
                )
                if resolution is not None and not resolution.is_active:
                    raise FinMindSnapshotError(
                        f"source repair is pending: {job_id}/{symbol}/{session_text}"
                    )
                if _effective_partition_metadata(
                    row, resolution
                ) != _planned_partition_projection(partition):
                    raise FinMindSnapshotError(
                        f"planned partition metadata drift: {job_id}/{symbol}/{session_text}"
                    )
                bars = (
                    resolution.bars
                    if resolution is not None and resolution.is_active
                    else _verified_partition_bars(row, symbol, session_date)
                )
                if resolution is not None and resolution.is_active:
                    observed_repair_lineage.append(resolution.lineage(job_id))
                if selected_bars is None:
                    selected_bars = bars
                elif bars != selected_bars:
                    raise FinMindSnapshotConflict(
                        f"planned duplicate payload conflict: {symbol}/{session_text}"
                    )
            if observed_repair_lineage != planned_repair_lineage:
                raise FinMindSnapshotError(
                    f"planned repair lineage drift: {symbol}/{session_text}"
                )
            for bar in selected_bars or ():
                if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
                    raise FinMindSnapshotError(
                        f"symbol Kbar order conflict: {symbol}/{bar.timestamp.isoformat()}"
                    )
                previous_timestamp = bar.timestamp
                yield replace(bar, name=name, market=market)

    def plan(
        self,
        *,
        stock_info_raw: Path,
        actor: str,
        planned_at: datetime,
        source_path: Path | None = None,
        plan_output_parent: Path | None = None,
    ) -> FinMindSnapshotPlan:
        """Build the canonical semantic identity and non-identity audit projections."""

        if not self._snapshot_path.is_file():
            raise FinMindSnapshotError(
                f"FinMind copied SQLite does not exist: {self._snapshot_path}"
            )
        normalized_actor = actor.strip()
        if not normalized_actor:
            raise FinMindSnapshotError("snapshot plan actor cannot be blank")
        planned_timestamp = _canonical_timestamp(planned_at)
        inspection = self.inspect()
        reference = _load_reference_mapping(
            Path(stock_info_raw), inspection.included_symbols
        )
        volume_contract = {"unit": VOLUME_UNIT}
        amount_contract = {
            "is_actual_turnover": False,
            "kind": AMOUNT_KIND,
            "vwap_semantic": VWAP_SEMANTIC,
        }
        amount_contract["digest"] = _digest(amount_contract)
        contributing_job_ids = sorted(
            {
                job_id
                for partition in inspection.included_partitions
                for job_id in partition["contributing_job_ids"]
            }
        )
        source_projection = {
            "amount_contract": amount_contract,
            "contributing_job_ids": contributing_job_ids,
            "included_partitions": list(inspection.included_partitions),
            "reference": reference,
            "snapshot_identity_at": inspection.snapshot_identity_at,
            "source_contract": inspection.contract,
            "volume_contract": volume_contract,
        }
        source_digest = self.source_snapshot_digest(source_projection)
        included_partitions = list(inspection.included_partitions)
        included_counts = {
            "bar_count": sum(int(row["bar_count"]) for row in included_partitions),
            "empty_partition_count": sum(
                row["status"] == "EMPTY" for row in included_partitions
            ),
            "included_partition_count": len(included_partitions),
            "included_symbol_count": len(inspection.included_symbols),
            "ready_partition_count": sum(
                row["status"] == "READY" for row in included_partitions
            ),
        }
        issues = list(DATASET_ISSUES)
        if any(
            partition.get("repair_lineage") for partition in included_partitions
        ):
            issues.append("ALTERNATE_SOURCE_REPAIR")
        identity = {
            "amount_contract": amount_contract,
            "contributing_job_ids": contributing_job_ids,
            "counts": included_counts,
            "dataset_id": f"{DATASET_ID_PREFIX}{source_digest}",
            "included_partitions": included_partitions,
            "issues": issues,
            "reference": reference,
            "research_eligible": False,
            "selection": {
                "included_symbols": list(inspection.included_symbols),
            },
            "snapshot_identity_at": inspection.snapshot_identity_at,
            "source_contract": inspection.contract,
            "source_snapshot_digest": source_digest,
            "universe_scope": "CURRENT_SNAPSHOT",
            "volume_contract": volume_contract,
        }
        selection_audit = {
            "compatible_job_ids": sorted(
                job.job_id for job in inspection.compatible_jobs
            ),
            "excluded_jobs": list(inspection.excluded_jobs),
            "excluded_symbols": list(inspection.excluded_symbols),
            "included_symbols": list(inspection.included_symbols),
            "snapshot_counts": inspection.counts,
        }
        handoff_evidence = {
            "copied_sqlite_sha256": _file_sha256(self._snapshot_path)
        }
        output_parent = Path(plan_output_parent or self._snapshot_path.parent)
        output_parent.mkdir(parents=True, exist_ok=True)
        expected_output_size = max(
            1,
            inspection.canonical_payload_bytes
            + inspection.counts["bar_count"] * 128,
        )
        free_bytes = shutil.disk_usage(output_parent).free
        operation_audit = {
            "actor": normalized_actor,
            "effective_paths": {
                "copied_sqlite": str(self._snapshot_path.resolve()),
                "live_source": (
                    str(Path(source_path).resolve()) if source_path is not None else None
                ),
                "plan_output_parent": str(output_parent.resolve()),
                "stock_info_raw": str(Path(stock_info_raw).resolve()),
            },
            "expected_output_size_bytes": expected_output_size,
            "free_space_evidence": {
                "available_bytes": free_bytes,
                "path": str(output_parent.resolve()),
                "sufficient": free_bytes >= expected_output_size,
            },
            "planned_at": planned_timestamp,
        }
        locators = {
            "copied_sqlite_path": str(self._snapshot_path.resolve()),
            "taiwan_stock_info_raw_path": str(Path(stock_info_raw).resolve()),
        }
        return FinMindSnapshotPlan(
            identity=identity,
            plan_identity_digest=_digest(identity),
            handoff_evidence=handoff_evidence,
            handoff_evidence_digest=_digest(handoff_evidence),
            selection_audit=selection_audit,
            selection_audit_digest=_digest(selection_audit),
            locators=locators,
            operation_audit=operation_audit,
            operation_audit_digest=_digest(operation_audit),
        )

    @staticmethod
    def source_snapshot_digest(projection: Mapping[str, Any]) -> str:
        return _digest(projection)


def save_snapshot_plan(plan: FinMindSnapshotPlan, path: Path) -> Path:
    """Save a canonical plan without replacing an existing review artifact."""

    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not isinstance(plan, FinMindSnapshotPlan):
        raise TypeError("plan must be a FinMindSnapshotPlan")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(plan.to_dict()) + "\n").encode("utf-8")
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, destination)
        except BaseException:
            if _paths_share_inode(temporary, destination):
                destination.unlink(missing_ok=True)
            raise
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _paths_share_inode(first: Path, second: Path) -> bool:
    """Return whether two existing paths are hard links to the same file."""

    try:
        return os.path.samefile(first, second)
    except (FileNotFoundError, OSError):
        return False


def load_snapshot_plan(path: Path) -> FinMindSnapshotPlan:
    source = Path(path)
    if not source.is_file():
        raise FinMindSnapshotError(f"snapshot plan does not exist: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FinMindSnapshotError("snapshot plan is not valid JSON") from error
    if not isinstance(value, Mapping):
        raise FinMindSnapshotError("snapshot plan must be a JSON object")
    return FinMindSnapshotPlan.from_dict(value)


def verify_snapshot_plan_handoff(
    plan: FinMindSnapshotPlan,
    *,
    snapshot_file: Path,
    stock_info_raw: Path,
) -> None:
    """Verify the physical files named by a saved plan before later execution."""

    plan.verify_digests()
    observed_snapshot = _file_sha256(Path(snapshot_file))
    expected_snapshot = str(plan.handoff_evidence.get("copied_sqlite_sha256") or "")
    if observed_snapshot != expected_snapshot:
        raise FinMindSnapshotError("snapshot handoff SHA-256 mismatch")
    observed_reference = _raw_body_sha256(Path(stock_info_raw))
    reference = plan.identity.get("reference")
    if not isinstance(reference, Mapping):
        raise FinMindSnapshotError("snapshot plan reference identity is missing")
    expected_reference = str(reference.get("raw_body_sha256") or "")
    if observed_reference != expected_reference:
        raise FinMindSnapshotError("stock-info raw-body SHA-256 mismatch")


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FinMindSnapshotError(f"SQLite file does not exist: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _verify_schema(connection: sqlite3.Connection) -> None:
    for table, required_columns in _REQUIRED_TABLE_COLUMNS.items():
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {str(row["name"]) for row in rows}
        missing = sorted(required_columns - columns)
        if missing:
            raise FinMindSnapshotError(
                f"FinMind snapshot schema missing {table} columns: {', '.join(missing)}"
            )


def _load_compatible_jobs(
    connection: sqlite3.Connection,
) -> tuple[tuple[_Job, ...], tuple[Mapping[str, Any], ...]]:
    rows = connection.execute(
        """
        SELECT job_id, source, source_version, start_date, end_date, symbols_json,
               trading_dates_json, calendar_raw_sha256, calendar_raw_payload,
               volume_unit
        FROM finmind_history_jobs
        ORDER BY job_id
        """
    )
    candidates: list[_Job] = []
    excluded: list[Mapping[str, Any]] = []
    for row in rows:
        job_id = str(row["job_id"])
        reasons: list[str] = []
        if row["source"] != SOURCE:
            reasons.append("UNSUPPORTED_SOURCE")
        if row["source_version"] != SOURCE_VERSION:
            reasons.append("UNSUPPORTED_SOURCE_VERSION")
        if row["volume_unit"] != VOLUME_UNIT:
            reasons.append("UNSUPPORTED_VOLUME_UNIT")
        if (
            row["trading_dates_json"] is None
            or row["calendar_raw_sha256"] is None
            or row["calendar_raw_payload"] is None
        ):
            reasons.append("CALENDAR_EVIDENCE_MISSING")
        if reasons:
            excluded.append({"job_id": job_id, "reason_codes": sorted(reasons)})
            continue
        try:
            start_date = date.fromisoformat(str(row["start_date"]))
            end_date = date.fromisoformat(str(row["end_date"]))
            raw_dates = json.loads(str(row["trading_dates_json"]))
            raw_symbols = json.loads(str(row["symbols_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise FinMindSnapshotError(f"invalid job contract: {job_id}") from error
        if start_date > end_date:
            raise FinMindSnapshotError(f"invalid requested date range: {job_id}")
        if not isinstance(raw_dates, list) or not isinstance(raw_symbols, list):
            raise FinMindSnapshotError(f"invalid job arrays: {job_id}")
        try:
            calendar_dates = tuple(
                sorted({date.fromisoformat(str(value)) for value in raw_dates})
            )
        except ValueError as error:
            raise FinMindSnapshotError(f"invalid trading calendar: {job_id}") from error
        if not calendar_dates or len(calendar_dates) != len(raw_dates):
            raise FinMindSnapshotError(f"non-unique or empty trading calendar: {job_id}")
        symbols = tuple(
            sorted({str(value).strip().upper() for value in raw_symbols if str(value).strip()})
        )
        if not symbols or len(symbols) != len(raw_symbols):
            raise FinMindSnapshotError(f"non-unique or empty job symbols: {job_id}")
        calendar_body = _gzip_body(bytes(row["calendar_raw_payload"]), "calendar")
        if hashlib.sha256(calendar_body).hexdigest() != row["calendar_raw_sha256"]:
            raise FinMindSnapshotError(f"calendar raw digest mismatch: {job_id}")
        calendar_response = _decode_response(calendar_body, "calendar")
        if (calendar_response.payload or {}).get("status") != 200:
            raise FinMindSnapshotError(f"calendar response status is invalid: {job_id}")
        observed_dates = trading_dates_from_response(
            calendar_response,
            start_date=start_date,
            end_date=end_date,
        )
        if observed_dates != calendar_dates:
            raise FinMindSnapshotError(f"calendar projection mismatch: {job_id}")
        calendar_values = [value.isoformat() for value in calendar_dates]
        contract = {
            "calendar_digest": _digest(calendar_values),
            "calendar_raw_sha256": str(row["calendar_raw_sha256"]),
            "end_date": end_date.isoformat(),
            "source": SOURCE,
            "source_version": SOURCE_VERSION,
            "start_date": start_date.isoformat(),
            "trading_dates": calendar_values,
            "volume_unit": VOLUME_UNIT,
        }
        candidates.append(_Job(job_id=job_id, symbols=symbols, contract=contract))
    if not candidates:
        raise FinMindSnapshotError("no compatible FinMind history jobs")
    grouped_contracts = {
        canonical_json(job.contract): job.contract for job in candidates
    }
    if len(grouped_contracts) != 1:
        raise FinMindSnapshotConflict(
            "multiple fully formed FinMind job compatibility families"
        )
    return tuple(candidates), tuple(excluded)


def _inspect_partitions(
    connection: sqlite3.Connection,
    jobs: Sequence[_Job],
    excluded_jobs: Sequence[Mapping[str, Any]],
) -> _Inspection:
    contract = jobs[0].contract
    calendar = tuple(date.fromisoformat(value) for value in contract["trading_dates"])
    expected_dates = set(calendar)
    declared_by_job = {job.job_id: set(job.symbols) for job in jobs}
    declared_symbols = sorted({symbol for job in jobs for symbol in job.symbols})
    placeholders = ",".join("?" for _ in jobs)
    cursor = connection.execute(
        f"""
        SELECT job_id, symbol, session_date, status, bar_count,
               first_event_at, last_event_at, raw_sha256, raw_payload,
               canonical_sha256
        FROM finmind_history_partitions
        WHERE job_id IN ({placeholders})
        ORDER BY symbol, session_date, job_id
        """,
        tuple(job.job_id for job in jobs),
    )
    included_partitions: list[Mapping[str, Any]] = []
    included_symbols: list[str] = []
    excluded_symbols: list[Mapping[str, Any]] = []
    observed_symbols: set[str] = set()
    counts = {
        "bar_count": 0,
        "empty_partition_count": 0,
        "excluded_symbol_count": 0,
        "included_partition_count": 0,
        "included_symbol_count": 0,
        "ready_partition_count": 0,
    }
    snapshot_identity_at: datetime | None = None
    canonical_payload_bytes = 0
    for symbol, symbol_rows in groupby(cursor, key=lambda row: str(row["symbol"])):
        observed_symbols.add(symbol)
        observed_dates: set[date] = set()
        invalid_dates: list[str] = []
        extra_dates: list[str] = []
        repair_pending_dates: list[str] = []
        symbol_partitions: list[Mapping[str, Any]] = []
        symbol_payload_bytes = 0
        for session_text, duplicate_rows_iter in groupby(
            symbol_rows, key=lambda row: str(row["session_date"])
        ):
            try:
                session_date = date.fromisoformat(session_text)
            except ValueError as error:
                raise FinMindSnapshotError(
                    f"invalid partition session date: {symbol}/{session_text}"
                ) from error
            duplicate_rows = list(duplicate_rows_iter)
            for row in duplicate_rows:
                job_id = str(row["job_id"])
                if symbol not in declared_by_job[job_id]:
                    raise FinMindSnapshotError(
                        f"partition symbol not declared by job: {job_id}/{symbol}"
                    )
            resolved_rows = [
                (
                    row,
                    load_repair_resolution(
                        connection,
                        job_id=str(row["job_id"]),
                        symbol=symbol,
                        session_date=session_date,
                    ),
                )
                for row in duplicate_rows
            ]
            pending_repairs = [
                resolution
                for _row, resolution in resolved_rows
                if resolution is not None and not resolution.is_active
            ]
            projections = {
                _effective_partition_metadata(row, resolution)
                for row, resolution in resolved_rows
            }
            if len(projections) != 1:
                raise FinMindSnapshotConflict(
                    f"conflicting duplicate partition: {symbol}/{session_text}"
                )
            observed_dates.add(session_date)
            status, bar_count, canonical_sha256, first_event_at, last_event_at = next(
                iter(projections)
            )
            if session_date not in expected_dates:
                extra_dates.append(session_text)
            if status not in {"READY", "EMPTY"}:
                invalid_dates.append(session_text)
            if pending_repairs:
                repair_pending_dates.append(session_text)
            elif status in {"READY", "EMPTY"}:
                observed_size: int | None = None
                for row, resolution in resolved_rows:
                    payload_size = _verify_effective_partition(
                        row,
                        resolution,
                        symbol,
                        session_date,
                    )
                    if observed_size is None:
                        observed_size = payload_size
                symbol_payload_bytes += observed_size or 0
            partition_projection: dict[str, Any] = {
                "bar_count": bar_count,
                "canonical_sha256": canonical_sha256,
                "contributing_job_ids": sorted(
                    str(row["job_id"]) for row in duplicate_rows
                ),
                "first_event_at": first_event_at,
                "last_event_at": last_event_at,
                "session_date": session_text,
                "status": status,
                "symbol": symbol,
            }
            repair_lineage = [
                resolution.lineage(str(row["job_id"]))
                for row, resolution in resolved_rows
                if resolution is not None and resolution.is_active
            ]
            if repair_lineage:
                partition_projection["repair_lineage"] = sorted(
                    repair_lineage, key=lambda value: str(value["job_id"])
                )
            symbol_partitions.append(partition_projection)
        missing_dates = sorted(expected_dates - observed_dates)
        reason_codes: list[str] = []
        if missing_dates:
            reason_codes.append("MISSING_SESSION")
        if invalid_dates:
            reason_codes.append("INVALID_PARTITION")
        if extra_dates:
            reason_codes.append("EXTRA_SESSION")
        if repair_pending_dates:
            reason_codes.append("SOURCE_REPAIR_PENDING")
        if reason_codes:
            exclusion: dict[str, Any] = {
                "extra_session_dates": sorted(extra_dates),
                "invalid_session_dates": sorted(invalid_dates),
                "missing_session_dates": [value.isoformat() for value in missing_dates],
                "observed_partitions": symbol_partitions,
                "reason_codes": sorted(reason_codes),
                "symbol": symbol,
            }
            if repair_pending_dates:
                exclusion["repair_pending_session_dates"] = sorted(
                    repair_pending_dates
                )
            excluded_symbols.append(exclusion)
            continue
        included_symbols.append(symbol)
        included_partitions.extend(symbol_partitions)
        canonical_payload_bytes += symbol_payload_bytes
        for partition in symbol_partitions:
            counts["included_partition_count"] += 1
            counts["bar_count"] += int(partition["bar_count"])
            if partition["status"] == "READY":
                counts["ready_partition_count"] += 1
                last_event_at = datetime.fromisoformat(str(partition["last_event_at"]))
                snapshot_identity_at = (
                    max(snapshot_identity_at, last_event_at)
                    if snapshot_identity_at is not None
                    else last_event_at
                )
            else:
                counts["empty_partition_count"] += 1
    for symbol in sorted(set(declared_symbols) - observed_symbols):
        excluded_symbols.append(
            {
                "extra_session_dates": [],
                "invalid_session_dates": [],
                "missing_session_dates": [value.isoformat() for value in calendar],
                "observed_partitions": [],
                "reason_codes": ["MISSING_SESSION"],
                "symbol": symbol,
            }
        )
    excluded_symbols.sort(key=lambda item: str(item["symbol"]))
    counts["included_symbol_count"] = len(included_symbols)
    counts["excluded_symbol_count"] = len(excluded_symbols)
    if snapshot_identity_at is None or counts["bar_count"] == 0:
        raise FinMindSnapshotError("EMPTY_DATASET: no complete symbol has a READY Kbar")
    return _Inspection(
        contract=contract,
        compatible_jobs=tuple(jobs),
        excluded_jobs=tuple(excluded_jobs),
        included_partitions=tuple(included_partitions),
        included_symbols=tuple(included_symbols),
        excluded_symbols=tuple(excluded_symbols),
        counts=counts,
        snapshot_identity_at=_canonical_timestamp(snapshot_identity_at),
        canonical_payload_bytes=canonical_payload_bytes,
    )


def _partition_metadata(row: sqlite3.Row) -> tuple[str, int, str, str | None, str | None]:
    return (
        str(row["status"]),
        int(row["bar_count"]),
        str(row["canonical_sha256"]),
        _canonical_optional_timestamp(row["first_event_at"]),
        _canonical_optional_timestamp(row["last_event_at"]),
    )


def _effective_partition_metadata(
    row: sqlite3.Row,
    resolution: RepairResolution | None,
) -> tuple[str, int, str, str | None, str | None]:
    if resolution is None or not resolution.is_active:
        return _partition_metadata(row)
    return (
        "READY",
        len(resolution.bars),
        str(resolution.canonical_sha256),
        resolution.first_event_at,
        resolution.last_event_at,
    )


def _planned_partition_projection(
    value: Mapping[str, Any],
) -> tuple[str, int, str, str | None, str | None]:
    return (
        str(value.get("status") or ""),
        int(value.get("bar_count") or 0),
        str(value.get("canonical_sha256") or ""),
        _canonical_optional_timestamp(value.get("first_event_at")),
        _canonical_optional_timestamp(value.get("last_event_at")),
    )


def _verified_partition_bars(
    row: sqlite3.Row,
    symbol: str,
    session_date: date,
) -> tuple[HistoricalBar, ...]:
    body = _gzip_body(bytes(row["raw_payload"]), "partition")
    if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
        raise FinMindSnapshotError(
            f"raw partition digest mismatch: {symbol}/{session_date.isoformat()}"
        )
    response = _decode_response(body, "partition")
    if (response.payload or {}).get("status") != 200:
        raise FinMindSnapshotError(
            f"partition response status is invalid: {symbol}/{session_date.isoformat()}"
        )
    try:
        bars = normalize_kbar_response(
            response,
            symbol=symbol,
            session_date=session_date,
        )
    except (TypeError, ValueError) as error:
        raise FinMindSnapshotError(
            f"partition normalization failed: {symbol}/{session_date.isoformat()}"
        ) from error
    canonical_payload = canonical_json([bar.to_dict() for bar in bars]).encode()
    if hashlib.sha256(canonical_payload).hexdigest() != row["canonical_sha256"]:
        raise FinMindSnapshotError(
            f"canonical partition digest mismatch: {symbol}/{session_date.isoformat()}"
        )
    if len(bars) != int(row["bar_count"]):
        raise FinMindSnapshotError(
            f"partition bar count mismatch: {symbol}/{session_date.isoformat()}"
        )
    status = str(row["status"])
    if (status == "READY") != bool(bars):
        raise FinMindSnapshotError(
            f"partition status/payload mismatch: {symbol}/{session_date.isoformat()}"
        )
    observed_first = _canonical_timestamp(bars[0].timestamp) if bars else None
    observed_last = _canonical_timestamp(bars[-1].timestamp) if bars else None
    if observed_first != _canonical_optional_timestamp(row["first_event_at"]):
        raise FinMindSnapshotError(
            f"partition first event mismatch: {symbol}/{session_date.isoformat()}"
        )
    if observed_last != _canonical_optional_timestamp(row["last_event_at"]):
        raise FinMindSnapshotError(
            f"partition last event mismatch: {symbol}/{session_date.isoformat()}"
        )
    if any(bar.session_date != session_date for bar in bars):
        raise FinMindSnapshotError(
            f"partition session mismatch: {symbol}/{session_date.isoformat()}"
        )
    return bars


def _verify_partition(row: sqlite3.Row, symbol: str, session_date: date) -> int:
    bars = _verified_partition_bars(row, symbol, session_date)
    canonical_payload = canonical_json([bar.to_dict() for bar in bars]).encode()
    return len(canonical_payload)


def _verify_effective_partition(
    row: sqlite3.Row,
    resolution: RepairResolution | None,
    symbol: str,
    session_date: date,
) -> int:
    if resolution is None:
        return _verify_partition(row, symbol, session_date)
    if not resolution.is_active:
        raise FinMindSnapshotError(
            f"source repair is pending: {symbol}/{session_date.isoformat()}"
        )
    canonical_payload = canonical_json(
        [bar.to_dict() for bar in resolution.bars]
    ).encode()
    if hashlib.sha256(canonical_payload).hexdigest() != resolution.canonical_sha256:
        raise FinMindSnapshotError(
            f"source repair canonical mismatch: {symbol}/{session_date.isoformat()}"
        )
    return len(canonical_payload)


def _load_reference_mapping(
    path: Path, included_symbols: Sequence[str]
) -> Mapping[str, Any]:
    if not path.is_file():
        raise FinMindSnapshotError(
            f"stock-info raw artifact does not exist: {path}"
        )
    body = _gzip_body(path.read_bytes(), "stock-info")
    response = _decode_response(body, "stock-info")
    payload = response.payload or {}
    rows = payload.get("data")
    if payload.get("status") != 200 or not isinstance(rows, list):
        raise FinMindSnapshotError("TaiwanStockInfo response envelope is invalid")
    grouped: dict[str, list[tuple[date, str, str]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FinMindSnapshotError("TaiwanStockInfo row must be an object")
        symbol = str(row.get("stock_id") or "").strip().upper()
        market = str(row.get("type") or "").strip().lower()
        name = str(row.get("stock_name") or "").strip()
        if not symbol or market not in {"twse", "tpex"} or not name:
            continue
        try:
            selected_date = date.fromisoformat(str(row.get("date") or ""))
        except ValueError:
            continue
        grouped.setdefault(symbol, []).append((selected_date, name, market))
    mapping: list[Mapping[str, str]] = []
    for symbol in sorted(included_symbols):
        observations = grouped.get(symbol, [])
        if not observations:
            raise FinMindSnapshotError(
                f"TaiwanStockInfo missing supported mapping for {symbol}"
            )
        selected_date = max(item[0] for item in observations)
        identities = {
            (name, market)
            for observed_date, name, market in observations
            if observed_date == selected_date
        }
        if len(identities) != 1:
            raise FinMindSnapshotError(
                f"TaiwanStockInfo ambiguous mapping for {symbol}"
            )
        name, market = next(iter(identities))
        mapping.append(
            {
                "market": "TWSE" if market == "twse" else "TPEX",
                "name": name,
                "selected_date": selected_date.isoformat(),
                "symbol": symbol,
            }
        )
    return {
        "dataset": REFERENCE_DATASET,
        "mapping": mapping,
        "mapping_contract": REFERENCE_MAPPING_CONTRACT,
        "raw_body_sha256": hashlib.sha256(body).hexdigest(),
    }


def _decode_response(body: bytes, label: str) -> FinMindResponse:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinMindSnapshotError(f"{label} response is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise FinMindSnapshotError(f"{label} response must be an object")
    return FinMindResponse(http_status=200, body=body, payload=payload)


def _gzip_body(value: bytes, label: str) -> bytes:
    try:
        return gzip.decompress(value)
    except (EOFError, OSError) as error:
        raise FinMindSnapshotError(f"{label} evidence is not valid gzip") from error


def _raw_body_sha256(path: Path) -> str:
    if not path.is_file():
        raise FinMindSnapshotError(f"stock-info raw artifact does not exist: {path}")
    return hashlib.sha256(_gzip_body(path.read_bytes(), "stock-info")).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise FinMindSnapshotError(f"handoff file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: Mapping[str, Any] | list[Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_optional_timestamp(value: object) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise FinMindSnapshotError("partition event timestamp is invalid") from error
    return _canonical_timestamp(parsed)


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FinMindSnapshotError("snapshot timestamps must include timezone")
    return value.astimezone(TAIPEI).isoformat()
