"""Canonical serialization for PR-008 evaluation inputs and reports."""

from __future__ import annotations

from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.domain import ArtifactIdentity, DefinitionIdentity

from .domain import (
    ArmComparison,
    ArmSummary,
    CompositeResearchInputManifestV1,
    EvaluationObservation,
    EvaluationThresholdsV0,
    FormalEvaluationReport,
    PreregisteredEvaluationGateV0,
    SessionRange,
)


def _artifact(value: ArtifactIdentity) -> dict[str, object]:
    return {"artifact_id": value.artifact_id, "digest": value.digest}


def _definition(value: DefinitionIdentity) -> dict[str, object]:
    return {
        "definition_digest": value.definition_digest,
        "definition_id": value.definition_id,
        "version": value.version,
    }


def _session_range(value: SessionRange) -> dict[str, object]:
    return {"end": value.end, "start": value.start}


def _manifest(value: CompositeResearchInputManifestV1) -> dict[str, object]:
    return {
        "calendar": _artifact(value.calendar),
        "candidate_prior_population": _artifact(value.candidate_prior_population),
        "code": _artifact(value.code),
        "corporate_actions": _artifact(value.corporate_actions),
        "cost_model": _definition(value.cost_model),
        "cost_model_effective_sessions": _session_range(
            value.cost_model_effective_sessions
        ),
        "coverage_amendment": _artifact(value.coverage_amendment),
        "coverage_audit": _artifact(value.coverage_audit),
        "coverage_matrix": _artifact(value.coverage_matrix),
        "evaluation_observations": _artifact(value.evaluation_observations),
        "evaluation_plan": _definition(value.evaluation_plan),
        "formal_evaluation_protocol": _artifact(
            value.formal_evaluation_protocol
        ),
        "frozen_population": _artifact(value.frozen_population),
        "holdout": _session_range(value.holdout),
        "institutional_partition_set": _artifact(
            value.institutional_partition_set
        ),
        "issue_codes": value.issue_codes,
        "matched_control_population": _artifact(value.matched_control_population),
        "outcome_definition": _definition(value.outcome_definition),
        "pit_classification_size": _artifact(value.pit_classification_size),
        "pit_universe": _artifact(value.pit_universe),
        "price_dataset": _artifact(value.price_dataset),
        "reference_data": _artifact(value.reference_data),
        "research_eligible": value.research_eligible,
        "setup_definition": _definition(value.setup_definition),
        "train": _session_range(value.train),
        "validation": _session_range(value.validation),
        "version": value.version,
    }


def serialize_research_input_manifest(
    manifest: CompositeResearchInputManifestV1,
) -> str:
    return canonical_json(_manifest(manifest))


def _thresholds(value: EvaluationThresholdsV0) -> dict[str, object]:
    return {
        "confidence_level": value.confidence_level,
        "maximum_guardrail_net_expectancy_deterioration": (
            value.maximum_guardrail_net_expectancy_deterioration
        ),
        "maximum_turnover_rate_increase": value.maximum_turnover_rate_increase,
        "minimum_executions_per_arm": value.minimum_executions_per_arm,
        "minimum_guardrail_executions_per_arm": value.minimum_guardrail_executions_per_arm,
        "minimum_sessions": value.minimum_sessions,
        "primary_metric": value.primary_metric,
        "required_liquidity_cohorts": value.required_liquidity_cohorts,
        "required_markets": value.required_markets,
        "version": value.version,
    }


def _gate(value: PreregisteredEvaluationGateV0) -> dict[str, object]:
    return {
        "registered_at": value.registered_at,
        "registered_thresholds_digest": value.registered_thresholds_digest,
        "registration_artifact": _artifact(value.registration_artifact),
        "thresholds": _thresholds(value.thresholds),
    }


def _observation(value: EvaluationObservation) -> dict[str, object]:
    return {
        "cohorts": value.cohorts,
        "cost_return": value.cost_return,
        "executed": value.executed,
        "first_valid_setup_at": value.first_valid_setup_at,
        "gross_return": value.gross_return,
        "liquidity_cohort": value.liquidity_cohort,
        "market": value.market,
        "net_return": value.net_return,
        "session_date": value.session_date,
        "setup_qualified": value.setup_qualified,
        "source_entry_digest": value.source_entry_digest,
        "symbol": value.symbol,
    }


def serialize_evaluation_observations(
    observations: tuple[EvaluationObservation, ...],
) -> str:
    ordered = tuple(
        sorted(
            observations,
            key=lambda row: (row.session_date, row.market.value, row.symbol),
        )
    )
    return canonical_json(
        {"observations": tuple(_observation(row) for row in ordered), "version": "v0"}
    )


def evaluation_observations_sha256(
    observations: tuple[EvaluationObservation, ...],
) -> str:
    return sha256_text(serialize_evaluation_observations(observations))


def _summary(value: ArmSummary) -> dict[str, object]:
    return {
        "arm": value.arm,
        "candidate_count": value.candidate_count,
        "cost_expectancy": value.cost_expectancy,
        "execution_count": value.execution_count,
        "gross_expectancy": value.gross_expectancy,
        "net_expectancy": value.net_expectancy,
        "setup_count": value.setup_count,
        "setup_precision": value.setup_precision,
        "turnover_rate": value.turnover_rate,
    }


def _comparison(value: ArmComparison) -> dict[str, object]:
    return {
        "arm": value.arm,
        "baseline": value.baseline,
        "clustered_session_count": value.clustered_session_count,
        "confidence_level": value.confidence_level,
        "confidence_lower": value.confidence_lower,
        "confidence_upper": value.confidence_upper,
        "net_expectancy_difference": value.net_expectancy_difference,
    }


def serialize_evaluation_report(report: FormalEvaluationReport) -> str:
    return canonical_json(
        {
            "execution_allowed": report.execution_allowed,
            "gate": _gate(report.gate),
            "gate_decision": {
                "reason_codes": report.gate_decision.reason_codes,
                "verdict": report.gate_decision.verdict,
            },
            "liquidity_guardrails": tuple(
                {"cohort": cohort, "comparison": _comparison(comparison)}
                for cohort, comparison in report.liquidity_guardrails
            ),
            "manifest": _manifest(report.manifest),
            "market_guardrails": tuple(
                {"market": market, "comparison": _comparison(comparison)}
                for market, comparison in report.market_guardrails
            ),
            "observation_count": report.observation_count,
            "primary_comparison": _comparison(report.primary_comparison),
            "session_count": report.session_count,
            "split": report.split,
            "subscription_allowed": report.subscription_allowed,
            "summaries": tuple(_summary(summary) for summary in report.summaries),
            "version": report.version,
        }
    )
