"""Immutable historical-bar datasets and server-side provider acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from backtest.domain import HistoricalBar, canonical_json, decimal
from market_data.models import KBar
from market_data.provider import MarketDataProvider


_TAIPEI = ZoneInfo("Asia/Taipei")
_MAX_PROVIDER_DAYS = 29
ProgressCallback = Callable[[float, str], None]
Cancelled = Callable[[], bool]


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
    parent_dataset_id: str | None = None
    delta_bar_count: int = 0
    symbol_last_timestamps: tuple[tuple[str, str], ...] = ()
    universe_selection: str = "ALL_CURRENT"

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
            bars = self._load_payload(dataset_id, "bars.jsonl", manifest.bars_sha256)
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
                timestamp=row.timestamp,
                open=decimal(row.open),
                high=decimal(row.high),
                low=decimal(row.low),
                close=decimal(row.close),
                volume=row.volume,
                amount=decimal(row.close) * row.volume,
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
            current_session: tuple[str, date] | None = None
            current_session_observations = 0
            max_session_observations = 0
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
                        session = (bar.symbol, bar.timestamp.date())
                        if session == current_session:
                            current_session_observations += 1
                        else:
                            max_session_observations = max(
                                max_session_observations,
                                current_session_observations,
                            )
                            current_session = session
                            current_session_observations = 1
                        first_date = bar.timestamp.date() if first_date is None else min(first_date, bar.timestamp.date())
                        last_date = bar.timestamp.date() if last_date is None else max(last_date, bar.timestamp.date())
            if bar_count == 0 or first_date is None or last_date is None:
                raise ValueError("不可建立空的歷史資料集")
            max_session_observations = max(max_session_observations, current_session_observations)
            profile = "KBAR_1M_V1" if max_session_observations > 20 else "KBAR_DAILY_TEST_V1"
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=profile,
                capabilities=("OHLCV",),
                start_date=first_date.isoformat(),
                end_date=last_date.isoformat(),
                requested_symbols=requested_symbols,
                observed_symbols=tuple(sorted(observed_symbols)),
                bar_count=bar_count,
                bars_sha256=checksum.hexdigest(),
                universe_scope="CURRENT_SNAPSHOT",
                research_eligible=False,
                issues=issues,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(symbol_last_timestamps.items())
                ),
                universe_selection=universe_selection,
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
                        observed_symbols.add(bar.symbol)
                        watermarks[bar.symbol] = bar.timestamp
                        latest_date = max(latest_date, bar.timestamp.date())
            if delta_bar_count == 0:
                raise ValueError("不可建立空的增量歷史資料集")
            combined_issues = tuple(dict.fromkeys((*base.issues, *issues)))
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=base.profile,
                capabilities=base.capabilities,
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
                parent_dataset_id=base_dataset_id,
                delta_bar_count=delta_bar_count,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(watermarks.items())
                ),
                universe_selection=base.universe_selection,
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
            observations_per_date: dict[date, int] = {}
            symbol_last_timestamps: dict[str, datetime] = {}
            for bar in bars:
                observations_per_date[bar.timestamp.date()] = observations_per_date.get(bar.timestamp.date(), 0) + 1
                symbol_last_timestamps[bar.symbol] = max(
                    bar.timestamp,
                    symbol_last_timestamps.get(bar.symbol, bar.timestamp),
                )
            profile = "KBAR_1M_V1" if max(observations_per_date.values()) > 20 else "KBAR_DAILY_TEST_V1"
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                created_at=datetime.now(_TAIPEI),
                source=source,
                profile=profile,
                capabilities=("OHLCV",),
                start_date=bars[0].timestamp.date().isoformat(),
                end_date=bars[-1].timestamp.date().isoformat(),
                requested_symbols=requested_symbols,
                observed_symbols=tuple(sorted({bar.symbol for bar in bars})),
                bar_count=len(bars),
                bars_sha256=checksum,
                universe_scope=universe_scope,
                research_eligible=research_eligible,
                issues=issues,
                symbol_last_timestamps=tuple(
                    (symbol, timestamp.isoformat())
                    for symbol, timestamp in sorted(symbol_last_timestamps.items())
                ),
                universe_selection=universe_selection,
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
