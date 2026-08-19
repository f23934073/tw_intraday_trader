"""Bounded Decimal daily-SMA state isolated from session-local indicators."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backtest.domain import HistoricalBar, digest
from backtest.indicators import simple_moving_average


DAILY_SMA_FEATURE_VERSION = "daily-sma-features-v1"


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("daily SMA values must be finite")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class DailySmaFeatureSnapshot:
    symbol: str
    resolved_session_date: date
    as_of: datetime
    daily_bars_seen: int
    close: Decimal
    sma20: Decimal | None
    sma60: Decimal | None
    validity: tuple[str, ...]
    missing_reasons: tuple[str, ...]
    feature_version: str
    input_digest: str


class DailySmaFeatureState:
    """Maintain at most sixty completed daily closes for one symbol."""

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol
        self._closes: deque[Decimal] = deque(maxlen=60)
        self._last_timestamp: datetime | None = None
        self._last_session_date: date | None = None
        self.current: DailySmaFeatureSnapshot | None = None

    def apply(self, bar: HistoricalBar) -> DailySmaFeatureSnapshot:
        if bar.symbol != self._symbol:
            raise ValueError("daily feature state only accepts one symbol")
        if bar.session_date is None:
            raise ValueError("daily feature state requires resolved session_date")
        if self._last_timestamp is not None and bar.timestamp <= self._last_timestamp:
            raise ValueError("daily feature timestamps must be strictly increasing")
        if self._last_session_date is not None and bar.session_date <= self._last_session_date:
            raise ValueError("daily feature session dates must be strictly increasing")
        close = Decimal(_decimal_text(bar.close))
        self._closes.append(close)
        values = tuple(self._closes)
        sma20 = simple_moving_average(values, 20)
        sma60 = simple_moving_average(values, 60)
        validity: list[str] = []
        missing: list[str] = []
        for name, value in (("SMA20", sma20), ("SMA60", sma60)):
            if value is None:
                missing.append(f"{name}_WARMUP")
            else:
                validity.append(name)
        snapshot = DailySmaFeatureSnapshot(
            symbol=bar.symbol,
            resolved_session_date=bar.session_date,
            as_of=bar.timestamp,
            daily_bars_seen=(self.current.daily_bars_seen + 1 if self.current else 1),
            close=close,
            sma20=sma20,
            sma60=sma60,
            validity=tuple(validity),
            missing_reasons=tuple(missing),
            feature_version=DAILY_SMA_FEATURE_VERSION,
            input_digest=digest(
                {
                    "feature_version": DAILY_SMA_FEATURE_VERSION,
                    "symbol": bar.symbol,
                    "resolved_session_date": bar.session_date.isoformat(),
                    "as_of": bar.timestamp.isoformat(),
                    "daily_bars_seen": self.current.daily_bars_seen + 1 if self.current else 1,
                    "close_window": [_decimal_text(value) for value in values],
                    "sma20": _decimal_text(sma20) if sma20 is not None else None,
                    "sma60": _decimal_text(sma60) if sma60 is not None else None,
                }
            ),
        )
        self._last_timestamp = bar.timestamp
        self._last_session_date = bar.session_date
        self.current = snapshot
        return snapshot
