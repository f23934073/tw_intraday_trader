from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from runtime.in_memory import InMemoryJournalRepository
from trading.journal import JournalSession, ProjectionCheckpoint
from trading.no_overnight import (
    NoOvernightEvidence,
    NoOvernightState,
    canonical_transition_digest,
    expected_would_actions,
)
from trading.no_overnight_journal import (
    NO_OVERNIGHT_BREACH_KIND,
    NO_OVERNIGHT_PROJECTION_NAME,
    NoOvernightProjectionError,
    breach_id_for,
    execution_fact_observed_record,
    no_overnight_breach_acknowledged_record,
    no_overnight_breach_record,
    no_overnight_breach_resolved_record,
    no_overnight_reconciliation_record,
    no_overnight_result_record,
    rebuild_no_overnight_projection,
    snapshot_record,
    transition_record,
    write_no_overnight_checkpoint,
)


SESSION_DATE = date(2026, 8, 24)
SESSION_ID = f"no-overnight-v1-{SESSION_DATE.isoformat()}"
NOW = datetime.fromisoformat("2026-08-24T13:30:00+08:00")
ACCOUNT_SCOPE_ID = "local-paper-account-v2"
POLICY_FAMILY_ID = "no-overnight-local-paper-v1"
POLICY_VERSION = "enforcing-policy-v1"
POLICY_DIGEST = "a" * 64


def _journal() -> InMemoryJournalRepository:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=NOW,
            mode="NO_OVERNIGHT_ENFORCING",
            metadata={
                "account_scope_id": ACCOUNT_SCOPE_ID,
                "policy_family_id": POLICY_FAMILY_ID,
                "session_date": SESSION_DATE.isoformat(),
                "policy_version": POLICY_VERSION,
                "policy_digest": POLICY_DIGEST,
            },
        )
    )
    return journal


def _snapshot_payload(
    *, quantity: int, source_sequence: int, digest: str
) -> dict[str, object]:
    return {
        "account_scope_id": ACCOUNT_SCOPE_ID,
        "policy_family_id": POLICY_FAMILY_ID,
        "session_date": SESSION_DATE.isoformat(),
        "managed_exposures": [
            {
                "exposure_id": "managed-exposure-1",
                "current_quantity": quantity,
                "max_quantity_during_session": 1000,
                "authoritative_open_fill_quantity": 1000,
                "authoritative_close_fill_quantity": 1000 - quantity,
            }
        ],
        "pending_entry_quantity": [],
        "pending_exit_quantity": [],
        "unresolved_execution_ids": [],
        "reconciliation_status": "MATCH",
        "reconciliation_digest": digest,
        "last_fill_journal_sequence": source_sequence,
        "last_execution_fact_journal_sequence": source_sequence,
        "snapshot_covers_through_journal_sequence": source_sequence,
        "snapshot_journal_sequence": 0,
        "snapshot_source_as_of": NOW.isoformat(),
        "snapshot_received_at": NOW.isoformat(),
    }


def _append_snapshot(
    journal: InMemoryJournalRepository,
    *,
    quantity: int,
    source_sequence: int,
    digest: str,
) -> NoOvernightEvidence:
    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            source_journal_sequence=source_sequence,
            source_kind="local_paper_fill.v2",
            source_record_id=f"fill-{source_sequence}",
            occurred_at=NOW,
        )
    )
    journal.append(
        snapshot_record(
            session_id=SESSION_ID,
            payload=_snapshot_payload(
                quantity=quantity,
                source_sequence=source_sequence,
                digest=digest,
            ),
        )
    )
    projection = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert projection.evidence is not None
    return projection.evidence


