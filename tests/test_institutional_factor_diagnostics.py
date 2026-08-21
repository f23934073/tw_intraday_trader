from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, localcontext

import pytest

from institutional_data.domain import (
    CorrectionPolicy,
    InstitutionalFlowDaily,
    InstitutionalMarket,
    InstitutionalPartitionManifest,
    PartitionStatus,
)
from institutional_data.serialization import flow_rows_sha256
from institutional_research import (
    ArtifactIdentity,
    BaselineFactorDefinition,
    DailyAdjustedClose,
    DefinitionIdentity,
    FactorMetric,
    InstitutionalComponent,
    InstitutionalFactorDiagnostics,
    InstitutionalResearchInput,
    PriceResearchInput,
    ResearchInputError,
    ResearchLabel,
    ResearchRunManifestV0,
    factor_definition_sha256,
    institutional_bundle_sha256,
    price_rows_sha256,
)
from institutional_research.application import (
    PRICE_OUTCOME_COVERAGE_INCOMPLETE,
    SCOPE_INCOMPATIBLE,
)
from institutional_research.statistics import average_ranks, spearman
from watchlist.reference_data import (
    PIT_UNIVERSE_MISSING,
    DateEffectiveEquityRecord,
    EquityMarket,
    EquityUniverseArtifact,
    EquityUniverseManifest,
    EquityUniverseSnapshot,
    MarketCapCohort,
    SecurityType,
    SnapshotEquityUniverse,
    UniverseArtifactStatus,
    UniverseEvidenceMode,
)
from watchlist.serialization import snapshot_sha256


