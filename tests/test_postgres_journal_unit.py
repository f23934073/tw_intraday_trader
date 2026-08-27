from contextlib import contextmanager
from datetime import datetime

import pytest

from trading.journal import (
    JournalClockRegressionError,
    JournalCutoffExceededError,
    JournalRecord,
    JournalSession,
)
from trading.postgres_journal import PostgresJournalRepository
from trading.postgres_journal import _postgres_storage_fingerprint


POSTGRES_IDENTITY_AT = datetime.fromisoformat("2026-08-27T00:00:00+00:00")


class FakeCursor:
    def __init__(
        self,
        health_row: tuple[object, ...] | None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.health_row = health_row
        self.rows = rows or []
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, _params=None) -> None:
        self.executed.append(query)

    def fetchone(self):
        return self.health_row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(
        self,
        health_row: tuple[object, ...] | None = (1,),
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.cursor_instance = FakeCursor(health_row, rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection_instance = connection
        self.closed = False
        self.acquisitions = 0

    @contextmanager
    def connection(self):
        self.acquisitions += 1
        yield self.connection_instance

    def close(self) -> None:
        self.closed = True


class ScriptedCursor:
    def __init__(
        self,
        steps: list[tuple[str, tuple[object, ...] | None, int]],
    ) -> None:
        self.steps = list(steps)
        self.current_row: tuple[object, ...] | None = None
        self.rowcount = -1
        self.calls: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params=None) -> None:
        assert self.steps, f"unexpected SQL: {query}"
        expected, row, rowcount = self.steps.pop(0)
        assert expected in query
        self.current_row = row
        self.rowcount = rowcount
        self.calls.append((query, params))

    def fetchone(self):
        return self.current_row


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_instance = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> ScriptedCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _atomic_session_and_record(
    occurred_at: datetime,
) -> tuple[JournalSession, JournalRecord]:
    session = JournalSession(
        session_id="disabled-evidence-20260827",
        started_at=occurred_at,
        mode="NO_OVERNIGHT_EVIDENCE_WINDOW",
        metadata={"activation_authority": "NONE_EVIDENCE_ONLY"},
    )
    record = JournalRecord(
        record_id="disabled-open-20260827",
        session_id=session.session_id,
        kind="no_overnight_evidence_window_opened.v1",
        occurred_at=occurred_at,
        payload={"stage": "DISABLED_BASELINE"},
        idempotency_scope="disabled-open",
        idempotency_key="2026-08-27",
    )
    return session, record


def test_atomic_open_uses_postgres_clock_and_one_transaction() -> None:
    requested_at = datetime.fromisoformat("2026-08-27T08:45:00+08:00")
    accepted_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    cutoff = datetime.fromisoformat("2026-08-27T09:00:00+08:00")
    cursor = ScriptedCursor(
        [
            ("clock_timestamp()", (accepted_at,), -1),
            ("FROM trading.journal_sessions", None, -1),
            ("INSERT INTO trading.journal_sessions", None, 1),
            ("clock_timestamp()", (accepted_at,), -1),
            ("INSERT INTO trading.journal_records", (41,), 1),
            ("clock_timestamp()", (accepted_at,), -1),
        ]
    )
    connection = ScriptedConnection(cursor)
    repository = PostgresJournalRepository(connection)
    session, record = _atomic_session_and_record(requested_at)

    result = repository.start_session_and_append_before(
        session,
        record,
        latest_allowed_at=cutoff,
        authoritative_now=lambda: datetime.fromisoformat(
            "2026-08-27T09:01:00+08:00"
        ),
    )

    assert result.sequence == 41
    assert result.record.occurred_at == accepted_at
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert cursor.steps == []
    session_insert = next(
        call for call in cursor.calls if "INSERT INTO trading.journal_sessions" in call[0]
    )
    record_insert = next(
        call for call in cursor.calls if "INSERT INTO trading.journal_records" in call[0]
    )
    assert session_insert[1][1] == accepted_at
    assert record_insert[1][3] == accepted_at


def test_atomic_open_matching_retry_preserves_original_server_time() -> None:
    accepted_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    cutoff = datetime.fromisoformat("2026-08-27T09:00:00+08:00")
    session, record = _atomic_session_and_record(accepted_at)
    existing_session = (
        accepted_at,
        session.mode,
        session.metadata_json,
        session.schema_version,
    )
    existing_record = (41, record.fingerprint)
    cursor = ScriptedCursor(
        [
            ("clock_timestamp()", (accepted_at,), -1),
            ("FROM trading.journal_sessions", existing_session, -1),
            ("INSERT INTO trading.journal_sessions", None, 0),
            ("FROM trading.journal_sessions", existing_session, -1),
            ("clock_timestamp()", (accepted_at,), -1),
            ("FROM trading.journal_records", existing_record, -1),
            ("INSERT INTO trading.journal_records", None, 0),
            ("FROM trading.journal_records", existing_record, -1),
            ("clock_timestamp()", (accepted_at,), -1),
        ]
    )
    connection = ScriptedConnection(cursor)
    repository = PostgresJournalRepository(connection)

    result = repository.start_session_and_append_before(
        session,
        record,
        latest_allowed_at=cutoff,
    )

    assert result.sequence == 41
    assert result.idempotent is True
    assert result.record.occurred_at == accepted_at
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert cursor.steps == []


def test_atomic_open_retry_preserves_original_offset_from_storage_envelope() -> None:
    original_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    rendered_at = datetime.fromisoformat("2026-08-27T00:59:59.900000+00:00")
    cutoff = datetime.fromisoformat("2026-08-27T01:00:00+00:00")
    session, record = _atomic_session_and_record(original_at)
    existing_session = (
        rendered_at,
        session.mode,
        session.metadata_json,
        session.schema_version,
    )
    existing_record = (41, _postgres_storage_fingerprint(record))
    cursor = ScriptedCursor(
        [
            ("clock_timestamp()", (rendered_at,), -1),
            ("FROM trading.journal_sessions", existing_session, -1),
            ("INSERT INTO trading.journal_sessions", None, 0),
            ("FROM trading.journal_sessions", existing_session, -1),
            ("clock_timestamp()", (rendered_at,), -1),
            ("FROM trading.journal_records", existing_record, -1),
            ("INSERT INTO trading.journal_records", None, 0),
            ("FROM trading.journal_records", existing_record, -1),
            ("clock_timestamp()", (rendered_at,), -1),
        ]
    )
    repository = PostgresJournalRepository(ScriptedConnection(cursor))

    result = repository.start_session_and_append_before(
        session,
        record,
        latest_allowed_at=cutoff,
    )

    assert result.idempotent is True
    assert result.record.occurred_at.isoformat() == original_at.isoformat()
    assert cursor.steps == []


@pytest.mark.parametrize("crosses_during", ("initial", "session", "record"))
def test_atomic_open_rolls_back_when_database_operation_crosses_cutoff(
    crosses_during: str,
) -> None:
    accepted_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    late_at = datetime.fromisoformat("2026-08-27T09:00:00.000001+08:00")
    cutoff = datetime.fromisoformat("2026-08-27T09:00:00+08:00")
    steps = [
        (
            "clock_timestamp()",
            ((late_at if crosses_during == "initial" else accepted_at),),
            -1,
        )
    ]
    if crosses_during != "initial":
        steps.extend(
            [
                ("FROM trading.journal_sessions", None, -1),
                ("INSERT INTO trading.journal_sessions", None, 1),
                (
                    "clock_timestamp()",
                    (
                        (
                            late_at
                            if crosses_during == "session"
                            else accepted_at
                        ),
                    ),
                    -1,
                ),
            ]
        )
    if crosses_during == "record":
        steps.extend(
            [
                ("INSERT INTO trading.journal_records", (42,), 1),
                ("clock_timestamp()", (late_at,), -1),
            ]
        )
    cursor = ScriptedCursor(steps)
    connection = ScriptedConnection(cursor)
    repository = PostgresJournalRepository(connection)
    session, record = _atomic_session_and_record(accepted_at)

    with pytest.raises(JournalCutoffExceededError):
        repository.start_session_and_append_before(
            session,
            record,
            latest_allowed_at=cutoff,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert cursor.steps == []


@pytest.mark.parametrize("regresses_during", ("session", "record"))
def test_atomic_open_rolls_back_when_server_clock_moves_backwards(
    regresses_during: str,
) -> None:
    accepted_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    regressed_at = datetime.fromisoformat("2026-08-27T08:59:59.800000+08:00")
    cutoff = datetime.fromisoformat("2026-08-27T09:00:00+08:00")
    steps = [
        ("clock_timestamp()", (accepted_at,), -1),
        ("FROM trading.journal_sessions", None, -1),
        ("INSERT INTO trading.journal_sessions", None, 1),
        (
            "clock_timestamp()",
            (
                (
                    regressed_at
                    if regresses_during == "session"
                    else accepted_at
                ),
            ),
            -1,
        ),
    ]
    if regresses_during == "record":
        steps.extend(
            [
                ("INSERT INTO trading.journal_records", (43,), 1),
                ("clock_timestamp()", (regressed_at,), -1),
            ]
        )
    cursor = ScriptedCursor(steps)
    connection = ScriptedConnection(cursor)
    repository = PostgresJournalRepository(connection)
    session, record = _atomic_session_and_record(accepted_at)

    with pytest.raises(JournalClockRegressionError, match="moved backwards"):
        repository.start_session_and_append_before(
            session,
            record,
            latest_allowed_at=cutoff,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert cursor.steps == []


def test_pool_backed_health_check_commits_and_owned_pool_closes() -> None:
    connection = FakeConnection()
    pool = FakePool(connection)
    repository = PostgresJournalRepository(pool=pool, owns_pool=True)

    repository.check_health()
    repository.close()

    assert pool.acquisitions == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert pool.closed is True


def test_guard_database_url_retains_explicit_password_authenticated_dsn() -> None:
    connection = FakeConnection(
        health_row=(
            "tw_intraday_trader_test",
            "16384",
            POSTGRES_IDENTITY_AT,
            "127.0.0.1",
            "5432",
        )
    )
    connection.info = type(
        "ConnectionInfo",
        (),
        {
            "dsn": (
                "user=postgres dbname=tw_intraday_trader_test "
                "host=localhost hostaddr=::1"
            ),
            "dbname": "tw_intraday_trader_test",
            "user": "postgres",
            "host": "localhost",
            "port": 5432,
        },
    )()
    authenticated_dsn = (
        "postgresql://postgres:postgres@localhost:5432/"
        "tw_intraday_trader_test"
    )

    repository = PostgresJournalRepository(
        connection,
        database_url=authenticated_dsn,
    )

    assert repository.database_url == authenticated_dsn
    assert authenticated_dsn not in repr(repository)


def test_guard_database_url_never_reconstructs_sanitized_connection_metadata() -> None:
    connection = FakeConnection()
    connection.info = type(
        "ConnectionInfo",
        (),
        {
            "dsn": (
                "user=postgres dbname=tw_intraday_trader_test "
                "host=localhost hostaddr=::1"
            ),
            "dbname": "tw_intraday_trader_test",
            "user": "postgres",
            "host": "localhost",
            "port": 5432,
        },
    )()

    repository = PostgresJournalRepository(connection)

    assert repository.database_url is None

    pool = FakePool(FakeConnection())
    pool.conninfo = connection.info.dsn

    pooled_repository = PostgresJournalRepository(pool=pool)

    assert pooled_repository.database_url is None


def test_guard_database_url_rejects_connection_identity_mismatch_without_leak() -> None:
    connection = FakeConnection(
        health_row=(
            "journal_a_test",
            "16384",
            POSTGRES_IDENTITY_AT,
            "127.0.0.1",
            "5432",
        )
    )
    connection.info = type(
        "ConnectionInfo",
        (),
        {
            "dbname": "journal_a_test",
            "user": "postgres",
            "host": "localhost",
            "port": 5432,
        },
    )()
    conflicting_dsn = (
        "postgresql://postgres:do-not-leak@localhost:5432/journal_b_test"
    )

    with pytest.raises(ValueError, match="connection identity") as caught:
        PostgresJournalRepository(
            connection,
            database_url=conflicting_dsn,
        )

    assert conflicting_dsn not in str(caught.value)
    assert "do-not-leak" not in str(caught.value)


def test_pool_transaction_rejects_backend_identity_change_before_operation() -> None:
    initial = FakeConnection(
        health_row=(
            "tw_intraday_trader_test",
            "16384",
            POSTGRES_IDENTITY_AT,
            "127.0.0.1",
            "5432",
        )
    )
    pool = FakePool(initial)
    pool.conninfo = (
        "postgresql://postgres:do-not-leak@127.0.0.1:5432/"
        "tw_intraday_trader_test"
    )
    repository = PostgresJournalRepository(
        pool=pool,
        database_url=pool.conninfo,
    )
    pool.connection_instance = FakeConnection(
        health_row=(
            "tw_intraday_trader_test",
            "16384",
            datetime.fromisoformat("2026-08-27T00:01:00+00:00"),
            "127.0.0.2",
            "5432",
        )
    )

    with pytest.raises(ValueError, match="pool resource identity changed") as caught:
        repository.check_health()

    assert "do-not-leak" not in str(caught.value)
    assert not any(
        "SELECT 1" in query
        for query in pool.connection_instance.cursor_instance.executed
    )


def test_failed_health_check_rolls_back_and_does_not_commit() -> None:
    connection = FakeConnection(health_row=None)
    repository = PostgresJournalRepository(connection)

    with pytest.raises(RuntimeError, match="returned no row"):
        repository.check_health()

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_session_lookup_reconstructs_registered_metadata() -> None:
    started_at = datetime.fromisoformat("2026-08-21T09:00:00+08:00")
    connection = FakeConnection(
        health_row=(
            started_at,
            "LOCAL_PAPER_SIMULATION",
            '{"execution_boundary":"LOCAL_ONLY"}',
            "journal-v1",
        )
    )
    repository = PostgresJournalRepository(connection)

    session = repository.session("local-paper-runtime-v1")

    assert session is not None
    assert session.session_id == "local-paper-runtime-v1"
    assert session.started_at == started_at
    assert session.mode == "LOCAL_PAPER_SIMULATION"
    assert session.metadata == {"execution_boundary": "LOCAL_ONLY"}
    assert connection.commits == 1


def test_session_prefix_lookup_reconstructs_ordered_metadata() -> None:
    started_at = datetime.fromisoformat("2026-08-24T09:00:00+08:00")
    connection = FakeConnection(
        rows=[
            (
                "no-overnight-v1-2026-08-24",
                started_at,
                "NO_OVERNIGHT_ENFORCING",
                '{"session_date":"2026-08-24"}',
                "journal-v1",
            )
        ]
    )
    repository = PostgresJournalRepository(connection)

    sessions = repository.sessions(session_id_prefix="no-overnight-v1-")

    assert len(sessions) == 1
    assert sessions[0].session_id == "no-overnight-v1-2026-08-24"
    assert sessions[0].metadata == {"session_date": "2026-08-24"}
    assert connection.commits == 1
    assert "ORDER BY session_id" in connection.cursor_instance.executed[0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"connection": FakeConnection(), "pool": FakePool(FakeConnection())},
        {"connection": FakeConnection(), "owns_pool": True},
    ],
)
def test_repository_requires_exactly_one_resource(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        PostgresJournalRepository(**kwargs)
