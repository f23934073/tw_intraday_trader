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


def _run_launcher(tmp_path: Path, python_bin: Path | str) -> subprocess.CompletedProcess[str]:
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
    }
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
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    for name in UNSET_VARS:
        assert name not in env, f"{name} must be unset so .env PostgreSQL settings win"
    assert LEAKY_DSN not in env.values()


def test_launcher_forces_mock_provider_memory_journal_and_no_incremental_sync(
    tmp_path: Path, stub_python: dict[str, Path]
) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    for name, expected in FORCED_VARS.items():
        assert env.get(name) == expected, name


def test_launcher_uses_fresh_temp_settings_and_data_dirs(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 0, result.stderr
    env = _child_env(stub_python)
    settings_path = Path(env["LOCAL_PAPER_SETTINGS_PATH"])
    data_dir = Path(env["BACKTEST_DATA_DIR"])
    assert settings_path.name == "settings-v1.json"
    assert settings_path.parent == data_dir.parent
    assert data_dir.is_dir()
    assert str(data_dir).startswith(str(tmp_path)), "throwaway data must live under TMPDIR"
    assert REPO_ROOT not in data_dir.parents and data_dir != REPO_ROOT
    assert str(settings_path) in result.stdout or str(settings_path.parent) in result.stdout


def test_launcher_runs_dashboard_module_from_repo_root(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    assert result.returncode == 0, result.stderr
    argv = stub_python["args"].read_text(encoding="utf-8").split()
    assert argv == ["-m", "dashboard"]
    cwd = Path(stub_python["cwd"].read_text(encoding="utf-8").strip())
    assert cwd == REPO_ROOT.resolve()


def test_launcher_never_prints_credentials(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, stub_python["bin"])
    output = result.stdout + result.stderr
    assert LEAKY_DSN not in output
    assert "leak_pass" not in output
    assert "http://127.0.0.1:8000/" in result.stdout


def test_launcher_fails_clearly_when_python_missing(tmp_path: Path, stub_python: dict[str, Path]) -> None:
    result = _run_launcher(tmp_path, tmp_path / "does-not-exist")
    assert result.returncode == 1
    assert result.stderr.strip()
    assert "leak_pass" not in result.stdout + result.stderr
    assert not stub_python["env"].exists(), "stub interpreter must not have been executed"
