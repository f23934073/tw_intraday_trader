"""Server-side allowlist for atomic strategy implementations."""

from __future__ import annotations

from typing import Iterable

from atomic_strategies.entries.above_vwap import AboveVwapEntryStrategy
from atomic_strategies.entries.breakout_previous_high import BreakoutPreviousHighEntryStrategy
from atomic_strategies.entries.rolling_return import RollingReturnEntryStrategy
from atomic_strategies.entries.volume_acceleration import (
    VolumeAccelerationEntryStrategy,
)
from atomic_strategies.protocol import AtomicStrategy


class AtomicStrategyRegistry:
    def __init__(self, strategies: Iterable[AtomicStrategy] | None = None) -> None:
        items = tuple(
            strategies
            or (
                AboveVwapEntryStrategy(),
                BreakoutPreviousHighEntryStrategy(),
                RollingReturnEntryStrategy(),
                VolumeAccelerationEntryStrategy(),
            )
        )
        self._strategies = {item.template.strategy_id: item for item in items}
        if len(self._strategies) != len(items):
            raise ValueError("atomic strategy_id 不可重複")

    def strategy(self, strategy_id: str) -> AtomicStrategy:
        try:
            return self._strategies[strategy_id]
        except KeyError as error:
            raise ValueError(f"未知或未部署的 atomic strategy：{strategy_id}") from error

    def templates(self):
        return tuple(item.template for item in self._strategies.values())
