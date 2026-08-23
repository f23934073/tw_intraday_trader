"""Bounded durable control traffic for large streaming backtests."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Mapping, Protocol

from backtest.domain import RunStatus


class _RunRepository(Protocol):
    def get_run(self, run_id: str) -> Mapping[str, Any]: ...

    def update_run(self, run_id: str, **changes: Any) -> Mapping[str, Any]: ...


class DurableRunControlProbe:
    """Cache durable cancellation state and poll at most once per interval."""

    def __init__(
        self,
        repository: _RunRepository,
        run_id: str,
        *,
        poll_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds 必須大於 0")
        self._repository = repository
        self._run_id = run_id
        self._poll_interval = poll_interval_seconds
        self._clock = clock
        self._last_poll: float | None = None
        self._cancelled = False

    def __call__(self) -> bool:
        now = self._clock()
        if self._last_poll is None or now - self._last_poll >= self._poll_interval:
            run = self._repository.get_run(self._run_id)
            self._cancelled = run["status"] == RunStatus.CANCELLING.value
            self._last_poll = now
        return self._cancelled


class ThrottledProgressReporter:
    """Persist progress by time/delta while preserving a forced terminal flush."""

    def __init__(
        self,
        repository: _RunRepository,
        run_id: str,
        *,
        interval_seconds: float = 1.0,
        minimum_delta: float = 0.01,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds 必須大於 0")
        if not 0 < minimum_delta <= 1:
            raise ValueError("minimum_delta 必須介於 0 與 1")
        self._repository = repository
        self._run_id = run_id
        self._interval = interval_seconds
        self._minimum_delta = minimum_delta
        self._clock = clock
        self._last_write_at: float | None = None
        self._last_progress = 0.0
        self._pending: tuple[float, str] | None = None

    def __call__(self, progress: float, message: str) -> None:
        value = min(1.0, max(0.0, float(progress)))
        self._pending = (value, str(message))
        now = self._clock()
        if (
            self._last_write_at is None
            or now - self._last_write_at >= self._interval
            or value - self._last_progress >= self._minimum_delta
        ):
            self._write(now)

    def flush(self) -> None:
        if self._pending is not None:
            self._write(self._clock())

    def _write(self, now: float) -> None:
        assert self._pending is not None
        progress, message = self._pending
        self._repository.update_run(
            self._run_id,
            progress=progress,
            progress_message=message,
        )
        self._last_write_at = now
        self._last_progress = progress
        self._pending = None
