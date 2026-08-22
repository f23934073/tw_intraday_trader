from __future__ import annotations

import pytest

from atomic_strategies.entries.above_vwap import AboveVwapEntryStrategy
from atomic_strategies.entries.breakout_previous_high import (
    BreakoutPreviousHighEntryStrategy,
)
from atomic_strategies.entries.opening_range_breakout import (
    OpeningRangeBreakoutEntryStrategy,
)
from atomic_strategies.entries.rolling_return import RollingReturnEntryStrategy
from atomic_strategies.entries.volume_acceleration import (
    VolumeAccelerationEntryStrategy,
)
from atomic_strategies.registry import AtomicStrategyRegistry


def test_first_atomic_templates_are_separate_allowlisted_implementations() -> None:
    registry = AtomicStrategyRegistry()
    templates = {item.strategy_id: item for item in registry.templates()}

    assert set(templates) == {
        "above_vwap_entry",
        "breakout_previous_high_entry",
        "rolling_return_entry",
        "volume_acceleration_entry",
        "opening_range_breakout_entry",
    }
    assert isinstance(registry.strategy("above_vwap_entry"), AboveVwapEntryStrategy)
    assert isinstance(
        registry.strategy("breakout_previous_high_entry"),
        BreakoutPreviousHighEntryStrategy,
    )
    assert isinstance(
        registry.strategy("rolling_return_entry"),
        RollingReturnEntryStrategy,
    )
    assert isinstance(
        registry.strategy("volume_acceleration_entry"),
        VolumeAccelerationEntryStrategy,
    )
    assert isinstance(
        registry.strategy("opening_range_breakout_entry"),
        OpeningRangeBreakoutEntryStrategy,
    )
    assert templates["above_vwap_entry"].template_digest != templates[
        "breakout_previous_high_entry"
    ].template_digest


def test_parameter_schema_canonicalizes_defaults_and_rejects_unknown_or_bad_window() -> None:
    template = AboveVwapEntryStrategy.template

    assert template.validate_parameters({}) == {
        "minimum_distance_bps": "0",
        "entry_window_start": "09:01",
        "entry_window_end": "12:45",
    }
    assert template.validate_parameters({"minimum_distance_bps": "2.00"})[
        "minimum_distance_bps"
    ] == "2"
    with pytest.raises(ValueError, match="未知策略參數"):
        template.validate_parameters({"trigger_mode": "CROSS_UP"})
    with pytest.raises(ValueError, match="必須早於"):
        template.validate_parameters(
            {"entry_window_start": "12:45", "entry_window_end": "09:01"}
        )


def test_phase5_strategy_schemas_are_parameterized_and_runtime_bound() -> None:
    rolling = RollingReturnEntryStrategy.template
    volume = VolumeAccelerationEntryStrategy.template

    assert rolling.validate_parameters(
        {"window_minutes": 3, "minimum_return_pct": "2.0"}
    )["minimum_return_pct"] == "2"
    assert volume.validate_parameters(
        {
            "window_minutes": 3,
            "baseline_window_count": 4,
            "minimum_complete_baseline_windows": 3,
        }
    )["window_minutes"] == 3
    assert set(rolling.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }
    assert set(volume.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }

    with pytest.raises(ValueError, match="不可大於"):
        volume.validate_parameters(
            {
                "baseline_window_count": 3,
                "minimum_complete_baseline_windows": 4,
            }
        )
