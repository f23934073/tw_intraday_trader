import hashlib
import json
from datetime import date, datetime, timedelta

import pytest

from runtime.in_memory import InMemoryJournalRepository
from trading.journal import JournalRecord, JournalSession, ProjectionCheckpoint
from trading.no_overnight import (
    ManagedExposureEvidence,
    NoOvernightEvidence,
    NoOvernightState,
    ReconciliationStatus,
)
from trading.no_overnight_journal import (
    NO_OVERNIGHT_PROJECTION_NAME,
    NoOvernightProjectionError,
    execution_fact_observed_record,
    no_overnight_result_record,
    no_overnight_reconciliation_record,
    rebuild_no_overnight_projection,
    snapshot_record,
    transition_record,
    write_no_overnight_checkpoint,
)


SESSION_ID = "no-overnight-v1-2026-08-24"
NOW = datetime.fromisoformat("2026-08-24T13:30:00+08:00")


def _transition_digest(
    *,
    previous_state: NoOvernightState,
    state: NoOvernightState,
    revision: int,
    planned_at: datetime,
    would_actions: tuple[str, ...],
    flat_proof_mode: str | None,
    planner_input_digest: str,
) -> str:
    payload = {
        "previous_state": previous_state.value,
        "state": state.value,
        "revision": revision,
        "planned_at": planned_at.isoformat(),
        "would_actions": list(would_actions),
        "flat_proof_mode": flat_proof_mode,
        "planner_input_digest": planner_input_digest,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _journal() -> InMemoryJournalRepository:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=NOW,
            mode="NO_OVERNIGHT_OBSERVE_ONLY",
            metadata={
                "account_scope_id": "local-paper-account-v2",
                "policy_family_id": "no-overnight-local-paper-v1",
                "session_date": "2026-08-24",
                "policy_version": "observe-policy-v1",
                "policy_digest": "a" * 64,
                "calendar_digest": "c" * 64,
            },
        )
    )
    return journal


def _snapshot_payload() -> dict[str, object]:
    return {
        "account_scope_id": "local-paper-account-v2",
        "policy_family_id": "no-overnight-local-paper-v1",
        "session_date": "2026-08-24",
        "managed_exposures": [],
        "pending_entry_quantity": [],
        "pending_exit_quantity": [],
        "unresolved_execution_ids": [],
        "reconciliation_status": "MATCH",
        "reconciliation_digest": "d" * 64,
        "last_fill_journal_sequence": 0,
        "last_execution_fact_journal_sequence": 10,
        "snapshot_covers_through_journal_sequence": 10,
        "snapshot_journal_sequence": 0,
        "snapshot_source_as_of": NOW.isoformat(),
        "snapshot_received_at": NOW.isoformat(),
    }


def _snapshot_evidence() -> NoOvernightEvidence:
    return NoOvernightEvidence(
        session_date=date(2026, 8, 24),
        managed_exposures=(),
        pending_entry_quantity=(),
        pending_exit_quantity=(),
        unresolved_execution_ids=(),
        reconciliation_status=ReconciliationStatus.MATCH,
        reconciliation_digest="d" * 64,
        last_fill_journal_sequence=0,
        last_execution_fact_journal_sequence=10,
        snapshot_covers_through_journal_sequence=10,
        snapshot_journal_sequence=2,
        snapshot_source_as_of=NOW,
        snapshot_received_at=NOW,
    )


