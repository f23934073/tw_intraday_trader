from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, localcontext

import pytest

from institutional_prior import (
    CandidatePriorArtifact,
    CandidatePriorHypothesis,
    CandidatePriorInputError,
    CandidatePriorRunManifestV0,
    EvaluationCohort,
    InstitutionalCandidatePriorBuilder,
    InstitutionalFactorPriorArtifact,
    PriceMomentumCandidate,
    PriceMomentumPrior,
    PriceMomentumPriorArtifact,
    build_price_momentum_prior_artifact,
    candidate_prior_definition_identity,
    candidate_prior_definition_sha256,
    candidate_prior_definitions,
    project_institutional_factor_prior,
)
from institutional_prior.application import PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE
from institutional_prior.serialization import (
    build_candidate_prior_artifact,
    candidate_prior_entries_sha256,
)
from institutional_research.domain import (
    ArtifactIdentity,
    BaselineFactorDefinition,
    ConfoundingStatus,
    CrossSectionalPoint,
    DefinitionIdentity,
    FactorMetric,
    InstitutionalComponent,
    InstitutionalFactorReport,
    InstitutionalFactorReportArtifact,
    ResearchLabel,
    ResearchRunManifestV0,
)
from institutional_research.serialization import (
    build_report_artifact,
    factor_definition_sha256,
)
from watchlist.reference_data import (
    DateEffectiveEquityRecord,
    EquityMarket,
    EquityUniverseResolution,
    MarketCapCohort,
    SecurityType,
    UniverseEvidenceMode,
)

TARGET = date(2026, 8, 20)
AS_OF = date(2026, 8, 19)
UNIVERSE = ArtifactIdentity("pit-equity-universe-2026", "a" * 64)
CALENDAR = ArtifactIdentity("taifex-calendar-2026", "b" * 64)
EXPECTED_DEFINITION_DIGESTS = (
    "63fb43439e1fcfa54e09d7d53e18f0cbd7ead221f419f8eb81d87f23c62ba409",
    "8c3b1bba7a93da4231de44b065c5b37a7dd434d620eb20e245f12dc769d5fe0c",
)
EXPECTED_FACTOR_PRIOR_DIGEST = (
    "e2fd58561470f9a48ca14c73a614784eb2af71122eca8ae4557b62189592dfa6"
)
EXPECTED_ARTIFACT_DIGEST = (
    "5b593a617563d3f121b547b9f7cf390d952afd70d063a65023ec63619028a573"
)


@dataclass(frozen=True)
class _Universe:
    resolution: EquityUniverseResolution

    def resolve(self, as_of_session: date) -> EquityUniverseResolution:
        assert as_of_session == TARGET
        return self.resolution


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _point(
    symbol: str,
    component: InstitutionalComponent,
    value: str,
    percentile: str,
    *,
    session: date = TARGET,
) -> CrossSectionalPoint:
    return CrossSectionalPoint(
        session_date=session,
        market=EquityMarket.TWSE,
        symbol=symbol,
        component=component,
        metric=FactorMetric.ROLLING_NET_SHARES_5D,
        value=Decimal(value),
        percentile=Decimal(percentile),
        decile=max(1, int(Decimal(percentile) * 10)),
        industry_code="SEMI",
        market_cap_cohort=MarketCapCohort.LARGE,
    )


def _universe() -> _Universe:
    members = tuple(
        DateEffectiveEquityRecord(
            symbol=symbol,
            name=f"Company {symbol}",
            market=EquityMarket.TWSE,
            security_type=SecurityType.COMMON_STOCK,
            listed_from=date(2020, 1, 1),
            listed_until=None,
            industry_code="SEMI",
            industry_name="Semiconductor",
            industry_as_of=date(2020, 1, 1),
            market_cap_twd=100_000_000_000,
            market_cap_cohort=MarketCapCohort.LARGE,
            market_cap_as_of=date(2020, 1, 1),
            effective_from=date(2020, 1, 1),
            effective_to=None,
            source_digest="f" * 64,
        )
        for symbol in ("A001", "B002", "C003", "D004", "M005")
    )
    return _Universe(
        EquityUniverseResolution(
            as_of_session=TARGET,
            snapshot_id=UNIVERSE.artifact_id,
            evidence_mode=UniverseEvidenceMode.DATE_EFFECTIVE,
            content_digest=UNIVERSE.digest,
            active_records=members,
            research_members=members,
            research_eligible=True,
            issue_codes=(),
        )
    )


