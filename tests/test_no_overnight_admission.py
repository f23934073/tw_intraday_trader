from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest

from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from trading.application import (
    ApplicationStatus,
    OrderApplicationService,
)
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.no_overnight import NoOvernightState
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionReason,
    ExecutionAdmissionSnapshot,
    ExecutionAdmissionStatus,
    evaluate_execution_admission,
)
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)


AT = datetime.fromisoformat("2026-08-24T13:10:00+08:00")
SESSION_ID = "no-overnight-admission-test"


def _config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.ENFORCING,
        account_scope_id="local-paper-account-v2",
        policy_family_id="no-overnight-local-paper-v1",
        policy_version="enforcing-v1",
        timezone="Asia/Taipei",
        market_open=time(9, 0),
        no_new_entry_at=time(13, 10),
        cancel_entry_at=time(13, 15),
        flatten_at=time(13, 20),
        aggressive_exit_at=time(13, 25),
        final_reconciliation_at=time(13, 28),
        reviewed_session_close=time(13, 30),
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
        executable_book_policy_id="local-paper-book-v1",
    )


def _command(horizon: HoldingHorizon) -> OrderCommand:
    exposure = build_exposure_identity(
        account_scope_id=_config().account_scope_id,
        policy_family_id=_config().policy_family_id,
        owner_origin=CommandOrigin.MANUAL_WEB.value,
        owner_id="manual-web",
        holding_horizon=horizon,
        entry_session_date=AT.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
        entry_identity=f"entry-{horizon.value}",
    )
    return OrderCommand(
        command_id=f"command-{horizon.value}",
        session_id=SESSION_ID,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("106"),
        idempotency_key=f"entry-{horizon.value}",
        requested_at=AT,
        exposure=exposure,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )


def _snapshot(
    *,
    state: NoOvernightState = NoOvernightState.NO_NEW_ENTRY,
    revision: int = 1,
    session_open: bool = True,
    instrument_tradable: bool = True,
    executable_book_ready: bool = True,
    guard_healthy: bool = True,
    recovery_required: bool = False,
) -> ExecutionAdmissionSnapshot:
    return ExecutionAdmissionSnapshot(
        evaluated_at=AT,
        session_date=date(2026, 8, 24),
        state=state,
        state_revision=revision,
        policy_digest=_config().policy_digest,
        calendar_digest="calendar-v1",
        session_open=session_open,
        instrument_tradable=instrument_tradable,
        executable_book_ready=executable_book_ready,
        guard_owned=True,
        guard_healthy=guard_healthy,
        recovery_required=recovery_required,
    )


def test_cutoff_blocks_only_intraday_buy_but_breach_blocks_every_buy() -> None:
    intraday = evaluate_execution_admission(
        command=_command(HoldingHorizon.INTRADAY),
        config=_config(),
        snapshot=_snapshot(),
    )
    long_term = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(),
    )
    breached_long_term = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.OVERNIGHT_BREACH),
    )

    assert intraday.status is ExecutionAdmissionStatus.BLOCKED
    assert intraday.reasons == (ExecutionAdmissionReason.CUTOFF,)
    assert long_term.status is ExecutionAdmissionStatus.APPROVED
    assert breached_long_term.status is ExecutionAdmissionStatus.BLOCKED
    assert breached_long_term.reasons == (ExecutionAdmissionReason.OPEN_BREACH,)


def test_final_server_time_closes_cutoff_race_even_if_controller_revision_lags() -> (
    None
):
    before_cutoff = datetime.fromisoformat("2026-08-24T13:09:59+08:00")
    command = replace(
        _command(HoldingHorizon.INTRADAY),
        requested_at=before_cutoff,
    )
    initial_snapshot = replace(
        _snapshot(state=NoOvernightState.NORMAL),
        evaluated_at=before_cutoff,
    )
    initial = evaluate_execution_admission(
        command=command,
        config=_config(),
        snapshot=initial_snapshot,
    )
    final = evaluate_execution_admission(
        command=command,
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
        expected_revision=initial.admission_revision,
        final_check=True,
    )

    assert initial.status is ExecutionAdmissionStatus.APPROVED
    assert final.status is ExecutionAdmissionStatus.BLOCKED
    assert final.reasons == (ExecutionAdmissionReason.CUTOFF,)


def test_admission_payload_reader_is_strict_and_recomputes_revision() -> None:
    decision = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )
    payload = decision.to_payload()

    assert ExecutionAdmissionDecision.from_payload(payload) == decision

    forged_boolean = {
        **payload,
        "snapshot": {**payload["snapshot"], "guard_healthy": 1},
    }
    with pytest.raises(ValueError, match="boolean"):
        ExecutionAdmissionDecision.from_payload(forged_boolean)

    forged_revision = {
        **payload,
        "snapshot": {
            **payload["snapshot"],
            "state_revision": 2,
        },
    }
    with pytest.raises(ValueError, match="revision conflicts"):
        ExecutionAdmissionDecision.from_payload(forged_revision)


