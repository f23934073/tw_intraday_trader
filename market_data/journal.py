"""Durable session-scoped journal for canonical market-event evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Mapping

from market_data.events import (
    EventEnvelope,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketStreamKind,
    StreamWatermark,
)
from market_data.health import DataHealthState
from market_data.ingestion import IngestResult, IngestStatus
from market_data.ingress import LifecycleIngressMessage
from market_data.serialization import (
    deserialize_event_envelope,
    serialize_event_envelope,
)


JOURNAL_SCHEMA_VERSION = "market-event-journal-v1"
_SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "market_event_schema",
        "session_id",
        "session_date",
        "timezone",
        "producer_identity",
        "source_mode",
        "started_at",
        "status",
        "record_count",
        "first_record_index",
        "last_record_index",
        "sha256",
        "statistics",
        "projection_digest",
        "shutdown",
        "incomplete_reason",
    }
)
_STATISTICS_FIELDS = frozenset({"accepted", "rejected", "incidents"})
_SHUTDOWN_FIELDS = frozenset({"queue_drained", "finalized_at"})
_PROJECTION_DIGEST_FIELDS = frozenset({"bar", "book", "health"})
_INGRESS_FIELDS = frozenset({"record_type", "record_index", "event"})
_DISPOSITION_FIELDS = frozenset(
    {
        "record_type",
        "record_index",
        "ingress_record_index",
        "event_id",
        "result",
    }
)
_SYSTEM_INCIDENT_FIELDS = frozenset(
    {"record_type", "record_index", "incident"}
)
_INCIDENT_FIELDS = frozenset(
    {
        "event_id",
        "session_id",
        "incident_type",
        "occurred_at",
        "ingress_sequence",
        "source_identity",
        "reason",
        "symbol",
        "raw_event_code",
        "raw_info",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "status",
        "event_id",
        "symbol",
        "stream_kind",
        "previous_watermark",
        "new_watermark",
        "projection_applied",
        "reason",
        "health_before",
        "health_after",
    }
)
_WATERMARK_FIELDS = frozenset({"event_time", "ingress_sequence"})


class JournalStatus(StrEnum):
    FINALIZED = "FINALIZED"
    INCOMPLETE = "INCOMPLETE"


class JournalRecordType(StrEnum):
    INGRESS = "INGRESS"
    DISPOSITION = "DISPOSITION"
    SYSTEM_INCIDENT = "SYSTEM_INCIDENT"


@dataclass(frozen=True)
class MarketEventJournalSummary:
    finalized_at: datetime
    queue_drained: bool
    projection_digest: Mapping[str, str]

    def __post_init__(self) -> None:
        _require_aware(self.finalized_at, "finalized_at")
        _validate_projection_digest(self.projection_digest)
        if not {"bar", "book"}.issubset(self.projection_digest):
            raise ValueError("journal summary requires bar/book digests")


@dataclass(frozen=True)
class JournalVerificationResult:
    valid: bool
    errors: tuple[str, ...]
    manifest: Mapping[str, object] | None
    calculated_sha256: str | None
    record_count: int
    event_count: int
    accepted_count: int
    rejected_count: int
    incident_count: int
    records: tuple[Mapping[str, object], ...]


class MarketEventJournalManifestBuilder:
    """Owns manifest counters without knowing file-system behavior."""

    def __init__(
        self,
        *,
        session_id: str,
        session_date: date,
        started_at: datetime,
        producer_identity: str,
        source_mode: str,
    ) -> None:
        _validate_session_metadata(
            session_id=session_id,
            session_date=session_date,
            started_at=started_at,
            producer_identity=producer_identity,
            source_mode=source_mode,
        )
        self._session_id = session_id
        self._session_date = session_date
        self._started_at = started_at
        self._producer_identity = producer_identity
        self._source_mode = source_mode
        self._record_count = 0
        self._accepted = 0
        self._rejected = 0
        self._incidents = 0

    def note_record(
        self,
        record_type: JournalRecordType,
        *,
        disposition: IngestResult | None = None,
    ) -> None:
        self._record_count += 1
        if record_type is JournalRecordType.SYSTEM_INCIDENT:
            self._incidents += 1
        elif record_type is JournalRecordType.DISPOSITION:
            if disposition is None:
                raise ValueError("disposition result is required")
            if disposition.projection_applied:
                self._accepted += 1
            else:
                self._rejected += 1

    def build(
        self,
        *,
        status: JournalStatus,
        sha256: str | None,
        projection_digest: Mapping[str, str],
        queue_drained: bool,
        finalized_at: datetime | None,
        incomplete_reason: str | None,
    ) -> dict[str, object]:
        if sha256 is not None and not _DIGEST_PATTERN.fullmatch(sha256):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        _validate_projection_digest(projection_digest)
        if finalized_at is not None:
            _require_aware(finalized_at, "finalized_at")
        if status is JournalStatus.FINALIZED:
            if not queue_drained or finalized_at is None or sha256 is None:
                raise ValueError("finalized journal requires drain, time, and digest")
            if incomplete_reason is not None:
                raise ValueError("finalized journal cannot have incomplete_reason")
            if not {"bar", "book"}.issubset(projection_digest):
                raise ValueError("finalized journal requires bar/book digests")
        elif incomplete_reason is not None and not incomplete_reason.strip():
            raise ValueError("incomplete_reason must not be blank")
        return {
            "schema": JOURNAL_SCHEMA_VERSION,
            "market_event_schema": MARKET_EVENT_SCHEMA_VERSION,
            "session_id": self._session_id,
            "session_date": self._session_date.isoformat(),
            "timezone": str(self._started_at.tzinfo),
            "producer_identity": self._producer_identity,
            "source_mode": self._source_mode,
            "started_at": self._started_at.isoformat(),
            "status": status.value,
            "record_count": self._record_count,
            "first_record_index": 1 if self._record_count else None,
            "last_record_index": self._record_count or None,
            "sha256": sha256,
            "statistics": {
                "accepted": self._accepted,
                "rejected": self._rejected,
                "incidents": self._incidents,
            },
            "projection_digest": dict(sorted(projection_digest.items())),
            "shutdown": {
                "queue_drained": queue_drained,
                "finalized_at": (
                    finalized_at.isoformat() if finalized_at is not None else None
                ),
            },
            "incomplete_reason": incomplete_reason,
        }


class JsonlMarketEventRecorder:
    """Single-writer JSONL adapter with flush/fsync-before-return semantics."""

    def __init__(
        self,
        *,
        root: Path,
        session_id: str,
        session_date: date,
        started_at: datetime,
        producer_identity: str,
        source_mode: str,
    ) -> None:
        _validate_session_metadata(
            session_id=session_id,
            session_date=session_date,
            started_at=started_at,
            producer_identity=producer_identity,
            source_mode=source_mode,
        )
        self._lock = RLock()
        self._session_id = session_id
        self._session_date = session_date
        self._builder = MarketEventJournalManifestBuilder(
            session_id=session_id,
            session_date=session_date,
            started_at=started_at,
            producer_identity=producer_identity,
            source_mode=source_mode,
        )
        self._hasher = hashlib.sha256()
        self._next_ingress_index = 0
        self._next_record_index = 1
        self._ingress_rows: dict[int, tuple[int, str]] = {}
        self._disposed_ingress: set[int] = set()
        self._failed = False
        self._closed = False
        root.mkdir(parents=True, exist_ok=True)
        self.session_dir = root / session_date.isoformat() / session_id
        self.session_dir.parent.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(exist_ok=False)
        self.records_path = self.session_dir / "records.jsonl"
        self.manifest_path = self.session_dir / "manifest.json"
        self._file = self.records_path.open("xb")
        self._file.flush()
        os.fsync(self._file.fileno())
        self._write_manifest_atomic(
            self._builder.build(
                status=JournalStatus.INCOMPLETE,
                sha256=None,
                projection_digest={},
                queue_drained=False,
                finalized_at=None,
                incomplete_reason="SESSION_OPEN",
            )
        )

    def record_market(
        self,
        *,
        record_index: int,
        envelope: EventEnvelope,
    ) -> None:
        with self._lock:
            self._require_writable()
            self._require_ingress_index(record_index)
            if (
                envelope.session_id != self._session_id
                or envelope.session_date != self._session_date
            ):
                raise ValueError("journal event session does not match writer")
            journal_index = self._next_record_index
            record = {
                "record_type": JournalRecordType.INGRESS.value,
                "record_index": journal_index,
                "event": json.loads(serialize_event_envelope(envelope)),
            }
            self._append(record, JournalRecordType.INGRESS)
            self._ingress_rows[record_index] = (journal_index, envelope.event_id)
            self._next_ingress_index += 1

    def record_lifecycle(
        self,
        *,
        record_index: int,
        message: LifecycleIngressMessage,
    ) -> None:
        with self._lock:
            self._require_writable()
            self._require_ingress_index(record_index)
            if message.session_id != self._session_id:
                raise ValueError("journal incident session does not match writer")
            record = {
                "record_type": JournalRecordType.SYSTEM_INCIDENT.value,
                "record_index": self._next_record_index,
                "incident": _incident_to_dict(message),
            }
            self._append(record, JournalRecordType.SYSTEM_INCIDENT)
            self._next_ingress_index += 1

    def record_disposition(
        self,
        *,
        record_index: int,
        result: IngestResult,
    ) -> None:
        with self._lock:
            self._require_writable()
            ingress = self._ingress_rows.get(record_index)
            if ingress is None:
                raise ValueError("disposition record_index has no market ingress")
            if record_index in self._disposed_ingress:
                raise ValueError("market ingress already has a disposition")
            ingress_record_index, event_id = ingress
            if result.event_id != event_id:
                raise ValueError("disposition event_id does not match ingress")
            record = {
                "record_type": JournalRecordType.DISPOSITION.value,
                "record_index": self._next_record_index,
                "ingress_record_index": ingress_record_index,
                "event_id": result.event_id,
                "result": _ingest_result_to_dict(result),
            }
            self._append(
                record,
                JournalRecordType.DISPOSITION,
                disposition=result,
            )
            self._disposed_ingress.add(record_index)

    def finalize(self, summary: MarketEventJournalSummary) -> Path:
        with self._lock:
            self._require_writable()
            if not summary.queue_drained:
                raise ValueError("journal cannot finalize before queue drain")
            pending = set(self._ingress_rows) - self._disposed_ingress
            if pending:
                raise ValueError(
                    "journal cannot finalize with missing dispositions: "
                    + ",".join(str(value) for value in sorted(pending))
                )
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
                manifest = self._builder.build(
                    status=JournalStatus.FINALIZED,
                    sha256=self._hasher.hexdigest(),
                    projection_digest=summary.projection_digest,
                    queue_drained=True,
                    finalized_at=summary.finalized_at,
                    incomplete_reason=None,
                )
                self._write_manifest_atomic(manifest)
            except Exception:
                self._failed = True
                raise
            finally:
                self._file.close()
                self._closed = True
            return self.manifest_path

    def mark_incomplete(
        self,
        *,
        reason: str,
        occurred_at: datetime,
    ) -> Path:
        with self._lock:
            if self._closed:
                raise ValueError("journal is already closed")
            if not reason.strip():
                raise ValueError("incomplete reason must not be blank")
            _require_aware(occurred_at, "occurred_at")
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
                manifest = self._builder.build(
                    status=JournalStatus.INCOMPLETE,
                    sha256=self._hasher.hexdigest(),
                    projection_digest={},
                    queue_drained=False,
                    finalized_at=occurred_at,
                    incomplete_reason=reason,
                )
                self._write_manifest_atomic(manifest)
            except Exception:
                self._failed = True
                raise
            finally:
                self._file.close()
                self._closed = True
            return self.manifest_path

    def close(self) -> None:
        """Close without claiming completeness; the initial manifest remains."""
        with self._lock:
            if not self._closed:
                self._file.close()
                self._closed = True

    def _append(
        self,
        record: Mapping[str, object],
        record_type: JournalRecordType,
        *,
        disposition: IngestResult | None = None,
    ) -> None:
        encoded = _canonical_json_bytes(record)
        try:
            self._file.write(encoded)
            self._file.flush()
            os.fsync(self._file.fileno())
        except Exception:
            self._failed = True
            raise
        self._hasher.update(encoded)
        self._builder.note_record(record_type, disposition=disposition)
        self._next_record_index += 1

    def _write_manifest_atomic(self, manifest: Mapping[str, object]) -> None:
        temporary = self.session_dir / "manifest.json.tmp"
        encoded = _canonical_json_bytes(manifest)
        try:
            with temporary.open("xb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.manifest_path)
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_fd = os.open(self.session_dir, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _require_writable(self) -> None:
        if self._closed:
            raise ValueError("journal is closed")
        if self._failed:
            raise OSError("journal is failed")

    def _require_ingress_index(self, record_index: int) -> None:
        if record_index != self._next_ingress_index:
            raise ValueError(
                "journal ingress index must be contiguous; "
                f"expected {self._next_ingress_index}, got {record_index}"
            )


def verify_market_event_journal(
    session_dir: Path,
    *,
    require_finalized: bool = True,
) -> JournalVerificationResult:
    errors: list[str] = []
    manifest = _load_manifest(session_dir / "manifest.json", errors)
    records_path = session_dir / "records.jsonl"
    try:
        content = records_path.read_bytes()
    except OSError as error:
        errors.append(f"records.jsonl unavailable: {error}")
        return _verification_result(errors, manifest, None, (), {})

    calculated_sha256 = hashlib.sha256(content).hexdigest()
    if manifest is not None:
        if manifest.get("sha256") != calculated_sha256:
            errors.append("records.jsonl sha256 does not match manifest")
        if require_finalized and manifest.get("status") != JournalStatus.FINALIZED:
            errors.append("journal status is INCOMPLETE; FINALIZED is required")
    if content and not content.endswith(b"\n"):
        errors.append("records.jsonl must end with a newline")

    records: list[Mapping[str, object]] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        try:
            decoded = raw_line.decode("utf-8")
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"line {line_number} is not valid UTF-8 JSON: {error}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number} must be a JSON object")
            continue
        if _canonical_json_bytes(value).rstrip(b"\n") != raw_line:
            errors.append(f"line {line_number} is not canonical JSON")
        records.append(value)

    ingress_by_record: dict[int, EventEnvelope] = {}
    disposed: set[int] = set()
    statistics = {"accepted": 0, "rejected": 0, "incidents": 0}
    last_ingress_sequence = -1
    for expected_index, record in enumerate(records, start=1):
        actual_index = _record_index(record, expected_index, errors)
        if actual_index != expected_index:
            errors.append(
                f"record_index must be contiguous; expected {expected_index}, "
                f"got {actual_index}"
            )
        record_type = _journal_record_type(record, expected_index, errors)
        if record_type is JournalRecordType.INGRESS:
            envelope = _verify_ingress_record(record, expected_index, errors)
            if envelope is not None and actual_index is not None:
                ingress_by_record[actual_index] = envelope
                if manifest is not None and (
                    envelope.session_id != manifest.get("session_id")
                    or envelope.session_date.isoformat()
                    != manifest.get("session_date")
                ):
                    errors.append("INGRESS session does not match manifest")
                if envelope.ingress_sequence <= last_ingress_sequence:
                    errors.append("recorded ingress_sequence must be increasing")
                last_ingress_sequence = envelope.ingress_sequence
        elif record_type is JournalRecordType.DISPOSITION:
            applied = _verify_disposition_record(
                record,
                expected_index,
                ingress_by_record,
                disposed,
                errors,
            )
            if applied is not None:
                statistics["accepted" if applied else "rejected"] += 1
        elif record_type is JournalRecordType.SYSTEM_INCIDENT:
            sequence = _verify_incident_record(
                record,
                expected_index,
                manifest.get("session_id") if manifest is not None else None,
                errors,
            )
            statistics["incidents"] += 1
            if sequence is not None:
                if sequence <= last_ingress_sequence:
                    errors.append("recorded ingress_sequence must be increasing")
                last_ingress_sequence = sequence

    if manifest is not None:
        _verify_manifest_counts(manifest, records, statistics, errors)
        if manifest.get("status") == JournalStatus.FINALIZED:
            missing = set(ingress_by_record) - disposed
            if missing:
                errors.append("finalized journal has ingress without disposition")
    return _verification_result(
        errors,
        manifest,
        calculated_sha256,
        tuple(records),
        statistics,
    )


def _load_manifest(
    path: Path,
    errors: list[str],
) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"manifest.json is unavailable or invalid: {error}")
        return None
    if not isinstance(value, dict):
        errors.append("manifest.json must be a JSON object")
        return None
    _require_fields(value, _MANIFEST_FIELDS, "manifest", errors)
    try:
        if value.get("schema") != JOURNAL_SCHEMA_VERSION:
            raise ValueError("unsupported journal schema")
        if value.get("market_event_schema") != MARKET_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported market event schema")
        _require_non_empty_string(value, "session_id")
        date.fromisoformat(_require_non_empty_string(value, "session_date"))
        _require_non_empty_string(value, "timezone")
        _require_non_empty_string(value, "producer_identity")
        _require_non_empty_string(value, "source_mode")
        _parse_aware(_require_non_empty_string(value, "started_at"), "started_at")
        status = JournalStatus(_require_non_empty_string(value, "status"))
        _optional_non_negative_integer(value.get("first_record_index"))
        _optional_non_negative_integer(value.get("last_record_index"))
        _non_negative_integer(value.get("record_count"), "record_count")
        sha256 = value.get("sha256")
        if sha256 is not None and (
            not isinstance(sha256, str) or not _DIGEST_PATTERN.fullmatch(sha256)
        ):
            raise ValueError("manifest sha256 is invalid")
        _verify_statistics(value.get("statistics"))
        projection_digest = _verify_projection_digest(
            value.get("projection_digest")
        )
        shutdown = _verify_shutdown(value.get("shutdown"))
        reason = value.get("incomplete_reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("incomplete_reason is invalid")
        if status is JournalStatus.FINALIZED:
            if sha256 is None:
                raise ValueError("FINALIZED manifest requires sha256")
            if not shutdown["queue_drained"] or shutdown["finalized_at"] is None:
                raise ValueError("FINALIZED manifest requires drained shutdown")
            if reason is not None:
                raise ValueError("FINALIZED manifest cannot have incomplete_reason")
            if not {"bar", "book"}.issubset(projection_digest):
                raise ValueError("FINALIZED manifest requires bar/book digests")
        elif reason is None:
            raise ValueError("INCOMPLETE manifest requires incomplete_reason")
    except (TypeError, ValueError) as error:
        errors.append(f"manifest contract violation: {error}")
    return value


def _verify_ingress_record(
    record: Mapping[str, object],
    line_number: int,
    errors: list[str],
) -> EventEnvelope | None:
    _require_fields(record, _INGRESS_FIELDS, f"line {line_number} INGRESS", errors)
    event = record.get("event")
    if not isinstance(event, dict):
        errors.append(f"line {line_number} event must be an object")
        return None
    try:
        return deserialize_event_envelope(
            json.dumps(event, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"line {line_number} event contract violation: {error}")
        return None


def _verify_disposition_record(
    record: Mapping[str, object],
    line_number: int,
    ingress_by_record: Mapping[int, EventEnvelope],
    disposed: set[int],
    errors: list[str],
) -> bool | None:
    _require_fields(
        record,
        _DISPOSITION_FIELDS,
        f"line {line_number} DISPOSITION",
        errors,
    )
    try:
        ingress_index = _positive_integer(
            record.get("ingress_record_index"),
            "ingress_record_index",
        )
        envelope = ingress_by_record[ingress_index]
        if ingress_index in disposed:
            raise ValueError("ingress already has a disposition")
        event_id = _require_non_empty_string(record, "event_id")
        if event_id != envelope.event_id:
            raise ValueError("disposition event_id does not match ingress")
        result = record.get("result")
        if not isinstance(result, dict):
            raise ValueError("result must be an object")
        _require_fields(result, _RESULT_FIELDS, "disposition result", errors)
        status = IngestStatus(_require_non_empty_string(result, "status"))
        if _require_non_empty_string(result, "event_id") != envelope.event_id:
            raise ValueError("result event_id does not match ingress")
        if _require_non_empty_string(result, "symbol") != envelope.symbol:
            raise ValueError("result symbol does not match ingress")
        if MarketStreamKind(
            _require_non_empty_string(result, "stream_kind")
        ) is not envelope.stream_kind:
            raise ValueError("result stream_kind does not match ingress")
        projection_applied = result.get("projection_applied")
        if not isinstance(projection_applied, bool):
            raise ValueError("projection_applied must be boolean")
        expected_applied = status in {
            IngestStatus.APPLIED,
            IngestStatus.APPLIED_HEALTH_BLOCKED,
        }
        if projection_applied is not expected_applied:
            raise ValueError("projection_applied does not match status")
        _verify_optional_watermark(result.get("previous_watermark"))
        _verify_optional_watermark(result.get("new_watermark"))
        DataHealthState(_require_non_empty_string(result, "health_before"))
        DataHealthState(_require_non_empty_string(result, "health_after"))
        reason = result.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("result reason must be a string or null")
        disposed.add(ingress_index)
        return projection_applied
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"line {line_number} disposition contract violation: {error}")
        return None


def _verify_incident_record(
    record: Mapping[str, object],
    line_number: int,
    expected_session_id: object,
    errors: list[str],
) -> int | None:
    _require_fields(
        record,
        _SYSTEM_INCIDENT_FIELDS,
        f"line {line_number} SYSTEM_INCIDENT",
        errors,
    )
    incident = record.get("incident")
    if not isinstance(incident, dict):
        errors.append(f"line {line_number} incident must be an object")
        return None
    _require_fields(incident, _INCIDENT_FIELDS, "system incident", errors)
    try:
        for field_name in (
            "event_id",
            "session_id",
            "incident_type",
            "source_identity",
            "reason",
        ):
            _require_non_empty_string(incident, field_name)
        if (
            expected_session_id is not None
            and incident.get("session_id") != expected_session_id
        ):
            raise ValueError("incident session does not match manifest")
        _parse_aware(
            _require_non_empty_string(incident, "occurred_at"),
            "occurred_at",
        )
        sequence = _non_negative_integer(
            incident.get("ingress_sequence"),
            "ingress_sequence",
        )
        for field_name in ("symbol", "raw_info"):
            value = incident.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{field_name} must be a string or null")
        raw_code = incident.get("raw_event_code")
        if raw_code is not None and (
            isinstance(raw_code, bool) or not isinstance(raw_code, int)
        ):
            raise ValueError("raw_event_code must be an integer or null")
        return sequence
    except (TypeError, ValueError) as error:
        errors.append(f"line {line_number} incident contract violation: {error}")
        return None


def _verify_manifest_counts(
    manifest: Mapping[str, object],
    records: list[Mapping[str, object]],
    statistics: Mapping[str, int],
    errors: list[str],
) -> None:
    if manifest.get("record_count") != len(records):
        errors.append("manifest record_count does not match records.jsonl")
    expected_first = 1 if records else None
    expected_last = len(records) or None
    if manifest.get("first_record_index") != expected_first:
        errors.append("manifest first_record_index does not match records.jsonl")
    if manifest.get("last_record_index") != expected_last:
        errors.append("manifest last_record_index does not match records.jsonl")
    if manifest.get("statistics") != statistics:
        errors.append("manifest statistics do not match records.jsonl")


def _verification_result(
    errors: list[str],
    manifest: Mapping[str, object] | None,
    calculated_sha256: str | None,
    records: tuple[Mapping[str, object], ...],
    statistics: Mapping[str, int],
) -> JournalVerificationResult:
    event_count = sum(
        record.get("record_type") == JournalRecordType.INGRESS for record in records
    )
    return JournalVerificationResult(
        valid=not errors,
        errors=tuple(errors),
        manifest=manifest,
        calculated_sha256=calculated_sha256,
        record_count=len(records),
        event_count=event_count,
        accepted_count=statistics.get("accepted", 0),
        rejected_count=statistics.get("rejected", 0),
        incident_count=statistics.get("incidents", 0),
        records=records,
    )


def _ingest_result_to_dict(result: IngestResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "event_id": result.event_id,
        "symbol": result.symbol,
        "stream_kind": result.stream_kind.value,
        "previous_watermark": _watermark_to_dict(result.previous_watermark),
        "new_watermark": _watermark_to_dict(result.new_watermark),
        "projection_applied": result.projection_applied,
        "reason": result.reason,
        "health_before": result.health_before.value,
        "health_after": result.health_after.value,
    }


def _watermark_to_dict(value: StreamWatermark | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "event_time": value.event_time.isoformat(),
        "ingress_sequence": value.ingress_sequence,
    }


def _incident_to_dict(message: LifecycleIngressMessage) -> dict[str, object]:
    return {
        "event_id": message.event_id,
        "session_id": message.session_id,
        "incident_type": message.event_type,
        "occurred_at": message.occurred_at.isoformat(),
        "ingress_sequence": message.ingress_sequence,
        "source_identity": message.source_identity,
        "reason": message.reason,
        "symbol": message.symbol,
        "raw_event_code": message.raw_event_code,
        "raw_info": message.raw_info,
    }


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _validate_session_metadata(
    *,
    session_id: str,
    session_date: date,
    started_at: datetime,
    producer_identity: str,
    source_mode: str,
) -> None:
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must be a path-safe identifier")
    if started_at.date() != session_date:
        raise ValueError("started_at date must match session_date")
    _require_aware(started_at, "started_at")
    if not producer_identity.strip():
        raise ValueError("producer_identity must not be empty")
    if not source_mode.strip():
        raise ValueError("source_mode must not be empty")


def _validate_projection_digest(value: Mapping[str, str]) -> None:
    unknown = set(value) - _PROJECTION_DIGEST_FIELDS
    if unknown:
        raise ValueError(f"unknown projection digests: {sorted(unknown)}")
    for name, digest in value.items():
        if not isinstance(digest, str) or not _DIGEST_PATTERN.fullmatch(digest):
            raise ValueError(f"projection digest {name} is invalid")


def _verify_projection_digest(value: object) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise ValueError("projection_digest must be an object")
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        raise ValueError("projection_digest values must be strings")
    _validate_projection_digest(value)
    return value


def _verify_statistics(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _STATISTICS_FIELDS:
        raise ValueError("statistics fields do not match contract")
    for field_name in _STATISTICS_FIELDS:
        _non_negative_integer(value.get(field_name), field_name)


def _verify_shutdown(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != _SHUTDOWN_FIELDS:
        raise ValueError("shutdown fields do not match contract")
    if not isinstance(value.get("queue_drained"), bool):
        raise ValueError("queue_drained must be boolean")
    finalized_at = value.get("finalized_at")
    if finalized_at is not None:
        if not isinstance(finalized_at, str):
            raise ValueError("finalized_at must be a string or null")
        _parse_aware(finalized_at, "finalized_at")
    return value


def _verify_optional_watermark(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != _WATERMARK_FIELDS:
        raise ValueError("watermark fields do not match contract")
    _parse_aware(_require_non_empty_string(value, "event_time"), "event_time")
    _non_negative_integer(value.get("ingress_sequence"), "ingress_sequence")


def _record_index(
    record: Mapping[str, object],
    line_number: int,
    errors: list[str],
) -> int | None:
    try:
        return _positive_integer(record.get("record_index"), "record_index")
    except ValueError as error:
        errors.append(f"line {line_number} record_index violation: {error}")
        return None


def _journal_record_type(
    record: Mapping[str, object],
    line_number: int,
    errors: list[str],
) -> JournalRecordType | None:
    try:
        return JournalRecordType(_require_non_empty_string(record, "record_type"))
    except (TypeError, ValueError) as error:
        errors.append(f"line {line_number} record_type violation: {error}")
        return None


def _require_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
    errors: list[str],
) -> None:
    if set(value) != expected:
        errors.append(
            f"{label} fields do not match contract; "
            f"missing={sorted(expected - set(value))}, "
            f"unknown={sorted(set(value) - expected)}"
        )


def _require_non_empty_string(
    value: Mapping[str, object],
    field_name: str,
) -> str:
    item = value.get(field_name)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return item


def _positive_integer(value: object, field_name: str) -> int:
    result = _non_negative_integer(value, field_name)
    if result == 0:
        raise ValueError(f"{field_name} must be positive")
    return result


def _optional_non_negative_integer(value: object) -> int | None:
    if value is None:
        return None
    return _non_negative_integer(value, "record index")


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _parse_aware(value: str, field_name: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    _require_aware(parsed, field_name)
    return parsed


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
