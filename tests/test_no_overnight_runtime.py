from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from config import twse_calendar_2026
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
    LOCAL_PAPER_V2_SESSION_ID,
)
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight import (
    ExecutionFactReference,
    LocalPaperNoOvernightEvidenceReader,
    LocalPaperExecutionAdmissionReader,
    NoOvernightEnforcementAction,
    NoOvernightController,
    NoOvernightEvidenceBundle,
    no_overnight_session_id,
)
from simulation.service import SimulationStateError
from simulation.settings import LocalPaperSettings
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)
from trading.journal import JournalRecord
from trading.no_overnight import (
    NoOvernightEvidence,
    NoOvernightState,
    ReconciliationStatus,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionReason,
    ExecutionAdmissionStatus,
)
from trading.no_overnight_journal import (
    NO_OVERNIGHT_RESULT_KIND,
    rebuild_no_overnight_projection,
)
from trading.risk import CommandOrigin, CommandSide, OrderCommand


NOW = datetime.fromisoformat("2026-08-24T13:26:00+08:00")
ACTIVE_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"


def _settings_v2() -> LocalPaperSettings:
    return LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())


def _config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.OBSERVE_ONLY,
        account_scope_id="local-paper-account-v2",
        policy_family_id="no-overnight-local-paper-v1",
        policy_version="observe-policy-v1",
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


