"""Data-only evidence capture for FreshnessPolicyV1 calibration.

This module intentionally does not select any freshness threshold and does not
touch the Portfolio, order, or broker-account domains.  It records the timing
evidence needed for a later human review to freeze quote thresholds.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from enum import Enum, StrEnum
from math import ceil
from pathlib import Path
from threading import Event, Lock
from time import monotonic_ns
from typing import Any, Mapping
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_SCHEMA_VERSION = "freshness_calibration_quote_v1"


class QuoteStreamKind(StrEnum):
    TICK = "TICK"
    BIDASK = "BIDASK"


class ConnectionState(StrEnum):
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


class SubscriptionState(StrEnum):
    INACTIVE = "INACTIVE"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class FreshnessCalibrationArtifactError(ValueError):
    """A capture artifact cannot be used as reviewable evidence."""


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _event_timestamp(event: object) -> datetime | None:
    value = getattr(event, "datetime", None)
    if isinstance(value, datetime):
        return value.replace(tzinfo=TAIPEI) if value.tzinfo is None else value.astimezone(TAIPEI)
    if isinstance(value, (list, tuple)) and len(value) >= 6:
        try:
            return datetime(*(int(part) for part in value[:7]), tzinfo=TAIPEI)
        except (TypeError, ValueError):
            return None

    event_date = getattr(event, "date", None)
    event_time = getattr(event, "time", None)
    if isinstance(event_date, date) and isinstance(event_time, time):
        combined = datetime.combine(event_date, event_time)
        return combined.replace(tzinfo=TAIPEI) if combined.tzinfo is None else combined.astimezone(TAIPEI)
    return None


@dataclass(frozen=True)
class QuoteFreshnessObservation:
    symbol: str
    liquidity_tier: str
    session_window: str
    stream_kind: QuoteStreamKind
    market_event_at: datetime | None
    callback_received_at: datetime
    store_updated_at: datetime
    callback_received_monotonic_ns: int
    store_updated_monotonic_ns: int
    connection_state: ConnectionState
    subscription_state: SubscriptionState

    def __post_init__(self) -> None:
        for field_name in ("symbol", "liquidity_tier", "session_window"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        for field_name in ("callback_received_at", "store_updated_at"):
            _require_aware(getattr(self, field_name), field_name)
        if self.market_event_at is not None:
            _require_aware(self.market_event_at, "market_event_at")
        if self.callback_received_monotonic_ns < 0:
            raise ValueError("callback_received_monotonic_ns must be non-negative")
        if self.store_updated_monotonic_ns < self.callback_received_monotonic_ns:
            raise ValueError("store_updated_monotonic_ns must not precede callback receipt")

    @property
    def event_to_callback_ms(self) -> float | None:
        if self.market_event_at is None:
            return None
        return (self.callback_received_at - self.market_event_at).total_seconds() * 1000.0

    @property
    def callback_to_store_ms(self) -> float:
        return (
            self.store_updated_monotonic_ns - self.callback_received_monotonic_ns
        ) / 1_000_000


@dataclass(frozen=True)
class ConnectionTransition:
    occurred_at: datetime
    connection_state: ConnectionState
    subscription_state: SubscriptionState
    detail: str
    raw_response_code: int | None = None
    raw_event_code: int | None = None
    raw_info: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        if not self.detail.strip():
            raise ValueError("detail must not be empty")


@dataclass
class LiveQuoteFreshnessCapture:
    """Thread-safe Tick/BidAsk callback collector with an explicit store boundary."""

    symbol_tiers: Mapping[str, str]
    session_window: str
    observations: list[QuoteFreshnessObservation] = field(default_factory=list)
    callback_counts: dict[str, int] = field(
        default_factory=lambda: {kind.value: 0 for kind in QuoteStreamKind}
    )
    callback_errors: list[str] = field(default_factory=list)
    connection_transitions: list[ConnectionTransition] = field(default_factory=list)
    connection_state: ConnectionState = ConnectionState.STARTING
    subscription_state: SubscriptionState = SubscriptionState.INACTIVE
    _subscription_states: dict[str, SubscriptionState] = field(
        default_factory=dict,
        repr=False,
    )
    _acknowledged_parts: dict[str, set[QuoteStreamKind]] = field(
        default_factory=dict,
        repr=False,
    )
    _lock: Lock = field(default_factory=Lock, repr=False)

    def __post_init__(self) -> None:
        normalized = {
            symbol.strip().upper(): tier.strip()
            for symbol, tier in self.symbol_tiers.items()
            if symbol.strip() and tier.strip()
        }
        if not normalized:
            raise ValueError("at least one symbol and liquidity tier are required")
        if not self.session_window.strip():
            raise ValueError("session_window must not be empty")
        self.symbol_tiers = normalized
        self._subscription_states = {
            symbol: self.subscription_state for symbol in normalized
        }
        self._acknowledged_parts = {symbol: set() for symbol in normalized}

    def transition(
        self,
        connection_state: ConnectionState,
        subscription_state: SubscriptionState,
        *,
        detail: str,
        raw_response_code: int | None = None,
        raw_event_code: int | None = None,
        raw_info: str | None = None,
    ) -> None:
        occurred_at = datetime.now(TAIPEI)
        with self._lock:
            self._set_state_locked(
                connection_state,
                subscription_state,
                occurred_at=occurred_at,
                detail=detail,
                raw_response_code=raw_response_code,
                raw_event_code=raw_event_code,
                raw_info=raw_info,
            )

    def on_tick(self, *callback_args: object) -> None:
        self._record(QuoteStreamKind.TICK, callback_args)

    def on_bidask(self, *callback_args: object) -> None:
        self._record(QuoteStreamKind.BIDASK, callback_args)

    def on_lifecycle(
        self,
        resp_code: int,
        event_code: int,
        info: str,
        event: str,
    ) -> None:
        """Retain SDK lifecycle evidence without treating callback silence as a fault."""
        occurred_at = datetime.now(TAIPEI)
        detail = str(event or info or f"event_code:{event_code}")
        symbol = self._symbol_from_lifecycle_info(info)
        with self._lock:
            connection_state = self.connection_state
            subscription_state = self.subscription_state
            if event_code in (1, 2):
                self._acknowledged_parts = {
                    configured_symbol: set()
                    for configured_symbol in self.symbol_tiers
                }
                self._subscription_states = {
                    configured_symbol: SubscriptionState.UNKNOWN
                    for configured_symbol in self.symbol_tiers
                }
                connection_state = ConnectionState.DISCONNECTED
                subscription_state = SubscriptionState.UNKNOWN
            elif event_code == 12:
                connection_state = ConnectionState.UNKNOWN
                subscription_state = SubscriptionState.UNKNOWN
            elif event_code == 13:
                self._acknowledged_parts = {
                    configured_symbol: set()
                    for configured_symbol in self.symbol_tiers
                }
                self._subscription_states = {
                    configured_symbol: SubscriptionState.PENDING
                    for configured_symbol in self.symbol_tiers
                }
                connection_state = ConnectionState.CONNECTED
                subscription_state = SubscriptionState.PENDING
            elif event_code == 16 and symbol is not None:
                part = self._part_from_lifecycle_info(info)
                if part is not None:
                    acknowledged = self._acknowledged_parts[symbol]
                    acknowledged.add(part)
                    if acknowledged == set(QuoteStreamKind):
                        self._subscription_states[symbol] = SubscriptionState.ACTIVE
                subscription_state = self._aggregate_subscription_state_locked()
            elif event_code == 4:
                if symbol is None:
                    self._subscription_states = {
                        configured_symbol: SubscriptionState.FAILED
                        for configured_symbol in self.symbol_tiers
                    }
                else:
                    self._subscription_states[symbol] = SubscriptionState.FAILED
                subscription_state = self._aggregate_subscription_state_locked()
            self._set_state_locked(
                connection_state,
                subscription_state,
                occurred_at=occurred_at,
                detail=detail,
                raw_response_code=resp_code,
                raw_event_code=event_code,
                raw_info=info,
            )

    def _record(
        self,
        stream_kind: QuoteStreamKind,
        callback_args: tuple[object, ...],
    ) -> None:
        event = callback_args[-1] if callback_args else None
        if event is None or bool(getattr(event, "intraday_odd", False)):
            return
        callback_received_at = datetime.now(TAIPEI)
        callback_received_monotonic = monotonic_ns()
        symbol = str(getattr(event, "code", "")).strip().upper()
        try:
            market_event_at = _event_timestamp(event)
            with self._lock:
                self.callback_counts[stream_kind.value] += 1
                liquidity_tier = self.symbol_tiers.get(symbol)
                if liquidity_tier is None:
                    return
                store_updated_at = datetime.now(TAIPEI)
                store_updated_monotonic = monotonic_ns()
                self.observations.append(
                    QuoteFreshnessObservation(
                        symbol=symbol,
                        liquidity_tier=liquidity_tier,
                        session_window=self.session_window,
                        stream_kind=stream_kind,
                        market_event_at=market_event_at,
                        callback_received_at=callback_received_at,
                        store_updated_at=store_updated_at,
                        callback_received_monotonic_ns=callback_received_monotonic,
                        store_updated_monotonic_ns=store_updated_monotonic,
                        connection_state=self.connection_state,
                        subscription_state=self._subscription_states[symbol],
                    )
                )
        except Exception as error:  # a malformed callback must not terminate the feed
            with self._lock:
                self.callback_errors.append(
                    f"{stream_kind.value}:{type(error).__name__}:{error}"
                )

    def payload(
        self,
        *,
        started_at: datetime,
        ended_at: datetime,
        simulation: bool,
        sdk_version: str,
    ) -> dict[str, object]:
        _require_aware(started_at, "started_at")
        _require_aware(ended_at, "ended_at")
        if ended_at < started_at:
            raise ValueError("ended_at must not precede started_at")
        with self._lock:
            return {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "sdk_version": sdk_version,
                "simulation": simulation,
                "started_at": started_at,
                "ended_at": ended_at,
                "session_window": self.session_window,
                "symbol_tiers": dict(self.symbol_tiers),
                "store_boundary": "calibration_in_memory_buffer",
                "callback_counts": dict(self.callback_counts),
                "callback_errors": tuple(self.callback_errors),
                "connection_transitions": tuple(self.connection_transitions),
                "observations": tuple(self.observations),
                "threshold_selection": "PROHIBITED_IN_CAPTURE_ARTIFACT",
            }

    def _set_state_locked(
        self,
        connection_state: ConnectionState,
        subscription_state: SubscriptionState,
        *,
        occurred_at: datetime,
        detail: str,
        raw_response_code: int | None,
        raw_event_code: int | None,
        raw_info: str | None,
    ) -> None:
        self.connection_state = connection_state
        self.subscription_state = subscription_state
        if subscription_state in {
            SubscriptionState.INACTIVE,
            SubscriptionState.PENDING,
            SubscriptionState.UNKNOWN,
        }:
            self._subscription_states = {
                symbol: subscription_state for symbol in self.symbol_tiers
            }
        self.connection_transitions.append(
            ConnectionTransition(
                occurred_at=occurred_at,
                connection_state=connection_state,
                subscription_state=subscription_state,
                detail=detail,
                raw_response_code=raw_response_code,
                raw_event_code=raw_event_code,
                raw_info=raw_info,
            )
        )

    def _aggregate_subscription_state_locked(self) -> SubscriptionState:
        states = set(self._subscription_states.values())
        if SubscriptionState.FAILED in states:
            return SubscriptionState.FAILED
        if states == {SubscriptionState.ACTIVE}:
            return SubscriptionState.ACTIVE
        if SubscriptionState.PENDING in states:
            return SubscriptionState.PENDING
        if SubscriptionState.UNKNOWN in states:
            return SubscriptionState.UNKNOWN
        return SubscriptionState.INACTIVE

    def _symbol_from_lifecycle_info(self, info: str) -> str | None:
        symbol = str(info).rsplit("/", maxsplit=1)[-1].strip().upper()
        return symbol if symbol in self.symbol_tiers else None

    @staticmethod
    def _part_from_lifecycle_info(info: str) -> QuoteStreamKind | None:
        normalized = str(info).upper()
        if "/TIC/" in f"/{normalized}":
            return QuoteStreamKind.TICK
        if "/QUO/" in f"/{normalized}":
            return QuoteStreamKind.BIDASK
        return None


def run_live_quote_freshness_capture(
    *,
    symbol_tiers: Mapping[str, str],
    session_window: str,
    duration_seconds: int,
    output_directory: Path,
) -> tuple[Path, dict[str, object]]:
    """Capture Tick/BidAsk timing only; never calls any order or account API."""
    if duration_seconds <= 0 or duration_seconds > 14_400:
        raise ValueError("duration_seconds must be between 1 and 14400")

    from dotenv import load_dotenv
    import shioaji as sj

    load_dotenv()
    api_key = os.getenv("SHIOAJI_API_KEY") or os.getenv("SJ_API_KEY")
    secret = (
        os.getenv("SHIOAJI_SECRET")
        or os.getenv("SJ_SECRET_KEY")
        or os.getenv("SJ_SEC_KEY")
    )
    if not api_key or not secret:
        raise RuntimeError("Shioaji data credentials are not configured")

    simulation = os.getenv("SJ_SIMULATION", "true").lower() != "false"
    capture = LiveQuoteFreshnessCapture(symbol_tiers, session_window)
    api = sj.Shioaji(simulation=simulation)
    subscribed: list[tuple[object, object]] = []
    started_at = datetime.now(TAIPEI)
    try:
        api.login(api_key=api_key, secret_key=secret, subscribe_trade=False)
        capture.transition(
            ConnectionState.CONNECTED,
            SubscriptionState.PENDING,
            detail="market_data_login",
        )
        api.set_on_tick_stk_v1_callback(capture.on_tick)
        api.set_on_bidask_stk_v1_callback(capture.on_bidask)
        api.set_event_callback(capture.on_lifecycle)
        for symbol in capture.symbol_tiers:
            contract = api.Contracts.Stocks[symbol]
            if contract is None:
                raise KeyError(f"Contract not found: {symbol}")
            for quote_type in (sj.QuoteType.Tick, sj.QuoteType.BidAsk):
                api.subscribe(contract, quote_type=quote_type, version=sj.QuoteVersion.v1)
                subscribed.append((contract, quote_type))
        Event().wait(duration_seconds)
    finally:
        for contract, quote_type in reversed(subscribed):
            try:
                api.unsubscribe(contract, quote_type=quote_type, version=sj.QuoteVersion.v1)
            except Exception:
                pass
        capture.transition(
            ConnectionState.DISCONNECTED,
            SubscriptionState.INACTIVE,
            detail="capture_cleanup",
        )
        for clear_name in (
            "clear_on_tick_stk_v1_callback",
            "clear_on_bidask_stk_v1_callback",
            "clear_event_callback",
        ):
            try:
                getattr(api, clear_name)()
            except Exception:
                pass
        try:
            api.logout()
        except Exception:
            pass

    payload = capture.payload(
        started_at=started_at,
        ended_at=datetime.now(TAIPEI),
        simulation=simulation,
        sdk_version=getattr(sj, "__version__", "unknown"),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = f"quote_{started_at.strftime('%Y%m%dT%H%M%S%z')}.json"
    output_path = output_directory / filename
    _write_json_once(output_path, payload)
    return output_path, analyze_quote_freshness_payload(payload)


def inspect_quote_freshness_artifact(path: Path) -> dict[str, object]:
    raw, payload = _load_payload(path)
    _validate_capture_metadata(payload)
    observations = _observations_from_payload(payload)
    return {
        "artifact_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_count": len(observations),
        "analysis": analyze_quote_freshness_payload(payload),
    }


def analyze_quote_freshness_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Summarize raw evidence without proposing a policy threshold."""
    observations = _observations_from_payload(payload)
    callback_errors = _required_string_list(payload, "callback_errors")
    groups: dict[tuple[str, str, str, str], list[QuoteFreshnessObservation]] = defaultdict(list)
    for observation in observations:
        groups[
            (
                observation.symbol,
                observation.liquidity_tier,
                observation.session_window,
                observation.stream_kind.value,
            )
        ].append(observation)

    observed_kinds = {item.stream_kind for item in observations}
    summaries = [
        _summarize_group(key, group)
        for key, group in sorted(groups.items())
    ]
    status = "REVIEW_REQUIRED"
    if not observations:
        status = "INSUFFICIENT_EVIDENCE"
    elif callback_errors:
        status = "REVIEW_REQUIRED_WITH_CALLBACK_ERRORS"
    return {
        "review_status": status,
        "threshold_candidates": None,
        "threshold_selection": "NOT_PERFORMED",
        "percentile_method": "nearest_rank",
        "observation_count": len(observations),
        "missing_stream_kinds": [
            kind.value for kind in QuoteStreamKind if kind not in observed_kinds
        ],
        "callback_errors": callback_errors,
        "groups": summaries,
        "limitations": [
            "This artifact measures the calibration buffer, not an unimplemented Portfolio projection path.",
            "Clock-skew observations are retained in the raw distributions and require reviewer disposition.",
            "No broker/account freshness metric is represented by this quote artifact.",
        ],
    }


