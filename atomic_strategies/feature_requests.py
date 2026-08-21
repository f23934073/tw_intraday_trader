"""Deterministic Feature Request resolution for atomic strategies."""

from __future__ import annotations

from features.specifications import FeatureRequestSpec
from strategy_catalog.drafts import StrategyTemplate


def resolve_feature_requests(template: StrategyTemplate) -> tuple[FeatureRequestSpec, ...]:
    return tuple(
        FeatureRequestSpec(
            feature_id=str(requirement["feature_id"]),
            parameters=dict(requirement.get("parameters") or {}),
        )
        for requirement in template.feature_requirements
    )
