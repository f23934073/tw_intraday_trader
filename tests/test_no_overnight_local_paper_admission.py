import hashlib
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from time import monotonic, sleep

import pytest

from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_ENTRY_POLICY_DIGEST,
    LOCAL_PAPER_ENTRY_POLICY_VERSION,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.no_overnight import (
    LocalPaperExecutionAdmissionReader,
    NoOvernightController,
    NoOvernightEvidenceBundle,
)
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService, SimulationStateError
from simulation.settings import LocalPaperSettings
from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.local_paper import (
    LOCAL_PAPER_FILL_V4_KIND,
    LOCAL_PAPER_ORDER_STATE_V2_KIND,
    LocalPaperProjection,
    ProjectionRecoveryError,
    build_local_paper_v1_import_record,
    latest_local_paper_order_states,
    rebuild_local_paper_v2_projection,
)
from trading.no_overnight import (
    NoOvernightEvidence,
    NoOvernightState,
    ReconciliationStatus,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionReason,
    ExecutionAdmissionSnapshot,
    ExecutionAdmissionStatus,
    evaluate_execution_admission,
)


AT = datetime.fromisoformat("2026-08-24T13:10:00+08:00")
SESSION_ID = "local-paper-runtime-v2"
SETTINGS_V2 = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())
SETTINGS_DIGEST = SETTINGS_V2.digest


def _simulation_v2(
    provider,
    *,
    clock,
    service_type=SimulationService,
    **kwargs,
) -> SimulationService:
    return service_type(
        provider,
        starting_cash=SETTINGS_V2.starting_cash_twd,
        max_daily_buy_notional=SETTINGS_V2.max_daily_buy_notional_twd,
        commission_rate=SETTINGS_V2.commission_rate,
        minimum_commission=SETTINGS_V2.minimum_commission_twd,
        slippage_bps=SETTINGS_V2.slippage_bps,
        cost_policy_enabled=True,
        clock=clock,
        **kwargs,
    )


class _Clock:
    def now(self) -> datetime:
        return AT

    def session_date(self) -> date:
        return AT.date()


class _MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class _SequenceClock:
    def __init__(self, default: datetime) -> None:
        self.default = default
        self.values: list[datetime] = []

    def set_values(self, values: list[datetime]) -> None:
        self.values = list(values)

    def now(self) -> datetime:
        return self.values.pop(0) if self.values else self.default

    def session_date(self) -> date:
        return self.default.date()


class _StreamingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        return None


