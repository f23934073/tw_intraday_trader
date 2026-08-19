"""Capture one raw Kbar session and an official TWSE daily report for G0."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from importlib.metadata import version
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import build_provider
from market_data.daily_kbar_qualification import build_capture_artifact, write_json
from market_data.daily_kbar_reconciliation import (
    TWSE_STOCK_DAY_URL,
    build_twse_stock_day_capture,
    reconcile_completed_session,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必須是 YYYY-MM-DD") from error


def _fetch_twse_stock_day(symbol: str, session_date: date) -> bytes:
    query = urlencode(
        {
            "response": "json",
            "date": session_date.replace(day=1).strftime("%Y%m%d"),
            "stockNo": symbol,
        }
    )
    request = Request(
        f"{TWSE_STOCK_DAY_URL}?{query}",
        headers={"User-Agent": "tw-intraday-trader-g0"},
    )
    with urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS TWSE URL
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture G0 Kbar/TWSE reconciliation evidence")
    parser.add_argument("--symbol", default="2330")
    parser.add_argument("--session-date", type=_date, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "research" / "daily_kbar_g0",
    )
    args = parser.parse_args()
    os.environ["PROVIDER"] = "shioaji"
    provider = build_provider()
    try:
        api = provider._api  # type: ignore[attr-defined]
        contract = api.Contracts.Stocks[args.symbol]
        if contract is None:
            raise KeyError(f"Shioaji contract not found: {args.symbol}")
        raw_kbars = provider._query_contract_kbars(  # type: ignore[attr-defined]
            contract=contract,
            label=args.symbol,
            start=args.session_date,
            end=args.session_date,
        )
        shioaji_capture = build_capture_artifact(
            capture_name="shioaji_intraday_full_session_amount_sample",
            symbol=args.symbol,
            query_start=args.session_date,
            query_end=args.session_date,
            queried_at=datetime.now(TAIPEI),
            sdk_version=version("shioaji"),
            raw_kbars=raw_kbars,
            extra_fields=("Amount",),
        )
        twse_capture = build_twse_stock_day_capture(
            symbol=args.symbol,
            requested_month=args.session_date.replace(day=1),
            retrieved_at=datetime.now(TAIPEI),
            raw_response=_fetch_twse_stock_day(args.symbol, args.session_date),
        )
        reconciliation = reconcile_completed_session(
            shioaji_capture=shioaji_capture,
            twse_capture=twse_capture,
            session_date=args.session_date,
        )
        fixtures = args.output_dir / "fixtures"
        qualification = args.output_dir / "qualification"
        write_json(fixtures / "shioaji_intraday_full_session_amount_sample.json", shioaji_capture)
        write_json(fixtures / "twse_stock_day_202608_sample.json", twse_capture)
        write_json(qualification / "twse_daily_reconciliation.json", reconciliation)
        print(
            f"G0 reconciliation written: {args.output_dir}; status={reconciliation['status']}",
            flush=True,
        )
    finally:
        provider.close()


if __name__ == "__main__":
    main()
