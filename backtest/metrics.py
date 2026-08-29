"""Result metrics and baseline/challenger comparison projections."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from backtest.comparability import run_comparability_diff
from backtest.domain import (
    ENGINE_V3_TW,
    BacktestRunConfig,
    FormalEvidence,
    digest,
    formal_evidence_from_result,
)
from backtest.engine import BacktestEngineResult


def summarize_run(
    *,
    config: BacktestRunConfig,
    result: BacktestEngineResult,
    dataset_research_eligible: bool,
    dataset_issues: tuple[str, ...] = (),
) -> dict[str, Any]:
    trades = [trade.to_dict() for trade in result.trades]
    equity = [point.to_dict() for point in result.daily_equity]
    oos_start = _oos_start(equity)
    oos_trades = [
        trade
        for trade in trades
        if datetime.fromisoformat(trade["exit"]["filled_at"]).date() >= oos_start
    ]
    full = _trade_metrics(trades)
    oos = _trade_metrics(oos_trades)
    if config.engine_version == ENGINE_V3_TW:
        full = {**full, **_active_date_metrics(trades)}
        oos = {**oos, **_active_date_metrics(oos_trades)}
    equity_metrics = _equity_metrics(equity, config.starting_cash)
    attribution = _strategy_attribution(trades, result.strategy_counts)
    reasons: list[str] = []
    if not dataset_research_eligible:
        reasons.append("資料集尚非 date-effective 全市場 universe，不能標示正式研究通過")
    if result.unresolved_positions:
        reasons.append("存在資料結束時未平倉部位")
    if oos["closed_trades"] < config.minimum_oos_trades:
        reasons.append("OOS 已平倉交易樣本不足")
    if oos["expectancy"] <= 0:
        reasons.append("OOS expectancy 未大於 0")
    if oos["profit_factor"] is not None and oos["profit_factor"] <= 1:
        reasons.append("OOS Profit Factor 未大於 1")
    if equity_metrics["max_drawdown"] > float(config.max_drawdown_guardrail):
        reasons.append("最大回撤超過 guardrail")
    if oos["win_rate_ci"][0] < float(config.target_win_rate):
        reasons.append("OOS 勝率信賴區間下界未達 target")
    verdict = "RESEARCH_PASS" if not reasons else "INSUFFICIENT_EVIDENCE"
    summary = {
        "verdict": verdict,
        "reasons": reasons,
        "dataset_issues": list(dataset_issues),
        "full": full,
        "oos": {**oos, "start_date": oos_start.isoformat()},
        "equity": equity_metrics,
        "strategy_attribution": attribution,
        "unresolved_position_count": len(result.unresolved_positions),
    }
    digest_input: dict[str, Any] = {
        "summary": summary,
        "trades": trades,
        "equity": equity,
        "decisions": [decision.to_dict() for decision in result.decisions],
    }
    if config.engine_version == ENGINE_V3_TW:
        if result.formal_evidence is None:
            raise ValueError("backtest-engine-v3-tw 缺少 formal_evidence")
        formal_evidence = FormalEvidence.from_dict(result.formal_evidence).to_dict()
        if formal_evidence["active_dates"] != full["active_date_count"]:
            raise ValueError("formal_evidence active_dates 與 trades 不一致")
        summary["formal_evidence"] = formal_evidence
        summary["risk"] = {
            "profit_factor": oos["profit_factor"],
            "expectancy": oos["expectancy"],
            "max_drawdown": equity_metrics["max_drawdown"],
            "win_rate_ci": oos["win_rate_ci"],
            "active_dates": oos["active_dates"],
            "capacity_before_cost_shares": formal_evidence["capacity"]["before_cost_shares"],
            "capacity_after_cost_shares": formal_evidence["capacity"]["after_cost_shares"],
        }
        digest_input["formal_evidence"] = formal_evidence
    summary["result_digest"] = digest(digest_input)
    return summary


def compare_runs(
    *,
    baseline_run: Mapping[str, Any],
    challenger_run: Mapping[str, Any],
    baseline_result: Mapping[str, Any],
    challenger_result: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_config = dict(baseline_run["config"])
    challenger_config = dict(challenger_run["config"])
    if (
        baseline_config.get("engine_version") == ENGINE_V3_TW
        or challenger_config.get("engine_version") == ENGINE_V3_TW
    ):
        formal_evidence_from_result(baseline_result)
        formal_evidence_from_result(challenger_result)
    config_diff = run_comparability_diff(baseline_config, challenger_config)
    comparable = not config_diff
    baseline_summary = baseline_result["summary"]
    challenger_summary = challenger_result["summary"]
    metric_keys = ("win_rate", "closed_trades", "net_pnl", "profit_factor", "expectancy")
    deltas = {
        key: _metric_delta(challenger_summary["oos"][key], baseline_summary["oos"][key])
        for key in metric_keys
    }
    deltas["max_drawdown"] = (
        challenger_summary["equity"]["max_drawdown"] - baseline_summary["equity"]["max_drawdown"]
    )
    deltas["total_return"] = (
        challenger_summary["equity"]["total_return"] - baseline_summary["equity"]["total_return"]
    )
    delta_ci = _clustered_win_rate_delta_ci(
        baseline_result.get("trades", []),
        challenger_result.get("trades", []),
        seed=f"{baseline_run['run_id']}:{challenger_run['run_id']}",
    )
    trade_diff = _trade_diff(baseline_result.get("trades", []), challenger_result.get("trades", []))
    if not comparable:
        verdict = "NOT_COMPARABLE"
    elif delta_ci is None or delta_ci[0] <= 0:
        verdict = "NO_CLEAR_EVIDENCE"
    elif deltas["expectancy"] <= 0 or deltas["max_drawdown"] > 0:
        verdict = "NO_CLEAR_EVIDENCE"
    else:
        verdict = "LIKELY_IMPROVED"
    projection = {
        "baseline_run_id": baseline_run["run_id"],
        "challenger_run_id": challenger_run["run_id"],
        "comparable": comparable,
        "config_diff": config_diff,
        "verdict": verdict,
        "message": (
            "本次調整關聯差異，非因果保證。"
            if comparable
            else "資料、執行或資金設定不同，不能判定策略調整是否有效。"
        ),
        "deltas": deltas,
        "win_rate_delta_ci": delta_ci,
        "trade_diff": trade_diff,
        "baseline_strategy_attribution": baseline_summary.get("strategy_attribution", []),
        "challenger_strategy_attribution": challenger_summary.get("strategy_attribution", []),
    }
    projection["comparison_digest"] = digest(projection)
    return projection


def _trade_metrics(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    net = [float(trade["net_pnl"]) for trade in trades]
    wins = sum(value > 0 for value in net)
    gross_profit = sum(value for value in net if value > 0)
    gross_loss = abs(sum(value for value in net if value < 0))
    win_rate = wins / len(net) if net else 0.0
    return {
        "closed_trades": len(net),
        "wins": wins,
        "losses": sum(value < 0 for value in net),
        "breakeven": sum(value == 0 for value in net),
        "win_rate": win_rate,
        "win_rate_ci": _wilson_interval(wins, len(net)),
        "net_pnl": sum(net),
        "gross_pnl": sum(float(trade["gross_pnl"]) for trade in trades),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "profit_factor_display": "∞" if gross_loss == 0 and gross_profit > 0 else None,
        "expectancy": sum(net) / len(net) if net else 0.0,
        "average_win": gross_profit / wins if wins else 0.0,
        "average_loss": -gross_loss / sum(value < 0 for value in net) if gross_loss else 0.0,
    }


def _active_date_metrics(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    active_dates = sorted(
        {
            datetime.fromisoformat(str(trade["exit"]["filled_at"])).date().isoformat()
            for trade in trades
        }
    )
    return {"active_dates": active_dates, "active_date_count": len(active_dates)}


def _equity_metrics(equity: list[Mapping[str, Any]], starting_cash: Any) -> dict[str, Any]:
    initial = float(starting_cash)
    points = [float(point["equity"]) for point in equity]
    peak = initial
    max_drawdown = 0.0
    for value in points:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    final = points[-1] if points else initial
    return {
        "starting_cash": initial,
        "final_equity": final,
        "total_return": (final - initial) / initial if initial else 0.0,
        "max_drawdown": max_drawdown,
    }


def _strategy_attribution(
    trades: list[Mapping[str, Any]],
    counts: Mapping[str, Mapping[str, int]],
) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy_id, counter in counts.items():
        rows[(strategy_id, "EVALUATION")] = {
            "strategy_id": strategy_id,
            "role": "EVALUATION",
            **dict(counter),
            "primary_trades": 0,
            "primary_net_pnl": 0.0,
            "participated_in_trades": 0,
        }
    for trade in trades:
        for role, details in (("ENTRY", trade["entry_decision"]), ("EXIT", trade["exit_decision"])):
            primary = details["primary_strategy_id"]
            triggered = details["triggered_strategy_ids"]
            for strategy_id in triggered:
                row = rows.setdefault(
                    (strategy_id, role),
                    {
                        "strategy_id": strategy_id,
                        "role": role,
                        "evaluated": 0,
                        "triggered": 0,
                        "blocked": 0,
                        "insufficient_data": 0,
                        "primary_trades": 0,
                        "primary_net_pnl": 0.0,
                        "participated_in_trades": 0,
                    },
                )
                row["participated_in_trades"] += 1
                if strategy_id == primary:
                    row["primary_trades"] += 1
                    row["primary_net_pnl"] += float(trade["net_pnl"])
    return sorted(rows.values(), key=lambda item: (item["role"], item["strategy_id"]))


def _metric_delta(challenger: Any, baseline: Any) -> float | None:
    if challenger is None or baseline is None:
        return None
    return float(challenger) - float(baseline)


def _trade_diff(
    baseline: list[Mapping[str, Any]],
    challenger: list[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    def identity(trade: Mapping[str, Any]) -> tuple[str, str]:
        return trade["symbol"], trade["entry"]["filled_at"]

    baseline_by_key = {identity(item): item for item in baseline}
    challenger_by_key = {identity(item): item for item in challenger}
    shared = []
    for key in sorted(set(baseline_by_key) & set(challenger_by_key)):
        left, right = baseline_by_key[key], challenger_by_key[key]
        shared.append(
            {
                "symbol": key[0],
                "entry_at": key[1],
                "baseline_net_pnl": left["net_pnl"],
                "challenger_net_pnl": right["net_pnl"],
                "baseline_exit_strategy": left["exit_decision"]["primary_strategy_id"],
                "challenger_exit_strategy": right["exit_decision"]["primary_strategy_id"],
            }
        )
    return {
        "shared": shared,
        "baseline_only": [
            baseline_by_key[key] for key in sorted(set(baseline_by_key) - set(challenger_by_key))
        ],
        "challenger_only": [
            challenger_by_key[key] for key in sorted(set(challenger_by_key) - set(baseline_by_key))
        ],
    }


def _clustered_win_rate_delta_ci(
    baseline: list[Mapping[str, Any]],
    challenger: list[Mapping[str, Any]],
    *,
    seed: str,
    samples: int = 300,
) -> list[float] | None:
    left = _daily_outcomes(baseline)
    right = _daily_outcomes(challenger)
    if not left or not right:
        return None
    generator = random.Random(seed)
    left_days, right_days = sorted(left), sorted(right)
    deltas: list[float] = []
    for _ in range(samples):
        left_values = [
            outcome
            for day in (generator.choice(left_days) for _ in left_days)
            for outcome in left[day]
        ]
        right_values = [
            outcome
            for day in (generator.choice(right_days) for _ in right_days)
            for outcome in right[day]
        ]
        if left_values and right_values:
            deltas.append(
                sum(right_values) / len(right_values) - sum(left_values) / len(left_values)
            )
    if not deltas:
        return None
    deltas.sort()
    return [deltas[int((len(deltas) - 1) * 0.025)], deltas[int((len(deltas) - 1) * 0.975)]]


def _daily_outcomes(trades: list[Mapping[str, Any]]) -> dict[str, list[int]]:
    output: dict[str, list[int]] = defaultdict(list)
    for trade in trades:
        date_key = datetime.fromisoformat(trade["exit"]["filled_at"]).date().isoformat()
        output[date_key].append(1 if float(trade["net_pnl"]) > 0 else 0)
    return output


def _wilson_interval(wins: int, count: int) -> list[float]:
    if count == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = wins / count
    denominator = 1 + z * z / count
    centre = (proportion + z * z / (2 * count)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count))
        / denominator
    )
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def _oos_start(equity: list[Mapping[str, Any]]) -> date:
    if not equity:
        return date.today()
    final = date.fromisoformat(str(equity[-1]["date"]))
    return final - timedelta(days=365)
