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
from strategy_catalog.paper_activation import PaperActivationCatalogSnapshot


class AtomicStrategyCatalogService:
    def __init__(
        self,
        repository: AtomicStrategyRepository,
        templates: Iterable[StrategyTemplate],
    ) -> None:
        self._repository = repository
        self._templates = {template.strategy_id: template for template in templates}

    def sync_templates(self) -> None:
        for template in self._templates.values():
            self._repository.upsert_template(template)

    def close(self) -> None:
        close = getattr(self._repository, "close", None)
        if callable(close):
            close()

    def create_draft(
        self,
        strategy_id: str,
        parameters: Mapping[str, object],
        *,
        actor_id: str,
        change_note: str = "",
        idempotency_key: str | None = None,
        operation_scope: str | None = None,
    ) -> StrategyDraft:
        template = self._template(strategy_id)
        return self._repository.create_draft(
            template,
            parameters,
            actor_id=actor_id,
            change_note=change_note,
            idempotency_key=idempotency_key,
            operation_scope=operation_scope,
        )

    def update_draft(
        self,
        draft_id: str,
        parameters: Mapping[str, object],
        *,
        expected_revision: int,
        actor_id: str,
        change_note: str,
        idempotency_key: str,
    ) -> StrategyDraft:
        draft = self._repository.get_draft(draft_id)
        return self._repository.update_draft(
            draft_id,
            self._template(draft.strategy_id),
            parameters,
            expected_revision=expected_revision,
            actor_id=actor_id,
            change_note=change_note,
            idempotency_key=idempotency_key,
        )

    def validate_draft(self, draft_id: str) -> dict[str, object]:
        draft = self._repository.get_draft(draft_id)
        template = self._template(draft.strategy_id)
        canonical = template.validate_parameters(draft.parameters)
        return {
            "valid": True,
            "draft_id": draft.draft_id,
            "revision": draft.revision,
            "canonical_parameters": canonical,
            "parameter_schema_version": template.parameter_schema.version,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
            "template_digest": template.template_digest,
            "implementation_digest": template.implementation_digest,
        }

    def clone_version(
        self,
        strategy_version_id: str,
        *,
        actor_id: str,
        change_note: str,
        idempotency_key: str,
    ) -> StrategyDraft:
        version = self._repository.get_version(strategy_version_id)
        return self.create_draft(
            version.strategy_id,
            version.parameters,
            actor_id=actor_id,
            change_note=change_note,
            idempotency_key=idempotency_key,
            operation_scope=f"strategy-version:clone:{strategy_version_id}",
        )

    def publish(self, request: PublishStrategyRequest) -> PublishStrategyResult:
        replay = self._repository.replay_publish(request)
        if replay is not None:
            return replay
        draft = self._repository.get_draft(request.draft_id)
        return self._repository.publish_draft(request, self._template(draft.strategy_id))

    def get_draft(self, draft_id: str) -> StrategyDraft:
        return self._repository.get_draft(draft_id)

    def list_drafts(self, strategy_id: str | None = None) -> tuple[StrategyDraft, ...]:
        return self._repository.list_drafts(strategy_id)

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        return self._repository.get_version(strategy_version_id)

    def list_versions(self, strategy_id: str | None = None) -> tuple[StrategyVersion, ...]:
        return self._repository.list_versions(strategy_id)

    def diff_versions(self, left_id: str, right_id: str) -> dict[str, object]:
        left = self.get_version(left_id)
        right = self.get_version(right_id)
        keys = sorted(set(left.parameters) | set(right.parameters))
        changes = [
            {"parameter": key, "left": left.parameters.get(key), "right": right.parameters.get(key)}
            for key in keys
            if left.parameters.get(key) != right.parameters.get(key)
        ]
        return {
            "left_strategy_version_id": left.strategy_version_id,
            "right_strategy_version_id": right.strategy_version_id,
            "same_strategy": left.strategy_id == right.strategy_id,
            "changes": changes,
        }

    def templates(self) -> tuple[StrategyTemplate, ...]:
        return tuple(sorted(self._templates.values(), key=lambda item: item.strategy_id))

    def template(self, strategy_id: str) -> StrategyTemplate:
        return self._template(strategy_id)

    def save_strategy_set(
        self,
        snapshot: ExactStrategySetSnapshot,
        *,
        actor_id: str,
        idempotency_key: str | None = None,
        change_note: str = "",
    ) -> bool:
        return self._repository.save_strategy_set(
            snapshot,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            change_note=change_note,
        )

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot:
        return self._repository.get_strategy_set(strategy_set_version_id)

    def list_strategy_sets(self) -> tuple[ExactStrategySetSnapshot, ...]:
        return self._repository.list_strategy_sets()

    def is_strategy_set_archived(self, strategy_set_version_id: str) -> bool:
        return self._repository.is_strategy_set_archived(strategy_set_version_id)

    def archive_strategy_set(
        self,
        strategy_set_version_id: str,
        *,
        actor_id: str,
        idempotency_key: str,
        change_note: str,
    ) -> bool:
        return self._repository.archive_strategy_set(
            strategy_set_version_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            change_note=change_note,
        )

    def get_paper_activation_snapshot(
        self,
        strategy_set_version_id: str,
    ) -> PaperActivationCatalogSnapshot:
        return self._repository.get_paper_activation_snapshot(
            strategy_set_version_id
        )

    def record_audit_event(self, **event: Any) -> dict[str, Any]:
        return self._repository.record_audit_event(**event)

    def list_audit_events(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        return self._repository.list_audit_events(limit=limit)

    def _template(self, strategy_id: str) -> StrategyTemplate:
        try:
            return self._templates[strategy_id]
        except KeyError as error:
            raise ValueError(f"未知或未部署的 atomic strategy：{strategy_id}") from error


def build_atomic_strategy_service(
    *,
    database_backend: str,
    connection: Any | None = None,
    pool: Any | None = None,
    owns_pool: bool = False,
    templates: Iterable[StrategyTemplate],
) -> AtomicStrategyCatalogService:
    if database_backend.strip().lower() != "postgresql":
        raise ValueError("atomic strategy persistence 只支援 PostgreSQL；禁止 SQLite fallback")
    if (connection is None) == (pool is None):
        raise ValueError("atomic strategy persistence 無可用 PostgreSQL connection 或 pool")
    service = AtomicStrategyCatalogService(
        PostgresAtomicStrategyRepository(connection, pool=pool, owns_pool=owns_pool),
        templates,
    )
    service.sync_templates()
    return service
