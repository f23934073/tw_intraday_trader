from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

import signals.entry_specification as entry_module
from signals.entry_specification import (
    UNDECIDED,
    AblationCohortPlan,
    CandidateSetEvidenceRequirement,
    EntrySpecification,
    ExecutionBinding,
    FalsifyingCase,
    HardPredicate,
    RequiredDatum,
    ScoreThreshold,
    ScoredEvidence,
    SelectionPolicyRef,
    Split,
    StageGate,
)


def sha(character: str) -> str:
    return character * 64


def complete_specification() -> EntrySpecification:
    return EntrySpecification(
        schema_version="entry-specification-v1",
        spec_id="momentum-entry-contract-test",
        strategy_id="momentum-entry",
        strategy_version="v1",
        required_data=(
            RequiredDatum(
                feature_id="price",
                must_be_valid=True,
                must_meet_threshold=True,
                max_staleness_seconds=Decimal("5.0"),
                data_health_required="HEALTHY",
                triggers_when_missing=False,
            ),
        ),
        hard_predicates=(
            HardPredicate(
                predicate_id="triggered",
                gate_id="gate.evaluation_status_triggered",
                description="signal evaluation is triggered",
                falsifying_case=FalsifyingCase(
                    kind="LEGAL_REACHABLE",
                    description="canonical producer emits NOT_TRIGGERED",
                ),
            ),
        ),
        scored_evidence=(
            ScoredEvidence(
                rule_id="breakout",
                weight=35,
                threshold=None,
                direction="BOOL",
                missing_handling="BLOCK",
                compensable=False,
            ),
            ScoredEvidence(
                rule_id="volume",
                weight=65,
                threshold="1.50",
                direction="GTE",
                missing_handling="ZERO_POINTS",
                compensable=True,
            ),
        ),
        score_threshold=ScoreThreshold(
            threshold=70,
            fixed_mandatory_points=35,
            optional_pool_points=65,
            minimal_qualifying_combinations=(("breakout", "volume"),),
        ),
        allowed_evidence_signatures=("breakout+volume",),
        stage_gate=StageGate(
            whitelist=("ACCELERATING", "NEAR_LIMIT_UP", "LIMIT_TOUCHED"),
            episode_status_required="ACTIVE",
            reentry_precedence=("COOLDOWN", "DEDUPLICATION"),
            cooldown_seconds=Decimal("120"),
        ),
        selection_function=SelectionPolicyRef(
            policy_id="fixture-policy",
            policy_digest=sha("a"),
            max_entries_per_session=1,
            deduplication_key_rule="signal_digest",
        ),
        candidate_set_evidence=CandidateSetEvidenceRequirement(
            required=True,
            record_schema_version="candidate-set-evidence-v1",
        ),
        ablation_cohort_plan=AblationCohortPlan(
            changed_field="allowed_evidence_signatures",
            control_spec_digest=sha("b"),
            split=Split(
                in_sample="2024-H1",
                out_of_sample="2024-H2",
                walk_forward="monthly",
            ),
            minimum_trades=30,
            regime_strata=("up", "down"),
        ),
        execution_admission_binding=ExecutionBinding(
            execution_policy_digest=sha("c"),
            cost_policy_digest=sha("d"),
            admission_policy_id="admission-v1",
            fill_model="CALIBRATED",
            performance_claims_allowed=True,
        ),
        qualification_evidence_profile=UNDECIDED,
    )


def test_entry_decision_digest_covers_only_declared_identity_inputs():
    specification = complete_specification()
    baseline = specification.entry_decision_digest

    assert len(baseline) == 64
    assert replace(specification, spec_id="display-only-id").entry_decision_digest == baseline
    assert replace(
        specification,
        ablation_cohort_plan=UNDECIDED,
    ).entry_decision_digest == baseline
    assert replace(
        specification,
        execution_admission_binding=replace(
            specification.execution_admission_binding,
            execution_policy_digest=sha("e"),
        ),
    ).entry_decision_digest == baseline
    changed = replace(
        specification,
        stage_gate=replace(
            specification.stage_gate,
            whitelist=("ACCELERATING",),
        ),
    )
    assert changed.entry_decision_digest != baseline
    assert specification.to_wire()["entry_decision_digest"] == baseline


def test_slice_one_readiness_is_always_false_and_structural_predicate_is_narrow():
    specification = complete_specification()

    assert specification.is_structurally_defined() is True
    assert specification.is_research_ready() is False
    assert specification.is_ablation_ready() is False
    assert specification.undecided_fields() == ("qualification_evidence_profile",)
    assert not hasattr(specification, "is_qualification_ready")

    incomplete = replace(
        specification,
        stage_gate=replace(specification.stage_gate, cooldown_seconds=UNDECIDED),
    )
    assert incomplete.is_structurally_defined() is False
    assert "stage_gate.cooldown_seconds" in incomplete.undecided_fields()
    ablation_undecided = replace(specification, ablation_cohort_plan=UNDECIDED)
    assert ablation_undecided.is_structurally_defined() is True
    assert ablation_undecided.is_research_ready() is False
    assert ablation_undecided.is_ablation_ready() is False


def test_qualification_field_accepts_only_the_undecided_singleton():
    specification = complete_specification()

    with pytest.raises(TypeError, match="accepts only UNDECIDED"):
        replace(specification, qualification_evidence_profile=("invented",))  # type: ignore[arg-type]
    assert not hasattr(entry_module, "QualificationEvidenceProfile")


def test_undecided_and_decimal_scale_are_digest_significant():
    specification = complete_specification()
    undecided = replace(
        specification,
        allowed_evidence_signatures=UNDECIDED,
    )
    scale_changed = replace(
        specification,
        required_data=(
            replace(
                specification.required_data[0],
                max_staleness_seconds=Decimal("5.00"),
            ),
        ),
    )

    assert undecided.entry_decision_digest != specification.entry_decision_digest
    assert scale_changed.entry_decision_digest != specification.entry_decision_digest
    assert undecided.to_wire()["allowed_evidence_signatures"] == "__UNDECIDED__"


def test_score_stage_signature_and_execution_validators_fail_closed():
    specification = complete_specification()

    with pytest.raises(ValueError, match="fixed and optional"):
        replace(
            specification,
            score_threshold=replace(
                specification.score_threshold,
                optional_pool_points=64,
            ),
        )
    with pytest.raises(ValueError, match="unknown MomentumStage"):
        replace(
            specification,
            stage_gate=replace(specification.stage_gate, whitelist=("UNKNOWN",)),
        )
    with pytest.raises(ValueError, match="unique and sorted"):
        replace(specification, allowed_evidence_signatures=("volume+breakout",))
    with pytest.raises(ValueError, match="CALIBRATED"):
        replace(
            specification,
            execution_admission_binding=replace(
                specification.execution_admission_binding,
                fill_model="EXPLICIT_ASSUMPTION",
                performance_claims_allowed=True,
            ),
        )


def test_scored_evidence_threshold_shape_is_strict():
    with pytest.raises(ValueError, match="BOOL evidence threshold"):
        ScoredEvidence(
            rule_id="boolean",
            weight=1,
            threshold="1",
            direction="BOOL",
            missing_handling="BLOCK",
            compensable=False,
        )
    with pytest.raises(ValueError, match="Decimal string"):
        ScoredEvidence(
            rule_id="numeric",
            weight=1,
            threshold="not-decimal",
            direction="GTE",
            missing_handling="BLOCK",
            compensable=False,
        )
