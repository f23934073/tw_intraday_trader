"""Runtime-neutral feature specifications shared by strategy adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from strategy_catalog.parameter_schema import ParameterSchema, canonical_digest


def _validate_volume_window_parameters(parameters: Mapping[str, Any]) -> None:
    minimum = int(parameters["minimum_complete_baseline_windows"])
    total = int(parameters["baseline_window_count"])
    if minimum > total:
        raise ValueError(
            "minimum_complete_baseline_windows 不可大於 baseline_window_count"
        )


def _validate_ema_parameters(parameters: Mapping[str, Any]) -> None:
    if int(parameters["fast_period"]) >= int(parameters["slow_period"]):
        raise ValueError("fast_period 必須小於 slow_period")


@dataclass(frozen=True)
class FeatureRequestSpec:
    feature_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.feature_id.strip():
            raise ValueError("feature_id 不可為空")
        object.__setattr__(self, "parameters", dict(self.parameters))

    @property
    def parameter_digest(self) -> str:
        return canonical_digest(dict(self.parameters))

    @property
    def request_digest(self) -> str:
        return canonical_digest(
            {
                "feature_id": self.feature_id,
                "parameters": dict(self.parameters),
                "parameter_digest": self.parameter_digest,
            }
        )

    def runtime_identity_digest(
        self,
        *,
        adapter_identity: str,
        cadence: str,
    ) -> str:
        """Identity shared by cache and state stores before symbol/session scope."""

        if not adapter_identity.strip() or not cadence.strip():
            raise ValueError("adapter_identity 與 cadence 不可為空")
        return canonical_digest(
            {
                "request_digest": self.request_digest,
                "adapter_identity": adapter_identity,
                "cadence": cadence,
            }
        )

    def state_key(
        self,
        *,
        adapter_identity: str,
        cadence: str,
        symbol: str,
        session: str,
    ) -> str:
        """Prevent parameter/window and runtime adapter state collisions."""

        if not symbol.strip() or not session.strip():
            raise ValueError("feature state symbol 與 session 不可為空")
        return canonical_digest(
            {
                "runtime_identity_digest": self.runtime_identity_digest(
                    adapter_identity=adapter_identity,
                    cadence=cadence,
                ),
                "symbol": symbol,
                "session": session,
            }
        )


@dataclass(frozen=True)
class FeatureSpecification:
    feature_id: str
    unit: str
    cadence: str
    completed_data_only: bool
    session_reset: bool
    warmup_bars: int
    missing_semantics: str
    as_of_semantics: str
    implementation_digest: str
    warmup_semantics: str = "FIXED_WARMUP_BARS"
    request_parameter_schema: ParameterSchema | None = field(
        default=None,
        repr=False,
    )

    @property
    def specification_digest(self) -> str:
        document = {
            "feature_id": self.feature_id,
            "unit": self.unit,
            "cadence": self.cadence,
            "completed_data_only": self.completed_data_only,
            "session_reset": self.session_reset,
            "warmup_bars": self.warmup_bars,
            "missing_semantics": self.missing_semantics,
            "as_of_semantics": self.as_of_semantics,
            "implementation_digest": self.implementation_digest,
        }
        # Preserve the already-published v1 digest for non-parameterized specs.
        if self.warmup_semantics != "FIXED_WARMUP_BARS":
            document["warmup_semantics"] = self.warmup_semantics
        if self.request_parameter_schema is not None:
            document["request_parameter_schema"] = (
                self.request_parameter_schema.schema_document
            )
        return canonical_digest(document)

    def validate_request(self, request: FeatureRequestSpec) -> None:
        if request.feature_id != self.feature_id:
            raise ValueError("Feature Request 與 Specification identity 不一致")
        if self.request_parameter_schema is None:
            if request.parameters:
                raise ValueError(f"{self.feature_id} 不接受 Feature parameters")
            return
        canonical = self.request_parameter_schema.canonicalize(request.parameters)
        if canonical != dict(request.parameters):
            raise ValueError(f"{self.feature_id} Feature parameters 必須先 canonicalize")


@dataclass(frozen=True)
class NormalizedFeatureSnapshot:
    symbol: str
    session: str
    as_of: datetime
    adapter_identity: str
    values: Mapping[str, Any]
    input_digest: str
    missing_reasons: Mapping[str, str] = field(default_factory=dict)
    request_digests: Mapping[str, str] = field(default_factory=dict)
    state_keys: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", dict(self.values))
        object.__setattr__(self, "missing_reasons", dict(self.missing_reasons))
        object.__setattr__(self, "request_digests", dict(self.request_digests))
        object.__setattr__(self, "state_keys", dict(self.state_keys))


class FeatureSpecificationRegistry:
    def __init__(self) -> None:
        specifications = (
            FeatureSpecification(
                feature_id="vwap_session_v1",
                unit="TWD_PER_SHARE",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=1,
                missing_semantics="INSUFFICIENT_DATA",
                as_of_semantics="CURRENT_COMPLETED_BAR_CLOSE_INCLUSIVE",
                implementation_digest=hashlib.sha256(
                    b"session-vwap-feature-implementation-v1"
                ).hexdigest(),
            ),
            FeatureSpecification(
                feature_id="previous_intraday_high_v1",
                unit="TWD_PER_SHARE",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=2,
                missing_semantics="INSUFFICIENT_DATA",
                as_of_semantics="STRICTLY_BEFORE_CURRENT_COMPLETED_BAR",
                implementation_digest=hashlib.sha256(
                    b"previous-intraday-high-feature-implementation-v1"
                ).hexdigest(),
            ),
            FeatureSpecification(
                feature_id="rolling_return_v1",
                unit="RATIO",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=2,
                missing_semantics="INSUFFICIENT_DATA_ON_INCOMPLETE_CONTIGUOUS_WINDOW",
                as_of_semantics="CURRENT_COMPLETED_BAR_CLOSE_INCLUSIVE_EXACT_WINDOW_ANCHOR",
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-rolling-return-feature-implementation-v1"
                ).hexdigest(),
                warmup_semantics="WINDOW_MINUTES_PLUS_ONE_CONTIGUOUS_COMPLETED_BARS",
                request_parameter_schema=ParameterSchema(
                    version="rolling-return-feature-request-v1",
                    fields={
                        "window_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 2,
                        }
                    },
                ),
            ),
            FeatureSpecification(
                feature_id="rolling_volume_ratio_v1",
                unit="RATIO",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=2,
                missing_semantics=(
                    "INSUFFICIENT_DATA_ON_INCOMPLETE_CURRENT_OR_"
                    "NON_SUFFIX_BASELINE_WINDOWS"
                ),
                as_of_semantics="CURRENT_COMPLETED_WINDOW_OVER_PRIOR_NON_OVERLAPPING_WINDOWS",
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-rolling-volume-ratio-feature-implementation-v2"
                ).hexdigest(),
                warmup_semantics=(
                    "NEWEST_CONTIGUOUS_COMPLETE_BASELINE_PREFIX_WITH_"
                    "OLDEST_WARMUP_SUFFIX"
                ),
                request_parameter_schema=ParameterSchema(
                    version="rolling-volume-ratio-feature-request-v1",
                    fields={
                        "window_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 2,
                        },
                        "baseline_window_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                        "minimum_complete_baseline_windows": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 4,
                        },
                        "baseline_method": {
                            "type": "string",
                            "enum": ["MEDIAN"],
                            "default": "MEDIAN",
                        },
                    },
                    cross_validators=(_validate_volume_window_parameters,),
                ),
            ),
            FeatureSpecification(
                feature_id="opening_range_high_v1",
                unit="TWD_PER_SHARE",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=5,
                missing_semantics=(
                    "INSUFFICIENT_DATA_UNLESS_EXACT_CONTIGUOUS_SESSION_OPEN_RANGE"
                ),
                as_of_semantics=(
                    "FIXED_SESSION_OPEN_09_00_THROUGH_N_COMPLETED_ONE_MINUTE_BARS"
                ),
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-opening-range-high-feature-implementation-v1"
                ).hexdigest(),
                warmup_semantics=(
                    "OPENING_RANGE_MINUTES_CONTIGUOUS_COMPLETED_BARS_FROM_09_00"
                ),
                request_parameter_schema=ParameterSchema(
                    version="opening-range-high-feature-request-v1",
                    fields={
                        "opening_range_minutes": {
                            "type": "integer",
                            "minimum": 5,
                            "maximum": 30,
                            "default": 15,
                        }
                    },
                ),
            ),
            FeatureSpecification(
                feature_id="ema_cross_up_v1",
                unit="BOOLEAN",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=21,
                missing_semantics=(
                    "INSUFFICIENT_DATA_UNLESS_CONTIGUOUS_SESSION_OPEN_PREFIX"
                ),
                as_of_semantics=(
                    "CURRENT_AND_PREVIOUS_COMPLETED_BAR_EMA_FROM_SESSION_OPEN_PREFIX"
                ),
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-ema-cross-up-feature-implementation-v1"
                ).hexdigest(),
                warmup_semantics="SLOW_PERIOD_PLUS_ONE_CONTIGUOUS_BARS_FROM_09_00",
                request_parameter_schema=ParameterSchema(
                    version="ema-cross-up-feature-request-v1",
                    fields={
                        "fast_period": {
                            "type": "integer",
                            "minimum": 2,
                            "maximum": 60,
                            "default": 5,
                        },
                        "slow_period": {
                            "type": "integer",
                            "minimum": 3,
                            "maximum": 120,
                            "default": 20,
                        },
                    },
                    cross_validators=(_validate_ema_parameters,),
                ),
            ),
            FeatureSpecification(
                feature_id="wilder_rsi_v1",
                unit="INDEX_0_100",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=15,
                missing_semantics=(
                    "INSUFFICIENT_DATA_UNLESS_CONTIGUOUS_SESSION_OPEN_PREFIX"
                ),
                as_of_semantics="CURRENT_COMPLETED_BAR_CLOSE_INCLUSIVE",
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-wilder-rsi-feature-implementation-v1"
                ).hexdigest(),
                warmup_semantics="RSI_PERIOD_PLUS_ONE_CONTIGUOUS_BARS_FROM_09_00",
                request_parameter_schema=ParameterSchema(
                    version="wilder-rsi-feature-request-v1",
                    fields={
                        "rsi_period": {
                            "type": "integer",
                            "minimum": 2,
                            "maximum": 120,
                            "default": 14,
                        }
                    },
                ),
            ),
            FeatureSpecification(
                feature_id="bollinger_lower_reentry_v1",
                unit="BOOLEAN",
                cadence="COMPLETED_KBAR_1M",
                completed_data_only=True,
                session_reset=True,
                warmup_bars=21,
                missing_semantics=(
                    "INSUFFICIENT_DATA_UNLESS_CONTIGUOUS_SESSION_OPEN_PREFIX"
                ),
                as_of_semantics=(
                    "PREVIOUS_AND_CURRENT_COMPLETED_CLOSE_AGAINST_OWN_LOWER_BAND"
                ),
                implementation_digest=hashlib.sha256(
                    b"completed-kbar-bollinger-lower-reentry-feature-implementation-v1"
                ).hexdigest(),
                warmup_semantics=(
                    "BOLLINGER_PERIOD_PLUS_ONE_CONTIGUOUS_BARS_FROM_09_00"
                ),
                request_parameter_schema=ParameterSchema(
                    version="bollinger-lower-reentry-feature-request-v1",
                    fields={
                        "bollinger_period": {
                            "type": "integer",
                            "minimum": 2,
                            "maximum": 120,
                            "default": 20,
                        },
                        "stddev_multiplier": {
                            "type": "decimal",
                            "minimum": "0.1",
                            "maximum": "10",
                            "default": "2",
                        },
                    },
                ),
            ),
        )
        self._specifications = {item.feature_id: item for item in specifications}

    def get(self, feature_id: str) -> FeatureSpecification:
        try:
            return self._specifications[feature_id]
        except KeyError as error:
            raise ValueError(f"未知 Feature Specification：{feature_id}") from error

    def validate_requests(self, requests: tuple[FeatureRequestSpec, ...]) -> None:
        for request in requests:
            self.get(request.feature_id).validate_request(request)