class _CountingSimulationService(SimulationService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.submit_calls = 0

    def submit_order(self, *args, **kwargs):
        self.submit_calls += 1
        return super().submit_order(*args, **kwargs)


class _Guard:
    guard_identity = "pytest-postgres-guard"

    def is_owned_and_healthy(self) -> bool:
        return True

    def execute_if_owned(self, operation):
        return operation()


class _MutableGuard(_Guard):
    def __init__(self) -> None:
        self.healthy = True

    def is_owned_and_healthy(self) -> bool:
        return self.healthy

    def execute_if_owned(self, operation):
        if not self.healthy:
            raise ValueError("guard ownership was lost")
        return operation()


class _DropGuardAfterFinalAdmissionJournal(InMemoryJournalRepository):
    def __init__(self, guard: _MutableGuard) -> None:
        super().__init__()
        self._guard = guard

    def append(self, record: JournalRecord):
        result = super().append(record)
        if record.kind == "no_overnight_final_admission.v1":
            self._guard.healthy = False
        return result


class _NoopCommandPort:
    def execute(self, action: object) -> bool:
        return False


class _EmptyEvidenceReader:
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


class _AdvanceAfterInitialAdmission:
    def __init__(
        self,
        delegate: LocalPaperExecutionAdmissionReader,
        *,
        clock: _MutableClock,
        advance: timedelta,
    ) -> None:
        self._delegate = delegate
        self._clock = clock
        self._advance = advance

    def read(self, command, *, expected_revision=None):
        decision = self._delegate.read(
            command,
            expected_revision=expected_revision,
        )
        if expected_revision is None:
            self._clock.value += self._advance
        return decision

    def read_at(self, command, *, expected_revision, evaluated_at):
        return self._delegate.read_at(
            command,
            expected_revision=expected_revision,
            evaluated_at=evaluated_at,
        )

    def execute_under_admission_fence(self, operation):
        return self._delegate.execute_under_admission_fence(operation)


def _wait_until(predicate) -> None:
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("simulation worker did not reach expected state")


def _config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.ENFORCING,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
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


def _snapshot(
    *,
    tradable: bool = True,
    evaluated_at: datetime = AT,
) -> ExecutionAdmissionSnapshot:
    return ExecutionAdmissionSnapshot(
        evaluated_at=evaluated_at,
        session_date=evaluated_at.date(),
        state=NoOvernightState.NO_NEW_ENTRY,
        state_revision=1,
        policy_digest=_config().policy_digest,
        calendar_digest="calendar-v1",
        session_open=True,
        instrument_tradable=tradable,
        executable_book_ready=True,
        guard_owned=True,
        guard_healthy=True,
    )


class _AdmissionReader:
    def __init__(self, *, final_tradable: bool = True) -> None:
        self._final_tradable = final_tradable
        self.calls = 0
        self.fence_calls = 0

    def read(self, command, *, expected_revision=None):
        self.calls += 1
        return evaluate_execution_admission(
            command=command,
            config=_config(),
            snapshot=_snapshot(
                tradable=(
                    self._final_tradable if expected_revision is not None else True
                )
            ),
            expected_revision=expected_revision,
            final_check=expected_revision is not None,
        )

    def read_at(self, command, *, expected_revision, evaluated_at):
        self.calls += 1
        return evaluate_execution_admission(
            command=command,
            config=_config(),
            snapshot=_snapshot(
                tradable=self._final_tradable,
                evaluated_at=evaluated_at,
            ),
            expected_revision=expected_revision,
            final_check=True,
        )

    def execute_under_admission_fence(self, operation):
        self.fence_calls += 1
        return operation()


def _service(
    reader: object,
    *,
    journal: InMemoryJournalRepository | None = None,
    simulation: SimulationService | None = None,
    clock: object | None = None,
):
    journal = journal or InMemoryJournalRepository()
    clock = clock or _Clock()
    predecessor = LocalPaperProjection(
        starting_cash=Decimal("10000000"),
        settings_digest=SETTINGS_DIGEST,
    )
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=clock.now(),
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
                "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
                "settings_digest": SETTINGS_DIGEST,
                "predecessor_session_id": "local-paper-runtime-v1",
                "predecessor_terminal_sequence": predecessor.last_sequence,
                "predecessor_digest": predecessor.digest,
            },
        )
    )
    journal.append(
        build_local_paper_v1_import_record(
            source_projection=predecessor,
            source_session_id="local-paper-runtime-v1",
            target_session_id=SESSION_ID,
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            occurred_at=clock.now(),
        )
    )
    simulation = simulation or _simulation_v2(MockProvider(), clock=clock)
    service = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=SESSION_ID,
        clock=clock,
        settings_digest=SETTINGS_DIGEST,
        account_scope=LOCAL_PAPER_ACCOUNT_SCOPE,
        policy_family=LOCAL_PAPER_POLICY_FAMILY,
        entry_policy_version=LOCAL_PAPER_ENTRY_POLICY_VERSION,
        entry_policy_digest=LOCAL_PAPER_ENTRY_POLICY_DIGEST,
        execution_admission_reader=reader,
    )
    return service, simulation, journal


def _real_admission_service(
    *,
    book_received_at: datetime,
    initial_advance: timedelta,
) -> tuple[LocalPaperCommandService, _CountingSimulationService]:
    now = datetime.fromisoformat("2026-08-24T09:05:00+08:00")
    clock = _MutableClock(now)
    journal = InMemoryJournalRepository()
    provider = _StreamingProvider()
    simulation = _simulation_v2(
        provider,
        service_type=_CountingSimulationService,
        clock=clock,
        max_book_age_seconds=15,
    )
    simulation.watch_quote(owner_id="admission-boundary", symbol="3231")
    assert provider.handler is not None
    provider.handler(
        RealtimeQuoteUpdate(
            symbol="3231",
            kind="BIDASK",
            exchange_timestamp=book_received_at,
            received_at=book_received_at,
            bid_price=105.4,
            ask_price=105.5,
            bid_volume_lots=1,
            ask_volume_lots=1,
            suspended=False,
        )
    )
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "BUY",
            max_book_age_seconds=15,
        )["instrument_tradable"]
        is True
    )
    config = _config()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    guard = _Guard()
    NoOvernightController(
        config=config,
        calendar=calendar,
        journal=journal,
        evidence_reader=_EmptyEvidenceReader(),
        command_port=_NoopCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    ).run_once(now)
    real_reader = LocalPaperExecutionAdmissionReader(
        config=config,
        calendar=calendar,
        journal=journal,
        clock=clock,
        simulation=simulation,
        guard=guard,
    )
    service, _, _ = _service(
        _AdvanceAfterInitialAdmission(
            real_reader,
            clock=clock,
            advance=initial_advance,
        ),
        journal=journal,
        simulation=simulation,
        clock=clock,
    )
    return service, simulation


