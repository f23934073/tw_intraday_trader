from __future__ import annotations

from datetime import date, datetime, timedelta
import sys
from threading import Event, Lock, Thread
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.momentum_stream import StreamLifecycleEventType
from market_data.shioaji_momentum_stream import ShioajiMomentumStream


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class ScriptedClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)
        self._lock = Lock()

    def now(self) -> datetime:
        with self._lock:
            return next(self._values)


class BlockingTick:
    def __init__(self, entered: Event, release: Event) -> None:
        self._raw = raw_tick()
        self._entered = entered
        self._release = release

    @property
    def close(self) -> str:
        self._entered.set()
        if not self._release.wait(timeout=1):
            raise RuntimeError("test did not release Tick mapping")
        return self._raw.close

    def __getattr__(self, name: str):
        return getattr(self._raw, name)


class FakeAPI:
    def __init__(self) -> None:
        contract = SimpleNamespace(
            code="8039",
            name="乙盛-KY",
            security_type=SimpleNamespace(value="STOCK"),
            exchange=SimpleNamespace(value="TSE"),
            reference="258.5",
            limit_up="284.5",
            limit_down="232.5",
            unit=1000,
            update_date=SESSION_DATE,
        )
        self.Contracts = SimpleNamespace(Stocks={"8039": contract})
        self.tick_callback = None
        self.bidask_callback = None
        self.event_callback = None
        self.subscriptions: list[tuple[str, str, str]] = []
        self.unsubscriptions: list[tuple[str, str, str]] = []
        self.cleared: list[str] = []
        self.fail_on: tuple[str, str] | None = None
        self.logged_out = False
        self.login_kwargs = None

    def login(self, **kwargs):
        self.login_kwargs = kwargs
        return []

    def snapshots(self, contracts):
        assert [item.code for item in contracts] == ["8039"]
        return [SimpleNamespace(yesterday_volume=4567)]

    def set_on_tick_stk_v1_callback(self, callback) -> None:
        self.tick_callback = callback

    def set_on_bidask_stk_v1_callback(self, callback) -> None:
        self.bidask_callback = callback

    def set_event_callback(self, callback) -> None:
        self.event_callback = callback

    def clear_on_tick_stk_v1_callback(self) -> None:
        self.cleared.append("tick")

    def clear_on_bidask_stk_v1_callback(self) -> None:
        self.cleared.append("bidask")

    def clear_event_callback(self) -> None:
        self.cleared.append("event")

    def subscribe(self, contract, *, quote_type: str, version: str) -> None:
        if self.fail_on == ("subscribe", quote_type):
            raise RuntimeError(f"subscribe failed: {quote_type}")
        self.subscriptions.append((contract.code, quote_type, version))

    def unsubscribe(self, contract, *, quote_type: str, version: str) -> None:
        if self.fail_on == ("unsubscribe", quote_type):
            raise RuntimeError(f"unsubscribe failed: {quote_type}")
        self.unsubscriptions.append((contract.code, quote_type, version))

    def logout(self) -> None:
        self.logged_out = True


def raw_tick() -> SimpleNamespace:
    return SimpleNamespace(
        code="8039",
        datetime=datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI),
        close="278",
        volume=12,
        total_volume=11_112,
        avg_price="270.76",
        high="278",
        low="258.5",
        tick_type=1,
        bid_side_total_vol=6_919,
        ask_side_total_vol=4_193,
        suspend=False,
        simtrade=False,
        intraday_odd=False,
    )


def raw_book() -> SimpleNamespace:
    return SimpleNamespace(
        code="8039",
        datetime=datetime(2026, 8, 18, 9, 18, 1, tzinfo=TAIPEI),
        bid_price=["277.5", "277"],
        bid_volume=[3000, 1200],
        ask_price=["278", "278.5"],
        ask_volume=[1000, 800],
        suspend=False,
        simtrade=False,
        intraday_odd=False,
    )


def make_stream(*, owns_session: bool = False):
    api = FakeAPI()
    clock = FixedClock(
        datetime(2026, 8, 18, 9, 18, 0, 10_000, tzinfo=TAIPEI)
    )
    stream = ShioajiMomentumStream(
        api,
        session_id="20260818-shadow",
        clock=clock,
        owns_session=owns_session,
    )
    return stream, api, clock