def _append_initial_breach(journal: InMemoryJournalRepository) -> str:
    evidence = _append_snapshot(
        journal,
        quantity=1000,
        source_sequence=10,
        digest="d" * 64,
    )
    actions = expected_would_actions(NoOvernightState.OVERNIGHT_BREACH)
    transition_digest = canonical_transition_digest(
        previous_state=NoOvernightState.NORMAL,
        state=NoOvernightState.OVERNIGHT_BREACH,
        revision=1,
        planned_at=NOW,
        would_actions=actions,
        flat_proof_mode=None,
        planner_input_digest="b" * 64,
    )
    journal.append(
        transition_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            previous_state=NoOvernightState.NORMAL,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=1,
            planned_at=NOW,
            would_actions=tuple(item.value for item in actions),
            planner_input_digest="b" * 64,
            transition_digest=transition_digest,
            flat_proof_mode=None,
        )
    )
    reconciled = journal.append(
        no_overnight_reconciliation_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            evidence=evidence,
            reconciled_at=NOW,
        )
    )
    result = journal.append(
        no_overnight_result_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            state=NoOvernightState.OVERNIGHT_BREACH,
            revision=1,
            flat_proof_mode=None,
            evidence=evidence,
            transition_planned_at=NOW,
            result_at=NOW,
        )
    )
    breach_id = breach_id_for(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        originating_session_date=SESSION_DATE,
    )
    journal.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id,
            breach_revision=1,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="MANAGED_EXPOSURE_OPEN",
            evidence=evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=reconciled.sequence,
            source_result_journal_sequence=result.sequence,
            breached_at=NOW,
        )
    )
    return breach_id


def test_breach_restart_preserves_exact_identity_reason_quantity_and_fences() -> None:
    journal = _journal()
    breach_id = _append_initial_breach(journal)
    write_no_overnight_checkpoint(journal, session_id=SESSION_ID)

    before = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=True,
    )
    restarted = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=True,
    )

    assert restarted.payload() == before.payload()
    assert restarted.breach_id == breach_id
    assert restarted.breach_revision == 1
    assert restarted.breach_reason == "MANAGED_EXPOSURE_OPEN"
    assert restarted.breach_revision_reason == "MANAGED_EXPOSURE_OPEN"
    assert restarted.breach_managed_open_quantity == 1000
    assert restarted.breach_pending_entry_quantity == 0
    assert restarted.breach_pending_exit_quantity == 0
    assert restarted.breach_unresolved_execution_count == 0
    assert restarted.breach_evidence_through_journal_sequence == 10
    assert restarted.breach_reconciliation_digest == "d" * 64
    assert restarted.breach_severity == "CRITICAL"
    assert restarted.breach_revised_at == NOW
    assert restarted.breach_resolved is False
    assert restarted.breach_acknowledged is False


def test_pr_no_004_checkpoint_digest_is_accepted_only_before_g5_events() -> None:
    source = _journal()
    _append_initial_breach(source)
    legacy = _journal()
    for appended in source.records(SESSION_ID):
        if appended.record.kind != NO_OVERNIGHT_BREACH_KIND:
            legacy.append(appended.record)
    legacy_projection = rebuild_no_overnight_projection(
        legacy,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    legacy.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=NO_OVERNIGHT_PROJECTION_NAME,
            journal_sequence=legacy_projection.last_sequence,
            digest=legacy_projection.legacy_digest,
        )
    )

    recovered = rebuild_no_overnight_projection(
        legacy,
        session_id=SESSION_ID,
        require_checkpoint=True,
    )

    assert recovered.state is NoOvernightState.OVERNIGHT_BREACH
    assert recovered.breach_id is None

    current = _journal()
    _append_initial_breach(current)
    current_projection = rebuild_no_overnight_projection(
        current,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    current.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=NO_OVERNIGHT_PROJECTION_NAME,
            journal_sequence=current_projection.last_sequence,
            digest=current_projection.legacy_digest,
        )
    )
    with pytest.raises(NoOvernightProjectionError, match="checkpoint digest"):
        rebuild_no_overnight_projection(
            current,
            session_id=SESSION_ID,
            require_checkpoint=True,
        )


