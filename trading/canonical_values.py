"""Dependency-free canonical scalar encodings shared by Journal contracts."""

from __future__ import annotations

from decimal import Decimal


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
