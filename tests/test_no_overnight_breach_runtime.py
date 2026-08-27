from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest

from config import twse_calendar_2026
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from market_data.equity_calendar import ReviewedEquityCalendar
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight import (
    ExecutionFactReference,
    LocalPaperExecutionAdmissionReader,
    NoOvernightBreachConflict,
    NoOvernightController,
    NoOvernightEvidenceBundle,
    no_overnight_session_id,
)
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)
from trading.journal import ProjectionCheckpoint
from trading.no_overnight import (
    ManagedExposureEvidence,
    NoOvernightEvidence,
    ReconciliationStatus,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionReason,
    ExecutionAdmissionStatus,
)
from trading.no_overnight_journal import (
    NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
    NO_OVERNIGHT_BREACH_KIND,
    NO_OVERNIGHT_BREACH_RESOLVED_KIND,
    NO_OVERNIGHT_PROJECTION_NAME,
    breach_id_for,
    rebuild_no_overnight_projection,
)
from trading.risk import CommandOrigin, CommandSide, OrderCommand


ORIGIN_DATE = date(2026, 8, 24)


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


class CountingCommandPort:
    def execute(self, action: object) -> bool:
        return False


class HealthyGuard:
    guard_identity = "test-postgres-guard"

    def is_owned_and_healthy(self) -> bool:
        return True

    def execute_if_owned(self, operation):
        return operation()


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class MutableBreachEvidenceReader:
    def __init__(self) -> None:
        self.quantity = 1000
        self.source_sequence = 10
        self.reconciliation_digest = "d" * 64
        self.entry_session_date = ORIGIN_DATE

    def set_flat(self) -> None:
        self.quantity = 0
        self.source_sequence = 11
        self.reconciliation_digest = "e" * 64

    def set_late_open(self) -> None:
        self.quantity = 100
        self.source_sequence = 12
        self.reconciliation_digest = "f" * 64

    def set_new_session_open(self, session_date: date) -> None:
        self.quantity = 200
        self.source_sequence = 13
        self.reconciliation_digest = "1" * 64
        self.entry_session_date = session_date

    def read(
        self,
        *,
        now: datetime,
        session_date: date,
    ) -> NoOvernightEvidenceBundle:
        fact = ExecutionFactReference(
            self.source_sequence,
            "local_paper_fill.v2",
            f"fill-{self.source_sequence}",
            self.entry_session_date,
        )
        evidence = NoOvernightEvidence(
            session_date=session_date,
            managed_exposures=(
                ManagedExposureEvidence(
                    exposure_id="managed-exposure-1",
                    current_quantity=self.quantity,
                    max_quantity_during_session=1000,
                    authoritative_open_fill_quantity=1000,
                    authoritative_close_fill_quantity=1000 - self.quantity,
                ),
            ),
            pending_entry_quantity=(),
            pending_exit_quantity=(),
            unresolved_execution_ids=(),
            reconciliation_status=ReconciliationStatus.MATCH,
            reconciliation_digest=self.reconciliation_digest,
            last_fill_journal_sequence=self.source_sequence,
            last_execution_fact_journal_sequence=self.source_sequence,
            snapshot_covers_through_journal_sequence=self.source_sequence,
            snapshot_journal_sequence=0,
            snapshot_source_as_of=now,
            snapshot_received_at=now,
        )
        return NoOvernightEvidenceBundle(
            evidence=evidence,
            execution_facts=(fact,),
            prior_session_execution_facts=(
                (fact,) if self.entry_session_date < session_date else ()
            ),
        )


class ReadyExecutionContext:
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


def _buy(at: datetime) -> OrderCommand:
    exposure = build_exposure_identity(
        account_scope_id=_config().account_scope_id,
        policy_family_id=_config().policy_family_id,
        owner_origin=CommandOrigin.MANUAL_WEB.value,
        owner_id="manual-web",
        holding_horizon=HoldingHorizon.LONG_TERM,
        entry_session_date=at.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
        entry_identity=f"buy-{at.date().isoformat()}",
    )
    return OrderCommand(
        command_id=f"buy-{at.date().isoformat()}",
        session_id="local-paper-v2",
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.BUY,
        quantity_shares=1000,
        limit_price=Decimal("106"),
        idempotency_key=f"buy-{at.date().isoformat()}",
        requested_at=at,
        exposure=exposure,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )


def _controller(
    journal: InMemoryJournalRepository,
    reader: MutableBreachEvidenceReader,
    guard: HealthyGuard,
    config: NoOvernightPolicyConfig | None = None,
) -> NoOvernightController:
    return NoOvernightController(
        config=config or _config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        evidence_reader=reader,
        command_port=CountingCommandPort(),
        guard=guard,
        deployment_manifest_digest="d" * 64,
    )


