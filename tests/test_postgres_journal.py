import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
from trading import migrations as trading_migrations  # noqa: E402
from trading.migrations import apply_migrations  # noqa: E402
from trading.postgres_journal import PostgresJournalRepository  # noqa: E402
from trading.no_overnight_evidence import (  # noqa: E402
    NoOvernightEvidenceStage,
    NoOvernightEvidenceWindowSpec,
    close_no_overnight_evidence_window,
    open_no_overnight_evidence_window,
)


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")


@pytest.fixture()
def journal():
    connection = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP SCHEMA IF EXISTS trading CASCADE;
                DROP TABLE IF EXISTS public.projection_checkpoints,
                public.journal_records, public.journal_sessions,
                public.journal_schema_migrations CASCADE
                """
            )
        connection.commit()
        assert apply_migrations(connection) == (
            "001_journal.sql",
            "002_trading_schema.sql",
        )
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
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP SCHEMA IF EXISTS trading CASCADE;
                DROP TABLE IF EXISTS public.projection_checkpoints,
                public.journal_records, public.journal_sessions,
                public.journal_schema_migrations CASCADE
                """
            )
        connection.commit()
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


def test_postgres_restart_rejects_payload_tampered_without_fingerprint(journal) -> None:
    journal.append(record())
    with journal._transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE trading.journal_records
                SET payload_json = jsonb_set(payload_json, '{symbol}', '"2317"')
                WHERE session_id = %s AND record_id = %s
                """,
                ("postgres-20260818", "command-1"),
            )

    with pytest.raises(JournalConflictError, match="stored fingerprint"):
        journal.records("postgres-20260818")


def test_atomic_open_retry_preserves_timestamp_identity_across_connection_timezone(
    journal,
) -> None:
    with journal._transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Taipei'")
    requested_at = datetime.fromisoformat("2026-08-27T08:45:00+08:00")
    session = JournalSession(
        session_id="postgres-atomic-offset-retry",
        started_at=requested_at,
        mode="NO_OVERNIGHT_EVIDENCE_WINDOW",
        metadata={"activation_authority": "NONE_EVIDENCE_ONLY"},
    )
    atomic_record = JournalRecord(
        record_id="postgres-atomic-offset-open",
        session_id=session.session_id,
        kind="no_overnight_evidence_window_opened.v1",
        occurred_at=requested_at,
        payload={"stage": "DISABLED_BASELINE"},
        idempotency_scope="postgres-atomic-offset-open",
        idempotency_key="2026-08-27",
    )
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=1)
    first = journal.start_session_and_append_before(
        session,
        atomic_record,
        latest_allowed_at=cutoff,
    )

    reconnect = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with reconnect.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
        reconnect.commit()
        retried = PostgresJournalRepository(
            reconnect
        ).start_session_and_append_before(
            session,
            atomic_record,
            latest_allowed_at=cutoff,
        )
    finally:
        reconnect.close()

    assert retried.idempotent is True
    assert retried.sequence == first.sequence
    assert retried.record.occurred_at.isoformat() == first.record.occurred_at.isoformat()


def test_postgres_atomic_open_projects_campaign_timezone(journal) -> None:
    fixed_server_time = datetime.fromisoformat(
        "2026-08-27T00:45:00+00:00"
    )

    class FixedServerTimePostgresJournal(PostgresJournalRepository):
        @staticmethod
        def _server_time(_cursor):
            return fixed_server_time

    with journal._transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
    zone = ZoneInfo("Asia/Taipei")
    now = fixed_server_time.astimezone(zone)
    session_date = now.date()
    reviewed_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    reviewed_close = now.replace(hour=13, minute=30, second=0, microsecond=0)
    spec = NoOvernightEvidenceWindowSpec(
        campaign_id="postgres-campaign-timezone",
        stage=NoOvernightEvidenceStage.DISABLED_BASELINE,
        session_date=session_date,
        account_scope_id="local-paper-main-v1",
        policy_family_id="no-overnight-equity-v1",
        policy_version="disabled-v1",
        policy_digest="a" * 64,
        calendar_schema_version="postgres-timezone-regression-v1",
        calendar_digest="b" * 64,
        timezone="Asia/Taipei",
        reviewed_open=reviewed_open,
        reviewed_close=reviewed_close,
        code_identity="c" * 40,
        expected_provider_identity="market_data.provider.MockProvider",
        local_paper_session_id="local-paper-no-overnight-evidence-v1",
    )
    first_journal = FixedServerTimePostgresJournal(journal._connection)
    opened = open_no_overnight_evidence_window(
        journal=first_journal,
        spec=spec,
        opened_at=now,
        latest_allowed_at=reviewed_open,
    )

    reconnect = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with reconnect.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Taipei'")
        reconnect.commit()
        retry_journal = FixedServerTimePostgresJournal(reconnect)
        retried = open_no_overnight_evidence_window(
            journal=retry_journal,
            spec=spec,
            opened_at=now,
            latest_allowed_at=reviewed_open,
        )
        observation = close_no_overnight_evidence_window(
            journal=retry_journal,
            spec=spec,
            opened=retried,
            closed_at=reviewed_close,
        )
    finally:
        reconnect.close()

    assert opened.record.occurred_at.utcoffset() == timedelta(0)
    assert retried.idempotent is True
    assert retried.sequence == opened.sequence
    assert retried.record.fingerprint == opened.record.fingerprint
    assert observation.observed_from == opened.record.occurred_at
    assert observation.observed_from.tzinfo == zone
    assert observation.observed_through.tzinfo == zone
    assert observation.finalized_at.tzinfo == zone


def test_migration_moves_legacy_public_journal_into_trading_schema() -> None:
    connection = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP SCHEMA IF EXISTS trading CASCADE;
                DROP TABLE IF EXISTS public.projection_checkpoints,
                public.journal_records, public.journal_sessions,
                public.journal_schema_migrations CASCADE
                """
            )
            cursor.execute(
                """
                CREATE TABLE public.journal_schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                (trading_migrations.MIGRATIONS_DIRECTORY / "001_journal.sql").read_text(
                    encoding="utf-8"
                )
            )
            cursor.execute(
                """
                INSERT INTO public.journal_schema_migrations (version)
                VALUES ('001_journal.sql')
                """
            )
        connection.commit()

        assert apply_migrations(connection) == ("002_trading_schema.sql",)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    to_regclass('public.journal_sessions'),
                    to_regclass('trading.journal_sessions'),
                    to_regclass('trading.journal_records'),
                    to_regclass('trading.projection_checkpoints')
                """
            )
            assert cursor.fetchone() == (
                None,
                "trading.journal_sessions",
                "trading.journal_records",
                "trading.projection_checkpoints",
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP SCHEMA IF EXISTS trading CASCADE;
                DROP TABLE IF EXISTS public.projection_checkpoints,
                public.journal_records, public.journal_sessions,
                public.journal_schema_migrations CASCADE
                """
            )
        connection.commit()
        connection.close()