def test_initial_cutoff_blocks_intraday_without_creating_simulator_order() -> None:
    service, simulation, journal = _service(_AdmissionReader())

    result, idempotent = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="blocked-intraday",
        holding_horizon="INTRADAY",
    )

    assert idempotent is False
    assert result["status"] == "BLOCKED"
    assert result["admission_reasons"] == ["NO_OVERNIGHT_CUTOFF"]
    assert simulation.orders() == []
    assert [item.record.kind for item in journal.records(SESSION_ID)][1:] == [
        "order_command.v2"
    ]
    assert (
        latest_local_paper_order_states(
            journal,
            session_id=SESSION_ID,
        )
        == ()
    )
    restarted_simulation = _simulation_v2(MockProvider(), clock=_Clock())
    LocalPaperCommandService(
        simulation=restarted_simulation,
        journal=journal,
        session_id=SESSION_ID,
        clock=_Clock(),
        settings_digest=SETTINGS_DIGEST,
        account_scope=LOCAL_PAPER_ACCOUNT_SCOPE,
        policy_family=LOCAL_PAPER_POLICY_FAMILY,
        entry_policy_version=LOCAL_PAPER_ENTRY_POLICY_VERSION,
        entry_policy_digest=LOCAL_PAPER_ENTRY_POLICY_DIGEST,
        execution_admission_reader=_AdmissionReader(),
    )
    assert restarted_simulation.orders() == []


def test_long_term_survives_cutoff_and_reaches_handler() -> None:
    reader = _AdmissionReader()
    service, simulation, journal = _service(reader)

    result, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="allowed-long",
        holding_horizon="LONG_TERM",
    )

    assert result["status"] == "FILLED"
    assert reader.calls == 4
    assert reader.fence_calls == 2
    assert len(simulation.orders()) == 1
    assert [item.record.kind for item in journal.records(SESSION_ID)][1:3] == [
        "order_command.v2",
        "no_overnight_final_admission.v1",
    ]


def test_final_admission_block_has_no_order_or_position_mutation() -> None:
    service, simulation, journal = _service(_AdmissionReader(final_tradable=False))

    result, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="final-blocked-long",
        holding_horizon="LONG_TERM",
    )

    assert result["status"] == "BLOCKED"
    assert result["admission_reasons"] == ["NO_OVERNIGHT_INSTRUMENT_NOT_TRADABLE"]
    assert simulation.orders() == []
    assert simulation.exposures() == []
    assert [item.record.kind for item in journal.records(SESSION_ID)][1:] == [
        "order_command.v2",
        "no_overnight_final_admission.v1",
    ]
    assert (
        latest_local_paper_order_states(
            journal,
            session_id=SESSION_ID,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("book_offset", "advance"),
    [
        (timedelta(0), timedelta(seconds=15, microseconds=1)),
        (timedelta(microseconds=1), timedelta(0)),
    ],
    ids=("fractional-stale-final-check", "future-book-timestamp"),
)
def test_exact_book_freshness_blocks_before_handler_order_side_effect(
    book_offset: timedelta,
    advance: timedelta,
) -> None:
    initial_now = datetime.fromisoformat("2026-08-24T09:05:00+08:00")
    service, simulation = _real_admission_service(
        book_received_at=initial_now + book_offset,
        initial_advance=advance,
    )
    try:
        result, idempotent = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"book-boundary-{book_offset}-{advance}",
            holding_horizon="LONG_TERM",
        )

        assert idempotent is False
        assert result["status"] == "BLOCKED"
        assert result["admission_reasons"] == [
            ExecutionAdmissionReason.BOOK_UNAVAILABLE.value
        ]
        assert simulation.submit_calls == 0
        assert simulation.orders() == []
        assert simulation.exposures() == []
    finally:
        simulation.close()


