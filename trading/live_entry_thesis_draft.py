"""Pure live EntryDecision and TradeThesisDraft builders.

This application boundary freezes an entry intent and its Thesis policy.  It
does not discover candidates, calculate scores, persist facts, submit orders,
create fills, activate a TradeThesis, or run Shadow decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading.trade_management import (
    EntryEvidence,
    ExpectedBehaviorPolicy,
    InvalidConditionSpec,
    LIVE_ENTRY_DECISION_BUILDER_VERSION,
    LiveEntryDecision,
    ThesisType,
    TradeSide,
    TradeThesisDraft,
    TradeTimestamp,
    build_live_entry_decision_id,
    build_live_entry_decision_input_digest,
    build_thesis_id,
)


LIVE_THESIS_DRAFT_BUILDER_VERSION = "live-thesis-draft-builder-v1"


@dataclass(frozen=True)
class LiveThesisDraftPolicy:
    policy_id: str
    strategy_id: str
    strategy_version: str
    thesis_type: ThesisType
    thesis_version: str
    side: TradeSide
    expected_behavior: ExpectedBehaviorPolicy
    invalid_conditions: tuple[InvalidConditionSpec, ...]
    builder_version: str = LIVE_THESIS_DRAFT_BUILDER_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.policy_id, "policy_id"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.thesis_version, "thesis_version"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.builder_version != LIVE_THESIS_DRAFT_BUILDER_VERSION:
            raise ValueError("unsupported live Thesis draft builder version")
        if self.expected_behavior.version != self.thesis_version:
            raise ValueError("expected behavior version must match thesis_version")
        if self.expected_behavior.policy_id != self.policy_id:
            raise ValueError("expected behavior policy_id must match draft policy")
        if not self.invalid_conditions:
            raise ValueError("invalid_conditions must not be empty")


class LiveEntryDecisionBuilder:
    """Freeze caller-selected live signal evidence into a deterministic intent."""

    __slots__ = ()

    def build(
        self,
        *,
        session_id: str,
        symbol: str,
        side: TradeSide,
        strategy_id: str,
        strategy_version: str,
        signal_at: TradeTimestamp,
        decided_at: TradeTimestamp,
        score: Decimal,
        matched_rules: tuple[str, ...],
        market_context_digest: str,
        entry_evidence: tuple[EntryEvidence, ...],
    ) -> LiveEntryDecision:
        canonical_rules = tuple(sorted(matched_rules))
        canonical_evidence = tuple(
            sorted(entry_evidence, key=lambda item: item.evidence_id)
        )
        input_digest = build_live_entry_decision_input_digest(
            builder_version=LIVE_ENTRY_DECISION_BUILDER_VERSION,
            session_id=session_id,
            symbol=symbol,
            side=side,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            signal_at=signal_at,
            decided_at=decided_at,
            score=score,
            matched_rules=canonical_rules,
            market_context_digest=market_context_digest,
            entry_evidence=canonical_evidence,
        )
        return LiveEntryDecision(
            decision_id=build_live_entry_decision_id(input_digest),
            builder_version=LIVE_ENTRY_DECISION_BUILDER_VERSION,
            session_id=session_id,
            symbol=symbol,
            side=side,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            signal_at=signal_at,
            decided_at=decided_at,
            score=score,
            matched_rules=canonical_rules,
            market_context_digest=market_context_digest,
            entry_evidence=canonical_evidence,
        )


class LiveTradeThesisDraftBuilder:
    """Apply one explicit versioned Thesis policy to an immutable entry intent."""

    __slots__ = ()

    def build(
        self,
        decision: LiveEntryDecision,
        policy: LiveThesisDraftPolicy,
    ) -> TradeThesisDraft:
        for actual, expected, field_name in (
            (decision.strategy_id, policy.strategy_id, "strategy_id"),
            (decision.strategy_version, policy.strategy_version, "strategy_version"),
            (decision.side, policy.side, "side"),
        ):
            if actual != expected:
                raise ValueError(f"entry decision does not match policy {field_name}")
        return TradeThesisDraft(
            thesis_id=build_thesis_id(
                decision.session_id,
                decision.decision_id,
                policy.thesis_type,
                policy.thesis_version,
            ),
            session_id=decision.session_id,
            symbol=decision.symbol,
            side=decision.side,
            strategy_id=decision.strategy_id,
            strategy_version=decision.strategy_version,
            thesis_type=policy.thesis_type,
            thesis_version=policy.thesis_version,
            decision_id=decision.decision_id,
            signal_at=decision.signal_at,
            created_at=decision.decided_at,
            entry_evidence=decision.entry_evidence,
            expected_behavior=policy.expected_behavior,
            invalid_conditions=policy.invalid_conditions,
        )
