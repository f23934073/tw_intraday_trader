import os
from collections.abc import Iterator
from typing import Any

import pytest


# Test modules import Backtest settings during collection, and another test may
# load the developer .env first.  Freeze the suite on the local SQLite adapter
# before collection so a workstation cutover cannot mutate PostgreSQL.
os.environ["BACKTEST_DATABASE_BACKEND"] = "sqlite"
os.environ.pop("BACKTEST_DATABASE_URL", None)


def postgres_test_database_is_safe(database_name: str, explicit_reset: bool) -> bool:
    normalized = database_name.strip().lower().replace("-", "_")
    return "test" in normalized.split("_") or explicit_reset


@pytest.fixture(autouse=True)
def isolate_trading_journal_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit/API tests never inherit a developer's durable Journal selection."""

    monkeypatch.setenv("TRADING_JOURNAL_BACKEND", "memory")
    monkeypatch.setenv("BACKTEST_DATABASE_BACKEND", "sqlite")


@pytest.fixture
def postgres_test_dsn() -> str:
    """Explicit opt-in only; never reuse application PostgreSQL settings."""

    dsn = os.getenv("TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("requires explicit disposable TEST_POSTGRES_DSN")
    return dsn


@pytest.fixture
def postgres_test_connection(postgres_test_dsn: str) -> Iterator[Any]:
    """Own and clean the backtest schema in a dedicated PostgreSQL test DB."""

    psycopg = pytest.importorskip("psycopg")
    connection = psycopg.connect(postgres_test_dsn)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database_name = str(cursor.fetchone()[0])
    explicit_reset = os.getenv("ALLOW_POSTGRES_TEST_SCHEMA_RESET", "").strip() == "1"
    if not postgres_test_database_is_safe(database_name, explicit_reset):
        connection.close()
        pytest.fail(
            "refusing destructive PostgreSQL fixture cleanup: database name must "
            "contain a standalone 'test' token or "
            "ALLOW_POSTGRES_TEST_SCHEMA_RESET=1 must be explicit"
        )
    lock_id = 1_984_073_521
    legacy_tables = (
        "backtest_history_partitions",
        "backtest_results",
        "backtest_decisions",
        "backtest_trades",
        "backtest_daily_equity",
        "backtest_comparisons",
        "strategy_definitions",
        "backtest_runs",
        "backtest_datasets",
        "backtest_jobs",
        "backtest_schema_migrations",
    )

    def reset() -> None:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS backtest CASCADE")
            for table in legacy_tables:
                cursor.execute(f'DROP TABLE IF EXISTS public."{table}" CASCADE')
        connection.commit()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        connection.commit()
        reset()
        yield connection
    finally:
        reset()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        connection.commit()
        connection.close()
