"""Runtime-neutral feature specifications shared by strategy adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from strategy_catalog.parameter_schema import canonical_digest


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

    @property
    def specification_digest(self) -> str:
        return canonical_digest(
            {
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
        )


@dataclass(frozen=True)
class NormalizedFeatureSnapshot:
    symbol: str
    session: str
    as_of: datetime
    adapter_identity: str
    values: Mapping[str, Any]
    input_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", dict(self.values))


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
        )
        self._specifications = {item.feature_id: item for item in specifications}

    def get(self, feature_id: str) -> FeatureSpecification:
        try:
            return self._specifications[feature_id]
        except KeyError as error:
            raise ValueError(f"未知 Feature Specification：{feature_id}") from error

    def validate_requests(self, requests: tuple[FeatureRequestSpec, ...]) -> None:
        for request in requests:
            self.get(request.feature_id)
