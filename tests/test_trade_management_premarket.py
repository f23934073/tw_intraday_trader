from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from runtime.trade_management_premarket import (
    AUTHORITATIVE_EVIDENCE_TABLES,
    EXPECTED_JOURNAL_TABLES,
    DataOnlyProviderPreflight,
    PostgresReadOnlyPreflight,
    PremarketBlocker,
    PremarketReadinessStatus,
    ShadowPremarketManifest,
    ShadowPremarketReadinessEvaluator,
    ShadowRehearsalEvidence,
)
from scripts import preflight_trade_management_shadow as cli


TAIPEI = ZoneInfo("Asia/Taipei")
PREPARED_AT = datetime(2026, 8, 20, 18, tzinfo=TAIPEI)
MARKET_DATE = date(2026, 8, 21)


def manifest(**changes) -> ShadowPremarketManifest:
    values = {
        "prepared_at": PREPARED_AT,
        "market_date": MARKET_DATE,
        "scheduled_open": datetime.combine(MARKET_DATE, time(9), tzinfo=TAIPEI),
        "scheduled_close": datetime.combine(
            MARKET_DATE,
            time(13, 30),
            tzinfo=TAIPEI,
        ),
        "calendar_schema_version": "twse_calendar_2026_v1",
        "calendar_digest": "a" * 64,
        "session_id": "tm-shadow-20260821-2330",
        "symbol": "2330",
        "provider": "shioaji",
        "provider_version": "1.7.2",
        "provider_simulation": True,
        "connection_session_id": "shioaji-20260821-c0",
        "code_identity": "git:" + "b" * 40,
        "migration_versions": (
            "001_journal.sql",
            "002_trading_schema.sql",
        ),
        "strategy_id": "opening_range_breakout",
        "strategy_version": "opening_range_breakout_entry_v1",
        "thesis_version": "orb-breakout-v1",
        "exit_policy_version": "exit-policy-v1",
        "risk_policy_version": "risk-v1",
        "fill_model_version": "shadow-observation-no-fill-v1",
        "validator_version": "trade-management-shadow-validation-v1",
    }
    values.update(changes)
    return ShadowPremarketManifest(**values)


def provider(**changes) -> DataOnlyProviderPreflight:
    values = {
        "credential_keys_present": ("API_KEY", "SECRET"),
        "login_succeeded": True,
        "logout_succeeded": True,
        "subscribe_trade": False,
        "environment_identity": "shioaji:1.7.2:simulation=true",
    }
    values.update(changes)
    return DataOnlyProviderPreflight(**values)


def postgres(**changes) -> PostgresReadOnlyPreflight:
    values = {
        "dsn_configured": True,
        "driver_version": "3.3.4",
        "connected": True,
        "transaction_read_only": True,
        "server_major": 17,
        "table_names": EXPECTED_JOURNAL_TABLES,
        "migration_versions": (
            "001_journal.sql",
            "002_trading_schema.sql",
        ),
        "evidence_row_counts": tuple(
            (table, 0) for table in AUTHORITATIVE_EVIDENCE_TABLES
        ),
    }
    values.update(changes)
    return PostgresReadOnlyPreflight(**values)


def rehearsal(**changes) -> ShadowRehearsalEvidence:
    values = {
        "test_targets": ("a.py", "b.py"),
        "historical_replay_verified": True,
        "operational_composition_verified": True,
        "journal_recovery_verified": True,
        "replay_parity_matched": True,
        "readiness_report_deterministic": True,
    }
    values.update(changes)
    return ShadowRehearsalEvidence(**values)


def test_ready_report_is_deterministic_and_never_qualifies_as_live() -> None:
    evaluator = ShadowPremarketReadinessEvaluator()

    first = evaluator.evaluate(
        manifest(),
        trading_date_reviewed=True,
        provider=provider(),
        postgres=postgres(),
        rehearsal=rehearsal(),
    )
    second = evaluator.evaluate(
        manifest(),
        trading_date_reviewed=True,
        provider=provider(),
        postgres=postgres(),
        rehearsal=rehearsal(),
    )

    assert first == second
    assert first.status is PremarketReadinessStatus.READY_FOR_SESSION
    assert first.blockers == ()
    assert not first.execution_enabled
    assert not first.qualifying_real_session


def test_manifest_binds_all_runtime_versions_and_rejects_authority_upgrade() -> None:
    value = manifest()

    assert value.provider_identity == "shioaji:1.7.2:simulation=true"
    assert value.to_dict()["risk_policy_version"] == "risk-v1"
    assert value.to_dict()["validator_version"] == (
        "trade-management-shadow-validation-v1"
    )
    with pytest.raises(ValueError, match="evidence-only"):
        replace(value, execution_enabled=True)
    with pytest.raises(ValueError, match="cannot qualify"):
        replace(value, qualifying_real_session=True)


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ({"trading_date_reviewed": False}, PremarketBlocker.UNREVIEWED_TRADING_DATE),
        (
            {"provider": provider(subscribe_trade=True)},
            PremarketBlocker.TRADE_SUBSCRIPTION_ENABLED,
        ),
        (
            {"postgres": postgres(transaction_read_only=False)},
            PremarketBlocker.POSTGRES_NOT_READ_ONLY,
        ),
        (
            {
                "postgres": postgres(
                    evidence_row_counts=(
                        ("journal_sessions", 1),
                        ("journal_records", 0),
                        ("projection_checkpoints", 0),
                    )
                )
            },
            PremarketBlocker.POSTGRES_EVIDENCE_NOT_EMPTY,
        ),
        (
            {"rehearsal": rehearsal(replay_parity_matched=False)},
            PremarketBlocker.REHEARSAL_FAILED,
        ),
    ),
)
def test_preflight_failures_are_typed(change, expected) -> None:
    values = {
        "trading_date_reviewed": True,
        "provider": provider(),
        "postgres": postgres(),
        "rehearsal": rehearsal(),
    }
    values.update(change)

    report = ShadowPremarketReadinessEvaluator().evaluate(manifest(), **values)

    assert report.status is PremarketReadinessStatus.BLOCKED
    assert expected in report.blockers


