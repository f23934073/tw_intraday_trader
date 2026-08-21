"""Create an in-sample exploratory dataset from existing history checkpoints."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.exploratory_pilot import ExploratoryPilotBuilder
from config import backtest as backtest_settings


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必須是 YYYY-MM-DD") from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "只讀既有歷史 checkpoint，封存不含 2025/2026 結果的探索性 partial pilot"
        )
    )
    parser.add_argument("--job-id", required=True, help="dataset-download-* 來源工作")
    parser.add_argument("--start-date", type=_date, default=date(2023, 8, 21))
    parser.add_argument("--end-date", type=_date, default=date(2024, 12, 31))
    parser.add_argument("--symbol-limit", type=int, default=12)
    parser.add_argument("--symbols", nargs="+", help="只選指定且通過涵蓋檢查的股票")
    parser.add_argument("--dry-run", action="store_true", help="只顯示選擇計畫，不封存資料集")
    args = parser.parse_args()

    repository = BacktestApplicationService._build_repository()
    try:
        builder = ExploratoryPilotBuilder(
            repository=repository,
            catalog=HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR),
        )
        plan = builder.plan(
            job_id=args.job_id,
            start_date=args.start_date,
            end_date=args.end_date,
            symbol_limit=args.symbol_limit,
            symbols=args.symbols,
        )
        result: dict[str, object] = {"plan": plan.to_dict(), "dry_run": args.dry_run}
        if not args.dry_run:
            result["manifest"] = builder.materialize(plan).to_dict()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
