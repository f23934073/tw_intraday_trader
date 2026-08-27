from datetime import date, datetime, time
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config import twse_calendar_2026
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.no_overnight import (
    LocalPaperManagedEntryCancellationPort,
    LocalPaperNoOvernightEvidenceReader,
    NoOvernightController,
    NoOvernightEnforcementAction,
)
from simulation.settings import LocalPaperSettings
from simulation.service import SimulationService, SimulationStateError
from trading.exposure import build_semantic_action_key
from trading.journal import InMemoryJournalRepository, JournalRecord
from trading.local_paper import LOCAL_PAPER_CANCEL_RESULT_V2_KIND
from trading.no_overnight import NoOvernightState


TAIPEI = ZoneInfo("Asia/Taipei")
AT = datetime(2026, 8, 24, 13, 14, tzinfo=TAIPEI)
ACTIVE_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"


def _settings_v2() -> LocalPaperSettings:
    return LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())


class _Clock:
    def now(self) -> datetime:
        return AT

    def session_date(self) -> date:
        return AT.date()


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

    def partial_fill(self) -> None:
        assert self.handler is not None
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=AT,
                received_at=AT,
                bid_price=105.4,
                ask_price=105.5,
                bid_volume_lots=1,
                ask_volume_lots=1,
            )
        )


def _wait_until(predicate) -> None:
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("simulation worker did not reach expected state")


def _action() -> NoOvernightEnforcementAction:
    return NoOvernightEnforcementAction(
        kind="CANCEL_MANAGED_BUY_REMAINDER",
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        session_date=AT.date(),
        state=NoOvernightState.CANCEL_ENTRY,
        state_revision=1,
        requested_at=AT,
    )


class _Guard:
    guard_identity = "pytest-postgres-guard"

    def is_owned_and_healthy(self) -> bool:
        return True

    def execute_if_owned(self, operation):
        return operation()


class _CrashBeforeCancelResultJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.crash_before_cancel_result = False

    def append(self, record: JournalRecord):
        if (
            self.crash_before_cancel_result
            and record.kind == LOCAL_PAPER_CANCEL_RESULT_V2_KIND
        ):
            raise RuntimeError("crash before cancel result")
        return super().append(record)


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


def test_partial_fill_cancellation_keeps_fill_and_never_creates_sell() -> None:
    journal = InMemoryJournalRepository()
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    order, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=2,
        limit_price="106",
        idempotency_key="managed-partial-buy",
        holding_horizon="INTRADAY",
    )
    provider.partial_fill()
    _wait_until(
        lambda: composition.simulation_service.orders()[0]["status"]
        == "PARTIALLY_FILLED"
    )

    LocalPaperManagedEntryCancellationPort(
        commands=composition.local_paper_commands,
        simulation=composition.simulation_service,
    ).execute(_action())

    cancelled = composition.simulation_service.orders()[0]
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["filled_quantity"] == 1000
    assert cancelled["remaining_quantity"] == 1000
    assert composition.simulation_service.exposures()[0]["quantity"] == 1000
    assert all(
        item["side"] == "BUY" for item in composition.simulation_service.orders()
    )
    kinds = [
        item.record.kind
        for item in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
    ]
    assert "local_paper_cancel_intent.v2" in kinds
    assert "local_paper_cancel_result.v2" in kinds

    evidence = LocalPaperNoOvernightEvidenceReader(
        journal=journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    ).read(now=AT, session_date=AT.date())
    assert evidence.evidence.pending_entry_quantity == ()
    assert evidence.evidence.managed_exposures[0].current_quantity == 1000
    assert evidence.execution_facts[-1].kind == "local_paper_cancel_result.v2"


