from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from trading.journal import (
    InMemoryJournalRepository,
    JournalClockRegressionError,
    JournalConflictError,
    JournalCutoffExceededError,
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


def test_atomic_session_and_record_use_accepted_time_and_retry_exactly() -> None:
    journal = InMemoryJournalRepository()
    requested_at = datetime.fromisoformat("2026-08-18T08:59:00+08:00")
    session = replace(SESSION, started_at=requested_at)
    open_record = replace(record(), occurred_at=requested_at)

    first = journal.start_session_and_append_before(
        session,
        open_record,
        latest_allowed_at=AT,
        authoritative_now=lambda: AT,
    )
    retried = journal.start_session_and_append_before(
        session,
        open_record,
        latest_allowed_at=AT,
        authoritative_now=lambda: AT,
    )

    assert journal.session(SESSION.session_id) == replace(session, started_at=AT)
    assert first.record.occurred_at == AT
    assert first.idempotent is False
    assert retried.sequence == first.sequence
    assert retried.idempotent is True


@pytest.mark.parametrize(
    "times",
    (
        (AT, datetime.fromisoformat("2026-08-18T09:00:00.000001+08:00")),
        (
            AT,
            AT,
            datetime.fromisoformat("2026-08-18T09:00:00.000001+08:00"),
        ),
    ),
)
def test_atomic_session_and_record_roll_back_if_operation_crosses_cutoff(
    times: tuple[datetime, ...],
) -> None:
    journal = InMemoryJournalRepository()
    observed_times = iter(times)

    with pytest.raises(JournalCutoffExceededError):
        journal.start_session_and_append_before(
            SESSION,
            record(),
            latest_allowed_at=AT,
            authoritative_now=lambda: next(observed_times),
        )

    assert journal.session(SESSION.session_id) is None
    assert journal.records(SESSION.session_id) == ()


@pytest.mark.parametrize(
    "times",
    (
        (
            AT,
            datetime.fromisoformat("2026-08-18T08:59:59.999999+08:00"),
        ),
        (
            AT,
            AT,
            datetime.fromisoformat("2026-08-18T08:59:59.999999+08:00"),
        ),
    ),
)
def test_atomic_session_and_record_roll_back_if_clock_moves_backwards(
    times: tuple[datetime, ...],
) -> None:
    journal = InMemoryJournalRepository()
    observed_times = iter(times)

    with pytest.raises(JournalClockRegressionError, match="moved backwards"):
        journal.start_session_and_append_before(
            SESSION,
            record(),
            latest_allowed_at=AT,
            authoritative_now=lambda: next(observed_times),
        )

    assert journal.session(SESSION.session_id) is None
    assert journal.records(SESSION.session_id) == ()


def test_atomic_session_without_atomic_record_fails_closed() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)

    with pytest.raises(JournalConflictError, match="without its open record"):
        journal.start_session_and_append_before(
            SESSION,
            record(),
            latest_allowed_at=AT,
            authoritative_now=lambda: AT,
        )

    assert journal.records(SESSION.session_id) == ()


def test_session_lookup_returns_registered_metadata_or_none() -> None:
    journal = InMemoryJournalRepository()

    assert journal.session(SESSION.session_id) is None

    journal.start_session(SESSION)

    assert journal.session(SESSION.session_id) == SESSION


def test_session_prefix_lookup_is_exact_and_ordered() -> None:
    journal = InMemoryJournalRepository()
    second = replace(SESSION, session_id="no-overnight-v1-2026-08-25")
    first = replace(SESSION, session_id="no-overnight-v1-2026-08-24")
    unrelated = replace(SESSION, session_id="local-paper-runtime-v2")
    for session in (second, unrelated, first):
        journal.start_session(session)

    assert journal.sessions(session_id_prefix="no-overnight-v1-") == (
        first,
        second,
    )
    with pytest.raises(ValueError, match="must not be empty"):
        journal.sessions(session_id_prefix="")


def test_conflicting_record_or_idempotency_key_fails_closed() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)
    journal.append(record())

    with pytest.raises(JournalConflictError, match="conflicts"):
        journal.append(replace(record(), payload={"symbol": "2317", "side": "BUY"}))


def test_record_owns_immutable_canonical_payload_bytes_snapshot() -> None:
    source = {
        "amount": Decimal("100.00"),
        "nested": {"items": ["first", "second"]},
    }
    immutable = record(payload=source)
    original_bytes = immutable.payload_bytes
    original_fingerprint = immutable.fingerprint

    source["amount"] = Decimal("999")
    source["nested"]["items"].append("third")

    assert immutable.payload_bytes == b'{"amount":"100","nested":{"items":["first","second"]}}'
    assert immutable.payload_json == immutable.payload_bytes.decode("utf-8")
    assert immutable.payload["amount"] == "100"
    assert immutable.payload["nested"]["items"] == ("first", "second")
    assert immutable.payload_bytes == original_bytes
    assert immutable.fingerprint == original_fingerprint
    with pytest.raises(TypeError):
        immutable.payload["amount"] = "200"
    with pytest.raises(TypeError):
        immutable.payload["nested"]["other"] = "blocked"


def test_repository_history_cannot_be_mutated_after_append() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(SESSION)
    appended = journal.append(record(payload={"nested": {"value": "original"}}))

    with pytest.raises(TypeError):
        appended.record.payload["nested"]["value"] = "changed"

    stored = journal.records(SESSION.session_id)[0].record
    assert stored.payload["nested"]["value"] == "original"
    assert stored.payload_bytes == appended.record.payload_bytes


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
    assert [path.name for path in migration_files()] == [
        "001_journal.sql",
        "002_trading_schema.sql",
    ]
