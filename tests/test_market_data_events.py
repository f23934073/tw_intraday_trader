"""Phase 0 tests for normalized market-data contracts."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)
EVENT_TIME = datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI)


def test_instrument_reference_uses_authoritative_contract_limit():
    reference = InstrumentReference(
        symbol="8039",
        exchange="TSE",
        session_date=SESSION_DATE,
        reference_price=Decimal("258.5"),
        limit_up_price=Decimal("284.5"),
        limit_down_price=Decimal("232.5"),
        price_limit_applies=True,
        trading_unit_shares=1000,
        source_updated_at=SESSION_DATE,
    )

    assert reference.limit_up_price == Decimal("284.5")
    assert reference.eligible_for_limit_up_momentum is True


def test_instrument_without_price_limit_is_explicitly_ineligible():
    reference = InstrumentReference(
        symbol="TEST",
        exchange="TSE",
        session_date=SESSION_DATE,
        reference_price=Decimal("100"),
        limit_up_price=None,
        limit_down_price=None,
        price_limit_applies=False,
        trading_unit_shares=1000,
        source_updated_at=SESSION_DATE,
    )

    assert reference.eligible_for_limit_up_momentum is False


def test_reference_without_current_session_update_is_ineligible():
    reference = InstrumentReference(
        symbol="8039",
        exchange="TSE",
        session_date=SESSION_DATE,
        reference_price=Decimal("258.5"),
        limit_up_price=Decimal("284.5"),
        limit_down_price=Decimal("232.5"),
        price_limit_applies=True,
        trading_unit_shares=1000,
        source_updated_at=None,
    )

    assert reference.eligible_for_limit_up_momentum is False


def test_tick_event_preserves_lot_units_and_aggressor_totals():
    event = TickEvent(
        event_id="quote:8039:1:trade",
        source=MarketEventSource.QUOTE,
        symbol="8039",
        session_date=SESSION_DATE,
        event_time=EVENT_TIME,
        received_at=EVENT_TIME,
        ingress_sequence=1,
        price=Decimal("278"),
        tick_volume_lots=10,
        total_volume_lots=11_112,
        average_price=Decimal("270.76"),
        intraday_high=Decimal("278"),
        intraday_low=Decimal("258.5"),
        raw_tick_type=1,
        aggressor_side=AggressorSide.BUY,
        buy_aggressor_total_lots=6_919,
        sell_aggressor_total_lots=4_193,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )

    assert event.total_volume_lots == 11_112
    assert event.buy_aggressor_total_lots + event.sell_aggressor_total_lots == 11_112


def test_bidask_event_preserves_five_levels_and_detects_crossed_book():
    event = BidAskEvent(
        event_id="quote:8039:1:book",
        source=MarketEventSource.QUOTE,
        symbol="8039",
        session_date=SESSION_DATE,
        event_time=EVENT_TIME,
        received_at=EVENT_TIME,
        ingress_sequence=1,
        bid_prices=(Decimal("278.5"), Decimal("278")),
        bid_volume_lots=(3000, 1200),
        ask_prices=(Decimal("278"), Decimal("278.5")),
        ask_volume_lots=(1000, 800),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )

    assert event.best_bid == Decimal("278.5")
    assert event.best_ask == Decimal("278")
    assert event.is_crossed is True
    assert event.is_locked is False


def test_tick_event_rejects_naive_source_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        TickEvent(
            event_id="bad-time",
            source=MarketEventSource.TICK,
            symbol="8039",
            session_date=SESSION_DATE,
            event_time=datetime(2026, 8, 18, 9, 18),
            received_at=EVENT_TIME,
            ingress_sequence=1,
            price=Decimal("278"),
            tick_volume_lots=1,
            total_volume_lots=1,
            average_price=Decimal("278"),
            intraday_high=Decimal("278"),
            intraday_low=Decimal("278"),
            raw_tick_type=0,
            aggressor_side=AggressorSide.UNKNOWN,
            buy_aggressor_total_lots=None,
            sell_aggressor_total_lots=None,
            suspended=False,
            simulated_trade=False,
            intraday_odd=False,
        )


def test_bidask_event_rejects_more_than_five_levels():
    prices = tuple(Decimal("100") for _ in range(6))
    volumes = tuple(1 for _ in range(6))
    with pytest.raises(ValueError, match="at most five levels"):
        BidAskEvent(
            event_id="too-deep",
            source=MarketEventSource.BIDASK,
            symbol="8039",
            session_date=SESSION_DATE,
            event_time=EVENT_TIME,
            received_at=EVENT_TIME,
            ingress_sequence=1,
            bid_prices=prices,
            bid_volume_lots=volumes,
            ask_prices=(),
            ask_volume_lots=(),
            suspended=False,
            simulated_trade=False,
            intraday_odd=False,
        )


def test_event_envelope_requires_payload_metadata_to_match():
    event = TickEvent(
        event_id="replay:8039:1",
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=SESSION_DATE,
        event_time=EVENT_TIME,
        received_at=EVENT_TIME,
        ingress_sequence=1,
        price=Decimal("278"),
        tick_volume_lots=1,
        total_volume_lots=1,
        average_price=Decimal("278"),
        intraday_high=Decimal("278"),
        intraday_low=Decimal("278"),
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    envelope = EventEnvelope(
        event_id=event.event_id,
        schema_version="market-event-v1",
        session_id="20260818-replay",
        session_date=SESSION_DATE,
        source=MarketEventSource.REPLAY,
        source_mode="SYNTHETIC_REPLAY",
        stream_kind=MarketStreamKind.TICK,
        symbol="8039",
        event_at=EVENT_TIME,
        received_at=EVENT_TIME,
        ingress_sequence=1,
        source_identity="row:1",
        payload=event,
        raw_capture_id="fixture-v1",
    )

    assert envelope.watermark.ingress_sequence == 1
    with pytest.raises(ValueError, match="do not match payload"):
        EventEnvelope(
            **{
                **envelope.__dict__,
                "symbol": "2330",
            }
        )
