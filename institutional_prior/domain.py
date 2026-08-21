"""Immutable research contracts for the institutional Candidate Prior gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from institutional_research.domain import (
    ArtifactIdentity,
    CrossSectionalPoint,
    DefinitionIdentity,
    FactorMetric,
    InstitutionalComponent,
    ResearchLabel,
)
from watchlist.reference_data import EquityMarket


class CandidatePriorInputError(ValueError):
    """A pinned input cannot safely produce a Candidate Prior artifact."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class CandidatePriorHypothesis(StrEnum):
    MOMENTUM_CONFIRMATION = "candidate.institutional_momentum_confirmation_v0"
    FOREIGN_TRUST_CONSENSUS = "candidate.institutional_foreign_trust_consensus_5d_v0"


class ComponentMatchPolicy(StrEnum):
    ANY = "ANY"
    ALL = "ALL"


class EvaluationCohort(StrEnum):
    ELIGIBLE_UNIVERSE = "ELIGIBLE_UNIVERSE"
    PRICE_ONLY = "PRICE_ONLY"
    INSTITUTIONAL_ONLY = "INSTITUTIONAL_ONLY"
    COMBINED = "COMBINED"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validate_component_pair(
    value: Decimal | None,
    percentile: Decimal | None,
    field_prefix: str,
) -> None:
    if (value is None) != (percentile is None):
        raise ValueError(f"{field_prefix} value and percentile must both be present")
    if percentile is not None and not Decimal(0) <= percentile <= Decimal(1):
        raise ValueError(f"{field_prefix}_percentile must be between zero and one")


@dataclass(frozen=True)
class CandidatePriorDefinition:
    hypothesis: CandidatePriorHypothesis
    requires_price_prior: bool
    component_match_policy: ComponentMatchPolicy
    version: str = "v0"
    primary_factor_metric: FactorMetric = FactorMetric.ROLLING_NET_SHARES_5D
    primary_lookback_sessions: int = 5
    primary_forward_horizon_sessions: int = 5
    secondary_forward_horizons: tuple[int, ...] = (1, 3)
    components: tuple[InstitutionalComponent, ...] = (
        InstitutionalComponent.FOREIGN_EX_DEALER,
        InstitutionalComponent.INVESTMENT_TRUST,
    )
    minimum_percentile: Decimal = Decimal("0.5")
    require_positive_raw_flow: bool = True
    label: ResearchLabel = ResearchLabel.EXPLORATORY

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hypothesis",
            CandidatePriorHypothesis(self.hypothesis),
        )
        object.__setattr__(
            self,
            "component_match_policy",
            ComponentMatchPolicy(self.component_match_policy),
        )
        if self.version != "v0":
            raise ValueError("Candidate Prior definition version is fixed at v0")
        if self.primary_factor_metric is not FactorMetric.ROLLING_NET_SHARES_5D:
            raise ValueError("primary factor metric is fixed at 5D rolling net shares")
        if self.primary_lookback_sessions != 5:
            raise ValueError("primary factor lookback is fixed at 5 sessions")
        if self.primary_forward_horizon_sessions != 5:
            raise ValueError("primary forward horizon is fixed at 5 sessions")
        if self.secondary_forward_horizons != (1, 3):
            raise ValueError("secondary exploratory horizons are fixed at 1/3")
        if self.components != tuple(InstitutionalComponent):
            raise ValueError("Candidate Prior components are fixed")
        if self.minimum_percentile != Decimal("0.5"):
            raise ValueError("v0 minimum percentile is fixed at 0.50")
        if not self.require_positive_raw_flow:
            raise ValueError("v0 requires strictly positive raw flow")
        if self.label is not ResearchLabel.EXPLORATORY:
            raise ValueError("Candidate Prior definition must remain EXPLORATORY")

        expected = {
            CandidatePriorHypothesis.MOMENTUM_CONFIRMATION: (
                True,
                ComponentMatchPolicy.ANY,
            ),
            CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS: (
                False,
                ComponentMatchPolicy.ALL,
            ),
        }[self.hypothesis]
        if (self.requires_price_prior, self.component_match_policy) != expected:
            raise ValueError("hypothesis input and match policy are fixed")

    @property
    def definition_id(self) -> str:
        return self.hypothesis.value


