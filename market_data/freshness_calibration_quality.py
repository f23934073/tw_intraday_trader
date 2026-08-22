"""Review-ready structural QA for immutable quote-freshness artifacts.

This module deliberately reports evidence quality only. It never selects a
freshness duration, does not read broker/account data, and does not alter raw
artifacts when a check fails.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from market_data.freshness_calibration import (
    FreshnessCalibrationArtifactError,
    inspect_quote_freshness_artifact,
)


_STREAM_MARKERS = {"TICK": "/TIC/", "BIDASK": "/QUO/"}


def summarize_post_capture_quality(
    artifact_path: Path,
    *,
    expected_symbol_tiers: Mapping[str, str],
    expected_session_window: str,
) -> dict[str, object]:
    """Return structural QA for one artifact without promoting its evidence.

    Structural parse/digest failures raise ``FreshnessCalibrationArtifactError``.
    Valid artifacts with missing callbacks remain reviewable partial evidence.
    """
    inspection = inspect_quote_freshness_artifact(artifact_path)
    try:
        raw = artifact_path.read_bytes()
        if sha256(raw).hexdigest() != inspection["sha256"]:
            raise FreshnessCalibrationArtifactError(
                "artifact changed between structural inspection and QA summary"
            )
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise FreshnessCalibrationArtifactError(
            f"cannot read inspected artifact: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise FreshnessCalibrationArtifactError("inspected artifact must be an object")

    expected = {
        (symbol, tier, expected_session_window, stream_kind)
        for symbol, tier in expected_symbol_tiers.items()
        for stream_kind in _STREAM_MARKERS
    }
    analysis = inspection["analysis"]
    if not isinstance(analysis, dict):
        raise FreshnessCalibrationArtifactError("artifact analysis must be an object")
    groups = analysis.get("groups")
    if not isinstance(groups, list):
        raise FreshnessCalibrationArtifactError("artifact analysis groups must be a list")
    observed = {
        (
            str(group["symbol"]),
            str(group["liquidity_tier"]),
            str(group["session_window"]),
            str(group["stream_kind"]),
        )
        for group in groups
        if isinstance(group, dict) and int(group.get("observation_count", 0)) > 0
    }
    missing_groups = sorted(expected - observed)
    unexpected_groups = sorted(observed - expected)

    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise FreshnessCalibrationArtifactError("artifact observations must be a list")
    lifecycle_failures = [
        index
        for index, observation in enumerate(observations)
        if not isinstance(observation, dict)
        or observation.get("connection_state") != "CONNECTED"
        or observation.get("subscription_state") != "ACTIVE"
    ]
    acknowledged = _acknowledged_groups(
        payload.get("connection_transitions"), expected_symbol_tiers
    )
    missing_acknowledgements = sorted(
        (symbol, stream_kind)
        for symbol in expected_symbol_tiers
        for stream_kind in _STREAM_MARKERS
        if (symbol, stream_kind) not in acknowledged
    )
    callback_errors = analysis.get("callback_errors")
    if not isinstance(callback_errors, list):
        raise FreshnessCalibrationArtifactError("artifact callback_errors must be a list")

    monotonic_regressions = sum(
        int(group.get("callback_monotonic_regression_count", 0))
        for group in groups
        if isinstance(group, dict)
    )
    source_clock_skew = sum(
        int(group.get("source_clock_skew_count", 0))
        for group in groups
        if isinstance(group, dict)
    )
    quality_issues = bool(
        unexpected_groups
        or lifecycle_failures
        or missing_acknowledgements
        or callback_errors
        or monotonic_regressions
    )
    if quality_issues:
        quality_status = "REVIEW_REQUIRED_WITH_QUALITY_ISSUES"
    elif missing_groups:
        quality_status = "REVIEW_REQUIRED_PARTIAL_COVERAGE"
    else:
        quality_status = "REVIEW_REQUIRED"

    return {
        "schema_version": "freshness_post_capture_quality_v1",
        "artifact": {
            "name": inspection["artifact_name"],
            "sha256": inspection["sha256"],
            "byte_length": inspection["byte_length"],
            "schema_version": inspection["schema_version"],
        },
        "expected_session_window": expected_session_window,
        "expected_group_count": len(expected),
        "observed_group_count": len(observed & expected),
        "missing_groups": [_group_dict(group) for group in missing_groups],
        "unexpected_groups": [_group_dict(group) for group in unexpected_groups],
        "paired_acknowledgement": {
            "acknowledged_group_count": len(acknowledged),
            "missing_groups": [
                {"symbol": symbol, "stream_kind": stream_kind}
                for symbol, stream_kind in missing_acknowledgements
            ],
        },
        "observation_lifecycle": {
            "observation_count": len(observations),
            "non_connected_active_observation_indices": lifecycle_failures,
        },
        "callback_errors": callback_errors,
        "callback_monotonic_regression_count": monotonic_regressions,
        "source_clock_skew_count": source_clock_skew,
        "quality_status": quality_status,
        "threshold_selection": "NOT_PERFORMED",
        "threshold_candidates": None,
        "limitations": [
            "This is structural evidence QA, not a FreshnessPolicyV1 decision.",
            "Partial callback coverage remains reviewable evidence and is never synthesized.",
            "No broker/account freshness metric is represented by this summary.",
        ],
    }


def _acknowledged_groups(
    transitions: object,
    expected_symbol_tiers: Mapping[str, str],
) -> set[tuple[str, str]]:
    if not isinstance(transitions, list):
        raise FreshnessCalibrationArtifactError("artifact connection_transitions must be a list")
    acknowledged: set[tuple[str, str]] = set()
    for transition in transitions:
        if not isinstance(transition, dict) or transition.get("raw_event_code") != 16:
            continue
        info = str(transition.get("raw_info") or "").upper()
        normalized_info = f"/{info.strip('/')}"
        for symbol in expected_symbol_tiers:
            if not normalized_info.endswith(f"/{symbol}"):
                continue
            for stream_kind, marker in _STREAM_MARKERS.items():
                if marker in normalized_info:
                    acknowledged.add((symbol, stream_kind))
    return acknowledged


def _group_dict(group: tuple[str, str, str, str]) -> dict[str, str]:
    symbol, liquidity_tier, session_window, stream_kind = group
    return {
        "symbol": symbol,
        "liquidity_tier": liquidity_tier,
        "session_window": session_window,
        "stream_kind": stream_kind,
    }
