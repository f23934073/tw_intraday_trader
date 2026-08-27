"""Strict local inputs shared by repository-owned no-overnight capture CLIs."""

from __future__ import annotations

from collections.abc import Mapping
from io import StringIO
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from dotenv import dotenv_values

from simulation.settings import (
    SETTINGS_SCHEMA_V1,
    SETTINGS_SCHEMA_V2,
    LocalPaperSettings,
    LocalPaperSettingsState,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _clean_git_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }


def _read_no_follow_file(path: Path, label: str) -> bytes:
    try:
        absolute_path = Path(os.path.abspath(os.fspath(path)))
    except TypeError as error:
        raise ValueError(f"{label} path is invalid") from error
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(os.sep, flags)
    try:
        for component in absolute_path.parent.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        file_fd = os.open(
            absolute_path.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        os.close(parent_fd)
        raise ValueError(f"{label} path is unsafe or unavailable") from error
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise ValueError(f"{label} must be a regular file")
        initial = os.fstat(file_fd)
        initial_fence = (
            initial.st_dev,
            initial.st_ino,
            initial.st_mode,
            initial.st_nlink,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        )
        chunks: list[bytes] = []
        while chunk := os.read(file_fd, 64 * 1024):
            chunks.append(chunk)
        final = os.fstat(file_fd)
        final_fence = (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        )
        if final_fence != initial_fence:
            raise ValueError(f"{label} changed during read")
        return b"".join(chunks)
    finally:
        os.close(file_fd)
        os.close(parent_fd)


def _environment_from_file(path: Path) -> dict[str, str]:
    try:
        text = _read_no_follow_file(path, "env file").decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("env file must be UTF-8") from error
    parsed = dotenv_values(stream=StringIO(text), interpolate=False)
    if any(
        type(key) is not str or type(value) is not str
        for key, value in parsed.items()
    ):
        raise ValueError("env file contains an unset or invalid value")
    return dict(parsed)


def _active_settings_from_file(path: Path) -> LocalPaperSettingsState:
    encoded = _read_no_follow_file(path, "settings file")
    try:
        raw = json.loads(encoded)
        if not isinstance(raw, Mapping):
            raise ValueError("settings document must be an object")
        document_schema = str(raw.get("schema_version") or "")
        if document_schema not in {SETTINGS_SCHEMA_V1, SETTINGS_SCHEMA_V2}:
            raise ValueError("settings schema is unsupported")
        return LocalPaperSettingsState(
            revision=int(raw["revision"]),
            active=LocalPaperSettings.from_mapping(
                raw["active"],
                schema_version=(
                    SETTINGS_SCHEMA_V1
                    if document_schema == SETTINGS_SCHEMA_V1
                    else None
                ),
            ),
            draft=LocalPaperSettings.from_mapping(
                raw["draft"],
                schema_version=(
                    SETTINGS_SCHEMA_V1
                    if document_schema == SETTINGS_SCHEMA_V1
                    else None
                ),
            ),
            active_session_id=str(raw["active_session_id"]),
            active_settings_revision=int(raw["active_settings_revision"]),
            draft_settings_revision=int(raw["draft_settings_revision"]),
            updated_at=(
                str(raw["updated_at"])
                if raw.get("updated_at") is not None
                else None
            ),
        )
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        raise ValueError("active Local Paper settings file is invalid") from error


def _code_identity() -> str:
    git_environment = _clean_git_environment()
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ],
        cwd=PROJECT_ROOT,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        raise ValueError("operational capture requires a clean code worktree")
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=PROJECT_ROOT,
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    identity = completed.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", identity) is None:
        raise ValueError("operational capture requires a canonical Git commit")
    return identity
