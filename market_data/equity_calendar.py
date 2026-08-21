"""Reviewed equity-market session calendar used by qualification capture."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ReviewedEquityCalendar:
    schema_version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    as_of: datetime
    source_urls: tuple[str, ...]
    non_trading_dates: frozenset[date]
    source_digest: str

    @classmethod
    def from_path(cls, path: Path) -> "ReviewedEquityCalendar":
        encoded = path.read_bytes()
        raw = json.loads(encoded)
        if not isinstance(raw, dict):
            raise ValueError("equity calendar must contain one object")
        annual = raw.get("annual_non_trading_dates")
        exceptional = raw.get("exceptional_closures")
        sources = raw.get("source_urls")
        if not isinstance(annual, list) or not isinstance(exceptional, list):
            raise ValueError("equity calendar closure lists are required")
        if not isinstance(sources, list) or not all(
            isinstance(item, str) and item.strip() for item in sources
        ):
            raise ValueError("equity calendar source URLs are required")
        as_of = datetime.fromisoformat(str(raw["as_of"]))
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("equity calendar as_of must be timezone-aware")
        start = date.fromisoformat(str(raw["coverage_start"]))
        end = date.fromisoformat(str(raw["coverage_end"]))
        if end < start:
            raise ValueError("equity calendar coverage is invalid")
        closures = frozenset(
            date.fromisoformat(str(item)) for item in (*annual, *exceptional)
        )
        if any(item < start or item > end for item in closures):
            raise ValueError("equity closure is outside calendar coverage")
        return cls(
            schema_version=str(raw["schema_version"]),
            timezone=str(raw["timezone"]),
            coverage_start=start,
            coverage_end=end,
            as_of=as_of,
            source_urls=tuple(sources),
            non_trading_dates=closures,
            source_digest=hashlib.sha256(encoded).hexdigest(),
        )

    def is_trading_day(self, value: date) -> bool:
        self._require_coverage(value)
        return value.weekday() < 5 and value not in self.non_trading_dates

    def previous_trading_day(self, value: date) -> date:
        self._require_coverage(value)
        cursor = value - timedelta(days=1)
        while cursor >= self.coverage_start:
            if self.is_trading_day(cursor):
                return cursor
            cursor -= timedelta(days=1)
        raise ValueError("equity calendar has no previous reviewed trading day")

    def _require_coverage(self, value: date) -> None:
        if value < self.coverage_start or value > self.coverage_end:
            raise ValueError(
                f"equity calendar has no reviewed coverage for {value.isoformat()}"
            )
