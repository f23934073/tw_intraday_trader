from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from simulation.kill_switch import (
    DurableLocalPaperKillSwitch,
    KillSwitchAdmissionBlocked,
    KillSwitchPersistenceUnavailable,
    KillSwitchStateConflict,
)
from trading.journal import (
    JournalAppendResult,
    JournalConflictError,
    JournalRecord,
    JournalSession,
)
from trading.kill_switch import (
    KILL_SWITCH_CONTROL_METADATA,
    KILL_SWITCH_CONTROL_MODE,
    KILL_SWITCH_CONTROL_SESSION_ID,
    KillSwitchAction,
    KillSwitchContractError,
    KillSwitchOperationConflict,
    kill_switch_control_session,
    kill_switch_record,
)


TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=TAIPEI)


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def session_date(self) -> date:
        return NOW.date()


class FailingAppendJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_append = False

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if self.fail_append:
            raise RuntimeError("injected append failure")
        return super().append(record)


class SemanticConflictJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.inject_conflict = False

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if self.inject_conflict:
            self.inject_conflict = False
            super().append(
                kill_switch_record(
                    action=KillSwitchAction.ENGAGE,
                    operation_id=str(record.idempotency_key),
                    actor_id="durable-operator",
                    reason="durable emergency stop",
                    prior_revision=0,
                    occurred_at=NOW,
                )
            )
            raise JournalConflictError("injected semantic conflict")
        return super().append(record)


def _service(
    journal: InMemoryJournalRepository | None = None,
) -> tuple[DurableLocalPaperKillSwitch, InMemoryJournalRepository]:
    resolved = journal or InMemoryJournalRepository()
    return (
        DurableLocalPaperKillSwitch.recover(
            journal=resolved,
            clock=FixedClock(),
        ),
        resolved,
    )


def test_memory_service_is_explicitly_ephemeral_and_restart_unsafe() -> None:
    service, _ = _service()

    assert service.status() == {
        "control_state": "DISENGAGED",
        "engaged": False,
        "revision": 0,
        "reason": None,
        "engaged_at": None,
        "last_transition_at": None,
        "last_actor_id": None,
        "last_operation_id": None,
        "durability": "EPHEMERAL_MEMORY",
        "restart_safe": False,
        "recovered": False,
        "recovery_error": None,
    }


def test_engage_retry_conflict_stale_reset_and_valid_reset() -> None:
    service, journal = _service()

    engaged = service.engage(
        actor_id="local-operator",
        operation_id="engage-1",
        reason="行情異常",
    )
    retry = service.engage(
        actor_id="local-operator",
        operation_id="engage-1",
        reason="行情異常",
    )

    assert engaged["kill_switch"]["revision"] == 1
    assert engaged["operation"]["idempotent"] is False
    assert retry["operation"] == {**engaged["operation"], "idempotent": True}
    assert len(journal.records(KILL_SWITCH_CONTROL_SESSION_ID)) == 1
    with pytest.raises(KillSwitchOperationConflict):
        service.engage(
            actor_id="another-operator",
            operation_id="engage-1",
            reason="行情異常",
        )
    with pytest.raises(KillSwitchStateConflict, match="revision is stale"):
        service.reset(
            actor_id="local-operator",
            operation_id="stale-reset",
            reason="checked",
            expected_revision=0,
        )
    assert service.status()["control_state"] == "ENGAGED"

    reset = service.reset(
        actor_id="local-operator",
        operation_id="reset-1",
        reason="checked",
        expected_revision=1,
    )

    assert reset["kill_switch"]["control_state"] == "DISENGAGED"
    assert reset["kill_switch"]["revision"] == 2
    old_engage_retry = service.engage(
        actor_id="local-operator",
        operation_id="engage-1",
        reason="行情異常",
    )
    assert old_engage_retry["kill_switch"]["control_state"] == "DISENGAGED"
    assert old_engage_retry["kill_switch"]["revision"] == 2
    assert old_engage_retry["operation"]["operation_revision"] == 1
    assert old_engage_retry["operation"]["idempotent"] is True
    with pytest.raises(KillSwitchStateConflict, match="not engaged"):
        service.reset(
            actor_id="local-operator",
            operation_id="new-reset",
            reason="checked",
            expected_revision=2,
        )
    with pytest.raises(KillSwitchContractError):
        service.reset(
            actor_id="local-operator",
            operation_id="invalid-reset-revision",
            reason="invalid",
            expected_revision=True,
        )
    service.engage(
        actor_id="local-operator",
        operation_id="engage-2",
        reason="newer incident",
    )

    old_reset_retry = service.reset(
        actor_id="local-operator",
        operation_id="reset-1",
        reason="checked",
        expected_revision=1,
    )

    assert old_reset_retry["kill_switch"]["control_state"] == "ENGAGED"
    assert old_reset_retry["kill_switch"]["revision"] == 3
    assert old_reset_retry["operation"]["operation_revision"] == 2
    assert old_reset_retry["operation"]["idempotent"] is True


