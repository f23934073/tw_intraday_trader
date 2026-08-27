"""RuntimeComposition G1 identity anchor and exposure-flow gates."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
    LOCAL_PAPER_V2_SESSION_ID,
)
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition, _settings_metadata
from simulation.settings import LocalPaperSettings
from trading.exposure import HoldingHorizon
from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.local_paper import (
    LOCAL_PAPER_FILL_V4_KIND,
    LOCAL_PAPER_ORDER_STATE_V2_KIND,
    LOCAL_PAPER_V1_IMPORTED_KIND,
    ProjectionRecoveryError,
    latest_local_paper_order_states,
    write_local_paper_checkpoint,
)


AT = datetime.fromisoformat("2026-08-23T09:30:00+08:00")
ACTIVE_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v2-test"
SETTINGS_V2 = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())


def _runtime(journal: InMemoryJournalRepository) -> RuntimeComposition:
    return RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        local_paper_settings=SETTINGS_V2,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
    )


def test_runtime_same_symbol_long_and_intraday_survive_targeted_sell_restart() -> None:
    journal = InMemoryJournalRepository()
    first = _runtime(journal)

    long_buy, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106,
        idempotency_key="runtime-long-buy",
        holding_horizon=HoldingHorizon.LONG_TERM,
    )
    day_buy, _ = first.local_paper_commands.submit_strategy_order(
        intent_id="runtime-day-buy",
        strategy_id="orb",
        strategy_version="orb-v1",
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106,
    )
    day_exposure_id = day_buy["exposure_identity"]["exposure_id"]
    sold, _ = first.local_paper_commands.submit_strategy_order(
        intent_id="runtime-day-sell",
        strategy_id="orb",
        strategy_version="orb-v1",
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=100,
        target_exposure_id=day_exposure_id,
    )

    assert long_buy["exposure_identity"]["holding_horizon"] == "LONG_TERM"
    assert day_buy["exposure_identity"]["holding_horizon"] == "INTRADAY"
    assert sold["target_exposure_id"] == day_exposure_id
    assert [item["exposure_id"] for item in first.simulation_service.exposures()] == [
        long_buy["exposure_identity"]["exposure_id"]
    ]
    first.close()

    restored = _runtime(journal)
    exposures = restored.simulation_service.exposures()
    assert len(exposures) == 1
    assert exposures[0]["holding_horizon"] == "LONG_TERM"
    assert exposures[0]["quantity"] == 1_000
    assert restored.local_paper_commands.session_id == ACTIVE_LOCAL_PAPER_SESSION_ID
    kinds = {
        result.record.kind
        for result in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
    }
    assert LOCAL_PAPER_V1_IMPORTED_KIND in kinds
    assert LOCAL_PAPER_FILL_V4_KIND in kinds
    assert LOCAL_PAPER_ORDER_STATE_V2_KIND in kinds
    restored.close()


def test_runtime_rejects_conflicting_fixed_v2_identity_metadata() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=LOCAL_PAPER_V2_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": "different-scope",
                "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            },
        )
    )

    with pytest.raises(ValueError, match="identity anchor conflicts"):
        _runtime(journal)


def test_v2_risk_rejection_preserves_identity_and_survives_restart() -> None:
    journal = InMemoryJournalRepository()
    first = _runtime(journal)

    rejected, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=100_000,
        limit_price=106,
        idempotency_key="v2-risk-rejected-buy",
        holding_horizon=HoldingHorizon.INTRADAY,
    )
    expected_identity = rejected["exposure_identity"]
    records = [
        item.record
        for item in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
        if item.record.payload.get("idempotency_key")
        == "v2-risk-rejected-buy"
        or item.record.payload.get("order_id") == rejected["order_id"]
    ]

    assert rejected["status"] == "REJECTED"
    assert {record.kind for record in records} == {
        "order_command.v2",
        "local_paper_order_state.v2",
        "local_paper_rejection.v2",
    }
    for record in records:
        assert record.payload["exposure_identity"] == expected_identity
        assert record.payload["position_action"] == "OPEN_LONG"
        assert record.payload["target_exposure_id"] is None
        assert record.payload["execution_reason_code"] == "MANUAL_ORDER"
    first.close()

    restored = _runtime(journal)
    restored_order = restored.simulation_service.orders()[0]
    assert restored_order["status"] == "REJECTED"
    assert restored_order["exposure_identity"] == expected_identity
    assert restored_order["exposure_identity"]["holding_horizon"] == "INTRADAY"
    restored.close()


def test_restart_rejects_v2_order_state_identity_mismatch() -> None:
    journal = InMemoryJournalRepository()
    first = _runtime(journal)
    first_order, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1,
        limit_price=106,
        idempotency_key="state-identity-first",
        holding_horizon=HoldingHorizon.INTRADAY,
    )
    second_order, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1,
        limit_price=106,
        idempotency_key="state-identity-second",
        holding_horizon=HoldingHorizon.LONG_TERM,
    )
    original_state = next(
        item.record
        for item in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
        if item.record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND
        and item.record.payload["order_id"] == first_order["order_id"]
    )
    corrupted_at = original_state.occurred_at + timedelta(seconds=1)
    journal.append(
        JournalRecord(
            record_id="corrupted-v2-order-state-identity",
            session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            kind=LOCAL_PAPER_ORDER_STATE_V2_KIND,
            occurred_at=corrupted_at,
            payload={
                **original_state.payload,
                "updated_at": corrupted_at.isoformat(),
                "exposure_identity": second_order["exposure_identity"],
            },
        )
    )
    first.close()

    with pytest.raises(ProjectionRecoveryError, match="integrity digest"):
        _runtime(journal)


def test_restart_rejects_forged_v2_retry_lineage() -> None:
    journal = InMemoryJournalRepository()
    first = _runtime(journal)
    original, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1,
        limit_price=1,
        idempotency_key="retry-lineage-original",
        holding_horizon=HoldingHorizon.INTRADAY,
    )
    cancelled, _ = first.local_paper_commands.cancel_order(
        original["order_id"],
        "retry-lineage-cancel",
    )
    original_state = next(
        item.record
        for item in reversed(journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID))
        if item.record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND
        and item.record.payload["order_id"] == original["order_id"]
    )
    corrupted_at = original_state.occurred_at + timedelta(seconds=1)
    journal.append(
        JournalRecord(
            record_id="corrupted-v2-order-state-retry-lineage",
            session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            kind=LOCAL_PAPER_ORDER_STATE_V2_KIND,
            occurred_at=corrupted_at,
            payload={
                **original_state.payload,
                "updated_at": corrupted_at.isoformat(),
                "attempt": 2,
                "predecessor_order_id": "forged-predecessor",
            },
        )
    )

    assert cancelled["status"] == "CANCELLED"
    with pytest.raises(ProjectionRecoveryError, match="integrity digest"):
        latest_local_paper_order_states(
            journal,
            session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        )
    first.close()

    with pytest.raises(ProjectionRecoveryError, match="integrity digest"):
        _runtime(journal)


def test_first_v2_import_rejects_unacknowledged_v1_command() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                **_settings_metadata(SETTINGS_V2, revision=0),
                "starting_cash": "10000000",
                "execution_boundary": "LOCAL_ONLY",
                "journal_backend": "INJECTED",
                "restart_policy": "RESUME_CHECKPOINTED_LOCAL_PAPER_SESSION",
            },
        )
    )
    journal.append(
        JournalRecord(
            record_id="unacknowledged-command",
            session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            kind="order_command.v1",
            occurred_at=AT,
            payload={
                "command_id": "unacknowledged-command",
                "idempotency_key": "unacknowledged-key",
                "origin": "MANUAL_WEB",
                "strategy_id": None,
                "strategy_version": None,
                "symbol": "3231",
                "side": "BUY",
                "quantity_shares": 1_000,
                "limit_price": "100",
                "attempt": 1,
                "predecessor_order_id": None,
                "risk_status": "APPROVED",
            },
        )
    )
    write_local_paper_checkpoint(
        journal,
        session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        starting_cash=Decimal("10000000"),
        settings_digest=SETTINGS_V2.digest,
    )

    with pytest.raises(ValueError, match="identity import unsafe"):
        _runtime(journal)

    assert all(
        item.record.kind != LOCAL_PAPER_V1_IMPORTED_KIND
        for item in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
    )
    assert LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id == "local-paper-main-v1"
