"""Offline evaluation for the frozen credentialed intraday source probe."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json

from institutional_data.serialization import canonical_json, sha256_text
from market_data.daily_kbar_qualification import resolve_shioaji_timestamp


REGULAR_START = time(9, 0)
REGULAR_END = time(13, 30)
PRICE_FIELDS = (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"))


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"invalid decimal value: {value!r}") from error
    if not result.is_finite():
        raise ValueError("numeric value must be finite")
    return result


def _raw_decimal(row: Mapping[str, Any], field: str) -> Decimal:
    value = row.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"reference row missing {field}")
    return _decimal(value.get("text"))


def _candidate_timestamp(row: Mapping[str, Any]) -> datetime:
    parsed = datetime.fromisoformat(str(row["date"]))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("candidate timestamp must include timezone")
    return parsed


def _reference_label_for(candidate_timestamp: datetime) -> datetime:
    # The controlled payloads establish Fugle start labels and Shioaji end
    # labels. Taiwan's 13:30 closing-auction bar is labelled 13:30 by both.
    if candidate_timestamp.timetz().replace(tzinfo=None) == REGULAR_END:
        return candidate_timestamp
    return candidate_timestamp + timedelta(minutes=1)


def inspect_candidate_payload(payload: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    if str(payload.get("symbol")) != symbol:
        raise ValueError("candidate payload symbol mismatch")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("candidate payload data must be a list")
    timestamps: list[datetime] = []
    issues: list[str] = []
    total_volume_lots = Decimal(0)
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("candidate row must be an object")
        timestamp = _candidate_timestamp(row)
        timestamps.append(timestamp)
        local_time = timestamp.timetz().replace(tzinfo=None)
        if not (REGULAR_START <= local_time <= REGULAR_END):
            issues.append("OUTSIDE_REGULAR_SESSION")
        if timestamp.second or timestamp.microsecond:
            issues.append("NOT_EXACT_MINUTE")
        for field, _ in PRICE_FIELDS:
            _decimal(row[field])
        total_volume_lots += _decimal(row["volume"])
        _decimal(row["average"])
    if timestamps != sorted(timestamps):
        issues.append("TIMESTAMP_NOT_MONOTONIC")
    if len(timestamps) != len(set(timestamps)):
        issues.append("DUPLICATE_TIMESTAMP")
    if not rows:
        issues.append("HTTP_200_EMPTY_DATA")
    return {
        "bar_count": len(rows),
        "first_timestamp": timestamps[0].isoformat() if timestamps else None,
        "issues": sorted(set(issues)),
        "last_average": str(_decimal(rows[-1]["average"])) if rows else None,
        "last_timestamp": timestamps[-1].isoformat() if timestamps else None,
        "total_volume_lots": str(total_volume_lots),
        "total_volume_shares": str(total_volume_lots * Decimal(1000)),
    }


def reconcile_control(
    candidate_payload: Mapping[str, Any],
    reference_capture: Mapping[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    candidate = inspect_candidate_payload(candidate_payload, symbol=symbol)
    candidate_rows = candidate_payload["data"]
    reference_rows = reference_capture.get("raw_rows")
    if not isinstance(candidate_rows, list) or not isinstance(reference_rows, list):
        raise ValueError("control rows must be lists")

    reference_by_time: dict[datetime, Mapping[str, Any]] = {}
    reference_amount = Decimal(0)
    reference_volume_lots = Decimal(0)
    for raw_row in reference_rows:
        if not isinstance(raw_row, Mapping):
            raise ValueError("reference row must be an object")
        timestamp = resolve_shioaji_timestamp(raw_row["ts"])
        reference_by_time[timestamp] = raw_row
        reference_amount += _raw_decimal(raw_row, "Amount")
        reference_volume_lots += _raw_decimal(raw_row, "Volume")

    matched_bars = 0
    ohlc_mismatch_count = 0
    volume_mismatch_count = 0
    for row in candidate_rows:
        assert isinstance(row, Mapping)
        reference = reference_by_time.get(_reference_label_for(_candidate_timestamp(row)))
        if reference is None:
            continue
        matched_bars += 1
        for candidate_field, reference_field in PRICE_FIELDS:
            if _decimal(row[candidate_field]) != _raw_decimal(reference, reference_field):
                ohlc_mismatch_count += 1
        if _decimal(row["volume"]) != _raw_decimal(reference, "Volume"):
            volume_mismatch_count += 1

    if reference_volume_lots <= 0:
        raise ValueError("reference control has no positive volume")
    reference_vwap = reference_amount / (reference_volume_lots * Decimal(1000))
    source_average = _decimal(candidate["last_average"])
    tolerance = max(Decimal("0.01"), reference_vwap * Decimal("0.0001"))
    difference = abs(source_average - reference_vwap)
    candidate_volume_lots = _decimal(candidate["total_volume_lots"])
    volume_difference_lots = candidate_volume_lots - reference_volume_lots
    return {
        "candidate_bar_count": candidate["bar_count"],
        "candidate_total_volume_lots": str(candidate_volume_lots),
        "label_alignment": "FUGLE_START_PLUS_ONE_MINUTE_TO_SHIOAJI_END;_13_30_UNSHIFTED",
        "matched_bar_count": matched_bars,
        "ohlc_field_mismatch_count": ohlc_mismatch_count,
        "reference_bar_count": len(reference_rows),
        "reference_total_volume_lots": str(reference_volume_lots),
        "reference_vwap": str(reference_vwap),
        "source_average": str(source_average),
        "volume_difference_lots": str(volume_difference_lots),
        "volume_exact_match": volume_difference_lots == 0,
        "volume_mismatch_bar_count": volume_mismatch_count,
        "vwap_absolute_difference": str(difference),
        "vwap_pass": difference <= tolerance,
        "vwap_tolerance": str(tolerance),
    }


def build_probe_result(
    *,
    protocol: Mapping[str, Any],
    protocol_digest: str,
    fugle_capture_dir: Path,
    reference_capture_dir: Path,
) -> dict[str, Any]:
    fugle_manifest = json.loads((fugle_capture_dir / "capture_manifest.json").read_text())
    reference_manifest = json.loads(
        (reference_capture_dir / "capture_manifest.json").read_text()
    )
    fugle_manifest_digest = sha256_text(canonical_json(fugle_manifest))
    reference_manifest_digest = sha256_text(canonical_json(reference_manifest))
    observations: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for record in fugle_manifest["records"]:
        symbol = str(record["symbol"])
        body_path = fugle_capture_dir / str(record["body_file"])
        raw_body = body_path.read_bytes()
        if hashlib.sha256(raw_body).hexdigest() != record["raw_response_sha256"]:
            raise ValueError(f"Fugle body digest mismatch: {symbol}")
        payload = json.loads(raw_body)
        observation = inspect_candidate_payload(payload, symbol=symbol)
        observation.update(
            {
                "http_status": record["http_status"],
                "market": record["market"],
                "raw_response_sha256": record["raw_response_sha256"],
                "role": record["role"],
                "symbol": symbol,
            }
        )
        observations.append(observation)
        if symbol != "1259":
            reference_path = reference_capture_dir / f"shioaji_{symbol}.capture.json"
            reference = json.loads(reference_path.read_text())
            comparison = reconcile_control(payload, reference, symbol=symbol)
            comparison.update({"market": record["market"], "symbol": symbol})
            controls.append(comparison)

    target = next(item for item in observations if item["symbol"] == "1259")
    all_vwap_pass = all(item["vwap_pass"] for item in controls)
    exact_volume_pass = all(item["volume_exact_match"] for item in controls)
    cross_market_vwap = all(
        any(item["market"] == market and item["vwap_pass"] for item in controls)
        for market in ("TWSE", "TPEX")
    )
    issues = []
    if target["bar_count"] == 0:
        issues.append(
            {
                "code": "FUGLE_1259_HTTP_200_EMPTY_DATA",
                "severity": "BLOCKING",
                "summary": "Fugle did not resolve the fixed 1259 provider-coverage mismatch.",
            }
        )
    if not exact_volume_pass:
        issues.append(
            {
                "code": "CONTROL_VOLUME_NOT_EXACTLY_RECONCILED",
                "severity": "BLOCKING",
                "summary": "At least one fixed control has a non-zero session or minute volume difference.",
            }
        )
    return {
        "artifact_id": "credentialed-intraday-source-probe-result-v1-2026-08-20-r1",
        "capture_references": {
            "fugle": {
                "artifact_id": fugle_manifest["artifact_id"],
                "canonical_sha256": fugle_manifest_digest,
            },
            "shioaji_controls": {
                "artifact_id": reference_manifest["artifact_id"],
                "canonical_sha256": reference_manifest_digest,
            },
        },
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "control_reconciliations": controls,
        "evidence_scope": {
            "holdout_outcomes_read": False,
            "price_values_read_only_from_fixed_probe": True,
            "provider_requests_after_capture": False,
            "strategy_outcomes_read": False,
        },
        "issues": issues,
        "observations": observations,
        "permissions": {
            "alternative_source_acquisition_allowed": False,
            "candidate_source_selected": False,
            "dataset_population_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "outcome_generation_allowed": False,
            "price_dataset_artifact_allowed": False,
            "provider_mismatch_exclusion_allowed": False,
        },
        "protocol_reference": {
            "artifact_id": protocol["artifact_id"],
            "canonical_sha256": protocol_digest,
        },
        "result": {
            "all_control_vwap_within_frozen_tolerance": all_vwap_pass,
            "all_control_volume_exactly_reconciled": exact_volume_pass,
            "cross_market_vwap_requirement_passed": cross_market_vwap,
            "source_qualified": False,
            "source_selected": False,
            "target_1259_nonempty": target["bar_count"] > 0,
            "verdict": "REJECTED_FOR_MISMATCH_RESOLUTION",
        },
        "schema_version": "credentialed_intraday_source_probe_result_v1",
        "status": "BLOCKED",
    }
