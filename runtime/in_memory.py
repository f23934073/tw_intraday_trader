"""In-memory adapters for tests and the current ephemeral runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trading.journal import InMemoryJournalRepository

__all__ = ["InMemoryJournalRepository", "InMemoryProjectionRepository"]


class InMemoryProjectionRepository:
    """Copy-on-read/write projection adapter for unit tests and local runtime."""

    def __init__(self) -> None:
        self._projections: dict[str, dict[str, Any]] = {}

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        if not key.strip():
            raise ValueError("projection key must not be empty")
        self._projections[key] = dict(value)

    def get(self, key: str) -> dict[str, Any] | None:
        projection = self._projections.get(key)
        return None if projection is None else dict(projection)
