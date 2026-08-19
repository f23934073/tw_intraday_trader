"""Capture raw Shioaji equity Kbars and produce replayable G0 qualification.

This is a market-data-only script.  It logs in with ``subscribe_trade=False``
through the existing Provider and never constructs or submits an order.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from hashlib import sha256
from importlib.metadata import version
from io import StringIO
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import build_provider
from market_data.daily_kbar_qualification import (
    build_capture_artifact,
    build_chunk_boundary_artifact,
    build_session_contract,
    qualify_daily_kbar_source,
    write_json,
)


TAIPEI = ZoneInfo("Asia/Taipei")
TWSE_HOLIDAY_URL = "https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=csv"


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必須是 YYYY-MM-DD") from error


def _fetch_twse_non_trading_dates(year: int) -> tuple[bytes, list[date]]:
    request = Request(TWSE_HOLIDAY_URL, headers={"User-Agent": "tw-intraday-trader-g0"})
    with urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS TWSE URL
        raw = response.read()
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - defensive for an official format change
        raise ValueError("TWSE holiday CSV encoding is unsupported")

    dates: list[date] = []
    for row in csv.reader(StringIO(text)):
        if not row:
            continue
        match = re.search(r"(\d{1,2})月(\d{1,2})日", row[0])
        if match is None:
            continue
        is_open_market_record = len(row) >= 4 and row[3].strip().lower() == "o"
        if not is_open_market_record:
            dates.append(date(year, int(match.group(1)), int(match.group(2))))
    return raw, sorted(set(dates))


def _capture(provider: object, *, name: str, symbol: str, start: date, end: date, sdk_version: str) -> dict[str, object]:
    api = getattr(provider, "_api")
    contract = api.Contracts.Stocks[symbol]
    if contract is None:
        raise KeyError(f"Shioaji contract not found: {symbol}")
    raw = provider._query_contract_kbars(  # type: ignore[attr-defined]
        contract=contract,
        label=symbol,
        start=start,
        end=end,
    )
    return build_capture_artifact(
        capture_name=name,
        symbol=symbol,
        query_start=start,
        query_end=end,
        queried_at=datetime.now(TAIPEI),
        sdk_version=sdk_version,
        raw_kbars=raw,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture raw Shioaji Kbars for daily-source G0 qualification")
    parser.add_argument("--symbol", default="2330")
    parser.add_argument("--full-session-date", type=_date, required=True)
    parser.add_argument("--partial-session-date", type=_date, required=True)
    parser.add_argument("--chunk-left-date", type=_date, required=True)
    parser.add_argument("--chunk-right-date", type=_date, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "research" / "daily_kbar_g0",
    )
    args = parser.parse_args()
    if args.chunk_right_date <= args.chunk_left_date:
        parser.error("--chunk-right-date 必須晚於 --chunk-left-date")

    os.environ["PROVIDER"] = "shioaji"
    sdk_version = version("shioaji")
    provider = build_provider()
    output_dir: Path = args.output_dir
    try:
        daily = _capture(
            provider,
            name="shioaji_daily_sample",
            symbol=args.symbol,
            start=args.full_session_date,
            end=args.full_session_date,
            sdk_version=sdk_version,
        )
        full = _capture(
            provider,
            name="shioaji_intraday_full_session_sample",
            symbol=args.symbol,
            start=args.full_session_date,
            end=args.full_session_date,
            sdk_version=sdk_version,
        )
        partial = _capture(
            provider,
            name="shioaji_partial_session_sample",
            symbol=args.symbol,
            start=args.partial_session_date,
            end=args.partial_session_date,
            sdk_version=sdk_version,
        )
        chunk_left = _capture(
            provider,
            name="chunk_left",
            symbol=args.symbol,
            start=args.chunk_left_date,
            end=args.chunk_left_date,
            sdk_version=sdk_version,
        )
        chunk_right = _capture(
            provider,
            name="chunk_right",
            symbol=args.symbol,
            start=args.chunk_right_date,
            end=args.chunk_right_date,
            sdk_version=sdk_version,
        )
        boundary = build_chunk_boundary_artifact(
            symbol=args.symbol,
            sdk_version=sdk_version,
            left=chunk_left,
            right=chunk_right,
        )
        holiday_csv, non_trading_dates = _fetch_twse_non_trading_dates(args.full_session_date.year)
        session_contract = build_session_contract(
            calendar_version=f"twse_holiday_schedule_{args.full_session_date.year}_v1",
            source_url=TWSE_HOLIDAY_URL,
            source_retrieved_at=datetime.now(TAIPEI),
            official_csv_sha256=sha256(holiday_csv).hexdigest(),
            explicitly_non_trading_dates=non_trading_dates,
        )

        fixtures_dir = output_dir / "fixtures"
        qualification_dir = output_dir / "qualification"
        write_json(fixtures_dir / "shioaji_daily_sample.json", daily)
        write_json(fixtures_dir / "shioaji_intraday_full_session_sample.json", full)
        write_json(fixtures_dir / "shioaji_partial_session_sample.json", partial)
        write_json(fixtures_dir / "shioaji_chunk_boundary_sample.json", boundary)
        reports = qualify_daily_kbar_source(
            daily_capture=daily,
            full_session_capture=full,
            partial_session_capture=partial,
            chunk_boundary_capture=boundary,
            session_contract=session_contract,
            now=datetime.now(TAIPEI),
        )
        for name, report in reports.items():
            write_json(qualification_dir / f"{name}.json", report)
        print(
            f"G0 artifacts written: {output_dir}; selected_path="
            f"{reports['qualification_result']['selected_path']}",
            flush=True,
        )
    finally:
        provider.close()


if __name__ == "__main__":
    main()
