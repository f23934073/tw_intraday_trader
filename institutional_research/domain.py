"""Immutable research-only contracts for institutional factor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from watchlist.reference_data import EquityMarket, MarketCapCohort


class ResearchLabel(StrEnum):
    EXPLORATORY = "EXPLORATORY"


class InstitutionalComponent(StrEnum):
    FOREIGN_EX_DEALER = "FOREIGN_EX_DEALER"
    INVESTMENT_TRUST = "INVESTMENT_TRUST"


class FactorMetric(StrEnum):
    NET_SHARES_1D = "NET_SHARES_1D"
    ROLLING_NET_SHARES_5D = "ROLLING_NET_SHARES_5D"
    POSITIVE_DAYS_5D = "POSITIVE_DAYS_5D"
    CONSECUTIVE_POSITIVE_DAYS_5D = "CONSECUTIVE_POSITIVE_DAYS_5D"
    SELF_NORMALIZED_FLOW_5D = "SELF_NORMALIZED_FLOW_5D"


class ConfoundingStatus(StrEnum):
    UNADJUSTED_INDUSTRY_SIZE = "UNADJUSTED_INDUSTRY_SIZE"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_sha256(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_id: str
    digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _non_empty(self.artifact_id, "artifact_id"),
        )
        _optional_sha256(self.digest, "digest")


@dataclass(frozen=True)
class DefinitionIdentity:
    definition_id: str
    version: str
    definition_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "definition_id",
            _non_empty(self.definition_id, "definition_id"),
        )
        object.__setattr__(self, "version", _non_empty(self.version, "version"))
        _optional_sha256(self.definition_digest, "definition_digest")
        if self.definition_digest is None:  # pragma: no cover - static type guard
            raise ValueError("definition_digest must not be None")


@dataclass(frozen=True)
class BaselineFactorDefinition:
    definition_id: str = "institutional_baseline_factor_diagnostics"
    version: str = "v0"
    lookback_sessions: int = 5
    forward_horizons: tuple[int, ...] = (1, 3, 5)
    components: tuple[InstitutionalComponent, ...] = (
        InstitutionalComponent.FOREIGN_EX_DEALER,
        InstitutionalComponent.INVESTMENT_TRUST,
    )
    metrics: tuple[FactorMetric, ...] = tuple(FactorMetric)
    label: ResearchLabel = ResearchLabel.EXPLORATORY

    def __post_init__(self) -> None:
        if self.definition_id != "institutional_baseline_factor_diagnostics":
            raise ValueError("baseline definition_id is fixed")
        if self.version != "v0":
            raise ValueError("baseline definition version is fixed at v0")
        if self.lookback_sessions != 5:
            raise ValueError("baseline lookback_sessions is fixed at 5")
        if self.forward_horizons != (1, 3, 5):
            raise ValueError("baseline forward_horizons are fixed at 1/3/5")
        if self.components != tuple(InstitutionalComponent):
            raise ValueError("baseline components are fixed")
        if self.metrics != tuple(FactorMetric):
            raise ValueError("baseline metrics are fixed")
        if self.label is not ResearchLabel.EXPLORATORY:
            raise ValueError("baseline definition must remain EXPLORATORY")


@dataclass(frozen=True)
class ResearchRunManifestV0:
    price_dataset: ArtifactIdentity
    institutional_dataset: ArtifactIdentity
    universe: ArtifactIdentity | None
    factor_definition: DefinitionIdentity
    factor_start_session: date
    factor_end_session: date

    def __post_init__(self) -> None:
        if self.factor_end_session < self.factor_start_session:
            raise ValueError("factor_end_session cannot precede factor_start_session")


@dataclass(frozen=True)
class FactorPoint:
    session_date: date
    market: EquityMarket
    symbol: str
    component: InstitutionalComponent
    metric: FactorMetric
    value: Decimal | None
    observed_sessions: int
    expected_sessions: int


@dataclass(frozen=True)
class DistributionSummary:
    session_date: date
    market: EquityMarket
    component: InstitutionalComponent
    metric: FactorMetric
    expected_count: int | None
    observed_count: int
    non_null_count: int
    null_count: int
    coverage_ratio: Decimal | None
    null_rate: Decimal | None
    minimum: Decimal | None
    percentile_25: Decimal | None
    median: Decimal | None
    percentile_75: Decimal | None
    maximum: Decimal | None


@dataclass(frozen=True)
class CrossSectionalPoint:
    session_date: date
    market: EquityMarket
    symbol: str
    component: InstitutionalComponent
    metric: FactorMetric
    value: Decimal
    percentile: Decimal
    decile: int
    industry_code: str
    market_cap_cohort: MarketCapCohort


@dataclass(frozen=True)
class ForwardOutcome:
    session_date: date
    market: EquityMarket
    symbol: str
    component: InstitutionalComponent
    metric: FactorMetric
    decile: int
    horizon_sessions: int
    adjusted_return: Decimal | None


@dataclass(frozen=True)
class RankIcObservation:
    session_date: date
    market: EquityMarket
    component: InstitutionalComponent
    metric: FactorMetric
    horizon_sessions: int
    sample_size: int
    rank_ic: Decimal | None


@dataclass(frozen=True)
class IcSummary:
    market: EquityMarket
    component: InstitutionalComponent
    metric: FactorMetric
    horizon_sessions: int
    observation_count: int
    mean_rank_ic: Decimal | None
    icir: Decimal | None


@dataclass(frozen=True)
class DecileOutcomeSummary:
    market: EquityMarket
    component: InstitutionalComponent
    metric: FactorMetric
    horizon_sessions: int
    decile: int
    observation_count: int
    mean_adjusted_return: Decimal | None


@dataclass(frozen=True)
class InstitutionalFactorReport:
    manifest: ResearchRunManifestV0
    label: ResearchLabel
    strategy_ready: bool
    production_ready: bool
    pit_eligible: bool
    scope_eligible: bool
    cross_sectional_eligible: bool
    research_eligible: bool
    confounding_status: ConfoundingStatus
    issue_codes: tuple[str, ...]
    factor_points: tuple[FactorPoint, ...]
    distributions: tuple[DistributionSummary, ...]
    cross_sectional_points: tuple[CrossSectionalPoint, ...]
    forward_outcomes: tuple[ForwardOutcome, ...]
    rank_ic_observations: tuple[RankIcObservation, ...]
    ic_summaries: tuple[IcSummary, ...]
    decile_outcomes: tuple[DecileOutcomeSummary, ...]

    def __post_init__(self) -> None:
        if self.label is not ResearchLabel.EXPLORATORY:
            raise ValueError("factor report must remain EXPLORATORY")
        if self.strategy_ready:
            raise ValueError("factor report cannot be strategy-ready")
        if self.production_ready:
            raise ValueError("factor report cannot be production-ready")


@dataclass(frozen=True)
class InstitutionalFactorReportArtifact:
    report: InstitutionalFactorReport
    report_json: str
    report_digest: str

    @property
    def artifact_id(self) -> str:
        return f"institutional-factor-report-{self.report_digest[:16]}"