def test_open_breach_provenance_is_strict_and_part_of_admission_revision() -> None:
    prior_breach = replace(
        _snapshot(state=NoOvernightState.NORMAL),
        breach_latched=True,
        breach_session_date=date(2026, 8, 23),
        breach_revision=3,
    )
    same_revision_different_session = replace(
        prior_breach,
        breach_session_date=date(2026, 8, 24),
    )

    assert ExecutionAdmissionSnapshot.from_payload(
        prior_breach.to_payload()
    ) == prior_breach
    assert (
        prior_breach.admission_revision
        != same_revision_different_session.admission_revision
    )
    with pytest.raises(ValueError, match="requires its session and revision"):
        replace(
            prior_breach,
            breach_session_date=None,
        )
    with pytest.raises(ValueError, match="cannot carry a breach fence"):
        replace(
            prior_breach,
            breach_latched=False,
        )


def test_admission_rejects_policy_or_entry_session_identity_conflict() -> None:
    command = _command(HoldingHorizon.LONG_TERM)
    wrong_policy = evaluate_execution_admission(
        command=command,
        config=_config(),
        snapshot=replace(_snapshot(state=NoOvernightState.NORMAL), policy_digest="f" * 64),
    )
    assert command.exposure is not None
    wrong_entry_session = evaluate_execution_admission(
        command=replace(
            command,
            exposure=replace(
                command.exposure,
                entry_session_date=date(2026, 8, 23),
            ),
        ),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )

    assert wrong_policy.status is ExecutionAdmissionStatus.RECOVERY_REQUIRED
    assert wrong_policy.reasons == (ExecutionAdmissionReason.IDENTITY_CONFLICT,)
    assert wrong_entry_session.status is ExecutionAdmissionStatus.RECOVERY_REQUIRED
    assert wrong_entry_session.reasons == (ExecutionAdmissionReason.IDENTITY_CONFLICT,)


def test_guard_loss_and_breach_still_allow_exact_risk_reducing_sell() -> None:
    buy = _command(HoldingHorizon.INTRADAY)
    assert buy.exposure is not None
    sell = replace(
        buy,
        command_id="risk-reducing-sell",
        side=CommandSide.SELL,
        idempotency_key="risk-reducing-sell",
        position_action=PositionAction.CLOSE_LONG,
        target_exposure_id=buy.exposure.exposure_id,
    )
    initial = evaluate_execution_admission(
        command=sell,
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )
    final = evaluate_execution_admission(
        command=sell,
        config=_config(),
        snapshot=_snapshot(
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=2,
            guard_healthy=False,
            recovery_required=True,
        ),
        expected_revision=initial.admission_revision,
        final_check=True,
    )

    assert initial.status is ExecutionAdmissionStatus.APPROVED
    assert final.status is ExecutionAdmissionStatus.APPROVED
    assert final.reasons == ()


def test_no_overnight_exit_cannot_cross_final_reconciliation_deadline() -> None:
    requested_at = datetime.fromisoformat("2026-08-24T13:27:59+08:00")
    evaluated_at = datetime.fromisoformat("2026-08-24T13:28:00+08:00")
    buy = _command(HoldingHorizon.INTRADAY)
    assert buy.exposure is not None
    sell = replace(
        buy,
        command_id="no-overnight-exit",
        requested_at=requested_at,
        side=CommandSide.SELL,
        idempotency_key="no-overnight-exit",
        position_action=PositionAction.CLOSE_LONG,
        target_exposure_id=buy.exposure.exposure_id,
        execution_reason_code="NO_OVERNIGHT_EXIT",
    )
    initial_snapshot = replace(
        _snapshot(state=NoOvernightState.AGGRESSIVE_EXIT, revision=4),
        evaluated_at=requested_at,
    )
    initial = evaluate_execution_admission(
        command=sell,
        config=_config(),
        snapshot=initial_snapshot,
    )
    final = evaluate_execution_admission(
        command=sell,
        config=_config(),
        snapshot=replace(
            initial_snapshot,
            evaluated_at=evaluated_at,
            state=NoOvernightState.FINAL_RECONCILIATION,
            state_revision=5,
        ),
        expected_revision=initial.admission_revision,
        final_check=True,
    )

    assert initial.status is ExecutionAdmissionStatus.APPROVED
    assert final.status is ExecutionAdmissionStatus.BLOCKED
    assert final.reasons == (ExecutionAdmissionReason.EXIT_DEADLINE,)


