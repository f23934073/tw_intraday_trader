"""Exact read-only Git subprocesses for Trade Management runtime identity."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


GIT_EXECUTABLE = "/usr/bin/git"
TERMINATION_GRACE_SECONDS = 15


def run_git_head(project_root: Path) -> str:
    result = _run_git(
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=project_root,
        timeout=10,
    )
    return result.stdout.strip()


def run_git_status(project_root: Path) -> str:
    result = _run_git(
        [GIT_EXECUTABLE, "status", "--porcelain", "--untracked-files=all"],
        cwd=project_root,
        timeout=30,
    )
    return result.stdout


def _run_git(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=_git_environment(),
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
            raise RuntimeError("GIT_TIMEOUT_TERMINATION_PENDING") from pending_error
        if _process_group_exists(process.pid):
            raise RuntimeError("GIT_TIMEOUT_TERMINATION_PENDING") from error
        raise RuntimeError("GIT_TIMEOUT_TERMINATED") from error
    result = subprocess.CompletedProcess(
        args=argv,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    return True


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": "/var/empty",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "XDG_CONFIG_HOME": "/var/empty",
    }
