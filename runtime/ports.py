"""Framework-free ports used by the runtime composition layer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from trading.journal import JournalRecord, JournalRepository

__all__ = [
    "JournalRecord",
    "JournalRepository",
    "MarketEventSource",
    "OrderCommandHandler",
    "ProjectionRepository",
]


@runtime_checkable
class MarketEventSource(Protocol):
    """Source boundary for future normalized live or replay events."""

    def read_events(self) -> Iterable[object]:
        """Yield normalized event objects without exposing SDK callbacks."""


@runtime_checkable
class ProjectionRepository(Protocol):
    """Read-model storage boundary with no database dependency."""

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        """Replace one projection value."""

    def get(self, key: str) -> dict[str, Any] | None:
        """Read one projection value."""


@runtime_checkable
class OrderCommandHandler(Protocol):
    """Compatibility seam around the current local-paper command service."""

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        lots: int,
        limit_price: float,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """Submit a local-paper order."""

    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """Cancel a local-paper order."""
