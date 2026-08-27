"""Single public visibility barrier for R6 benchmark results."""

from __future__ import annotations

from typing import Any

from .repository import BenchmarkVisibilityRepositoryPort


class BenchmarkResultReader:
    """Never expose quarantine evidence before a verified family release."""

    def __init__(self, repository: BenchmarkVisibilityRepositoryPort) -> None:
        self._repository = repository

    def read_family(self, family_id: str) -> dict[str, Any]:
        visibility = self._repository.get_family_visibility(family_id)
        if visibility.get("release_state") != "RELEASED":
            return visibility
        public = self._repository.get_verified_public_bundle(family_id)
        if public is None:
            raise RuntimeError("R6_PUBLIC_BUNDLE_INTEGRITY_ERROR")
        return public
