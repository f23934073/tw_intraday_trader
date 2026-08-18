from datetime import datetime

from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.recovery import CommandRecoveryStatus, classify_command_recovery


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
SESSION_ID = "command-recovery-20260818"
COMMAND_ID = "command-1"


def journal() -> InMemoryJournalRepository:
    repository = InMemoryJournalRepository()
    repository.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER",
            metadata={},
        )
    )
    return repository


def append_command(repository: InMemoryJournalRepository, risk_status: str) -> None:
    repository.append(
        JournalRecord(
            record_id=f"command:{COMMAND_ID}",
            session_id=SESSION_ID,
            kind="order_command.v1",
            occurred_at=AT,
            payload={"command_id": COMMAND_ID, "risk_status": risk_status},
        )
    )


def test_missing_command_is_not_found() -> None:
    recovery = classify_command_recovery(
        journal(),
        session_id=SESSION_ID,
        command_id=COMMAND_ID,
    )

    assert recovery.status is CommandRecoveryStatus.NOT_FOUND
    assert recovery.reasons == ("command_not_found",)


def test_blocked_and_rejected_commands_are_terminal_without_handler_evidence() -> None:
    for risk_status, expected in (
        ("BLOCKED", CommandRecoveryStatus.BLOCKED),
        ("REJECTED", CommandRecoveryStatus.REJECTED),
    ):
        repository = journal()
        append_command(repository, risk_status)

        recovery = classify_command_recovery(
            repository,
            session_id=SESSION_ID,
            command_id=COMMAND_ID,
        )

        assert recovery.status is expected
        assert recovery.evidence_sequences == ()


def test_correlated_fill_proves_completed_local_paper_outcome() -> None:
    repository = journal()
    append_command(repository, "APPROVED")
    repository.append(
        JournalRecord(
            record_id="fill-1",
            session_id=SESSION_ID,
            kind="local_paper_fill.v1",
            occurred_at=AT,
            payload={"command_id": COMMAND_ID, "order_id": "paper-1"},
        )
    )

    recovery = classify_command_recovery(
        repository,
        session_id=SESSION_ID,
        command_id=COMMAND_ID,
    )

    assert recovery.status is CommandRecoveryStatus.FILLED
    assert recovery.evidence_sequences == (2,)


def test_unproven_or_handler_failure_outcome_remains_recovery_required() -> None:
    repository = journal()
    append_command(repository, "APPROVED")
    repository.append(
        JournalRecord(
            record_id="handler-failure-1",
            session_id=SESSION_ID,
            kind="order_handler_failure.v1",
            occurred_at=AT,
            payload={"command_id": COMMAND_ID},
        )
    )
    repository.append(
        JournalRecord(
            record_id="unrelated-fill-1",
            session_id=SESSION_ID,
            kind="local_paper_fill.v1",
            occurred_at=AT,
            payload={"command_id": "other-command", "order_id": "paper-2"},
        )
    )

    recovery = classify_command_recovery(
        repository,
        session_id=SESSION_ID,
        command_id=COMMAND_ID,
    )

    assert recovery.status is CommandRecoveryStatus.RECOVERY_REQUIRED
    assert recovery.evidence_sequences == (2,)
    assert recovery.reasons == ("outcome_not_proven", "handler_failure_recorded")
