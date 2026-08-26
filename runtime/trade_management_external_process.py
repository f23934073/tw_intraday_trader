"""Exact subprocess allowlist for Trade Management Shadow external execution."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from runtime.trade_management_external_supervisor import (
    CommandPlan,
    ProcessResult,
    SupervisorBlocked,
)


C0_TIMEOUT_SECONDS = 600
REHEARSAL_TIMEOUT_SECONDS = 120
TERMINATION_GRACE_SECONDS = 15
SAFE_CHILD_ENV_KEYS = frozenset(
    {
        "LANG",
        "LC_ALL",
        "PYTHONHASHSEED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TZ",
    }
)
PROVIDER_ENV_KEYS = SAFE_CHILD_ENV_KEYS | {
    "SHIOAJI_API_KEY",
    "SHIOAJI_SECRET",
    "SJ_API_KEY",
    "SJ_SEC_KEY",
    "SJ_SECRET_KEY",
    "SJ_SIMULATION",
}
REHEARSAL_TARGETS = tuple(
    sorted(
        (
            "tests/test_trade_management_c1_session.py",
            "tests/test_trade_management_operational_composition.py",
            "tests/test_trade_management_replay.py",
            "tests/test_trade_management_shadow_operation.py",
            "tests/test_trade_management_shadow_validation.py",
        )
    )
)


def run_c0_provider_worker(
    *,
    python_executable: str,
    c0_script: Path,
    project_root: Path,
    worker_argument: str,
) -> subprocess.CompletedProcess[str]:
    _require_c0_python_and_script(
        python_executable=python_executable,
        c0_script=c0_script,
        project_root=project_root,
    )
    if worker_argument != "--provider-preflight-worker":
        raise RuntimeError("C0_PROVIDER_WORKER_ARGV_DENIED")
    return _run_captured_allowed(
        role="C0_PROVIDER_WORKER",
        argv=[python_executable, str(c0_script), worker_argument],
        cwd=project_root,
        timeout=120,
        env=_selected_environment(PROVIDER_ENV_KEYS),
    )


def run_c0_rehearsal(
    *,
    python_executable: str,
    project_root: Path,
    targets: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    _require_project_python(python_executable, project_root=project_root)
    if tuple(targets) != REHEARSAL_TARGETS:
        raise RuntimeError("C0_REHEARSAL_ARGV_DENIED")
    environment = _selected_environment(SAFE_CHILD_ENV_KEYS)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return _run_captured_allowed(
        role="C0_REHEARSAL",
        argv=[python_executable, "-m", "pytest", "-q", *REHEARSAL_TARGETS],
        cwd=project_root,
        timeout=REHEARSAL_TIMEOUT_SECONDS,
        env=environment,
    )


def run_c0_entrypoint(
    *,
    plan: CommandPlan,
    project_root: Path,
    environment: Mapping[str, str],
    now: Callable[[], datetime],
) -> ProcessResult:
    return _run_entrypoint(
        role="C0",
        argv=plan.c0_argv,
        expected_argv=plan.c0_argv,
        stdout_path=plan.paths.c0_stdout,
        stderr_path=plan.paths.c0_stderr,
        project_root=project_root,
        environment=environment,
        timeout_seconds=C0_TIMEOUT_SECONDS,
        now=now,
    )


def run_c1_entrypoint(
    *,
    plan: CommandPlan,
    project_root: Path,
    environment: Mapping[str, str],
    now: Callable[[], datetime],
) -> ProcessResult:
    return _run_entrypoint(
        role="C1",
        argv=plan.c1_argv,
        expected_argv=plan.c1_argv,
        stdout_path=plan.paths.c1_stdout,
        stderr_path=plan.paths.c1_stderr,
        project_root=project_root,
        environment=environment,
        timeout_seconds=None,
        now=now,
    )


def _run_entrypoint(
    *,
    role: str,
    argv: tuple[str, ...],
    expected_argv: tuple[str, ...],
    stdout_path: Path,
    stderr_path: Path,
    project_root: Path,
    environment: Mapping[str, str],
    timeout_seconds: int | None,
    now: Callable[[], datetime],
) -> ProcessResult:
    if argv != expected_argv:
        raise RuntimeError(f"{role}_ARGV_DENIED")
    expected_script = {
        "C0": "scripts/preflight_trade_management_shadow.py",
        "C1": "scripts/run_trade_management_shadow_c1.py",
    }.get(role)
    if expected_script is None or len(argv) < 2 or argv[1] != expected_script:
        raise RuntimeError(f"{role}_ENTRYPOINT_DENIED")
    _require_project_python(argv[0], project_root=project_root)
    started_at = now()
    with _open_owner_only_exclusive(stdout_path) as stdout_handle:
        with _open_owner_only_exclusive(stderr_path) as stderr_handle:
            process = subprocess.Popen(
                list(argv),
                cwd=project_root,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=TERMINATION_GRACE_SECONDS)
                except subprocess.TimeoutExpired as pending_error:
                    raise SupervisorBlocked(
                        f"{role}_TIMEOUT_TERMINATION_PENDING"
                    ) from pending_error
                if _process_group_exists(process.pid):
                    raise SupervisorBlocked(
                        f"{role}_TIMEOUT_TERMINATION_PENDING"
                    ) from error
                raise SupervisorBlocked(f"{role}_TIMEOUT_TERMINATED") from error
    return ProcessResult(
        role=role,
        returncode=returncode,
        started_at=started_at,
        completed_at=now(),
        pid=process.pid,
    )


def _require_c0_python_and_script(
    *,
    python_executable: str,
    c0_script: Path,
    project_root: Path,
) -> None:
    _require_project_python(python_executable, project_root=project_root)
    expected_script = project_root / "scripts/preflight_trade_management_shadow.py"
    if c0_script.resolve() != expected_script.resolve():
        raise RuntimeError("C0_PROVIDER_WORKER_SCRIPT_DENIED")


def _require_project_python(python_executable: str, *, project_root: Path) -> None:
    expected = project_root / ".venv/bin/python"
    try:
        matches = Path(python_executable).samefile(expected)
    except OSError as error:
        raise RuntimeError("PROJECT_PYTHON_UNAVAILABLE") from error
    if not matches:
        raise RuntimeError("PYTHON_EXECUTABLE_DENIED")


def _open_owner_only_exclusive(path: Path):
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    return os.fdopen(descriptor, "wb")


def _run_captured_allowed(
    role: str,
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=None if env is None else dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired as pending_error:
            raise RuntimeError(
                f"{role}_TIMEOUT_TERMINATION_PENDING"
            ) from pending_error
        if _process_group_exists(process.pid):
            raise RuntimeError(f"{role}_TIMEOUT_TERMINATION_PENDING") from error
        raise RuntimeError(f"{role}_TIMEOUT_TERMINATED") from error
    return subprocess.CompletedProcess(
        args=argv,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    return True


def _selected_environment(keys: frozenset[str] | set[str]) -> dict[str, str]:
    return {key: os.environ[key] for key in keys if os.environ.get(key)}
