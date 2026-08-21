"""Optional PostgreSQL adapter used by platform deployments."""

from __future__ import annotations

from typing import Any

from backtest.migrations import apply_migrations
from backtest.repository import _JsonBacktestRepository


class PostgresBacktestRepository(_JsonBacktestRepository):
    def __init__(self, connection: Any) -> None:
        apply_migrations(connection)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO backtest, public")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        super().__init__(
            connection,
            placeholder="%s",
            json_type="JSONB",
            blob_type="BYTEA",
            apply_schema=False,
        )
