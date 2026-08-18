"""Immutable, source-timestamped intraday feature values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from market_data.health import DataHealthSnapshot, DataHealthState


FEATURE_VERSION_V0 = "intraday_features_v0"
FeatureScalar = Decimal | int | bool | str


class FeatureStatus(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class FeatureValue:
    value: FeatureScalar | None
    status: FeatureStatus
    source_as_of: datetime | None
    reason: str | None = None
    source_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_as_of is not None:
            _require_aware(self.source_as_of, "source_as_of")
        if self.status is FeatureStatus.VALID and self.value is None:
            raise ValueError("valid feature must have a value")
        if self.status is not FeatureStatus.VALID and not self.reason:
            raise ValueError("non-valid feature must include a reason")

    @property
    def is_valid(self) -> bool:
        return self.status is FeatureStatus.VALID


@dataclass(frozen=True)
class OpeningVolumeContext:
    mode: str
    value: FeatureValue
    provenance: str

    def __post_init__(self) -> None:
        if not self.mode.strip():
            raise ValueError("opening volume context mode must not be empty")
        if not self.provenance.strip():
            raise ValueError("opening volume context provenance must not be empty")


@dataclass(frozen=True)
class FeatureEvaluationContext:
    data_health: DataHealthSnapshot
    tick_coverage_started_at: datetime | None
    aggressor_mapping_verified: bool
    opening_volume_context: OpeningVolumeContext | None = None

    def __post_init__(self) -> None:
        if self.tick_coverage_started_at is not None:
            _require_aware(
                self.tick_coverage_started_at,
                "tick_coverage_started_at",
            )


@dataclass(frozen=True)
class FeatureEngineConfig:
    version: str = FEATURE_VERSION_V0
    price_lookback: timedelta = timedelta(minutes=2)
    price_lookback_tolerance: timedelta = timedelta(seconds=30)
    volume_window: timedelta = timedelta(minutes=2)
    baseline_window_count: int = 5
    minimum_complete_baseline_windows: int = 4
    order_book_max_age: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("feature config version must not be empty")
        if self.price_lookback <= timedelta(0):
            raise ValueError("price lookback must be positive")
        if self.price_lookback_tolerance < timedelta(0):
            raise ValueError("price lookback tolerance cannot be negative")
        if self.volume_window <= timedelta(0):
            raise ValueError("volume window must be positive")
        if self.baseline_window_count <= 0:
            raise ValueError("baseline window count must be positive")
        if not (
            1
            <= self.minimum_complete_baseline_windows
            <= self.baseline_window_count
        ):
            raise ValueError("minimum complete windows must fit baseline count")
        if self.order_book_max_age < timedelta(0):
            raise ValueError("order-book max age cannot be negative")


@dataclass(frozen=True)
class IntradayFeatureSnapshot:
    symbol: str
    as_of: datetime
    current_event_id: str
    feature_version: str
    data_health: DataHealthState
    required_inputs_valid: bool
    block_reasons: tuple[str, ...]
    price: FeatureValue
    vwap: FeatureValue
    previous_intraday_high: FeatureValue
    price_above_vwap: FeatureValue
    breakout: FeatureValue
    return_2m: FeatureValue
    distance_to_limit: FeatureValue
    volume_2m: FeatureValue
    baseline_2m: FeatureValue
    baseline_complete_windows: int
    volume_acceleration_2m: FeatureValue
    volume_vs_previous_2m: FeatureValue
    external_ratio_session: FeatureValue
    external_ratio_session_2m_ago: FeatureValue
    external_ratio_rising: FeatureValue
    bid_depth_5: FeatureValue
    ask_depth_5: FeatureValue
    bid_ask_ratio_5: FeatureValue
    book_imbalance_5: FeatureValue
    opening_volume_context: FeatureValue
    opening_volume_context_mode: str | None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("feature symbol must not be empty")
        if not self.current_event_id.strip():
            raise ValueError("current event id must not be empty")
        if not self.feature_version.strip():
            raise ValueError("feature version must not be empty")
        _require_aware(self.as_of, "feature as_of")
        if self.baseline_complete_windows < 0:
            raise ValueError("baseline complete windows cannot be negative")
