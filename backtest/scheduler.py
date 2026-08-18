"""Asia/Taipei after-close scheduler for durable incremental Kbar jobs."""

from __future__ import annotations

from datetime import date, datetime, time
from threading import Event, RLock, Thread
from typing import Callable
from zoneinfo import ZoneInfo


_TAIPEI = ZoneInfo("Asia/Taipei")
IncrementalTrigger = Callable[[date], dict[str, object]]
JobStatusReader = Callable[[str], dict[str, object]]


class AfterCloseIncrementalScheduler:
    """Poll a pure due-time rule and submit at most once per local session."""

    def __init__(
        self,
        *,
        trigger: IncrementalTrigger,
        close_time: time,
        poll_seconds: float,
        job_status: JobStatusReader | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds 必須大於 0")
        self._trigger = trigger
        self._close_time = close_time
        self._poll_seconds = poll_seconds
        self._job_status = job_status
        self._stop = Event()
        self._lock = RLock()
        self._thread: Thread | None = None
        self._submitted_sessions: dict[date, str] = {}
        self._snapshot: dict[str, object] = {
            "enabled": True,
            "state": "STOPPED",
            "timezone": "Asia/Taipei",
            "close_time": close_time.strftime("%H:%M"),
            "last_checked_at": None,
            "session_date": None,
            "job_id": None,
            "message": "收盤後增量同步排程尚未啟動",
            "error_message": None,
        }

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(
                target=self._run_loop,
                name="backtest-incremental-sync-scheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, min(10.0, self._poll_seconds + 1.0)))
        with self._lock:
            self._thread = None
            self._snapshot = {
                **self._snapshot,
                "state": "STOPPED",
                "message": "收盤後增量同步排程已停止",
            }

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._snapshot)

    def run_due(self, now: datetime | None = None) -> dict[str, object]:
        current = now or datetime.now(_TAIPEI)
        if current.tzinfo is None:
            raise ValueError("scheduler now 必須包含 timezone")
        current = current.astimezone(_TAIPEI)
        session_date = current.date()
        base = {
            "enabled": True,
            "timezone": "Asia/Taipei",
            "close_time": self._close_time.strftime("%H:%M"),
            "last_checked_at": current.isoformat(),
            "session_date": session_date.isoformat(),
            "error_message": None,
        }
        if session_date.weekday() >= 5:
            return self._set_snapshot(
                **base,
                state="WAITING_FOR_TRADING_DAY",
                job_id=None,
                message="今天是週末，不執行歷史 Kbar 增量同步",
            )
        if current.time().replace(tzinfo=None) < self._close_time:
            return self._set_snapshot(
                **base,
                state="WAITING_FOR_CLOSE",
                job_id=None,
                message=f"等待 {self._close_time.strftime('%H:%M')} 收盤後同步",
            )
        with self._lock:
            submitted_job_id = self._submitted_sessions.get(session_date)
        if submitted_job_id is not None:
            if self._job_status is None:
                return self.status()
            job = self._job_status(submitted_job_id)
            if job["status"] not in {"FAILED", "PAUSED", "CANCELLED"}:
                state = "COMPLETED" if job["status"] == "COMPLETED" else "SYNC_IN_PROGRESS"
                return self._set_snapshot(
                    **{
                        **base,
                        "state": state,
                        "job_id": submitted_job_id,
                        "message": str(job.get("progress_message") or "增量同步工作執行中"),
                    }
                )
            with self._lock:
                self._submitted_sessions.pop(session_date, None)
        try:
            result = self._trigger(session_date)
            job = dict(result.get("job", {}))
            snapshot = self._set_snapshot(
                **base,
                state=str(result.get("state") or "SUBMITTED"),
                job_id=job.get("job_id"),
                message=str(
                    result.get("message")
                    or ("已建立收盤後增量同步工作" if result.get("created") else "本日同步工作已存在")
                ),
            )
            if job.get("job_id"):
                with self._lock:
                    self._submitted_sessions[session_date] = str(job["job_id"])
            return snapshot
        except Exception as error:
            state = str(getattr(error, "scheduler_state", "ERROR"))
            return self._set_snapshot(
                **{
                    **base,
                    "state": state,
                    "job_id": getattr(error, "job_id", None),
                    "message": str(error),
                    "error_message": str(error) if state == "ERROR" else None,
                }
            )

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self.run_due()
            self._stop.wait(self._poll_seconds)

    def _set_snapshot(self, **values: object) -> dict[str, object]:
        with self._lock:
            self._snapshot = values
            return dict(self._snapshot)
