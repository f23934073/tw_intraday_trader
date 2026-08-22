"""Runtime-neutral Bollinger lower-band re-entry from completed 1m bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Protocol


BOLLINGER_SESSION_BAR_CAPACITY = 300


class CompletedBollingerBar(Protocol):
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class BollingerBar:
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class BollingerReentryFeatureValue:
    value: bool | None
    missing_reason: str | None
    evidence: Mapping[str, Any]


def evaluate_bollinger_lower_reentry(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedBollingerBar, ...],
) -> BollingerReentryFeatureValue:
    period = int(parameters["bollinger_period"])
    multiplier = Decimal(str(parameters["stddev_multiplier"]))
    if period <= 1:
        raise ValueError("bollinger_period 必須大於 1")
    if multiplier <= 0:
        raise ValueError("stddev_multiplier 必須大於 0")
    if not bars:
        return BollingerReentryFeatureValue(
            None,
            "completed_kbar_history_empty",
            {},
        )

    current = bars[-1]
    session_open = current.timestamp.replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    )
    evidence: dict[str, Any] = {
        "bollinger_period": period,
        "stddev_multiplier": _decimal_text(multiplier),
        "session_open": session_open.isoformat(),
        "completed_through": current.timestamp.isoformat(),
    }
    if current.timestamp < session_open:
        return BollingerReentryFeatureValue(
            None,
            "bollinger_session_not_started",
            evidence,
        )

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
        return BollingerReentryFeatureValue(
            None,
            "bollinger_session_kbars_non_contiguous",
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
        return BollingerReentryFeatureValue(
            None,
            "bollinger_warmup_incomplete",
            {
                **evidence,
                "observed_bar_count": len(expected),
                "required_bar_count": required_bars,
            },
        )

    closes = tuple(selected[timestamp].close for timestamp in expected)
    previous_middle, previous_upper, previous_lower = _bollinger_bands(
        closes[:-1],
        period,
        multiplier,
    )
    current_middle, current_upper, current_lower = _bollinger_bands(
        closes,
        period,
        multiplier,
    )
    previous_close = closes[-2]
    current_close = closes[-1]
    reentered = lower_band_reentry_triggered(
        previous_close=previous_close,
        previous_lower_band=previous_lower,
        current_close=current_close,
        current_lower_band=current_lower,
    )
    return BollingerReentryFeatureValue(
        reentered,
        None,
        {
            **evidence,
            "observed_bar_count": len(expected),
            "required_bar_count": required_bars,
            "previous_close": _decimal_text(previous_close),
            "current_close": _decimal_text(current_close),
            "previous_middle_band": _decimal_text(previous_middle),
            "previous_upper_band": _decimal_text(previous_upper),
            "previous_lower_band": _decimal_text(previous_lower),
            "current_middle_band": _decimal_text(current_middle),
            "current_upper_band": _decimal_text(current_upper),
            "current_lower_band": _decimal_text(current_lower),
            "reentered_lower_band": reentered,
        },
    )


def lower_band_reentry_triggered(
    *,
    previous_close: Decimal,
    previous_lower_band: Decimal,
    current_close: Decimal,
    current_lower_band: Decimal,
) -> bool:
    """Return true only for an outside-to-inside lower-band transition."""

    return (
        previous_close < previous_lower_band
        and current_close >= current_lower_band
    )


def _bollinger_bands(
    values: tuple[Decimal, ...],
    period: int,
    multiplier: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    window = values[-period:]
    if len(window) != period:
        raise RuntimeError("Bollinger warm-up contract violated")
    middle = sum(window, Decimal("0")) / Decimal(period)
    variance = sum(
        ((value - middle) ** 2 for value in window),
        Decimal("0"),
    ) / Decimal(period)
    standard_deviation = variance.sqrt()
    return (
        middle,
        middle + multiplier * standard_deviation,
        middle - multiplier * standard_deviation,
    )


def _decimal_text(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return "0" if normalized == "-0" else normalized
