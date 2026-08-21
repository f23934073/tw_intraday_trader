"""Run the frozen Phase 5 operator-UAT acceptance matrix."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "tests/test_strategy_paper_flow.py::test_strategy_cannot_sell_a_manual_position",
    "tests/test_recoverable_simulation_orders.py::test_local_paper_command_gate_rejects_sell_with_stale_executable_book",
    "tests/test_continuous_paper_strategy.py::test_sell_rejection_is_reported_instead_of_exit_submitted",
    "tests/test_recoverable_simulation_orders.py::test_timeout_cancels_then_bounded_retry_creates_successor_order",
    "tests/test_recoverable_simulation_orders.py::test_best_level_volume_drives_two_partial_fill_events",
    "tests/test_continuous_paper_strategy.py::test_after_close_cancels_pending_exit_and_escalates_alert",
    "tests/test_phase5_paper_sell_postgres_uat.py::test_postgresql_restart_restores_orders_positions_reservations_and_alerts",
)


def main() -> int:
    if not os.getenv("TEST_POSTGRES_DSN"):
        print(
            "Phase 5 UAT requires explicit TEST_POSTGRES_DSN; no memory fallback.",
            file=sys.stderr,
        )
        return 2
    command = [sys.executable, "-m", "pytest", "-q", *TARGETS]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