def _factor_artifact(
    *,
    pit_eligible: bool = True,
    factor_end_session: date = TARGET,
    points: tuple[CrossSectionalPoint, ...] | None = None,
) -> InstitutionalFactorReportArtifact:
    definition = BaselineFactorDefinition()
    run = ResearchRunManifestV0(
        price_dataset=ArtifactIdentity("price-dataset", "c" * 64),
        institutional_dataset=ArtifactIdentity("institutional-dataset", "d" * 64),
        universe=UNIVERSE,
        factor_definition=DefinitionIdentity(
            definition.definition_id,
            definition.version,
            factor_definition_sha256(definition),
        ),
        factor_start_session=TARGET,
        factor_end_session=factor_end_session,
    )
    selected_points = points or (
        _point("A001", InstitutionalComponent.FOREIGN_EX_DEALER, "10", "0.5"),
        _point("A001", InstitutionalComponent.INVESTMENT_TRUST, "8", "0.8"),
        _point("B002", InstitutionalComponent.FOREIGN_EX_DEALER, "7", "0.7"),
        _point("B002", InstitutionalComponent.INVESTMENT_TRUST, "-2", "0.2"),
        _point("C003", InstitutionalComponent.FOREIGN_EX_DEALER, "6", "0.6"),
        _point("C003", InstitutionalComponent.INVESTMENT_TRUST, "5", "0.6"),
        _point("D004", InstitutionalComponent.FOREIGN_EX_DEALER, "0", "0.9"),
        _point("D004", InstitutionalComponent.INVESTMENT_TRUST, "-1", "0.4"),
    )
    report = InstitutionalFactorReport(
        manifest=run,
        label=ResearchLabel.EXPLORATORY,
        strategy_ready=False,
        production_ready=False,
        pit_eligible=pit_eligible,
        scope_eligible=True,
        cross_sectional_eligible=pit_eligible,
        research_eligible=False,
        confounding_status=ConfoundingStatus.UNADJUSTED_INDUSTRY_SIZE,
        issue_codes=(
            "UNADJUSTED_INDUSTRY_SIZE",
            "FORMAL_RESEARCH_REQUIREMENTS_MISSING",
        ),
        factor_points=(),
        distributions=(),
        cross_sectional_points=selected_points,
        forward_outcomes=(),
        rank_ic_observations=(),
        ic_summaries=(),
        decile_outcomes=(),
    )
    return build_report_artifact(report)


def _price_artifact() -> PriceMomentumPriorArtifact:
    prior = PriceMomentumPrior(
        definition=DefinitionIdentity(
            "price_momentum_baseline",
            "v1",
            "e" * 64,
        ),
        calendar=CALENDAR,
        target_session=TARGET,
        as_of_session=AS_OF,
        generated_at=datetime.fromisoformat("2026-08-19T21:00:00+08:00"),
        entries=tuple(
            PriceMomentumCandidate(
                market=EquityMarket.TWSE,
                symbol=symbol,
                rank=rank,
                source_entry_digest=_sha(f"price-entry-{symbol}"),
            )
            for rank, symbol in enumerate(("A001", "B002", "D004", "X999"), 1)
        ),
    )
    return build_price_momentum_prior_artifact(
        artifact_id="price-momentum-prior-2026-08-20",
        prior=prior,
    )


def _factor_prior(
    report: InstitutionalFactorReportArtifact | None = None,
) -> InstitutionalFactorPriorArtifact:
    return project_institutional_factor_prior(
        factor_report=report or _factor_artifact(),
        target_session=TARGET,
    )


def _run_manifest(
    factor: InstitutionalFactorPriorArtifact,
    price: PriceMomentumPriorArtifact,
    *,
    definitions: tuple[DefinitionIdentity, ...] | None = None,
) -> CandidatePriorRunManifestV0:
    return CandidatePriorRunManifestV0(
        factor_prior=ArtifactIdentity(factor.artifact_id, factor.prior_digest),
        price_momentum_prior=ArtifactIdentity(price.artifact_id, price.prior_digest),
        universe=UNIVERSE,
        calendar=CALENDAR,
        hypothesis_definitions=definitions
        or tuple(
            candidate_prior_definition_identity(item)
            for item in candidate_prior_definitions()
        ),
        target_session=TARGET,
        as_of_session=AS_OF,
        generated_at=datetime.fromisoformat("2026-08-20T07:00:00+08:00"),
    )