def _mutation_boundary_race_service(
    *,
    quote_at: datetime,
    journal: InMemoryJournalRepository | None = None,
    guard: object | None = None,
) -> tuple[LocalPaperCommandService, _CountingSimulationService, _SequenceClock]:
    clock = _SequenceClock(quote_at)
    journal = journal or InMemoryJournalRepository()
    provider = _StreamingProvider()
    simulation = _simulation_v2(
        provider,
        service_type=_CountingSimulationService,
        clock=clock,
        max_book_age_seconds=15,
    )
    simulation.watch_quote(owner_id="handler-boundary-race", symbol="3231")
    assert provider.handler is not None
    provider.handler(
        RealtimeQuoteUpdate(
            symbol="3231",
            kind="BIDASK",
            exchange_timestamp=quote_at,
            received_at=quote_at,
            bid_price=105.4,
            ask_price=105.5,
            bid_volume_lots=1,
            ask_volume_lots=1,
            suspended=False,
        )
    )
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "BUY",
            max_book_age_seconds=15,
        )["instrument_tradable"]
        is True
    )
    config = _config()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    guard = guard or _Guard()
    NoOvernightController(
        config=config,
        calendar=calendar,
        journal=journal,
        evidence_reader=_EmptyEvidenceReader(),
        command_port=_NoopCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    ).run_once(quote_at)
    reader = LocalPaperExecutionAdmissionReader(
        config=config,
        calendar=calendar,
        journal=journal,
        clock=clock,
        simulation=simulation,
        guard=guard,
    )
    service, _, _ = _service(
        reader,
        journal=journal,
        simulation=simulation,
        clock=clock,
    )
    return service, simulation, clock


def test_guard_loss_after_final_event_has_zero_order_mutation() -> None:
    quote_at = datetime.fromisoformat("2026-08-24T09:05:00+08:00")
    guard = _MutableGuard()
    journal = _DropGuardAfterFinalAdmissionJournal(guard)
    service, simulation, _ = _mutation_boundary_race_service(
        quote_at=quote_at,
        journal=journal,
        guard=guard,
    )
    try:
        result, idempotent = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="guard-loss-after-final-event",
            holding_horizon="LONG_TERM",
        )

        assert idempotent is False
        assert result["status"] == "RECOVERY_REQUIRED"
        assert simulation.submit_calls == 0
        assert simulation.orders() == []
        assert simulation.exposures() == []
    finally:
        simulation.close()


def test_book_expiring_at_handler_mutation_boundary_has_zero_mutation() -> None:
    quote_at = datetime.fromisoformat("2026-08-24T09:05:00+08:00")
    service, simulation, clock = _mutation_boundary_race_service(quote_at=quote_at)
    final_fresh = quote_at + timedelta(seconds=14, microseconds=999_000)
    handler_stale = quote_at + timedelta(seconds=15, microseconds=1_000)
    clock.set_values(
        [
            quote_at,
            quote_at,
            quote_at,
            quote_at,
            final_fresh,
            final_fresh,
            handler_stale,
            handler_stale,
            handler_stale,
        ]
    )
    try:
        result, idempotent = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="handler-book-freshness-race",
            holding_horizon="LONG_TERM",
        )

        assert idempotent is False
        assert result["status"] == "BLOCKED"
        assert result["admission_reasons"] == [
            ExecutionAdmissionReason.BOOK_UNAVAILABLE.value
        ]
        assert simulation.submit_calls == 0
        assert simulation.orders() == []
        assert simulation.exposures() == []
    finally:
        simulation.close()


def test_cutoff_crossing_at_handler_mutation_boundary_has_zero_mutation() -> None:
    quote_at = datetime.fromisoformat("2026-08-24T13:09:59+08:00")
    service, simulation, clock = _mutation_boundary_race_service(quote_at=quote_at)
    final_before_cutoff = datetime.fromisoformat(
        "2026-08-24T13:09:59.999000+08:00"
    )
    handler_after_cutoff = datetime.fromisoformat(
        "2026-08-24T13:10:00.001000+08:00"
    )
    clock.set_values(
        [
            quote_at,
            quote_at,
            quote_at,
            quote_at,
            final_before_cutoff,
            final_before_cutoff,
            handler_after_cutoff,
            handler_after_cutoff,
            handler_after_cutoff,
        ]
    )
    try:
        result, idempotent = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="handler-cutoff-race",
            holding_horizon="INTRADAY",
        )

        assert idempotent is False
        assert result["status"] == "BLOCKED"
        assert result["admission_reasons"] == [
            ExecutionAdmissionReason.CUTOFF.value
        ]
        assert simulation.submit_calls == 0
        assert simulation.orders() == []
        assert simulation.exposures() == []
    finally:
        simulation.close()


