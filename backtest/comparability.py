"""One fail-closed comparability contract shared by compare and qualification."""

from __future__ import annotations

from typing import Any, Mapping

from backtest.domain import canonical_json, digest


_IGNORED_RUN_FIELDS = {
    "strategy_set",
    "atomic_strategy_run_snapshot",
    "experiment_id",
    "baseline_run_id",
    "research_baseline_digest",
    "parent_run_id",
    "change_note",
    "target_win_rate",
    "minimum_oos_trades",
    "max_drawdown_guardrail",
}


def verify_run_identity(run: Mapping[str, Any]) -> None:
    """Reject drift between a Run row and its immutable config snapshot."""

    config = run.get("config")
    stored = str(run.get("config_digest") or "")
    if not isinstance(config, Mapping) or not stored or digest(dict(config)) != stored:
        raise ValueError(f"Run config digest 不一致：{run.get('run_id', 'unknown')}")
    run_id = run.get("run_id", "unknown")
    for field_name in ("dataset_id", "dataset_digest"):
        row_value = str(run.get(field_name) or "")
        config_value = str(config.get(field_name) or "")
        if not row_value or not config_value or row_value != config_value:
            raise ValueError(f"Run {field_name} identity 不一致：{run_id}")


def verify_run_config_identity(run: Mapping[str, Any]) -> None:
    """Backward-compatible alias; new code should use verify_run_identity()."""

    verify_run_identity(run)


def verified_atomic_snapshot(config: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return one verified Atomic Snapshot, or None for a legacy Run."""

    raw = config.get("atomic_strategy_run_snapshot")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("Atomic Run Snapshot 格式不合法")
    snapshot = dict(raw)
    if snapshot.get("contract_version") != "atomic-backtest-run-snapshot-v2":
        raise ValueError("不是 Atomic Run Snapshot v2")
    stored = str(snapshot.pop("snapshot_digest", ""))
    if not stored or digest(snapshot) != stored:
        raise ValueError("Atomic Run Snapshot digest 不一致")
    return dict(raw)


def run_comparability_diff(
    baseline: Mapping[str, Any], challenger: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Compare stable execution identity while allowing the tested strategy change.

    Strategy Set/member/Feature Request selection is the independent variable. The
    engine, data, cash/cost/position policy, exit contract, Atomic contract, and
    Feature adapter runtime must remain identical.
    """

    keys = sorted((set(baseline) | set(challenger)) - _IGNORED_RUN_FIELDS)
    output = [
        {
            "field": key,
            "baseline": baseline.get(key),
            "challenger": challenger.get(key),
        }
        for key in keys
        if baseline.get(key) != challenger.get(key)
    ]
    baseline_exit = _exit_contract(baseline)
    challenger_exit = _exit_contract(challenger)
    if canonical_json(baseline_exit) != canonical_json(challenger_exit):
        output.append(
            {
                "field": "strategy_set.exit_contract",
                "baseline": baseline_exit,
                "challenger": challenger_exit,
            }
        )

    left_snapshot = verified_atomic_snapshot(baseline)
    right_snapshot = verified_atomic_snapshot(challenger)
    if (left_snapshot is None) != (right_snapshot is None):
        output.append(
            {
                "field": "atomic_strategy_run_snapshot.contract",
                "baseline": left_snapshot is not None,
                "challenger": right_snapshot is not None,
            }
        )
        return output
    if left_snapshot is None or right_snapshot is None:
        return output

    for field_name in ("contract_version", "feature_adapter_identity"):
        if left_snapshot.get(field_name) != right_snapshot.get(field_name):
            output.append(
                {
                    "field": f"atomic_strategy_run_snapshot.{field_name}",
                    "baseline": left_snapshot.get(field_name),
                    "challenger": right_snapshot.get(field_name),
                }
            )
    left_contracts = _feature_contracts(left_snapshot)
    right_contracts = _feature_contracts(right_snapshot)
    for request_identity in sorted(set(left_contracts) & set(right_contracts)):
        if left_contracts[request_identity] != right_contracts[request_identity]:
            output.append(
                {
                    "field": (
                        "atomic_strategy_run_snapshot.feature_contracts."
                        + request_identity
                    ),
                    "baseline": left_contracts[request_identity],
                    "challenger": right_contracts[request_identity],
                }
            )
    return output


def comparability_contract_digest(config: Mapping[str, Any]) -> str:
    """Stable identity used by the experiment-family aggregate."""

    snapshot = verified_atomic_snapshot(config)
    projection = {
        key: config.get(key)
        for key in sorted(set(config) - _IGNORED_RUN_FIELDS)
    }
    projection["exit_contract"] = _exit_contract(config)
    projection["atomic_runtime"] = (
        {
            "contract_version": snapshot.get("contract_version"),
            "feature_adapter_identity": snapshot.get("feature_adapter_identity"),
        }
        if snapshot is not None
        else None
    )
    return digest(projection)


def baseline_research_config_digest(config: Mapping[str, Any]) -> str:
    """Exact Baseline research identity independent of one execution Run ID."""

    snapshot = verified_atomic_snapshot(config)
    if snapshot is None:
        raise ValueError("Experiment Baseline 必須是 Atomic Run Snapshot v2")
    ignored = {
        "experiment_id",
        "baseline_run_id",
        "research_baseline_digest",
        "parent_run_id",
        "change_note",
        "target_win_rate",
        "minimum_oos_trades",
        "max_drawdown_guardrail",
    }
    projection = {
        key: config.get(key)
        for key in sorted(set(config) - ignored)
    }
    projection["atomic_strategy_run_snapshot"] = snapshot
    return digest(projection)


def _exit_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    strategy_set = config.get("strategy_set")
    value = strategy_set if isinstance(strategy_set, Mapping) else {}
    return {
        key: value.get(key)
        for key in (
            "exit_strategy_ids",
            "exit_policy",
            "exit_min_trigger_count",
        )
    }


def _feature_contracts(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for owner in snapshot.get("feature_requests", ()):
        if not isinstance(owner, Mapping):
            raise ValueError("Atomic Feature Request owner 格式不合法")
        for raw in owner.get("requests", ()):
            if not isinstance(raw, Mapping):
                raise ValueError("Atomic Feature Request 格式不合法")
            request = dict(raw)
            request_identity = str(
                request.get("request_digest")
                or digest(
                    {
                        "feature_id": request.get("feature_id"),
                        "parameters": request.get("parameters", {}),
                    }
                )
            )
            contract = {
                key: request.get(key)
                for key in (
                    "feature_id",
                    "parameter_digest",
                    "request_digest",
                    "specification_digest",
                    "feature_implementation_digest",
                    "as_of_semantics",
                    "runtime_identity_digest",
                )
            }
            previous = output.get(request_identity)
            if previous is not None and previous != contract:
                raise ValueError("同一 Feature Request identity 對應不同契約")
            output[request_identity] = contract
    return output
