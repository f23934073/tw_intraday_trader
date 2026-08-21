"""Persistence port and stable conflict codes for atomic strategy versions."""

from __future__ import annotations

from typing import Mapping, Protocol

from strategy_catalog.drafts import (
    PublishStrategyRequest,
    PublishStrategyResult,
    StrategyDraft,
    StrategyTemplate,
    StrategyVersion,
)
from strategy_catalog.sets import ExactStrategySetSnapshot


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
    ) -> StrategyDraft: ...

    def get_draft(self, draft_id: str) -> StrategyDraft: ...

    def get_version(self, strategy_version_id: str) -> StrategyVersion: ...

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
    ) -> bool: ...

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot: ...
