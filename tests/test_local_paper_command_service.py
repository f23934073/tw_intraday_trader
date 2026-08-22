"""Journal-first route facade tests for local-paper simulation only."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_data.provider import MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService, SimulationValidationError
from trading.journal import JournalSession


_TAIPEI = ZoneInfo("Asia/Taipei")
_NOW = datetime(2026, 8, 19, 9, 30, tzinfo=_TAIPEI)
_SESSION_ID = "local-paper-test-session"


class FixedClock:
    def now(self) -> datetime:
        return _NOW

    def session_date(self) -> date:
        return _NOW.date()


def command_service(*, starting_cash: Decimal = Decimal("300000")):
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=_SESSION_ID,
            started_at=_NOW,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    simulation = SimulationService(MockProvider(), starting_cash=starting_cash)
    return (
        LocalPaperCommandService(
            simulation=simulation,
            journal=journal,
            session_id=_SESSION_ID,
            clock=FixedClock(),
        ),
        simulation,
        journal,
    )


def test_submit_uses_journal_risk_gate_and_records_local_fill_once():
    service, simulation, journal = command_service()

    first, idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="journaled-buy",
    )
    repeated, repeated_idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="journaled-buy",
    )

    assert idempotent is False
    assert first["status"] == "FILLED"
    assert repeated_idempotent is True
    assert repeated["order_id"] == first["order_id"]
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]
    assert simulation.positions()[0]["quantity"] == 1_000


@pytest.mark.parametrize("quantity_shares", [1, 125, 999, 1_000, 1_500])
def test_submit_accepts_exact_share_quantity(quantity_shares: int) -> None:
    service, simulation, journal = command_service()

    order, idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=quantity_shares,
        limit_price="106",
        idempotency_key=f"journaled-{quantity_shares}-share-buy",
    )

    assert idempotent is False
    assert order["status"] == "FILLED"
    assert order["quantity_shares"] == quantity_shares
    assert order["quantity"] == quantity_shares
    assert order["filled_quantity"] == quantity_shares
    assert simulation.positions()[0]["quantity"] == quantity_shares
    command = journal.records(_SESSION_ID)[0].record
    assert command.kind == "order_command.v1"
    assert command.payload["quantity_shares"] == quantity_shares


def test_odd_lot_risk_rejection_preserves_exact_share_quantity() -> None:
    service, _, _ = command_service(starting_cash=Decimal("100"))

    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=125,
        limit_price="106",
        idempotency_key="rejected-odd-lot-buy",
    )

    assert order["status"] == "REJECTED"
    assert order["quantity_shares"] == 125
    assert order["quantity"] == 125


def test_submit_rejects_ambiguous_share_and_legacy_lot_quantity() -> None:
    service, _, _ = command_service()

    with pytest.raises(SimulationValidationError, match="不可同時提供"):
        service.submit_order(
            symbol="3231",
            side="BUY",
            quantity_shares=125,
            lots=1,
            limit_price="106",
            idempotency_key="ambiguous-quantity-buy",
        )


def test_facade_rejects_reserved_cash_overcommit_and_journals_cancellation():
    service, simulation, journal = command_service(starting_cash=Decimal("150000"))
    first, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="facade-reserved-buy-1",
    )
    second, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="facade-reserved-buy-2",
    )

    assert first["status"] == "PENDING"
    assert second["status"] == "REJECTED"
    assert "INSUFFICIENT_CASH" in second["reason"]
    assert simulation.session()["reserved_cash"] == 100_000.0

    cancelled, cancelled_idempotent = service.cancel_order(
        first["order_id"],
        "facade-cancel-reserved-buy",
    )

    assert cancelled_idempotent is False
    assert cancelled["status"] == "CANCELLED"
    assert simulation.session()["available_cash"] == 150_000.0
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        "order_command.v1",
        "local_paper_order_state.v1",
        "order_command.v1",
        "local_paper_order_state.v1",
        "local_paper_rejection.v1",
        "local_paper_cancel_command.v1",
        "local_paper_order_state.v1",
        "local_paper_cancellation.v1",
    ]
