"""Atomic append-only file repository for daily institutional MVP batches."""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from institutional_data.serialization import canonical_json
from institutional_mvp.domain import (
    DailyRunStatus,
    InstitutionalMvpCandidateBatchV1,
    verify_candidate_batch_payload,
)
from institutional_mvp.ports import (
    InstitutionalMvpArtifactPublication,
    ReviewedEquitySessionCalendar,
)


class InstitutionalMvpArtifactError(RuntimeError):
    """An immutable batch cannot be safely published or replayed."""


class InstitutionalMvpArtifactConflict(InstitutionalMvpArtifactError):
    """A session has multiple immutable revisions and requires an exact pin."""


class DirectoryInstitutionalMvpCandidateBatchRepository:
    """Content-addressed repository with process-safe no-clobber publication."""

    def __init__(
        self,
        root: Path,
        *,
        calendar: ReviewedEquitySessionCalendar,
        expected_policy_digest: str,
        expected_base_policy_digest: str,
        expected_calendar_digest: str,
    ) -> None:
        self._root = Path(root)
        self._expected_policy_digest = _require_digest(
            expected_policy_digest, "expected_policy_digest"
        )
        self._expected_base_policy_digest = _require_digest(
            expected_base_policy_digest, "expected_base_policy_digest"
        )
        self._expected_calendar_digest = _require_digest(
            expected_calendar_digest, "expected_calendar_digest"
        )
        if _require_digest(calendar.source_digest, "calendar source_digest") != (
            self._expected_calendar_digest
        ):
            raise ValueError("repository calendar differs from expected calendar digest")
        self._calendar = calendar
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._root / ".publish.lock"
        self._lock_path.touch(exist_ok=True)
        os.chmod(self._lock_path, 0o600)

    def put_immutable(
        self, batch: InstitutionalMvpCandidateBatchV1
    ) -> InstitutionalMvpArtifactPublication:
        payload = json.loads(canonical_json(batch.to_dict()))
        if not isinstance(payload, Mapping):
            raise InstitutionalMvpArtifactError("candidate batch must serialize to one object")
        self._verify_payload(payload)
        encoded = (canonical_json(payload) + "\n").encode("utf-8")
        directory = self._session_directory(
            batch.source_session, batch.target_session
        )
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{batch.artifact_digest}.json"

        with self._lock_path.open("r+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            existing = self._load_session(
                source_session=batch.source_session,
                target_session=batch.target_session,
            )
            for path, artifact in existing:
                if artifact.get("source_fingerprint") == batch.source_fingerprint:
                    if _stable_replay_projection(artifact) == _stable_replay_projection(
                        payload
                    ):
                        return self._publication(
                            artifact,
                            path,
                            DailyRunStatus.IDEMPOTENT_REPLAY,
                        )

            if destination.exists():
                if destination.read_bytes() == encoded:
                    loaded = self._load_verified(destination)
                    return self._publication(
                        loaded,
                        destination,
                        DailyRunStatus.IDEMPOTENT_REPLAY,
                    )
                raise InstitutionalMvpArtifactError(
                    "artifact digest collision or non-canonical existing bytes"
                )

            temporary = directory / f".{batch.artifact_digest}.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as output:
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(temporary, 0o440)
                try:
                    try:
                        os.link(temporary, destination)
                        self._fsync_directory(directory)
                    except BaseException:
                        if _paths_share_inode(temporary, destination):
                            destination.unlink(missing_ok=True)
                            self._fsync_directory(directory)
                        raise
                except FileExistsError:
                    if destination.read_bytes() != encoded:
                        raise InstitutionalMvpArtifactError(
                            "artifact digest collision during concurrent publish"
                        )
            finally:
                temporary.unlink(missing_ok=True)

            loaded = self._load_verified(destination)
            status = (
                DailyRunStatus.CONFLICT_REVISION_CREATED
                if existing
                else DailyRunStatus.PUBLISHED
            )
            return self._publication(loaded, destination, status)

    def get_by_target_session(
        self, target_session: date
    ) -> Mapping[str, Any] | None:
        with self._lock_path.open("rb") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            paths = sorted((self._root / target_session.isoformat()).glob("*/*.json"))
            artifacts = [self._load_verified(path) for path in paths]
            if not artifacts:
                return None
            if len(artifacts) != 1:
                raise InstitutionalMvpArtifactConflict(
                    "target session has multiple revisions; pin an artifact digest"
                )
            return artifacts[0]

    def get_by_digest(
        self, *, target_session: date, artifact_digest: str
    ) -> Mapping[str, Any] | None:
        artifact_digest = _require_digest(artifact_digest, "artifact_digest")
        with self._lock_path.open("rb") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            matches = sorted(
                (self._root / target_session.isoformat()).glob(
                    f"*/{artifact_digest}.json"
                )
            )
            if not matches:
                return None
            if len(matches) != 1:
                raise InstitutionalMvpArtifactConflict(
                    "artifact digest resolves to multiple session paths"
                )
            return self._load_verified(matches[0])

    def _load_session(
        self, *, source_session: date, target_session: date
    ) -> list[tuple[Path, Mapping[str, Any]]]:
        directory = self._session_directory(source_session, target_session)
        return [
            (path, self._load_verified(path))
            for path in sorted(directory.glob("*.json"))
        ]

    def _load_verified(self, path: Path) -> Mapping[str, Any]:
        try:
            encoded = path.read_bytes()
            payload = json.loads(encoded)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstitutionalMvpArtifactError(
                f"invalid institutional MVP artifact: {path}"
            ) from error
        if not isinstance(payload, Mapping):
            raise InstitutionalMvpArtifactError("candidate batch must be one object")
        try:
            self._verify_payload(payload)
        except (TypeError, ValueError) as error:
            raise InstitutionalMvpArtifactError(
                f"candidate batch verification failed: {path}"
            ) from error
        canonical = (canonical_json(payload) + "\n").encode("utf-8")
        if encoded != canonical:
            raise InstitutionalMvpArtifactError(
                "candidate batch bytes are not canonical JSON"
            )
        if path.stem != payload["artifact_digest"]:
            raise InstitutionalMvpArtifactError(
                "candidate batch filename does not match artifact digest"
            )
        if path.parent.name != payload["source_session"]:
            raise InstitutionalMvpArtifactError(
                "candidate batch source-session path mismatch"
            )
        if path.parent.parent.name != payload["target_session"]:
            raise InstitutionalMvpArtifactError(
                "candidate batch target-session path mismatch"
            )
        return payload

    def _verify_payload(self, payload: Mapping[str, Any]) -> None:
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=self._calendar.next_trading_day,
            expected_policy_digest=self._expected_policy_digest,
            expected_base_policy_digest=self._expected_base_policy_digest,
            expected_calendar_digest=self._expected_calendar_digest,
        )

    def _session_directory(
        self, source_session: date, target_session: date
    ) -> Path:
        return (
            self._root
            / target_session.isoformat()
            / source_session.isoformat()
        )

    @staticmethod
    def _publication(
        payload: Mapping[str, Any], path: Path, status: DailyRunStatus
    ) -> InstitutionalMvpArtifactPublication:
        return InstitutionalMvpArtifactPublication(
            status=status,
            artifact_id=str(payload["artifact_id"]),
            artifact_digest=str(payload["artifact_digest"]),
            source_session=date.fromisoformat(str(payload["source_session"])),
            target_session=date.fromisoformat(str(payload["target_session"])),
            path=path,
        )

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _paths_share_inode(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except (FileNotFoundError, OSError):
        return False


def _require_digest(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return value


def _stable_replay_projection(payload: Mapping[str, Any]) -> str:
    projection = dict(payload)
    projection.pop("artifact_digest", None)
    projection.pop("artifact_id", None)
    projection.pop("generated_at", None)
    source = dict(_mapping_value(projection.get("source_evidence"), "source_evidence"))
    source.pop("retrieved_at", None)
    source.pop("usage", None)
    projection["source_evidence"] = source
    return canonical_json(projection)


def _mapping_value(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstitutionalMvpArtifactError(f"{field_name} must be an object")
    return value
