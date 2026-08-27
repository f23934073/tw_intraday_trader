from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import supervise_atomic_entry_benchmark_preflight as supervisor


FORMAL_ENV = {
    "BACKTEST_DATABASE_BACKEND": "postgresql",
    "BACKTEST_DATABASE_URL": (
        "postgresql://research:secret@localhost:5090/"
        "tw_intraday_trader_backtest"
    ),
}


def test_database_evidence_is_sanitized_and_exact() -> None:
    evidence = supervisor._database_evidence(FORMAL_ENV)
    assert evidence == {
        "backend": "postgresql",
        "host": "localhost",
        "port": 5090,
        "database": "tw_intraday_trader_backtest",
    }
    assert "secret" not in json.dumps(evidence)


@pytest.mark.parametrize(
    "override",
    [
        {"BACKTEST_DATABASE_BACKEND": "sqlite"},
        {"BACKTEST_DATABASE_URL": "postgresql://u:p@localhost:5090/other"},
        {
            "BACKTEST_DATABASE_URL": (
                "postgresql://u:p@localhost:5432/tw_intraday_trader_backtest"
            )
        },
    ],
)
def test_database_evidence_rejects_wrong_formal_identity(
    override: dict[str, str],
) -> None:
    environment = {**FORMAL_ENV, **override}
    with pytest.raises(RuntimeError):
        supervisor._database_evidence(environment)


def test_submit_command_is_fixed_and_contains_no_dsn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    run_root = tmp_path / "runs" / "r6-g3-fixed"
    argv = supervisor._submit_argv(run_root)

    assert argv[:4] == (
        "/bin/launchctl",
        "submit",
        "-l",
        supervisor.JOB_LABEL,
    )
    assert "/usr/bin/caffeinate" in argv
    assert "worker" in argv
    assert "BACKTEST_DATABASE_URL" not in " ".join(argv)
    assert "preflight_atomic_entry_benchmark.py" not in " ".join(argv)


def test_start_writes_durable_submission_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor.sys, "platform", "darwin")
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(supervisor, "PYTHON_EXECUTABLE", Path(sys.executable).resolve())
    monkeypatch.setattr(supervisor, "_launchd_job_exists", lambda: False)
    launched: list[tuple[str, ...]] = []

    def fake_run(argv: tuple[str, ...], *, check: bool) -> None:
        assert check is True
        launched.append(argv)

    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)
    result = supervisor.start_supervised(
        execute=True,
        now=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert result["executed"] is True
    assert len(launched) == 1
    run_root = Path(str(result["run_root"]))
    submission = json.loads((run_root / "submission.json").read_text())
    current = json.loads((tmp_path / "current.json").read_text())
    assert submission["status"] == "SUBMITTED"
    assert current["run_root"] == str(run_root)
    assert "secret" not in (run_root / "submission.json").read_text()


def test_start_refuses_second_loaded_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor.sys, "platform", "darwin")
    monkeypatch.setattr(supervisor, "PYTHON_EXECUTABLE", Path(sys.executable).resolve())
    monkeypatch.setattr(supervisor, "_launchd_job_exists", lambda: True)
    with pytest.raises(RuntimeError, match="already loaded"):
        supervisor.start_supervised(execute=True)


def test_start_rejects_non_macos_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="requires macOS"):
        supervisor.start_supervised(execute=True)


def test_worker_records_completion_and_removes_test_dsn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(supervisor, "load_dotenv", lambda *args, **kwargs: False)
    for key, value in FORMAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TEST_POSTGRES_DSN", FORMAL_ENV["BACKTEST_DATABASE_URL"])
    observed: list[list[str]] = []

    def fake_preflight(argv: object) -> int:
        observed.append(list(argv))
        assert "TEST_POSTGRES_DSN" not in supervisor.os.environ
        return 0

    run_root = tmp_path / "runs" / "r6-g3-worker"
    assert supervisor.run_worker(
        run_root=run_root,
        preflight_main=fake_preflight,
    ) == 0

    status = json.loads((run_root / "status.json").read_text())
    assert status["status"] == "COMPLETED"
    assert status["exit_code"] == 0
    assert status["test_postgres_dsn_removed"] is True
    assert observed == [["--execute", "--progress-every", "1000000"]]
    assert "secret" not in (run_root / "status.json").read_text()


def test_worker_records_failure_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(supervisor, "load_dotenv", lambda *args, **kwargs: False)
    for key, value in FORMAL_ENV.items():
        monkeypatch.setenv(key, value)

    def fail(_: object) -> int:
        raise ValueError("dataset rejected")

    run_root = tmp_path / "runs" / "r6-g3-failed"
    with pytest.raises(ValueError, match="dataset rejected"):
        supervisor.run_worker(run_root=run_root, preflight_main=fail)

    status = json.loads((run_root / "status.json").read_text())
    assert status["status"] == "FAILED"
    assert status["exit_code"] == 1
    assert status["error_type"] == "ValueError"


def test_worker_claim_makes_same_run_root_at_most_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(supervisor, "load_dotenv", lambda *args, **kwargs: False)
    for key, value in FORMAL_ENV.items():
        monkeypatch.setenv(key, value)
    calls = 0

    def fail(_: object) -> int:
        nonlocal calls
        calls += 1
        raise ValueError("deterministic rejection")

    run_root = tmp_path / "runs" / "r6-g3-one-shot"
    with pytest.raises(ValueError, match="deterministic rejection"):
        supervisor.run_worker(run_root=run_root, preflight_main=fail)
    first_status = (run_root / "status.json").read_bytes()

    assert supervisor.run_worker(run_root=run_root, preflight_main=fail) == 0
    assert calls == 1
    assert (run_root / "status.json").read_bytes() == first_status
    claim = json.loads((run_root / "worker_claim.json").read_text())
    assert claim["schema_version"] == supervisor.WORKER_CLAIM_SCHEMA
    assert claim["run_id"] == run_root.name


def test_worker_rejects_drifted_existing_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    run_root = tmp_path / "runs" / "r6-g3-drifted-claim"
    run_root.mkdir(parents=True)
    (run_root / "worker_claim.json").write_text(
        json.dumps({"schema_version": "foreign", "run_id": run_root.name}) + "\n"
    )

    with pytest.raises(RuntimeError, match="claim evidence drift"):
        supervisor.run_worker(run_root=run_root, preflight_main=lambda _: 0)


def test_status_marks_unloaded_running_worker_as_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(supervisor, "_launchd_job_exists", lambda: False)
    run_root = tmp_path / "runs" / "r6-g3-interrupted"
    run_root.mkdir(parents=True)
    supervisor._write_json(
        tmp_path / "current.json",
        {
            "schema_version": "r6-g3-supervisor-current-v1",
            "run_id": run_root.name,
            "run_root": str(run_root),
            "job_label": supervisor.JOB_LABEL,
        },
    )
    supervisor._write_json(
        run_root / "status.json",
        {
            "schema_version": supervisor.STATUS_SCHEMA,
            "run_id": run_root.name,
            "status": "RUNNING",
            "worker_pid": 1978,
        },
    )

    result = supervisor.current_status()

    assert result["effective_status"] == "INTERRUPTED"
    assert result["status"]["status"] == "RUNNING"
    assert result["launchd_loaded"] is False