def _summarize_group(
    key: tuple[str, str, str, str],
    observations: list[QuoteFreshnessObservation],
) -> dict[str, object]:
    event_to_callback = [
        value
        for observation in observations
        if (value := observation.event_to_callback_ms) is not None
    ]
    callback_to_store = [
        observation.callback_to_store_ms for observation in observations
    ]
    inter_arrival: list[float] = []
    monotonic_regressions = 0
    previous: int | None = None
    for observation in observations:
        current = observation.callback_received_monotonic_ns
        if previous is not None:
            if current < previous:
                monotonic_regressions += 1
            else:
                inter_arrival.append((current - previous) / 1_000_000)
        previous = current
    symbol, liquidity_tier, session_window, stream_kind = key
    return {
        "symbol": symbol,
        "liquidity_tier": liquidity_tier,
        "session_window": session_window,
        "stream_kind": stream_kind,
        "observation_count": len(observations),
        "missing_market_event_at_count": len(observations) - len(event_to_callback),
        "source_clock_skew_count": sum(value < 0 for value in event_to_callback),
        "callback_monotonic_regression_count": monotonic_regressions,
        "event_to_callback_ms": _distribution(event_to_callback),
        "callback_to_store_ms": _distribution(callback_to_store),
        "inter_arrival_ms": _distribution(inter_arrival),
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "p99": None, "max": None}
    sorted_values = sorted(values)
    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "p50": _nearest_rank(sorted_values, 0.50),
        "p95": _nearest_rank(sorted_values, 0.95),
        "p99": _nearest_rank(sorted_values, 0.99),
        "max": sorted_values[-1],
    }


