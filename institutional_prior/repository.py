"""Persistence port for immutable institutional Candidate Prior artifacts."""

from __future__ import annotations

from typing import Protocol

from .domain import CandidatePriorArtifact

NON_DETERMINISTIC_REPLAY = "NON_DETERMINISTIC_REPLAY"
ARTIFACT_CONTRACT_MISMATCH = "ARTIFACT_CONTRACT_MISMATCH"
PERSISTED_ARTIFACT_MISMATCH = "PERSISTED_ARTIFACT_MISMATCH"


class CandidatePriorPersistenceError(RuntimeError):
    """Durable Candidate Prior state failed a frozen persistence invariant."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class CandidatePriorRepository(Protocol):
    def save(self, artifact: CandidatePriorArtifact) -> bool:
        """Persist once; return False for an exact idempotent replay."""

        ...

    def get(self, artifact_id: str) -> CandidatePriorArtifact | None:
        """Return a parity-verified artifact, or None when it is absent."""

        ...

    def close(self) -> None: ...
