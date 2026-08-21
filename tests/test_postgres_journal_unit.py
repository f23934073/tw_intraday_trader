from contextlib import contextmanager
from datetime import datetime

import pytest

from trading.postgres_journal import PostgresJournalRepository


class FakeCursor:
    def __init__(self, health_row: tuple[int] | None) -> None:
        self.health_row = health_row
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, _params=None) -> None:
        self.executed.append(query)

    def fetchone(self):
        return self.health_row


class FakeConnection:
    def __init__(self, health_row: tuple[int] | None = (1,)) -> None:
        self.cursor_instance = FakeCursor(health_row)
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
