from datetime import datetime
from decimal import Decimal

import pytest

from trading.journal import (
    InMemoryJournalRepository,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.local_paper import (
    LOCAL_PAPER_CANCEL_COMMAND_KIND,
    LOCAL_PAPER_FILL_KIND,
    LOCAL_PAPER_FILL_V2_KIND,
    LOCAL_PAPER_PROJECTION_NAME,
    LocalPaperFill,
    LocalPaperProjection,
    ProjectionRecoveryError,
    journal_record_from_simulation_order,
    rebuild_local_paper_projection,
    write_local_paper_checkpoint,
)
from market_data.provider import MockProvider
from simulation.service import SimulationService


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
SESSION_ID = "local-paper-recovery-20260818"


def fill_record(
    record_id: str,
    *,
    side: str,
    price: str,
    quantity: int = 100,
) -> JournalRecord:
    return JournalRecord(
        record_id=record_id,
        session_id=SESSION_ID,
        kind=LOCAL_PAPER_FILL_KIND,
        occurred_at=AT,
        payload={
            "order_id": record_id,
            "symbol": "2330",
            "name": "台積電",
            "side": side,
            "quantity_shares": quantity,
            "fill_price": price,
        },
    )


def journal() -> InMemoryJournalRepository:
    repository = InMemoryJournalRepository()
    repository.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER",
            metadata={"starting_cash": "10000"},
        )
    )
    return repository


def test_recovery_rebuilds_decimal_cash_positions_and_realized_pnl() -> None:
    repository = journal()
    buy = repository.append(fill_record("buy-1", side="BUY", price="10"))
    sell = repository.append(fill_record("sell-1", side="SELL", price="12"))
    completed = LocalPaperProjection(starting_cash=Decimal("10000"))
    completed.apply(buy)
    completed.apply(sell)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=sell.sequence,
            digest=completed.digest,
        )
    )

    restored = rebuild_local_paper_projection(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000"),
    )

    assert restored.cash == Decimal("10200")
    assert restored.position("2330") is None
    assert restored.realized_pnl("2330") == Decimal("200")
    assert restored.last_sequence == 2


def test_recovery_rejects_uncheckpointed_local_paper_tail() -> None:
    repository = journal()
    buy = repository.append(fill_record("buy-1", side="BUY", price="10"))
    checkpointed = LocalPaperProjection(starting_cash=Decimal("10000"))
    checkpointed.apply(buy)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=buy.sequence,
            digest=checkpointed.digest,
        )
    )
    repository.append(fill_record("sell-1", side="SELL", price="12"))

    with pytest.raises(ProjectionRecoveryError, match="does not cover Journal tail"):
        rebuild_local_paper_projection(
            repository,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000"),
        )


def test_recovery_rejects_unresolved_cancel_intent_after_checkpoint() -> None:
    repository = journal()
    buy = repository.append(fill_record("buy-1", side="BUY", price="10"))
    checkpointed = LocalPaperProjection(starting_cash=Decimal("10000"))
    checkpointed.apply(buy)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=buy.sequence,
            digest=checkpointed.digest,
        )
    )
    repository.append(
        JournalRecord(
            record_id="cancel-command:pending-1",
            session_id=SESSION_ID,
            kind=LOCAL_PAPER_CANCEL_COMMAND_KIND,
            occurred_at=AT,
            payload={
                "order_id": "pending-1",
                "idempotency_key": "cancel-pending-1",
            },
        )
    )

    with pytest.raises(ProjectionRecoveryError, match="does not cover Journal tail"):
        rebuild_local_paper_projection(
            repository,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000"),
        )


def test_legacy_v2_ignores_tax_field_and_preserves_original_monetary_truth() -> None:
    record = JournalRecord(
        record_id="legacy-v2-extra-tax",
        session_id=SESSION_ID,
        kind=LOCAL_PAPER_FILL_V2_KIND,
        occurred_at=AT,
        payload={
            "order_id": "legacy-v2-extra-tax",
            "symbol": "2330",
            "name": "台積電",
            "side": "SELL",
            "quantity_shares": 100,
            "fill_price": "12",
            "commission": "1",
            "tax": "99",
            "gross_notional": "1200",
            "net_cash_effect": "1199",
            "cumulative_order_commission": "1",
            "settings_digest": "a" * 64,
        },
    )

    fill = LocalPaperFill.from_record(record)

    assert fill.tax == Decimal("0")
    assert fill.cash_effect == Decimal("1199")


def test_recovery_ignores_unrelated_records_but_tracks_global_sequence() -> None:
    repository = journal()
    repository.append(
        JournalRecord(
            record_id="market-1",
            session_id=SESSION_ID,
            kind="market_event.v1",
            occurred_at=AT,
            payload={"symbol": "2330"},
        )
    )
    fill = repository.append(fill_record("buy-1", side="BUY", price="10"))
    projection = LocalPaperProjection(starting_cash=Decimal("10000"))
    for result in repository.records(SESSION_ID):
        projection.apply(result)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=fill.sequence,
            digest=projection.digest,
        )
    )

    restored = rebuild_local_paper_projection(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000"),
    )

    assert restored.last_sequence == fill.sequence
    assert restored.position("2330").quantity_shares == 100