def _build(
    factor: InstitutionalFactorPriorArtifact | None = None,
    price: PriceMomentumPriorArtifact | None = None,
    universe: _Universe | None = None,
) -> CandidatePriorArtifact:
    selected_factor = factor or _factor_prior()
    selected_price = price or _price_artifact()
    manifest = _run_manifest(selected_factor, selected_price)
    return InstitutionalCandidatePriorBuilder().build(
        manifest=manifest,
        factor_prior=selected_factor,
        price_momentum_prior=selected_price,
        universe=universe or _universe(),
    )


def test_v0_definitions_freeze_primary_5d_before_candidate_evaluation() -> None:
    definitions = candidate_prior_definitions()

    assert tuple(item.primary_lookback_sessions for item in definitions) == (5, 5)
    assert tuple(item.primary_forward_horizon_sessions for item in definitions) == (
        5,
        5,
    )
    assert tuple(item.secondary_forward_horizons for item in definitions) == (
        (1, 3),
        (1, 3),
    )
    assert tuple(item.minimum_percentile for item in definitions) == (
        Decimal("0.5"),
        Decimal("0.5"),
    )
    assert tuple(candidate_prior_definition_sha256(item) for item in definitions) == (
        EXPECTED_DEFINITION_DIGESTS
    )
    assert _factor_prior().prior_digest == EXPECTED_FACTOR_PRIOR_DIGEST


def test_builds_candidate_only_projection_and_preserves_evaluation_cohorts() -> None:
    artifact = _build()
    payloads = {entry.payload.symbol: entry.payload for entry in artifact.entries}

    assert tuple(entry.payload.symbol for entry in artifact.entries) == (
        "A001",
        "C003",
        "B002",
        "D004",
        "M005",
    )
    assert tuple(item.symbol for item in artifact.projections) == (
        "A001",
        "C003",
        "B002",
    )
    assert payloads["A001"].candidate_rank == 1
    assert payloads["A001"].matched_hypotheses == tuple(CandidatePriorHypothesis)
    assert payloads["A001"].foreign_5d_percentile == Decimal("0.5")
    assert payloads["A001"].cohorts == tuple(EvaluationCohort)
    assert payloads["C003"].candidate_rank == 2
    assert payloads["C003"].matched_hypotheses == (
        CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS,
    )
    assert payloads["C003"].cohorts == (
        EvaluationCohort.ELIGIBLE_UNIVERSE,
        EvaluationCohort.INSTITUTIONAL_ONLY,
    )
    assert payloads["B002"].candidate_rank == 3
    assert payloads["B002"].matched_hypotheses == (
        CandidatePriorHypothesis.MOMENTUM_CONFIRMATION,
    )
    assert payloads["D004"].candidate_rank is None
    assert payloads["D004"].cohorts == (
        EvaluationCohort.ELIGIBLE_UNIVERSE,
        EvaluationCohort.PRICE_ONLY,
    )
    assert payloads["D004"].selection_reason_codes == ("PRICE_ONLY_CONTROL",)
    assert payloads["M005"].cohorts == (EvaluationCohort.ELIGIBLE_UNIVERSE,)
    assert payloads["M005"].foreign_5d_value is None
    assert payloads["M005"].trust_5d_value is None
    assert artifact.manifest.entry_count == 5
    assert artifact.manifest.projected_candidate_count == 3
    assert PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE in artifact.manifest.issue_codes