def test_blocked_same_attempt_with_changed_input_remains_side_effect_free() -> None:
    service, simulation, journal = _service(_AdmissionReader(final_tradable=False))
    first, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="same-attempt-final-block",
        holding_horizon="LONG_TERM",
    )

    with pytest.raises(SimulationStateError, match="需先完成復原"):
        service.submit_order(
            symbol="3231",
            side="BUY",
            lots=2,
            limit_price="106",
            idempotency_key="same-attempt-final-block",
            holding_horizon="LONG_TERM",
        )

    assert first["status"] == "BLOCKED"
    assert simulation.orders() == []
    assert [item.record.kind for item in journal.records(SESSION_ID)].count(
        "order_command.v2"
    ) == 1


def _journal_with_forged_final_admission(
    *,
    blocked: bool,
) -> InMemoryJournalRepository:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=(
                "state-after-blocked-final" if blocked else "approved-revision-drift"
            ),
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        forged = InMemoryJournalRepository()
        forged.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            if record.kind == "no_overnight_final_admission.v1":
                original = ExecutionAdmissionDecision.from_payload(
                    record.payload["decision"]
                )
                snapshot = replace(
                    original.snapshot,
                    **(
                        {"instrument_tradable": False}
                        if blocked
                        else {"state_revision": original.snapshot.state_revision + 1}
                    ),
                )
                decision = ExecutionAdmissionDecision(
                    status=(
                        ExecutionAdmissionStatus.BLOCKED
                        if blocked
                        else ExecutionAdmissionStatus.APPROVED
                    ),
                    reasons=(
                        (ExecutionAdmissionReason.INSTRUMENT_NOT_TRADABLE,)
                        if blocked
                        else ()
                    ),
                    admission_revision=snapshot.admission_revision,
                    snapshot=snapshot,
                    final_check=True,
                )
                record = JournalRecord(
                    record_id=(
                        "forged-blocked-final"
                        if blocked
                        else "forged-approved-revision"
                    ),
                    session_id=record.session_id,
                    kind=record.kind,
                    occurred_at=record.occurred_at,
                    payload={**record.payload, "decision": decision.to_payload()},
                    idempotency_scope=record.idempotency_scope,
                    idempotency_key=record.idempotency_key,
                )
            forged.append(record)
        return forged
    finally:
        simulation.close()


def _recover_forged_execution_facts(
    journal: InMemoryJournalRepository,
    *,
    projection: str,
) -> None:
    if projection == "order-state":
        latest_local_paper_order_states(journal, session_id=SESSION_ID)
        return
    rebuild_local_paper_v2_projection(
        journal,
        session_id=SESSION_ID,
        starting_cash=Decimal("10000000"),
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        settings_digest=SETTINGS_DIGEST,
        require_checkpoint=False,
    )


@pytest.mark.parametrize("projection", ("order-state", "exposure-fill"))
def test_recovery_rejects_approved_final_admission_revision_drift(
    projection: str,
) -> None:
    forged = _journal_with_forged_final_admission(blocked=False)

    with pytest.raises(ProjectionRecoveryError, match="final admission lineage"):
        _recover_forged_execution_facts(forged, projection=projection)


@pytest.mark.parametrize("projection", ("order-state", "exposure-fill"))
def test_recovery_rejects_execution_fact_after_blocked_final_admission(
    projection: str,
) -> None:
    forged = _journal_with_forged_final_admission(blocked=True)

    with pytest.raises(ProjectionRecoveryError, match="final admission"):
        _recover_forged_execution_facts(forged, projection=projection)


def _journal_with_final_admission_failure() -> InMemoryJournalRepository:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="execution-after-final-failure",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        forged = InMemoryJournalRepository()
        forged.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            forged.append(record)
            if record.kind == "no_overnight_final_admission.v1":
                forged.append(
                    JournalRecord(
                        record_id="forged-final-admission-failure",
                        session_id=SESSION_ID,
                        kind="no_overnight_final_admission_failure.v1",
                        occurred_at=record.occurred_at,
                        payload={
                            "command_id": record.payload["command_id"],
                            "error_type": "POST_FINAL_ADMISSION_FENCE_CHANGED",
                        },
                    )
                )
        return forged
    finally:
        simulation.close()


@pytest.mark.parametrize("projection", ("order-state", "exposure-fill"))
def test_recovery_rejects_execution_fact_after_final_admission_failure(
    projection: str,
) -> None:
    forged = _journal_with_final_admission_failure()

    with pytest.raises(ProjectionRecoveryError, match="final admission failure"):
        _recover_forged_execution_facts(forged, projection=projection)


