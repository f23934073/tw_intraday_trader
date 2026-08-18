from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_data.events import (
    BidAskEvent,
    MarketEventSource,
    ProjectionApplyStatus,
)
from market_data.order_book_store import OrderBookStatus, OrderBookStore


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 18)


def book(
    event_id: str,
    *,
    minute: int,
    second: int,
    sequence: int,
    bid: str = "277.5",
    ask: str = "278",
    session_date: date = SESSION_DATE,
) -> BidAskEvent:
    event_time = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        9,
        minute,
        second,
        tzinfo=TAIPEI,
    )
    return BidAskEvent(
        event_id=event_id,
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=session_date,
        event_time=event_time,
        received_at=event_time,
        ingress_sequence=sequence,
        bid_prices=(Decimal(bid),),
        bid_volume_lots=(3000,),
        ask_prices=(Decimal(ask),),
        ask_volume_lots=(1000,),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )


def store() -> OrderBookStore:
    return OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))


def test_book_duplicate_out_of_order_and_crossed_updates_do_not_overwrite():
    books = store()
    accepted = book("book-2", minute=18, second=10, sequence=2)
    assert books.apply(accepted).status is ProjectionApplyStatus.APPLIED
    expected_digest = books.digest

    assert books.apply(accepted).status is ProjectionApplyStatus.DUPLICATE
    assert books.apply(
        book("book-1", minute=18, second=5, sequence=1)
    ).status is ProjectionApplyStatus.OUT_OF_ORDER
    assert books.apply(
        book(
            "crossed",
            minute=18,
            second=20,
            sequence=3,
            bid="278.5",
            ask="278",
        )
    ).status is ProjectionApplyStatus.INVALID
    assert books.digest == expected_digest


def test_as_of_lookup_never_pairs_a_future_book_and_marks_stale():
    books = store()
    older = book("older", minute=17, second=50, sequence=1)
    newer = book("newer", minute=18, second=10, sequence=2)
    books.apply(older)
    books.apply(newer)

    as_of = datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI)
    selected = books.at_or_before(
        "8039",
        as_of=as_of,
        max_age=timedelta(seconds=15),
    )
    stale = books.at_or_before(
        "8039",
        as_of=as_of + timedelta(seconds=30),
        max_age=timedelta(seconds=15),
    )

    assert selected.status is OrderBookStatus.VALID
    assert selected.event == older
    assert stale.status is OrderBookStatus.STALE
    assert stale.event == newer


def test_locked_and_empty_sides_are_valid_but_missing_symbol_is_explicit():
    books = store()
    locked = book(
        "locked",
        minute=18,
        second=0,
        sequence=1,
        bid="278",
        ask="278",
    )
    assert books.apply(locked).status is ProjectionApplyStatus.APPLIED
    assert books.latest("8039").is_locked is True

    missing = books.at_or_before(
        "2330",
        as_of=locked.event_time,
        max_age=timedelta(seconds=1),
    )
    assert missing.status is OrderBookStatus.MISSING


def test_book_session_reset_and_finalize_clear_or_reject_updates():
    books = store()
    first = book("book-1", minute=18, second=0, sequence=1)
    books.apply(first)
    digest = books.finalize_session()
    assert books.apply(
        book("book-2", minute=18, second=1, sequence=2)
    ).status is ProjectionApplyStatus.INVALID
    assert books.digest == digest

    next_date = date(2026, 8, 19)
    books.begin_session(next_date)
    assert books.latest("8039") is None
    assert books.apply(first).status is ProjectionApplyStatus.SESSION_MISMATCH