def _admission(
    journal: InMemoryJournalRepository,
    guard: HealthyGuard | None,
    at: datetime,
    *,
    config: NoOvernightPolicyConfig | None = None,
):
    return LocalPaperExecutionAdmissionReader(
        config=config or _config(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        journal=journal,
        clock=MutableClock(at),
        simulation=ReadyExecutionContext(),
        guard=guard,
    ).read_at(_buy(at), evaluated_at=at)


def test_resolution_and_ack_release_only_in_next_reviewed_session() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)

    breached = controller.run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert breached["breach"]["open"] is True
    breach_id = breached["breach"]["breach_id"]
    assert breached["breach"]["breach_revision"] == 1

    reader.set_flat()
    resolution_day = datetime.fromisoformat("2026-08-25T09:05:00+08:00")
    resolved = controller.run_once(resolution_day)
    assert resolved["breach"]["resolved"] is True
    assert resolved["breach"]["acknowledged"] is False
    assert resolved["breach"]["breach_revision"] == 2

    same_day_before_ack = _admission(journal, guard, resolution_day)
    assert same_day_before_ack.status is ExecutionAdmissionStatus.BLOCKED
    assert same_day_before_ack.reasons == (ExecutionAdmissionReason.OPEN_BREACH,)

    acknowledged = controller.acknowledge_breach(
        breach_id=breach_id,
        breach_revision=2,
        reconciliation_digest="e" * 64,
        actor_id="local-operator",
        idempotency_key="ack-breach-revision-2",
        acknowledged_at=datetime.fromisoformat("2026-08-25T09:06:00+08:00"),
    )
    assert acknowledged["acknowledged"] is True
    before_retry = len(journal.records(no_overnight_session_id(ORIGIN_DATE)))
    retried = controller.acknowledge_breach(
        breach_id=breach_id,
        breach_revision=2,
        reconciliation_digest="e" * 64,
        actor_id="local-operator",
        idempotency_key="ack-breach-revision-2",
        acknowledged_at=datetime.fromisoformat("2026-08-25T09:07:00+08:00"),
    )
    assert retried["idempotent"] is True
    assert len(journal.records(no_overnight_session_id(ORIGIN_DATE))) == before_retry
    assert _admission(journal, guard, resolution_day).status is (
        ExecutionAdmissionStatus.BLOCKED
    )

    next_session = datetime.fromisoformat("2026-08-26T09:05:00+08:00")
    controller.run_once(next_session)
    released = _admission(journal, guard, next_session)
    assert released.status is ExecutionAdmissionStatus.APPROVED
    assert released.snapshot.breach_latched is False

    restarted = _controller(journal, reader, guard)
    restarted.run_once(next_session)
    assert _admission(journal, guard, next_session).status is (
        ExecutionAdmissionStatus.APPROVED
    )

    reader.set_new_session_open(next_session.date())
    controller.run_once(datetime.fromisoformat("2026-08-26T09:10:00+08:00"))
    historical = rebuild_no_overnight_projection(
        journal,
        session_id=no_overnight_session_id(ORIGIN_DATE),
        require_checkpoint=True,
    )
    assert historical.breach_revision == 2
    assert historical.breach_acknowledged is True
    assert (
        _admission(
            journal,
            guard,
            datetime.fromisoformat("2026-08-26T09:10:00+08:00"),
        ).status
        is ExecutionAdmissionStatus.APPROVED
    )


def test_non_enforcing_downgrade_keeps_acknowledged_breach_latched_on_weekend() -> (
    None
):
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)
    breached = controller.run_once(
        datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    )
    reader.set_flat()
    controller.run_once(datetime.fromisoformat("2026-08-25T09:05:00+08:00"))
    controller.acknowledge_breach(
        breach_id=str(dict(breached["breach"])["breach_id"]),
        breach_revision=2,
        reconciliation_digest="e" * 64,
        actor_id="local-operator",
        idempotency_key="ack-before-weekend-downgrade",
        acknowledged_at=datetime.fromisoformat("2026-08-25T09:06:00+08:00"),
    )
    disabled = NoOvernightPolicyConfig.disabled(
        account_scope_id=_config().account_scope_id,
        policy_family_id=_config().policy_family_id,
    )

    weekend = _admission(
        journal,
        None,
        datetime.fromisoformat("2026-08-29T09:05:00+08:00"),
        config=disabled,
    )
    next_reviewed_session = _admission(
        journal,
        None,
        datetime.fromisoformat("2026-08-31T09:05:00+08:00"),
        config=disabled,
    )

    assert weekend.status is ExecutionAdmissionStatus.BLOCKED
    assert weekend.reasons == (ExecutionAdmissionReason.OPEN_BREACH,)
    assert weekend.snapshot.breach_latched is True
    assert next_reviewed_session.status is ExecutionAdmissionStatus.APPROVED
    assert next_reviewed_session.snapshot.breach_latched is False


