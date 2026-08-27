from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import capture_no_overnight_observe_only as capture_script
from scripts import no_overnight_capture_common as capture_common


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _cli_args(tmp_path: Path, env_file: Path, settings_file: Path) -> tuple[str, ...]:
    return (
        "--campaign-id",
        "observe-only-cli-test",
        "--session-date",
        "2026-08-31",
        "--artifact-root",
        str(tmp_path / "campaign"),
        "--env-file",
        str(env_file),
        "--settings-file",
        str(settings_file),
    )


def test_observe_only_cli_checks_clean_identity_before_postgres(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / "capture.env"
    env_file.write_text(
        "TRADING_JOURNAL_BACKEND=postgresql\n"
        "PostgreSQL_DSN=postgresql://reviewed.example/reviewed\n"
    )
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")
    journal_created = False

    def fail_code_identity() -> str:
        raise ValueError("dirty worktree")

    def build_journal(_persistence):
        nonlocal journal_created
        journal_created = True
        raise AssertionError("PostgreSQL must not be initialized")

    monkeypatch.setattr(capture_script, "_code_identity", fail_code_identity)
    monkeypatch.setattr(capture_script, "build_journal_repository", build_journal)

    with pytest.raises(ValueError, match="dirty worktree"):
        capture_script.main(
            _cli_args(tmp_path, env_file, settings_file)
        )

    assert journal_created is False


@pytest.mark.parametrize(
    ("environment", "message"),
    (
        ("TRADING_JOURNAL_BACKEND=memory\n", "requires the PostgreSQL Journal"),
        (
            "TRADING_JOURNAL_BACKEND=postgresql\n",
            "DATABASE_URL is required",
        ),
    ),
)
def test_observe_only_cli_fails_closed_without_postgres_or_dsn(
    monkeypatch,
    tmp_path,
    environment: str,
    message: str,
) -> None:
    env_file = tmp_path / "capture.env"
    env_file.write_text(environment)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")
    identity_checked = False
    journal_created = False

    def code_identity() -> str:
        nonlocal identity_checked
        identity_checked = True
        return "a" * 40

    def build_journal(_persistence):
        nonlocal journal_created
        journal_created = True
        raise AssertionError("PostgreSQL must not be initialized")

    monkeypatch.setattr(capture_script, "_code_identity", code_identity)
    monkeypatch.setattr(capture_script, "build_journal_repository", build_journal)

    with pytest.raises(ValueError, match=message):
        capture_script.main(_cli_args(tmp_path, env_file, settings_file))

    assert identity_checked is False
    assert journal_created is False


def test_code_identity_detects_untracked_files_hidden_by_git_config(
    monkeypatch,
    tmp_path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "codex-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Codex Test"],
        cwd=repository,
        check=True,
    )
    tracked = repository / "tracked.py"
    tracked.write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "tracked.py"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "status.showUntrackedFiles", "no"],
        cwd=repository,
        check=True,
    )
    (repository / "untracked.py").write_text("VALUE = 2\n")
    monkeypatch.setattr(capture_common, "PROJECT_ROOT", repository)
    monkeypatch.setenv("GIT_WORK_TREE", os.fspath(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")

    with pytest.raises(ValueError, match="clean code worktree"):
        capture_common._code_identity()


def test_clean_git_environment_removes_repository_redirection(monkeypatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/tmp/redirected.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/redirected-worktree")
    monkeypatch.setenv("GIT_INDEX_FILE", "/tmp/redirected-index")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "status.showUntrackedFiles")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "no")

    environment = capture_common._clean_git_environment()

    assert "GIT_DIR" not in environment
    assert "GIT_WORK_TREE" not in environment
    assert "GIT_INDEX_FILE" not in environment
    assert "GIT_CONFIG_KEY_0" not in environment
    assert "GIT_CONFIG_VALUE_0" not in environment


def test_observe_only_cli_settings_file_is_explicit_no_follow(tmp_path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")
    linked = tmp_path / "linked-settings.json"
    linked.symlink_to(settings_file)

    with pytest.raises(ValueError, match="unsafe"):
        capture_script._active_settings_from_file(linked)


def test_observe_only_cli_parser_requires_settings_file() -> None:
    parser = capture_script.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            (
                "--campaign-id",
                "observe-only-cli-test",
                "--session-date",
                "2026-08-31",
                "--artifact-root",
                "/tmp/campaign",
                "--env-file",
                "/tmp/capture.env",
            )
        )


@pytest.mark.parametrize(
    "script_name",
    (
        "capture_no_overnight_disabled_baseline.py",
        "capture_no_overnight_observe_only.py",
    ),
)
def test_no_overnight_capture_cli_direct_help_uses_current_checkout(
    script_name: str,
    tmp_path: Path,
) -> None:
    poison_root = tmp_path / "poison"
    poison_scripts = poison_root / "scripts"
    poison_scripts.mkdir(parents=True)
    (poison_scripts / "__init__.py").write_text("")
    (poison_scripts / "no_overnight_capture_common.py").write_text(
        "raise RuntimeError('external scripts package loaded')\n"
    )
    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPATH"] = str(poison_root)
    script_path = REPOSITORY_ROOT / "scripts" / script_name
    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--campaign-id" in completed.stdout
    assert "--settings-file" in completed.stdout

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy,sys;"
                "values=runpy.run_path(sys.argv[1],run_name='checkout_probe');"
                "print(values['_CAPTURE_COMMON'].PROJECT_ROOT)"
            ),
            str(script_path),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == str(REPOSITORY_ROOT)


def test_observe_only_cli_source_constructs_only_mock_provider() -> None:
    source = Path(capture_script.__file__).read_text(encoding="utf-8")

    assert "MockProvider()" in source
    assert "build_provider" not in source
    assert "Shioaji" not in source
