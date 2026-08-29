from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backtest.comparability import run_comparability_diff
from backtest.cost_policy_tw import build_cost_policy_snapshot
from backtest.dataset import DatasetManifest
from backtest.domain import FormalEvidence, digest
from backtest.execution_policy_tw import build_execution_policy_snapshot
from backtest.metrics import compare_runs
from backtest.qualification import (
    EvaluationWindow,
    MultipleTestingRecord,
    QualificationPolicy,
    QualificationProtocol,
    build_qualification_evidence,
    experiment_family_id,
    research_baseline_identity_digest,
)
from backtest.research_truth import build_research_truth_snapshot


FORMAL_FIXTURE = Path("tests/fixtures/backtest/tw_research_truth_v1/pass_manifest.json")


def _window(label: str, oos_start: date, oos_end: date) -> EvaluationWindow:
    return EvaluationWindow(
        label=label,
        train_start=date(2025, 1, 1),
        train_end=date(2025, 6, 30),
        validation_start=date(2025, 7, 1),
        validation_end=date(2025, 9, 30),
        oos_start=oos_start,
        oos_end=oos_end,
    )


def _snapshot(set_id: str, version_id: str) -> dict:
    value = {
        "contract_version": "atomic-backtest-run-snapshot-v2",
        "strategy_set": {
            "strategy_set_version_id": set_id,
            "members": [{"strategy_version_id": version_id}],
        },
        "feature_adapter_identity": "backtest.completed-kbar-1m-feature-adapter-v1",
        "feature_requests": [
            {
                "strategy_version_id": version_id,
                "requests": [
                    {
                        "feature_id": "rolling_return_v1",
                        "parameters": {"window_minutes": 3},
                        "runtime_identity_digest": "runtime-feature-identity",
                    }
                ],
            }
        ],
    }
    value["snapshot_digest"] = digest(value)
    return value


def _run(run_id: str, set_id: str, version_id: str) -> dict:
    config = {
        "dataset_id": "dataset-1",
        "dataset_digest": "dataset-digest",
        "starting_cash": "10000000",
        "position_fraction": "0.10",
        "commission_rate": "0.001425",
        "sell_tax_rate": "0.003",
        "slippage_bps": "5",
        "min_lot_shares": 1000,
        "engine_version": "backtest-engine-v2",
        "strategy_set": {
            "entry_strategy_ids": [version_id],
            "exit_strategy_ids": ["end_of_day_exit_v1"],
            "entry_policy": "ANY",
            "exit_policy": "ANY",
            "entry_min_trigger_count": 1,
            "exit_min_trigger_count": 1,
        },
        "atomic_strategy_run_snapshot": _snapshot(set_id, version_id),
    }
    return {
        "run_id": run_id,
        "status": "COMPLETED",
        "config": config,
        "config_digest": digest(config),
        "result_digest": f"result-{run_id}",
    }


def _result(*, win: bool) -> dict:
    trades = []
    equity = []
    pnl = 100.0 if win else -100.0
    running = 10_000_000.0
    trade_dates = [
        *(date(2025, 10, 1) + timedelta(days=index) for index in range(10)),
        *(date(2025, 11, 1) + timedelta(days=index) for index in range(10)),
        *(date(2026, 1, 1) + timedelta(days=index) for index in range(30)),
    ]
    for index, session_date in enumerate(trade_dates, start=1):
        timestamp = f"{session_date.isoformat()}T13:25:00+08:00"
        trades.append(
            {
                "trade_id": f"trade-{index}",
                "symbol": "2330",
                "net_pnl": pnl,
                "gross_pnl": pnl,
                "exit": {"filled_at": timestamp},
            }
        )
    session_date = date(2025, 1, 1)
    while session_date <= date(2026, 3, 31):
        running += pnl if session_date in trade_dates else 0
        equity.append({"date": session_date.isoformat(), "equity": running})
        session_date += timedelta(days=1)
    return {"trades": trades, "daily_equity": equity, "summary": {}}


