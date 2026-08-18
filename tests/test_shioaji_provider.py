"""Tests for ShioajiProvider's snapshot mapping and batching."""

from datetime import date
from types import SimpleNamespace

import pytest

from market_data.provider import (
    MarketDataLimitReached,
    ShioajiProvider,
    _RollingRequestLimiter,
)


def make_provider(tse: list[object], otc: list[object], snapshots: list[object]):
    class FakeAPI:
        def __init__(self):
            self.Contracts = SimpleNamespace(
                Stocks=SimpleNamespace(TSE=tse, OTC=otc),
            )
            self.snapshot_batches: list[list[object]] = []

        def snapshots(self, contracts):
            self.snapshot_batches.append(contracts)
            return snapshots[:len(contracts)]

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    return provider


def test_snapshot_mapping_uses_cumulative_and_reference_fields():
    provider = object.__new__(ShioajiProvider)
    snapshot = SimpleNamespace(
        close=105.0,
        change_price=5.0,
        open=104.0,
        high=106.0,
        low=103.0,
        total_volume=120_000,
        yesterday_volume=80_000,
        average_price=104.5,
        volume_ratio=1.5,
    )
    contract = SimpleNamespace(code="6231", name="系微", exchange="OTC")

    stock = provider._snap_to_stock(snapshot, contract)

    assert stock.volume == 120_000
    assert stock.previous_day_volume == 80_000
    assert stock.vwap == 104.5
    assert stock.relative_volume == 1.5
    assert stock.market == "TPEX"


def test_market_snapshot_queries_include_tse_and_otc():
    tse = [SimpleNamespace(code="2330", name="台積電", exchange="TSE")]
    otc = [SimpleNamespace(code="6231", name="系微", exchange="OTC")]
    snapshots = [
        SimpleNamespace(
            close=980.0,
            change_price=20.0,
            open=975.0,
            high=985.0,
            low=970.0,
            total_volume=300_000,
            yesterday_volume=280_000,
            average_price=978.0,
            volume_ratio=1.07,
        ),
        SimpleNamespace(
            close=100.0,
            change_price=2.0,
            open=99.0,
            high=101.0,
            low=98.0,
            total_volume=10_000,
            yesterday_volume=8_000,
            average_price=99.5,
            volume_ratio=1.25,
        ),
    ]
    provider = make_provider(tse, otc, snapshots)

    stocks = provider.get_market_stocks()

    assert {stock.symbol for stock in stocks} == {"2330", "6231"}
    assert [len(batch) for batch in provider._api.snapshot_batches] == [2]


def test_market_snapshot_queries_are_batched_at_500_contracts():
    contracts = [
        SimpleNamespace(code=str(index), name="Test", exchange="TSE")
        for index in range(501)
    ]
    snapshots = [
        SimpleNamespace(
            close=100.0,
            change_price=0.0,
            open=100.0,
            high=100.0,
            low=100.0,
            total_volume=1,
            yesterday_volume=1,
            average_price=100.0,
            volume_ratio=1.0,
        )
        for _ in contracts
    ]
    provider = make_provider(contracts, [], snapshots)

    stocks = provider.get_market_stocks()

    assert len(stocks) == 501
    assert [len(batch) for batch in provider._api.snapshot_batches] == [500, 1]


def test_kbar_rate_limiter_waits_before_exceeding_safe_window():
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = _RollingRequestLimiter(
        max_calls=2,
        window_seconds=10.0,
        clock=lambda: now[0],
        sleep=sleep,
    )

    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert sleeps == [10.0]


def test_shioaji_usage_is_normalized_and_low_quota_blocks_kbar_request():
    class FakeAPI:
        def __init__(self) -> None:
            self.Contracts = SimpleNamespace(Stocks={"2330": object()})
            self.kbar_calls = 0

        def usage(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                connections=1,
                bytes=510 * 1024 * 1024,
                limit_bytes=512 * 1024 * 1024,
                remaining_bytes=2 * 1024 * 1024,
            )

        def kbars(self, **_kwargs):  # type: ignore[no-untyped-def]
            self.kbar_calls += 1
            return SimpleNamespace(ts=[])

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    provider._kbar_request_limiter = SimpleNamespace(wait=lambda: None)

    usage = provider.market_data_usage()

    assert usage is not None
    assert usage.bytes_used == 510 * 1024 * 1024
    assert usage.remaining_bytes == 2 * 1024 * 1024
    with pytest.raises(MarketDataLimitReached, match="剩餘流量"):
        provider.get_kbars("2330", date(2026, 8, 1), date(2026, 8, 2))
    assert provider._api.kbar_calls == 0


def test_empty_kbar_response_rechecks_usage_and_detects_exhaustion():
    class FakeAPI:
        def __init__(self) -> None:
            self.Contracts = SimpleNamespace(Stocks={"2330": object()})
            self.usage_calls = 0

        def usage(self):  # type: ignore[no-untyped-def]
            self.usage_calls += 1
            remaining = 100 * 1024 * 1024 if self.usage_calls == 1 else 0
            return SimpleNamespace(
                connections=1,
                bytes=512 * 1024 * 1024 - remaining,
                limit_bytes=512 * 1024 * 1024,
                remaining_bytes=remaining,
            )

        def kbars(self, **_kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                ts=[], Open=[], High=[], Low=[], Close=[], Volume=[]
            )

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    provider._kbar_request_limiter = SimpleNamespace(wait=lambda: None)

    with pytest.raises(MarketDataLimitReached, match="剩餘流量"):
        provider.get_kbars("2330", date(2026, 8, 1), date(2026, 8, 2))

    assert provider._api.usage_calls == 2
