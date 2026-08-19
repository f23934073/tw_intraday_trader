"""Replayable G0 evidence for Shioaji equity Kbar daily-source qualification.

This module intentionally does not create a backtest dataset or register a
strategy.  It records the SDK response before the normal Provider mapper
coerces prices to ``float``, then evaluates only the evidence needed to decide
whether a future daily-Kbar ingestion path is eligible to be designed.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_SCHEMA_VERSION = "shioaji_equity_kbar_capture_v1"
QUALIFICATION_SCHEMA_VERSION = "daily_kbar_source_qualification_v1"
REQUIRED_KBAR_FIELDS = ("ts", "Open", "High", "Low", "Close", "Volume")
PRICE_FIELDS = ("Open", "High", "Low", "Close")


class DailySourcePath(StrEnum):
    EXPLICIT_SOURCE_DAILY_V1 = "EXPLICIT_SOURCE_DAILY_V1"
    DERIVED_FINALIZED_SESSION_V1 = "DERIVED_FINALIZED_SESSION_V1"
    BLOCKED = "BLOCKED"


def canonical_json(value: Mapping[str, Any] | list[Any]) -> str:
    """Return the stable JSON form used for artifact evidence digests."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_digest(value: Mapping[str, Any] | list[Any]) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return raw


def _raw_value(value: object) -> dict[str, str]:
    return {
        "python_type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": repr(value),
        "text": str(value),
    }


def _kbar_values(kbars: object, field: str) -> list[object]:
    if isinstance(kbars, Mapping):
        values = kbars.get(field, kbars.get(field.lower(), []))
    else:
        values = getattr(kbars, field, getattr(kbars, field.lower(), []))
    return list(values or [])


def build_capture_artifact(
    *,
    capture_name: str,
    symbol: str,
    query_start: date,
    query_end: date,
    queried_at: datetime,
    sdk_version: str,
    raw_kbars: object,
    extra_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Encode a raw SDK Kbar response without numeric coercion.

    ``python_type``, ``repr`` and ``text`` are all retained because a JSON
    number alone cannot distinguish an SDK ``float`` from a Decimal/integer
    representation after serialisation.
    """
    if queried_at.tzinfo is None or queried_at.utcoffset() is None:
        raise ValueError("queried_at must be timezone-aware")
    if not symbol.strip():
        raise ValueError("symbol must not be empty")
    if query_end < query_start:
        raise ValueError("query_end must not precede query_start")

    captured_fields = tuple(dict.fromkeys((*REQUIRED_KBAR_FIELDS, *extra_fields)))
    if any(not field.strip() for field in captured_fields):
        raise ValueError("captured Kbar field names must not be empty")
    field_values = {
        field: _kbar_values(raw_kbars, field)
        for field in captured_fields
    }
    field_counts = {field: len(values) for field, values in field_values.items()}
    row_count = min(field_counts.values(), default=0)
    rows = [
        {
            field: _raw_value(field_values[field][index])
            for field in captured_fields
        }
        for index in range(row_count)
    ]
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "capture_name": capture_name,
        "provider": "SHIOAJI",
        "symbol": symbol,
        "sdk_version": sdk_version,
        "queried_at": queried_at.astimezone(TAIPEI).isoformat(),
        "request": {
            "api": "Shioaji.kbars",
            "query_start": query_start.isoformat(),
            "query_end": query_end.isoformat(),
            "parameters_observed": ["contract", "start", "end", "timeout"],
            "interval_parameter_observed": False,
        },
        "raw_response_type": (
            f"{type(raw_kbars).__module__}.{type(raw_kbars).__qualname__}"
        ),
        "captured_fields": list(captured_fields),
        "field_counts": field_counts,
        "raw_rows": rows,
        "raw_rows_digest": sha256_digest(rows),
    }


def build_chunk_boundary_artifact(
    *,
    symbol: str,
    sdk_version: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep both independently queried chunks so a boundary can be replayed."""
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "capture_name": "shioaji_chunk_boundary_sample",
        "provider": "SHIOAJI",
        "symbol": symbol,
        "sdk_version": sdk_version,
        "left_chunk": dict(left),
        "right_chunk": dict(right),
    }