def _protocol() -> QualificationProtocol:
    research_baseline_digest = research_baseline_identity_digest(
        _run("run-baseline", "set-v1", "strategy-v1")["config"]
    )
    return QualificationProtocol(
        primary_window=_window("primary", date(2026, 1, 1), date(2026, 3, 31)),
        walk_forward_windows=(
            _window("fold-1", date(2025, 10, 1), date(2025, 10, 31)),
            _window("fold-2", date(2025, 11, 1), date(2025, 11, 30)),
        ),
        multiple_testing=MultipleTestingRecord(
            family_id=experiment_family_id(research_baseline_digest),
            hypothesis_id="vwap-v2-beats-v1",
            attempt_number=1,
            planned_attempts=20,
            baseline_run_id="run-baseline",
            research_baseline_digest=research_baseline_digest,
            attempted_run_ids=("run-challenger",),
            family_head_sequence=1,
            family_snapshot_digest="family-snapshot",
        ),
        policy=QualificationPolicy(),
    )


def _v3_window(label: str, oos_start: date, oos_end: date) -> EvaluationWindow:
    return EvaluationWindow(
        label=label,
        train_start=date(2023, 1, 1),
        train_end=date(2023, 6, 30),
        validation_start=date(2023, 7, 1),
        validation_end=date(2023, 9, 30),
        oos_start=oos_start,
        oos_end=oos_end,
    )


def _v3_run(run_id: str, strategy_id: str) -> dict:
    manifest = DatasetManifest.from_dict(json.loads(FORMAL_FIXTURE.read_text()))
    config = {
        "dataset_id": manifest.dataset_id,
        "dataset_digest": manifest.manifest_digest,
        "starting_cash": "10000000",
        "position_fraction": "0.10",
        "commission_rate": "0.001425",
        "sell_tax_rate": "0.003",
        "slippage_bps": "5",
        "min_lot_shares": 1000,
        "engine_version": "backtest-engine-v3-tw",
        "strategy_set": {
            "entry_strategy_ids": [strategy_id],
            "exit_strategy_ids": ["end_of_day_exit_v1"],
            "entry_policy": "ANY",
            "exit_policy": "ANY",
            "entry_min_trigger_count": 1,
            "exit_min_trigger_count": 1,
        },
        "execution_policy_snapshot": build_execution_policy_snapshot(
            participation_calibration_digest="a" * 64
        ),
        "cost_policy_snapshot": build_cost_policy_snapshot(
            slippage_bps="5", slippage_calibration_digest="b" * 64
        ),
        "research_truth_snapshot": build_research_truth_snapshot(manifest),
    }
    return {
        "run_id": run_id,
        "status": "COMPLETED",
        "config": config,
        "config_digest": digest(config),
        "result_digest": f"result-{run_id}",
    }


def _v3_result(*, win: bool, residual_count: int = 0) -> dict:
    trade_dates = [
        *(
            date(2025, month, 1) + timedelta(days=index)
            for month in range(1, 5)
            for index in range(20)
        ),
        *(date(2026, 1, 1) + timedelta(days=index) for index in range(120)),
    ]
    pnl = 100.0 if win else -100.0
    trades = [
        {
            "trade_id": f"formal-trade-{index}",
            "symbol": "2330",
            "net_pnl": pnl,
            "gross_pnl": pnl,
            "exit": {"filled_at": f"{session_date.isoformat()}T13:30:00+08:00"},
        }
        for index, session_date in enumerate(trade_dates, start=1)
    ]
    equity = []
    running = 10_000_000.0
    session_date = date(2023, 1, 1)
    while session_date <= date(2026, 7, 31):
        if session_date in trade_dates:
            running += pnl
        equity.append({"date": session_date.isoformat(), "equity": running})
        session_date += timedelta(days=1)
    formal = FormalEvidence(
        active_dates=len(trade_dates),
        coverage_eligible_count=1000,
        coverage_evaluable_count=1000,
        coverage_unavailable_count=0,
        coverage_ratio="1",
        coverage_minimum="0.95",
        execution_fallback_count=0,
        execution_locked_limit_count=0,
        execution_partial_fill_count=residual_count,
        execution_residual_count=residual_count,
        execution_auction_close_count=len(trade_dates),
        execution_overnight_breach_count=0,
        special_regime_denominator_count=0,
        special_regime_reason_counts={},
        capacity_before_cost_shares=1_000_000,
        capacity_after_cost_shares=900_000,
    ).to_dict()
    return {
        "trades": trades,
        "daily_equity": equity,
        "formal_evidence": formal,
        "summary": {"formal_evidence": formal},
    }


