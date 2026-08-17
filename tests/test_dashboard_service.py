"""Tests for the read-only dashboard snapshot."""

from dashboard.service import DashboardService
from market_data.provider import MockProvider


def test_dashboard_snapshot_uses_existing_scan_decisions():
    snapshot = DashboardService(MockProvider()).refresh()

    assert snapshot["provider"] == {
        "name": "MockProvider",
        "mode": "snapshot",
        "streaming": False,
    }
    assert snapshot["market"]["loaded_symbols"] == 5

    candidates = {candidate["symbol"]: candidate for candidate in snapshot["candidates"]}
    assert candidates["3231"]["sources"] == ["AUTO", "MANUAL"]
    assert candidates["3231"]["matched_rules"] == ["gap_up", "high_volume"]
    assert candidates["3231"]["score"]["total"] == 40
    assert candidates["3231"]["score"]["max"] == 40

    assert len(snapshot["positions"]) == 1
    position = snapshot["positions"][0]
    assert position["symbol"] == "2317"
    assert position["exit"]["decision"] == "HOLD"
    assert position["exit"]["stop_price"] == 200.9
    assert position["exit"]["take_profit_price"] == 211.15


def test_dashboard_candidate_history_uses_provider_kbars_on_demand():
    service = DashboardService(MockProvider())

    history = service.candidate_history("3231", "5d")

    assert history["symbol"] == "3231"
    assert history["period"] == "5d"
    assert history["resolution"] == "日"
    assert history["status"] == "ready"
    assert len(history["candles"]) == 5
    assert history["display_start"] == history["candles"][0]["timestamp"][:10]
    assert history["display_end"] == history["candles"][-1]["timestamp"][:10]
    assert history["candles"][-1]["close"] == 105.5
    assert history is service.candidate_history("3231", "5d")


def test_dashboard_snapshot_is_cached_until_explicit_refresh():
    service = DashboardService(MockProvider())

    first = service.snapshot()
    second = service.snapshot()

    assert first is second
