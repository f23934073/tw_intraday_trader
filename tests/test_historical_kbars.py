"""Focused tests for source-backed historical Kbar support."""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from dashboard.service import DashboardService
from market_data.provider import MockProvider, ShioajiProvider


class RecordingMockProvider(MockProvider):
    """記錄 Kbar 請求區間，驗證長週期不會交給來源一次查完。"""

    def __init__(self) -> None:
        super().__init__()
        self.kbar_requests: list[tuple[date, date]] = []

    def get_kbars(self, symbol: str, start: date, end: date):
        self.kbar_requests.append((start, end))
        return super().get_kbars(symbol, start, end)


def test_mock_history_has_intraday_and_daily_resolutions():
    service = DashboardService(MockProvider())

    intraday = service.candidate_history("3231", "1d")
    daily = service.candidate_history("3231", "20d")

    assert intraday["status"] == "ready"
    assert intraday["resolution"] == "5分鐘"
    assert len(intraday["candles"]) == 54
    assert intraday["candles"][-1]["close"] == 105.5
    assert daily["status"] == "ready"
    assert daily["resolution"] == "日"
    assert len(daily["candles"]) == 20


def test_shioaji_kbar_mapping_preserves_ohlcv_and_taipei_wall_time():
    # Shioaji's documented 2026-05-18 09:01 Kbar numeric timestamp.
    timestamp = 1_779_094_860_000_000_000
    raw_kbars = SimpleNamespace(
        ts=[timestamp],
        Open=[104.0],
        High=[106.0],
        Low=[103.5],
        Close=[105.5],
        Volume=[180_000],
    )

    bars = ShioajiProvider._map_kbars(raw_kbars)

    assert len(bars) == 1
    assert bars[0].timestamp == datetime(
        2026,
        5,
        18,
        9,
        1,
        tzinfo=ZoneInfo("Asia/Taipei"),
    )
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close) == (104.0, 106.0, 103.5, 105.5)
    assert bars[0].volume == 180_000


def test_three_month_history_batches_requests_and_keeps_ma_warmup():
    provider = RecordingMockProvider()
    history = DashboardService(provider).candidate_history("3231", "3m")

    assert history["status"] == "ready"
    assert history["resolution"] == "日"
    assert len(history["candles"]) == 65
    assert len(provider.kbar_requests) > 1
    assert all((end - start).days <= 29 for start, end in provider.kbar_requests)

    first, last = history["candles"][0], history["candles"][-1]
    assert first["ma5"] is not None
    assert first["ma20"] is not None
    assert first["ma60"] is not None
    assert last["ma5"] == round(
        sum(candle["close"] for candle in history["candles"][-5:]) / 5,
        4,
    )
