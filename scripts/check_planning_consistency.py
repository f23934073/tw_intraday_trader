#!/usr/bin/env python3
"""Validate the repository's planning-document layout."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MAX_GLOBAL_LOG_LINES = 1_500
PLANNING_SCOPE_MARKER = "<!-- planning-scope: global -->"
REQUIRED_TICKET_FILES = ("task_plan.md", "findings.md", "progress.md")
GLOBAL_LOG_FILES = ("findings.md", "progress.md")


@dataclass(frozen=True)
class Diagnostic:
    """One consistency-check result."""

    rule_id: str
    message: str

    def render(self) -> str:
        return f"{self.rule_id}: {self.message}"


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _is_contained_regular_file(path: Path, parent: Path) -> bool:
    if path.is_symlink():
        return False
    try:
        resolved_parent = parent.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
    except OSError:
        return False
    return (
        resolved_path.is_file()
        and resolved_path.parent == resolved_parent
        and resolved_path == resolved_parent / path.name
    )


def _active_ticket(
    planning_dir: Path,
    errors: list[Diagnostic],
) -> tuple[str, Path] | None:
    pointer_text = _read_text(planning_dir / ".active_plan")
    if pointer_text is None:
        errors.append(
            Diagnostic("PC001", "active_plan pointer is missing or malformed")
        )
        return None

    pointer_lines = pointer_text.splitlines()
    if len(pointer_lines) != 1 or not pointer_lines[0].strip():
        errors.append(
            Diagnostic("PC001", "active_plan pointer is missing or malformed")
        )
        return None

    ticket_name = pointer_lines[0].strip()
    ticket_dir = planning_dir / ticket_name
    is_direct_child = Path(ticket_name).name == ticket_name and ticket_name not in {
        ".",
        "..",
    }
    resolved_ticket_dir = ticket_dir
    try:
        resolved_planning_dir = planning_dir.resolve(strict=True)
        resolved_ticket_dir = ticket_dir.resolve(strict=True)
    except OSError:
        is_resolved_direct_child = False
    else:
        is_resolved_direct_child = (
            not ticket_dir.is_symlink()
            and resolved_ticket_dir.is_dir()
            and resolved_ticket_dir.parent == resolved_planning_dir
            and resolved_ticket_dir == resolved_planning_dir / ticket_name
        )
    if not is_direct_child or not is_resolved_direct_child:
        errors.append(
            Diagnostic(
                "PC002",
                f"active_plan points to non-existent ticket: {ticket_name}",
            )
        )
        return None
    return ticket_name, resolved_ticket_dir


def check_repository(
    repository_root: Path,
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Return fail-closed errors and warning-only historical-ticket findings."""

    root = repository_root.resolve()
    planning_dir = root / ".planning"
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []

    active = _active_ticket(planning_dir, errors)
    if active is not None:
        _, active_dir = active
        for filename in REQUIRED_TICKET_FILES:
            if not _is_contained_regular_file(active_dir / filename, active_dir):
                errors.append(
                    Diagnostic("PC003", f"active ticket is missing {filename}")
                )

    if (root / "task_plan.md").exists():
        errors.append(
            Diagnostic(
                "PC004",
                "root task_plan.md is deprecated; use "
                ".planning/<active>/task_plan.md",
            )
        )

    for filename in GLOBAL_LOG_FILES:
        text = _read_text(root / filename)
        if text is None:
            errors.append(
                Diagnostic("PC006", f"{filename} is missing its planning-scope header")
            )
            continue
        if len(text.splitlines()) > MAX_GLOBAL_LOG_LINES:
            errors.append(
                Diagnostic(
                    "PC005",
                    f"{filename} exceeds 1500 lines; archive older sessions to "
                    ".planning/_archive/",
                )
            )
        if PLANNING_SCOPE_MARKER not in text.splitlines()[:10]:
            errors.append(
                Diagnostic("PC006", f"{filename} is missing its planning-scope header")
            )

    if planning_dir.is_dir():
        ticket_dirs = sorted(
            path
            for path in planning_dir.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        )
        for ticket_dir in ticket_dirs:
            for filename in REQUIRED_TICKET_FILES:
                if not (ticket_dir / filename).is_file():
                    warnings.append(
                        Diagnostic(
                            "PC007",
                            f"ticket {ticket_dir.name} is missing {filename}",
                        )
                    )

    return errors, warnings


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> int:
    parser = argparse.ArgumentParser(
        description="Check repository planning-document consistency."
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="report every violation without returning a failing exit code",
    )
    args = parser.parse_args(argv)

    errors, warnings = check_repository(repository_root)
    for diagnostic in (*errors, *warnings):
        print(diagnostic.render())

    if args.warn_only:
        return 0
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
