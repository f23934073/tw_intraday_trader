"""Report institutional package dependencies and repository consumers via AST."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path
from typing import Iterable


INSTITUTIONAL_PACKAGES = (
    "institutional_data",
    "institutional_research",
    "institutional_prior",
    "institutional_mvp",
)
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build"}
)


def imported_top_level_packages(path: Path) -> frozenset[str]:
    """Return absolute top-level imports without importing the inspected file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.partition(".")[0])
    return frozenset(imports)


def package_imports(package_root: Path) -> frozenset[str]:
    """Return absolute top-level imports used anywhere below one package root."""

    imports: set[str] = set()
    for path in sorted(package_root.rglob("*.py")):
        imports.update(imported_top_level_packages(path))
    imports.discard(package_root.name)
    return frozenset(imports)


def project_package_names(project_root: Path) -> frozenset[str]:
    """Return top-level Python package directories in the repository."""

    return frozenset(
        path.name
        for path in project_root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )


def python_files(project_root: Path) -> Iterable[Path]:
    """Yield repository Python files while excluding generated environments."""

    for path in sorted(project_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        yield path


def institutional_consumers(
    project_root: Path,
) -> dict[str, dict[Path, frozenset[str]]]:
    """Group non-institutional importers into production, tests, and scripts."""

    grouped: dict[str, dict[Path, frozenset[str]]] = defaultdict(dict)
    institutional_names = frozenset(INSTITUTIONAL_PACKAGES)
    for path in python_files(project_root):
        relative = path.relative_to(project_root)
        if relative.parts[0] in institutional_names:
            continue
        imports = imported_top_level_packages(path) & institutional_names
        if not imports:
            continue
        category = (
            "tests"
            if relative.parts[0] == "tests"
            else "scripts"
            if relative.parts[0] == "scripts"
            else "production"
        )
        grouped[category][relative] = imports
    return grouped


def _names(values: Iterable[str]) -> str:
    rendered = ", ".join(f"`{value}`" for value in sorted(values))
    return rendered or "(none)"


def render_markdown(project_root: Path) -> str:
    """Render the dependency report in deterministic Markdown."""

    project_names = project_package_names(project_root)
    institutional_names = frozenset(INSTITUTIONAL_PACKAGES)
    lines = [
        "# Institutional dependency report",
        "",
        "## Package imports",
        "",
        "| Package | Institutional dependencies | Other project dependencies |",
        "|---|---|---|",
    ]
    for package in INSTITUTIONAL_PACKAGES:
        imports = package_imports(project_root / package)
        lines.append(
            f"| `{package}` | "
            f"{_names(imports & institutional_names)} | "
            f"{_names((imports & project_names) - institutional_names)} |"
        )

    lines.extend(["", "## Consumers", ""])
    consumers = institutional_consumers(project_root)
    for category in ("production", "tests", "scripts"):
        entries = consumers.get(category, {})
        lines.extend(
            [
                f"### {category}",
                "",
                "| Path | Imported institutional packages |",
                "|---|---|",
            ]
        )
        if entries:
            for path, imports in sorted(entries.items(), key=lambda item: str(item[0])):
                lines.append(f"| `{path.as_posix()}` | {_names(imports)} |")
        else:
            lines.append("| (none) | (none) |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to inspect",
    )
    args = parser.parse_args()
    print(render_markdown(args.project_root.resolve()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
