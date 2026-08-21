"""Deterministic session-clustered evaluation for frozen candidate cohorts."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from institutional_data.serialization import sha256_text

from .domain import (
    ArmComparison,
    ArmSummary,
    CompositeResearchInputManifestV1,
    EvaluationArm,
    EvaluationGateDecision,
    EvaluationObservation,
    EvaluationSplit,
    FormalEvaluationArtifact,
    FormalEvaluationReport,
    FormalGateVerdict,
    PreregisteredEvaluationGateV0,
)
from .serialization import evaluation_observations_sha256, serialize_evaluation_report


_Z_SCORE = {
    Decimal("0.90"): Decimal("1.6448536269514722"),
    Decimal("0.95"): Decimal("1.959963984540054"),
    Decimal("0.99"): Decimal("2.5758293035489004"),
}


class FormalEvaluationError(ValueError):
    """Evaluation inputs violate a frozen PR-008 contract."""


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal(0)) / Decimal(len(values))


def _arm_rows(
    rows: tuple[EvaluationObservation, ...], arm: EvaluationArm
) -> tuple[EvaluationObservation, ...]:
    return tuple(row for row in rows if arm in row.cohorts)


def _summary(
    rows: tuple[EvaluationObservation, ...], arm: EvaluationArm
) -> ArmSummary:
    candidates = _arm_rows(rows, arm)
    setups = tuple(row for row in candidates if row.setup_qualified)
    executed = tuple(row for row in candidates if row.executed)
    gross = tuple(row.gross_return for row in executed if row.gross_return is not None)
    costs = tuple(row.cost_return for row in executed if row.cost_return is not None)
    net = tuple(row.net_return for row in executed if row.net_return is not None)
    candidate_count = len(candidates)
    return ArmSummary(
        arm=arm,
        candidate_count=candidate_count,
        setup_count=len(setups),
        setup_precision=(
            Decimal(len(setups)) / Decimal(candidate_count)
            if candidate_count
            else None
        ),
        execution_count=len(executed),
        gross_expectancy=_mean(gross),
        cost_expectancy=_mean(costs),
        net_expectancy=_mean(net),
        turnover_rate=(
            Decimal(len(executed)) / Decimal(candidate_count)
            if candidate_count
            else None
        ),
    )


def _executed_values_by_session(
    rows: tuple[EvaluationObservation, ...], arm: EvaluationArm
) -> dict[object, tuple[Decimal, ...]]:
    grouped: dict[object, list[Decimal]] = defaultdict(list)
    for row in rows:
        if arm in row.cohorts and row.executed:
            assert row.net_return is not None
            grouped[row.session_date].append(row.net_return)
    return {session: tuple(values) for session, values in grouped.items()}


def _comparison(
    rows: tuple[EvaluationObservation, ...],
    arm: EvaluationArm,
    baseline: EvaluationArm,
    confidence_level: Decimal,
) -> ArmComparison:
    arm_values = _executed_values_by_session(rows, arm)
    baseline_values = _executed_values_by_session(rows, baseline)
    arm_flat = tuple(value for values in arm_values.values() for value in values)
    baseline_flat = tuple(
        value for values in baseline_values.values() for value in values
    )
    arm_mean = _mean(arm_flat)
    baseline_mean = _mean(baseline_flat)
    sessions = tuple(sorted(set(arm_values) | set(baseline_values)))
    if arm_mean is None or baseline_mean is None:
        return ArmComparison(
            arm=arm,
            baseline=baseline,
            net_expectancy_difference=None,
            confidence_lower=None,
            confidence_upper=None,
            confidence_level=confidence_level,
            clustered_session_count=len(sessions),
        )
    difference = arm_mean - baseline_mean
    if len(sessions) < 2:
        return ArmComparison(
            arm=arm,
            baseline=baseline,
            net_expectancy_difference=difference,
            confidence_lower=None,
            confidence_upper=None,
            confidence_level=confidence_level,
            clustered_session_count=len(sessions),
        )
    arm_count = Decimal(len(arm_flat))
    baseline_count = Decimal(len(baseline_flat))
    influences = []
    for session in sessions:
        arm_influence = sum(
            (value - arm_mean for value in arm_values.get(session, ())),
            Decimal(0),
        ) / arm_count
        baseline_influence = sum(
            (value - baseline_mean for value in baseline_values.get(session, ())),
            Decimal(0),
        ) / baseline_count
        influences.append(arm_influence - baseline_influence)
    cluster_count = Decimal(len(sessions))
    variance = (
        cluster_count
        / (cluster_count - Decimal(1))
        * sum((value * value for value in influences), Decimal(0))
    )
    margin = _Z_SCORE[confidence_level] * variance.sqrt()
    return ArmComparison(
        arm=arm,
        baseline=baseline,
        net_expectancy_difference=difference,
        confidence_lower=difference - margin,
        confidence_upper=difference + margin,
        confidence_level=confidence_level,
        clustered_session_count=len(sessions),
    )


def _gate_decision(
    *,
    manifest: CompositeResearchInputManifestV1,
    gate: PreregisteredEvaluationGateV0,
    split: EvaluationSplit,
    rows: tuple[EvaluationObservation, ...],
    summaries: tuple[ArmSummary, ...],
    primary: ArmComparison,
    market_guardrails: tuple[tuple[object, ArmComparison], ...],
    liquidity_guardrails: tuple[tuple[str, ArmComparison], ...],
) -> EvaluationGateDecision:
    if split is not EvaluationSplit.HOLDOUT:
        return EvaluationGateDecision(
            FormalGateVerdict.NOT_APPLICABLE,
            ("FORMAL_GATE_RESERVED_FOR_HOLDOUT",),
        )
    blocked = []
    if not manifest.research_eligible or manifest.issue_codes:
        blocked.append("COMPOSITE_INPUT_NOT_RESEARCH_ELIGIBLE")
    if gate.registered_at.date() >= manifest.holdout.start:
        blocked.append("GATE_NOT_REGISTERED_BEFORE_HOLDOUT")
    if blocked:
        return EvaluationGateDecision(FormalGateVerdict.BLOCKED, tuple(blocked))

    thresholds = gate.thresholds
    summary_by_arm = {summary.arm: summary for summary in summaries}
    insufficient = []
    if len({row.session_date for row in rows}) < thresholds.minimum_sessions:
        insufficient.append("MINIMUM_SESSIONS_NOT_MET")
    if not any(EvaluationArm.MATCHED_CONTROL in row.cohorts for row in rows):
        insufficient.append("MATCHED_CONTROL_POPULATION_EMPTY")
    for arm in (EvaluationArm.PRICE_ONLY, EvaluationArm.COMBINED):
        if summary_by_arm[arm].execution_count < thresholds.minimum_executions_per_arm:
            insufficient.append(f"{arm.value}_MINIMUM_EXECUTIONS_NOT_MET")
    if primary.confidence_lower is None:
        insufficient.append("PRIMARY_CONFIDENCE_INTERVAL_UNAVAILABLE")

    for label, comparison in (*market_guardrails, *liquidity_guardrails):
        subgroup = tuple(
            row
            for row in rows
            if row.market == label or row.liquidity_cohort == label
        )
        for arm in (EvaluationArm.PRICE_ONLY, EvaluationArm.COMBINED):
            execution_count = sum(
                1 for row in subgroup if arm in row.cohorts and row.executed
            )
            if execution_count < thresholds.minimum_guardrail_executions_per_arm:
                insufficient.append(f"GUARDRAIL_{label}_{arm.value}_EXECUTIONS_LOW")
        if comparison.confidence_lower is None:
            insufficient.append(f"GUARDRAIL_{label}_CONFIDENCE_UNAVAILABLE")
    if insufficient:
        return EvaluationGateDecision(
            FormalGateVerdict.INSUFFICIENT_EVIDENCE,
            tuple(sorted(set(insufficient))),
        )

    failures = []
    assert primary.confidence_lower is not None
    if primary.confidence_lower <= 0:
        failures.append("PRIMARY_CI_LOWER_NOT_POSITIVE")
    combined_turnover = summary_by_arm[EvaluationArm.COMBINED].turnover_rate
    price_turnover = summary_by_arm[EvaluationArm.PRICE_ONLY].turnover_rate
    assert combined_turnover is not None and price_turnover is not None
    if (
        combined_turnover - price_turnover
        > thresholds.maximum_turnover_rate_increase
    ):
        failures.append("TURNOVER_RATE_GUARDRAIL_FAILED")
    deterioration_floor = -thresholds.maximum_guardrail_net_expectancy_deterioration
    for label, comparison in (*market_guardrails, *liquidity_guardrails):
        assert comparison.confidence_lower is not None
        if comparison.confidence_lower < deterioration_floor:
            failures.append(f"GUARDRAIL_{label}_NET_EXPECTANCY_FAILED")
    if failures:
        return EvaluationGateDecision(FormalGateVerdict.FAIL, tuple(failures))
    return EvaluationGateDecision(FormalGateVerdict.PASS, ("PREREGISTERED_GATE_PASSED",))


def evaluate_candidate_prior(
    *,
    manifest: CompositeResearchInputManifestV1,
    gate: PreregisteredEvaluationGateV0,
    split: EvaluationSplit,
    observations: tuple[EvaluationObservation, ...],
) -> FormalEvaluationArtifact:
    """Evaluate one time split without changing candidate or trading behavior."""

    split = EvaluationSplit(split)
    if not observations:
        raise FormalEvaluationError("evaluation observations must not be empty")
    identities = tuple(
        (row.session_date, row.market, row.symbol) for row in observations
    )
    if len(identities) != len(set(identities)):
        raise FormalEvaluationError("evaluation observation identities must be unique")
    expected_range = manifest.sessions_for(split)
    if any(not expected_range.contains(row.session_date) for row in observations):
        raise FormalEvaluationError("observation lies outside the requested time split")
    expected_digest = manifest.evaluation_observations.digest
    if evaluation_observations_sha256(observations) != expected_digest:
        raise FormalEvaluationError("evaluation observations differ from pinned digest")

    ordered = tuple(
        sorted(
            observations,
            key=lambda row: (row.session_date, row.market.value, row.symbol),
        )
    )
    summaries = tuple(_summary(ordered, arm) for arm in EvaluationArm)
    confidence = gate.thresholds.confidence_level
    primary = _comparison(
        ordered,
        EvaluationArm.COMBINED,
        EvaluationArm.PRICE_ONLY,
        confidence,
    )
    market_guardrails = tuple(
        (
            market,
            _comparison(
                tuple(row for row in ordered if row.market is market),
                EvaluationArm.COMBINED,
                EvaluationArm.PRICE_ONLY,
                confidence,
            ),
        )
        for market in gate.thresholds.required_markets
    )
    liquidity_guardrails = tuple(
        (
            cohort,
            _comparison(
                tuple(row for row in ordered if row.liquidity_cohort == cohort),
                EvaluationArm.COMBINED,
                EvaluationArm.PRICE_ONLY,
                confidence,
            ),
        )
        for cohort in gate.thresholds.required_liquidity_cohorts
    )
    decision = _gate_decision(
        manifest=manifest,
        gate=gate,
        split=split,
        rows=ordered,
        summaries=summaries,
        primary=primary,
        market_guardrails=market_guardrails,
        liquidity_guardrails=liquidity_guardrails,
    )
    report = FormalEvaluationReport(
        manifest=manifest,
        gate=gate,
        split=split,
        session_count=len({row.session_date for row in ordered}),
        observation_count=len(ordered),
        summaries=summaries,
        primary_comparison=primary,
        market_guardrails=market_guardrails,
        liquidity_guardrails=liquidity_guardrails,
        gate_decision=decision,
    )
    report_json = serialize_evaluation_report(report)
    return FormalEvaluationArtifact(
        report=report,
        report_json=report_json,
        report_digest=sha256_text(report_json),
    )
