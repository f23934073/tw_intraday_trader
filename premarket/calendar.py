"""Versioned TAIFEX trading-date and historical-contract resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from premarket.models import ContractIdentity, ContractIdentityStatus, SessionWindow


class CalendarCoverageError(ValueError):
    """The requested date is outside reviewed calendar evidence."""


def _date(value: object, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error


def _datetime(value: object, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


class TaifexTradingCalendar:
    """Reviewed annual calendar plus dated exceptional closures."""

    def __init__(
        self,
        *,
        schema_version: str,
        timezone: str,
        coverage_start: date,
        coverage_end: date,
        as_of: datetime,
        source_urls: tuple[str, ...],
        non_trading_dates: frozenset[date],
        source_digest: str,
    ) -> None:
        if coverage_end < coverage_start:
            raise ValueError("calendar coverage is invalid")
        if not source_urls:
            raise ValueError("calendar source URLs are required")
        if any(item < coverage_start or item > coverage_end for item in non_trading_dates):
            raise ValueError("non-trading date falls outside calendar coverage")
        self.schema_version = schema_version
        self.timezone = timezone
        self.coverage_start = coverage_start
        self.coverage_end = coverage_end
        self.as_of = as_of
        self.source_urls = source_urls
        self.non_trading_dates = non_trading_dates
        self.source_digest = source_digest
        self._tz = ZoneInfo(timezone)

    @classmethod
    def from_path(cls, path: Path) -> "TaifexTradingCalendar":
        raw = path.read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("calendar artifact must contain one object")
        annual = payload.get("annual_non_trading_dates")
        exceptional = payload.get("exceptional_closures")
        sources = payload.get("source_urls")
        if not isinstance(annual, list) or not isinstance(exceptional, list):
            raise ValueError("calendar closure lists are required")
        if not isinstance(sources, list) or not all(isinstance(item, str) and item for item in sources):
            raise ValueError("calendar source URLs are invalid")
        closures = frozenset(
            _date(item, "non-trading date")
            for item in (*annual, *exceptional)
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            timezone=str(payload["timezone"]),
            coverage_start=_date(payload["coverage_start"], "coverage_start"),
            coverage_end=_date(payload["coverage_end"], "coverage_end"),
            as_of=_datetime(payload["as_of"], "as_of"),
            source_urls=tuple(sources),
            non_trading_dates=closures,
            source_digest=hashlib.sha256(raw).hexdigest(),
        )

    def _require_coverage(self, value: date) -> None:
        if value < self.coverage_start or value > self.coverage_end:
            raise CalendarCoverageError(
                f"TAIFEX calendar has no reviewed coverage for {value.isoformat()}"
            )

    def is_trading_day(self, value: date) -> bool:
        self._require_coverage(value)
        return value.weekday() < 5 and value not in self.non_trading_dates

    def next_trading_day_on_or_after(self, value: date) -> date:
        cursor = value
        while cursor <= self.coverage_end:
            if self.is_trading_day(cursor):
                return cursor
            cursor += timedelta(days=1)
        raise CalendarCoverageError("calendar has no next reviewed trading day")

    def previous_trading_day(self, value: date) -> date:
        cursor = value - timedelta(days=1)
        while cursor >= self.coverage_start:
            if self.is_trading_day(cursor):
                return cursor
            cursor -= timedelta(days=1)
        raise CalendarCoverageError("calendar has no previous reviewed trading day")

    def trading_date_for(self, now: datetime) -> date:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("current time must include a timezone")
        local = now.astimezone(self._tz)
        start = local.date() + timedelta(days=1) if local.time() >= time(15, 0) else local.date()
        return self.next_trading_day_on_or_after(start)

    def session_window(self, trading_date: date, query_delay: timedelta) -> SessionWindow:
        if not self.is_trading_day(trading_date):
            raise ValueError("session trading_date must be a TAIFEX trading day")
        previous = self.previous_trading_day(trading_date)
        start = datetime.combine(previous, time(15, 0), tzinfo=self._tz)
        end = datetime.combine(previous + timedelta(days=1), time(5, 0), tzinfo=self._tz)
        return SessionWindow(
            trading_date=trading_date,
            start=start,
            end=end,
            query_not_before=end + query_delay,
        )


@dataclass(frozen=True)
class _HistoricalMapping:
    effective_from: date
    effective_to: date
    contract_code: str
    delivery_month: str | None
    last_trading_date: date | None


class HistoricalContractResolver:
    """Resolve only dated historical mappings; current aliases are not inputs."""

    def __init__(self, mappings: tuple[_HistoricalMapping, ...]) -> None:
        self._mappings = tuple(sorted(mappings, key=lambda item: item.effective_from))
        for previous, current in zip(self._mappings, self._mappings[1:]):
            if previous.effective_to >= current.effective_from:
                raise ValueError("historical contract mappings overlap")

    @classmethod
    def from_path(cls, path: Path) -> "HistoricalContractResolver":
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("mappings"), list):
            raise ValueError("historical roll artifact is invalid")
        mappings = tuple(
            _HistoricalMapping(
                effective_from=_date(item["effective_from"], "effective_from"),
                effective_to=_date(item["effective_to"], "effective_to"),
                contract_code=str(item["contract_code"]),
                delivery_month=str(item.get("delivery_month") or "") or None,
                last_trading_date=(
                    _date(item["last_trading_date"], "last_trading_date")
                    if item.get("last_trading_date")
                    else None
                ),
            )
            for item in payload["mappings"]
            if isinstance(item, dict)
        )
        return cls(mappings)

    def resolve(self, trading_date: date) -> ContractIdentity:
        for mapping in self._mappings:
            if mapping.effective_from <= trading_date <= mapping.effective_to:
                return ContractIdentity(
                    status=ContractIdentityStatus.RESOLVED_HISTORICALLY,
                    resolution_method="DATED_CONTRACT_ROLL_MAPPING",
                    resolved_contract_code=mapping.contract_code,
                    delivery_month=mapping.delivery_month,
                    last_trading_date=mapping.last_trading_date,
                )
        return ContractIdentity(
            status=ContractIdentityStatus.UNRESOLVED,
            resolution_method="HISTORICAL_MAPPING_NOT_FOUND",
        )
