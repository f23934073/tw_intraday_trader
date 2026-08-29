"""Formal v3 risk-metric, evidence, and comparability tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from backtest.comparability import run_comparability_diff
from backtest.cost_policy_tw import build_cost_policy_snapshot
from backtest.domain import (
    BacktestRunConfig,
    FormalEvidence,
    StrategySetSnapshot,
    digest,
)
from backtest.engine import BacktestEngineResult, DailyEquityPoint
from backtest.execution_policy_tw import build_execution_policy_snapshot
from backtest.metrics import compare_runs, summarize_run


@dataclass(frozen=True)
class _Trade:
    value: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)


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


def _config(*, cost_bps: str = "5") -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="metrics-fixture",
        dataset_digest="metrics-fixture-digest",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("entry",), exit_strategy_ids=("exit",)
        ),
        starting_cash=Decimal("1000"),
        minimum_oos_trades=1,
        engine_version="backtest-engine-v3-tw",
        execution_policy_snapshot=build_execution_policy_snapshot(
            participation_calibration_digest="a" * 64
        ),
        cost_policy_snapshot=build_cost_policy_snapshot(
            slippage_bps=cost_bps, slippage_calibration_digest="b" * 64
        ),
        research_truth_snapshot=_truth_snapshot(),
    )


def _trade(day: int, net_pnl: float) -> _Trade:
    timestamp = f"2026-01-{day:02d}T13:30:00+08:00"
    decision = {
        "primary_strategy_id": "entry" if net_pnl > 0 else "exit",
        "triggered_strategy_ids": ["entry" if net_pnl > 0 else "exit"],
    }
    return _Trade(
        {
            "symbol": f"{day:04d}",
            "entry": {"filled_at": timestamp},
            "exit": {"filled_at": timestamp},
            "entry_decision": decision,
            "exit_decision": decision,
            "gross_pnl": net_pnl + 10,
            "net_pnl": net_pnl,
        }
    )


def _formal_evidence(*, active_dates: int = 2) -> dict[str, Any]:
    return FormalEvidence(
        active_dates=active_dates,
        coverage_eligible_count=2,
        coverage_evaluable_count=2,
        coverage_unavailable_count=0,
        coverage_ratio=Decimal("1"),
        coverage_minimum=Decimal("0.95"),
        execution_fallback_count=0,
        execution_locked_limit_count=0,
        execution_partial_fill_count=0,
        execution_residual_count=0,
        execution_auction_close_count=2,
        execution_overnight_breach_count=0,
        special_regime_denominator_count=0,
        special_regime_reason_counts={},
        capacity_before_cost_shares=1000,
        capacity_after_cost_shares=900,
    ).to_dict()


def _result(*, active_dates: int = 2) -> BacktestEngineResult:
    return BacktestEngineResult(
        trades=[_trade(2, 100.0), _trade(3, -50.0)],  # type: ignore[list-item]
        daily_equity=[
            DailyEquityPoint(date(2026, 1, 2), Decimal("1100"), Decimal("1100"), Decimal("0")),
            DailyEquityPoint(date(2026, 1, 3), Decimal("900"), Decimal("900"), Decimal("0")),
        ],
        formal_evidence=_formal_evidence(active_dates=active_dates),
    )


def test_public_summary_reconciles_pf_expectancy_drawdown_ci_dates_and_capacity() -> None:
    summary = summarize_run(config=_config(), result=_result(), dataset_research_eligible=True)

    assert summary["full"]["profit_factor"] == 2.0
    assert summary["full"]["expectancy"] == 25.0
    assert summary["full"]["active_dates"] == ["2026-01-02", "2026-01-03"]
    assert summary["full"]["active_date_count"] == 2
    assert summary["equity"]["max_drawdown"] == pytest.approx(200 / 1100)
    assert summary["full"]["win_rate_ci"][0] < 0.5
    assert summary["full"]["win_rate_ci"][1] > 0.5
    assert summary["risk"]["capacity_before_cost_shares"] == 1000
    assert summary["risk"]["capacity_after_cost_shares"] == 900
    assert summary["formal_evidence"] == _formal_evidence()


def test_formal_summary_fails_when_evidence_is_missing_or_not_reconciled() -> None:
    missing = _result()
    missing.formal_evidence = None
    with pytest.raises(ValueError, match="缺少 formal_evidence"):
        summarize_run(config=_config(), result=missing, dataset_research_eligible=True)

    with pytest.raises(ValueError, match="active_dates"):
        summarize_run(
            config=_config(),
            result=_result(active_dates=1),
            dataset_research_eligible=True,
        )


def test_v3_comparability_binds_all_three_verified_snapshots() -> None:
    baseline = _config().to_dict()
    changed = _config(cost_bps="6").to_dict()

    diff = run_comparability_diff(baseline, changed)
    assert [item["field"] for item in diff] == ["cost_policy_snapshot"]

    drifted = dict(baseline)
    drifted_execution = dict(drifted["execution_policy_snapshot"])
    drifted_execution["max_participation_rate"] = "1"
    drifted["execution_policy_snapshot"] = drifted_execution
    with pytest.raises(ValueError, match="snapshot_digest"):
        run_comparability_diff(drifted, baseline)


def test_compare_runs_requires_matching_verified_formal_result_evidence() -> None:
    config = _config()
    engine_result = _result()
    summary = summarize_run(config=config, result=engine_result, dataset_research_eligible=True)
    stored = {**engine_result.to_dict(), "summary": summary}
    run = {"run_id": "run-a", "config": config.to_dict()}

    comparison = compare_runs(
        baseline_run=run,
        challenger_run={**run, "run_id": "run-b"},
        baseline_result=stored,
        challenger_result=stored,
    )
    assert comparison["comparable"] is True

    drifted = {**stored, "formal_evidence": dict(stored["formal_evidence"])}
    drifted["formal_evidence"]["active_dates"] = 3
    with pytest.raises(ValueError, match="copies do not match"):
        compare_runs(
            baseline_run=run,
            challenger_run={**run, "run_id": "run-b"},
            baseline_result=drifted,
            challenger_result=stored,
        )