def test_ack_requires_resolution_and_late_fact_invalidates_matching_chain() -> None:
    journal = _journal()
    breach_id = _append_initial_breach(journal)

    premature = no_overnight_breach_acknowledged_record(
        session_id=SESSION_ID,
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        originating_session_date=SESSION_DATE,
        breach_id=breach_id,
        breach_revision=1,
        reconciliation_digest="d" * 64,
        actor_id="operator-1",
        resolution_journal_sequence=1,
        acknowledged_session_date=SESSION_DATE,
        acknowledged_at=NOW + timedelta(seconds=1),
        idempotency_key="ack-before-resolution",
    )
    journal.append(premature)
    with pytest.raises(NoOvernightProjectionError, match="resolution"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )

    journal = _journal()
    breach_id = _append_initial_breach(journal)
    flat_evidence = _append_snapshot(
        journal,
        quantity=0,
        source_sequence=11,
        digest="e" * 64,
    )
    reconciled = journal.append(
        no_overnight_reconciliation_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            evidence=flat_evidence,
            reconciled_at=NOW + timedelta(seconds=2),
        )
    )
    journal.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id,
            breach_revision=2,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="STRICT_FLAT_REESTABLISHED",
            evidence=flat_evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=reconciled.sequence,
            source_result_journal_sequence=0,
            breached_at=NOW + timedelta(seconds=2),
        )
    )
    resolution = journal.append(
        no_overnight_breach_resolved_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            evidence_through_journal_sequence=11,
            evidence_snapshot_journal_sequence=(
                flat_evidence.snapshot_journal_sequence
            ),
            evidence_reconciliation_journal_sequence=reconciled.sequence,
            strict_flat_proof_mode="FILL_DERIVED_CLOSE",
            resolved_session_date=SESSION_DATE,
            resolved_at=NOW + timedelta(seconds=3),
        )
    )
    journal.append(
        no_overnight_breach_acknowledged_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            actor_id="operator-1",
            resolution_journal_sequence=resolution.sequence,
            acknowledged_session_date=SESSION_DATE,
            acknowledged_at=NOW + timedelta(seconds=4),
            idempotency_key="ack-latest-resolution",
        )
    )
    resolved = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert resolved.breach_resolved is True
    assert resolved.breach_acknowledged is True
    assert resolved.breach_resolution_sequence < resolved.breach_ack_sequence

    journal.append(
        execution_fact_observed_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            source_journal_sequence=12,
            source_kind="local_paper_fill.v2",
            source_record_id="late-fill-12",
            occurred_at=NOW + timedelta(seconds=5),
        )
    )
    invalidated = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert invalidated.breach_revision == 2
    assert invalidated.breach_resolved is False
    assert invalidated.breach_acknowledged is False
    assert invalidated.breach_invalidation_sequence > resolved.breach_ack_sequence


