"""Download historical Kbars with database checkpoints and safe resume."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import build_provider
from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.historical_download import (
    HistoricalDownloadPaused,
    ResumableHistoricalDownloader,
    assert_generic_history_resume_allowed,
)
from config import backtest as backtest_settings


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必須是 YYYY-MM-DD") from error


def _resume_command(job_id: str, *, coverage_scan_mode: bool) -> str:
    command = (
        "PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py "
        f"--resume {job_id}"
    )
    if coverage_scan_mode:
        command += " --continue-on-empty-for-coverage-audit"
    return command


def _preflight_generic_resume_before_provider(job_id: str) -> None:
    repository = BacktestApplicationService._build_repository()
    try:
        assert_generic_history_resume_allowed(repository.get_job(job_id))
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下載歷史 Kbar；每檔股票完成後壓縮寫入回測資料庫，可中斷續傳",
    )
    parser.add_argument("--years", type=int, default=3, help="下載年數，預設 3")
    parser.add_argument("--symbols", nargs="+", help="只下載指定股票，例如 --symbols 2330 2317")
    parser.add_argument("--symbol-limit", type=int, help="只取排序後前 N 檔，適合先做小量驗證")
    parser.add_argument("--end-date", type=_date, help="固定截止日 YYYY-MM-DD，預設今天")
    parser.add_argument(
        "--provider",
        choices=("mock", "shioaji"),
        help="覆寫 .env 的 PROVIDER；正式歷史資料請使用 shioaji",
    )
    parser.add_argument("--resume", metavar="JOB_ID", help="接續先前 dataset-download-* 工作")
    parser.add_argument(
        "--continue-on-empty-for-coverage-audit",
        action="store_true",
        help=(
            "將 Provider 空回應記為 PRICE_DATA_UNAVAILABLE observation 後繼續；"
            "不代表資料成功或正式研究排除"
        ),
    )
    args = parser.parse_args()
    if args.years <= 0:
        parser.error("--years 必須大於 0")
    if args.symbol_limit is not None and args.symbol_limit <= 0:
        parser.error("--symbol-limit 必須大於 0")
    if args.provider:
        os.environ["PROVIDER"] = args.provider
    if args.resume:
        try:
            _preflight_generic_resume_before_provider(args.resume)
        except (KeyError, ValueError) as error:
            parser.error(str(error))

    provider = build_provider()
    repository = None
    job_id = args.resume or ""
    try:
        repository = BacktestApplicationService._build_repository()
        catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
        downloader = ResumableHistoricalDownloader(
            provider=provider,
            repository=repository,
            catalog=catalog,
            report=lambda message: print(message, flush=True),
            coverage_scan_mode=(
                args.continue_on_empty_for_coverage_audit
            ),
        )
        if args.resume:
            print(f"接續下載工作：{job_id}", flush=True)
        else:
            job = downloader.create_job(
                years=args.years,
                symbols=args.symbols,
                symbol_limit=args.symbol_limit,
                end_date=args.end_date,
            )
            job_id = str(job["job_id"])
            print(f"下載工作 ID：{job_id}", flush=True)
            print(f"中斷後可使用 --resume {job_id} 接續。", flush=True)
        manifest = downloader.run(job_id)
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True), flush=True)
    except HistoricalDownloadPaused as error:
        print(f"\n下載已安全暫停：{error}", file=sys.stderr, flush=True)
        if job_id:
            print(
                "若是查詢逾時，可稍後直接接續；若是流量不足，請等交易日上午 "
                "08:00 重置後接續：\n"
                f"  {_resume_command(job_id, coverage_scan_mode=args.continue_on_empty_for_coverage_audit)}",
                file=sys.stderr,
                flush=True,
            )
        raise SystemExit(75)
    except KeyboardInterrupt:
        message = (
            f"\n已暫停。下次使用 --resume {job_id} 接續。"
            if job_id
            else "\n已在建立下載工作前中止；尚未產生可接續的 job id。"
        )
        print(message, file=sys.stderr, flush=True)
        raise SystemExit(130)
    finally:
        try:
            provider.close()
        finally:
            close = getattr(repository, "close", None) if repository is not None else None
            if callable(close):
                close()


if __name__ == "__main__":
    main()
