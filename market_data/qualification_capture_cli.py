"""CLI for the standalone historical qualification capture harness."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.qualification_capture import (
    HistoricalQualificationCapture,
    QualificationCaptureConfig,
    require_qualification_flags_off,
)
from market_data.shioaji_momentum_stream import ShioajiMomentumStream


TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a flags-off, subscribe_trade=false Tick/BidAsk session "
            "and run exact projection replay qualification."
        )
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--duration-seconds", type=int, default=30)
    parser.add_argument("--case", choices=("A", "B"), default="A")
    parser.add_argument(
        "--records-root",
        type=Path,
        default=Path("records/market_events"),
    )
    parser.add_argument("--session-id")
    parser.add_argument("--subscribe-ack-timeout-seconds", type=int, default=30)
    parser.add_argument("--preopen-wait-timeout-seconds", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_qualification_flags_off()
    except RuntimeError as error:
        print("qualification_capture: FAILED")
        print(f"reason: {error}")
        return 2
    now = datetime.now(TAIPEI)
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    if not calendar.is_trading_day(now.date()):
        print("qualification_capture: FAILED")
        print("reason: NOT_A_REVIEWED_TRADING_DAY")
        return 2
    scheduled_open = datetime.combine(now.date(), time(9, 0), tzinfo=TAIPEI)
    scheduled_close = datetime.combine(now.date(), time(13, 30), tzinfo=TAIPEI)
    earliest_connect = scheduled_open - timedelta(
        seconds=args.preopen_wait_timeout_seconds
    )
    if now < earliest_connect or now > scheduled_close:
        print("qualification_capture: FAILED")
        print("reason: OUTSIDE_QUALIFICATION_CONNECTION_WINDOW")
        return 2
    session_id = args.session_id or (
        f"hqual-{now.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
    )
    config = QualificationCaptureConfig(
        symbol=args.symbol,
        session_id=session_id,
        records_root=args.records_root,
        duration_seconds=args.duration_seconds,
        subscribe_ack_timeout_seconds=args.subscribe_ack_timeout_seconds,
        preopen_wait_timeout_seconds=args.preopen_wait_timeout_seconds,
        qualification_case=args.case,
    )
    stream = ShioajiMomentumStream.connect_from_env(session_id=session_id)
    result = HistoricalQualificationCapture(
        stream,
        config,
        prior_session_date=calendar.previous_trading_day(now.date()),
        calendar_version=(
            f"{calendar.schema_version}:{calendar.source_digest}"
        ),
    ).run()
    print(f"qualification_capture: {'PASS' if result.qualified else 'FAILED'}")
    print(f"classification: {result.classification}")
    print(f"exact_replay: {'PASS' if result.exact_replay_passed else 'FAILED'}")
    print(f"session: {result.session_dir}")
    if result.report_path is not None:
        print(f"report: {result.report_path}")
    for reason in result.reasons:
        print(f"reason: {reason}")
    print("gate_effect: NONE_P1_2_REMAINS_BLOCKED")
    return 0 if result.qualified else 2


if __name__ == "__main__":
    raise SystemExit(main())
