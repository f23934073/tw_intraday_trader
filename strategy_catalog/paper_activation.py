"""Immutable catalog evidence admitted for one Local Paper activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.lifecycle import StrategyLifecycleStatus
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import ExactStrategySetSnapshot


@dataclass(frozen=True)
class StrategyLifecycleProjection:
    strategy_version_id: str
    status: StrategyLifecycleStatus
    last_sequence: int
    last_event_id: str
    projection_digest: str

    def __post_init__(self) -> None:
        if not self.strategy_version_id.strip() or not self.last_event_id.strip():
            raise ValueError("Lifecycle projection identity 不可為空")
        if self.last_sequence <= 0:
            raise ValueError("Lifecycle projection sequence 必須大於 0")
        if self.projection_digest != canonical_digest(self.projection_document):
            raise ValueError("Lifecycle projection digest 不一致")

    @property
    def projection_document(self) -> dict[str, Any]:
        return {
            "strategy_version_id": self.strategy_version_id,
            "status": self.status.value,
            "last_sequence": self.last_sequence,
            "last_event_id": self.last_event_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.projection_document, "projection_digest": self.projection_digest}


@dataclass(frozen=True)
class PaperActivationMember:
    version: StrategyVersion
    lifecycle: StrategyLifecycleProjection

    def __post_init__(self) -> None:
        if self.version.strategy_version_id != self.lifecycle.strategy_version_id:
            raise ValueError("Activation Version 與 lifecycle identity 不一致")


@dataclass(frozen=True)
class PaperActivationCatalogSnapshot:
    strategy_set: ExactStrategySetSnapshot
    members: tuple[PaperActivationMember, ...]

    def __post_init__(self) -> None:
        expected = self.strategy_set.runtime_member_ids
        actual = tuple(item.version.strategy_version_id for item in self.members)
        if actual != expected:
            raise ValueError("Activation members 與 exact Strategy Set 不一致")
