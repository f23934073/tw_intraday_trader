"""Session-scoped one-minute bars and recent common-lot Tick history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from market_data.events import (
    MarketStreamKind,
    ProjectionApplyResult,
    ProjectionApplyStatus,
    StreamWatermark,
    TickEvent,
)


@dataclass(frozen=True)
class IntradayBar:
    symbol: str
    session_date: date
    minute: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume_lots: int
    tick_count: int
    first_event_time: datetime
    last_event_time: datetime
    ending_total_volume_lots: int


class IntradayBarStore:
    """Apply monotonic common-lot ticks without double-counting volume."""

    def __init__(self, session_date: date, *, retention: timedelta) -> None:
        if retention < timedelta(minutes=20):
            raise ValueError("intraday retention must be at least 20 minutes")
        self._session_date = session_date
        self._retention = retention
        self._bars: dict[tuple[str, datetime], IntradayBar] = {}
        self._ticks: dict[str, list[TickEvent]] = {}
        self._seen_event_ids: set[str] = set()
        self._watermarks: dict[str, StreamWatermark] = {}
        self._last_total_volume: dict[str, int] = {}
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
        self._bars.clear()
        self._ticks.clear()
        self._seen_event_ids.clear()
        self._watermarks.clear()
        self._last_total_volume.clear()
        self._finalized = False

    def apply(self, event: TickEvent) -> ProjectionApplyResult:
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
                "tick_watermark_not_monotonic",
            )

        prior_total = self._last_total_volume.get(event.symbol)
        gap = False
        if prior_total is not None:
            cumulative_delta = event.total_volume_lots - prior_total
            if cumulative_delta < event.tick_volume_lots:
                return self._result(
                    event,
                    ProjectionApplyStatus.INVALID,
                    previous,
                    previous,
                    "cumulative_volume_delta_below_tick_volume",
                )
            gap = cumulative_delta > event.tick_volume_lots

        minute = event.event_time.replace(second=0, microsecond=0)
        key = (event.symbol, minute)
        bar = self._bars.get(key)
        if bar is None:
            bar = IntradayBar(
                symbol=event.symbol,
                session_date=event.session_date,
                minute=minute,
                open=event.price,
                high=event.price,
                low=event.price,
                close=event.price,
                volume_lots=event.tick_volume_lots,
                tick_count=1,
                first_event_time=event.event_time,
                last_event_time=event.event_time,
                ending_total_volume_lots=event.total_volume_lots,
            )
        else:
            bar = replace(
                bar,
                high=max(bar.high, event.price),
                low=min(bar.low, event.price),
                close=event.price,
                volume_lots=bar.volume_lots + event.tick_volume_lots,
                tick_count=bar.tick_count + 1,
                last_event_time=event.event_time,
                ending_total_volume_lots=event.total_volume_lots,
            )
        self._bars[key] = bar
        self._ticks.setdefault(event.symbol, []).append(event)
        self._seen_event_ids.add(event.event_id)
        self._watermarks[event.symbol] = watermark
        self._last_total_volume[event.symbol] = event.total_volume_lots
        self._prune(event.event_time)

        status = (
            ProjectionApplyStatus.APPLIED_WITH_GAP
            if gap
            else ProjectionApplyStatus.APPLIED
        )
        return self._result(
            event,
            status,
            previous,
            watermark,
            "cumulative_volume_gap" if gap else None,
        )

    def bars(
        self,
        symbol: str,
        *,
        through: datetime | None = None,
    ) -> tuple[IntradayBar, ...]:
        values = [
            bar
            for (stored_symbol, _), bar in self._bars.items()
            if stored_symbol == symbol
            and (through is None or bar.minute <= through)
        ]
        return tuple(sorted(values, key=lambda item: item.minute))

    def ticks(
        self,
        symbol: str,
        *,
        after: datetime | None = None,
        through: datetime | None = None,
    ) -> tuple[TickEvent, ...]:
        return tuple(
            item
            for item in self._ticks.get(symbol, ())
            if (after is None or item.event_time > after)
            and (through is None or item.event_time <= through)
        )

    def latest_tick_at_or_before(
        self,
        symbol: str,
        as_of: datetime,
    ) -> TickEvent | None:
        for event in reversed(self._ticks.get(symbol, ())):
            if event.event_time <= as_of:
                return event
        return None

    def finalize_session(self) -> str:
        self._finalized = True
        return self.digest

    @property
    def digest(self) -> str:
        payload = [
            {
                "symbol": item.symbol,
                "session_date": item.session_date.isoformat(),
                "minute": item.minute.isoformat(),
                "open": str(item.open),
                "high": str(item.high),
                "low": str(item.low),
                "close": str(item.close),
                "volume_lots": item.volume_lots,
                "tick_count": item.tick_count,
                "first_event_time": item.first_event_time.isoformat(),
                "last_event_time": item.last_event_time.isoformat(),
                "ending_total_volume_lots": item.ending_total_volume_lots,
            }
            for item in sorted(
                self._bars.values(),
                key=lambda value: (value.symbol, value.minute),
            )
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _prune(self, latest_event_time: datetime) -> None:
        cutoff = latest_event_time - self._retention
        for symbol, events in tuple(self._ticks.items()):
            kept = [event for event in events if event.event_time >= cutoff]
            if kept:
                self._ticks[symbol] = kept
            else:
                self._ticks.pop(symbol, None)
        cutoff_minute = cutoff.replace(second=0, microsecond=0)
        self._bars = {
            key: bar
            for key, bar in self._bars.items()
            if bar.minute >= cutoff_minute
        }

    @staticmethod
    def _result(
        event: TickEvent,
        status: ProjectionApplyStatus,
        previous: StreamWatermark | None,
        new: StreamWatermark | None,
        reason: str | None,
    ) -> ProjectionApplyResult:
        return ProjectionApplyResult(
            status=status,
            event_id=event.event_id,
            symbol=event.symbol,
            stream_kind=MarketStreamKind.TICK,
            previous_watermark=previous,
            new_watermark=new,
            reason=reason,
        )
