from dataclasses import replace
from datetime import datetime

import pytest

from trading.journal import (
    InMemoryJournalRepository,
    JournalConflictError,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.migrations import migration_files


AT = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
SESSION = JournalSession(
    session_id="local-paper-20260818",
    started_at=AT,
    mode="LOCAL_PAPER",
    metadata={"provider": "MockProvider", "config_version": "foundation_v0"},
)


def record(*, payload: dict[str, object] | None = None) -> JournalRecord:
    return JournalRecord(
        record_id="manual-buy-1",
        session_id=SESSION.session_id,
        kind="command_record",
        occurred_at=AT,
        payload=payload or {"symbol": "2330", "side": "BUY"},
        idempotency_scope=f"{SESSION.session_id}:manual_order",
        idempotency_key="browser-1",
    )


def test_append_is_ordered_and_matching_retries_return_original_sequence() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)

    first = journal.append(record())
    retried = journal.append(record())

    assert first.sequence == 1
    assert first.idempotent is False
    assert retried.sequence == 1
    assert retried.idempotent is True
    assert journal.records(SESSION.session_id) == (first,)


def test_conflicting_record_or_idempotency_key_fails_closed() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)
    journal.append(record())

    with pytest.raises(JournalConflictError, match="conflicts"):
        journal.append(replace(record(), payload={"symbol": "2317", "side": "BUY"}))


def test_checkpoints_only_advance_and_can_be_resumed_from_sequence() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)
    first = journal.append(record())
    second = journal.append(
        replace(
            record(),
            record_id="manual-buy-2",
            idempotency_key="browser-2",
        )
    )
    checkpoint = ProjectionCheckpoint(
        session_id=SESSION.session_id,
        projection_name="local_paper",
        journal_sequence=first.sequence,
        digest="before-second-record",
    )

    journal.save_checkpoint(checkpoint)

    assert journal.latest_checkpoint(SESSION.session_id, "local_paper") == checkpoint
    assert journal.records(SESSION.session_id, after_sequence=first.sequence) == (second,)
    with pytest.raises(JournalConflictError, match="cannot move backward"):
        journal.save_checkpoint(
            replace(checkpoint, journal_sequence=0, digest="stale-checkpoint")
        )


def test_session_must_exist_and_journal_timestamps_must_be_aware() -> None:
    journal = InMemoryJournalRepository()
    with pytest.raises(JournalConflictError, match="must be started"):
        journal.append(record())

    with pytest.raises(ValueError, match="timezone-aware"):
        JournalRecord(
            record_id="bad-time",
            session_id=SESSION.session_id,
            kind="event",
            occurred_at=datetime(2026, 8, 18, 9, 0),
            payload={},
        )


def test_forward_migration_is_discoverable_from_the_installed_package() -> None:
    assert [path.name for path in migration_files()] == ["001_journal.sql"]
