"""Exact-version Strategy Set snapshots for new atomic-platform runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from strategy_catalog.domain import StrategyRole
from strategy_catalog.parameter_schema import canonical_digest


class CompositionPolicy(StrEnum):
    ANY = "ANY"
    ALL = "ALL"
    AT_LEAST_N = "AT_LEAST_N"


@dataclass(frozen=True)
class StrategySetMemberSnapshot:
    strategy_version_id: str
    strategy_id: str
    role: StrategyRole
    configuration_digest: str
    implementation_digest: str
    member_order: int
    attribution_priority: int

    def __post_init__(self) -> None:
        if self.role not in {StrategyRole.FILTER, StrategyRole.ENTRY, StrategyRole.EXIT}:
            raise ValueError("Strategy Set member role 必須是 FILTER、ENTRY 或 EXIT")
        if self.member_order < 0 or self.attribution_priority < 0:
            raise ValueError("Strategy Set order/priority 不可小於 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_version_id": self.strategy_version_id,
            "strategy_id": self.strategy_id,
            "role": self.role.value,
            "configuration_digest": self.configuration_digest,
            "implementation_digest": self.implementation_digest,
            "member_order": self.member_order,
            "attribution_priority": self.attribution_priority,
        }


@dataclass(frozen=True)
class ExactStrategySetSnapshot:
    strategy_set_version_id: str
    strategy_set_id: str
    version_number: int
    display_name_zh_tw: str
    stage: StrategyRole
    policy: CompositionPolicy
    members: tuple[StrategySetMemberSnapshot, ...]
    minimum_trigger_count: int = 1
    contract_version: str = "exact-strategy-set-v1"

    def __post_init__(self) -> None:
        if not self.strategy_set_version_id.strip() or not self.strategy_set_id.strip():
            raise ValueError("Strategy Set identity 不可為空")
        if self.version_number <= 0:
            raise ValueError("Strategy Set version_number 必須大於 0")
        if not self.display_name_zh_tw.strip():
            raise ValueError("Strategy Set display_name_zh_tw 不可為空")
        if self.stage not in {StrategyRole.FILTER, StrategyRole.ENTRY, StrategyRole.EXIT}:
            raise ValueError("Strategy Set stage 必須是 FILTER、ENTRY 或 EXIT")
        if not self.members:
            raise ValueError("Strategy Set 至少需要一個 exact-version member")
        version_ids = tuple(item.strategy_version_id for item in self.members)
        orders = tuple(item.member_order for item in self.members)
        priorities = tuple(item.attribution_priority for item in self.members)
        if len(set(version_ids)) != len(version_ids):
            raise ValueError("Strategy Set member version 不可重複")
        if len(set(orders)) != len(orders) or len(set(priorities)) != len(priorities):
            raise ValueError("Strategy Set member order/priority 不可重複")
        if any(item.role != self.stage for item in self.members):
            raise ValueError("Strategy Set member role 必須與 stage 相同")
        if self.policy is CompositionPolicy.AT_LEAST_N:
            if not 1 <= self.minimum_trigger_count <= len(self.members):
                raise ValueError("AT_LEAST_N 必須介於 1 與 member 數量")

    @property
    def ordered_members(self) -> tuple[StrategySetMemberSnapshot, ...]:
        return tuple(sorted(self.members, key=lambda item: item.member_order))

    @property
    def runtime_member_ids(self) -> tuple[str, ...]:
        return tuple(item.strategy_version_id for item in self.ordered_members)

    @property
    def priority_order(self) -> tuple[str, ...]:
        return tuple(
            item.strategy_version_id
            for item in sorted(self.members, key=lambda item: item.attribution_priority)
        )

    @property
    def snapshot_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "strategy_set_version_id": self.strategy_set_version_id,
            "strategy_set_id": self.strategy_set_id,
            "version_number": self.version_number,
            "display_name_zh_tw": self.display_name_zh_tw,
            "stage": self.stage.value,
            "policy": self.policy.value,
            "minimum_trigger_count": self.minimum_trigger_count,
            "members": [item.to_dict() for item in self.ordered_members],
        }
