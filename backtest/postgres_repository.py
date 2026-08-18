"""Optional PostgreSQL adapter used by platform deployments."""

from __future__ import annotations

from typing import Any

from backtest.migrations import apply_migrations
from backtest.repository import _JsonBacktestRepository


class PostgresBacktestRepository(_JsonBacktestRepository):
    def __init__(self, connection: Any) -> None:
        apply_migrations(connection)
        super().__init__(connection, placeholder="%s", json_type="JSONB", blob_type="BYTEA")
