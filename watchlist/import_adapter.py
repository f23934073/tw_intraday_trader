"""Strict import boundary for sealed PIT universe snapshot/manifest bytes."""

from __future__ import annotations

import hashlib

from watchlist.reference_data import EquityUniverseArtifact, SnapshotEquityUniverse
from watchlist.serialization import (
    EquityUniverseSerializationError,
    deserialize_manifest,
    deserialize_snapshot,
    snapshot_sha256,
)


class EquityUniverseImportError(ValueError):
    """Imported evidence is internally inconsistent or has drifted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class CanonicalPitEquityUniverseImportAdapter:
    """Build an immutable query port from canonical, caller-sealed bytes."""

    def load(
        self,
        *,
        snapshot_payload: bytes,
        manifest_payload: bytes,
        source_payload: bytes | None = None,
    ) -> SnapshotEquityUniverse:
        try:
            snapshot_json = snapshot_payload.decode("utf-8")
            manifest_json = manifest_payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise EquityUniverseImportError(
                "INVALID_UTF8",
                "universe artifacts must be UTF-8 JSON",
            ) from error
        try:
            snapshot = deserialize_snapshot(snapshot_json)
            manifest = deserialize_manifest(manifest_json)
        except EquityUniverseSerializationError as error:
            raise EquityUniverseImportError("SCHEMA_DRIFT", str(error)) from error

        if snapshot.snapshot_id != manifest.snapshot_id:
            raise EquityUniverseImportError(
                "SNAPSHOT_ID_MISMATCH",
                "snapshot and manifest identities differ",
            )
        if manifest.record_count != len(snapshot.records):
            raise EquityUniverseImportError(
                "ROW_COUNT_MISMATCH",
                "manifest record_count differs from snapshot rows",
            )
        if (
            manifest.content_digest is not None
            and snapshot_sha256(snapshot) != manifest.content_digest
        ):
            raise EquityUniverseImportError(
                "CONTENT_DIGEST_MISMATCH",
                "canonical snapshot content differs from the manifest digest",
            )
        if source_payload is not None and manifest.source_digest is not None:
            source_digest = hashlib.sha256(source_payload).hexdigest()
            if source_digest != manifest.source_digest:
                raise EquityUniverseImportError(
                    "SOURCE_DIGEST_MISMATCH",
                    "source bytes differ from the manifest source digest",
                )

        return SnapshotEquityUniverse(
            EquityUniverseArtifact(snapshot=snapshot, manifest=manifest)
        )
