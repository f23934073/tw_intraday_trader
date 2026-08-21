"""Immutable raw-response artifacts for official institutional-flow sources."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Protocol

from institutional_data.domain import InstitutionalMarket
from institutional_data.serialization import canonical_json, sha256_text


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_sha256(value: str, field_name: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


def _pairs(
    values: tuple[tuple[str, str], ...],
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for key, value in values:
        normalized.append(
            (
                _require_text(key, f"{field_name} key"),
                _require_text(value, f"{field_name} value"),
            )
        )
    return tuple(normalized)


@dataclass(frozen=True)
class InstitutionalRawArtifactKey:
    """Logical revision key; content digest is deliberately not part of it."""

    market: InstitutionalMarket
    session_date: date
    source_product: str
    trade_scope_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", InstitutionalMarket(self.market))
        for field_name in ("source_product", "trade_scope_id"):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True)
class InstitutionalRawCapture:
    """Raw bytes and request evidence captured before any parser is invoked."""

    key: InstitutionalRawArtifactKey
    source_url: str
    request_method: str
    request_parameters: tuple[tuple[str, str], ...]
    response_headers: tuple[tuple[str, str], ...]
    content_type: str
    parser_version: str
    retrieved_at: datetime
    first_observed_at: datetime
    payload: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_url", _require_text(self.source_url, "source_url")
        )
        method = _require_text(self.request_method, "request_method").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("request_method must be GET or POST")
        object.__setattr__(self, "request_method", method)
        object.__setattr__(
            self,
            "request_parameters",
            _pairs(self.request_parameters, "request_parameters"),
        )
        object.__setattr__(
            self,
            "response_headers",
            _pairs(self.response_headers, "response_headers"),
        )
        object.__setattr__(
            self,
            "content_type",
            _require_text(self.content_type, "content_type"),
        )
        object.__setattr__(
            self,
            "parser_version",
            _require_text(self.parser_version, "parser_version"),
        )
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_aware(self.first_observed_at, "first_observed_at")
        if self.first_observed_at > self.retrieved_at:
            raise ValueError("first_observed_at cannot be after retrieved_at")
        if not isinstance(self.payload, bytes):
            raise ValueError("payload must be bytes")


@dataclass(frozen=True)
class InstitutionalRawArtifact:
    """One immutable content-addressed source response revision."""

    artifact_id: str
    revision: int
    key: InstitutionalRawArtifactKey
    source_url: str
    request_method: str
    request_parameters: tuple[tuple[str, str], ...]
    response_headers: tuple[tuple[str, str], ...]
    content_type: str
    parser_version: str
    retrieved_at: datetime
    first_observed_at: datetime
    raw_sha256: str
    payload: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, "artifact_id"),
        )
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("revision must be a positive integer")
        _require_sha256(self.raw_sha256, "raw_sha256")
        if hashlib.sha256(self.payload).hexdigest() != self.raw_sha256:
            raise ValueError("payload does not match raw_sha256")
        InstitutionalRawCapture(
            key=self.key,
            source_url=self.source_url,
            request_method=self.request_method,
            request_parameters=self.request_parameters,
            response_headers=self.response_headers,
            content_type=self.content_type,
            parser_version=self.parser_version,
            retrieved_at=self.retrieved_at,
            first_observed_at=self.first_observed_at,
            payload=self.payload,
        )


class InstitutionalRawArtifactStore(Protocol):
    """Append-only storage port used by the raw-first ingestion application."""

    def capture(self, capture: InstitutionalRawCapture) -> InstitutionalRawArtifact:
        """Deduplicate identical bytes or append a revision for changed bytes."""

    def get(self, artifact_id: str) -> InstitutionalRawArtifact | None:
        """Return one immutable raw artifact by identity."""

    def revisions(
        self,
        key: InstitutionalRawArtifactKey,
    ) -> tuple[InstitutionalRawArtifact, ...]:
        """Return all revisions for one logical key in ascending order."""


def _artifact_id(key: InstitutionalRawArtifactKey, raw_sha256: str) -> str:
    identity = canonical_json(
        {
            "market": key.market.value,
            "session_date": key.session_date,
            "source_product": key.source_product,
            "trade_scope_id": key.trade_scope_id,
            "raw_sha256": raw_sha256,
        }
    )
    return f"institutional-raw-{sha256_text(identity)[:32]}"


def _new_artifact(
    capture: InstitutionalRawCapture,
    revision: int,
) -> InstitutionalRawArtifact:
    digest = hashlib.sha256(capture.payload).hexdigest()
    return InstitutionalRawArtifact(
        artifact_id=_artifact_id(capture.key, digest),
        revision=revision,
        key=capture.key,
        source_url=capture.source_url,
        request_method=capture.request_method,
        request_parameters=capture.request_parameters,
        response_headers=capture.response_headers,
        content_type=capture.content_type,
        parser_version=capture.parser_version,
        retrieved_at=capture.retrieved_at,
        first_observed_at=capture.first_observed_at,
        raw_sha256=digest,
        payload=capture.payload,
    )


class InMemoryInstitutionalRawArtifactStore:
    """Thread-safe append-only store for tests and caller-owned ephemeral jobs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_id: dict[str, InstitutionalRawArtifact] = {}
        self._by_key: dict[
            InstitutionalRawArtifactKey,
            list[InstitutionalRawArtifact],
        ] = {}

    def capture(self, capture: InstitutionalRawCapture) -> InstitutionalRawArtifact:
        digest = hashlib.sha256(capture.payload).hexdigest()
        with self._lock:
            revisions = self._by_key.setdefault(capture.key, [])
            for artifact in revisions:
                if artifact.raw_sha256 == digest:
                    if artifact.payload != capture.payload:
                        raise RuntimeError("SHA256 collision in raw artifact store")
                    return artifact
            artifact = _new_artifact(capture, len(revisions) + 1)
            revisions.append(artifact)
            self._by_id[artifact.artifact_id] = artifact
            return artifact

    def get(self, artifact_id: str) -> InstitutionalRawArtifact | None:
        with self._lock:
            return self._by_id.get(artifact_id)

    def revisions(
        self,
        key: InstitutionalRawArtifactKey,
    ) -> tuple[InstitutionalRawArtifact, ...]:
        with self._lock:
            return tuple(self._by_key.get(key, ()))


