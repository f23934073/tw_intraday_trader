"""Historical-backtest configuration.

The backtest process is intentionally data-only.  No setting in this module
enables broker orders, account access, CA, or realtime quote subscriptions.
"""

from __future__ import annotations

import os
from datetime import time
from pathlib import Path


def _time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError("BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME 必須是 HH:MM") from error
    if parsed.tzinfo is not None:
        raise ValueError("BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME 不可包含 timezone")
    return parsed


BACKTEST_ENABLED = os.environ.get("BACKTEST_ENABLED", "true").lower() == "true"
BACKTEST_DATA_DIR = Path(os.environ.get("BACKTEST_DATA_DIR", "data/backtest"))
BACKTEST_DATABASE_URL = os.environ.get("BACKTEST_DATABASE_URL", "").strip()
BACKTEST_WORKERS = max(1, int(os.environ.get("BACKTEST_WORKERS", "1")))
BACKTEST_INCREMENTAL_SYNC_ENABLED = (
    os.environ.get("BACKTEST_INCREMENTAL_SYNC_ENABLED", "true").lower() == "true"
)
BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME = _time(
    os.environ.get("BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME", "14:30")
)
BACKTEST_INCREMENTAL_SYNC_POLL_SECONDS = max(
    1.0,
    float(os.environ.get("BACKTEST_INCREMENTAL_SYNC_POLL_SECONDS", "60")),
)
BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS = max(
    1,
    int(os.environ.get("BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS", "1")),
)
BACKTEST_ACTIVE_JOB_STALE_MINUTES = max(
    1,
    int(os.environ.get("BACKTEST_ACTIVE_JOB_STALE_MINUTES", "30")),
)
BACKTEST_DEFAULT_YEARS = 3
BACKTEST_DEFAULT_STARTING_CASH = "10000000"
BACKTEST_DEFAULT_POSITION_FRACTION = "0.10"
BACKTEST_DEFAULT_COMMISSION_RATE = "0.001425"
BACKTEST_DEFAULT_SELL_TAX_RATE = "0.003"
BACKTEST_DEFAULT_SLIPPAGE_BPS = "5"
