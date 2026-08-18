"""Versioned, replay-safe Momentum domain contracts.

Feature-driven engines, the state reducer, and the in-memory projection live in
explicit submodules.  This package surface exposes only dependency-free model
contracts; broker actions remain outside the Momentum domain.
"""

from signals.models import (
    EntryMode,
    EntryOpportunity,
    EntryOpportunityStatus,
    EntryPolicyDecision,
    EntryRiskLevel,
    EpisodeStatus,
    EvidenceStatus,
    SignalDetail,
    EvidenceUpdate,
    MomentumEntryPolicyConfig,
    MomentumEpisode,
    MomentumSignal,
    MomentumStage,
    RiskGateStatus,
    SignalEvaluationStatus,
    SignalFamily,
    SignalResult,
    StageTransition,
    evaluate_momentum_entry_opportunity,
    evaluate_momentum_entry_policy,
)

__all__ = [
    "EntryMode",
    "EntryOpportunity",
    "EntryOpportunityStatus",
    "EntryPolicyDecision",
    "EntryRiskLevel",
    "EpisodeStatus",
    "EvidenceStatus",
    "EvidenceUpdate",
    "MomentumEntryPolicyConfig",
    "MomentumEpisode",
    "MomentumSignal",
    "MomentumStage",
    "RiskGateStatus",
    "SignalEvaluationStatus",
    "SignalFamily",
    "SignalDetail",
    "SignalResult",
    "StageTransition",
    "evaluate_momentum_entry_opportunity",
    "evaluate_momentum_entry_policy",
]
