"""JSON-safe projections for the local atomic-strategy management UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from strategy_catalog.drafts import StrategyDraft, StrategyTemplate, StrategyVersion


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def template_projection(template: StrategyTemplate) -> dict[str, Any]:
    return {
        **template.template_document,
        "parameter_schema_digest": template.parameter_schema.schema_digest,
        "template_digest": template.template_digest,
    }


def draft_projection(draft: StrategyDraft) -> dict[str, Any]:
    return {
        "draft_id": draft.draft_id,
        "strategy_id": draft.strategy_id,
        "revision": draft.revision,
        "parameters": dict(draft.parameters),
        "parameters_digest": draft.parameters_digest,
        "change_note": draft.change_note,
        "created_by": draft.created_by,
        "updated_by": draft.updated_by,
        "created_at": _time(draft.created_at),
        "updated_at": _time(draft.updated_at),
        "is_sealed": draft.is_sealed,
        "published_strategy_version_id": draft.published_strategy_version_id,
        "published_event_id": draft.published_event_id,
        "published_operation_id": draft.published_operation_id,
        "published_at": _time(draft.published_at),
    }


def version_projection(version: StrategyVersion) -> dict[str, Any]:
    return {
        "strategy_version_id": version.strategy_version_id,
        "strategy_id": version.strategy_id,
        "source_draft_id": version.source_draft_id,
        "version_number": version.version_number,
        "parameters": dict(version.parameters),
        "parameter_schema_version": version.parameter_schema_version,
        "parameter_schema_digest": version.parameter_schema_digest,
        "parameters_digest": version.parameters_digest,
        "template_digest": version.template_digest,
        "implementation_digest": version.implementation_digest,
        "configuration_digest": version.configuration_digest,
        "change_note": version.change_note,
        "created_by": version.created_by,
        "created_at": _time(version.created_at),
        "published_at": _time(version.published_at),
    }
