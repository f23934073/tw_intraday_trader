"""Exposure-keyed accounting for same-symbol Local Paper positions."""

from datetime import date
from decimal import Decimal

from market_data.provider import MockProvider
from simulation.execution_costs import ReferenceSource
from simulation.service import SimulationService
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)


def _exposure(
    *,
    owner_origin: str,
    owner_id: str,
    horizon: HoldingHorizon,
    entry_identity: str,
):
    return build_exposure_identity(
        account_scope_id="local-paper-main-v1",
        policy_family_id="no-overnight-equity-v1",
        owner_origin=owner_origin,
        owner_id=owner_id,
        holding_horizon=horizon,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity=entry_identity,
    )


def _submit_v2(
    service: SimulationService,
    *,
    exposure,
    side: str,
    key: str,
    target_exposure_id: str | None = None,
):
    strategy = exposure.owner_origin == "STRATEGY_AUTOMATED"
    return service.submit_order(
        symbol="3231",
        side=side,
        lots=1,
        limit_price=106 if side == "BUY" else 100,
        idempotency_key=key,
        origin=exposure.owner_origin,
        strategy_id=exposure.owner_id if strategy else None,
        strategy_version="strategy-v1" if strategy else None,
        exposure=exposure,
        position_action=(
            PositionAction.OPEN_LONG if side == "BUY" else PositionAction.CLOSE_LONG
        ),
        target_exposure_id=target_exposure_id,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="TEST_ORDER",
    )


def test_same_symbol_exposures_are_accounted_independently_and_aggregated() -> None:
    service = SimulationService(MockProvider(), starting_cash=500_000)
    long_term = _exposure(
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        horizon=HoldingHorizon.LONG_TERM,
        entry_identity="manual:long-term:3231",
    )
    intraday = _exposure(
        owner_origin="STRATEGY_AUTOMATED",
        owner_id="orb",
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="orb:2026-08-23:3231",
    )

    _submit_v2(service, exposure=long_term, side="BUY", key="long-buy")
    _submit_v2(service, exposure=intraday, side="BUY", key="intraday-buy")

    exposures = service.exposures()
    assert {item["exposure_id"] for item in exposures} == {
        long_term.exposure_id,
        intraday.exposure_id,
    }
    assert {item["holding_horizon"] for item in exposures} == {
        "LONG_TERM",
        "INTRADAY",
    }
    aggregate = service.positions()
    assert len(aggregate) == 1
    assert aggregate[0]["quantity"] == 2_000
    assert aggregate[0]["exposure_count"] == 2
    assert aggregate[0]["owner_origin"] == "MIXED"

    sold, _ = _submit_v2(
        service,
        exposure=intraday,
        side="SELL",
        key="intraday-sell",
        target_exposure_id=intraday.exposure_id,
    )

    assert sold["status"] == "FILLED"
    assert sold["target_exposure_id"] == intraday.exposure_id
    remaining = service.exposures()
    assert [item["exposure_id"] for item in remaining] == [long_term.exposure_id]
    assert service.positions()[0]["quantity"] == 1_000


def test_sell_without_target_rejects_ambiguous_same_owner_exposures() -> None:
    service = SimulationService(MockProvider(), starting_cash=500_000)
    first = _exposure(
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        horizon=HoldingHorizon.LONG_TERM,
        entry_identity="manual:first:3231",
    )
    second = _exposure(
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="manual:second:3231",
    )
    _submit_v2(service, exposure=first, side="BUY", key="first-buy")
    _submit_v2(service, exposure=second, side="BUY", key="second-buy")

    rejected, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=100,
        idempotency_key="ambiguous-sell",
    )

    assert rejected["status"] == "REJECTED"
    assert (
        rejected["reason"]
        == "同股票有多個符合歸屬的 exposure，賣出必須指定 target_exposure_id"
    )
    assert len(service.exposures()) == 2


def test_legacy_direct_calls_use_one_deterministic_unclassified_exposure() -> None:
    service = SimulationService(MockProvider(), starting_cash=300_000)

    bought, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106,
        idempotency_key="legacy-buy",
    )
    sold, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=100,
        idempotency_key="legacy-sell",
    )

    assert bought["exposure_identity"]["holding_horizon"] == "UNCLASSIFIED_LEGACY"
    assert sold["target_exposure_id"] == bought["exposure_identity"]["exposure_id"]
    assert sold["status"] == "FILLED"
    assert service.exposures() == []


def test_v2_sell_rejects_cross_symbol_target_without_accounting_mutation() -> None:
    service = SimulationService(MockProvider(), starting_cash=500_000)
    identity = _exposure(
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="manual:3231:cross-symbol-guard",
    )
    bought, _ = _submit_v2(
        service,
        exposure=identity,
        side="BUY",
        key="cross-symbol-buy",
    )
    cash_after_buy = service.session()["available_cash"]
    exposure_after_buy = service.exposures()[0]

    rejected, _ = service.submit_order(
        symbol="2330",
        side="SELL",
        quantity_shares=1_000,
        limit_price=980,
        idempotency_key="cross-symbol-sell",
        origin="MANUAL_WEB",
        exposure=identity,
        position_action=PositionAction.CLOSE_LONG,
        target_exposure_id=identity.exposure_id,
        execution_reason_category=ExecutionReasonCategory.OPERATIONAL_RISK,
        execution_reason_code="FORCED_FLATTEN",
    )

    assert bought["status"] == "FILLED"
    assert rejected["status"] == "REJECTED"
    assert "股票" in rejected["reason"]
    assert service.session()["available_cash"] == cash_after_buy
    assert service.exposures() == [exposure_after_buy]


def test_fill_rechecks_target_symbol_before_mutating_accounting() -> None:
    service = SimulationService(MockProvider(), starting_cash=500_000)
    identity = _exposure(
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="manual:3231:fill-fence",
    )
    _submit_v2(service, exposure=identity, side="BUY", key="fill-fence-buy")
    pending, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        quantity_shares=1_000,
        limit_price=200,
        idempotency_key="fill-fence-sell",
        origin="MANUAL_WEB",
        exposure=identity,
        position_action=PositionAction.CLOSE_LONG,
        target_exposure_id=identity.exposure_id,
        execution_reason_category=ExecutionReasonCategory.OPERATIONAL_RISK,
        execution_reason_code="FORCED_FLATTEN",
    )
    cash_before_fill = service.session()["available_cash"]
    exposure_before_fill = service.exposures()[0]

    with service._lock:
        internal_order = service._orders[pending["order_id"]]
        internal_order.symbol = "2330"
        execution = service._execution_decision(
            internal_order,
            Decimal("980"),
            ReferenceSource.SNAPSHOT_COMPATIBILITY,
        )
        assert execution is not None
        filled_quantity = service._fill(internal_order, execution)

    assert filled_quantity == 0
    assert service.orders()[0]["status"] == "REJECTED"
    assert service.session()["available_cash"] == cash_before_fill
    assert service.exposures() == [exposure_before_fill]
