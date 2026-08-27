from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight import (
    LocalPaperExecutionAdmissionReader,
    LocalPaperNoOvernightEvidenceReader,
    NoOvernightController,
    NoOvernightEvidenceBundle,
    NoOvernightReconciliationRequired,
    no_overnight_session_id,
)
from simulation.settings import LocalPaperSettings
from tests.test_no_overnight_admission import _command, _config as _admission_config
from tests.test_no_overnight_flattening import _StreamingProvider, _wait_until
from tests.test_no_overnight_runtime import (
    CountingCommandPort,
    HealthyGuard,
    _runtime_config,
)
from trading.exposure import HoldingHorizon
from trading.local_paper import ProjectionRecoveryError
from trading.no_overnight import (
    NoOvernightEvidence,
    NoOvernightState,
    ReconciliationStatus,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionReason,
    ExecutionAdmissionStatus,
)
from trading.no_overnight_journal import rebuild_no_overnight_projection


TAIPEI = ZoneInfo("Asia/Taipei")
ACTIVE_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"


def _settings_v2() -> LocalPaperSettings:
    return LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


def _reader(
    composition: RuntimeComposition,
    simulation: object,
) -> LocalPaperNoOvernightEvidenceReader:
    return LocalPaperNoOvernightEvidenceReader(
        journal=composition.journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=simulation,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )


class _RequiredEvidenceReader:
    def read(
        self,
        *,
        now: datetime,
        session_date: date,
    ) -> NoOvernightEvidenceBundle:
        bundle = NoOvernightEvidenceBundle(
            evidence=NoOvernightEvidence(
                session_date=session_date,
                managed_exposures=(),
                pending_entry_quantity=(),
                pending_exit_quantity=(),
                unresolved_execution_ids=(),
                reconciliation_status=ReconciliationStatus.REQUIRED,
                reconciliation_digest="a" * 64,
                last_fill_journal_sequence=0,
                last_execution_fact_journal_sequence=0,
                snapshot_covers_through_journal_sequence=0,
                snapshot_journal_sequence=0,
                snapshot_source_as_of=now,
                snapshot_received_at=now,
            ),
            execution_facts=(),
        )
        raise NoOvernightReconciliationRequired(
            "test reconciliation mismatch",
            bundle=bundle,
        )


class _AdmissionSimulation:
    max_book_age_seconds = 15

    def execution_admission_context(
        self,
        symbol: str,
        side: str,
        *,
        max_book_age_seconds: int,
    ) -> dict[str, object]:
        return {
            "instrument_tradable": True,
            "executable_book_ready": True,
            "data_health_state": "HEALTHY",
        }


@pytest.mark.parametrize(
    "horizon",
    (HoldingHorizon.INTRADAY, HoldingHorizon.LONG_TERM),
)
def test_required_reconciliation_blocks_initial_and_final_buy_admission(
    horizon: HoldingHorizon,
) -> None:
    now = datetime(2026, 8, 24, 9, 5, tzinfo=TAIPEI)
    config = _admission_config()
    journal = InMemoryJournalRepository()
    guard = HealthyGuard()
    NoOvernightController(
        config=config,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=_RequiredEvidenceReader(),
        command_port=CountingCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    ).run_once(now)
    reader = LocalPaperExecutionAdmissionReader(
        config=config,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        clock=_Clock(now),
        simulation=_AdmissionSimulation(),
        guard=guard,
    )
    command = replace(_command(horizon), requested_at=now)

    initial = reader.read_at(command, evaluated_at=now)
    final = reader.read_at(
        command,
        expected_revision=initial.admission_revision,
        evaluated_at=now,
    )

    for decision in (initial, final):
        assert decision.status is ExecutionAdmissionStatus.RECOVERY_REQUIRED
        assert ExecutionAdmissionReason.RECOVERY_REQUIRED in decision.reasons


def test_missing_evidence_blocks_buy_admission_after_failed_controller_start() -> None:
    now = datetime(2026, 8, 24, 9, 5, tzinfo=TAIPEI)
    config = _admission_config()
    journal = InMemoryJournalRepository()
    guard = HealthyGuard()

    class _StructuralFailureReader:
        def read(self, *, now: datetime, session_date: date):
            raise ValueError("structural evidence failure")

    controller = NoOvernightController(
        config=config,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=_StructuralFailureReader(),
        command_port=CountingCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    )
    with pytest.raises(ValueError, match="structural evidence failure"):
        controller.run_once(now)

    decision = LocalPaperExecutionAdmissionReader(
        config=config,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        clock=_Clock(now),
        simulation=_AdmissionSimulation(),
        guard=guard,
    ).read_at(
        replace(_command(HoldingHorizon.LONG_TERM), requested_at=now),
        evaluated_at=now,
    )

    assert decision.status is ExecutionAdmissionStatus.RECOVERY_REQUIRED
    assert ExecutionAdmissionReason.RECOVERY_REQUIRED in decision.reasons


