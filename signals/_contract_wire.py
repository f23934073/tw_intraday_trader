"""Shared canonical-wire contract for the pure Momentum signal modules.

This private helper is the single owner of the ``Undecided`` sentinel, the
canonical recursive :func:`to_wire` serializer, and the :func:`digest` wrapper
over the unchanged :func:`strategy_catalog.parameter_schema.canonical_digest`.
The four public contract modules import the same class and instance from here so
their sentinels compose across module boundaries and their wire output stays
byte-identical. This module also holds the sole ``signals -> strategy_catalog``
dependency edge; no public contract module imports ``strategy_catalog`` directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from strategy_catalog.parameter_schema import canonical_digest


UNDECIDED_WIRE = "__UNDECIDED__"


class Undecided:
    """Singleton marker for a contract value that has not been decided."""

    _instance: Undecided | None = None

    def __new__(cls) -> Undecided:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNDECIDED"


UNDECIDED = Undecided()


def to_wire(value: object) -> object:
    if isinstance(value, Undecided):
        return UNDECIDED_WIRE
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: to_wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_wire(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_wire(value.value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise ValueError("float values are forbidden in canonical wire contracts")
    raise ValueError(f"unsupported canonical wire type: {type(value).__name__}")


def digest(value: object) -> str:
    wire = cast(Mapping[str, Any] | list[Any], to_wire(value))
    return canonical_digest(wire)
