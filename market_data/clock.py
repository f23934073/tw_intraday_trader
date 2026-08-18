"""Injected event-time clock contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def session_date(self) -> date: ...

    def sleep_until(self, event_at: datetime) -> None: ...


class ReplayClock:
    """Fast deterministic clock that never reads or sleeps on wall time."""

    def __init__(self, start_at: datetime) -> None:
        self._require_aware(start_at)
        self._current = start_at

    def now(self) -> datetime:
        return self._current

    def session_date(self) -> date:
        return self._current.date()

    def sleep_until(self, event_at: datetime) -> None:
        self._require_aware(event_at)
        if event_at < self._current:
            raise ValueError("ReplayClock cannot move backward")
        self._current = event_at

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ReplayClock timestamps must be timezone-aware")
