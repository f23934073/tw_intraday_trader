"""Pure baseline institutional-factor computation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from institutional_data.domain import InstitutionalFlowDaily, InstitutionalMarket
from watchlist.reference_data import EquityMarket

from .domain import (
    BaselineFactorDefinition,
    FactorMetric,
    FactorPoint,
    InstitutionalComponent,
)
from .inputs import InstitutionalResearchInput


def _component_values(
    row: InstitutionalFlowDaily,
    component: InstitutionalComponent,
) -> tuple[int, int, int]:
    if component is InstitutionalComponent.FOREIGN_EX_DEALER:
        return (
            row.foreign_ex_dealer_buy_shares,
            row.foreign_ex_dealer_sell_shares,
            row.foreign_ex_dealer_net_shares,
        )
    return (
        row.investment_trust_buy_shares,
        row.investment_trust_sell_shares,
        row.investment_trust_net_shares,
    )


def _five_session_values(
    *,
    rows_by_identity: dict[
        tuple[InstitutionalMarket, str, date], InstitutionalFlowDaily
    ],
    market: InstitutionalMarket,
    symbol: str,
    source_sessions: tuple[date, ...],
    component: InstitutionalComponent,
) -> tuple[tuple[int, int, int], ...]:
    values: list[tuple[int, int, int]] = []
    for session in source_sessions:
        row = rows_by_identity.get((market, symbol, session))
        if row is not None:
            values.append(_component_values(row, component))
    return tuple(values)


def _five_session_metric(
    metric: FactorMetric,
    values: tuple[tuple[int, int, int], ...],
    *,
    complete: bool,
) -> Decimal | None:
    if not complete:
        return None
    net_values = tuple(value[2] for value in values)
    if metric is FactorMetric.ROLLING_NET_SHARES_5D:
        return Decimal(sum(net_values))
    if metric is FactorMetric.POSITIVE_DAYS_5D:
        return Decimal(sum(value > 0 for value in net_values))
    if metric is FactorMetric.CONSECUTIVE_POSITIVE_DAYS_5D:
        consecutive = 0
        for value in reversed(net_values):
            if value <= 0:
                break
            consecutive += 1
        return Decimal(consecutive)
    if metric is FactorMetric.SELF_NORMALIZED_FLOW_5D:
        denominator = sum(buy + sell for buy, sell, _ in values)
        if denominator == 0:
            return None
        return Decimal(sum(net_values)) / Decimal(denominator)
    raise ValueError(f"unsupported five-session metric: {metric}")


def compute_baseline_factor_points(
    institutional: InstitutionalResearchInput,
    definition: BaselineFactorDefinition,
    *,
    factor_start_session: date,
    factor_end_session: date,
) -> tuple[FactorPoint, ...]:
    """Compute factors on the first session where each partition is usable."""

    rows_by_identity = {
        (row.market, row.symbol, row.session_date): row for row in institutional.rows
    }
    rows_by_partition: dict[str, list[InstitutionalFlowDaily]] = defaultdict(list)
    for row in institutional.rows:
        rows_by_partition[row.partition_id].append(row)

    manifests_by_market: dict[InstitutionalMarket, list[tuple[date, date, str]]] = (
        defaultdict(list)
    )
    for manifest in institutional.manifests:
        manifests_by_market[manifest.market].append(
            (
                manifest.session_date,
                manifest.usable_from_session,
                manifest.partition_id,
            )
        )

    points: list[FactorPoint] = []
    for market in sorted(manifests_by_market, key=lambda item: item.value):
        manifests = sorted(manifests_by_market[market])
        source_calendar = tuple(item[0] for item in manifests)
        for source_index, (_, target_session, partition_id) in enumerate(manifests):
            if not factor_start_session <= target_session <= factor_end_session:
                continue
            start_index = max(0, source_index - definition.lookback_sessions + 1)
            expected_source_sessions = source_calendar[start_index : source_index + 1]
            available_source_sessions = frozenset(
                source_session
                for source_session, usable_from_session, _ in manifests[
                    : source_index + 1
                ]
                if usable_from_session <= target_session
            )
            usable_source_sessions = tuple(
                session
                for session in expected_source_sessions
                if session in available_source_sessions
            )
            partition_rows = sorted(
                rows_by_partition[partition_id],
                key=lambda row: row.symbol,
            )
            for row in partition_rows:
                for component in definition.components:
                    _, _, net_shares = _component_values(row, component)
                    points.append(
                        FactorPoint(
                            session_date=target_session,
                            market=EquityMarket(row.market.value),
                            symbol=row.symbol,
                            component=component,
                            metric=FactorMetric.NET_SHARES_1D,
                            value=Decimal(net_shares),
                            observed_sessions=1,
                            expected_sessions=1,
                        )
                    )
                    values = _five_session_values(
                        rows_by_identity=rows_by_identity,
                        market=market,
                        symbol=row.symbol,
                        source_sessions=usable_source_sessions,
                        component=component,
                    )
                    complete = (
                        len(expected_source_sessions) == (definition.lookback_sessions)
                        and len(values) == definition.lookback_sessions
                    )
                    for metric in definition.metrics:
                        if metric is FactorMetric.NET_SHARES_1D:
                            continue
                        points.append(
                            FactorPoint(
                                session_date=target_session,
                                market=EquityMarket(row.market.value),
                                symbol=row.symbol,
                                component=component,
                                metric=metric,
                                value=_five_session_metric(
                                    metric,
                                    values,
                                    complete=complete,
                                ),
                                observed_sessions=len(values),
                                expected_sessions=definition.lookback_sessions,
                            )
                        )
    return tuple(
        sorted(
            points,
            key=lambda point: (
                point.session_date,
                point.market.value,
                point.symbol,
                point.component.value,
                point.metric.value,
            ),
        )
    )
