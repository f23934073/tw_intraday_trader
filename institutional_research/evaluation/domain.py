"""Immutable contracts for PR-008 formal candidate-prior evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.domain import ArtifactIdentity, DefinitionIdentity
from watchlist.reference_data import EquityMarket


class EvaluationArm(StrEnum):
    ELIGIBLE_UNIVERSE = "ELIGIBLE_UNIVERSE"
    PRICE_ONLY = "PRICE_ONLY"
    INSTITUTIONAL_ONLY = "INSTITUTIONAL_ONLY"
    COMBINED = "COMBINED"
    MATCHED_CONTROL = "MATCHED_CONTROL"


class EvaluationSplit(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"


class FormalGateVerdict(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAIL = "FAIL"
    PASS = "PASS"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_digest(identity: ArtifactIdentity, field_name: str) -> None:
    if identity.digest is None:
        raise ValueError(f"{field_name} digest is required")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class SessionRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("session range end must not precede start")

    def contains(self, session: date) -> bool:
        return self.start <= session <= self.end


@dataclass(frozen=True)
class CompositeResearchInputManifestV1:
    formal_evaluation_protocol: ArtifactIdentity
    coverage_amendment: ArtifactIdentity
    coverage_audit: ArtifactIdentity
    frozen_population: ArtifactIdentity
    price_dataset: ArtifactIdentity
    institutional_partition_set: ArtifactIdentity
    pit_universe: ArtifactIdentity
    pit_classification_size: ArtifactIdentity
    calendar: ArtifactIdentity
    corporate_actions: ArtifactIdentity
    reference_data: ArtifactIdentity
    candidate_prior_population: ArtifactIdentity
    matched_control_population: ArtifactIdentity
    evaluation_observations: ArtifactIdentity
    coverage_matrix: ArtifactIdentity
    setup_definition: DefinitionIdentity
    outcome_definition: DefinitionIdentity
    cost_model: DefinitionIdentity
    evaluation_plan: DefinitionIdentity
    code: ArtifactIdentity
    train: SessionRange
    validation: SessionRange
    holdout: SessionRange
    cost_model_effective_sessions: SessionRange
    research_eligible: bool
    issue_codes: tuple[str, ...] = ()
    version: str = "v1"

    def __post_init__(self) -> None:
        if self.version != "v1":
            raise ValueError("CompositeResearchInputManifest version is fixed at v1")
        for field_name in (
            "formal_evaluation_protocol",
            "coverage_amendment",
            "coverage_audit",
            "frozen_population",
            "price_dataset",
            "institutional_partition_set",
            "pit_universe",
            "pit_classification_size",
            "calendar",
            "corporate_actions",
            "reference_data",
            "candidate_prior_population",
            "matched_control_population",
            "evaluation_observations",
            "coverage_matrix",
            "code",
        ):
            _require_digest(getattr(self, field_name), field_name)
        if not self.train.end < self.validation.start:
            raise ValueError("train must end before validation starts")
        if not self.validation.end < self.holdout.start:
            raise ValueError("validation must end before holdout starts")
        if not self.cost_model_effective_sessions.contains(self.train.start):
            raise ValueError("cost model must cover the train start")
        if not self.cost_model_effective_sessions.contains(self.holdout.end):
            raise ValueError("cost model must cover the holdout end")
        normalized_issues = tuple(
            sorted({_non_empty(code, "issue_code") for code in self.issue_codes})
        )
        object.__setattr__(self, "issue_codes", normalized_issues)
        if self.research_eligible and normalized_issues:
            raise ValueError("research-eligible manifest cannot contain issue codes")

    def sessions_for(self, split: EvaluationSplit) -> SessionRange:
        return {
            EvaluationSplit.TRAIN: self.train,
            EvaluationSplit.VALIDATION: self.validation,
            EvaluationSplit.HOLDOUT: self.holdout,
        }[EvaluationSplit(split)]


@dataclass(frozen=True)
class EvaluationThresholdsV0:
    confidence_level: Decimal
    minimum_sessions: int
    minimum_executions_per_arm: int
    minimum_guardrail_executions_per_arm: int
    maximum_turnover_rate_increase: Decimal
    maximum_guardrail_net_expectancy_deterioration: Decimal
    required_markets: tuple[EquityMarket, ...]
    required_liquidity_cohorts: tuple[str, ...]
    primary_metric: str = "combined_minus_price_only_net_expectancy"
    version: str = "v0"

    def __post_init__(self) -> None:
        if self.version != "v0":
            raise ValueError("evaluation thresholds version is fixed at v0")
        if self.primary_metric != "combined_minus_price_only_net_expectancy":
            raise ValueError("primary metric is fixed for PR-008")
        if self.confidence_level not in {
            Decimal("0.90"),
            Decimal("0.95"),
            Decimal("0.99"),
        }:
            raise ValueError("confidence_level must be 0.90, 0.95, or 0.99")
        for value, field_name in (
            (self.minimum_sessions, "minimum_sessions"),
            (self.minimum_executions_per_arm, "minimum_executions_per_arm"),
            (
                self.minimum_guardrail_executions_per_arm,
                "minimum_guardrail_executions_per_arm",
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.maximum_turnover_rate_increase < 0:
            raise ValueError("maximum_turnover_rate_increase must be non-negative")
        if self.maximum_guardrail_net_expectancy_deterioration < 0:
            raise ValueError("guardrail deterioration allowance must be non-negative")
        markets = tuple(EquityMarket(market) for market in self.required_markets)
        if set(markets) != set(EquityMarket) or len(markets) != len(set(markets)):
            raise ValueError("required_markets must contain TWSE and TPEX exactly once")
        liquidity = tuple(
            _non_empty(value, "required_liquidity_cohort")
            for value in self.required_liquidity_cohorts
        )
        if not liquidity or len(liquidity) != len(set(liquidity)):
            raise ValueError("required_liquidity_cohorts must be non-empty and unique")
        object.__setattr__(
            self,
            "required_markets",
            tuple(sorted(markets, key=lambda market: market.value)),
        )
        object.__setattr__(self, "required_liquidity_cohorts", tuple(sorted(liquidity)))

    @property
    def digest(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "confidence_level": self.confidence_level,
                    "maximum_guardrail_net_expectancy_deterioration": (
                        self.maximum_guardrail_net_expectancy_deterioration
                    ),
                    "maximum_turnover_rate_increase": self.maximum_turnover_rate_increase,
                    "minimum_executions_per_arm": self.minimum_executions_per_arm,
                    "minimum_guardrail_executions_per_arm": (
                        self.minimum_guardrail_executions_per_arm
                    ),
                    "minimum_sessions": self.minimum_sessions,
                    "primary_metric": self.primary_metric,
                    "required_liquidity_cohorts": self.required_liquidity_cohorts,
                    "required_markets": self.required_markets,
                    "version": self.version,
                }
            )
        )


@dataclass(frozen=True)
class PreregisteredEvaluationGateV0:
    registration_artifact: ArtifactIdentity
    registered_at: datetime
    registered_thresholds_digest: str
    thresholds: EvaluationThresholdsV0

    def __post_init__(self) -> None:
        _require_digest(self.registration_artifact, "registration_artifact")
        _require_aware(self.registered_at, "registered_at")
        if self.registered_thresholds_digest != self.thresholds.digest:
            raise ValueError("registered thresholds digest does not match thresholds")


@dataclass(frozen=True)
class EvaluationObservation:
    session_date: date
    market: EquityMarket
    symbol: str
    liquidity_cohort: str
    cohorts: tuple[EvaluationArm, ...]
    setup_qualified: bool
    first_valid_setup_at: datetime | None
    executed: bool
    gross_return: Decimal | None
    cost_return: Decimal | None
    net_return: Decimal | None
    source_entry_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        object.__setattr__(
            self,
            "liquidity_cohort",
            _non_empty(self.liquidity_cohort, "liquidity_cohort"),
        )
        cohorts = tuple(EvaluationArm(value) for value in self.cohorts)
        if len(cohorts) != len(set(cohorts)):
            raise ValueError("evaluation cohorts must be unique")
        if EvaluationArm.ELIGIBLE_UNIVERSE not in cohorts:
            raise ValueError("every observation must include ELIGIBLE_UNIVERSE")
        has_price = EvaluationArm.PRICE_ONLY in cohorts
        has_institutional = EvaluationArm.INSTITUTIONAL_ONLY in cohorts
        if (EvaluationArm.COMBINED in cohorts) != (has_price and has_institutional):
            raise ValueError("COMBINED membership must equal price and institutional overlap")
        if EvaluationArm.MATCHED_CONTROL in cohorts and has_institutional:
            raise ValueError("matched controls cannot satisfy institutional selection")
        object.__setattr__(
            self,
            "cohorts",
            tuple(sorted(cohorts, key=lambda cohort: tuple(EvaluationArm).index(cohort))),
        )
        if self.first_valid_setup_at is not None:
            _require_aware(self.first_valid_setup_at, "first_valid_setup_at")
            if self.first_valid_setup_at.date() != self.session_date:
                raise ValueError("first setup timestamp must belong to the session")
        if self.setup_qualified != (self.first_valid_setup_at is not None):
            raise ValueError("setup qualification and first setup timestamp must agree")
        returns = (self.gross_return, self.cost_return, self.net_return)
        if self.executed != all(value is not None for value in returns):
            raise ValueError("executed observations require all return fields")
        if not self.executed and any(value is not None for value in returns):
            raise ValueError("non-executed observations cannot contain returns")
        if self.executed:
            if not self.setup_qualified:
                raise ValueError("execution requires a qualified setup")
            assert self.gross_return is not None
            assert self.cost_return is not None
            assert self.net_return is not None
            if self.cost_return < 0:
                raise ValueError("cost_return must be non-negative")
            if self.net_return != self.gross_return - self.cost_return:
                raise ValueError("net_return must equal gross_return minus cost_return")
        if len(self.source_entry_digest) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.source_entry_digest
        ):
            raise ValueError("source_entry_digest must be a lowercase SHA256 digest")


@dataclass(frozen=True)
class ArmSummary:
    arm: EvaluationArm
    candidate_count: int
    setup_count: int
    setup_precision: Decimal | None
    execution_count: int
    gross_expectancy: Decimal | None
    cost_expectancy: Decimal | None
    net_expectancy: Decimal | None
    turnover_rate: Decimal | None


@dataclass(frozen=True)
class ArmComparison:
    arm: EvaluationArm
    baseline: EvaluationArm
    net_expectancy_difference: Decimal | None
    confidence_lower: Decimal | None
    confidence_upper: Decimal | None
    confidence_level: Decimal
    clustered_session_count: int


@dataclass(frozen=True)
class EvaluationGateDecision:
    verdict: FormalGateVerdict
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FormalEvaluationReport:
    manifest: CompositeResearchInputManifestV1
    gate: PreregisteredEvaluationGateV0
    split: EvaluationSplit
    session_count: int
    observation_count: int
    summaries: tuple[ArmSummary, ...]
    primary_comparison: ArmComparison
    market_guardrails: tuple[tuple[EquityMarket, ArmComparison], ...]
    liquidity_guardrails: tuple[tuple[str, ArmComparison], ...]
    gate_decision: EvaluationGateDecision
    subscription_allowed: bool = False
    execution_allowed: bool = False
    version: str = "v0"

    def __post_init__(self) -> None:
        if self.version != "v0":
            raise ValueError("formal evaluation report version is fixed at v0")
        if self.subscription_allowed or self.execution_allowed:
            raise ValueError("evaluation reports cannot authorize runtime side effects")


@dataclass(frozen=True)
class FormalEvaluationArtifact:
    report: FormalEvaluationReport
    report_json: str
    report_digest: str

    def __post_init__(self) -> None:
        if len(self.report_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.report_digest
        ):
            raise ValueError("report_digest must be a lowercase SHA256 digest")
        if sha256_text(self.report_json) != self.report_digest:
            raise ValueError("report JSON differs from report_digest")

    @property
    def artifact_id(self) -> str:
        return f"institutional-formal-evaluation-{self.report_digest[:16]}"
