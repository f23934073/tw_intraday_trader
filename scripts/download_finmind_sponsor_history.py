"""Begin or resume a paced FinMind Sponsor symbol-day history job."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from time import sleep

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.finmind_history import (  # noqa: E402
    FinMindApiClient,
    FinMindHistoryStore,
    FinMindSponsorDownloader,
)


DEFAULT_START = date(2023, 8, 19)
DEFAULT_END = date(2026, 8, 18)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "以 FinMind Sponsor 建立可續跑的三年一分鐘 K；每個 symbol-day "
            "成功後立即寫入獨立 SQLite acquisition store"
        )
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start-date", type=_date, default=DEFAULT_START)
    parser.add_argument("--end-date", type=_date, default=DEFAULT_END)
    parser.add_argument("--calendar-symbol", default="2330")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/finmind_sponsor/history.sqlite3"),
    )
    parser.add_argument("--max-requests", type=int, default=100)
    parser.add_argument("--reserve-requests", type=int, default=500)
    parser.add_argument("--pace-seconds", type=float, default=1.0)
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--revalidate-invalid", action="store_true")
    parser.add_argument("--continuous-hourly", action="store_true")
    parser.add_argument("--quota-poll-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.quota_poll_seconds <= 0:
        parser.error("quota-poll-seconds must be positive")

    load_dotenv(PROJECT_ROOT / ".env")
    database = args.database
    if not database.is_absolute():
        database = PROJECT_ROOT / database
    store = FinMindHistoryStore(database)
    try:
        job_id = store.ensure_job(
            symbols=args.symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            calendar_symbol=args.calendar_symbol,
        )
        selected_modes = sum(
            (args.status_only, args.audit_only, args.revalidate_invalid)
        )
        if selected_modes > 1:
            parser.error("select only one status/audit/revalidate mode")
        if selected_modes and args.continuous_hourly:
            parser.error("continuous-hourly cannot be combined with offline modes")
        if args.status_only:
            result = store.reconcile_completion(job_id)
        elif args.audit_only:
            result = store.audit(job_id)
        elif args.revalidate_invalid:
            result = store.revalidate_invalid(job_id)
        else:
            client = FinMindApiClient(os.environ.get("FINMIND_API_TOKEN", ""))
            downloader = FinMindSponsorDownloader(
                client=client,
                store=store,
                report=lambda message: print(message, flush=True),
            )
            remaining_budget = args.max_requests
            direct_quota_probe = False
            wait_before_direct_probe = False
            while True:
                if wait_before_direct_probe:
                    release_delay = store.seconds_until_next_recorded_release()
                    wait_seconds = max(args.quota_poll_seconds, release_delay)
                    print(
                        f"FinMind 額度已滿；{wait_seconds:.2f} 秒後重查",
                        flush=True,
                    )
                    sleep(wait_seconds)
                    wait_before_direct_probe = False
                result = downloader.run(
                    job_id,
                    max_requests=remaining_budget,
                    reserve_requests=args.reserve_requests,
                    pace_seconds=args.pace_seconds,
                    check_usage=not direct_quota_probe,
                )
                spent = int(result.get("batch_requests_spent", 0))
                remaining_budget -= spent
                if not args.continuous_hourly:
                    break
                if result["status"] in {"COMPLETED", "BLOCKED_DATA_QUALITY"}:
                    break
                if remaining_budget <= 0:
                    break
                if result.get("stop_kind") == "PROVIDER":
                    break
                if args.reserve_requests == 0:
                    direct_quota_probe = True
                if spent:
                    print(
                        "滾動額度批次完成："
                        f"{spent} requests；尚餘 {result['remaining_symbol_days']} "
                        "symbol-days",
                        flush=True,
                    )
                if result.get("stop_kind") == "QUOTA" or not spent:
                    wait_before_direct_probe = True
                    continue
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
