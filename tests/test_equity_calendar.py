from datetime import date

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar


def test_reviewed_twse_calendar_covers_qualification_session() -> None:
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)

    assert calendar.schema_version == "twse_calendar_2026_v1"
    assert calendar.is_trading_day(date(2026, 8, 20)) is True
    assert calendar.previous_trading_day(date(2026, 8, 20)) == date(2026, 8, 19)
    assert calendar.next_trading_day(date(2026, 8, 21)) == date(2026, 8, 24)
    assert calendar.next_trading_day(date(2026, 9, 24)) == date(2026, 9, 29)
    assert calendar.is_trading_day(date(2026, 7, 10)) is False
    assert len(calendar.source_urls) == 2


def test_reviewed_twse_calendar_rejects_closed_source_and_missing_next_session() -> None:
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)

    try:
        calendar.next_trading_day(date(2026, 8, 22))
    except ValueError as error:
        assert "source session" in str(error)
    else:
        raise AssertionError("closed source session must fail")

    try:
        calendar.next_trading_day(date(2026, 12, 31))
    except ValueError as error:
        assert "no next" in str(error)
    else:
        raise AssertionError("calendar coverage boundary must fail")
