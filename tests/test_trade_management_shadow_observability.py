from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.trade_management_shadow_observability import (
    SHADOW_OBSERVABILITY_VERSION,
    ShadowOperationHealth,
    ShadowOperationMetrics,
    ShadowReadinessEvaluator,
    ShadowReadinessPolicy,
    ShadowReadinessReason,
    ShadowReadinessStatus,
)
from tests.test_trade_management_replay import THESIS
from tests.test_trade_management_shadow_operation import (
    FailOnceDecisionJournal,
    build_operation,
    live_events,
    submit_and_process,
)
from trading.journal import InMemoryJournalRepository
from trading.shadow_evidence_journal import ShadowEvidenceJournalKind
from trading.trade_management_shadow import ShadowParityStatus


def test_operation_reports_blocked_backpressure_and_recovery_metrics() -> None:
    operation, _journal = build_operation(journal=FailOnceDecisionJournal())
    event = live_events()[0]
    assert operation.submit_market(lambda sequence: event).accepted

    with pytest.raises(OSError, match="evidence unavailable"):
        operation.process_pending(occurred_at=event.received_at)

    blocked = operation.metrics(
        observed_at=event.received_at + timedelta(seconds=5)
    )
    assert blocked.health is ShadowOperationHealth.BLOCKED
    assert blocked.pending_evidence_count == 1
    assert blocked.durable_decision_count == 0
    assert blocked.oldest_pending_age_seconds == Decimal("5")
    assert blocked.writer_failure_count == 1

    operation.process_pending(
        occurred_at=event.received_at + timedelta(seconds=8)
    )
    recovered = operation.metrics(
        observed_at=event.received_at + timedelta(seconds=8)
    )
    assert recovered.health is ShadowOperationHealth.RUNNING
    assert recovered.pending_evidence_count == 0
    assert recovered.durable_decision_count == 1
    assert recovered.recovery_count == 1
    assert recovered.last_recovery_seconds == Decimal("8")


def test_operation_reports_canonical_event_backpressure() -> None:
    operation, _journal = build_operation()
    events = live_events()
    assert operation.submit_market(lambda sequence: events[0]).accepted
    assert operation.submit_market(lambda sequence: events[1]).accepted

    queued = operation.metrics(
        observed_at=events[1].received_at + timedelta(seconds=5)
    )
    assert queued.pending_market_event_count == 2
    assert queued.oldest_pending_event_age_seconds == Decimal("32")

    operation.process_pending(
        occurred_at=events[1].received_at + timedelta(seconds=5),
        max_messages=1,
    )
    partially_drained = operation.metrics(
        observed_at=events[1].received_at + timedelta(seconds=5)
    )
    assert partially_drained.pending_market_event_count == 1
    assert partially_drained.oldest_pending_event_age_seconds == Decimal("5")
    with pytest.raises(RuntimeError, match="pending canonical messages"):
        operation.finalize()


def test_finalized_metrics_prove_evidence_completeness_and_parity() -> None:
    operation, _journal = build_operation()
    for event in live_events():
        submit_and_process(operation, event)
    operation.finalize()

    metrics = operation.metrics(observed_at=live_events()[-1].received_at)

    assert metrics.health is ShadowOperationHealth.FINALIZED
    assert metrics.finalized
    assert metrics.finalization_persisted
    assert metrics.parity_status is ShadowParityStatus.MATCHED
    assert metrics.evidence_complete
    assert metrics.lost_evidence_count == 0
    assert metrics.decision_record_count == metrics.durable_decision_count
    with pytest.raises(FrozenInstanceError):
        metrics.health = ShadowOperationHealth.BLOCKED  # type: ignore[misc]


class FailOnceFinalizationJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def append(self, record):
        if (
            record.kind == ShadowEvidenceJournalKind.SESSION_FINALIZED.value
            and not self.failed
        ):
            self.failed = True
            raise OSError("finalization evidence unavailable")
        return super().append(record)


def test_finalization_failure_is_blocked_and_retry_is_observable() -> None:
    operation, _journal = build_operation(journal=FailOnceFinalizationJournal())
    events = live_events()
    for event in events:
        submit_and_process(operation, event)

    with pytest.raises(OSError, match="finalization evidence unavailable"):
        operation.finalize(observed_at=events[-1].received_at)

    blocked = operation.metrics(observed_at=events[-1].received_at)
    assert blocked.health is ShadowOperationHealth.BLOCKED
    assert not blocked.finalized
    assert blocked.writer_failure_count == 1

    operation.finalize(
        observed_at=events[-1].received_at + timedelta(seconds=3)
    )
    recovered = operation.metrics(
        observed_at=events[-1].received_at + timedelta(seconds=3)
    )
    assert recovered.health is ShadowOperationHealth.FINALIZED
    assert recovered.recovery_count == 1
    assert recovered.last_recovery_seconds == Decimal("3")
    assert recovered.evidence_complete


