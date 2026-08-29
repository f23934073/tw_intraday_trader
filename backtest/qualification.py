"""Deterministic, review-only qualification evidence for completed backtests.

This module does not run strategies and cannot change strategy lifecycle state.
It projects immutable Run results through an explicitly dated research protocol.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from backtest.comparability import (
    baseline_research_config_digest,
    run_comparability_diff,
    verified_atomic_snapshot,
)
from backtest.domain import ENGINE_V3_TW, decimal, digest, formal_evidence_from_result


SERVER_FAMILY_ALPHA = Decimal("0.05")
SERVER_FAMILY_PLANNED_ATTEMPTS = 20
V3_PRIMARY_MINIMUM_ACTIVE_DATES = 120
V3_PRIMARY_MINIMUM_CALENDAR_DAYS = 183
V3_MINIMUM_WALK_FORWARD_FOLDS = 4
V3_FOLD_MINIMUM_ACTIVE_DATES = 20
V3_MINIMUM_POSITIVE_FOLDS = 3
V3_MINIMUM_POSITIVE_FOLD_RATIO = Decimal("0.75")


def _formal_v3_policy() -> dict[str, Any]:
    return {
        "coverage_minimum": "0.95",
        "primary_minimum_active_dates": V3_PRIMARY_MINIMUM_ACTIVE_DATES,
        "primary_minimum_calendar_days": V3_PRIMARY_MINIMUM_CALENDAR_DAYS,
        "minimum_oos_trades": 30,
        "minimum_profit_factor_exclusive": "1",
        "minimum_expectancy_exclusive": "0",
        "maximum_drawdown": "0.20",
        "minimum_walk_forward_folds": V3_MINIMUM_WALK_FORWARD_FOLDS,
        "fold_minimum_active_dates": V3_FOLD_MINIMUM_ACTIVE_DATES,
        "minimum_positive_folds": V3_MINIMUM_POSITIVE_FOLDS,
        "minimum_positive_fold_ratio": str(V3_MINIMUM_POSITIVE_FOLD_RATIO),
        "maximum_execution_fallback_count": 0,
        "maximum_execution_residual_count": 0,
        "maximum_execution_overnight_breach_count": 0,
        "maximum_special_regime_denominator_count": 0,
        "minimum_capacity_before_cost_shares_exclusive": 0,
        "minimum_capacity_after_cost_shares_exclusive": 0,
        "family_alpha": str(SERVER_FAMILY_ALPHA),
        "planned_attempts": SERVER_FAMILY_PLANNED_ATTEMPTS,
        "multiple_testing_adjustment": "BONFERRONI",
    }


def experiment_family_id(research_baseline_digest: str) -> str:
    baseline_identity = research_baseline_digest.strip()
    if not baseline_identity:
        raise ValueError("experiment family research baseline digest 不可為空")
    return (
        "experiment-family-"
        + uuid5(
            NAMESPACE_URL,
            f"tw-intraday-trader:qualification-family:{baseline_identity}",
        ).hex
    )


def research_protocol_identity() -> dict[str, Any]:
    """Code-owned semantics that share one multiple-testing budget."""

    policy = QualificationPolicy()
    return {
        "contract_version": "backtest-research-protocol-identity-v1",
        "qualification_protocol_version": "backtest-qualification-protocol-v2",
        "qualification_evidence_version": "backtest-qualification-evidence-v2",
        "policy": policy.to_dict(),
        "policy_digest": digest(policy.to_dict()),
        "family_alpha": str(SERVER_FAMILY_ALPHA),
        "family_planned_attempts": SERVER_FAMILY_PLANNED_ATTEMPTS,
        "multiple_testing_adjustment": "BONFERRONI",
        "fold_oos_isolation": "STRICTLY_BEFORE_PRIMARY_OOS",
        "bootstrap_cluster_unit": "EXIT_SESSION_DATE",
    }


def research_baseline_identity_digest(config: Mapping[str, Any]) -> str:
    """Stable family owner shared by semantically equivalent Baseline Runs."""

    if config.get("engine_version") == ENGINE_V3_TW:
        # The formal engine supports ordinary Strategy Set Runs as well as Atomic
        # Runs.  Reuse the shared comparability verifier for the three frozen v3
        # seams, then retain the selected Baseline strategy in the family owner.
        run_comparability_diff(config, config)
        ignored = {
            "experiment_id",
            "baseline_run_id",
            "research_baseline_digest",
            "parent_run_id",
            "change_note",
            "target_win_rate",
            "minimum_oos_trades",
            "max_drawdown_guardrail",
            "atomic_run_request",
            "atomic_run_request_digest",
            "dataset_binding_snapshot",
        }
        baseline_config_digest = digest(
            {key: config.get(key) for key in sorted(set(config) - ignored)}
        )
        protocol_identity = {
            **research_protocol_identity(),
            "formal_v3_policy": _formal_v3_policy(),
        }
    else:
        baseline_config_digest = baseline_research_config_digest(config)
        protocol_identity = research_protocol_identity()
    return digest(
        {
            "baseline_research_config_digest": baseline_config_digest,
            "research_protocol_identity": protocol_identity,
        }
    )


def experiment_family_definition(
    *,
    canonical_baseline_run_id: str,
    research_baseline_digest: str,
    comparability_digest: str,
) -> dict[str, Any]:
    """Build the immutable, code-owned definition for one Baseline family."""

    policy = QualificationPolicy()
    value: dict[str, Any] = {
        "contract_version": "backtest-experiment-family-v2",
        "family_id": experiment_family_id(research_baseline_digest),
        "baseline_run_id": canonical_baseline_run_id,
        "research_baseline_digest": research_baseline_digest,
        "research_protocol_identity": research_protocol_identity(),
        "planned_attempts": SERVER_FAMILY_PLANNED_ATTEMPTS,
        "alpha": str(SERVER_FAMILY_ALPHA),
        "adjustment_method": "BONFERRONI",
        "policy": policy.to_dict(),
        "policy_digest": digest(policy.to_dict()),
        "comparability_digest": comparability_digest,
    }
    value["definition_digest"] = digest(value)
    return value


def verify_experiment_family_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Verify immutable definition plus the monotonic attempt projection."""

    value = dict(snapshot)
    stored_snapshot_digest = str(value.pop("family_snapshot_digest", ""))
    if not stored_snapshot_digest or digest(value) != stored_snapshot_digest:
        raise ValueError("Experiment family snapshot digest 不一致")
    expected = experiment_family_definition(
        canonical_baseline_run_id=str(value["baseline_run_id"]),
        research_baseline_digest=str(value["research_baseline_digest"]),
        comparability_digest=str(value["comparability_digest"]),
    )
    for field_name, expected_value in expected.items():
        if value.get(field_name) != expected_value:
            raise ValueError(f"Experiment family {field_name} integrity 不一致")
    attempts = [dict(item) for item in value.get("attempts", ())]
    sequences = [int(item["attempt_sequence"]) for item in attempts]
    head = int(value.get("head_sequence", -1))
    if sequences != list(range(1, head + 1)):
        raise ValueError("Experiment family attempt sequence 不連續")
    run_ids = [str(item["run_id"]) for item in attempts]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Experiment family attempted Run 重複")
    if head > SERVER_FAMILY_PLANNED_ATTEMPTS:
        raise ValueError("Experiment family attempts 超過 server ceiling")
    return dict(snapshot)


