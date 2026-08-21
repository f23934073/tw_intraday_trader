from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_trade_management_replay import (
    POLICY,
    SNAPSHOT,
    THESIS,
    hard_invalid_events,
)
from tests.trade_management_builders import EXIT_POLICY_VERSION
from trading.trade_management import ExitAction, ThesisStatus
from trading.trade_management_shadow import (
    ShadowDecisionConfig,
    ShadowDecisionPipeline,
    ShadowParityStatus,
)


def config(**changes: object) -> ShadowDecisionConfig:
    values: dict[str, object] = {
        "thesis": THESIS,
        "exit_policy_version": EXIT_POLICY_VERSION,
        "risk_policy": POLICY,
        "volume_baseline_shares": Decimal("1000"),
        "shares_per_lot": 1000,
        "remaining_quantity_shares": 1000,
        "fill_model_version": "shadow-observation-no-fill-v1",
        "code_identity": "git:pr-tm-007-test",
    }
    values.update(changes)
    return ShadowDecisionConfig(**values)


def test_live_canonical_events_emit_hold_then_exit_shadow_records() -> None:
    pipeline = ShadowDecisionPipeline(config())

    records = tuple(
        pipeline.consume(event, risk_snapshot=SNAPSHOT)
        for event in hard_invalid_events()
    )

    assert all(record is not None for record in records)
    assert records[0].step.recommendation_result.decision.action is ExitAction.HOLD
    assert records[-1].step.evaluation.status is ThesisStatus.INVALID
    assert records[-1].step.recommendation_result.decision.action is ExitAction.EXIT
    assert records[-1].step.eligibility is not None
    assert records[-1].risk_snapshot == SNAPSHOT
    assert pipeline.snapshot().records == records
    assert not hasattr(records[-1], "command")


def test_exact_duplicate_is_idempotent_but_conflict_and_out_of_order_fail_closed() -> None:
    pipeline = ShadowDecisionPipeline(config())
    events = hard_invalid_events()
    first = pipeline.consume(events[0], risk_snapshot=SNAPSHOT)
    before = pipeline.snapshot()

    assert pipeline.consume(events[0], risk_snapshot=SNAPSHOT) is first
    assert pipeline.snapshot() == before
    with pytest.raises(ValueError, match="duplicate event conflict"):
        pipeline.consume(
            replace(events[0], source_identity="changed-duplicate"),
            risk_snapshot=SNAPSHOT,
        )
    with pytest.raises(ValueError, match="strictly ordered"):
        pipeline.consume(
            replace(
                events[1],
                event_at=events[0].event_at,
                ingress_sequence=0,
                payload=replace(
                    events[1].payload,
                    event_time=events[0].event_at,
                    ingress_sequence=0,
                ),
            ),
            risk_snapshot=SNAPSHOT,
        )
    assert pipeline.snapshot() == before


def test_finalize_proves_live_to_replay_digest_parity() -> None:
    pipeline = ShadowDecisionPipeline(config())
    for event in hard_invalid_events():
        pipeline.consume(event, risk_snapshot=SNAPSHOT)

    session = pipeline.finalize()

    assert session.parity.status is ShadowParityStatus.MATCHED
    assert session.parity.shadow_decision_digest == (
        session.parity.replay_decision_digest
    )
    assert session.manifest_sha256 == (
        session.replay_result.run_identity.manifest_sha256
    )
    assert session.records == pipeline.snapshot().records
    with pytest.raises(RuntimeError, match="finalized"):
        pipeline.consume(hard_invalid_events()[-1], risk_snapshot=SNAPSHOT)


def test_per_event_risk_evidence_is_replayed_exactly() -> None:
    pipeline = ShadowDecisionPipeline(config())
    events = hard_invalid_events()
    for event in events[:-1]:
        pipeline.consume(event, risk_snapshot=SNAPSHOT)
    blocked_snapshot = replace(SNAPSHOT, market_open=False)
    live_record = pipeline.consume(events[-1], risk_snapshot=blocked_snapshot)

    session = pipeline.finalize()
    replay_record = session.replay_result.steps[-1]

    assert live_record is not None and live_record.step.eligibility is not None
    assert live_record.step.eligibility.status.value == "BLOCKED"
    assert replay_record.eligibility == live_record.step.eligibility
    assert session.parity.status is ShadowParityStatus.MATCHED


def test_session_identity_and_full_policy_values_are_bound() -> None:
    pipeline = ShadowDecisionPipeline(config())
    event = hard_invalid_events()[0]

    with pytest.raises(ValueError, match="session does not match"):
        pipeline.consume(
            replace(event, session_id="other-session"),
            risk_snapshot=SNAPSHOT,
        )
    changed_policy = replace(POLICY, max_daily_loss=POLICY.max_daily_loss + 1)

    assert config(risk_policy=changed_policy).digest != config().digest


def test_shadow_contracts_are_immutable_and_have_no_execution_authority() -> None:
    pipeline = ShadowDecisionPipeline(config())
    record = pipeline.consume(hard_invalid_events()[0], risk_snapshot=SNAPSHOT)
    assert record is not None

    with pytest.raises(FrozenInstanceError):
        record.record_id = "changed"  # type: ignore[misc]

    root = Path(__file__).parents[1]
    source = (root / "trading" / "trade_management_shadow.py").read_text()
    tree = ast.parse(source)
    imported_roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_roots.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert imported_roots.isdisjoint(
        {"dashboard", "position", "runtime", "simulation", "shioaji"}
    )
    assert referenced_names.isdisjoint(
        {"Journal", "OrderCommand", "OrderApplicationService", "Broker"}
    )
