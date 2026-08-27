"""Append-only Journal contracts and an ephemeral in-memory adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from threading import RLock
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from trading.canonical_values import canonical_decimal_string


JOURNAL_SCHEMA_VERSION = "journal-v1"


class JournalConflictError(ValueError):
    """A record or idempotency key was reused with different content."""


class JournalCutoffExceededError(RuntimeError):
    """An atomic Journal mutation did not finish before its durable cutoff."""


class JournalClockRegressionError(RuntimeError):
    """Authoritative time moved backwards during an atomic Journal mutation."""


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _json_default(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported Journal payload value: {type(value).__name__}")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True)
class JournalSession:
    """Versioned metadata for one append-only Journal session."""

    session_id: str
    started_at: datetime
    mode: str
    metadata: Mapping[str, Any]
    schema_version: str = JOURNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.mode, "mode")
        _require_non_empty(self.schema_version, "schema_version")
        _require_aware(self.started_at, "started_at")
        _canonical_json(self.metadata)

    @property
    def metadata_json(self) -> str:
        return _canonical_json(self.metadata)


@dataclass(frozen=True)
class JournalRecord:
    """One immutable, append-only business or market-data record."""

    record_id: str
    session_id: str
    kind: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    idempotency_scope: str | None = None
    idempotency_key: str | None = None
    schema_version: str = JOURNAL_SCHEMA_VERSION
    _payload_bytes: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.record_id, "record_id"),
            (self.session_id, "session_id"),
            (self.kind, "kind"),
            (self.schema_version, "schema_version"),
        ):
            _require_non_empty(value, field_name)
        _require_aware(self.occurred_at, "occurred_at")
        if (self.idempotency_scope is None) != (self.idempotency_key is None):
            raise ValueError(
                "idempotency_scope and idempotency_key must be set together"
            )
        if self.idempotency_scope is not None:
            _require_non_empty(self.idempotency_scope, "idempotency_scope")
            _require_non_empty(self.idempotency_key or "", "idempotency_key")
        payload_json = _canonical_json(self.payload)
        payload_snapshot = json.loads(payload_json)
        object.__setattr__(self, "payload", _freeze_json(payload_snapshot))
        object.__setattr__(self, "_payload_bytes", payload_json.encode("utf-8"))

    @property
    def payload_bytes(self) -> bytes:
        """The authoritative immutable canonical payload artifact."""

        return self._payload_bytes

    @property
    def payload_json(self) -> str:
        return self.payload_bytes.decode("utf-8")

    @property
    def fingerprint(self) -> str:
        payload = {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": json.loads(self.payload_json),
            "idempotency_scope": self.idempotency_scope,
            "idempotency_key": self.idempotency_key,
            "schema_version": self.schema_version,
        }
        return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


@dataclass(frozen=True)
class JournalAppendResult:
    record: JournalRecord
    sequence: int
    idempotent: bool


@dataclass(frozen=True)
class ProjectionCheckpoint:
    session_id: str
    projection_name: str
    journal_sequence: int
    digest: str
    schema_version: str = JOURNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.projection_name, "projection_name")
        _require_non_empty(self.digest, "digest")
        _require_non_empty(self.schema_version, "schema_version")
        if self.journal_sequence < 0:
            raise ValueError("journal_sequence must be non-negative")


@runtime_checkable
class JournalRepository(Protocol):
    """One authoritative write path per configured runtime mode."""

    def start_session(self, session: JournalSession) -> None:
        """Register immutable session metadata."""

    def session(self, session_id: str) -> JournalSession | None:
        """Return immutable session metadata for retry-stable recovery."""

    def sessions(
        self,
        *,
        session_id_prefix: str,
    ) -> tuple[JournalSession, ...]:
        """Return immutable sessions under one deterministic identity prefix."""

    def append(self, record: JournalRecord) -> JournalAppendResult:
        """Append a record or return the result of the matching retry."""

    def start_session_and_append_before(
        self,
        session: JournalSession,
        record: JournalRecord,
        *,
        latest_allowed_at: datetime,
        authoritative_now: Callable[[], datetime] | None = None,
    ) -> JournalAppendResult:
        """Atomically create a session/record only before a storage cutoff."""

    def records(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[JournalAppendResult, ...]:
        """Return append-order records after a checkpoint sequence."""

    def save_checkpoint(self, checkpoint: ProjectionCheckpoint) -> None:
        """Advance a projection checkpoint without moving it backward."""

    def latest_checkpoint(
        self,
        session_id: str,
        projection_name: str,
    ) -> ProjectionCheckpoint | None:
        """Return the current checkpoint for one projection."""


class InMemoryJournalRepository:
    """Ephemeral adapter with the same idempotency/checkpoint semantics."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, JournalSession] = {}
        self._records: list[JournalAppendResult] = []
        self._records_by_id: dict[tuple[str, str], JournalAppendResult] = {}
        self._records_by_idempotency: dict[
            tuple[str, str], JournalAppendResult
        ] = {}
        self._checkpoints: dict[tuple[str, str], ProjectionCheckpoint] = {}

    def start_session(self, session: JournalSession) -> None:
        with self._lock:
            existing = self._sessions.get(session.session_id)
            if existing is None:
                self._sessions[session.session_id] = session
                return
            if existing != session:
                raise JournalConflictError(
                    "session metadata conflicts with existing session"
                )

    def session(self, session_id: str) -> JournalSession | None:
        return self._sessions.get(session_id)

    def sessions(
        self,
        *,
        session_id_prefix: str,
    ) -> tuple[JournalSession, ...]:
        if type(session_id_prefix) is not str or not session_id_prefix.strip():
            raise ValueError("session_id_prefix must not be empty")
        return tuple(
            self._sessions[session_id]
            for session_id in sorted(self._sessions)
            if session_id.startswith(session_id_prefix)
        )

    def append(self, record: JournalRecord) -> JournalAppendResult:
        with self._lock:
            if record.session_id not in self._sessions:
                raise JournalConflictError(
                    "Journal session must be started before append"
                )

            existing = self._records_by_id.get(
                (record.session_id, record.record_id)
            )
            if existing is not None:
                return self._matching_retry(existing, record)

            if record.idempotency_scope is not None:
                idempotency = (
                    record.idempotency_scope,
                    record.idempotency_key or "",
                )
                existing = self._records_by_idempotency.get(idempotency)
                if existing is not None:
                    return self._matching_retry(existing, record)

            result = JournalAppendResult(
                record=record,
                sequence=len(self._records) + 1,
                idempotent=False,
            )
            self._records.append(result)
            self._records_by_id[(record.session_id, record.record_id)] = result
            if record.idempotency_scope is not None:
                self._records_by_idempotency[
                    (record.idempotency_scope, record.idempotency_key or "")
                ] = result
            return result

    def start_session_and_append_before(
        self,
        session: JournalSession,
        record: JournalRecord,
        *,
        latest_allowed_at: datetime,
        authoritative_now: Callable[[], datetime] | None = None,
    ) -> JournalAppendResult:
        if session.session_id != record.session_id:
            raise ValueError("atomic Journal session and record identity differ")
        _require_aware(latest_allowed_at, "latest_allowed_at")
        now = authoritative_now or (lambda: record.occurred_at)
        with self._lock:
            sessions = dict(self._sessions)
            records = list(self._records)
            records_by_id = dict(self._records_by_id)
            records_by_idempotency = dict(self._records_by_idempotency)
            try:
                accepted_at = now()
                self._require_monotonic_before_cutoff(
                    accepted_at,
                    latest_allowed_at,
                )
                existing_session = self._sessions.get(session.session_id)
                existing_record = self._records_by_id.get(
                    (record.session_id, record.record_id)
                )
                if (
                    existing_record is None
                    and record.idempotency_scope is not None
                ):
                    existing_record = self._records_by_idempotency.get(
                        (
                            record.idempotency_scope,
                            record.idempotency_key or "",
                        )
                    )
                if existing_session is not None and existing_record is None:
                    raise JournalConflictError(
                        "atomic Journal session exists without its open record"
                    )
                stored_at = (
                    existing_session.started_at
                    if existing_session is not None
                    else accepted_at
                )
                stored_session = replace(session, started_at=stored_at)
                stored_record = replace(record, occurred_at=stored_at)
                self.start_session(stored_session)
                after_session = now()
                self._require_monotonic_before_cutoff(
                    after_session,
                    latest_allowed_at,
                    previous=accepted_at,
                )
                appended = self.append(stored_record)
                self._require_monotonic_before_cutoff(
                    now(),
                    latest_allowed_at,
                    previous=after_session,
                )
                return appended
            except Exception:
                self._sessions = sessions
                self._records = records
                self._records_by_id = records_by_id
                self._records_by_idempotency = records_by_idempotency
                raise

    def records(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[JournalAppendResult, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        return tuple(
            result
            for result in self._records
            if result.record.session_id == session_id
            and result.sequence > after_sequence
        )

    def save_checkpoint(self, checkpoint: ProjectionCheckpoint) -> None:
        key = (checkpoint.session_id, checkpoint.projection_name)
        existing = self._checkpoints.get(key)
        if existing is None or checkpoint.journal_sequence > existing.journal_sequence:
            self._checkpoints[key] = checkpoint
            return
        if checkpoint != existing:
            raise JournalConflictError("projection checkpoint cannot move backward")

    def latest_checkpoint(
        self,
        session_id: str,
        projection_name: str,
    ) -> ProjectionCheckpoint | None:
        return self._checkpoints.get((session_id, projection_name))

    @staticmethod
    def _matching_retry(
        existing: JournalAppendResult,
        record: JournalRecord,
    ) -> JournalAppendResult:
        if existing.record.fingerprint != record.fingerprint:
            raise JournalConflictError("Journal identity conflicts with existing record")
        return JournalAppendResult(
            record=existing.record,
            sequence=existing.sequence,
            idempotent=True,
        )

    @staticmethod
    def _require_monotonic_before_cutoff(
        value: datetime,
        cutoff: datetime,
        *,
        previous: datetime | None = None,
    ) -> None:
        _require_aware(value, "authoritative Journal time")
        if previous is not None and value < previous:
            raise JournalClockRegressionError(
                "authoritative Journal time moved backwards"
            )
        if value > cutoff:
            raise JournalCutoffExceededError(
                "atomic Journal mutation exceeded its durable cutoff"
            )