def test_stream_admission_requires_explicit_not_suspended_bidask_fact() -> None:
    provider = _StreamingProvider()
    simulation = SimulationService(provider, clock=_Clock())
    simulation.watch_quote(owner_id="admission-test", symbol="3231")
    unknown = simulation.execution_admission_context(
        "3231",
        "BUY",
        max_book_age_seconds=15,
    )
    assert unknown["instrument_tradable"] is False
    assert unknown["executable_book_ready"] is False
    assert provider.handler is not None
    provider.handler(
        RealtimeQuoteUpdate(
            symbol="3231",
            kind="BIDASK",
            exchange_timestamp=AT,
            received_at=AT,
            bid_price=105.4,
            ask_price=105.5,
            bid_volume_lots=1,
            ask_volume_lots=1,
            suspended=True,
        )
    )
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "BUY",
            max_book_age_seconds=15,
        )["executable_book_ready"]
        is True
    )
    suspended = simulation.execution_admission_context(
        "3231",
        "BUY",
        max_book_age_seconds=15,
    )
    assert suspended["instrument_tradable"] is False

    provider.handler(
        RealtimeQuoteUpdate(
            symbol="3231",
            kind="BIDASK",
            exchange_timestamp=AT.replace(microsecond=1),
            received_at=AT.replace(microsecond=1),
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
    simulation.close()


def test_snapshot_price_is_not_treated_as_executable_bidask() -> None:
    simulation = SimulationService(MockProvider(), clock=_Clock())

    context = simulation.execution_admission_context(
        "3231",
        "BUY",
        max_book_age_seconds=15,
    )

    assert context["instrument_tradable"] is True
    assert context["executable_book_ready"] is False
    assert context["data_health_state"] == "BLOCKED"


def test_cancel_result_is_idempotently_recovered_after_restart() -> None:
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    order, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="1",
        idempotency_key="managed-pending-buy",
        holding_horizon="INTRADAY",
    )
    raw_identity = order["exposure_identity"]
    cancel_key = build_semantic_action_key(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        session_date=AT.date(),
        exposure_id=raw_identity["exposure_id"],
        action="CANCEL_ENTRY_REMAINDER",
        attempt=1,
        target_order_id=order["order_id"],
    )
    LocalPaperManagedEntryCancellationPort(
        commands=first.local_paper_commands,
        simulation=first.simulation_service,
    ).execute(_action())

    restarted = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    recovered, idempotent = restarted.local_paper_commands.cancel_order(
        order["order_id"],
        cancel_key,
    )

    assert idempotent is True
    assert recovered["status"] == "CANCELLED"
    assert len(restarted.simulation_service.orders()) == 1


def test_managed_cancellation_preserves_same_symbol_long_term_buy() -> None:
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=InMemoryJournalRepository(),
        local_paper_settings=_settings_v2(),
    )
    long_term, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="1",
        idempotency_key="pending-long-term-buy",
        holding_horizon="LONG_TERM",
    )
    intraday, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="1",
        idempotency_key="pending-intraday-buy",
        holding_horizon="INTRADAY",
    )

    LocalPaperManagedEntryCancellationPort(
        commands=composition.local_paper_commands,
        simulation=composition.simulation_service,
    ).execute(_action())

    by_id = {
        item["order_id"]: item for item in composition.simulation_service.orders()
    }
    assert by_id[long_term["order_id"]]["status"] == "PENDING"
    assert by_id[intraday["order_id"]]["status"] == "CANCELLED"


def test_controller_recaptures_cancel_facts_before_publishing_status() -> None:
    journal = InMemoryJournalRepository()
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    order, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="1",
        idempotency_key="controller-cancel-fence",
        holding_horizon="INTRADAY",
    )
    assert order["status"] == "PENDING"
    evidence_reader = LocalPaperNoOvernightEvidenceReader(
        journal=journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    controller = NoOvernightController(
        config=_config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=evidence_reader,
        command_port=LocalPaperManagedEntryCancellationPort(
            commands=composition.local_paper_commands,
            simulation=composition.simulation_service,
        ),
        guard=_Guard(),
        deployment_manifest_digest="d" * 64,
    )

    status = controller.run_once(datetime(2026, 8, 24, 13, 16, tzinfo=TAIPEI))
    cancel_result = next(
        item
        for item in journal.records(ACTIVE_LOCAL_PAPER_SESSION_ID)
        if item.record.kind == "local_paper_cancel_result.v2"
    )

    assert status["state"] == "CANCEL_ENTRY"
    assert status["last_execution_fact_journal_sequence"] == cancel_result.sequence
    assert composition.simulation_service.orders()[0]["status"] == "CANCELLED"


def test_cancel_intent_without_result_remains_unresolved_evidence() -> None:
    journal = _CrashBeforeCancelResultJournal()
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    order, _ = composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="1",
        idempotency_key="unresolved-cancel-intent",
        holding_horizon="INTRADAY",
    )
    raw_identity = order["exposure_identity"]
    cancel_key = build_semantic_action_key(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        session_date=AT.date(),
        exposure_id=raw_identity["exposure_id"],
        action="CANCEL_ENTRY_REMAINDER",
        attempt=1,
        target_order_id=order["order_id"],
    )
    journal.crash_before_cancel_result = True

    with pytest.raises(RuntimeError, match="crash before cancel result"):
        LocalPaperManagedEntryCancellationPort(
            commands=composition.local_paper_commands,
            simulation=composition.simulation_service,
        ).execute(_action())

    evidence = LocalPaperNoOvernightEvidenceReader(
        journal=journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=composition.simulation_service,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    ).read(now=AT, session_date=AT.date())
    assert composition.simulation_service.orders()[0]["status"] == "CANCELLED"
    assert evidence.evidence.unresolved_execution_ids == (f"cancel:{cancel_key}",)
    composition.close()

    restarted = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        journal=journal,
        local_paper_settings=_settings_v2(),
    )
    try:
        with pytest.raises(SimulationStateError, match="需要復原"):
            restarted.local_paper_commands.cancel_order(order["order_id"], cancel_key)
    finally:
        restarted.close()
