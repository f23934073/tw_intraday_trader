"""Validated defaults for editable LOCAL_PAPER runtime settings."""

from __future__ import annotations

import os
from pathlib import Path


LOCAL_PAPER_DEFAULT_STARTING_CASH_TWD = "10000000"
LOCAL_PAPER_DEFAULT_DAILY_BUY_LIMIT_TWD = "2000000"
LOCAL_PAPER_DEFAULT_COMMISSION_RATE = "0"
LOCAL_PAPER_DEFAULT_MINIMUM_COMMISSION_TWD = "0"
LOCAL_PAPER_V2_DEFAULT_SLIPPAGE_BPS = "5"
LOCAL_PAPER_SETTINGS_PATH = Path(
    os.environ.get(
        "LOCAL_PAPER_SETTINGS_PATH",
        "data/local_paper/settings_v1.json",
    )
)
