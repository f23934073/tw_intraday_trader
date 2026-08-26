"""Provider-free adapter for exact immutable full-Dataset source bars."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from backtest.dataset import HistoricalDatasetCatalog
from backtest.dataset_binding import canonical_registration_manifest
from backtest.domain import HistoricalBar, canonical_json

from .domain import ObservedBar, ResearchReplayIntegrityError


class CanonicalFullDatasetAdapter:
    """Stream exact canonical JSONL bytes in timestamp/symbol order."""

    def __init__(
        self,
        *,
        root: Path,
        registered_manifest: Mapping[str, Any],
        progress_every: int = 1_000_000,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if progress_every < 1:
            raise ValueError("progress_every 必須大於 0")
        self._root = Path(root)
        self._manifest = canonical_registration_manifest(registered_manifest)
        self._progress_every = progress_every
        self._progress = progress
        local = HistoricalDatasetCatalog(self._root).get_manifest(
            str(self._manifest["dataset_id"])
        )
        if canonical_registration_manifest(local.to_dict()) != self._manifest:
            raise ResearchReplayIntegrityError(
                "G3 local Dataset manifest 與 PostgreSQL registration 不一致"
            )
        if (
            self._manifest.get("storage_format") != "JSONL_FULL_V1"
            or self._manifest.get("payload_order") != "TIMESTAMP_SYMBOL"
        ):
            raise ResearchReplayIntegrityError(
                "G3 只接受 timestamp-major canonical full Dataset"
            )

    def iter_observed_bars(self) -> Iterator[ObservedBar]:
        dataset_id = str(self._manifest["dataset_id"])
        path = self._root / dataset_id / "bars.jsonl"
        if not path.is_file():
            raise ResearchReplayIntegrityError("G3 Dataset 缺少 bars.jsonl")
        expected_count = int(self._manifest["bar_count"])
        checksum = hashlib.sha256()
        count = 0
        previous: tuple[Any, str] | None = None
        with path.open("rb") as handle:
            for raw in handle:
                checksum.update(raw)
                if raw == b"\n" or not raw.endswith(b"\n"):
                    raise ResearchReplayIntegrityError(
                        "G3 Dataset JSONL 不可空白且每列必須有 LF"
                    )
                source = raw[:-1]
                try:
                    parsed = json.loads(source)
                    bar = HistoricalBar.from_dict(parsed)
                except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                    raise ResearchReplayIntegrityError(
                        "G3 Dataset bar 無法解析"
                    ) from error
                if source != canonical_json(bar.to_dict()).encode("utf-8"):
                    raise ResearchReplayIntegrityError(
                        "G3 Dataset bar bytes 不是 exact canonical HistoricalBar"
                    )
                key = (bar.timestamp, bar.symbol)
                if previous is not None and key <= previous:
                    raise ResearchReplayIntegrityError(
                        "G3 Dataset bars 必須依 timestamp/symbol unique 排序"
                    )
                previous = key
                count += 1
                if self._progress is not None and count % self._progress_every == 0:
                    self._progress(count, expected_count)
                yield ObservedBar.from_historical_bar(bar, source_json=source)
        if count != expected_count:
            raise ResearchReplayIntegrityError("G3 Dataset bar count 不一致")
        if checksum.hexdigest() != self._manifest["bars_sha256"]:
            raise ResearchReplayIntegrityError("G3 Dataset bars SHA-256 不一致")
        if self._progress is not None:
            self._progress(count, expected_count)
