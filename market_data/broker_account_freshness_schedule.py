"""Calendar/time boundary for broker/account read-only evidence scheduling.

The decision path intentionally imports neither Shioaji nor the capture
implementation. A closed day or off-window invocation therefore has no broker
side effect, credential read, or SDK initialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.freshness_calibration import TAIPEI


@dataclass(frozen=True)
class ScheduledBrokerAccountWindow:
    label: str


SCHEDULED_BROKER_ACCOUNT_WINDOWS: Mapping[tuple[int, int], ScheduledBrokerAccountWindow] = {
    (9, 35): ScheduledBrokerAccountWindow("early_continuous"),
    (10, 30): ScheduledBrokerAccountWindow("continuous"),
    (11, 30): ScheduledBrokerAccountWindow("continuous"),
    (12, 30): ScheduledBrokerAccountWindow("late_continuous"),
    (13, 20): ScheduledBrokerAccountWindow("pre_close"),
}


@dataclass(frozen=True)
class BrokerAccountScheduleDecision:
    status: str
    now: datetime
    scheduled_window: ScheduledBrokerAccountWindow | None
    reason: str

    @property
    def permitted(self) -> bool:
        return self.status == "CAPTURE_PERMITTED"


def decide_scheduled_broker_account_capture(
    now: datetime,
    *,
    calendar: ReviewedEquityCalendar,
) -> BrokerAccountScheduleDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(TAIPEI)
    window = SCHEDULED_BROKER_ACCOUNT_WINDOWS.get((local_now.hour, local_now.minute))
    if window is None:
        return BrokerAccountScheduleDecision(
            status="NO_CAPTURE_OFF_SCHEDULE",
            now=local_now,
            scheduled_window=None,
            reason="no configured broker/account evidence window starts in this minute",
        )
    try:
        is_trading_day = calendar.is_trading_day(local_now.date())
    except ValueError as error:
        return BrokerAccountScheduleDecision(
            status="NO_CAPTURE_CALENDAR_UNAVAILABLE",
            now=local_now,
            scheduled_window=window,
            reason=str(error),
        )
    if not is_trading_day:
        return BrokerAccountScheduleDecision(
            status="NO_CAPTURE_NON_TRADING_DAY",
            now=local_now,
            scheduled_window=window,
            reason="reviewed TWSE calendar marks this date closed",
        )
    return BrokerAccountScheduleDecision(
        status="CAPTURE_PERMITTED",
        now=local_now,
        scheduled_window=window,
        reason="reviewed TWSE calendar and scheduled window both permit capture",
    )
