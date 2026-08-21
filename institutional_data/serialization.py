"""Canonical JSON boundaries for institutional data-contract artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from institutional_data.domain import (
    CorrectionPolicy,
    InstitutionalFlowDaily,
    InstitutionalMarket,
    InstitutionalPartitionManifest,
    PartitionStatus,
)


FLOW_ROWS_SCHEMA_VERSION = "institutional_flow_rows_v1"
PARTITION_MANIFEST_SCHEMA_VERSION = "institutional_partition_manifest_v1"
PARTITION_MANIFEST_V1_FIELDS = (
    "partition_id",
    "market",
    "session_date",
    "source_product",
    "trade_scope_id",
    "correction_policy",
    "response_scope_note",
    "raw_artifact_id",
    "raw_sha256",
    "normalized_sha256",
    "retrieved_at",
    "first_observed_at",
    "usable_from_session",
    "source_row_count",
    "normalized_row_count",
    "status",
)


class InstitutionalSerializationError(ValueError):
    """An artifact cannot be treated as a supported institutional contract."""


_FLOW_FIELDS = frozenset(
    {
        "partition_id",
        "market",
        "symbol",
        "session_date",
        "foreign_ex_dealer_buy_shares",
        "foreign_ex_dealer_sell_shares",
        "foreign_ex_dealer_net_shares",
        "foreign_dealer_buy_shares",
        "foreign_dealer_sell_shares",
        "foreign_dealer_net_shares",
        "investment_trust_buy_shares",
        "investment_trust_sell_shares",
        "investment_trust_net_shares",
        "dealer_proprietary_buy_shares",
        "dealer_proprietary_sell_shares",
        "dealer_proprietary_net_shares",
        "dealer_hedge_buy_shares",
        "dealer_hedge_sell_shares",
        "dealer_hedge_net_shares",
        "dealer_total_buy_shares",
        "dealer_total_sell_shares",
        "dealer_total_net_shares",
        "published_total_net_shares",
        "trade_scope_id",
        "correction_policy",
        "raw_artifact_id",
        "raw_sha256",
        "retrieved_at",
        "first_observed_at",
        "usable_from_session",
    }
)

_MANIFEST_FIELDS = frozenset(PARTITION_MANIFEST_V1_FIELDS)


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InstitutionalSerializationError("Decimal values must be finite")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise InstitutionalSerializationError(
                "datetime values must include a timezone"
            )
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        raise InstitutionalSerializationError("float values are not canonical")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise InstitutionalSerializationError("JSON object keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise InstitutionalSerializationError(
        f"unsupported canonical JSON value: {type(value).__name__}"
    )


def canonical_json(value: object) -> str:
    return json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _flow_to_dict(row: InstitutionalFlowDaily) -> dict[str, object]:
    return {field_name: getattr(row, field_name) for field_name in sorted(_FLOW_FIELDS)}


def serialize_flow_rows(rows: tuple[InstitutionalFlowDaily, ...]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: (
            row.market.value,
            row.session_date,
            row.symbol,
            row.partition_id,
        ),
    )
    return canonical_json(
        {
            "schema_version": FLOW_ROWS_SCHEMA_VERSION,
            "rows": [_flow_to_dict(row) for row in ordered],
        }
    )


def flow_rows_sha256(rows: tuple[InstitutionalFlowDaily, ...]) -> str:
    return sha256_text(serialize_flow_rows(rows))


def deserialize_flow_rows(payload_json: str) -> tuple[InstitutionalFlowDaily, ...]:
    payload = _json_object(payload_json)
    _require_exact_fields(payload, {"schema_version", "rows"}, "flow artifact")
    if payload["schema_version"] != FLOW_ROWS_SCHEMA_VERSION:
        raise InstitutionalSerializationError("unsupported flow schema_version")
    rows = payload["rows"]
    if not isinstance(rows, list):
        raise InstitutionalSerializationError("flow artifact rows must be a list")
    return tuple(_flow_from_object(value) for value in rows)


def _flow_from_object(value: object) -> InstitutionalFlowDaily:
    if not isinstance(value, Mapping):
        raise InstitutionalSerializationError("flow row must be an object")
    _require_exact_fields(value, _FLOW_FIELDS, "flow row")
    try:
        return InstitutionalFlowDaily(
            partition_id=_string(value, "partition_id"),
            market=InstitutionalMarket(_string(value, "market")),
            symbol=_string(value, "symbol"),
            session_date=_date(value, "session_date"),
            foreign_ex_dealer_buy_shares=_int(value, "foreign_ex_dealer_buy_shares"),
            foreign_ex_dealer_sell_shares=_int(value, "foreign_ex_dealer_sell_shares"),
            foreign_ex_dealer_net_shares=_int(value, "foreign_ex_dealer_net_shares"),
            foreign_dealer_buy_shares=_optional_int(value, "foreign_dealer_buy_shares"),
            foreign_dealer_sell_shares=_optional_int(
                value, "foreign_dealer_sell_shares"
            ),
            foreign_dealer_net_shares=_optional_int(value, "foreign_dealer_net_shares"),
            investment_trust_buy_shares=_int(value, "investment_trust_buy_shares"),
            investment_trust_sell_shares=_int(value, "investment_trust_sell_shares"),
            investment_trust_net_shares=_int(value, "investment_trust_net_shares"),
            dealer_proprietary_buy_shares=_optional_int(
                value, "dealer_proprietary_buy_shares"
            ),
            dealer_proprietary_sell_shares=_optional_int(
                value, "dealer_proprietary_sell_shares"
            ),
            dealer_proprietary_net_shares=_optional_int(
                value, "dealer_proprietary_net_shares"
            ),
            dealer_hedge_buy_shares=_optional_int(value, "dealer_hedge_buy_shares"),
            dealer_hedge_sell_shares=_optional_int(value, "dealer_hedge_sell_shares"),
            dealer_hedge_net_shares=_optional_int(value, "dealer_hedge_net_shares"),
            dealer_total_buy_shares=_int(value, "dealer_total_buy_shares"),
            dealer_total_sell_shares=_int(value, "dealer_total_sell_shares"),
            dealer_total_net_shares=_int(value, "dealer_total_net_shares"),
            published_total_net_shares=_int(value, "published_total_net_shares"),
            trade_scope_id=_string(value, "trade_scope_id"),
            correction_policy=CorrectionPolicy(_string(value, "correction_policy")),
            raw_artifact_id=_string(value, "raw_artifact_id"),
            raw_sha256=_string(value, "raw_sha256"),
            retrieved_at=_datetime(value, "retrieved_at"),
            first_observed_at=_datetime(value, "first_observed_at"),
            usable_from_session=_date(value, "usable_from_session"),
        )
    except (ValueError, TypeError) as error:
        if isinstance(error, InstitutionalSerializationError):
            raise
        raise InstitutionalSerializationError(f"invalid flow row: {error}") from error


def _manifest_to_dict(
    manifest: InstitutionalPartitionManifest,
) -> dict[str, object]:
    body = {
        field_name: getattr(manifest, field_name)
        for field_name in sorted(_MANIFEST_FIELDS)
    }
    body["schema_version"] = PARTITION_MANIFEST_SCHEMA_VERSION
    return body


def serialize_partition_manifest(manifest: InstitutionalPartitionManifest) -> str:
    return canonical_json(_manifest_to_dict(manifest))


def deserialize_partition_manifest(
    payload_json: str,
) -> InstitutionalPartitionManifest:
    payload = _json_object(payload_json)
    _require_exact_fields(
        payload,
        _MANIFEST_FIELDS | {"schema_version"},
        "partition manifest",
    )
    if payload["schema_version"] != PARTITION_MANIFEST_SCHEMA_VERSION:
        raise InstitutionalSerializationError("unsupported manifest schema_version")
    try:
        return InstitutionalPartitionManifest(
            partition_id=_string(payload, "partition_id"),
            market=InstitutionalMarket(_string(payload, "market")),
            session_date=_date(payload, "session_date"),
            source_product=_string(payload, "source_product"),
            trade_scope_id=_string(payload, "trade_scope_id"),
            correction_policy=CorrectionPolicy(_string(payload, "correction_policy")),
            response_scope_note=_string(payload, "response_scope_note"),
            raw_artifact_id=_string(payload, "raw_artifact_id"),
            raw_sha256=_string(payload, "raw_sha256"),
            normalized_sha256=_string(payload, "normalized_sha256"),
            retrieved_at=_datetime(payload, "retrieved_at"),
            first_observed_at=_datetime(payload, "first_observed_at"),
            usable_from_session=_date(payload, "usable_from_session"),
            source_row_count=_int(payload, "source_row_count"),
            normalized_row_count=_int(payload, "normalized_row_count"),
            status=PartitionStatus(_string(payload, "status")),
        )
    except (ValueError, TypeError) as error:
        if isinstance(error, InstitutionalSerializationError):
            raise
        raise InstitutionalSerializationError(
            f"invalid partition manifest: {error}"
        ) from error


def _json_object(payload_json: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise InstitutionalSerializationError("artifact is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise InstitutionalSerializationError("artifact must contain one object")
    return payload


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str] | set[str],
    label: str,
) -> None:
    actual = set(payload)
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - set(expected))
    if missing:
        raise InstitutionalSerializationError(
            f"{label} missing fields: {', '.join(missing)}"
        )
    if unexpected:
        raise InstitutionalSerializationError(
            f"{label} has unexpected fields: {', '.join(unexpected)}"
        )


def _string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise InstitutionalSerializationError(f"{field_name} must be a string")
    return value


def _int(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InstitutionalSerializationError(f"{field_name} must be an integer")
    return value


def _optional_int(payload: Mapping[str, Any], field_name: str) -> int | None:
    return None if payload[field_name] is None else _int(payload, field_name)


def _date(payload: Mapping[str, Any], field_name: str) -> date:
    value = _string(payload, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise InstitutionalSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error


def _datetime(payload: Mapping[str, Any], field_name: str) -> datetime:
    value = _string(payload, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise InstitutionalSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InstitutionalSerializationError(f"{field_name} must include a timezone")
    return parsed