@pytest.mark.parametrize(
    ("late_kind", "late_record_id"),
    (
        ("local_paper_fill.v2", "late-fill-11"),
        ("local_paper_order_state.v2", "late-cancel-11"),
        ("local_paper_rejection.v2", "late-reject-11"),
        ("order_command.v2", "late-submit-unknown-11"),
        ("local_paper_order_state.v2", "late-recovery-required-11"),
    ),
)
def test_projection_checkpoint_rebuild_is_deterministic_and_late_fact_supersedes(
    late_kind: str,
    late_record_id: str,
) -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="order-state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    transition_digest = _transition_digest(
        previous_state=NoOvernightState.NORMAL,
        state=NoOvernightState.CONFIRMED_FLAT,
        revision=1,
        planned_at=NOW,
        would_actions=("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE"),
        flat_proof_mode="NEVER_EXPOSED",
        planner_input_digest="b" * 64,
    )
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            planned_at=NOW,
            would_actions=("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE"),
            planner_input_digest="b" * 64,
            transition_digest=transition_digest,
            flat_proof_mode="NEVER_EXPOSED",
        )
    )
    journal.append(
        no_overnight_reconciliation_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            evidence=_snapshot_evidence(),
            reconciled_at=NOW,
        )
    )
    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            flat_proof_mode="NEVER_EXPOSED",
            evidence=_snapshot_evidence(),
            transition_planned_at=NOW,
            result_at=NOW,
        )
    )
    written = write_no_overnight_checkpoint(journal, session_id=SESSION_ID)
    restored = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=True,
    )

    assert restored.digest == written.digest
    assert restored.result_status == "CURRENT"
    assert restored.last_reconciliation_status == "MATCH"

    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=11,
            source_kind=late_kind,
            source_record_id=late_record_id,
            occurred_at=NOW,
        )
    )
    superseded = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=True,
    )
    assert superseded.result_status == "SUPERSEDED"
    assert superseded.last_execution_fact_journal_sequence == 11

    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            flat_proof_mode="NEVER_EXPOSED",
            evidence=_snapshot_evidence(),
            transition_planned_at=NOW,
            result_at=NOW + timedelta(seconds=1),
        )
    )
    with pytest.raises(NoOvernightProjectionError, match="result.*fence|superseded"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=True,
        )


def test_projection_rejects_transition_out_of_latched_breach() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_fill.v2",
            source_record_id="open-fill-10",
            occurred_at=NOW,
        )
    )
    breach_payload = {
        **_snapshot_payload(),
        "managed_exposures": [
            {
                "exposure_id": "managed-1",
                "current_quantity": 1000,
                "max_quantity_during_session": 1000,
                "authoritative_open_fill_quantity": 1000,
                "authoritative_close_fill_quantity": 0,
            }
        ],
        "last_fill_journal_sequence": 10,
    }
    journal.append(snapshot_record(session_id=SESSION_ID, payload=breach_payload))
    first_actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    first_input = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=1,
            planned_at=NOW,
            would_actions=first_actions,
            planner_input_digest=first_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.OVERNIGHT_BREACH,
                revision=1,
                planned_at=NOW,
                would_actions=first_actions,
                flat_proof_mode=None,
                planner_input_digest=first_input,
            ),
            flat_proof_mode=None,
        )
    )
    second_actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    second_input = "c" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.OVERNIGHT_BREACH,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=2,
            planned_at=NOW + timedelta(seconds=1),
            would_actions=second_actions,
            planner_input_digest=second_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.OVERNIGHT_BREACH,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=2,
                planned_at=NOW + timedelta(seconds=1),
                would_actions=second_actions,
                flat_proof_mode="NEVER_EXPOSED",
                planner_input_digest=second_input,
            ),
            flat_proof_mode="NEVER_EXPOSED",
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="OVERNIGHT_BREACH"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_rejects_initial_breach_from_flat_snapshot() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    planner_input_digest = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=planner_input_digest,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.OVERNIGHT_BREACH,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode=None,
                planner_input_digest=planner_input_digest,
            ),
            flat_proof_mode=None,
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="breach.*non-flat"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_keeps_latched_breach_when_later_snapshot_is_flat() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_fill.v2",
            source_record_id="open-fill-10",
            occurred_at=NOW,
        )
    )
    non_flat_payload = {
        **_snapshot_payload(),
        "managed_exposures": [
            {
                "exposure_id": "managed-1",
                "current_quantity": 1000,
                "max_quantity_during_session": 1000,
                "authoritative_open_fill_quantity": 1000,
                "authoritative_close_fill_quantity": 0,
            }
        ],
        "last_fill_journal_sequence": 10,
    }
    journal.append(snapshot_record(session_id=SESSION_ID, payload=non_flat_payload))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    first_input = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=first_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.OVERNIGHT_BREACH,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode=None,
                planner_input_digest=first_input,
            ),
            flat_proof_mode=None,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    second_input = "c" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.OVERNIGHT_BREACH,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=2,
            planned_at=NOW + timedelta(seconds=1),
            would_actions=actions,
            planner_input_digest=second_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.OVERNIGHT_BREACH,
                state=NoOvernightState.OVERNIGHT_BREACH,
                revision=2,
                planned_at=NOW + timedelta(seconds=1),
                would_actions=actions,
                flat_proof_mode=None,
                planner_input_digest=second_input,
            ),
            flat_proof_mode=None,
        )
    )

    restored = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )

    assert restored.state is NoOvernightState.OVERNIGHT_BREACH
    assert restored.revision == 2


