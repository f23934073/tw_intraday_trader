"""Seal a current, source-backed cross-industry large-cap universe."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.domain import canonical_json  # noqa: E402
from backtest.finmind_history import (  # noqa: E402
    TAIPEI,
    FinMindApiClient,
    FinMindResponse,
    select_industry_market_value_leaders,
)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def _load_raw_response(path: Path) -> FinMindResponse:
    source = path if path.is_absolute() else PROJECT_ROOT / path
    body = gzip.decompress(source.read_bytes())
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"raw response is not an object: {source}")
    return FinMindResponse(http_status=200, body=body, payload=payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="依 FinMind 最新市值，封存每個上市櫃產業的市值代表股名單"
    )
    parser.add_argument(
        "--market-window-end",
        type=_date,
        default=datetime.now(TAIPEI).date() - timedelta(days=1),
    )
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--trading-date-count", type=int, default=727)
    parser.add_argument("--reserve-requests", type=int, default=500)
    parser.add_argument("--calendar-requests", type=int, default=1)
    parser.add_argument(
        "--already-complete", nargs="+", default=("2317", "2330")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/finmind_sponsor/universes/industry_leaders.json"),
    )
    parser.add_argument("--stock-info-raw", type=Path)
    parser.add_argument("--market-value-raw", type=Path)
    args = parser.parse_args()
    if args.lookback_days < 1:
        parser.error("lookback-days must be positive")
    if args.trading_date_count < 1:
        parser.error("trading-date-count must be positive")
    if args.reserve_requests < 0 or args.calendar_requests < 0:
        parser.error("request reserves cannot be negative")
    if (args.stock_info_raw is None) != (args.market_value_raw is None):
        parser.error("provide both stock-info-raw and market-value-raw")

    load_dotenv(PROJECT_ROOT / ".env")
    client = FinMindApiClient(os.environ.get("FINMIND_API_TOKEN", ""))
    usage_before = client.usage()
    market_window_start = args.market_window_end - timedelta(
        days=args.lookback_days - 1
    )
    metadata_data_requests = 0
    if args.stock_info_raw is not None and args.market_value_raw is not None:
        stock_info = _load_raw_response(args.stock_info_raw)
        market_value = _load_raw_response(args.market_value_raw)
    else:
        stock_info = client.data(dataset="TaiwanStockInfo")
        metadata_data_requests += 1
        market_value = None
        for offset in range(args.lookback_days):
            candidate_date = args.market_window_end - timedelta(days=offset)
            metadata_data_requests += 1
            response = client.data(
                dataset="TaiwanStockMarketValue",
                start_date=candidate_date,
            )
            rows = (response.payload or {}).get("data")
            if isinstance(rows, list) and rows:
                market_value = response
                break
        if market_value is None:
            raise ValueError(
                "TaiwanStockMarketValue returned no rows in the requested lookback window"
            )
    output = args.output
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    raw_directory = output.parent / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    for dataset, response in (
        ("TaiwanStockInfo", stock_info),
        ("TaiwanStockMarketValue", market_value),
    ):
        digest = hashlib.sha256(response.body).hexdigest()
        raw_path = raw_directory / f"{dataset}_{digest}.json.gz"
        if not raw_path.exists():
            raw_path.write_bytes(gzip.compress(response.body, mtime=0))
    leaders = select_industry_market_value_leaders(
        stock_info_response=stock_info,
        market_value_response=market_value,
        already_complete_symbols=args.already_complete,
    )
    usage_after = client.usage()
    remaining_after_metadata = usage_after.remaining
    safe_data_requests = max(
        0,
        remaining_after_metadata
        - args.reserve_requests
        - args.calendar_requests,
    )
    complete_symbol_capacity = safe_data_requests // args.trading_date_count
    pending = sorted(
        (leader for leader in leaders if not leader.already_complete),
        key=lambda item: (-item.market_value, item.symbol),
    )
    selected = pending[:complete_symbol_capacity]
    market_value_date = leaders[0].market_value_date
    artifact = {
        "schema_version": 1,
        "created_at": datetime.now(TAIPEI).isoformat(),
        "selection_rule": (
            "latest listed TWSE/TPEX 4-digit common-stock row; highest positive "
            "market value per detailed FinMind industry; aggregate electronic, "
            "chemical/biotech, and innovation-board labels removed when a "
            "detailed category exists; ties by stock_id; truly ambiguous same-date "
            "listing rows, incomplete/invalid info rows, and non-positive market "
            "values excluded"
        ),
        "market_value_date": market_value_date.isoformat(),
        "market_value_window": {
            "start": market_window_start.isoformat(),
            "end": args.market_window_end.isoformat(),
        },
        "already_complete_symbols": sorted(set(args.already_complete)),
        "industry_count": len(leaders),
        "leaders": [leader.to_dict() for leader in leaders],
        "today_budget": {
            "usage_before": {
                "user_count": usage_before.user_count,
                "api_request_limit": usage_before.api_request_limit,
            },
            "usage_after_metadata": {
                "user_count": usage_after.user_count,
                "api_request_limit": usage_after.api_request_limit,
                "remaining": remaining_after_metadata,
            },
            "reserve_requests": args.reserve_requests,
            "calendar_requests": args.calendar_requests,
            "trading_date_count": args.trading_date_count,
            "complete_symbol_capacity": complete_symbol_capacity,
            "selected_symbols": [leader.symbol for leader in selected],
            "selected_industries": [leader.industry for leader in selected],
            "planned_data_requests": (
                args.calendar_requests
                + len(selected) * args.trading_date_count
            ),
            "metadata_data_requests_this_run": metadata_data_requests,
        },
        "source_provenance": {
            "stock_info_dataset": "TaiwanStockInfo",
            "stock_info_raw_sha256": hashlib.sha256(stock_info.body).hexdigest(),
            "market_value_dataset": "TaiwanStockMarketValue",
            "market_value_raw_sha256": hashlib.sha256(market_value.body).hexdigest(),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(artifact) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "market_value_date": artifact["market_value_date"],
                "industry_count": artifact["industry_count"],
                **artifact["today_budget"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
