#!/usr/bin/env python3
"""Run the formal R6 G3 preflight as one launchd-supervised macOS job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
PYTHON_EXECUTABLE = (PROJECT_ROOT / ".venv/bin/python").resolve()
SCRIPT_PATH = Path(__file__).resolve()
STATE_ROOT = (
    PROJECT_ROOT / "data/backtest/atomic_entry_benchmark/supervisor"
).resolve()
JOB_LABEL = "com.tw-intraday-trader.r6-g3-preflight"
JOB_TARGET = f"gui/{os.getuid()}/{JOB_LABEL}"
EXPECTED_DATABASE = "tw_intraday_trader_backtest"
EXPECTED_HOST = "localhost"
EXPECTED_PORT = 5090
STATUS_SCHEMA = "r6-g3-supervisor-status-v1"
SUBMISSION_SCHEMA = "r6-g3-supervisor-submission-v1"
WORKER_CLAIM_SCHEMA = "r6-g3-supervisor-worker-claim-v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(_canonical_json(value) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _claim_worker_once(run_root: Path, *, claimed_at: datetime) -> bool:
    """Claim one run root exactly once, even if launchd re-invokes the job.

    ``launchctl submit`` can re-launch a failed command.  The claim is therefore
    created with ``O_EXCL`` before loading credentials or touching PostgreSQL.
    A later invocation for the same immutable run root exits successfully and
    leaves the first invocation's status/evidence untouched.
    """

    claim_path = run_root / "worker_claim.json"
    payload = (
        _canonical_json(
            {
                "schema_version": WORKER_CLAIM_SCHEMA,
                "run_id": run_root.name,
                "claimed_at": claimed_at.isoformat(),
            }
        )
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            claim_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        existing = _read_json(claim_path)
        if (
            existing.get("schema_version") != WORKER_CLAIM_SCHEMA
            or existing.get("run_id") != run_root.name
        ):
            raise RuntimeError("R6 G3 worker claim evidence drift")
        return False
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_descriptor = os.open(run_root, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return True


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"supervisor JSON must be an object: {path}")
    return value


def _run_id(now: datetime) -> str:
    return f"r6-g3-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _require_run_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(STATE_ROOT):
        raise RuntimeError("run root must remain under the R6 G3 supervisor root")
    return resolved


def _database_evidence(environment: Mapping[str, str]) -> dict[str, object]:
    if environment.get("BACKTEST_DATABASE_BACKEND") != "postgresql":
        raise RuntimeError("formal G3 requires BACKTEST_DATABASE_BACKEND=postgresql")
    parsed = urlsplit(environment.get("BACKTEST_DATABASE_URL", ""))
    database = parsed.path.lstrip("/")
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or database != EXPECTED_DATABASE
    ):
        raise RuntimeError("formal G3 Backtest database identity mismatch")
    return {
        "backend": "postgresql",
        "host": EXPECTED_HOST,
        "port": EXPECTED_PORT,
        "database": EXPECTED_DATABASE,
    }


def _launchd_job_exists() -> bool:
    result = subprocess.run(
        ["/bin/launchctl", "print", JOB_TARGET],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _submit_argv(run_root: Path) -> tuple[str, ...]:
    return (
        "/bin/launchctl",
        "submit",
        "-l",
        JOB_LABEL,
        "-o",
        str(run_root / "stdout.log"),
        "-e",
        str(run_root / "stderr.log"),
        "--",
        "/usr/bin/caffeinate",
        "-i",
        str(PYTHON_EXECUTABLE),
        str(SCRIPT_PATH),
        "worker",
        "--run-root",
        str(run_root),
    )


def start_supervised(*, execute: bool, now: datetime | None = None) -> dict[str, object]:
    observed_at = now or _utc_now()
    if sys.platform != "darwin":
        raise RuntimeError("R6 G3 launchd supervisor requires macOS")
    if not PYTHON_EXECUTABLE.is_file():
        raise RuntimeError("reviewed project Python executable is missing")
    if _launchd_job_exists():
        raise RuntimeError("R6 G3 supervised job is already loaded")
    if not execute:
        return {
            "executed": False,
            "job_label": JOB_LABEL,
            "database": EXPECTED_DATABASE,
            "progress_every": 1_000_000,
        }

    run_root = _require_run_root(STATE_ROOT / "runs" / _run_id(observed_at))
    run_root.mkdir(parents=True, exist_ok=False)
    argv = _submit_argv(run_root)
    command_digest = hashlib.sha256(
        _canonical_json({"argv": list(argv[9:])}).encode("utf-8")
    ).hexdigest()
    submission = {
        "schema_version": SUBMISSION_SCHEMA,
        "run_id": run_root.name,
        "job_label": JOB_LABEL,
        "job_target": JOB_TARGET,
        "status": "SUBMITTED",
        "submitted_at": observed_at.isoformat(),
        "run_root": str(run_root),
        "stdout_path": str(run_root / "stdout.log"),
        "stderr_path": str(run_root / "stderr.log"),
        "command_digest": command_digest,
        "sleep_prevention": "CAFFEINATE_IDLE_SYSTEM_V1",
    }
    _write_json(run_root / "submission.json", submission)
    _write_json(
        STATE_ROOT / "current.json",
        {
            "schema_version": "r6-g3-supervisor-current-v1",
            "run_id": run_root.name,
            "run_root": str(run_root),
            "job_label": JOB_LABEL,
        },
    )
    try:
        subprocess.run(argv, check=True)
    except BaseException:
        _write_json(
            run_root / "status.json",
            {
                "schema_version": STATUS_SCHEMA,
                "run_id": run_root.name,
                "status": "SUBMISSION_FAILED",
                "updated_at": _utc_now().isoformat(),
            },
        )
        raise
    return {**submission, "executed": True}


def run_worker(
    *,
    run_root: Path,
    preflight_main: Callable[[Sequence[str] | None], int] | None = None,
) -> int:
    run_root = _require_run_root(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    status_path = run_root / "status.json"
    if not _claim_worker_once(run_root, claimed_at=started_at):
        return 0
    try:
        os.chdir(PROJECT_ROOT)
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        test_dsn_was_present = bool(os.environ.pop("TEST_POSTGRES_DSN", None))
        database = _database_evidence(os.environ)
        _write_json(
            status_path,
            {
                "schema_version": STATUS_SCHEMA,
                "run_id": run_root.name,
                "status": "RUNNING",
                "worker_pid": os.getpid(),
                "started_at": started_at.isoformat(),
                "updated_at": started_at.isoformat(),
                "database": database,
                "test_postgres_dsn_removed": test_dsn_was_present,
                "formal_attempts_created": 0,
            },
        )
        if preflight_main is None:
            from scripts.preflight_atomic_entry_benchmark import main as preflight_main

        exit_code = int(
            preflight_main(
                [
                    "--execute",
                    "--progress-every",
                    "1000000",
                ]
            )
        )
        finished_at = _utc_now()
        _write_json(
            status_path,
            {
                "schema_version": STATUS_SCHEMA,
                "run_id": run_root.name,
                "status": "COMPLETED" if exit_code == 0 else "FAILED",
                "worker_pid": os.getpid(),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "updated_at": finished_at.isoformat(),
                "exit_code": exit_code,
                "database": database,
                "test_postgres_dsn_removed": test_dsn_was_present,
            },
        )
        return exit_code
    except BaseException as error:
        failed_at = _utc_now()
        _write_json(
            status_path,
            {
                "schema_version": STATUS_SCHEMA,
                "run_id": run_root.name,
                "status": "FAILED",
                "worker_pid": os.getpid(),
                "started_at": started_at.isoformat(),
                "finished_at": failed_at.isoformat(),
                "updated_at": failed_at.isoformat(),
                "exit_code": 1,
                "error_type": type(error).__name__,
            },
        )
        raise


def current_status() -> dict[str, object]:
    current_path = STATE_ROOT / "current.json"
    if not current_path.is_file():
        return {"configured": False, "launchd_loaded": _launchd_job_exists()}
    current = _read_json(current_path)
    run_root = _require_run_root(Path(str(current["run_root"])))
    status_path = run_root / "status.json"
    status = _read_json(status_path) if status_path.is_file() else {"status": "SUBMITTED"}
    launchd_loaded = _launchd_job_exists()
    effective_status = status.get("status")
    if effective_status in {"SUBMITTED", "RUNNING"} and not launchd_loaded:
        effective_status = "INTERRUPTED"
    return {
        "configured": True,
        "launchd_loaded": launchd_loaded,
        "job_label": JOB_LABEL,
        "run_root": str(run_root),
        "effective_status": effective_status,
        "status": status,
        "stdout_path": str(run_root / "stdout.log"),
        "stderr_path": str(run_root / "stderr.log"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--execute", action="store_true")
    commands.add_parser("status")
    worker = commands.add_parser("worker")
    worker.add_argument("--run-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "start":
        result = start_supervised(execute=arguments.execute)
    elif arguments.command == "status":
        result = current_status()
    else:
        return run_worker(run_root=arguments.run_root)
    print(_canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
