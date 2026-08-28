"""CLI gates for institutional candidate-series planning and execution."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from institutional_mvp.ports import InstitutionalFlowSnapshot
from institutional_mvp.series import load_canonical_artifact
from scripts import run_finmind_institutional_mvp_series as cli


TAIPEI = ZoneInfo("Asia/Taipei")


def _reference() -> dict[str, object]:
    return {
        "bar_count": 51_213_436,
        "bars_sha256": "e" * 64,
        "dataset_id": "dataset-finmind-test",
        "end_date": "2026-08-18",
        "issues": ["CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED"],
        "manifest_digest": "d" * 64,
        "observed_symbol_count": 1,
        "payload_order": "TIMESTAMP_SYMBOL",
        "plan_identity_digest": "c" * 64,
        "profile": "KBAR_1M_V1",
        "research_eligible": False,
        "selection_audit_digest": "a" * 64,
        "source": "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        "source_snapshot_digest": "b" * 64,
        "start_date": "2023-08-19",
        "storage_format": "JSONL_FULL_V1",
        "universe_scope": "CURRENT_SNAPSHOT",
        "universe_selection": "FINMIND_COMPLETE_SYMBOLS_V1",
    }


class Provider:
    calls: list[date] = []

    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        self.calls.append(source_session)
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
            },
            separators=(",", ":"),
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
            },
            separators=(",", ":"),
        ).encode()
        return InstitutionalFlowSnapshot(
            provider="FINMIND",
            source_version="FINMIND_API_V4",
            retrieved_at=datetime(2026, 8, 27, 14, 0, tzinfo=TAIPEI),
            wide_payload=wide,
            stock_info_payload=info,
            wide_row_count=1,
            stock_info_row_count=1,
            usage_user_count_before=100,
            usage_request_limit=1000,
            usage_remaining_before=900,
        )


def _patch_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_price_dataset_reference", lambda **kwargs: _reference())


def _publish_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _patch_metadata(monkeypatch)
    assert (
        cli.main(
            [
                "plan",
                "--target-end",
                "2026-08-18",
                "--session-count",
                "60",
                "--output-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    return next((tmp_path / "plans").glob("*.json"))


def test_plan_is_offline_and_does_not_require_token_or_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FINMIND_API_TOKEN", raising=False)
    _patch_metadata(monkeypatch)
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    assert (
        cli.main(
            [
                "plan",
                "--target-end",
                "2026-08-18",
                "--output-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    plan = load_canonical_artifact(next((tmp_path / "plans").glob("*.json")))
    assert plan["planned_session_count"] == 60


def test_execute_publishes_60_batches_and_one_series_then_replays_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _publish_plan(tmp_path, monkeypatch)
    capsys.readouterr()
    secret = "never-print-series-token"
    monkeypatch.setenv("FINMIND_API_TOKEN", secret)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: False)
    Provider.calls = []
    monkeypatch.setattr(
        cli,
        "FinMindInstitutionalFlowProvider",
        lambda token, minimum_remaining_after_batch, acquisition_lock_path: Provider(),
    )

    args = [
        "execute",
        "--plan-file",
        str(plan_path),
        "--output-root",
        str(tmp_path),
    ]
    assert cli.main(args) == 0
    first_output = capsys.readouterr()
    assert len(Provider.calls) == 60
    assert "overlapping_target_sessions=60" in first_output.out
    assert secret not in first_output.out + first_output.err
    assert len(list((tmp_path / "series").glob("*.json"))) == 1
    assert len(list(tmp_path.glob("2026-*/*/*.json"))) == 60

    Provider.calls = []
    assert cli.main(args) == 0
    replay_output = capsys.readouterr()
    assert Provider.calls == []
    assert "status=IDEMPOTENT_REPLAY" in replay_output.out
    assert len(list((tmp_path / "series").glob("*.json"))) == 1
