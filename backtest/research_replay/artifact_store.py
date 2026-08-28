"""Canonical filesystem adapter for R5 revision-2 replay artifacts."""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from backtest.domain import canonical_json, digest

from .domain import (
    ResearchReplayIntegrityError,
    canonical_object_bytes,
    require_sha256,
    verify_episode_row,
    verify_ledger_manifest,
    verify_ledger_row,
    verify_match_manifest,
    verify_match_row,
    verify_modeled_entry_row,
    verify_modeled_exit_row,
    verify_order_row,
    verify_result_manifest,
    verify_replay_consistency,
)


Verifier = Callable[[Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class LedgerArtifact:
    manifest: dict[str, Any]
    ledger_rows: tuple[dict[str, Any], ...]
    order_rows: tuple[dict[str, Any], ...]
    path: Path


@dataclass(frozen=True)
class MatchPlanArtifact:
    manifest: dict[str, Any]
    rows: tuple[dict[str, Any], ...]
    path: Path


@dataclass(frozen=True)
class ResultArtifact:
    manifest: dict[str, Any]
    episodes: tuple[dict[str, Any], ...]
    modeled_entries: tuple[dict[str, Any], ...]
    modeled_exits: tuple[dict[str, Any], ...]
    path: Path


@dataclass(frozen=True)
class _PayloadEvidence:
    count: int
    sha256: str
    parity_digest: str
    semantic_multiplicity_digest: str
    primary_duplicate_count: int


class ReplayArtifactStore:
    """Publish exact artifact directories without putting paths in identity."""

    def __init__(
        self, root: Path, *, chunk_size: int = 1024, merge_fan_in: int = 64
    ) -> None:
        self._root = Path(root)
        if chunk_size < 1:
            raise ValueError("chunk_size 必須大於 0")
        if merge_fan_in < 2:
            raise ValueError("merge_fan_in 必須至少為 2")
        self._chunk_size = chunk_size
        self._merge_fan_in = merge_fan_in

    def publish_ledger(
        self,
        *,
        manifest: Mapping[str, object],
        ledger_rows: Iterable[Mapping[str, object]],
        order_rows: Iterable[Mapping[str, object]],
    ) -> Path:
        verified = verify_ledger_manifest(manifest)
        final = self._path("ledgers", verified["ledger_manifest_digest"])
        if final.exists():
            loaded = self.load_ledger(verified["ledger_manifest_digest"])
            if loaded.manifest != verified:
                raise ResearchReplayIntegrityError("existing ledger manifest conflict")
            return final
        temporary = self._temporary("ledgers", verified["ledger_manifest_digest"])
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            ledger_evidence = self._write_rows(
                temporary, "ledger.jsonl", ledger_rows, verify_ledger_row, "signal_id"
            )
            order_evidence = self._write_rows(
                temporary, "order_derivation.jsonl", order_rows, verify_order_row, "baseline_order_id"
            )
            if ledger_evidence.count != verified["ledger_signal_count"]:
                raise ResearchReplayIntegrityError("ledger artifact count conflict")
            if ledger_evidence.sha256 != verified["ledger_rows_sha256"]:
                raise ResearchReplayIntegrityError("ledger artifact SHA conflict")
            if (
                ledger_evidence.semantic_multiplicity_digest
                != verified["ledger_semantic_multiplicity_digest"]
            ):
                raise ResearchReplayIntegrityError("ledger semantic digest conflict")
            if order_evidence.count != verified["v2_inception_order_derivation_count"]:
                raise ResearchReplayIntegrityError("order derivation count conflict")
            if order_evidence.sha256 != verified["v2_inception_order_derivation_rows_sha256"]:
                raise ResearchReplayIntegrityError("order derivation SHA conflict")
            projection = {
                "row_count": order_evidence.count,
                "rows_sha256": order_evidence.sha256,
                "schema_version": "r5-order-derivation-projection-v2",
            }
            if digest(projection) != verified["v2_inception_order_derivation_digest"]:
                raise ResearchReplayIntegrityError("order derivation projection conflict")
            if ledger_evidence.parity_digest != order_evidence.parity_digest:
                raise ResearchReplayIntegrityError("ledger/order layer parity conflict")
            self._write_manifest(temporary, verified)
            self._publish_directory(temporary, final)
            return self.load_ledger(verified["ledger_manifest_digest"]).path
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def load_ledger(self, manifest_digest: str) -> LedgerArtifact:
        path = self._path("ledgers", require_sha256(manifest_digest, "ledger manifest digest"))
        self._require_files(path, {"ledger.jsonl", "order_derivation.jsonl", "manifest.json"})
        manifest = self._load_manifest(path, verify_ledger_manifest)
        if manifest["ledger_manifest_digest"] != manifest_digest:
            raise ResearchReplayIntegrityError("ledger locator/digest conflict")
        ledger_rows, ledger_evidence = self._read_rows(
            path / "ledger.jsonl", verify_ledger_row, "signal_id"
        )
        order_rows, order_evidence = self._read_rows(
            path / "order_derivation.jsonl", verify_order_row, "baseline_order_id"
        )
        if (
            ledger_evidence.count != manifest["ledger_signal_count"]
            or ledger_evidence.sha256 != manifest["ledger_rows_sha256"]
            or ledger_evidence.semantic_multiplicity_digest
            != manifest["ledger_semantic_multiplicity_digest"]
        ):
            raise ResearchReplayIntegrityError("ledger payload/manifest conflict")
        projection = {
            "row_count": order_evidence.count,
            "rows_sha256": order_evidence.sha256,
            "schema_version": "r5-order-derivation-projection-v2",
        }
        if (
            order_evidence.count != manifest["v2_inception_order_derivation_count"]
            or order_evidence.sha256 != manifest["v2_inception_order_derivation_rows_sha256"]
            or digest(projection) != manifest["v2_inception_order_derivation_digest"]
            or ledger_evidence.parity_digest != order_evidence.parity_digest
        ):
            raise ResearchReplayIntegrityError("order derivation payload/manifest conflict")
        return LedgerArtifact(manifest, ledger_rows, order_rows, path)

    def publish_match_plan(
        self,
        *,
        manifest: Mapping[str, object],
        match_rows: Iterable[Mapping[str, object]],
    ) -> Path:
        verified = verify_match_manifest(manifest)
        final = self._path("match_plans", verified["match_plan_manifest_digest"])
        if final.exists():
            loaded = self.load_match_plan(verified["match_plan_manifest_digest"])
            if loaded.manifest != verified:
                raise ResearchReplayIntegrityError("existing match-plan manifest conflict")
            return final
        temporary = self._temporary("match_plans", verified["match_plan_manifest_digest"])
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            evidence = self._write_rows(
                temporary, "matches.jsonl", match_rows, verify_match_row, "match_id"
            )
            self._verify_match_evidence(verified, evidence)
            self._write_manifest(temporary, verified)
            self._publish_directory(temporary, final)
            return self.load_match_plan(verified["match_plan_manifest_digest"]).path
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def load_match_plan(self, manifest_digest: str) -> MatchPlanArtifact:
        path = self._path(
            "match_plans", require_sha256(manifest_digest, "match-plan manifest digest")
        )
        self._require_files(path, {"matches.jsonl", "manifest.json"})
        manifest = self._load_manifest(path, verify_match_manifest)
        if manifest["match_plan_manifest_digest"] != manifest_digest:
            raise ResearchReplayIntegrityError("match-plan locator/digest conflict")
        rows, evidence = self._read_rows(path / "matches.jsonl", verify_match_row, "match_id")
        self._verify_match_evidence(manifest, evidence)
        return MatchPlanArtifact(manifest, rows, path)

    def publish_result(
        self,
        *,
        manifest: Mapping[str, object],
        episode_rows: Iterable[Mapping[str, object]],
        modeled_entry_rows: Iterable[Mapping[str, object]],
        modeled_exit_rows: Iterable[Mapping[str, object]],
    ) -> Path:
        verified = verify_result_manifest(manifest)
        final = self._path("results", verified["result_manifest_digest"])
        if final.exists():
            loaded = self.load_result(verified["result_manifest_digest"])
            if loaded.manifest != verified:
                raise ResearchReplayIntegrityError("existing result manifest conflict")
            return final
        temporary = self._temporary("results", verified["result_manifest_digest"])
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            episodes = self._write_rows(
                temporary, "episodes.jsonl", episode_rows, verify_episode_row, "episode_id"
            )
            entries = self._write_rows(
                temporary,
                "modeled_entries.jsonl",
                modeled_entry_rows,
                verify_modeled_entry_row,
                "modeled_entry_id",
            )
            exits = self._write_rows(
                temporary,
                "modeled_exits.jsonl",
                modeled_exit_rows,
                verify_modeled_exit_row,
                "modeled_exit_id",
            )
            self._verify_result_evidence(verified, episodes, entries, exits)
            persisted_episodes, _ = self._read_rows(
                temporary / "episodes.jsonl", verify_episode_row, "episode_id"
            )
            persisted_entries, _ = self._read_rows(
                temporary / "modeled_entries.jsonl",
                verify_modeled_entry_row,
                "modeled_entry_id",
            )
            persisted_exits, _ = self._read_rows(
                temporary / "modeled_exits.jsonl",
                verify_modeled_exit_row,
                "modeled_exit_id",
            )
            reconstructed_cost_identity = verify_replay_consistency(
                episode_rows=persisted_episodes,
                modeled_entry_rows=persisted_entries,
                modeled_exit_rows=persisted_exits,
                summary=verified["summary"],
            )
            if digest(reconstructed_cost_identity) != verified["cost_identity_digest"]:
                raise ResearchReplayIntegrityError("result cost identity/rows conflict")
            self._write_manifest(temporary, verified)
            self._publish_directory(temporary, final)
            return self.load_result(verified["result_manifest_digest"]).path
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def load_result(self, manifest_digest: str) -> ResultArtifact:
        path = self._path("results", require_sha256(manifest_digest, "result manifest digest"))
        self._require_files(
            path,
            {
                "episodes.jsonl",
                "modeled_entries.jsonl",
                "modeled_exits.jsonl",
                "manifest.json",
            },
        )
        manifest = self._load_manifest(path, verify_result_manifest)
        if manifest["result_manifest_digest"] != manifest_digest:
            raise ResearchReplayIntegrityError("result locator/digest conflict")
        episodes, episode_evidence = self._read_rows(
            path / "episodes.jsonl", verify_episode_row, "episode_id"
        )
        entries, entry_evidence = self._read_rows(
            path / "modeled_entries.jsonl", verify_modeled_entry_row, "modeled_entry_id"
        )
        exits, exit_evidence = self._read_rows(
            path / "modeled_exits.jsonl", verify_modeled_exit_row, "modeled_exit_id"
        )
        self._verify_result_evidence(
            manifest, episode_evidence, entry_evidence, exit_evidence
        )
        reconstructed_cost_identity = verify_replay_consistency(
            episode_rows=episodes,
            modeled_entry_rows=entries,
            modeled_exit_rows=exits,
            summary=manifest["summary"],
        )
        if digest(reconstructed_cost_identity) != manifest["cost_identity_digest"]:
            raise ResearchReplayIntegrityError("result cost identity/rows conflict")
        return ResultArtifact(manifest, episodes, entries, exits, path)

    def _path(self, category: str, artifact_digest: str) -> Path:
        return self._root / category / artifact_digest

    def _temporary(self, category: str, artifact_digest: str) -> Path:
        return self._root / category / f".{artifact_digest}.{uuid4().hex}.tmp"

    def _publish_directory(self, temporary: Path, final: Path) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(temporary, final)
        except OSError:
            if not final.is_dir():
                raise
            shutil.rmtree(temporary, ignore_errors=True)
        directory_fd = os.open(final.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _write_manifest(directory: Path, manifest: Mapping[str, Any]) -> None:
        with (directory / "manifest.json").open("xb") as handle:
            handle.write(canonical_object_bytes(manifest))
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _load_manifest(path: Path, verifier: Verifier) -> dict[str, Any]:
        try:
            payload = (path / "manifest.json").read_bytes()
            parsed = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResearchReplayIntegrityError("artifact manifest 無法讀取") from error
        if not isinstance(parsed, Mapping):
            raise ResearchReplayIntegrityError("artifact manifest 必須是 object")
        manifest = verifier(parsed)
        if payload != canonical_object_bytes(manifest):
            raise ResearchReplayIntegrityError("artifact manifest bytes 不 canonical")
        return manifest

    @staticmethod
    def _require_files(path: Path, expected: set[str]) -> None:
        if not path.is_dir():
            raise KeyError(f"找不到 replay artifact：{path.name}")
        actual = {item.name for item in path.iterdir()}
        if actual != expected:
            raise ResearchReplayIntegrityError(
                f"artifact file set 不一致：missing={sorted(expected - actual)}, "
                f"unknown={sorted(actual - expected)}"
            )

    def _write_rows(
        self,
        directory: Path,
        filename: str,
        rows: Iterable[Mapping[str, object]],
        verifier: Verifier,
        primary_id: str,
    ) -> _PayloadEvidence:
        scratch = directory / f".{filename}.chunks"
        scratch.mkdir(exist_ok=False)
        chunks: list[Path] = []
        batch: list[dict[str, Any]] = []
        try:
            for source in rows:
                batch.append(verifier(source))
                if len(batch) >= self._chunk_size:
                    chunks.append(self._write_chunk(scratch, len(chunks), batch))
                    batch = []
            if batch:
                chunks.append(self._write_chunk(scratch, len(chunks), batch))
            merge_round = 0
            while len(chunks) > self._merge_fan_in:
                merged: list[Path] = []
                for group_index, offset in enumerate(
                    range(0, len(chunks), self._merge_fan_in)
                ):
                    group = chunks[offset : offset + self._merge_fan_in]
                    destination = scratch / (
                        f"merge-{merge_round:04d}-{group_index:08d}.jsonl"
                    )
                    self._merge_sorted_files(group, destination, verifier)
                    merged.append(destination)
                for chunk in chunks:
                    chunk.unlink()
                chunks = merged
                merge_round += 1
            target = directory / filename
            evidence = self._merge_chunks(chunks, target, verifier, primary_id)
            return evidence
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    @staticmethod
    def _write_chunk(directory: Path, index: int, rows: list[dict[str, Any]]) -> Path:
        path = directory / f"chunk-{index:08d}.jsonl"
        ordered = sorted(rows, key=lambda item: int(item["sequence"]))
        with path.open("xb") as handle:
            for row in ordered:
                handle.write(canonical_object_bytes(row))
            handle.flush()
            os.fsync(handle.fileno())
        return path

    @staticmethod
    def _merge_sorted_files(
        chunks: list[Path], target: Path, verifier: Verifier
    ) -> None:
        handles = [path.open("rb") for path in chunks]
        heap: list[tuple[int, int, dict[str, Any]]] = []

        def read_one(index: int) -> dict[str, Any] | None:
            raw = handles[index].readline()
            if not raw:
                return None
            return ReplayArtifactStore._parse_row(raw, verifier)

        try:
            for index in range(len(handles)):
                row = read_one(index)
                if row is not None:
                    heapq.heappush(heap, (int(row["sequence"]), index, row))
            previous_sequence: int | None = None
            with target.open("xb") as output:
                while heap:
                    sequence, index, row = heapq.heappop(heap)
                    if previous_sequence is not None and sequence <= previous_sequence:
                        raise ResearchReplayIntegrityError(
                            "artifact intermediate sequence 必須 unique"
                        )
                    output.write(canonical_object_bytes(row))
                    previous_sequence = sequence
                    next_row = read_one(index)
                    if next_row is not None:
                        heapq.heappush(
                            heap, (int(next_row["sequence"]), index, next_row)
                        )
                output.flush()
                os.fsync(output.fileno())
        finally:
            for handle in handles:
                handle.close()

    def _merge_chunks(
        self,
        chunks: list[Path],
        target: Path,
        verifier: Verifier,
        primary_id: str,
    ) -> _PayloadEvidence:
        handles = [path.open("rb") for path in chunks]
        heap: list[tuple[int, int, dict[str, Any]]] = []
        checksum = hashlib.sha256()
        parity: Counter[str] = Counter()
        semantic: Counter[str] = Counter()
        primary: Counter[str] = Counter()
        seen_signals: set[str] = set()
        count = 0

        def read_one(index: int) -> dict[str, Any] | None:
            raw = handles[index].readline()
            if not raw:
                return None
            row = self._parse_row(raw, verifier)
            return row

        try:
            for index in range(len(handles)):
                row = read_one(index)
                if row is not None:
                    heapq.heappush(heap, (int(row["sequence"]), index, row))
            with target.open("xb") as output:
                while heap:
                    sequence, index, row = heapq.heappop(heap)
                    if sequence != count + 1:
                        raise ResearchReplayIntegrityError(
                            "artifact row sequence 必須從 1 連續且 unique"
                        )
                    payload = canonical_object_bytes(row)
                    if row["signal_id"] in seen_signals:
                        raise ResearchReplayIntegrityError(
                            "artifact row signal_id 必須 unique"
                        )
                    seen_signals.add(row["signal_id"])
                    output.write(payload)
                    checksum.update(payload)
                    token = canonical_json(
                        {
                            "semantic_key": row["semantic_key"],
                            "sequence": sequence,
                            "signal_id": row["signal_id"],
                        }
                    )
                    parity[token] += 1
                    semantic[str(row["semantic_key"])] += 1
                    primary[str(row[primary_id])] += 1
                    count += 1
                    next_row = read_one(index)
                    if next_row is not None:
                        heapq.heappush(
                            heap, (int(next_row["sequence"]), index, next_row)
                        )
                output.flush()
                os.fsync(output.fileno())
        finally:
            for handle in handles:
                handle.close()
        parity_projection = {
            "schema_version": "r5-layer-parity-projection-v2",
            "tokens": dict(sorted(parity.items())),
        }
        semantic_projection = {
            "schema_version": "r5-signal-multiplicity-v2",
            "tokens": dict(sorted(semantic.items())),
        }
        return _PayloadEvidence(
            count=count,
            sha256=checksum.hexdigest(),
            parity_digest=digest(parity_projection),
            semantic_multiplicity_digest=digest(semantic_projection),
            primary_duplicate_count=sum(max(value - 1, 0) for value in primary.values()),
        )

    @staticmethod
    def _parse_row(raw: bytes, verifier: Verifier) -> dict[str, Any]:
        if raw == b"\n" or not raw.endswith(b"\n"):
            raise ResearchReplayIntegrityError("artifact JSONL 不可空白且必須有 LF")
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResearchReplayIntegrityError("artifact JSONL row 無法解析") from error
        if not isinstance(parsed, Mapping):
            raise ResearchReplayIntegrityError("artifact JSONL row 必須是 object")
        row = verifier(parsed)
        if raw != canonical_object_bytes(row):
            raise ResearchReplayIntegrityError("artifact JSONL row bytes 不 canonical")
        return row

    def _read_rows(
        self, path: Path, verifier: Verifier, primary_id: str
    ) -> tuple[tuple[dict[str, Any], ...], _PayloadEvidence]:
        rows: list[dict[str, Any]] = []
        checksum = hashlib.sha256()
        parity: Counter[str] = Counter()
        semantic: Counter[str] = Counter()
        primary: Counter[str] = Counter()
        seen_signals: set[str] = set()
        try:
            with path.open("rb") as handle:
                for expected, raw in enumerate(handle, start=1):
                    row = self._parse_row(raw, verifier)
                    if row["sequence"] != expected:
                        raise ResearchReplayIntegrityError(
                            "artifact sequence 必須從 1 連續且 unique"
                        )
                    if row["signal_id"] in seen_signals:
                        raise ResearchReplayIntegrityError(
                            "artifact row signal_id 必須 unique"
                        )
                    seen_signals.add(row["signal_id"])
                    rows.append(row)
                    checksum.update(raw)
                    parity[
                        canonical_json(
                            {
                                "semantic_key": row["semantic_key"],
                                "sequence": row["sequence"],
                                "signal_id": row["signal_id"],
                            }
                        )
                    ] += 1
                    semantic[str(row["semantic_key"])] += 1
                    primary[str(row[primary_id])] += 1
        except OSError as error:
            raise ResearchReplayIntegrityError("artifact payload 無法讀取") from error
        parity_projection = {
            "schema_version": "r5-layer-parity-projection-v2",
            "tokens": dict(sorted(parity.items())),
        }
        semantic_projection = {
            "schema_version": "r5-signal-multiplicity-v2",
            "tokens": dict(sorted(semantic.items())),
        }
        return tuple(rows), _PayloadEvidence(
            count=len(rows),
            sha256=checksum.hexdigest(),
            parity_digest=digest(parity_projection),
            semantic_multiplicity_digest=digest(semantic_projection),
            primary_duplicate_count=sum(max(value - 1, 0) for value in primary.values()),
        )

    @staticmethod
    def _verify_match_evidence(
        manifest: Mapping[str, Any], evidence: _PayloadEvidence
    ) -> None:
        if (
            evidence.count != manifest["matched_exit_count"]
            or evidence.sha256 != manifest["match_rows_sha256"]
            or evidence.parity_digest != manifest["match_signal_multiplicity_digest"]
            or evidence.primary_duplicate_count != manifest["duplicate_match_count"]
        ):
            raise ResearchReplayIntegrityError("match-plan payload/manifest conflict")

    @staticmethod
    def _verify_result_evidence(
        manifest: Mapping[str, Any],
        episodes: _PayloadEvidence,
        entries: _PayloadEvidence,
        exits: _PayloadEvidence,
    ) -> None:
        expected = (
            (episodes, "episode"),
            (entries, "modeled_entry"),
            (exits, "modeled_exit"),
        )
        for evidence, prefix in expected:
            if (
                evidence.count != manifest[f"{prefix}_count"]
                or evidence.sha256 != manifest[f"{prefix}_rows_sha256"]
                or evidence.parity_digest
                != manifest[f"{prefix}_signal_multiplicity_digest"]
            ):
                raise ResearchReplayIntegrityError(
                    f"{prefix} payload/manifest conflict"
                )
        if not (
            episodes.parity_digest == entries.parity_digest == exits.parity_digest
        ):
            raise ResearchReplayIntegrityError("result layer parity conflict")
