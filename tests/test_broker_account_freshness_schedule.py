from datetime import datetime

from config import twse_calendar_2026
from market_data.broker_account_freshness_schedule import (
    SCHEDULED_BROKER_ACCOUNT_WINDOWS,
    decide_scheduled_broker_account_capture,
)
from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = datetime.fromisoformat("2026-08-24T09:35:00+08:00").tzinfo
assert TAIPEI is not None


def calendar() -> ReviewedEquityCalendar:
    return ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)


def test_schedule_is_accelerated_but_bounded_to_five_spaced_windows() -> None:
    assert list(SCHEDULED_BROKER_ACCOUNT_WINDOWS) == [
        (9, 35), (10, 30), (11, 30), (12, 30), (13, 20)
    ]
    decision = decide_scheduled_broker_account_capture(
        datetime(2026, 8, 24, 9, 35, tzinfo=TAIPEI),
        calendar=calendar(),
    )
    assert decision.permitted
    assert decision.scheduled_window is not None
    assert decision.scheduled_window.label == "early_continuous"


def test_schedule_fails_closed_for_closed_or_unplanned_time() -> None:
    closed = decide_scheduled_broker_account_capture(
        datetime(2026, 8, 22, 9, 35, tzinfo=TAIPEI),
        calendar=calendar(),
    )
    off_schedule = decide_scheduled_broker_account_capture(
        datetime(2026, 8, 24, 9, 36, tzinfo=TAIPEI),
        calendar=calendar(),
    )
    assert closed.status == "NO_CAPTURE_NON_TRADING_DAY"
    assert not closed.permitted
    assert off_schedule.status == "NO_CAPTURE_OFF_SCHEDULE"
    assert not off_schedule.permitted
