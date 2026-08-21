"""Tests for Shioaji Tick/BidAsk normalization and local simulation consumption."""

from datetime import date, datetime, timedelta
from threading import RLock
from time import monotonic, sleep
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider, ShioajiProvider
from simulation.service import SimulationService


_TAIPEI = ZoneInfo("Asia/Taipei")


class StreamingMockProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None
        self.synced_symbols: list[set[str]] = []
        self.stopped = False

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        self.synced_symbols.append(set(symbols))
        return set(symbols)

    def stop_quote_stream(self) -> None:
        self.stopped = True
        self.sync_quote_subscriptions(set())

    def emit(self, update: RealtimeQuoteUpdate) -> None:
        assert self.handler is not None
        self.handler(update)


class SnapshotlessStreamingProvider(StreamingMockProvider):
    def get_stock(self, symbol: str):
        raise AssertionError("streaming order admission must not require snapshot")

    def get_stock_identity(self, symbol: str) -> tuple[str, str]:
        return symbol, "緯創"


class FailedStreamingProvider(SnapshotlessStreamingProvider):
    def start_quote_stream(self, handler) -> None:
        raise RuntimeError("fixture stream failed")


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("quote worker did not reach the expected state")


def quote_update(
    *,
    kind: str,
    at: datetime,
    last_price: float | None = None,
    bid_price: float | None = None,
    ask_price: float | None = None,
    received_at: datetime | None = None,
) -> RealtimeQuoteUpdate:
    return RealtimeQuoteUpdate(
        symbol="3231",
        kind=kind,
        exchange_timestamp=at,
        received_at=received_at or datetime.now(_TAIPEI),
        last_price=last_price,
        bid_price=bid_price,
        ask_price=ask_price,
    )


def test_streaming_buy_waits_for_bidask_then_marks_position_from_ticks():
    provider = StreamingMockProvider()
    service = SimulationService(provider, starting_cash=300_000)

    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="stream-buy",
    )

    assert order["status"] == "PENDING"
    assert provider.synced_symbols[-1] == {"3231"}

    book_at = datetime.now(_TAIPEI)
    provider.emit(
        quote_update(
            kind="BIDASK",
            at=book_at,
            bid_price=105.4,
            ask_price=105.6,
        )
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    assert service.orders()[0]["filled_price"] == 105.6
    provider.emit(quote_update(kind="TICK", at=book_at, last_price=106.0))
    wait_until(lambda: service.positions()[0]["current_price"] == 106.0)

    position = service.positions()[0]
    assert position["bid_price"] == 105.4
    assert position["ask_price"] == 105.6
    assert position["unrealized_pnl"] == pytest.approx(400.0)
    assert position["quote_source"] == "SHIOAJI_TICK_BIDASK"
    assert service.session()["subscribed_symbols"] == ["3231"]

    service.close()
    assert provider.stopped is True
    assert provider.synced_symbols[-1] == set()


def test_streaming_order_admission_uses_contract_identity_without_snapshot():
    provider = SnapshotlessStreamingProvider()
    service = SimulationService(provider, starting_cash=300_000)

    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="snapshotless-stream-buy",
    )

    assert order["status"] == "PENDING"
    assert provider.synced_symbols[-1] == {"3231"}

    provider.emit(
        quote_update(
            kind="BIDASK",
            at=datetime.now(_TAIPEI),
            bid_price=105.4,
            ask_price=105.6,
        )
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")
    assert service.positions()[0]["current_price"] == 105.6
    service.close()


def test_pending_stream_order_explains_quote_wait_and_limit_condition():
    provider = SnapshotlessStreamingProvider()
    service = SimulationService(provider, starting_cash=300_000)

    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=100.0,
        idempotency_key="explain-pending-stream-buy",
    )

    assert order["waiting_reason"] == "WAITING_FOR_FIRST_BIDASK"
    assert order["bid_price"] is None
    assert order["ask_price"] is None

    provider.emit(
        quote_update(
            kind="BIDASK",
            at=datetime.now(_TAIPEI),
            bid_price=105.4,
            ask_price=105.6,
        )
    )
    wait_until(lambda: service.orders()[0]["ask_price"] == 105.6)

    pending = service.orders()[0]
    assert pending["status"] == "PENDING"
    assert pending["waiting_reason"] == "LIMIT_NOT_REACHED"
    assert pending["bid_price"] == 105.4
    assert pending["last_quote_at"] is not None
    service.close()


def test_failed_stream_blocks_new_order_risk_snapshot():
    service = SimulationService(FailedStreamingProvider())

    assert service.risk_snapshot("3231")["data_health_state"] == "BLOCKED"

    service.close()


def test_streaming_sell_uses_best_bid_and_ignores_older_tick():
    provider = StreamingMockProvider()
    service = SimulationService(provider, starting_cash=300_000)
    now = datetime.now(_TAIPEI)
    service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="buy-before-stream-sell",
    )
    provider.emit(
        quote_update(
            kind="BIDASK",
            at=now,
            bid_price=105.4,
            ask_price=105.5,
        )
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    provider.emit(quote_update(kind="TICK", at=now, last_price=106.0))
    provider.emit(
        quote_update(
            kind="TICK",
            at=now - timedelta(seconds=1),
            last_price=104.0,
        )
    )
    wait_until(lambda: service.positions()[0]["current_price"] == 106.0)

    sold, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=105.0,
        idempotency_key="stream-sell",
    )

    assert sold["status"] == "FILLED"
    assert sold["filled_price"] == 105.4
    assert service.positions() == []
    assert service.session()["available_cash"] == 299_900.0
    service.close()