@pytest.mark.parametrize(
    ("would_actions", "transition_digest", "message"),
    (
        (("WOULD_BLOCK_ENTRY",), "f" * 64, "transition digest"),
        (("WOULD_EXIT",), None, "would actions"),
    ),
)
def test_projection_recomputes_transition_digest_and_semantics(
    would_actions: tuple[str, ...],
    transition_digest: str | None,
    message: str,
) -> None:
    journal = _journal()
    planner_input_digest = "b" * 64
    digest = transition_digest or _transition_digest(
        previous_state=NoOvernightState.NORMAL,
        state=NoOvernightState.NO_NEW_ENTRY,
        revision=1,
        planned_at=NOW,
        would_actions=would_actions,
        flat_proof_mode=None,
        planner_input_digest=planner_input_digest,
    )
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.NO_NEW_ENTRY,
            revision=1,
            planned_at=NOW,
            would_actions=would_actions,
            planner_input_digest=planner_input_digest,
            transition_digest=digest,
            flat_proof_mode=None,
        )
    )

    with pytest.raises(NoOvernightProjectionError, match=message):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_accepts_new_revision_and_fresh_fence_after_supersession() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    first_input = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=first_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode="NEVER_EXPOSED",
                planner_input_digest=first_input,
            ),
            flat_proof_mode="NEVER_EXPOSED",
        )
    )
    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            flat_proof_mode="NEVER_EXPOSED",
            evidence=_snapshot_evidence(),
            transition_planned_at=NOW,
            result_at=NOW,
        )
    )
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=11,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-11",
            occurred_at=NOW + timedelta(seconds=1),
        )
    )
    fresh_payload = {
        **_snapshot_payload(),
        "last_execution_fact_journal_sequence": 11,
        "snapshot_covers_through_journal_sequence": 11,
        "snapshot_source_as_of": (NOW + timedelta(seconds=1)).isoformat(),
        "snapshot_received_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    fresh_snapshot = journal.append(
        snapshot_record(session_id=SESSION_ID, payload=fresh_payload)
    )
    fresh_evidence = NoOvernightEvidence(
        session_date=date(2026, 8, 24),
        managed_exposures=(),
        pending_entry_quantity=(),
        pending_exit_quantity=(),
        unresolved_execution_ids=(),
        reconciliation_status=ReconciliationStatus.MATCH,
        reconciliation_digest="d" * 64,
        last_fill_journal_sequence=0,
        last_execution_fact_journal_sequence=11,
        snapshot_covers_through_journal_sequence=11,
        snapshot_journal_sequence=fresh_snapshot.sequence,
        snapshot_source_as_of=NOW + timedelta(seconds=1),
        snapshot_received_at=NOW + timedelta(seconds=1),
    )
    second_input = "c" * 64
    second_planned_at = NOW + timedelta(seconds=1)
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.CONFIRMED_FLAT,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=2,
            planned_at=second_planned_at,
            would_actions=actions,
            planner_input_digest=second_input,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.CONFIRMED_FLAT,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=2,
                planned_at=second_planned_at,
                would_actions=actions,
                flat_proof_mode="NEVER_EXPOSED",
                planner_input_digest=second_input,
            ),
            flat_proof_mode="NEVER_EXPOSED",
        )
    )
    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=2,
            flat_proof_mode="NEVER_EXPOSED",
            evidence=fresh_evidence,
            transition_planned_at=second_planned_at,
            result_at=second_planned_at,
        )
    )

    restored = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert restored.revision == 2
    assert restored.result_status == "CURRENT"
    assert restored.latest_result_snapshot_fence == 11


