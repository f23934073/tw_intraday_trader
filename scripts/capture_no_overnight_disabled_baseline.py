#!/usr/bin/env python3
"""Capture one real-time, evidence-only no-overnight DISABLED baseline."""

from __future__ import annotations

import argparse
from datetime import date
from io import StringIO
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Sequence

from dotenv import dotenv_values

from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from market_data.provider import MockProvider
from runtime.clock import SystemClock
from runtime.composition import RuntimeComposition
from runtime.no_overnight_evidence_capture import capture_disabled_baseline
from runtime.trading_persistence import build_journal_repository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _environment_from_file(path: Path) -> dict[str, str]:
    try:
        absolute_path = Path(os.path.abspath(os.fspath(path)))
    except TypeError as error:
        raise ValueError("env file path is invalid") from error
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
        raise ValueError("env file path is unsafe or unavailable") from error
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise ValueError("env file must be a regular file")
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
            raise ValueError("env file changed during read")
    finally:
        os.close(file_fd)
        os.close(parent_fd)
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("env file must be UTF-8") from error
    parsed = dotenv_values(stream=StringIO(text), interpolate=False)
    if any(type(key) is not str or type(value) is not str for key, value in parsed.items()):
        raise ValueError("env file contains an unset or invalid value")
    return dict(parsed)


def _code_identity() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        raise ValueError("operational capture requires a clean code worktree")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    identity = completed.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", identity) is None:
        raise ValueError("operational capture requires a canonical Git commit")
    return identity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-date", required=True, type=date.fromisoformat)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    persistence = TradingPersistenceConfig.from_environment(
        _environment_from_file(args.env_file)
    )
    if persistence.backend is not TradingJournalBackend.POSTGRESQL:
        raise ValueError("operational baseline requires the PostgreSQL Journal")

    code_identity = _code_identity()
    provider = MockProvider()
    report = capture_disabled_baseline(
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        code_identity=code_identity,
        artifact_root=args.artifact_root,
        marker_journal_factory=lambda: build_journal_repository(persistence),
        provider=provider,
        clock=SystemClock(),
        runtime_factory=lambda **values: RuntimeComposition.create(
            **values,
            persistence_config=persistence,
        ),
    )
    print(
        json.dumps(
            report.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
