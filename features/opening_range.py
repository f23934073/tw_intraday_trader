"""Runtime-neutral opening-range projection from completed one-minute bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Protocol


OPENING_RANGE_SESSION_BAR_CAPACITY = 300


class CompletedOpeningRangeBar(Protocol):
    @property
    def timestamp(self) -> datetime: ...

    @property
    def high(self) -> Decimal: ...

    @property
    def low(self) -> Decimal: ...


@dataclass(frozen=True)
class OpeningRangeBar:
    timestamp: datetime
    high: Decimal
    low: Decimal


@dataclass(frozen=True)
class OpeningRangeFeatureValue:
    value: Decimal | None
    missing_reason: str | None
    evidence: Mapping[str, Any]


def evaluate_opening_range_high(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedOpeningRangeBar, ...],
) -> OpeningRangeFeatureValue:
    if not bars:
        return OpeningRangeFeatureValue(None, "completed_kbar_history_empty", {})

    current = bars[-1]
    opening_range_minutes = int(parameters["opening_range_minutes"])
    session_open = current.timestamp.replace(hour=9, minute=0, second=0, microsecond=0)
    range_end = session_open + timedelta(minutes=opening_range_minutes - 1)
    evidence = {
        "opening_range_minutes": opening_range_minutes,
        "opening_range_start": session_open.isoformat(),
        "opening_range_end": range_end.isoformat(),
    }
    if current.timestamp < session_open:
        return OpeningRangeFeatureValue(
            None,
            "opening_range_not_started",
            evidence,
        )
    if current.timestamp < range_end:
        return OpeningRangeFeatureValue(
            None,
            "opening_range_still_collecting",
            {
                **evidence,
                "completed_through": current.timestamp.isoformat(),
            },
        )

    expected = tuple(
        session_open + timedelta(minutes=offset)
        for offset in range(opening_range_minutes)
    )
    selected = {
        item.timestamp: item
        for item in bars
        if session_open <= item.timestamp <= range_end
    }
    if tuple(sorted(selected)) != expected:
        return OpeningRangeFeatureValue(
            None,
            "opening_range_kbars_non_contiguous",
            {
                **evidence,
                "opening_range_bar_count": len(selected),
                "expected_bar_count": opening_range_minutes,
                "observed_minutes": tuple(
                    item.isoformat() for item in sorted(selected)
                ),
            },
        )

    opening_high = max(selected[item].high for item in expected)
    opening_low = min(selected[item].low for item in expected)
    return OpeningRangeFeatureValue(
        opening_high,
        None,
        {
            **evidence,
            "opening_range_bar_count": opening_range_minutes,
            "opening_range_high": str(opening_high),
            "opening_range_low": str(opening_low),
        },
    )
