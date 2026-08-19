"""Bounded, session-local feature state shared by backtest strategies."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backtest.domain import HistoricalBar, digest
from backtest.indicators import bollinger_bands, rsi_from_averages, true_range


FEATURE_VERSION = "historical-features-v1"


@dataclass(frozen=True)
class BarFeatureSnapshot:
    symbol: str
    session_date: date
    as_of: datetime
    bar_interval_seconds: int
    bars_seen: int
    close: Decimal
    opening_range_status: str
    opening_bar_count: int
    opening_range_high: Decimal | None
    opening_range_low: Decimal | None
    ema_fast: Decimal | None
    ema_slow: Decimal | None
    rsi: Decimal | None
    bollinger_middle: Decimal | None
    bollinger_upper: Decimal | None
    bollinger_lower: Decimal | None
    atr: Decimal | None
    validity: tuple[str, ...]
    missing_reasons: tuple[str, ...]
    feature_version: str
    input_digest: str


@dataclass(frozen=True)
class PositionStrategyContext:
    entry_fill_price: Decimal
    entry_fill_at: datetime
    entry_event_index: int
    bars_held_completed: int
    entry_signal_atr: Decimal | None
    fixed_atr_stop_price: Decimal | None


class _EmaState:
    def __init__(self, period: int) -> None:
        self._period = period
        self._count = 0
        self._seed_sum = Decimal(0)
        self.value: Decimal | None = None

    def update(self, value: Decimal) -> Decimal | None:
        self._count += 1
        if self.value is None:
            self._seed_sum += value
            if self._count == self._period:
                self.value = self._seed_sum / Decimal(self._period)
            return self.value
        alpha = Decimal(2) / Decimal(self._period + 1)
        self.value = alpha * value + (Decimal(1) - alpha) * self.value
        return self.value


class _WilderState:
    def __init__(self, period: int) -> None:
        self._period = period
        self._count = 0
        self._seed_sum = Decimal(0)
        self.value: Decimal | None = None

    def update(self, value: Decimal) -> Decimal | None:
        self._count += 1
        if self.value is None:
            self._seed_sum += value
            if self._count == self._period:
                self.value = self._seed_sum / Decimal(self._period)
            return self.value
        self.value = (self.value * Decimal(self._period - 1) + value) / Decimal(self._period)
        return self.value


class BarFeatureState:
    """Maintain O(max indicator window) state for one symbol-session."""

    def __init__(self, symbol: str, session_date: date) -> None:
        self._symbol = symbol
        self._session_date = session_date
        self._bars_seen = 0
        self._opening_bars: dict[tuple[int, int], HistoricalBar] = {}
        self._closes: deque[Decimal] = deque(maxlen=20)
        self._ema_fast = _EmaState(5)
        self._ema_slow = _EmaState(20)
        self._rsi_gain = _WilderState(14)
        self._rsi_loss = _WilderState(14)
        self._atr = _WilderState(14)
        self._previous_close: Decimal | None = None
        self.current: BarFeatureSnapshot | None = None

    def apply(self, bar: HistoricalBar) -> BarFeatureSnapshot:
        if bar.symbol != self._symbol or bar.timestamp.date() != self._session_date:
            raise ValueError("feature state 只能接收同一 symbol-session 的 Kbar")
        self._bars_seen += 1
        self._record_opening_bar(bar)
        ema_fast = self._ema_fast.update(bar.close)
        ema_slow = self._ema_slow.update(bar.close)

        if self._previous_close is not None:
            difference = bar.close - self._previous_close
            average_gain = self._rsi_gain.update(max(difference, Decimal(0)))
            average_loss = self._rsi_loss.update(max(-difference, Decimal(0)))
            rsi = (
                rsi_from_averages(average_gain, average_loss)
                if average_gain is not None and average_loss is not None
                else None
            )
        else:
            rsi = None

        atr = self._atr.update(
            true_range(high=bar.high, low=bar.low, previous_close=self._previous_close)
        )
        self._previous_close = bar.close
        self._closes.append(bar.close)
        bands = bollinger_bands(tuple(self._closes), 20)
        middle, upper, lower = bands if bands is not None else (None, None, None)
        opening_status, opening_high, opening_low = self._opening_range(bar)

        validity: list[str] = []
        missing: list[str] = []
        for name, value in (
            ("EMA_FAST", ema_fast),
            ("EMA_SLOW", ema_slow),
            ("RSI", rsi),
            ("BOLLINGER", bands),
            ("ATR", atr),
        ):
            (validity if value is not None else missing).append(
                name if value is not None else f"{name}_WARMUP"
            )
        if opening_status == "COMPLETE":
            validity.append("OPENING_RANGE")
        else:
            missing.append(f"OPENING_RANGE_{opening_status}")

        self.current = BarFeatureSnapshot(
            symbol=bar.symbol,
            session_date=bar.timestamp.date(),
            as_of=bar.timestamp,
            bar_interval_seconds=60,
            bars_seen=self._bars_seen,
            close=bar.close,
            opening_range_status=opening_status,
            opening_bar_count=len(self._opening_bars),
            opening_range_high=opening_high,
            opening_range_low=opening_low,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            bollinger_middle=middle,
            bollinger_upper=upper,
            bollinger_lower=lower,
            atr=atr,
            validity=tuple(validity),
            missing_reasons=tuple(missing),
            feature_version=FEATURE_VERSION,
            input_digest=digest(
                {
                    "feature_version": FEATURE_VERSION,
                    "bar": bar.to_dict(),
                    "bars_seen": self._bars_seen,
                    "opening_range_status": opening_status,
                    "opening_range_high": str(opening_high) if opening_high is not None else None,
                    "opening_range_low": str(opening_low) if opening_low is not None else None,
                    "ema_fast": str(ema_fast) if ema_fast is not None else None,
                    "ema_slow": str(ema_slow) if ema_slow is not None else None,
                    "rsi": str(rsi) if rsi is not None else None,
                    "bollinger_middle": str(middle) if middle is not None else None,
                    "bollinger_upper": str(upper) if upper is not None else None,
                    "bollinger_lower": str(lower) if lower is not None else None,
                    "atr": str(atr) if atr is not None else None,
                }
            ),
        )
        return self.current

    def _record_opening_bar(self, bar: HistoricalBar) -> None:
        key = (bar.timestamp.hour, bar.timestamp.minute)
        if (9, 0) <= key <= (9, 14) and bar.timestamp.second == 0 and bar.timestamp.microsecond == 0:
            self._opening_bars[key] = bar

    def _opening_range(
        self,
        bar: HistoricalBar,
    ) -> tuple[str, Decimal | None, Decimal | None]:
        expected = {(9, minute) for minute in range(15)}
        complete = set(self._opening_bars) == expected
        if complete:
            values = tuple(self._opening_bars.values())
            return "COMPLETE", max(item.high for item in values), min(item.low for item in values)
        if (bar.timestamp.hour, bar.timestamp.minute) <= (9, 14):
            return "COLLECTING", None, None
        return "INCOMPLETE", None, None
