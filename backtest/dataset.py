"""Immutable historical-bar datasets and server-side provider acquisition."""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import shutil
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable, Iterator, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from backtest.domain import HistoricalBar, canonical_json, decimal
from market_data.models import KBar
from market_data.provider import MarketDataProvider


_TAIPEI = ZoneInfo("Asia/Taipei")
_MAX_PROVIDER_DAYS = 29
_TIMESTAMP_SYMBOL_ORDER = "TIMESTAMP_SYMBOL"
_SYMBOL_TIMESTAMP_ORDER = "SYMBOL_TIMESTAMP"
_ORDER_CHUNK_SIZE = 50_000
_ORDER_MERGE_FAN_IN = 32
ProgressCallback = Callable[[float, str], None]
Cancelled = Callable[[], bool]


def _canonical_daily_decimal(value: Decimal | int | float | str) -> Decimal:
    """Freeze equivalent daily numeric values to one Decimal representation."""
    parsed = decimal(value)
    if not parsed.is_finite():
        raise ValueError("daily dataset Decimal must be finite")
    if parsed == 0:
        return Decimal("0")
    return Decimal(format(parsed.normalize(), "f"))


class _CadenceEvidence:
    """Coverage-weighted cadence evidence grouped by symbol and session."""

    def __init__(self) -> None:
        self._last_by_session: dict[tuple[str, date], datetime] = {}
        self._observations: Counter[tuple[str, date]] = Counter()
        self._gap_seconds: Counter[int] = Counter()
        self._minute_aligned = True
        self._taipei_timezone = True

    def add(self, bar: HistoricalBar) -> None:
        session = (bar.symbol, bar.timestamp.date())
        previous = self._last_by_session.get(session)
        if previous is not None:
            seconds = int((bar.timestamp - previous).total_seconds())
            if seconds > 0:
                self._gap_seconds[seconds] += 1
        self._last_by_session[session] = bar.timestamp
        self._observations[session] += 1
        self._minute_aligned = self._minute_aligned and (
            bar.timestamp.second == 0 and bar.timestamp.microsecond == 0
        )
        self._taipei_timezone = self._taipei_timezone and (
            bar.timestamp.utcoffset() == timedelta(hours=8)
        )

    def result(self) -> tuple[str, tuple[str, ...], dict[str, Any]]:
        total_gaps = sum(self._gap_seconds.values())
        dominant_seconds: int | None = None
        dominant_count = 0
        if self._gap_seconds:
            dominant_seconds, dominant_count = self._gap_seconds.most_common(1)[0]
        dominant_ratio = dominant_count / total_gaps if total_gaps else 0.0
        intraday_sessions = sum(count > 1 for count in self._observations.values())
        max_bars = max(self._observations.values(), default=0)
        capabilities = ["OHLCV"]
        if intraday_sessions and self._minute_aligned and self._taipei_timezone:
            capabilities.extend(("KBAR_INTRADAY", "SESSION_BOUNDARIES"))
        if (
            intraday_sessions
            and self._minute_aligned
            and self._taipei_timezone
            and dominant_seconds == 60
            and dominant_ratio >= 0.80
        ):
            capabilities.append("KBAR_1M")
        if "KBAR_1M" in capabilities:
            profile = "KBAR_1M_V1"
        elif "KBAR_INTRADAY" in capabilities:
            profile = "KBAR_INTRADAY_V1"
        else:
            profile = "KBAR_DAILY_TEST_V1"
        summary = {
            "method": "SYMBOL_SESSION_GAP_V1",
            "session_count": len(self._observations),
            "intraday_session_count": intraday_sessions,
            "max_bars_per_session": max_bars,
            "observed_gap_count": total_gaps,
            "dominant_interval_seconds": dominant_seconds,
            "dominant_interval_ratio": dominant_ratio,
            "minute_aligned": self._minute_aligned,
            "taipei_timezone": self._taipei_timezone,
        }
        return profile, tuple(capabilities), summary


class _BoundedCadenceEvidence:
    """Cadence evidence that retains only the current session per symbol."""

    def __init__(self) -> None:
        self._current: dict[str, tuple[date, datetime, int]] = {}
        self._session_count = 0
        self._intraday_session_count = 0
        self._max_bars_per_session = 0
        self._gap_seconds: Counter[int] = Counter()
        self._minute_aligned = True
        self._taipei_timezone = True

    def add(self, bar: HistoricalBar) -> None:
        session_date = bar.session_date or bar.timestamp.date()
        current = self._current.get(bar.symbol)
        if current is None or current[0] != session_date:
            if current is not None:
                if session_date < current[0]:
                    raise ValueError("Kbar session date must be monotonic per symbol")
                self._finish_session(current[2])
            self._current[bar.symbol] = (session_date, bar.timestamp, 1)
        else:
            seconds = int((bar.timestamp - current[1]).total_seconds())
            if seconds <= 0:
                raise ValueError("Kbar timestamps must increase within a session")
            self._gap_seconds[seconds] += 1
            self._current[bar.symbol] = (session_date, bar.timestamp, current[2] + 1)
        self._minute_aligned = self._minute_aligned and (
            bar.timestamp.second == 0 and bar.timestamp.microsecond == 0
        )
        self._taipei_timezone = self._taipei_timezone and (
            bar.timestamp.utcoffset() == timedelta(hours=8)
        )

    def result(self) -> tuple[str, tuple[str, ...], dict[str, Any]]:
        for _session_date, _last_timestamp, count in self._current.values():
            self._finish_session(count)
        self._current.clear()
        total_gaps = sum(self._gap_seconds.values())
        dominant_seconds: int | None = None
        dominant_count = 0
        if self._gap_seconds:
            dominant_seconds, dominant_count = self._gap_seconds.most_common(1)[0]
        dominant_ratio = dominant_count / total_gaps if total_gaps else 0.0
        capabilities = ["OHLCV"]
        if (
            self._intraday_session_count
            and self._minute_aligned
            and self._taipei_timezone
        ):
            capabilities.extend(("KBAR_INTRADAY", "SESSION_BOUNDARIES"))
        if (
            self._intraday_session_count
            and self._minute_aligned
            and self._taipei_timezone
            and dominant_seconds == 60
            and dominant_ratio >= 0.80
        ):
            capabilities.append("KBAR_1M")
        if "KBAR_1M" in capabilities:
            profile = "KBAR_1M_V1"
        elif "KBAR_INTRADAY" in capabilities:
            profile = "KBAR_INTRADAY_V1"
        else:
            profile = "KBAR_DAILY_TEST_V1"
        summary = {
            "method": "SYMBOL_SESSION_GAP_V1",
            "session_count": self._session_count,
            "intraday_session_count": self._intraday_session_count,
            "max_bars_per_session": self._max_bars_per_session,
            "observed_gap_count": total_gaps,
            "dominant_interval_seconds": dominant_seconds,
            "dominant_interval_ratio": dominant_ratio,
            "minute_aligned": self._minute_aligned,
            "taipei_timezone": self._taipei_timezone,
        }
        return profile, tuple(capabilities), summary

    def _finish_session(self, count: int) -> None:
        self._session_count += 1
        self._intraday_session_count += count > 1
        self._max_bars_per_session = max(self._max_bars_per_session, count)


def _taipei_timestamp(timestamp: datetime) -> datetime:
    """Canonicalize a Provider Kbar event time to Taiwan market time."""

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Provider Kbar timestamp 必須包含 timezone")
    return timestamp.astimezone(_TAIPEI)


def _taipei_session_date(timestamp: datetime) -> date:
    """Resolve the Taiwan market session date for a Provider Kbar."""

    return _taipei_timestamp(timestamp).date()


