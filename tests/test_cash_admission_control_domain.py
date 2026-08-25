from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
from backtest.domain import BacktestRunConfig, HistoricalBar, RunStatus, StrategySetSnapshot
from backtest.research_control import (
    CashAdmissionControlNotAccepted,
    CashAdmissionControlIntegrityError,
    CashAdmissionPreflightCatalog,
    build_cash_admission_postflight,
    build_cash_admission_preflight,
    build_research_control_snapshot,
    cash_admission_projection_digest,
    compute_cash_admission_preflight_statistics,
    derive_cash_admission_sizing,
    entry_signal_multiplicity_digest,
    recompute_backtest_result_digest,
    verify_cash_admission_postflight,
    verify_cash_admission_preflight,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _identity() -> dict[str, object]:
    return {
        "baseline_run_id": "run-baseline",
        "baseline_config_digest": "1" * 64,
        "baseline_result_digest": "2" * 64,
        "dataset_id": "dataset-finmind",
        "dataset_digest": "3" * 64,
        "dataset_manifest_digest": "4" * 64,
        "dataset_bars_sha256": "5" * 64,
        "dataset_binding_revision": 1,
        "strategy_set_snapshot_digest": "6" * 64,
        "atomic_strategy_run_snapshot_digest": "7" * 64,
        "dataset_amount_contract_digest": "8" * 64,
        "engine_version": "backtest-engine-v2",
        "commission_rate": "0.001425",
        "sell_tax_rate": "0.003",
        "slippage_bps": "5",
        "min_lot_shares": 1000,
    }


def _preflight(**statistics: int) -> dict[str, object]:
    values = {
        "s_max": 182,
        "candidate_order_count": 2,
        "matched_next_bar_count": 2,
        "missing_next_bar_count": 0,
        "baseline_signal_multiplicity_digest": entry_signal_multiplicity_digest(
            _orders()
        ),
    }
    values.update(statistics)
    return build_cash_admission_preflight(
        identity=_identity(),
        p_max="2850",
        **values,
    )


def _orders() -> list[dict[str, object]]:
    return [
        {
            "order_id": f"order-{index}",
            "symbol": symbol,
            "side": "ENTRY",
            "status": "FILLED",
            "created_at": "2026-08-21T09:01:00+08:00",
            "primary_strategy_id": "version-vwap",
            "triggered_strategy_ids": ["version-vwap"],
        }
        for index, symbol in enumerate(("2317", "2330"), start=1)
    ]


def _fills() -> list[dict[str, object]]:
    return [
        {"fill_id": "fill-1", "side": "ENTRY"},
        {"fill_id": "fill-2", "side": "ENTRY"},
    ]


def test_deterministic_sizing_uses_frozen_decimal_rounding() -> None:
    sizing = derive_cash_admission_sizing(
        s_max=182,
        p_max="2850",
        min_lot_shares=1000,
        slippage_bps="5",
        commission_rate="0.001425",
    )

    assert sizing.position_fraction.as_tuple().exponent == -12
    assert sizing.starting_cash == sizing.starting_cash.to_integral_value()
    assert sizing.starting_cash * sizing.position_fraction >= Decimal("2850000")
    assert sizing.maximum_session_allocation_ratio <= Decimal("0.80")
    assert (
        derive_cash_admission_sizing(
            s_max=182,
            p_max="2850",
            min_lot_shares=1000,
            slippage_bps="5",
            commission_rate="0.001425",
        )
        == sizing
    )


def test_preflight_is_strict_and_rebuildable() -> None:
    preflight = _preflight()
    assert verify_cash_admission_preflight(preflight) == preflight

    tampered = deepcopy(preflight)
    tampered["sizing"]["starting_cash"] = "1"
    with pytest.raises(CashAdmissionControlIntegrityError):
        verify_cash_admission_preflight(tampered)

    unknown = deepcopy(preflight)
    unknown["locator"] = "/tmp/not-identity"
    with pytest.raises(CashAdmissionControlIntegrityError):
        verify_cash_admission_preflight(unknown)


def test_preflight_catalog_rejects_noncanonical_bytes(tmp_path) -> None:
    catalog = CashAdmissionPreflightCatalog(tmp_path)
    preflight = _preflight()
    path = catalog.save(preflight)
    assert catalog.load(preflight["artifact_digest"]) == preflight

    path.write_text(" " + path.read_text())
    with pytest.raises(CashAdmissionControlIntegrityError):
        catalog.load(preflight["artifact_digest"])


def test_research_control_snapshot_is_part_of_run_config_identity() -> None:
    preflight = _preflight()
    snapshot = build_research_control_snapshot(
        preflight=preflight,
        actor_id="local-researcher",
        change_note="frozen R5 control",
        created_at="2026-08-25T09:00:00+08:00",
    )
    config = BacktestRunConfig(
        dataset_id="dataset-finmind",
        dataset_digest="3" * 64,
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("version-vwap",),
            exit_strategy_ids=("exit-eod",),
        ),
        starting_cash=preflight["sizing"]["starting_cash"],
        position_fraction=preflight["sizing"]["position_fraction"],
        research_control_snapshot=snapshot,
    )

    rebuilt = BacktestRunConfig.from_dict(config.to_dict())
    assert rebuilt.config_digest == config.config_digest
    assert rebuilt.research_control_snapshot == snapshot