def test_recovery_allows_checkpoint_independent_strategy_record_tail() -> None:
    repository = journal()
    fill = repository.append(fill_record("buy-1", side="BUY", price="10"))
    checkpointed = LocalPaperProjection(starting_cash=Decimal("10000"))
    checkpointed.apply(fill)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=fill.sequence,
            digest=checkpointed.digest,
        )
    )
    strategy_record = repository.append(
        JournalRecord(
            record_id="strategy-checkpoint-1",
            session_id=SESSION_ID,
            kind="strategy_runtime_checkpoint.v1",
            occurred_at=AT,
            payload={"owner_strategy_id": "strategy-1"},
        )
    )

    restored = rebuild_local_paper_projection(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000"),
    )

    assert restored.cash == Decimal("9000")
    assert restored.last_sequence == strategy_record.sequence


def test_recovery_fails_closed_for_missing_or_corrupted_checkpoint() -> None:
    repository = journal()
    record = repository.append(fill_record("buy-1", side="BUY", price="10"))

    with pytest.raises(ProjectionRecoveryError, match="requires a checkpoint"):
        rebuild_local_paper_projection(
            repository,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000"),
        )

    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=record.sequence,
            digest="corrupted",
        )
    )
    with pytest.raises(ProjectionRecoveryError, match="digest mismatch"):
        rebuild_local_paper_projection(
            repository,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000"),
        )


def test_checkpoint_writer_replays_all_records_and_enables_default_recovery() -> None:
    repository = journal()
    repository.append(
        JournalRecord(
            record_id="command-1",
            session_id=SESSION_ID,
            kind="order_command.v1",
            occurred_at=AT,
            payload={"command_id": "command-1"},
        )
    )
    repository.append(fill_record("buy-1", side="BUY", price="10"))

    written = write_local_paper_checkpoint(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000"),
    )
    checkpoint = repository.latest_checkpoint(
        SESSION_ID,
        LOCAL_PAPER_PROJECTION_NAME,
    )
    restored = rebuild_local_paper_projection(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000"),
    )

    assert checkpoint is not None
    assert checkpoint.journal_sequence == 2
    assert checkpoint.digest == written.digest
    assert restored.digest == written.digest


def test_filled_legacy_simulation_payload_has_observation_only_journal_parity() -> None:
    service = SimulationService(MockProvider(), starting_cash=Decimal("300000"))
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="journal-parity-buy",
    )
    repository = journal()
    converted = journal_record_from_simulation_order(order, session_id=SESSION_ID)

    assert converted is not None
    result = repository.append(converted)
    projection = LocalPaperProjection(starting_cash=Decimal("300000"))
    projection.apply(result)
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=result.sequence,
            digest=projection.digest,
        )
    )
    restored = rebuild_local_paper_projection(
        repository,
        session_id=SESSION_ID,
        starting_cash=Decimal("300000"),
    )

    assert restored.cash == Decimal(str(service.session()["available_cash"]))
    position = service.positions()[0]
    restored_position = restored.position("3231")
    assert restored_position is not None
    assert restored_position.quantity_shares == position["quantity"]
    assert restored_position.average_price == Decimal(str(position["average_price"]))


def test_non_filled_legacy_simulation_payload_is_not_journaled() -> None:
    service = SimulationService(MockProvider())
    submitted, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=100.0,
        idempotency_key="journal-parity-pending",
    )

    assert journal_record_from_simulation_order(submitted, session_id=SESSION_ID) is None


def test_settings_bound_zero_fee_fill_writes_complete_v2_evidence() -> None:
    service = SimulationService(MockProvider(), starting_cash=Decimal("300000"))
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106,
        idempotency_key="settings-bound-v2-zero-fee",
    )
    settings_digest = "a" * 64

    record = journal_record_from_simulation_order(
        order,
        session_id=SESSION_ID,
        settings_digest=settings_digest,
    )

    assert record is not None
    assert record.kind == "local_paper_fill.v2"
    assert record.payload["gross_notional"] == "105500"
    assert record.payload["commission"] == "0"
    assert record.payload["net_cash_effect"] == "-105500"
    assert record.payload["cumulative_order_commission"] == "0"
    assert record.payload["settings_digest"] == settings_digest

    result = journal().append(record)
    projection = LocalPaperProjection(
        starting_cash=Decimal("300000"),
        settings_digest="b" * 64,
    )
    with pytest.raises(
        ProjectionRecoveryError,
        match="settings digest conflicts with session",
    ):
        projection.apply(result)


def test_settings_bound_fee_fill_writes_net_and_cumulative_commission() -> None:
    service = SimulationService(
        MockProvider(),
        starting_cash=Decimal("300000"),
        commission_rate=Decimal("0.001425"),
        minimum_commission=Decimal("20"),
    )
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106,
        idempotency_key="settings-bound-v2-fee",
    )

    record = journal_record_from_simulation_order(
        order,
        session_id=SESSION_ID,
        settings_digest="c" * 64,
    )

    assert record is not None
    assert record.kind == "local_paper_fill.v2"
    assert record.payload["gross_notional"] == "105500"
    assert record.payload["commission"] == "150.34"
    assert record.payload["net_cash_effect"] == "-105650.34"
    assert record.payload["cumulative_order_commission"] == "150.34"
