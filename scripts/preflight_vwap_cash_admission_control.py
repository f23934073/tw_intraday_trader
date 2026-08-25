#!/usr/bin/env python3
"""Build the canonical R5 preflight from PostgreSQL evidence and local bars."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backtest.comparability import verify_run_identity
from backtest.dataset import HistoricalDatasetCatalog
from backtest.dataset_binding import canonical_registration_manifest
from backtest.domain import RunStatus, digest
from backtest.repository import _decode_json, _rebuild_chunked_result
from backtest.research_control import (
    CashAdmissionPreflightCatalog,
    build_cash_admission_preflight,
    compute_cash_admission_preflight_statistics,
    recompute_backtest_result_digest,
)
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a read-only, provider-free R5 cash-admission preflight",
    )
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="defaults to BACKTEST_DATA_DIR/research_controls/preflights",
    )
    return parser


def _row(cursor: Any, raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {column.name: raw[index] for index, column in enumerate(cursor.description)}


def _result(cursor: Any, run_id: str) -> dict[str, Any]:
    cursor.execute(
        "SELECT result_json FROM backtest.backtest_results WHERE run_id = %s",
        (run_id,),
    )
    raw = cursor.fetchone()
    if raw is None:
        raise ValueError("baseline Run 沒有 immutable result")
    root = _decode_json(_row(cursor, raw)["result_json"])
    if root.get("_storage") is None:
        return root
    cursor.execute(
        """
        SELECT field_name, chunk_sequence, item_count, payload_json, payload_digest
        FROM backtest.backtest_result_chunks
        WHERE run_id = %s
        ORDER BY field_name, chunk_sequence
        """,
        (run_id,),
    )
    rows = [_row(cursor, item) for item in cursor.fetchall()]
    return _rebuild_chunked_result(root, rows)


def _verify_baseline_result_identity(
    baseline: dict[str, Any],
    result: dict[str, Any],
) -> None:
    stored_digest = str(result.get("summary", {}).get("result_digest") or "")
    if (
        not stored_digest
        or stored_digest != str(baseline.get("result_digest") or "")
        or recompute_backtest_result_digest(result) != stored_digest
    ):
        raise ValueError("baseline semantic result digest 無法重建")


def main() -> int:
    args = _parser().parse_args()
    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R5 preflight requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT * FROM backtest.backtest_runs WHERE run_id = %s",
                (args.baseline_run_id,),
            )
            raw_run = cursor.fetchone()
            if raw_run is None:
                raise KeyError(f"找不到 baseline Run：{args.baseline_run_id}")
            baseline = {
                **_row(cursor, raw_run),
                "config": _decode_json(_row(cursor, raw_run)["config_json"]),
            }
            baseline.pop("config_json", None)
            baseline["progress"] = float(baseline["progress"])
            verify_run_identity(baseline)
            if baseline["status"] != RunStatus.COMPLETED.value:
                raise ValueError("baseline Run 必須是 COMPLETED")
            result = _result(cursor, args.baseline_run_id)
            _verify_baseline_result_identity(baseline, result)
            cursor.execute(
                "SELECT * FROM backtest.backtest_datasets WHERE dataset_id = %s",
                (baseline["dataset_id"],),
            )
            raw_dataset = cursor.fetchone()
            if raw_dataset is None:
                raise ValueError("baseline Dataset registration 遺失")
            dataset_row = _row(cursor, raw_dataset)
            if dataset_row["status"] != "READY":
                raise ValueError("baseline Dataset 不是 READY")
            registered_manifest = canonical_registration_manifest(
                _decode_json(dataset_row["manifest_json"])
            )
            cursor.execute("COMMIT")

    catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
    local_manifest = catalog.get_manifest(str(baseline["dataset_id"]))
    if local_manifest.to_dict() != registered_manifest:
        raise ValueError("local Dataset manifest 與 PostgreSQL registration 不一致")
    statistics = compute_cash_admission_preflight_statistics(
        baseline_orders=result.get("orders", ()),
        bars=catalog.iter_bars_ordered(str(baseline["dataset_id"])),
    )
    config = dict(baseline["config"])
    atomic_snapshot = dict(config["atomic_strategy_run_snapshot"])
    amount_contract = dict(config["dataset_amount_contract"])
    binding_snapshot = dict(config["dataset_binding_snapshot"])
    identity = {
        "baseline_run_id": baseline["run_id"],
        "baseline_config_digest": baseline["config_digest"],
        "baseline_result_digest": baseline["result_digest"],
        "dataset_id": baseline["dataset_id"],
        "dataset_digest": baseline["dataset_digest"],
        "dataset_manifest_digest": registered_manifest["manifest_digest"],
        "dataset_bars_sha256": registered_manifest["bars_sha256"],
        "dataset_binding_revision": int(binding_snapshot["revision"]),
        "strategy_set_snapshot_digest": digest(dict(config["strategy_set"])),
        "atomic_strategy_run_snapshot_digest": atomic_snapshot["snapshot_digest"],
        "dataset_amount_contract_digest": digest(amount_contract),
        "engine_version": config["engine_version"],
        "commission_rate": str(config["commission_rate"]),
        "sell_tax_rate": str(config["sell_tax_rate"]),
        "slippage_bps": str(config["slippage_bps"]),
        "min_lot_shares": int(config["min_lot_shares"]),
    }
    preflight = build_cash_admission_preflight(
        identity=identity,
        s_max=statistics.s_max,
        p_max=statistics.p_max,
        candidate_order_count=statistics.candidate_order_count,
        matched_next_bar_count=statistics.matched_next_bar_count,
        missing_next_bar_count=statistics.missing_next_bar_count,
        baseline_signal_multiplicity_digest=(
            statistics.baseline_signal_multiplicity_digest
        ),
    )
    output_dir = args.output_dir or (
        backtest_settings.BACKTEST_DATA_DIR / "research_controls" / "preflights"
    )
    path = CashAdmissionPreflightCatalog(output_dir).save(preflight)
    print(
        json.dumps(
            {
                "artifact_digest": preflight["artifact_digest"],
                "path": str(path),
                "statistics": preflight["statistics"],
                "sizing": preflight["sizing"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