def finalized_metrics(
    session_id: str,
    *,
    parity: ShadowParityStatus = ShadowParityStatus.MATCHED,
    decisions: int = 100,
    durable: int | None = None,
    pending: int = 0,
    pending_market: int = 0,
    writer_failures: int = 0,
    recovery_seconds: str | None = None,
    observation_seconds: str = "14400",
) -> ShadowOperationMetrics:
    durable_count = decisions if durable is None else durable
    return ShadowOperationMetrics(
        version=SHADOW_OBSERVABILITY_VERSION,
        session_id=session_id,
        observed_at=THESIS.filled_at.value,
        health=ShadowOperationHealth.FINALIZED,
        admitted_message_count=decisions + pending_market,
        processed_message_count=decisions,
        pending_market_event_count=pending_market,
        oldest_pending_event_age_seconds=(
            Decimal("1") if pending_market else None
        ),
        applied_event_count=decisions,
        rejected_event_count=0,
        decision_record_count=decisions,
        durable_decision_count=durable_count,
        pending_evidence_count=pending,
        oldest_pending_age_seconds=Decimal("1") if pending else None,
        writer_failure_count=writer_failures,
        recovery_count=1 if recovery_seconds is not None else 0,
        last_recovery_seconds=(
            None if recovery_seconds is None else Decimal(recovery_seconds)
        ),
        observation_seconds=Decimal(observation_seconds),
        finalized=True,
        finalization_persisted=True,
        parity_status=parity,
        first_divergent_sequence=(
            1 if parity is ShadowParityStatus.DIVERGED else None
        ),
    )


def policy(**changes: object) -> ShadowReadinessPolicy:
    values = {
        "version": "shadow-readiness-policy-v1",
        "min_finalized_sessions": 2,
        "min_total_observation_seconds": Decimal("28800"),
        "min_total_decision_records": 200,
        "min_parity_rate": Decimal("1"),
        "max_writer_failures": 0,
        "max_recovery_seconds": Decimal("30"),
    }
    values.update(changes)
    return ShadowReadinessPolicy(**values)


def test_readiness_is_pure_deterministic_and_never_enables_execution() -> None:
    sessions = (
        finalized_metrics("shadow-session-b"),
        finalized_metrics("shadow-session-a"),
    )

    first = ShadowReadinessEvaluator().evaluate(policy(), sessions)
    second = ShadowReadinessEvaluator().evaluate(policy(), tuple(reversed(sessions)))

    assert first.status is ShadowReadinessStatus.READY
    assert first.reasons == ()
    assert first.parity_rate == Decimal("1")
    assert first.evidence_complete
    assert not first.execution_enabled
    assert first == second


def test_readiness_reports_typed_failures_without_guessing() -> None:
    sessions = (
        finalized_metrics(
            "shadow-session-a",
            parity=ShadowParityStatus.DIVERGED,
            decisions=10,
            durable=9,
            writer_failures=2,
            recovery_seconds="45",
            observation_seconds="60",
        ),
    )

    report = ShadowReadinessEvaluator().evaluate(policy(), sessions)

    assert report.status is ShadowReadinessStatus.NOT_READY
    assert set(report.reasons) == {
        ShadowReadinessReason.INSUFFICIENT_FINALIZED_SESSIONS,
        ShadowReadinessReason.INSUFFICIENT_OBSERVATION_TIME,
        ShadowReadinessReason.INSUFFICIENT_DECISION_RECORDS,
        ShadowReadinessReason.EVIDENCE_INCOMPLETE,
        ShadowReadinessReason.PARITY_DIVERGENCE,
        ShadowReadinessReason.PARITY_RATE_BELOW_THRESHOLD,
        ShadowReadinessReason.WRITER_FAILURE_LIMIT_EXCEEDED,
        ShadowReadinessReason.RECOVERY_TIME_EXCEEDED,
    }
    assert report.lost_evidence_count == 1
    assert report.parity_rate == Decimal("0")
    assert report.divergent_session_ids == ("shadow-session-a",)
    assert not report.execution_enabled


def test_observability_has_no_decision_or_execution_authority() -> None:
    root = Path(__file__).parents[1]
    source = (
        root / "runtime" / "trade_management_shadow_observability.py"
    ).read_text()
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
        {"RiskGate", "ThesisMonitor", "OrderCommand", "OrderApplicationService"}
    )
    assert referenced_names.isdisjoint(
        {"Broker", "Position", "SELL", "Shioaji", "SimulationService"}
    )
