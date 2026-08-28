"""Regression contracts for the hygiene integration remediation."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.build_price_coverage_source_drift_acknowledgement import (
    build_acknowledgement,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ci_checkout_fetches_complete_history_for_pcd_gate() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    test_job = workflow.partition("\n  postgres-journal:")[0]
    checkout_with_history = (
        "      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n"
    )

    assert checkout_with_history in test_job


def test_pcd_builder_records_full_commit_identities() -> None:
    acknowledgement = build_acknowledgement()
    causing_commits = [
        commit
        for source in acknowledgement["pinned_sources"]
        for commit in source["causing_commits"]
    ]

    assert causing_commits
    assert all(len(commit) == 40 for commit in causing_commits)
    assert all(
        all(character in "0123456789abcdef" for character in commit) for commit in causing_commits
    )


def test_ruff_has_no_blanket_per_file_ignores() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lint = configuration["tool"]["ruff"]["lint"]

    assert "per-file-ignores" not in lint
    assert lint["select"] == ["F", "E9"]