def build_session_contract(
    *,
    calendar_version: str,
    source_url: str,
    source_retrieved_at: datetime,
    official_csv_sha256: str,
    explicitly_non_trading_dates: list[date],
) -> dict[str, Any]:
    if source_retrieved_at.tzinfo is None or source_retrieved_at.utcoffset() is None:
        raise ValueError("source_retrieved_at must be timezone-aware")
    return {
        "version": calendar_version,
        "authority": "TWSE",
        "source_url": source_url,
        "source_retrieved_at": source_retrieved_at.astimezone(TAIPEI).isoformat(),
        "official_csv_sha256": official_csv_sha256,
        "timezone": "Asia/Taipei",
        "regular_session": {
            "start": "09:00:00",
            "end": "13:30:00",
            "opening_interruption_latest_start": "09:02:00",
            "closing_interruption_latest_end": "13:33:00",
        },
        "explicitly_non_trading_dates": sorted(
            item.isoformat() for item in explicitly_non_trading_dates
        ),
    }


def _capture_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported capture schema version")
    rows = payload.get("raw_rows")
    if not isinstance(rows, list):
        raise ValueError("capture raw_rows must be a list")
    for row in rows:
        if not isinstance(row, Mapping) or any(field not in row for field in REQUIRED_KBAR_FIELDS):
            raise ValueError("capture contains an invalid raw Kbar row")
    expected_digest = str(payload.get("raw_rows_digest", ""))
    if expected_digest != sha256_digest(rows):
        raise ValueError("capture raw_rows digest does not match")
    return rows


def _decimal_from_raw(raw: Mapping[str, Any]) -> Decimal:
    try:
        value = Decimal(str(raw["text"]))
    except (InvalidOperation, KeyError) as error:
        raise ValueError("raw numeric text is not Decimal-compatible") from error
    if not value.is_finite():
        raise ValueError("raw numeric text must be finite")
    return value


def resolve_shioaji_timestamp(raw: Mapping[str, Any]) -> datetime:
    """Resolve the SDK timestamp using the existing Provider wall-time rule."""
    python_type = str(raw.get("python_type", ""))
    text = str(raw.get("text", ""))
    if python_type == "datetime.datetime":
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=TAIPEI) if parsed.tzinfo is None else parsed.astimezone(TAIPEI)

    numeric = float(_decimal_from_raw(raw))
    if abs(numeric) >= 10_000_000_000_000:
        numeric /= 1_000_000_000
    elif abs(numeric) >= 10_000_000_000:
        numeric /= 1_000
    # The existing Provider explicitly treats numeric Shioaji Kbar timestamps
    # as Taiwan market wall time, not instants to be UTC-converted.
    source_wall_time = datetime.fromtimestamp(numeric, tz=timezone.utc)
    return source_wall_time.replace(tzinfo=TAIPEI)


def _calendar_non_trading_dates(contract: Mapping[str, Any]) -> set[date]:
    values = contract.get("explicitly_non_trading_dates")
    if not isinstance(values, list):
        raise ValueError("session contract explicitly_non_trading_dates must be a list")
    return {date.fromisoformat(str(value)) for value in values}


def _is_expected_session(day: date, contract: Mapping[str, Any]) -> bool:
    return day.weekday() < 5 and day not in _calendar_non_trading_dates(contract)


def _session_times(contract: Mapping[str, Any]) -> tuple[time, time, time, time]:
    regular = contract.get("regular_session")
    if not isinstance(regular, Mapping):
        raise ValueError("session contract regular_session must be an object")
    try:
        return tuple(
            time.fromisoformat(str(regular[name]))
            for name in (
                "start",
                "end",
                "opening_interruption_latest_start",
                "closing_interruption_latest_end",
            )
        )  # type: ignore[return-value]
    except (KeyError, ValueError) as error:
        raise ValueError("session contract contains invalid session times") from error


