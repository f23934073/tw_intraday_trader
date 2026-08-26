"""Fail-closed immutable JSON/digest artifact-pair writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def digest_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def write_json_digest_pair_exclusive(
    path: Path,
    value: object,
    digest: str,
) -> None:
    """Publish sidecar first and JSON last as the pair's commit marker."""

    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = digest_path(path)
    lock = path.with_suffix(path.suffix + ".write.lock")
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    artifact_stage: Path | None = None
    sidecar_stage: Path | None = None
    sidecar_committed = False
    artifact_committed = False
    try:
        os.write(lock_fd, b"INCOMPLETE_ARTIFACT_PAIR\n")
        os.fsync(lock_fd)
        if path.exists() or sidecar.exists():
            raise FileExistsError(f"artifact pair target already exists: {path}")
        artifact_bytes = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        sidecar_bytes = (digest + "\n").encode("ascii")
        artifact_stage = _stage_bytes(path.parent, path.name, artifact_bytes)
        sidecar_stage = _stage_bytes(path.parent, sidecar.name, sidecar_bytes)
        os.link(sidecar_stage, sidecar)
        sidecar_committed = True
        os.link(artifact_stage, path)
        artifact_committed = True
        _fsync_directory(path.parent)
    finally:
        os.close(lock_fd)
        for staged in (artifact_stage, sidecar_stage):
            if staged is not None:
                staged.unlink(missing_ok=True)
        if artifact_committed and sidecar_committed:
            lock.unlink(missing_ok=True)
            _fsync_directory(path.parent)
        elif not artifact_committed and not sidecar_committed:
            lock.unlink(missing_ok=True)


def require_complete_artifact_pair(path: Path) -> Path:
    sidecar = digest_path(path)
    lock = path.with_suffix(path.suffix + ".write.lock")
    if lock.exists():
        raise RuntimeError("INCOMPLETE_ARTIFACT_PAIR")
    if not path.is_file() or not sidecar.is_file():
        raise RuntimeError("ARTIFACT_PAIR_INCOMPLETE")
    return sidecar


def _stage_bytes(parent: Path, name: str, content: bytes) -> Path:
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{name}.",
        suffix=".staging",
        dir=parent,
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