def candidate_prior_definitions() -> tuple[CandidatePriorDefinition, ...]:
    return (
        CandidatePriorDefinition(
            hypothesis=CandidatePriorHypothesis.MOMENTUM_CONFIRMATION,
            requires_price_prior=True,
            component_match_policy=ComponentMatchPolicy.ANY,
        ),
        CandidatePriorDefinition(
            hypothesis=CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS,
            requires_price_prior=False,
            component_match_policy=ComponentMatchPolicy.ALL,
        ),
    )


@dataclass(frozen=True)
class PriceMomentumCandidate:
    market: EquityMarket
    symbol: str
    rank: int
    source_entry_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise TypeError("rank must be an integer")
        if self.rank <= 0:
            raise ValueError("rank must be positive")
        _require_sha256(self.source_entry_digest, "source_entry_digest")


@dataclass(frozen=True)
class PriceMomentumPrior:
    definition: DefinitionIdentity
    calendar: ArtifactIdentity
    target_session: date
    as_of_session: date
    generated_at: datetime
    entries: tuple[PriceMomentumCandidate, ...]

    def __post_init__(self) -> None:
        if self.target_session <= self.as_of_session:
            raise ValueError("target_session must be after as_of_session")
        _require_aware(self.generated_at, "generated_at")
        if self.calendar.digest is None:
            raise ValueError("calendar digest is required")
        ordered = tuple(
            sorted(
                self.entries,
                key=lambda entry: (entry.rank, entry.market.value, entry.symbol),
            )
        )
        identities = [(entry.market, entry.symbol) for entry in ordered]
        if len(identities) != len(set(identities)):
            raise ValueError("price-momentum entries must have unique identities")
        object.__setattr__(self, "entries", ordered)


@dataclass(frozen=True)
class PriceMomentumPriorArtifact:
    artifact_id: str
    prior: PriceMomentumPrior
    prior_json: str
    prior_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _non_empty(self.artifact_id, "artifact_id"),
        )
        _require_sha256(self.prior_digest, "prior_digest")


@dataclass(frozen=True)
class InstitutionalFactorPrior:
    institutional_dataset: ArtifactIdentity
    universe: ArtifactIdentity
    factor_definition: DefinitionIdentity
    target_session: date
    primary_factor_metric: FactorMetric
    label: ResearchLabel
    strategy_ready: bool
    production_ready: bool
    cross_sectional_points: tuple[CrossSectionalPoint, ...]

    def __post_init__(self) -> None:
        if self.institutional_dataset.digest is None:
            raise ValueError("institutional dataset digest is required")
        if self.universe.digest is None:
            raise ValueError("universe digest is required")
        if self.primary_factor_metric is not FactorMetric.ROLLING_NET_SHARES_5D:
            raise ValueError("factor prior metric is fixed at 5D rolling net shares")
        if self.label is not ResearchLabel.EXPLORATORY:
            raise ValueError("factor prior must remain EXPLORATORY")
        if self.strategy_ready or self.production_ready:
            raise ValueError("factor prior cannot claim strategy/production readiness")
        if not self.cross_sectional_points:
            raise ValueError("factor prior requires target-session 5D points")
        ordered = tuple(
            sorted(
                self.cross_sectional_points,
                key=lambda point: (
                    point.market.value,
                    point.component.value,
                    point.symbol,
                ),
            )
        )
        identities = []
        for point in ordered:
            if point.session_date != self.target_session:
                raise ValueError("factor prior cannot contain another session")
            if point.metric is not self.primary_factor_metric:
                raise ValueError("factor prior cannot contain another metric")
            identities.append((point.market, point.symbol, point.component))
        if len(identities) != len(set(identities)):
            raise ValueError(
                "factor prior points must have unique component identities"
            )
        object.__setattr__(self, "cross_sectional_points", ordered)