def test_same_inputs_are_byte_identical_and_never_claim_execution_readiness() -> None:
    first = _build()
    second = _build()

    assert first == second
    assert first.artifact_digest == EXPECTED_ARTIFACT_DIGEST
    with localcontext() as context:
        context.prec = 7
        reduced_caller_precision = _build()
    assert reduced_caller_precision.artifact_json == first.artifact_json
    assert reduced_caller_precision.artifact_digest == first.artifact_digest
    assert not first.manifest.strategy_ready
    assert not first.manifest.production_ready
    assert not first.manifest.live_admission_ready
    assert not first.manifest.execution_allowed
    assert first.manifest.research_status is ResearchLabel.EXPLORATORY
    for projection in first.projections:
        assert not projection.strategy_ready
        assert not projection.production_ready
        assert not projection.live_admission_ready
        assert not projection.execution_allowed
        assert projection.research_status is ResearchLabel.EXPLORATORY
    lowered = first.artifact_json.lower()
    for forbidden in (
        "buy_score",
        "entry_rule",
        "order_instruction",
        '"strategy_ready":true',
        '"production_ready":true',
        '"live_admission_ready":true',
        '"execution_allowed":true',
    ):
        assert forbidden not in lowered


def test_missing_component_is_not_zero_filled_or_treated_as_consensus() -> None:
    base = _factor_artifact()
    points = tuple(
        point
        for point in base.report.cross_sectional_points
        if not (
            point.symbol == "C003"
            and point.component is InstitutionalComponent.INVESTMENT_TRUST
        )
    )
    factor = _factor_prior(_factor_artifact(points=points))

    artifact = _build(factor=factor)
    c003 = next(
        entry.payload for entry in artifact.entries if entry.payload.symbol == "C003"
    )

    assert c003.trust_5d_value is None
    assert c003.trust_5d_percentile is None
    assert CandidatePriorHypothesis.FOREIGN_TRUST_CONSENSUS not in (
        c003.matched_hypotheses
    )
    assert all(projection.symbol != "C003" for projection in artifact.projections)


@pytest.mark.parametrize(
    ("poison", "expected_code"),
    [
        ("factor_json", "FACTOR_REPORT_DIGEST_MISMATCH"),
        ("factor_prior_json", "FACTOR_PRIOR_DIGEST_MISMATCH"),
        ("price_json", "PRICE_PRIOR_DIGEST_MISMATCH"),
        ("pit", "FACTOR_REPORT_NOT_CROSS_SECTIONAL_ELIGIBLE"),
        ("definitions", "CANDIDATE_DEFINITION_LINEAGE_MISMATCH"),
    ],
)
def test_lineage_and_eligibility_poison_gates_emit_no_artifact(
    poison: str,
    expected_code: str,
) -> None:
    factor_report = _factor_artifact(pit_eligible=poison != "pit")
    price = _price_artifact()
    definitions = None
    if poison == "factor_json":
        factor_report = replace(factor_report, report_json="{}")
    elif poison == "price_json":
        price = replace(price, prior_json="{}")
    elif poison == "definitions":
        definitions = (
            replace(
                candidate_prior_definition_identity(candidate_prior_definitions()[0]),
                definition_digest="0" * 64,
            ),
        )
    if poison in {"factor_json", "pit"}:
        with pytest.raises(CandidatePriorInputError) as caught:
            _factor_prior(factor_report)
        assert caught.value.code == expected_code
        return

    factor = _factor_prior(factor_report)
    if poison == "factor_prior_json":
        factor = replace(factor, prior_json="{}")
    manifest = _run_manifest(factor, price, definitions=definitions)

    with pytest.raises(CandidatePriorInputError) as caught:
        InstitutionalCandidatePriorBuilder().build(
            manifest=manifest,
            factor_prior=factor,
            price_momentum_prior=price,
            universe=_universe(),
        )

    assert caught.value.code == expected_code


