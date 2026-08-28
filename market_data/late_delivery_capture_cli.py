"""Run one scheduled passive late-delivery collection window."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.late_delivery_capture import (
    PassiveLateDeliveryCapture,
    PassiveLateDeliveryCaptureConfig,
)
from market_data.late_delivery_evidence import (
    LateDeliveryCohort,
    SessionPhase,
    build_daily_late_delivery_report,
    write_daily_late_delivery_report,
)
from market_data.qualification_capture import require_qualification_flags_off
from market_data.shioaji_momentum_stream import (
    ShioajiLoopbackBindError,
    ShioajiMomentumStream,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one flags-off, subscribe_trade=false passive Tick/BidAsk "
            "late-delivery evidence window.  It never changes Health policy."
        )
    )
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=[item.value for item in SessionPhase])
    parser.add_argument("--duration-seconds", type=int, default=1800)
    parser.add_argument("--records-root", type=Path, default=Path("records/market_events"))
    parser.add_argument("--session-id")
    parser.add_argument("--subscribe-ack-timeout-seconds", type=int, default=30)
    parser.add_argument("--prephase-wait-timeout-seconds", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_qualification_flags_off()
        cohort = LateDeliveryCohort.from_path(args.cohort)
    except (OSError, RuntimeError, ValueError) as error:
        print("late_delivery_capture: FAILED")
        print(f"reason: {type(error).__name__}:{error}")
        return 2
    now = datetime.now(TAIPEI)
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    if not calendar.is_trading_day(now.date()):
        print("late_delivery_capture: SKIPPED")
        print("reason: NOT_A_REVIEWED_TRADING_DAY")
        return 0
    phase = SessionPhase(args.phase)
    phase_start, phase_end = _phase_bounds(now, phase)
    earliest_connect = phase_start - timedelta(seconds=args.prephase_wait_timeout_seconds)
    if not earliest_connect <= now < phase_end:
        print("late_delivery_capture: FAILED")
        print("reason: OUTSIDE_COLLECTION_CONNECTION_WINDOW")
        return 2
    session_id = args.session_id or (
        f"ldev-{now.strftime('%Y%m%dT%H%M%S')}-{phase.value.lower()}-{uuid4().hex[:8]}"
    )
    config = PassiveLateDeliveryCaptureConfig(
        cohort=cohort,
        phase=phase,
        session_id=session_id,
        records_root=args.records_root,
        duration_seconds=args.duration_seconds,
        subscribe_ack_timeout_seconds=args.subscribe_ack_timeout_seconds,
        prephase_wait_timeout_seconds=args.prephase_wait_timeout_seconds,
    )
    try:
        stream = ShioajiMomentumStream.connect_from_env(session_id=session_id)
    except ShioajiLoopbackBindError as error:
        print("late_delivery_capture: FAILED")
        print("mode: PASSIVE_EVIDENCE_ONLY")
        print(f"phase: {phase.value}")
        print("exact_replay: NOT_RUN")
        print(f"reason: {type(error).__name__}:{error}")
        print("safety: flags_off=true subscribe_trade=false order_path=NOT_WIRED")
        print("gate_effect: NONE_HEALTH_POLICY_FRESHNESS_AND_P1_2_UNCHANGED")
        return 2
    result = PassiveLateDeliveryCapture(
        stream,
        config,
        prior_session_date=calendar.previous_trading_day(now.date()),
        calendar_version=f"{calendar.schema_version}:{calendar.source_digest}",
    ).run()
    daily = build_daily_late_delivery_report(args.records_root, now.date())
    daily_path = write_daily_late_delivery_report(
        args.records_root / now.date().isoformat() / "late_delivery_daily_evidence.json",
        daily,
    )
    outcome = (
        "PASS_WITH_WARNINGS"
        if result.status == "COMPLETE_WITH_WARNINGS"
        else "PASS" if result.completed else "FAILED"
    )
    print(f"late_delivery_capture: {outcome}")
    print(f"status: {result.status}")
    print("mode: PASSIVE_EVIDENCE_ONLY")
    print(f"phase: {phase.value}")
    print(f"exact_replay: {result.exact_replay_status}")
    print(f"session: {result.session_dir}")
    print(f"daily_report: {daily_path}")
    if result.evidence_path is not None:
        print(f"evidence: {result.evidence_path}")
    if result.report_path is not None:
        print(f"report: {result.report_path}")
    for reason in result.reasons:
        print(f"reason: {reason}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    print("safety: flags_off=true subscribe_trade=false order_path=NOT_WIRED")
    print("gate_effect: NONE_HEALTH_POLICY_FRESHNESS_AND_P1_2_UNCHANGED")
    return 0 if result.completed else 2


def _phase_bounds(now: datetime, phase: SessionPhase) -> tuple[datetime, datetime]:
    bounds = {
        SessionPhase.OPEN: ((9, 0), (9, 30)),
        SessionPhase.MID: ((10, 30), (11, 0)),
        SessionPhase.CLOSE: ((13, 0), (13, 30)),
    }[phase]
    return (
        now.replace(hour=bounds[0][0], minute=bounds[0][1], second=0, microsecond=0),
        now.replace(hour=bounds[1][0], minute=bounds[1][1], second=0, microsecond=0),
    )


if __name__ == "__main__":
    raise SystemExit(main())
