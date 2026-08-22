"""Runtime-neutral calculations for completed one-minute rolling features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Protocol


class CompletedOneMinuteBar(Protocol):
    timestamp: datetime
    close: Decimal
    volume: int


@dataclass(frozen=True)
class RollingBar:
    timestamp: datetime
    close: Decimal
    volume: int


@dataclass(frozen=True)
class RollingFeatureValue:
    value: Decimal | None
    missing_reason: str | None
    evidence: Mapping[str, Any]


def required_bar_capacity(
    feature_id: str,
    parameters: Mapping[str, Any],
) -> int:
    window = int(parameters["window_minutes"])
    if feature_id == "rolling_return_v1":
        return window + 1
    if feature_id == "rolling_volume_ratio_v1":
        return window * (int(parameters["baseline_window_count"]) + 1)
    raise ValueError(f"completed Kbar calculator 不支援 Feature：{feature_id}")


def evaluate_completed_bars(
    feature_id: str,
    parameters: Mapping[str, Any],
    bars: tuple[CompletedOneMinuteBar, ...],
) -> RollingFeatureValue:
    if not bars:
        return RollingFeatureValue(None, "completed_kbar_history_empty", {})
    if feature_id == "rolling_return_v1":
        return _rolling_return(parameters, bars)
    if feature_id == "rolling_volume_ratio_v1":
        return _rolling_volume_ratio(parameters, bars)
    raise ValueError(f"completed Kbar calculator 不支援 Feature：{feature_id}")


def _rolling_return(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedOneMinuteBar, ...],
) -> RollingFeatureValue:
    current = bars[-1]
    window = int(parameters["window_minutes"])
    target_at = current.timestamp - timedelta(minutes=window)
    expected = tuple(
        target_at + timedelta(minutes=offset)
        for offset in range(window + 1)
    )
    selected = {item.timestamp: item for item in bars}
    if tuple(sorted(selected)) != expected:
        return RollingFeatureValue(
            None,
            "rolling_return_window_incomplete",
            {
                "window_minutes": window,
                "current_at": current.timestamp.isoformat(),
                "target_at": target_at.isoformat(),
            },
        )
    comparison = selected[target_at]
    value = current.close / comparison.close - Decimal("1")
    return RollingFeatureValue(
        value,
        None,
        {
            "window_minutes": window,
            "current_at": current.timestamp.isoformat(),
            "current_close": str(current.close),
            "comparison_at": comparison.timestamp.isoformat(),
            "comparison_close": str(comparison.close),
            "value": str(value),
        },
    )


def _rolling_volume_ratio(
    parameters: Mapping[str, Any],
    bars: tuple[CompletedOneMinuteBar, ...],
) -> RollingFeatureValue:
    current = bars[-1]
    window = int(parameters["window_minutes"])
    baseline_count = int(parameters["baseline_window_count"])
    minimum_complete = int(parameters["minimum_complete_baseline_windows"])
    current_volume = _complete_window_volume(
        bars,
        end=current.timestamp,
        window_minutes=window,
    )
    if current_volume is None:
        return RollingFeatureValue(
            None,
            "current_volume_window_incomplete",
            {"window_minutes": window, "complete_baseline_windows": 0},
        )

    baseline_volumes: list[Decimal] = []
    missing_offsets: list[int] = []
    for offset in range(1, baseline_count + 1):
        end = current.timestamp - timedelta(minutes=window * offset)
        volume = _complete_window_volume(
            bars,
            end=end,
            window_minutes=window,
        )
        if volume is None:
            missing_offsets.append(offset)
            continue
        if missing_offsets:
            return RollingFeatureValue(
                None,
                "baseline_volume_windows_non_contiguous",
                {
                    "window_minutes": window,
                    "current_volume": current_volume,
                    "complete_baseline_windows": len(baseline_volumes),
                    "first_missing_baseline_offset": missing_offsets[0],
                    "older_complete_baseline_offset": offset,
                },
            )
        baseline_volumes.append(Decimal(volume))
    if len(baseline_volumes) < minimum_complete:
        return RollingFeatureValue(
            None,
            (
                "insufficient_complete_baseline_windows:"
                f"{len(baseline_volumes)}/{baseline_count}"
            ),
            {
                "window_minutes": window,
                "current_volume": current_volume,
                "complete_baseline_windows": len(baseline_volumes),
                "required_complete_baseline_windows": minimum_complete,
            },
        )
    baseline = _median(baseline_volumes)
    if baseline == 0:
        return RollingFeatureValue(
            None,
            "baseline_volume_zero",
            {
                "window_minutes": window,
                "current_volume": current_volume,
                "baseline_volume": "0",
                "complete_baseline_windows": len(baseline_volumes),
            },
        )
    value = Decimal(current_volume) / baseline
    return RollingFeatureValue(
        value,
        None,
        {
            "window_minutes": window,
            "current_volume": current_volume,
            "baseline_volume": str(baseline),
            "baseline_method": parameters["baseline_method"],
            "complete_baseline_windows": len(baseline_volumes),
            "value": str(value),
        },
    )


def _complete_window_volume(
    bars: tuple[CompletedOneMinuteBar, ...],
    *,
    end: datetime,
    window_minutes: int,
) -> int | None:
    expected = tuple(
        end - timedelta(minutes=offset)
        for offset in reversed(range(window_minutes))
    )
    selected = {
        item.timestamp: item
        for item in bars
        if expected[0] <= item.timestamp <= expected[-1]
    }
    if tuple(sorted(selected)) != expected:
        return None
    return sum(selected[timestamp].volume for timestamp in expected)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")
