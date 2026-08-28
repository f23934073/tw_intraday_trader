"""Static import and documentation boundaries for institutional packages."""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED: dict[str, frozenset[str]] = {
    "institutional_data": frozenset(),
    "institutional_research": frozenset(
        {"institutional_data", "market_data", "watchlist"}
    ),
    "institutional_prior": frozenset(
        {"institutional_data", "institutional_research", "watchlist"}
    ),
    "institutional_mvp": frozenset({"backtest", "institutional_data"}),
}
EXECUTION_LAYERS = frozenset({"dashboard", "runtime", "simulation", "trading"})
DECLARED_PRODUCTION_CONSUMERS: dict[Path, frozenset[str]] = {
    Path("candidate/previous_session.py"): frozenset({"institutional_prior"}),
    Path("config/institutional_mvp.py"): frozenset(
        {"institutional_data", "institutional_mvp"}
    ),
}
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build"}
)


def _absolute_imports(path: Path) -> tuple[tuple[str, int], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                (alias.name.partition(".")[0], node.lineno) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module.partition(".")[0], node.lineno))
    return tuple(imports)


def _package_imports(project_root: Path, package: str) -> set[str]:
    imports: set[str] = set()
    for path in sorted((project_root / package).rglob("*.py")):
        imports.update(name for name, _ in _absolute_imports(path))
    imports.discard(package)
    return imports


def _boundary_violations(project_root: Path) -> tuple[str, ...]:
    violations: list[str] = []
    for package, declared_allowed in ALLOWED.items():
        package_root = project_root / package
        if not package_root.is_dir():
            violations.append(f"{package}: package root is missing")
            continue
        allowed = declared_allowed | {package}
        for path in sorted(package_root.rglob("*.py")):
            for imported, line in _absolute_imports(path):
                if (
                    imported.startswith("institutional_")
                    or imported in EXECUTION_LAYERS
                ) and imported not in allowed:
                    relative = path.relative_to(project_root)
                    violations.append(
                        f"{relative}:{line}: {package} imports forbidden {imported}"
                    )
    return tuple(violations)


def _production_consumers(project_root: Path) -> dict[Path, frozenset[str]]:
    consumers: dict[Path, frozenset[str]] = {}
    institutional_packages = frozenset(ALLOWED)
    for path in sorted(project_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        if relative.parts[0] in institutional_packages | {"scripts", "tests"}:
            continue
        imports = frozenset(name for name, _ in _absolute_imports(path))
        institutional_imports = imports & institutional_packages
        if institutional_imports:
            consumers[relative] = institutional_imports
    return consumers


def test_institutional_data_has_no_institutional_dependencies() -> None:
    imports = _package_imports(PROJECT_ROOT, "institutional_data")

    assert imports.isdisjoint(frozenset(ALLOWED) - {"institutional_data"})


def test_lineage_a_and_b_do_not_cross() -> None:
    assert _boundary_violations(PROJECT_ROOT) == ()


def test_no_institutional_module_imports_execution_layer() -> None:
    offenders = {
        package: sorted(_package_imports(PROJECT_ROOT, package) & EXECUTION_LAYERS)
        for package in ALLOWED
    }

    assert all(not imports for imports in offenders.values()), offenders


def test_declared_consumers_match_actual_imports() -> None:
    assert _production_consumers(PROJECT_ROOT) == DECLARED_PRODUCTION_CONSUMERS


def test_every_institutional_init_declares_layer_and_lineage() -> None:
    for package in ALLOWED:
        path = PROJECT_ROOT / package / "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstring = ast.get_docstring(tree, clean=False)
        assert docstring is not None
        assert "Layer:" in docstring
        assert "Lineage:" in docstring
        assert "Status:" in docstring


def test_boundary_checker_rejects_synthetic_violation(tmp_path: Path) -> None:
    for package in ALLOWED:
        (tmp_path / package).mkdir()
    violation = tmp_path / "institutional_prior" / "violation.py"
    violation.write_text(
        "from institutional_mvp.domain import InstitutionalMvpDailyPolicy\n",
        encoding="utf-8",
    )

    assert _boundary_violations(tmp_path) == (
        "institutional_prior/violation.py:1: institutional_prior imports "
        "forbidden institutional_mvp",
    )
