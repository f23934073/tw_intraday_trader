"""Build a bounded exploratory dataset from durable history checkpoints only."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog
from backtest.domain import HistoricalBar, canonical_json
from backtest.repository import BacktestRepository


PILOT_END_CEILING = date(2024, 12, 31)
_ENDPOINT_GRACE = timedelta(days=7)
_BUILDER_VERSION = "exploratory-partial-job-partitions-v1"


@dataclass(frozen=True)
class ExploratoryPilotPlan:
    job_id: str
    start_date: date
    end_date: date
    dataset_id: str
    eligible_symbols: tuple[str, ...]
    selected_symbols: tuple[str, ...]
    rejected_counts: Mapping[str, int]
    selection_method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "dataset_id": self.dataset_id,
            "eligible_symbol_count": len(self.eligible_symbols),
            "selected_symbols": list(self.selected_symbols),
            "selected_symbol_count": len(self.selected_symbols),
            "rejected_counts": dict(self.rejected_counts),
            "selection_method": self.selection_method,
            "research_eligible": False,
            "formal_validation_allowed": False,
            "formal_holdout_allowed": False,
        }


class ExploratoryPilotBuilder:
    """Seal a new dataset without changing the incomplete source job."""

    def __init__(
        self,
        *,
        repository: BacktestRepository,
        catalog: HistoricalDatasetCatalog,
    ) -> None:
        self._repository = repository
        self._catalog = catalog

    def plan(
        self,
        *,
        job_id: str,
        start_date: date,
        end_date: date,
        symbol_limit: int,
        symbols: Iterable[str] | None = None,
    ) -> ExploratoryPilotPlan:
        if start_date > end_date:
            raise ValueError("pilot start_date 不可晚於 end_date")
        if end_date > PILOT_END_CEILING:
            raise ValueError(
                f"探索性 pilot 不可讀取 {PILOT_END_CEILING.isoformat()} 之後的資料"
            )
        if symbol_limit <= 0:
            raise ValueError("symbol_limit 必須大於 0")

        job = self._repository.get_job(job_id)
        if job["kind"] != "DATASET_DOWNLOAD":
            raise ValueError(f"{job_id} 不是歷史下載工作")
        request = job["request"]
        requested_start = date.fromisoformat(str(request["start_date"]))
        requested_end = date.fromisoformat(str(request["end_date"]))
        if start_date < requested_start or end_date > requested_end:
            raise ValueError("pilot 日期超出來源工作的固定下載範圍")

        order = {
            str(item["symbol"]): index
            for index, item in enumerate(request["instruments"])
        }
        partitions = self._repository.list_history_partitions(job_id)
        eligible: list[Mapping[str, Any]] = []
        rejected = {"empty": 0, "provider_error": 0, "endpoint_coverage": 0}
        for partition in partitions:
            if partition.get("error_message"):
                rejected["provider_error"] += 1
                continue
            if int(partition["bar_count"]) <= 0:
                rejected["empty"] += 1
                continue
            first = _optional_date(partition.get("start_date"))
            last = _optional_date(partition.get("end_date"))
            if (
                first is None
                or last is None
                or first > start_date + _ENDPOINT_GRACE
                or last < end_date - _ENDPOINT_GRACE
            ):
                rejected["endpoint_coverage"] += 1
                continue
            eligible.append(partition)

        eligible.sort(key=lambda item: order.get(str(item["symbol"]), len(order)))
        eligible_symbols = tuple(str(item["symbol"]) for item in eligible)
        if not eligible_symbols:
            raise ValueError("目前沒有通過 pilot 端點涵蓋檢查的非空分區")

        if symbols is not None:
            requested = tuple(
                dict.fromkeys(str(item).strip().upper() for item in symbols)
            )
            missing = tuple(symbol for symbol in requested if symbol not in eligible_symbols)
            if missing:
                raise ValueError("指定股票尚未通過 pilot 涵蓋檢查：" + ", ".join(missing))
            selected = tuple(symbol for symbol in eligible_symbols if symbol in requested)
            if len(selected) > symbol_limit:
                raise ValueError("指定股票數超過 symbol_limit")
            selection_method = "EXPLICIT_ELIGIBLE_SYMBOLS_V1"
        else:
            selected = _evenly_spaced(
                eligible_symbols,
                min(symbol_limit, len(eligible_symbols)),
            )
            selection_method = "EVENLY_SPACED_JOB_ORDER_V1"
        if not selected:
            raise ValueError("pilot 至少需要一檔股票")

        partition_by_symbol = {str(item["symbol"]): item for item in eligible}
        identity = {
            "builder_version": _BUILDER_VERSION,
            "job_id": job_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "selection_method": selection_method,
            "partitions": [
                {
                    "symbol": symbol,
                    "bars_sha256": partition_by_symbol[symbol]["bars_sha256"],
                }
                for symbol in selected
            ],
        }
        digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
        return ExploratoryPilotPlan(
            job_id=job_id,
            start_date=start_date,
            end_date=end_date,
            dataset_id=f"dataset-exploratory-{digest[:20]}",
            eligible_symbols=eligible_symbols,
            selected_symbols=selected,
            rejected_counts=rejected,
            selection_method=selection_method,
        )

    def materialize(self, plan: ExploratoryPilotPlan) -> DatasetManifest:
        job = self._repository.get_job(plan.job_id)
        issues = (
            "EXPLORATORY_PARTIAL_UNIVERSE",
            "FORMAL_RESEARCH_INELIGIBLE",
            "FORMAL_VALIDATION_PROHIBITED",
            "FORMAL_HOLDOUT_PROHIBITED",
            "SURVIVORSHIP_BIASED_CURRENT_CONTRACTS",
            "COVERAGE_ENDPOINT_HEURISTIC_ONLY",
            f"SOURCE_JOB_ID={plan.job_id}",
            f"SOURCE_JOB_STATUS={job['status']}",
            f"PILOT_SELECTION={plan.selection_method}",
        )
        manifest = self._catalog.create_provider_dataset_from_partitions(
            dataset_id=plan.dataset_id,
            partitions=self._clipped_partitions(plan),
            source=f"{job['request']['provider']}:EXPLORATORY_PARTIAL_V1",
            requested_symbols=plan.selected_symbols,
            issues=issues,
            universe_selection="EXPLORATORY_PARTIAL_JOB_PARTITIONS_V1",
        )
        if (
            manifest.research_eligible
            or manifest.start_date < plan.start_date.isoformat()
            or manifest.end_date > plan.end_date.isoformat()
            or manifest.requested_symbols != plan.selected_symbols
            or not {"FORMAL_VALIDATION_PROHIBITED", "FORMAL_HOLDOUT_PROHIBITED"}.issubset(
                manifest.issues
            )
        ):
            raise ValueError("既有 pilot dataset 與探索性安全契約不相容")
        self._repository.upsert_dataset(manifest.to_dict(), "READY")
        return manifest

    def _clipped_partitions(
        self,
        plan: ExploratoryPilotPlan,
    ) -> Iterable[tuple[HistoricalBar, ...]]:
        selected = set(plan.selected_symbols)
        found: set[str] = set()
        for partition in self._repository.iter_history_partition_payloads(plan.job_id):
            symbol = str(partition["symbol"])
            if symbol not in selected:
                continue
            raw = gzip.decompress(bytes(partition["bars_payload"]))
            if hashlib.sha256(raw).hexdigest() != partition["bars_sha256"]:
                raise ValueError(f"{symbol} 歷史分區 checksum 不符")
            bars = tuple(
                bar
                for bar in (
                    HistoricalBar.from_dict(json.loads(line))
                    for line in raw.decode("utf-8").splitlines()
                    if line
                )
                if plan.start_date
                <= (bar.session_date or bar.timestamp.date())
                <= plan.end_date
            )
            if not bars:
                raise ValueError(f"{symbol} 在 pilot 日期內沒有 Kbar")
            first = bars[0].session_date or bars[0].timestamp.date()
            last = bars[-1].session_date or bars[-1].timestamp.date()
            if (
                first > plan.start_date + _ENDPOINT_GRACE
                or last < plan.end_date - _ENDPOINT_GRACE
            ):
                raise ValueError(f"{symbol} payload 未通過 pilot 端點涵蓋檢查")
            found.add(symbol)
            yield bars
        missing = selected - found
        if missing:
            raise ValueError("找不到已選分區 payload：" + ", ".join(sorted(missing)))


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def _evenly_spaced(items: tuple[str, ...], count: int) -> tuple[str, ...]:
    if count >= len(items):
        return items
    if count == 1:
        return (items[len(items) // 2],)
    positions = tuple(
        round(index * (len(items) - 1) / (count - 1))
        for index in range(count)
    )
    return tuple(items[position] for position in positions)
