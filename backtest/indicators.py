"""Deterministic Decimal indicator formulas for completed historical bars."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.domain import HistoricalBar


def exponential_moving_average(
    values: Sequence[Decimal],
    period: int,
) -> Decimal | None:
    """Return an SMA-seeded EMA, or ``None`` before warm-up."""

    _validate_period(period)
    if len(values) < period:
        return None
    alpha = Decimal(2) / Decimal(period + 1)
    result = sum(values[:period], Decimal(0)) / Decimal(period)
    for value in values[period:]:
        result = alpha * value + (Decimal(1) - alpha) * result
    return result


def simple_moving_average(
    values: Sequence[Decimal],
    period: int,
) -> Decimal | None:
    """Return the completed-window SMA, or ``None`` before warm-up."""

    _validate_period(period)
    if len(values) < period:
        return None
    return sum(values[-period:], Decimal(0)) / Decimal(period)


def relative_strength_index(
    closes: Sequence[Decimal],
    period: int,
) -> Decimal | None:
    """Return Wilder RSI using ``period`` consecutive close differences."""

    _validate_period(period)
    if len(closes) < period + 1:
        return None
    differences = [current - previous for previous, current in zip(closes, closes[1:])]
    gains = [max(value, Decimal(0)) for value in differences]
    losses = [max(-value, Decimal(0)) for value in differences]
    average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
    average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (average_gain * Decimal(period - 1) + gain) / Decimal(period)
        average_loss = (average_loss * Decimal(period - 1) + loss) / Decimal(period)
    return rsi_from_averages(average_gain, average_loss)


def bollinger_bands(
    values: Sequence[Decimal],
    period: int,
    multiplier: Decimal = Decimal(2),
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Return middle, upper and lower population-standard-deviation bands."""

    _validate_period(period)
    if len(values) < period:
        return None
    window = values[-period:]
    middle = sum(window, Decimal(0)) / Decimal(period)
    variance = sum(((value - middle) ** 2 for value in window), Decimal(0)) / Decimal(period)
    standard_deviation = variance.sqrt()
    return (
        middle,
        middle + multiplier * standard_deviation,
        middle - multiplier * standard_deviation,
    )


def average_true_range(
    bars: Sequence[HistoricalBar],
    period: int,
) -> Decimal | None:
    """Return Wilder ATR; the first bar uses its high-low range."""

    _validate_period(period)
    if len(bars) < period:
        return None
    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for bar in bars:
        true_ranges.append(
            true_range(
                high=bar.high,
                low=bar.low,
                previous_close=previous_close,
            )
        )
        previous_close = bar.close
    result = sum(true_ranges[:period], Decimal(0)) / Decimal(period)
    for value in true_ranges[period:]:
        result = (result * Decimal(period - 1) + value) / Decimal(period)
    return result


def true_range(
    *,
    high: Decimal,
    low: Decimal,
    previous_close: Decimal | None,
) -> Decimal:
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def rsi_from_averages(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_gain == 0 and average_loss == 0:
        return Decimal(50)
    if average_loss == 0:
        return Decimal(100)
    relative_strength = average_gain / average_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("indicator period 必須大於 0")