@dataclass(frozen=True)
class HistoricalInstrument:
    symbol: str
    name: str
    market: str

    def to_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "name": self.name, "market": self.market}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HistoricalInstrument":
        return cls(
            symbol=str(value["symbol"]),
            name=str(value.get("name") or value["symbol"]),
            market=str(value.get("market") or ""),
        )


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    created_at: datetime
    source: str
    profile: str
    capabilities: tuple[str, ...]
    start_date: str
    end_date: str
    requested_symbols: tuple[str, ...]
    observed_symbols: tuple[str, ...]
    bar_count: int
    bars_sha256: str
    universe_scope: str
    research_eligible: bool
    issues: tuple[str, ...] = ()
    storage_format: str = "JSONL_FULL_V1"
    payload_order: str | None = None
    parent_dataset_id: str | None = None
    delta_bar_count: int = 0
    symbol_last_timestamps: tuple[tuple[str, str], ...] = ()
    universe_selection: str = "ALL_CURRENT"
    cadence_summary: Mapping[str, Any] = field(default_factory=dict)
    includes_cadence_summary: bool = field(default=True, repr=False, compare=False)
    daily_bar_contract: str | None = None
    derivation: Mapping[str, Any] | None = None
    session_contract: Mapping[str, Any] | None = None
    price_adjustment_policy: str | None = None
    corporate_action_adjusted: bool | None = None
    volume_contract: Mapping[str, Any] | None = None
    amount_contract: Mapping[str, Any] | None = None
    source_snapshot_digest: str | None = None
    plan_identity: Mapping[str, Any] | None = None
    plan_identity_digest: str | None = None

    @property
    def manifest_digest(self) -> str:
        value = self.to_dict(include_digest=False)
        return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        value = {
            "dataset_id": self.dataset_id,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "profile": self.profile,
            "capabilities": list(self.capabilities),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "requested_symbols": list(self.requested_symbols),
            "observed_symbols": list(self.observed_symbols),
            "bar_count": self.bar_count,
            "bars_sha256": self.bars_sha256,
            "universe_scope": self.universe_scope,
            "research_eligible": self.research_eligible,
            "issues": list(self.issues),
            "storage_format": self.storage_format,
            "parent_dataset_id": self.parent_dataset_id,
            "delta_bar_count": self.delta_bar_count,
            "symbol_last_timestamps": [
                {"symbol": symbol, "timestamp": timestamp}
                for symbol, timestamp in self.symbol_last_timestamps
            ],
            "universe_selection": self.universe_selection,
        }
        if self.includes_cadence_summary:
            value["cadence_summary"] = dict(self.cadence_summary)
        # Keep legacy manifest bytes and historical result digests unchanged:
        # new fields are serialised only when explicitly set.
        if self.payload_order is not None:
            value["payload_order"] = self.payload_order
        if self.daily_bar_contract is not None:
            value["daily_bar_contract"] = self.daily_bar_contract
        if self.derivation is not None:
            value["derivation"] = dict(self.derivation)
        if self.session_contract is not None:
            value["session_contract"] = dict(self.session_contract)
        if self.price_adjustment_policy is not None:
            value["price_adjustment_policy"] = self.price_adjustment_policy
        if self.corporate_action_adjusted is not None:
            value["corporate_action_adjusted"] = self.corporate_action_adjusted
        if self.volume_contract is not None:
            value["volume_contract"] = dict(self.volume_contract)
        if self.amount_contract is not None:
            value["amount_contract"] = dict(self.amount_contract)
        if self.source_snapshot_digest is not None:
            value["source_snapshot_digest"] = self.source_snapshot_digest
        if self.plan_identity is not None:
            value["plan_identity"] = dict(self.plan_identity)
        if self.plan_identity_digest is not None:
            value["plan_identity_digest"] = self.plan_identity_digest
        if include_digest:
            value["manifest_digest"] = self.manifest_digest
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DatasetManifest":
        return cls(
            dataset_id=str(value["dataset_id"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            source=str(value["source"]),
            profile=str(value["profile"]),
            capabilities=tuple(str(item) for item in value.get("capabilities", ())),
            start_date=str(value["start_date"]),
            end_date=str(value["end_date"]),
            requested_symbols=tuple(str(item) for item in value.get("requested_symbols", ())),
            observed_symbols=tuple(str(item) for item in value.get("observed_symbols", ())),
            bar_count=int(value["bar_count"]),
            bars_sha256=str(value["bars_sha256"]),
            universe_scope=str(value.get("universe_scope", "IMPORTED")),
            research_eligible=bool(value.get("research_eligible", False)),
            issues=tuple(str(item) for item in value.get("issues", ())),
            storage_format=str(value.get("storage_format", "JSONL_FULL_V1")),
            payload_order=(
                str(value["payload_order"])
                if value.get("payload_order") is not None
                else None
            ),
            parent_dataset_id=(
                str(value["parent_dataset_id"])
                if value.get("parent_dataset_id")
                else None
            ),
            delta_bar_count=int(value.get("delta_bar_count", 0)),
            symbol_last_timestamps=tuple(
                (str(item["symbol"]), str(item["timestamp"]))
                for item in value.get("symbol_last_timestamps", ())
            ),
            universe_selection=str(value.get("universe_selection", "ALL_CURRENT")),
            cadence_summary=dict(value.get("cadence_summary") or {}),
            includes_cadence_summary="cadence_summary" in value,
            daily_bar_contract=(
                str(value["daily_bar_contract"])
                if value.get("daily_bar_contract") is not None
                else None
            ),
            derivation=(dict(value["derivation"]) if value.get("derivation") is not None else None),
            session_contract=(
                dict(value["session_contract"])
                if value.get("session_contract") is not None
                else None
            ),
            price_adjustment_policy=(
                str(value["price_adjustment_policy"])
                if value.get("price_adjustment_policy") is not None
                else None
            ),
            corporate_action_adjusted=(
                bool(value["corporate_action_adjusted"])
                if value.get("corporate_action_adjusted") is not None
                else None
            ),
            volume_contract=(
                dict(value["volume_contract"])
                if value.get("volume_contract") is not None
                else None
            ),
            amount_contract=(
                dict(value["amount_contract"])
                if value.get("amount_contract") is not None
                else None
            ),
            source_snapshot_digest=(
                str(value["source_snapshot_digest"])
                if value.get("source_snapshot_digest") is not None
                else None
            ),
            plan_identity=(
                dict(value["plan_identity"])
                if value.get("plan_identity") is not None
                else None
            ),
            plan_identity_digest=(
                str(value["plan_identity_digest"])
                if value.get("plan_identity_digest") is not None
                else None
            ),
        )


class DatasetCancelled(RuntimeError):
    """Raised when a durable dataset job asks the collector to stop."""


class HistoricalDatasetCatalog:
    """Append-only JSONL catalog with an optional Parquet future adapter.

    JSONL is deliberate as the dependency-free local format: every row is
    canonical, auditable, and usable in CI.  The manifest records the exact
    format rather than pretending that generated fixture data is production
    Parquet.  A production ingestion deployment can add a Parquet adapter
    without changing this public catalog contract.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def list_manifests(self) -> list[DatasetManifest]:
        manifests: list[DatasetManifest] = []
        for path in self._root.glob("*/manifest.json"):
            try:
                manifests.append(DatasetManifest.from_dict(json.loads(path.read_text())))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(manifests, key=lambda value: value.created_at, reverse=True)

    def get_manifest(self, dataset_id: str) -> DatasetManifest:
        path = self._dataset_dir(dataset_id) / "manifest.json"
        if not path.is_file():
            raise KeyError(f"找不到歷史資料集：{dataset_id}")
        return DatasetManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def load_bars(self, dataset_id: str) -> list[HistoricalBar]:
        manifest = self.get_manifest(dataset_id)
        if manifest.storage_format == "JSONL_FULL_V1":
            bars = list(self.iter_bars(dataset_id))
        elif manifest.storage_format == "JSONL_DELTA_V1":
            if not manifest.parent_dataset_id:
                raise ValueError(f"增量資料集 {dataset_id} 缺少 parent_dataset_id")
            parent = self.load_bars(manifest.parent_dataset_id)
            delta = self._load_payload(dataset_id, "bars.delta.jsonl", manifest.bars_sha256)
            if len(delta) != manifest.delta_bar_count:
                raise ValueError(f"資料集 {dataset_id} delta bar count 不符，拒絕回測")
            bars = self._validate_and_sort((*parent, *delta))
        else:
            raise ValueError(f"資料集 {dataset_id} storage format 不支援")
        if len(bars) != manifest.bar_count:
            raise ValueError(f"資料集 {dataset_id} bar count 不符，拒絕回測")
        return sorted(bars, key=lambda value: (value.timestamp, value.symbol))

    def iter_bars(self, dataset_id: str) -> Iterator[HistoricalBar]:
        """Yield verified full JSONL bars without creating a second full-size list.

        The engine still orders events deterministically before replay.  This
        method removes the catalog's otherwise redundant list allocation for
        full snapshots while keeping checksum and bar-count checks fail-closed.
        Delta datasets retain their existing merge-and-deduplicate semantics.
        """

        manifest = self.get_manifest(dataset_id)
        if manifest.storage_format == "JSONL_FULL_V1":
            return self._iter_full_dataset(
                dataset_id,
                manifest.bar_count,
                manifest.bars_sha256,
            )
        if manifest.storage_format == "JSONL_DELTA_V1":
            # A delta requires parent/child merge and conflict validation, so
            # its canonical ordering is still materialized exactly once here.
            return iter(self.load_bars(dataset_id))
        raise ValueError(f"資料集 {dataset_id} storage format 不支援")

    def iter_bars_ordered(
        self,
        dataset_id: str,
        *,
        chunk_size: int = _ORDER_CHUNK_SIZE,
        merge_fan_in: int = _ORDER_MERGE_FAN_IN,
    ) -> Iterator[HistoricalBar]:
        """Yield verified bars in deterministic event order with bounded RAM.

        Timestamp-major payloads are validated while streaming.  Legacy and
        symbol-partition payloads are sorted through bounded temporary files;
        merge fan-in is capped so full-market datasets do not exhaust file
        descriptors.  Delta datasets merge their ordered parent and child
        streams without calling ``load_bars()``.
        """

        if chunk_size < 1:
            raise ValueError("ordered Kbar chunk_size 必須大於 0")
        if merge_fan_in < 2:
            raise ValueError("ordered Kbar merge_fan_in 必須至少為 2")
        manifest = self.get_manifest(dataset_id)
        if manifest.storage_format == "JSONL_FULL_V1":
            source = self._iter_full_dataset(
                dataset_id,
                manifest.bar_count,
                manifest.bars_sha256,
            )
            ordered = self._order_payload(
                source,
                payload_order=manifest.payload_order,
                chunk_size=chunk_size,
                merge_fan_in=merge_fan_in,
            )
            return self._validate_ordered_bars(
                dataset_id,
                ordered,
                expected_bar_count=manifest.bar_count,
            )
        if manifest.storage_format == "JSONL_DELTA_V1":
            if not manifest.parent_dataset_id:
                raise ValueError(f"增量資料集 {dataset_id} 缺少 parent_dataset_id")
            parent = self.iter_bars_ordered(
                manifest.parent_dataset_id,
                chunk_size=chunk_size,
                merge_fan_in=merge_fan_in,
            )
            delta_source = self._iter_counted_payload(
                dataset_id,
                "bars.delta.jsonl",
                manifest.bars_sha256,
                manifest.delta_bar_count,
            )
            delta = self._order_payload(
                delta_source,
                payload_order=manifest.payload_order,
                chunk_size=chunk_size,
                merge_fan_in=merge_fan_in,
            )
            merged = heapq.merge(parent, delta, key=self._event_key)
            return self._validate_ordered_bars(
                dataset_id,
                merged,
                expected_bar_count=manifest.bar_count,
                allow_identical_duplicates=True,
            )
        raise ValueError(f"資料集 {dataset_id} storage format 不支援")

    def _iter_full_dataset(
        self,
        dataset_id: str,
        expected_bar_count: int,
        expected_checksum: str,
    ) -> Iterator[HistoricalBar]:
        count = 0
        for bar in self._iter_payload(dataset_id, "bars.jsonl", expected_checksum):
            count += 1
            yield bar
        if count != expected_bar_count:
            raise ValueError(f"資料集 {dataset_id} bar count 不符，拒絕回測")

    def _iter_counted_payload(
        self,
        dataset_id: str,
        filename: str,
        expected_checksum: str,
        expected_bar_count: int,
    ) -> Iterator[HistoricalBar]:
        count = 0
        for bar in self._iter_payload(dataset_id, filename, expected_checksum):
            count += 1
            yield bar
        if count != expected_bar_count:
            raise ValueError(f"資料集 {dataset_id} delta bar count 不符，拒絕回測")

    def _order_payload(
        self,
        bars: Iterable[HistoricalBar],
        *,
        payload_order: str | None,
        chunk_size: int,
        merge_fan_in: int,
    ) -> Iterator[HistoricalBar]:
        if payload_order == _TIMESTAMP_SYMBOL_ORDER:
            return iter(bars)
        return self._iter_external_ordered(
            bars,
            chunk_size=chunk_size,
            merge_fan_in=merge_fan_in,
        )

    def _iter_external_ordered(
        self,
        bars: Iterable[HistoricalBar],
        *,
        chunk_size: int,
        merge_fan_in: int,
    ) -> Iterator[HistoricalBar]:
        with TemporaryDirectory(prefix=".ordered-kbars-", dir=self._root) as directory:
            temporary_root = Path(directory)
            paths: list[Path] = []
            chunk: list[HistoricalBar] = []
            for bar in bars:
                chunk.append(bar)
                if len(chunk) >= chunk_size:
                    paths.append(
                        self._write_ordered_chunk(
                            temporary_root,
                            chunk,
                            len(paths),
                        )
                    )
                    chunk = []
            if chunk:
                paths.append(
                    self._write_ordered_chunk(
                        temporary_root,
                        chunk,
                        len(paths),
                    )
                )
            pass_index = 0
            while len(paths) > 1:
                next_paths: list[Path] = []
                for group_index, start in enumerate(range(0, len(paths), merge_fan_in)):
                    group = paths[start : start + merge_fan_in]
                    output = temporary_root / f"merge-{pass_index}-{group_index}.jsonl"
                    self._merge_ordered_files(group, output)
                    next_paths.append(output)
                for path in paths:
                    path.unlink()
                paths = next_paths
                pass_index += 1
            if paths:
                yield from self._iter_temporary_bars(paths[0])

    def _write_ordered_chunk(
        self,
        directory: Path,
        bars: list[HistoricalBar],
        index: int,
    ) -> Path:
        bars.sort(key=self._event_key)
        path = directory / f"chunk-{index}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for bar in bars:
                handle.write(canonical_json(bar.to_dict()) + "\n")
        return path

    def _merge_ordered_files(self, paths: list[Path], output: Path) -> None:
        with ExitStack() as stack:
            handles = [stack.enter_context(path.open("r", encoding="utf-8")) for path in paths]
            streams = [self._iter_bar_lines(handle) for handle in handles]
            with output.open("w", encoding="utf-8") as target:
                for bar in heapq.merge(*streams, key=self._event_key):
                    target.write(canonical_json(bar.to_dict()) + "\n")

    @staticmethod
    def _iter_bar_lines(lines: Iterable[str]) -> Iterator[HistoricalBar]:
        for line in lines:
            if line.strip():
                yield HistoricalBar.from_dict(json.loads(line))

    @staticmethod
    def _iter_temporary_bars(path: Path) -> Iterator[HistoricalBar]:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield HistoricalBar.from_dict(json.loads(line))

    @classmethod
    def _validate_ordered_bars(
        cls,
        dataset_id: str,
        bars: Iterable[HistoricalBar],
        *,
        expected_bar_count: int,
        allow_identical_duplicates: bool = False,
    ) -> Iterator[HistoricalBar]:
        previous_key: tuple[datetime, str] | None = None
        previous_bar: HistoricalBar | None = None
        count = 0
        for bar in bars:
            key = cls._event_key(bar)
            if previous_key is not None and key < previous_key:
                raise ValueError(f"資料集 {dataset_id} Kbar 順序或唯一性錯誤")
            if key == previous_key:
                if allow_identical_duplicates and bar == previous_bar:
                    continue
                raise ValueError(f"資料集 {dataset_id} Kbar 順序或唯一性錯誤")
            previous_key = key
            previous_bar = bar
            count += 1
            yield bar
        if count != expected_bar_count:
            raise ValueError(f"資料集 {dataset_id} bar count 不符，拒絕回測")

    @staticmethod
    def _event_key(bar: HistoricalBar) -> tuple[datetime, str]:
        return bar.timestamp, bar.symbol

    def symbol_last_timestamps(self, dataset_id: str) -> dict[str, datetime]:
        """Return compact per-symbol watermarks, scanning legacy datasets once."""

        manifest = self.get_manifest(dataset_id)
        if manifest.symbol_last_timestamps:
            return {
                symbol: datetime.fromisoformat(timestamp)
                for symbol, timestamp in manifest.symbol_last_timestamps
            }
        watermarks: dict[str, datetime] = {}
        if manifest.storage_format == "JSONL_FULL_V1":
            bars = self._iter_payload(dataset_id, "bars.jsonl", manifest.bars_sha256)
        else:
            bars = iter(self.load_bars(dataset_id))
        for bar in bars:
            previous = watermarks.get(bar.symbol)
            if previous is None or bar.timestamp > previous:
                watermarks[bar.symbol] = bar.timestamp
        return watermarks

    def _load_payload(
        self,
        dataset_id: str,
        filename: str,
        expected_checksum: str,
    ) -> list[HistoricalBar]:
        return list(self._iter_payload(dataset_id, filename, expected_checksum))

    def _iter_payload(
        self,
        dataset_id: str,
        filename: str,
        expected_checksum: str,
    ) -> Iterator[HistoricalBar]:
        path = self._dataset_dir(dataset_id) / filename
        if not path.is_file():
            raise ValueError(f"資料集 {dataset_id} 缺少 {filename}")
        checksum = hashlib.sha256()
        with path.open("rb") as handle:
            for raw_line in handle:
                checksum.update(raw_line)
                line = raw_line.decode("utf-8").strip()
                if line:
                    yield HistoricalBar.from_dict(json.loads(line))
        if checksum.hexdigest() != expected_checksum:
            raise ValueError(f"資料集 {dataset_id} checksum 不符，拒絕回測")

    def _iter_canonical_payload(
        self,
        dataset_id: str,
        filename: str,
        expected_checksum: str,
    ) -> Iterator[HistoricalBar]:
        """Yield only exact canonical JSONL bytes for immutable replay checks."""

        path = self._dataset_dir(dataset_id) / filename
        if not path.is_file():
            raise ValueError(f"資料集 {dataset_id} 缺少 {filename}")
        checksum = hashlib.sha256()
        with path.open("rb") as handle:
            for raw_line in handle:
                checksum.update(raw_line)
                try:
                    bar = HistoricalBar.from_dict(json.loads(raw_line))
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                    raise ValueError(
                        f"FinMind Dataset {dataset_id} payload is not canonical JSONL"
                    ) from error
                canonical_line = (
                    canonical_json(bar.to_dict()) + "\n"
                ).encode("utf-8")
                if raw_line != canonical_line:
                    raise ValueError(
                        f"FinMind Dataset {dataset_id} payload canonical bytes conflict"
                    )
                yield bar
        if checksum.hexdigest() != expected_checksum:
            raise ValueError(f"資料集 {dataset_id} checksum 不符，拒絕回測")

    def create_imported_dataset(
        self,
        *,
        bars: Iterable[HistoricalBar],
        source: str,
        universe_scope: str = "IMPORTED",
        research_eligible: bool = False,
        issues: Iterable[str] = (),
    ) -> DatasetManifest:
        normalized = self._validate_and_sort(bars)
        if not normalized:
            raise ValueError("不可建立空的歷史資料集")
        return self._seal(
            bars=normalized,
            source=source,
            requested_symbols=tuple(sorted({bar.symbol for bar in normalized})),
            universe_scope=universe_scope,
            research_eligible=research_eligible,
            issues=tuple(issues),
            universe_selection="EXPLICIT",
        )

    def create_derived_daily_dataset(
        self,
        *,
        dataset_id: str,
        base_dataset_id: str,
        completion_proofs: Mapping[tuple[str, date], str],
        session_contract: Mapping[str, Any],
        price_adjustment_policy: str,
        corporate_action_adjusted: bool,
        volume_contract: Mapping[str, Any],
        issues: Iterable[str] = (),
    ) -> DatasetManifest:
        """Materialise a sealed daily series from verified intraday sessions.

        The caller must provide an evidence digest for every parent
        ``(symbol, session_date)`` being aggregated.  This prevents the G0
        sample from being misused as blanket evidence for an arbitrary provider
        dataset.  The parent stays immutable and the daily child gets a full
        JSONL payload plus parent lineage in its manifest.
        """
        base = self.get_manifest(base_dataset_id)
        if not {"OHLCV", "KBAR_INTRADAY"}.issubset(base.capabilities):
            raise ValueError("daily derivation requires an intraday OHLCV parent dataset")
        if price_adjustment_policy != "RAW":
            raise ValueError("daily v1 only supports price_adjustment_policy=RAW")
        if corporate_action_adjusted:
            raise ValueError("daily v1 cannot claim corporate action adjustment")
        if not str(session_contract.get("version") or "").strip():
            raise ValueError("daily derivation requires a versioned session contract")
        if str(volume_contract.get("scope") or "") != "REGULAR_SESSION":
            raise ValueError("daily derivation requires REGULAR_SESSION volume scope")
        if str(volume_contract.get("unit") or "") != "COMMON_LOT":
            raise ValueError("daily derivation requires COMMON_LOT volume unit")

        grouped: dict[tuple[str, date], list[HistoricalBar]] = {}
        for bar in self.load_bars(base_dataset_id):
            if bar.session_date is None:
                raise ValueError(
                    "daily derivation requires calendar-resolved session_date on every parent bar"
                )
            grouped.setdefault((bar.symbol, bar.session_date), []).append(bar)
        if not grouped:
            raise ValueError("daily derivation parent dataset has no bars")
        missing_proofs = sorted(
            f"{symbol}:{session.isoformat()}"
            for symbol, session in grouped
            if not str(completion_proofs.get((symbol, session), "")).strip()
        )
        if missing_proofs:
            raise ValueError(
                "daily derivation requires completion evidence for every session: "
                + ", ".join(missing_proofs[:5])
            )
        unexpected_proofs = sorted(
            f"{symbol}:{session.isoformat()}"
            for symbol, session in completion_proofs
            if (symbol, session) not in grouped
        )
        if unexpected_proofs:
            raise ValueError(
                "daily derivation completion evidence does not match the parent dataset: "
                + ", ".join(unexpected_proofs[:5])
            )
        proof_digests = {
            f"{symbol}:{session.isoformat()}": completion_proofs[(symbol, session)]
            for symbol, session in sorted(grouped)
        }
        derivation = {
            "version": "daily-ohclv-v1",
            "parent_dataset_id": base.dataset_id,
            "parent_dataset_digest": base.manifest_digest,
            "completion_proof_digests": proof_digests,
        }
        all_issues = tuple(
            dict.fromkeys(
                (
                    *base.issues,
                    *issues,
                    "RAW_PRICE_UNADJUSTED",
                    "FORMAL_RESEARCH_INELIGIBLE",
                )
            )
        )
        final_dir = self._dataset_dir(dataset_id)
        if final_dir.is_dir():
            existing = self.get_manifest(dataset_id)
            compatible = (
                existing.source == "DERIVED_FINALIZED_SESSION_V1"
                and existing.profile == "KBAR_DAILY_V1"
                and existing.capabilities == ("OHLCV", "KBAR_DAILY")
                and existing.derivation == derivation
                and existing.session_contract == dict(session_contract)
                and existing.price_adjustment_policy == price_adjustment_policy
                and existing.corporate_action_adjusted is False
                and existing.volume_contract == dict(volume_contract)
                and existing.issues == all_issues
            )
            if not compatible:
                raise ValueError(
                    f"daily dataset {dataset_id} already exists with a different immutable contract"
                )
            return existing

        daily_bars: list[HistoricalBar] = []
        coverage: dict[str, dict[str, Any]] = {}
        for (symbol, session), session_bars in sorted(grouped.items()):
            ordered = sorted(session_bars, key=lambda item: item.timestamp)
            if len({bar.timestamp for bar in ordered}) != len(ordered):
                raise ValueError(f"daily derivation found duplicate timestamps: {symbol} {session}")
            if any(bar.timestamp.date() != session for bar in ordered):
                raise ValueError(
                    "daily derivation source timestamp/session_date mismatch: "
                    f"{symbol} {session.isoformat()}"
                )
            first, last = ordered[0], ordered[-1]
            daily_bars.append(
                HistoricalBar(
                    symbol=symbol,
                    name=first.name,
                    market=first.market,
                    timestamp=last.timestamp,
                    open=_canonical_daily_decimal(first.open),
                    high=_canonical_daily_decimal(max(bar.high for bar in ordered)),
                    low=_canonical_daily_decimal(min(bar.low for bar in ordered)),
                    close=_canonical_daily_decimal(last.close),
                    volume=sum(bar.volume for bar in ordered),
                    amount=_canonical_daily_decimal(
                        sum(
                            bar.amount if bar.amount is not None else bar.close * bar.volume
                            for bar in ordered
                        )
                    ),
                    session_date=session,
                    session_open_at=first.timestamp,
                )
            )
            item = coverage.setdefault(
                symbol,
                {"resolved_session_count": 0, "first_session_date": session.isoformat(), "last_session_date": session.isoformat()},
            )
            item["resolved_session_count"] += 1
            item["first_session_date"] = min(item["first_session_date"], session.isoformat())
            item["last_session_date"] = max(item["last_session_date"], session.isoformat())

        temporary_dir = self._root / f".{dataset_id}.tmp"
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        temporary_dir.mkdir(parents=True, exist_ok=False)
        try:
            normalized = self._validate_and_sort(daily_bars)
            payload = "".join(
                canonical_json(bar.to_dict()) + "\n" for bar in normalized
            ).encode("utf-8")
            checksum = hashlib.sha256(payload).hexdigest()
            (temporary_dir / "bars.jsonl").write_bytes(payload)
            daily_watermarks = {
                bar.symbol: bar.timestamp
                for bar in sorted(normalized, key=lambda item: (item.symbol, item.timestamp))
            }
            session_dates = [bar.session_date for bar in normalized]
            assert all(item is not None for item in session_dates)
            resolved_dates = [item for item in session_dates if item is not None]
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source="DERIVED_FINALIZED_SESSION_V1",
                profile="KBAR_DAILY_V1",
                capabilities=("OHLCV", "KBAR_DAILY"),
                start_date=min(resolved_dates).isoformat(),
                end_date=max(resolved_dates).isoformat(),
                requested_symbols=base.requested_symbols,
                observed_symbols=tuple(sorted({bar.symbol for bar in normalized})),
                bar_count=len(normalized),
                bars_sha256=checksum,
                universe_scope=base.universe_scope,
                research_eligible=False,
                issues=all_issues,
                payload_order=_TIMESTAMP_SYMBOL_ORDER,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(daily_watermarks.items())
                ),
                universe_selection=base.universe_selection,
                cadence_summary={
                    "method": "DERIVED_FINALIZED_SESSION_V1",
                    "per_symbol": coverage,
                    "completion_proof_count": len(completion_proofs),
                },
                daily_bar_contract="DERIVED_FINALIZED_SESSION_V1",
                derivation=derivation,
                session_contract=dict(session_contract),
                price_adjustment_policy=price_adjustment_policy,
                corporate_action_adjusted=False,
                volume_contract=dict(volume_contract),
            )
            (temporary_dir / "manifest.json").write_text(
                canonical_json(manifest.to_dict()) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_dir, final_dir)
            return manifest
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

    def collect_from_provider(
        self,
        provider: MarketDataProvider,
        *,
        years: int,
        symbols: Iterable[str] | None = None,
        symbol_limit: int | None = None,
        progress: ProgressCallback | None = None,
        cancelled: Cancelled | None = None,
        end_date: date | None = None,
    ) -> DatasetManifest:
        """Fetch only historical Kbars through the existing provider port.

        Current provider contracts only expose the current contract list, so
        this collector labels its universe `CURRENT_SNAPSHOT` and marks the
        output not research eligible.  Imported date-effective universe data
        can create a research-eligible dataset through `create_imported_dataset`.
        """

        if years <= 0:
            raise ValueError("years 必須大於 0")
        if not provider.supports_kbars():
            raise ValueError("目前資料來源不支援歷史 Kbar")

        instruments = self.provider_instruments(
            provider,
            symbols=symbols,
            symbol_limit=symbol_limit,
        )

        end = end_date or datetime.now(_TAIPEI).date()
        start = end - timedelta(days=365 * years)
        collected: list[HistoricalBar] = []
        missing_symbols: list[str] = []
        for index, instrument in enumerate(instruments, start=1):
            self._raise_if_cancelled(cancelled)
            try:
                rows = self.fetch_provider_bars(
                    provider,
                    instrument=instrument,
                    start=start,
                    end=end,
                    cancelled=cancelled,
                )
            except (KeyError, ValueError) as error:
                missing_symbols.append(f"{instrument.symbol}: {error}")
                rows = []
            collected.extend(rows)
            if progress is not None:
                progress(
                    index / len(instruments),
                    f"已下載 {index}/{len(instruments)} 檔：{instrument.symbol}",
                )

        if not collected:
            raise ValueError("資料來源未回傳任何歷史 Kbar")
        issues = [
            "目前 Provider 僅能列出當前 contracts；資料集不含已下市股票，不能作 survivorship-free 正式證據。"
        ]
        issues.extend(missing_symbols)
        return self._seal(
            bars=self._validate_and_sort(collected),
            source=type(provider).__name__,
            requested_symbols=tuple(item.symbol for item in instruments),
            universe_scope="CURRENT_SNAPSHOT",
            research_eligible=False,
            issues=tuple(issues),
        )

    def provider_instruments(
        self,
        provider: MarketDataProvider,
        *,
        symbols: Iterable[str] | None = None,
        symbol_limit: int | None = None,
    ) -> tuple[HistoricalInstrument, ...]:
        stock_by_symbol = {
            stock.symbol: stock
            for stock in provider.get_market_stocks()
        }
        selected = sorted(
            {
                str(item).strip().upper()
                for item in (symbols or stock_by_symbol)
                if str(item).strip()
            }
        )
        if symbol_limit is not None:
            selected = selected[: max(0, symbol_limit)]
        if not selected:
            raise ValueError("沒有可下載的股票代碼")
        return tuple(
            HistoricalInstrument(
                symbol=symbol,
                name=stock_by_symbol[symbol].name if symbol in stock_by_symbol else symbol,
                market=(stock_by_symbol[symbol].market or "") if symbol in stock_by_symbol else "",
            )
            for symbol in selected
        )

    def fetch_provider_bars(
        self,
        provider: MarketDataProvider,
        *,
        instrument: HistoricalInstrument,
        start: date,
        end: date,
        cancelled: Cancelled | None = None,
    ) -> list[HistoricalBar]:
        rows = self._fetch_symbol(provider, instrument.symbol, start, end, cancelled)
        return self._validate_and_sort(
            HistoricalBar(
                symbol=instrument.symbol,
                name=instrument.name,
                market=instrument.market,
                timestamp=_taipei_timestamp(row.timestamp),
                open=decimal(row.open),
                high=decimal(row.high),
                low=decimal(row.low),
                close=decimal(row.close),
                volume=row.volume,
                amount=decimal(row.close) * row.volume,
                session_date=_taipei_session_date(row.timestamp),
            )
            for row in rows
        )

    def create_provider_dataset_from_partitions(
        self,
        *,
        dataset_id: str,
        partitions: Iterable[Iterable[HistoricalBar]],
        source: str,
        requested_symbols: tuple[str, ...],
        issues: tuple[str, ...],
        universe_selection: str = "ALL_CURRENT",
    ) -> DatasetManifest:
        """Stream database checkpoints into the existing immutable dataset."""

        final_dir = self._dataset_dir(dataset_id)
        if final_dir.is_dir():
            return self.get_manifest(dataset_id)
        temporary_dir = self._root / f".{dataset_id}.tmp"
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        temporary_dir.mkdir(parents=True, exist_ok=False)
        try:
            checksum = hashlib.sha256()
            bar_count = 0
            observed_symbols: set[str] = set()
            seen_partition_symbols: set[str] = set()
            symbol_last_timestamps: dict[str, datetime] = {}
            cadence = _CadenceEvidence()
            first_date: date | None = None
            last_date: date | None = None
            with (temporary_dir / "bars.jsonl").open("wb") as handle:
                for partition in partitions:
                    partition_symbol: str | None = None
                    previous_timestamp: datetime | None = None
                    for bar in partition:
                        if partition_symbol is None:
                            partition_symbol = bar.symbol
                            if partition_symbol in seen_partition_symbols:
                                raise ValueError(f"重複的股票分區：{partition_symbol}")
                            seen_partition_symbols.add(partition_symbol)
                        elif bar.symbol != partition_symbol:
                            raise ValueError("單一歷史資料分區不可混合多個股票代碼")
                        if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
                            raise ValueError(f"Kbar 分區順序或唯一性錯誤：{bar.symbol} {bar.timestamp.isoformat()}")
                        previous_timestamp = bar.timestamp
                        payload = (canonical_json(bar.to_dict()) + "\n").encode("utf-8")
                        handle.write(payload)
                        checksum.update(payload)
                        bar_count += 1
                        observed_symbols.add(bar.symbol)
                        symbol_last_timestamps[bar.symbol] = bar.timestamp
                        cadence.add(bar)
                        first_date = bar.timestamp.date() if first_date is None else min(first_date, bar.timestamp.date())
                        last_date = bar.timestamp.date() if last_date is None else max(last_date, bar.timestamp.date())
            if bar_count == 0 or first_date is None or last_date is None:
                raise ValueError("不可建立空的歷史資料集")
            profile, capabilities, cadence_summary = cadence.result()
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=profile,
                capabilities=capabilities,
                start_date=first_date.isoformat(),
                end_date=last_date.isoformat(),
                requested_symbols=requested_symbols,
                observed_symbols=tuple(sorted(observed_symbols)),
                bar_count=bar_count,
                bars_sha256=checksum.hexdigest(),
                universe_scope="CURRENT_SNAPSHOT",
                research_eligible=False,
                issues=issues,
                payload_order=_SYMBOL_TIMESTAMP_ORDER,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(symbol_last_timestamps.items())
                ),
                universe_selection=universe_selection,
                cadence_summary=cadence_summary,
            )
            (temporary_dir / "manifest.json").write_text(
                canonical_json(manifest.to_dict()) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_dir, final_dir)
            return manifest
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

    def create_finmind_snapshot_dataset(
        self,
        *,
        dataset_id: str,
        symbol_streams: Iterable[Iterable[HistoricalBar]],
        created_at: datetime,
        source: str,
        requested_symbols: tuple[str, ...],
        expected_bar_count: int,
        start_date: str,
        end_date: str,
        issues: tuple[str, ...],
        volume_contract: Mapping[str, Any],
        amount_contract: Mapping[str, Any],
        source_snapshot_digest: str,
        plan_identity: Mapping[str, Any],
        plan_identity_digest: str,
        required_free_bytes: int | None = None,
    ) -> DatasetManifest:
        """Seal a reviewed FinMind plan as a timestamp-major immutable Dataset."""

        expected_dataset_id = (
            "dataset-finmind-sponsor-sha256-" + source_snapshot_digest
        )
        if dataset_id != expected_dataset_id:
            raise ValueError("FinMind dataset ID does not match source snapshot digest")
        if len(source_snapshot_digest) != 64 or any(
            value not in "0123456789abcdef" for value in source_snapshot_digest
        ):
            raise ValueError("FinMind source snapshot digest must be lowercase SHA-256")
        observed_plan_digest = hashlib.sha256(
            canonical_json(plan_identity).encode("utf-8")
        ).hexdigest()
        if observed_plan_digest != plan_identity_digest:
            raise ValueError("FinMind plan identity digest mismatch")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("FinMind manifest created_at must include timezone")
        if expected_bar_count < 1:
            raise ValueError("不可建立空的 FinMind 歷史資料集")
        requested_symbol_set = set(requested_symbols)
        if (
            not requested_symbol_set
            or len(requested_symbol_set) != len(requested_symbols)
            or tuple(sorted(requested_symbol_set)) != requested_symbols
        ):
            raise ValueError("FinMind requested symbols must be unique and sorted")

        expected = {
            "dataset_id": dataset_id,
            "created_at": created_at,
            "source": source,
            "requested_symbols": tuple(requested_symbols),
            "expected_bar_count": expected_bar_count,
            "start_date": start_date,
            "end_date": end_date,
            "issues": tuple(issues),
            "volume_contract": dict(volume_contract),
            "amount_contract": dict(amount_contract),
            "source_snapshot_digest": source_snapshot_digest,
            "plan_identity": dict(plan_identity),
            "plan_identity_digest": plan_identity_digest,
        }
        streams = tuple(iter(stream) for stream in symbol_streams)
        final_dir = self._dataset_dir(dataset_id)
        if final_dir.exists():
            return self._verify_finmind_snapshot_dataset(
                expected,
                expected_bars=heapq.merge(*streams, key=self._event_key),
            )
        if required_free_bytes is not None:
            if required_free_bytes < 1:
                raise ValueError("FinMind disk preflight bytes must be positive")
            if shutil.disk_usage(self._root).free < required_free_bytes:
                raise ValueError("FinMind Dataset disk space is insufficient")

        temporary_dir = self._root / f".{dataset_id}.{uuid4().hex}.tmp"
        temporary_dir.mkdir(parents=True, exist_ok=False)
        try:
            checksum = hashlib.sha256()
            bar_count = 0
            observed_symbols: set[str] = set()
            symbol_last_timestamps: dict[str, datetime] = {}
            cadence = _BoundedCadenceEvidence()
            previous_key: tuple[datetime, str] | None = None
            with (temporary_dir / "bars.jsonl").open("xb") as handle:
                for bar in heapq.merge(*streams, key=self._event_key):
                    key = self._event_key(bar)
                    if previous_key is not None and key <= previous_key:
                        raise ValueError(
                            f"FinMind Kbar order or uniqueness conflict: {bar.symbol} "
                            f"{bar.timestamp.isoformat()}"
                        )
                    if bar.symbol not in requested_symbol_set:
                        raise ValueError(
                            f"FinMind Kbar symbol is outside the plan: {bar.symbol}"
                        )
                    if not bar.name.strip() or not bar.market.strip():
                        raise ValueError(
                            f"FinMind Kbar reference metadata is incomplete: {bar.symbol}"
                        )
                    payload = (canonical_json(bar.to_dict()) + "\n").encode("utf-8")
                    handle.write(payload)
                    checksum.update(payload)
                    previous_key = key
                    bar_count += 1
                    observed_symbols.add(bar.symbol)
                    symbol_last_timestamps[bar.symbol] = bar.timestamp
                    cadence.add(bar)
                handle.flush()
                os.fsync(handle.fileno())
            if bar_count != expected_bar_count:
                raise ValueError("FinMind Dataset bar count does not match the plan")
            if not observed_symbols.issubset(requested_symbol_set):
                raise ValueError("FinMind Dataset observed symbols do not match the plan")
            profile, capabilities, cadence_summary = cadence.result()
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=created_at,
                source=source,
                profile=profile,
                capabilities=capabilities,
                start_date=start_date,
                end_date=end_date,
                requested_symbols=requested_symbols,
                observed_symbols=tuple(sorted(observed_symbols)),
                bar_count=bar_count,
                bars_sha256=checksum.hexdigest(),
                universe_scope="CURRENT_SNAPSHOT",
                research_eligible=False,
                issues=issues,
                payload_order=_TIMESTAMP_SYMBOL_ORDER,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(symbol_last_timestamps.items())
                ),
                universe_selection="FINMIND_COMPLETE_SYMBOLS_V1",
                cadence_summary=cadence_summary,
                volume_contract=dict(volume_contract),
                amount_contract=dict(amount_contract),
                source_snapshot_digest=source_snapshot_digest,
                plan_identity=dict(plan_identity),
                plan_identity_digest=plan_identity_digest,
            )
            (temporary_dir / "manifest.json").write_text(
                canonical_json(manifest.to_dict()) + "\n",
                encoding="utf-8",
            )
            try:
                os.rename(temporary_dir, final_dir)
            except OSError:
                if not final_dir.is_dir():
                    raise
                shutil.rmtree(temporary_dir, ignore_errors=True)
                return self._verify_finmind_snapshot_dataset(
                    expected,
                    expected_bars_sha256=checksum.hexdigest(),
                )
            return manifest
        except BaseException:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

    def _verify_finmind_snapshot_dataset(
        self,
        expected: Mapping[str, Any],
        *,
        expected_bars: Iterable[HistoricalBar] | None = None,
        expected_bars_sha256: str | None = None,
    ) -> DatasetManifest:
        dataset_id = str(expected["dataset_id"])
        manifest_path = self._dataset_dir(dataset_id) / "manifest.json"
        try:
            raw_manifest_bytes = manifest_path.read_bytes()
            raw_manifest = json.loads(raw_manifest_bytes)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(
                f"FinMind Dataset {dataset_id} has an invalid manifest"
            ) from error
        if not isinstance(raw_manifest, Mapping):
            raise ValueError(f"FinMind Dataset {dataset_id} manifest must be an object")
        manifest = DatasetManifest.from_dict(raw_manifest)
        if raw_manifest.get("manifest_digest") != manifest.manifest_digest:
            raise ValueError(f"FinMind Dataset {dataset_id} manifest digest conflict")
        expected_manifest_bytes = (
            canonical_json(manifest.to_dict()) + "\n"
        ).encode("utf-8")
        if raw_manifest_bytes != expected_manifest_bytes:
            raise ValueError(
                f"FinMind Dataset {dataset_id} manifest schema or canonical bytes conflict"
            )
        immutable_checks = {
            "dataset_id": manifest.dataset_id,
            "created_at": manifest.created_at,
            "source": manifest.source,
            "requested_symbols": manifest.requested_symbols,
            "expected_bar_count": manifest.bar_count,
            "start_date": manifest.start_date,
            "end_date": manifest.end_date,
            "issues": manifest.issues,
            "volume_contract": manifest.volume_contract,
            "amount_contract": manifest.amount_contract,
            "source_snapshot_digest": manifest.source_snapshot_digest,
            "plan_identity": manifest.plan_identity,
            "plan_identity_digest": manifest.plan_identity_digest,
        }
        if immutable_checks != dict(expected):
            raise ValueError(f"FinMind Dataset {dataset_id} immutable identity conflict")
        if (
            manifest.storage_format != "JSONL_FULL_V1"
            or manifest.payload_order != _TIMESTAMP_SYMBOL_ORDER
            or manifest.universe_scope != "CURRENT_SNAPSHOT"
            or manifest.research_eligible
            or manifest.universe_selection != "FINMIND_COMPLETE_SYMBOLS_V1"
        ):
            raise ValueError(f"FinMind Dataset {dataset_id} storage contract conflict")

        cadence = _BoundedCadenceEvidence()
        observed_symbols: set[str] = set()
        watermarks: dict[str, datetime] = {}
        previous_key: tuple[datetime, str] | None = None
        expected_iterator = iter(expected_bars) if expected_bars is not None else None
        missing = object()
        count = 0
        for bar in self._iter_canonical_payload(
            dataset_id,
            "bars.jsonl",
            manifest.bars_sha256,
        ):
            if expected_iterator is not None:
                expected_bar = next(expected_iterator, missing)
                if expected_bar is missing or bar != expected_bar:
                    raise ValueError(
                        f"FinMind Dataset {dataset_id} payload/source conflict"
                    )
            key = self._event_key(bar)
            if previous_key is not None and key <= previous_key:
                raise ValueError(f"FinMind Dataset {dataset_id} order conflict")
            previous_key = key
            count += 1
            observed_symbols.add(bar.symbol)
            watermarks[bar.symbol] = bar.timestamp
            cadence.add(bar)
        if expected_iterator is not None and next(expected_iterator, missing) is not missing:
            raise ValueError(f"FinMind Dataset {dataset_id} payload/source conflict")
        profile, capabilities, cadence_summary = cadence.result()
        if (
            count != manifest.bar_count
            or (
                expected_bars_sha256 is not None
                and manifest.bars_sha256 != expected_bars_sha256
            )
            or tuple(sorted(observed_symbols)) != manifest.observed_symbols
            or tuple(
                (symbol, timestamp.isoformat())
                for symbol, timestamp in sorted(watermarks.items())
            )
            != manifest.symbol_last_timestamps
            or profile != manifest.profile
            or capabilities != manifest.capabilities
            or cadence_summary != manifest.cadence_summary
        ):
            raise ValueError(f"FinMind Dataset {dataset_id} payload evidence conflict")
        return manifest

    def create_incremental_dataset(
        self,
        *,
        dataset_id: str,
        base_dataset_id: str,
        partitions: Iterable[Iterable[HistoricalBar]],
        source: str,
        requested_symbols: tuple[str, ...],
        issues: tuple[str, ...],
    ) -> DatasetManifest:
        """Seal only bars newer than the immutable parent symbol watermarks."""

        final_dir = self._dataset_dir(dataset_id)
        if final_dir.is_dir():
            return self.get_manifest(dataset_id)
        base = self.get_manifest(base_dataset_id)
        watermarks = self.symbol_last_timestamps(base_dataset_id)
        temporary_dir = self._root / f".{dataset_id}.tmp"
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        temporary_dir.mkdir(parents=True, exist_ok=False)
        try:
            checksum = hashlib.sha256()
            delta_bar_count = 0
            delta_bars: list[HistoricalBar] = []
            observed_symbols = set(base.observed_symbols)
            seen_partition_symbols: set[str] = set()
            latest_date = date.fromisoformat(base.end_date)
            with (temporary_dir / "bars.delta.jsonl").open("wb") as handle:
                for partition in partitions:
                    partition_symbol: str | None = None
                    previous_timestamp: datetime | None = None
                    for bar in partition:
                        if partition_symbol is None:
                            partition_symbol = bar.symbol
                            if partition_symbol in seen_partition_symbols:
                                raise ValueError(f"重複的股票分區：{partition_symbol}")
                            seen_partition_symbols.add(partition_symbol)
                        elif bar.symbol != partition_symbol:
                            raise ValueError("單一歷史資料分區不可混合多個股票代碼")
                        if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
                            raise ValueError(
                                f"Kbar 分區順序或唯一性錯誤：{bar.symbol} {bar.timestamp.isoformat()}"
                            )
                        parent_watermark = watermarks.get(bar.symbol)
                        if parent_watermark is not None and bar.timestamp <= parent_watermark:
                            raise ValueError(
                                f"增量 Kbar 未通過 watermark：{bar.symbol} {bar.timestamp.isoformat()}"
                            )
                        previous_timestamp = bar.timestamp
                        payload = (canonical_json(bar.to_dict()) + "\n").encode("utf-8")
                        handle.write(payload)
                        checksum.update(payload)
                        delta_bar_count += 1
                        delta_bars.append(bar)
                        observed_symbols.add(bar.symbol)
                        watermarks[bar.symbol] = bar.timestamp
                        latest_date = max(latest_date, bar.timestamp.date())
            if delta_bar_count == 0:
                raise ValueError("不可建立空的增量歷史資料集")
            cadence = _CadenceEvidence()
            for bar in self.load_bars(base_dataset_id):
                cadence.add(bar)
            for bar in delta_bars:
                cadence.add(bar)
            profile, capabilities, cadence_summary = cadence.result()
            combined_issues = tuple(dict.fromkeys((*base.issues, *issues)))
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=profile,
                capabilities=capabilities,
                start_date=base.start_date,
                end_date=latest_date.isoformat(),
                requested_symbols=tuple(
                    sorted(set(base.requested_symbols) | set(requested_symbols))
                ),
                observed_symbols=tuple(sorted(observed_symbols)),
                bar_count=base.bar_count + delta_bar_count,
                bars_sha256=checksum.hexdigest(),
                universe_scope=base.universe_scope,
                research_eligible=base.research_eligible,
                issues=combined_issues,
                storage_format="JSONL_DELTA_V1",
                payload_order=_SYMBOL_TIMESTAMP_ORDER,
                parent_dataset_id=base_dataset_id,
                delta_bar_count=delta_bar_count,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(watermarks.items())
                ),
                universe_selection=base.universe_selection,
                cadence_summary=cadence_summary,
            )
            (temporary_dir / "manifest.json").write_text(
                canonical_json(manifest.to_dict()) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_dir, final_dir)
            return manifest
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

    def _fetch_symbol(
        self,
        provider: MarketDataProvider,
        symbol: str,
        start: date,
        end: date,
        cancelled: Cancelled | None,
    ) -> list[KBar]:
        bars_by_timestamp: dict[datetime, KBar] = {}
        cursor = start
        while cursor <= end:
            self._raise_if_cancelled(cancelled)
            window_end = min(cursor + timedelta(days=_MAX_PROVIDER_DAYS), end)
            for bar in provider.get_kbars(symbol, cursor, window_end):
                bars_by_timestamp[bar.timestamp] = bar
            cursor = window_end + timedelta(days=1)
        return [bars_by_timestamp[key] for key in sorted(bars_by_timestamp)]

    @staticmethod
    def _raise_if_cancelled(cancelled: Cancelled | None) -> None:
        if cancelled is not None and cancelled():
            raise DatasetCancelled("資料集工作已取消")

    @staticmethod
    def _validate_and_sort(bars: Iterable[HistoricalBar]) -> list[HistoricalBar]:
        by_identity: dict[tuple[str, datetime], HistoricalBar] = {}
        for bar in bars:
            key = (bar.symbol, bar.timestamp)
            existing = by_identity.get(key)
            if existing is not None and existing != bar:
                raise ValueError(f"重複且不一致的 Kbar：{bar.symbol} {bar.timestamp.isoformat()}")
            by_identity[key] = bar
        return [by_identity[key] for key in sorted(by_identity, key=lambda item: (item[1], item[0]))]

    def _seal(
        self,
        *,
        bars: list[HistoricalBar],
        source: str,
        requested_symbols: tuple[str, ...],
        universe_scope: str,
        research_eligible: bool,
        issues: tuple[str, ...],
        universe_selection: str = "ALL_CURRENT",
    ) -> DatasetManifest:
        dataset_id = f"dataset-{uuid4().hex}"
        final_dir = self._dataset_dir(dataset_id)
        temporary_dir = self._root / f".{dataset_id}.tmp"
        temporary_dir.mkdir(parents=True, exist_ok=False)
        try:
            payload = "".join(canonical_json(bar.to_dict()) + "\n" for bar in bars).encode("utf-8")
            checksum = hashlib.sha256(payload).hexdigest()
            (temporary_dir / "bars.jsonl").write_bytes(payload)
            cadence = _CadenceEvidence()
            symbol_last_timestamps: dict[str, datetime] = {}
            for bar in bars:
                cadence.add(bar)
                symbol_last_timestamps[bar.symbol] = max(
                    bar.timestamp,
                    symbol_last_timestamps.get(bar.symbol, bar.timestamp),
                )
            profile, capabilities, cadence_summary = cadence.result()
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=profile,
                capabilities=capabilities,
                start_date=bars[0].timestamp.date().isoformat(),
                end_date=bars[-1].timestamp.date().isoformat(),
                requested_symbols=requested_symbols,
                observed_symbols=tuple(sorted({bar.symbol for bar in bars})),
                bar_count=len(bars),
                bars_sha256=checksum,
                universe_scope=universe_scope,
                research_eligible=research_eligible,
                issues=issues,
                payload_order=_TIMESTAMP_SYMBOL_ORDER,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(symbol_last_timestamps.items())
                ),
                universe_selection=universe_selection,
                cadence_summary=cadence_summary,
            )
            (temporary_dir / "manifest.json").write_text(
                canonical_json(manifest.to_dict()) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_dir, final_dir)
            return manifest
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

    def _dataset_dir(self, dataset_id: str) -> Path:
        if not dataset_id.startswith("dataset-") or "/" in dataset_id or "\\" in dataset_id:
            raise ValueError("不合法的 dataset id")
        return self._root / dataset_id