def test_postflight_accepts_exact_multiplicity_and_all_fills() -> None:
    postflight = build_cash_admission_postflight(
        baseline_orders=_orders(),
        control_result={"orders": _orders(), "fills": _fills()},
        preflight=_preflight(),
        control_run_id="run-control",
        control_config_digest="9" * 64,
        control_result_digest="a" * 64,
        identity_validation_digest="b" * 64,
    )

    assert postflight["verdict"] == "ACCEPTED"
    assert postflight["control_admission_projection_digest"] == (
        cash_admission_projection_digest(
            {"orders": _orders(), "fills": _fills()}
        )
    )
    assert verify_cash_admission_postflight(postflight) == postflight


def test_admission_projection_binds_order_status_and_actual_fills() -> None:
    accepted = {"orders": _orders(), "fills": _fills()}
    tampered = deepcopy(accepted)
    tampered["orders"][0]["status"] = "REJECTED"
    tampered["fills"] = []

    assert cash_admission_projection_digest(tampered) != (
        cash_admission_projection_digest(accepted)
    )


def test_accepted_result_read_rejects_order_status_and_fill_tamper() -> None:
    result: dict[str, object] = {
        "orders": _orders(),
        "fills": _fills(),
        "trades": [],
        "daily_equity": [],
        "decisions": [],
        "summary": {"verdict": "INSUFFICIENT_EVIDENCE"},
    }
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    postflight = build_cash_admission_postflight(
        baseline_orders=_orders(),
        control_result=result,
        preflight=_preflight(),
        control_run_id="run-control",
        control_config_digest="9" * 64,
        control_result_digest=result["summary"]["result_digest"],
        identity_validation_digest="b" * 64,
    )
    tampered = deepcopy(result)
    tampered["orders"][0]["status"] = "REJECTED"
    tampered["fills"] = []

    class _Repository:
        def get_run(self, run_id: str):
            return {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "result_digest": result["summary"]["result_digest"],
                "config": {"research_control_snapshot": {"sealed": True}},
            }

        def get_cash_admission_control(self, run_id: str):
            return {"status": "ACCEPTED", "postflight": postflight}

        def get_result(self, run_id: str):
            return tampered

    service = object.__new__(BacktestApplicationService)
    service._repository = _Repository()

    with pytest.raises(CashAdmissionControlNotAccepted, match="integrity conflict"):
        service._verified_result("run-control")