class QualificationVerdict(StrEnum):
    ELIGIBLE_FOR_PROMOTION_REVIEW = "ELIGIBLE_FOR_PROMOTION_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvaluationWindow:
    label: str
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    oos_start: date
    oos_end: date

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("evaluation window label 不可為空")
        if not (
            self.train_start
            <= self.train_end
            < self.validation_start
            <= self.validation_end
            < self.oos_start
            <= self.oos_end
        ):
            raise ValueError("研究區間必須依序且不重疊：train < validation < OOS")

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "oos_start": self.oos_start.isoformat(),
            "oos_end": self.oos_end.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvaluationWindow":
        return cls(
            label=str(value["label"]),
            train_start=_date(value["train_start"]),
            train_end=_date(value["train_end"]),
            validation_start=_date(value["validation_start"]),
            validation_end=_date(value["validation_end"]),
            oos_start=_date(value["oos_start"]),
            oos_end=_date(value["oos_end"]),
        )


@dataclass(frozen=True)
class MultipleTestingRecord:
    family_id: str
    hypothesis_id: str
    attempt_number: int
    planned_attempts: int
    baseline_run_id: str
    research_baseline_digest: str
    attempted_run_ids: tuple[str, ...]
    family_head_sequence: int
    family_snapshot_digest: str
    alpha: Decimal = SERVER_FAMILY_ALPHA
    adjustment_method: str = "BONFERRONI"

    def __post_init__(self) -> None:
        object.__setattr__(self, "alpha", decimal(self.alpha))
        attempted = tuple(str(item).strip() for item in self.attempted_run_ids)
        object.__setattr__(self, "attempted_run_ids", attempted)
        if not all(
            value.strip()
            for value in (
                self.family_id,
                self.hypothesis_id,
                self.baseline_run_id,
                self.research_baseline_digest,
                self.family_snapshot_digest,
            )
        ):
            raise ValueError("multiple-testing family identity 不可為空")
        if self.family_id != experiment_family_id(self.research_baseline_digest):
            raise ValueError("multiple-testing family_id 不是 server-derived identity")
        if self.adjustment_method != "BONFERRONI":
            raise ValueError("Phase 3 v1 只支援 BONFERRONI")
        if self.planned_attempts != SERVER_FAMILY_PLANNED_ATTEMPTS:
            raise ValueError("planned_attempts 必須使用 server-owned policy")
        if self.alpha != SERVER_FAMILY_ALPHA:
            raise ValueError("alpha 必須使用 server-owned policy")
        if not 1 <= self.attempt_number <= self.planned_attempts:
            raise ValueError("attempt_number 必須介於 1 與 planned_attempts")
        if self.family_head_sequence != len(attempted):
            raise ValueError("family head sequence 與 attempted Run history 不一致")
        if self.attempt_number > self.family_head_sequence:
            raise ValueError("attempt_number 不可超過 family head sequence")
        if len(attempted) < 1 or len(set(attempted)) != len(attempted):
            raise ValueError("attempted_run_ids 至少要有一個且不可重複")
        if len(attempted) > 200:
            raise ValueError("attempted_run_ids 最多 200 個")
        if self.planned_attempts < len(attempted):
            raise ValueError("planned_attempts 不可小於已記錄的 attempted runs")

    @property
    def adjusted_alpha(self) -> Decimal:
        return self.alpha / Decimal(self.planned_attempts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "hypothesis_id": self.hypothesis_id,
            "attempt_number": self.attempt_number,
            "planned_attempts": self.planned_attempts,
            "baseline_run_id": self.baseline_run_id,
            "research_baseline_digest": self.research_baseline_digest,
            "attempted_run_ids": list(self.attempted_run_ids),
            "family_head_sequence": self.family_head_sequence,
            "family_snapshot_digest": self.family_snapshot_digest,
            "alpha": str(self.alpha),
            "adjustment_method": self.adjustment_method,
            "adjusted_alpha": str(self.adjusted_alpha),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MultipleTestingRecord":
        return cls(
            family_id=str(value["family_id"]),
            hypothesis_id=str(value["hypothesis_id"]),
            attempt_number=int(value["attempt_number"]),
            planned_attempts=int(value["planned_attempts"]),
            baseline_run_id=str(value["baseline_run_id"]),
            research_baseline_digest=str(value["research_baseline_digest"]),
            attempted_run_ids=tuple(str(item) for item in value["attempted_run_ids"]),
            family_head_sequence=int(value["family_head_sequence"]),
            family_snapshot_digest=str(value["family_snapshot_digest"]),
            alpha=decimal(value.get("alpha", "0.05")),
            adjustment_method=str(value.get("adjustment_method", "BONFERRONI")),
        )


@dataclass(frozen=True)
class QualificationPolicy:
    minimum_oos_trades: int = 30
    maximum_oos_drawdown: Decimal = Decimal("0.20")
    minimum_positive_fold_ratio: Decimal = Decimal("0.60")
    minimum_walk_forward_folds: int = 2
    minimum_oos_independent_days: int = 10
    minimum_fold_oos_trades: int = 5
    minimum_fold_independent_days: int = 3
    minimum_train_calendar_days: int = 60
    minimum_validation_calendar_days: int = 20
    minimum_oos_calendar_days: int = 20
    minimum_train_observed_sessions: int = 20
    minimum_validation_observed_sessions: int = 10
    policy_version: str = "qualification-policy-v2"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_oos_drawdown",
            decimal(self.maximum_oos_drawdown),
        )
        object.__setattr__(
            self,
            "minimum_positive_fold_ratio",
            decimal(self.minimum_positive_fold_ratio),
        )
        if self.policy_version != "qualification-policy-v2":
            raise ValueError("不支援的 qualification policy version")
        if self.minimum_oos_trades < 30:
            raise ValueError("minimum_oos_trades 不可低於 server floor 30")
        if not Decimal("0") <= self.maximum_oos_drawdown <= Decimal("0.20"):
            raise ValueError("maximum_oos_drawdown 不可高於 server ceiling 0.20")
        if not Decimal("0.60") <= self.minimum_positive_fold_ratio <= Decimal("1"):
            raise ValueError("minimum_positive_fold_ratio 不可低於 server floor 0.60")
        if self.minimum_walk_forward_folds < 2:
            raise ValueError("minimum_walk_forward_folds 不可低於 server floor 2")
        if self.minimum_oos_independent_days < 10:
            raise ValueError("minimum_oos_independent_days 不可低於 server floor 10")
        if self.minimum_fold_oos_trades < 5:
            raise ValueError("minimum_fold_oos_trades 不可低於 server floor 5")
        if self.minimum_fold_independent_days < 3:
            raise ValueError("minimum_fold_independent_days 不可低於 server floor 3")
        if self.minimum_train_calendar_days < 60:
            raise ValueError("minimum_train_calendar_days 不可低於 server floor 60")
        if self.minimum_validation_calendar_days < 20:
            raise ValueError("minimum_validation_calendar_days 不可低於 server floor 20")
        if self.minimum_oos_calendar_days < 20:
            raise ValueError("minimum_oos_calendar_days 不可低於 server floor 20")
        if self.minimum_train_observed_sessions < 20:
            raise ValueError("minimum_train_observed_sessions 不可低於 server floor 20")
        if self.minimum_validation_observed_sessions < 10:
            raise ValueError("minimum_validation_observed_sessions 不可低於 server floor 10")

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_oos_trades": self.minimum_oos_trades,
            "maximum_oos_drawdown": str(self.maximum_oos_drawdown),
            "minimum_positive_fold_ratio": str(self.minimum_positive_fold_ratio),
            "minimum_walk_forward_folds": self.minimum_walk_forward_folds,
            "minimum_oos_independent_days": self.minimum_oos_independent_days,
            "minimum_fold_oos_trades": self.minimum_fold_oos_trades,
            "minimum_fold_independent_days": self.minimum_fold_independent_days,
            "minimum_train_calendar_days": self.minimum_train_calendar_days,
            "minimum_validation_calendar_days": self.minimum_validation_calendar_days,
            "minimum_oos_calendar_days": self.minimum_oos_calendar_days,
            "minimum_train_observed_sessions": self.minimum_train_observed_sessions,
            "minimum_validation_observed_sessions": (self.minimum_validation_observed_sessions),
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QualificationPolicy":
        return cls(
            minimum_oos_trades=int(value.get("minimum_oos_trades", 30)),
            maximum_oos_drawdown=decimal(value.get("maximum_oos_drawdown", "0.20")),
            minimum_positive_fold_ratio=decimal(value.get("minimum_positive_fold_ratio", "0.60")),
            minimum_walk_forward_folds=int(value.get("minimum_walk_forward_folds", 2)),
            minimum_oos_independent_days=int(value.get("minimum_oos_independent_days", 10)),
            minimum_fold_oos_trades=int(value.get("minimum_fold_oos_trades", 5)),
            minimum_fold_independent_days=int(value.get("minimum_fold_independent_days", 3)),
            minimum_train_calendar_days=int(value.get("minimum_train_calendar_days", 60)),
            minimum_validation_calendar_days=int(value.get("minimum_validation_calendar_days", 20)),
            minimum_oos_calendar_days=int(value.get("minimum_oos_calendar_days", 20)),
            minimum_train_observed_sessions=int(value.get("minimum_train_observed_sessions", 20)),
            minimum_validation_observed_sessions=int(
                value.get("minimum_validation_observed_sessions", 10)
            ),
            policy_version=str(value.get("policy_version", "qualification-policy-v2")),
        )


