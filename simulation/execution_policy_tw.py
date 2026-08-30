"""Local Paper adapter over the sealed pure Taiwan execution/cost policies."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from threading import RLock

from backtest.cost_policy_tw import (
    calculate_costs,
    cost_policy_readiness_reason,
    verify_cost_policy_snapshot,
)
from backtest.execution_policy_tw import (
    BOARD_LOT_SHARES,
    adverse_tick_price,
    execution_policy_readiness_reason,
    is_on_tick,
    verify_execution_policy_snapshot,
)
from market_data.session_evidence import (
    ServerExecutionEvidenceSnapshot,
    SessionPhase,
)
from trading.canonical_values import canonical_decimal_string
from trading.exposure import ExecutionReasonCategory, PositionAction
from trading.no_overnight import NoOvernightReason
from trading.no_overnight_admission import (
    FinalExecutionAdmissionPolicy,
    evaluate_final_execution_admission,
)
from trading.risk import CommandSide, OrderCommand


class LocalPaperAllocationSource(StrEnum):
    CONTINUOUS_BIDASK = "CONTINUOUS_BIDASK"
    ISOLATED_CLOSING_AUCTION = "ISOLATED_CLOSING_AUCTION"


@dataclass(frozen=True)
class LocalPaperExecutionAllocation:
    """One costed allocation derived from an admitted immutable snapshot."""

    allocation_id: str
    source: LocalPaperAllocationSource
    quantity_shares: int
    pre_cost_price: Decimal
    fill_price: Decimal
    commission: Decimal
    tax: Decimal
    slippage: Decimal
    execution_policy_digest: str
    cost_policy_digest: str
    evidence_snapshot_digest: str
    auction_event_id: str | None = None
    auction_event_digest: str | None = None

    @property
    def total_cost(self) -> Decimal:
        return self.commission + self.tax + self.slippage


@dataclass(frozen=True)
class LocalPaperExecutionDecision:
    allocation: LocalPaperExecutionAllocation | None
    reason: NoOvernightReason | None

    def __post_init__(self) -> None:
        if (self.allocation is None) == (self.reason is None):
            raise ValueError("execution decision must contain allocation xor reason")

    @property
    def allocated(self) -> bool:
        return self.allocation is not None


class TwLocalPaperExecutionPolicyAdapter:
    """Allocate from BidAsk or one isolated 13:30 event, never a close bar."""

    def __init__(
        self,
        *,
        execution_policy_snapshot: Mapping[str, object],
        cost_policy_snapshot: Mapping[str, object],
        admission_policy: FinalExecutionAdmissionPolicy,
        allocated_auction_sessions: Mapping[tuple[date, str], str],
    ) -> None:
        self._execution_policy = verify_execution_policy_snapshot(execution_policy_snapshot)
        execution_reason = execution_policy_readiness_reason(self._execution_policy)
        if execution_reason is not None:
            raise ValueError(execution_reason)
        self._cost_policy = verify_cost_policy_snapshot(cost_policy_snapshot)
        cost_reason = cost_policy_readiness_reason(self._cost_policy)
        if cost_reason is not None:
            raise ValueError(cost_reason)
        if not isinstance(admission_policy, FinalExecutionAdmissionPolicy):
            raise TypeError("admission_policy must be FinalExecutionAdmissionPolicy")
        if (
            self._execution_policy["snapshot_digest"] != admission_policy.execution_policy_digest
            or self._cost_policy["snapshot_digest"] != admission_policy.cost_policy_digest
        ):
            raise ValueError("IDENTITY_MISMATCH: sealed policy digest drift")
        restored: dict[tuple[date, str], str] = {}
        for raw_key, digest in allocated_auction_sessions.items():
            session_date, symbol = raw_key
            normalized_symbol = str(symbol).strip().upper()
            if (
                not isinstance(session_date, date)
                or not normalized_symbol
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError("allocated auction session identity is invalid")
            restored[(session_date, normalized_symbol)] = digest
        self._admission_policy = admission_policy
        self._allocated_auction_sessions = restored
        self._lock = RLock()

    @property
    def allocated_auction_sessions(self) -> dict[tuple[date, str], str]:
        with self._lock:
            return dict(self._allocated_auction_sessions)

    def allocate_close_long(
        self,
        *,
        command: OrderCommand,
        evidence: ServerExecutionEvidenceSnapshot,
        evaluated_at: datetime,
    ) -> LocalPaperExecutionDecision:
        """Return one deterministic fill allocation or one stable reason."""

        if not isinstance(evidence, ServerExecutionEvidenceSnapshot) or not isinstance(
            command, OrderCommand
        ):
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=NoOvernightReason.IDENTITY_MISMATCH,
            )
        if (
            command.side is not CommandSide.SELL
            or command.position_action is not PositionAction.CLOSE_LONG
            or command.execution_reason_category is not ExecutionReasonCategory.OPERATIONAL_RISK
            or command.target_exposure_id is None
        ):
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=NoOvernightReason.IDENTITY_MISMATCH,
            )
        admission = evaluate_final_execution_admission(
            command=command,
            snapshot=evidence,
            evaluated_at=evaluated_at,
            policy=self._admission_policy,
        )
        if not admission.approved:
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=admission.reasons[0],
            )

        if evidence.session_phase is SessionPhase.CONTINUOUS:
            assert evidence.bid_ask is not None
            assert evidence.bid_ask.best_bid_price is not None
            assert evidence.bid_ask.best_bid_quantity is not None
            source = LocalPaperAllocationSource.CONTINUOUS_BIDASK
            pre_cost_price = evidence.bid_ask.best_bid_price
            observable_shares = evidence.bid_ask.best_bid_quantity
            auction_event_id = None
            auction_event_digest = None
        elif evidence.session_phase is SessionPhase.CLOSING_AUCTION:
            assert evidence.isolated_auction_price is not None
            assert evidence.isolated_auction_matchable_volume is not None
            assert evidence.isolated_auction_volume_unit is not None
            assert evidence.isolated_auction_event_id is not None
            assert evidence.isolated_auction_event_digest is not None
            source = LocalPaperAllocationSource.ISOLATED_CLOSING_AUCTION
            pre_cost_price = evidence.isolated_auction_price
            observable_shares = evidence.isolated_auction_matchable_volume
            if evidence.isolated_auction_volume_unit == "COMMON_LOTS":
                observable_shares *= BOARD_LOT_SHARES
            elif evidence.isolated_auction_volume_unit != "SHARES":
                return LocalPaperExecutionDecision(
                    allocation=None,
                    reason=NoOvernightReason.IDENTITY_MISMATCH,
                )
            auction_event_id = evidence.isolated_auction_event_id
            auction_event_digest = evidence.isolated_auction_event_digest
        else:
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=NoOvernightReason.UNSUPPORTED_SESSION_REGIME,
            )

        participation = Decimal(str(self._execution_policy["max_participation_rate"]))
        allocatable = (
            int((Decimal(observable_shares) * participation) // BOARD_LOT_SHARES) * BOARD_LOT_SHARES
        )
        quantity = min(command.quantity_shares, allocatable)
        if quantity <= 0:
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=(
                    NoOvernightReason.ZERO_AUCTION_MATCHABLE_VOLUME
                    if source is LocalPaperAllocationSource.ISOLATED_CLOSING_AUCTION
                    else NoOvernightReason.NO_EXECUTABLE_LIQUIDITY
                ),
            )

        assert evidence.pit_lower_limit_price is not None
        assert evidence.pit_upper_limit_price is not None
        if (
            pre_cost_price < evidence.pit_lower_limit_price
            or pre_cost_price > evidence.pit_upper_limit_price
            or not is_on_tick(pre_cost_price)
        ):
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=NoOvernightReason.RECOVERY_REQUIRED,
            )
        fill_price = adverse_tick_price(
            pre_cost_price,
            side="EXIT",
            slippage_bps=str(self._cost_policy["slippage_bps"]),
            lower_limit_price=evidence.pit_lower_limit_price,
            upper_limit_price=evidence.pit_upper_limit_price,
        )
        if fill_price is None or command.limit_price > fill_price:
            return LocalPaperExecutionDecision(
                allocation=None,
                reason=NoOvernightReason.NO_EXECUTABLE_LIQUIDITY,
            )
        costs = calculate_costs(
            pre_cost_price=pre_cost_price,
            post_cost_price=fill_price,
            shares=quantity,
            side="EXIT",
            trade_date=evidence.session_date,
            is_day_trade=True,
            cost_policy_snapshot=self._cost_policy,
        )
        identity = {
            "command_id": command.command_id,
            "semantic_action_key": command.idempotency_key,
            "source": source.value,
            "quantity_shares": quantity,
            "pre_cost_price": canonical_decimal_string(pre_cost_price),
            "fill_price": canonical_decimal_string(fill_price),
            "evidence_snapshot_digest": evidence.digest,
            "auction_event_id": auction_event_id,
            "auction_event_digest": auction_event_digest,
            "execution_policy_digest": self._execution_policy["snapshot_digest"],
            "cost_policy_digest": self._cost_policy["snapshot_digest"],
        }
        allocation_id = (
            "local_paper_allocation_v1_"
            + hashlib.sha256(
                json.dumps(
                    identity,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        allocation = LocalPaperExecutionAllocation(
            allocation_id=allocation_id,
            source=source,
            quantity_shares=quantity,
            pre_cost_price=pre_cost_price,
            fill_price=fill_price,
            commission=costs.commission,
            tax=costs.tax,
            slippage=costs.slippage,
            execution_policy_digest=str(self._execution_policy["snapshot_digest"]),
            cost_policy_digest=str(self._cost_policy["snapshot_digest"]),
            evidence_snapshot_digest=evidence.digest,
            auction_event_id=auction_event_id,
            auction_event_digest=auction_event_digest,
        )
        if source is LocalPaperAllocationSource.ISOLATED_CLOSING_AUCTION:
            key = (evidence.session_date, evidence.symbol)
            assert auction_event_digest is not None
            with self._lock:
                if key in self._allocated_auction_sessions:
                    return LocalPaperExecutionDecision(
                        allocation=None,
                        reason=NoOvernightReason.RECOVERY_REQUIRED,
                    )
                self._allocated_auction_sessions[key] = auction_event_digest
        return LocalPaperExecutionDecision(allocation=allocation, reason=None)