def test_postflight_fails_closed_for_nonfilled_or_multiplicity_drift() -> None:
    rejected_orders = _orders()
    rejected_orders[0]["status"] = "REJECTED"
    rejected_orders[0]["reason"] = "any localized message"
    rejected = build_cash_admission_postflight(
        baseline_orders=_orders(),
        control_result={"orders": rejected_orders, "fills": _fills()[1:]},
        preflight=_preflight(),
        control_run_id="run-control",
        control_config_digest="9" * 64,
        control_result_digest="a" * 64,
        identity_validation_digest="b" * 64,
    )
    assert rejected["verdict"] == "INVALID"
    assert rejected["diagnostics"]["non_filled_entry_order_count"] == 1

    duplicate = _orders() + [_orders()[0]]
    multiplicity_drift = build_cash_admission_postflight(
        baseline_orders=_orders(),
        control_result={"orders": duplicate, "fills": _fills() + [_fills()[0]]},
        preflight=_preflight(),
        control_run_id="run-control",
        control_config_digest="9" * 64,
        control_result_digest="a" * 64,
        identity_validation_digest="b" * 64,
    )
    assert multiplicity_drift["verdict"] == "INVALID"
    assert not multiplicity_drift["conditions"][
        "entry_signal_multiplicity_matches_baseline"
    ]


def test_postflight_never_accepts_incomplete_preflight() -> None:
    postflight = build_cash_admission_postflight(
        baseline_orders=_orders(),
        control_result={"orders": _orders(), "fills": _fills()},
        preflight=_preflight(
            matched_next_bar_count=1,
            missing_next_bar_count=1,
        ),
        control_run_id="run-control",
        control_config_digest="9" * 64,
        control_result_digest="a" * 64,
        identity_validation_digest="b" * 64,
    )
    assert postflight["verdict"] == "INVALID"
    assert not postflight["conditions"]["preflight_has_no_missing_next_bar"]


def test_preflight_statistics_stream_exact_same_session_next_bar() -> None:
    order = _orders()[0]
    bars = [
        HistoricalBar(
            symbol="2317",
            timestamp=datetime(2026, 8, 21, 9, minute, tzinfo=_TAIPEI),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=1,
        )
        for minute, price in ((1, 100), (2, 101))
    ]

    statistics = compute_cash_admission_preflight_statistics(
        baseline_orders=[order],
        bars=bars,
    )

    assert statistics.candidate_order_count == 1
    assert statistics.matched_next_bar_count == 1
    assert statistics.missing_next_bar_count == 0
    assert statistics.p_max == Decimal("101")
    assert statistics.s_max == 1


def test_preflight_statistics_accepts_single_pass_order_stream() -> None:
    orders = _orders()
    bars = [
        HistoricalBar(
            symbol=order["symbol"],
            timestamp=datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI),
            open=Decimal("101"),
            high=Decimal("101"),
            low=Decimal("101"),
            close=Decimal("101"),
            volume=1,
        )
        for order in orders
    ]

    statistics = compute_cash_admission_preflight_statistics(
        baseline_orders=(order for order in orders),
        bars=bars,
    )

    assert statistics.baseline_signal_multiplicity_digest == (
        entry_signal_multiplicity_digest(orders)
    )


def test_preflight_statistics_uses_next_observed_symbol_bar_across_session() -> None:
    order = _orders()[0]
    bars = [
        HistoricalBar(
            symbol="2330",
            timestamp=datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI),
            open=Decimal("900"),
            high=Decimal("900"),
            low=Decimal("900"),
            close=Decimal("900"),
            volume=1,
        ),
        HistoricalBar(
            symbol="2317",
            timestamp=datetime(2026, 8, 22, 9, 1, tzinfo=_TAIPEI),
            open=Decimal("102"),
            high=Decimal("102"),
            low=Decimal("102"),
            close=Decimal("102"),
            volume=1,
        ),
    ]

    statistics = compute_cash_admission_preflight_statistics(
        baseline_orders=[order],
        bars=bars,
    )

    assert statistics.matched_next_bar_count == 1
    assert statistics.missing_next_bar_count == 0
    assert statistics.p_max == Decimal("102")