def _runtime_config() -> NoOvernightPolicyConfig:
    return replace(
        _config(),
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def session_date(self) -> date:
        return NOW.date()


class StaticEvidenceReader:
    def read(self, *, now: datetime, session_date: date) -> NoOvernightEvidenceBundle:
        evidence = NoOvernightEvidence(
            session_date=session_date,
            managed_exposures=(),
            pending_entry_quantity=(),
            pending_exit_quantity=(),
            unresolved_execution_ids=(),
            reconciliation_status=ReconciliationStatus.MATCH,
            reconciliation_digest="d" * 64,
            last_fill_journal_sequence=0,
            last_execution_fact_journal_sequence=10,
            snapshot_covers_through_journal_sequence=10,
            snapshot_journal_sequence=0,
            snapshot_source_as_of=now,
            snapshot_received_at=now,
        )
        return NoOvernightEvidenceBundle(
            evidence=evidence,
            execution_facts=(
                ExecutionFactReference(
                    10,
                    "local_paper_order_state.v2",
                    "state-10",
                    session_date,
                ),
            ),
        )


class AdvancingEvidenceReader(StaticEvidenceReader):
    def __init__(self) -> None:
        self.calls = 0

    def read(self, *, now: datetime, session_date: date) -> NoOvernightEvidenceBundle:
        self.calls += 1
        base = super().read(now=now, session_date=session_date)
        if self.calls == 1:
            return base
        return NoOvernightEvidenceBundle(
            evidence=replace(
                base.evidence,
                last_execution_fact_journal_sequence=11,
                snapshot_covers_through_journal_sequence=11,
            ),
            execution_facts=(
                *base.execution_facts,
                ExecutionFactReference(
                    11,
                    "local_paper_fill.v2",
                    "late-fill-11",
                    session_date,
                ),
            ),
        )


class EmptyEvidenceReader:
    def read(self, *, now: datetime, session_date: date) -> NoOvernightEvidenceBundle:
        return NoOvernightEvidenceBundle(
            evidence=NoOvernightEvidence(
                session_date=session_date,
                managed_exposures=(),
                pending_entry_quantity=(),
                pending_exit_quantity=(),
                unresolved_execution_ids=(),
                reconciliation_status=ReconciliationStatus.MATCH,
                reconciliation_digest="d" * 64,
                last_fill_journal_sequence=0,
                last_execution_fact_journal_sequence=0,
                snapshot_covers_through_journal_sequence=0,
                snapshot_journal_sequence=0,
                snapshot_source_as_of=now,
                snapshot_received_at=now,
            ),
            execution_facts=(),
        )


class AdvancingPriorSessionEvidenceReader(EmptyEvidenceReader):
    def __init__(self) -> None:
        self.calls = 0

    def read(self, *, now: datetime, session_date: date) -> NoOvernightEvidenceBundle:
        self.calls += 1
        base = super().read(now=now, session_date=session_date)
        if self.calls == 1:
            return base
        return replace(
            base,
            prior_session_execution_facts=(
                ExecutionFactReference(
                    5,
                    "local_paper_fill.v2",
                    "prior-session-fill-5",
                    session_date - timedelta(days=1),
                ),
            ),
        )


class CountingCommandPort:
    def __init__(self) -> None:
        self.calls = 0
        self.actions: list[object] = []

    def execute(self, action: object) -> bool:
        self.calls += 1
        self.actions.append(action)
        return False


class HealthyGuard:
    guard_identity = "test-postgres-guard"

    def __init__(self, health: tuple[bool, ...] = (True,)) -> None:
        self._health = list(health)

    def is_owned_and_healthy(self) -> bool:
        if len(self._health) > 1:
            return self._health.pop(0)
        return self._health[0]

    def execute_if_owned(self, operation):
        if not self.is_owned_and_healthy():
            raise ValueError("no-overnight guard ownership was lost")
        return operation()


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class ReadyExecutionContext:
    max_book_age_seconds = 15

    def execution_admission_context(
        self,
        symbol: str,
        side: str,
        *,
        max_book_age_seconds: int,
    ) -> dict[str, object]:
        assert symbol == "3231"
        assert side == "BUY"
        assert max_book_age_seconds == 15
        return {
            "instrument_tradable": True,
            "executable_book_ready": True,
            "data_health_state": "HEALTHY",
            "book_age_seconds": 0,
        }

    def exposures(self) -> list[dict[str, object]]:
        return []

    def orders(self) -> list[dict[str, object]]:
        return []


class CrashBeforeFirstResultJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self._crash_before_result = True

    def append(self, record: JournalRecord):
        if self._crash_before_result and record.kind == NO_OVERNIGHT_RESULT_KIND:
            self._crash_before_result = False
            raise RuntimeError("simulated crash before terminal result append")
        return super().append(record)


def test_observe_only_records_would_actions_and_never_calls_handler() -> None:
    command_port = CountingCommandPort()
    controller = NoOvernightController(
        config=_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=InMemoryJournalRepository(),
        evidence_reader=StaticEvidenceReader(),
        command_port=command_port,
    )

    status = controller.run_once(NOW)

    assert status["mode"] == "OBSERVE_ONLY"
    assert status["enforcing"] is False
    assert status["state"] == "AGGRESSIVE_EXIT"
    assert status["would_actions"] == ["WOULD_BLOCK_ENTRY", "WOULD_EXIT"]
    assert command_port.calls == 0


def test_controller_fails_closed_on_holiday_and_calendar_out_of_range() -> None:
    controller = NoOvernightController(
        config=_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=InMemoryJournalRepository(),
        evidence_reader=StaticEvidenceReader(),
    )

    with pytest.raises(ValueError, match="reviewed trading day"):
        controller.run_once(datetime.fromisoformat("2026-08-23T13:26:00+08:00"))

    with pytest.raises(ValueError, match="reviewed coverage"):
        controller.run_once(datetime.fromisoformat("2027-01-04T13:26:00+08:00"))


def test_controller_retries_snapshot_when_execution_fact_advances() -> None:
    reader = AdvancingEvidenceReader()
    controller = NoOvernightController(
        config=_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=InMemoryJournalRepository(),
        evidence_reader=reader,
    )

    status = controller.run_once(NOW)

    assert reader.calls == 4
    assert status["last_execution_fact_journal_sequence"] == 11
    assert status["snapshot_covers_through_journal_sequence"] == 11


def test_same_phase_observation_does_not_churn_state_revision() -> None:
    controller = NoOvernightController(
        config=_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=InMemoryJournalRepository(),
        evidence_reader=StaticEvidenceReader(),
    )

    first = controller.run_once(NOW)
    second = controller.run_once(
        datetime.fromisoformat("2026-08-24T13:27:00+08:00")
    )

    assert first["revision"] == second["revision"] == 1


def test_controller_restart_recovers_checkpointed_state_without_revision_churn() -> None:
    journal = InMemoryJournalRepository()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    first_controller = NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
    )
    first = first_controller.run_once(NOW)

    restarted = NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
    ).run_once(datetime.fromisoformat("2026-08-24T13:27:00+08:00"))

    assert first["state"] == restarted["state"] == "AGGRESSIVE_EXIT"
    assert first["revision"] == restarted["revision"] == 1


