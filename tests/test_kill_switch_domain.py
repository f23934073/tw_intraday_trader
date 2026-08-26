from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from runtime.in_memory import InMemoryJournalRepository
from trading.journal import (
    JOURNAL_SCHEMA_VERSION,
    JournalAppendResult,
    JournalRecord,
    JournalSession,
)
from trading.kill_switch import (
    KILL_SWITCH_CONTRACT_VERSION,
    KILL_SWITCH_CONTROL_METADATA,
    KILL_SWITCH_CONTROL_MODE,
    KILL_SWITCH_CONTROL_SESSION_ID,
    KILL_SWITCH_ENGAGED_KIND,
    KILL_SWITCH_EXECUTION_BOUNDARY,
    KILL_SWITCH_IDEMPOTENCY_SCOPE,
    KillSwitchAction,
    KillSwitchControlState,
    KillSwitchOperationConflict,
    KillSwitchReplayError,
    kill_switch_control_session,
    kill_switch_record,
    matching_operation_receipt,
    replay_kill_switch,
)


TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=TAIPEI)


def _journal() -> tuple[InMemoryJournalRepository, JournalSession]:
    journal = InMemoryJournalRepository()
    session = kill_switch_control_session(started_at=NOW)
    journal.start_session(session)
    return journal, session


def _append(
    journal: InMemoryJournalRepository,
    *,
    action: KillSwitchAction,
    operation_id: str,
    reason: str,
    prior_revision: int,
    seconds: int,
    actor_id: str = "local-operator",
) -> JournalAppendResult:
    return journal.append(
        kill_switch_record(
            action=action,
            operation_id=operation_id,
            actor_id=actor_id,
            reason=reason,
            prior_revision=prior_revision,
            occurred_at=NOW + timedelta(seconds=seconds),
        )
    )


def test_empty_control_journal_is_revision_zero_disengaged() -> None:
    journal, session = _journal()
    stored_session = journal.session(session.session_id)
    assert stored_session is not None

    projected = replay_kill_switch(
        stored_session,
        journal.records(session.session_id),
    )

    assert projected.control_state is KillSwitchControlState.DISENGAGED
    assert projected.revision == 0
    assert projected.engaged is False
    assert projected.admission_blocked is False
    assert projected.last_journal_sequence == 0
    assert projected.operation_receipts == {}


def test_engage_reaffirm_and_reset_replay_is_deterministic() -> None:
    journal, session = _journal()
    _append(
        journal,
        action=KillSwitchAction.ENGAGE,
        operation_id="engage-1",
        reason="行情異常",
        prior_revision=0,
        seconds=1,
    )
    _append(
        journal,
        action=KillSwitchAction.ENGAGE,
        operation_id="engage-2",
        reason="再次確認停止",
        prior_revision=1,
        seconds=2,
        actor_id="second-operator",
    )
    _append(
        journal,
        action=KillSwitchAction.RESET,
        operation_id="reset-1",
        reason="檢查完成",
        prior_revision=2,
        seconds=3,
        actor_id="second-operator",
    )

    first = replay_kill_switch(session, journal.records(session.session_id))
    second = replay_kill_switch(session, journal.records(session.session_id))

    assert first == second
    assert first.control_state is KillSwitchControlState.DISENGAGED
    assert first.revision == 3
    assert first.reason is None
    assert first.engaged_at is None
    assert first.last_actor_id == "second-operator"
    assert first.last_operation_id == "reset-1"
    assert first.operation_receipts["engage-2"].prior_revision == 1
    assert (
        first.operation_receipts["reset-1"].resulting_state
        is KillSwitchControlState.DISENGAGED
    )


def test_canonical_record_has_global_idempotency_and_local_only_evidence() -> None:
    record = kill_switch_record(
        action=KillSwitchAction.ENGAGE,
        operation_id="  engage-canonical  ",
        actor_id="  local-operator  ",
        reason="  strategy anomaly  ",
        prior_revision=4,
        occurred_at=NOW,
    )

    assert record.record_id == "local-paper-kill-switch:engage-canonical"
    assert record.session_id == KILL_SWITCH_CONTROL_SESSION_ID
    assert record.kind == KILL_SWITCH_ENGAGED_KIND
    assert record.idempotency_scope == KILL_SWITCH_IDEMPOTENCY_SCOPE
    assert record.idempotency_key == "engage-canonical"
    assert record.occurred_at.tzinfo is not None
    assert record.payload == {
        "contract_version": KILL_SWITCH_CONTRACT_VERSION,
        "action": "ENGAGE",
        "operation_id": "engage-canonical",
        "actor_id": "local-operator",
        "reason": "strategy anomaly",
        "prior_revision": 4,
        "revision": 5,
        "resulting_state": "ENGAGED",
        "execution_boundary": KILL_SWITCH_EXECUTION_BOUNDARY,
    }


def test_matching_retry_returns_original_receipt_and_conflicts_fail_closed() -> None:
    journal, session = _journal()
    _append(
        journal,
        action=KillSwitchAction.ENGAGE,
        operation_id="retry-key",
        reason="halt",
        prior_revision=0,
        seconds=1,
    )
    projected = replay_kill_switch(session, journal.records(session.session_id))

    receipt = matching_operation_receipt(
        projected,
        action=KillSwitchAction.ENGAGE,
        operation_id="retry-key",
        actor_id="local-operator",
        reason="halt",
    )

    assert receipt is projected.operation_receipts["retry-key"]
    assert receipt.revision == 1
    for conflict in (
        {"action": KillSwitchAction.RESET, "expected_revision": 0},
        {"actor_id": "other-operator"},
        {"reason": "different halt"},
    ):
        request = {
            "action": KillSwitchAction.ENGAGE,
            "operation_id": "retry-key",
            "actor_id": "local-operator",
            "reason": "halt",
            "expected_revision": None,
            **conflict,
        }
        with pytest.raises(KillSwitchOperationConflict):
            matching_operation_receipt(projected, **request)