def _v3_protocol() -> QualificationProtocol:
    baseline = _v3_run("run-v3-baseline", "strategy-v3-baseline")
    baseline_digest = research_baseline_identity_digest(baseline["config"])
    return QualificationProtocol(
        primary_window=_v3_window("primary", date(2026, 1, 1), date(2026, 7, 31)),
        walk_forward_windows=tuple(
            _v3_window(
                f"fold-{month}",
                date(2025, month, 1),
                date(2025, month, 20),
            )
            for month in range(1, 5)
        ),
        multiple_testing=MultipleTestingRecord(
            family_id=experiment_family_id(baseline_digest),
            hypothesis_id="formal-v3-challenger",
            attempt_number=1,
            planned_attempts=20,
            baseline_run_id="run-v3-baseline",
            research_baseline_digest=baseline_digest,
            attempted_run_ids=("run-v3-challenger",),
            family_head_sequence=1,
            family_snapshot_digest="formal-family-snapshot",
        ),
    )


def test_qualification_records_fixed_oos_walk_forward_and_all_attempts() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_result(win=False),
        challenger_result=_result(win=True),
        attempted_runs=(challenger,),
        protocol=_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2025, 1, 1),
        dataset_end_date=date(2026, 3, 31),
    )

    assert evidence["verdict"] == "ELIGIBLE_FOR_PROMOTION_REVIEW"
    assert evidence["effect"] == "REVIEW_ONLY_NO_LIFECYCLE_MUTATION"
    assert evidence["primary_oos"]["window"]["oos_start"] == "2026-01-01"
    assert len(evidence["walk_forward"]["folds"]) == 2
    assert evidence["walk_forward"]["positive_fold_ratio"] == 1.0
    assert evidence["protocol"]["multiple_testing"]["adjusted_alpha"] == "0.0025"
    assert [item["run_id"] for item in evidence["attempted_runs"]] == [
        "run-baseline",
        "run-challenger",
    ]
    assert evidence["attempted_runs"][1]["strategy_version_ids"] == ["strategy-v2"]