@dataclass(frozen=True)
class InstitutionalFactorPriorArtifact:
    prior: InstitutionalFactorPrior
    prior_json: str
    prior_digest: str

    def __post_init__(self) -> None:
        _require_sha256(self.prior_digest, "prior_digest")

    @property
    def artifact_id(self) -> str:
        return f"institutional-factor-prior-{self.prior_digest[:16]}"


@dataclass(frozen=True)
class CandidatePriorRunManifestV0:
    factor_prior: ArtifactIdentity
    price_momentum_prior: ArtifactIdentity
    universe: ArtifactIdentity
    calendar: ArtifactIdentity
    hypothesis_definitions: tuple[DefinitionIdentity, ...]
    target_session: date
    as_of_session: date
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.target_session <= self.as_of_session:
            raise ValueError("target_session must be after as_of_session")
        _require_aware(self.generated_at, "generated_at")
        for field_name in (
            "factor_prior",
            "price_momentum_prior",
            "universe",
            "calendar",
        ):
            if getattr(self, field_name).digest is None:
                raise ValueError(f"{field_name} digest is required")
        definition_ids = tuple(
            identity.definition_id for identity in self.hypothesis_definitions
        )
        if len(definition_ids) != len(set(definition_ids)):
            raise ValueError("hypothesis definition identities must be unique")


