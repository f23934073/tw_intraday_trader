from __future__ import annotations

from dataclasses import replace

from atomic_strategies.entries.above_vwap import AboveVwapEntryStrategy
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
