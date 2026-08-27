"""Packaging regression tests for the Institutional MVP package."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
import tomllib


def test_institutional_mvp_is_included_in_package_discovery() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text())
    include_patterns = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]

    assert any(fnmatchcase("institutional_mvp", pattern) for pattern in include_patterns)
    assert any(
        fnmatchcase("institutional_mvp.application", pattern)
        for pattern in include_patterns
    )
