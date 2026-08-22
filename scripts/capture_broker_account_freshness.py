"""Run one calendar-gated, read-only broker/account evidence capture."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from config import twse_calendar_2026
from market_data.broker_account_freshness import (
    inspect_broker_account_freshness_artifact,
    load_broker_account_runtime_config,
    run_broker_account_freshness_capture,
)
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.freshness_calibration import TAIPEI


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("research/captures/freshness_broker_account"),
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args()

    now = datetime.now(TAIPEI)
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    if not calendar.is_trading_day(now.date()):
        print(json.dumps({
            "status": "NO_CAPTURE_NON_TRADING_DAY",
            "now": now.isoformat(),
            "provider_called": False,
            "threshold_candidates": None,
        }, ensure_ascii=False, indent=2))
        return 0

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    import shioaji as sj

    config = load_broker_account_runtime_config(
        sdk_version=str(getattr(sj, "__version__", "unknown")),
    )
    artifact = run_broker_account_freshness_capture(
        api_factory=lambda simulation: sj.Shioaji(simulation=simulation),
        config=config,
        output_directory=args.output_directory,
        observed_at=now,
        timeout_ms=args.timeout_ms,
    )
    print(json.dumps({
        "status": "CAPTURED",
        "artifact": str(artifact),
        "inspection": inspect_broker_account_freshness_artifact(artifact),
        "threshold_candidates": None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
