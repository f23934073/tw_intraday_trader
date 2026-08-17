"""Tests for ShioajiProvider's snapshot mapping and batching."""

from types import SimpleNamespace

from market_data.provider import ShioajiProvider


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