def test_reference_and_callbacks_preserve_canonical_detector_fields():
    stream, api, clock = make_stream()
    events = []
    lifecycle = []
    stream.start(events.append, lifecycle.append)

    reference = stream.instrument_reference("8039", SESSION_DATE)
    stream.request_subscribe("8039")
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "ok")
    assert lifecycle == []
    api.event_callback(200, 16, "QUO/v1/STK/*/TSE/8039", "ok")

    clock.value += timedelta(milliseconds=1)
    api.tick_callback("TSE", raw_tick())
    clock.value += timedelta(milliseconds=1)
    api.bidask_callback("TSE", raw_book())

    assert reference.eligible_for_limit_up_momentum is True
    assert api.subscriptions == [
        ("8039", "tick", "v1"),
        ("8039", "bid_ask", "v1"),
    ]
    assert lifecycle[0].event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED
    assert lifecycle[0].symbol == "8039"
    assert stream.subscribed_symbols == frozenset({"8039"})

    tick_envelope, book_envelope = events
    assert tick_envelope.stream_kind is MarketStreamKind.TICK
    assert tick_envelope.source is MarketEventSource.TICK
    assert isinstance(tick_envelope.payload, TickEvent)
    assert tick_envelope.payload.tick_volume_lots == 12
    assert tick_envelope.payload.total_volume_lots == 11_112
    assert str(tick_envelope.payload.average_price) == "270.76"
    assert tick_envelope.payload.raw_tick_type == 1
    assert tick_envelope.payload.aggressor_side is AggressorSide.UNKNOWN
    assert tick_envelope.payload.buy_aggressor_total_lots is None
    assert tick_envelope.payload.sell_aggressor_total_lots is None

    assert book_envelope.stream_kind is MarketStreamKind.BIDASK
    assert book_envelope.source is MarketEventSource.BIDASK
    assert isinstance(book_envelope.payload, BidAskEvent)
    assert book_envelope.payload.bid_volume_lots == (3000, 1200)
    assert book_envelope.payload.ask_volume_lots == (1000, 800)
    assert tick_envelope.ingress_sequence < book_envelope.ingress_sequence


def test_tick_and_bidask_callbacks_share_one_ingress_serialization_boundary():
    api = FakeAPI()
    first_observed_at = datetime(
        2026, 8, 18, 9, 18, 0, 10_000, tzinfo=TAIPEI
    )
    second_observed_at = first_observed_at + timedelta(milliseconds=1)
    stream = ShioajiMomentumStream(
        api,
        session_id="20260818-concurrent",
        clock=ScriptedClock(first_observed_at, second_observed_at),
    )
    events = []
    stream.start(events.append, lambda event: None)
    tick_mapping_entered = Event()
    release_tick_mapping = Event()
    tick_thread = Thread(
        target=api.tick_callback,
        args=("TSE", BlockingTick(tick_mapping_entered, release_tick_mapping)),
    )
    bidask_thread = Thread(
        target=api.bidask_callback,
        args=("TSE", raw_book()),
    )

    tick_thread.start()
    assert tick_mapping_entered.wait(timeout=1)
    bidask_thread.start()
    bidask_thread.join(timeout=0.05)
    release_tick_mapping.set()
    tick_thread.join(timeout=1)
    bidask_thread.join(timeout=1)

    assert not tick_thread.is_alive()
    assert not bidask_thread.is_alive()
    assert [item.stream_kind for item in events] == [
        MarketStreamKind.TICK,
        MarketStreamKind.BIDASK,
    ]
    assert [item.received_at for item in events] == [
        first_observed_at,
        second_observed_at,
    ]
    assert events[0].ingress_sequence < events[1].ingress_sequence


def test_received_at_preserves_a_regressed_observation_clock():
    api = FakeAPI()
    later = datetime(2026, 8, 18, 9, 18, 0, 20_000, tzinfo=TAIPEI)
    earlier = later - timedelta(milliseconds=1)
    stream = ShioajiMomentumStream(
        api,
        session_id="20260818-clock-regression",
        clock=ScriptedClock(later, earlier),
    )
    events = []
    stream.start(events.append, lambda event: None)

    api.tick_callback("TSE", raw_tick())
    api.bidask_callback("TSE", raw_book())

    assert [item.received_at for item in events] == [later, earlier]


def test_qualification_bootstrap_uses_current_contract_and_real_snapshot():
    stream, _, _ = make_stream()

    evidence = stream.qualification_bootstrap_evidence(
        "8039",
        SESSION_DATE,
        date(2026, 8, 17),
    )

    assert evidence.instrument_name == "乙盛-KY"
    assert evidence.security_type == "STOCK"
    assert evidence.previous_close == evidence.reference.reference_price
    assert evidence.previous_session_volume_lots == 4567
    assert evidence.prior_session_date == date(2026, 8, 17)


