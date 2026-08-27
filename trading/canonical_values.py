"""Dependency-free canonical scalar encodings shared by Journal contracts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation


def canonical_decimal_string(value: Decimal) -> str:
    """Encode a finite Decimal once, without exponent or insignificant zeros."""

    if not value.is_finite():
        raise ValueError("canonical Decimal must be finite")
    encoded = format(value, "f")
    if "." in encoded:
        encoded = encoded.rstrip("0").rstrip(".")
    if encoded == "-0":
        return "0"
    return encoded


def require_json_fields(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    allowed: frozenset[str] | None = None,
    field_name: str,
) -> None:
    """Reject missing and unknown keys at a versioned JSON boundary."""

    actual = frozenset(value)
    permitted = required if allowed is None else allowed
    missing = sorted(required - actual)
    unknown = sorted(actual - permitted)
    if missing or unknown:
        raise ValueError(
            f"{field_name} fields mismatch: missing={missing}, unknown={unknown}"
        )


def require_json_string(
    value: object,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Return an exact JSON string without coercing another scalar type."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def require_optional_json_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return require_json_string(value, field_name)


def require_json_integer(value: object, field_name: str) -> int:
    """Return an exact JSON integer, explicitly excluding booleans."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def require_canonical_decimal_string(
    value: object,
    field_name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    """Parse one finite canonical Decimal string without scalar coercion."""

    raw = require_json_string(value, field_name)
    try:
        parsed = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError(f"{field_name} must be a decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal string")
    if canonical_decimal_string(parsed) != raw:
        raise ValueError(f"{field_name} must use canonical decimal notation")
    if positive and parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    if non_negative and parsed < 0:
        raise ValueError(f"{field_name} must not be negative")
    return parsed


def require_aware_datetime_string(value: object, field_name: str) -> datetime:
    raw = require_json_string(value, field_name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO datetime string") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed
