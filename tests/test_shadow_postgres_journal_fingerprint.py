from __future__ import annotations

from datetime import datetime

import pytest

from trading.journal import JournalAppendResult, JournalConflictError, JournalRecord
from trading.postgres_journal import PostgresJournalRepository


AT = datetime.fromisoformat("2026-08-27T09:00:00+08:00")


class FakeCursor:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        assert "fingerprint" in statement
        assert parameters == ("shadow-postgres-fingerprint", 0)

    def fetchall(self) -> tuple[tuple[object, ...], ...]:
        return self._rows


class FakeConnection:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self._rows = rows
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _record(*, payload: dict[str, object]) -> JournalRecord:
    return JournalRecord(
        record_id="shadow-postgres-record-1",
        session_id="shadow-postgres-fingerprint",
        kind="shadow_reader_contract.v1",
        occurred_at=AT,
        payload=payload,
        idempotency_scope="shadow-postgres-fingerprint:reader",
        idempotency_key="reader-1",
    )


def _row(record: JournalRecord, *, payload_json: str | None = None):
    return (
        1,
        record.record_id,
        record.kind,
        record.occurred_at,
        payload_json or record.payload_json,
        record.idempotency_scope,
        record.idempotency_key,
        record.schema_version,
        record.fingerprint,
    )


def test_postgres_reader_checks_stored_fingerprint_before_replay() -> None:
    original = _record(payload={"symbol": "2330"})
    valid_connection = FakeConnection((_row(original),))
    valid = PostgresJournalRepository(valid_connection)

    assert valid.records(original.session_id) == (
        JournalAppendResult(original, 1, False),
    )
    assert valid_connection.commits == 1

    tampered_connection = FakeConnection(
        (_row(original, payload_json='{"symbol":"2317"}'),)
    )
    tampered = PostgresJournalRepository(tampered_connection)

    with pytest.raises(JournalConflictError, match="stored fingerprint"):
        tampered.records(original.session_id)
    assert tampered_connection.rollbacks == 0
