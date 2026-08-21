"""PostgreSQL adapter for Candidate Prior persistence."""

from __future__ import annotations

from typing import Any

from .migrations import apply_migrations
from .sql_repository import SqlCandidatePriorRepository


class PostgresCandidatePriorRepository(SqlCandidatePriorRepository):
    def __init__(self, connection: Any) -> None:
        apply_migrations(connection, placeholder="%s")
        super().__init__(connection, placeholder="%s")