def test_post_target_report_bytes_do_not_change_factor_or_candidate_prior() -> None:
    base_report = _factor_artifact()
    base_prior = _factor_prior(base_report)
    future_session = date(2026, 8, 21)
    points = base_report.report.cross_sectional_points + (
        _point(
            "A001",
            InstitutionalComponent.FOREIGN_EX_DEALER,
            "999999",
            "1",
            session=future_session,
        ),
    )
    future_report = _factor_artifact(
        factor_end_session=future_session,
        points=points,
    )
    future_manifest = replace(
        future_report.report.manifest,
        price_dataset=ArtifactIdentity("future-price-bundle", "1" * 64),
    )
    future_report = build_report_artifact(
        replace(future_report.report, manifest=future_manifest)
    )
    future_prior = _factor_prior(future_report)
    price = _price_artifact()

    assert future_report.report_digest != base_report.report_digest
    assert future_prior == base_prior
    lowered_prior = base_prior.prior_json.lower()
    for forbidden in (
        "forward_outcomes",
        "rank_ic",
        "decile_outcomes",
        "price_dataset",
        "report_digest",
    ):
        assert forbidden not in lowered_prior
    assert "institutional_dataset" in lowered_prior
    first = _build(factor=base_prior, price=price)
    second = _build(factor=future_prior, price=price)

    assert second.artifact_json == first.artifact_json
    assert second.artifact_digest == first.artifact_digest

    changed_institutional_report = build_report_artifact(
        replace(
            future_report.report,
            manifest=replace(
                future_report.report.manifest,
                institutional_dataset=ArtifactIdentity(
                    "future-institutional-bundle",
                    "2" * 64,
                ),
            ),
        )
    )
    changed_institutional_prior = _factor_prior(changed_institutional_report)
    assert changed_institutional_prior.prior_digest != base_prior.prior_digest
    with pytest.raises(CandidatePriorInputError) as caught:
        InstitutionalCandidatePriorBuilder().build(
            manifest=_run_manifest(base_prior, price),
            factor_prior=changed_institutional_prior,
            price_momentum_prior=price,
            universe=_universe(),
        )
    assert caught.value.code == "FACTOR_PRIOR_LINEAGE_MISMATCH"


@pytest.mark.parametrize(
    ("poison", "expected_code"),
    [
        ("readiness", "FACTOR_REPORT_READINESS_INVALID"),
        ("target", "TARGET_SESSION_OUTSIDE_FACTOR_REPORT"),
        ("universe", "FACTOR_REPORT_UNIVERSE_MISSING"),
        ("definition", "PRIMARY_FACTOR_DEFINITION_MISMATCH"),
        ("points", "FACTOR_PRIOR_PROJECTION_INVALID"),
    ],
)
def test_factor_prior_projection_is_fail_closed(
    poison: str,
    expected_code: str,
) -> None:
    artifact = _factor_artifact()
    report = artifact.report
    target = TARGET
    if poison == "readiness":
        report = replace(report, research_eligible=True)
    elif poison == "target":
        target = date(2026, 8, 21)
    elif poison == "universe":
        report = replace(report, manifest=replace(report.manifest, universe=None))
    elif poison == "definition":
        report = replace(
            report,
            manifest=replace(
                report.manifest,
                factor_definition=replace(
                    report.manifest.factor_definition,
                    definition_digest="0" * 64,
                ),
            ),
        )
    else:
        report = replace(report, cross_sectional_points=())
    artifact = build_report_artifact(report)

    with pytest.raises(CandidatePriorInputError) as caught:
        project_institutional_factor_prior(
            factor_report=artifact,
            target_session=target,
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("poison", "expected_code"),
    [
        ("identity", "UNIVERSE_LINEAGE_MISMATCH"),
        ("ineligible", "PIT_UNIVERSE_NOT_RESEARCH_ELIGIBLE"),
    ],
)
def test_complete_pit_denominator_is_itself_poison_gated(
    poison: str,
    expected_code: str,
) -> None:
    universe = _universe()
    if poison == "identity":
        resolution = replace(universe.resolution, snapshot_id="wrong-universe")
    else:
        resolution = replace(
            universe.resolution,
            research_members=(),
            research_eligible=False,
            issue_codes=("PIT_UNIVERSE_MISSING",),
        )

    with pytest.raises(CandidatePriorInputError) as caught:
        _build(universe=_Universe(resolution))

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("poison", "expected_code"),
    [
        ("session", "PRICE_PRIOR_SESSION_MISMATCH"),
        ("generated_after_run", "PRICE_PRIOR_GENERATED_AFTER_RUN"),
    ],
)
def test_stale_or_late_price_prior_is_rejected(
    poison: str,
    expected_code: str,
) -> None:
    base = _price_artifact()
    if poison == "session":
        prior = replace(base.prior, target_session=date(2026, 8, 21))
    else:
        prior = replace(
            base.prior,
            generated_at=datetime.fromisoformat("2026-08-20T08:00:00+08:00"),
        )
    price = build_price_momentum_prior_artifact(
        artifact_id=base.artifact_id,
        prior=prior,
    )
    factor = _factor_prior()

    with pytest.raises(CandidatePriorInputError) as caught:
        InstitutionalCandidatePriorBuilder().build(
            manifest=_run_manifest(factor, price),
            factor_prior=factor,
            price_momentum_prior=price,
            universe=_universe(),
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("poison", "expected_code"),
    [
        ("outside_universe", "FACTOR_POINT_OUTSIDE_PINNED_UNIVERSE"),
        ("duplicate", "FACTOR_PRIOR_PROJECTION_INVALID"),
    ],
)
def test_primary_factor_population_is_structurally_poison_gated(
    poison: str,
    expected_code: str,
) -> None:
    base_points = _factor_artifact().report.cross_sectional_points
    if poison == "outside_universe":
        extra = _point(
            "X999",
            InstitutionalComponent.FOREIGN_EX_DEALER,
            "10",
            "0.9",
        )
    else:
        extra = base_points[0]
    factor_report = _factor_artifact(points=base_points + (extra,))
    price = _price_artifact()

    if poison == "duplicate":
        with pytest.raises(CandidatePriorInputError) as caught:
            _factor_prior(factor_report)
        assert caught.value.code == expected_code
        return

    factor = _factor_prior(factor_report)

    with pytest.raises(CandidatePriorInputError) as caught:
        InstitutionalCandidatePriorBuilder().build(
            manifest=_run_manifest(factor, price),
            factor_prior=factor,
            price_momentum_prior=price,
            universe=_universe(),
        )

    assert caught.value.code == expected_code