def _source_float_lossy(rows: list[Mapping[str, Any]]) -> bool:
    return any(
        str(row[field].get("python_type", "")) in {"builtins.float", "numpy.float64"}
        for row in rows
        for field in PRICE_FIELDS
        if isinstance(row[field], Mapping)
    )


def summarize_capture(
    payload: Mapping[str, Any],
    *,
    session_contract: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Evaluate one capture without upgrading coverage evidence to finality."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    rows = _capture_rows(payload)
    field_counts = payload.get("field_counts")
    if not isinstance(field_counts, Mapping):
        raise ValueError("capture field_counts must be an object")
    count_values = {int(field_counts.get(field, -1)) for field in REQUIRED_KBAR_FIELDS}
    issues: list[str] = []
    if len(count_values) != 1:
        issues.append("KBAR_FIELD_CARDINALITY_MISMATCH")

    timestamps: list[datetime] = []
    for row in rows:
        try:
            timestamps.append(resolve_shioaji_timestamp(row["ts"]))
            for field in (*PRICE_FIELDS, "Volume"):
                _decimal_from_raw(row[field])
        except ValueError as error:
            issues.append(f"INVALID_RAW_VALUE:{error}")
            break
    if timestamps != sorted(timestamps):
        issues.append("TIMESTAMP_NOT_MONOTONIC")
    try:
        parsed_queried_at = datetime.fromisoformat(str(payload["queried_at"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("capture queried_at must be an aware ISO-8601 time") from error
    if parsed_queried_at.tzinfo is None or parsed_queried_at.utcoffset() is None:
        raise ValueError("capture queried_at must include a timezone")
    queried_at = parsed_queried_at.astimezone(TAIPEI)
    if timestamps and max(timestamps) > queried_at:
        # A live response whose final bar label is later than the local capture
        # time can be a bar-end label or a source/host-clock disagreement. G0
        # must retain the fact rather than assume a bar-start semantic.
        issues.append("TIMESTAMP_AFTER_CAPTURE_TIME")

    type_counts = {
        field: dict(
            sorted(
                Counter(
                    str(row[field].get("python_type", ""))
                    for row in rows
                    if isinstance(row[field], Mapping)
                ).items()
            )
        )
        for field in REQUIRED_KBAR_FIELDS
    }
    if _source_float_lossy(rows):
        issues.append("SOURCE_FLOAT_LOSSY")

    start, end, latest_open, latest_close = _session_times(session_contract)
    sessions: list[dict[str, Any]] = []
    grouped: dict[date, list[datetime]] = {}
    for timestamp in timestamps:
        grouped.setdefault(timestamp.date(), []).append(timestamp)
    for session_date, values in sorted(grouped.items()):
        values.sort()
        expected = _is_expected_session(session_date, session_contract)
        first = values[0]
        last = values[-1]
        coverage_complete = (
            expected
            and start <= first.timetz().replace(tzinfo=None) <= latest_open
            and latest_close >= last.timetz().replace(tzinfo=None) >= time(13, 29)
        )
        if not expected:
            issues.append(f"BAR_ON_NON_TRADING_DATE:{session_date.isoformat()}")
        if expected and not coverage_complete:
            issues.append(f"INTRADAY_COVERAGE_INCOMPLETE:{session_date.isoformat()}")
        sessions.append(
            {
                "resolved_session_date": session_date.isoformat(),
                "expected_session": expected,
                "first_bar": first.isoformat(),
                "last_bar": last.isoformat(),
                "bar_count": len(values),
                "coverage_complete": coverage_complete,
                # A source query returning bars contains no source-level
                # finalization marker, sequence watermark, or completion flag.
                "source_completion_evidence": "UNAVAILABLE",
                "is_complete": False,
            }
        )

    if sessions:
        issues.append("SOURCE_COMPLETION_UNPROVEN")
    direct_daily_shape = bool(sessions) and all(item["bar_count"] == 1 for item in sessions)
    return {
        "capture_name": payload.get("capture_name"),
        "symbol": payload.get("symbol"),
        "query": payload.get("request"),
        "raw_timestamp_representation": type_counts["ts"],
        "timestamp_semantics": "WALL_TIME_MAPPING_OBSERVED_NOT_PROVIDER_DOCUMENTED",
        "raw_numeric_representation": {field: type_counts[field] for field in (*PRICE_FIELDS, "Volume")},
        "raw_rows_digest": payload.get("raw_rows_digest"),
        "first_raw_timestamp": rows[0]["ts"] if rows else None,
        "last_raw_timestamp": rows[-1]["ts"] if rows else None,
        "first_bar": sessions[0]["first_bar"] if sessions else None,
        "last_bar": sessions[-1]["last_bar"] if sessions else None,
        "resolved_sessions": sessions,
        "direct_daily_shape": direct_daily_shape,
        "coverage_complete": bool(sessions) and all(item["coverage_complete"] for item in sessions),
        "is_complete": False,
        "issues": sorted(set(issues)),
    }


def _boundary_summary(
    payload: Mapping[str, Any],
    *,
    session_contract: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported chunk-boundary capture schema")
    left = payload.get("left_chunk")
    right = payload.get("right_chunk")
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        raise ValueError("chunk-boundary capture requires two captures")
    left_summary = summarize_capture(left, session_contract=session_contract, now=now)
    right_summary = summarize_capture(right, session_contract=session_contract, now=now)
    left_sessions = left_summary["resolved_sessions"]
    right_sessions = right_summary["resolved_sessions"]
    left_dates = {item["resolved_session_date"] for item in left_sessions}
    right_dates = {item["resolved_session_date"] for item in right_sessions}
    issues: list[str] = []
    if left_dates & right_dates:
        issues.append("CHUNK_DUPLICATE_RESOLVED_SESSION")
    if not left_sessions or not right_sessions:
        issues.append("CHUNK_EMPTY")
    return {
        "left": left_summary,
        "right": right_summary,
        "duplicate_resolved_sessions": sorted(left_dates & right_dates),
        "issues": issues,
    }


def qualify_daily_kbar_source(
    *,
    daily_capture: Mapping[str, Any],
    full_session_capture: Mapping[str, Any],
    partial_session_capture: Mapping[str, Any],
    chunk_boundary_capture: Mapping[str, Any],
    session_contract: Mapping[str, Any],
    now: datetime,
    completion_reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Produce G0's four replayable reports and fail closed on finalization."""
    daily = summarize_capture(daily_capture, session_contract=session_contract, now=now)
    full = summarize_capture(full_session_capture, session_contract=session_contract, now=now)
    partial = summarize_capture(partial_session_capture, session_contract=session_contract, now=now)
    boundary = _boundary_summary(
        chunk_boundary_capture,
        session_contract=session_contract,
        now=now,
    )

    source_contract = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "provider": "SHIOAJI",
        "get_kbars_request": daily["query"],
        "daily_capture": {
            "direct_daily_shape": daily["direct_daily_shape"],
            "raw_timestamp_representation": daily["raw_timestamp_representation"],
            "timestamp_semantics": daily["timestamp_semantics"],
            "raw_numeric_representation": daily["raw_numeric_representation"],
            "issues": daily["issues"],
        },
        "direct_daily_source_eligible": (
            daily["direct_daily_shape"] and daily["is_complete"]
        ),
    }
    session_resolution = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "session_contract": dict(session_contract),
        "captures": {
            "daily": daily,
            "full_session": full,
            "partial_session": partial,
            "chunk_boundary": boundary,
        },
    }
    completion_evidence: dict[str, Any] = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "full_session": {
            "coverage_complete": full["coverage_complete"],
            "source_completion_evidence": "UNAVAILABLE",
            "is_complete": full["is_complete"],
            "issues": full["issues"],
        },
        "partial_session": {
            "coverage_complete": partial["coverage_complete"],
            "source_completion_evidence": "UNAVAILABLE",
            "is_complete": partial["is_complete"],
            "issues": partial["issues"],
        },
        "chunk_boundary": {
            "duplicate_resolved_sessions": boundary["duplicate_resolved_sessions"],
            "issues": boundary["issues"],
        },
        "same_completed_session_requery": {
            "raw_rows_digests": {
                "daily_candidate": daily["raw_rows_digest"],
                "full_session": full["raw_rows_digest"],
                "chunk_right": boundary["right"]["raw_rows_digest"],
            },
            "all_identical": len(
                {
                    daily["raw_rows_digest"],
                    full["raw_rows_digest"],
                    boundary["right"]["raw_rows_digest"],
                }
            ) == 1,
            "interpretation": (
                "Repeated historical queries were byte-equivalent after raw encoding; "
                "this is replay evidence, not a provider finalization marker."
            ),
        },
    }

    candidate_path = (
        DailySourcePath.EXPLICIT_SOURCE_DAILY_V1
        if daily["direct_daily_shape"]
        else DailySourcePath.DERIVED_FINALIZED_SESSION_V1
    )
    issues = sorted(
        set(
            [
                *daily["issues"],
                *full["issues"],
                *partial["issues"],
                *boundary["issues"],
            ]
        )
    )
    reconciliation_status = (
        str(completion_reconciliation.get("status", ""))
        if completion_reconciliation is not None
        else ""
    )
    reconciliation_qualified = (
        reconciliation_status == "QUALIFIED_FOR_DERIVED_FINALIZED_SESSION_V1"
    )
    if completion_reconciliation is not None:
        completion_evidence["official_daily_reconciliation"] = dict(
            completion_reconciliation
        )
    selected_path = (
        DailySourcePath.DERIVED_FINALIZED_SESSION_V1
        if reconciliation_qualified and candidate_path is DailySourcePath.DERIVED_FINALIZED_SESSION_V1
        else DailySourcePath.BLOCKED
    )
    qualification_issues = [
        issue
        for issue in issues
        if not (reconciliation_qualified and issue == "SOURCE_COMPLETION_UNPROVEN")
    ]
    evidence_observations: list[str] = []
    if reconciliation_qualified:
        evidence_observations = [
            issue
            for issue in qualification_issues
            if issue.startswith("INTRADAY_COVERAGE_INCOMPLETE:")
            or issue == "TIMESTAMP_AFTER_CAPTURE_TIME"
        ]
        qualification_issues = [
            issue for issue in qualification_issues if issue not in evidence_observations
        ]
    qualification_result = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "selected_path": selected_path.value,
        "candidate_path_if_completion_is_later_proven": candidate_path.value,
        "status": (
            "QUALIFIED_FOR_DERIVED_FINALIZED_SESSION_V1"
            if reconciliation_qualified
            else "BLOCKED"
        ),
        "formal_research_eligible": False,
        "formal_research_blockers": ["RAW_CORPORATE_ACTION_UNADJUSTED"],
        "blockers": (
            []
            if reconciliation_qualified
            else ["SOURCE_COMPLETION_UNPROVEN"]
        ),
        "p1_issues": sorted(
            issue for issue in qualification_issues if issue == "SOURCE_FLOAT_LOSSY"
        ),
        "qualification_issues": qualification_issues,
        "evidence_observations": evidence_observations,
        "next_required_evidence": [
            *(
                []
                if reconciliation_qualified
                else [
                    "A provider-level finalization/completion marker or independently replayable end-of-session proof"
                ]
            ),
            "A reviewed canonical adapter if source floats must support formal numeric evidence",
        ],
    }
    return {
        "source_contract": source_contract,
        "session_resolution": session_resolution,
        "completion_evidence": completion_evidence,
        "qualification_result": qualification_result,
    }