def test_postgres_preflight_digest_never_contains_a_dsn() -> None:
    value = postgres()
    payload = json.dumps(
        {
            "digest": value.digest,
            "driver": value.driver_version,
            "tables": value.table_names,
        }
    )

    assert "postgresql://" not in payload
    assert "password" not in payload.lower()


def test_provider_preflight_contains_native_worker_signal(monkeypatch) -> None:
    monkeypatch.setenv("SHIOAJI_API_KEY", "present")
    monkeypatch.setenv("SHIOAJI_SECRET", "present")
    monkeypatch.setattr(cli, "_loopback_bind_supported", lambda: True)
    monkeypatch.setattr(
        cli,
        "_run_provider_preflight_worker",
        lambda: subprocess.CompletedProcess([], -11, "", "native crash"),
    )

    result = cli._provider_preflight(skip_login=False)

    assert result.error_code == "NATIVE_SIGNAL_11"
    assert not result.passed
    assert not result.login_succeeded
    assert not result.logout_succeeded
    assert not result.subscribe_trade


def test_provider_preflight_decodes_successful_worker(monkeypatch) -> None:
    monkeypatch.setenv("SHIOAJI_API_KEY", "present")
    monkeypatch.setenv("SHIOAJI_SECRET", "present")
    monkeypatch.setattr(cli, "_loopback_bind_supported", lambda: True)
    payload = {
        "credential_keys_present": ["API_KEY", "SECRET"],
        "login_succeeded": True,
        "logout_succeeded": True,
        "subscribe_trade": False,
        "environment_identity": "shioaji:1.7.2:simulation=true",
        "error_code": None,
    }
    monkeypatch.setattr(
        cli,
        "_run_provider_preflight_worker",
        lambda: subprocess.CompletedProcess(
            [],
            0,
            "provider log\n"
            + cli.PROVIDER_WORKER_SENTINEL
            + json.dumps(payload)
            + "\n",
            "",
        ),
    )

    assert cli._provider_preflight(skip_login=False) == provider()


def test_provider_preflight_skips_native_worker_when_loopback_bind_is_denied(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SHIOAJI_API_KEY", "present")
    monkeypatch.setenv("SHIOAJI_SECRET", "present")
    monkeypatch.setattr(cli, "_loopback_bind_supported", lambda: False)

    def unexpected_worker():
        raise AssertionError("native worker must not start")

    monkeypatch.setattr(cli, "_run_provider_preflight_worker", unexpected_worker)

    result = cli._provider_preflight(skip_login=False)

    assert result.error_code == "LOOPBACK_BIND_DENIED"
    assert not result.passed
    assert not result.subscribe_trade


def test_cli_writes_nonqualifying_ready_artifact_without_secret(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(cli, "_provider_preflight", lambda **_: provider())
    monkeypatch.setattr(cli, "_postgres_preflight", lambda _dsn: postgres())
    monkeypatch.setattr(cli, "_rehearsal", lambda **_: rehearsal())
    monkeypatch.setattr(cli, "_git_identity", lambda: "git:" + "b" * 40)
    monkeypatch.setenv("PostgreSQL_DSN", "postgresql://secret@example/db")
    output = tmp_path / "preflight.json"

    result = cli.main(
        [
            "--market-date",
            "2026-08-21",
            "--prepared-at",
            PREPARED_AT.isoformat(),
            "--session-id",
            "tm-shadow-20260821-2330",
            "--connection-session-id",
            "shioaji-20260821-c0",
            "--output",
            str(output),
        ]
    )

    artifact = output.read_text()
    assert result == 0
    assert '"status": "READY_FOR_SESSION"' in artifact
    assert '"qualifying_real_session": false' in artifact
    assert '"production_shadow_gate": "NOT_PASSED"' in artifact
    assert "postgresql://" not in artifact
    assert output.with_suffix(".json.sha256").exists()


def test_premarket_core_has_no_provider_database_order_or_execution_authority() -> None:
    root = Path(__file__).parents[1]
    source = (root / "runtime" / "trade_management_premarket.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported_names.isdisjoint(
        {
            "JournalRepository",
            "PostgresJournalRepository",
            "ShioajiMomentumStream",
            "OrderCommand",
            "RiskGate",
            "TradeThesis",
        }
    )
    assert referenced_names.isdisjoint(
        {"Broker", "Position", "SELL", "SimulationService", "OrderApplicationService"}
    )
