"""Independent TWSE daily-report reconciliation for G0 Kbar completion proof.

The Shioaji Kbar response has no finalization marker.  This module compares a
completed regular-session Kbar capture with the official TWSE daily report and
records the volume unit/scope separately from OHLC equality.  It does not
create a backtest dataset or change any strategy.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Mapping

from market_data.daily_kbar_qualification import (
    CAPTURE_SCHEMA_VERSION,
    PRICE_FIELDS,
    _capture_rows,
    _decimal_from_raw,
    canonical_json,
    resolve_shioaji_timestamp,
)


TWSE_STOCK_DAY_CAPTURE_SCHEMA_VERSION = "twse_stock_day_capture_v1"
RECONCILIATION_SCHEMA_VERSION = "daily_kbar_completion_reconciliation_v1"
TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TWSE_STOCK_DAY_FIELDS = (
    "日期",
    "成交股數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "成交筆數",
    "註記",
)


def build_twse_stock_day_capture(
    *,
    symbol: str,
    requested_month: date,
    retrieved_at: datetime,
    raw_response: bytes,
) -> dict[str, Any]:
    """Store raw official response text plus an integrity-verifiable parse."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    if requested_month.day != 1:
        raise ValueError("requested_month must be the first day of a month")
    try:
        response_text = raw_response.decode("utf-8")
        payload = json.loads(response_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TWSE daily response must be UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("TWSE daily response must contain one JSON object")
    return {
        "schema_version": TWSE_STOCK_DAY_CAPTURE_SCHEMA_VERSION,
        "source": "TWSE_STOCK_DAY",
        "source_url": TWSE_STOCK_DAY_URL,
        "symbol": symbol,
        "requested_month": requested_month.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "raw_response_encoding": "utf-8",
        "raw_response_text": response_text,
        "raw_response_sha256": sha256(raw_response).hexdigest(),
        "parsed_payload": payload,
    }


def _validate_twse_capture(capture: Mapping[str, Any]) -> Mapping[str, Any]:
    if capture.get("schema_version") != TWSE_STOCK_DAY_CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported TWSE daily capture schema")
    raw_text = capture.get("raw_response_text")
    if not isinstance(raw_text, str):
        raise ValueError("TWSE capture raw_response_text must be a string")
    if sha256(raw_text.encode("utf-8")).hexdigest() != capture.get("raw_response_sha256"):
        raise ValueError("TWSE capture response digest does not match")
    payload = capture.get("parsed_payload")
    if not isinstance(payload, Mapping):
        raise ValueError("TWSE capture parsed_payload must be an object")
    if payload.get("stat") != "OK":
        raise ValueError("TWSE daily response did not report OK")
    fields = payload.get("fields")
    if not isinstance(fields, list) or tuple(fields) != TWSE_STOCK_DAY_FIELDS:
        raise ValueError("TWSE daily response fields do not match the reviewed contract")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("TWSE daily response data must be a list")
    return payload


def _twse_date(value: object) -> date:
    try:
        year_text, month_text, day_text = str(value).strip().split("/")
        return date(int(year_text) + 1911, int(month_text), int(day_text))
    except (TypeError, ValueError) as error:
        raise ValueError("TWSE daily report date must be Minguo Y/MM/DD") from error


def _official_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("TWSE daily numeric value is invalid") from error
    if not parsed.is_finite():
        raise ValueError("TWSE daily numeric value must be finite")
    return parsed


def extract_twse_daily_bar(
    capture: Mapping[str, Any],
    *,
    session_date: date,
) -> dict[str, Any]:
    payload = _validate_twse_capture(capture)
    rows = payload["data"]
    assert isinstance(rows, list)
    matches = [
        row
        for row in rows
        if isinstance(row, list) and row and _twse_date(row[0]) == session_date
    ]
    if len(matches) != 1 or len(matches[0]) != len(TWSE_STOCK_DAY_FIELDS):
        raise ValueError("TWSE daily report has no unique row for the session date")
    row = matches[0]
    return {
        "session_date": session_date.isoformat(),
        "volume_shares": int(_official_decimal(row[1])),
        "amount": str(_official_decimal(row[2])),
        "open": str(_official_decimal(row[3])),
        "high": str(_official_decimal(row[4])),
        "low": str(_official_decimal(row[5])),
        "close": str(_official_decimal(row[6])),
        "transaction_count": int(_official_decimal(row[8])),
        "note": str(row[9]),
        "report_notes": list(payload.get("notes", [])),
        "raw_row": row,
    }


def aggregate_shioaji_regular_session(
    capture: Mapping[str, Any],
    *,
    session_date: date,
) -> dict[str, Any]:
    """Aggregate a raw Kbar capture, retaining the source's raw volume unit."""
    rows = _capture_rows(capture)
    selected = [
        row
        for row in rows
        if resolve_shioaji_timestamp(row["ts"]).date() == session_date
    ]
    if not selected:
        raise ValueError("Shioaji capture has no rows for the session date")
    if any("Amount" not in row for row in selected):
        raise ValueError("Shioaji reconciliation requires raw Amount values")
    timestamps = [resolve_shioaji_timestamp(row["ts"]) for row in selected]
    if timestamps != sorted(timestamps):
        raise ValueError("Shioaji timestamps must be monotonic")
    prices = {
        "open": _decimal_from_raw(selected[0]["Open"]),
        "high": max(_decimal_from_raw(row["High"]) for row in selected),
        "low": min(_decimal_from_raw(row["Low"]) for row in selected),
        "close": _decimal_from_raw(selected[-1]["Close"]),
    }
    volumes = [_decimal_from_raw(row["Volume"]) for row in selected]
    if any(value != value.to_integral_value() or value < 0 for value in volumes):
        raise ValueError("Shioaji Kbar Volume must be a non-negative integer")
    amounts = [_decimal_from_raw(row["Amount"]) for row in selected]
    if any(value < 0 for value in amounts):
        raise ValueError("Shioaji Kbar Amount must be non-negative")

    # Actual source-level proof of the common-lot multiplier: for every nonzero
    # bar, Amount / (Volume * 1000) must be a trade price within that bar's OHLC
    # range. This is stronger than inferring the unit from the daily total.
    consistent_lot_rows = 0
    eligible_lot_rows = 0
    for row, volume, amount in zip(selected, volumes, amounts):
        if volume == 0:
            continue
        eligible_lot_rows += 1
        implied_price = amount / (volume * Decimal("1000"))
        low = _decimal_from_raw(row["Low"])
        high = _decimal_from_raw(row["High"])
        if low <= implied_price <= high:
            consistent_lot_rows += 1
    common_lot_proven = eligible_lot_rows > 0 and consistent_lot_rows == eligible_lot_rows
    raw_volume_lots = int(sum(volumes))
    return {
        "session_date": session_date.isoformat(),
        "first_bar": timestamps[0].isoformat(),
        "last_bar": timestamps[-1].isoformat(),
        "bar_count": len(selected),
        **{name: str(value) for name, value in prices.items()},
        "amount": str(sum(amounts)),
        "volume": {
            "raw_value": raw_volume_lots,
            "unit": "COMMON_LOT" if common_lot_proven else "UNRESOLVED",
            "shares_per_lot": 1000 if common_lot_proven else None,
            "equivalent_shares": raw_volume_lots * 1000 if common_lot_proven else None,
            "amount_lot_consistent_rows": consistent_lot_rows,
            "amount_lot_eligible_rows": eligible_lot_rows,
        },
    }


def reconcile_completed_session(
    *,
    shioaji_capture: Mapping[str, Any],
    twse_capture: Mapping[str, Any],
    session_date: date,
) -> dict[str, Any]:
    """Return a deterministic G0 completion decision for one stock session."""
    if shioaji_capture.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported Shioaji capture schema")
    shioaji = aggregate_shioaji_regular_session(
        shioaji_capture,
        session_date=session_date,
    )
    official = extract_twse_daily_bar(twse_capture, session_date=session_date)
    price_matches = {
        source_name: Decimal(shioaji[source_name.lower()])
        == Decimal(official[source_name.lower()])
        for source_name in PRICE_FIELDS
    }
    # The official report itself says its daily statistical information includes
    # additional sessions. That differs from Shioaji's observed 09:01–13:30
    # Kbar window and is recorded as a scope difference, not a failed price
    # reconciliation.
    volume = shioaji["volume"]
    assert isinstance(volume, Mapping)
    raw_equivalent = volume.get("equivalent_shares")
    volume_matches_official = raw_equivalent == official["volume_shares"]
    amount_matches_official = Decimal(shioaji["amount"]) == Decimal(official["amount"])
    session_ohlc_proven = all(price_matches.values())
    volume_unit_proven = volume.get("unit") == "COMMON_LOT"
    issues: list[str] = []
    if not session_ohlc_proven:
        issues.append("TWSE_OFFICIAL_OHLC_MISMATCH")
    if not volume_unit_proven:
        issues.append("SHIOAJI_KBAR_VOLUME_UNIT_UNPROVEN")
    if not volume_matches_official:
        issues.append("TWSE_DAILY_VOLUME_SCOPE_DIFFERENT")
    if not amount_matches_official:
        issues.append("TWSE_DAILY_AMOUNT_SCOPE_DIFFERENT")
    qualified = session_ohlc_proven and volume_unit_proven
    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "status": (
            "QUALIFIED_FOR_DERIVED_FINALIZED_SESSION_V1"
            if qualified
            else "INCOMPLETE"
        ),
        "session_date": session_date.isoformat(),
        "completion_evidence": (
            "TWSE_OFFICIAL_DAILY_OHLC_RECONCILIATION_V1"
            if qualified
            else "UNQUALIFIED"
        ),
        "shioaji_regular_session": shioaji,
        "twse_official_daily": official,
        "comparison": {
            "ohlc_matches": price_matches,
            "official_volume_matches_shioaji_equivalent_shares": volume_matches_official,
            "official_amount_matches_shioaji_regular_session_amount": amount_matches_official,
            "volume_scope_contract": (
                "SHIOAJI_REGULAR_SESSION_COMMON_LOTS_V1"
                if volume_unit_proven
                else "UNRESOLVED"
            ),
            "official_daily_scope": "TWSE_STOCK_DAY_REPORTED_DAILY_TOTAL_V1",
        },
        "issues": issues,
        "input_digests": {
            "shioaji_raw_rows": shioaji_capture.get("raw_rows_digest"),
            "twse_raw_response": twse_capture.get("raw_response_sha256"),
            "reconciliation": sha256(
                canonical_json(
                    {
                        "shioaji": shioaji,
                        "twse": official,
                        "ohlc_matches": price_matches,
                    }
                ).encode("utf-8")
            ).hexdigest(),
        },
    }