def test_qualification_fails_closed_on_non_comparable_execution_settings() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    challenger["config"]["commission_rate"] = "0"

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_result(win=False),
        challenger_result=_result(win=True),
        attempted_runs=(challenger,),
        protocol=_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2025, 1, 1),
        dataset_end_date=date(2026, 3, 31),
    )

    assert evidence["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert evidence["config_diff"][0]["field"] == "commission_rate"


def test_primary_oos_drawdown_includes_the_last_pre_oos_equity_anchor() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    challenger_result = _result(win=True)
    next(point for point in challenger_result["daily_equity"] if point["date"] == "2025-12-31")[
        "equity"
    ] = 10_000_000.0
    next(point for point in challenger_result["daily_equity"] if point["date"] == "2026-01-01")[
        "equity"
    ] = 7_000_000.0

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_result(win=False),
        challenger_result=challenger_result,
        attempted_runs=(challenger,),
        protocol=_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2025, 1, 1),
        dataset_end_date=date(2026, 3, 31),
    )

    assert evidence["primary_oos"]["challenger"]["max_drawdown"] == pytest.approx(0.3)
    assert evidence["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "Primary OOS 最大回撤超過 guardrail" in evidence["reasons"]


def test_walk_forward_oos_windows_cannot_overlap() -> None:
    research_baseline_digest = research_baseline_identity_digest(
        _run("run-baseline", "set-v1", "strategy-v1")["config"]
    )
    with pytest.raises(ValueError, match="不可重疊"):
        QualificationProtocol(
            primary_window=_window("primary", date(2026, 1, 1), date(2026, 3, 31)),
            walk_forward_windows=(
                _window("fold-1", date(2025, 10, 1), date(2025, 10, 31)),
                _window("fold-2", date(2025, 10, 20), date(2025, 11, 30)),
            ),
            multiple_testing=MultipleTestingRecord(
                family_id=experiment_family_id(research_baseline_digest),
                hypothesis_id="hypothesis",
                attempt_number=1,
                planned_attempts=20,
                baseline_run_id="run-baseline",
                research_baseline_digest=research_baseline_digest,
                attempted_run_ids=("run-challenger",),
                family_head_sequence=1,
                family_snapshot_digest="family-snapshot",
            ),
        )


def test_walk_forward_oos_must_finish_before_primary_oos() -> None:
    research_baseline_digest = research_baseline_identity_digest(
        _run("run-baseline", "set-v1", "strategy-v1")["config"]
    )
    with pytest.raises(ValueError, match="Primary OOS"):
        QualificationProtocol(
            primary_window=_window("primary", date(2026, 1, 1), date(2026, 3, 31)),
            walk_forward_windows=(
                _window("fold-1", date(2026, 1, 1), date(2026, 1, 31)),
                _window("fold-2", date(2026, 2, 1), date(2026, 2, 28)),
            ),
            multiple_testing=MultipleTestingRecord(
                family_id=experiment_family_id(research_baseline_digest),
                hypothesis_id="overlap-must-fail",
                attempt_number=1,
                planned_attempts=20,
                baseline_run_id="run-baseline",
                research_baseline_digest=research_baseline_digest,
                attempted_run_ids=("run-challenger",),
                family_head_sequence=1,
                family_snapshot_digest="family-snapshot",
            ),
        )


def test_server_policy_cannot_be_weakened_by_a_request() -> None:
    with pytest.raises(ValueError, match="server floor 30"):
        QualificationPolicy(
            minimum_oos_trades=1,
            maximum_oos_drawdown="1",
            minimum_positive_fold_ratio="0",
            minimum_walk_forward_folds=0,
        )


def test_one_independent_oos_day_is_insufficient_for_cluster_bootstrap() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    baseline_result = _result(win=False)
    challenger_result = _result(win=True)
    for result in (baseline_result, challenger_result):
        for trade in result["trades"]:
            if trade["exit"]["filled_at"].startswith("2026-"):
                trade["exit"]["filled_at"] = "2026-01-02T13:25:00+08:00"

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=baseline_result,
        challenger_result=challenger_result,
        attempted_runs=(challenger,),
        protocol=_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2025, 1, 1),
        dataset_end_date=date(2026, 3, 31),
    )

    assert evidence["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert evidence["primary_oos"]["bootstrap"]["eligible"] is False
    assert "Primary daily-cluster bootstrap 獨立交易日不足" in evidence["reasons"]


def test_feature_adapter_identity_is_part_of_shared_comparability() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    snapshot = dict(challenger["config"]["atomic_strategy_run_snapshot"])
    snapshot["feature_adapter_identity"] = "tick-adapter-v2"
    snapshot.pop("snapshot_digest")
    snapshot["snapshot_digest"] = digest(snapshot)
    challenger["config"]["atomic_strategy_run_snapshot"] = snapshot

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_result(win=False),
        challenger_result=_result(win=True),
        attempted_runs=(challenger,),
        protocol=_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2025, 1, 1),
        dataset_end_date=date(2026, 3, 31),
    )

    assert evidence["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert evidence["config_diff"][0]["field"] == (
        "atomic_strategy_run_snapshot.feature_adapter_identity"
    )


def test_regular_compare_uses_the_same_atomic_comparability_contract() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    result = {
        "summary": {
            "oos": {
                "win_rate": 0.5,
                "closed_trades": 0,
                "net_pnl": 0,
                "profit_factor": None,
                "expectancy": 0,
            },
            "equity": {"max_drawdown": 0, "total_return": 0},
            "strategy_attribution": [],
        },
        "trades": [],
    }

    comparable = compare_runs(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=result,
        challenger_result=result,
    )
    assert comparable["comparable"] is True

    snapshot = dict(challenger["config"]["atomic_strategy_run_snapshot"])
    snapshot["feature_adapter_identity"] = "tick-adapter-v2"
    snapshot.pop("snapshot_digest")
    snapshot["snapshot_digest"] = digest(snapshot)
    challenger["config"]["atomic_strategy_run_snapshot"] = snapshot
    not_comparable = compare_runs(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=result,
        challenger_result=result,
    )
    assert not_comparable["comparable"] is False
    assert not_comparable["config_diff"][0]["field"] == (
        "atomic_strategy_run_snapshot.feature_adapter_identity"
    )


