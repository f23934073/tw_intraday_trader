"""Tests for ShioajiProvider's snapshot mapping and batching."""

from datetime import date, timedelta
import sys
from types import SimpleNamespace

import pytest

from market_data.provider import (
    MarketDataLimitReached,
    MarketDataTemporarilyUnavailable,
    ShioajiProvider,
    _RollingRequestLimiter,
)
from market_data.models import LocalPaperProductClass
from premarket.calendar import TaifexTradingCalendar
from premarket.models import CompletenessStatus, ContractIdentityStatus
from config.premarket import PREMARKET_CONTEXT_V0


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


def test_stock_contract_readiness_waits_for_automatic_catalog_load():
    contract = SimpleNamespace(code="2330")
    responses = iter((None, None, contract))
    now = [0.0]
    waits: list[float] = []

    class Stocks:
        def __getitem__(self, symbol: str):
            assert symbol == "2330"
            return next(responses)

    api = SimpleNamespace(
        Contracts=SimpleNamespace(Stocks=Stocks()),
    )

    def wait(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    ShioajiProvider._wait_for_stock_contracts(
        api,
        timeout_seconds=1.0,
        poll_seconds=0.1,
        clock=lambda: now[0],
        wait=wait,
    )

    assert waits == [0.1, 0.1]


def test_stock_contract_readiness_timeout_is_explicit():
    now = [0.0]
    api = SimpleNamespace(
        Contracts=SimpleNamespace(Stocks={}),
    )

    def wait(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(RuntimeError, match="股票合約目錄未在 0.2 秒內就緒"):
        ShioajiProvider._wait_for_stock_contracts(
            api,
            timeout_seconds=0.2,
            poll_seconds=0.1,
            clock=lambda: now[0],
            wait=wait,
        )


def test_provider_logs_out_when_stock_contract_catalog_never_becomes_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeAPI:
        def __init__(self) -> None:
            self.logged_out = False

        def login(self, **_kwargs):
            return []

        def logout(self) -> None:
            self.logged_out = True

    api = FakeAPI()
    fake_shioaji = SimpleNamespace(
        __version__="1.7.2",
        Shioaji=lambda **_kwargs: api,
        ShioajiTimeoutError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "shioaji", fake_shioaji)
    monkeypatch.setenv("SHIOAJI_API_KEY", "data-key")
    monkeypatch.setenv("SHIOAJI_SECRET", "data-secret")
    monkeypatch.setattr(
        ShioajiProvider,
        "_wait_for_stock_contracts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("catalog timeout")
        ),
    )

    with pytest.raises(RuntimeError, match="catalog timeout"):
        ShioajiProvider()

    assert api.logged_out is True


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


def test_stock_identity_uses_contract_catalog_without_snapshot_request():
    contract = SimpleNamespace(code="00909", name="國泰數位支付服務")

    class FakeAPI:
        def __init__(self) -> None:
            self.Contracts = SimpleNamespace(Stocks={"00909": contract})

        def snapshots(self, _contracts):
            raise AssertionError("streaming order admission must not require snapshot")

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()

    assert provider.get_stock_identity("00909") == (
        "00909",
        "國泰數位支付服務",
    )


def test_local_paper_descriptor_uses_explicit_shioaji_raw_mapping() -> None:
    contract = SimpleNamespace(
        code="2330",
        name="台積電",
        exchange=SimpleNamespace(value="TSE"),
        security_type=SimpleNamespace(value="STK"),
        category="24",
    )
    provider = object.__new__(ShioajiProvider)
    provider._api = SimpleNamespace(
        Contracts=SimpleNamespace(Stocks={"2330": contract}),
    )
    provider._environment_identity = "shioaji:1.7.2:simulation=true"

    descriptor = provider.get_local_paper_instrument_descriptor("2330")

    assert descriptor.normalized_product_class is LocalPaperProductClass.COMMON_STOCK
    assert descriptor.exchange_raw == "TSE"
    assert descriptor.security_type_raw == "STK"
    assert descriptor.product_category_raw == "24"
    assert descriptor.source_identity.endswith(":TSE:STK:24:2330")


@pytest.mark.parametrize(
    ("symbol", "exchange", "security_type", "category", "expected"),
    [
        ("2330", "TSE", "WRT", "24", LocalPaperProductClass.UNSUPPORTED),
        ("0050", "TSE", "STK", "00", LocalPaperProductClass.UNSUPPORTED),
        ("2330", "OES", "STK", "24", LocalPaperProductClass.UNKNOWN),
        ("2330", "TSE", "UNTESTED", "24", LocalPaperProductClass.UNKNOWN),
        ("2330", "TSE", "STK", "UNTESTED", LocalPaperProductClass.UNKNOWN),
        ("2881A", "TSE", "STK", "17", LocalPaperProductClass.UNSUPPORTED),
    ],
)
def test_local_paper_descriptor_fails_closed_for_non_allowlisted_raw_values(
    symbol: str,
    exchange: str,
    security_type: str,
    category: str,
    expected: LocalPaperProductClass,
) -> None:
    contract = SimpleNamespace(
        code=symbol,
        name="Test",
        exchange=exchange,
        security_type=security_type,
        category=category,
    )
    provider = object.__new__(ShioajiProvider)
    provider._api = SimpleNamespace(
        Contracts=SimpleNamespace(Stocks={symbol: contract}),
    )

    descriptor = provider.get_local_paper_instrument_descriptor(symbol)

    assert descriptor.normalized_product_class is expected


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


def test_kbar_timeout_retries_with_longer_timeout_and_backoff():
    class ShioajiTimeoutError(RuntimeError):
        pass

    class FakeAPI:
        def __init__(self) -> None:
            self.Contracts = SimpleNamespace(Stocks={"2330": object()})
            self.kbar_calls: list[dict[str, object]] = []

        def usage(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                connections=1,
                bytes=0,
                limit_bytes=0,
                remaining_bytes=0,
            )

        def kbars(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kbar_calls.append(kwargs)
            if len(self.kbar_calls) < 3:
                raise ShioajiTimeoutError("fixture timeout")
            return SimpleNamespace(
                ts=[], Open=[], High=[], Low=[], Close=[], Volume=[]
            )

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    provider._kbar_request_limiter = SimpleNamespace(wait=lambda: None)
    sleeps: list[float] = []
    provider._kbar_retry_sleep = sleeps.append

    assert provider.get_kbars(
        "2330",
        date(2026, 8, 1),
        date(2026, 8, 2),
    ) == []

    assert len(provider._api.kbar_calls) == 3
    assert [call["timeout"] for call in provider._api.kbar_calls] == [60_000] * 3
    assert sleeps == [2.0, 5.0]


def test_kbar_timeout_exhaustion_becomes_recoverable_provider_error():
    class ShioajiTimeoutError(RuntimeError):
        pass

    class FakeAPI:
        def __init__(self) -> None:
            self.Contracts = SimpleNamespace(Stocks={"2330": object()})
            self.kbar_calls = 0

        def usage(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                connections=1,
                bytes=0,
                limit_bytes=0,
                remaining_bytes=0,
            )

        def kbars(self, **_kwargs):  # type: ignore[no-untyped-def]
            self.kbar_calls += 1
            raise ShioajiTimeoutError("fixture timeout")

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    provider._kbar_request_limiter = SimpleNamespace(wait=lambda: None)
    provider._kbar_retry_sleep = lambda _seconds: None

    with pytest.raises(MarketDataTemporarilyUnavailable, match="重試 3 次"):
        provider.get_kbars("2330", date(2026, 8, 1), date(2026, 8, 2))

    assert provider._api.kbar_calls == 3


def test_shioaji_taifex_context_uses_contract_info_without_claiming_settlement():
    window = TaifexTradingCalendar.from_path(
        PREMARKET_CONTEXT_V0.calendar_path
    ).session_window(date(2026, 8, 24), timedelta(minutes=5))
    contract = SimpleNamespace(code="TXFR1", target_code="TXFH6")
    info = SimpleNamespace(
        delivery_month="202608",
        last_trading_date=date(2026, 8, 19),
        reference=24000,
        update_date=date(2026, 8, 21),
    )

    class ContractsAPI:
        def __init__(self) -> None:
            self.get_calls: list[str] = []

        def get(self, code: str):
            self.get_calls.append(code)
            return contract

        def info(self, value):  # type: ignore[no-untyped-def]
            assert value is contract
            return info

    class FakeAPI:
        def __init__(self) -> None:
            self.contracts = ContractsAPI()
            self.kbar_calls: list[dict[str, object]] = []
            self.tick_calls: list[dict[str, object]] = []

        def usage(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                connections=1,
                bytes=0,
                limit_bytes=0,
                remaining_bytes=0,
            )

        def kbars(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kbar_calls.append(kwargs)
            return SimpleNamespace(
                ts=[window.start + timedelta(minutes=1), window.end],
                Open=[24000, 24050],
                High=[24100, 24220],
                Low=[23910, 24020],
                Close=[24050, 24180],
                Volume=[10, 20],
            )

        def ticks(self, **kwargs):  # type: ignore[no-untyped-def]
            self.tick_calls.append(kwargs)
            return SimpleNamespace(
                ts=[window.start, window.end - timedelta(minutes=1)],
                close=[24000, 24180],
                volume=[10, 20],
                bid_price=[23999, 24179],
                bid_volume=[1, 1],
                ask_price=[24001, 24181],
                ask_volume=[1, 1],
                tick_type=[1, 2],
            )

    provider = object.__new__(ShioajiProvider)
    provider._api = FakeAPI()
    provider._kbar_request_limiter = SimpleNamespace(wait=lambda: None)
    provider._kbar_retry_sleep = lambda _seconds: None

    observation = provider.get_taifex_night_session(window, "TXFR1")

    assert observation is not None
    assert provider._api.contracts.get_calls == ["TXFR1"]
    assert observation.contract_identity.status is ContractIdentityStatus.RESOLVED_AS_OF_QUERY
    assert observation.contract_identity.resolved_contract_code == "TXFH6"
    assert observation.provider_reference_price == 24000
    assert observation.provider_reference_source == "SHIOAJI_CONTRACT_INFO"
    assert observation.completeness_status is CompletenessStatus.UNKNOWN
    assert observation.completeness_evidence == (
        "SHIOAJI_KBAR_FINALIZATION_UNQUALIFIED",
    )
    assert len(observation.raw_source_digest) == 64
    assert provider._api.kbar_calls[0]["contract"] is contract
    assert "settlement" not in repr(observation).lower()

    capture = provider.capture_taifex_night_qualification(window, "TXFR1")

    assert capture.trading_date == window.trading_date
    assert capture.contract_identity.resolved_contract_code == "TXFH6"
    assert len(capture.bars) == 2
    assert len(capture.ticks) == 2
    assert provider._api.tick_calls == [
        {
            "contract": contract,
            "date": "2026-08-24",
            "timeout": ShioajiProvider.KBAR_REQUEST_TIMEOUT_MS,
        }
    ]
    assert len(capture.raw_source_digest) == 64
