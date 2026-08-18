"""Pure, versioned RiskGate contracts for future local-paper command routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


RISK_GATE_VERSION = "risk-gate-v1"


class CommandOrigin(StrEnum):
    MANUAL_WEB = "MANUAL_WEB"
    STRATEGY_AUTOMATED = "STRATEGY_AUTOMATED"


class CommandSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class RiskDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class RiskReason(StrEnum):
    STRATEGY_ORIGIN_DISABLED = "STRATEGY_ORIGIN_DISABLED"
    DATA_HEALTH_UNHEALTHY = "DATA_HEALTH_UNHEALTHY"
    MARKET_CLOSED = "MARKET_CLOSED"
    INSTRUMENT_NOT_TRADABLE = "INSTRUMENT_NOT_TRADABLE"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    ORDER_NOTIONAL_LIMIT = "ORDER_NOTIONAL_LIMIT"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    POSITION_NOTIONAL_LIMIT = "POSITION_NOTIONAL_LIMIT"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"
    PENDING_ORDER_DUPLICATE = "PENDING_ORDER_DUPLICATE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    BOOK_UNAVAILABLE = "BOOK_UNAVAILABLE"
    BOOK_STALE = "BOOK_STALE"


@dataclass(frozen=True)
class OrderCommand:
    command_id: str
    session_id: str
    origin: CommandOrigin
    symbol: str
    side: CommandSide
    quantity_shares: int
    limit_price: Decimal
    idempotency_key: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.command_id, "command_id"),
            (self.session_id, "session_id"),
            (self.symbol, "symbol"),
            (self.idempotency_key, "idempotency_key"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")


@dataclass(frozen=True)
class RiskPolicy:
    version: str
    allow_strategy_origin: bool
    max_order_notional: Decimal
    max_position_notional: Decimal
    max_daily_loss: Decimal
    require_fresh_book: bool = False
    max_book_age_seconds: int = 15

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version must not be empty")
        for value, name in (
            (self.max_order_notional, "max_order_notional"),
            (self.max_position_notional, "max_position_notional"),
            (self.max_daily_loss, "max_daily_loss"),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_book_age_seconds < 0:
            raise ValueError("max_book_age_seconds must not be negative")


@dataclass(frozen=True)
class RiskSnapshot:
    data_health_state: str
    market_open: bool
    instrument_tradable: bool
    available_cash: Decimal
    current_position_shares: int
    pending_buy_shares: int
    pending_sell_shares: int
    daily_realized_pnl: Decimal
    same_side_pending_order: bool = False
    book_age_seconds: int | None = None

    def __post_init__(self) -> None:
        if min(
            self.current_position_shares,
            self.pending_buy_shares,
            self.pending_sell_shares,
        ) < 0:
            raise ValueError("position and pending quantities must not be negative")


@dataclass(frozen=True)
class RiskDecision:
    status: RiskDecisionStatus
    reasons: tuple[RiskReason, ...]
    approved_quantity_shares: int
    policy_version: str
    evaluated_at: datetime


class RiskGate:
    """Deterministic gate with no framework, provider, or broker dependencies."""

    def __init__(self, policy: RiskPolicy) -> None:
        self._policy = policy

    def evaluate(
        self,
        command: OrderCommand,
        snapshot: RiskSnapshot,
        *,
        evaluated_at: datetime,
    ) -> RiskDecision:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        blocked: list[RiskReason] = []
        rejected: list[RiskReason] = []

        if (
            command.origin is CommandOrigin.STRATEGY_AUTOMATED
            and not self._policy.allow_strategy_origin
        ):
            blocked.append(RiskReason.STRATEGY_ORIGIN_DISABLED)
        if snapshot.data_health_state != "HEALTHY":
            blocked.append(RiskReason.DATA_HEALTH_UNHEALTHY)
        if not snapshot.market_open:
            blocked.append(RiskReason.MARKET_CLOSED)
        if not snapshot.instrument_tradable:
            blocked.append(RiskReason.INSTRUMENT_NOT_TRADABLE)
        if snapshot.daily_realized_pnl <= -self._policy.max_daily_loss:
            blocked.append(RiskReason.DAILY_LOSS_LIMIT)
        if snapshot.same_side_pending_order:
            blocked.append(RiskReason.PENDING_ORDER_DUPLICATE)
        if self._policy.require_fresh_book:
            if snapshot.book_age_seconds is None:
                blocked.append(RiskReason.BOOK_UNAVAILABLE)
            elif snapshot.book_age_seconds > self._policy.max_book_age_seconds:
                blocked.append(RiskReason.BOOK_STALE)

        if command.quantity_shares <= 0:
            rejected.append(RiskReason.INVALID_QUANTITY)
        if command.limit_price <= 0:
            rejected.append(RiskReason.INVALID_PRICE)

        notional = command.quantity_shares * command.limit_price
        if notional > self._policy.max_order_notional:
            rejected.append(RiskReason.ORDER_NOTIONAL_LIMIT)
        if command.side is CommandSide.BUY:
            if notional > snapshot.available_cash:
                rejected.append(RiskReason.INSUFFICIENT_CASH)
            position_notional = (
                snapshot.current_position_shares
                + snapshot.pending_buy_shares
                + command.quantity_shares
            ) * command.limit_price
            if position_notional > self._policy.max_position_notional:
                rejected.append(RiskReason.POSITION_NOTIONAL_LIMIT)
        elif command.quantity_shares > (
            snapshot.current_position_shares - snapshot.pending_sell_shares
        ):
            rejected.append(RiskReason.INSUFFICIENT_POSITION)

        if blocked:
            return self._decision(
                RiskDecisionStatus.BLOCKED,
                blocked,
                evaluated_at,
            )
        if rejected:
            return self._decision(
                RiskDecisionStatus.REJECTED,
                rejected,
                evaluated_at,
            )
        return self._decision(
            RiskDecisionStatus.APPROVED,
            (),
            evaluated_at,
            approved_quantity_shares=command.quantity_shares,
        )

    def _decision(
        self,
        status: RiskDecisionStatus,
        reasons: list[RiskReason] | tuple[()],
        evaluated_at: datetime,
        *,
        approved_quantity_shares: int = 0,
    ) -> RiskDecision:
        return RiskDecision(
            status=status,
            reasons=tuple(sorted(reasons, key=lambda item: item.value)),
            approved_quantity_shares=approved_quantity_shares,
            policy_version=self._policy.version,
            evaluated_at=evaluated_at,
        )
