"""Fail-closed scheduling boundary for quote-freshness evidence collection.

This module deliberately contains no account, order, trade-callback, or
Portfolio import.  It decides whether a scheduled Tick/BidAsk capture may run
before the live Shioaji quote-capture function is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
import json
from zoneinfo import ZoneInfo

from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = ZoneInfo("Asia/Taipei")
FROZEN_MANIFEST_PATH = Path(
    "research/freshness_calibration/cohort_manifest_2026-08-20_twse_2026-08-19.json"
)


@dataclass(frozen=True)
class ScheduledQuoteWindow:
    session_window: str
    duration_seconds: int
    launch_grace_seconds: int = 300


SCHEDULED_QUOTE_WINDOWS: Mapping[tuple[int, int], ScheduledQuoteWindow] = {
    (9, 0): ScheduledQuoteWindow("opening", 900),
    (9, 15): ScheduledQuoteWindow("opening", 900),
    (10, 0): ScheduledQuoteWindow("continuous", 900),
    (11, 0): ScheduledQuoteWindow("continuous", 900),
    (12, 0): ScheduledQuoteWindow("continuous", 900),
    # Start inside the frozen close label, then retain five minutes after 13:30
    # solely to observe the session boundary. It does not choose a threshold.
    (13, 15): ScheduledQuoteWindow("close", 1_200),
}


@dataclass(frozen=True)
class ScheduleDecision:
    status: str
    now: datetime
    scheduled_window: ScheduledQuoteWindow | None
    scheduled_for: datetime | None
    launch_delay_seconds: float | None
    reason: str

    @property
    def permitted(self) -> bool:
        return self.status == "CAPTURE_PERMITTED"


class FrozenManifestError(ValueError):
    """The unattended campaign must not run against an altered cohort."""


def decide_scheduled_quote_capture(
    now: datetime,
    *,
    calendar: ReviewedEquityCalendar,
) -> ScheduleDecision:
    """Return a no-provider decision for this local time and reviewed calendar."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(TAIPEI)
    scheduled_for: datetime | None = None
    window: ScheduledQuoteWindow | None = None
    launch_delay_seconds: float | None = None
    for (hour, minute), candidate in sorted(SCHEDULED_QUOTE_WINDOWS.items(), reverse=True):
        candidate_scheduled_for = local_now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        candidate_delay_seconds = (local_now - candidate_scheduled_for).total_seconds()
        if 0 <= candidate_delay_seconds <= candidate.launch_grace_seconds:
            scheduled_for = candidate_scheduled_for
            window = candidate
            launch_delay_seconds = candidate_delay_seconds
            break
    if window is None:
        return ScheduleDecision(
            status="NO_CAPTURE_OFF_SCHEDULE",
            now=local_now,
            scheduled_window=None,
            scheduled_for=None,
            launch_delay_seconds=None,
            reason="no configured quote-evidence window starts within its bounded late-launch grace",
        )
    try:
        is_trading_day = calendar.is_trading_day(local_now.date())
    except ValueError as error:
        return ScheduleDecision(
            status="NO_CAPTURE_CALENDAR_UNAVAILABLE",
            now=local_now,
            scheduled_window=window,
            scheduled_for=scheduled_for,
            launch_delay_seconds=launch_delay_seconds,
            reason=str(error),
        )
    if not is_trading_day:
        return ScheduleDecision(
            status="NO_CAPTURE_NON_TRADING_DAY",
            now=local_now,
            scheduled_window=window,
            scheduled_for=scheduled_for,
            launch_delay_seconds=launch_delay_seconds,
            reason="reviewed TWSE calendar marks this date closed",
        )
    return ScheduleDecision(
        status="CAPTURE_PERMITTED",
        now=local_now,
        scheduled_window=window,
        scheduled_for=scheduled_for,
        launch_delay_seconds=launch_delay_seconds,
        reason="reviewed TWSE calendar and scheduled window permit capture within bounded launch grace",
    )


def load_frozen_cohort(manifest_path: Path) -> dict[str, str]:
    """Load the exact cohort labels without allowing scheduler-side edits."""
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FrozenManifestError(f"cannot load frozen cohort manifest: {error}") from error
    if raw.get("status") != "FROZEN_FOR_COLLECTION":
        raise FrozenManifestError("cohort manifest is not frozen for collection")
    entries = raw.get("symbols")
    if not isinstance(entries, list):
        raise FrozenManifestError("cohort manifest symbols must be a list")
    cohort: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise FrozenManifestError("cohort manifest symbol entry must be an object")
        symbol = entry.get("symbol")
        tier = entry.get("liquidity_tier")
        if not isinstance(symbol, str) or not isinstance(tier, str):
            raise FrozenManifestError("cohort manifest symbol and tier must be strings")
        if not symbol.strip() or not tier.strip() or symbol in cohort:
            raise FrozenManifestError("cohort manifest has an empty or duplicate symbol")
        cohort[symbol] = tier
    if cohort != {"2886": "high", "6863": "mid", "1530": "low"}:
        raise FrozenManifestError("cohort manifest does not match the approved frozen cohort")
    return cohort


CaptureFunction = Callable[..., tuple[Path, dict[str, object]]]
NtpPreflightFunction = Callable[[], dict[str, object]]


def run_scheduled_quote_capture(
    now: datetime,
    *,
    calendar: ReviewedEquityCalendar,
    manifest_path: Path = FROZEN_MANIFEST_PATH,
    output_directory: Path = Path("research/captures/freshness_quote"),
    ntp_preflight: NtpPreflightFunction,
    capture: CaptureFunction,
) -> dict[str, object]:
    """Run one permitted quote capture, otherwise return a no-capture outcome.

    The calendar decision precedes manifest parsing, NTP, and the supplied
    capture callable. Callers can therefore prove no provider path was entered
    on closed or uncovered dates.
    """
    decision = decide_scheduled_quote_capture(now, calendar=calendar)
    result: dict[str, object] = {
        "status": decision.status,
        "now": decision.now.isoformat(),
        "reason": decision.reason,
        "session_window": (
            decision.scheduled_window.session_window
            if decision.scheduled_window is not None
            else None
        ),
        "scheduled_for": (
            decision.scheduled_for.isoformat()
            if decision.scheduled_for is not None
            else None
        ),
        "launch_delay_seconds": decision.launch_delay_seconds,
    }
    if not decision.permitted:
        return result

    assert decision.scheduled_window is not None
    cohort = load_frozen_cohort(manifest_path)
    preflight = ntp_preflight()
    successful_samples = preflight.get("successful_samples")
    if successful_samples != 5:
        result.update(
            status="NO_CAPTURE_NTP_PREFLIGHT_FAILED",
            reason="five successful read-only NTP samples are required before quote capture",
            ntp_preflight=preflight,
        )
        return result

    artifact, review = capture(
        symbol_tiers=cohort,
        session_window=decision.scheduled_window.session_window,
        duration_seconds=decision.scheduled_window.duration_seconds,
        output_directory=output_directory,
    )
    result.update(
        status="CAPTURED",
        artifact=str(artifact),
        review=review,
        ntp_preflight=preflight,
        duration_seconds=decision.scheduled_window.duration_seconds,
    )
    return result
