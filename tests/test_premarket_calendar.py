from datetime import date, datetime

import pytest

from config.premarket import PREMARKET_CONTEXT_V0
from premarket.calendar import CalendarCoverageError, TaifexTradingCalendar


def test_versioned_calendar_includes_annual_and_exceptional_closures() -> None:
    calendar = TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)

    assert calendar.schema_version == "taifex_calendar_2026_v0"
    assert calendar.as_of.date() == date(2026, 8, 19)
    assert not calendar.is_trading_day(date(2026, 2, 12))
    assert not calendar.is_trading_day(date(2026, 7, 10))
    assert calendar.is_trading_day(date(2026, 8, 19))


def test_monday_session_uses_previous_trading_day_not_sunday() -> None:
    calendar = TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)

    window = calendar.session_window(
        date(2026, 8, 24),
        PREMARKET_CONTEXT_V0.query_delay,
    )

    assert window.start.isoformat() == "2026-08-21T15:00:00+08:00"
    assert window.end.isoformat() == "2026-08-22T05:00:00+08:00"
    assert window.query_not_before.isoformat() == "2026-08-22T05:05:00+08:00"


def test_long_holiday_session_is_derived_from_calendar() -> None:
    calendar = TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)

    window = calendar.session_window(
        date(2026, 9, 29),
        PREMARKET_CONTEXT_V0.query_delay,
    )

    assert window.start.isoformat() == "2026-09-24T15:00:00+08:00"
    assert window.end.isoformat() == "2026-09-25T05:00:00+08:00"


def test_trading_date_rolls_after_night_session_opens() -> None:
    calendar = TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)

    before = calendar.trading_date_for(datetime.fromisoformat("2026-08-19T14:59:59+08:00"))
    after = calendar.trading_date_for(datetime.fromisoformat("2026-08-19T15:00:00+08:00"))

    assert before == date(2026, 8, 19)
    assert after == date(2026, 8, 20)


def test_calendar_fails_closed_outside_versioned_coverage() -> None:
    calendar = TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)

    with pytest.raises(CalendarCoverageError):
        calendar.is_trading_day(date(2027, 1, 4))
