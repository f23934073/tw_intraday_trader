from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.freshness_calibration_schedule import (
    SCHEDULED_QUOTE_WINDOWS,
    run_scheduled_quote_capture,
)


TAIPEI = ZoneInfo("Asia/Taipei")
CALENDAR = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
MANIFEST = Path("research/freshness_calibration/cohort_manifest_2026-08-20_twse_2026-08-19.json")


def scheduled_at(hour: int, minute: int, day: int = 20) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=TAIPEI)


def test_permitted_opening_capture_uses_frozen_cohort_after_ntp_preflight(tmp_path) -> None:
    calls: list[object] = []

    def ntp_preflight() -> dict[str, object]:
        calls.append("ntp")
        return {"successful_samples": 5}

    def capture(**kwargs):
        calls.append(kwargs)
        return tmp_path / "quote.json", {"review_status": "REVIEW_REQUIRED"}

    result = run_scheduled_quote_capture(
        scheduled_at(9, 15),
        calendar=CALENDAR,
        manifest_path=MANIFEST,
        output_directory=tmp_path,
        ntp_preflight=ntp_preflight,
        capture=capture,
    )

    assert result["status"] == "CAPTURED"
    assert calls[0] == "ntp"
    assert calls[1] == {
        "symbol_tiers": {"2886": "high", "6863": "mid", "1530": "low"},
        "session_window": "opening",
        "duration_seconds": 900,
        "output_directory": tmp_path,
    }


def test_closed_session_never_runs_ntp_or_quote_capture() -> None:
    calls: list[str] = []
    result = run_scheduled_quote_capture(
        scheduled_at(9, 15, day=22),
        calendar=CALENDAR,
        manifest_path=MANIFEST,
        ntp_preflight=lambda: calls.append("ntp") or {"successful_samples": 5},
        capture=lambda **_: calls.append("capture"),
    )

    assert result["status"] == "NO_CAPTURE_NON_TRADING_DAY"
    assert calls == []


def test_uncovered_calendar_never_runs_ntp_or_quote_capture() -> None:
    calls: list[str] = []
    result = run_scheduled_quote_capture(
        datetime(2027, 1, 4, 9, 15, tzinfo=TAIPEI),
        calendar=CALENDAR,
        manifest_path=MANIFEST,
        ntp_preflight=lambda: calls.append("ntp") or {"successful_samples": 5},
        capture=lambda **_: calls.append("capture"),
    )

    assert result["status"] == "NO_CAPTURE_CALENDAR_UNAVAILABLE"
    assert calls == []


def test_off_schedule_never_runs_ntp_or_quote_capture() -> None:
    calls: list[str] = []
    result = run_scheduled_quote_capture(
        scheduled_at(9, 14),
        calendar=CALENDAR,
        manifest_path=MANIFEST,
        ntp_preflight=lambda: calls.append("ntp") or {"successful_samples": 5},
        capture=lambda **_: calls.append("capture"),
    )

    assert result["status"] == "NO_CAPTURE_OFF_SCHEDULE"
    assert calls == []


def test_failed_ntp_preflight_never_starts_quote_capture() -> None:
    calls: list[str] = []
    result = run_scheduled_quote_capture(
        scheduled_at(10, 0),
        calendar=CALENDAR,
        manifest_path=MANIFEST,
        ntp_preflight=lambda: {"successful_samples": 4},
        capture=lambda **_: calls.append("capture"),
    )

    assert result["status"] == "NO_CAPTURE_NTP_PREFLIGHT_FAILED"
    assert calls == []


def test_close_boundary_window_is_explicitly_twenty_minutes() -> None:
    assert SCHEDULED_QUOTE_WINDOWS[(13, 15)].session_window == "close"
    assert SCHEDULED_QUOTE_WINDOWS[(13, 15)].duration_seconds == 1_200


def test_accelerated_windows_are_non_overlapping_and_keep_frozen_labels() -> None:
    assert SCHEDULED_QUOTE_WINDOWS == {
        (9, 0): SCHEDULED_QUOTE_WINDOWS[(9, 0)],
        (9, 15): SCHEDULED_QUOTE_WINDOWS[(9, 15)],
        (10, 0): SCHEDULED_QUOTE_WINDOWS[(10, 0)],
        (11, 0): SCHEDULED_QUOTE_WINDOWS[(11, 0)],
        (12, 0): SCHEDULED_QUOTE_WINDOWS[(12, 0)],
        (13, 15): SCHEDULED_QUOTE_WINDOWS[(13, 15)],
    }
    assert [
        (window.session_window, window.duration_seconds)
        for _, window in sorted(SCHEDULED_QUOTE_WINDOWS.items())
    ] == [
        ("opening", 900),
        ("opening", 900),
        ("continuous", 900),
        ("continuous", 900),
        ("continuous", 900),
        ("close", 1_200),
    ]
