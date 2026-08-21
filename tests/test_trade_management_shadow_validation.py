from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.trade_management_shadow_validation import (
    SHADOW_VALIDATION_VERSION,
    ShadowOperationalDrill,
    ShadowOperationalDrillType,
    ShadowSessionSource,
    ShadowSourceClass,
    ShadowValidationEvaluator,
    ShadowValidationPolicy,
    ShadowValidationReason,
    ShadowValidationSession,
    ShadowValidationStatus,
)
from tests.test_trade_management_replay import THESIS
from tests.test_trade_management_shadow_observability import finalized_metrics, policy


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def source(
    connection: str,
    *,
    source_class: ShadowSourceClass = ShadowSourceClass.LIVE_MARKET,
) -> ShadowSessionSource:
    return ShadowSessionSource(
        source_class=source_class,
        provider="SHIOAJI",
        provider_version="1.7.2",
        connection_session_id=connection,
    )


def validation_session(
    session_id: str,
    market_date: date,
    *,
    source_class: ShadowSourceClass = ShadowSourceClass.LIVE_MARKET,
    duration_seconds: str = "16200",
    recovered_digest: str = DIGEST_A,
) -> ShadowValidationSession:
    started_at = THESIS.filled_at.value.replace(
        year=market_date.year,
        month=market_date.month,
        day=market_date.day,
        hour=9,
        minute=0,
        second=0,
    )
    return ShadowValidationSession(
        version=SHADOW_VALIDATION_VERSION,
        session_id=session_id,
        market_date=market_date,
        source=source(session_id, source_class=source_class),
        coverage_started_at=started_at,
        coverage_ended_at=started_at + timedelta(seconds=int(duration_seconds)),
        metrics=replace(
            finalized_metrics(
                session_id,
                observation_seconds=duration_seconds,
            ),
            observed_at=started_at + timedelta(seconds=int(duration_seconds)),
        ),
        durable_projection_digest=DIGEST_A,
        recovered_projection_digest=recovered_digest,
    )


def drill(
    drill_id: str,
    drill_type: ShadowOperationalDrillType,
    *,
    passed: bool = True,
) -> ShadowOperationalDrill:
    started_at = THESIS.filled_at.value
    return ShadowOperationalDrill(
        version=SHADOW_VALIDATION_VERSION,
        drill_id=drill_id,
        drill_type=drill_type,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=5),
        failure_detected=True,
        fail_closed_observed=passed,
        recovery_verified=passed,
        investigation_completed=passed,
        first_divergent_sequence=(
            2 if drill_type is ShadowOperationalDrillType.PARITY_DIVERGENCE else None
        ),
        evidence_digest=DIGEST_B,
    )


def validation_policy() -> ShadowValidationPolicy:
    return ShadowValidationPolicy(
        version="shadow-operational-readiness-v1",
        min_complete_sessions=2,
        min_distinct_market_dates=2,
        min_session_coverage_seconds=Decimal("16200"),
        require_live_market_source=True,
        require_recovery_drill=True,
        require_divergence_drill=True,
    )


def complete_inputs():
    sessions = (
        validation_session("shadow-20260819", date(2026, 8, 19)),
        validation_session("shadow-20260820", date(2026, 8, 20)),
    )
    drills = (
        drill("drill-recovery", ShadowOperationalDrillType.JOURNAL_RECOVERY),
        drill("drill-divergence", ShadowOperationalDrillType.PARITY_DIVERGENCE),
    )
    return sessions, drills


def test_extended_validation_is_deterministic_and_never_enables_execution() -> None:
    sessions, drills = complete_inputs()
    evaluator = ShadowValidationEvaluator()

    first = evaluator.evaluate(
        validation_policy(),
        policy(min_total_observation_seconds=Decimal("32400")),
        sessions,
        drills,
    )
    second = evaluator.evaluate(
        validation_policy(),
        policy(min_total_observation_seconds=Decimal("32400")),
        tuple(reversed(sessions)),
        tuple(reversed(drills)),
    )

    assert first == second
    assert first.status is ShadowValidationStatus.PASSED
    assert first.reasons == ()
    assert first.complete_session_count == 2
    assert first.distinct_market_dates == (date(2026, 8, 19), date(2026, 8, 20))
    assert first.readiness_report.status.value == "READY"
    assert not first.execution_enabled
    with pytest.raises(FrozenInstanceError):
        first.execution_enabled = True  # type: ignore[misc]
    with pytest.raises(ValueError, match="cannot enable execution"):
        replace(first, execution_enabled=True)


