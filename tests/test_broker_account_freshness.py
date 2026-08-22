import json
from dataclasses import dataclass
from datetime import datetime

import pytest

from market_data.broker_account_freshness import (
    BrokerAccountFreshnessArtifactError,
    BrokerAccountRuntimeConfig,
    BrokerEvidenceOutcome,
    inspect_broker_account_freshness_artifact,
    load_broker_account_runtime_config,
    run_broker_account_freshness_capture,
)


TAIPEI = datetime.fromisoformat("2026-08-24T09:30:00+08:00").tzinfo
assert TAIPEI is not None
NOW = datetime(2026, 8, 24, 9, 30, tzinfo=TAIPEI)


@dataclass
class FakeAccount:
    account_type: str
    account_id: str


@dataclass
class FakePosition:
    code: str
    quantity: int
    date: str


class FakeApi:
    def __init__(self, *, balance_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.balance_error = balance_error
        self.stock_account = FakeAccount("S", "SENSITIVE_ACCOUNT_ID")

    def login(self, **kwargs):
        self.calls.append("login")
        assert kwargs["subscribe_trade"] is False

    def logout(self):
        self.calls.append("logout")

    def list_accounts(self):
        self.calls.append("list_accounts")
        return [self.stock_account]

    def list_positions(self, *, account, timeout):
        self.calls.append("list_positions")
        assert account is self.stock_account
        assert timeout == 123
        return [FakePosition("SECRET_SYMBOL", 99999, "2026-08-24")]

    def list_profit_loss(self, *, account, begin_date, end_date, timeout):
        self.calls.append("list_profit_loss")
        assert account is self.stock_account
        assert (begin_date, end_date) == ("2026-08-24", "2026-08-24")
        assert timeout == 123
        return []

    def account_balance(self, *, account, timeout):
        self.calls.append("account_balance")
        assert account is self.stock_account
        assert timeout == 123
        if self.balance_error is not None:
            raise self.balance_error
        return [FakePosition("CASH", 123456, "2026-08-24")]

    def update_status(self, *args, **kwargs):
        raise AssertionError("update_status must never be called")

    def list_trades(self, *args, **kwargs):
        raise AssertionError("list_trades must never be called")


def config() -> BrokerAccountRuntimeConfig:
    return BrokerAccountRuntimeConfig(
        api_key="api-key",
        secret_key="secret-key",
        simulation=True,
        sdk_version="test",
    )


def test_capture_is_redacted_read_only_and_retains_orders_gap(tmp_path) -> None:
    api = FakeApi()

    artifact = run_broker_account_freshness_capture(
        api_factory=lambda simulation: api,
        config=config(),
        output_directory=tmp_path,
        observed_at=NOW,
        timeout_ms=123,
    )

    raw = artifact.read_text(encoding="utf-8")
    payload = json.loads(raw)
    inspection = inspect_broker_account_freshness_artifact(artifact)

    assert api.calls == [
        "login", "list_accounts", "list_positions", "list_profit_loss", "account_balance", "logout"
    ]
    assert "api-key" not in raw
    assert "secret-key" not in raw
    assert "SENSITIVE_ACCOUNT_ID" not in raw
    assert "SECRET_SYMBOL" not in raw
    assert "99999" not in raw
    assert payload["guardrails"] == {
        "submit_order": False,
        "cancel_order": False,
        "modify_order": False,
        "activate_ca": False,
        "subscribe_trade": False,
        "trade_callback": False,
        "update_status": False,
        "retry": False,
    }
    assert payload["evidence_gaps"] == [{
        "evidence_kind": "ORDERS",
        "source_reference": "shioaji.api.update_status + shioaji.api.list_trades",
        "invoked": False,
        "reason": "REQUIRES_EXCLUDED_UPDATE_STATUS_OR_TRADE_CALLBACK",
        "threshold_supported": False,
    }]
    buying_power = next(item for item in payload["observations"] if item["evidence_kind"] == "BUYING_POWER")
    assert buying_power["outcome"] == BrokerEvidenceOutcome.UNSUPPORTED_FOR_EVIDENCE_KIND
    assert buying_power["error_class"] == "ACCOUNT_BALANCE_NOT_CONFIRMED_AS_BUYING_POWER"
    assert inspection["threshold_candidates"] is None
    assert inspection["review_status"] == "REVIEW_REQUIRED"


def test_capture_records_ca_prohibition_without_raw_provider_message(tmp_path) -> None:
    api = FakeApi(balance_error=RuntimeError("certificate CA required for SENSITIVE_ACCOUNT_ID"))

    artifact = run_broker_account_freshness_capture(
        api_factory=lambda simulation: api,
        config=config(),
        output_directory=tmp_path,
        observed_at=NOW,
        timeout_ms=123,
    )

    raw = artifact.read_text(encoding="utf-8")
    payload = json.loads(raw)
    buying_power = next(item for item in payload["observations"] if item["evidence_kind"] == "BUYING_POWER")
    assert buying_power["outcome"] == BrokerEvidenceOutcome.CA_REQUIRED_BUT_PROHIBITED
    assert buying_power["error_class"] == "CA_REQUIRED_BUT_PROHIBITED"
    assert "SENSITIVE_ACCOUNT_ID" not in raw


def test_runtime_config_reads_accepted_aliases_without_exposing_them() -> None:
    loaded = load_broker_account_runtime_config(
        {
            "SJ_API_KEY": "api-key",
            "SJ_SECRET_KEY": "secret-key",
            "SJ_SIMULATION": "false",
        },
        sdk_version="1.7.2",
    )

    assert loaded.simulation is False
    assert loaded.environment == "shioaji:1.7.2:simulation=false"


def test_inspector_rejects_a_mutated_guardrail(tmp_path) -> None:
    api = FakeApi()
    artifact = run_broker_account_freshness_capture(
        api_factory=lambda simulation: api,
        config=config(),
        output_directory=tmp_path,
        observed_at=NOW,
        timeout_ms=123,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["guardrails"]["update_status"] = True
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BrokerAccountFreshnessArtifactError, match="guardrails"):
        inspect_broker_account_freshness_artifact(artifact)
