"""Application boundary for reproducible institutional-factor diagnostics."""

from __future__ import annotations

from datetime import date
from decimal import localcontext

from watchlist.reference_data import (
    PIT_UNIVERSE_MISSING,
    DateEffectiveEquityRecord,
    EquityMarket,
    EquityUniversePort,
)

from .diagnostics import (
    build_cross_sectional_points,
    build_distributions,
    build_forward_outcomes,
    build_rank_ic_observations,
    summarize_decile_outcomes,
    summarize_rank_ic,
)
from .domain import (
    BaselineFactorDefinition,
    ConfoundingStatus,
    InstitutionalFactorReport,
    InstitutionalFactorReportArtifact,
    ResearchLabel,
    ResearchRunManifestV0,
)
from .factors import compute_baseline_factor_points
from .inputs import (
    InstitutionalResearchInput,
    PriceResearchInput,
    ResearchInputError,
)
from .serialization import build_report_artifact, factor_definition_sha256


SCOPE_INCOMPATIBLE = "SCOPE_INCOMPATIBLE"
FORMAL_RESEARCH_REQUIREMENTS_MISSING = "FORMAL_RESEARCH_REQUIREMENTS_MISSING"
UNADJUSTED_INDUSTRY_SIZE = "UNADJUSTED_INDUSTRY_SIZE"
PRICE_OUTCOME_COVERAGE_INCOMPLETE = "PRICE_OUTCOME_COVERAGE_INCOMPLETE"


def _validate_lineage(
    manifest: ResearchRunManifestV0,
    institutional: InstitutionalResearchInput,
    prices: PriceResearchInput,
    definition: BaselineFactorDefinition,
) -> None:
    if manifest.institutional_dataset.digest is None:
        raise ResearchInputError(
            "INSTITUTIONAL_DIGEST_MISSING",
            "ResearchRunManifest requires an institutional dataset digest",
        )
    if (
        manifest.institutional_dataset.artifact_id != institutional.dataset_id
        or manifest.institutional_dataset.digest != institutional.dataset_digest
    ):
        raise ResearchInputError(
            "INSTITUTIONAL_LINEAGE_MISMATCH",
            "institutional input differs from ResearchRunManifest",
        )
    if manifest.price_dataset.digest is None:
        raise ResearchInputError(
            "PRICE_DIGEST_MISSING",
            "ResearchRunManifest requires a price dataset digest",
        )
    if (
        manifest.price_dataset.artifact_id != prices.dataset_id
        or manifest.price_dataset.digest != prices.dataset_digest
    ):
        raise ResearchInputError(
            "PRICE_LINEAGE_MISMATCH",
            "price input differs from ResearchRunManifest",
        )
    expected_definition_digest = factor_definition_sha256(definition)
    definition_identity = manifest.factor_definition
    if (
        definition_identity.definition_id != definition.definition_id
        or definition_identity.version != definition.version
        or definition_identity.definition_digest != expected_definition_digest
    ):
        raise ResearchInputError(
            "FACTOR_DEFINITION_LINEAGE_MISMATCH",
            "factor definition differs from ResearchRunManifest",
        )


def _resolve_pit_members(
    *,
    sessions: tuple[date, ...],
    markets: frozenset[EquityMarket],
    manifest: ResearchRunManifestV0,
    universe: EquityUniversePort | None,
) -> tuple[
    bool,
    dict[date, tuple[DateEffectiveEquityRecord, ...]],
    tuple[str, ...],
]:
    identity = manifest.universe
    if identity is None or identity.digest is None or universe is None:
        return False, {}, (PIT_UNIVERSE_MISSING,)

    members_by_session: dict[date, tuple[DateEffectiveEquityRecord, ...]] = {}
    issues: list[str] = []
    for session in sessions:
        try:
            resolution = universe.resolve(session)
        except Exception:  # fail closed at a provider boundary
            issues.extend((PIT_UNIVERSE_MISSING, "PIT_UNIVERSE_RESOLUTION_FAILED"))
            continue
        if resolution.snapshot_id != identity.artifact_id:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_IDENTITY_MISMATCH"))
        if resolution.content_digest != identity.digest:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_DIGEST_MISMATCH"))
        if not resolution.research_eligible:
            issues.extend(resolution.issue_codes or (PIT_UNIVERSE_MISSING,))
        member_markets = frozenset(
            member.market for member in resolution.research_members
        )
        if not markets <= member_markets:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_MARKET_OUT_OF_SCOPE"))
        members_by_session[session] = resolution.research_members

    if issues:
        if PIT_UNIVERSE_MISSING not in issues:
            issues.insert(0, PIT_UNIVERSE_MISSING)
        return False, {}, tuple(dict.fromkeys(issues))
    return True, members_by_session, ()