def test_late_fact_creates_new_revision_and_stale_ack_is_zero_mutation() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)
    first = controller.run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    breach_id = first["breach"]["breach_id"]
    reader.set_flat()
    controller.run_once(datetime.fromisoformat("2026-08-25T09:05:00+08:00"))
    controller.acknowledge_breach(
        breach_id=breach_id,
        breach_revision=2,
        reconciliation_digest="e" * 64,
        actor_id="local-operator",
        idempotency_key="ack-before-late-fill",
        acknowledged_at=datetime.fromisoformat("2026-08-25T09:06:00+08:00"),
    )

    reader.set_late_open()
    revised = controller.run_once(datetime.fromisoformat("2026-08-25T09:10:00+08:00"))
    assert revised["breach"]["breach_revision"] == 3
    assert revised["breach"]["resolved"] is False
    assert revised["breach"]["acknowledged"] is False
    before_records = len(journal.records(no_overnight_session_id(ORIGIN_DATE)))

    with pytest.raises(NoOvernightBreachConflict) as caught:
        controller.acknowledge_breach(
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            actor_id="local-operator",
            idempotency_key="stale-ack-after-late-fill",
            acknowledged_at=datetime.fromisoformat("2026-08-25T09:11:00+08:00"),
        )

    assert caught.value.code == "STALE_BREACH_REVISION"
    assert len(journal.records(no_overnight_session_id(ORIGIN_DATE))) == before_records
    recovered = rebuild_no_overnight_projection(
        journal,
        session_id=no_overnight_session_id(ORIGIN_DATE),
        require_checkpoint=True,
    )
    assert recovered.breach_revision == 3
    assert recovered.breach_acknowledged is False


def test_same_session_late_close_resolves_new_revision_without_releasing_latch() -> (
    None
):
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)
    first = controller.run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    assert first["breach"]["breach_revision"] == 1

    reader.set_flat()
    resolved = controller.run_once(datetime.fromisoformat("2026-08-24T13:31:00+08:00"))

    assert resolved["breach"]["breach_revision"] == 2
    assert resolved["breach"]["resolved"] is True
    assert resolved["breach"]["open"] is True


def test_restart_fails_closed_when_historical_breach_checkpoint_is_missing() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)
    controller.run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))
    journal._checkpoints.pop((no_overnight_session_id(ORIGIN_DATE), "no_overnight.v1"))

    reader.set_flat()
    restarted = _controller(journal, reader, guard)
    with pytest.raises(ValueError, match="requires a checkpoint"):
        restarted.run_once(datetime.fromisoformat("2026-08-25T09:05:00+08:00"))


def test_prior_breach_refresh_preserves_originating_policy_after_upgrade() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    original_config = _config()
    _controller(journal, reader, guard, original_config).run_once(
        datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    )

    reader.set_flat()
    upgraded_config = replace(original_config, policy_version="enforcing-v2")
    status = _controller(journal, reader, guard, upgraded_config).run_once(
        datetime.fromisoformat("2026-08-25T09:05:00+08:00")
    )
    recovered = rebuild_no_overnight_projection(
        journal,
        session_id=no_overnight_session_id(ORIGIN_DATE),
        require_checkpoint=True,
    )

    assert recovered.policy_version == original_config.policy_version
    assert recovered.policy_digest == original_config.policy_digest
    assert recovered.breach_revision == 2
    assert recovered.breach_resolved is True
    assert status["breach"]["breach_revision"] == 2
    revisions = [
        appended.record.payload
        for appended in journal.records(no_overnight_session_id(ORIGIN_DATE))
        if appended.record.kind == NO_OVERNIGHT_BREACH_KIND
    ]
    assert {payload["policy_version"] for payload in revisions} == {
        original_config.policy_version
    }
    assert {payload["policy_digest"] for payload in revisions} == {
        original_config.policy_digest
    }