def test_controller_restart_repairs_terminal_transition_missing_result() -> None:
    journal = CrashBeforeFirstResultJournal()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    closed = datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    first_controller = NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
    )

    with pytest.raises(RuntimeError, match="simulated crash"):
        first_controller.run_once(closed)

    restarted = NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
    ).run_once(closed)

    assert restarted["state"] == "CONFIRMED_FLAT"
    assert restarted["result_status"] == "CURRENT"
    assert restarted["revision"] == 1


def test_disabled_controller_has_no_journal_side_effect() -> None:
    journal = InMemoryJournalRepository()
    controller = NoOvernightController(
        config=NoOvernightPolicyConfig.disabled(
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
    )

    assert controller.run_once(NOW)["state"] == "DISABLED"
    assert journal.session("no-overnight-v1-2026-08-24") is None


def test_enforcing_requires_guard_and_command_port() -> None:
    with pytest.raises(ValueError, match="guard and command port"):
        NoOvernightController(
            config=replace(_config(), mode=NoOvernightMode.ENFORCING),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            journal=InMemoryJournalRepository(),
            evidence_reader=StaticEvidenceReader(),
        )


def test_enforcing_runs_entry_cancel_then_aggressive_exit_action() -> None:
    command_port = CountingCommandPort()
    command_port.actions = []
    controller = NoOvernightController(
        config=replace(_config(), mode=NoOvernightMode.ENFORCING),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=InMemoryJournalRepository(),
        evidence_reader=StaticEvidenceReader(),
        command_port=command_port,
        guard=HealthyGuard(),
        deployment_manifest_digest="d" * 64,
    )

    status = controller.run_once(NOW)

    assert status["enforcing"] is True
    assert command_port.calls == 2
    assert len(command_port.actions) == 2
    assert all(
        isinstance(action, NoOvernightEnforcementAction)
        for action in command_port.actions
    )
    assert [action.kind for action in command_port.actions] == [
        "CANCEL_MANAGED_BUY_REMAINDER",
        "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
    ]


def test_guard_loss_immediately_before_command_has_zero_command_side_effect() -> None:
    journal = InMemoryJournalRepository()
    command_port = CountingCommandPort()
    command_port.actions = []
    controller = NoOvernightController(
        config=replace(_config(), mode=NoOvernightMode.ENFORCING),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=StaticEvidenceReader(),
        command_port=command_port,
        guard=HealthyGuard((True, False)),
        deployment_manifest_digest="d" * 64,
    )

    with pytest.raises(ValueError, match="guard ownership was lost"):
        controller.run_once(NOW)

    assert command_port.calls == 0


def test_final_admission_detects_controller_revision_advance() -> None:
    before_cutoff = datetime.fromisoformat("2026-08-24T13:09:00+08:00")
    at_cutoff = datetime.fromisoformat("2026-08-24T13:10:00+08:00")
    clock = MutableClock(before_cutoff)
    journal = InMemoryJournalRepository()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    guard = HealthyGuard()
    controller = NoOvernightController(
        config=replace(_runtime_config(), mode=NoOvernightMode.ENFORCING),
        calendar=calendar,
        journal=journal,
        evidence_reader=EmptyEvidenceReader(),
        command_port=CountingCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    )
    controller.run_once(before_cutoff)
    reader = LocalPaperExecutionAdmissionReader(
        config=replace(_runtime_config(), mode=NoOvernightMode.ENFORCING),
        calendar=calendar,
        journal=journal,
        clock=clock,
        simulation=ReadyExecutionContext(),
        guard=guard,
    )
    exposure = build_exposure_identity(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        owner_origin=CommandOrigin.MANUAL_WEB.value,
        owner_id="manual-web",
        holding_horizon=HoldingHorizon.LONG_TERM,
        entry_session_date=before_cutoff.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
        entry_identity="revision-race-long",
    )
    command = OrderCommand(
        command_id="revision-race-long",
        session_id=LOCAL_PAPER_V2_SESSION_ID,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("106"),
        idempotency_key="revision-race-long",
        requested_at=before_cutoff,
        exposure=exposure,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )
    initial = reader.read(command)

    clock.value = at_cutoff
    controller.run_once(at_cutoff)
    final = reader.read(
        command,
        expected_revision=initial.admission_revision,
    )

    assert initial.status is ExecutionAdmissionStatus.APPROVED
    assert final.status is ExecutionAdmissionStatus.RECOVERY_REQUIRED
    assert final.reasons == (ExecutionAdmissionReason.STATE_REVISION_CHANGED,)


def test_restart_keeps_prior_session_breach_latched_for_next_session_buy() -> None:
    journal = InMemoryJournalRepository()
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=FixedClock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    bought, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="breach-before-cross-session-restart",
        holding_horizon="INTRADAY",
    )
    assert bought["status"] == "FILLED"
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    config = replace(_runtime_config(), mode=NoOvernightMode.ENFORCING)
    evidence_reader = LocalPaperNoOvernightEvidenceReader(
        journal=journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    breach = NoOvernightController(
        config=config,
        calendar=calendar,
        journal=journal,
        evidence_reader=evidence_reader,
        command_port=CountingCommandPort(),
        guard=HealthyGuard(),
        deployment_manifest_digest="d" * 64,
    ).run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert breach["state"] == "OVERNIGHT_BREACH"
    assert breach["result_status"] == "CURRENT"

    next_session_at = datetime.fromisoformat("2026-08-25T09:05:00+08:00")
    restarted = NoOvernightController(
        config=config,
        calendar=calendar,
        journal=journal,
        evidence_reader=evidence_reader,
        command_port=CountingCommandPort(),
        guard=HealthyGuard(),
        deployment_manifest_digest="d" * 64,
    ).run_once(next_session_at)
    assert restarted["state"] == "NORMAL"

    exposure = build_exposure_identity(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        owner_origin=CommandOrigin.MANUAL_WEB.value,
        owner_id="manual-web",
        holding_horizon=HoldingHorizon.LONG_TERM,
        entry_session_date=next_session_at.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
        entry_identity="cross-session-breach-long-term",
    )
    command = OrderCommand(
        command_id="cross-session-breach-long-term",
        session_id=LOCAL_PAPER_V2_SESSION_ID,
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("106"),
        idempotency_key="cross-session-breach-long-term",
        requested_at=next_session_at,
        exposure=exposure,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )
    decision = LocalPaperExecutionAdmissionReader(
        config=config,
        calendar=calendar,
        journal=journal,
        clock=MutableClock(next_session_at),
        simulation=ReadyExecutionContext(),
        guard=HealthyGuard(),
    ).read(command)

    assert decision.status is ExecutionAdmissionStatus.BLOCKED
    assert decision.reasons == (ExecutionAdmissionReason.OPEN_BREACH,)
    assert decision.snapshot.state is NoOvernightState.NORMAL
    assert decision.snapshot.breach_latched is True
    assert decision.snapshot.breach_session_date == date(2026, 8, 24)


def test_runtime_observe_only_does_not_block_or_flatten_local_paper() -> None:
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=FixedClock(),
        journal=InMemoryJournalRepository(),
        local_paper_settings=_settings_v2(),
        no_overnight_config=_runtime_config(),
    )

    initial = composition.no_overnight_controller.status()
    assert initial["state"] == "AGGRESSIVE_EXIT"
    bought, idempotent = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="observe-only-buy-after-cutoff",
        holding_horizon="INTRADAY",
    )
    observed = composition.no_overnight_controller.run_once(NOW)

    assert idempotent is False
    assert bought["status"] == "FILLED"
    assert observed["state"] == "AGGRESSIVE_EXIT"
    assert observed["last_execution_fact_journal_sequence"] > 0
    assert len(composition.simulation_service.orders()) == 1

    after_close = composition.no_overnight_controller.run_once(
        datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    )
    assert after_close["state"] == "OVERNIGHT_BREACH"
    assert after_close["enforcing"] is False
    assert len(composition.simulation_service.orders()) == 1