def test_pr004_contract_rejects_strategy_or_production_readiness() -> None:
    report = _factor_artifact().report

    with pytest.raises(ValueError, match="strategy-ready"):
        replace(report, strategy_ready=True)
    with pytest.raises(ValueError, match="production-ready"):
        replace(report, production_ready=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "v1"},
        {"primary_lookback_sessions": 3},
        {"primary_forward_horizon_sessions": 3},
        {"secondary_forward_horizons": (1, 5)},
        {"minimum_percentile": Decimal("0.8")},
        {"require_positive_raw_flow": False},
        {"requires_price_prior": False},
    ],
)
def test_definition_constructor_rejects_post_result_rule_changes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(candidate_prior_definitions()[0], **changes)


def test_entry_constructor_rejects_contradictory_hypothesis_semantics() -> None:
    payloads = {entry.payload.symbol: entry.payload for entry in _build().entries}
    c003 = payloads["C003"]
    b002 = payloads["B002"]

    with pytest.raises(ValueError, match="both be present"):
        replace(c003, trust_5d_percentile=None)
    with pytest.raises(ValueError, match="between zero and one"):
        replace(c003, trust_5d_percentile=Decimal("1.1"))
    with pytest.raises(ValueError, match="INSTITUTIONAL_ONLY"):
        replace(
            c003,
            cohorts=(EvaluationCohort.ELIGIBLE_UNIVERSE,),
        )
    with pytest.raises(ValueError, match="consensus"):
        replace(c003, matched_hypotheses=(), candidate_rank=None)
    with pytest.raises(ValueError, match="momentum confirmation"):
        replace(b002, matched_hypotheses=(), candidate_rank=None)


def test_artifact_builder_rejects_manifest_or_entry_digest_contradictions() -> None:
    artifact = _build()

    with pytest.raises(ValueError, match="entry_count"):
        build_candidate_prior_artifact(
            manifest=replace(
                artifact.manifest,
                entry_count=artifact.manifest.entry_count + 1,
            ),
            entries=artifact.entries,
        )
    with pytest.raises(ValueError, match="entries_digest"):
        build_candidate_prior_artifact(
            manifest=replace(artifact.manifest, entries_digest="0" * 64),
            entries=artifact.entries,
        )
    tampered_entries = (
        replace(artifact.entries[0], entry_digest="0" * 64),
        *artifact.entries[1:],
    )
    with pytest.raises(ValueError, match="entry_digest"):
        build_candidate_prior_artifact(
            manifest=replace(
                artifact.manifest,
                entries_digest=candidate_prior_entries_sha256(tampered_entries),
            ),
            entries=tampered_entries,
        )
    with pytest.raises(ValueError, match="projected_candidate_count"):
        build_candidate_prior_artifact(
            manifest=replace(
                artifact.manifest,
                projected_candidate_count=2,
            ),
            entries=artifact.entries,
        )