def _journal_with_unlinked_fill_after_blocked_final() -> InMemoryJournalRepository:
    forged = _journal_with_forged_final_admission(blocked=True)
    without_state_or_fill_link = InMemoryJournalRepository()
    session = forged.session(SESSION_ID)
    assert session is not None
    without_state_or_fill_link.start_session(session)
    for appended in forged.records(SESSION_ID):
        record = appended.record
        if record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND:
            continue
        if record.kind == LOCAL_PAPER_FILL_V4_KIND:
            record = JournalRecord(
                record_id=record.record_id,
                session_id=record.session_id,
                kind=record.kind,
                occurred_at=record.occurred_at,
                payload={
                    key: value
                    for key, value in record.payload.items()
                    if key not in {"command_id", "command_idempotency_key"}
                },
                idempotency_scope=record.idempotency_scope,
                idempotency_key=record.idempotency_key,
            )
        without_state_or_fill_link.append(record)
    return without_state_or_fill_link


def test_recovery_rejects_unlinked_fill_after_admission_bearing_command() -> None:
    without_state_or_fill_link = _journal_with_unlinked_fill_after_blocked_final()

    with pytest.raises(ProjectionRecoveryError, match="unlinked v4 fill"):
        _recover_forged_execution_facts(
            without_state_or_fill_link,
            projection="exposure-fill",
        )


@pytest.mark.parametrize(
    ("holding_horizon", "entry_session_date"),
    (
        ("INTRADAY", AT.date().isoformat()),
        ("UNCLASSIFIED_LEGACY", None),
    ),
)
def test_recovery_rejects_v4_fill_exposure_identity_drift_from_command(
    holding_horizon: str,
    entry_session_date: str | None,
) -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"v4-command-drift:{holding_horizon}",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        forged = InMemoryJournalRepository()
        forged.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            if record.kind == LOCAL_PAPER_FILL_V4_KIND:
                exposure = dict(record.payload["exposure_identity"])
                exposure["holding_horizon"] = holding_horizon
                exposure["entry_session_date"] = entry_session_date
                record = JournalRecord(
                    record_id=record.record_id,
                    session_id=record.session_id,
                    kind=record.kind,
                    occurred_at=record.occurred_at,
                    payload={**record.payload, "exposure_identity": exposure},
                    idempotency_scope=record.idempotency_scope,
                    idempotency_key=record.idempotency_key,
                )
            forged.append(record)

        with pytest.raises(
            ProjectionRecoveryError,
            match="v4 fill exposure_identity does not match command",
        ):
            _recover_forged_execution_facts(
                forged,
                projection="exposure-fill",
            )
    finally:
        simulation.close()


@pytest.mark.parametrize(
    ("field_name", "forged_value", "expected_message"),
    (
        ("order_id", "forged-unrelated-order", "v4 fill order_id"),
        ("limit_price", "107", "v4 fill limit_price"),
    ),
)
def test_recovery_rejects_v4_fill_order_lineage_drift(
    field_name: str,
    forged_value: str,
    expected_message: str,
) -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"v4-order-lineage:{field_name}",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        forged = InMemoryJournalRepository()
        forged.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            if record.kind == LOCAL_PAPER_FILL_V4_KIND:
                payload = {**record.payload, field_name: forged_value}
                record = JournalRecord(
                    record_id=(
                        f"local-paper-fill-v4:{forged_value}:"
                        f"{record.occurred_at.isoformat()}"
                        if field_name == "order_id"
                        else record.record_id
                    ),
                    session_id=record.session_id,
                    kind=record.kind,
                    occurred_at=record.occurred_at,
                    payload=payload,
                    idempotency_scope=record.idempotency_scope,
                    idempotency_key=(
                        forged_value
                        if field_name == "order_id"
                        else record.idempotency_key
                    ),
                )
            forged.append(record)

        with pytest.raises(ProjectionRecoveryError, match=expected_message):
            _recover_forged_execution_facts(
                forged,
                projection="exposure-fill",
            )
    finally:
        simulation.close()