class InstitutionalFactorDiagnostics:
    """Run fixed v0 diagnostics; this class never emits a candidate strategy."""

    def run(
        self,
        *,
        manifest: ResearchRunManifestV0,
        institutional: InstitutionalResearchInput,
        prices: PriceResearchInput,
        universe: EquityUniversePort | None = None,
        definition: BaselineFactorDefinition | None = None,
    ) -> InstitutionalFactorReportArtifact:
        selected_definition = definition or BaselineFactorDefinition()
        with localcontext() as context:
            context.prec = 36
            return self._run_with_fixed_decimal_context(
                manifest=manifest,
                institutional=institutional,
                prices=prices,
                universe=universe,
                definition=selected_definition,
            )

    @staticmethod
    def _run_with_fixed_decimal_context(
        *,
        manifest: ResearchRunManifestV0,
        institutional: InstitutionalResearchInput,
        prices: PriceResearchInput,
        universe: EquityUniversePort | None,
        definition: BaselineFactorDefinition,
    ) -> InstitutionalFactorReportArtifact:
        _validate_lineage(manifest, institutional, prices, definition)
        _ = institutional.target_sessions_by_market

        factor_points = compute_baseline_factor_points(
            institutional,
            definition,
            factor_start_session=manifest.factor_start_session,
            factor_end_session=manifest.factor_end_session,
        )
        if not factor_points:
            raise ResearchInputError(
                "NO_FACTOR_POINTS",
                "factor date range does not include a usable institutional partition",
            )

        sessions = tuple(sorted({point.session_date for point in factor_points}))
        markets = frozenset(point.market for point in factor_points)
        pit_eligible, members_by_session, pit_issues = _resolve_pit_members(
            sessions=sessions,
            markets=markets,
            manifest=manifest,
            universe=universe,
        )
        scope_eligible = institutional.scope_eligible
        cross_sectional_eligible = pit_eligible and scope_eligible

        distributions = build_distributions(
            factor_points,
            members_by_session=members_by_session if pit_eligible else None,
        )
        if cross_sectional_eligible:
            cross_sectional_points = build_cross_sectional_points(
                factor_points,
                members_by_session=members_by_session,
            )
            forward_outcomes = build_forward_outcomes(
                cross_sectional_points,
                prices,
                horizons=definition.forward_horizons,
            )
            rank_ic_observations = build_rank_ic_observations(
                cross_sectional_points,
                forward_outcomes,
                horizons=definition.forward_horizons,
            )
            ic_summaries = summarize_rank_ic(rank_ic_observations)
            decile_outcomes = summarize_decile_outcomes(forward_outcomes)
        else:
            cross_sectional_points = ()
            forward_outcomes = ()
            rank_ic_observations = ()
            ic_summaries = ()
            decile_outcomes = ()

        issues = list(pit_issues)
        if not scope_eligible:
            issues.append(SCOPE_INCOMPATIBLE)
        if any(outcome.adjusted_return is None for outcome in forward_outcomes):
            issues.append(PRICE_OUTCOME_COVERAGE_INCOMPLETE)
        issues.extend(
            (
                UNADJUSTED_INDUSTRY_SIZE,
                FORMAL_RESEARCH_REQUIREMENTS_MISSING,
            )
        )
        report = InstitutionalFactorReport(
            manifest=manifest,
            label=ResearchLabel.EXPLORATORY,
            strategy_ready=False,
            production_ready=False,
            pit_eligible=pit_eligible,
            scope_eligible=scope_eligible,
            cross_sectional_eligible=cross_sectional_eligible,
            research_eligible=False,
            confounding_status=ConfoundingStatus.UNADJUSTED_INDUSTRY_SIZE,
            issue_codes=tuple(dict.fromkeys(issues)),
            factor_points=factor_points,
            distributions=distributions,
            cross_sectional_points=cross_sectional_points,
            forward_outcomes=forward_outcomes,
            rank_ic_observations=rank_ic_observations,
            ic_summaries=ic_summaries,
            decile_outcomes=decile_outcomes,
        )
        return build_report_artifact(report)