def _nearest_rank(sorted_values: list[float], percentile: float) -> float:
    return sorted_values[max(0, ceil(percentile * len(sorted_values)) - 1)]


def _load_payload(path: Path) -> tuple[bytes, Mapping[str, object]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FreshnessCalibrationArtifactError("artifact must be valid JSON") from error
    if not isinstance(payload, Mapping):
        raise FreshnessCalibrationArtifactError("artifact must be an object")
    return raw, payload


def _observations_from_payload(payload: Mapping[str, object]) -> list[QuoteFreshnessObservation]:
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise FreshnessCalibrationArtifactError("unsupported freshness capture schema")
    values = payload.get("observations")
    if not isinstance(values, (list, tuple)):
        raise FreshnessCalibrationArtifactError("observations must be a list")
    return [
        value if isinstance(value, QuoteFreshnessObservation) else _observation_from_payload(value)
        for value in values
    ]


def _validate_capture_metadata(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise FreshnessCalibrationArtifactError("unsupported freshness capture schema")
    started_at = _required_datetime(payload, "started_at")
    ended_at = _required_datetime(payload, "ended_at")
    if ended_at < started_at:
        raise FreshnessCalibrationArtifactError("ended_at must not precede started_at")
    _required_string(payload, "session_window")
    symbol_tiers = payload.get("symbol_tiers")
    if not isinstance(symbol_tiers, Mapping) or not symbol_tiers:
        raise FreshnessCalibrationArtifactError("symbol_tiers must be a non-empty object")
    for symbol, tier in symbol_tiers.items():
        if not isinstance(symbol, str) or not symbol.strip() or not isinstance(tier, str) or not tier.strip():
            raise FreshnessCalibrationArtifactError("symbol_tiers entries must be non-empty strings")
    if payload.get("store_boundary") != "calibration_in_memory_buffer":
        raise FreshnessCalibrationArtifactError("store_boundary is invalid")
    if payload.get("threshold_selection") != "PROHIBITED_IN_CAPTURE_ARTIFACT":
        raise FreshnessCalibrationArtifactError("threshold_selection is invalid")
    callback_counts = payload.get("callback_counts")
    if not isinstance(callback_counts, Mapping):
        raise FreshnessCalibrationArtifactError("callback_counts must be an object")
    for kind in QuoteStreamKind:
        value = callback_counts.get(kind.value)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FreshnessCalibrationArtifactError(
                f"callback_counts.{kind.value} must be a non-negative integer"
            )
    transitions = payload.get("connection_transitions")
    if not isinstance(transitions, list):
        raise FreshnessCalibrationArtifactError("connection_transitions must be a list")
    for transition in transitions:
        _transition_from_payload(transition)


def _transition_from_payload(value: object) -> ConnectionTransition:
    if not isinstance(value, Mapping):
        raise FreshnessCalibrationArtifactError("connection transition must be an object")
    try:
        return ConnectionTransition(
            occurred_at=_required_datetime(value, "occurred_at"),
            connection_state=ConnectionState(_required_string(value, "connection_state")),
            subscription_state=SubscriptionState(_required_string(value, "subscription_state")),
            detail=_required_string(value, "detail"),
            raw_response_code=_optional_int(value, "raw_response_code"),
            raw_event_code=_optional_int(value, "raw_event_code"),
            raw_info=_optional_string(value, "raw_info"),
        )
    except ValueError as error:
        raise FreshnessCalibrationArtifactError(str(error)) from error


def _observation_from_payload(value: object) -> QuoteFreshnessObservation:
    if not isinstance(value, Mapping):
        raise FreshnessCalibrationArtifactError("observation must be an object")
    try:
        return QuoteFreshnessObservation(
            symbol=_required_string(value, "symbol"),
            liquidity_tier=_required_string(value, "liquidity_tier"),
            session_window=_required_string(value, "session_window"),
            stream_kind=QuoteStreamKind(_required_string(value, "stream_kind")),
            market_event_at=_optional_datetime(value, "market_event_at"),
            callback_received_at=_required_datetime(value, "callback_received_at"),
            store_updated_at=_required_datetime(value, "store_updated_at"),
            callback_received_monotonic_ns=_required_non_negative_int(
                value, "callback_received_monotonic_ns"
            ),
            store_updated_monotonic_ns=_required_non_negative_int(
                value, "store_updated_monotonic_ns"
            ),
            connection_state=ConnectionState(_required_string(value, "connection_state")),
            subscription_state=SubscriptionState(_required_string(value, "subscription_state")),
        )
    except ValueError as error:
        raise FreshnessCalibrationArtifactError(str(error)) from error


def _required_string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise FreshnessCalibrationArtifactError(f"{field_name} must be a non-empty string")
    return value


def _required_string_list(payload: Mapping[str, object], field_name: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise FreshnessCalibrationArtifactError(f"{field_name} must be a list of strings")
    return list(value)


def _required_datetime(payload: Mapping[str, object], field_name: str) -> datetime:
    value = _required_string(payload, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise FreshnessCalibrationArtifactError(f"{field_name} must be ISO-8601") from error
    try:
        _require_aware(parsed, field_name)
    except ValueError as error:
        raise FreshnessCalibrationArtifactError(str(error)) from error
    return parsed


def _optional_datetime(payload: Mapping[str, object], field_name: str) -> datetime | None:
    if payload.get(field_name) is None:
        return None
    return _required_datetime(payload, field_name)


def _required_non_negative_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FreshnessCalibrationArtifactError(f"{field_name} must be a non-negative integer")
    return value


def _optional_int(payload: Mapping[str, object], field_name: str) -> int | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FreshnessCalibrationArtifactError(f"{field_name} must be an integer or null")
    return value


def _optional_string(payload: Mapping[str, object], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise FreshnessCalibrationArtifactError(f"{field_name} must be a string or null")
    return value


def _write_json_once(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(payload, file, default=_json_default, ensure_ascii=False, indent=2)
        file.write("\n")


def _json_default(value: Any) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
