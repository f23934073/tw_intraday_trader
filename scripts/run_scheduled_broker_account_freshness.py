"""Run one calendar/time-gated broker/account read-only evidence capture."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import twse_calendar_2026
from market_data.broker_account_freshness_schedule import (
    decide_scheduled_broker_account_capture,
)
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.freshness_calibration import TAIPEI


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
    label = str(payload.get("window_label") or "none")
    path = directory / f"broker_account_run_{local_now:%Y%m%dT%H%M%S%z}_{label}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="timezone-aware ISO timestamp; test-only")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("research/captures/freshness_broker_account"),
    )
    parser.add_argument(
        "--run-log-directory",
        type=Path,
        default=Path("research/freshness_calibration/broker_account_scheduled_runs"),
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args(argv)
    now = _parse_now(args.now)
    decision = decide_scheduled_broker_account_capture(
        now,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
    )
    outcome: dict[str, object] = {
        "status": decision.status,
        "now": decision.now.isoformat(),
        "window_label": (
            decision.scheduled_window.label if decision.scheduled_window is not None else None
        ),
        "reason": decision.reason,
        "provider_called": False,
        "threshold_candidates": None,
    }
    if decision.permitted:
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
            import shioaji as sj

            from market_data.broker_account_freshness import (
                inspect_broker_account_freshness_artifact,
                load_broker_account_runtime_config,
                run_broker_account_freshness_capture,
            )

            config = load_broker_account_runtime_config(
                sdk_version=str(getattr(sj, "__version__", "unknown")),
            )
            artifact = run_broker_account_freshness_capture(
                api_factory=lambda simulation: sj.Shioaji(simulation=simulation),
                config=config,
                output_directory=args.output_directory,
                observed_at=decision.now,
                timeout_ms=args.timeout_ms,
            )
            outcome.update(
                status="CAPTURED",
                provider_called=True,
                artifact=str(artifact),
                inspection=inspect_broker_account_freshness_artifact(artifact),
            )
        except Exception as error:
            outcome.update(
                status="CAPTURE_FAILED",
                provider_called=True,
                error_class=type(error).__name__,
            )
    record = _write_run_record(args.run_log_directory, outcome)
    print(json.dumps({"record": str(record), **outcome}, ensure_ascii=False, indent=2))
    return 0 if outcome["status"] in {
        "CAPTURED",
        "NO_CAPTURE_NON_TRADING_DAY",
        "NO_CAPTURE_OFF_SCHEDULE",
    } else 75


if __name__ == "__main__":
    raise SystemExit(main())
