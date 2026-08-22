from __future__ import annotations

from dataclasses import replace

import pytest

from atomic_strategies.entries.above_vwap import AboveVwapEntryStrategy
from atomic_strategies.entries.ema_crossover import EmaCrossoverEntryStrategy
from atomic_strategies.entries.rolling_return import RollingReturnEntryStrategy
from atomic_strategies.entries.opening_range_breakout import (
    OpeningRangeBreakoutEntryStrategy,
)
from atomic_strategies.entries.volume_acceleration import (
    VolumeAccelerationEntryStrategy,
)
from atomic_strategies.feature_requests import resolve_feature_requests
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry


def test_feature_request_identity_includes_canonical_parameters() -> None:
    two = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 2})
    three = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})

    assert two.parameter_digest != three.parameter_digest
    assert two.request_digest != three.request_digest
    assert two.state_key(
        adapter_identity="backtest.completed-kbar-1m-feature-adapter-v1",
        cadence="COMPLETED_KBAR_1M",
        symbol="2330",
        session="2026-08-21",
    ) != three.state_key(
        adapter_identity="backtest.completed-kbar-1m-feature-adapter-v1",
        cadence="COMPLETED_KBAR_1M",
        symbol="2330",
        session="2026-08-21",
    )


def test_feature_state_identity_isolated_by_runtime_adapter() -> None:
    request = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})

    backtest_key = request.state_key(
        adapter_identity="backtest.completed-kbar-1m-feature-adapter-v1",
        cadence="COMPLETED_KBAR_1M",
        symbol="2330",
        session="2026-08-21",
    )
    tick_key = request.state_key(
        adapter_identity="paper.tick-feature-adapter-v1",
        cadence="TICK",
        symbol="2330",
        session="2026-08-21",
    )

    assert backtest_key != tick_key


def test_first_strategy_feature_requests_resolve_against_shared_registry() -> None:
    requests = resolve_feature_requests(AboveVwapEntryStrategy.template)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert tuple(item.feature_id for item in requests) == ("vwap_session_v1",)


def test_feature_specification_digest_freezes_implementation_and_as_of_semantics() -> None:
    specification = FeatureSpecificationRegistry().get("vwap_session_v1")

    assert len(specification.implementation_digest) == 64
    assert specification.as_of_semantics == "CURRENT_COMPLETED_BAR_CLOSE_INCLUSIVE"
    assert replace(
        specification,
        as_of_semantics="STRICTLY_BEFORE_CURRENT_COMPLETED_BAR",
    ).specification_digest != specification.specification_digest


def test_existing_feature_specification_digests_do_not_change_in_phase5() -> None:
    registry = FeatureSpecificationRegistry()

    assert registry.get("vwap_session_v1").specification_digest == (
        "362508f9163f669d8aee28f74585f0124dc9e2b6f71d067a5fcd875eed7bfba0"
    )
    assert registry.get("previous_intraday_high_v1").specification_digest == (
        "bb0e2ae9f141448e624cf94d7266fe10531bcb0918741de955a959f37a34e1f1"
    )


def test_volume_specification_and_web_schema_freeze_gap_semantics() -> None:
    specification = FeatureSpecificationRegistry().get("rolling_volume_ratio_v1")
    minimum_field = VolumeAccelerationEntryStrategy.template.parameter_schema.fields[
        "minimum_complete_baseline_windows"
    ]

    assert specification.missing_semantics == (
        "INSUFFICIENT_DATA_ON_INCOMPLETE_CURRENT_OR_NON_SUFFIX_BASELINE_WINDOWS"
    )
    assert specification.warmup_semantics == (
        "NEWEST_CONTIGUOUS_COMPLETE_BASELINE_PREFIX_WITH_OLDEST_WARMUP_SUFFIX"
    )
    assert "中間缺少任何 1 分 Kbar" in minimum_field["help"]


def test_strategy_parameters_resolve_into_real_feature_windows() -> None:
    rolling_requests = resolve_feature_requests(
        RollingReturnEntryStrategy.template,
        {"window_minutes": 3, "minimum_return_pct": "2.0"},
    )
    volume_requests = resolve_feature_requests(
        VolumeAccelerationEntryStrategy.template,
        {
            "window_minutes": 3,
            "baseline_window_count": 4,
            "minimum_complete_baseline_windows": 3,
            "minimum_acceleration_ratio": "2",
        },
    )
    registry = FeatureSpecificationRegistry()
    registry.validate_requests(rolling_requests)
    registry.validate_requests(volume_requests)

    assert rolling_requests[0].parameters == {"window_minutes": 3}
    assert volume_requests[0].parameters == {
        "window_minutes": 3,
        "baseline_window_count": 4,
        "minimum_complete_baseline_windows": 3,
        "baseline_method": "MEDIAN",
    }
    assert registry.get("rolling_return_v1").request_parameter_schema is not None
    assert registry.get("rolling_volume_ratio_v1").request_parameter_schema is not None


def test_orb_feature_specification_freezes_exact_session_open_range() -> None:
    requests = resolve_feature_requests(
        OpeningRangeBreakoutEntryStrategy.template,
        {
            "opening_range_minutes": 5,
            "entry_window_start": "09:05",
        },
    )
    registry = FeatureSpecificationRegistry()
    registry.validate_requests(requests)
    specification = registry.get("opening_range_high_v1")

    assert requests[0].parameters == {"opening_range_minutes": 5}
    assert specification.missing_semantics == (
        "INSUFFICIENT_DATA_UNLESS_EXACT_CONTIGUOUS_SESSION_OPEN_RANGE"
    )
    assert specification.warmup_semantics == (
        "OPENING_RANGE_MINUTES_CONTIGUOUS_COMPLETED_BARS_FROM_09_00"
    )


def test_ema_feature_specification_freezes_cross_and_session_prefix() -> None:
    requests = resolve_feature_requests(
        EmaCrossoverEntryStrategy.template,
        {"fast_period": 8, "slow_period": 34},
    )
    registry = FeatureSpecificationRegistry()
    registry.validate_requests(requests)
    specification = registry.get("ema_cross_up_v1")

    assert requests[0].parameters == {"fast_period": 8, "slow_period": 34}
    assert specification.unit == "BOOLEAN"
    assert specification.missing_semantics == (
        "INSUFFICIENT_DATA_UNLESS_CONTIGUOUS_SESSION_OPEN_PREFIX"
    )
    assert specification.warmup_semantics == (
        "SLOW_PERIOD_PLUS_ONE_CONTIGUOUS_BARS_FROM_09_00"
    )
    with pytest.raises(ValueError, match="fast_period 必須小於 slow_period"):
        registry.validate_requests(
            (
                FeatureRequestSpec(
                    "ema_cross_up_v1",
                    {"fast_period": 20, "slow_period": 20},
                ),
            )
        )