@dataclass(frozen=True)
class QualificationProtocol:
    primary_window: EvaluationWindow
    multiple_testing: MultipleTestingRecord
    policy: QualificationPolicy = field(default_factory=QualificationPolicy)
    walk_forward_windows: tuple[EvaluationWindow, ...] = ()
    contract_version: str = "backtest-qualification-protocol-v2"

    def __post_init__(self) -> None:
        windows = tuple(self.walk_forward_windows)
        object.__setattr__(self, "walk_forward_windows", windows)
        if len(windows) > 50:
            raise ValueError("walk-forward windows 最多 50 個")
        labels = (self.primary_window.label,) + tuple(item.label for item in windows)
        if len(labels) != len(set(labels)):
            raise ValueError("evaluation window label 不可重複")
        ordered = sorted(windows, key=lambda item: item.oos_start)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.oos_end >= current.oos_start:
                raise ValueError("walk-forward OOS 區間不可重疊")
        for window in windows:
            if window.oos_end >= self.primary_window.oos_start:
                raise ValueError("walk-forward OOS 必須在 Primary OOS 開始前結束")
        for window in (self.primary_window, *windows):
            self._validate_window_duration(window)
        if self.contract_version != "backtest-qualification-protocol-v2":
            raise ValueError("不支援的 qualification protocol version")

    def _validate_window_duration(self, window: EvaluationWindow) -> None:
        policy = self.policy
        durations = {
            "train": (window.train_end - window.train_start).days + 1,
            "validation": (window.validation_end - window.validation_start).days + 1,
            "OOS": (window.oos_end - window.oos_start).days + 1,
        }
        minimums = {
            "train": policy.minimum_train_calendar_days,
            "validation": policy.minimum_validation_calendar_days,
            "OOS": policy.minimum_oos_calendar_days,
        }
        for label, duration in durations.items():
            if duration < minimums[label]:
                raise ValueError(f"{window.label} {label} 日曆範圍不足：至少 {minimums[label]} 日")

    @property
    def protocol_digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "primary_window": self.primary_window.to_dict(),
            "walk_forward_windows": [item.to_dict() for item in self.walk_forward_windows],
            "multiple_testing": self.multiple_testing.to_dict(),
            "policy": self.policy.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QualificationProtocol":
        return cls(
            contract_version=str(
                value.get(
                    "contract_version",
                    "backtest-qualification-protocol-v2",
                )
            ),
            primary_window=EvaluationWindow.from_dict(value["primary_window"]),
            walk_forward_windows=tuple(
                EvaluationWindow.from_dict(item) for item in value.get("walk_forward_windows", ())
            ),
            multiple_testing=MultipleTestingRecord.from_dict(value["multiple_testing"]),
            policy=QualificationPolicy.from_dict(value.get("policy", {})),
        )


