"""Application ports for the R6 atomic-entry benchmark.

Only PostgreSQL adapters implement mutation.  The public read port deliberately
excludes quarantine payload access so callers cannot bypass the family release
barrier.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .domain import MatrixSealBuild


class AtomicBenchmarkConflict(RuntimeError):
    """A durable R6 identity, idempotency key, or revision conflicts."""


class AtomicBenchmarkUnavailable(RuntimeError):
    """PostgreSQL-only R6 persistence is unavailable."""


class BenchmarkMatrixRepositoryPort(Protocol):
    def seal_matrix(
        self,
        *,
        build: MatrixSealBuild,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]: ...

    def activate_matrix_revision2(
        self,
        *,
        build: MatrixSealBuild,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]: ...

    def register_preflight(
        self,
        *,
        request: Mapping[str, Any],
        request_digest: str,
        manifest: Mapping[str, Any],
        artifact_locator: str,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]: ...

    def get_matrix(self, family_id: str) -> dict[str, Any]: ...

    def get_preflight_context(self, family_id: str) -> dict[str, Any]: ...

    def start_next_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        expected_family_head_sequence: int,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]: ...

    def transition_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        expected_status: str,
        next_status: str,
        retry_generation: int,
        outcome_code: str,
        progress: str | None,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]: ...


class BenchmarkVisibilityRepositoryPort(Protocol):
    def get_family_visibility(self, family_id: str) -> dict[str, Any]: ...

    def get_verified_public_bundle(self, family_id: str) -> dict[str, Any] | None: ...
