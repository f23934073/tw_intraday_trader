"""Clock boundary for runtime code.

The current application uses :class:`SystemClock`; deterministic replay adds a
second implementation in a later phase without changing callers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")


class Clock(Protocol):
    """Minimal time dependency required by the current runtime."""

    def now(self) -> datetime:
        """Return a timezone-aware instant."""

    def session_date(self) -> date:
        """Return the local market-session date."""


class SystemClock:
    """Production clock pinned to the Taiwan market timezone."""

    def now(self) -> datetime:
        return datetime.now(TAIPEI)

    def session_date(self) -> date:
        return self.now().date()