@pytest.mark.parametrize(
    ("changed", "reason", "status"),
    [
        (
            {"revision": 2},
            ExecutionAdmissionReason.STATE_REVISION_CHANGED,
            ExecutionAdmissionStatus.RECOVERY_REQUIRED,
        ),
        (
            {"session_open": False},
            ExecutionAdmissionReason.SESSION_CLOSED,
            ExecutionAdmissionStatus.BLOCKED,
        ),
        (
            {"instrument_tradable": False},
            ExecutionAdmissionReason.INSTRUMENT_NOT_TRADABLE,
            ExecutionAdmissionStatus.BLOCKED,
        ),
        (
            {"executable_book_ready": False},
            ExecutionAdmissionReason.BOOK_UNAVAILABLE,
            ExecutionAdmissionStatus.BLOCKED,
        ),
        (
            {"guard_healthy": False},
            ExecutionAdmissionReason.GUARD_UNHEALTHY,
            ExecutionAdmissionStatus.RECOVERY_REQUIRED,
        ),
        (
            {"recovery_required": True},
            ExecutionAdmissionReason.RECOVERY_REQUIRED,
            ExecutionAdmissionStatus.RECOVERY_REQUIRED,
        ),
    ],
)
def test_final_admission_fails_closed_on_server_owned_changes(
    changed: dict[str, object],
    reason: ExecutionAdmissionReason,
    status: ExecutionAdmissionStatus,
) -> None:
    initial = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )
    final = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL, **changed),
        expected_revision=initial.admission_revision,
        final_check=True,
    )

    assert final.status is status
    assert reason in final.reasons


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, command: object) -> dict[str, object]:
        self.calls += 1
        return {"status": "FILLED"}


class _BlockingFinalReader:
    def read(
        self,
        command: OrderCommand,
        *,
        expected_revision: str,
    ) -> ExecutionAdmissionDecision:
        return evaluate_execution_admission(
            command=command,
            config=_config(),
            snapshot=_snapshot(
                state=NoOvernightState.NORMAL,
                instrument_tradable=False,
            ),
            expected_revision=expected_revision,
            final_check=True,
        )


class _NonFinalReader:
    def read(
        self,
        command: OrderCommand,
        *,
        expected_revision: str,
    ) -> ExecutionAdmissionDecision:
        return evaluate_execution_admission(
            command=command,
            config=_config(),
            snapshot=_snapshot(state=NoOvernightState.NORMAL),
        )


def test_application_journals_final_block_without_handler_side_effect() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={},
        )
    )
    handler = _RecordingHandler()
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=True,
                max_order_notional=Decimal("200000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("50000"),
            )
        ),
        handler=handler,
        final_admission_reader=_BlockingFinalReader(),
    )
    initial = evaluate_execution_admission(
        command=_command(HoldingHorizon.LONG_TERM),
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )

    result = application.apply(
        _command(HoldingHorizon.LONG_TERM),
        RiskSnapshot(
            data_health_state="HEALTHY",
            market_open=True,
            instrument_tradable=True,
            available_cash=Decimal("300000"),
            current_position_shares=0,
            pending_buy_shares=0,
            pending_sell_shares=0,
            daily_realized_pnl=Decimal("0"),
        ),
        evaluated_at=AT,
        execution_admission=initial,
    )

    assert result.status is ApplicationStatus.BLOCKED
    assert result.execution_admission is not None
    assert result.execution_admission.reasons == (
        ExecutionAdmissionReason.INSTRUMENT_NOT_TRADABLE,
    )
    assert handler.calls == 0
    assert [item.record.kind for item in journal.records(SESSION_ID)] == [
        "order_command.v2",
        "no_overnight_final_admission.v1",
    ]


def test_application_rejects_reader_decision_that_is_not_a_final_check() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={},
        )
    )
    handler = _RecordingHandler()
    application = OrderApplicationService(
        journal=journal,
        risk_gate=RiskGate(
            RiskPolicy(
                version="risk-v1",
                allow_strategy_origin=True,
                max_order_notional=Decimal("200000"),
                max_position_notional=Decimal("300000"),
                max_daily_loss=Decimal("50000"),
            )
        ),
        handler=handler,
        final_admission_reader=_NonFinalReader(),
    )
    command = _command(HoldingHorizon.LONG_TERM)
    initial = evaluate_execution_admission(
        command=command,
        config=_config(),
        snapshot=_snapshot(state=NoOvernightState.NORMAL),
    )

    result = application.apply(
        command,
        RiskSnapshot(
            data_health_state="HEALTHY",
            market_open=True,
            instrument_tradable=True,
            available_cash=Decimal("300000"),
            current_position_shares=0,
            pending_buy_shares=0,
            pending_sell_shares=0,
            daily_realized_pnl=Decimal("0"),
        ),
        evaluated_at=AT,
        execution_admission=initial,
    )

    assert result.status is ApplicationStatus.RECOVERY_REQUIRED
    assert handler.calls == 0
    assert [item.record.kind for item in journal.records(SESSION_ID)] == [
        "order_command.v2",
        "no_overnight_final_admission_failure.v1",
    ]
