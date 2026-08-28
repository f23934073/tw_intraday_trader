from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts import run_one_shot_late_delivery_open as runner


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 28, hour, minute, tzinfo=runner.TAIPEI)


def test_runs_exact_command_once_and_preserves_terminal_output(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["cwd"] == runner.PROJECT_ROOT
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(argv, 2, "exact_replay: FAILED\n", "provider error\n")

    assert runner.run_one_shot(now=at(8, 55), state_root=tmp_path, run=fake_run) == 2
    assert runner.run_one_shot(now=at(8, 56), state_root=tmp_path, run=fake_run) == 0
    assert calls == [runner.CAPTURE_COMMAND]

    claim = json.loads((tmp_path / f"{runner.RUN_ID}_claim.json").read_text())
    result = json.loads((tmp_path / f"{runner.RUN_ID}_result.json").read_text())
    assert claim["command"] == list(runner.CAPTURE_COMMAND)
    assert claim["safety"] == {
        "foundation_flags": "MUST_REMAIN_OFF",
        "subscribe_trade": False,
        "order_path": "NOT_WIRED",
        "retry": "PROHIBITED",
    }
    assert result["status"] == "COMMAND_COMPLETED"
    assert result["exit_code"] == 2
    assert result["stdout"] == "exact_replay: FAILED\n"
    assert result["stderr"] == "provider error\n"


@pytest.mark.parametrize("ambient_home", [None, "/intentionally/wrong/home"])
def test_child_home_comes_from_os_user_without_mutating_parent_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambient_home: str | None,
) -> None:
    if ambient_home is None:
        monkeypatch.delenv("HOME", raising=False)
    else:
        monkeypatch.setenv("HOME", ambient_home)
    monkeypatch.setenv("D_HEALTH_ENV_SENTINEL", "preserved")
    monkeypatch.setenv("FAKE_CREDENTIAL_LIKE_KEY", "preserved-for-env-copy-test")
    parent_env = os.environ.copy()
    expected_child_env = {
        **parent_env,
        "HOME": runner.pwd.getpwuid(runner.os.getuid()).pw_dir,
    }

    def fake_run(
        argv: tuple[str, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        assert kwargs["env"] == expected_child_env
        return subprocess.CompletedProcess(argv, 0, "", "")

    assert runner.run_one_shot(now=at(8, 55), state_root=tmp_path, run=fake_run) == 0
    assert os.environ.copy() == parent_env
    assert os.environ.get("HOME") == ambient_home
    assert os.environ["D_HEALTH_ENV_SENTINEL"] == "preserved"
    assert os.environ["FAKE_CREDENTIAL_LIKE_KEY"] == "preserved-for-env-copy-test"


def test_passwd_lookup_failure_does_not_run_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fail_lookup(_uid: int) -> object:
        raise KeyError("passwd entry unavailable")

    def unexpected_run(
        argv: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        raise AssertionError("provider command must not run")

    monkeypatch.setattr(runner.pwd, "getpwuid", fail_lookup)

    with pytest.raises(KeyError, match="passwd entry unavailable"):
        runner.run_one_shot(now=at(8, 55), state_root=tmp_path, run=unexpected_run)
    assert calls == []


@pytest.mark.parametrize("observed_at", [at(8, 49), at(9, 0), at(9, 15)])
def test_off_window_claims_without_running_provider(
    tmp_path: Path, observed_at: datetime
) -> None:
    def unexpected_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("provider command must not run")

    assert runner.run_one_shot(
        now=observed_at,
        state_root=tmp_path,
        run=unexpected_run,
    ) == 2
    result = json.loads((tmp_path / f"{runner.RUN_ID}_result.json").read_text())
    assert result["status"] == "NOT_RUN"
    assert result["reason"] == "OUTSIDE_FULL_OPEN_COLLECTION_START_WINDOW"


def test_wrong_date_claims_without_running_provider(tmp_path: Path) -> None:
    def unexpected_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("provider command must not run")

    exit_code = runner.run_one_shot(
        now=datetime(2026, 8, 29, 8, 55, tzinfo=runner.TAIPEI),
        state_root=tmp_path,
        run=unexpected_run,
    )
    assert exit_code == 2
    result = json.loads((tmp_path / f"{runner.RUN_ID}_result.json").read_text())
    assert result["reason"] == "NOT_REVIEWED_TARGET_DATE"


def test_existing_claim_with_different_command_fails_closed(tmp_path: Path) -> None:
    claim_path = tmp_path / f"{runner.RUN_ID}_claim.json"
    claim_path.write_text(
        json.dumps(
            {
                "schema_version": runner.CLAIM_SCHEMA,
                "run_id": runner.RUN_ID,
                "command": ["different"],
            }
        )
    )

    with pytest.raises(RuntimeError, match="claim evidence drift"):
        runner.run_one_shot(now=at(8, 55), state_root=tmp_path)
