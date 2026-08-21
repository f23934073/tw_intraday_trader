"""PR-008 formal evaluation and preregistered holdout gates."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

import pytest

from institutional_research.domain import ArtifactIdentity, DefinitionIdentity
from institutional_research.evaluation import (
    CompositeResearchInputManifestV1,
    EvaluationArm,
    EvaluationObservation,
    EvaluationSplit,
    EvaluationThresholdsV0,
    FormalGateVerdict,
    PreregisteredEvaluationGateV0,
    SessionRange,
    evaluate_candidate_prior,
    evaluation_observations_sha256,
    serialize_research_input_manifest,
)
from institutional_research.evaluation.application import FormalEvaluationError
from watchlist.reference_data import EquityMarket


TAIPEI = ZoneInfo("Asia/Taipei")
DIGEST = "a" * 64
DEFINITION_DIGEST = "b" * 64
TRAIN = SessionRange(date(2026, 7, 1), date(2026, 7, 10))
VALIDATION = SessionRange(date(2026, 7, 13), date(2026, 7, 24))
HOLDOUT = SessionRange(date(2026, 8, 3), date(2026, 8, 14))


def _artifact(name: str, digest: str = DIGEST) -> ArtifactIdentity:
    return ArtifactIdentity(name, digest)


def _definition(name: str) -> DefinitionIdentity:
    return DefinitionIdentity(name, "v0", DEFINITION_DIGEST)


def _row(
    session: date,
    market: EquityMarket,
    symbol: str,
    liquidity: str,
    *,
    institutional: bool,
    matched_control: bool,
    net_return: str,
) -> EvaluationObservation:
    gross = Decimal(net_return) + Decimal("0.01")
    cohorts = [EvaluationArm.ELIGIBLE_UNIVERSE, EvaluationArm.PRICE_ONLY]
    if institutional:
        cohorts.extend((EvaluationArm.INSTITUTIONAL_ONLY, EvaluationArm.COMBINED))
    if matched_control:
        cohorts.append(EvaluationArm.MATCHED_CONTROL)
    return EvaluationObservation(
        session_date=session,
        market=market,
        symbol=symbol,
        liquidity_cohort=liquidity,
        cohorts=tuple(cohorts),
        setup_qualified=True,
        first_valid_setup_at=datetime(
            session.year, session.month, session.day, 9, 5, tzinfo=TAIPEI
        ),
        executed=True,
        gross_return=gross,
        cost_return=Decimal("0.01"),
        net_return=Decimal(net_return),
        source_entry_digest=DIGEST,
    )


def _rows(
    sessions: tuple[date, ...] = (date(2026, 8, 3), date(2026, 8, 4)),
) -> tuple[EvaluationObservation, ...]:
    values = []
    for index, session in enumerate(sessions):
        values.extend(
            (
                _row(
                    session,
                    EquityMarket.TWSE,
                    f"T{index}A",
                    "LARGE",
                    institutional=True,
                    matched_control=False,
                    net_return="0.10",
                ),
                _row(
                    session,
                    EquityMarket.TWSE,
                    f"T{index}B",
                    "LARGE",
                    institutional=False,
                    matched_control=True,
                    net_return="-0.10",
                ),
                _row(
                    session,
                    EquityMarket.TPEX,
                    f"O{index}A",
                    "SMALL",
                    institutional=True,
                    matched_control=False,
                    net_return="0.10",
                ),
                _row(
                    session,
                    EquityMarket.TPEX,
                    f"O{index}B",
                    "SMALL",
                    institutional=False,
                    matched_control=True,
                    net_return="-0.10",
                ),
            )
        )
    return tuple(values)


def _manifest(
    rows: tuple[EvaluationObservation, ...],
    *,
    research_eligible: bool = True,
    issue_codes: tuple[str, ...] = (),
) -> CompositeResearchInputManifestV1:
    return CompositeResearchInputManifestV1(
        formal_evaluation_protocol=_artifact("formal-protocol"),
        coverage_amendment=_artifact("coverage-amendment"),
        coverage_audit=_artifact("coverage-audit"),
        frozen_population=_artifact("frozen-population"),
        price_dataset=_artifact("price"),
        institutional_partition_set=_artifact("institutional"),
        pit_universe=_artifact("universe"),
        pit_classification_size=_artifact("classification-size"),
        calendar=_artifact("calendar"),
        corporate_actions=_artifact("corporate-actions"),
        reference_data=_artifact("reference"),
        candidate_prior_population=_artifact("candidate-prior"),
        matched_control_population=_artifact("matched-controls"),
        evaluation_observations=_artifact(
            "evaluation-observations", evaluation_observations_sha256(rows)
        ),
        coverage_matrix=_artifact("coverage"),
        setup_definition=_definition("setup"),
        outcome_definition=_definition("outcome"),
        cost_model=_definition("cost-model"),
        evaluation_plan=_definition("evaluation-plan"),
        code=_artifact("code"),
        train=TRAIN,
        validation=VALIDATION,
        holdout=HOLDOUT,
        cost_model_effective_sessions=SessionRange(TRAIN.start, HOLDOUT.end),
        research_eligible=research_eligible,
        issue_codes=issue_codes,
    )


def test_composite_manifest_digest_pins_every_coverage_rule_lineage_input() -> None:
    payload = json.loads(serialize_research_input_manifest(_manifest(_rows())))

    assert payload["formal_evaluation_protocol"] == {
        "artifact_id": "formal-protocol",
        "digest": _artifact("formal-protocol").digest,
    }
    assert payload["coverage_amendment"] == {
        "artifact_id": "coverage-amendment",
        "digest": _artifact("coverage-amendment").digest,
    }
    assert payload["coverage_audit"] == {
        "artifact_id": "coverage-audit",
        "digest": _artifact("coverage-audit").digest,
    }
    assert payload["frozen_population"] == {
        "artifact_id": "frozen-population",
        "digest": _artifact("frozen-population").digest,
    }


def _thresholds() -> EvaluationThresholdsV0:
    return EvaluationThresholdsV0(
        confidence_level=Decimal("0.95"),
        minimum_sessions=2,
        minimum_executions_per_arm=2,
        minimum_guardrail_executions_per_arm=2,
        maximum_turnover_rate_increase=Decimal("0"),
        maximum_guardrail_net_expectancy_deterioration=Decimal("0"),
        required_markets=tuple(EquityMarket),
        required_liquidity_cohorts=("LARGE", "SMALL"),
    )


def _gate(*, registered_at: date = date(2026, 8, 1)) -> PreregisteredEvaluationGateV0:
    thresholds = _thresholds()
    return PreregisteredEvaluationGateV0(
        registration_artifact=_artifact("preregistered-gate"),
        registered_at=datetime(
            registered_at.year,
            registered_at.month,
            registered_at.day,
            12,
            tzinfo=TAIPEI,
        ),
        registered_thresholds_digest=thresholds.digest,
        thresholds=thresholds,
    )


def test_holdout_gate_passes_only_on_pinned_positive_clustered_evidence() -> None:
    rows = _rows()
    artifact = evaluate_candidate_prior(
        manifest=_manifest(rows),
        gate=_gate(),
        split=EvaluationSplit.HOLDOUT,
        observations=rows,
    )

    report = artifact.report
    assert report.gate_decision.verdict is FormalGateVerdict.PASS
    assert report.primary_comparison.net_expectancy_difference == Decimal("0.10")
    assert report.primary_comparison.confidence_lower == Decimal("0.10")
    assert report.subscription_allowed is False
    assert report.execution_allowed is False
    assert artifact.report_digest == evaluate_candidate_prior(
        manifest=_manifest(tuple(reversed(rows))),
        gate=_gate(),
        split=EvaluationSplit.HOLDOUT,
        observations=tuple(reversed(rows)),
    ).report_digest


def test_train_and_validation_cannot_claim_formal_gate_pass() -> None:
    rows = _rows((date(2026, 7, 1), date(2026, 7, 2)))
    report = evaluate_candidate_prior(
        manifest=_manifest(rows),
        gate=_gate(),
        split=EvaluationSplit.TRAIN,
        observations=rows,
    ).report

    assert report.gate_decision.verdict is FormalGateVerdict.NOT_APPLICABLE
    assert report.gate_decision.reason_codes == ("FORMAL_GATE_RESERVED_FOR_HOLDOUT",)


def test_holdout_fails_closed_when_gate_was_not_preregistered() -> None:
    rows = _rows()
    report = evaluate_candidate_prior(
        manifest=_manifest(rows),
        gate=_gate(registered_at=HOLDOUT.start),
        split=EvaluationSplit.HOLDOUT,
        observations=rows,
    ).report

    assert report.gate_decision.verdict is FormalGateVerdict.BLOCKED
    assert "GATE_NOT_REGISTERED_BEFORE_HOLDOUT" in report.gate_decision.reason_codes


def test_holdout_requires_matched_control_population() -> None:
    rows = tuple(
        replace(
            row,
            cohorts=tuple(
                cohort
                for cohort in row.cohorts
                if cohort is not EvaluationArm.MATCHED_CONTROL
            ),
        )
        for row in _rows()
    )
    report = evaluate_candidate_prior(
        manifest=_manifest(rows),
        gate=_gate(),
        split=EvaluationSplit.HOLDOUT,
        observations=rows,
    ).report

    assert report.gate_decision.verdict is FormalGateVerdict.INSUFFICIENT_EVIDENCE
    assert "MATCHED_CONTROL_POPULATION_EMPTY" in report.gate_decision.reason_codes


def test_observation_digest_or_split_drift_fails_closed() -> None:
    rows = _rows()
    manifest = _manifest(rows)
    changed = replace(rows[0], net_return=Decimal("0.09"), gross_return=Decimal("0.10"))

    with pytest.raises(FormalEvaluationError, match="pinned digest"):
        evaluate_candidate_prior(
            manifest=manifest,
            gate=_gate(),
            split=EvaluationSplit.HOLDOUT,
            observations=(changed, *rows[1:]),
        )

    with pytest.raises(FormalEvaluationError, match="outside"):
        evaluate_candidate_prior(
            manifest=manifest,
            gate=_gate(),
            split=EvaluationSplit.TRAIN,
            observations=rows,
        )


def test_execution_returns_must_follow_frozen_cost_identity() -> None:
    with pytest.raises(ValueError, match="gross_return minus cost_return"):
        replace(_rows()[0], net_return=Decimal("0.99"))


def test_registered_thresholds_digest_cannot_drift() -> None:
    thresholds = _thresholds()
    with pytest.raises(ValueError, match="registered thresholds digest"):
        PreregisteredEvaluationGateV0(
            registration_artifact=_artifact("gate"),
            registered_at=datetime(2026, 8, 1, tzinfo=TAIPEI),
            registered_thresholds_digest=DIGEST,
            thresholds=thresholds,
        )


def test_negative_primary_holdout_evidence_fails_formal_gate() -> None:
    rows = tuple(
        replace(
            row,
            gross_return=Decimal("-0.09"),
            net_return=Decimal("-0.10"),
        )
        if EvaluationArm.COMBINED in row.cohorts
        else replace(row, gross_return=Decimal("0.11"), net_return=Decimal("0.10"))
        for row in _rows()
    )
    report = evaluate_candidate_prior(
        manifest=_manifest(rows),
        gate=_gate(),
        split=EvaluationSplit.HOLDOUT,
        observations=rows,
    ).report

    assert report.gate_decision.verdict is FormalGateVerdict.FAIL
    assert "PRIMARY_CI_LOWER_NOT_POSITIVE" in report.gate_decision.reason_codes


def test_ineligible_composite_manifest_blocks_holdout_claim() -> None:
    rows = _rows()
    report = evaluate_candidate_prior(
        manifest=_manifest(
            rows,
            research_eligible=False,
            issue_codes=("PIT_CLASSIFICATION_COVERAGE_INCOMPLETE",),
        ),
        gate=_gate(),
        split=EvaluationSplit.HOLDOUT,
        observations=rows,
    ).report

    assert report.gate_decision.verdict is FormalGateVerdict.BLOCKED
    assert report.gate_decision.reason_codes == (
        "COMPOSITE_INPUT_NOT_RESEARCH_ELIGIBLE",
    )
