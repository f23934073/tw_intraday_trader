"""Framework-free contracts for the historical backtest bounded context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum
from typing import Any, Mapping

from strategy_catalog.domain import StrategyDefinition, StrategySide

__all__ = ["StrategyDefinition", "StrategySide"]


def decimal(value: Decimal | int | float | str) -> Decimal:
    """Build a Decimal without carrying binary-float rounding into accounting."""

    return value if isinstance(value, Decimal) else Decimal(str(value))


def canonical_json(value: Mapping[str, Any] | list[Any]) -> str:
    """Stable JSON used for snapshots, idempotency and reproducibility digests."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Mapping[str, Any] | list[Any] | str) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AggregationPolicy(StrEnum):
    ANY = "ANY"
    ALL = "ALL"
    AT_LEAST_N = "AT_LEAST_N"


class EvaluationStatus(StrEnum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BLOCKED = "BLOCKED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    PREFLIGHT = "PREFLIGHT"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class HistoricalBar:
    """A canonical historical OHLCV bar.  Timestamps must be timezone aware."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    name: str = ""
    market: str = ""
    amount: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol 不可為空")
        if self.timestamp.tzinfo is None:
            raise ValueError("歷史 Kbar timestamp 必須包含 timezone")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC 必須大於 0")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC 範圍不合法")
        if self.volume < 0:
            raise ValueError("volume 不可小於 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "timestamp": self.timestamp.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "amount": str(self.amount) if self.amount is not None else None,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HistoricalBar":
        timestamp = datetime.fromisoformat(str(value["timestamp"]))
        return cls(
            symbol=str(value["symbol"]),
            name=str(value.get("name") or ""),
            market=str(value.get("market") or ""),
            timestamp=timestamp,
            open=decimal(value["open"]),
            high=decimal(value["high"]),
            low=decimal(value["low"]),
            close=decimal(value["close"]),
            volume=int(value["volume"]),
            amount=(decimal(value["amount"]) if value.get("amount") is not None else None),
        )


@dataclass(frozen=True)
class StrategySetSnapshot:
    """Immutable entry/exit selections and aggregation rules for one run."""

    entry_strategy_ids: tuple[str, ...]
    exit_strategy_ids: tuple[str, ...]
    entry_policy: AggregationPolicy = AggregationPolicy.ANY
    exit_policy: AggregationPolicy = AggregationPolicy.ANY
    entry_min_trigger_count: int = 1
    exit_min_trigger_count: int = 1
    priority_order: tuple[str, ...] = ()
    version: str = "v1"

    def __post_init__(self) -> None:
        entries = tuple(str(item).strip() for item in self.entry_strategy_ids)
        exits = tuple(str(item).strip() for item in self.exit_strategy_ids)
        priority = tuple(str(item).strip() for item in self.priority_order)
        object.__setattr__(self, "entry_strategy_ids", entries)
        object.__setattr__(self, "exit_strategy_ids", exits)
        object.__setattr__(self, "priority_order", priority)
        if not entries or any(not item for item in entries):
            raise ValueError("至少要選擇一個買入策略")
        if not exits or any(not item for item in exits):
            raise ValueError("至少要選擇一個賣出策略")
        if len(set(entries)) != len(entries):
            raise ValueError("買入策略不可重複選擇")
        if len(set(exits)) != len(exits):
            raise ValueError("賣出策略不可重複選擇")
        if len(set(priority)) != len(priority):
            raise ValueError("策略優先順序不可重複")
        unknown_priority = set(priority) - set(entries) - set(exits)
        if unknown_priority:
            raise ValueError("策略優先順序只能包含本次已選策略")
        self._validate_policy(
            self.entry_policy,
            self.entry_min_trigger_count,
            len(entries),
            "買入",
        )
        self._validate_policy(
            self.exit_policy,
            self.exit_min_trigger_count,
            len(exits),
            "賣出",
        )

    @staticmethod
    def _validate_policy(
        policy: AggregationPolicy,
        minimum: int,
        count: int,
        label: str,
    ) -> None:
        if policy is AggregationPolicy.AT_LEAST_N and not 1 <= minimum <= count:
            raise ValueError(f"{label} AT_LEAST_N 必須介於 1 與已選策略數量")

    @property
    def snapshot_digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_strategy_ids": list(self.entry_strategy_ids),
            "exit_strategy_ids": list(self.exit_strategy_ids),
            "entry_policy": self.entry_policy.value,
            "exit_policy": self.exit_policy.value,
            "entry_min_trigger_count": self.entry_min_trigger_count,
            "exit_min_trigger_count": self.exit_min_trigger_count,
            "priority_order": list(self.priority_order),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StrategySetSnapshot":
        return cls(
            entry_strategy_ids=tuple(str(item) for item in value["entry_strategy_ids"]),
            exit_strategy_ids=tuple(str(item) for item in value["exit_strategy_ids"]),
            entry_policy=AggregationPolicy(str(value.get("entry_policy", "ANY"))),
            exit_policy=AggregationPolicy(str(value.get("exit_policy", "ANY"))),
            entry_min_trigger_count=int(value.get("entry_min_trigger_count", 1)),
            exit_min_trigger_count=int(value.get("exit_min_trigger_count", 1)),
            priority_order=tuple(str(item) for item in value.get("priority_order", ())),
            version=str(value.get("version", "v1")),
        )


@dataclass(frozen=True)
class BacktestRunConfig:
    dataset_id: str
    dataset_digest: str
    strategy_set: StrategySetSnapshot
    starting_cash: Decimal = Decimal("10000000")
    position_fraction: Decimal = Decimal("0.10")
    commission_rate: Decimal = Decimal("0.001425")
    sell_tax_rate: Decimal = Decimal("0.003")
    slippage_bps: Decimal = Decimal("5")
    min_lot_shares: int = 1000
    target_win_rate: Decimal = Decimal("0.50")
    minimum_oos_trades: int = 30
    max_drawdown_guardrail: Decimal = Decimal("0.20")
    engine_version: str = "backtest-engine-v1"
    experiment_id: str | None = None
    baseline_run_id: str | None = None
    parent_run_id: str | None = None
    change_note: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "starting_cash",
            "position_fraction",
            "commission_rate",
            "sell_tax_rate",
            "slippage_bps",
            "target_win_rate",
            "max_drawdown_guardrail",
        ):
            object.__setattr__(self, field_name, decimal(getattr(self, field_name)))
        if self.starting_cash <= 0:
            raise ValueError("starting_cash 必須大於 0")
        if not Decimal("0") < self.position_fraction <= Decimal("1"):
            raise ValueError("position_fraction 必須介於 0 與 1")
        if self.min_lot_shares <= 0:
            raise ValueError("min_lot_shares 必須大於 0")

    @property
    def config_digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "strategy_set": self.strategy_set.to_dict(),
            "starting_cash": str(self.starting_cash),
            "position_fraction": str(self.position_fraction),
            "commission_rate": str(self.commission_rate),
            "sell_tax_rate": str(self.sell_tax_rate),
            "slippage_bps": str(self.slippage_bps),
            "min_lot_shares": self.min_lot_shares,
            "target_win_rate": str(self.target_win_rate),
            "minimum_oos_trades": self.minimum_oos_trades,
            "max_drawdown_guardrail": str(self.max_drawdown_guardrail),
            "engine_version": self.engine_version,
            "experiment_id": self.experiment_id,
            "baseline_run_id": self.baseline_run_id,
            "parent_run_id": self.parent_run_id,
            "change_note": self.change_note,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BacktestRunConfig":
        return cls(
            dataset_id=str(value["dataset_id"]),
            dataset_digest=str(value["dataset_digest"]),
            strategy_set=StrategySetSnapshot.from_dict(value["strategy_set"]),
            starting_cash=decimal(value.get("starting_cash", "10000000")),
            position_fraction=decimal(value.get("position_fraction", "0.10")),
            commission_rate=decimal(value.get("commission_rate", "0.001425")),
            sell_tax_rate=decimal(value.get("sell_tax_rate", "0.003")),
            slippage_bps=decimal(value.get("slippage_bps", "5")),
            min_lot_shares=int(value.get("min_lot_shares", 1000)),
            target_win_rate=decimal(value.get("target_win_rate", "0.50")),
            minimum_oos_trades=int(value.get("minimum_oos_trades", 30)),
            max_drawdown_guardrail=decimal(value.get("max_drawdown_guardrail", "0.20")),
            engine_version=str(value.get("engine_version", "backtest-engine-v1")),
            experiment_id=value.get("experiment_id"),
            baseline_run_id=value.get("baseline_run_id"),
            parent_run_id=value.get("parent_run_id"),
            change_note=str(value.get("change_note", "")),
        )


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy_id: str
    strategy_name: str
    strategy_version: str
    side: StrategySide
    status: EvaluationStatus
    symbol: str
    event_at: datetime
    reason: str
    observed: Mapping[str, Any] = field(default_factory=dict)
    threshold: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "side": self.side.value,
            "status": self.status.value,
            "symbol": self.symbol,
            "event_at": self.event_at.isoformat(),
            "reason": self.reason,
            "observed": dict(self.observed),
            "threshold": dict(self.threshold),
        }


@dataclass(frozen=True)
class TradeDecision:
    decision_id: str
    symbol: str
    side: StrategySide
    event_at: datetime
    policy: AggregationPolicy
    triggered_strategy_ids: tuple[str, ...]
    primary_strategy_id: str
    evaluations: tuple[StrategyEvaluation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "event_at": self.event_at.isoformat(),
            "policy": self.policy.value,
            "triggered_strategy_ids": list(self.triggered_strategy_ids),
            "primary_strategy_id": self.primary_strategy_id,
            "evaluations": [evaluation.to_dict() for evaluation in self.evaluations],
        }


@dataclass(frozen=True)
class HistoricalFill:
    fill_id: str
    decision_id: str
    symbol: str
    side: StrategySide
    filled_at: datetime
    price: Decimal
    shares: int
    commission: Decimal
    tax: Decimal
    source: str

    @property
    def total_cost(self) -> Decimal:
        return self.commission + self.tax

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "filled_at": self.filled_at.isoformat(),
            "price": float(self.price),
            "shares": self.shares,
            "commission": float(self.commission),
            "tax": float(self.tax),
            "total_cost": float(self.total_cost),
            "source": self.source,
        }


@dataclass(frozen=True)
class ClosedTrade:
    trade_id: str
    symbol: str
    name: str
    entry_decision: TradeDecision
    exit_decision: TradeDecision
    entry_fill: HistoricalFill
    exit_fill: HistoricalFill
    gross_pnl: Decimal
    net_pnl: Decimal
    holding_minutes: int

    def to_dict(self) -> dict[str, Any]:
        entry_evaluations = [
            value.to_dict()
            for value in self.entry_decision.evaluations
            if value.status is EvaluationStatus.TRIGGERED
        ]
        exit_evaluations = [
            value.to_dict()
            for value in self.exit_decision.evaluations
            if value.status is EvaluationStatus.TRIGGERED
        ]
        entry_cost = self.entry_fill.price * self.entry_fill.shares + self.entry_fill.total_cost
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "name": self.name,
            "entry": self.entry_fill.to_dict(),
            "exit": self.exit_fill.to_dict(),
            "gross_pnl": float(self.gross_pnl),
            "net_pnl": float(self.net_pnl),
            "net_pnl_pct": float(self.net_pnl / entry_cost * Decimal("100")) if entry_cost else 0.0,
            "holding_minutes": self.holding_minutes,
            "entry_decision": self.entry_decision.to_dict(),
            "exit_decision": self.exit_decision.to_dict(),
            "entry_strategies": entry_evaluations,
            "exit_strategies": exit_evaluations,
        }


def lot_floor(shares: Decimal, lot_size: int) -> int:
    return int((shares / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size)