def test_breach_reader_rejects_unknown_fields_in_revision_payload() -> None:
    journal = _journal()
    _append_initial_breach(journal)
    original = journal.records(SESSION_ID)[-1]
    payload = dict(original.record.payload)
    payload["clear_breach"] = True
    corrupted = replace(
        original.record,
        record_id="corrupted-breach-extra-field",
        payload=payload,
        idempotency_scope=None,
        idempotency_key=None,
    )
    clean = _journal()
    for appended in journal.records(SESSION_ID)[:-1]:
        clean.append(appended.record)
    clean.append(corrupted)

    with pytest.raises(NoOvernightProjectionError, match="breach fields mismatch"):
        rebuild_no_overnight_projection(
            clean,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_breach_reader_rejects_journal_identity_metadata_mismatch() -> None:
    source = _journal()
    _append_initial_breach(source)
    corrupted = _journal()
    for appended in source.records(SESSION_ID)[:-1]:
        corrupted.append(appended.record)
    original = source.records(SESSION_ID)[-1].record
    corrupted.append(
        replace(
            original,
            occurred_at=original.occurred_at + timedelta(seconds=1),
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="Journal identity"):
        rebuild_no_overnight_projection(
            corrupted,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_trusted_recovery_cross_checks_breach_snapshot_reference() -> None:
    source = _journal()
    _append_initial_breach(source)
    corrupted = _journal()
    for appended in source.records(SESSION_ID)[:-1]:
        corrupted.append(appended.record)
    pre_breach = rebuild_no_overnight_projection(
        corrupted,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert pre_breach.evidence is not None
    corrupted.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id_for(
                account_scope_id=ACCOUNT_SCOPE_ID,
                policy_family_id=POLICY_FAMILY_ID,
                originating_session_date=SESSION_DATE,
            ),
            breach_revision=1,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="MANAGED_EXPOSURE_OPEN",
            evidence=replace(
                pre_breach.evidence,
                snapshot_journal_sequence=3,
            ),
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=(
                pre_breach.last_reconciliation_journal_sequence
            ),
            source_result_journal_sequence=(
                pre_breach.latest_result_journal_sequence or 0
            ),
            breached_at=NOW,
        )
    )
    write_no_overnight_checkpoint(corrupted, session_id=SESSION_ID)

    with pytest.raises(
        NoOvernightProjectionError,
        match="snapshot evidence record is missing",
    ):
        rebuild_no_overnight_projection(
            corrupted,
            session_id=SESSION_ID,
            require_checkpoint=True,
        )


def test_trusted_recovery_rejects_breach_timestamp_before_evidence() -> None:
    source = _journal()
    _append_initial_breach(source)
    corrupted = _journal()
    for appended in source.records(SESSION_ID)[:-1]:
        corrupted.append(appended.record)
    pre_breach = rebuild_no_overnight_projection(
        corrupted,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert pre_breach.evidence is not None
    corrupted.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id_for(
                account_scope_id=ACCOUNT_SCOPE_ID,
                policy_family_id=POLICY_FAMILY_ID,
                originating_session_date=SESSION_DATE,
            ),
            breach_revision=1,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="MANAGED_EXPOSURE_OPEN",
            evidence=pre_breach.evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=(
                pre_breach.last_reconciliation_journal_sequence
            ),
            source_result_journal_sequence=(
                pre_breach.latest_result_journal_sequence or 0
            ),
            breached_at=NOW - timedelta(seconds=1),
        )
    )
    write_no_overnight_checkpoint(corrupted, session_id=SESSION_ID)

    with pytest.raises(
        NoOvernightProjectionError,
        match="predates referenced evidence",
    ):
        rebuild_no_overnight_projection(
            corrupted,
            session_id=SESSION_ID,
            require_checkpoint=True,
        )


def test_resolution_rejects_nonflat_and_stale_digest_targets() -> None:
    nonflat = _journal()
    breach_id = _append_initial_breach(nonflat)
    nonflat_projection = rebuild_no_overnight_projection(
        nonflat,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    nonflat.append(
        no_overnight_breach_resolved_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=1,
            reconciliation_digest="d" * 64,
            evidence_through_journal_sequence=(
                nonflat_projection.breach_evidence_through_journal_sequence
            ),
            evidence_snapshot_journal_sequence=(
                nonflat_projection.breach_evidence_snapshot_journal_sequence
            ),
            evidence_reconciliation_journal_sequence=(
                nonflat_projection.breach_evidence_reconciliation_journal_sequence
            ),
            strict_flat_proof_mode="FILL_DERIVED_CLOSE",
            resolved_session_date=SESSION_DATE,
            resolved_at=NOW + timedelta(seconds=1),
        )
    )
    with pytest.raises(NoOvernightProjectionError, match="strict flat"):
        rebuild_no_overnight_projection(
            nonflat,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )

    stale = _journal()
    breach_id = _append_initial_breach(stale)
    stale_projection = rebuild_no_overnight_projection(
        stale,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    stale.append(
        no_overnight_breach_resolved_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=1,
            reconciliation_digest="e" * 64,
            evidence_through_journal_sequence=(
                stale_projection.breach_evidence_through_journal_sequence
            ),
            evidence_snapshot_journal_sequence=(
                stale_projection.breach_evidence_snapshot_journal_sequence
            ),
            evidence_reconciliation_journal_sequence=(
                stale_projection.breach_evidence_reconciliation_journal_sequence
            ),
            strict_flat_proof_mode="FILL_DERIVED_CLOSE",
            resolved_session_date=SESSION_DATE,
            resolved_at=NOW + timedelta(seconds=1),
        )
    )
    with pytest.raises(NoOvernightProjectionError, match="latest revision"):
        rebuild_no_overnight_projection(
            stale,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_breach_revision_cannot_roll_back_to_older_evidence() -> None:
    journal = _journal()
    breach_id = _append_initial_breach(journal)
    initial = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert initial.evidence is not None
    newer_evidence = _append_snapshot(
        journal,
        quantity=500,
        source_sequence=11,
        digest="e" * 64,
    )
    newer_reconciliation = journal.append(
        no_overnight_reconciliation_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            evidence=newer_evidence,
            reconciled_at=NOW + timedelta(seconds=1),
        )
    )
    journal.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id,
            breach_revision=2,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="EVIDENCE_CHANGED",
            evidence=newer_evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=(newer_reconciliation.sequence),
            source_result_journal_sequence=0,
            breached_at=NOW + timedelta(seconds=1),
        )
    )
    journal.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id,
            breach_revision=3,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="EVIDENCE_CHANGED",
            evidence=initial.evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=(
                initial.breach_evidence_reconciliation_journal_sequence
            ),
            source_result_journal_sequence=0,
            breached_at=NOW + timedelta(seconds=2),
        )
    )

    with pytest.raises(NoOvernightProjectionError, match="monotonically forward"):
        rebuild_no_overnight_projection(
            journal,
            session_id=SESSION_ID,
            require_checkpoint=False,
        )