def test_pr_no_004_legacy_breach_bootstraps_before_cross_day_refresh() -> None:
    source = InMemoryJournalRepository()
    source_reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    original_config = _config()
    _controller(source, source_reader, guard, original_config).run_once(
        datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    )
    origin_session_id = no_overnight_session_id(ORIGIN_DATE)
    origin_session = source.session(origin_session_id)
    assert origin_session is not None

    legacy = InMemoryJournalRepository()
    legacy.start_session(origin_session)
    g5_kinds = {
        NO_OVERNIGHT_BREACH_KIND,
        NO_OVERNIGHT_BREACH_RESOLVED_KIND,
        NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
    }
    for appended in source.records(origin_session_id):
        if appended.record.kind not in g5_kinds:
            legacy.append(appended.record)
    legacy_projection = rebuild_no_overnight_projection(
        legacy,
        session_id=origin_session_id,
        require_checkpoint=False,
    )
    legacy.save_checkpoint(
        ProjectionCheckpoint(
            session_id=origin_session_id,
            projection_name=NO_OVERNIGHT_PROJECTION_NAME,
            journal_sequence=legacy_projection.last_sequence,
            digest=legacy_projection.legacy_digest,
        )
    )

    next_reader = MutableBreachEvidenceReader()
    next_reader.set_flat()
    upgraded_config = replace(original_config, policy_version="enforcing-v2")
    status = _controller(legacy, next_reader, guard, upgraded_config).run_once(
        datetime.fromisoformat("2026-08-25T09:05:00+08:00")
    )
    recovered = rebuild_no_overnight_projection(
        legacy,
        session_id=origin_session_id,
        require_checkpoint=True,
    )

    expected_breach_id = breach_id_for(
        account_scope_id=_config().account_scope_id,
        policy_family_id=_config().policy_family_id,
        originating_session_date=ORIGIN_DATE,
    )
    assert recovered.breach_id == expected_breach_id
    assert recovered.policy_version == original_config.policy_version
    assert recovered.policy_digest == original_config.policy_digest
    assert recovered.breach_revision == 2
    assert recovered.breach_resolved is True
    assert status["breach"]["breach_id"] == expected_breach_id
    revisions = [
        appended.record.payload
        for appended in legacy.records(origin_session_id)
        if appended.record.kind == NO_OVERNIGHT_BREACH_KIND
    ]
    assert [payload["breach_revision"] for payload in revisions] == [1, 2]
    assert {payload["policy_version"] for payload in revisions} == {
        original_config.policy_version
    }
    assert {payload["policy_digest"] for payload in revisions} == {
        original_config.policy_digest
    }
    assert revisions[0]["source_result_journal_sequence"] > 0


def test_historical_policy_conflict_fails_before_breach_append() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    original_config = _config()
    _controller(journal, reader, guard, original_config).run_once(
        datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    )
    origin_session_id = no_overnight_session_id(ORIGIN_DATE)
    origin_session = journal.session(origin_session_id)
    assert origin_session is not None
    journal._sessions[origin_session_id] = replace(
        origin_session,
        metadata={
            **origin_session.metadata,
            "policy_version": "enforcing-v2",
        },
    )
    historical_records_before = journal.records(origin_session_id)

    reader.set_flat()
    upgraded_config = replace(original_config, policy_version="enforcing-v2")
    with pytest.raises(
        ValueError,
        match="no-overnight projection/session policy mismatch",
    ):
        _controller(journal, reader, guard, upgraded_config).run_once(
            datetime.fromisoformat("2026-08-25T09:05:00+08:00")
        )

    assert journal.records(origin_session_id) == historical_records_before


def test_acknowledging_later_breach_keeps_earliest_open_breach_in_status() -> None:
    journal = InMemoryJournalRepository()
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    controller = _controller(journal, reader, guard)
    controller.run_once(datetime.fromisoformat("2026-08-24T13:30:00+08:00"))

    second_date = date(2026, 8, 25)
    reader.set_new_session_open(second_date)
    controller.run_once(datetime.fromisoformat("2026-08-25T13:30:00+08:00"))
    reader.quantity = 0
    reader.source_sequence = 14
    reader.reconciliation_digest = "e" * 64
    controller.run_once(datetime.fromisoformat("2026-08-26T09:05:00+08:00"))

    second = rebuild_no_overnight_projection(
        journal,
        session_id=no_overnight_session_id(second_date),
        require_checkpoint=True,
    )
    assert second.breach_id is not None
    assert second.breach_reconciliation_digest is not None
    assert second.breach_resolved is True
    acknowledged = controller.acknowledge_breach(
        breach_id=second.breach_id,
        breach_revision=second.breach_revision,
        reconciliation_digest=second.breach_reconciliation_digest,
        actor_id="local-operator",
        idempotency_key="ack-second-breach-first",
        acknowledged_at=datetime.fromisoformat("2026-08-26T09:06:00+08:00"),
    )

    assert acknowledged["breach_id"] == second.breach_id
    assert acknowledged["release_requires_later_reviewed_session"] is True
    displayed = controller.status()["breach"]
    assert displayed["originating_session_date"] == ORIGIN_DATE.isoformat()
    assert displayed["breach_id"] != second.breach_id