def _slug(value: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"
    return f"{readable}-{sha256_text(value)[:8]}"


class DirectoryInstitutionalRawArtifactStore:
    """Append-only directory store for raw evidence without a database schema."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = RLock()
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_directory(self, key: InstitutionalRawArtifactKey) -> Path:
        return (
            self._root
            / key.market.value.lower()
            / key.session_date.isoformat()
            / _slug(key.source_product)
            / _slug(key.trade_scope_id)
        )

    def capture(self, capture: InstitutionalRawCapture) -> InstitutionalRawArtifact:
        digest = hashlib.sha256(capture.payload).hexdigest()
        with self._lock:
            existing = self.revisions(capture.key)
            for artifact in existing:
                if artifact.raw_sha256 == digest:
                    if artifact.payload != capture.payload:
                        raise RuntimeError("SHA256 collision in raw artifact store")
                    return artifact

            artifact = _new_artifact(capture, len(existing) + 1)
            directory = self._key_directory(capture.key)
            directory.mkdir(parents=True, exist_ok=True)
            stem = f"r{artifact.revision:06d}-{artifact.raw_sha256}"
            raw_path = directory / f"{stem}.raw"
            metadata_path = directory / f"{stem}.json"
            with raw_path.open("xb") as raw_file:
                raw_file.write(artifact.payload)
                raw_file.flush()
            with metadata_path.open("x", encoding="utf-8") as metadata_file:
                metadata_file.write(self._metadata_json(artifact))
                metadata_file.flush()
            return artifact

    def get(self, artifact_id: str) -> InstitutionalRawArtifact | None:
        with self._lock:
            for metadata_path in self._root.rglob("r*.json"):
                artifact = self._load(metadata_path)
                if artifact.artifact_id == artifact_id:
                    return artifact
        return None

    def revisions(
        self,
        key: InstitutionalRawArtifactKey,
    ) -> tuple[InstitutionalRawArtifact, ...]:
        with self._lock:
            directory = self._key_directory(key)
            if not directory.exists():
                return ()
            artifacts = tuple(
                self._load(metadata_path)
                for metadata_path in sorted(directory.glob("r*.json"))
            )
            expected = tuple(range(1, len(artifacts) + 1))
            actual = tuple(artifact.revision for artifact in artifacts)
            if actual != expected:
                raise ValueError("raw artifact revisions are not contiguous")
            if any(artifact.key != key for artifact in artifacts):
                raise ValueError("raw artifact metadata does not match directory key")
            return artifacts

    @staticmethod
    def _metadata_json(artifact: InstitutionalRawArtifact) -> str:
        return canonical_json(
            {
                "schema_version": "institutional_raw_artifact_v1",
                "artifact_id": artifact.artifact_id,
                "revision": artifact.revision,
                "market": artifact.key.market.value,
                "session_date": artifact.key.session_date,
                "source_product": artifact.key.source_product,
                "trade_scope_id": artifact.key.trade_scope_id,
                "source_url": artifact.source_url,
                "request_method": artifact.request_method,
                "request_parameters": artifact.request_parameters,
                "response_headers": artifact.response_headers,
                "content_type": artifact.content_type,
                "parser_version": artifact.parser_version,
                "retrieved_at": artifact.retrieved_at,
                "first_observed_at": artifact.first_observed_at,
                "raw_sha256": artifact.raw_sha256,
                "raw_file": f"r{artifact.revision:06d}-{artifact.raw_sha256}.raw",
            }
        )

    @staticmethod
    def _load(metadata_path: Path) -> InstitutionalRawArtifact:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"invalid raw artifact metadata: {metadata_path}"
            ) from error
        expected_fields = {
            "schema_version",
            "artifact_id",
            "revision",
            "market",
            "session_date",
            "source_product",
            "trade_scope_id",
            "source_url",
            "request_method",
            "request_parameters",
            "response_headers",
            "content_type",
            "parser_version",
            "retrieved_at",
            "first_observed_at",
            "raw_sha256",
            "raw_file",
        }
        if not isinstance(metadata, dict) or set(metadata) != expected_fields:
            raise ValueError(f"raw artifact metadata schema drift: {metadata_path}")
        if metadata["schema_version"] != "institutional_raw_artifact_v1":
            raise ValueError("unsupported raw artifact schema_version")
        raw_file = metadata["raw_file"]
        if not isinstance(raw_file, str) or Path(raw_file).name != raw_file:
            raise ValueError("raw_file must be a local filename")
        payload = (metadata_path.parent / raw_file).read_bytes()
        try:
            return InstitutionalRawArtifact(
                artifact_id=str(metadata["artifact_id"]),
                revision=int(metadata["revision"]),
                key=InstitutionalRawArtifactKey(
                    market=InstitutionalMarket(str(metadata["market"])),
                    session_date=date.fromisoformat(str(metadata["session_date"])),
                    source_product=str(metadata["source_product"]),
                    trade_scope_id=str(metadata["trade_scope_id"]),
                ),
                source_url=str(metadata["source_url"]),
                request_method=str(metadata["request_method"]),
                request_parameters=tuple(
                    (str(key), str(value))
                    for key, value in metadata["request_parameters"]
                ),
                response_headers=tuple(
                    (str(key), str(value))
                    for key, value in metadata["response_headers"]
                ),
                content_type=str(metadata["content_type"]),
                parser_version=str(metadata["parser_version"]),
                retrieved_at=datetime.fromisoformat(str(metadata["retrieved_at"])),
                first_observed_at=datetime.fromisoformat(
                    str(metadata["first_observed_at"])
                ),
                raw_sha256=str(metadata["raw_sha256"]),
                payload=payload,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"invalid raw artifact metadata: {metadata_path}"
            ) from error
