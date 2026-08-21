"""Tests for the read-only dashboard snapshot."""

from datetime import datetime

from config.premarket import PREMARKET_CONTEXT_V0
from dashboard.service import DashboardService
from market_data.provider import MarketDataUsage, MockProvider
from premarket.artifacts import InMemoryPremarketArtifactRepository
from premarket.calendar import TaifexTradingCalendar
from premarket.service import PremarketContextService


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


def test_dashboard_provider_usage_marks_exhausted_shioaji_allowance() -> None:
    class ExhaustedUsageProvider(MockProvider):
        def market_data_usage(self) -> MarketDataUsage:
            return MarketDataUsage(
                connections=2,
                bytes_used=529_961_576,
                limit_bytes=524_288_000,
                remaining_bytes=-5_673_576,
            )

    usage = DashboardService(ExhaustedUsageProvider()).provider_usage()

    assert usage == {
        "provider": "ExhaustedUsageProvider",
        "supported": True,
        "exhausted": True,
        "connections": 2,
        "bytes_used": 529_961_576,
        "limit_bytes": 524_288_000,
        "remaining_bytes": -5_673_576,
    }


def test_dashboard_provider_usage_is_unsupported_for_mock_provider() -> None:
    assert DashboardService(MockProvider()).provider_usage() == {
        "provider": "MockProvider",
        "supported": False,
        "exhausted": False,
        "connections": None,
        "bytes_used": None,
        "limit_bytes": None,
        "remaining_bytes": None,
    }


def test_realtime_candidate_snapshot_skips_premarket_projection() -> None:
    class FailingPremarket:
        def projection(self):  # type: ignore[no-untyped-def]
            raise AssertionError("realtime candidate scan must not load premarket")

    snapshot = DashboardService(
        MockProvider(),
        premarket_service=FailingPremarket(),  # type: ignore[arg-type]
    ).realtime_candidate_snapshot()

    assert {candidate["symbol"] for candidate in snapshot["candidates"]} >= {
        "3231",
        "2376",
    }


def _premarket_service(provider: MockProvider) -> PremarketContextService:
    return PremarketContextService(
        source=provider,
        calendar=TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path),
        config=PREMARKET_CONTEXT_V0,
        artifacts=InMemoryPremarketArtifactRepository(),
        now=lambda: datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
    )


def test_dashboard_adds_observation_only_premarket_projection() -> None:
    provider = MockProvider()
    service = DashboardService(
        provider,
        premarket_service=_premarket_service(provider),
    )

    snapshot = service.refresh()

    assert snapshot["premarket_context"]["status"] == "READY"
    assert snapshot["premarket_context"]["metrics"]["session_move_pct"] == 0.75
    assert snapshot["premarket_context"]["reconciliation"]["status"] == "PENDING"
    assert snapshot["market"]["loaded_symbols"] == 5
    assert {candidate["symbol"] for candidate in snapshot["candidates"]} >= {"3231", "2376"}


def test_premarket_failure_does_not_block_stock_snapshot() -> None:
    class FailingPremarketMock(MockProvider):
        def get_taifex_night_session(self, window, contract_alias):  # type: ignore[no-untyped-def]
            raise RuntimeError("fixture failure")

    provider = FailingPremarketMock()
    service = DashboardService(
        provider,
        premarket_service=_premarket_service(provider),
    )

    snapshot = service.refresh()

    assert snapshot["premarket_context"]["status"] == "UNAVAILABLE"
    assert snapshot["premarket_context"]["health"]["reasons"] == ["SOURCE_QUERY_FAILED"]
    assert snapshot["market"]["loaded_symbols"] == 5
