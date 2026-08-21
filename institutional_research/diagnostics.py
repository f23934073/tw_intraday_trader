"""Research-only distributions and PIT-gated cross-sectional diagnostics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_CEILING

from watchlist.reference_data import DateEffectiveEquityRecord, EquityMarket

from .domain import (
    CrossSectionalPoint,
    DecileOutcomeSummary,
    DistributionSummary,
    FactorMetric,
    FactorPoint,
    ForwardOutcome,
    IcSummary,
    InstitutionalComponent,
    RankIcObservation,
)
from .inputs import PriceResearchInput
from .statistics import (
    mean,
    nearest_rank,
    percentile_ranks,
    sample_standard_deviation,
    spearman,
)


DistributionKey = tuple[
    date,
    EquityMarket,
    InstitutionalComponent,
    FactorMetric,
]


def _member_lookup(
    members_by_session: dict[date, tuple[DateEffectiveEquityRecord, ...]],
    session: date,
    market: EquityMarket,
) -> dict[str, DateEffectiveEquityRecord]:
    return {
        member.symbol: member
        for member in members_by_session.get(session, ())
        if member.market is market
    }


def build_distributions(
    factor_points: tuple[FactorPoint, ...],
    *,
    members_by_session: dict[date, tuple[DateEffectiveEquityRecord, ...]] | None,
) -> tuple[DistributionSummary, ...]:
    grouped: dict[DistributionKey, list[FactorPoint]] = defaultdict(list)
    for point in factor_points:
        grouped[
            (point.session_date, point.market, point.component, point.metric)
        ].append(point)

    summaries: list[DistributionSummary] = []
    for (session, market, component, metric), points in sorted(
        grouped.items(),
        key=lambda item: tuple(
            value.value if hasattr(value, "value") else value for value in item[0]
        ),
    ):
        expected_count: int | None = None
        selected = points
        if members_by_session is not None:
            members = _member_lookup(members_by_session, session, market)
            expected_count = len(members)
            selected = [point for point in points if point.symbol in members]
        values = tuple(point.value for point in selected if point.value is not None)
        observed_count = len(selected)
        non_null_count = len(values)
        denominator = expected_count if expected_count is not None else observed_count
        null_count = max(denominator - non_null_count, 0)
        coverage_ratio = (
            Decimal(non_null_count) / Decimal(expected_count)
            if expected_count
            else None
        )
        null_rate = Decimal(null_count) / Decimal(denominator) if denominator else None
        summaries.append(
            DistributionSummary(
                session_date=session,
                market=market,
                component=component,
                metric=metric,
                expected_count=expected_count,
                observed_count=observed_count,
                non_null_count=non_null_count,
                null_count=null_count,
                coverage_ratio=coverage_ratio,
                null_rate=null_rate,
                minimum=min(values) if values else None,
                percentile_25=nearest_rank(values, Decimal("0.25")),
                median=nearest_rank(values, Decimal("0.5")),
                percentile_75=nearest_rank(values, Decimal("0.75")),
                maximum=max(values) if values else None,
            )
        )
    return tuple(summaries)


def _decile(percentile: Decimal) -> int:
    value = int((percentile * Decimal(10)).to_integral_value(rounding=ROUND_CEILING))
    return min(10, max(1, value))


def build_cross_sectional_points(
    factor_points: tuple[FactorPoint, ...],
    *,
    members_by_session: dict[date, tuple[DateEffectiveEquityRecord, ...]],
) -> tuple[CrossSectionalPoint, ...]:
    grouped: dict[DistributionKey, list[FactorPoint]] = defaultdict(list)
    for point in factor_points:
        if point.value is not None:
            grouped[
                (point.session_date, point.market, point.component, point.metric)
            ].append(point)

    output: list[CrossSectionalPoint] = []
    for (session, market, component, metric), points in grouped.items():
        members = _member_lookup(members_by_session, session, market)
        selected = sorted(
            (point for point in points if point.symbol in members),
            key=lambda point: point.symbol,
        )
        values = tuple(point.value for point in selected)
        if len(values) < 2 or any(value is None for value in values):
            continue
        percentiles = percentile_ranks(
            tuple(value for value in values if value is not None)
        )
        for point, percentile in zip(selected, percentiles, strict=True):
            member = members[point.symbol]
            assert point.value is not None
            output.append(
                CrossSectionalPoint(
                    session_date=session,
                    market=market,
                    symbol=point.symbol,
                    component=component,
                    metric=metric,
                    value=point.value,
                    percentile=percentile,
                    decile=_decile(percentile),
                    industry_code=member.industry_code,
                    market_cap_cohort=member.market_cap_cohort,
                )
            )
    return tuple(
        sorted(
            output,
            key=lambda point: (
                point.session_date,
                point.market.value,
                point.component.value,
                point.metric.value,
                point.symbol,
            ),
        )
    )


def build_forward_outcomes(
    cross_sectional_points: tuple[CrossSectionalPoint, ...],
    prices: PriceResearchInput,
    *,
    horizons: tuple[int, ...],
) -> tuple[ForwardOutcome, ...]:
    price_by_identity = {
        (row.market, row.symbol, row.session_date): row.adjusted_close
        for row in prices.rows
    }
    market_sessions: dict[EquityMarket, tuple[date, ...]] = {}
    for market in EquityMarket:
        market_sessions[market] = tuple(
            sorted({row.session_date for row in prices.rows if row.market is market})
        )
    session_indexes = {
        market: {session: index for index, session in enumerate(sessions)}
        for market, sessions in market_sessions.items()
    }

    outcomes: list[ForwardOutcome] = []
    for point in cross_sectional_points:
        sessions = market_sessions[point.market]
        base_index = session_indexes[point.market].get(point.session_date)
        base_price = price_by_identity.get(
            (point.market, point.symbol, point.session_date)
        )
        for horizon in horizons:
            adjusted_return: Decimal | None = None
            if (
                base_index is not None
                and base_price is not None
                and base_index + horizon < len(sessions)
            ):
                future_session = sessions[base_index + horizon]
                future_price = price_by_identity.get(
                    (point.market, point.symbol, future_session)
                )
                if future_price is not None:
                    adjusted_return = future_price / base_price - Decimal(1)
            outcomes.append(
                ForwardOutcome(
                    session_date=point.session_date,
                    market=point.market,
                    symbol=point.symbol,
                    component=point.component,
                    metric=point.metric,
                    decile=point.decile,
                    horizon_sessions=horizon,
                    adjusted_return=adjusted_return,
                )
            )
    return tuple(outcomes)


def build_rank_ic_observations(
    cross_sectional_points: tuple[CrossSectionalPoint, ...],
    outcomes: tuple[ForwardOutcome, ...],
    *,
    horizons: tuple[int, ...],
) -> tuple[RankIcObservation, ...]:
    point_groups: dict[DistributionKey, list[CrossSectionalPoint]] = defaultdict(list)
    for point in cross_sectional_points:
        point_groups[
            (point.session_date, point.market, point.component, point.metric)
        ].append(point)
    outcome_lookup = {
        (
            outcome.session_date,
            outcome.market,
            outcome.symbol,
            outcome.component,
            outcome.metric,
            outcome.horizon_sessions,
        ): outcome.adjusted_return
        for outcome in outcomes
    }

    observations: list[RankIcObservation] = []
    for (session, market, component, metric), points in sorted(
        point_groups.items(),
        key=lambda item: tuple(
            value.value if hasattr(value, "value") else value for value in item[0]
        ),
    ):
        ordered = sorted(points, key=lambda point: point.symbol)
        for horizon in horizons:
            pairs = tuple(
                (point.value, outcome)
                for point in ordered
                if (
                    outcome := outcome_lookup.get(
                        (
                            session,
                            market,
                            point.symbol,
                            component,
                            metric,
                            horizon,
                        )
                    )
                )
                is not None
            )
            observations.append(
                RankIcObservation(
                    session_date=session,
                    market=market,
                    component=component,
                    metric=metric,
                    horizon_sessions=horizon,
                    sample_size=len(pairs),
                    rank_ic=spearman(
                        tuple(pair[0] for pair in pairs),
                        tuple(pair[1] for pair in pairs),
                    ),
                )
            )
    return tuple(observations)


def summarize_rank_ic(
    observations: tuple[RankIcObservation, ...],
) -> tuple[IcSummary, ...]:
    grouped: dict[
        tuple[EquityMarket, InstitutionalComponent, FactorMetric, int],
        list[Decimal],
    ] = defaultdict(list)
    keys: set[tuple[EquityMarket, InstitutionalComponent, FactorMetric, int]] = set()
    for observation in observations:
        key = (
            observation.market,
            observation.component,
            observation.metric,
            observation.horizon_sessions,
        )
        keys.add(key)
        if observation.rank_ic is not None:
            grouped[key].append(observation.rank_ic)

    summaries: list[IcSummary] = []
    for market, component, metric, horizon in sorted(
        keys,
        key=lambda key: (key[0].value, key[1].value, key[2].value, key[3]),
    ):
        values = tuple(grouped[(market, component, metric, horizon)])
        average = mean(values)
        deviation = sample_standard_deviation(values)
        summaries.append(
            IcSummary(
                market=market,
                component=component,
                metric=metric,
                horizon_sessions=horizon,
                observation_count=len(values),
                mean_rank_ic=average,
                icir=(
                    average / deviation
                    if average is not None and deviation is not None and deviation != 0
                    else None
                ),
            )
        )
    return tuple(summaries)


def summarize_decile_outcomes(
    outcomes: tuple[ForwardOutcome, ...],
) -> tuple[DecileOutcomeSummary, ...]:
    grouped: dict[
        tuple[EquityMarket, InstitutionalComponent, FactorMetric, int, int],
        list[Decimal],
    ] = defaultdict(list)
    base_keys: set[tuple[EquityMarket, InstitutionalComponent, FactorMetric, int]] = (
        set()
    )
    for outcome in outcomes:
        base_key = (
            outcome.market,
            outcome.component,
            outcome.metric,
            outcome.horizon_sessions,
        )
        base_keys.add(base_key)
        if outcome.adjusted_return is not None:
            grouped[(*base_key, outcome.decile)].append(outcome.adjusted_return)

    summaries: list[DecileOutcomeSummary] = []
    for market, component, metric, horizon in sorted(
        base_keys,
        key=lambda key: (key[0].value, key[1].value, key[2].value, key[3]),
    ):
        for decile in range(1, 11):
            values = tuple(grouped[(market, component, metric, horizon, decile)])
            summaries.append(
                DecileOutcomeSummary(
                    market=market,
                    component=component,
                    metric=metric,
                    horizon_sessions=horizon,
                    decile=decile,
                    observation_count=len(values),
                    mean_adjusted_return=mean(values),
                )
            )
    return tuple(summaries)
