from datetime import date, datetime
from decimal import Decimal

import pytest

from trading.application import (
    ApprovedOrderCommand,
    ApplicationStatus,
    OrderApplicationService,
    order_command_from_record,
)
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)
from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)


AT = datetime.fromisoformat("2026-08-23T09:30:00+08:00")
SESSION_ID = "local-paper-runtime-v2"


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[ApprovedOrderCommand] = []

    def submit(self, command: ApprovedOrderCommand) -> dict[str, object]:
        self.calls.append(command)
        return {"order_id": "paper-v2-1", "status": "SUBMITTED"}


def exposure():
    return build_exposure_identity(
        account_scope_id="local-paper-main-v1",
        policy_family_id="no-overnight-equity-v1",
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity="manual-order:001",
    )


def command(*, side: CommandSide = CommandSide.BUY) -> OrderCommand:
    identity = exposure()
    return OrderCommand(
        command_id="command-v2-1",
        session_id=SESSION_ID,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="2330",
        side=side,
        quantity_shares=1_000,
        limit_price=Decimal("100"),
        idempotency_key="browser-v2-1",
        requested_at=AT,
        exposure=identity,
        position_action=(
            PositionAction.OPEN_LONG
            if side is CommandSide.BUY
            else PositionAction.CLOSE_LONG
        ),
        target_exposure_id=(identity.exposure_id if side is CommandSide.SELL else None),
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )


def snapshot(*, position: int = 0) -> RiskSnapshot:
    return RiskSnapshot(
        data_health_state="HEALTHY",
        market_open=True,
        instrument_tradable=True,
        available_cash=Decimal("300000"),
        current_position_shares=position,
        pending_buy_shares=0,
        pending_sell_shares=0,
        daily_realized_pnl=Decimal("0"),
    )


def test_v2_command_round_trips_strict_exposure_identity_through_journal() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": "local-paper-main-v1",
                "policy_family_id": "no-overnight-equity-v1",
            },
        )
    )
    handler = RecordingHandler()
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=True,
                max_order_notional=Decimal("300000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("100000"),
            )
        ),
        handler=handler,
    )

    result = application.apply(command(), snapshot(), evaluated_at=AT)
    record = journal.records(SESSION_ID)[0].record
    restored = order_command_from_record(record)

    assert result.status is ApplicationStatus.APPLIED
    assert record.kind == "order_command.v2"
    assert record.payload["exposure_identity"]["account_scope_id"] == (
        "local-paper-main-v1"
    )
    assert record.payload["position_action"] == "OPEN_LONG"
    assert restored == command()
    assert handler.calls[0].command.exposure == exposure()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("quantity_shares", True),
        ("symbol", 2330),
        ("limit_price", 100),
        ("limit_price", "NaN"),
    ],
)
def test_v2_command_reader_rejects_noncanonical_json_scalars(
    field_name: str,
    invalid_value: object,
) -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={},
        )
    )
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=True,
                max_order_notional=Decimal("300000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("100000"),
            )
        ),
        handler=RecordingHandler(),
    )
    application.apply(command(), snapshot(), evaluated_at=AT)
    original = journal.records(SESSION_ID)[0].record
    malformed = JournalRecord(
        record_id=f"malformed-{field_name}-{type(invalid_value).__name__}",
        session_id=SESSION_ID,
        kind="order_command.v2",
        occurred_at=AT,
        payload={**original.payload, field_name: invalid_value},
    )

    with pytest.raises(ValueError, match=field_name):
        order_command_from_record(malformed)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_v2_command_reader_requires_complete_known_field_set(mutation: str) -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={},
        )
    )
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=True,
                max_order_notional=Decimal("300000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("100000"),
            )
        ),
        handler=RecordingHandler(),
    )
    application.apply(command(), snapshot(), evaluated_at=AT)
    payload = dict(journal.records(SESSION_ID)[0].record.payload)
    if mutation == "missing":
        del payload["requested_at"]
    else:
        payload["unexpected_field"] = "unexpected"
    malformed = JournalRecord(
        record_id=f"malformed-fields-{mutation}",
        session_id=SESSION_ID,
        kind="order_command.v2",
        occurred_at=AT,
        payload=payload,
    )

    with pytest.raises(ValueError, match="fields mismatch"):
        order_command_from_record(malformed)


def test_v2_close_requires_exact_target_exposure() -> None:
    identity = exposure()

    with pytest.raises(ValueError, match="target_exposure_id"):
        OrderCommand(
            command_id="command-v2-invalid-sell",
            session_id=SESSION_ID,
            origin=CommandOrigin.MANUAL_WEB,
            symbol="2330",
            side=CommandSide.SELL,
            quantity_shares=1_000,
            limit_price=Decimal("100"),
            idempotency_key="browser-v2-invalid-sell",
            requested_at=AT,
            exposure=identity,
            position_action=PositionAction.CLOSE_LONG,
            target_exposure_id="exposure_v1_" + "f" * 64,
            execution_reason_category=ExecutionReasonCategory.STRATEGY,
            execution_reason_code="MANUAL_ORDER",
        )


def test_v2_strategy_owner_must_match_strategy_identity() -> None:
    identity = build_exposure_identity(
        account_scope_id="local-paper-main-v1",
        policy_family_id="no-overnight-equity-v1",
        owner_origin="STRATEGY_AUTOMATED",
        owner_id="different-strategy",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity="strategy-order:001",
    )

    with pytest.raises(ValueError, match="owner_id"):
        OrderCommand(
            command_id="command-v2-strategy",
            session_id=SESSION_ID,
            origin=CommandOrigin.STRATEGY_AUTOMATED,
            symbol="2330",
            side=CommandSide.BUY,
            quantity_shares=1_000,
            limit_price=Decimal("100"),
            idempotency_key="strategy-v2-1",
            requested_at=AT,
            strategy_id="actual-strategy",
            strategy_version="v1",
            exposure=identity,
            position_action=PositionAction.OPEN_LONG,
            execution_reason_category=ExecutionReasonCategory.STRATEGY,
            execution_reason_code="STRATEGY_SIGNAL",
        )
