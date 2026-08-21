from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tests.test_trade_management_replay import POLICY, SNAPSHOT, hard_invalid_events
from tests.test_trade_management_shadow import config
from trading.journal import (
    InMemoryJournalRepository,
    JournalAppendResult,
    JournalConflictError,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.shadow_evidence_journal import (
    SHADOW_EVIDENCE_PROJECTION_NAME,
    ShadowEvidenceJournalError,
    ShadowEvidenceProjection,
    ShadowEvidenceRetentionMode,
    ShadowEvidenceRetentionPolicy,
    append_shadow_session_evidence,
    journal_record_for_shadow_decision,
    journal_record_for_shadow_session,
    read_shadow_evidence_record,
    rebuild_shadow_evidence_projection,
    write_shadow_evidence_checkpoint,
)
from trading.trade_management_shadow import ShadowDecisionPipeline


def shadow_session():
    pipeline = ShadowDecisionPipeline(config())
    for event in hard_invalid_events():
        pipeline.consume(event, risk_snapshot=SNAPSHOT)
    return pipeline.finalize()


def journal() -> InMemoryJournalRepository:
    repository = InMemoryJournalRepository()
    thesis = config().thesis
    repository.start_session(
        JournalSession(
            session_id=thesis.draft.session_id,
            started_at=thesis.draft.signal_at.value,
            mode="SHADOW_DECISION_ONLY",
            metadata={"execution_enabled": False},
        )
    )
    return repository


def test_session_evidence_append_retry_and_restart_reconstruction() -> None:
    repository = journal()
    session = shadow_session()

    first = append_shadow_session_evidence(repository, session)
    retried = append_shadow_session_evidence(repository, session)
    written = write_shadow_evidence_checkpoint(
        repository,
        session_id=config().thesis.draft.session_id,
    )
    rebuilt = rebuild_shadow_evidence_projection(
        repository,
        session_id=config().thesis.draft.session_id,
    )

    assert len(first) == len(session.records) + 1
    assert all(not item.idempotent for item in first)
    assert all(item.idempotent for item in retried)
    assert [item.sequence for item in first] == [item.sequence for item in retried]
    assert tuple(item.record_id for item in rebuilt.decisions) == tuple(
        item.record_id for item in session.records
    )
    assert rebuilt.finalization is not None
    assert rebuilt.finalization.manifest_sha256 == session.manifest_sha256
    assert rebuilt.finalization.final_decision_chain_digest == (
        rebuilt.finalization.replay_decision_digest
    )
    assert rebuilt.digest == written.digest


def test_decision_artifact_keeps_full_risk_snapshot_and_is_immutable() -> None:
    session = shadow_session()
    source = session.records[-1]
    journal_record = journal_record_for_shadow_decision(source)
    evidence = read_shadow_evidence_record(journal_record)

    assert evidence is not None
    assert evidence.decision is not None
    assert evidence.decision.risk_snapshot == source.risk_snapshot
    assert evidence.decision.source_event_digest == source.source_event_digest
    assert evidence.decision.decision_chain_digest == source.decision_chain_digest
    assert evidence.decision.market_context["source_event_id"] == source.step.source_event_id
    with pytest.raises(FrozenInstanceError):
        evidence.decision.record_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        journal_record.payload["evidence_json"] = "changed"


def test_partial_append_can_resume_without_duplicate_evidence() -> None:
    repository = journal()
    session = shadow_session()
    repository.append(journal_record_for_shadow_decision(session.records[0]))
    repository.append(journal_record_for_shadow_decision(session.records[1]))

    resumed = append_shadow_session_evidence(repository, session)

    assert [item.idempotent for item in resumed[:2]] == [True, True]
    assert all(not item.idempotent for item in resumed[2:])
    assert len(repository.records(config().thesis.draft.session_id)) == (
        len(session.records) + 1
    )


def test_corruption_conflict_and_append_order_fail_closed() -> None:
    repository = journal()
    session = shadow_session()
    decision_record = journal_record_for_shadow_decision(session.records[0])
    first = repository.append(decision_record)

    with pytest.raises(JournalConflictError, match="conflicts"):
        repository.append(
            replace(
                decision_record,
                payload={**decision_record.payload, "evidence_digest": "0" * 64},
            )
        )
    corrupted = replace(
        decision_record,
        payload={**decision_record.payload, "evidence_digest": "0" * 64},
    )
    projection = ShadowEvidenceProjection()
    with pytest.raises(ShadowEvidenceJournalError, match="digest mismatch"):
        projection.apply(
            JournalAppendResult(corrupted, sequence=1, idempotent=False)
        )
    projection.apply(first)
    with pytest.raises(ShadowEvidenceJournalError, match="strictly increasing"):
        projection.apply(first)


def test_risk_snapshot_values_cannot_change_behind_their_digest() -> None:
    source = shadow_session().records[-1]
    record = journal_record_for_shadow_decision(source)
    artifact = json.loads(record.payload["evidence_json"])
    artifact["payload"]["risk_snapshot"]["market_open"] = False
    evidence_json = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    corrupted = replace(
        record,
        payload={
            **record.payload,
            "evidence_json": evidence_json,
            "evidence_digest": hashlib.sha256(evidence_json.encode()).hexdigest(),
        },
    )

    with pytest.raises(ShadowEvidenceJournalError, match="cannot decode"):
        read_shadow_evidence_record(corrupted)


def test_unknown_evidence_fields_are_rejected_even_with_updated_digest() -> None:
    source = shadow_session().records[0]
    record = journal_record_for_shadow_decision(source)
    artifact = json.loads(record.payload["evidence_json"])
    artifact["payload"]["unexpected"] = "ambiguous"
    evidence_json = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    changed = replace(
        record,
        payload={
            **record.payload,
            "evidence_json": evidence_json,
            "evidence_digest": hashlib.sha256(evidence_json.encode()).hexdigest(),
        },
    )

    with pytest.raises(ShadowEvidenceJournalError, match="invalid decision evidence"):
        read_shadow_evidence_record(changed)


def test_finalization_requires_exact_chain_and_rejects_later_decisions() -> None:
    session = shadow_session()
    projection = ShadowEvidenceProjection()
    final_record = journal_record_for_shadow_session(session)

    with pytest.raises(ShadowEvidenceJournalError, match="record count"):
        projection.apply(
            JournalAppendResult(final_record, sequence=1, idempotent=False)
        )
    for sequence, record in enumerate(session.records, start=1):
        projection.apply(
            JournalAppendResult(
                journal_record_for_shadow_decision(record),
                sequence=sequence,
                idempotent=False,
            )
        )
    projection.apply(
        JournalAppendResult(
            final_record,
            sequence=len(session.records) + 1,
            idempotent=False,
        )
    )
    with pytest.raises(ShadowEvidenceJournalError, match="after finalization"):
        projection.apply(
            JournalAppendResult(
                journal_record_for_shadow_decision(session.records[-1]),
                sequence=len(session.records) + 2,
                idempotent=False,
            )
        )


def test_checkpoint_recovery_and_retain_all_policy_are_fail_closed() -> None:
    repository = journal()
    session = shadow_session()
    append_shadow_session_evidence(repository, session)

    with pytest.raises(ShadowEvidenceJournalError, match="requires a checkpoint"):
        rebuild_shadow_evidence_projection(
            repository,
            session_id=config().thesis.draft.session_id,
        )
    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=config().thesis.draft.session_id,
            projection_name=SHADOW_EVIDENCE_PROJECTION_NAME,
            journal_sequence=len(session.records) + 1,
            digest="corrupted",
        )
    )
    with pytest.raises(ShadowEvidenceJournalError, match="digest mismatch"):
        rebuild_shadow_evidence_projection(
            repository,
            session_id=config().thesis.draft.session_id,
        )
    with pytest.raises(ValueError, match="compaction"):
        ShadowEvidenceRetentionPolicy(
            version="shadow-evidence-retention-v1",
            mode=ShadowEvidenceRetentionMode.RETAIN_ALL,
            compaction_allowed=True,
        )


def test_shadow_evidence_adapter_has_no_trade_or_execution_authority() -> None:
    root = Path(__file__).parents[1]
    source = (root / "trading" / "shadow_evidence_journal.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert imported_names.isdisjoint(
        {"OrderCommand", "OrderApplicationService", "TradeManagementProjection"}
    )
    assert referenced_names.isdisjoint(
        {"Broker", "Position", "SELL", "SimulationService"}
    )
