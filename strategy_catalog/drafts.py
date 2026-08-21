"""Framework-free Template, Draft, and immutable Version domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from strategy_catalog.domain import SessionPhase, StrategyRole
from strategy_catalog.parameter_schema import ParameterSchema, canonical_digest


@dataclass(frozen=True)
class StrategyTemplate:
    strategy_id: str
    display_name_zh_tw: str
    role: StrategyRole
    session_phase: SessionPhase
    implementation_version: str
    implementation_digest: str
    parameter_schema: ParameterSchema
    required_capabilities: tuple[str, ...]
    feature_requirements: tuple[Mapping[str, Any], ...]
    runtime_bindings: Mapping[str, str]
    description_zh_tw: str = ""

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.display_name_zh_tw.strip():
            raise ValueError("Strategy Template identity 不可為空")
        if self.role not in {
            StrategyRole.FILTER,
            StrategyRole.ENTRY,
            StrategyRole.EXIT,
            StrategyRole.CONTEXT,
        }:
            raise ValueError("atomic Strategy Template role 不可使用 legacy metadata role")
        if not self.implementation_version.strip() or not self.implementation_digest.strip():
            raise ValueError("Strategy Template implementation identity 不可為空")
        if not self.runtime_bindings:
            raise ValueError("Strategy Template 至少需要一個 allowlisted runtime binding")
        object.__setattr__(
            self,
            "required_capabilities",
            tuple(str(item).strip().upper() for item in self.required_capabilities),
        )
        object.__setattr__(self, "runtime_bindings", dict(self.runtime_bindings))
        object.__setattr__(
            self,
            "feature_requirements",
            tuple(dict(item) for item in self.feature_requirements),
        )

    @property
    def template_document(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "display_name_zh_tw": self.display_name_zh_tw,
            "role": self.role.value,
            "session_phase": self.session_phase.value,
            "implementation_version": self.implementation_version,
            "implementation_digest": self.implementation_digest,
            "parameter_schema": self.parameter_schema.schema_document,
            "required_capabilities": list(self.required_capabilities),
            "feature_requirements": [dict(item) for item in self.feature_requirements],
            "runtime_bindings": dict(self.runtime_bindings),
            "description_zh_tw": self.description_zh_tw,
        }

    @property
    def template_digest(self) -> str:
        return canonical_digest(self.template_document)

    def validate_parameters(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return self.parameter_schema.canonicalize(values)


@dataclass(frozen=True)
class StrategyDraft:
    draft_id: str
    strategy_id: str
    revision: int
    parameters: Mapping[str, Any]
    parameters_digest: str
    change_note: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    published_strategy_version_id: str | None = None
    published_event_id: str | None = None
    published_operation_id: str | None = None
    published_at: datetime | None = None

    @property
    def is_sealed(self) -> bool:
        return self.published_at is not None


@dataclass(frozen=True)
class StrategyVersion:
    strategy_version_id: str
    strategy_id: str
    source_draft_id: str
    version_number: int
    parameters: Mapping[str, Any]
    parameter_schema_version: str
    parameter_schema_digest: str
    parameters_digest: str
    template_digest: str
    implementation_digest: str
    configuration_digest: str
    change_note: str
    created_by: str
    created_at: datetime
    published_at: datetime


@dataclass(frozen=True)
class PublishStrategyRequest:
    draft_id: str
    idempotency_key: str
    expected_draft_revision: int
    actor_id: str
    actor_session_id: str
    change_note: str = ""

    def __post_init__(self) -> None:
        for field_name in ("draft_id", "idempotency_key", "actor_id", "actor_session_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} 不可為空")
        if self.expected_draft_revision <= 0:
            raise ValueError("expected_draft_revision 必須大於 0")

    @property
    def request_digest(self) -> str:
        return canonical_digest(
            {
                "contract_version": "strategy-publish-v1",
                "draft_id": self.draft_id,
                "expected_draft_revision": self.expected_draft_revision,
                "actor_id": self.actor_id,
                "actor_session_id": self.actor_session_id,
                "change_note": self.change_note,
            }
        )


@dataclass(frozen=True)
class PublishStrategyResult:
    publish_operation_id: str
    draft_id: str
    strategy_version_id: str
    published_event_id: str
    version_number: int
    configuration_digest: str
    result_digest: str
    replayed: bool = False