def test_dataset_amount_contract_digest_is_comparability_identity() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")["config"]
    challenger = _run("run-challenger", "set-v2", "strategy-v2")["config"]
    baseline["dataset_amount_contract"] = {
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "digest": "a" * 64,
    }
    challenger["dataset_amount_contract"] = {
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "digest": "b" * 64,
    }

    differences = run_comparability_diff(baseline, challenger)
    assert any(item["field"] == "dataset_amount_contract" for item in differences)


def test_research_windows_must_fit_the_dataset_manifest() -> None:
    baseline = _run("run-baseline", "set-v1", "strategy-v1")
    challenger = _run("run-challenger", "set-v2", "strategy-v2")
    with pytest.raises(ValueError, match="DatasetManifest"):
        build_qualification_evidence(
            baseline_run=baseline,
            challenger_run=challenger,
            baseline_result=_result(win=False),
            challenger_result=_result(win=True),
            attempted_runs=(challenger,),
            protocol=_protocol(),
            dataset_research_eligible=True,
            dataset_start_date=date(2025, 2, 1),
            dataset_end_date=date(2026, 3, 31),
        )


def test_formal_v3_qualification_passes_only_the_frozen_high_bar() -> None:
    baseline = _v3_run("run-v3-baseline", "strategy-v3-baseline")
    challenger = _v3_run("run-v3-challenger", "strategy-v3-challenger")

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_v3_result(win=False),
        challenger_result=_v3_result(win=True),
        attempted_runs=(challenger,),
        protocol=_v3_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2023, 1, 1),
        dataset_end_date=date(2026, 7, 31),
    )

    assert evidence["verdict"] == "ELIGIBLE_FOR_PROMOTION_REVIEW"
    assert evidence["formal_v3"]["policy"] == {
        "coverage_minimum": "0.95",
        "primary_minimum_active_dates": 120,
        "primary_minimum_calendar_days": 183,
        "minimum_oos_trades": 30,
        "minimum_profit_factor_exclusive": "1",
        "minimum_expectancy_exclusive": "0",
        "minimum_walk_forward_folds": 4,
        "fold_minimum_active_dates": 20,
        "minimum_positive_folds": 3,
        "minimum_positive_fold_ratio": "0.75",
        "maximum_drawdown": "0.20",
        "maximum_execution_fallback_count": 0,
        "maximum_execution_residual_count": 0,
        "maximum_execution_overnight_breach_count": 0,
        "maximum_special_regime_denominator_count": 0,
        "minimum_capacity_before_cost_shares_exclusive": 0,
        "minimum_capacity_after_cost_shares_exclusive": 0,
        "family_alpha": "0.05",
        "planned_attempts": 20,
        "multiple_testing_adjustment": "BONFERRONI",
    }
    assert evidence["walk_forward"]["positive_folds"] == 4
    assert evidence["effect"] == "REVIEW_ONLY_NO_LIFECYCLE_MUTATION"


def test_formal_v3_qualification_consumes_verified_summary_evidence_and_fails_residual() -> None:
    baseline = _v3_run("run-v3-baseline", "strategy-v3-baseline")
    challenger = _v3_run("run-v3-challenger", "strategy-v3-challenger")
    missing = _v3_result(win=True)
    missing["summary"] = {}

    with pytest.raises(ValueError, match="summary.formal_evidence"):
        build_qualification_evidence(
            baseline_run=baseline,
            challenger_run=challenger,
            baseline_result=_v3_result(win=False),
            challenger_result=missing,
            attempted_runs=(challenger,),
            protocol=_v3_protocol(),
            dataset_research_eligible=True,
            dataset_start_date=date(2023, 1, 1),
            dataset_end_date=date(2026, 7, 31),
        )

    evidence = build_qualification_evidence(
        baseline_run=baseline,
        challenger_run=challenger,
        baseline_result=_v3_result(win=False),
        challenger_result=_v3_result(win=True, residual_count=1),
        attempted_runs=(challenger,),
        protocol=_v3_protocol(),
        dataset_research_eligible=True,
        dataset_start_date=date(2023, 1, 1),
        dataset_end_date=date(2026, 7, 31),
    )

    assert evidence["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "Formal v3 challenger 存在 unresolved residual" in evidence["reasons"]
