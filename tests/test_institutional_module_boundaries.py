"""Static import and documentation boundaries for institutional packages."""

from __future__ import annotations

import ast
import os
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
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
NON_SOURCE_TOP_LEVEL_NAMES = EXCLUDED_DIRECTORY_NAMES | {
    "cache",
    "data",
    "records",
    "research",
}


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


def _contains_python_source(project_root: Path, top_level: Path) -> bool:
    if top_level.is_symlink():
        return False
    try:
        resolved_project_root = project_root.resolve(strict=True)
        resolved_top_level = top_level.resolve(strict=True)
    except OSError:
        return False
    if (
        not resolved_top_level.is_dir()
        or resolved_top_level.parent != resolved_project_root
        or resolved_top_level != resolved_project_root / top_level.name
    ):
        return False

    for directory, directory_names, filenames in os.walk(
        resolved_top_level, followlinks=False
    ):
        current_directory = Path(directory)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if not name.startswith(".")
            and name not in EXCLUDED_DIRECTORY_NAMES
            and not (current_directory / name).is_symlink()
        )
        for filename in sorted(filenames):
            candidate = current_directory / filename
            if candidate.suffix != ".py" or candidate.is_symlink():
                continue
            try:
                resolved_candidate = candidate.resolve(strict=True)
                resolved_candidate.relative_to(resolved_top_level)
            except (OSError, ValueError):
                continue
            if resolved_candidate.is_file():
                return True
    return False


def _project_local_import_names(project_root: Path) -> frozenset[str]:
    resolved_project_root = project_root.resolve(strict=True)
    packages = {
        path.name
        for path in resolved_project_root.iterdir()
        if not path.is_symlink()
        and path.is_dir()
        and not path.name.startswith(".")
        and path.name not in NON_SOURCE_TOP_LEVEL_NAMES
        and _contains_python_source(resolved_project_root, path)
    }
    modules = {
        path.stem
        for path in resolved_project_root.iterdir()
        if not path.is_symlink()
        and path.is_file()
        and path.suffix == ".py"
        and path.resolve(strict=True).parent == resolved_project_root
    }
    return frozenset(packages | modules)


def _institutional_package_names(project_root: Path) -> frozenset[str]:
    return frozenset(
        name
        for name in _project_local_import_names(project_root)
        if name.startswith("institutional_")
    )


def _boundary_violations(project_root: Path) -> tuple[str, ...]:
    violations: list[str] = []
    project_local_names = _project_local_import_names(project_root)
    declared_packages = frozenset(ALLOWED)
    discovered_packages = _institutional_package_names(project_root)
    if discovered_packages != declared_packages:
        violations.append(
            "institutional package allowlist mismatch: "
            f"declared={','.join(sorted(declared_packages))}; "
            f"discovered={','.join(sorted(discovered_packages))}"
        )
    for package, declared_allowed in ALLOWED.items():
        package_root = project_root / package
        if not package_root.is_dir():
            violations.append(f"{package}: package root is missing")
            continue
        allowed = declared_allowed | {package}
        for path in sorted(package_root.rglob("*.py")):
            for imported, line in _absolute_imports(path):
                if imported in project_local_names and imported not in allowed:
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


def test_allowed_packages_match_actual_institutional_packages() -> None:
    assert _institutional_package_names(PROJECT_ROOT) == frozenset(ALLOWED)


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
        package_root = tmp_path / package
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
    violation = tmp_path / "institutional_prior" / "violation.py"
    violation.write_text(
        "from institutional_mvp.domain import InstitutionalMvpDailyPolicy\n",
        encoding="utf-8",
    )

    assert _boundary_violations(tmp_path) == (
        "institutional_prior/violation.py:1: institutional_prior imports "
        "forbidden institutional_mvp",
    )


def test_boundary_checker_rejects_project_local_candidate_leak(tmp_path: Path) -> None:
    for package in (*ALLOWED, "candidate"):
        package_root = tmp_path / package
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
    violation = tmp_path / "institutional_data" / "leak.py"
    violation.write_text(
        "from candidate.previous_session import PreviousSessionCandidateBuilder\n",
        encoding="utf-8",
    )

    assert _boundary_violations(tmp_path) == (
        "institutional_data/leak.py:1: institutional_data imports forbidden candidate",
    )


def test_boundary_checker_rejects_nested_namespace_leak(tmp_path: Path) -> None:
    for package in ALLOWED:
        package_root = tmp_path / package
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
    namespace_package = tmp_path / "project_namespace" / "subpkg"
    namespace_package.mkdir(parents=True)
    (namespace_package / "__init__.py").write_text("", encoding="utf-8")
    violation = tmp_path / "institutional_data" / "leak.py"
    violation.write_text("import project_namespace.subpkg\n", encoding="utf-8")

    assert _boundary_violations(tmp_path) == (
        "institutional_data/leak.py:1: institutional_data imports forbidden "
        "project_namespace",
    )


def test_project_local_discovery_accepts_nested_namespace(tmp_path: Path) -> None:
    namespace_package = tmp_path / "project_namespace" / "subpkg"
    namespace_package.mkdir(parents=True)
    (namespace_package / "__init__.py").write_text("", encoding="utf-8")
    for excluded_name in (".hidden", ".venv", "cache", "data", "research"):
        excluded_package = tmp_path / excluded_name / "subpkg"
        excluded_package.mkdir(parents=True)
        (excluded_package / "module.py").write_text("", encoding="utf-8")

    assert _project_local_import_names(tmp_path) == frozenset({"project_namespace"})


def test_project_local_discovery_rejects_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "repository"
    project_root.mkdir()
    outside_package = tmp_path / "outside" / "subpkg"
    outside_package.mkdir(parents=True)
    (outside_package / "module.py").write_text("", encoding="utf-8")
    nested_namespace = project_root / "nested_namespace"
    nested_namespace.mkdir()
    (nested_namespace / "subpkg").symlink_to(
        outside_package, target_is_directory=True
    )
    (project_root / "linked_namespace").symlink_to(
        outside_package, target_is_directory=True
    )

    assert _project_local_import_names(project_root) == frozenset()


def test_boundary_checker_rejects_institutional_package_matrix_drift(
    tmp_path: Path,
) -> None:
    for package in ALLOWED:
        package_root = tmp_path / package
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
    unknown_package = tmp_path / "institutional_unknown"
    unknown_package.mkdir()
    (unknown_package / "module.py").write_text("", encoding="utf-8")

    assert _boundary_violations(tmp_path) == (
        "institutional package allowlist mismatch: "
        "declared=institutional_data,institutional_mvp,institutional_prior,"
        "institutional_research; "
        "discovered=institutional_data,institutional_mvp,institutional_prior,"
        "institutional_research,institutional_unknown",
    )


def test_boundary_checker_rejects_nested_institutional_package_matrix_drift(
    tmp_path: Path,
) -> None:
    for package in ALLOWED:
        package_root = tmp_path / package
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
    unknown_package = tmp_path / "institutional_unknown" / "subpkg"
    unknown_package.mkdir(parents=True)
    (unknown_package / "module.py").write_text("", encoding="utf-8")

    assert _boundary_violations(tmp_path) == (
        "institutional package allowlist mismatch: "
        "declared=institutional_data,institutional_mvp,institutional_prior,"
        "institutional_research; "
        "discovered=institutional_data,institutional_mvp,institutional_prior,"
        "institutional_research,institutional_unknown",
    )
