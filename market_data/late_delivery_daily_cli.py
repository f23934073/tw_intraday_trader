"""Build the derived daily D-HEALTH-LATE-001 evidence summary."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_data.late_delivery_evidence import (
    build_daily_late_delivery_report,
    write_daily_late_delivery_report,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a derived daily late-delivery evidence report from retained sessions."
    )
    parser.add_argument("--date", type=_date)
    parser.add_argument("--records-root", type=Path, default=Path("records/market_events"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_date = args.date or datetime.now(TAIPEI).date()
    try:
        report = build_daily_late_delivery_report(args.records_root, session_date)
        path = write_daily_late_delivery_report(
            args.records_root / session_date.isoformat() / "late_delivery_daily_evidence.json",
            report,
        )
    except (OSError, ValueError) as error:
        print("late_delivery_daily: FAILED")
        print(f"reason: {type(error).__name__}:{error}")
        return 2
    print("late_delivery_daily: PASS")
    print(f"report: {path}")
    print(f"finalized_session_count: {report.session_count}")
    print(f"incomplete_session_ids: {','.join(report.incomplete_session_ids) or 'none'}")
    print(f"replay_failed_session_ids: {','.join(report.replay_failed_session_ids) or 'none'}")
    print("policy_interpretation: PROHIBITED_EVIDENCE_ONLY")
    return 0


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


if __name__ == "__main__":
    raise SystemExit(main())