@dataclass(frozen=True)
class CandidatePriorEntryPayload:
    target_session: date
    as_of_session: date
    market: EquityMarket
    symbol: str
    cohorts: tuple[EvaluationCohort, ...]
    matched_hypotheses: tuple[CandidatePriorHypothesis, ...]
    candidate_rank: int | None
    price_rank: int | None
    foreign_5d_value: Decimal | None
    foreign_5d_percentile: Decimal | None
    trust_5d_value: Decimal | None
    trust_5d_percentile: Decimal | None
    selection_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        if self.target_session <= self.as_of_session:
            raise ValueError("target_session must be after as_of_session")
        if len(self.cohorts) != len(set(self.cohorts)):
            raise ValueError("cohorts must be unique")
        if EvaluationCohort.ELIGIBLE_UNIVERSE not in self.cohorts:
            raise ValueError("every entry must belong to ELIGIBLE_UNIVERSE")
        if len(self.matched_hypotheses) != len(set(self.matched_hypotheses)):
            raise ValueError("matched_hypotheses must be unique")
        if (self.candidate_rank is None) != (not self.matched_hypotheses):
            raise ValueError("candidate_rank is present only for matched hypotheses")
        for value, field_name in (
            (self.candidate_rank, "candidate_rank"),
            (self.price_rank, "price_rank"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{field_name} must be a positive integer")
        has_price = EvaluationCohort.PRICE_ONLY in self.cohorts
        has_flow = EvaluationCohort.INSTITUTIONAL_ONLY in self.cohorts
        has_combined = EvaluationCohort.COMBINED in self.cohorts
        if has_price != (self.price_rank is not None):
            raise ValueError("PRICE_ONLY cohort and price_rank must agree")
        if has_combined != (has_price and has_flow):
            raise ValueError("COMBINED cohort requires both price and institutional")
        if (
            CandidatePriorHypothesis.MOMENTUM_CONFIRMATION in self.matched_hypotheses
            and not has_combined
        ):
            raise ValueError("momentum confirmation requires COMBINED cohort")
        _validate_component_pair(
            self.foreign_5d_value,
            self.foreign_5d_percentile,
            "foreign_5d",
        )
        _validate_component_pair(
            self.trust_5d_value,
            self.trust_5d_percentile,
            "trust_5d",
        )
        foreign_qualifies = (
            self.foreign_5d_value is not None
            and self.foreign_5d_value > 0
            and self.foreign_5d_percentile is not None
            and self.foreign_5d_percentile >= Decimal("0.5")
        )
        trust_qualifies = (
            self.trust_5d_value is not None
            and self.trust_5d_value > 0
            and self.trust_5d_percentile is not None
            and self.trust_5d_percentile >= Decimal("0.5")
        )
        if has_flow != (foreign_qualifies or trust_qualifies):
            raise ValueError("INSTITUTIONAL_ONLY cohort must follow the frozen v0 rule")
        has_momentum_confirmation = (
            CandidatePriorHypothesis.MOMENTUM_CONFIRMATION in self.matched_hypotheses
        )
        if has_momentum_confirmation != has_combined:
            raise ValueError("momentum confirmation must follow the frozen v0 rule")
        has_consensus = (
            CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS in self.matched_hypotheses
        )
        if has_consensus != (foreign_qualifies and trust_qualifies):
            raise ValueError("foreign/trust consensus must follow the frozen v0 rule")
        if not self.selection_reason_codes:
            raise ValueError("selection_reason_codes must not be empty")
        if len(self.selection_reason_codes) != len(set(self.selection_reason_codes)):
            raise ValueError("selection_reason_codes must be unique")


@dataclass(frozen=True)
class CandidatePriorEntry:
    payload: CandidatePriorEntryPayload
    entry_digest: str

    def __post_init__(self) -> None:
        _require_sha256(self.entry_digest, "entry_digest")


@dataclass(frozen=True)
class CandidatePriorArtifactManifestV0:
    run: CandidatePriorRunManifestV0
    research_status: ResearchLabel
    strategy_ready: bool
    production_ready: bool
    live_admission_ready: bool
    execution_allowed: bool
    issue_codes: tuple[str, ...]
    entry_count: int
    projected_candidate_count: int
    entries_digest: str

    def __post_init__(self) -> None:
        if self.research_status is not ResearchLabel.EXPLORATORY:
            raise ValueError("Candidate Prior artifact must remain EXPLORATORY")
        if (
            self.strategy_ready
            or self.production_ready
            or self.live_admission_ready
            or self.execution_allowed
        ):
            raise ValueError("Candidate Prior artifact cannot be execution-ready")
        for value, field_name in (
            (self.entry_count, "entry_count"),
            (self.projected_candidate_count, "projected_candidate_count"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.projected_candidate_count > self.entry_count:
            raise ValueError("projected candidates cannot exceed artifact entries")
        _require_sha256(self.entries_digest, "entries_digest")
        if not self.issue_codes:
            raise ValueError("issue_codes must not be empty")


@dataclass(frozen=True)
class CandidatePriorProjection:
    artifact_id: str
    artifact_digest: str
    entry_digest: str
    target_session: date
    as_of_session: date
    market: EquityMarket
    symbol: str
    candidate_rank: int
    matched_hypotheses: tuple[CandidatePriorHypothesis, ...]
    research_status: ResearchLabel
    strategy_ready: bool
    production_ready: bool
    live_admission_ready: bool
    execution_allowed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        _require_sha256(self.artifact_digest, "artifact_digest")
        _require_sha256(self.entry_digest, "entry_digest")
        if self.candidate_rank <= 0:
            raise ValueError("candidate_rank must be positive")
        if not self.matched_hypotheses:
            raise ValueError("projection requires a matched hypothesis")
        if self.research_status is not ResearchLabel.EXPLORATORY:
            raise ValueError("projection must remain EXPLORATORY")
        if (
            self.strategy_ready
            or self.production_ready
            or self.live_admission_ready
            or self.execution_allowed
        ):
            raise ValueError("projection cannot be execution-ready")


@dataclass(frozen=True)
class CandidatePriorArtifact:
    manifest: CandidatePriorArtifactManifestV0
    entries: tuple[CandidatePriorEntry, ...]
    projections: tuple[CandidatePriorProjection, ...]
    artifact_json: str
    artifact_digest: str

    def __post_init__(self) -> None:
        _require_sha256(self.artifact_digest, "artifact_digest")

    @property
    def artifact_id(self) -> str:
        return f"institutional-candidate-prior-{self.artifact_digest[:16]}"
