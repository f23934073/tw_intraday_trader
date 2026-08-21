"""Offline reconciliation for the sealed FinMind KBar plus Tick probe."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from institutional_data.serialization import canonical_json, sha256_text
from market_data.daily_kbar_qualification import resolve_shioaji_timestamp


REGULAR_START = time(9, 0)
REGULAR_END = time(13, 30)
PRICE_FIELDS = ("open", "high", "low", "close")
TAIPEI = timezone(timedelta(hours=8))


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


def _local_datetime(row: Mapping[str, Any], time_field: str) -> datetime:
    return datetime.fromisoformat(
        f"{row['date']}T{row[time_field]}"
    ).replace(tzinfo=TAIPEI)


def _reference_label(kbar_timestamp: datetime) -> datetime:
    if kbar_timestamp.timetz().replace(tzinfo=None) == REGULAR_END:
        return kbar_timestamp
    return kbar_timestamp + timedelta(minutes=1)


def _load_payload(capture_dir: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    body = (capture_dir / str(record["body_file"])).read_bytes()
    if hashlib.sha256(body).hexdigest() != record["raw_response_sha256"]:
        raise ValueError("FinMind response digest mismatch")
    payload = json.loads(body)
    if (
        record["http_status"] != 200
        or payload.get("status") != 200
        or not isinstance(payload.get("data"), list)
    ):
        raise ValueError("FinMind response is not an entitled data envelope")
    return payload


def inspect_symbol(
    *, symbol: str, kbar_payload: Mapping[str, Any], tick_payload: Mapping[str, Any]
) -> dict[str, Any]:
    kbars = kbar_payload.get("data")
    ticks = tick_payload.get("data")
    if not isinstance(kbars, list) or not isinstance(ticks, list):
        raise ValueError("FinMind data must be arrays")

    kbar_timestamps = [_local_datetime(row, "minute") for row in kbars]
    tick_timestamps = [_local_datetime(row, "Time") for row in ticks]
    regular_ticks = [
        row
        for row, timestamp in zip(ticks, tick_timestamps, strict=True)
        if REGULAR_START <= timestamp.timetz().replace(tzinfo=None) <= REGULAR_END
    ]
    return {
        "kbar_count": len(kbars),
        "kbar_first_timestamp": (
            kbar_timestamps[0].isoformat() if kbar_timestamps else None
        ),
        "kbar_last_timestamp": (
            kbar_timestamps[-1].isoformat() if kbar_timestamps else None
        ),
        "kbar_timestamp_monotonic": kbar_timestamps == sorted(kbar_timestamps),
        "post_regular_session_tick_count": len(ticks) - len(regular_ticks),
        "regular_session_tick_count": len(regular_ticks),
        "symbol": symbol,
        "tick_count": len(ticks),
        "tick_timestamp_monotonic": tick_timestamps == sorted(tick_timestamps),
    }


def reconcile_control(
    *,
    symbol: str,
    market: str,
    kbar_payload: Mapping[str, Any],
    tick_payload: Mapping[str, Any],
    reference_capture: Mapping[str, Any],
) -> dict[str, Any]:
    kbars = kbar_payload.get("data")
    ticks = tick_payload.get("data")
    reference_rows = reference_capture.get("raw_rows")
    if not isinstance(kbars, list) or not isinstance(ticks, list):
        raise ValueError("FinMind control data must be arrays")
    if not isinstance(reference_rows, list):
        raise ValueError("Shioaji control rows must be an array")
    if not kbars or not ticks:
        return {
            "available": False,
            "candidate_kbar_count": len(kbars),
            "candidate_tick_count": len(ticks),
            "market": market,
            "reference_bar_count": len(reference_rows),
            "semantic_pass": False,
            "symbol": symbol,
        }

    regular_ticks = [
        row
        for row in ticks
        if REGULAR_START
        <= _local_datetime(row, "Time").timetz().replace(tzinfo=None)
        <= REGULAR_END
    ]
    grouped_ticks: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in regular_ticks:
        grouped_ticks[str(row["Time"])[:5]].append(row)

    tick_kbar_mismatch_count = 0
    for kbar in kbars:
        minute_ticks = grouped_ticks.get(str(kbar["minute"])[:5], [])
        if not minute_ticks:
            tick_kbar_mismatch_count += 1
            continue
        prices = [_decimal(row["deal_price"]) for row in minute_ticks]
        reconstructed = {
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum((_decimal(row["volume"]) for row in minute_ticks), Decimal(0)),
        }
        if any(_decimal(kbar[field]) != reconstructed[field] for field in PRICE_FIELDS):
            tick_kbar_mismatch_count += 1
        elif _decimal(kbar["volume"]) != reconstructed["volume"]:
            tick_kbar_mismatch_count += 1

    reference_by_timestamp: dict[datetime, Mapping[str, Any]] = {}
    reference_amount = Decimal(0)
    reference_volume_lots = Decimal(0)
    for row in reference_rows:
        timestamp = resolve_shioaji_timestamp(row["ts"])
        reference_by_timestamp[timestamp] = row
        reference_amount += _raw_decimal(row, "Amount")
        reference_volume_lots += _raw_decimal(row, "Volume")

    matched_reference_bars = 0
    reference_ohlcv_mismatch_count = 0
    for kbar in kbars:
        reference = reference_by_timestamp.get(
            _reference_label(_local_datetime(kbar, "minute"))
        )
        if reference is None:
            continue
        matched_reference_bars += 1
        for field in PRICE_FIELDS:
            if _decimal(kbar[field]) != _raw_decimal(reference, field.title()):
                reference_ohlcv_mismatch_count += 1
        if _decimal(kbar["volume"]) != _raw_decimal(reference, "Volume"):
            reference_ohlcv_mismatch_count += 1

    kbar_volume = sum((_decimal(row["volume"]) for row in kbars), Decimal(0))
    tick_volume = sum(
        (_decimal(row["volume"]) for row in regular_ticks), Decimal(0)
    )
    if kbar_volume == reference_volume_lots:
        volume_hypothesis = "RAW_VOLUME_IS_COMMON_LOTS_MULTIPLY_BY_1000"
    elif kbar_volume == reference_volume_lots * Decimal(1000):
        volume_hypothesis = "RAW_VOLUME_IS_SHARES"
    else:
        volume_hypothesis = "UNRESOLVED"

    tick_vwap = sum(
        (
            _decimal(row["deal_price"]) * _decimal(row["volume"])
            for row in regular_ticks
        ),
        Decimal(0),
    ) / tick_volume
    reference_vwap = reference_amount / (reference_volume_lots * Decimal(1000))
    tolerance = max(Decimal("0.01"), reference_vwap * Decimal("0.0001"))
    vwap_difference = abs(tick_vwap - reference_vwap)
    semantic_pass = all(
        (
            len(grouped_ticks) == len(kbars),
            tick_kbar_mismatch_count == 0,
            matched_reference_bars == len(reference_rows) == len(kbars),
            reference_ohlcv_mismatch_count == 0,
            kbar_volume == tick_volume == reference_volume_lots,
            volume_hypothesis == "RAW_VOLUME_IS_COMMON_LOTS_MULTIPLY_BY_1000",
            vwap_difference <= tolerance,
        )
    )
    return {
        "available": True,
        "candidate_kbar_count": len(kbars),
        "candidate_kbar_total_volume_raw": str(kbar_volume),
        "candidate_regular_tick_count": len(regular_ticks),
        "candidate_tick_total_volume_raw": str(tick_volume),
        "kbar_label_alignment": (
            "FINMIND_START_PLUS_ONE_MINUTE_TO_SHIOAJI_END;_13_30_UNSHIFTED"
        ),
        "market": market,
        "matched_reference_bar_count": matched_reference_bars,
        "post_regular_session_tick_count": len(ticks) - len(regular_ticks),
        "reference_bar_count": len(reference_rows),
        "reference_ohlcv_mismatch_count": reference_ohlcv_mismatch_count,
        "reference_total_volume_lots": str(reference_volume_lots),
        "reference_vwap": str(reference_vwap),
        "semantic_pass": semantic_pass,
        "symbol": symbol,
        "tick_kbar_mismatch_count": tick_kbar_mismatch_count,
        "tick_vwap": str(tick_vwap),
        "vwap_absolute_difference": str(vwap_difference),
        "vwap_pass": vwap_difference <= tolerance,
        "vwap_tolerance": str(tolerance),
        "volume_hypothesis": volume_hypothesis,
    }


def build_finmind_probe_result(
    *,
    protocol: Mapping[str, Any],
    protocol_digest: str,
    finmind_capture_dir: Path,
    reference_capture_dir: Path,
) -> dict[str, Any]:
    finmind_manifest = json.loads(
        (finmind_capture_dir / "capture_manifest.json").read_text()
    )
    reference_manifest = json.loads(
        (reference_capture_dir / "capture_manifest.json").read_text()
    )
    records = {
        (str(record["symbol"]), str(record["dataset"])): record
        for record in finmind_manifest["records"]
    }
    observations: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    markets = {str(item["data_id"]): str(item["market"]) for item in protocol["fixed_requests"]}
    roles = {str(item["data_id"]): str(item["role"]) for item in protocol["fixed_requests"]}
    for symbol in ("1259", "1240", "12561", "2330", "2317"):
        kbar_payload = _load_payload(
            finmind_capture_dir, records[(symbol, "TaiwanStockKBar")]
        )
        tick_payload = _load_payload(
            finmind_capture_dir, records[(symbol, "TaiwanStockPriceTick")]
        )
        observation = inspect_symbol(
            symbol=symbol, kbar_payload=kbar_payload, tick_payload=tick_payload
        )
        observation.update({"market": markets[symbol], "role": roles[symbol]})
        observations.append(observation)
        if symbol != "1259":
            reference = json.loads(
                (reference_capture_dir / f"shioaji_{symbol}.capture.json").read_text()
            )
            controls.append(
                reconcile_control(
                    symbol=symbol,
                    market=markets[symbol],
                    kbar_payload=kbar_payload,
                    tick_payload=tick_payload,
                    reference_capture=reference,
                )
            )

    target = next(item for item in observations if item["symbol"] == "1259")
    available_controls = [item for item in controls if item["available"]]
    unavailable_controls = [item for item in controls if not item["available"]]
    available_semantics_pass = bool(available_controls) and all(
        item["semantic_pass"] for item in available_controls
    )
    cross_market_semantics_pass = all(
        any(item["market"] == market and item["semantic_pass"] for item in available_controls)
        for market in ("TWSE", "TPEX")
    )
    issues = []
    if target["kbar_count"] == 0 or target["tick_count"] == 0:
        issues.append(
            {
                "code": "FINMIND_1259_HTTP_200_EMPTY_DATA",
                "severity": "BLOCKING",
                "summary": "FinMind did not resolve the fixed 1259 provider-coverage mismatch.",
            }
        )
    for control in unavailable_controls:
        issues.append(
            {
                "code": "FINMIND_FIXED_CONTROL_EMPTY_DATA",
                "severity": "BLOCKING",
                "summary": (
                    f"FinMind returned no KBar or Tick rows for fixed control {control['symbol']}."
                ),
                "symbol": control["symbol"],
            }
        )

    return {
        "artifact_id": (
            "credentialed-finmind-intraday-source-probe-result-v1-2026-08-21-r2"
        ),
        "capture_references": {
            "finmind": {
                "artifact_id": finmind_manifest["artifact_id"],
                "canonical_sha256": sha256_text(canonical_json(finmind_manifest)),
            },
            "shioaji_controls": {
                "artifact_id": reference_manifest["artifact_id"],
                "canonical_sha256": sha256_text(canonical_json(reference_manifest)),
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
            "source_mixing_allowed": False,
        },
        "protocol_reference": {
            "artifact_id": protocol["artifact_id"],
            "canonical_sha256": protocol_digest,
        },
        "result": {
            "all_available_control_semantics_passed": available_semantics_pass,
            "all_fixed_controls_available": not unavailable_controls,
            "cross_market_semantics_passed": cross_market_semantics_pass,
            "dataset_entitlement_verified": True,
            "source_qualified": False,
            "source_selected": False,
            "target_1259_nonempty": False,
            "verdict": "REJECTED_FOR_MISMATCH_RESOLUTION",
        },
        "schema_version": "credentialed_finmind_intraday_source_probe_result_v1",
        "status": "BLOCKED",
    }
