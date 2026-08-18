"""Session-scoped recent five-level order-book projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from market_data.events import (
    BidAskEvent,
    MarketStreamKind,
    ProjectionApplyResult,
    ProjectionApplyStatus,
    StreamWatermark,
)


class OrderBookStatus(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"


@dataclass(frozen=True)
class OrderBookSnapshot:
    status: OrderBookStatus
    as_of: datetime
    event: BidAskEvent | None
    age: timedelta | None
    reason: str | None = None


class OrderBookStore:
    """Retains enough book history for an event-time as-of lookup."""

    def __init__(self, session_date: date, *, retention: timedelta) -> None:
        if retention < timedelta(minutes=20):
            raise ValueError("order-book retention must be at least 20 minutes")
        self._session_date = session_date
        self._retention = retention
        self._events: dict[str, list[BidAskEvent]] = {}
        self._seen_event_ids: set[str] = set()
        self._watermarks: dict[str, StreamWatermark] = {}
        self._finalized = False

    @property
    def session_date(self) -> date:
        return self._session_date

    @property
    def finalized(self) -> bool:
        return self._finalized

    def begin_session(self, session_date: date) -> None:
        if session_date == self._session_date and not self._finalized:
            return
        self._session_date = session_date
        self._events.clear()
        self._seen_event_ids.clear()
        self._watermarks.clear()
        self._finalized = False

    def apply(self, event: BidAskEvent) -> ProjectionApplyResult:
        previous = self._watermarks.get(event.symbol)
        watermark = StreamWatermark(event.event_time, event.ingress_sequence)
        if self._finalized:
            return self._result(
                event,
                ProjectionApplyStatus.INVALID,
                previous,
                previous,
                "session_finalized",
            )
        if event.session_date != self._session_date:
            return self._result(
                event,
                ProjectionApplyStatus.SESSION_MISMATCH,
                previous,
                previous,
                "event_session_does_not_match_store",
            )
        if event.event_id in self._seen_event_ids:
            return self._result(
                event,
                ProjectionApplyStatus.DUPLICATE,
                previous,
                previous,
                "event_id_already_applied",
            )
        if previous is not None and watermark <= previous:
            return self._result(
                event,
                ProjectionApplyStatus.OUT_OF_ORDER,
                previous,
                previous,
                "book_watermark_not_monotonic",
            )
        if event.is_crossed:
            return self._result(
                event,
                ProjectionApplyStatus.INVALID,
                previous,
                previous,
                "crossed_order_book",
            )

        self._events.setdefault(event.symbol, []).append(event)
        self._seen_event_ids.add(event.event_id)
        self._watermarks[event.symbol] = watermark
        self._prune(event.event_time)
        return self._result(
            event,
            ProjectionApplyStatus.APPLIED,
            previous,
            watermark,
            None,
        )

    def latest(self, symbol: str) -> BidAskEvent | None:
        events = self._events.get(symbol, ())
        return events[-1] if events else None

    def at_or_before(
        self,
        symbol: str,
        *,
        as_of: datetime,
        max_age: timedelta,
    ) -> OrderBookSnapshot:
        if max_age < timedelta(0):
            raise ValueError("max_age cannot be negative")
        selected = None
        for event in reversed(self._events.get(symbol, ())):
            if event.event_time <= as_of:
                selected = event
                break
        if selected is None:
            return OrderBookSnapshot(
                status=OrderBookStatus.MISSING,
                as_of=as_of,
                event=None,
                age=None,
                reason="no_book_at_or_before_as_of",
            )
        age = as_of - selected.event_time
        if age > max_age:
            return OrderBookSnapshot(
                status=OrderBookStatus.STALE,
                as_of=as_of,
                event=selected,
                age=age,
                reason="book_age_exceeds_limit",
            )
        return OrderBookSnapshot(
            status=OrderBookStatus.VALID,
            as_of=as_of,
            event=selected,
            age=age,
        )

    def finalize_session(self) -> str:
        self._finalized = True
        return self.digest

    @property
    def digest(self) -> str:
        payload = [
            {
                "event_id": item.event_id,
                "symbol": item.symbol,
                "session_date": item.session_date.isoformat(),
                "event_time": item.event_time.isoformat(),
                "ingress_sequence": item.ingress_sequence,
                "bid_prices": [str(value) for value in item.bid_prices],
                "bid_volume_lots": list(item.bid_volume_lots),
                "ask_prices": [str(value) for value in item.ask_prices],
                "ask_volume_lots": list(item.ask_volume_lots),
                "suspended": item.suspended,
                "simulated_trade": item.simulated_trade,
                "intraday_odd": item.intraday_odd,
            }
            for symbol in sorted(self._events)
            for item in self._events[symbol]
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _prune(self, latest_event_time: datetime) -> None:
        cutoff = latest_event_time - self._retention
        for symbol, events in tuple(self._events.items()):
            kept = [event for event in events if event.event_time >= cutoff]
            if kept:
                self._events[symbol] = kept
            else:
                self._events.pop(symbol, None)

    @staticmethod
    def _result(
        event: BidAskEvent,
        status: ProjectionApplyStatus,
        previous: StreamWatermark | None,
        new: StreamWatermark | None,
        reason: str | None,
    ) -> ProjectionApplyResult:
        return ProjectionApplyResult(
            status=status,
            event_id=event.event_id,
            symbol=event.symbol,
            stream_kind=MarketStreamKind.BIDASK,
            previous_watermark=previous,
            new_watermark=new,
            reason=reason,
        )
