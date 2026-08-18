"""Seal a validated historical JSONL file and register it for the Web backtest.

The input must contain one canonical ``HistoricalBar.to_dict()`` JSON object
per line.  This boundary deliberately does not accept browser file uploads:
large date-effective universe data should be prepared and reviewed server-side.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

# `python scripts/import_backtest_dataset.py` makes ``scripts/`` the first
# import path.  Add the repository root so the documented invocation works
# before (and after) editable installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import HistoricalBar
from backtest.repository import BacktestRepository
from config import backtest as backtest_settings


def import_dataset(
    *,
    bars_path: Path,
    source: str,
    universe_scope: str,
    research_eligible: bool,
    catalog: HistoricalDatasetCatalog,
    repository: BacktestRepository,
) -> dict[str, object]:
    """Validate, seal and register a JSONL dataset atomically."""
    if research_eligible and universe_scope != "DATE_EFFECTIVE":
        raise ValueError("只有 DATE_EFFECTIVE universe 才能標示 research eligible")
    bars = tuple(_read_bars(bars_path))
    manifest = catalog.create_imported_dataset(
        bars=bars,
        source=source,
        universe_scope=universe_scope,
        research_eligible=research_eligible,
        issues=() if research_eligible else ("匯入資料未宣告 date-effective 完整 universe",),
    )
    repository.upsert_dataset(manifest.to_dict(), "READY")
    return manifest.to_dict()


def _read_bars(path: Path) -> Iterable[HistoricalBar]:
    if not path.is_file():
        raise ValueError(f"找不到 JSONL 檔案：{path}")
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield HistoricalBar.from_dict(json.loads(line))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}:{line_number} 不是合法 HistoricalBar JSON") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="匯入並封存歷史回測 JSONL 資料集")
    parser.add_argument("--bars", required=True, type=Path, help="每列一個 HistoricalBar JSON 的 JSONL 檔")
    parser.add_argument("--source", required=True, help="資料來源與版本，例如 twse-tpex-master-v1")
    parser.add_argument(
        "--universe-scope",
        default="IMPORTED",
        choices=("IMPORTED", "CURRENT_SNAPSHOT", "DATE_EFFECTIVE"),
    )
    parser.add_argument(
        "--research-eligible",
        action="store_true",
        help="僅在輸入涵蓋 date-effective universe、交易日與必要調整資料時使用",
    )
    args = parser.parse_args()
    catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
    repository = BacktestApplicationService._build_repository()
    try:
        manifest = import_dataset(
            bars_path=args.bars,
            source=args.source,
            universe_scope=args.universe_scope,
            research_eligible=args.research_eligible,
            catalog=catalog,
            repository=repository,
        )
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
