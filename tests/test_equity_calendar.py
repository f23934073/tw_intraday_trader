from datetime import date

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar


def test_reviewed_twse_calendar_covers_qualification_session() -> None:
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)

    assert calendar.schema_version == "twse_calendar_2026_v1"
    assert calendar.is_trading_day(date(2026, 8, 20)) is True
    assert calendar.previous_trading_day(date(2026, 8, 20)) == date(2026, 8, 19)
    assert calendar.is_trading_day(date(2026, 7, 10)) is False
    assert len(calendar.source_urls) == 2
