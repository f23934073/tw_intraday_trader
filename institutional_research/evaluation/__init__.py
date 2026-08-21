"""Formal, research-only evaluation contracts for institutional candidate priors."""

from .application import evaluate_candidate_prior
from .domain import (
    ArmComparison,
    ArmSummary,
    CompositeResearchInputManifestV1,
    EvaluationArm,
    EvaluationGateDecision,
    EvaluationObservation,
    EvaluationSplit,
    EvaluationThresholdsV0,
    FormalEvaluationArtifact,
    FormalEvaluationReport,
    FormalGateVerdict,
    PreregisteredEvaluationGateV0,
    SessionRange,
)
from .serialization import (
    evaluation_observations_sha256,
    serialize_evaluation_report,
    serialize_research_input_manifest,
)

__all__ = [
    "ArmComparison",
    "ArmSummary",
    "CompositeResearchInputManifestV1",
    "EvaluationArm",
    "EvaluationGateDecision",
    "EvaluationObservation",
    "EvaluationSplit",
    "EvaluationThresholdsV0",
    "FormalEvaluationArtifact",
    "FormalEvaluationReport",
    "FormalGateVerdict",
    "PreregisteredEvaluationGateV0",
    "SessionRange",
    "evaluate_candidate_prior",
    "evaluation_observations_sha256",
    "serialize_evaluation_report",
    "serialize_research_input_manifest",
]
