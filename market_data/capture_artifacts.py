"""Offline integrity and shape validation for Quote-parity capture artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from config.momentum import QuoteSubscriptionMode
from market_data.quote_qualification import (
    ObservationKind,
    StreamCapture,
    StreamObservation,
)
from market_data.shioaji_quote_capture import CAPTURE_SCHEMA_VERSION


class CaptureArtifactValidationError(ValueError):
    """The capture cannot be treated as reviewable evidence."""


@dataclass(frozen=True)
class CaptureArtifactManifest:
    """Digest and bounded metadata derived from immutable capture bytes."""

    artifact_name: str
    sha256: str
    byte_length: int
    schema_version: str
    symbol: str
    started_at: datetime
    ended_at: datetime
    quote_observation_count: int
    tick_bidask_observation_count: int
    quote_callback_count: int
    tick_callback_count: int
    bidask_callback_count: int
    preliminary_status: str


@dataclass(frozen=True)
class LoadedCaptureArtifact:
    """A validated local capture rehydrated for deterministic parity replay."""

    manifest: CaptureArtifactManifest
    quote_capture: StreamCapture
    tick_bidask_capture: StreamCapture


def inspect_capture_artifact(path: Path) -> CaptureArtifactManifest:
    """Read only bounded metadata without initializing an SDK or provider."""

    raw, payload = _load_payload(path)
    return _build_manifest(path, raw, payload)


def load_capture_artifact(path: Path) -> LoadedCaptureArtifact:
    """Rehydrate one validated local capture for offline parity evaluation."""

    raw, payload = _load_payload(path)
    manifest = _build_manifest(path, raw, payload)
    quote_payload = _capture(payload, "quote_capture", "QUOTE", manifest.symbol)
    paired_payload = _capture(
        payload,
        "tick_bidask_capture",
        "TICK_BIDASK",
        manifest.symbol,
    )
    return LoadedCaptureArtifact(
        manifest=manifest,
        quote_capture=_rehydrate_capture(
            quote_payload,
            QuoteSubscriptionMode.QUOTE,
        ),
        tick_bidask_capture=_rehydrate_capture(
            paired_payload,
            QuoteSubscriptionMode.TICK_BIDASK,
        ),
    )


def _load_payload(path: Path) -> tuple[bytes, Mapping[str, Any]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CaptureArtifactValidationError("capture artifact is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise CaptureArtifactValidationError("capture artifact must contain one object")
    return raw, payload



def _build_manifest(
    path: Path,
    raw: bytes,
    payload: Mapping[str, Any],
) -> CaptureArtifactManifest:
    schema_version = _required_string(payload, "schema_version")
    if schema_version != CAPTURE_SCHEMA_VERSION:
        raise CaptureArtifactValidationError("capture schema version is unsupported")
    symbol = _required_string(payload, "symbol")
    started_at = _required_aware_time(payload, "started_at")
    ended_at = _required_aware_time(payload, "ended_at")
    if ended_at < started_at:
        raise CaptureArtifactValidationError("capture ended before it started")

    quote_payload = _capture(payload, "quote_capture", "QUOTE", symbol)
    paired_payload = _capture(payload, "tick_bidask_capture", "TICK_BIDASK", symbol)
    callback_counts = _required_mapping(payload, "callback_counts")
    preliminary_report = _required_mapping(payload, "preliminary_report")

    manifest = CaptureArtifactManifest(
        artifact_name=path.name,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_length=len(raw),
        schema_version=schema_version,
        symbol=symbol,
        started_at=started_at,
        ended_at=ended_at,
        quote_observation_count=len(quote_payload["observations"]),
        tick_bidask_observation_count=len(paired_payload["observations"]),
        quote_callback_count=_required_non_negative_int(callback_counts, "quote"),
        tick_callback_count=_required_non_negative_int(callback_counts, "tick"),
        bidask_callback_count=_required_non_negative_int(callback_counts, "bidask"),
        preliminary_status=_required_status(preliminary_report),
    )
    return manifest


def _capture(
    payload: Mapping[str, Any],
    name: str,
    expected_source_mode: str,
    symbol: str,
) -> Mapping[str, Any]:
    capture = _required_mapping(payload, name)
    if _required_string(capture, "source_mode") != expected_source_mode:
        raise CaptureArtifactValidationError(f"{name} source mode is invalid")
    if _required_string(capture, "symbol") != symbol:
        raise CaptureArtifactValidationError(f"{name} symbol does not match artifact")
    observations = capture.get("observations")
    if not isinstance(observations, list):
        raise CaptureArtifactValidationError(f"{name} observations must be a list")
    return capture


def _rehydrate_capture(
    payload: Mapping[str, Any],
    source_mode: QuoteSubscriptionMode,
) -> StreamCapture:
    symbol = _required_string(payload, "symbol")
    observations = payload["observations"]
    assert isinstance(observations, list)
    return StreamCapture(
        source_mode=source_mode,
        symbol=symbol,
        observations=tuple(
            _rehydrate_observation(item, source_mode, symbol)
            for item in observations
        ),
        reconnect_attempted=_required_bool(payload, "reconnect_attempted"),
        continuity_verified_after_reconnect=_optional_bool(
            payload,
            "continuity_verified_after_reconnect",
        ),
    )


def _rehydrate_observation(
    payload: object,
    source_mode: QuoteSubscriptionMode,
    symbol: str,
) -> StreamObservation:
    if not isinstance(payload, Mapping):
        raise CaptureArtifactValidationError("observation must be an object")
    if _required_string(payload, "source_mode") != source_mode.value:
        raise CaptureArtifactValidationError("observation source mode is invalid")
    if _required_string(payload, "symbol") != symbol:
        raise CaptureArtifactValidationError("observation symbol is invalid")
    try:
        kind = ObservationKind(_required_string(payload, "kind"))
    except ValueError as error:
        raise CaptureArtifactValidationError("observation kind is invalid") from error
    return StreamObservation(
        source_mode=source_mode,
        symbol=symbol,
        kind=kind,
        event_time=_required_aware_time(payload, "event_time"),
        received_at=_required_aware_time(payload, "received_at"),
        is_baseline=_required_bool(payload, "is_baseline"),
        total_volume_lots=_optional_non_negative_int(payload, "total_volume_lots"),
        total_amount=_optional_decimal(payload, "total_amount"),
        last_price=_optional_decimal(payload, "last_price"),
        average_price=_optional_decimal(payload, "average_price"),
        raw_tick_type=_optional_int(payload, "raw_tick_type"),
        bid_side_total_lots=_optional_non_negative_int(
            payload,
            "bid_side_total_lots",
        ),
        ask_side_total_lots=_optional_non_negative_int(
            payload,
            "ask_side_total_lots",
        ),
        bid_prices=_optional_decimal_tuple(payload, "bid_prices"),
        bid_volume_lots=_optional_non_negative_int_tuple(
            payload,
            "bid_volume_lots",
        ),
        ask_prices=_optional_decimal_tuple(payload, "ask_prices"),
        ask_volume_lots=_optional_non_negative_int_tuple(
            payload,
            "ask_volume_lots",
        ),
    )


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise CaptureArtifactValidationError(f"{name} must be an object")
    return value


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CaptureArtifactValidationError(f"{name} must be a non-empty string")
    return value


def _required_aware_time(payload: Mapping[str, Any], name: str) -> datetime:
    value = _required_string(payload, name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CaptureArtifactValidationError(f"{name} must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureArtifactValidationError(f"{name} must include a timezone")
    return parsed


def _required_non_negative_int(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CaptureArtifactValidationError(f"{name} must be a non-negative integer")
    return value


def _optional_non_negative_int(
    payload: Mapping[str, Any],
    name: str,
) -> int | None:
    if payload.get(name) is None:
        return None
    return _required_non_negative_int(payload, name)


def _optional_int(payload: Mapping[str, Any], name: str) -> int | None:
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaptureArtifactValidationError(f"{name} must be an integer")
    return value


def _optional_decimal(payload: Mapping[str, Any], name: str) -> Decimal | None:
    value = payload.get(name)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise CaptureArtifactValidationError(f"{name} must be decimal-compatible") from error


def _optional_decimal_tuple(
    payload: Mapping[str, Any],
    name: str,
) -> tuple[Decimal, ...]:
    values = payload.get(name)
    if not isinstance(values, list):
        raise CaptureArtifactValidationError(f"{name} must be a list")
    result: list[Decimal] = []
    for value in values:
        try:
            result.append(Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise CaptureArtifactValidationError(
                f"{name} values must be decimal-compatible"
            ) from error
    return tuple(result)


def _optional_non_negative_int_tuple(
    payload: Mapping[str, Any],
    name: str,
) -> tuple[int, ...]:
    values = payload.get(name)
    if not isinstance(values, list):
        raise CaptureArtifactValidationError(f"{name} must be a list")
    return tuple(_required_non_negative_int({name: value}, name) for value in values)


def _required_bool(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise CaptureArtifactValidationError(f"{name} must be a boolean")
    return value


def _optional_bool(payload: Mapping[str, Any], name: str) -> bool | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise CaptureArtifactValidationError(f"{name} must be a boolean or null")
    return value


def _required_status(payload: Mapping[str, Any]) -> str:
    value = _required_string(payload, "status")
    if value not in {"PASS", "FAIL", "INCOMPLETE"}:
        raise CaptureArtifactValidationError("preliminary report status is invalid")
    return value
