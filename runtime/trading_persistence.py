"""Infrastructure wiring for the LOCAL_PAPER Journal adapter."""

from __future__ import annotations

from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from trading.journal import InMemoryJournalRepository, JournalRepository
from trading.migrations import apply_migrations
from trading.postgres_journal import PostgresJournalRepository


class TradingPersistenceUnavailable(RuntimeError):
    """The explicitly selected durable Journal cannot be initialized."""


def build_journal_repository(
    config: TradingPersistenceConfig,
) -> JournalRepository:
    """Select one Journal adapter without leaking database types inward."""

    if config.backend is TradingJournalBackend.MEMORY:
        return InMemoryJournalRepository()

    try:
        import psycopg
        from psycopg_pool import ConnectionPool
    except ImportError as error:
        raise TradingPersistenceUnavailable(
            "PostgreSQL Journal requires the project postgres extra"
        ) from error

    assert config.database_url is not None
    pool = None
    try:
        with psycopg.connect(
            config.database_url,
            connect_timeout=config.connect_timeout_seconds,
        ) as migration_connection:
            apply_migrations(migration_connection)

        pool = ConnectionPool(
            conninfo=config.database_url,
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
            kwargs={"connect_timeout": config.connect_timeout_seconds},
            open=False,
        )
        pool.open(wait=True, timeout=config.connect_timeout_seconds)
    except Exception as error:
        if pool is not None:
            pool.close()
        raise TradingPersistenceUnavailable(
            "PostgreSQL Journal initialization failed"
        ) from error

    repository = PostgresJournalRepository(pool=pool, owns_pool=True)
    try:
        repository.check_health()
    except Exception as error:
        repository.close()
        raise TradingPersistenceUnavailable(
            "PostgreSQL Journal health check failed"
        ) from error
    return repository
