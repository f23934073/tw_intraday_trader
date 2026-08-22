"""Runtime-neutral EMA crossover projection from completed one-minute bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Protocol


EMA_SESSION_BAR_CAPACITY = 300


class CompletedEmaBar(Protocol):
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class EmaBar:
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class EmaCrossoverFeatureValue:
    value: bool | None
    missing_reason: str | None
    evidence: Mapping[str, Any]


def evaluate_ema_cross_up(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedEmaBar, ...],
) -> EmaCrossoverFeatureValue:
    fast_period = int(parameters["fast_period"])
    slow_period = int(parameters["slow_period"])
    if fast_period <= 0 or slow_period <= 0 or fast_period >= slow_period:
        raise ValueError("EMA periods 必須為正數且 fast_period 小於 slow_period")
    if not bars:
        return EmaCrossoverFeatureValue(None, "completed_kbar_history_empty", {})

    current = bars[-1]
    session_open = current.timestamp.replace(hour=9, minute=0, second=0, microsecond=0)
    evidence: dict[str, Any] = {
        "fast_period": fast_period,
        "slow_period": slow_period,
        "session_open": session_open.isoformat(),
        "completed_through": current.timestamp.isoformat(),
    }
    if current.timestamp < session_open:
        return EmaCrossoverFeatureValue(None, "ema_session_not_started", evidence)

    selected = {
        item.timestamp: item
        for item in bars
        if session_open <= item.timestamp <= current.timestamp
    }
    expected_count = (
        int((current.timestamp - session_open).total_seconds() // 60) + 1
    )
    expected = tuple(
        session_open + timedelta(minutes=offset)
        for offset in range(expected_count)
    )
    if tuple(sorted(selected)) != expected:
        return EmaCrossoverFeatureValue(
            None,
            "ema_session_kbars_non_contiguous",
            {
                **evidence,
                "observed_bar_count": len(selected),
                "expected_bar_count": expected_count,
                "observed_minutes": tuple(
                    item.isoformat() for item in sorted(selected)
                ),
            },
        )

    required_bars = slow_period + 1
    if len(expected) < required_bars:
        return EmaCrossoverFeatureValue(
            None,
            "ema_warmup_incomplete",
            {
                **evidence,
                "observed_bar_count": len(expected),
                "required_bar_count": required_bars,
            },
        )

    closes = tuple(selected[timestamp].close for timestamp in expected)
    fast_values = _ema_series(closes, fast_period)
    slow_values = _ema_series(closes, slow_period)
    previous_fast = fast_values[-2]
    current_fast = fast_values[-1]
    previous_slow = slow_values[-2]
    current_slow = slow_values[-1]
    if None in (previous_fast, current_fast, previous_slow, current_slow):
        raise RuntimeError("EMA warm-up contract violated")

    crossed_up = previous_fast <= previous_slow and current_fast > current_slow
    return EmaCrossoverFeatureValue(
        crossed_up,
        None,
        {
            **evidence,
            "observed_bar_count": len(expected),
            "required_bar_count": required_bars,
            "previous_fast_ema": _decimal_text(previous_fast),
            "current_fast_ema": _decimal_text(current_fast),
            "previous_slow_ema": _decimal_text(previous_slow),
            "current_slow_ema": _decimal_text(current_slow),
            "crossed_up": crossed_up,
        },
    )


def _ema_series(
    values: tuple[Decimal, ...],
    period: int,
) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    current = sum(values[:period], Decimal("0")) / Decimal(period)
    result[period - 1] = current
    alpha = Decimal("2") / Decimal(period + 1)
    for index in range(period, len(values)):
        current = alpha * values[index] + (Decimal("1") - alpha) * current
        result[index] = current
    return tuple(result)


def _decimal_text(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return "0" if normalized == "-0" else normalized
