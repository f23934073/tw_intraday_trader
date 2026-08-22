"""Deterministic Feature Request resolution for atomic strategies."""

from __future__ import annotations

from typing import Any, Mapping

from features.specifications import FeatureRequestSpec
from strategy_catalog.drafts import StrategyTemplate


def resolve_feature_requests(
    template: StrategyTemplate,
    parameters: Mapping[str, Any] | None = None,
) -> tuple[FeatureRequestSpec, ...]:
    canonical_parameters = template.validate_parameters(parameters or {})
    resolved: list[FeatureRequestSpec] = []
    for requirement in template.feature_requirements:
        unknown = set(requirement) - {
            "feature_id",
            "parameters",
            "parameter_bindings",
        }
        if unknown:
            raise ValueError(
                f"未知 Feature requirement 欄位：{', '.join(sorted(unknown))}"
            )
        request_parameters = dict(requirement.get("parameters") or {})
        bindings = dict(requirement.get("parameter_bindings") or {})
        for feature_parameter, strategy_parameter in bindings.items():
            if feature_parameter in request_parameters:
                raise ValueError(
                    f"Feature parameter {feature_parameter} 不可同時 static 與 bound"
                )
            try:
                request_parameters[str(feature_parameter)] = canonical_parameters[
                    str(strategy_parameter)
                ]
            except KeyError as error:
                raise ValueError(
                    f"Feature parameter binding 找不到策略參數：{strategy_parameter}"
                ) from error
        resolved.append(
            FeatureRequestSpec(
                feature_id=str(requirement["feature_id"]),
                parameters=request_parameters,
            )
        )
    return tuple(resolved)
