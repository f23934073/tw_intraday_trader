"""Persistence port and stable conflict codes for atomic strategy versions."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from strategy_catalog.drafts import (
    PublishStrategyRequest,
    PublishStrategyResult,
    StrategyDraft,
    StrategyTemplate,
    StrategyVersion,
)
from strategy_catalog.sets import ExactStrategySetSnapshot
from strategy_catalog.paper_activation import PaperActivationCatalogSnapshot


class StrategyCatalogConflict(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class AtomicStrategyRepository(Protocol):
    def upsert_template(self, template: StrategyTemplate) -> None: ...

    def create_draft(
        self,
        template: StrategyTemplate,
        parameters: Mapping[str, object],
        *,
        actor_id: str,
        change_note: str = "",
        idempotency_key: str | None = None,
        operation_scope: str | None = None,
    ) -> StrategyDraft: ...

    def update_draft(
        self,
        draft_id: str,
        template: StrategyTemplate,
        parameters: Mapping[str, object],
        *,
        expected_revision: int,
        actor_id: str,
        change_note: str,
        idempotency_key: str,
    ) -> StrategyDraft: ...

    def get_draft(self, draft_id: str) -> StrategyDraft: ...

    def list_drafts(self, strategy_id: str | None = None) -> tuple[StrategyDraft, ...]: ...

    def get_version(self, strategy_version_id: str) -> StrategyVersion: ...

    def list_versions(self, strategy_id: str | None = None) -> tuple[StrategyVersion, ...]: ...

    def replay_publish(
        self,
        request: PublishStrategyRequest,
    ) -> PublishStrategyResult | None: ...

    def publish_draft(
        self,
        request: PublishStrategyRequest,
        template: StrategyTemplate,
    ) -> PublishStrategyResult: ...

    def save_strategy_set(
        self,
        snapshot: ExactStrategySetSnapshot,
        *,
        actor_id: str,
        idempotency_key: str | None = None,
        change_note: str = "",
    ) -> bool: ...

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot: ...

    def list_strategy_sets(self) -> tuple[ExactStrategySetSnapshot, ...]: ...

    def get_paper_activation_snapshot(
        self,
        strategy_set_version_id: str,
    ) -> PaperActivationCatalogSnapshot: ...

    def record_audit_event(self, **event: Any) -> dict[str, Any]: ...

    def list_audit_events(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]: ...
