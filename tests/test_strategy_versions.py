from __future__ import annotations

import pytest

from strategy_catalog.domain import StrategyRole
from strategy_catalog.lifecycle import StrategyLifecycleStatus, ensure_lifecycle_transition
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


def _member(version_id: str, order: int) -> StrategySetMemberSnapshot:
    return StrategySetMemberSnapshot(
        strategy_version_id=version_id,
        strategy_id=f"strategy-{order}",
        role=StrategyRole.ENTRY,
        configuration_digest=f"config-{order}",
        implementation_digest=f"implementation-{order}",
        member_order=order,
        attribution_priority=order,
    )


def test_lifecycle_transition_table_keeps_retired_terminal() -> None:
    ensure_lifecycle_transition(
        StrategyLifecycleStatus.PUBLISHED,
        StrategyLifecycleStatus.REVIEWED,
    )
    ensure_lifecycle_transition(
        StrategyLifecycleStatus.PAUSED,
        StrategyLifecycleStatus.ACTIVE,
    )
    with pytest.raises(ValueError, match="不合法"):
        ensure_lifecycle_transition(
            StrategyLifecycleStatus.RETIRED,
            StrategyLifecycleStatus.ACTIVE,
        )


def test_exact_strategy_set_digest_and_order_are_deterministic() -> None:
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-version-1",
        strategy_set_id="set-1",
        version_number=1,
        display_name_zh_tw="進場組合",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ALL,
        members=(_member("version-b", 1), _member("version-a", 0)),
    )

    assert snapshot.runtime_member_ids == ("version-a", "version-b")
    assert snapshot.priority_order == ("version-a", "version-b")
    assert len(snapshot.snapshot_digest) == 64
