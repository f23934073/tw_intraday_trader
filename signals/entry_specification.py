"""Pure, undecided-aware Momentum Entry specification contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from signals._contract_wire import UNDECIDED, Undecided
from signals._contract_wire import digest as _digest
from signals._contract_wire import to_wire as _to_wire
from signals.models import MomentumStage


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_non_empty(value: str, field_name: str, *, max_length: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")


def _require_decimal_or_undecided(
    value: Decimal | Undecided,
    field_name: str,
    *,
    non_negative: bool = True,
) -> None:
    if value is UNDECIDED:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"{field_name} must be Decimal or UNDECIDED")
    if non_negative and value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _undecided_paths(value: object, prefix: str) -> tuple[str, ...]:
    if value is UNDECIDED:
        return (prefix,)
    if is_dataclass(value) and not isinstance(value, type):
        paths: list[str] = []
        for item in fields(value):
            child = f"{prefix}.{item.name}" if prefix else item.name
            paths.extend(_undecided_paths(getattr(value, item.name), child))
        return tuple(paths)
    if isinstance(value, Mapping):
        paths = []
        for key in sorted(value, key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_undecided_paths(value[key], child))
        return tuple(paths)
    if isinstance(value, (tuple, list)):
        paths = []
        for index, item in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            paths.extend(_undecided_paths(item, child))
        return tuple(paths)
    return ()


@dataclass(frozen=True)
class RequiredDatum:
    feature_id: str
    must_be_valid: bool
    must_meet_threshold: bool
    max_staleness_seconds: Decimal | Undecided
    data_health_required: Literal["HEALTHY"] | Undecided
    triggers_when_missing: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.feature_id, "feature_id")
        for value, name in (
            (self.must_be_valid, "must_be_valid"),
            (self.must_meet_threshold, "must_meet_threshold"),
            (self.triggers_when_missing, "triggers_when_missing"),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be bool")
        _require_decimal_or_undecided(
            self.max_staleness_seconds,
            "max_staleness_seconds",
        )
        if self.data_health_required is not UNDECIDED and (
            self.data_health_required != "HEALTHY"
        ):
            raise ValueError("data_health_required must be HEALTHY or UNDECIDED")


@dataclass(frozen=True)
class FalsifyingCase:
    kind: Literal["LEGAL_REACHABLE", "CONTRACT_VIOLATION"]
    description: str

    def __post_init__(self) -> None:
        if self.kind not in {"LEGAL_REACHABLE", "CONTRACT_VIOLATION"}:
            raise ValueError("invalid falsifying case kind")
        _require_non_empty(self.description, "falsifying case description")


@dataclass(frozen=True)
class HardPredicate:
    predicate_id: str
    gate_id: str | None
    description: str
    falsifying_case: FalsifyingCase | Undecided

    def __post_init__(self) -> None:
        _require_non_empty(self.predicate_id, "predicate_id")
        if self.gate_id is not None:
            _require_non_empty(self.gate_id, "gate_id")
        _require_non_empty(self.description, "hard predicate description")
        if self.falsifying_case is not UNDECIDED and not isinstance(
            self.falsifying_case,
            FalsifyingCase,
        ):
            raise TypeError("falsifying_case must be FalsifyingCase or UNDECIDED")


@dataclass(frozen=True)
class ScoredEvidence:
    rule_id: str
    weight: int
    threshold: str | None
    direction: Literal["GTE", "LTE", "BOOL"]
    missing_handling: Literal["ZERO_POINTS", "BLOCK"] | Undecided
    compensable: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.rule_id, "rule_id")
        if isinstance(self.weight, bool) or not isinstance(self.weight, int) or self.weight <= 0:
            raise ValueError("weight must be a positive integer")
        if self.direction not in {"GTE", "LTE", "BOOL"}:
            raise ValueError("invalid evidence direction")
        if self.direction == "BOOL":
            if self.threshold is not None:
                raise ValueError("BOOL evidence threshold must be None")
        else:
            if not isinstance(self.threshold, str) or not self.threshold.strip():
                raise ValueError("numeric evidence threshold must be a Decimal string")
            try:
                parsed = Decimal(self.threshold)
            except InvalidOperation as error:
                raise ValueError("numeric evidence threshold must be a Decimal string") from error
            if not parsed.is_finite():
                raise ValueError("numeric evidence threshold must be finite")
        if self.missing_handling is not UNDECIDED and self.missing_handling not in {
            "ZERO_POINTS",
            "BLOCK",
        }:
            raise ValueError("invalid missing_handling")
        if not isinstance(self.compensable, bool):
            raise TypeError("compensable must be bool")


@dataclass(frozen=True)
class ScoreThreshold:
    threshold: int
    fixed_mandatory_points: int
    optional_pool_points: int
    minimal_qualifying_combinations: tuple[tuple[str, ...], ...] | Undecided

    def __post_init__(self) -> None:
        for value, name in (
            (self.threshold, "threshold"),
            (self.fixed_mandatory_points, "fixed_mandatory_points"),
            (self.optional_pool_points, "optional_pool_points"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        combinations = self.minimal_qualifying_combinations
        if combinations is UNDECIDED:
            return
        if not isinstance(combinations, tuple):
            raise TypeError("minimal_qualifying_combinations must be tuple or UNDECIDED")
        for combination in combinations:
            if not isinstance(combination, tuple) or not combination:
                raise ValueError("minimal qualifying combinations must be non-empty tuples")
            for rule_id in combination:
                _require_non_empty(rule_id, "minimal qualifying rule_id")


@dataclass(frozen=True)
class StageGate:
    whitelist: tuple[str, ...]
    episode_status_required: Literal["ACTIVE"] | Undecided
    reentry_precedence: tuple[Literal["COOLDOWN", "DEDUPLICATION"], ...] | Undecided
    cooldown_seconds: Decimal | Undecided

    def __post_init__(self) -> None:
        if not isinstance(self.whitelist, tuple):
            raise TypeError("stage whitelist must be a tuple")
        allowed_stages = {stage.value for stage in MomentumStage}
        if any(stage not in allowed_stages for stage in self.whitelist):
            raise ValueError("stage whitelist contains an unknown MomentumStage")
        if len(set(self.whitelist)) != len(self.whitelist):
            raise ValueError("stage whitelist must not contain duplicates")
        if self.episode_status_required is not UNDECIDED and (
            self.episode_status_required != "ACTIVE"
        ):
            raise ValueError("episode_status_required must be ACTIVE or UNDECIDED")
        precedence = self.reentry_precedence
        if precedence is not UNDECIDED and (
            not isinstance(precedence, tuple)
            or len(precedence) != 2
            or set(precedence) != {"COOLDOWN", "DEDUPLICATION"}
        ):
            raise ValueError("reentry_precedence must contain COOLDOWN and DEDUPLICATION once")
        _require_decimal_or_undecided(self.cooldown_seconds, "cooldown_seconds")


@dataclass(frozen=True)
class SelectionPolicyRef:
    policy_id: str
    policy_digest: str
    max_entries_per_session: int | Undecided
    deduplication_key_rule: str | Undecided

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "selection policy_id")
        _require_sha256(self.policy_digest, "selection policy_digest")
        if self.max_entries_per_session is not UNDECIDED and (
            isinstance(self.max_entries_per_session, bool)
            or not isinstance(self.max_entries_per_session, int)
            or self.max_entries_per_session <= 0
        ):
            raise ValueError("max_entries_per_session must be positive or UNDECIDED")
        if self.deduplication_key_rule is not UNDECIDED:
            _require_non_empty(self.deduplication_key_rule, "deduplication_key_rule")


@dataclass(frozen=True)
class CandidateSetEvidenceRequirement:
    required: bool
    record_schema_version: Literal["candidate-set-evidence-v1"]

    def __post_init__(self) -> None:
        if not isinstance(self.required, bool):
            raise TypeError("candidate-set evidence required must be bool")
        if self.record_schema_version != "candidate-set-evidence-v1":
            raise ValueError("unsupported candidate-set evidence schema")


@dataclass(frozen=True)
class Split:
    in_sample: str
    out_of_sample: str
    walk_forward: str

    def __post_init__(self) -> None:
        _require_non_empty(self.in_sample, "in_sample")
        _require_non_empty(self.out_of_sample, "out_of_sample")
        _require_non_empty(self.walk_forward, "walk_forward")


_ENTRY_FIELD_NAMES = {
    "required_data",
    "hard_predicates",
    "scored_evidence",
    "score_threshold",
    "allowed_evidence_signatures",
    "stage_gate",
    "selection_function",
    "candidate_set_evidence",
    "entry_decision_digest",
    "ablation_cohort_plan",
    "execution_admission_binding",
    "qualification_evidence_profile",
}


@dataclass(frozen=True)
class AblationCohortPlan:
    changed_field: str
    control_spec_digest: str
    split: Split
    minimum_trades: int
    regime_strata: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.changed_field not in _ENTRY_FIELD_NAMES:
            raise ValueError("changed_field must name an Entry Specification 3.x field")
        _require_sha256(self.control_spec_digest, "control_spec_digest")
        if not isinstance(self.split, Split):
            raise TypeError("split must be Split")
        if (
            isinstance(self.minimum_trades, bool)
            or not isinstance(self.minimum_trades, int)
            or self.minimum_trades <= 0
        ):
            raise ValueError("minimum_trades must be a positive integer")
        if not isinstance(self.regime_strata, tuple):
            raise TypeError("regime_strata must be a tuple")
        for stratum in self.regime_strata:
            _require_non_empty(stratum, "regime stratum")


@dataclass(frozen=True)
class ExecutionBinding:
    execution_policy_digest: str | Undecided
    cost_policy_digest: str | Undecided
    admission_policy_id: str | Undecided
    fill_model: Literal["EXPLICIT_ASSUMPTION", "CALIBRATED"] | Undecided
    performance_claims_allowed: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.execution_policy_digest, "execution_policy_digest"),
            (self.cost_policy_digest, "cost_policy_digest"),
        ):
            if value is not UNDECIDED:
                _require_sha256(value, name)
        if self.admission_policy_id is not UNDECIDED:
            _require_non_empty(self.admission_policy_id, "admission_policy_id")
        if self.fill_model is not UNDECIDED and self.fill_model not in {
            "EXPLICIT_ASSUMPTION",
            "CALIBRATED",
        }:
            raise ValueError("invalid fill_model")
        if not isinstance(self.performance_claims_allowed, bool):
            raise TypeError("performance_claims_allowed must be bool")
        if self.fill_model != "CALIBRATED" and self.performance_claims_allowed:
            raise ValueError("performance claims require a CALIBRATED fill model")


@dataclass(frozen=True)
class EntrySpecification:
    schema_version: Literal["entry-specification-v1"]
    spec_id: str
    strategy_id: str
    strategy_version: str
    required_data: tuple[RequiredDatum, ...]
    hard_predicates: tuple[HardPredicate, ...]
    scored_evidence: tuple[ScoredEvidence, ...]
    score_threshold: ScoreThreshold
    allowed_evidence_signatures: tuple[str, ...] | Undecided
    stage_gate: StageGate
    selection_function: SelectionPolicyRef
    candidate_set_evidence: CandidateSetEvidenceRequirement
    ablation_cohort_plan: AblationCohortPlan | Undecided
    execution_admission_binding: ExecutionBinding
    qualification_evidence_profile: Undecided

    def __post_init__(self) -> None:
        if self.schema_version != "entry-specification-v1":
            raise ValueError("unsupported entry specification schema")
        _require_non_empty(self.spec_id, "spec_id", max_length=96)
        _require_non_empty(self.strategy_id, "strategy_id")
        _require_non_empty(self.strategy_version, "strategy_version")
        self._validate_tuple(self.required_data, RequiredDatum, "required_data")
        self._validate_tuple(self.hard_predicates, HardPredicate, "hard_predicates")
        self._validate_tuple(self.scored_evidence, ScoredEvidence, "scored_evidence")
        if not isinstance(self.score_threshold, ScoreThreshold):
            raise TypeError("score_threshold must be ScoreThreshold")
        if not isinstance(self.stage_gate, StageGate):
            raise TypeError("stage_gate must be StageGate")
        if not isinstance(self.selection_function, SelectionPolicyRef):
            raise TypeError("selection_function must be SelectionPolicyRef")
        if not isinstance(self.candidate_set_evidence, CandidateSetEvidenceRequirement):
            raise TypeError("candidate_set_evidence must be CandidateSetEvidenceRequirement")
        if self.ablation_cohort_plan is not UNDECIDED and not isinstance(
            self.ablation_cohort_plan,
            AblationCohortPlan,
        ):
            raise TypeError("ablation_cohort_plan must be AblationCohortPlan or UNDECIDED")
        if not isinstance(self.execution_admission_binding, ExecutionBinding):
            raise TypeError("execution_admission_binding must be ExecutionBinding")
        if self.qualification_evidence_profile is not UNDECIDED:
            raise TypeError("qualification_evidence_profile accepts only UNDECIDED in Slice 1")
        self._validate_unique_ids()
        self._validate_score_contract()
        self._validate_signatures()

    @staticmethod
    def _validate_tuple(value: object, item_type: type[object], field_name: str) -> None:
        if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
            raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}")

    def _validate_unique_ids(self) -> None:
        collections = (
            (tuple(item.feature_id for item in self.required_data), "feature_id"),
            (tuple(item.predicate_id for item in self.hard_predicates), "predicate_id"),
            (tuple(item.rule_id for item in self.scored_evidence), "rule_id"),
        )
        for values, name in collections:
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name}")

    def _validate_score_contract(self) -> None:
        total = sum(item.weight for item in self.scored_evidence)
        threshold = self.score_threshold
        if threshold.fixed_mandatory_points + threshold.optional_pool_points != total:
            raise ValueError("fixed and optional points must equal scored evidence weights")
        if threshold.threshold > total:
            raise ValueError("score threshold cannot exceed total evidence weight")
        combinations = threshold.minimal_qualifying_combinations
        if combinations is UNDECIDED:
            return
        rule_ids = {item.rule_id for item in self.scored_evidence}
        for combination in combinations:
            if len(set(combination)) != len(combination) or not set(combination) <= rule_ids:
                raise ValueError("minimal qualifying combination contains duplicate or unknown rule")

    def _validate_signatures(self) -> None:
        signatures = self.allowed_evidence_signatures
        if signatures is UNDECIDED:
            return
        if not isinstance(signatures, tuple):
            raise TypeError("allowed_evidence_signatures must be tuple or UNDECIDED")
        known_rules = {item.rule_id for item in self.scored_evidence}
        for signature in signatures:
            _require_non_empty(signature, "evidence signature")
            rule_ids = signature.split("+")
            if rule_ids != sorted(rule_ids) or len(rule_ids) != len(set(rule_ids)):
                raise ValueError("evidence signature rule_ids must be unique and sorted")
            if not set(rule_ids) <= known_rules:
                raise ValueError("evidence signature contains an unknown rule_id")

    @property
    def entry_decision_digest(self) -> str:
        return _digest(
            {
                "schema_version": self.schema_version,
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "required_data": self.required_data,
                "hard_predicates": self.hard_predicates,
                "scored_evidence": self.scored_evidence,
                "score_threshold": self.score_threshold,
                "allowed_evidence_signatures": self.allowed_evidence_signatures,
                "stage_gate": self.stage_gate,
                "selection_function": self.selection_function,
                "candidate_set_evidence": self.candidate_set_evidence,
            }
        )

    def undecided_fields(self) -> tuple[str, ...]:
        """Return stable dotted paths for every explicitly undecided field."""
        paths: list[str] = []
        for name in (
            "required_data",
            "hard_predicates",
            "scored_evidence",
            "score_threshold",
            "allowed_evidence_signatures",
            "stage_gate",
            "selection_function",
            "candidate_set_evidence",
            "ablation_cohort_plan",
            "execution_admission_binding",
            "qualification_evidence_profile",
        ):
            paths.extend(_undecided_paths(getattr(self, name), name))
        return tuple(paths)

    def is_structurally_defined(self) -> bool:
        """Check definition structure only; this confers no readiness or qualification."""
        structural_values = (
            self.required_data,
            self.hard_predicates,
            self.scored_evidence,
            self.score_threshold,
            self.allowed_evidence_signatures,
            self.stage_gate,
            self.selection_function,
            self.candidate_set_evidence,
            self.execution_admission_binding,
        )
        return not any(_undecided_paths(value, "") for value in structural_values)

    def is_research_ready(self) -> bool:
        return False

    def is_ablation_ready(self) -> bool:
        return False

    def to_wire(self) -> dict[str, object]:
        wire = cast(dict[str, object], _to_wire(self))
        return {**wire, "entry_decision_digest": self.entry_decision_digest}
