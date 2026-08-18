"""Offline mapping tests for the bounded Shioaji parity capture."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_data.quote_qualification import ObservationKind
from market_data.shioaji_quote_capture import (
    QuoteProjectionTracker,
    bidask_event_to_observations,
    tick_event_to_observations,
)


TAIPEI = ZoneInfo("Asia/Taipei")
EVENT_TIME = datetime(2026, 8, 18, 10, 30, tzinfo=TAIPEI)
RECEIVED_AT = EVENT_TIME + timedelta(milliseconds=12)


def quote_event() -> SimpleNamespace:
    return SimpleNamespace(
        code="8039",
        datetime=EVENT_TIME,
        close=278.0,
        avg_price=270.76,
        total_volume=11_112,
        total_amount=306_000_000,
        tick_type=1,
        bid_side_total_vol=6_919,
        ask_side_total_vol=4_193,
        bid_price=[277.5, 277.0],
        bid_volume=[3000, 1200],
        ask_price=[278.0, 278.5],
        ask_volume=[1000, 800],
    )


def test_quote_tracker_emits_initial_trade_and_book_as_baselines():
    tracker = QuoteProjectionTracker()

    observations = tracker.project(quote_event(), RECEIVED_AT)

    assert {item.kind for item in observations} == {
        ObservationKind.TRADE,
        ObservationKind.BOOK,
    }
    assert all(item.is_baseline for item in observations)


def test_quote_tracker_deduplicates_unchanged_combined_updates():
    tracker = QuoteProjectionTracker()
    event = quote_event()
    tracker.project(event, RECEIVED_AT)

    assert tracker.project(event, RECEIVED_AT + timedelta(milliseconds=1)) == ()


def test_quote_tracker_emits_only_changed_trade_projection():
    tracker = QuoteProjectionTracker()
    event = quote_event()
    tracker.project(event, RECEIVED_AT)
    event.total_volume = 11_113
    event.total_amount = 306_000_278

    observations = tracker.project(event, RECEIVED_AT + timedelta(milliseconds=1))

    assert len(observations) == 1
    assert observations[0].kind is ObservationKind.TRADE
    assert observations[0].is_baseline is False
    assert observations[0].bid_side_total_lots == 6_919
    assert observations[0].ask_side_total_lots == 4_193


def test_tick_mapper_preserves_detector_trade_fields_without_side_remap():
    event = quote_event()
    event.intraday_odd = False

    observations = tick_event_to_observations(event, RECEIVED_AT)

    assert len(observations) == 1
    trade = observations[0]
    assert trade.raw_tick_type == 1
    assert trade.average_price is not None
    assert trade.bid_side_total_lots == 6_919
    assert trade.ask_side_total_lots == 4_193


def test_bidask_mapper_preserves_depth_and_excludes_odd_lot():
    event = quote_event()
    event.intraday_odd = False
    observations = bidask_event_to_observations(event, RECEIVED_AT)

    assert len(observations) == 1
    assert observations[0].bid_volume_lots == (3000, 1200)
    assert observations[0].ask_volume_lots == (1000, 800)

    event.intraday_odd = True
    assert bidask_event_to_observations(event, RECEIVED_AT) == ()
