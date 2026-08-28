from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import check_planning_consistency as checker


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_planning_consistency.py"


def _build_valid_repository(root: Path) -> Path:
    active_ticket = root / ".planning" / "active-ticket"
    active_ticket.mkdir(parents=True)
    (root / ".planning" / ".active_plan").write_text(
        "active-ticket\n", encoding="utf-8"
    )
    for filename in checker.REQUIRED_TICKET_FILES:
        (active_ticket / filename).write_text("# Ticket record\n", encoding="utf-8")
    for filename in checker.GLOBAL_LOG_FILES:
        (root / filename).write_text(
            f"{checker.PLANNING_SCOPE_MARKER}\n# Global record\n", encoding="utf-8"
        )
    return root


def _rule_ids(diagnostics: list[checker.Diagnostic]) -> set[str]:
    return {diagnostic.rule_id for diagnostic in diagnostics}


def _rendered(diagnostics: list[checker.Diagnostic]) -> set[str]:
    return {diagnostic.render() for diagnostic in diagnostics}


def test_current_repository_passes_cli_check() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_pc001_rejects_missing_active_pointer(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / ".planning" / ".active_plan").unlink()

    errors, _ = checker.check_repository(root)

    assert "PC001: active_plan pointer is missing or malformed" in _rendered(errors)


def test_pc001_rejects_multiline_active_pointer(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / ".planning" / ".active_plan").write_text(
        "active-ticket\nsecond-ticket\n", encoding="utf-8"
    )

    errors, _ = checker.check_repository(root)

    assert "PC001: active_plan pointer is missing or malformed" in _rendered(errors)


def test_pc002_rejects_nonexistent_active_ticket(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / ".planning" / ".active_plan").write_text("missing\n", encoding="utf-8")

    errors, _ = checker.check_repository(root)

    assert (
        "PC002: active_plan points to non-existent ticket: missing"
        in _rendered(errors)
    )


def test_pc002_rejects_active_ticket_symlink_escape(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    active_ticket = root / ".planning" / "active-ticket"
    outside_ticket = root / "outside-ticket"
    active_ticket.rename(outside_ticket)
    active_ticket.symlink_to(outside_ticket, target_is_directory=True)

    errors, _ = checker.check_repository(root)

    assert "PC002" in _rule_ids(errors)


def test_pc003_rejects_missing_active_ticket_file(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / ".planning" / "active-ticket" / "progress.md").unlink()

    errors, _ = checker.check_repository(root)

    assert "PC003: active ticket is missing progress.md" in _rendered(errors)


def test_pc003_rejects_required_file_symlink_escape(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    required_file = root / ".planning" / "active-ticket" / "progress.md"
    outside_file = root / "outside-progress.md"
    required_file.rename(outside_file)
    required_file.symlink_to(outside_file)

    errors, _ = checker.check_repository(root)

    assert "PC003" in _rule_ids(errors)


def test_pc004_rejects_root_task_plan(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / "task_plan.md").write_text("# Deprecated\n", encoding="utf-8")

    errors, _ = checker.check_repository(root)

    assert (
        "PC004: root task_plan.md is deprecated; use "
        ".planning/<active>/task_plan.md"
        in _rendered(errors)
    )


def test_pc005_rejects_oversized_global_log(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / "findings.md").write_text(
        checker.PLANNING_SCOPE_MARKER + "\n" + ("line\n" * 1_500),
        encoding="utf-8",
    )

    errors, _ = checker.check_repository(root)

    assert (
        "PC005: findings.md exceeds 1500 lines; archive older sessions to "
        ".planning/_archive/"
        in _rendered(errors)
    )


def test_pc006_rejects_missing_scope_header(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / "progress.md").write_text("# Global record\n", encoding="utf-8")

    errors, _ = checker.check_repository(root)

    assert (
        "PC006: progress.md is missing its planning-scope header"
        in _rendered(errors)
    )


def test_pc007_is_warning_only(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    inactive_ticket = root / ".planning" / "inactive-ticket"
    inactive_ticket.mkdir()
    (inactive_ticket / "task_plan.md").write_text("# Plan\n", encoding="utf-8")

    errors, warnings = checker.check_repository(root)

    assert errors == []
    assert _rule_ids(warnings) == {"PC007"}
    assert _rendered(warnings) == {
        "PC007: ticket inactive-ticket is missing findings.md",
        "PC007: ticket inactive-ticket is missing progress.md",
    }
    assert checker.main([], repository_root=root) == 0


def test_warn_only_downgrades_fail_closed_rule(tmp_path: Path) -> None:
    root = _build_valid_repository(tmp_path)
    (root / "task_plan.md").write_text("# Deprecated\n", encoding="utf-8")

    assert checker.main(["--warn-only"], repository_root=root) == 0
    assert checker.main([], repository_root=root) == 1