def build_qualification_evidence(
    *,
    baseline_run: Mapping[str, Any],
    challenger_run: Mapping[str, Any],
    baseline_result: Mapping[str, Any],
    challenger_result: Mapping[str, Any],
    attempted_runs: Sequence[Mapping[str, Any]],
    protocol: QualificationProtocol,
    dataset_research_eligible: bool,
    dataset_start_date: date,
    dataset_end_date: date,
) -> dict[str, Any]:
    """Create a reproducible evidence projection without mutating any Run."""

    baseline_id = str(baseline_run["run_id"])
    challenger_id = str(challenger_run["run_id"])
    if baseline_id == challenger_id:
        raise ValueError("Baseline 與 Challenger 必須是不同 Run")
    attempted_by_id = {str(item["run_id"]): item for item in attempted_runs}
    recorded_ids = protocol.multiple_testing.attempted_run_ids
    if tuple(attempted_by_id) != recorded_ids:
        raise ValueError("attempted runs 與 multiple-testing record 不一致")
    if protocol.multiple_testing.baseline_run_id != baseline_id:
        raise ValueError("multiple-testing family Baseline 與 request 不一致")
    if challenger_id not in attempted_by_id:
        raise ValueError("multiple-testing history 必須包含 Challenger")
    _validate_dataset_windows(
        protocol,
        dataset_start_date=dataset_start_date,
        dataset_end_date=dataset_end_date,
    )

    reasons: list[str] = []
    baseline_v3 = baseline_run.get("config", {}).get("engine_version") == ENGINE_V3_TW
    challenger_v3 = challenger_run.get("config", {}).get("engine_version") == ENGINE_V3_TW
    formal_v3 = baseline_v3 or challenger_v3
    formal_evidence: dict[str, dict[str, Any]] = {}
    if formal_v3:
        if not (baseline_v3 and challenger_v3):
            raise ValueError("formal v3 qualification requires two v3-tw Runs")
        formal_evidence = {
            "baseline": formal_evidence_from_result(baseline_result),
            "challenger": formal_evidence_from_result(challenger_result),
        }
        for role, evidence in formal_evidence.items():
            reasons.extend(_formal_v3_reasons(role, evidence))
    comparable_diff = run_comparability_diff(baseline_run["config"], challenger_run["config"])
    if comparable_diff:
        reasons.append("Baseline 與 Challenger 的資料、資金、成本或執行設定不同")
    if not dataset_research_eligible:
        reasons.append("資料集不是 research eligible 的 date-effective universe")

    attempted_evidence = []
    history_by_id = {baseline_id: baseline_run, **attempted_by_id}
    for attempt_sequence, run_id in enumerate((baseline_id, *recorded_ids)):
        run = history_by_id[run_id]
        if str(run.get("status")) != "COMPLETED":
            reasons.append(f"attempted Run 尚未完成：{run_id}")
        try:
            snapshot = verified_atomic_snapshot(run["config"])
            if snapshot is None and not formal_v3:
                raise ValueError("不是 Atomic Run Snapshot v2")
        except ValueError as error:
            reasons.append(f"{run_id}：{error}")
            snapshot = None
        if run_comparability_diff(baseline_run["config"], run["config"]):
            reasons.append(f"attempted Run 不可比較：{run_id}")
        attempted_evidence.append(
            {
                "run_id": run_id,
                "status": run.get("status"),
                "history_role": "BASELINE" if attempt_sequence == 0 else "CHALLENGER",
                "attempt_sequence": attempt_sequence,
                "config_digest": run.get("config_digest"),
                "result_digest": run.get("result_digest"),
                "strategy_set_version_id": (
                    snapshot.get("strategy_set", {}).get("strategy_set_version_id")
                    if snapshot is not None
                    else None
                ),
                "strategy_version_ids": (
                    [
                        member["strategy_version_id"]
                        for member in snapshot.get("strategy_set", {}).get("members", [])
                    ]
                    if snapshot is not None
                    else []
                ),
                "feature_adapter_identity": (
                    snapshot.get("feature_adapter_identity") if snapshot is not None else None
                ),
                "feature_requests": (
                    snapshot.get("feature_requests", []) if snapshot is not None else []
                ),
            }
        )

    primary = _window_evidence(
        protocol.primary_window,
        baseline_id=baseline_id,
        challenger_id=challenger_id,
        baseline_result=baseline_result,
        challenger_result=challenger_result,
        adjusted_alpha=float(protocol.multiple_testing.adjusted_alpha),
        minimum_independent_days=protocol.policy.minimum_oos_independent_days,
    )
    policy = protocol.policy
    reasons.extend(_coverage_reasons("Primary", primary, policy, primary=True))
    challenger_primary = primary["challenger"]
    if challenger_primary["closed_trades"] < policy.minimum_oos_trades:
        reasons.append("Primary OOS 已平倉交易樣本不足")
    if challenger_primary["expectancy"] <= 0:
        reasons.append("Primary OOS expectancy 未大於 0")
    profit_factor = challenger_primary["profit_factor"]
    if profit_factor is not None and profit_factor <= 1:
        reasons.append("Primary OOS Profit Factor 未大於 1")
    if challenger_primary["max_drawdown"] > float(policy.maximum_oos_drawdown):
        reasons.append("Primary OOS 最大回撤超過 guardrail")
    confidence_interval = primary["win_rate_delta_ci"]
    if confidence_interval is None or confidence_interval[0] <= 0:
        reasons.append("Bonferroni 調整後勝率差信賴區間下界未大於 0")
    if formal_v3:
        primary_days = (
            protocol.primary_window.oos_end - protocol.primary_window.oos_start
        ).days + 1
        if primary_days < V3_PRIMARY_MINIMUM_CALENDAR_DAYS:
            reasons.append("Formal v3 Primary OOS 未覆蓋至少六個月")
        for role in ("baseline", "challenger"):
            if primary[role]["independent_days"] < V3_PRIMARY_MINIMUM_ACTIVE_DATES:
                reasons.append(f"Formal v3 Primary OOS {role} active dates 少於 120")

    folds = [
        _window_evidence(
            window,
            baseline_id=baseline_id,
            challenger_id=challenger_id,
            baseline_result=baseline_result,
            challenger_result=challenger_result,
            adjusted_alpha=float(protocol.multiple_testing.adjusted_alpha),
            minimum_independent_days=policy.minimum_fold_independent_days,
        )
        for window in protocol.walk_forward_windows
    ]
    for fold in folds:
        reasons.extend(
            _coverage_reasons(
                f"Walk-forward {fold['window']['label']}",
                fold,
                policy,
                primary=False,
            )
        )
    if len(folds) < policy.minimum_walk_forward_folds:
        reasons.append("walk-forward folds 數量不足")
    positive_folds = sum(
        item["challenger"]["expectancy"] > 0 and item["deltas"]["expectancy"] > 0 for item in folds
    )
    positive_ratio = positive_folds / len(folds) if folds else 0.0
    if positive_ratio < float(policy.minimum_positive_fold_ratio):
        reasons.append("walk-forward 正向 fold 比例未達門檻")
    if formal_v3:
        if len(folds) < V3_MINIMUM_WALK_FORWARD_FOLDS:
            reasons.append("Formal v3 walk-forward folds 少於 4")
        for fold in folds:
            label = fold["window"]["label"]
            for role in ("baseline", "challenger"):
                if fold[role]["independent_days"] < V3_FOLD_MINIMUM_ACTIVE_DATES:
                    reasons.append(f"Formal v3 Walk-forward {label} {role} active dates 少於 20")
        if (
            positive_folds < V3_MINIMUM_POSITIVE_FOLDS
            or Decimal(str(positive_ratio)) < V3_MINIMUM_POSITIVE_FOLD_RATIO
        ):
            reasons.append("Formal v3 walk-forward 至少需 3/4 正向")

    # Stable ordering is part of the stored evidence contract.
    reasons = list(dict.fromkeys(reasons))
    verdict = (
        QualificationVerdict.ELIGIBLE_FOR_PROMOTION_REVIEW
        if not reasons
        else QualificationVerdict.INSUFFICIENT_EVIDENCE
    )
    evidence: dict[str, Any] = {
        "contract_version": "backtest-qualification-evidence-v2",
        "verdict": verdict.value,
        "reasons": reasons,
        "effect": "REVIEW_ONLY_NO_LIFECYCLE_MUTATION",
        "baseline_run_id": baseline_id,
        "challenger_run_id": challenger_id,
        "protocol": protocol.to_dict(),
        "protocol_digest": protocol.protocol_digest,
        "config_diff": comparable_diff,
        "dataset_research_eligible": dataset_research_eligible,
        "dataset_coverage": {
            "start_date": dataset_start_date.isoformat(),
            "end_date": dataset_end_date.isoformat(),
        },
        "primary_oos": primary,
        "walk_forward": {
            "folds": folds,
            "positive_folds": positive_folds,
            "positive_fold_ratio": positive_ratio,
        },
        "attempted_runs": attempted_evidence,
    }
    if formal_v3:
        evidence["formal_v3"] = {
            "formal_evidence": formal_evidence,
            "policy": _formal_v3_policy(),
        }
    evidence["evidence_digest"] = digest(evidence)
    return evidence