@pytest.mark.parametrize(
    "restart_mode",
    (NoOvernightMode.OBSERVE_ONLY, NoOvernightMode.DISABLED),
)
def test_runtime_downgrade_keeps_durable_breach_buy_latch_and_allows_reduction(
    restart_mode: NoOvernightMode,
) -> None:
    clock = MutableClock(datetime.fromisoformat("2026-08-24T13:09:00+08:00"))
    journal = InMemoryJournalRepository()
    original = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    filled, _ = original.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key=f"downgrade-filled:{restart_mode.value}",
        holding_horizon="INTRADAY",
    )
    pending, _ = original.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key=f"downgrade-pending:{restart_mode.value}",
        holding_horizon="INTRADAY",
    )
    exposure_id = str(dict(filled["exposure_identity"])["exposure_id"])
    evidence_reader = LocalPaperNoOvernightEvidenceReader(
        journal=journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=original.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    breached = NoOvernightController(
        config=_runtime_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=evidence_reader,
    ).run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert breached["state"] == "OVERNIGHT_BREACH"
    assert dict(breached["breach"])["open"] is True
    original.close()

    clock.value = datetime.fromisoformat("2026-08-25T09:05:00+08:00")
    restart_config = (
        _runtime_config()
        if restart_mode is NoOvernightMode.OBSERVE_ONLY
        else NoOvernightPolicyConfig.disabled(
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        )
    )
    restarted = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
        local_paper_settings=_settings_v2(),
        no_overnight_config=restart_config,
    )
    try:
        exposures_before = restarted.simulation_service.exposures()
        orders_before = restarted.simulation_service.orders()
        records_before = journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)

        with pytest.raises(
            SimulationStateError,
            match="durable breach blocks BUY admission",
        ):
            restarted.local_paper_commands.submit_order(
                symbol="3231",
                side="BUY",
                lots=1,
                limit_price="106",
                idempotency_key=f"downgrade-blocked:{restart_mode.value}",
                holding_horizon="LONG_TERM",
            )

        assert journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID) == records_before
        assert restarted.simulation_service.orders() == orders_before
        assert restarted.simulation_service.exposures() == exposures_before

        cancelled, _ = restarted.local_paper_commands.cancel_order(
            str(pending["order_id"]),
            f"downgrade-cancel:{restart_mode.value}",
        )
        assert cancelled["status"] == "CANCELLED"
        sold, _ = restarted.local_paper_commands.submit_order(
            symbol="3231",
            side="SELL",
            lots=1,
            limit_price="105",
            idempotency_key=f"downgrade-sell:{restart_mode.value}",
            target_exposure_id=exposure_id,
        )
        assert sold["status"] == "FILLED"
        assert restarted.simulation_service.exposures() == []
    finally:
        restarted.close()

    if restart_mode is NoOvernightMode.DISABLED:
        legacy_session_id = "local-paper-runtime-downgraded-v1"
        legacy = RuntimeComposition.create(
            MockProvider(),
            clock=clock,
            journal=journal,
            local_paper_settings=LocalPaperSettings.defaults(),
            local_paper_session_id=legacy_session_id,
        )
        try:
            legacy_records_before = journal.records(legacy_session_id)
            with pytest.raises(
                SimulationStateError,
                match="durable breach blocks BUY admission",
            ):
                legacy.local_paper_commands.submit_order(
                    symbol="3231",
                    side="BUY",
                    lots=1,
                    limit_price="106",
                    idempotency_key="downgrade-v1-blocked",
                )
            assert journal.records(legacy_session_id) == legacy_records_before
            assert legacy.simulation_service.orders() == []
        finally:
            legacy.close()


