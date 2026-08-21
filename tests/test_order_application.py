from datetime import datetime
from decimal import Decimal

from trading.application import (
    ApplicationStatus,
    OrderApplicationService,
)
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.local_paper import (
    LocalPaperFillOutcomeRecorder,
    rebuild_local_paper_projection,
)
from trading.recovery import CommandRecoveryStatus, classify_command_recovery
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)
from market_data.provider import MockProvider
from simulation.application_adapter import LocalPaperSimulationCommandAdapter
from simulation.service import SimulationService


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
SESSION_ID = "application-test-20260818"


class RecordingHandler:
    def __init__(self, journal: InMemoryJournalRepository, *, fail: bool = False) -> None:
        self._journal = journal
        self._fail = fail
        self.calls: list[OrderCommand] = []
        self.record_count_at_call: int | None = None

    def submit(self, command: OrderCommand) -> dict[str, object]:
        self.calls.append(command)
        self.record_count_at_call = len(self._journal.records(SESSION_ID))
        if self._fail:
            raise RuntimeError("simulated handler error")
        return {"order_id": "paper-order-1", "status": "SUBMITTED"}


class FailingOutcomeRecorder:
    def records_for(
        self,
        command: OrderCommand,
        handler_result: dict[str, object],
    ) -> tuple[object, ...]:
        raise RuntimeError("simulated outcome recording error")


def command(*, origin: CommandOrigin = CommandOrigin.MANUAL_WEB) -> OrderCommand:
    return OrderCommand(
        command_id="command-1",
        session_id=SESSION_ID,
        origin=origin,
        symbol="2330",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("100"),
        idempotency_key="browser-1",
        requested_at=AT,
        strategy_id=("test-strategy" if origin is CommandOrigin.STRATEGY_AUTOMATED else None),
        strategy_version=("v1" if origin is CommandOrigin.STRATEGY_AUTOMATED else None),
    )


def snapshot(*, health: str = "HEALTHY") -> RiskSnapshot:
    return RiskSnapshot(
        data_health_state=health,
        market_open=True,
        instrument_tradable=True,
        available_cash=Decimal("300000"),
        current_position_shares=0,
        pending_buy_shares=0,
        pending_sell_shares=0,
        daily_realized_pnl=Decimal("0"),
    )


def service(*, fail_handler: bool = False) -> tuple[OrderApplicationService, InMemoryJournalRepository, RecordingHandler]:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER",
            metadata={},
        )
    )
    handler = RecordingHandler(journal, fail=fail_handler)
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=False,
                max_order_notional=Decimal("200000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("50000"),
            )
        ),
        handler=handler,
    )
    return application, journal, handler


def test_approved_command_is_journaled_before_handler_side_effect() -> None:
    application, journal, handler = service()

    result = application.apply(command(), snapshot(), evaluated_at=AT)

    assert result.status is ApplicationStatus.APPLIED
    assert handler.record_count_at_call == 1
    assert len(handler.calls) == 1
    assert journal.records(SESSION_ID)[0].record.kind == "order_command.v1"


def test_command_journal_evidence_preserves_complete_risk_snapshot() -> None:
    application, journal, _ = service()
    risk_snapshot = RiskSnapshot(
        data_health_state="HEALTHY",
        market_open=True,
        instrument_tradable=True,
        available_cash=Decimal("123456.78"),
        current_position_shares=1000,
        pending_buy_shares=2000,
        pending_sell_shares=500,
        daily_realized_pnl=Decimal("-12.34"),
        same_side_pending_order=False,
        book_age_seconds=7,
    )

    application.apply(command(), risk_snapshot, evaluated_at=AT)

    payload = journal.records(SESSION_ID)[0].record.payload["risk_snapshot"]
    assert payload == {
        "data_health_state": "HEALTHY",
        "market_open": True,
        "instrument_tradable": True,
        "available_cash": "123456.78",
        "current_position_shares": 1000,
        "pending_buy_shares": 2000,
        "pending_sell_shares": 500,
        "daily_realized_pnl": "-12.34",
        "same_side_pending_order": False,
        "book_age_seconds": 7,
    }


def test_blocked_command_is_journaled_but_never_reaches_handler() -> None:
    application, journal, handler = service()

    result = application.apply(
        command(origin=CommandOrigin.STRATEGY_AUTOMATED),
        snapshot(health="BLOCKED"),
        evaluated_at=AT,
    )

    assert result.status is ApplicationStatus.BLOCKED
    assert handler.calls == []
    assert journal.records(SESSION_ID)[0].record.payload["risk_status"] == "BLOCKED"


def test_ambiguous_retry_fails_closed_without_second_handler_call() -> None:
    application, journal, handler = service()
    first = application.apply(command(), snapshot(), evaluated_at=AT)
    retry = application.apply(command(), snapshot(), evaluated_at=AT)

    assert first.status is ApplicationStatus.APPLIED
    assert retry.status is ApplicationStatus.RECOVERY_REQUIRED
    assert len(handler.calls) == 1
    assert len(journal.records(SESSION_ID)) == 1


def test_handler_failure_has_append_only_evidence() -> None:
    application, journal, handler = service(fail_handler=True)

    result = application.apply(command(), snapshot(), evaluated_at=AT)

    assert result.status is ApplicationStatus.HANDLER_FAILED
    assert len(handler.calls) == 1
    assert [item.record.kind for item in journal.records(SESSION_ID)] == [
        "order_command.v1",
        "order_handler_failure.v1",
    ]


def test_outcome_recording_failure_requires_recovery_without_retrying_handler() -> None:
    application, journal, handler = service()
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=False,
                max_order_notional=Decimal("200000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("50000"),
            )
        ),
        handler=handler,
        outcome_recorder=FailingOutcomeRecorder(),
    )

    result = application.apply(command(), snapshot(), evaluated_at=AT)

    assert result.status is ApplicationStatus.RECOVERY_REQUIRED
    assert len(handler.calls) == 1
    assert [item.record.kind for item in journal.records(SESSION_ID)] == [
        "order_command.v1",
    ]


def test_approved_command_can_use_legacy_local_paper_only_through_adapter() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER",
            metadata={},
        )
    )
    simulation = SimulationService(MockProvider(), starting_cash=300_000)
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=False,
                max_order_notional=Decimal("200000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("50000"),
            )
        ),
        handler=LocalPaperSimulationCommandAdapter(simulation),
        outcome_recorder=LocalPaperFillOutcomeRecorder(),
    )

    local_paper_command = OrderCommand(
        command_id="command-local-paper-1",
        session_id=SESSION_ID,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("106"),
        idempotency_key="browser-local-paper-1",
        requested_at=AT,
    )
    result = application.apply(local_paper_command, snapshot(), evaluated_at=AT)

    assert result.status is ApplicationStatus.APPLIED
    assert result.handler_result["status"] == "FILLED"
    assert result.outcome_journal_sequences == (2, 3)
    assert simulation.positions()[0]["quantity"] == 1000
    assert [item.record.kind for item in journal.records(SESSION_ID)] == [
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]
    assert journal.records(SESSION_ID)[1].record.payload["command_id"] == (
        "command-local-paper-1"
    )

    rebuilt = rebuild_local_paper_projection(
        journal,
        session_id=SESSION_ID,
        starting_cash=Decimal("300000"),
        require_checkpoint=False,
    )
    assert rebuilt.cash == Decimal(str(simulation.session()["available_cash"]))
    assert rebuilt.position("3231").quantity_shares == 1000
    assert classify_command_recovery(
        journal,
        session_id=SESSION_ID,
        command_id="command-local-paper-1",
    ).status is CommandRecoveryStatus.FILLED