def test_recovery_rejects_v4_fill_strategy_version_drift_from_command() -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_strategy_order(
            intent_id="v4-strategy-version-lineage",
            strategy_id="strategy-owner",
            strategy_version="strategy-v1",
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        forged = InMemoryJournalRepository()
        forged.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            if record.kind == LOCAL_PAPER_FILL_V4_KIND:
                record = JournalRecord(
                    record_id=record.record_id,
                    session_id=record.session_id,
                    kind=record.kind,
                    occurred_at=record.occurred_at,
                    payload={
                        **record.payload,
                        "owner_strategy_version": "strategy-v2",
                    },
                    idempotency_scope=record.idempotency_scope,
                    idempotency_key=record.idempotency_key,
                )
            forged.append(record)

        with pytest.raises(
            ProjectionRecoveryError,
            match="v4 fill owner_strategy_version",
        ):
            _recover_forged_execution_facts(
                forged,
                projection="exposure-fill",
            )
    finally:
        simulation.close()


def test_recovery_accepts_fill_before_missing_state_as_recovery_required() -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="v4-fill-before-state-crash",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        crashed = InMemoryJournalRepository()
        crashed.start_session(session)
        for appended in source.records(SESSION_ID):
            if appended.record.kind != LOCAL_PAPER_ORDER_STATE_V2_KIND:
                crashed.append(appended.record)

        projection = rebuild_local_paper_v2_projection(
            crashed,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000000"),
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            settings_digest=SETTINGS_DIGEST,
            require_checkpoint=False,
        )
        recovered_states = latest_local_paper_order_states(
            crashed,
            session_id=SESSION_ID,
        )

        assert projection.aggregate_quantity("3231") == 1_000
        assert len(recovered_states) == 1
        assert recovered_states[0]["status"] == "RECOVERY_REQUIRED"
        assert recovered_states[0]["reason"] == "COMMAND_ACKNOWLEDGEMENT_MISSING"
    finally:
        simulation.close()


def _journal_with_resigned_v2_state(
    source: InMemoryJournalRepository,
    updates: dict[str, object],
) -> InMemoryJournalRepository:
    session = source.session(SESSION_ID)
    assert session is not None
    forged = InMemoryJournalRepository()
    forged.start_session(session)
    for appended in source.records(SESSION_ID):
        record = appended.record
        if record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND:
            unsigned_payload = {**record.payload, **updates}
            unsigned_payload.pop("order_state_digest")
            unsigned = JournalRecord(
                record_id=record.record_id,
                session_id=record.session_id,
                kind=record.kind,
                occurred_at=record.occurred_at,
                payload=unsigned_payload,
                idempotency_scope=record.idempotency_scope,
                idempotency_key=record.idempotency_key,
            )
            record = JournalRecord(
                record_id=unsigned.record_id,
                session_id=unsigned.session_id,
                kind=unsigned.kind,
                occurred_at=unsigned.occurred_at,
                payload={
                    **unsigned.payload,
                    "order_state_digest": hashlib.sha256(
                        unsigned.payload_bytes
                    ).hexdigest(),
                },
                idempotency_scope=unsigned.idempotency_scope,
                idempotency_key=unsigned.idempotency_key,
            )
        forged.append(record)
    return forged


def test_recovery_rejects_v2_state_cumulative_drift_from_v4_fills() -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="v2-state-fill-cumulative-drift",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        forged = _journal_with_resigned_v2_state(
            source,
            {
                "filled_quantity": 500,
                "remaining_quantity": 500,
            },
        )

        with pytest.raises(
            ProjectionRecoveryError,
            match="v2 order state fill progression",
        ):
            _recover_forged_execution_facts(
                forged,
                projection="exposure-fill",
            )
        with pytest.raises(
            ProjectionRecoveryError,
            match="v2 order state fill progression",
        ):
            _recover_forged_execution_facts(
                forged,
                projection="order-state",
            )
    finally:
        simulation.close()


@pytest.mark.parametrize(
    ("field_name", "forged_value", "expected_message"),
    (
        ("limit_price_decimal", "1", "limit_price_decimal must match"),
        ("filled_amount_decimal", "1", "filled_amount_decimal must match"),
        ("last_fill_price_decimal", "1", "last_fill_price_decimal must match"),
        (
            "filled_commission_decimal",
            "1",
            "filled_commission_decimal must match",
        ),
        (
            "last_fill_commission_decimal",
            "1",
            "last_fill_commission_decimal must match",
        ),
    ),
)
def test_recovery_rejects_v2_state_decimal_alias_drift(
    field_name: str,
    forged_value: str,
    expected_message: str,
) -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"v2-state-decimal-drift:{field_name}",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        forged = _journal_with_resigned_v2_state(
            source,
            {field_name: forged_value},
        )

        for projection in ("exposure-fill", "order-state"):
            with pytest.raises(ProjectionRecoveryError, match=expected_message):
                _recover_forged_execution_facts(
                    forged,
                    projection=projection,
                )
    finally:
        simulation.close()


@pytest.mark.parametrize("forged_status", ("CANCELLED", "REJECTED"))
def test_recovery_rejects_terminal_state_with_full_fill(
    forged_status: str,
) -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"v2-state-status-drift:{forged_status}",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        forged = _journal_with_resigned_v2_state(
            source,
            {"status": forged_status},
        )

        for projection in ("exposure-fill", "order-state"):
            with pytest.raises(
                ProjectionRecoveryError,
                match="fully filled order state",
            ):
                _recover_forged_execution_facts(
                    forged,
                    projection=projection,
                )
    finally:
        simulation.close()


def _journal_with_execution_fact_before_final(
    fact_kind: str,
) -> InMemoryJournalRepository:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key=f"execution-before-final:{fact_kind}",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        records = tuple(item.record for item in source.records(SESSION_ID))
        premature = InMemoryJournalRepository()
        premature.start_session(session)
        for record in records:
            if record.kind in {"local_paper_v1_imported.v1", "order_command.v2"}:
                premature.append(record)
        premature.append(next(record for record in records if record.kind == fact_kind))
        premature.append(
            next(
                record
                for record in records
                if record.kind == "no_overnight_final_admission.v1"
            )
        )
        return premature
    finally:
        simulation.close()


@pytest.mark.parametrize(
    ("fact_kind", "projection"),
    (
        (LOCAL_PAPER_ORDER_STATE_V2_KIND, "order-state"),
        (LOCAL_PAPER_FILL_V4_KIND, "exposure-fill"),
    ),
)
def test_recovery_rejects_execution_fact_before_final_admission(
    fact_kind: str,
    projection: str,
) -> None:
    premature = _journal_with_execution_fact_before_final(fact_kind)

    with pytest.raises(ProjectionRecoveryError, match="append order"):
        _recover_forged_execution_facts(premature, projection=projection)


def _journal_with_order_state_before_final() -> InMemoryJournalRepository:
    return _journal_with_execution_fact_before_final(
        LOCAL_PAPER_ORDER_STATE_V2_KIND
    )


@pytest.mark.parametrize(
    "journal_factory",
    (
        _journal_with_final_admission_failure,
        _journal_with_unlinked_fill_after_blocked_final,
        _journal_with_order_state_before_final,
    ),
)
def test_restart_fails_closed_for_invalid_execution_lineage(
    journal_factory,
) -> None:
    simulation = _simulation_v2(MockProvider(), clock=_Clock())
    try:
        with pytest.raises(SimulationStateError, match="execution lineage"):
            LocalPaperCommandService(
                simulation=simulation,
                journal=journal_factory(),
                session_id=SESSION_ID,
                clock=_Clock(),
                settings_digest=SETTINGS_DIGEST,
                account_scope=LOCAL_PAPER_ACCOUNT_SCOPE,
                policy_family=LOCAL_PAPER_POLICY_FAMILY,
                entry_policy_version=LOCAL_PAPER_ENTRY_POLICY_VERSION,
                entry_policy_digest=LOCAL_PAPER_ENTRY_POLICY_DIGEST,
                execution_admission_reader=_AdmissionReader(),
            )
    finally:
        simulation.close()


def test_recovery_accepts_unlinked_fill_before_any_admission_boundary() -> None:
    service, simulation, source = _service(_AdmissionReader())
    try:
        order, _ = service.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="legacy-unlinked-fill",
            holding_horizon="LONG_TERM",
        )
        assert order["status"] == "FILLED"
        session = source.session(SESSION_ID)
        assert session is not None
        legacy = InMemoryJournalRepository()
        legacy.start_session(session)
        for appended in source.records(SESSION_ID):
            record = appended.record
            if record.kind == "local_paper_v1_imported.v1":
                legacy.append(record)
            elif record.kind == LOCAL_PAPER_FILL_V4_KIND:
                legacy.append(
                    JournalRecord(
                        record_id=record.record_id,
                        session_id=record.session_id,
                        kind=record.kind,
                        occurred_at=record.occurred_at,
                        payload={
                            key: value
                            for key, value in record.payload.items()
                            if key
                            not in {"command_id", "command_idempotency_key"}
                        },
                        idempotency_scope=record.idempotency_scope,
                        idempotency_key=record.idempotency_key,
                    )
                )

        projection = rebuild_local_paper_v2_projection(
            legacy,
            session_id=SESSION_ID,
            starting_cash=Decimal("10000000"),
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            settings_digest=SETTINGS_DIGEST,
            require_checkpoint=False,
        )

        assert projection.aggregate_quantity("3231") == 1_000
    finally:
        simulation.close()