def test_fresh_tick_does_not_allow_fill_against_ten_second_old_book() -> None:
    provider = StreamingMockProvider()
    at = datetime.fromisoformat("2026-08-21T10:30:00+08:00")
    clock = MutableClock(at)
    service = SimulationService(provider, starting_cash=300_000, clock=clock)
    buy, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=106.0,
        idempotency_key="owned-stream-buy",
        origin="STRATEGY_AUTOMATED",
        strategy_id="momentum_acceleration_local_paper",
        strategy_version="entry-v1",
    )
    assert buy["status"] == "PENDING"
    provider.emit(
        quote_update(
            kind="BIDASK",
            at=at,
            received_at=at,
            bid_price=105.4,
            ask_price=105.5,
        )
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    clock.value = at + timedelta(seconds=10)
    provider.emit(
        quote_update(
            kind="TICK",
            at=clock.now(),
            received_at=clock.now(),
            last_price=105.4,
        )
    )
    wait_until(
        lambda: service.positions()[0]["quote_received_at"] == clock.now().isoformat()
    )

    sell, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price=105.0,
        idempotency_key="stale-book-stream-sell",
        origin="STRATEGY_AUTOMATED",
        strategy_id="momentum_acceleration_local_paper",
        strategy_version="exit-v1",
    )

    assert sell["status"] == "PENDING"
    assert sell["waiting_reason"] == "WAITING_FOR_FRESH_BIDASK"
    assert service.positions()[0]["book_received_at"] == at.isoformat()
    service.close()


def test_pending_order_cancellation_removes_stream_subscription():
    provider = StreamingMockProvider()
    service = SimulationService(provider)
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price=100.0,
        idempotency_key="pending-stream-buy",
    )

    service.cancel_order(order["order_id"], "cancel-stream-buy")

    assert provider.synced_symbols[-1] == set()
    assert service.session()["subscribed_symbols"] == []
    service.close()


class FakeShioajiStreamAPI:
    def __init__(self) -> None:
        self.Contracts = SimpleNamespace(
            Stocks={"2330": SimpleNamespace(code="2330")},
        )
        self.subscriptions: list[tuple[str, str]] = []
        self.unsubscriptions: list[tuple[str, str]] = []
        self.tick_callback = None
        self.bidask_callback = None
        self.tick_cleared = False
        self.bidask_cleared = False
        self.logged_out = False

    def set_on_tick_stk_v1_callback(self, callback) -> None:
        self.tick_callback = callback

    def set_on_bidask_stk_v1_callback(self, callback) -> None:
        self.bidask_callback = callback

    def clear_on_tick_stk_v1_callback(self) -> None:
        self.tick_cleared = True

    def clear_on_bidask_stk_v1_callback(self) -> None:
        self.bidask_cleared = True

    def subscribe(self, contract, quote_type: str) -> None:
        self.subscriptions.append((contract.code, quote_type))

    def unsubscribe(self, contract, quote_type: str) -> None:
        self.unsubscriptions.append((contract.code, quote_type))

    def logout(self) -> None:
        self.logged_out = True


def make_stream_provider() -> tuple[ShioajiProvider, FakeShioajiStreamAPI]:
    provider = object.__new__(ShioajiProvider)
    api = FakeShioajiStreamAPI()
    provider._api = api
    provider._stream_lock = RLock()
    provider._stream_handler = None
    provider._streaming_symbols = set()
    return provider, api


def test_shioaji_provider_normalizes_callbacks_and_syncs_pairs_once():
    provider, api = make_stream_provider()
    updates: list[RealtimeQuoteUpdate] = []
    provider.start_quote_stream(updates.append)

    assert provider.sync_quote_subscriptions({"2330"}) == {"2330"}
    assert provider.sync_quote_subscriptions({"2330"}) == {"2330"}
    assert api.subscriptions == [("2330", "tick"), ("2330", "bid_ask")]

    api.tick_callback(
        "TSE",
        SimpleNamespace(
            code="2330",
            close="980.5",
            datetime=(2026, 8, 18, 9, 30, 0, 123456),
            intraday_odd=False,
        ),
    )
    api.bidask_callback(
        "TSE",
        SimpleNamespace(
            code="2330",
            bid_price=["980", "979"],
            bid_volume=[3, 4],
            ask_price=["981", "982"],
            ask_volume=[5, 6],
            datetime=(2026, 8, 18, 9, 30, 1, 0),
            intraday_odd=False,
        ),
    )

    assert [update.kind for update in updates] == ["TICK", "BIDASK"]
    assert updates[0].last_price == 980.5
    assert updates[1].bid_price == 980.0
    assert updates[1].ask_price == 981.0
    assert updates[1].bid_volume_lots == 3
    assert updates[1].ask_volume_lots == 5
    assert updates[0].exchange_timestamp.utcoffset() == timedelta(hours=8)

    provider.stop_quote_stream()
    assert api.unsubscriptions == [("2330", "tick"), ("2330", "bid_ask")]
    assert api.tick_cleared is True
    assert api.bidask_cleared is True


def test_shioaji_provider_close_stops_stream_and_logs_out():
    provider, api = make_stream_provider()
    provider.start_quote_stream(lambda update: None)
    provider.sync_quote_subscriptions({"2330"})

    provider.close()

    assert provider._streaming_symbols == set()
    assert api.logged_out is True
