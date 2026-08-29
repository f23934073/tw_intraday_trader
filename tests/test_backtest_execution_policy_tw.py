"""Formal Taiwan execution-policy and engine behavior tests."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.cost_policy_tw import build_cost_policy_snapshot
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySetSnapshot, digest
from backtest.engine import HistoricalBacktestEngine
from backtest.execution_policy_tw import (
    adverse_tick_price,
    available_shares,
    build_execution_policy_snapshot,
    execution_policy_readiness_reason,
    formal_bar_reason,
    is_on_tick,
    locked_limit_reason,
    tick_size,
    verify_execution_policy_snapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")
FIXTURE_ROOT = Path("tests/fixtures/backtest/tw_execution_v1")


def _truth_snapshot() -> dict[str, object]:
    body: dict[str, object] = {
        "contract_version": "tw-research-truth-v1",
        "status": "VERIFIED",
        "closing_auction_event_contract": {
            "status": "VERIFIED",
            "price_semantics": "AUCTION_ONLY",
            "volume_semantics": "AUCTION_ONLY",
        },
    }
    return {**body, "snapshot_digest": digest(body)}


def _config(*, participation_digest: str | None = "a" * 64) -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="formal-fixture",
        dataset_digest="formal-fixture-digest",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
            priority_order=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
        engine_version="backtest-engine-v3-tw",
        minimum_oos_trades=1,
        execution_policy_snapshot=build_execution_policy_snapshot(
            participation_calibration_digest=participation_digest
        ),
        cost_policy_snapshot=build_cost_policy_snapshot(
            slippage_bps="5", slippage_calibration_digest="b" * 64
        ),
        research_truth_snapshot=_truth_snapshot(),
    )


def _bar(
    day: int,
    hour: int,
    minute: int,
    opened: int,
    high: int,
    low: int,
    close: int,
    *,
    volume: int = 1_000_000,
    phase: str = "CONTINUOUS",
    regime: str = "REGULAR",
) -> HistoricalBar:
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(2026, 1, day, hour, minute, tzinfo=TAIPEI),
        open=Decimal(opened),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        market_phase=phase,
        session_regime=regime,
        reference_price=Decimal("100"),
        lower_limit_price=Decimal("90"),
        upper_limit_price=Decimal("110"),
    )


def _bars(*, fill_volume: int = 1_000_000, fill_regime: str = "REGULAR") -> list[HistoricalBar]:
    return [
        _bar(2, 13, 25, 100, 101, 99, 100),
        _bar(3, 9, 0, 103, 104, 102, 104),
        _bar(3, 9, 1, 104, 106, 103, 105),
        _bar(
            3,
            9,
            2,
            105,
            109,
            104,
            108,
            volume=fill_volume,
            regime=fill_regime,
        ),
        _bar(3, 13, 29, 108, 109, 107, 108),
        _bar(3, 13, 30, 108, 108, 108, 108, phase="CLOSING_AUCTION"),
    ]


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        ("9.99", "0.01"),
        ("10", "0.05"),
        ("50", "0.1"),
        ("100", "0.5"),
        ("500", "1"),
        ("1000", "5"),
    ],
)
def test_six_tick_bands(price: str, expected: str) -> None:
    assert tick_size(price) == Decimal(expected)
    assert is_on_tick(price)


def test_regular_fixture_snapshot_and_participation_are_deterministic() -> None:
    fixture = json.loads((FIXTURE_ROOT / "regular_session.json").read_text())
    bar = HistoricalBar.from_dict(fixture["bar"])
    snapshot = verify_execution_policy_snapshot(fixture["execution_policy_snapshot"])

    assert formal_bar_reason(bar) is None
    assert available_shares(bar, snapshot) == fixture["expected"]["maximum_participating_shares"]
    assert snapshot == build_execution_policy_snapshot(participation_calibration_digest="a" * 64)
    assert execution_policy_readiness_reason(snapshot) is None


def test_adverse_price_is_outward_tick_rounded_and_limit_bounded() -> None:
    assert adverse_tick_price(
        "100",
        side="ENTRY",
        slippage_bps="5",
        lower_limit_price="90",
        upper_limit_price="110",
    ) == Decimal("100.5")
    assert adverse_tick_price(
        "100",
        side="EXIT",
        slippage_bps="5",
        lower_limit_price="90",
        upper_limit_price="110",
    ) == Decimal("99.9")
    assert (
        adverse_tick_price(
            "110",
            side="ENTRY",
            slippage_bps="5",
            lower_limit_price="90",
            upper_limit_price="110",
        )
        is None
    )


def test_partial_fill_records_requested_filled_residual_and_no_fallback() -> None:
    result = HistoricalBacktestEngine().run(config=_config(), bars=_bars(fill_volume=20_000))

    entry = result.fills[0].to_dict()
    assert entry["requested_shares"] == 9000
    assert entry["filled_shares"] == 1000
    assert entry["residual_shares"] == 8000
    assert result.orders[0]["status"] == "PARTIALLY_FILLED"
    assert result.formal_evidence is not None
    assert result.formal_evidence["execution"] == {
        "fallback_count": 0,
        "locked_limit_count": 0,
        "partial_fill_count": 1,
        "residual_count": 1,
        "auction_close_count": 1,
        "overnight_breach_count": 0,
    }


def test_locked_limit_and_unknown_regime_are_unfilled_fail_closed() -> None:
    locked = _bars()
    locked[3] = _bar(3, 9, 2, 110, 110, 110, 110)
    locked_result = HistoricalBacktestEngine().run(config=_config(), bars=locked)

    assert locked_result.fills == []
    assert locked_result.orders[0]["status"] == "UNFILLED_LOCKED_LIMIT"
    assert locked_result.formal_evidence is not None
    assert locked_result.formal_evidence["execution"]["locked_limit_count"] == 1

    unknown_result = HistoricalBacktestEngine().run(
        config=_config(), bars=_bars(fill_regime="UNRECOGNISED")
    )
    assert unknown_result.fills == []
    assert unknown_result.orders[0]["status"] == "UNFILLED_FORMAL_EVIDENCE"
    assert unknown_result.formal_evidence is not None
    assert unknown_result.formal_evidence["special_regime"] == {
        "denominator_count": 1,
        "reason_counts": {"UNKNOWN_SESSION_REGIME": 1},
    }


def test_missing_participation_calibration_stops_before_any_fill() -> None:
    with pytest.raises(ValueError, match="MISSING_PARTICIPATION_CALIBRATION"):
        HistoricalBacktestEngine().run(config=_config(participation_digest=None), bars=_bars())


def test_locked_limit_policy_detects_only_side_specific_unavailable_liquidity() -> None:
    limit_up = _bar(3, 9, 2, 110, 110, 110, 110)
    limit_down = _bar(3, 9, 2, 90, 90, 90, 90)

    assert locked_limit_reason(limit_up, side="ENTRY") == "LOCKED_LIMIT_UP"
    assert locked_limit_reason(limit_up, side="EXIT") is None
    assert locked_limit_reason(limit_down, side="EXIT") == "LOCKED_LIMIT_DOWN"