SOURCE_TARGET_SESSIONS = (
    (date(2024, 1, 2), date(2024, 1, 3)),
    (date(2024, 1, 3), date(2024, 1, 4)),
    (date(2024, 1, 4), date(2024, 1, 5)),
    (date(2024, 1, 5), date(2024, 1, 8)),
    (date(2024, 1, 8), date(2024, 1, 9)),
    (date(2024, 1, 9), date(2024, 1, 10)),
    (date(2024, 1, 10), date(2024, 1, 11)),
    (date(2024, 1, 11), date(2024, 1, 12)),
)
PRICE_SESSIONS = (
    date(2024, 1, 9),
    date(2024, 1, 10),
    date(2024, 1, 11),
    date(2024, 1, 12),
    date(2024, 1, 15),
    date(2024, 1, 16),
    date(2024, 1, 17),
    date(2024, 1, 18),
    date(2024, 1, 19),
)
SYMBOLS = ("A001", "B002", "C003")
EXPECTED_FACTOR_DEFINITION_SHA256 = (
    "7d4f6cdf3c811134d46fa2006e558b83335abae9e14386ea81ce4f06aa92e420"
)
EXPECTED_REPORT_SHA256 = (
    "209168663059183a230ab812d9d44d6470c66d61976ce3cd2c2bb827ac136265"
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fixed_ratio(numerator: int, denominator: int) -> Decimal:
    with localcontext() as context:
        context.prec = 36
        return Decimal(numerator) / Decimal(denominator)


def _sides(net_shares: int) -> tuple[int, int]:
    base = 1_000
    if net_shares >= 0:
        return base + net_shares, base
    return base, base - net_shares


def _net_shares(symbol: str, source_index: int) -> tuple[int, int]:
    if symbol == "A001":
        return 10 + source_index, 4 + source_index
    if symbol == "B002":
        return 2 + source_index, 12 + source_index
    return -8 - source_index, -5 - source_index


def _build_institutional(*, include_future: bool = False) -> InstitutionalResearchInput:
    sessions = list(SOURCE_TARGET_SESSIONS)
    if include_future:
        sessions.append((date(2024, 1, 12), date(2024, 1, 15)))

    all_rows: list[InstitutionalFlowDaily] = []
    manifests: list[InstitutionalPartitionManifest] = []
    for source_index, (source_session, target_session) in enumerate(sessions):
        partition_id = f"twse-{source_session.isoformat()}-final"
        raw_digest = _sha(partition_id)
        retrieved_at = datetime.fromisoformat(
            f"{source_session.isoformat()}T20:10:00+08:00"
        )
        first_observed_at = datetime.fromisoformat(
            f"{source_session.isoformat()}T20:05:00+08:00"
        )
        partition_rows: list[InstitutionalFlowDaily] = []
        for symbol in SYMBOLS:
            foreign_net, trust_net = _net_shares(symbol, source_index)
            foreign_buy, foreign_sell = _sides(foreign_net)
            trust_buy, trust_sell = _sides(trust_net)
            partition_rows.append(
                InstitutionalFlowDaily(
                    partition_id=partition_id,
                    market=InstitutionalMarket.TWSE,
                    symbol=symbol,
                    session_date=source_session,
                    foreign_ex_dealer_buy_shares=foreign_buy,
                    foreign_ex_dealer_sell_shares=foreign_sell,
                    foreign_ex_dealer_net_shares=foreign_net,
                    foreign_dealer_buy_shares=None,
                    foreign_dealer_sell_shares=None,
                    foreign_dealer_net_shares=None,
                    investment_trust_buy_shares=trust_buy,
                    investment_trust_sell_shares=trust_sell,
                    investment_trust_net_shares=trust_net,
                    dealer_proprietary_buy_shares=None,
                    dealer_proprietary_sell_shares=None,
                    dealer_proprietary_net_shares=None,
                    dealer_hedge_buy_shares=None,
                    dealer_hedge_sell_shares=None,
                    dealer_hedge_net_shares=None,
                    dealer_total_buy_shares=0,
                    dealer_total_sell_shares=0,
                    dealer_total_net_shares=0,
                    published_total_net_shares=foreign_net + trust_net,
                    trade_scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
                    correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
                    raw_artifact_id=f"raw-{partition_id}",
                    raw_sha256=raw_digest,
                    retrieved_at=retrieved_at,
                    first_observed_at=first_observed_at,
                    usable_from_session=target_session,
                )
            )
        rows = tuple(partition_rows)
        all_rows.extend(rows)
        manifests.append(
            InstitutionalPartitionManifest(
                partition_id=partition_id,
                market=InstitutionalMarket.TWSE,
                session_date=source_session,
                source_product="TWSE_T86_FINAL",
                trade_scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
                correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
                response_scope_note="Reviewed final scope fixture.",
                raw_artifact_id=f"raw-{partition_id}",
                raw_sha256=raw_digest,
                normalized_sha256=flow_rows_sha256(rows),
                retrieved_at=retrieved_at,
                first_observed_at=first_observed_at,
                usable_from_session=target_session,
                source_row_count=len(rows),
                normalized_row_count=len(rows),
                status=PartitionStatus.VALIDATED,
            )
        )
    rows_tuple = tuple(all_rows)
    manifests_tuple = tuple(manifests)
    return InstitutionalResearchInput(
        dataset_id="institutional-fixture-future"
        if include_future
        else "institutional-fixture-v0",
        dataset_digest=institutional_bundle_sha256(rows_tuple, manifests_tuple),
        rows=rows_tuple,
        manifests=manifests_tuple,
    )


def _build_prices(*, include_future: bool = False) -> PriceResearchInput:
    sessions = list(PRICE_SESSIONS)
    if include_future:
        sessions.append(date(2024, 1, 22))
    rows: list[DailyAdjustedClose] = []
    source_digest = _sha("adjusted-close-fixture")
    daily_step = {"A001": Decimal(2), "B002": Decimal(1), "C003": Decimal(-1)}
    for session_index, session in enumerate(sessions):
        for symbol in SYMBOLS:
            rows.append(
                DailyAdjustedClose(
                    market=EquityMarket.TWSE,
                    symbol=symbol,
                    session_date=session,
                    adjusted_close=Decimal(100)
                    + daily_step[symbol] * Decimal(session_index),
                    source_digest=source_digest,
                )
            )
    rows_tuple = tuple(rows)
    return PriceResearchInput(
        dataset_id="price-fixture-future" if include_future else "price-fixture-v0",
        dataset_digest=price_rows_sha256(rows_tuple),
        rows=rows_tuple,
    )


def _equity_record(
    symbol: str,
    *,
    source_digest: str,
    effective_from: date = date(2024, 1, 1),
) -> DateEffectiveEquityRecord:
    return DateEffectiveEquityRecord(
        symbol=symbol,
        name=f"Company {symbol}",
        market=EquityMarket.TWSE,
        security_type=SecurityType.COMMON_STOCK,
        listed_from=effective_from,
        listed_until=None,
        industry_code={"A001": "SEMI", "B002": "FIN", "C003": "IND"}.get(
            symbol, "OTHER"
        ),
        industry_name="Fixture industry",
        industry_as_of=effective_from,
        market_cap_twd=100_000_000_000,
        market_cap_cohort=MarketCapCohort.LARGE,
        market_cap_as_of=effective_from,
        effective_from=effective_from,
        effective_to=None,
        source_digest=source_digest,
    )


def _build_universe(
    *,
    evidence_mode: UniverseEvidenceMode = UniverseEvidenceMode.DATE_EFFECTIVE,
    include_future: bool = False,
) -> SnapshotEquityUniverse:
    source_digest = _sha("pit-universe-source")
    records = tuple(
        _equity_record(symbol, source_digest=source_digest) for symbol in SYMBOLS
    )
    snapshot_id = "pit-universe-fixture-v0"
    coverage_end = date(2024, 12, 31)
    if include_future:
        records += (
            _equity_record(
                "D004",
                source_digest=source_digest,
                effective_from=date(2025, 1, 1),
            ),
        )
        snapshot_id = "pit-universe-fixture-future"
        coverage_end = date(2025, 12, 31)
    snapshot = EquityUniverseSnapshot(snapshot_id=snapshot_id, records=records)
    manifest = EquityUniverseManifest(
        snapshot_id=snapshot_id,
        evidence_mode=evidence_mode,
        source_id="pit-universe-fixture",
        source_license="test-only",
        source_revision=1,
        parent_snapshot_id=None,
        correction_policy_note="Immutable test fixture.",
        immutable_revision_policy="New identity for every revision.",
        retrieved_at=datetime.fromisoformat("2024-01-01T00:00:00+08:00"),
        available_from_session=date(2024, 1, 1),
        coverage_start=date(2024, 1, 1),
        coverage_end=coverage_end,
        covered_markets=frozenset({EquityMarket.TWSE}),
        record_count=len(records),
        source_digest=source_digest,
        content_digest=snapshot_sha256(snapshot),
        status=UniverseArtifactStatus.VALIDATED,
    )
    return SnapshotEquityUniverse(EquityUniverseArtifact(snapshot, manifest))


@dataclass(frozen=True)
class ResearchFixture:
    institutional: InstitutionalResearchInput
    prices: PriceResearchInput
    universe: SnapshotEquityUniverse
    manifest: ResearchRunManifestV0


def _fixture(
    *,
    include_future: bool = False,
    universe_future: bool = False,
) -> ResearchFixture:
    institutional = _build_institutional(include_future=include_future)
    prices = _build_prices(include_future=include_future)
    universe = _build_universe(include_future=universe_future)
    definition = BaselineFactorDefinition()
    universe_artifact = universe.artifact
    manifest = ResearchRunManifestV0(
        price_dataset=ArtifactIdentity(prices.dataset_id, prices.dataset_digest),
        institutional_dataset=ArtifactIdentity(
            institutional.dataset_id,
            institutional.dataset_digest,
        ),
        universe=ArtifactIdentity(
            universe_artifact.snapshot.snapshot_id,
            universe_artifact.manifest.content_digest,
        ),
        factor_definition=DefinitionIdentity(
            definition.definition_id,
            definition.version,
            factor_definition_sha256(definition),
        ),
        factor_start_session=date(2024, 1, 9),
        factor_end_session=date(2024, 1, 12),
    )
    return ResearchFixture(institutional, prices, universe, manifest)


def _run(fixture: ResearchFixture):  # type: ignore[no-untyped-def]
    return InstitutionalFactorDiagnostics().run(
        manifest=fixture.manifest,
        institutional=fixture.institutional,
        prices=fixture.prices,
        universe=fixture.universe,
    )


def test_validated_inputs_produce_complete_exploratory_factor_report() -> None:
    artifact = _run(_fixture())
    report = artifact.report

    assert report.label is ResearchLabel.EXPLORATORY
    assert not report.strategy_ready
    assert not report.production_ready
    assert report.pit_eligible
    assert report.scope_eligible
    assert report.cross_sectional_eligible
    assert not report.research_eligible
    assert len(report.factor_points) == 120
    assert len(report.distributions) == 40
    assert len(report.cross_sectional_points) == 120
    assert len(report.forward_outcomes) == 360
    assert len(report.rank_ic_observations) == 120
    assert len(report.ic_summaries) == 30
    assert len(report.decile_outcomes) == 300

    foreign_a001 = {
        point.metric: point
        for point in report.factor_points
        if point.session_date == date(2024, 1, 9)
        and point.symbol == "A001"
        and point.component is InstitutionalComponent.FOREIGN_EX_DEALER
    }
    assert foreign_a001[FactorMetric.NET_SHARES_1D].value == Decimal(14)
    assert foreign_a001[FactorMetric.ROLLING_NET_SHARES_5D].value == Decimal(60)
    assert foreign_a001[FactorMetric.POSITIVE_DAYS_5D].value == Decimal(5)
    assert foreign_a001[FactorMetric.CONSECUTIVE_POSITIVE_DAYS_5D].value == Decimal(5)
    assert foreign_a001[FactorMetric.SELF_NORMALIZED_FLOW_5D].value == _fixed_ratio(
        60, 10_060
    )

    net_distribution = next(
        distribution
        for distribution in report.distributions
        if distribution.session_date == date(2024, 1, 9)
        and distribution.component is InstitutionalComponent.FOREIGN_EX_DEALER
        and distribution.metric is FactorMetric.NET_SHARES_1D
    )
    assert net_distribution.expected_count == 3
    assert net_distribution.observed_count == 3
    assert net_distribution.coverage_ratio == Decimal(1)
    assert net_distribution.null_rate == Decimal(0)
    assert {summary.horizon_sessions for summary in report.ic_summaries} == {1, 3, 5}


def test_same_inputs_produce_byte_identical_report_without_strategy_semantics() -> None:
    fixture = _fixture()
    first = _run(fixture)
    second = _run(fixture)

    assert first.report == second.report
    assert first.report_json == second.report_json
    assert first.report_digest == second.report_digest
    assert factor_definition_sha256(BaselineFactorDefinition()) == (
        EXPECTED_FACTOR_DEFINITION_SHA256
    )
    assert first.report_digest == EXPECTED_REPORT_SHA256
    with localcontext() as context:
        context.prec = 9
        reduced_caller_precision = _run(fixture)
    assert reduced_caller_precision.report_json == first.report_json
    assert reduced_caller_precision.report_digest == first.report_digest
    assert '"strategy_ready":false' in first.report_json
    assert '"production_ready":false' in first.report_json
    lowered = first.report_json.lower()
    for forbidden in ("candidate", "buy_score", "order", "top_10", "strategy_id"):
        assert forbidden not in lowered


def test_incomplete_five_session_history_is_null_not_backfilled() -> None:
    fixture = _fixture()
    manifest = replace(
        fixture.manifest,
        factor_start_session=date(2024, 1, 3),
        factor_end_session=date(2024, 1, 9),
    )
    report = (
        InstitutionalFactorDiagnostics()
        .run(
            manifest=manifest,
            institutional=fixture.institutional,
            prices=fixture.prices,
            universe=fixture.universe,
        )
        .report
    )

    early = next(
        point
        for point in report.factor_points
        if point.session_date == date(2024, 1, 3)
        and point.symbol == "A001"
        and point.component is InstitutionalComponent.FOREIGN_EX_DEALER
        and point.metric is FactorMetric.ROLLING_NET_SHARES_5D
    )
    assert early.value is None
    assert early.observed_sessions == 1
    assert early.expected_sessions == 5
    assert PRICE_OUTCOME_COVERAGE_INCOMPLETE in report.issue_codes


def test_delayed_partition_is_not_used_before_usable_session() -> None:
    fixture = _fixture()
    delayed_partition_id = "twse-2024-01-05-final"
    delayed_target = date(2024, 1, 13)
    changed_rows = tuple(
        replace(row, usable_from_session=delayed_target)
        if row.partition_id == delayed_partition_id
        else row
        for row in fixture.institutional.rows
    )
    changed_manifests = tuple(
        replace(
            manifest,
            usable_from_session=delayed_target,
            normalized_sha256=flow_rows_sha256(
                tuple(
                    row
                    for row in changed_rows
                    if row.partition_id == delayed_partition_id
                )
            ),
        )
        if manifest.partition_id == delayed_partition_id
        else manifest
        for manifest in fixture.institutional.manifests
    )
    institutional = InstitutionalResearchInput(
        dataset_id="institutional-delayed-partition",
        dataset_digest=institutional_bundle_sha256(
            changed_rows,
            changed_manifests,
        ),
        rows=changed_rows,
        manifests=changed_manifests,
    )
    manifest = replace(
        fixture.manifest,
        institutional_dataset=ArtifactIdentity(
            institutional.dataset_id,
            institutional.dataset_digest,
        ),
        factor_end_session=date(2024, 1, 9),
    )
    report = (
        InstitutionalFactorDiagnostics()
        .run(
            manifest=manifest,
            institutional=institutional,
            prices=fixture.prices,
            universe=fixture.universe,
        )
        .report
    )

    point = next(
        point
        for point in report.factor_points
        if point.session_date == date(2024, 1, 9)
        and point.symbol == "A001"
        and point.component is InstitutionalComponent.FOREIGN_EX_DEALER
        and point.metric is FactorMetric.ROLLING_NET_SHARES_5D
    )
    assert point.value is None
    assert point.observed_sessions == 4
    assert point.expected_sessions == 5


def test_zero_self_normalization_denominator_is_reported_as_null() -> None:
    fixture = _fixture()
    changed_rows = tuple(
        replace(
            row,
            foreign_ex_dealer_buy_shares=0,
            foreign_ex_dealer_sell_shares=0,
            foreign_ex_dealer_net_shares=0,
            published_total_net_shares=row.investment_trust_net_shares,
        )
        if row.symbol == "A001" and row.session_date <= date(2024, 1, 8)
        else row
        for row in fixture.institutional.rows
    )
    changed_manifests = tuple(
        replace(
            manifest,
            normalized_sha256=flow_rows_sha256(
                tuple(
                    row
                    for row in changed_rows
                    if row.partition_id == manifest.partition_id
                )
            ),
        )
        for manifest in fixture.institutional.manifests
    )
    institutional = InstitutionalResearchInput(
        dataset_id="institutional-zero-denominator",
        dataset_digest=institutional_bundle_sha256(
            changed_rows,
            changed_manifests,
        ),
        rows=changed_rows,
        manifests=changed_manifests,
    )
    manifest = replace(
        fixture.manifest,
        institutional_dataset=ArtifactIdentity(
            institutional.dataset_id,
            institutional.dataset_digest,
        ),
        factor_end_session=date(2024, 1, 9),
    )
    report = (
        InstitutionalFactorDiagnostics()
        .run(
            manifest=manifest,
            institutional=institutional,
            prices=fixture.prices,
            universe=fixture.universe,
        )
        .report
    )

    point = next(
        point
        for point in report.factor_points
        if point.session_date == date(2024, 1, 9)
        and point.symbol == "A001"
        and point.component is InstitutionalComponent.FOREIGN_EX_DEALER
        and point.metric is FactorMetric.SELF_NORMALIZED_FLOW_5D
    )
    distribution = next(
        item
        for item in report.distributions
        if item.session_date == date(2024, 1, 9)
        and item.component is InstitutionalComponent.FOREIGN_EX_DEALER
        and item.metric is FactorMetric.SELF_NORMALIZED_FLOW_5D
    )
    assert point.value is None
    assert distribution.non_null_count == 2
    assert distribution.null_count == 1
    assert distribution.null_rate == _fixed_ratio(1, 3)


def test_missing_pit_keeps_raw_factors_but_poison_gates_cross_sectional_output() -> (
    None
):
    fixture = _fixture()
    manifest = replace(fixture.manifest, universe=None)
    artifact = InstitutionalFactorDiagnostics().run(
        manifest=manifest,
        institutional=fixture.institutional,
        prices=fixture.prices,
        universe=None,
    )
    report = artifact.report

    assert report.factor_points
    assert report.distributions
    assert all(item.expected_count is None for item in report.distributions)
    assert not report.pit_eligible
    assert not report.cross_sectional_eligible
    assert PIT_UNIVERSE_MISSING in report.issue_codes
    assert report.cross_sectional_points == ()
    assert report.forward_outcomes == ()
    assert report.rank_ic_observations == ()
    assert report.ic_summaries == ()
    assert report.decile_outcomes == ()


@pytest.mark.parametrize("poison", ["current_snapshot", "digest_mismatch"])
def test_ineligible_or_mismatched_universe_poison_gates_entire_report(
    poison: str,
) -> None:
    fixture = _fixture()
    if poison == "current_snapshot":
        universe = _build_universe(evidence_mode=UniverseEvidenceMode.CURRENT_SNAPSHOT)
        manifest = fixture.manifest
    else:
        universe = fixture.universe
        manifest = replace(
            fixture.manifest,
            universe=ArtifactIdentity(
                fixture.manifest.universe.artifact_id,  # type: ignore[union-attr]
                "0" * 64,
            ),
        )
    report = (
        InstitutionalFactorDiagnostics()
        .run(
            manifest=manifest,
            institutional=fixture.institutional,
            prices=fixture.prices,
            universe=universe,
        )
        .report
    )

    assert PIT_UNIVERSE_MISSING in report.issue_codes
    assert not report.cross_sectional_eligible
    assert report.cross_sectional_points == ()
    assert report.rank_ic_observations == ()


def test_scope_drift_blocks_cross_sectional_diagnostics() -> None:
    fixture = _fixture()
    last_manifest = fixture.institutional.manifests[-1]
    updated_rows = tuple(
        replace(row, trade_scope_id="TWSE_SCOPE_CHANGED")
        if row.partition_id == last_manifest.partition_id
        else row
        for row in fixture.institutional.rows
    )
    last_partition_rows = tuple(
        row for row in updated_rows if row.partition_id == last_manifest.partition_id
    )
    updated_manifests = fixture.institutional.manifests[:-1] + (
        replace(
            last_manifest,
            trade_scope_id="TWSE_SCOPE_CHANGED",
            normalized_sha256=flow_rows_sha256(last_partition_rows),
        ),
    )
    institutional = InstitutionalResearchInput(
        dataset_id="institutional-scope-drift",
        dataset_digest=institutional_bundle_sha256(
            updated_rows,
            updated_manifests,
        ),
        rows=updated_rows,
        manifests=updated_manifests,
    )
    manifest = replace(
        fixture.manifest,
        institutional_dataset=ArtifactIdentity(
            institutional.dataset_id,
            institutional.dataset_digest,
        ),
    )
    report = (
        InstitutionalFactorDiagnostics()
        .run(
            manifest=manifest,
            institutional=institutional,
            prices=fixture.prices,
            universe=fixture.universe,
        )
        .report
    )

    assert report.pit_eligible
    assert not report.scope_eligible
    assert not report.cross_sectional_eligible
    assert SCOPE_INCOMPATIBLE in report.issue_codes
    assert report.cross_sectional_points == ()


def test_input_and_definition_digest_mismatches_fail_closed() -> None:
    fixture = _fixture()
    changed_price_rows = (
        replace(
            fixture.prices.rows[0],
            adjusted_close=fixture.prices.rows[0].adjusted_close + Decimal(1),
        ),
        *fixture.prices.rows[1:],
    )
    with pytest.raises(ResearchInputError) as price_error:
        PriceResearchInput(
            fixture.prices.dataset_id,
            fixture.prices.dataset_digest,
            changed_price_rows,
        )
    assert price_error.value.code == "PRICE_DIGEST_MISMATCH"

    changed_institutional_rows = (
        replace(
            fixture.institutional.rows[0],
            foreign_ex_dealer_net_shares=999,
        ),
        *fixture.institutional.rows[1:],
    )
    with pytest.raises(ResearchInputError) as institutional_error:
        InstitutionalResearchInput(
            fixture.institutional.dataset_id,
            fixture.institutional.dataset_digest,
            changed_institutional_rows,
            fixture.institutional.manifests,
        )
    assert institutional_error.value.code == "INSTITUTIONAL_PARTITION_DIGEST_MISMATCH"

    wrong_definition = replace(
        fixture.manifest.factor_definition,
        definition_digest="0" * 64,
    )
    with pytest.raises(ResearchInputError) as definition_error:
        InstitutionalFactorDiagnostics().run(
            manifest=replace(fixture.manifest, factor_definition=wrong_definition),
            institutional=fixture.institutional,
            prices=fixture.prices,
            universe=fixture.universe,
        )
    assert definition_error.value.code == "FACTOR_DEFINITION_LINEAGE_MISMATCH"


def test_future_evidence_does_not_change_earlier_diagnostic_values() -> None:
    base = _run(_fixture())
    future = _run(_fixture(include_future=True, universe_future=True))

    assert future.report.factor_points == base.report.factor_points
    assert future.report.distributions == base.report.distributions
    assert future.report.cross_sectional_points == base.report.cross_sectional_points
    assert future.report.forward_outcomes == base.report.forward_outcomes
    assert future.report.rank_ic_observations == base.report.rank_ic_observations
    assert future.report.ic_summaries == base.report.ic_summaries
    assert future.report.decile_outcomes == base.report.decile_outcomes
    assert future.report_digest != base.report_digest


def test_decimal_rank_statistics_handle_ties_without_float() -> None:
    assert average_ranks((Decimal(2), Decimal(1), Decimal(2))) == (
        Decimal("2.5"),
        Decimal(1),
        Decimal("2.5"),
    )
    assert spearman(
        (Decimal(1), Decimal(2), Decimal(3)),
        (Decimal(3), Decimal(2), Decimal(1)),
    ) == Decimal(-1)
