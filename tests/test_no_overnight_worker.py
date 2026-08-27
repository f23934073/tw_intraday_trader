from datetime import datetime
from threading import Event
from types import SimpleNamespace

from config.no_overnight import NoOvernightMode
from runtime.no_overnight import NoOvernightControllerWorker


AT = datetime.fromisoformat("2026-08-24T13:15:00+08:00")


class _Clock:
    def now(self) -> datetime:
        return AT


class _Controller:
    config = SimpleNamespace(mode=NoOvernightMode.ENFORCING)

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.called = Event()
        self._fail = fail

    def run_once(self, now: datetime) -> dict[str, object]:
        assert now == AT
        self.calls += 1
        self.called.set()
        if self._fail:
            raise ValueError("controller evidence failed")
        return {"state": "CANCEL_ENTRY"}


def test_worker_runs_controller_independently_until_composition_stops_it() -> None:
    controller = _Controller()
    worker = NoOvernightControllerWorker(
        controller=controller,
        clock=_Clock(),
        on_failure=lambda: None,
        poll_seconds=0.01,
    )

    worker.start()
    assert controller.called.wait(1.0)
    worker.stop()

    assert controller.calls >= 1
    assert worker.status() == {
        "running": False,
        "poll_seconds": 0.01,
        "last_error_type": None,
    }


def test_worker_failure_closes_guard_boundary_and_stops_mutation_loop() -> None:
    controller = _Controller(fail=True)
    guard_closed = Event()
    worker = NoOvernightControllerWorker(
        controller=controller,
        clock=_Clock(),
        on_failure=guard_closed.set,
        poll_seconds=0.01,
    )

    worker.start()
    assert guard_closed.wait(1.0)
    worker.stop()

    assert controller.calls == 1
    assert worker.status()["last_error_type"] == "ValueError"