def test_fixture_sources_cannot_satisfy_production_shadow_validation() -> None:
    sessions, drills = complete_inputs()
    sessions = (
        replace(
            sessions[0],
            source=source("fixture-1", source_class=ShadowSourceClass.TEST_FIXTURE),
        ),
        sessions[1],
    )

    report = ShadowValidationEvaluator().evaluate(
        validation_policy(), policy(), sessions, drills
    )

    assert report.status is ShadowValidationStatus.FAILED
    assert ShadowValidationReason.NON_LIVE_MARKET_SOURCE in report.reasons
    assert ShadowValidationReason.INSUFFICIENT_COMPLETE_SESSIONS in report.reasons
    assert ShadowValidationReason.INSUFFICIENT_MARKET_DATES in report.reasons
    assert report.non_live_session_ids == ("shadow-20260819",)
    assert not report.execution_enabled


def test_incomplete_coverage_and_checkpoint_recovery_are_typed_failures() -> None:
    sessions, drills = complete_inputs()
    sessions = (
        replace(
            sessions[0],
            coverage_ended_at=sessions[0].coverage_started_at + timedelta(hours=1),
        ),
        replace(sessions[1], recovered_projection_digest="c" * 64),
    )

    report = ShadowValidationEvaluator().evaluate(
        validation_policy(), policy(), sessions, drills
    )

    assert report.status is ShadowValidationStatus.FAILED
    assert ShadowValidationReason.INSUFFICIENT_COMPLETE_SESSIONS in report.reasons
    assert ShadowValidationReason.INSUFFICIENT_MARKET_DATES in report.reasons
    assert ShadowValidationReason.SESSION_COVERAGE_INCOMPLETE in report.reasons
    assert ShadowValidationReason.CHECKPOINT_RECOVERY_MISMATCH in report.reasons
    assert report.incomplete_session_ids == (
        "shadow-20260819",
        "shadow-20260820",
    )


def test_missing_and_failed_operational_drills_are_reported() -> None:
    sessions, _drills = complete_inputs()
    failed_recovery = drill(
        "drill-recovery",
        ShadowOperationalDrillType.JOURNAL_RECOVERY,
        passed=False,
    )

    report = ShadowValidationEvaluator().evaluate(
        validation_policy(), policy(), sessions, (failed_recovery,)
    )

    assert set(report.reasons) >= {
        ShadowValidationReason.RECOVERY_DRILL_FAILED,
        ShadowValidationReason.DIVERGENCE_DRILL_MISSING,
    }
    assert report.failed_drill_ids == ("drill-recovery",)


def test_one_passing_drill_cannot_hide_another_failed_drill() -> None:
    sessions, drills = complete_inputs()
    recovery_passed = drills[0]
    recovery_failed = drill(
        "drill-recovery-second",
        ShadowOperationalDrillType.JOURNAL_RECOVERY,
        passed=False,
    )

    report = ShadowValidationEvaluator().evaluate(
        validation_policy(),
        policy(),
        sessions,
        (recovery_passed, recovery_failed, drills[1]),
    )

    assert report.status is ShadowValidationStatus.FAILED
    assert ShadowValidationReason.RECOVERY_DRILL_FAILED in report.reasons
    assert report.failed_drill_ids == ("drill-recovery-second",)


def test_base_readiness_failure_remains_authoritative() -> None:
    sessions, drills = complete_inputs()

    report = ShadowValidationEvaluator().evaluate(
        validation_policy(),
        policy(min_finalized_sessions=3),
        sessions,
        drills,
    )

    assert report.status is ShadowValidationStatus.FAILED
    assert ShadowValidationReason.BASE_READINESS_NOT_READY in report.reasons
    assert report.readiness_report.status.value == "NOT_READY"


def test_validation_rejects_duplicate_session_and_drill_identity() -> None:
    sessions, drills = complete_inputs()
    evaluator = ShadowValidationEvaluator()

    with pytest.raises(ValueError, match="validation sessions must be unique"):
        evaluator.evaluate(validation_policy(), policy(), (sessions[0], sessions[0]), drills)
    with pytest.raises(ValueError, match="operational drills must be unique"):
        evaluator.evaluate(validation_policy(), policy(), sessions, (drills[0], drills[0]))


def test_validation_has_no_decision_persistence_or_execution_authority() -> None:
    root = Path(__file__).parents[1]
    source_text = (
        root / "runtime" / "trade_management_shadow_validation.py"
    ).read_text()
    tree = ast.parse(source_text)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported_names.isdisjoint(
        {
            "JournalRepository",
            "RiskGate",
            "ThesisMonitor",
            "OrderCommand",
            "OrderApplicationService",
        }
    )
    assert referenced_names.isdisjoint(
        {"Broker", "Position", "SELL", "Shioaji", "SimulationService"}
    )