def test_reconciliation_digest_change_invalidates_ack_without_new_fact() -> None:
    journal = _journal()
    breach_id = _append_initial_breach(journal)
    flat_evidence = _append_snapshot(
        journal,
        quantity=0,
        source_sequence=11,
        digest="e" * 64,
    )
    reconciled = journal.append(
        no_overnight_reconciliation_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            evidence=flat_evidence,
            reconciled_at=NOW + timedelta(seconds=2),
        )
    )
    journal.append(
        no_overnight_breach_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            policy_version=POLICY_VERSION,
            policy_digest=POLICY_DIGEST,
            breach_id=breach_id,
            breach_revision=2,
            breach_reason="MANAGED_EXPOSURE_OPEN",
            revision_reason="STRICT_FLAT_REESTABLISHED",
            evidence=flat_evidence,
            evidence_session_date=SESSION_DATE,
            evidence_reconciliation_journal_sequence=reconciled.sequence,
            source_result_journal_sequence=0,
            breached_at=NOW + timedelta(seconds=2),
        )
    )
    resolution = journal.append(
        no_overnight_breach_resolved_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            evidence_through_journal_sequence=11,
            evidence_snapshot_journal_sequence=(
                flat_evidence.snapshot_journal_sequence
            ),
            evidence_reconciliation_journal_sequence=reconciled.sequence,
            strict_flat_proof_mode="FILL_DERIVED_CLOSE",
            resolved_session_date=SESSION_DATE,
            resolved_at=NOW + timedelta(seconds=3),
        )
    )
    journal.append(
        no_overnight_breach_acknowledged_record(
            session_id=SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            originating_session_date=SESSION_DATE,
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            actor_id="operator-1",
            resolution_journal_sequence=resolution.sequence,
            acknowledged_session_date=SESSION_DATE,
            acknowledged_at=NOW + timedelta(seconds=4),
            idempotency_key="ack-before-digest-change",
        )
    )
    changed_payload = _snapshot_payload(
        quantity=0,
        source_sequence=11,
        digest="f" * 64,
    )
    changed_payload["snapshot_received_at"] = (NOW + timedelta(seconds=5)).isoformat()
    changed_payload["snapshot_source_as_of"] = (NOW + timedelta(seconds=5)).isoformat()
    journal.append(snapshot_record(session_id=SESSION_ID, payload=changed_payload))

    changed = rebuild_no_overnight_projection(
        journal,
        session_id=SESSION_ID,
        require_checkpoint=False,
    )
    assert changed.breach_resolved is False
    assert changed.breach_acknowledged is False
    assert changed.breach_invalidation_sequence == changed.last_sequence
