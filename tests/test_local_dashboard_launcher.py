"""Focused tests for the project-root ``make run`` safe Dashboard launcher.

The launcher is exercised with a stub interpreter so no server is started and
no database is touched; the stub only records the argv/env/cwd it received.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
SCRIPT = REPO_ROOT / "scripts" / "run_local_dashboard.sh"
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "backtest"
# Sealed local Datasets are gitignored, so the default directory may be absent
# (fresh clone / CI); the two default-path tests are complementary.
DEFAULT_DATA_DIR_PRESENT = DEFAULT_DATA_DIR.is_dir()

UNSET_VARS = (
    "BACKTEST_DATABASE_BACKEND",
    "BACKTEST_DATABASE_URL",
    "DATABASE_URL",
    "POSTGRESQL_DSN",
    "PostgreSQL_DSN",
)
FORCED_VARS = {
    "PROVIDER": "mock",
    "TRADING_JOURNAL_BACKEND": "memory",
    "BACKTEST_INCREMENTAL_SYNC_ENABLED": "false",
}
# Deliberately recognisable secret: must never reach the child env or stdout.
LEAKY_DSN = "postgresql://leak_user:leak_pass@127.0.0.1:5432/leak_db"
# Inherited BACKTEST_DATA_DIR must be replaced, never honoured.
POISONED_DATA_DIR = "/nonexistent/poisoned-backtest-data"


@pytest.fixture
def stub_python(tmp_path: Path) -> dict[str, Path]:
    """A fake interpreter that records what the launcher hands it."""
    args_file = tmp_path / "argv.txt"
    env_file = tmp_path / "env.txt"
    cwd_file = tmp_path / "cwd.txt"
    stub = tmp_path / "stub-python"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$@\" > '{args_file}'\n"
        f"env > '{env_file}'\n"
        f"pwd -P > '{cwd_file}'\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return {"bin": stub, "args": args_file, "env": env_file, "cwd": cwd_file}


def _run_launcher(
    tmp_path: Path, python_bin: Path | str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "TW_DASHBOARD_PYTHON": str(python_bin),
        # Poisoned process-level overrides: `.env` PostgreSQL settings must win.
        "BACKTEST_DATABASE_BACKEND": "sqlite",
        "BACKTEST_DATABASE_URL": LEAKY_DSN,
        "DATABASE_URL": LEAKY_DSN,
        "POSTGRESQL_DSN": LEAKY_DSN,
        "PostgreSQL_DSN": LEAKY_DSN,
        # Values that the launcher must override.
        "PROVIDER": "shioaji",
        "TRADING_JOURNAL_BACKEND": "postgresql",
        "BACKTEST_INCREMENTAL_SYNC_ENABLED": "true",
        "BACKTEST_DATA_DIR": POISONED_DATA_DIR,
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,  # not the repo: the script must derive the repo root itself
        env=env,
        capture_output=True,
        text=True,
        errors="replace",  # bash localises errors; never let odd bytes crash the test
        timeout=30,
        check=False,
    )


def _child_env(stub: dict[str, Path]) -> dict[str, str]:
    lines = stub["env"].read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def _any_data_dir(tmp_path: Path) -> dict[str, str]:
    """Override env for tests that only need *some* valid data dir."""
    return {"TW_DASHBOARD_BACKTEST_DATA_DIR": str(_make_dataset_root(tmp_path / "any-datasets", ("dataset-a",)))}


def _make_dataset_root(root: Path, dataset_ids: tuple[str, ...]) -> Path:
    """A fake BACKTEST_DATA_DIR holding <dataset-id>/manifest.json entries."""
    root.mkdir(parents=True, exist_ok=True)
    for dataset_id in dataset_ids:
        (root / dataset_id).mkdir()
        (root / dataset_id / "manifest.json").write_text(
            f'{{"dataset_id": "{dataset_id}"}}\n', encoding="utf-8"
        )
    return root


# --- static shape ----------------------------------------------------------


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n")


def test_script_passes_bash_syntax_check() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_makefile_run_target_delegates_to_script() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert any(line.startswith(".PHONY:") and "run" in line.split()[1:] for line in lines)
    run_index = next(i for i, line in enumerate(lines) if line == "run:")
    recipe = lines[run_index + 1]
    assert recipe.startswith("\t"), "make recipes must be tab-indented"
    assert "scripts/run_local_dashboard.sh" in recipe


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_dry_run_invokes_script_without_running_it() -> None:
    result = subprocess.run(
        ["make", "-n", "run"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "scripts/run_local_dashboard.sh" in result.stdout
    # Dry run must not have actually executed the launcher.
    assert "http://127.0.0.1:8000" not in result.stdout


# --- runtime semantics (stub interpreter, no server, no database) ----------


def test_launcher_unsets_process_db_overrides_so_dotenv_wins(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"], _any_data_dir(tmp_path))
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    for name in UNSET_VARS:
        assert name not in env, f"{name} must be unset so .env PostgreSQL settings win"
    assert LEAKY_DSN not in env.values()


def test_launcher_forces_mock_provider_memory_journal_and_no_incremental_sync(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"], _any_data_dir(tmp_path))
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    for name, expected in FORCED_VARS.items():
        assert env.get(name) == expected, name


def test_launcher_keeps_settings_in_fresh_temp_dir(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    data_root = _make_dataset_root(tmp_path / "datasets", ("dataset-a",))
    result = _run_launcher(
        tmp_path, stub_python["bin"], {"TW_DASHBOARD_BACKTEST_DATA_DIR": str(data_root)}
    )
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    settings_path = Path(env["LOCAL_PAPER_SETTINGS_PATH"])
    assert settings_path.name == "settings-v1.json"
    assert str(settings_path).startswith(str(tmp_path)), "throwaway settings must live under TMPDIR"
    assert settings_path.parent.is_dir()
    assert REPO_ROOT not in settings_path.parents
    # Settings and historical data are deliberately decoupled now.
    assert data_root not in settings_path.parents
    assert str(settings_path.parent) in result.stdout


@pytest.mark.skipif(not DEFAULT_DATA_DIR_PRESENT, reason="repo data/backtest not present")
def test_launcher_defaults_backtest_data_dir_to_repo_data_backtest(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    assert Path(env["BACKTEST_DATA_DIR"]) == DEFAULT_DATA_DIR.resolve()
    assert env["BACKTEST_DATA_DIR"] != POISONED_DATA_DIR, "inherited BACKTEST_DATA_DIR must not win"
    assert "TW_DASHBOARD_BACKTEST_DATA_DIR" not in env
    assert str(DEFAULT_DATA_DIR.resolve()) in result.stdout
    expected_manifests = len(list(DEFAULT_DATA_DIR.glob("*/manifest.json")))
    assert f"manifest 數量：{expected_manifests}" in result.stdout


@pytest.mark.skipif(DEFAULT_DATA_DIR_PRESENT, reason="repo data/backtest is present")
def test_launcher_fails_clearly_when_default_data_dir_missing(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 1
    assert str(DEFAULT_DATA_DIR) in result.stderr
    assert "TW_DASHBOARD_BACKTEST_DATA_DIR" in result.stderr
    assert not stub_python["env"].exists(), "stub interpreter must not have been executed"


def test_launcher_honours_explicit_data_dir_override_and_counts_manifests(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    data_root = _make_dataset_root(
        tmp_path / "datasets", ("dataset-finmind-sponsor-sha256-aaaa", "dataset-finmind-sponsor-sha256-bbbb")
    )
    (data_root / "backtest.sqlite3").write_bytes(b"")  # sibling files must not be counted
    result = _run_launcher(
        tmp_path, stub_python["bin"], {"TW_DASHBOARD_BACKTEST_DATA_DIR": str(data_root)}
    )
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    assert Path(env["BACKTEST_DATA_DIR"]) == data_root.resolve()
    assert "TW_DASHBOARD_BACKTEST_DATA_DIR" not in env, "launcher-only override must not leak to the dashboard"
    assert "TW_DASHBOARD_BACKTEST_DATA_DIR" in result.stdout
    assert "manifest 數量：2" in result.stdout
    assert "警告" not in result.stderr


def test_launcher_resolves_relative_override_against_invoking_directory(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    data_root = _make_dataset_root(tmp_path / "rel-datasets", ("dataset-a",))
    result = _run_launcher(
        tmp_path, stub_python["bin"], {"TW_DASHBOARD_BACKTEST_DATA_DIR": "rel-datasets"}
    )
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    assert Path(env["BACKTEST_DATA_DIR"]).is_absolute()
    assert Path(env["BACKTEST_DATA_DIR"]) == data_root.resolve()


def test_launcher_warns_when_data_dir_has_no_manifests(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    data_root = _make_dataset_root(tmp_path / "empty-datasets", ())
    result = _run_launcher(
        tmp_path, stub_python["bin"], {"TW_DASHBOARD_BACKTEST_DATA_DIR": str(data_root)}
    )
    assert result.returncode == 0, result.stderr  # empty is allowed, but loudly
    assert "manifest 數量：0" in result.stdout
    assert "manifest.json" in result.stderr


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_launcher_fails_clearly_when_override_data_dir_invalid(
    tmp_path: Path, stub_python: dict[str, Path], kind: str
) -> None:
    target = tmp_path / "bad-datasets"
    if kind == "file":
        target.write_text("not a directory", encoding="utf-8")
    result = _run_launcher(tmp_path, stub_python["bin"], {"TW_DASHBOARD_BACKTEST_DATA_DIR": str(target)})
    assert result.returncode == 1
    assert str(target) in result.stderr
    assert "TW_DASHBOARD_BACKTEST_DATA_DIR" in result.stderr
    assert "leak_pass" not in result.stdout + result.stderr
    assert not stub_python["env"].exists(), "stub interpreter must not have been executed"


def test_launcher_runs_dashboard_module_from_repo_root(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"], _any_data_dir(tmp_path))
    assert result.returncode == 0, result.stderr
    argv = stub_python["args"].read_text(encoding="utf-8").split()
    assert argv == ["-m", "dashboard"]
    cwd = Path(stub_python["cwd"].read_text(encoding="utf-8").strip())
    assert cwd == REPO_ROOT.resolve()


def test_launcher_never_prints_credentials(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"], _any_data_dir(tmp_path))
    output = result.stdout + result.stderr
    assert LEAKY_DSN not in output
    assert "leak_pass" not in output
    assert "http://127.0.0.1:8000/" in result.stdout
    env = _child_env(stub_python)
    assert env["BACKTEST_DATA_DIR"] != POISONED_DATA_DIR


def test_launcher_fails_clearly_when_python_missing(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, tmp_path / "does-not-exist")
    assert result.returncode == 1
    assert result.stderr.strip()
    assert "leak_pass" not in result.stdout + result.stderr
    assert not stub_python["env"].exists(), "stub interpreter must not have been executed"
