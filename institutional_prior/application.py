"""Build the two approved Candidate Prior hypotheses without runtime admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from institutional_data.serialization import sha256_text
from institutional_research.domain import (
    ArtifactIdentity,
    BaselineFactorDefinition,
    CrossSectionalPoint,
    FactorMetric,
    InstitutionalComponent,
    InstitutionalFactorReportArtifact,
    ResearchLabel,
)
from institutional_research.serialization import (
    factor_definition_sha256,
    serialize_factor_report,
)
from watchlist.reference_data import EquityMarket, EquityUniversePort

from .domain import (
    CandidatePriorArtifact,
    CandidatePriorArtifactManifestV0,
    CandidatePriorEntry,
    CandidatePriorEntryPayload,
    CandidatePriorHypothesis,
    CandidatePriorInputError,
    CandidatePriorRunManifestV0,
    EvaluationCohort,
    InstitutionalFactorPrior,
    InstitutionalFactorPriorArtifact,
    PriceMomentumPriorArtifact,
    candidate_prior_definitions,
)
from .serialization import (
    build_candidate_prior_artifact,
    build_candidate_prior_entry,
    build_institutional_factor_prior_artifact,
    candidate_prior_definition_identity,
    candidate_prior_entries_sha256,
    serialize_institutional_factor_prior,
    serialize_price_momentum_prior,
)

EXPLORATORY_ONLY = "EXPLORATORY_ONLY"
FORMAL_EVALUATION_REQUIRED = "FORMAL_EVALUATION_REQUIRED"
LIVE_ADMISSION_NOT_AUTHORIZED = "LIVE_ADMISSION_NOT_AUTHORIZED"
PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE = "PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE"


@dataclass(frozen=True)
class _EntryFacts:
    market: EquityMarket
    symbol: str
    cohorts: tuple[EvaluationCohort, ...]
    matched_hypotheses: tuple[CandidatePriorHypothesis, ...]
    price_rank: int | None
    foreign_point: CrossSectionalPoint | None
    trust_point: CrossSectionalPoint | None
    selection_reason_codes: tuple[str, ...]

    @property
    def rank_key(self) -> tuple[object, ...]:
        percentiles = tuple(
            point.percentile
            for point in (self.foreign_point, self.trust_point)
            if point is not None
        )
        return (
            -len(self.matched_hypotheses),
            -min(percentiles),
            -max(percentiles),
            self.price_rank is None,
            self.price_rank or 0,
            self.market.value,
            self.symbol,
        )


def _same_identity(
    expected: ArtifactIdentity,
    *,
    artifact_id: str,
    digest: str,
) -> bool:
    return expected.artifact_id == artifact_id and expected.digest == digest


def project_institutional_factor_prior(
    *,
    factor_report: InstitutionalFactorReportArtifact,
    target_session: date,
) -> InstitutionalFactorPriorArtifact:
    """Project PIT-safe factor bytes without carrying future outcomes/IC."""

    artifact = factor_report
    canonical_json = serialize_factor_report(artifact.report)
    if artifact.report_json != canonical_json or artifact.report_digest != sha256_text(
        canonical_json
    ):
        raise CandidatePriorInputError(
            "FACTOR_REPORT_DIGEST_MISMATCH",
            "factor report JSON or digest is not canonical",
        )

    report = artifact.report
    if report.label is not ResearchLabel.EXPLORATORY:
        raise CandidatePriorInputError(
            "FACTOR_REPORT_NOT_EXPLORATORY",
            "PR-005 accepts only EXPLORATORY factor evidence",
        )
    if report.strategy_ready or report.production_ready or report.research_eligible:
        raise CandidatePriorInputError(
            "FACTOR_REPORT_READINESS_INVALID",
            "factor evidence cannot claim research, strategy, or production readiness",
        )
    if not (
        report.pit_eligible
        and report.scope_eligible
        and report.cross_sectional_eligible
    ):
        raise CandidatePriorInputError(
            "FACTOR_REPORT_NOT_CROSS_SECTIONAL_ELIGIBLE",
            "PIT, scope, and cross-sectional gates must all pass",
        )
    if not (
        report.manifest.factor_start_session
        <= target_session
        <= report.manifest.factor_end_session
    ):
        raise CandidatePriorInputError(
            "TARGET_SESSION_OUTSIDE_FACTOR_REPORT",
            "target session is outside the pinned factor report range",
        )
    if report.manifest.universe is None or report.manifest.universe.digest is None:
        raise CandidatePriorInputError(
            "FACTOR_REPORT_UNIVERSE_MISSING",
            "factor prior projection requires a pinned PIT universe",
        )

    baseline = BaselineFactorDefinition()
    expected_definition = (
        baseline.definition_id,
        baseline.version,
        factor_definition_sha256(baseline),
    )
    actual_definition = report.manifest.factor_definition
    if (
        actual_definition.definition_id,
        actual_definition.version,
        actual_definition.definition_digest,
    ) != expected_definition:
        raise CandidatePriorInputError(
            "PRIMARY_FACTOR_DEFINITION_MISMATCH",
            "PR-005 requires the frozen v0 5D primary factor definition",
        )
    points = tuple(
        point
        for point in report.cross_sectional_points
        if point.session_date == target_session
        and point.metric is FactorMetric.ROLLING_NET_SHARES_5D
    )
    try:
        prior = InstitutionalFactorPrior(
            institutional_dataset=report.manifest.institutional_dataset,
            universe=report.manifest.universe,
            factor_definition=report.manifest.factor_definition,
            target_session=target_session,
            primary_factor_metric=FactorMetric.ROLLING_NET_SHARES_5D,
            label=ResearchLabel.EXPLORATORY,
            strategy_ready=False,
            production_ready=False,
            cross_sectional_points=points,
        )
    except ValueError as error:
        raise CandidatePriorInputError(
            "FACTOR_PRIOR_PROJECTION_INVALID",
            str(error),
        ) from error
    return build_institutional_factor_prior_artifact(prior)


def _validate_factor_prior(
    manifest: CandidatePriorRunManifestV0,
    artifact: InstitutionalFactorPriorArtifact,
) -> None:
    if not _same_identity(
        manifest.factor_prior,
        artifact_id=artifact.artifact_id,
        digest=artifact.prior_digest,
    ):
        raise CandidatePriorInputError(
            "FACTOR_PRIOR_LINEAGE_MISMATCH",
            "factor prior differs from CandidatePriorRunManifestV0",
        )
    canonical_json = serialize_institutional_factor_prior(artifact.prior)
    if artifact.prior_json != canonical_json or artifact.prior_digest != sha256_text(
        canonical_json
    ):
        raise CandidatePriorInputError(
            "FACTOR_PRIOR_DIGEST_MISMATCH",
            "factor prior JSON or digest is not canonical",
        )
    prior = artifact.prior
    if prior.target_session != manifest.target_session:
        raise CandidatePriorInputError(
            "FACTOR_PRIOR_SESSION_MISMATCH",
            "factor prior does not match the Candidate Prior target session",
        )
    if prior.universe != manifest.universe:
        raise CandidatePriorInputError(
            "UNIVERSE_LINEAGE_MISMATCH",
            "factor prior and Candidate Prior pin different PIT universes",
        )
    if prior.label is not ResearchLabel.EXPLORATORY or (
        prior.strategy_ready or prior.production_ready
    ):
        raise CandidatePriorInputError(
            "FACTOR_PRIOR_READINESS_INVALID",
            "factor prior cannot claim strategy or production readiness",
        )
    baseline = BaselineFactorDefinition()
    expected_definition = (
        baseline.definition_id,
        baseline.version,
        factor_definition_sha256(baseline),
    )
    actual_definition = prior.factor_definition
    if (
        actual_definition.definition_id,
        actual_definition.version,
        actual_definition.definition_digest,
    ) != expected_definition:
        raise CandidatePriorInputError(
            "PRIMARY_FACTOR_DEFINITION_MISMATCH",
            "factor prior does not use the frozen v0 5D definition",
        )


def _validate_price_prior(
    manifest: CandidatePriorRunManifestV0,
    artifact: PriceMomentumPriorArtifact,
) -> None:
    if not _same_identity(
        manifest.price_momentum_prior,
        artifact_id=artifact.artifact_id,
        digest=artifact.prior_digest,
    ):
        raise CandidatePriorInputError(
            "PRICE_PRIOR_LINEAGE_MISMATCH",
            "price-momentum prior differs from CandidatePriorRunManifestV0",
        )
    canonical_json = serialize_price_momentum_prior(artifact.prior)
    if artifact.prior_json != canonical_json or artifact.prior_digest != sha256_text(
        canonical_json
    ):
        raise CandidatePriorInputError(
            "PRICE_PRIOR_DIGEST_MISMATCH",
            "price-momentum prior JSON or digest is not canonical",
        )
    prior = artifact.prior
    if (
        prior.target_session != manifest.target_session
        or prior.as_of_session != manifest.as_of_session
    ):
        raise CandidatePriorInputError(
            "PRICE_PRIOR_SESSION_MISMATCH",
            "price-momentum prior does not match target/as-of sessions",
        )
    if prior.calendar != manifest.calendar:
        raise CandidatePriorInputError(
            "CALENDAR_LINEAGE_MISMATCH",
            "price-momentum prior and Candidate Prior pin different calendars",
        )
    if prior.generated_at > manifest.generated_at:
        raise CandidatePriorInputError(
            "PRICE_PRIOR_GENERATED_AFTER_RUN",
            "price-momentum prior was generated after the Candidate Prior run",
        )


def _validate_definitions(manifest: CandidatePriorRunManifestV0) -> Decimal:
    definitions = candidate_prior_definitions()
    expected = tuple(candidate_prior_definition_identity(item) for item in definitions)
    if manifest.hypothesis_definitions != expected:
        raise CandidatePriorInputError(
            "CANDIDATE_DEFINITION_LINEAGE_MISMATCH",
            "Candidate Prior hypotheses differ from the two frozen v0 definitions",
        )
    return definitions[0].minimum_percentile


def _resolve_eligible_universe(
    manifest: CandidatePriorRunManifestV0,
    universe: EquityUniversePort,
) -> set[tuple[EquityMarket, str]]:
    try:
        resolution = universe.resolve(manifest.target_session)
    except Exception as error:
        raise CandidatePriorInputError(
            "PIT_UNIVERSE_RESOLUTION_FAILED",
            "pinned PIT universe could not be resolved for target session",
        ) from error
    if (
        resolution.snapshot_id != manifest.universe.artifact_id
        or resolution.content_digest != manifest.universe.digest
    ):
        raise CandidatePriorInputError(
            "UNIVERSE_LINEAGE_MISMATCH",
            "resolved PIT universe differs from CandidatePriorRunManifestV0",
        )
    if not resolution.research_eligible or not resolution.research_members:
        raise CandidatePriorInputError(
            "PIT_UNIVERSE_NOT_RESEARCH_ELIGIBLE",
            "resolved universe cannot provide a PIT eligible-equity denominator",
        )
    return {(member.market, member.symbol) for member in resolution.research_members}


def _target_factor_population(
    artifact: InstitutionalFactorPriorArtifact,
    eligible: set[tuple[EquityMarket, str]],
) -> dict[tuple[EquityMarket, str, InstitutionalComponent], CrossSectionalPoint]:
    target_points = artifact.prior.cross_sectional_points
    if not target_points:
        raise CandidatePriorInputError(
            "TARGET_FACTOR_POPULATION_MISSING",
            "factor prior has no PIT cross-sectional rows for target session",
        )
    primary: dict[
        tuple[EquityMarket, str, InstitutionalComponent],
        CrossSectionalPoint,
    ] = {}
    for point in target_points:
        if (point.market, point.symbol) not in eligible:
            raise CandidatePriorInputError(
                "FACTOR_POINT_OUTSIDE_PINNED_UNIVERSE",
                "factor report contains a symbol outside the resolved PIT universe",
            )
        if point.metric is not FactorMetric.ROLLING_NET_SHARES_5D:
            continue
        key = (point.market, point.symbol, point.component)
        if key in primary:
            raise CandidatePriorInputError(
                "DUPLICATE_PRIMARY_FACTOR_POINT",
                "factor report contains duplicate target 5D component points",
            )
        primary[key] = point
    return primary


def _qualifies(point: CrossSectionalPoint | None, threshold: Decimal) -> bool:
    return point is not None and point.value > 0 and point.percentile >= threshold


def _selection_reasons(
    *,
    price_member: bool,
    flow_member: bool,
    matched: tuple[CandidatePriorHypothesis, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if CandidatePriorHypothesis.MOMENTUM_CONFIRMATION in matched:
        reasons.append("MOMENTUM_CONFIRMED_BY_INSTITUTIONAL_5D")
    if CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS in matched:
        reasons.append("FOREIGN_TRUST_CONSENSUS_5D")
    if reasons:
        return tuple(reasons)
    if price_member and not flow_member:
        return ("PRICE_ONLY_CONTROL",)
    if flow_member and not price_member:
        return ("INSTITUTIONAL_ONLY_CONTROL",)
    return ("ELIGIBLE_UNIVERSE_CONTROL",)


def _build_facts(
    *,
    manifest: CandidatePriorRunManifestV0,
    factor_prior: InstitutionalFactorPriorArtifact,
    price_prior: PriceMomentumPriorArtifact,
    threshold: Decimal,
    eligible: set[tuple[EquityMarket, str]],
) -> tuple[tuple[_EntryFacts, ...], bool]:
    primary = _target_factor_population(factor_prior, eligible)
    price_by_key = {
        (entry.market, entry.symbol): entry for entry in price_prior.prior.entries
    }
    price_outside_universe = any(key not in eligible for key in price_by_key)
    facts: list[_EntryFacts] = []
    for market, symbol in sorted(eligible, key=lambda item: (item[0].value, item[1])):
        price_entry = price_by_key.get((market, symbol))
        foreign = primary.get(
            (market, symbol, InstitutionalComponent.FOREIGN_EX_DEALER)
        )
        trust = primary.get((market, symbol, InstitutionalComponent.INVESTMENT_TRUST))
        foreign_qualifies = _qualifies(foreign, threshold)
        trust_qualifies = _qualifies(trust, threshold)
        flow_member = foreign_qualifies or trust_qualifies
        price_member = price_entry is not None
        consensus = foreign_qualifies and trust_qualifies

        cohorts = [EvaluationCohort.ELIGIBLE_UNIVERSE]
        if price_member:
            cohorts.append(EvaluationCohort.PRICE_ONLY)
        if flow_member:
            cohorts.append(EvaluationCohort.INSTITUTIONAL_ONLY)
        if price_member and flow_member:
            cohorts.append(EvaluationCohort.COMBINED)

        matched: list[CandidatePriorHypothesis] = []
        if price_member and flow_member:
            matched.append(CandidatePriorHypothesis.MOMENTUM_CONFIRMATION)
        if consensus:
            matched.append(CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS)
        matched_tuple = tuple(matched)
        facts.append(
            _EntryFacts(
                market=market,
                symbol=symbol,
                cohorts=tuple(cohorts),
                matched_hypotheses=matched_tuple,
                price_rank=price_entry.rank if price_entry is not None else None,
                foreign_point=foreign,
                trust_point=trust,
                selection_reason_codes=_selection_reasons(
                    price_member=price_member,
                    flow_member=flow_member,
                    matched=matched_tuple,
                ),
            )
        )
    return tuple(facts), price_outside_universe


def _materialize_entries(
    manifest: CandidatePriorRunManifestV0,
    facts: tuple[_EntryFacts, ...],
) -> tuple[CandidatePriorEntry, ...]:
    matched = sorted(
        (fact for fact in facts if fact.matched_hypotheses),
        key=lambda fact: fact.rank_key,
    )
    ranks = {
        (fact.market, fact.symbol): rank for rank, fact in enumerate(matched, start=1)
    }
    ordered = matched + sorted(
        (fact for fact in facts if not fact.matched_hypotheses),
        key=lambda fact: (fact.market.value, fact.symbol),
    )
    return tuple(
        build_candidate_prior_entry(
            CandidatePriorEntryPayload(
                target_session=manifest.target_session,
                as_of_session=manifest.as_of_session,
                market=fact.market,
                symbol=fact.symbol,
                cohorts=fact.cohorts,
                matched_hypotheses=fact.matched_hypotheses,
                candidate_rank=ranks.get((fact.market, fact.symbol)),
                price_rank=fact.price_rank,
                foreign_5d_value=(
                    fact.foreign_point.value if fact.foreign_point else None
                ),
                foreign_5d_percentile=(
                    fact.foreign_point.percentile if fact.foreign_point else None
                ),
                trust_5d_value=fact.trust_point.value if fact.trust_point else None,
                trust_5d_percentile=(
                    fact.trust_point.percentile if fact.trust_point else None
                ),
                selection_reason_codes=fact.selection_reason_codes,
            )
        )
        for fact in ordered
    )


class InstitutionalCandidatePriorBuilder:
    """Build exploratory Candidate Prior evidence; never emit an entry rule."""

    def build(
        self,
        *,
        manifest: CandidatePriorRunManifestV0,
        factor_prior: InstitutionalFactorPriorArtifact,
        price_momentum_prior: PriceMomentumPriorArtifact,
        universe: EquityUniversePort,
    ) -> CandidatePriorArtifact:
        with localcontext() as context:
            context.prec = 36
            _validate_factor_prior(manifest, factor_prior)
            _validate_price_prior(manifest, price_momentum_prior)
            threshold = _validate_definitions(manifest)
            eligible = _resolve_eligible_universe(manifest, universe)
            facts, price_outside_universe = _build_facts(
                manifest=manifest,
                factor_prior=factor_prior,
                price_prior=price_momentum_prior,
                threshold=threshold,
                eligible=eligible,
            )
            entries = _materialize_entries(manifest, facts)
            issue_codes = [
                EXPLORATORY_ONLY,
                FORMAL_EVALUATION_REQUIRED,
                LIVE_ADMISSION_NOT_AUTHORIZED,
            ]
            if price_outside_universe:
                issue_codes.append(PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE)
            projected_count = sum(
                bool(entry.payload.matched_hypotheses) for entry in entries
            )
            artifact_manifest = CandidatePriorArtifactManifestV0(
                run=manifest,
                research_status=ResearchLabel.EXPLORATORY,
                strategy_ready=False,
                production_ready=False,
                live_admission_ready=False,
                execution_allowed=False,
                issue_codes=tuple(issue_codes),
                entry_count=len(entries),
                projected_candidate_count=projected_count,
                entries_digest=candidate_prior_entries_sha256(entries),
            )
            return build_candidate_prior_artifact(
                manifest=artifact_manifest,
                entries=entries,
            )
