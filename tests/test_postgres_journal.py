import os
from dataclasses import replace
from datetime import datetime

import pytest


TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_DSN,
    reason="requires explicit TEST_POSTGRES_DSN",
)

from trading.journal import (  # noqa: E402
    JournalConflictError,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.migrations import apply_migrations  # noqa: E402
from trading.postgres_journal import PostgresJournalRepository  # noqa: E402


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")


@pytest.fixture()
def journal():
    connection = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP TABLE IF EXISTS projection_checkpoints, journal_records,
                journal_sessions, journal_schema_migrations CASCADE
                """
            )
        connection.commit()
        apply_migrations(connection)
        repository = PostgresJournalRepository(connection)
        repository.start_session(
            JournalSession(
                session_id="postgres-20260818",
                started_at=AT,
                mode="LOCAL_PAPER",
                metadata={"provider": "MockProvider"},
            )
        )
        yield repository
    finally:
        connection.close()


def record(*, payload: dict[str, object] | None = None) -> JournalRecord:
    return JournalRecord(
        record_id="command-1",
        session_id="postgres-20260818",
        kind="command_record",
        occurred_at=AT,
        payload=payload or {"symbol": "2330"},
        idempotency_scope="postgres-20260818:manual",
        idempotency_key="browser-1",
    )


def test_postgres_migration_append_idempotency_and_checkpoint(journal) -> None:
    first = journal.append(record())
    retry = journal.append(record())

    assert first.sequence == 1
    assert retry == replace(first, idempotent=True)
    assert journal.records("postgres-20260818") == (first,)

    checkpoint = ProjectionCheckpoint(
        session_id="postgres-20260818",
        projection_name="local_paper",
        journal_sequence=first.sequence,
        digest="projection-v1",
    )
    journal.save_checkpoint(checkpoint)
    assert journal.latest_checkpoint("postgres-20260818", "local_paper") == checkpoint

    with pytest.raises(JournalConflictError, match="conflicts"):
        journal.append(replace(record(), payload={"symbol": "2317"}))
