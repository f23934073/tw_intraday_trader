"""Minimal repository factory for dedicated price-coverage acquisition CLIs."""

from __future__ import annotations

from backtest.postgres_repository import PostgresBacktestRepository
from backtest.repository import BacktestRepository
from backtest.sqlite_repository import SQLiteBacktestRepository
from config import backtest as backtest_settings


def build_price_coverage_repository() -> BacktestRepository:
    if backtest_settings.BACKTEST_DATABASE_BACKEND == "postgresql":
        try:
            from psycopg_pool import ConnectionPool  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "使用 PostgreSQL price coverage store 前必須安裝 postgres extra"
            ) from error
        pool = ConnectionPool(
            backtest_settings.BACKTEST_DATABASE_URL,
            min_size=1,
            max_size=2,
            timeout=5,
            open=True,
        )
        return PostgresBacktestRepository(pool=pool, owns_pool=True)
    return SQLiteBacktestRepository(
        backtest_settings.BACKTEST_DATA_DIR / "backtest.sqlite3"
    )
