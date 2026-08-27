"""Offline Local Paper slippage model-stress evidence analysis.

This module consumes sealed canonical market-data artifacts and optional
``local_paper_fill.v3`` exports.  It never connects to a provider and never
represents model stress as broker execution calibration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from market_data.exact_replay import verify_exact_projection_replay
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.journal import verify_market_event_journal
from market_data.late_delivery_evidence import LateDeliveryCohort
from simulation.execution_costs import (
    PRICE_TICK_POLICY_VERSION,
    SLIPPAGE_POLICY_VERSION,
    common_stock_tick_size,
    is_valid_common_stock_tick,
)
from trading.canonical_values import canonical_decimal_string
from trading.journal import (
    InMemoryJournalRepository,
    JournalRecord,
    JournalRepository,
    JournalSession,
)
from trading.local_paper import (
    LOCAL_PAPER_FILL_V3_KIND,
    LocalPaperFill,
    ProjectionRecoveryError,
)
from trading.postgres_journal import PostgresJournalRepository


INPUT_MANIFEST_SCHEMA = "local-paper-slippage-calibration-input-manifest.v1"
ANALYSIS_REPORT_SCHEMA = "local-paper-slippage-calibration-analysis-report.v1"
CLOCK_DISPOSITION_SCHEMA = "local-paper-slippage-clock-disposition.v1"
CLOCK_REVIEW_EVIDENCE_SCHEMA = "local-paper-slippage-clock-review-evidence.v1"
FILL_EXPORT_SCHEMA = "local-paper-fill-calibration-export.v1"
FILL_JOURNAL_SNAPSHOT_SCHEMA = "local-paper-fill-journal-snapshot.v1"
ANALYZER_VERSION = "local-paper-slippage-proxy-analyzer.v1"
METRIC_POLICY_VERSION = "bbo-tick-adverse-movement-proxy.v1"
TIMESTAMP_POLICY_VERSION = "reviewed-source-receive-comparability.v1"
PERCENTILE_METHOD = "nearest-rank.v1"
ANALYSIS_SCOPE = "LOCAL_PAPER_MODEL_STRESS_PROXY_ONLY"
ACTUAL_EXECUTION_STATUS = "ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED"
PROXY_QUALIFIED = "MODEL_STRESS_PROXY_QUALIFIED"
PROXY_INSUFFICIENT = "MODEL_STRESS_PROXY_INSUFFICIENT_COVERAGE"
PROXY_INPUT_NOT_QUALIFIED = "MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED"
METRIC_USE_PROHIBITION = "DIAGNOSTIC_ONLY_NOT_BROKER_FILL_PROMISE"
TAIPEI = ZoneInfo("Asia/Taipei")

MINIMUM_DISTINCT_TRADING_DAYS = 5
MINIMUM_SAMPLES_PER_GROUP = 30
MINIMUM_UNIQUE_BOOKS_PER_GROUP = 30
MAXIMUM_SOURCE_RECEIVE_SKEW_MS = 1_000
MAXIMUM_BOOK_AGE_MS = 3_000
MAXIMUM_HORIZON_TOLERANCE_MS = 1_000
REVIEWED_EQUITY_CALENDAR_SCHEMA = "twse_calendar_2026_v1"
_REQUIRED_PHASES = ("OPENING", "CONTINUOUS", "CLOSE")
_REQUIRED_SIDES = ("BUY", "SELL")
_REQUIRED_TIERS = ("high", "mid", "low")
_REQUIRED_PHASE_BUCKETS = ("EARLY", "MIDDLE", "LATE")
_SESSION_ARTIFACTS = (
    "manifest.json",
    "records.jsonl",
    "bootstrap_snapshot.json",
    "instrument_reference.json",
    "projection_state.json",
    "qualification_report.json",
)
_BPS = Decimal("10000")


class CalibrationContractError(ValueError):
    """A sealed calibration artifact is malformed, altered, or unsupported."""


class SessionPhase(StrEnum):
    OPENING = "OPENING"
    CONTINUOUS = "CONTINUOUS"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class _Book:
    symbol: str
    received_at: datetime
    event_at: datetime
    bid: Decimal
    ask: Decimal
    identity: str


@dataclass(frozen=True)
class _Tick:
    symbol: str
    received_at: datetime
    event_at: datetime
    price: Decimal


@dataclass(frozen=True)
class _ProxySample:
    symbol: str
    liquidity_tier: str
    session_phase: str
    session_date: date
    side: str
    reference_source: str
    spread_bps: Decimal
    reference_tick_bps: Decimal
    crossing_bps: Decimal
    adverse_movement_bps: Decimal | None
    book_identity: str
    phase_bucket: str


@dataclass(frozen=True)
class _SessionAnalysis:
    session_id: str
    session_date: date | None
    sample_count: int
    tick_count: int
    paired_book_count: int
    missing_book_count: int
    stale_book_count: int
    causal_ordering_failure_count: int
    max_abs_source_receive_skew_ms: Decimal | None
    samples: tuple[_ProxySample, ...]
    issues: tuple[dict[str, str], ...]


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_content_sha256(payload: Mapping[str, object]) -> str:
    content = dict(payload)
    content.pop("content_sha256", None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest_bound_bytes(
    path: Path,
    expected_sha256: object,
    field_name: str,
) -> bytes:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise CalibrationContractError(f"{field_name} is unavailable") from error
    if hashlib.sha256(encoded).hexdigest() != _sha256(
        expected_sha256,
        f"{field_name}.sha256",
    ):
        raise CalibrationContractError(f"{field_name} sha256 mismatch")
    return encoded


def write_sealed_json_once(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    """Atomically publish a versioned JSON artifact and digest sidecar once."""

    if "content_sha256" in payload:
        raise CalibrationContractError("payload is already sealed")
    sealed = dict(payload)
    sealed["content_sha256"] = canonical_content_sha256(sealed)
    sidecar = path.with_suffix(".canonical.sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"sealed artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = (
        json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    sidecar_bytes = f"{sealed['content_sha256']}\n".encode("ascii")
    temporary_paths: list[Path] = []
    published_json = False
    published_sidecar = False
    try:
        for value in (json_bytes, sidecar_bytes):
            descriptor, temporary_name = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            temporary_paths.append(temporary)
            with os.fdopen(descriptor, "wb") as output:
                output.write(value)
                output.flush()
                os.fsync(output.fileno())
        os.link(temporary_paths[0], path)
        published_json = True
        os.link(temporary_paths[1], sidecar)
        published_sidecar = True
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if published_sidecar:
            sidecar.unlink(missing_ok=True)
        if published_json:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return sealed


def load_sealed_json(
    path: Path,
    *,
    expected_schema: str,
    expected_file_sha256: str | None = None,
) -> Mapping[str, object]:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise CalibrationContractError(f"sealed JSON is unavailable: {path}") from error
    if expected_file_sha256 is not None and hashlib.sha256(encoded).hexdigest() != (
        _sha256(expected_file_sha256, "expected_file_sha256")
    ):
        raise CalibrationContractError("sealed JSON file sha256 mismatch")
    try:
        raw = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationContractError(f"sealed JSON is unavailable: {path}") from error
    if not isinstance(raw, dict):
        raise CalibrationContractError("sealed JSON root must be an object")
    if raw.get("schema_version") != expected_schema:
        raise CalibrationContractError(
            f"unsupported schema_version: {raw.get('schema_version')}"
        )
    expected_digest = _sha256(raw.get("content_sha256"), "content_sha256")
    if canonical_content_sha256(raw) != expected_digest:
        raise CalibrationContractError("content_sha256 does not match canonical payload")
    sidecar = path.with_suffix(".canonical.sha256")
    try:
        sidecar_digest = sidecar.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise CalibrationContractError(f"checksum sidecar is unavailable: {sidecar}") from error
    if sidecar_digest != expected_digest:
        raise CalibrationContractError("checksum sidecar does not match content_sha256")
    return raw


def seal_input_manifest(draft_path: Path, output_path: Path) -> dict[str, object]:
    """Bind a draft to immutable input bytes without modifying source evidence."""

    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationContractError("input manifest draft is unavailable") from error
    if not isinstance(draft, dict):
        raise CalibrationContractError("input manifest draft must be an object")
    _validate_manifest(draft, sealed=False)
    sealed = dict(draft)

    cohort = dict(_mapping(draft["cohort"], "cohort"))
    cohort_path = _resolve_input_path(draft_path.parent, cohort["path"])
    cohort["path"] = _relative_artifact_path(cohort_path, output_path.parent)
    cohort["sha256"] = file_sha256(cohort_path)
    sealed["cohort"] = cohort

    calendar = dict(_mapping(draft["trading_calendar"], "trading_calendar"))
    calendar_path = _resolve_input_path(draft_path.parent, calendar["path"])
    calendar["path"] = _relative_artifact_path(calendar_path, output_path.parent)
    calendar["sha256"] = file_sha256(calendar_path)
    sealed["trading_calendar"] = calendar

    sessions: list[dict[str, object]] = []
    for raw_session in _object_list(draft["market_sessions"], "market_sessions"):
        session = dict(raw_session)
        session_path = _resolve_input_path(draft_path.parent, session["path"])
        session["path"] = _relative_artifact_path(session_path, output_path.parent)
        session["artifact_sha256"] = {
            name: file_sha256(session_path / name) for name in _SESSION_ARTIFACTS
        }
        clock = session.get("clock_disposition")
        if clock is not None:
            clock_mapping = dict(_mapping(clock, "clock_disposition"))
            clock_path = _resolve_input_path(draft_path.parent, clock_mapping["path"])
            clock_mapping["path"] = _relative_artifact_path(
                clock_path,
                output_path.parent,
            )
            clock_mapping["sha256"] = file_sha256(clock_path)
            session["clock_disposition"] = clock_mapping
        sessions.append(session)
    sealed["market_sessions"] = sessions

    fill_exports: list[dict[str, object]] = []
    for raw_export in _object_list(draft["fill_exports"], "fill_exports"):
        export = dict(raw_export)
        export_path = _resolve_input_path(draft_path.parent, export["path"])
        export["path"] = _relative_artifact_path(export_path, output_path.parent)
        export["sha256"] = file_sha256(export_path)
        fill_exports.append(export)
    sealed["fill_exports"] = fill_exports
    _validate_manifest({**sealed, "content_sha256": "0" * 64}, sealed=True)
    return write_sealed_json_once(output_path, sealed)


def load_input_manifest(path: Path) -> Mapping[str, object]:
    manifest = load_sealed_json(path, expected_schema=INPUT_MANIFEST_SCHEMA)
    _validate_manifest(manifest, sealed=True)
    return manifest


def seal_clock_disposition(draft_path: Path, output_path: Path) -> dict[str, object]:
    draft = _load_draft(draft_path, "clock disposition")
    expected = {
        "schema_version",
        "session_id",
        "status",
        "max_abs_source_receive_skew_ms",
        "review_basis",
        "review_authority",
        "review_evidence_path",
    }
    if set(draft) != expected or draft.get("schema_version") != CLOCK_DISPOSITION_SCHEMA:
        raise CalibrationContractError("clock disposition draft fields do not match contract")
    _non_empty(draft["session_id"], "session_id")
    if draft["status"] != "REVIEWED_COMPARABLE":
        raise CalibrationContractError("clock disposition must be REVIEWED_COMPARABLE")
    _non_empty(draft["review_basis"], "review_basis")
    if draft["review_authority"] != "INDEPENDENT_REVIEWER":
        raise CalibrationContractError("clock review authority must be independent")
    bound = _decimal(draft["max_abs_source_receive_skew_ms"], "max skew")
    if bound < 0 or bound > Decimal(MAXIMUM_SOURCE_RECEIVE_SKEW_MS):
        raise CalibrationContractError("clock skew bound exceeds bounded contract")
    evidence_path = _resolve_input_path(draft_path.parent, draft["review_evidence_path"])
    if not evidence_path.is_file():
        raise CalibrationContractError("clock review evidence is unavailable")
    evidence_sha256 = _validate_clock_review_evidence(
        evidence_path,
        session_id=str(draft["session_id"]),
        approved_bound=bound,
        expected_market_manifest_sha256=None,
        expected_file_sha256=None,
    )
    sealed = dict(draft)
    sealed.pop("review_evidence_path")
    sealed["review_evidence"] = {
        "path": _relative_artifact_path(evidence_path, output_path.parent),
        "sha256": evidence_sha256,
    }
    return write_sealed_json_once(output_path, sealed)


def _validate_clock_review_evidence(
    path: Path,
    *,
    session_id: str,
    approved_bound: Decimal,
    expected_market_manifest_sha256: str | None,
    expected_file_sha256: str | None,
) -> str:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise CalibrationContractError("clock review evidence is invalid") from error
    digest = hashlib.sha256(encoded).hexdigest()
    if expected_file_sha256 is not None and digest != _sha256(
        expected_file_sha256,
        "clock_review_evidence.sha256",
    ):
        raise CalibrationContractError("clock review evidence sha256 mismatch")
    try:
        raw = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationContractError("clock review evidence is invalid") from error
    expected = {
        "schema_version",
        "session_id",
        "disposition",
        "approved_max_abs_source_receive_skew_ms",
        "market_session_manifest_sha256",
        "review_method",
        "reviewed_at",
        "reviewer",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise CalibrationContractError("clock review evidence fields are invalid")
    reviewer = _mapping(raw["reviewer"], "reviewer")
    if set(reviewer) != {"reviewer_id", "authority"}:
        raise CalibrationContractError("clock reviewer fields are invalid")
    manifest_sha256 = _sha256(
        raw["market_session_manifest_sha256"],
        "market_session_manifest_sha256",
    )
    if (
        raw["schema_version"] != CLOCK_REVIEW_EVIDENCE_SCHEMA
        or raw["session_id"] != session_id
        or raw["disposition"] != "REVIEWED_COMPARABLE"
        or _decimal(
            raw["approved_max_abs_source_receive_skew_ms"],
            "approved_max_abs_source_receive_skew_ms",
        )
        != approved_bound
        or raw["review_method"] != "SOURCE_RECEIVE_TIMESTAMP_COMPARABILITY_REVIEW"
        or reviewer["authority"] != "INDEPENDENT_REVIEWER"
    ):
        raise CalibrationContractError("clock review evidence lineage mismatch")
    _non_empty(reviewer["reviewer_id"], "reviewer_id")
    _aware_datetime(raw["reviewed_at"], "reviewed_at")
    if (
        expected_market_manifest_sha256 is not None
        and manifest_sha256 != expected_market_manifest_sha256
    ):
        raise CalibrationContractError("clock review market manifest mismatch")
    return digest


def seal_fill_journal_snapshot_from_repository(
    *,
    repository: JournalRepository,
    session_id: str,
    output_path: Path,
) -> dict[str, object]:
    """Read and seal one existing Journal session without appending records."""

    normalized_session_id = _non_empty(session_id, "session_id")
    if isinstance(repository, PostgresJournalRepository):
        repository_kind = "POSTGRESQL"
    elif isinstance(repository, InMemoryJournalRepository):
        repository_kind = "IN_MEMORY_TEST_FIXTURE"
    else:
        raise CalibrationContractError("snapshot repository adapter is unsupported")
    session = repository.session(normalized_session_id)
    if session is None:
        raise CalibrationContractError("source Journal session is unavailable")
    if session.mode not in {"LOCAL_PAPER", "LOCAL_PAPER_SIMULATION"}:
        raise CalibrationContractError("source Journal session mode is not Local Paper")
    _sha256(session.metadata.get("settings_digest"), "session.settings_digest")
    results = repository.records(normalized_session_id)
    if not results:
        raise CalibrationContractError("source Journal session has no records")
    serialized_records: list[dict[str, object]] = []
    previous_sequence = 0
    record_ids: set[str] = set()
    fingerprints: set[str] = set()
    for result in results:
        if result.sequence <= previous_sequence:
            raise CalibrationContractError("source Journal sequence is not increasing")
        previous_sequence = result.sequence
        if result.record.session_id != normalized_session_id:
            raise CalibrationContractError("source Journal record session mismatch")
        if (
            result.record.record_id in record_ids
            or result.record.fingerprint in fingerprints
        ):
            raise CalibrationContractError("source Journal contains duplicate record identity")
        record_ids.add(result.record.record_id)
        fingerprints.add(result.record.fingerprint)
        serialized_records.append(
            {
                "sequence": result.sequence,
                "fingerprint": result.record.fingerprint,
                "record": journal_record_to_export_mapping(result.record),
            }
        )
    session_mapping = _journal_session_to_mapping(session)
    root_payload = {"session": session_mapping, "records": serialized_records}
    payload: dict[str, object] = {
        "schema_version": FILL_JOURNAL_SNAPSHOT_SCHEMA,
        "producer_version": ANALYZER_VERSION,
        "repository_kind": repository_kind,
        "read_authority": "READ_ONLY_JOURNAL_REPOSITORY_SNAPSHOT",
        "session": session_mapping,
        "records": serialized_records,
        "journal_session_root_sha256": hashlib.sha256(
            canonical_json_bytes(root_payload)
        ).hexdigest(),
    }
    return write_sealed_json_once(output_path, payload)


def _load_fill_journal_snapshot(
    path: Path,
    *,
    expected_file_sha256: str | None = None,
) -> tuple[Mapping[str, object], JournalSession, tuple[Mapping[str, object], ...]]:
    snapshot = load_sealed_json(
        path,
        expected_schema=FILL_JOURNAL_SNAPSHOT_SCHEMA,
        expected_file_sha256=expected_file_sha256,
    )
    expected = {
        "schema_version",
        "producer_version",
        "repository_kind",
        "read_authority",
        "session",
        "records",
        "journal_session_root_sha256",
        "content_sha256",
    }
    if set(snapshot) != expected:
        raise CalibrationContractError("Journal snapshot fields do not match contract")
    if (
        snapshot["producer_version"] != ANALYZER_VERSION
        or snapshot["repository_kind"] not in {"POSTGRESQL", "IN_MEMORY_TEST_FIXTURE"}
        or snapshot["read_authority"]
        != "READ_ONLY_JOURNAL_REPOSITORY_SNAPSHOT"
    ):
        raise CalibrationContractError("Journal snapshot authority is unsupported")
    session_raw = _mapping(snapshot["session"], "snapshot.session")
    session = _journal_session_from_mapping(session_raw)
    if session.mode not in {"LOCAL_PAPER", "LOCAL_PAPER_SIMULATION"}:
        raise CalibrationContractError("Journal snapshot mode is not Local Paper")
    _sha256(session.metadata.get("settings_digest"), "session.settings_digest")
    records = tuple(_object_list(snapshot["records"], "snapshot.records"))
    if not records:
        raise CalibrationContractError("Journal snapshot records must not be empty")
    previous_sequence = 0
    record_ids: set[str] = set()
    fingerprints: set[str] = set()
    for item in records:
        if set(item) != {"sequence", "fingerprint", "record"}:
            raise CalibrationContractError("Journal snapshot record fields are invalid")
        sequence = _positive_int(item["sequence"], "snapshot.sequence")
        if sequence <= previous_sequence:
            raise CalibrationContractError("Journal snapshot sequence is not increasing")
        previous_sequence = sequence
        record = _journal_record_from_mapping(_mapping(item["record"], "record"))
        fingerprint = _sha256(item["fingerprint"], "snapshot.fingerprint")
        if record.session_id != session.session_id or record.fingerprint != fingerprint:
            raise CalibrationContractError("Journal snapshot record lineage mismatch")
        if record.record_id in record_ids or fingerprint in fingerprints:
            raise CalibrationContractError("Journal snapshot has duplicate record identity")
        record_ids.add(record.record_id)
        fingerprints.add(fingerprint)
    root_payload = {"session": dict(session_raw), "records": list(records)}
    expected_root = _sha256(
        snapshot["journal_session_root_sha256"],
        "journal_session_root_sha256",
    )
    if hashlib.sha256(canonical_json_bytes(root_payload)).hexdigest() != expected_root:
        raise CalibrationContractError("Journal snapshot session root mismatch")
    return snapshot, session, records


def seal_fill_export(draft_path: Path, output_path: Path) -> dict[str, object]:
    draft = _load_draft(draft_path, "fill export")
    expected = {
        "schema_version",
        "export_id",
        "session_id",
        "session_date",
        "settings_digest",
        "source_journal",
        "records",
    }
    if set(draft) != expected or draft.get("schema_version") != FILL_EXPORT_SCHEMA:
        raise CalibrationContractError("fill export draft fields do not match contract")
    session_id = _non_empty(draft["session_id"], "session_id")
    _non_empty(draft["export_id"], "export_id")
    session_date = _iso_date(draft["session_date"], "session_date")
    settings_digest = _sha256(draft["settings_digest"], "settings_digest")
    source_journal = _validate_source_journal(
        _mapping(draft["source_journal"], "source_journal"),
        sealed=False,
    )
    snapshot_path = _resolve_input_path(
        draft_path.parent,
        source_journal["snapshot_path"],
    )
    snapshot, snapshot_session, snapshot_records = _load_fill_journal_snapshot(
        snapshot_path
    )
    if (
        snapshot["repository_kind"] != source_journal["repository_kind"]
        or snapshot_session.session_id != session_id
        or snapshot_session.metadata.get("settings_digest") != settings_digest
    ):
        raise CalibrationContractError("fill export snapshot lineage mismatch")
    sequence_start = int(source_journal["sequence_start"])
    sequence_end = int(source_journal["sequence_end"])
    snapshot_sequences = [int(item["sequence"]) for item in snapshot_records]
    if sequence_start < snapshot_sequences[0] or sequence_end > snapshot_sequences[-1]:
        raise CalibrationContractError("fill export range is outside Journal snapshot")
    selected_snapshot_records = [
        item
        for item in snapshot_records
        if sequence_start <= int(item["sequence"]) <= sequence_end
        and _mapping(item["record"], "record").get("kind")
        == LOCAL_PAPER_FILL_V3_KIND
    ]
    records = _object_list(draft["records"], "records")
    if not records:
        raise CalibrationContractError("fill export records must not be empty")
    if canonical_json_bytes(records) != canonical_json_bytes(selected_snapshot_records):
        raise CalibrationContractError(
            "submitted fills do not exactly match read-only Journal snapshot range"
        )
    previous_sequence = sequence_start - 1
    fingerprints: set[str] = set()
    record_ids: set[str] = set()
    idempotency_identities: set[tuple[str, str]] = set()
    order_fill_sequences: set[tuple[str, int]] = set()
    range_rows: list[dict[str, object]] = []
    for item in records:
        if set(item) != {"sequence", "fingerprint", "record"}:
            raise CalibrationContractError("fill export record fields do not match contract")
        sequence = _positive_int(item["sequence"], "sequence")
        if sequence <= previous_sequence or sequence > sequence_end:
            raise CalibrationContractError("fill export sequence is outside ordered range")
        previous_sequence = sequence
        record = _journal_record_from_mapping(_mapping(item["record"], "record"))
        if (
            record.session_id != session_id
            or record.kind != LOCAL_PAPER_FILL_V3_KIND
            or record.occurred_at.astimezone(TAIPEI).date() != session_date
            or record.payload.get("settings_digest") != settings_digest
        ):
            raise CalibrationContractError("fill record lineage does not match export")
        if record.fingerprint != _sha256(item["fingerprint"], "fingerprint"):
            raise CalibrationContractError("fill record fingerprint mismatch")
        fingerprint = record.fingerprint
        if fingerprint in fingerprints or record.record_id in record_ids:
            raise CalibrationContractError("fill export contains duplicate record identity")
        fingerprints.add(fingerprint)
        record_ids.add(record.record_id)
        if record.idempotency_scope is not None or record.idempotency_key is not None:
            if record.idempotency_scope is None or record.idempotency_key is None:
                raise CalibrationContractError("fill idempotency identity is incomplete")
            idempotency_identity = (record.idempotency_scope, record.idempotency_key)
            if idempotency_identity in idempotency_identities:
                raise CalibrationContractError("fill export contains duplicate idempotency identity")
            idempotency_identities.add(idempotency_identity)
        fill = LocalPaperFill.from_record(record)
        fill_identity = (
            fill.order_id,
            _positive_int(record.payload.get("fill_sequence"), "fill_sequence"),
        )
        if fill_identity in order_fill_sequences:
            raise CalibrationContractError("fill export contains duplicate order fill sequence")
        order_fill_sequences.add(fill_identity)
        range_rows.append({"sequence": sequence, "fingerprint": fingerprint})
    sealed = dict(draft)
    sealed["source_journal"] = {
        "repository_kind": source_journal["repository_kind"],
        "snapshot": {
            "path": _relative_artifact_path(snapshot_path, output_path.parent),
            "sha256": file_sha256(snapshot_path),
        },
        "journal_session_root_sha256": snapshot["journal_session_root_sha256"],
        "sequence_start": sequence_start,
        "sequence_end": sequence_end,
        "selected_record_count": len(records),
        "selected_range_root_sha256": hashlib.sha256(
            canonical_json_bytes(range_rows)
        ).hexdigest(),
    }
    return write_sealed_json_once(output_path, sealed)


def _load_draft(path: Path, artifact_name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationContractError(f"{artifact_name} draft is unavailable") from error
    if not isinstance(raw, dict):
        raise CalibrationContractError(f"{artifact_name} draft must be an object")
    return raw


def _validate_source_journal(
    raw: Mapping[str, object],
    *,
    sealed: bool,
) -> dict[str, object]:
    expected = {
        "repository_kind",
        "sequence_start",
        "sequence_end",
    }
    if sealed:
        expected.update(
            {
                "snapshot",
                "journal_session_root_sha256",
                "selected_record_count",
                "selected_range_root_sha256",
            }
        )
    else:
        expected.add("snapshot_path")
    if set(raw) != expected:
        raise CalibrationContractError("source Journal fields do not match contract")
    repository_kind = _non_empty(raw["repository_kind"], "repository_kind")
    if repository_kind not in {"POSTGRESQL", "IN_MEMORY_TEST_FIXTURE"}:
        raise CalibrationContractError("source Journal repository_kind is unsupported")
    start = _positive_int(raw["sequence_start"], "sequence_start")
    end = _positive_int(raw["sequence_end"], "sequence_end")
    if end < start:
        raise CalibrationContractError("source Journal range is invalid")
    validated: dict[str, object] = {
        "repository_kind": repository_kind,
        "sequence_start": start,
        "sequence_end": end,
    }
    if sealed:
        snapshot = _mapping(raw["snapshot"], "snapshot")
        if set(snapshot) != {"path", "sha256"}:
            raise CalibrationContractError("source Journal snapshot fields are invalid")
        validated["snapshot"] = {
            "path": _non_empty(snapshot["path"], "snapshot.path"),
            "sha256": _sha256(snapshot["sha256"], "snapshot.sha256"),
        }
        validated["journal_session_root_sha256"] = _sha256(
            raw["journal_session_root_sha256"],
            "journal_session_root_sha256",
        )
        validated["selected_record_count"] = _positive_int(
            raw["selected_record_count"],
            "selected_record_count",
        )
        validated["selected_range_root_sha256"] = _sha256(
            raw["selected_range_root_sha256"],
            "selected_range_root_sha256",
        )
    else:
        validated["snapshot_path"] = _non_empty(
            raw["snapshot_path"],
            "snapshot_path",
        )
    return validated


def _validate_manifest(raw: Mapping[str, object], *, sealed: bool) -> None:
    expected = {
        "schema_version",
        "manifest_id",
        "analysis_scope",
        "policy",
        "cohort",
        "trading_calendar",
        "market_sessions",
        "fill_exports",
    }
    if sealed:
        expected.add("content_sha256")
    if set(raw) != expected:
        raise CalibrationContractError("input manifest fields do not match contract")
    if raw["schema_version"] != INPUT_MANIFEST_SCHEMA:
        raise CalibrationContractError("input manifest schema is unsupported")
    _non_empty(raw["manifest_id"], "manifest_id")
    if raw["analysis_scope"] != ANALYSIS_SCOPE:
        raise CalibrationContractError("analysis scope must be model-stress proxy only")
    _validate_policy(_mapping(raw["policy"], "policy"))

    cohort = _mapping(raw["cohort"], "cohort")
    cohort_fields = {"cohort_id", "path"} | ({"sha256"} if sealed else set())
    if set(cohort) != cohort_fields:
        raise CalibrationContractError("cohort fields do not match contract")
    _non_empty(cohort["cohort_id"], "cohort_id")
    _non_empty(cohort["path"], "cohort.path")
    if sealed:
        _sha256(cohort["sha256"], "cohort.sha256")

    calendar = _mapping(raw["trading_calendar"], "trading_calendar")
    calendar_fields = {"path"} | ({"sha256"} if sealed else set())
    if set(calendar) != calendar_fields:
        raise CalibrationContractError("trading_calendar fields do not match contract")
    _non_empty(calendar["path"], "trading_calendar.path")
    if sealed:
        _sha256(calendar["sha256"], "trading_calendar.sha256")

    sessions = _object_list(raw["market_sessions"], "market_sessions")
    if not sessions:
        raise CalibrationContractError("market_sessions must not be empty")
    session_ids: set[str] = set()
    for session in sessions:
        expected_session = {
            "path",
            "session_id",
            "session_phase",
            "clock_disposition",
        }
        if sealed:
            expected_session.add("artifact_sha256")
        if set(session) != expected_session:
            raise CalibrationContractError("market session fields do not match contract")
        _non_empty(session["path"], "market_session.path")
        session_id = _non_empty(session["session_id"], "market_session.session_id")
        if session_id in session_ids:
            raise CalibrationContractError("market session_id must be unique")
        session_ids.add(session_id)
        try:
            SessionPhase(str(session["session_phase"]))
        except ValueError as error:
            raise CalibrationContractError("session_phase is unsupported") from error
        clock = session["clock_disposition"]
        if clock is not None:
            clock_mapping = _mapping(clock, "clock_disposition")
            clock_fields = {"path"} | ({"sha256"} if sealed else set())
            if set(clock_mapping) != clock_fields:
                raise CalibrationContractError(
                    "clock_disposition fields do not match contract"
                )
            _non_empty(clock_mapping["path"], "clock_disposition.path")
            if sealed:
                _sha256(clock_mapping["sha256"], "clock_disposition.sha256")
        if sealed:
            digests = _mapping(session["artifact_sha256"], "artifact_sha256")
            if set(digests) != set(_SESSION_ARTIFACTS):
                raise CalibrationContractError("session artifact digests are incomplete")
            for name, digest in digests.items():
                _sha256(digest, f"artifact_sha256.{name}")

    exports = _object_list(raw["fill_exports"], "fill_exports")
    export_paths: set[str] = set()
    for export in exports:
        expected_export = {"path"} | ({"sha256"} if sealed else set())
        if set(export) != expected_export:
            raise CalibrationContractError("fill export fields do not match contract")
        export_path = _non_empty(export["path"], "fill_export.path")
        if export_path in export_paths:
            raise CalibrationContractError("fill export path must be unique")
        export_paths.add(export_path)
        if sealed:
            _sha256(export["sha256"], "fill_export.sha256")
    if sealed:
        _sha256(raw["content_sha256"], "content_sha256")


def _validate_policy(policy: Mapping[str, object]) -> None:
    expected = {
        "analyzer_version",
        "metric_policy_version",
        "timestamp_policy_version",
        "percentile_method",
        "local_paper_slippage_policy_version",
        "price_tick_policy_version",
        "adverse_horizon_ms",
        "horizon_observation_tolerance_ms",
        "maximum_source_receive_skew_ms",
        "maximum_book_age_ms",
        "minimum_distinct_trading_days",
        "minimum_samples_per_group",
        "minimum_unique_books_per_group",
        "required_session_phases",
        "required_phase_buckets",
        "required_sides",
        "required_liquidity_tiers",
    }
    if set(policy) != expected:
        raise CalibrationContractError("policy fields do not match contract")
    identities = {
        "analyzer_version": ANALYZER_VERSION,
        "metric_policy_version": METRIC_POLICY_VERSION,
        "timestamp_policy_version": TIMESTAMP_POLICY_VERSION,
        "percentile_method": PERCENTILE_METHOD,
        "local_paper_slippage_policy_version": SLIPPAGE_POLICY_VERSION,
        "price_tick_policy_version": PRICE_TICK_POLICY_VERSION,
    }
    for field_name, expected_value in identities.items():
        if policy[field_name] != expected_value:
            raise CalibrationContractError(f"{field_name} is unsupported")
    horizon = _positive_int(policy["adverse_horizon_ms"], "adverse_horizon_ms")
    if horizon > 60_000:
        raise CalibrationContractError("adverse_horizon_ms exceeds bounded contract")
    tolerance = _positive_int(
        policy["horizon_observation_tolerance_ms"],
        "horizon_observation_tolerance_ms",
    )
    if tolerance > MAXIMUM_HORIZON_TOLERANCE_MS:
        raise CalibrationContractError("horizon observation tolerance exceeds bound")
    maximum_skew = _positive_int(
        policy["maximum_source_receive_skew_ms"],
        "maximum_source_receive_skew_ms",
    )
    if maximum_skew > MAXIMUM_SOURCE_RECEIVE_SKEW_MS or maximum_skew > horizon:
        raise CalibrationContractError("source/receive skew exceeds bounded contract")
    if (
        _positive_int(policy["maximum_book_age_ms"], "maximum_book_age_ms")
        > MAXIMUM_BOOK_AGE_MS
    ):
        raise CalibrationContractError("book age exceeds bounded contract")
    if (
        _positive_int(
            policy["minimum_distinct_trading_days"],
            "minimum_distinct_trading_days",
        )
        < MINIMUM_DISTINCT_TRADING_DAYS
    ):
        raise CalibrationContractError("minimum_distinct_trading_days weakens floor")
    if (
        _positive_int(policy["minimum_samples_per_group"], "minimum_samples_per_group")
        < MINIMUM_SAMPLES_PER_GROUP
    ):
        raise CalibrationContractError("minimum_samples_per_group weakens floor")
    if (
        _positive_int(
            policy["minimum_unique_books_per_group"],
            "minimum_unique_books_per_group",
        )
        < MINIMUM_UNIQUE_BOOKS_PER_GROUP
    ):
        raise CalibrationContractError("minimum_unique_books_per_group weakens floor")
    _exact_string_list(
        policy["required_session_phases"],
        _REQUIRED_PHASES,
        "required_session_phases",
    )
    _exact_string_list(policy["required_sides"], _REQUIRED_SIDES, "required_sides")
    _exact_string_list(
        policy["required_phase_buckets"],
        _REQUIRED_PHASE_BUCKETS,
        "required_phase_buckets",
    )
    _exact_string_list(
        policy["required_liquidity_tiers"],
        _REQUIRED_TIERS,
        "required_liquidity_tiers",
    )


def _resolve_input_path(base: Path, value: object) -> Path:
    raw = Path(_non_empty(value, "artifact.path"))
    return raw if raw.is_absolute() else (base / raw).resolve()


def _relative_artifact_path(path: Path, manifest_parent: Path) -> str:
    return Path(os.path.relpath(path, manifest_parent.resolve())).as_posix()


def build_analysis_report(manifest_path: Path) -> dict[str, object]:
    """Build one deterministic report without writing or mutating any input."""

    manifest = load_input_manifest(manifest_path)
    manifest_digest = _sha256(manifest["content_sha256"], "content_sha256")
    issues: list[dict[str, str]] = []
    cohort_mapping = _mapping(manifest["cohort"], "cohort")
    cohort_path = _resolve_input_path(manifest_path.parent, cohort_mapping["path"])
    try:
        cohort_raw = json.loads(
            _read_manifest_bound_bytes(
                cohort_path,
                cohort_mapping["sha256"],
                "cohort artifact",
            ).decode("utf-8")
        )
        cohort = LateDeliveryCohort.from_mapping(
            _mapping(cohort_raw, "cohort artifact")
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise CalibrationContractError(f"cohort artifact is invalid: {error}") from error

    calendar_mapping = _mapping(manifest["trading_calendar"], "trading_calendar")
    calendar_path = _resolve_input_path(manifest_path.parent, calendar_mapping["path"])
    try:
        calendar_bytes = _read_manifest_bound_bytes(
            calendar_path,
            calendar_mapping["sha256"],
            "trading calendar",
        )
        with tempfile.TemporaryDirectory(prefix="slippage-calendar-") as temporary:
            calendar_snapshot = Path(temporary) / "calendar.json"
            calendar_snapshot.write_bytes(calendar_bytes)
            calendar = ReviewedEquityCalendar.from_path(calendar_snapshot)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise CalibrationContractError(f"trading calendar is invalid: {error}") from error
    _validate_reviewed_equity_calendar(calendar)
    policy = _mapping(manifest["policy"], "policy")

    sessions = tuple(
        _analyze_market_session(
            manifest_path=manifest_path,
            raw_session=session,
            cohort=cohort,
            calendar=calendar,
            horizon_ms=_positive_int(
                policy["adverse_horizon_ms"],
                "adverse_horizon_ms",
            ),
            horizon_tolerance_ms=_positive_int(
                policy["horizon_observation_tolerance_ms"],
                "horizon_observation_tolerance_ms",
            ),
            maximum_source_receive_skew_ms=_positive_int(
                policy["maximum_source_receive_skew_ms"],
                "maximum_source_receive_skew_ms",
            ),
            maximum_book_age_ms=_positive_int(
                policy["maximum_book_age_ms"],
                "maximum_book_age_ms",
            ),
        )
        for session in _object_list(manifest["market_sessions"], "market_sessions")
    )
    for session in sessions:
        issues.extend(session.issues)

    valid_samples = tuple(
        sample
        for session in sessions
        if not session.issues
        for sample in session.samples
    )
    fill_diagnostics, fill_issues = _analyze_fill_exports(
        manifest_path=manifest_path,
        raw_exports=_object_list(manifest["fill_exports"], "fill_exports"),
        cohort=cohort,
    )
    issues.extend(fill_issues)

    groups = _group_proxy_samples(valid_samples)
    coverage, coverage_issues = _coverage_report(
        groups=groups,
        cohort=cohort,
        minimum_days=_positive_int(
            policy["minimum_distinct_trading_days"],
            "minimum_distinct_trading_days",
        ),
        minimum_samples=_positive_int(
            policy["minimum_samples_per_group"],
            "minimum_samples_per_group",
        ),
        minimum_unique_books=_positive_int(
            policy["minimum_unique_books_per_group"],
            "minimum_unique_books_per_group",
        ),
    )
    input_issue_codes = sorted(
        {
            item["code"]
            for item in issues
            if item["code"] != "FILL_V3_EVIDENCE_UNAVAILABLE"
        }
    )
    proxy_status = _proxy_qualification_status(input_issue_codes, coverage_issues)

    all_issues = sorted(
        [*issues, *coverage_issues],
        key=lambda item: (item["code"], item["scope"], item["detail"]),
    )
    report: dict[str, object] = {
        "schema_version": ANALYSIS_REPORT_SCHEMA,
        "report_id": f"slippage-proxy-{manifest_digest[:20]}",
        "input_manifest": {
            "manifest_id": manifest["manifest_id"],
            "content_sha256": manifest_digest,
        },
        "policy_lineage": dict(policy),
        "qualification": {
            "actual_execution_calibration": {
                "status": ACTUAL_EXECUTION_STATUS,
                "reason_codes": [
                    "NO_BROKER_ORDER_FILL_AUTHORITY_IN_CONTRACT",
                    "LOCAL_PAPER_FILL_V3_EXECUTION_AUTHORITY_FALSE",
                ],
            },
            "model_stress_proxy": {
                "status": proxy_status,
                "metric_use": (
                    "MODEL_STRESS_EVIDENCE_ONLY"
                    if proxy_status == PROXY_QUALIFIED
                    else METRIC_USE_PROHIBITION
                ),
                "reason_codes": sorted(
                    {item["code"] for item in [*issues, *coverage_issues]}
                ),
            },
        },
        "session_quality": [
            {
                "session_id": session.session_id,
                "session_date": (
                    session.session_date.isoformat()
                    if session.session_date is not None
                    else None
                ),
                "status": "QUALIFIED" if not session.issues else "NOT_QUALIFIED",
                "sample_count": session.sample_count,
                "tick_count": session.tick_count,
                "paired_book_count": session.paired_book_count,
                "missing_book_count": session.missing_book_count,
                "stale_book_count": session.stale_book_count,
                "causal_ordering_failure_count": session.causal_ordering_failure_count,
                "max_abs_source_receive_skew_ms": _optional_decimal_string(
                    session.max_abs_source_receive_skew_ms
                ),
                "reason_codes": sorted({item["code"] for item in session.issues}),
            }
            for session in sessions
        ],
        "coverage": coverage,
        "diagnostic_model_stress_metrics": groups,
        "local_paper_fill_v3_model_output_diagnostics": fill_diagnostics,
        "issues": all_issues,
        "limitations": [
            "No broker order, fill, queue-priority, market-impact, or account authority is represented.",
            "BBO, Tick, spread, tick-size, and short-horizon movement are model-stress proxies only.",
            "local_paper_fill.v3 prices are deterministic model outputs, not observed broker executions.",
            "The five-day and per-group sample floors are structural evidence gates, not statistical sufficiency claims.",
        ],
    }
    return report


def write_analysis_report_once(
    manifest_path: Path,
    output_path: Path,
) -> dict[str, object]:
    return write_sealed_json_once(output_path, build_analysis_report(manifest_path))


def _analyze_market_session(
    *,
    manifest_path: Path,
    raw_session: Mapping[str, object],
    cohort: LateDeliveryCohort,
    calendar: ReviewedEquityCalendar,
    horizon_ms: int,
    horizon_tolerance_ms: int,
    maximum_source_receive_skew_ms: int,
    maximum_book_age_ms: int,
) -> _SessionAnalysis:
    session_id = str(raw_session["session_id"])
    source_session_dir = _resolve_input_path(
        manifest_path.parent,
        raw_session["path"],
    )
    declared_phase = str(raw_session["session_phase"])
    issues: list[dict[str, str]] = []
    expected_digests = _mapping(raw_session["artifact_sha256"], "artifact_sha256")
    artifact_bytes: dict[str, bytes] = {}
    for name in _SESSION_ARTIFACTS:
        try:
            encoded = (source_session_dir / name).read_bytes()
        except OSError as error:
            issues.append(_issue("ARTIFACT_UNAVAILABLE", session_id, f"{name}: {error}"))
            continue
        if hashlib.sha256(encoded).hexdigest() != expected_digests[name]:
            issues.append(_issue("ARTIFACT_SHA256_MISMATCH", session_id, name))
            continue
        artifact_bytes[name] = encoded
    if issues:
        return _empty_session_analysis(session_id, issues)

    with tempfile.TemporaryDirectory(prefix="slippage-session-") as temporary:
        session_dir = Path(temporary)
        for name, encoded in artifact_bytes.items():
            (session_dir / name).write_bytes(encoded)
        return _analyze_verified_market_session(
            manifest_path=manifest_path,
            raw_session=raw_session,
            session_dir=session_dir,
            session_id=session_id,
            declared_phase=declared_phase,
            expected_digests=expected_digests,
            cohort=cohort,
            calendar=calendar,
            horizon_ms=horizon_ms,
            horizon_tolerance_ms=horizon_tolerance_ms,
            maximum_source_receive_skew_ms=maximum_source_receive_skew_ms,
            maximum_book_age_ms=maximum_book_age_ms,
        )


def _analyze_verified_market_session(
    *,
    manifest_path: Path,
    raw_session: Mapping[str, object],
    session_dir: Path,
    session_id: str,
    declared_phase: str,
    expected_digests: Mapping[str, object],
    cohort: LateDeliveryCohort,
    calendar: ReviewedEquityCalendar,
    horizon_ms: int,
    horizon_tolerance_ms: int,
    maximum_source_receive_skew_ms: int,
    maximum_book_age_ms: int,
) -> _SessionAnalysis:
    issues: list[dict[str, str]] = []
    session_date: date | None = None

    journal = verify_market_event_journal(session_dir)
    if not journal.valid or journal.manifest is None:
        detail = "; ".join(journal.errors) or "manifest unavailable"
        issues.append(_issue("JOURNAL_INTEGRITY_FAILED", session_id, detail))
        return _empty_session_analysis(session_id, issues)
    if journal.manifest.get("session_id") != session_id:
        issues.append(_issue("SESSION_IDENTITY_MISMATCH", session_id, "Journal session_id"))
    try:
        session_date = date.fromisoformat(str(journal.manifest["session_date"]))
    except ValueError:
        issues.append(_issue("SESSION_IDENTITY_MISMATCH", session_id, "session_date"))
    if session_date is not None:
        try:
            if not calendar.is_trading_day(session_date):
                issues.append(
                    _issue(
                        "REVIEWED_TRADING_DAY_NOT_QUALIFIED",
                        session_id,
                        session_date.isoformat(),
                    )
                )
        except ValueError as error:
            issues.append(
                _issue("REVIEWED_TRADING_DAY_NOT_QUALIFIED", session_id, str(error))
            )
    if journal.rejected_count:
        issues.append(
            _issue(
                "OUT_OF_ORDER_OR_REJECTED_EVENTS",
                session_id,
                f"rejected_count={journal.rejected_count}",
            )
        )

    exact = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=session_dir / "bootstrap_snapshot.json",
        instrument_reference_path=session_dir / "instrument_reference.json",
    )
    if not exact.valid:
        issues.append(
            _issue("EXACT_REPLAY_FAILED", session_id, "; ".join(exact.errors))
        )
    issues.extend(
        _validate_qualification_report(
            session_dir,
            session_id,
            journal.manifest,
            journal.records,
        )
    )
    issues.extend(
        _validate_descriptor_lineage(
            session_dir,
            session_id,
            cohort,
            session_date,
            journal.records,
        )
    )

    clock = raw_session.get("clock_disposition")
    approved_skew: Decimal | None = None
    if clock is None:
        issues.append(
            _issue(
                "CLOCK_DISPOSITION_MISSING",
                session_id,
                "reviewed source/receive comparability is required",
            )
        )
    else:
        try:
            approved_skew = _load_clock_disposition(
                manifest_path=manifest_path,
                raw_clock=_mapping(clock, "clock_disposition"),
                session_id=session_id,
                maximum_bound_ms=maximum_source_receive_skew_ms,
                horizon_ms=horizon_ms,
                market_session_manifest_sha256=str(
                    expected_digests["manifest.json"]
                ),
            )
        except (CalibrationContractError, OSError) as error:
            issues.append(_issue("CLOCK_DISPOSITION_INVALID", session_id, str(error)))

    try:
        samples, quality = _extract_proxy_samples(
            records=journal.records,
            cohort=cohort,
            session_date=session_date,
            declared_phase=declared_phase,
            horizon_ms=horizon_ms,
            horizon_tolerance_ms=horizon_tolerance_ms,
            maximum_book_age_ms=maximum_book_age_ms,
        )
    except (CalibrationContractError, KeyError, TypeError, ValueError) as error:
        issues.append(_issue("MARKET_EVENT_CONTRACT_FAILED", session_id, str(error)))
        return _SessionAnalysis(
            session_id=session_id,
            session_date=session_date,
            sample_count=0,
            tick_count=0,
            paired_book_count=0,
            missing_book_count=0,
            stale_book_count=0,
            causal_ordering_failure_count=0,
            max_abs_source_receive_skew_ms=None,
            samples=(),
            issues=tuple(issues),
        )

    max_skew = quality["max_abs_source_receive_skew_ms"]
    assert isinstance(max_skew, Decimal)
    if approved_skew is not None and max_skew > approved_skew:
        issues.append(
            _issue(
                "CLOCK_SKEW_EXCEEDS_REVIEWED_BOUND",
                session_id,
                f"observed={_decimal_string(max_skew)} approved={_decimal_string(approved_skew)}",
            )
        )
    missing_book_count = int(quality["missing_book_count"])
    stale_book_count = int(quality["stale_book_count"])
    causal_ordering_failure_count = int(quality["causal_ordering_failure_count"])
    if missing_book_count:
        issues.append(
            _issue(
                "MISSING_BOOK_FOR_TICK",
                session_id,
                f"missing_book_count={missing_book_count}",
            )
        )
    if stale_book_count:
        issues.append(
            _issue(
                "STALE_BOOK_FOR_TICK",
                session_id,
                f"stale_book_count={stale_book_count}",
            )
        )
    if causal_ordering_failure_count:
        issues.append(
            _issue(
                "BOOK_TICK_CAUSAL_ORDERING_FAILED",
                session_id,
                f"failure_count={causal_ordering_failure_count}",
            )
        )
    return _SessionAnalysis(
        session_id=session_id,
        session_date=session_date,
        sample_count=len(samples) if not issues else 0,
        tick_count=int(quality["tick_count"]),
        paired_book_count=int(quality["paired_book_count"]),
        missing_book_count=missing_book_count,
        stale_book_count=stale_book_count,
        causal_ordering_failure_count=causal_ordering_failure_count,
        max_abs_source_receive_skew_ms=max_skew,
        samples=tuple(samples) if not issues else (),
        issues=tuple(issues),
    )


def _empty_session_analysis(
    session_id: str,
    issues: list[dict[str, str]],
) -> _SessionAnalysis:
    return _SessionAnalysis(
        session_id=session_id,
        session_date=None,
        sample_count=0,
        tick_count=0,
        paired_book_count=0,
        missing_book_count=0,
        stale_book_count=0,
        causal_ordering_failure_count=0,
        max_abs_source_receive_skew_ms=None,
        samples=(),
        issues=tuple(issues),
    )


def _validate_qualification_report(
    session_dir: Path,
    session_id: str,
    journal_manifest: Mapping[str, object],
    records: tuple[Mapping[str, object], ...],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    try:
        raw = json.loads((session_dir / "qualification_report.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [_issue("QUALITY_REPORT_INVALID", session_id, str(error))]
    if not isinstance(raw, dict) or raw.get("session_id") != session_id:
        return [_issue("QUALITY_REPORT_INVALID", session_id, "session identity")]
    capture = raw.get("capture")
    exact = raw.get("exact_replay")
    safety = raw.get("safety")
    if not isinstance(capture, dict) or not isinstance(exact, dict) or not isinstance(safety, dict):
        return [_issue("QUALITY_REPORT_INVALID", session_id, "required sections")]
    counts = capture.get("stream_counts")
    lifecycle = capture.get("natural_lifecycle_events")
    capture_symbol = str(capture.get("symbol") or "").strip().upper()
    observed_counts: dict[tuple[str, str], int] = defaultdict(int)
    for record in records:
        if record.get("record_type") != "INGRESS":
            continue
        event = record.get("event")
        if not isinstance(event, Mapping):
            continue
        symbol = str(event.get("symbol") or "").strip().upper()
        stream_kind = str(event.get("stream_kind") or "")
        if symbol and stream_kind in {"TICK", "BIDASK"}:
            observed_counts[(symbol, stream_kind)] += 1
    observed_symbols = {symbol for symbol, _ in observed_counts}
    paired = (
        journal_manifest.get("source_mode") == "TICK_BIDASK"
        and bool(capture_symbol)
        and observed_symbols == {capture_symbol}
        and isinstance(counts, dict)
        and isinstance(counts.get("TICK"), int)
        and counts["TICK"] > 0
        and observed_counts.get((capture_symbol, "TICK")) == counts["TICK"]
        and isinstance(counts.get("BIDASK"), int)
        and counts["BIDASK"] > 0
        and observed_counts.get((capture_symbol, "BIDASK")) == counts["BIDASK"]
        and isinstance(lifecycle, list)
        and "SUBSCRIBE_ACKED" in lifecycle
    )
    if not paired:
        issues.append(
            _issue("PAIRED_TICK_BIDASK_ACK_NOT_QUALIFIED", session_id, "quality report")
        )
    if (
        raw.get("status") != "PASS"
        or raw.get("classification") != "CASE_A"
        or raw.get("requested_case") != "A"
        or exact.get("passed") is not True
    ):
        issues.append(_issue("CAPTURE_QUALITY_NOT_PASSED", session_id, "status/exact replay"))
    if (
        safety.get("subscribe_trade") is not False
        or safety.get("order_path") != "NOT_WIRED"
        or safety.get("foundation_flags_off") is not True
    ):
        issues.append(_issue("SAFETY_LINEAGE_INVALID", session_id, "quality report safety"))
    return issues


def _validate_descriptor_lineage(
    session_dir: Path,
    session_id: str,
    cohort: LateDeliveryCohort,
    session_date: date | None,
    records: tuple[Mapping[str, object], ...],
) -> list[dict[str, str]]:
    try:
        raw = json.loads((session_dir / "instrument_reference.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [_issue("DESCRIPTOR_LINEAGE_INVALID", session_id, str(error))]
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != "instrument-reference-v1"
        or raw.get("status") != "FINALIZED"
        or raw.get("session_id") != session_id
        or session_date is None
        or raw.get("session_date") != session_date.isoformat()
    ):
        return [_issue("DESCRIPTOR_LINEAGE_INVALID", session_id, "artifact identity")]
    references = raw.get("references")
    if not isinstance(references, list) or not references:
        return [_issue("DESCRIPTOR_LINEAGE_INVALID", session_id, "references missing")]
    symbols: set[str] = set()
    for item in references:
        if not isinstance(item, dict):
            return [_issue("DESCRIPTOR_LINEAGE_INVALID", session_id, "reference shape")]
        symbol = str(item.get("symbol") or "").strip().upper()
        symbols.add(symbol)
        eligible = (
            bool(symbol)
            and item.get("exchange") in {"TSE", "TWSE", "OTC", "TPEX"}
            and item.get("security_type") == "STK"
            and item.get("trading_unit_shares") == 1000
            and item.get("price_limit_applies") is True
            and bool(str(item.get("source_identity") or "").strip())
            and item.get("valid_from") == session_date.isoformat()
            and item.get("valid_to") == session_date.isoformat()
        )
        prices = (
            item.get("reference_price"),
            item.get("limit_down_price"),
            item.get("limit_up_price"),
        )
        if not eligible or not all(is_valid_common_stock_tick(price) for price in prices):
            return [
                _issue(
                    "COMMON_STOCK_DESCRIPTOR_NOT_ELIGIBLE",
                    session_id,
                    symbol or "missing-symbol",
                )
            ]
    unknown = sorted(symbols - set(cohort.symbols))
    if unknown:
        return [
            _issue(
                "LIQUIDITY_TAG_OR_COHORT_LINEAGE_MISSING",
                session_id,
                ",".join(unknown),
            )
        ]
    observed_symbols = {
        str(_mapping(record["event"], "event").get("symbol") or "").strip().upper()
        for record in records
        if record.get("record_type") == "INGRESS"
        and isinstance(record.get("event"), Mapping)
    }
    missing_references = sorted(observed_symbols - symbols)
    if missing_references:
        return [
            _issue(
                "DESCRIPTOR_LINEAGE_INVALID",
                session_id,
                "missing references: " + ",".join(missing_references),
            )
        ]
    return []


def _load_clock_disposition(
    *,
    manifest_path: Path,
    raw_clock: Mapping[str, object],
    session_id: str,
    maximum_bound_ms: int,
    horizon_ms: int,
    market_session_manifest_sha256: str,
) -> Decimal:
    path = _resolve_input_path(manifest_path.parent, raw_clock["path"])
    disposition = load_sealed_json(
        path,
        expected_schema=CLOCK_DISPOSITION_SCHEMA,
        expected_file_sha256=str(raw_clock["sha256"]),
    )
    expected = {
        "schema_version",
        "session_id",
        "status",
        "max_abs_source_receive_skew_ms",
        "review_basis",
        "review_authority",
        "review_evidence",
        "content_sha256",
    }
    if set(disposition) != expected:
        raise CalibrationContractError("clock disposition fields do not match contract")
    if disposition["session_id"] != session_id:
        raise CalibrationContractError("clock disposition session mismatch")
    if disposition["status"] != "REVIEWED_COMPARABLE":
        raise CalibrationContractError("clock disposition is not REVIEWED_COMPARABLE")
    if disposition["review_authority"] != "INDEPENDENT_REVIEWER":
        raise CalibrationContractError("clock review authority is not independent")
    _non_empty(disposition["review_basis"], "review_basis")
    evidence = _mapping(disposition["review_evidence"], "review_evidence")
    if set(evidence) != {"path", "sha256"}:
        raise CalibrationContractError("clock review evidence fields do not match contract")
    evidence_path = _resolve_input_path(path.parent, evidence["path"])
    bound = _decimal(disposition["max_abs_source_receive_skew_ms"], "max skew")
    if bound < 0 or bound > min(Decimal(maximum_bound_ms), Decimal(horizon_ms)):
        raise CalibrationContractError("clock skew bound exceeds analysis policy")
    _validate_clock_review_evidence(
        evidence_path,
        session_id=session_id,
        approved_bound=bound,
        expected_market_manifest_sha256=_sha256(
            market_session_manifest_sha256,
            "market_session_manifest_sha256",
        ),
        expected_file_sha256=_sha256(
            evidence["sha256"],
            "review_evidence.sha256",
        ),
    )
    return bound


def _extract_proxy_samples(
    *,
    records: tuple[Mapping[str, object], ...],
    cohort: LateDeliveryCohort,
    session_date: date | None,
    declared_phase: str,
    horizon_ms: int,
    horizon_tolerance_ms: int,
    maximum_book_age_ms: int,
) -> tuple[list[_ProxySample], dict[str, int | Decimal]]:
    if session_date is None:
        raise CalibrationContractError("session_date is unavailable")
    applied_ingress = {
        _positive_int(record["ingress_record_index"], "ingress_record_index")
        for record in records
        if record.get("record_type") == "DISPOSITION"
        and isinstance(record.get("result"), Mapping)
        and _mapping(record["result"], "result").get("projection_applied") is True
    }
    books: dict[str, _Book] = {}
    ticks_by_symbol: dict[str, list[_Tick]] = defaultdict(list)
    paired: list[tuple[_Tick, int, _Book]] = []
    tick_count = 0
    missing_book_count = 0
    stale_book_count = 0
    causal_ordering_failure_count = 0
    max_skew = Decimal("0")
    last_received_at: dict[tuple[str, str], datetime] = {}
    last_event_at: dict[tuple[str, str], datetime] = {}

    for record in records:
        if record.get("record_type") != "INGRESS":
            continue
        record_index = _positive_int(record["record_index"], "record_index")
        if record_index not in applied_ingress:
            continue
        event = _mapping(record["event"], "event")
        payload = _mapping(event["payload"], "event.payload")
        symbol = _non_empty(event["symbol"], "event.symbol").upper()
        try:
            cohort.tier_for(symbol)
        except KeyError as error:
            raise CalibrationContractError(
                f"liquidity tag is unavailable for symbol {symbol}"
            ) from error
        received_at = _aware_datetime(event["received_at"], "event.received_at")
        event_at = _aware_datetime(event["event_at"], "event.event_at")
        if received_at.astimezone(TAIPEI).date() != session_date:
            raise CalibrationContractError("received_at date does not match session")
        actual_phase = _classify_session_phase(event_at)
        receive_phase = _classify_session_phase(received_at)
        if actual_phase != declared_phase or receive_phase != declared_phase:
            raise CalibrationContractError(
                "event/receive phase does not match declared phase"
            )
        skew = abs(_milliseconds(event_at - received_at))
        max_skew = max(max_skew, skew)
        stream_kind = _non_empty(event["stream_kind"], "event.stream_kind")
        if stream_kind not in {"BIDASK", "TICK"}:
            continue
        ordering_key = (symbol, stream_kind)
        if (
            ordering_key in last_received_at
            and received_at < last_received_at[ordering_key]
        ):
            raise CalibrationContractError("received_at regressed within symbol/stream")
        if ordering_key in last_event_at and event_at < last_event_at[ordering_key]:
            raise CalibrationContractError("event_at regressed within symbol/stream")
        last_received_at[ordering_key] = received_at
        last_event_at[ordering_key] = event_at
        if payload.get("intraday_odd") is not False:
            raise CalibrationContractError("odd-lot evidence is outside common-stock policy")
        if payload.get("simulated_trade") is not False:
            raise CalibrationContractError("simulated market event is not eligible")
        if stream_kind == "BIDASK":
            bids = _decimal_list(payload.get("bid_prices"), "bid_prices")
            asks = _decimal_list(payload.get("ask_prices"), "ask_prices")
            if not bids or not asks or bids[0] >= asks[0]:
                raise CalibrationContractError("BIDASK has no valid non-crossed top book")
            if not is_valid_common_stock_tick(bids[0]) or not is_valid_common_stock_tick(
                asks[0]
            ):
                raise CalibrationContractError("BIDASK top book is off common-stock tick grid")
            books[symbol] = _Book(
                symbol=symbol,
                received_at=received_at,
                event_at=event_at,
                bid=bids[0],
                ask=asks[0],
                identity=_non_empty(event.get("event_id"), "event.event_id"),
            )
        elif stream_kind == "TICK":
            tick_count += 1
            price = _positive_decimal(payload.get("price"), "tick.price")
            if not is_valid_common_stock_tick(price):
                raise CalibrationContractError("Tick price is off common-stock tick grid")
            tick = _Tick(
                symbol=symbol,
                received_at=received_at,
                event_at=event_at,
                price=price,
            )
            symbol_ticks = ticks_by_symbol[symbol]
            tick_index = len(symbol_ticks)
            symbol_ticks.append(tick)
            book = books.get(symbol)
            if book is None:
                missing_book_count += 1
                continue
            if book.received_at > tick.received_at or book.event_at > tick.event_at:
                causal_ordering_failure_count += 1
                continue
            if _milliseconds(tick.received_at - book.received_at) > Decimal(
                maximum_book_age_ms
            ):
                stale_book_count += 1
                continue
            paired.append((tick, tick_index, book))

    samples: list[_ProxySample] = []
    horizon = timedelta(milliseconds=horizon_ms)
    tolerance = timedelta(milliseconds=horizon_tolerance_ms)
    tick_times = {
        symbol: [item.received_at for item in ticks]
        for symbol, ticks in ticks_by_symbol.items()
    }
    for tick, tick_index, book in paired:
        future_price: Decimal | None = None
        target = tick.received_at + horizon
        future_index = bisect_left(tick_times[tick.symbol], target)
        if future_index > tick_index and future_index < len(tick_times[tick.symbol]):
            future_tick = ticks_by_symbol[tick.symbol][future_index]
            if future_tick.received_at <= target + tolerance:
                future_price = future_tick.price
        mid = (book.bid + book.ask) / Decimal("2")
        spread_bps = (book.ask - book.bid) / mid * _BPS
        tier = cohort.tier_for(tick.symbol)
        phase_bucket = _classify_phase_bucket(tick.received_at, declared_phase)
        if phase_bucket is None:
            raise CalibrationContractError("sample is outside required phase buckets")
        for side, reference, source in (
            ("BUY", book.ask, "BEST_ASK"),
            ("SELL", book.bid, "BEST_BID"),
        ):
            adverse: Decimal | None = None
            if future_price is not None:
                adverse = (
                    max(Decimal("0"), future_price - reference) / reference * _BPS
                    if side == "BUY"
                    else max(Decimal("0"), reference - future_price) / reference * _BPS
                )
            samples.append(
                _ProxySample(
                    symbol=tick.symbol,
                    liquidity_tier=tier,
                    session_phase=declared_phase,
                    session_date=session_date,
                    side=side,
                    reference_source=source,
                    spread_bps=spread_bps,
                    reference_tick_bps=(
                        common_stock_tick_size(reference) / reference * _BPS
                    ),
                    crossing_bps=abs(reference - mid) / mid * _BPS,
                    adverse_movement_bps=adverse,
                    book_identity=book.identity,
                    phase_bucket=phase_bucket,
                )
            )
    return samples, {
        "tick_count": tick_count,
        "paired_book_count": len(paired),
        "missing_book_count": missing_book_count,
        "stale_book_count": stale_book_count,
        "causal_ordering_failure_count": causal_ordering_failure_count,
        "max_abs_source_receive_skew_ms": max_skew,
    }


def _group_proxy_samples(samples: tuple[_ProxySample, ...]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str], list[_ProxySample]] = defaultdict(list)
    for sample in samples:
        key = (
            sample.symbol,
            sample.liquidity_tier,
            sample.session_phase,
            sample.side,
            sample.reference_source,
        )
        grouped[key].append(sample)
    result: list[dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        symbol, tier, phase, side, source = key
        adverse = [
            item.adverse_movement_bps
            for item in values
            if item.adverse_movement_bps is not None
        ]
        result.append(
            {
                "dimensions": {
                    "symbol": symbol,
                    "liquidity_tier": tier,
                    "session_phase": phase,
                    "side": side,
                    "reference_source": source,
                },
                "coverage": {
                    "reference_sample_count": len(values),
                    "adverse_sample_count": len(adverse),
                    "missing_horizon_sample_count": len(values) - len(adverse),
                    "unique_book_count": len(
                        {item.book_identity for item in values}
                    ),
                    "observed_phase_buckets": sorted(
                        {item.phase_bucket for item in values}
                    ),
                    "distinct_trading_days": len(
                        {item.session_date for item in values}
                    ),
                },
                "metrics_bps": {
                    "spread": _distribution([item.spread_bps for item in values]),
                    "reference_tick_size": _distribution(
                        [item.reference_tick_bps for item in values]
                    ),
                    "crossing_half_spread": _distribution(
                        [item.crossing_bps for item in values]
                    ),
                    "short_horizon_adverse_movement": _distribution(adverse),
                },
            }
        )
    return result


def _coverage_report(
    *,
    groups: list[dict[str, object]],
    cohort: LateDeliveryCohort,
    minimum_days: int,
    minimum_samples: int,
    minimum_unique_books: int,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    indexed = {
        (
            str(_mapping(item["dimensions"], "dimensions")["symbol"]),
            str(_mapping(item["dimensions"], "dimensions")["session_phase"]),
            str(_mapping(item["dimensions"], "dimensions")["side"]),
        ): item
        for item in groups
    }
    gaps: list[dict[str, object]] = []
    qualified_count = 0
    for symbol in cohort.symbols:
        for phase in _REQUIRED_PHASES:
            for side in _REQUIRED_SIDES:
                item = indexed.get((symbol, phase, side))
                reference_count = 0
                adverse_count = 0
                distinct_days = 0
                unique_books = 0
                phase_buckets: set[str] = set()
                if item is not None:
                    group_coverage = _mapping(item["coverage"], "coverage")
                    reference_count = int(group_coverage["reference_sample_count"])
                    adverse_count = int(group_coverage["adverse_sample_count"])
                    distinct_days = int(group_coverage["distinct_trading_days"])
                    unique_books = int(group_coverage["unique_book_count"])
                    buckets = group_coverage["observed_phase_buckets"]
                    if not isinstance(buckets, list):
                        raise CalibrationContractError("observed_phase_buckets must be a list")
                    phase_buckets = {str(value) for value in buckets}
                missing = {
                    "reference_samples": max(0, minimum_samples - reference_count),
                    "adverse_samples": max(0, minimum_samples - adverse_count),
                    "unique_books": max(0, minimum_unique_books - unique_books),
                    "trading_days": max(0, minimum_days - distinct_days),
                    "phase_buckets": [
                        bucket
                        for bucket in _REQUIRED_PHASE_BUCKETS
                        if bucket not in phase_buckets
                    ],
                }
                if any(bool(value) for value in missing.values()):
                    gaps.append(
                        {
                            "symbol": symbol,
                            "liquidity_tier": cohort.tier_for(symbol),
                            "session_phase": phase,
                            "side": side,
                            "missing": missing,
                        }
                    )
                else:
                    qualified_count += 1
    expected_count = len(cohort.symbols) * len(_REQUIRED_PHASES) * len(_REQUIRED_SIDES)
    coverage = {
        "structural_floor_only_not_statistical_sufficiency": True,
        "minimum_distinct_trading_days_per_group": minimum_days,
        "minimum_reference_samples_per_group": minimum_samples,
        "minimum_adverse_samples_per_group": minimum_samples,
        "minimum_unique_books_per_group": minimum_unique_books,
        "required_phase_buckets_per_group": list(_REQUIRED_PHASE_BUCKETS),
        "expected_group_count": expected_count,
        "observed_group_count": len(groups),
        "qualified_group_count": qualified_count,
        "group_gaps": gaps,
    }
    issues = (
        []
        if not gaps
        else [
            _issue(
                "COVERAGE_FLOOR_NOT_MET",
                "all-groups",
                f"qualified={qualified_count}/{expected_count}",
            )
        ]
    )
    return coverage, issues


def _proxy_qualification_status(
    input_issue_codes: list[str],
    coverage_issues: list[dict[str, str]],
) -> str:
    if input_issue_codes:
        return PROXY_INPUT_NOT_QUALIFIED
    if coverage_issues:
        return PROXY_INSUFFICIENT
    return PROXY_QUALIFIED


def _analyze_fill_exports(
    *,
    manifest_path: Path,
    raw_exports: list[Mapping[str, object]],
    cohort: LateDeliveryCohort,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    if not raw_exports:
        return [], [
            _issue(
                "FILL_V3_EVIDENCE_UNAVAILABLE",
                "fill-exports",
                "no persisted local_paper_fill.v3 export is bound",
            )
        ]
    issues: list[dict[str, str]] = []
    rows: list[dict[str, object]] = []
    export_ids: set[str] = set()
    journal_record_ids: set[tuple[str, str]] = set()
    journal_fingerprints: set[tuple[str, str]] = set()
    journal_idempotency_identities: set[tuple[str, str]] = set()
    order_fill_identities: set[tuple[str, int]] = set()
    journal_ranges: dict[
        tuple[str, str, str],
        list[tuple[int, int]],
    ] = defaultdict(list)
    for raw_export in raw_exports:
        path = _resolve_input_path(manifest_path.parent, raw_export["path"])
        scope = path.name
        try:
            export = load_sealed_json(
                path,
                expected_schema=FILL_EXPORT_SCHEMA,
                expected_file_sha256=str(raw_export["sha256"]),
            )
            export_id = _non_empty(export.get("export_id"), "export_id")
            if export_id in export_ids:
                raise CalibrationContractError("fill export_id must be unique")
            export_ids.add(export_id)
            source_journal = _validate_source_journal(
                _mapping(export["source_journal"], "source_journal"),
                sealed=True,
            )
            snapshot = _mapping(source_journal["snapshot"], "snapshot")
            range_scope = (
                _non_empty(export.get("session_id"), "fill_export.session_id"),
                _sha256(snapshot["sha256"], "snapshot.sha256"),
                _sha256(
                    source_journal["journal_session_root_sha256"],
                    "journal_session_root_sha256",
                ),
            )
            sequence_range = (
                int(source_journal["sequence_start"]),
                int(source_journal["sequence_end"]),
            )
            if any(
                sequence_range[0] <= existing_end
                and existing_start <= sequence_range[1]
                for existing_start, existing_end in journal_ranges[range_scope]
            ):
                raise CalibrationContractError(
                    "fill exports contain overlapping source Journal ranges"
                )
            export_rows = _fill_export_rows(export, cohort, path)
            export_record_ids = {
                (str(row["_journal_session_id"]), str(row["_journal_record_id"]))
                for row in export_rows
            }
            export_fingerprints = {
                (str(row["_journal_session_id"]), str(row["_journal_fingerprint"]))
                for row in export_rows
            }
            export_idempotency_identities = {
                (
                    str(row["_journal_idempotency_scope"]),
                    str(row["_journal_idempotency_key"]),
                )
                for row in export_rows
                if row["_journal_idempotency_scope"] is not None
            }
            export_order_fill_identities = {
                (str(row["_fill_order_id"]), int(row["_fill_sequence"]))
                for row in export_rows
            }
            if (
                export_record_ids & journal_record_ids
                or export_fingerprints & journal_fingerprints
                or export_idempotency_identities & journal_idempotency_identities
                or export_order_fill_identities & order_fill_identities
            ):
                raise CalibrationContractError(
                    "fill exports contain duplicate Journal record identity"
                )
            if source_journal["repository_kind"] == "IN_MEMORY_TEST_FIXTURE":
                issues.append(
                    _issue(
                        "FILL_EXPORT_TEST_FIXTURE_ONLY",
                        scope,
                        "test repository evidence cannot qualify analysis",
                    )
                )
            journal_ranges[range_scope].append(sequence_range)
            journal_record_ids.update(export_record_ids)
            journal_fingerprints.update(export_fingerprints)
            journal_idempotency_identities.update(export_idempotency_identities)
            order_fill_identities.update(export_order_fill_identities)
            rows.extend(export_rows)
        except (
            CalibrationContractError,
            ProjectionRecoveryError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            issues.append(_issue("FILL_EXPORT_INVALID", scope, str(error)))

    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["symbol"]),
                str(row["liquidity_tier"]),
                str(row["session_phase"]),
                str(row["side"]),
                str(row["reference_source"]),
            )
        ].append(row)
    diagnostics: list[dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        diagnostics.append(
            {
                "dimensions": dict(
                    zip(
                        (
                            "symbol",
                            "liquidity_tier",
                            "session_phase",
                            "side",
                            "reference_source",
                        ),
                        key,
                        strict=True,
                    )
                ),
                "sample_count": len(values),
                "configured_slippage_bps": _distribution(
                    [_decimal(item["configured_bps"], "configured_bps") for item in values]
                ),
                "realized_model_slippage_bps": _distribution(
                    [_decimal(item["realized_bps"], "realized_bps") for item in values]
                ),
                "slippage_cost_twd": _distribution(
                    [_decimal(item["slippage_cost"], "slippage_cost") for item in values]
                ),
                "interpretation": "LOCAL_PAPER_MODEL_OUTPUT_NOT_BROKER_EXECUTION",
            }
        )
    return diagnostics, issues


def _fill_export_rows(
    export: Mapping[str, object],
    cohort: LateDeliveryCohort,
    export_path: Path,
) -> list[dict[str, object]]:
    expected = {
        "schema_version",
        "export_id",
        "session_id",
        "session_date",
        "settings_digest",
        "source_journal",
        "records",
        "content_sha256",
    }
    if set(export) != expected:
        raise CalibrationContractError("fill export fields do not match contract")
    session_id = _non_empty(export["session_id"], "fill_export.session_id")
    _non_empty(export["export_id"], "fill_export.export_id")
    session_date = _iso_date(export["session_date"], "fill_export.session_date")
    settings_digest = _sha256(export["settings_digest"], "settings_digest")
    source_journal = _validate_source_journal(
        _mapping(export["source_journal"], "source_journal"),
        sealed=True,
    )
    snapshot_reference = _mapping(
        source_journal["snapshot"],
        "snapshot",
    )
    snapshot_path = _resolve_input_path(
        export_path.parent,
        snapshot_reference["path"],
    )
    snapshot, snapshot_session, snapshot_records = _load_fill_journal_snapshot(
        snapshot_path,
        expected_file_sha256=str(snapshot_reference["sha256"]),
    )
    if (
        snapshot["repository_kind"] != source_journal["repository_kind"]
        or snapshot["journal_session_root_sha256"]
        != source_journal["journal_session_root_sha256"]
        or snapshot_session.session_id != session_id
        or snapshot_session.metadata.get("settings_digest") != settings_digest
    ):
        raise CalibrationContractError("fill export snapshot lineage mismatch")
    sequence_start = int(source_journal["sequence_start"])
    sequence_end = int(source_journal["sequence_end"])
    snapshot_sequences = [int(item["sequence"]) for item in snapshot_records]
    if sequence_start < snapshot_sequences[0] or sequence_end > snapshot_sequences[-1]:
        raise CalibrationContractError("fill export range is outside Journal snapshot")
    selected_snapshot_records = [
        item
        for item in snapshot_records
        if sequence_start <= int(item["sequence"]) <= sequence_end
        and _mapping(item["record"], "record").get("kind")
        == LOCAL_PAPER_FILL_V3_KIND
    ]
    rows: list[dict[str, object]] = []
    records = _object_list(export["records"], "fill_export.records")
    if not records:
        raise CalibrationContractError("fill export records must not be empty")
    if canonical_json_bytes(records) != canonical_json_bytes(selected_snapshot_records):
        raise CalibrationContractError(
            "sealed fills do not exactly match read-only Journal snapshot range"
        )
    previous_sequence = sequence_start - 1
    fingerprints: set[str] = set()
    record_ids: set[str] = set()
    idempotency_identities: set[tuple[str, str]] = set()
    order_fill_sequences: set[tuple[str, int]] = set()
    range_rows: list[dict[str, object]] = []
    for item in records:
        if set(item) != {"sequence", "fingerprint", "record"}:
            raise CalibrationContractError("fill export record fields do not match contract")
        sequence = _positive_int(item["sequence"], "fill sequence")
        if sequence <= previous_sequence or sequence > sequence_end:
            raise CalibrationContractError("fill export sequence is outside ordered range")
        previous_sequence = sequence
        raw_record = _mapping(item["record"], "record")
        record = _journal_record_from_mapping(raw_record)
        if record.session_id != session_id or record.kind != LOCAL_PAPER_FILL_V3_KIND:
            raise CalibrationContractError("fill record session/kind is invalid")
        fingerprint = _sha256(item["fingerprint"], "fingerprint")
        if record.fingerprint != fingerprint:
            raise CalibrationContractError("fill record fingerprint mismatch")
        if record.payload.get("settings_digest") != settings_digest:
            raise CalibrationContractError("fill record settings_digest mismatch")
        if fingerprint in fingerprints or record.record_id in record_ids:
            raise CalibrationContractError("fill export contains duplicate record identity")
        fingerprints.add(fingerprint)
        record_ids.add(record.record_id)
        if record.idempotency_scope is not None or record.idempotency_key is not None:
            if record.idempotency_scope is None or record.idempotency_key is None:
                raise CalibrationContractError("fill idempotency identity is incomplete")
            idempotency_identity = (record.idempotency_scope, record.idempotency_key)
            if idempotency_identity in idempotency_identities:
                raise CalibrationContractError("fill export contains duplicate idempotency identity")
            idempotency_identities.add(idempotency_identity)
        fill = LocalPaperFill.from_record(record)
        fill_sequence = _positive_int(
            record.payload.get("fill_sequence"),
            "fill_sequence",
        )
        fill_identity = (fill.order_id, fill_sequence)
        if fill_identity in order_fill_sequences:
            raise CalibrationContractError("fill export contains duplicate order fill sequence")
        order_fill_sequences.add(fill_identity)
        range_rows.append({"sequence": sequence, "fingerprint": fingerprint})
        if record.occurred_at.astimezone(TAIPEI).date() != session_date:
            raise CalibrationContractError("fill record date does not match export")
        try:
            tier = cohort.tier_for(fill.symbol)
        except KeyError as error:
            raise CalibrationContractError("fill symbol has no cohort lineage") from error
        phase = _classify_session_phase(record.occurred_at)
        if phase is None:
            raise CalibrationContractError("fill occurred outside supported market phases")
        rows.append(
            {
                "_journal_session_id": session_id,
                "_journal_sequence": sequence,
                "_journal_fingerprint": fingerprint,
                "_journal_record_id": record.record_id,
                "_journal_idempotency_scope": record.idempotency_scope,
                "_journal_idempotency_key": record.idempotency_key,
                "_fill_order_id": fill.order_id,
                "_fill_sequence": fill_sequence,
                "symbol": fill.symbol,
                "liquidity_tier": tier,
                "session_phase": phase,
                "side": fill.side.value,
                "reference_source": str(record.payload["reference_source"]),
                "configured_bps": record.payload["configured_slippage_bps"],
                "realized_bps": record.payload["realized_slippage_bps"],
                "slippage_cost": record.payload["slippage_cost"],
            }
        )
    if len(records) != source_journal["selected_record_count"]:
        raise CalibrationContractError("fill export selected_record_count mismatch")
    range_root = hashlib.sha256(canonical_json_bytes(range_rows)).hexdigest()
    if range_root != source_journal["selected_range_root_sha256"]:
        raise CalibrationContractError("fill export selected range root mismatch")
    return rows


def _validate_reviewed_equity_calendar(
    calendar: ReviewedEquityCalendar,
) -> None:
    try:
        approved_digest = file_sha256(twse_calendar_2026.PATH)
    except OSError as error:
        raise CalibrationContractError(
            "approved reviewed TWSE calendar is unavailable"
        ) from error
    if (
        calendar.schema_version != REVIEWED_EQUITY_CALENDAR_SCHEMA
        or calendar.timezone != "Asia/Taipei"
        or calendar.source_digest != approved_digest
    ):
        raise CalibrationContractError(
            "trading calendar does not match the approved reviewed TWSE artifact"
        )


def _journal_record_from_mapping(raw: Mapping[str, object]) -> JournalRecord:
    expected = {
        "record_id",
        "session_id",
        "kind",
        "occurred_at",
        "payload",
        "idempotency_scope",
        "idempotency_key",
        "schema_version",
    }
    if set(raw) != expected:
        raise CalibrationContractError("JournalRecord fields do not match contract")
    return JournalRecord(
        record_id=_non_empty(raw["record_id"], "record_id"),
        session_id=_non_empty(raw["session_id"], "session_id"),
        kind=_non_empty(raw["kind"], "kind"),
        occurred_at=_aware_datetime(raw["occurred_at"], "occurred_at"),
        payload=_mapping(raw["payload"], "payload"),
        idempotency_scope=_optional_string(raw["idempotency_scope"], "idempotency_scope"),
        idempotency_key=_optional_string(raw["idempotency_key"], "idempotency_key"),
        schema_version=_non_empty(raw["schema_version"], "schema_version"),
    )


def journal_record_to_export_mapping(record: JournalRecord) -> dict[str, object]:
    """Serialize an existing JournalRecord without changing its canonical payload."""

    return {
        "record_id": record.record_id,
        "session_id": record.session_id,
        "kind": record.kind,
        "occurred_at": record.occurred_at.isoformat(),
        "payload": json.loads(record.payload_json),
        "idempotency_scope": record.idempotency_scope,
        "idempotency_key": record.idempotency_key,
        "schema_version": record.schema_version,
    }


def _journal_session_to_mapping(session: JournalSession) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "started_at": session.started_at.isoformat(),
        "mode": session.mode,
        "metadata": json.loads(session.metadata_json),
        "schema_version": session.schema_version,
    }


def _journal_session_from_mapping(raw: Mapping[str, object]) -> JournalSession:
    expected = {"session_id", "started_at", "mode", "metadata", "schema_version"}
    if set(raw) != expected:
        raise CalibrationContractError("JournalSession fields do not match contract")
    return JournalSession(
        session_id=_non_empty(raw["session_id"], "session_id"),
        started_at=_aware_datetime(raw["started_at"], "started_at"),
        mode=_non_empty(raw["mode"], "mode"),
        metadata=_mapping(raw["metadata"], "metadata"),
        schema_version=_non_empty(raw["schema_version"], "schema_version"),
    )


def _distribution(values: list[Decimal]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": _decimal_string(ordered[0]),
        "p50": _decimal_string(_nearest_rank(ordered, Decimal("0.50"))),
        "p90": _decimal_string(_nearest_rank(ordered, Decimal("0.90"))),
        "p95": _decimal_string(_nearest_rank(ordered, Decimal("0.95"))),
        "p99": _decimal_string(_nearest_rank(ordered, Decimal("0.99"))),
        "max": _decimal_string(ordered[-1]),
    }


def _nearest_rank(values: list[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise ValueError("nearest-rank requires values")
    rank = max(1, math.ceil(Decimal(len(values)) * percentile))
    return values[rank - 1]


def _classify_session_phase(value: datetime) -> str | None:
    local = value.astimezone(TAIPEI).time().replace(tzinfo=None)
    windows = (
        (SessionPhase.OPENING.value, time(9, 0), time(9, 30)),
        (SessionPhase.CONTINUOUS.value, time(9, 30), time(13, 0)),
        (SessionPhase.CLOSE.value, time(13, 0), time(13, 30)),
    )
    for phase, starts, ends in windows:
        if starts <= local < ends:
            return phase
    return None


def _classify_phase_bucket(value: datetime, phase: str) -> str | None:
    local = value.astimezone(TAIPEI).time().replace(tzinfo=None)
    windows = {
        SessionPhase.OPENING.value: (
            ("EARLY", time(9, 0), time(9, 10)),
            ("MIDDLE", time(9, 10), time(9, 20)),
            ("LATE", time(9, 20), time(9, 30)),
        ),
        SessionPhase.CONTINUOUS.value: (
            ("EARLY", time(9, 30), time(10, 40)),
            ("MIDDLE", time(10, 40), time(11, 50)),
            ("LATE", time(11, 50), time(13, 0)),
        ),
        SessionPhase.CLOSE.value: (
            ("EARLY", time(13, 0), time(13, 10)),
            ("MIDDLE", time(13, 10), time(13, 20)),
            ("LATE", time(13, 20), time(13, 30)),
        ),
    }
    for bucket, starts, ends in windows.get(phase, ()):
        if starts <= local < ends:
            return bucket
    return None


def _issue(code: str, scope: str, detail: str) -> dict[str, str]:
    return {"code": code, "scope": scope, "detail": detail}


def _milliseconds(value: timedelta) -> Decimal:
    return Decimal(value.days * 86_400_000 + value.seconds * 1000) + (
        Decimal(value.microseconds) / Decimal("1000")
    )


def _decimal_string(value: Decimal) -> str:
    return canonical_decimal_string(value)


def _optional_decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else _decimal_string(value)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CalibrationContractError(f"{field_name} must be an object")
    return value


def _object_list(value: object, field_name: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise CalibrationContractError(f"{field_name} must be a list")
    return [_mapping(item, field_name) for item in value]


def _non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationContractError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty(value, field_name)


def _sha256(value: object, field_name: str) -> str:
    normalized = _non_empty(value, field_name).lower()
    if len(normalized) != 64:
        raise CalibrationContractError(f"{field_name} must be SHA-256")
    try:
        int(normalized, 16)
    except ValueError as error:
        raise CalibrationContractError(f"{field_name} must be SHA-256") from error
    return normalized


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CalibrationContractError(f"{field_name} must be a positive integer")
    return value


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise CalibrationContractError(f"{field_name} must be a finite decimal") from error
    if not parsed.is_finite():
        raise CalibrationContractError(f"{field_name} must be a finite decimal")
    return parsed


def _positive_decimal(value: object, field_name: str) -> Decimal:
    parsed = _decimal(value, field_name)
    if parsed <= 0:
        raise CalibrationContractError(f"{field_name} must be positive")
    return parsed


def _decimal_list(value: object, field_name: str) -> list[Decimal]:
    if not isinstance(value, list):
        raise CalibrationContractError(f"{field_name} must be a list")
    return [_positive_decimal(item, field_name) for item in value]


def _aware_datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_non_empty(value, field_name))
    except ValueError as error:
        raise CalibrationContractError(f"{field_name} must be ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CalibrationContractError(f"{field_name} must be timezone-aware")
    return parsed


def _iso_date(value: object, field_name: str) -> date:
    try:
        return date.fromisoformat(_non_empty(value, field_name))
    except ValueError as error:
        raise CalibrationContractError(f"{field_name} must be ISO date") from error


def _exact_string_list(value: object, expected: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, list) or tuple(value) != expected:
        raise CalibrationContractError(f"{field_name} must equal {list(expected)}")
