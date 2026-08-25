#!/usr/bin/env python3
"""Read-only diagnostic for unmatched R5 preflight ENTRY candidates."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
BASELINE_RUN_ID = "run-91ad87981676414da87b928398fa43c9"
OUTPUT_PATH = Path(__file__).with_name("r5_missing_next_bar_diagnostics.json")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    import psycopg

    from backtest.comparability import verify_run_identity
    from backtest.dataset import HistoricalDatasetCatalog
    from backtest.domain import canonical_json, digest
    from config import backtest as backtest_settings
    from scripts.preflight_vwap_cash_admission_control import (
        _result,
        _row,
        _verify_baseline_result_identity,
    )

    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT * FROM backtest.backtest_runs WHERE run_id = %s",
                (BASELINE_RUN_ID,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise KeyError(BASELINE_RUN_ID)
            raw_row = _row(cursor, raw)
            baseline = {
                **raw_row,
                "config": (
                    dict(raw_row["config_json"])
                    if isinstance(raw_row["config_json"], dict)
                    else json.loads(raw_row["config_json"])
                ),
            }
            baseline.pop("config_json", None)
            baseline["progress"] = float(baseline["progress"])
            verify_run_identity(baseline)
            result = _result(cursor, BASELINE_RUN_ID)
            _verify_baseline_result_identity(baseline, result)
            cursor.execute("ROLLBACK")

    orders = [
        dict(order)
        for order in result.get("orders", ())
        if order.get("side") == "ENTRY"
    ]
    by_symbol: dict[str, list[tuple[datetime, int]]] = {}
    for index, order in enumerate(orders):
        created_at = datetime.fromisoformat(str(order["created_at"]))
        by_symbol.setdefault(str(order["symbol"]), []).append((created_at, index))
    for values in by_symbol.values():
        values.sort(key=lambda item: (item[0], str(orders[item[1]].get("order_id", ""))))

    indexes = {symbol: 0 for symbol in by_symbol}
    matched: set[int] = set()
    last_bar: dict[tuple[str, str], datetime] = {}
    catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
    for bar in catalog.iter_bars_ordered(str(baseline["dataset_id"])):
        if bar.symbol not in by_symbol:
            continue
        last_bar[(bar.symbol, bar.timestamp.date().isoformat())] = bar.timestamp
        values = by_symbol[bar.symbol]
        position = indexes[bar.symbol]
        while position < len(values):
            created_at, order_index = values[position]
            if bar.timestamp <= created_at:
                break
            if bar.timestamp.date() > created_at.date():
                position += 1
                continue
            if bar.timestamp.date() < created_at.date():
                break
            matched.add(order_index)
            position += 1
        indexes[bar.symbol] = position

    missing: list[dict[str, Any]] = []
    for index, order in enumerate(orders):
        if index in matched:
            continue
        created_at = datetime.fromisoformat(str(order["created_at"]))
        terminal = last_bar.get(
            (str(order["symbol"]), created_at.date().isoformat())
        )
        missing.append(
            {
                "order_id": order.get("order_id"),
                "symbol": order.get("symbol"),
                "created_at": order.get("created_at"),
                "status": order.get("status"),
                "reason": order.get("reason"),
                "session_last_bar": terminal.isoformat() if terminal else None,
            }
        )
    body = {
        "baseline_run_id": BASELINE_RUN_ID,
        "dataset_id": baseline["dataset_id"],
        "candidate_order_count": len(orders),
        "matched_next_bar_count": len(matched),
        "missing_next_bar_count": len(missing),
        "missing": missing,
    }
    artifact = {**body, "artifact_digest": digest(body)}
    OUTPUT_PATH.write_text(canonical_json(artifact) + "\n", encoding="utf-8")
    print(canonical_json({"path": str(OUTPUT_PATH), **artifact}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
