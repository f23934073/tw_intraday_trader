"""Code-owned parameter schemas for immutable strategy versions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Callable, Mapping


CrossValidator = Callable[[Mapping[str, Any]], None]


def canonical_json(value: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_digest(value: Mapping[str, Any] | list[Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParameterSchema:
    """Small validated JSON-schema subset owned by deployed strategy code."""

    version: str
    fields: Mapping[str, Mapping[str, Any]]
    cross_validators: tuple[CrossValidator, ...] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("parameter schema version 不可為空")
        if not self.fields:
            raise ValueError("parameter schema fields 不可為空")
        for name, specification in self.fields.items():
            if not str(name).strip() or not isinstance(specification, Mapping):
                raise ValueError("parameter schema field 必須有名稱與 object specification")
            if specification.get("type") not in {
                "string",
                "integer",
                "decimal",
                "boolean",
                "time",
            }:
                raise ValueError(f"不支援的參數型別：{name}")
        # Ensure defaults are valid when the schema is constructed.
        defaults = {
            name: specification["default"]
            for name, specification in self.fields.items()
            if "default" in specification
        }
        self.canonicalize(defaults, require_all=False)

    @property
    def schema_document(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "fields": {name: dict(spec) for name, spec in self.fields.items()},
        }

    @property
    def schema_digest(self) -> str:
        return canonical_digest(self.schema_document)

    def canonicalize(
        self,
        values: Mapping[str, Any],
        *,
        require_all: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(values, Mapping):
            raise ValueError("策略參數必須是 JSON object")
        unknown = sorted(set(values) - set(self.fields))
        if unknown:
            raise ValueError(f"未知策略參數：{', '.join(unknown)}")

        canonical: dict[str, Any] = {}
        for name, specification in self.fields.items():
            if name in values:
                raw = values[name]
            elif "default" in specification:
                raw = specification["default"]
            elif specification.get("required", True) and require_all:
                raise ValueError(f"缺少必要策略參數：{name}")
            else:
                continue
            value = self._canonical_value(name, raw, specification)
            canonical[name] = value

        if require_all:
            for validator in self.cross_validators:
                validator(canonical)
        return canonical

    @staticmethod
    def _canonical_value(
        name: str,
        raw: Any,
        specification: Mapping[str, Any],
    ) -> Any:
        kind = str(specification["type"])
        if kind == "boolean":
            if not isinstance(raw, bool):
                raise ValueError(f"{name} 必須是 boolean")
            value: Any = raw
        elif kind == "integer":
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ValueError(f"{name} 必須是 integer")
            value = raw
        elif kind == "decimal":
            if isinstance(raw, bool):
                raise ValueError(f"{name} 必須是 decimal")
            try:
                decimal_value = Decimal(str(raw))
            except (InvalidOperation, ValueError) as error:
                raise ValueError(f"{name} 必須是 decimal") from error
            if not decimal_value.is_finite():
                raise ValueError(f"{name} 不可為 NaN 或 Infinity")
            value = format(decimal_value.normalize(), "f")
            if value == "-0":
                value = "0"
        elif kind == "time":
            if (
                not isinstance(raw, str)
                or len(raw) != 5
                or raw[2] != ":"
            ):
                raise ValueError(f"{name} 必須是 HH:MM")
            try:
                parsed = time.fromisoformat(raw)
            except ValueError as error:
                raise ValueError(f"{name} 必須是 HH:MM") from error
            if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
                raise ValueError(f"{name} 必須是沒有 timezone 的 HH:MM")
            value = parsed.strftime("%H:%M")
        else:
            if not isinstance(raw, str):
                raise ValueError(f"{name} 必須是 string")
            value = raw.strip()
            if not value and specification.get("min_length", 0) > 0:
                raise ValueError(f"{name} 不可為空")

        allowed = specification.get("enum")
        if allowed is not None and value not in allowed:
            raise ValueError(f"{name} 必須是：{', '.join(str(item) for item in allowed)}")

        if kind in {"integer", "decimal"}:
            numeric = Decimal(str(value))
            if "minimum" in specification and numeric < Decimal(str(specification["minimum"])):
                raise ValueError(f"{name} 小於 minimum")
            if "maximum" in specification and numeric > Decimal(str(specification["maximum"])):
                raise ValueError(f"{name} 大於 maximum")
        elif kind == "string" and "max_length" in specification:
            if len(value) > int(specification["max_length"]):
                raise ValueError(f"{name} 超過 max_length")

        if isinstance(value, float) and not isfinite(value):
            raise ValueError(f"{name} 不可為 NaN 或 Infinity")
        return value


def validate_entry_window(parameters: Mapping[str, Any]) -> None:
    start = parameters.get("entry_window_start")
    end = parameters.get("entry_window_end")
    if start is not None and end is not None and str(start) >= str(end):
        raise ValueError("entry_window_start 必須早於 entry_window_end")
