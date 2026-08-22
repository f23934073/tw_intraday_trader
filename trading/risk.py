"""Pure, versioned RiskGate contracts for future local-paper command routing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading.canonical_values import canonical_decimal_string
from trading.trade_management import (
    ExitRecommendation,
    ExitRecommendationStatus,
)


RISK_GATE_VERSION = "risk-gate-v1"
EXIT_ELIGIBILITY_ID_VERSION = "exit-eligibility-id-v1"


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


class ExecutionEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    INELIGIBLE = "INELIGIBLE"


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
    strategy_id: str | None = None
    strategy_version: str | None = None
    attempt: int = 1
    predecessor_order_id: str | None = None

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
        if self.origin is CommandOrigin.STRATEGY_AUTOMATED:
            if not (self.strategy_id or "").strip():
                raise ValueError("automated strategy command requires strategy_id")
            if not (self.strategy_version or "").strip():
                raise ValueError("automated strategy command requires strategy_version")
        elif self.strategy_id is not None or self.strategy_version is not None:
            raise ValueError("manual command must not carry strategy identity")
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")
        if (self.attempt == 1) != (self.predecessor_order_id is None):
            raise ValueError("predecessor_order_id must match retry attempt")


@dataclass(frozen=True)
class RiskPolicy:
    version: str
    allow_strategy_origin: bool
    max_order_notional: Decimal
    max_position_notional: Decimal
    max_daily_loss: Decimal
    require_fresh_book: bool = False
    max_book_age_seconds: int = 15
    fresh_book_sides: frozenset[CommandSide] = frozenset(CommandSide)

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
        if not self.fresh_book_sides.issubset(frozenset(CommandSide)):
            raise ValueError("fresh_book_sides contains an unsupported side")

    @property
    def policy_digest(self) -> str:
        """Return the immutable identity of the effective Hard Risk policy."""

        encoded = json.dumps(
            _risk_policy_payload(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return _risk_policy_payload(self)


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
    daily_loss: Decimal | None = None

    def __post_init__(self) -> None:
        if min(
            self.current_position_shares,
            self.pending_buy_shares,
            self.pending_sell_shares,
        ) < 0:
            raise ValueError("position and pending quantities must not be negative")
        if self.daily_loss is not None and self.daily_loss < 0:
            raise ValueError("daily_loss must not be negative")


@dataclass(frozen=True)
class RiskDecision:
    status: RiskDecisionStatus
    reasons: tuple[RiskReason, ...]
    approved_quantity_shares: int
    policy_version: str
    evaluated_at: datetime


def _risk_policy_payload(policy: RiskPolicy) -> dict[str, object]:
    return {
        "version": policy.version,
        "allow_strategy_origin": policy.allow_strategy_origin,
        "max_order_notional": canonical_decimal_string(
            policy.max_order_notional
        ),
        "max_position_notional": canonical_decimal_string(
            policy.max_position_notional
        ),
        "max_daily_loss": canonical_decimal_string(policy.max_daily_loss),
        "require_fresh_book": policy.require_fresh_book,
        "max_book_age_seconds": policy.max_book_age_seconds,
        "fresh_book_sides": sorted(side.value for side in policy.fresh_book_sides),
    }


@dataclass(frozen=True)
class ExitEligibilityContext:
    snapshot_id: str
    session_id: str
    trade_id: str
    thesis_id: str
    snapshot: RiskSnapshot
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.snapshot_id, "snapshot_id"),
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")


@dataclass(frozen=True)
class ExecutionEligibility:
    eligibility_id: str
    recommendation_id: str
    session_id: str
    trade_id: str
    thesis_id: str
    status: ExecutionEligibilityStatus
    reasons: tuple[RiskReason, ...]
    eligible_quantity_shares: int
    gate_version: str
    policy_version: str
    evaluated_at: datetime
    input_digest: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.eligibility_id, "eligibility_id"),
            (self.recommendation_id, "recommendation_id"),
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
            (self.gate_version, "gate_version"),
            (self.policy_version, "policy_version"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if len(self.input_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_digest
        ):
            raise ValueError("input_digest must be a lowercase SHA-256 hex digest")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("reasons must not contain duplicates")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.status is ExecutionEligibilityStatus.ELIGIBLE:
            if self.reasons or self.eligible_quantity_shares <= 0:
                raise ValueError("ELIGIBLE requires positive quantity and no reasons")
        elif self.eligible_quantity_shares != 0 or not self.reasons:
            raise ValueError(
                "non-eligible status requires zero quantity and at least one reason"
            )


def _eligibility_input_digest(
    recommendation: ExitRecommendation,
    context: ExitEligibilityContext,
    policy: RiskPolicy,
) -> str:
    snapshot = context.snapshot
    payload = {
        "identity_version": EXIT_ELIGIBILITY_ID_VERSION,
        "gate_version": RISK_GATE_VERSION,
        "recommendation": {
            "recommendation_id": recommendation.recommendation_id,
            "session_id": recommendation.session_id,
            "trade_id": recommendation.trade_id,
            "thesis_id": recommendation.thesis_id,
            "exit_policy_version": recommendation.exit_policy_version,
            "status": recommendation.status.value,
            "primary_reason": recommendation.primary_reason.value,
            "triggered_reasons": [
                reason.value for reason in recommendation.triggered_reasons
            ],
            "updated_at": recommendation.updated_at.isoformat,
        },
        "context": {
            "snapshot_id": context.snapshot_id,
            "session_id": context.session_id,
            "trade_id": context.trade_id,
            "thesis_id": context.thesis_id,
            "evaluated_at": context.evaluated_at.isoformat(),
            "snapshot": {
                "data_health_state": snapshot.data_health_state,
                "market_open": snapshot.market_open,
                "instrument_tradable": snapshot.instrument_tradable,
                "available_cash": canonical_decimal_string(
                    snapshot.available_cash
                ),
                "current_position_shares": snapshot.current_position_shares,
                "pending_buy_shares": snapshot.pending_buy_shares,
                "pending_sell_shares": snapshot.pending_sell_shares,
                "daily_realized_pnl": canonical_decimal_string(
                    snapshot.daily_realized_pnl
                ),
                "daily_loss": (
                    canonical_decimal_string(snapshot.daily_loss)
                    if snapshot.daily_loss is not None
                    else None
                ),
                "same_side_pending_order": snapshot.same_side_pending_order,
                "book_age_seconds": snapshot.book_age_seconds,
            },
        },
        "policy": _risk_policy_payload(policy),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _eligibility_id(
    recommendation: ExitRecommendation,
    context: ExitEligibilityContext,
    input_digest: str,
) -> str:
    encoded = json.dumps(
        [
            EXIT_ELIGIBILITY_ID_VERSION,
            recommendation.recommendation_id,
            context.snapshot_id,
            input_digest,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return f"exit_eligibility_v1_{hashlib.sha256(encoded).hexdigest()}"


class RiskGate:
    """Deterministic gate with no framework, provider, or broker dependencies."""

    def __init__(self, policy: RiskPolicy) -> None:
        self._policy = policy

    @property
    def policy_digest(self) -> str:
        return self._policy.policy_digest

    @property
    def policy_payload(self) -> dict[str, object]:
        return self._policy.to_dict()

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
            command.side is CommandSide.BUY
            and command.origin is CommandOrigin.STRATEGY_AUTOMATED
            and not self._policy.allow_strategy_origin
        ):
            blocked.append(RiskReason.STRATEGY_ORIGIN_DISABLED)
        if snapshot.data_health_state != "HEALTHY":
            blocked.append(RiskReason.DATA_HEALTH_UNHEALTHY)
        if not snapshot.market_open:
            blocked.append(RiskReason.MARKET_CLOSED)
        if not snapshot.instrument_tradable:
            blocked.append(RiskReason.INSTRUMENT_NOT_TRADABLE)
        effective_daily_loss = (
            snapshot.daily_loss
            if snapshot.daily_loss is not None
            else max(Decimal("0"), -snapshot.daily_realized_pnl)
        )
        if (
            command.side is CommandSide.BUY
            and effective_daily_loss >= self._policy.max_daily_loss
        ):
            blocked.append(RiskReason.DAILY_LOSS_LIMIT)
        if snapshot.same_side_pending_order:
            blocked.append(RiskReason.PENDING_ORDER_DUPLICATE)
        if (
            self._policy.require_fresh_book
            and command.side in self._policy.fresh_book_sides
        ):
            if snapshot.book_age_seconds is None:
                blocked.append(RiskReason.BOOK_UNAVAILABLE)
            elif snapshot.book_age_seconds > self._policy.max_book_age_seconds:
                blocked.append(RiskReason.BOOK_STALE)

        if command.quantity_shares <= 0:
            rejected.append(RiskReason.INVALID_QUANTITY)
        if command.limit_price <= 0:
            rejected.append(RiskReason.INVALID_PRICE)

        notional = command.quantity_shares * command.limit_price
        if command.side is CommandSide.BUY:
            if notional > self._policy.max_order_notional:
                rejected.append(RiskReason.ORDER_NOTIONAL_LIMIT)
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

    def evaluate_exit_recommendation(
        self,
        recommendation: ExitRecommendation,
        context: ExitEligibilityContext,
    ) -> ExecutionEligibility:
        if recommendation.status is not ExitRecommendationStatus.ACTIVE:
            raise ValueError("exit eligibility requires an ACTIVE recommendation")
        for field_name in ("session_id", "trade_id", "thesis_id"):
            if getattr(context, field_name) != getattr(recommendation, field_name):
                raise ValueError(f"context {field_name} does not match recommendation")
        if context.evaluated_at < recommendation.updated_at.value:
            raise ValueError("eligibility evaluated_at cannot predate recommendation")

        snapshot = context.snapshot
        blocked: list[RiskReason] = []
        if snapshot.data_health_state != "HEALTHY":
            blocked.append(RiskReason.DATA_HEALTH_UNHEALTHY)
        if not snapshot.market_open:
            blocked.append(RiskReason.MARKET_CLOSED)
        if not snapshot.instrument_tradable:
            blocked.append(RiskReason.INSTRUMENT_NOT_TRADABLE)
        if snapshot.same_side_pending_order:
            blocked.append(RiskReason.PENDING_ORDER_DUPLICATE)
        if (
            self._policy.require_fresh_book
            and CommandSide.SELL in self._policy.fresh_book_sides
        ):
            if snapshot.book_age_seconds is None:
                blocked.append(RiskReason.BOOK_UNAVAILABLE)
            elif snapshot.book_age_seconds > self._policy.max_book_age_seconds:
                blocked.append(RiskReason.BOOK_STALE)

        available_quantity = (
            snapshot.current_position_shares - snapshot.pending_sell_shares
        )
        input_digest = _eligibility_input_digest(
            recommendation,
            context,
            self._policy,
        )
        common = {
            "eligibility_id": _eligibility_id(
                recommendation,
                context,
                input_digest,
            ),
            "recommendation_id": recommendation.recommendation_id,
            "session_id": recommendation.session_id,
            "trade_id": recommendation.trade_id,
            "thesis_id": recommendation.thesis_id,
            "gate_version": RISK_GATE_VERSION,
            "policy_version": self._policy.version,
            "evaluated_at": context.evaluated_at,
            "input_digest": input_digest,
        }
        if blocked:
            return ExecutionEligibility(
                status=ExecutionEligibilityStatus.BLOCKED,
                reasons=tuple(sorted(blocked, key=lambda item: item.value)),
                eligible_quantity_shares=0,
                **common,
            )
        if available_quantity <= 0:
            return ExecutionEligibility(
                status=ExecutionEligibilityStatus.INELIGIBLE,
                reasons=(RiskReason.INSUFFICIENT_POSITION,),
                eligible_quantity_shares=0,
                **common,
            )
        return ExecutionEligibility(
            status=ExecutionEligibilityStatus.ELIGIBLE,
            reasons=(),
            eligible_quantity_shares=available_quantity,
            **common,
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