def verify_qualification_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed if immutable qualification JSON or digests drift."""

    value = dict(record)
    protocol = QualificationProtocol.from_dict(value["protocol"])
    if protocol.protocol_digest != value["protocol_digest"]:
        raise ValueError("Qualification protocol digest 不一致")
    evidence = dict(value["evidence"])
    stored_evidence_digest = str(evidence.pop("evidence_digest", ""))
    if digest(evidence) != stored_evidence_digest:
        raise ValueError("Qualification evidence digest 不一致")
    if stored_evidence_digest != value["evidence_digest"]:
        raise ValueError("Qualification row/evidence digest 不一致")
    request_document = dict(value["request"])
    if digest(request_document) != value["request_digest"]:
        raise ValueError("Qualification request digest 不一致")
    if evidence.get("protocol_digest") != value["protocol_digest"]:
        raise ValueError("Qualification evidence/protocol digest 不一致")
    if evidence.get("protocol") != value["protocol"]:
        raise ValueError("Qualification evidence/protocol projection 不一致")
    if request_document.get("primary_window") != value["protocol"].get("primary_window"):
        raise ValueError("Qualification request/primary window projection 不一致")
    if request_document.get("walk_forward_windows") != value["protocol"].get(
        "walk_forward_windows"
    ):
        raise ValueError("Qualification request/walk-forward projection 不一致")
    for field_name in ("baseline_run_id", "challenger_run_id"):
        if (
            request_document.get(field_name) != value[field_name]
            or evidence.get(field_name) != value[field_name]
        ):
            raise ValueError(f"Qualification {field_name} projection 不一致")
    if evidence.get("verdict") != value["verdict"]:
        raise ValueError("Qualification verdict projection 不一致")
    if request_document.get("actor_id") != value["actor_id"]:
        raise ValueError("Qualification actor projection 不一致")
    if request_document.get("change_note") != value["change_note"]:
        raise ValueError("Qualification change note projection 不一致")
    multiple_testing = value["protocol"].get("multiple_testing", {})
    for field_name in (
        "family_id",
        "attempt_number",
        "family_head_sequence",
        "family_snapshot_digest",
    ):
        if value.get(field_name) != multiple_testing.get(field_name):
            raise ValueError(f"Qualification {field_name} projection 不一致")
    family_snapshot = value.get("family_snapshot")
    if not isinstance(family_snapshot, Mapping):
        raise ValueError("Qualification family snapshot body 遺失")
    verified_family = verify_experiment_family_snapshot(family_snapshot)
    if verified_family.get("family_id") != value.get("family_id"):
        raise ValueError("Qualification family snapshot identity 不一致")
    if verified_family.get("family_snapshot_digest") != value.get("family_snapshot_digest"):
        raise ValueError("Qualification family snapshot digest 不一致")
    if verified_family.get("research_baseline_digest") != multiple_testing.get(
        "research_baseline_digest"
    ):
        raise ValueError("Qualification research Baseline identity 不一致")
    return value


def _formal_v3_reasons(role: str, evidence: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    coverage = evidence["coverage"]
    execution = evidence["execution"]
    special = evidence["special_regime"]
    capacity = evidence["capacity"]
    if decimal(coverage["minimum"]) != Decimal("0.95"):
        reasons.append(f"Formal v3 {role} coverage minimum 不是 frozen 0.95")
    if decimal(coverage["ratio"]) < Decimal("0.95"):
        reasons.append(f"Formal v3 {role} coverage 低於 0.95")
    if execution["fallback_count"] != 0:
        reasons.append(f"Formal v3 {role} 存在 fallback execution")
    if execution["residual_count"] != 0:
        reasons.append(f"Formal v3 {role} 存在 unresolved residual")
    if execution["overnight_breach_count"] != 0:
        reasons.append(f"Formal v3 {role} 存在 OVERNIGHT_BREACH")
    if special["denominator_count"] != 0:
        reasons.append(f"Formal v3 {role} 存在 unsupported regime denominator")
    if capacity["before_cost_shares"] <= 0:
        reasons.append(f"Formal v3 {role} 缺少 pre-cost capacity")
    if capacity["after_cost_shares"] <= 0:
        reasons.append(f"Formal v3 {role} capacity 未能通過成本後門檻")
    return reasons


def _window_evidence(
    window: EvaluationWindow,
    *,
    baseline_id: str,
    challenger_id: str,
    baseline_result: Mapping[str, Any],
    challenger_result: Mapping[str, Any],
    adjusted_alpha: float,
    minimum_independent_days: int,
) -> dict[str, Any]:
    baseline_trades = _trades_in_window(baseline_result, window)
    challenger_trades = _trades_in_window(challenger_result, window)
    baseline = _interval_metrics(baseline_trades, baseline_result, window)
    challenger = _interval_metrics(challenger_trades, challenger_result, window)
    confidence_interval = _clustered_win_rate_delta_ci(
        baseline_trades,
        challenger_trades,
        seed=f"{baseline_id}:{challenger_id}:{window.label}",
        alpha=adjusted_alpha,
        minimum_independent_days=minimum_independent_days,
    )
    return {
        "window": window.to_dict(),
        "baseline": baseline,
        "challenger": challenger,
        "deltas": {
            "closed_trades": challenger["closed_trades"] - baseline["closed_trades"],
            "win_rate": challenger["win_rate"] - baseline["win_rate"],
            "net_pnl": challenger["net_pnl"] - baseline["net_pnl"],
            "expectancy": challenger["expectancy"] - baseline["expectancy"],
            "max_drawdown": challenger["max_drawdown"] - baseline["max_drawdown"],
        },
        "adjusted_alpha": adjusted_alpha,
        "win_rate_delta_ci": confidence_interval,
        "coverage": {
            "baseline": _segment_coverage(baseline_result, window),
            "challenger": _segment_coverage(challenger_result, window),
        },
        "bootstrap": {
            "cluster_unit": "EXIT_SESSION_DATE",
            "baseline_independent_days": baseline["independent_days"],
            "challenger_independent_days": challenger["independent_days"],
            "minimum_required": minimum_independent_days,
            "eligible": (
                baseline["independent_days"] >= minimum_independent_days
                and challenger["independent_days"] >= minimum_independent_days
            ),
        },
    }


def _trades_in_window(
    result: Mapping[str, Any], window: EvaluationWindow
) -> list[Mapping[str, Any]]:
    output = []
    for trade in result.get("trades", []):
        exit_date = datetime.fromisoformat(str(trade["exit"]["filled_at"])).date()
        if window.oos_start <= exit_date <= window.oos_end:
            output.append(trade)
    return output


def _interval_metrics(
    trades: Sequence[Mapping[str, Any]],
    result: Mapping[str, Any],
    window: EvaluationWindow,
) -> dict[str, Any]:
    net = [float(item["net_pnl"]) for item in trades]
    wins = sum(value > 0 for value in net)
    gross_profit = sum(value for value in net if value > 0)
    gross_loss = abs(sum(value for value in net if value < 0))
    all_equity = sorted(
        (
            (_date(point["date"]), float(point["equity"]))
            for point in result.get("daily_equity", [])
        ),
        key=lambda item: item[0],
    )
    prior = [value for session_date, value in all_equity if session_date < window.oos_start]
    equity = [
        value
        for session_date, value in all_equity
        if window.oos_start <= session_date <= window.oos_end
    ]
    peak = prior[-1] if prior else (equity[0] if equity else 0.0)
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            drawdown = max(drawdown, (peak - value) / peak)
    return {
        "closed_trades": len(net),
        "independent_days": len(_daily_outcomes(trades)),
        "wins": wins,
        "win_rate": wins / len(net) if net else 0.0,
        "net_pnl": sum(net),
        "expectancy": sum(net) / len(net) if net else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "max_drawdown": drawdown,
    }


def _clustered_win_rate_delta_ci(
    baseline: Sequence[Mapping[str, Any]],
    challenger: Sequence[Mapping[str, Any]],
    *,
    seed: str,
    alpha: float,
    minimum_independent_days: int,
    samples: int = 1000,
) -> list[float] | None:
    left = _daily_outcomes(baseline)
    right = _daily_outcomes(challenger)
    if len(left) < minimum_independent_days or len(right) < minimum_independent_days:
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
    lower = max(0, min(len(deltas) - 1, int((len(deltas) - 1) * alpha / 2)))
    upper = max(
        0,
        min(len(deltas) - 1, int((len(deltas) - 1) * (1 - alpha / 2))),
    )
    return [deltas[lower], deltas[upper]]


def _daily_outcomes(
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, list[int]]:
    output: dict[str, list[int]] = defaultdict(list)
    for trade in trades:
        key = datetime.fromisoformat(str(trade["exit"]["filled_at"])).date().isoformat()
        output[key].append(1 if float(trade["net_pnl"]) > 0 else 0)
    return output


def _validate_dataset_windows(
    protocol: QualificationProtocol,
    *,
    dataset_start_date: date,
    dataset_end_date: date,
) -> None:
    for window in (protocol.primary_window, *protocol.walk_forward_windows):
        if window.train_start < dataset_start_date or window.oos_end > dataset_end_date:
            raise ValueError(
                f"{window.label} 超出 DatasetManifest 範圍 "
                f"{dataset_start_date.isoformat()} 至 {dataset_end_date.isoformat()}"
            )


def _segment_coverage(result: Mapping[str, Any], window: EvaluationWindow) -> dict[str, int]:
    dates = {
        _date(point["date"])
        for point in result.get("daily_equity", ())
        if point.get("date") is not None
    }
    return {
        "train_sessions": sum(
            window.train_start <= session_date <= window.train_end for session_date in dates
        ),
        "validation_sessions": sum(
            window.validation_start <= session_date <= window.validation_end
            for session_date in dates
        ),
        "oos_sessions": sum(
            window.oos_start <= session_date <= window.oos_end for session_date in dates
        ),
    }


def _coverage_reasons(
    label: str,
    evidence: Mapping[str, Any],
    policy: QualificationPolicy,
    *,
    primary: bool,
) -> list[str]:
    reasons: list[str] = []
    for side in ("baseline", "challenger"):
        coverage = evidence["coverage"][side]
        if coverage["train_sessions"] < policy.minimum_train_observed_sessions:
            reasons.append(f"{label} {side} Train 獨立交易日覆蓋不足")
        if coverage["validation_sessions"] < policy.minimum_validation_observed_sessions:
            reasons.append(f"{label} {side} Validation 獨立交易日覆蓋不足")
        minimum_oos_sessions = (
            policy.minimum_oos_independent_days if primary else policy.minimum_fold_independent_days
        )
        if coverage["oos_sessions"] < minimum_oos_sessions:
            reasons.append(f"{label} {side} OOS 獨立交易日覆蓋不足")
    minimum_trades = policy.minimum_oos_trades if primary else policy.minimum_fold_oos_trades
    if evidence["challenger"]["closed_trades"] < minimum_trades:
        reasons.append(f"{label} Challenger OOS 已平倉交易樣本不足")
    if not evidence["bootstrap"]["eligible"]:
        reasons.append(f"{label} daily-cluster bootstrap 獨立交易日不足")
    return reasons


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
