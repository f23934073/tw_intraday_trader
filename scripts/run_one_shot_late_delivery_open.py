#!/usr/bin/env python3
"""Run the reviewed D-HEALTH-LATE-001 OPEN capture at most once."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = ZoneInfo("Asia/Taipei")
TARGET_DATE = date(2026, 8, 28)
EARLIEST_START = time(8, 50)
LATEST_FULL_WINDOW_START = time(9, 0)
STATE_ROOT = (
    PROJECT_ROOT / "research/late_delivery_evidence/scheduled_runs"
).resolve()
RUN_ID = "d-health-late-001-open-20260828"
CLAIM_SCHEMA = "d-health-late-001-open-launchd-claim-v1"
RESULT_SCHEMA = "d-health-late-001-open-launchd-result-v1"
CAPTURE_COMMAND = (
    ".venv/bin/python",
    "-m",
    "market_data.late_delivery_capture_cli",
    "--cohort",
    "research/late_delivery_evidence/cohorts/"
    "cohort_2026-08-21_twse_2026-08-20.json",
    "--phase",
    "OPEN",
    "--duration-seconds",
    "1800",
)


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"one-shot runner JSON must be an object: {path}")
    return value


def _write_json_once(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _claim_once(state_root: Path, *, claimed_at: datetime) -> bool:
    claim_path = state_root / f"{RUN_ID}_claim.json"
    try:
        _write_json_once(
            claim_path,
            {
                "schema_version": CLAIM_SCHEMA,
                "run_id": RUN_ID,
                "claimed_at": claimed_at.isoformat(),
                "target_date": TARGET_DATE.isoformat(),
                "command": list(CAPTURE_COMMAND),
                "safety": {
                    "foundation_flags": "MUST_REMAIN_OFF",
                    "subscribe_trade": False,
                    "order_path": "NOT_WIRED",
                    "retry": "PROHIBITED",
                },
            },
        )
    except FileExistsError:
        existing = _read_json(claim_path)
        if (
            existing.get("schema_version") != CLAIM_SCHEMA
            or existing.get("run_id") != RUN_ID
            or existing.get("command") != list(CAPTURE_COMMAND)
        ):
            raise RuntimeError("D-HEALTH-LATE-001 OPEN claim evidence drift")
        return False
    return True


def _normalized_exit_code(value: int) -> int:
    return value if value >= 0 else 128 + abs(value)


def run_one_shot(
    *,
    now: datetime | None = None,
    state_root: Path = STATE_ROOT,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    observed_at = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    resolved_state_root = state_root.resolve()
    if not _claim_once(resolved_state_root, claimed_at=observed_at):
        print("late_delivery_open_launchd: ALREADY_CLAIMED_NO_RETRY")
        print(f"claim: {resolved_state_root / f'{RUN_ID}_claim.json'}")
        return 0

    status = "NOT_RUN"
    reason: str | None = None
    raw_exit_code: int | None = None
    exit_code = 2
    stdout = ""
    stderr = ""
    local_time = observed_at.timetz().replace(tzinfo=None)

    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    if observed_at.date() != TARGET_DATE:
        reason = "NOT_REVIEWED_TARGET_DATE"
    elif not calendar.is_trading_day(TARGET_DATE):
        reason = "TARGET_DATE_NOT_A_REVIEWED_TRADING_DAY"
    elif not EARLIEST_START <= local_time < LATEST_FULL_WINDOW_START:
        reason = "OUTSIDE_FULL_OPEN_COLLECTION_START_WINDOW"
    else:
        completed = run(
            CAPTURE_COMMAND,
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            check=False,
            capture_output=True,
            text=True,
        )
        raw_exit_code = completed.returncode
        exit_code = _normalized_exit_code(raw_exit_code)
        stdout = completed.stdout
        stderr = completed.stderr
        status = "COMMAND_COMPLETED"
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    result_path = resolved_state_root / f"{RUN_ID}_result.json"
    _write_json_once(
        result_path,
        {
            "schema_version": RESULT_SCHEMA,
            "run_id": RUN_ID,
            "observed_at": observed_at.isoformat(),
            "target_date": TARGET_DATE.isoformat(),
            "status": status,
            "reason": reason,
            "command": list(CAPTURE_COMMAND),
            "raw_exit_code": raw_exit_code,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "gate_effect": "NONE_HEALTH_POLICY_FRESHNESS_AND_P1_2_UNCHANGED",
        },
    )
    print(f"launchd_result: {result_path}")
    if reason is not None:
        print(f"reason: {reason}")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("this one-shot runner accepts no arguments")
    return run_one_shot()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
