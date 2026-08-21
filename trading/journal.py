"""Append-only Journal contracts and an ephemeral in-memory adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from trading.canonical_values import canonical_decimal_string


JOURNAL_SCHEMA_VERSION = "journal-v1"


class JournalConflictError(ValueError):
    """A record or idempotency key was reused with different content."""


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

    def append(self, record: JournalRecord) -> JournalAppendResult:
        """Append a record or return the result of the matching retry."""

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
        self._sessions: dict[str, JournalSession] = {}
        self._records: list[JournalAppendResult] = []
        self._records_by_id: dict[tuple[str, str], JournalAppendResult] = {}
        self._records_by_idempotency: dict[
            tuple[str, str], JournalAppendResult
        ] = {}
        self._checkpoints: dict[tuple[str, str], ProjectionCheckpoint] = {}

    def start_session(self, session: JournalSession) -> None:
        existing = self._sessions.get(session.session_id)
        if existing is None:
            self._sessions[session.session_id] = session
            return
        if existing != session:
            raise JournalConflictError("session metadata conflicts with existing session")

    def session(self, session_id: str) -> JournalSession | None:
        return self._sessions.get(session_id)

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if record.session_id not in self._sessions:
            raise JournalConflictError("Journal session must be started before append")

        existing = self._records_by_id.get((record.session_id, record.record_id))
        if existing is not None:
            return self._matching_retry(existing, record)

        if record.idempotency_scope is not None:
            idempotency = (record.idempotency_scope, record.idempotency_key or "")
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
