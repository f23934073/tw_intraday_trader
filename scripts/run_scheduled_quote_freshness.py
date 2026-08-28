"""Run one calendar-gated quote-freshness capture selected by Taipei time."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPOSITORY_ROOT)
sys.path.insert(0, str(REPOSITORY_ROOT))

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.freshness_calibration import run_live_quote_freshness_capture
from market_data.freshness_calibration import FreshnessCalibrationArtifactError
from market_data.freshness_calibration_quality import summarize_post_capture_quality
from market_data.freshness_calibration_schedule import (
    FROZEN_MANIFEST_PATH,
    TAIPEI,
    load_frozen_cohort,
    run_scheduled_quote_capture,
)


def _ntp_preflight() -> dict[str, object]:
    samples: list[dict[str, object]] = []
    for _ in range(5):
        try:
            completed = subprocess.run(
                ["/usr/bin/sntp", "-d", "time.apple.com"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            samples.append(
                {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4_000:],
                    "stderr": completed.stderr[-4_000:],
                }
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            samples.append({"error": str(error)})
    return {
        "command": ["/usr/bin/sntp", "-d", "time.apple.com"],
        "samples": samples,
        "successful_samples": sum(
            sample.get("returncode") == 0 for sample in samples
        ),
    }


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(TAIPEI)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--now must include a timezone offset")
    return parsed.astimezone(TAIPEI)


def _write_run_record(directory: Path, payload: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    local_now = datetime.fromisoformat(str(payload["now"])).astimezone(TAIPEI)
    window = str(payload.get("session_window") or "none")
    path = directory / f"run_{local_now:%Y%m%dT%H%M%S%z}_{window}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="timezone-aware ISO timestamp; test-only")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=FROZEN_MANIFEST_PATH,
        help="must remain the approved frozen cohort manifest",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("research/captures/freshness_quote"),
    )
    parser.add_argument(
        "--run-log-directory",
        type=Path,
        default=Path("research/freshness_calibration/scheduled_runs"),
    )
    args = parser.parse_args(argv)
    now = _parse_now(args.now)
    outcome = run_scheduled_quote_capture(
        now,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        manifest_path=args.manifest,
        output_directory=args.output_directory,
        ntp_preflight=_ntp_preflight,
        capture=run_live_quote_freshness_capture,
    )
    if outcome["status"] == "CAPTURED":
        try:
            outcome["post_capture_quality"] = summarize_post_capture_quality(
                Path(str(outcome["artifact"])),
                expected_symbol_tiers=load_frozen_cohort(args.manifest),
                expected_session_window=str(outcome["session_window"]),
            )
        except (FreshnessCalibrationArtifactError, OSError, ValueError) as error:
            outcome.update(
                status="CAPTURE_INVALID",
                post_capture_quality_error=f"{type(error).__name__}: {error}",
            )
    record = _write_run_record(args.run_log_directory, outcome)
    print(json.dumps({"record": str(record), **outcome}, ensure_ascii=False, indent=2))
    return 0 if outcome["status"] in {"CAPTURED", "NO_CAPTURE_NON_TRADING_DAY", "NO_CAPTURE_OFF_SCHEDULE"} else 75


if __name__ == "__main__":
    raise SystemExit(main())
