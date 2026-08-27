"""CLI boundary tests for the explicit daily institutional MVP job."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from institutional_mvp.ports import InstitutionalFlowSnapshot
from institutional_mvp.domain import InstitutionalMvpDailyError
from scripts import run_finmind_institutional_mvp_daily as cli


TAIPEI = ZoneInfo("Asia/Taipei")


class Provider:
    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        wide = json.dumps(
            {
                "status": 200,
                "data": [
                    {
                        "date": source_session.isoformat(),
                        "stock_id": "1101",
                        "Foreign_Investor_buy": 10,
                        "Foreign_Investor_sell": 1,
                        "Investment_Trust_buy": 5,
                        "Investment_Trust_sell": 1,
                        "Dealer_buy": 0,
                        "Dealer_sell": 0,
                        "Dealer_self_buy": 2,
                        "Dealer_self_sell": 0,
                        "Dealer_Hedging_buy": 1,
                        "Dealer_Hedging_sell": 0,
                    }
                ],
            }
        ).encode()
        info = json.dumps(
            {
                "status": 200,
                "data": [
                    {
                        "date": "2026-01-01",
                        "stock_id": "1101",
                        "stock_name": "Company A",
                        "type": "twse",
                    }
                ],
            }
        ).encode()
        return InstitutionalFlowSnapshot(
            provider="FINMIND",
            source_version="FINMIND_API_V4",
            retrieved_at=datetime(2026, 8, 21, 18, 0, tzinfo=TAIPEI),
            wide_payload=wide,
            stock_info_payload=info,
            wide_row_count=1,
            stock_info_row_count=1,
            usage_user_count_before=100,
            usage_request_limit=1000,
            usage_remaining_before=900,
        )


class NotReadyProvider:
    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        wide = json.dumps({"status": 200, "data": []}).encode()
        info = json.dumps(
            {
                "status": 200,
                "data": [
                    {
                        "date": "2026-01-01",
                        "stock_id": "1101",
                        "stock_name": "Company A",
                        "type": "twse",
                    }
                ],
            }
        ).encode()
        return InstitutionalFlowSnapshot(
            provider="FINMIND",
            source_version="FINMIND_API_V4",
            retrieved_at=datetime(2026, 8, 21, 18, 0, tzinfo=TAIPEI),
            wide_payload=wide,
            stock_info_payload=info,
            wide_row_count=0,
            stock_info_row_count=1,
            usage_user_count_before=100,
            usage_request_limit=1000,
            usage_remaining_before=900,
        )


class RejectedProvider:
    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        raise InstitutionalMvpDailyError(
            "PROVIDER_REQUEST_REJECTED", "FinMind request was permanently rejected"
        )


class RetryableProvider:
    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        raise InstitutionalMvpDailyError(
            "PROVIDER_REQUEST_FAILED", "FinMind request may be retried later"
        )


def test_cli_requires_explicit_source_session() -> None:
    with pytest.raises(SystemExit) as captured:
        cli.main([])
    assert captured.value.code == 2


def test_cli_missing_token_fails_without_provider_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FINMIND_API_TOKEN", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)

    assert cli.main(["--source-session", "2026-08-21"]) == 2
    assert "FINMIND_API_TOKEN_MISSING" in capsys.readouterr().err


def test_cli_publishes_with_fake_provider_without_leaking_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "never-print-this-token"
    monkeypatch.setenv("FINMIND_API_TOKEN", secret)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda token, minimum_remaining_after_batch, acquisition_lock_path: Provider(),
    )

    exit_code = cli.main(
        [
            "--source-session",
            "2026-08-21",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert "status=PUBLISHED" in output.out
    assert secret not in output.out
    assert secret not in output.err
    assert len(list(tmp_path.rglob("*.json"))) == 1
    artifact_text = next(tmp_path.rglob("*.json")).read_text(encoding="utf-8")
    assert secret not in artifact_text
    assert "Foreign_Investor_buy" not in artifact_text


def test_cli_source_not_ready_returns_temporary_exit_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "never-print-not-ready-token"
    monkeypatch.setenv("FINMIND_API_TOKEN", secret)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda token, minimum_remaining_after_batch, acquisition_lock_path: NotReadyProvider(),
    )

    exit_code = cli.main(
        [
            "--source-session",
            "2026-08-21",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 75
    assert "code=SOURCE_NOT_READY" in output.out
    assert secret not in output.out
    assert secret not in output.err
    assert list(tmp_path.rglob("*.json")) == []


def test_cli_permanent_provider_rejection_returns_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "secret-token")
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda token, minimum_remaining_after_batch, acquisition_lock_path: RejectedProvider(),
    )

    exit_code = cli.main(
        [
            "--source-session",
            "2026-08-21",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR code=PROVIDER_REQUEST_REJECTED" in output.err
    assert output.out == ""
    assert list(tmp_path.rglob("*.json")) == []


def test_cli_retryable_provider_failure_returns_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "secret-token")
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda token, minimum_remaining_after_batch, acquisition_lock_path: RetryableProvider(),
    )

    exit_code = cli.main(
        [
            "--source-session",
            "2026-08-21",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 75
    assert "WAIT code=PROVIDER_REQUEST_FAILED" in output.out
    assert output.err == ""
    assert list(tmp_path.rglob("*.json")) == []