def test_reset_retry_semantics_include_the_exact_prior_revision() -> None:
    journal, session = _journal()
    _append(
        journal,
        action=KillSwitchAction.ENGAGE,
        operation_id="engage",
        reason="halt",
        prior_revision=0,
        seconds=1,
    )
    _append(
        journal,
        action=KillSwitchAction.RESET,
        operation_id="reset",
        reason="reviewed",
        prior_revision=1,
        seconds=2,
    )
    projected = replay_kill_switch(session, journal.records(session.session_id))

    receipt = matching_operation_receipt(
        projected,
        action=KillSwitchAction.RESET,
        operation_id="reset",
        actor_id="local-operator",
        reason="reviewed",
        expected_revision=1,
    )

    assert receipt is not None
    with pytest.raises(KillSwitchOperationConflict):
        matching_operation_receipt(
            projected,
            action=KillSwitchAction.RESET,
            operation_id="reset",
            actor_id="local-operator",
            reason="reviewed",
            expected_revision=2,
        )


@pytest.mark.parametrize(
    "records",
    [
        [
            kill_switch_record(
                action=KillSwitchAction.ENGAGE,
                operation_id="gap",
                actor_id="local-operator",
                reason="gap",
                prior_revision=2,
                occurred_at=NOW,
            )
        ],
        [
            JournalRecord(
                record_id="unknown",
                session_id=KILL_SWITCH_CONTROL_SESSION_ID,
                kind="unknown_control_event.v1",
                occurred_at=NOW,
                payload={},
            )
        ],
        [
            kill_switch_record(
                action=KillSwitchAction.RESET,
                operation_id="reset-without-engage",
                actor_id="local-operator",
                reason="invalid",
                prior_revision=0,
                occurred_at=NOW,
            )
        ],
    ],
)
def test_revision_gap_unknown_event_and_reset_without_engage_fail_closed(
    records: list[JournalRecord],
) -> None:
    session = kill_switch_control_session(started_at=NOW)
    appended = tuple(
        JournalAppendResult(record=record, sequence=index, idempotent=False)
        for index, record in enumerate(records, start=1)
    )

    with pytest.raises(KillSwitchReplayError):
        replay_kill_switch(session, appended)


def test_control_session_metadata_conflict_fails_closed() -> None:
    conflicting = JournalSession(
        session_id=KILL_SWITCH_CONTROL_SESSION_ID,
        started_at=NOW,
        mode=KILL_SWITCH_CONTROL_MODE,
        metadata={**KILL_SWITCH_CONTROL_METADATA, "writer_model": "MULTI_PROCESS"},
    )

    with pytest.raises(KillSwitchReplayError, match="metadata conflicts"):
        replay_kill_switch(conflicting, ())


def test_control_session_and_event_journal_schema_drift_fail_closed() -> None:
    unsupported_schema = f"{JOURNAL_SCHEMA_VERSION}-unsupported"
    conflicting_session = JournalSession(
        session_id=KILL_SWITCH_CONTROL_SESSION_ID,
        started_at=NOW,
        mode=KILL_SWITCH_CONTROL_MODE,
        metadata=KILL_SWITCH_CONTROL_METADATA,
        schema_version=unsupported_schema,
    )
    with pytest.raises(KillSwitchReplayError, match="session schema version"):
        replay_kill_switch(conflicting_session, ())

    session = kill_switch_control_session(started_at=NOW)
    canonical = kill_switch_record(
        action=KillSwitchAction.ENGAGE,
        operation_id="unsupported-record-schema",
        actor_id="local-operator",
        reason="schema drift",
        prior_revision=0,
        occurred_at=NOW,
    )
    unsupported_record = JournalRecord(
        record_id=canonical.record_id,
        session_id=canonical.session_id,
        kind=canonical.kind,
        occurred_at=canonical.occurred_at,
        payload=canonical.payload,
        idempotency_scope=canonical.idempotency_scope,
        idempotency_key=canonical.idempotency_key,
        schema_version=unsupported_schema,
    )
    with pytest.raises(KillSwitchReplayError, match="event schema version"):
        replay_kill_switch(
            session,
            (JournalAppendResult(unsupported_record, 1, False),),
        )


@pytest.mark.parametrize("field_name", ["operation_id", "actor_id", "reason"])
def test_noncanonical_control_payload_text_fails_closed(field_name: str) -> None:
    session = kill_switch_control_session(started_at=NOW)
    canonical = kill_switch_record(
        action=KillSwitchAction.ENGAGE,
        operation_id="canonical-operation",
        actor_id="local-operator",
        reason="canonical reason",
        prior_revision=0,
        occurred_at=NOW,
    )
    payload = dict(canonical.payload)
    payload[field_name] = f" {payload[field_name]} "
    malformed = JournalRecord(
        record_id=canonical.record_id,
        session_id=canonical.session_id,
        kind=canonical.kind,
        occurred_at=canonical.occurred_at,
        payload=payload,
        idempotency_scope=canonical.idempotency_scope,
        idempotency_key=canonical.idempotency_key,
    )

    with pytest.raises(KillSwitchReplayError, match=field_name):
        replay_kill_switch(
            session,
            (JournalAppendResult(malformed, 1, False),),
        )


def test_control_event_requires_timezone_aware_server_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        kill_switch_record(
            action=KillSwitchAction.ENGAGE,
            operation_id="naive",
            actor_id="local-operator",
            reason="invalid clock",
            prior_revision=0,
            occurred_at=datetime(2026, 8, 26, 10, 0),
        )
