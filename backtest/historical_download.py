"""Resumable, database-checkpointed historical Kbar acquisition."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Iterator, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from backtest.dataset import DatasetCancelled, HistoricalDatasetCatalog, HistoricalInstrument
from backtest.domain import HistoricalBar, canonical_json
from backtest.repository import BacktestRepository
from market_data.provider import (
    MarketDataLimitReached,
    MarketDataProvider,
    MarketDataTemporarilyUnavailable,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
ProgressReporter = Callable[[str], None]
_LEGACY_TRANSIENT_EMPTY = "資料來源未回傳 Kbar"
_RETRY_SYMBOL_PREFIX = "[RETRY_SYMBOL="
_CURRENT_SYMBOL_PREFIX = "[CURRENT_SYMBOL="


class HistoricalDownloadPaused(RuntimeError):
    """A recoverable Provider condition paused a durable history job."""


class ResumableHistoricalDownloader:
    """Persist one compressed symbol partition before fetching the next."""

    JOB_KIND = "DATASET_DOWNLOAD"

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        repository: BacktestRepository,
        catalog: HistoricalDatasetCatalog,
        report: ProgressReporter | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._catalog = catalog
        self._report = report or (lambda _message: None)

    def create_job(
        self,
        *,
        years: int,
        symbols: Iterable[str] | None = None,
        symbol_limit: int | None = None,
        end_date: date | None = None,
    ) -> dict[str, object]:
        if years <= 0:
            raise ValueError("years 必須大於 0")
        if not self._provider.supports_kbars():
            raise ValueError("目前資料來源不支援歷史 Kbar")
        instruments = self._catalog.provider_instruments(
            self._provider,
            symbols=symbols,
            symbol_limit=symbol_limit,
        )
        end = end_date or datetime.now(_TAIPEI).date()
        start = end - timedelta(days=365 * years)
        identity = uuid4().hex
        created_at = datetime.now(_TAIPEI).isoformat()
        return self._repository.create_job(
            {
                "job_id": f"dataset-download-{identity}",
                "kind": self.JOB_KIND,
                "status": "QUEUED",
                "request": {
                    "provider": type(self._provider).__name__,
                    "years": years,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "universe_selection": "EXPLICIT" if symbols is not None else "ALL_CURRENT",
                    "instruments": [instrument.to_dict() for instrument in instruments],
                    "target_dataset_id": f"dataset-{identity}",
                },
                "progress": 0.0,
                "progress_message": f"等待下載 {len(instruments)} 檔股票",
                "created_at": created_at,
            }
        )

    def run(self, job_id: str) -> dict[str, object]:
        job = self._repository.get_job(job_id)
        if job["kind"] != self.JOB_KIND:
            raise ValueError(f"{job_id} 不是可續傳的歷史下載工作")
        request = job["request"]
        expected_provider = str(request["provider"])
        current_provider = type(self._provider).__name__
        if current_provider != expected_provider:
            raise ValueError(
                f"下載工作使用 {expected_provider} 建立，不能改用 {current_provider} 接續"
            )
        if job["status"] == "COMPLETED" and job.get("resource_id"):
            return self._catalog.get_manifest(str(job["resource_id"])).to_dict()

        instruments = tuple(
            HistoricalInstrument.from_dict(value)
            for value in request["instruments"]
        )
        start = date.fromisoformat(str(request["start_date"]))
        end = date.fromisoformat(str(request["end_date"]))
        retry_symbol = _retry_symbol_from_job(job, instruments)
        completed, retry_from = _resume_state(
            instruments,
            self._repository.list_history_partitions(job_id),
            retry_symbol=retry_symbol,
        )
        resume_message = f"從資料庫接續；已完成 {len(completed)}/{len(instruments)} 檔"
        if retry_from is not None:
            resume_message += f"；從 {retry_from} 重新驗證可疑尾段"
        self._repository.update_job(
            job_id,
            status="RUNNING",
            progress=len(completed) / len(instruments),
            progress_message=resume_message,
            error_message=None,
        )
        self._report(resume_message)
        current_symbol: str | None = None
        try:
            for instrument in instruments:
                if instrument.symbol in completed:
                    continue
                current_symbol = instrument.symbol
                self._repository.update_job(
                    job_id,
                    status="RUNNING",
                    progress=len(completed) / len(instruments),
                    progress_message=(
                        f"{_CURRENT_SYMBOL_PREFIX}{current_symbol}] "
                        f"正在下載；已確認 {len(completed)}/{len(instruments)} 檔"
                    ),
                    error_message=None,
                )
                try:
                    bars = self._catalog.fetch_provider_bars(
                        self._provider,
                        instrument=instrument,
                        start=start,
                        end=end,
                    )
                    if not bars:
                        raise HistoricalDownloadPaused(
                            f"{instrument.symbol} 收到空 Kbar 回應；"
                            "為避免把 Provider 額度或暫停狀態誤存成完成，未保存此分區"
                        )
                    error_message = None
                except KeyError as error:
                    bars = []
                    error_message = str(error)
                self._repository.upsert_history_partition(
                    _encode_partition(
                        job_id=job_id,
                        instrument=instrument,
                        bars=bars,
                        error_message=error_message,
                    )
                )
                completed.add(instrument.symbol)
                message = (
                    f"已保存 {len(completed)}/{len(instruments)} 檔："
                    f"{instrument.symbol}（{len(bars):,} 根 Kbar）"
                )
                self._repository.update_job(
                    job_id,
                    status="RUNNING",
                    progress=len(completed) / len(instruments),
                    progress_message=message,
                    error_message=None,
                )
                self._report(message)
                current_symbol = None

            partitions = self._repository.list_history_partitions(job_id)
            bar_count = sum(int(item["bar_count"]) for item in partitions)
            if bar_count == 0:
                raise ValueError("資料來源未回傳任何歷史 Kbar")
            issues = (
                "目前 Provider 僅能列出當前 contracts；資料集不含已下市股票，不能作 survivorship-free 正式證據。",
                *(
                    f"{item['symbol']}: {item['error_message']}"
                    for item in partitions
                    if item.get("error_message")
                ),
            )
            manifest = self._catalog.create_provider_dataset_from_partitions(
                dataset_id=str(request["target_dataset_id"]),
                partitions=self._decoded_partitions(job_id),
                source=expected_provider,
                requested_symbols=tuple(item.symbol for item in instruments),
                issues=tuple(issues),
                universe_selection=str(request.get("universe_selection", "ALL_CURRENT")),
            )
            self._repository.upsert_dataset(manifest.to_dict(), "READY")
            self._repository.update_job(
                job_id,
                status="COMPLETED",
                resource_id=manifest.dataset_id,
                progress=1.0,
                progress_message=f"歷史資料集已封存：{manifest.dataset_id}",
                error_message=None,
            )
            self._report(
                f"完成：{manifest.dataset_id}，{manifest.bar_count:,} 根 Kbar，"
                f"{len(manifest.observed_symbols):,} 檔股票"
            )
            return manifest.to_dict()
        except KeyboardInterrupt:
            pending_symbol = _pending_symbol(instruments, completed, current_symbol)
            self._repository.update_job(
                job_id,
                status="PAUSED",
                progress=len(completed) / len(instruments),
                progress_message=f"已暫停；資料庫已保存 {len(completed)}/{len(instruments)} 檔",
                error_message=_retry_error(pending_symbol, "使用者中斷"),
            )
            raise
        except (
            HistoricalDownloadPaused,
            MarketDataLimitReached,
            MarketDataTemporarilyUnavailable,
        ) as error:
            message = str(error)
            pending_symbol = _pending_symbol(instruments, completed, current_symbol)
            self._repository.update_job(
                job_id,
                status="PAUSED",
                progress=len(completed) / len(instruments),
                progress_message=(
                    "已暫停：Provider 暫時不可用／額度／空回應保護；"
                    f"已確認 {len(completed)}/{len(instruments)} 檔"
                ),
                error_message=_retry_error(pending_symbol, message),
            )
            if isinstance(error, HistoricalDownloadPaused):
                raise
            raise HistoricalDownloadPaused(message) from error
        except Exception as error:
            pending_symbol = _pending_symbol(instruments, completed, current_symbol)
            self._repository.update_job(
                job_id,
                status="FAILED",
                progress=len(completed) / len(instruments),
                progress_message=f"下載失敗；可用同一 job id 接續（已保存 {len(completed)} 檔）",
                error_message=_retry_error(pending_symbol, str(error)),
            )
            raise

    def _decoded_partitions(self, job_id: str) -> Iterator[tuple[HistoricalBar, ...]]:
        for partition in self._repository.iter_history_partition_payloads(job_id):
            yield _decode_partition(partition)


class IncrementalHistoricalSync:
    """Create one resumable, immutable delta dataset for a market session."""

    JOB_KIND = "DATASET_INCREMENTAL"

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        repository: BacktestRepository,
        catalog: HistoricalDatasetCatalog,
        report: ProgressReporter | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._catalog = catalog
        self._report = report or (lambda _message: None)

    def create_job(
        self,
        *,
        base_dataset_id: str,
        session_date: date,
        overlap_days: int,
    ) -> tuple[dict[str, object], bool]:
        if overlap_days <= 0:
            raise ValueError("overlap_days 必須大於 0")
        if not self._provider.supports_kbars():
            raise ValueError("目前資料來源不支援歷史 Kbar")
        base = self._catalog.get_manifest(base_dataset_id)
        provider_name = type(self._provider).__name__
        if base.source != provider_name:
            raise ValueError(
                f"基礎資料集使用 {base.source}，不能用 {provider_name} 增量更新"
            )
        if base.universe_scope != "CURRENT_SNAPSHOT":
            raise ValueError("只有目前 Provider 建立的 CURRENT_SNAPSHOT 資料集可自動更新")

        requested_symbols: Iterable[str] | None = None
        if base.universe_selection == "EXPLICIT":
            requested_symbols = base.requested_symbols
        instruments = self._catalog.provider_instruments(
            self._provider,
            symbols=requested_symbols,
        )
        watermarks = self._catalog.symbol_last_timestamps(base_dataset_id)
        base_start = date.fromisoformat(base.start_date)
        starts: dict[str, str] = {}
        selected_watermarks: dict[str, str] = {}
        for instrument in instruments:
            watermark = watermarks.get(instrument.symbol)
            if watermark is None:
                start = base_start
            else:
                start = max(
                    base_start,
                    watermark.date() - timedelta(days=overlap_days - 1),
                )
                selected_watermarks[instrument.symbol] = watermark.isoformat()
            starts[instrument.symbol] = min(start, session_date).isoformat()

        session_key = session_date.strftime("%Y%m%d")
        job_id = f"dataset-incremental-{session_key}"
        created_at = datetime.now(_TAIPEI).isoformat()
        return self._repository.create_job_once(
            {
                "job_id": job_id,
                "kind": self.JOB_KIND,
                "status": "QUEUED",
                "request": {
                    "provider": provider_name,
                    "session_date": session_date.isoformat(),
                    "overlap_days": overlap_days,
                    "base_dataset_id": base_dataset_id,
                    "base_manifest_digest": base.manifest_digest,
                    "target_dataset_id": (
                        f"dataset-incremental-{session_key}-{base.manifest_digest[:12]}"
                    ),
                    "instruments": [instrument.to_dict() for instrument in instruments],
                    "start_dates": starts,
                    "watermarks": selected_watermarks,
                },
                "progress": 0.0,
                "progress_message": f"等待增量同步 {len(instruments)} 檔股票",
                "created_at": created_at,
            }
        )

    def run(self, job_id: str) -> dict[str, object]:
        job = self._repository.get_job(job_id)
        if job["kind"] != self.JOB_KIND:
            raise ValueError(f"{job_id} 不是歷史增量同步工作")
        request = job["request"]
        expected_provider = str(request["provider"])
        if type(self._provider).__name__ != expected_provider:
            raise ValueError(
                f"增量工作使用 {expected_provider} 建立，不能改用 "
                f"{type(self._provider).__name__} 接續"
            )
        if job["status"] == "COMPLETED" and job.get("resource_id"):
            return self._catalog.get_manifest(str(job["resource_id"])).to_dict()

        base_dataset_id = str(request["base_dataset_id"])
        base = self._catalog.get_manifest(base_dataset_id)
        if job["status"] == "CANCELLING":
            self._repository.update_job(
                job_id,
                status="PAUSED",
                progress_message="服務關閉，增量同步已暫停",
                error_message=None,
            )
            return base.to_dict()
        if base.manifest_digest != request["base_manifest_digest"]:
            raise ValueError("基礎資料集 manifest 已改變，拒絕接續增量同步")
        session_date = date.fromisoformat(str(request["session_date"]))
        instruments = tuple(
            HistoricalInstrument.from_dict(value)
            for value in request["instruments"]
        )
        start_dates = {
            str(symbol): date.fromisoformat(str(value))
            for symbol, value in dict(request["start_dates"]).items()
        }
        watermarks = {
            str(symbol): datetime.fromisoformat(str(value))
            for symbol, value in dict(request.get("watermarks", {})).items()
        }
        completed = {
            str(partition["symbol"])
            for partition in self._repository.list_history_partitions(job_id)
        }
        self._repository.update_job(
            job_id,
            status="RUNNING",
            progress=len(completed) / len(instruments),
            progress_message=(
                f"從資料庫接續增量同步；已完成 {len(completed)}/{len(instruments)} 檔"
            ),
            error_message=None,
        )
        try:
            for instrument in instruments:
                if instrument.symbol in completed:
                    continue
                try:
                    bars = self._catalog.fetch_provider_bars(
                        self._provider,
                        instrument=instrument,
                        start=start_dates[instrument.symbol],
                        end=session_date,
                        cancelled=lambda: self._repository.get_job(job_id)["status"]
                        == "CANCELLING",
                    )
                    watermark = watermarks.get(instrument.symbol)
                    if watermark is not None:
                        bars = [bar for bar in bars if bar.timestamp > watermark]
                    error_message = None if bars else "沒有新 Kbar"
                except KeyError as error:
                    bars = []
                    error_message = str(error)
                self._repository.upsert_history_partition(
                    _encode_partition(
                        job_id=job_id,
                        instrument=instrument,
                        bars=bars,
                        error_message=error_message,
                    )
                )
                completed.add(instrument.symbol)
                message = (
                    f"已保存增量 {len(completed)}/{len(instruments)} 檔："
                    f"{instrument.symbol}（{len(bars):,} 根新 Kbar）"
                )
                self._repository.update_job(
                    job_id,
                    status="RUNNING",
                    progress=len(completed) / len(instruments),
                    progress_message=message,
                )
                self._report(message)

            partitions = self._repository.list_history_partitions(job_id)
            delta_bar_count = sum(int(item["bar_count"]) for item in partitions)
            if delta_bar_count == 0:
                self._repository.update_job(
                    job_id,
                    status="COMPLETED",
                    resource_id=base_dataset_id,
                    progress=1.0,
                    progress_message="同步完成：沒有新 Kbar，沿用目前資料集",
                    error_message=None,
                )
                return base.to_dict()

            issues = tuple(
                f"{item['symbol']}: {item['error_message']}"
                for item in partitions
                if item.get("error_message") and item["error_message"] != "沒有新 Kbar"
            )
            manifest = self._catalog.create_incremental_dataset(
                dataset_id=str(request["target_dataset_id"]),
                base_dataset_id=base_dataset_id,
                partitions=self._decoded_partitions(job_id),
                source=expected_provider,
                requested_symbols=tuple(item.symbol for item in instruments),
                issues=issues,
            )
            self._repository.upsert_dataset(manifest.to_dict(), "READY")
            self._repository.update_job(
                job_id,
                status="COMPLETED",
                resource_id=manifest.dataset_id,
                progress=1.0,
                progress_message=(
                    f"增量資料集已封存：{manifest.dataset_id}（新增 {delta_bar_count:,} 根）"
                ),
                error_message=None,
            )
            return manifest.to_dict()
        except DatasetCancelled:
            self._repository.update_job(
                job_id,
                status="PAUSED",
                progress=len(completed) / len(instruments),
                progress_message=f"服務關閉，已保存 {len(completed)}/{len(instruments)} 檔增量",
                error_message=None,
            )
            raise
        except (MarketDataLimitReached, MarketDataTemporarilyUnavailable) as error:
            message = str(error)
            self._repository.update_job(
                job_id,
                status="PAUSED",
                progress=len(completed) / len(instruments),
                progress_message=(
                    "Provider 暫時不可用或額度不足，增量同步已暫停；"
                    f"已保存 {len(completed)}/{len(instruments)} 檔"
                ),
                error_message=message,
            )
            raise HistoricalDownloadPaused(message) from error
        except Exception as error:
            self._repository.update_job(
                job_id,
                status="FAILED",
                progress=len(completed) / len(instruments),
                progress_message=(
                    f"增量同步失敗；下次排程可接續（已保存 {len(completed)} 檔）"
                ),
                error_message=str(error),
            )
            raise

    def _decoded_partitions(self, job_id: str) -> Iterator[tuple[HistoricalBar, ...]]:
        for partition in self._repository.iter_history_partition_payloads(job_id):
            yield _decode_partition(partition)


def _encode_partition(
    *,
    job_id: str,
    instrument: HistoricalInstrument,
    bars: Iterable[HistoricalBar],
    error_message: str | None,
) -> dict[str, object]:
    normalized = tuple(bars)
    raw = "".join(canonical_json(bar.to_dict()) + "\n" for bar in normalized).encode("utf-8")
    now = datetime.now(_TAIPEI).isoformat()
    return {
        "job_id": job_id,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "market": instrument.market,
        "start_date": normalized[0].timestamp.date().isoformat() if normalized else None,
        "end_date": normalized[-1].timestamp.date().isoformat() if normalized else None,
        "bar_count": len(normalized),
        "bars_sha256": hashlib.sha256(raw).hexdigest(),
        "bars_payload": gzip.compress(raw, compresslevel=6, mtime=0),
        "error_message": error_message,
        "created_at": now,
    }


def _resume_state(
    instruments: tuple[HistoricalInstrument, ...],
    partitions: Iterable[Mapping[str, object]],
    *,
    retry_symbol: str | None = None,
) -> tuple[set[str], str | None]:
    """Keep valid checkpoints, retry one interrupted symbol, and repair an empty tail."""

    by_symbol = {str(item["symbol"]): item for item in partitions}
    empty_index: int | None = None
    for index, instrument in enumerate(instruments):
        partition = by_symbol.get(instrument.symbol)
        if (
            partition is not None
            and int(partition["bar_count"]) == 0
            and partition.get("error_message") == _LEGACY_TRANSIENT_EMPTY
        ):
            empty_index = index
            break

    completed = {
        instrument.symbol
        for instrument in instruments
        if instrument.symbol in by_symbol
    }
    if empty_index is not None:
        for instrument in instruments[empty_index:]:
            completed.discard(instrument.symbol)
    if retry_symbol is not None:
        completed.discard(retry_symbol)

    retry_from = next(
        (
            instrument.symbol
            for instrument in instruments
            if instrument.symbol not in completed
        ),
        None,
    )
    return completed, retry_from


def _retry_symbol_from_job(
    job: Mapping[str, object],
    instruments: tuple[HistoricalInstrument, ...],
) -> str | None:
    """Read the durable retry marker, with a narrow fallback for old clients."""

    known_symbols = {instrument.symbol for instrument in instruments}
    for value, prefix in (
        (job.get("error_message"), _RETRY_SYMBOL_PREFIX),
        (job.get("progress_message"), _CURRENT_SYMBOL_PREFIX),
    ):
        text = str(value or "")
        start = text.find(prefix)
        if start < 0:
            continue
        symbol_start = start + len(prefix)
        symbol_end = text.find("]", symbol_start)
        symbol = text[symbol_start:symbol_end] if symbol_end >= 0 else ""
        if symbol in known_symbols:
            return symbol

    # Jobs started by the previous downloader did not persist their current
    # symbol. Their progress was a contiguous prefix, so the next index is the
    # safest one-time recovery point after FAILED/PAUSED.
    status = str(job.get("status") or "")
    progress_message = str(job.get("progress_message") or "")
    legacy_interruption = status == "FAILED" or (
        status == "PAUSED"
        and (
            progress_message.startswith("已暫停；資料庫已保存")
            or progress_message.startswith("已暫停：Provider 額度／空回應保護")
        )
    )
    if legacy_interruption and instruments:
        completed_count = round(float(job.get("progress") or 0.0) * len(instruments))
        if 0 <= completed_count < len(instruments):
            return instruments[completed_count].symbol
    return None


def _pending_symbol(
    instruments: tuple[HistoricalInstrument, ...],
    completed: set[str],
    current_symbol: str | None,
) -> str | None:
    if current_symbol is not None:
        return current_symbol
    return next(
        (
            instrument.symbol
            for instrument in instruments
            if instrument.symbol not in completed
        ),
        None,
    )


def _retry_error(symbol: str | None, message: str) -> str | None:
    if symbol is None:
        return message or None
    return f"{_RETRY_SYMBOL_PREFIX}{symbol}] {message}".strip()


def _decode_partition(partition: Mapping[str, object]) -> tuple[HistoricalBar, ...]:
    raw = gzip.decompress(bytes(partition["bars_payload"]))
    if hashlib.sha256(raw).hexdigest() != partition["bars_sha256"]:
        raise ValueError(f"{partition['symbol']} 歷史分區 checksum 不符")
    bars = tuple(
        HistoricalBar.from_dict(json.loads(line))
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    )
    if len(bars) != int(partition["bar_count"]):
        raise ValueError(f"{partition['symbol']} 歷史分區 bar count 不符")
    if any(bar.symbol != partition["symbol"] for bar in bars):
        raise ValueError(f"{partition['symbol']} 歷史分區含有其他股票代碼")
    return bars