def test_accounting_mismatch_is_a_durable_close_breach_after_recovery() -> None:
    close = datetime(2026, 8, 24, 13, 30, tzinfo=TAIPEI)
    clock = _Clock(close)
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service

    class _AccountingMismatch:
        def exposures(self):
            return simulation.exposures()

        def orders(self):
            return simulation.orders()

        def no_overnight_reconciliation_context(self):
            context = simulation.no_overnight_reconciliation_context()
            context["cash"] = "0"
            return context

    try:
        controller = NoOvernightController(
            config=_runtime_config(),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            journal=composition.journal,
            evidence_reader=_reader(composition, _AccountingMismatch()),
        )

        status = controller.run_once(close)

        assert status["state"] == NoOvernightState.OVERNIGHT_BREACH.value
        assert status["reconciliation_status"] == ReconciliationStatus.REQUIRED.value
        assert status["result_status"] == "CURRENT"
        recovered = rebuild_no_overnight_projection(
            composition.journal,
            session_id=no_overnight_session_id(close.date()),
            require_checkpoint=True,
        )
        assert recovered.state is NoOvernightState.OVERNIGHT_BREACH
        assert recovered.last_reconciliation_status == ReconciliationStatus.REQUIRED.value
        assert recovered.result_status == "CURRENT"
        assert recovered.last_reconciliation_digest == status["reconciliation_digest"]
    finally:
        composition.close()


def test_limit_price_drift_is_bound_to_required_reconciliation_digest() -> None:
    at = datetime(2026, 8, 24, 13, 21, tzinfo=TAIPEI)
    clock = _Clock(at)
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service
    try:
        simulation.watch_quote(owner_id="g4-regression", symbol="3231")
        provider.emit(at=clock.now())
        _wait_until(
            lambda: simulation.execution_admission_context(
                "3231",
                "BUY",
                max_book_age_seconds=simulation.max_book_age_seconds,
            )["executable_book_ready"]
            is True
        )
        composition.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="g4-regression-limit-price",
            holding_horizon="INTRADAY",
        )
        matched = _reader(composition, simulation).read(
            now=clock.now(),
            session_date=clock.session_date(),
        )

        class _LimitPriceMismatch:
            def exposures(self):
                return simulation.exposures()

            def orders(self):
                rows = simulation.orders()
                rows[0]["limit_price"] = "999"
                return rows

            def no_overnight_reconciliation_context(self):
                return simulation.no_overnight_reconciliation_context()

        with pytest.raises(
            NoOvernightReconciliationRequired,
            match="order Journal/simulator state mismatch",
        ) as caught:
            _reader(composition, _LimitPriceMismatch()).read(
                now=clock.now(),
                session_date=clock.session_date(),
            )

        assert caught.value.bundle.evidence.reconciliation_status is (
            ReconciliationStatus.REQUIRED
        )
        assert (
            caught.value.bundle.evidence.reconciliation_digest
            != matched.evidence.reconciliation_digest
        )
    finally:
        composition.close()


def test_malformed_order_value_remains_a_structural_recovery_error() -> None:
    at = datetime(2026, 8, 24, 13, 21, tzinfo=TAIPEI)
    clock = _Clock(at)
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service
    try:
        simulation.watch_quote(owner_id="g4-corruption", symbol="3231")
        provider.emit(at=clock.now())
        _wait_until(
            lambda: simulation.execution_admission_context(
                "3231",
                "BUY",
                max_book_age_seconds=simulation.max_book_age_seconds,
            )["executable_book_ready"]
            is True
        )
        composition.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="g4-corruption-limit-price",
            holding_horizon="INTRADAY",
        )

        class _MalformedOrder:
            def exposures(self):
                return simulation.exposures()

            def orders(self):
                rows = simulation.orders()
                rows[0]["limit_price"] = True
                return rows

            def no_overnight_reconciliation_context(self):
                return simulation.no_overnight_reconciliation_context()

        with pytest.raises(ProjectionRecoveryError, match="limit_price"):
            _reader(composition, _MalformedOrder()).read(
                now=clock.now(),
                session_date=clock.session_date(),
            )
    finally:
        composition.close()


def test_duplicate_exposure_identity_fails_direct_and_restarted_controller() -> None:
    at = datetime(2026, 8, 24, 13, 21, tzinfo=TAIPEI)
    clock = _Clock(at)
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service
    try:
        simulation.watch_quote(owner_id="g4-duplicate-exposure", symbol="3231")
        provider.emit(at=at)
        _wait_until(
            lambda: simulation.execution_admission_context(
                "3231",
                "BUY",
                max_book_age_seconds=simulation.max_book_age_seconds,
            )["executable_book_ready"]
            is True
        )
        composition.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="g4-duplicate-exposure-entry",
            holding_horizon="INTRADAY",
        )
        stale_open_row = simulation.exposures()[0]
        exposure_id = str(stale_open_row["exposure_id"])
        composition.local_paper_commands.submit_order(
            symbol="3231",
            side="SELL",
            lots=1,
            limit_price="105",
            idempotency_key="g4-duplicate-exposure-close",
            target_exposure_id=exposure_id,
        )

        class _DuplicateExposureRows:
            def exposures(self):
                zero_row = dict(stale_open_row)
                zero_row["quantity"] = 0
                return [dict(stale_open_row), zero_row]

            def orders(self):
                return simulation.orders()

            def no_overnight_reconciliation_context(self):
                return simulation.no_overnight_reconciliation_context()

        reader = _reader(composition, _DuplicateExposureRows())
        with pytest.raises(ValueError, match="exposure identity is duplicated"):
            reader.read(now=at, session_date=at.date())

        calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
        for _ in range(2):
            restarted = NoOvernightController(
                config=_runtime_config(),
                calendar=calendar,
                journal=composition.journal,
                evidence_reader=reader,
            )
            with pytest.raises(
                ValueError,
                match="exposure identity is duplicated",
            ):
                restarted.run_once(at)
    finally:
        composition.close()