def test_same_journal_recovery_preserves_engaged_and_reset_states() -> None:
    first, journal = _service()
    first.engage(
        actor_id="local-operator",
        operation_id="engage-restart",
        reason="restart test",
    )

    second, _ = _service(journal)

    assert second.status()["control_state"] == "ENGAGED"
    assert second.status()["revision"] == 1
    assert second.status()["recovered"] is True
    with pytest.raises(KillSwitchAdmissionBlocked):
        second.assert_start_allowed()
    second.reset(
        actor_id="local-operator",
        operation_id="reset-restart",
        reason="review complete",
        expected_revision=1,
    )

    third, _ = _service(journal)

    assert third.status()["control_state"] == "DISENGAGED"
    assert third.status()["revision"] == 2
    third.assert_start_allowed()


def test_settings_session_rotation_uses_the_same_global_control_revision() -> None:
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        clock=FixedClock(),
        local_paper_session_id="local-paper-settings-before",
        start_simulation_streaming=False,
    )
    first.kill_switch.engage(
        actor_id="local-operator",
        operation_id="engage-before-settings",
        reason="keep blocked",
    )

    replacement = RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        clock=FixedClock(),
        local_paper_session_id="local-paper-settings-after",
        start_simulation_streaming=False,
    )

    assert replacement.local_paper_commands.session_id == "local-paper-settings-after"
    assert replacement.kill_switch.status()["control_state"] == "ENGAGED"
    assert replacement.kill_switch.status()["revision"] == 1
    assert len(journal.records(KILL_SWITCH_CONTROL_SESSION_ID)) == 1
    first.simulation_service.close()
    replacement.simulation_service.close()


def test_malformed_replay_enters_recovery_required_and_blocks_all_admission() -> None:
    journal = InMemoryJournalRepository()
    session = kill_switch_control_session(started_at=NOW)
    journal.start_session(session)
    journal.append(
        kill_switch_record(
            action=KillSwitchAction.ENGAGE,
            operation_id="revision-gap",
            actor_id="local-operator",
            reason="corrupt",
            prior_revision=4,
            occurred_at=NOW,
        )
    )

    service, _ = _service(journal)

    assert service.status()["control_state"] == "RECOVERY_REQUIRED"
    assert service.status()["engaged"] is True
    assert service.status()["revision"] is None
    assert service.status()["recovery_error"].startswith("KillSwitchReplayError:")
    with pytest.raises(KillSwitchPersistenceUnavailable):
        service.assert_start_allowed()
    with pytest.raises(KillSwitchPersistenceUnavailable):
        service.reset(
            actor_id="local-operator",
            operation_id="reset-corrupt",
            reason="must not clear",
            expected_revision=0,
        )


def test_control_session_metadata_conflict_enters_recovery_required() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=KILL_SWITCH_CONTROL_SESSION_ID,
            started_at=NOW,
            mode=KILL_SWITCH_CONTROL_MODE,
            metadata={**KILL_SWITCH_CONTROL_METADATA, "writer_model": "MULTI_PROCESS"},
        )
    )

    service, _ = _service(journal)

    assert service.status()["control_state"] == "RECOVERY_REQUIRED"
    assert service.status()["restart_safe"] is False


def test_append_failure_enters_blocking_recovery_without_false_transition() -> None:
    journal = FailingAppendJournal()
    service, _ = _service(journal)
    journal.fail_append = True

    with pytest.raises(KillSwitchPersistenceUnavailable, match="append failed"):
        service.engage(
            actor_id="local-operator",
            operation_id="failed-engage",
            reason="must fail closed",
        )

    assert service.status()["control_state"] == "RECOVERY_REQUIRED"
    assert journal.records(KILL_SWITCH_CONTROL_SESSION_ID) == ()


def test_semantic_conflict_synchronizes_durable_engagement_before_returning_409() -> None:
    journal = SemanticConflictJournal()
    service, _ = _service(journal)
    journal.inject_conflict = True

    with pytest.raises(KillSwitchOperationConflict):
        service.engage(
            actor_id="requesting-operator",
            operation_id="conflicting-engage",
            reason="different request semantics",
        )

    assert service.status()["control_state"] == "ENGAGED"
    assert service.status()["revision"] == 1
    assert service.status()["last_actor_id"] == "durable-operator"
    with pytest.raises(KillSwitchAdmissionBlocked):
        service.admit_automated_intent(lambda: None)


def test_final_admission_callback_is_not_run_while_engaged() -> None:
    service, _ = _service()
    service.engage(
        actor_id="local-operator",
        operation_id="engage-admission",
        reason="block callback",
    )
    called = False

    def operation() -> None:
        nonlocal called
        called = True

    with pytest.raises(KillSwitchAdmissionBlocked):
        service.admit_automated_intent(operation)

    assert called is False
