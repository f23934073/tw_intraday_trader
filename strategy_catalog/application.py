"""Application service for the PostgreSQL-only atomic strategy catalog."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from strategy_catalog.drafts import (
    PublishStrategyRequest,
    PublishStrategyResult,
    StrategyDraft,
    StrategyTemplate,
    StrategyVersion,
)
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository
from strategy_catalog.repository import AtomicStrategyRepository
from strategy_catalog.sets import ExactStrategySetSnapshot


class AtomicStrategyCatalogService:
    def __init__(
        self,
        repository: AtomicStrategyRepository,
        templates: Iterable[StrategyTemplate],
    ) -> None:
        self._repository = repository
        self._templates = {template.strategy_id: template for template in templates}
        if not self._templates:
            raise ValueError("atomic strategy registry 不可為空")

    def sync_templates(self) -> None:
        for template in self._templates.values():
            self._repository.upsert_template(template)

    def create_draft(
        self,
        strategy_id: str,
        parameters: Mapping[str, object],
        *,
        actor_id: str,
        change_note: str = "",
    ) -> StrategyDraft:
        template = self._template(strategy_id)
        return self._repository.create_draft(
            template,
            parameters,
            actor_id=actor_id,
            change_note=change_note,
        )

    def publish(self, request: PublishStrategyRequest) -> PublishStrategyResult:
        draft = self._repository.get_draft(request.draft_id)
        return self._repository.publish_draft(request, self._template(draft.strategy_id))

    def get_draft(self, draft_id: str) -> StrategyDraft:
        return self._repository.get_draft(draft_id)

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        return self._repository.get_version(strategy_version_id)

    def save_strategy_set(
        self,
        snapshot: ExactStrategySetSnapshot,
        *,
        actor_id: str,
    ) -> bool:
        return self._repository.save_strategy_set(snapshot, actor_id=actor_id)

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot:
        return self._repository.get_strategy_set(strategy_set_version_id)

    def _template(self, strategy_id: str) -> StrategyTemplate:
        try:
            return self._templates[strategy_id]
        except KeyError as error:
            raise ValueError(f"未知或未部署的 atomic strategy：{strategy_id}") from error


def build_atomic_strategy_service(
    *,
    database_backend: str,
    connection: Any,
    templates: Iterable[StrategyTemplate],
) -> AtomicStrategyCatalogService:
    if database_backend.strip().lower() != "postgresql":
        raise ValueError("atomic strategy persistence 只支援 PostgreSQL；禁止 SQLite fallback")
    if connection is None:
        raise ValueError("atomic strategy persistence 無可用 PostgreSQL connection")
    service = AtomicStrategyCatalogService(
        PostgresAtomicStrategyRepository(connection),
        templates,
    )
    service.sync_templates()
    return service