def test_prior_session_managed_exposure_remains_visible_until_flat() -> None:
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=FixedClock(),
        journal=InMemoryJournalRepository(),
        local_paper_settings=_settings_v2(),
    )
    bought, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="prior-session-managed-buy",
        holding_horizon="INTRADAY",
    )
    assert bought["status"] == "FILLED"
    reader = LocalPaperNoOvernightEvidenceReader(
        journal=composition.journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )

    bundle = reader.read(
        now=datetime.fromisoformat("2026-08-25T13:30:00+08:00"),
        session_date=date(2026, 8, 25),
    )

    assert len(bundle.evidence.managed_exposures) == 1
    assert bundle.evidence.managed_exposures[0].current_quantity == 1000
    assert bundle.evidence.last_execution_fact_journal_sequence > 0

    status = NoOvernightController(
        config=_runtime_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=composition.journal,
        evidence_reader=reader,
    ).run_once(datetime.fromisoformat("2026-08-25T13:30:00+08:00"))
    assert status["state"] == "OVERNIGHT_BREACH"
    assert status["flat_proof_mode"] is None


def test_restart_routes_cross_session_late_fact_to_original_result_chain() -> None:
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=FixedClock(),
        journal=InMemoryJournalRepository(),
        local_paper_settings=_settings_v2(),
    )
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    reader = LocalPaperNoOvernightEvidenceReader(
        journal=composition.journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    session_date = date(2026, 8, 24)
    session_id = no_overnight_session_id(session_date)
    first = NoOvernightController(
        config=_runtime_config(),
        calendar=calendar,
        journal=composition.journal,
        evidence_reader=reader,
    ).run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert first["state"] == "CONFIRMED_FLAT"
    assert first["result_status"] == "CURRENT"
    assert first["snapshot_covers_through_journal_sequence"] == 0

    bought, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="late-buy-after-2026-08-24-flat-result",
        holding_horizon="INTRADAY",
    )
    assert bought["status"] == "FILLED"

    restarted = NoOvernightController(
        config=_runtime_config(),
        calendar=calendar,
        journal=composition.journal,
        evidence_reader=reader,
    ).run_once(datetime.fromisoformat("2026-08-25T13:30:00+08:00"))
    original = rebuild_no_overnight_projection(
        composition.journal,
        session_id=session_id,
        require_checkpoint=True,
    )

    assert restarted["state"] == "OVERNIGHT_BREACH"
    assert original.result_status == "SUPERSEDED"
    assert original.latest_result_snapshot_fence == 0
    assert original.last_execution_fact_journal_sequence > 0


def test_controller_retries_when_prior_session_facts_advance_after_snapshot() -> None:
    journal = InMemoryJournalRepository()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    original_date = date(2026, 8, 24)
    original_session_id = no_overnight_session_id(original_date)
    original = NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=EmptyEvidenceReader(),
    ).run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert original["result_status"] == "CURRENT"
    assert original["last_execution_fact_journal_sequence"] == 0

    advancing_reader = AdvancingPriorSessionEvidenceReader()
    NoOvernightController(
        config=_config(),
        calendar=calendar,
        journal=journal,
        evidence_reader=advancing_reader,
    ).run_once(datetime.fromisoformat("2026-08-25T13:30:00+08:00"))
    superseded = rebuild_no_overnight_projection(
        journal,
        session_id=original_session_id,
        require_checkpoint=True,
    )

    assert advancing_reader.calls == 4
    assert superseded.result_status == "SUPERSEDED"
    assert superseded.last_execution_fact_journal_sequence == 5