def test_connect_from_env_forces_subscribe_trade_false(monkeypatch):
    api = FakeAPI()
    fake_shioaji = SimpleNamespace(Shioaji=lambda simulation: api)
    monkeypatch.setitem(sys.modules, "shioaji", fake_shioaji)
    monkeypatch.setenv("SHIOAJI_API_KEY", "data-key")
    monkeypatch.setenv("SHIOAJI_SECRET", "data-secret")
    monkeypatch.setenv("SJ_SIMULATION", "false")

    stream = ShioajiMomentumStream.connect_from_env(session_id="data-only")

    assert api.login_kwargs == {
        "api_key": "data-key",
        "secret_key": "data-secret",
        "subscribe_trade": False,
    }
    assert stream.environment_identity == "shioaji:unknown:simulation=false"
    stream.close()


def test_event_callback_maps_disconnect_reconnect_and_paired_unsubscribe_ack():
    stream, api, _ = make_stream()
    lifecycle = []
    stream.start(lambda event: None, lifecycle.append)
    stream.request_subscribe("8039")
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "ok")
    api.event_callback(200, 16, "QUO/v1/STK/*/TSE/8039", "ok")

    api.event_callback(500, 12, "session", "reconnecting")
    api.event_callback(200, 13, "session", "reconnected")
    stream.request_unsubscribe("8039")
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "ok")
    api.event_callback(200, 16, "QUO/v1/STK/*/TSE/8039", "ok")

    assert [item.event_type for item in lifecycle] == [
        StreamLifecycleEventType.SUBSCRIBE_ACKED,
        StreamLifecycleEventType.RECONNECTING,
        StreamLifecycleEventType.RECONNECTED,
        StreamLifecycleEventType.UNSUBSCRIBE_ACKED,
    ]
    assert stream.subscribed_symbols == frozenset()


def test_second_subscribe_failure_keeps_capacity_pending_until_rollback_ack():
    stream, api, _ = make_stream()
    lifecycle = []
    stream.start(lambda event: None, lifecycle.append)
    api.fail_on = ("subscribe", "bid_ask")

    stream.request_subscribe("8039")

    assert api.unsubscriptions == []
    assert stream.subscribed_symbols == frozenset()
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "subscribe")
    assert api.unsubscriptions == [("8039", "tick", "v1")]
    assert [item.event_type for item in lifecycle] == [
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED,
    ]

    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "unsubscribe")
    assert [item.event_type for item in lifecycle] == [
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED,
        StreamLifecycleEventType.UNSUBSCRIBE_ACKED,
    ]


def test_async_bidask_subscription_error_rolls_back_acked_tick():
    stream, api, _ = make_stream()
    lifecycle = []
    stream.start(lambda event: None, lifecycle.append)
    stream.request_subscribe("8039")
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "subscribe")

    api.event_callback(
        500,
        4,
        "QUO/v1/STK/*/TSE/8039",
        "bidask subscription failed",
    )

    assert set(api.unsubscriptions) == {("8039", "tick", "v1")}
    assert lifecycle[-1].event_type is (
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED
    )
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "unsubscribe")
    assert lifecycle[-1].event_type is (
        StreamLifecycleEventType.UNSUBSCRIBE_ACKED
    )


def test_stop_clears_callbacks_and_close_logs_out_only_when_owned():
    stream, api, _ = make_stream(owns_session=True)
    stream.start(lambda event: None, lambda event: None)
    stream.request_subscribe("8039")
    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "ok")
    api.event_callback(200, 16, "QUO/v1/STK/*/TSE/8039", "ok")

    stream.close()

    assert set(api.cleared) == {"tick", "bidask", "event"}
    assert api.logged_out is True
    assert stream.subscribed_symbols == frozenset()


def test_contract_unit_is_required_instead_of_assuming_one_lot_size():
    stream, api, _ = make_stream()
    api.Contracts.Stocks["8039"].unit = None

    with pytest.raises(ValueError, match="contract unit is unavailable"):
        stream.instrument_reference("8039", SESSION_DATE)


def test_rollback_request_failure_is_explicitly_reported():
    stream, api, _ = make_stream()
    lifecycle = []
    stream.start(lambda event: None, lifecycle.append)
    api.fail_on = ("subscribe", "bid_ask")
    stream.request_subscribe("8039")
    api.fail_on = ("unsubscribe", "tick")

    api.event_callback(200, 16, "TIC/v1/STK/*/TSE/8039", "subscribe")

    assert [item.event_type for item in lifecycle] == [
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED,
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED,
    ]
