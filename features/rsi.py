"""Runtime-neutral Wilder RSI projection from completed one-minute bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Protocol


RSI_SESSION_BAR_CAPACITY = 300


class CompletedRsiBar(Protocol):
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class RsiBar:
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class RsiFeatureValue:
    value: Decimal | None
    missing_reason: str | None
    evidence: Mapping[str, Any]


def evaluate_wilder_rsi(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedRsiBar, ...],
) -> RsiFeatureValue:
    period = int(parameters["rsi_period"])
    if period <= 0:
        raise ValueError("rsi_period 必須大於 0")
    if not bars:
        return RsiFeatureValue(None, "completed_kbar_history_empty", {})

    current = bars[-1]
    session_open = current.timestamp.replace(hour=9, minute=0, second=0, microsecond=0)
    evidence: dict[str, Any] = {
        "rsi_period": period,
        "session_open": session_open.isoformat(),
        "completed_through": current.timestamp.isoformat(),
    }
    if current.timestamp < session_open:
        return RsiFeatureValue(None, "rsi_session_not_started", evidence)

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
        return RsiFeatureValue(
            None,
            "rsi_session_kbars_non_contiguous",
            {
                **evidence,
                "observed_bar_count": len(selected),
                "expected_bar_count": expected_count,
                "observed_minutes": tuple(
                    item.isoformat() for item in sorted(selected)
                ),
            },
        )

    required_bars = period + 1
    if len(expected) < required_bars:
        return RsiFeatureValue(
            None,
            "rsi_warmup_incomplete",
            {
                **evidence,
                "observed_bar_count": len(expected),
                "required_bar_count": required_bars,
            },
        )

    closes = tuple(selected[timestamp].close for timestamp in expected)
    differences = tuple(
        current_close - previous_close
        for previous_close, current_close in zip(closes, closes[1:])
    )
    gains = tuple(max(value, Decimal("0")) for value in differences)
    losses = tuple(max(-value, Decimal("0")) for value in differences)
    average_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    average_loss = sum(losses[:period], Decimal("0")) / Decimal(period)
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (
            average_gain * Decimal(period - 1) + gain
        ) / Decimal(period)
        average_loss = (
            average_loss * Decimal(period - 1) + loss
        ) / Decimal(period)

    rsi = _rsi_from_averages(average_gain, average_loss)
    return RsiFeatureValue(
        rsi,
        None,
        {
            **evidence,
            "observed_bar_count": len(expected),
            "required_bar_count": required_bars,
            "average_gain": _decimal_text(average_gain),
            "average_loss": _decimal_text(average_loss),
            "rsi": _decimal_text(rsi),
        },
    )


def _rsi_from_averages(
    average_gain: Decimal,
    average_loss: Decimal,
) -> Decimal:
    if average_gain == 0 and average_loss == 0:
        return Decimal("50")
    if average_loss == 0:
        return Decimal("100")
    relative_strength = average_gain / average_loss
    return Decimal("100") - Decimal("100") / (
        Decimal("1") + relative_strength
    )


def _decimal_text(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return "0" if normalized == "-0" else normalized
