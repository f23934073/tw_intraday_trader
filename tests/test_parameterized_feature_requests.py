from __future__ import annotations

from atomic_strategies.entries.above_vwap import AboveVwapEntryStrategy
from atomic_strategies.feature_requests import resolve_feature_requests
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry


def test_feature_request_identity_includes_canonical_parameters() -> None:
    two = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 2})
    three = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})

    assert two.parameter_digest != three.parameter_digest
    assert two.request_digest != three.request_digest


def test_first_strategy_feature_requests_resolve_against_shared_registry() -> None:
    requests = resolve_feature_requests(AboveVwapEntryStrategy.template)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert tuple(item.feature_id for item in requests) == ("vwap_session_v1",)