def test_projection_revalidates_terminal_flat_proof_from_result_evidence() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    planner_input_digest = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=planner_input_digest,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode="NEVER_EXPOSED",
                planner_input_digest=planner_input_digest,
            ),
            flat_proof_mode="NEVER_EXPOSED",
        )
    )
    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            flat_proof_mode="FILL_DERIVED_CLOSE",
            evidence=_snapshot_evidence(),
            transition_planned_at=NOW,
            result_at=NOW,
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="result proof"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_rejects_transition_proof_conflicting_with_latest_snapshot() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    planner_input_digest = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=planner_input_digest,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode="FILL_DERIVED_CLOSE",
                planner_input_digest=planner_input_digest,
            ),
            flat_proof_mode="FILL_DERIVED_CLOSE",
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="transition proof"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_rejects_result_proof_conflicting_with_transition() -> None:
    journal = _journal()
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="state-10",
            occurred_at=NOW,
        )
    )
    journal.append(snapshot_record(session_id=SESSION_ID, payload=_snapshot_payload()))
    actions = ("WOULD_BLOCK_ENTRY", "WOULD_RECONCILE")
    planner_input_digest = "b" * 64
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            planned_at=NOW,
            would_actions=actions,
            planner_input_digest=planner_input_digest,
            transition_digest=_transition_digest(
                previous_state=NoOvernightState.NORMAL,
                state=NoOvernightState.CONFIRMED_FLAT,
                revision=1,
                planned_at=NOW,
                would_actions=actions,
                flat_proof_mode="NEVER_EXPOSED",
                planner_input_digest=planner_input_digest,
            ),
            flat_proof_mode="NEVER_EXPOSED",
        )
    )
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=11,
            source_kind="local_paper_fill.v2",
            source_record_id="fill-11",
            occurred_at=NOW + timedelta(seconds=1),
        )
    )
    snapshot_at = NOW + timedelta(seconds=1)
    fill_payload = {
        **_snapshot_payload(),
        "managed_exposures": [
            {
                "exposure_id": "managed-1",
                "current_quantity": 0,
                "max_quantity_during_session": 1000,
                "authoritative_open_fill_quantity": 1000,
                "authoritative_close_fill_quantity": 1000,
            }
        ],
        "last_fill_journal_sequence": 11,
        "last_execution_fact_journal_sequence": 11,
        "snapshot_covers_through_journal_sequence": 11,
        "snapshot_source_as_of": snapshot_at.isoformat(),
        "snapshot_received_at": snapshot_at.isoformat(),
    }
    snapshot = journal.append(
        snapshot_record(session_id=SESSION_ID, payload=fill_payload)
    )
    fill_evidence = NoOvernightEvidence(
        session_date=date(2026, 8, 24),
        managed_exposures=(
            ManagedExposureEvidence(
                exposure_id="managed-1",
                current_quantity=0,
                max_quantity_during_session=1000,
                authoritative_open_fill_quantity=1000,
                authoritative_close_fill_quantity=1000,
            ),
        ),
        pending_entry_quantity=(),
        pending_exit_quantity=(),
        unresolved_execution_ids=(),
        reconciliation_status=ReconciliationStatus.MATCH,
        reconciliation_digest="d" * 64,
        last_fill_journal_sequence=11,
        last_execution_fact_journal_sequence=11,
        snapshot_covers_through_journal_sequence=11,
        snapshot_journal_sequence=snapshot.sequence,
        snapshot_source_as_of=snapshot_at,
        snapshot_received_at=snapshot_at,
    )
    journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            policy_version="observe-policy-v1",
            policy_digest="a" * 64,
            state=NoOvernightState.CONFIRMED_FLAT,
            revision=1,
            flat_proof_mode="FILL_DERIVED_CLOSE",
            evidence=fill_evidence,
            transition_planned_at=NOW,
            result_at=snapshot_at,
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="transition proof"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_projection_rejects_corrupted_checkpoint_and_noncanonical_payload() -> None:
    journal = _journal()
    appended = journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id="local-paper-account-v2",
            policy_family_id="no-overnight-local-paper-v1",
            session_date=date(2026, 8, 24),
            source_journal_sequence=10,
            source_kind="local_paper_order_state.v2",
            source_record_id="order-state-10",
            occurred_at=NOW,
        )
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=NO_OVERNIGHT_PROJECTION_NAME,
            journal_sequence=appended.sequence,
            digest="forged",
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="checkpoint digest"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=True,
        )

    malformed = _journal()
    malformed.append(
        JournalRecord(
            record_id="boolean-source-sequence",
            session_id=SESSION_ID,
            kind="no_overnight_execution_fact_observed.v1",
            occurred_at=NOW,
            payload={
                "account_scope_id": "local-paper-account-v2",
                "policy_family_id": "no-overnight-local-paper-v1",
                "session_date": "2026-08-24",
                "source_journal_sequence": True,
                "source_kind": "local_paper_order_state.v2",
                "source_record_id": "state-boolean",
            },
        )
    )
    with pytest.raises(
        NoOvernightProjectionError,
        match="source_journal_sequence",
    ):
        rebuild_no_overnight_projection(
            malformed,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )
