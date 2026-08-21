import ast
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import (
    SESSION_ID,
    build_exit_recommendation,
    build_trade_outcome,
    build_trade_thesis,
    runtime_at,
)
from trading.journal import (
    InMemoryJournalRepository,
    JournalAppendResult,
    JournalConflictError,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.trade_management import (
    ExitReason,
    ExitRecommendationStatus,
    TimestampRole,
    TAIPEI,
)
from trading.trade_management_journal import (
    TRADE_MANAGEMENT_PROJECTION_NAME,
    TradeManagementJournalError,
    TradeManagementJournalKind,
    TradeManagementProjection,
    journal_record_for_exit_recommendation_created,
    journal_record_for_exit_recommendation_resolved,
    journal_record_for_exit_recommendation_updated,
    journal_record_for_trade_outcome,
    journal_record_for_trade_thesis,
    journal_record_for_trade_thesis_draft,
    read_trade_management_record,
    rebuild_trade_management_projection,
    write_trade_management_checkpoint,
)


def journal() -> InMemoryJournalRepository:
    repository = InMemoryJournalRepository()
    repository.start_session(
        JournalSession(
            session_id=SESSION_ID,
            started_at=datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI),
            mode="LOCAL_PAPER",
            metadata={"trade_management_schema": "trade-management-v1"},
        )
    )
    return repository


def recommendation_snapshots():
    created = build_exit_recommendation()
    updated = replace(
        created,
        latest_decision_id="exit-decision-002",
        latest_evidence_event_id="tick-2330-093600",
        triggered_reasons=(ExitReason.THESIS_INVALID, ExitReason.TIME_DECAY),
        updated_at=runtime_at(
            9,
            36,
            0,
            "replay-clock:tick-2330-093600",
            role=TimestampRole.EXIT_DECISION,
        ),
    )
    outcome = build_trade_outcome()
    resolved = replace(
        updated,
        status=ExitRecommendationStatus.RESOLVED_ON_CLOSE,
        resolved_at=outcome.closed_at,
        closing_fill_id=outcome.exit_legs[-1].fill_id,
    )
    return created, updated, resolved, outcome


def append_complete_trade(repository: InMemoryJournalRepository):
    thesis = build_trade_thesis()
    created, updated, resolved, outcome = recommendation_snapshots()
    records = (
        journal_record_for_trade_thesis_draft(thesis.draft),
        journal_record_for_trade_thesis(thesis),
        journal_record_for_exit_recommendation_created(created),
        JournalRecord(
            record_id="unrelated-market-record",
            session_id=SESSION_ID,
            kind="market_event.v1",
            occurred_at=created.created_at.value,
            payload={"event_id": "tick-2330-093502"},
        ),
        journal_record_for_exit_recommendation_updated(updated),
        journal_record_for_exit_recommendation_resolved(resolved),
        journal_record_for_trade_outcome(outcome, session_id=SESSION_ID),
    )
    return tuple(repository.append(record) for record in records), (
        thesis,
        resolved,
        outcome,
    )


def test_record_codecs_preserve_canonical_contract_and_timestamp_identity():
    thesis = build_trade_thesis()
    record = journal_record_for_trade_thesis(thesis)

    event = read_trade_management_record(record)

    assert event is not None
    assert event.kind is TradeManagementJournalKind.THESIS_ACTIVATED
    assert event.session_id == SESSION_ID
    assert event.contract == thesis
    assert record.record_id == (
        "trade_management_event_v1_"
        "8b5f73387415084453ded351aeb4b6425548dd382702c339ab4270de090c770e"
    )
    assert record.payload["contract_digest"] == (
        "bad5b55ecc7772dc1a090c2c89236c056668ae6e5b47497a9b60ca4ef7ceb743"
    )
    assert record.payload["contract_json"] == (
        Path("tests/fixtures/trade_management/v1/trade_thesis.json")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert record.occurred_at == thesis.filled_at.value
    assert record.session_id == thesis.draft.session_id
    assert read_trade_management_record(
        JournalRecord(
            record_id="unrelated",
            session_id=SESSION_ID,
            kind="other.v1",
            occurred_at=thesis.filled_at.value,
            payload={},
        )
    ) is None

    with pytest.raises(TradeManagementJournalError, match="unsupported"):
        read_trade_management_record(replace(record, kind="trade_thesis_draft.v2"))


def test_trade_management_journal_v1_kind_values_and_draft_identity_are_frozen():
    assert [item.value for item in TradeManagementJournalKind] == [
        "trade_thesis_draft.v1",
        "trade_thesis_activated.v1",
        "exit_recommendation_created.v1",
        "exit_recommendation_updated.v1",
        "exit_recommendation_resolved.v1",
        "trade_closed.v1",
    ]
    record = journal_record_for_trade_thesis_draft(build_trade_thesis().draft)
    assert record.record_id == (
        "trade_management_event_v1_"
        "3aabc8c232e53f7453d4266baa558604e554182f738168372338c4f6ac431eac"
    )
    assert record.payload["contract_digest"] == (
        "34bdaaabd822b644d820a8d734d596ccfce2640b633d7dc6f2fec205520f3840"
    )


def test_equivalent_decimal_scales_have_one_record_digest_and_fingerprint():
    records = tuple(
        journal_record_for_trade_thesis(
            replace(build_trade_thesis(), entry_reference_price=Decimal(raw))
        )
        for raw in ("100", "100.0", "100.00", "1E+2")
    )

    assert len({record.record_id for record in records}) == 1
    assert len({record.payload["contract_digest"] for record in records}) == 1
    assert len({record.fingerprint for record in records}) == 1


def test_append_retry_is_idempotent_and_changed_contract_fails_closed():
    repository = journal()
    record = journal_record_for_trade_thesis_draft(build_trade_thesis().draft)

    first = repository.append(record)
    retry = repository.append(record)

    assert first.sequence == retry.sequence == 1
    assert first.idempotent is False
    assert retry.idempotent is True
    with pytest.raises(JournalConflictError, match="conflicts"):
        repository.append(
            replace(
                record,
                payload={**record.payload, "contract_digest": "0" * 64},
            )
        )


def test_checkpointed_replay_reconstructs_all_contracts_and_is_deterministic():
    repository = journal()
    results, (thesis, resolved, outcome) = append_complete_trade(repository)

    written = write_trade_management_checkpoint(repository, session_id=SESSION_ID)
    rebuilt = rebuild_trade_management_projection(
        repository,
        session_id=SESSION_ID,
    )
    digests = {
        rebuild_trade_management_projection(
            repository,
            session_id=SESSION_ID,
        ).digest
        for _iteration in range(10)
    }

    assert written.last_sequence == results[-1].sequence == 7
    assert rebuilt.last_sequence == 7
    assert rebuilt.draft(thesis.thesis_id) == thesis.draft
    assert rebuilt.thesis_for_trade(thesis.trade_id) == thesis
    assert rebuilt.recommendation_for_trade(thesis.trade_id) == resolved
    assert rebuilt.outcome(thesis.trade_id) == outcome
    assert digests == {written.digest}


def test_checkpoint_remains_stable_after_payload_mutation_is_rejected():
    repository = journal()
    results, (thesis, _resolved, _outcome) = append_complete_trade(repository)
    written = write_trade_management_checkpoint(repository, session_id=SESSION_ID)
    activation = results[1].record

    with pytest.raises(TypeError):
        activation.payload["contract_json"] = "rewritten-history"

    rebuilt = rebuild_trade_management_projection(
        repository,
        session_id=SESSION_ID,
    )
    assert rebuilt.thesis_for_trade(thesis.trade_id) == thesis
    assert rebuilt.digest == written.digest
    assert activation.payload_bytes == repository.records(SESSION_ID)[1].record.payload_bytes


def test_replay_fails_closed_for_digest_corruption_and_out_of_order_sequence():
    thesis = build_trade_thesis()
    draft_record = journal_record_for_trade_thesis_draft(thesis.draft)
    corrupted = replace(
        draft_record,
        payload={**draft_record.payload, "contract_digest": "0" * 64},
    )
    projection = TradeManagementProjection()

    with pytest.raises(TradeManagementJournalError, match="digest mismatch"):
        projection.apply(
            JournalAppendResult(record=corrupted, sequence=1, idempotent=False)
        )

    projection.apply(
        JournalAppendResult(record=draft_record, sequence=2, idempotent=False)
    )
    with pytest.raises(TradeManagementJournalError, match="strictly increasing"):
        projection.apply(
            JournalAppendResult(record=draft_record, sequence=2, idempotent=True)
        )


def test_replay_requires_draft_before_activation_and_one_recommendation_per_trade():
    thesis = build_trade_thesis()
    projection = TradeManagementProjection()
    with pytest.raises(TradeManagementJournalError, match="requires a journaled draft"):
        projection.apply(
            JournalAppendResult(
                record=journal_record_for_trade_thesis(thesis),
                sequence=1,
                idempotent=False,
            )
        )

    projection = TradeManagementProjection()
    projection.apply(
        JournalAppendResult(
            record=journal_record_for_trade_thesis_draft(thesis.draft),
            sequence=1,
            idempotent=False,
        )
    )
    projection.apply(
        JournalAppendResult(
            record=journal_record_for_trade_thesis(thesis),
            sequence=2,
            idempotent=False,
        )
    )
    created = build_exit_recommendation()
    created_record = journal_record_for_exit_recommendation_created(created)
    projection.apply(
        JournalAppendResult(record=created_record, sequence=3, idempotent=False)
    )
    with pytest.raises(TradeManagementJournalError, match="already has"):
        projection.apply(
            JournalAppendResult(record=created_record, sequence=4, idempotent=False)
        )


def test_recovery_requires_matching_checkpoint():
    repository = journal()
    result = repository.append(
        journal_record_for_trade_thesis_draft(build_trade_thesis().draft)
    )
    with pytest.raises(TradeManagementJournalError, match="requires a checkpoint"):
        rebuild_trade_management_projection(repository, session_id=SESSION_ID)

    repository.save_checkpoint(
        ProjectionCheckpoint(
            session_id=SESSION_ID,
            projection_name=TRADE_MANAGEMENT_PROJECTION_NAME,
            journal_sequence=result.sequence,
            digest="corrupted",
        )
    )
    with pytest.raises(TradeManagementJournalError, match="digest mismatch"):
        rebuild_trade_management_projection(repository, session_id=SESSION_ID)


def test_replay_rejects_cross_session_and_mismatched_close_resolution():
    repository = journal()
    results, (_thesis, _resolved, outcome) = append_complete_trade(repository)
    projection = TradeManagementProjection()
    for result in results[:-1]:
        projection.apply(result)

    outcome_record = journal_record_for_trade_outcome(
        outcome,
        session_id="different-session",
    )
    with pytest.raises(TradeManagementJournalError, match="mix Journal sessions"):
        projection.apply(
            JournalAppendResult(
                record=outcome_record,
                sequence=results[-1].sequence,
                idempotent=False,
            )
        )

    projection = TradeManagementProjection()
    for result in results[:-2]:
        projection.apply(result)
    _created, updated, _resolved, _outcome = recommendation_snapshots()
    wrong_resolution = replace(
        updated,
        status=ExitRecommendationStatus.RESOLVED_ON_CLOSE,
        resolved_at=outcome.closed_at,
        closing_fill_id="different-closing-fill",
    )
    projection.apply(
        JournalAppendResult(
            record=journal_record_for_exit_recommendation_resolved(
                wrong_resolution
            ),
            sequence=results[-2].sequence,
            idempotent=False,
        )
    )
    with pytest.raises(TradeManagementJournalError, match="final exit fill"):
        projection.apply(results[-1])


def test_journal_integration_has_no_decision_risk_broker_or_runtime_dependency():
    source = Path("trading/trade_management_journal.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_roots.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imported_roots.isdisjoint(
        {"market_data", "position", "runtime", "simulation"}
    )
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert referenced_names.isdisjoint({"RiskGate", "ThesisMonitor"})
    assert "submit_order" not in called_attributes
    assert "now" not in called_attributes
