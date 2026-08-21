"""Pure Historical Tick replay validation for the Trade Management chain.

PR-TM-006 consumes existing immutable ``market-event-v1`` Tick envelopes.  It
does not read files, write a Journal, mutate a Position, build an OrderCommand,
or invoke any broker/runtime capability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from market_data.events import (
    EventEnvelope,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketStreamKind,
    TickEvent,
)
from market_data.serialization import serialize_event_envelope
from trading.canonical_values import canonical_decimal_string
from trading.exit_recommendation import (
    ExitPositionContext,
    ExitRecommendationEngine,
    ExitRecommendationResult,
)
from trading.risk import (
    ExecutionEligibility,
    ExitEligibilityContext,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)
from trading.thesis_monitor import (
    MarketContextStatus,
    ThesisEvaluation,
    ThesisMarketContext,
    ThesisMonitor,
)
from trading.trade_management import (
    BreakoutLevelLostSpec,
    ExitRecommendation,
    ReplayOutput,
    ReplayRunIdentity,
    ReplayVerification,
    ThesisStatus,
    TimestampRole,
    TimestampSource,
    TradeLifecycleState,
    TradeThesis,
    TradeTimestamp,
)


TRADE_MANAGEMENT_REPLAY_VERSION = "trade-management-replay-v1"
EMPTY_JOURNAL_DIGEST = hashlib.sha256(b"").hexdigest()


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_market_manifest_digest(events: tuple[EventEnvelope, ...]) -> str:
    """Digest the exact canonical event artifacts in their replay order."""

    artifacts = [
        json.loads(serialize_event_envelope(event))
        for event in events
    ]
    return _sha256(
        {
            "schema_version": MARKET_EVENT_SCHEMA_VERSION,
            "events": artifacts,
        }
    )


@dataclass(frozen=True)
class TradeManagementReplayInput:
    run_identity: ReplayRunIdentity
    thesis: TradeThesis
    events: tuple[EventEnvelope, ...]
    volume_baseline_shares: Decimal
    shares_per_lot: int
    remaining_quantity_shares: int
    risk_snapshot: RiskSnapshot
    risk_policy: RiskPolicy
    risk_snapshots: tuple[RiskSnapshot, ...] | None = None

    def __post_init__(self) -> None:
        if not self.events:
            raise ValueError("Trade Management replay requires Historical Tick events")
        if not self.volume_baseline_shares.is_finite():
            raise ValueError("volume_baseline_shares must be finite")
        if self.volume_baseline_shares <= 0:
            raise ValueError("volume_baseline_shares must be positive")
        if self.shares_per_lot <= 0:
            raise ValueError("shares_per_lot must be positive")
        if self.remaining_quantity_shares <= 0:
            raise ValueError("remaining_quantity_shares must be positive")
        if (
            self.risk_snapshots is not None
            and len(self.risk_snapshots) != len(self.events)
        ):
            raise ValueError("risk_snapshots must align one-for-one with events")

    def risk_snapshot_at(self, index: int) -> RiskSnapshot:
        if self.risk_snapshots is None:
            return self.risk_snapshot
        return self.risk_snapshots[index]


@dataclass(frozen=True)
class TradeManagementDecisionConfig:
    thesis: TradeThesis
    exit_policy_version: str
    volume_baseline_shares: Decimal
    shares_per_lot: int
    remaining_quantity_shares: int
    risk_policy: RiskPolicy

    def __post_init__(self) -> None:
        if not self.exit_policy_version.strip():
            raise ValueError("exit_policy_version must not be empty")
        if not self.volume_baseline_shares.is_finite():
            raise ValueError("volume_baseline_shares must be finite")
        if self.volume_baseline_shares <= 0:
            raise ValueError("volume_baseline_shares must be positive")
        if self.shares_per_lot <= 0:
            raise ValueError("shares_per_lot must be positive")
        if self.remaining_quantity_shares <= 0:
            raise ValueError("remaining_quantity_shares must be positive")


@dataclass(frozen=True)
class TradeManagementDecisionState:
    last_event_at: datetime | None = None
    last_ingress_sequence: int | None = None
    seen_event_ids: frozenset[str] = frozenset()
    highest_price: Decimal | None = None
    post_entry_volume_shares: int = 0
    volume_sample_count: int = 0
    completed_bar_count: int = 0
    completed_bars_below_vwap: int = 0
    consecutive_below_vwap: int = 0
    consecutive_below_breakout: int = 0
    vwap_evidence_complete: bool = True
    active_recommendation: ExitRecommendation | None = None
    prior_status: ThesisStatus | None = None
    current_minute: tuple[int, int, int, int, int] | None = None
    current_close: Decimal | None = None
    current_vwap: Decimal | None = None
    processed_step_count: int = 0
    decision_digest: str = _sha256([])


def _breakout_level(thesis: TradeThesis) -> Decimal:
    for condition in thesis.draft.invalid_conditions:
        if isinstance(condition, BreakoutLevelLostSpec):
            return condition.breakout_level
    raise ValueError("ORB replay requires a breakout-level invalid condition")


def _step_wire(step: "TradeManagementReplayStep") -> dict[str, object]:
    result = step.recommendation_result
    recommendation = result.recommendation
    eligibility = step.eligibility
    return {
        "sequence": step.sequence,
        "source_event_id": step.source_event_id,
        "evaluation": {
            "evaluation_id": step.evaluation.evaluation_id,
            "input_digest": step.evaluation.input_digest,
            "status": step.evaluation.status.value,
            "reason_codes": [item.value for item in step.evaluation.reason_codes],
        },
        "decision": {
            "decision_id": result.decision.decision_id,
            "action": result.decision.action.value,
            "evaluation_digest": result.decision.evaluation_digest,
            "triggered_reasons": [
                item.value for item in result.decision.triggered_reasons
            ],
        },
        "recommendation": (
            None
            if recommendation is None
            else {
                "recommendation_id": recommendation.recommendation_id,
                "status": recommendation.status.value,
                "primary_reason": recommendation.primary_reason.value,
                "triggered_reasons": [
                    item.value for item in recommendation.triggered_reasons
                ],
            }
        ),
        "eligibility": (
            None
            if eligibility is None
            else {
                "eligibility_id": eligibility.eligibility_id,
                "input_digest": eligibility.input_digest,
                "status": eligibility.status.value,
                "reasons": [item.value for item in eligibility.reasons],
                "eligible_quantity_shares": eligibility.eligible_quantity_shares,
                "gate_version": eligibility.gate_version,
                "policy_version": eligibility.policy_version,
            }
        ),
    }


@dataclass(frozen=True)
class TradeManagementReplayStep:
    sequence: int
    source_event_id: str
    market_context: ThesisMarketContext
    evaluation: ThesisEvaluation
    recommendation_result: ExitRecommendationResult
    eligibility: ExecutionEligibility | None

    def __post_init__(self) -> None:
        if self.sequence <= 0:
            raise ValueError("replay step sequence must be positive")
        if self.source_event_id != self.evaluation.source_event_id:
            raise ValueError("replay step event identity mismatch")
        recommendation = self.recommendation_result.recommendation
        if self.eligibility is not None and (
            recommendation is None
            or self.eligibility.recommendation_id
            != recommendation.recommendation_id
        ):
            raise ValueError("eligibility must bind to the step recommendation")


class TradeManagementDecisionKernel:
    """Apply one canonical Tick without persistence or execution authority."""

    __slots__ = ()

    def apply(
        self,
        config: TradeManagementDecisionConfig,
        state: TradeManagementDecisionState,
        event: EventEnvelope,
        *,
        risk_snapshot: RiskSnapshot,
    ) -> tuple[TradeManagementDecisionState, TradeManagementReplayStep | None]:
        self._validate_event(config.thesis, state, event)
        common_state = {
            "last_event_at": event.event_at,
            "last_ingress_sequence": event.ingress_sequence,
            "seen_event_ids": state.seen_event_ids | {event.event_id},
        }
        if event.event_at < config.thesis.filled_at.value:
            return replace(state, **common_state), None

        tick = event.payload
        assert isinstance(tick, TickEvent)
        breakout_level = _breakout_level(config.thesis)
        minute = (
            event.event_at.year,
            event.event_at.month,
            event.event_at.day,
            event.event_at.hour,
            event.event_at.minute,
        )
        completed_bar_count = state.completed_bar_count
        completed_bars_below_vwap = state.completed_bars_below_vwap
        consecutive_below_vwap = state.consecutive_below_vwap
        consecutive_below_breakout = state.consecutive_below_breakout
        vwap_evidence_complete = state.vwap_evidence_complete
        if state.current_minute is not None and minute != state.current_minute:
            completed_bar_count += 1
            assert state.current_close is not None
            if state.current_vwap is None:
                vwap_evidence_complete = False
            elif state.current_close < state.current_vwap:
                completed_bars_below_vwap += 1
                consecutive_below_vwap += 1
            else:
                consecutive_below_vwap = 0
            if state.current_close < breakout_level:
                consecutive_below_breakout += 1
            else:
                consecutive_below_breakout = 0

        highest_price = (
            tick.price
            if state.highest_price is None
            else max(state.highest_price, tick.price)
        )
        post_entry_volume_shares = (
            state.post_entry_volume_shares
            + tick.tick_volume_lots * config.shares_per_lot
        )
        volume_sample_count = state.volume_sample_count + 1
        observed_at = TradeTimestamp(
            role=TimestampRole.MARKET_EVENT,
            value=event.event_at,
            source=TimestampSource.CANONICAL_MARKET_EVENT,
            source_identity=event.event_id,
        )
        market_context = ThesisMarketContext(
            thesis_id=config.thesis.thesis_id,
            trade_id=config.thesis.trade_id,
            session_id=config.thesis.draft.session_id,
            symbol=config.thesis.draft.symbol,
            source_event_id=event.event_id,
            observed_at=observed_at,
            data_status=MarketContextStatus.READY,
            health_state=risk_snapshot.data_health_state,
            highest_price_since_entry=highest_price,
            post_entry_volume_shares=post_entry_volume_shares,
            volume_baseline_shares=config.volume_baseline_shares,
            volume_sample_count=volume_sample_count,
            completed_bar_count=completed_bar_count,
            completed_bars_below_vwap=(
                completed_bars_below_vwap if vwap_evidence_complete else None
            ),
            consecutive_completed_bars_below_vwap=(
                consecutive_below_vwap if vwap_evidence_complete else None
            ),
            consecutive_completed_bars_below_breakout=consecutive_below_breakout,
            prior_status=state.prior_status,
        )
        evaluation = ThesisMonitor().evaluate(config.thesis, market_context)
        decided_at = TradeTimestamp(
            role=TimestampRole.EXIT_DECISION,
            value=event.event_at,
            source=TimestampSource.SIMULATION_CLOCK,
            source_identity=f"{TRADE_MANAGEMENT_REPLAY_VERSION}:{event.event_id}",
        )
        position = ExitPositionContext(
            session_id=config.thesis.draft.session_id,
            trade_id=config.thesis.trade_id,
            thesis_id=config.thesis.thesis_id,
            remaining_quantity_shares=config.remaining_quantity_shares,
            lifecycle_state=TradeLifecycleState.ACTIVE_POSITION,
            decided_at=decided_at,
            active_recommendation=state.active_recommendation,
        )
        recommendation_result = ExitRecommendationEngine(
            config.exit_policy_version
        ).evaluate(evaluation, position)
        active_recommendation = recommendation_result.recommendation
        eligibility = None
        if active_recommendation is not None:
            eligibility = RiskGate(config.risk_policy).evaluate_exit_recommendation(
                active_recommendation,
                ExitEligibilityContext(
                    snapshot_id=f"risk-snapshot:{event.event_id}",
                    session_id=config.thesis.draft.session_id,
                    trade_id=config.thesis.trade_id,
                    thesis_id=config.thesis.thesis_id,
                    snapshot=risk_snapshot,
                    evaluated_at=event.event_at,
                ),
            )
        step = TradeManagementReplayStep(
            sequence=state.processed_step_count + 1,
            source_event_id=event.event_id,
            market_context=market_context,
            evaluation=evaluation,
            recommendation_result=recommendation_result,
            eligibility=eligibility,
        )
        next_state = replace(
            state,
            **common_state,
            highest_price=highest_price,
            post_entry_volume_shares=post_entry_volume_shares,
            volume_sample_count=volume_sample_count,
            completed_bar_count=completed_bar_count,
            completed_bars_below_vwap=completed_bars_below_vwap,
            consecutive_below_vwap=consecutive_below_vwap,
            consecutive_below_breakout=consecutive_below_breakout,
            vwap_evidence_complete=vwap_evidence_complete,
            active_recommendation=active_recommendation,
            prior_status=evaluation.status,
            current_minute=minute,
            current_close=tick.price,
            current_vwap=tick.average_price,
            processed_step_count=step.sequence,
            decision_digest=_sha256([state.decision_digest, _step_wire(step)]),
        )
        return next_state, step

    @staticmethod
    def _validate_event(
        thesis: TradeThesis,
        state: TradeManagementDecisionState,
        event: EventEnvelope,
    ) -> None:
        if event.stream_kind is not MarketStreamKind.TICK or not isinstance(
            event.payload, TickEvent
        ):
            raise ValueError("Trade Management decision kernel accepts Tick only")
        if "SYNTHETIC" in event.source_mode.upper():
            raise ValueError("synthetic ticks are prohibited")
        if event.session_id != thesis.draft.session_id:
            raise ValueError("event session does not match TradeThesis")
        if event.symbol != thesis.draft.symbol:
            raise ValueError("event symbol does not match TradeThesis")
        if event.event_id in state.seen_event_ids:
            raise ValueError("Tick event IDs must be unique")
        if state.last_event_at is not None:
            assert state.last_ingress_sequence is not None
            if (event.event_at, event.ingress_sequence) <= (
                state.last_event_at,
                state.last_ingress_sequence,
            ):
                raise ValueError("Tick events must be strictly ordered")


@dataclass(frozen=True)
class TradeManagementReplayResult:
    run_identity: ReplayRunIdentity
    steps: tuple[TradeManagementReplayStep, ...]
    verification: ReplayVerification
    empty_journal_digest: str = EMPTY_JOURNAL_DIGEST

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("replay result requires at least one post-fill step")
        if self.verification.run_identity != self.run_identity:
            raise ValueError("verification must bind to replay run identity")
        if self.verification.output.journal_digest != self.empty_journal_digest:
            raise ValueError("decision-only replay must retain the empty Journal digest")


class TradeManagementReplayRunner:
    """Rebuild the decision chain from ordered captured Tick evidence."""

    __slots__ = ()

    def run(self, replay: TradeManagementReplayInput) -> TradeManagementReplayResult:
        self._validate_input(replay)
        config = TradeManagementDecisionConfig(
            thesis=replay.thesis,
            exit_policy_version=replay.run_identity.exit_policy_version,
            volume_baseline_shares=replay.volume_baseline_shares,
            shares_per_lot=replay.shares_per_lot,
            remaining_quantity_shares=replay.remaining_quantity_shares,
            risk_policy=replay.risk_policy,
        )
        kernel = TradeManagementDecisionKernel()
        state = TradeManagementDecisionState()
        steps: list[TradeManagementReplayStep] = []
        for index, event in enumerate(replay.events):
            state, step = kernel.apply(
                config,
                state,
                event,
                risk_snapshot=replay.risk_snapshot_at(index),
            )
            if step is not None:
                steps.append(step)

        if not steps:
            raise ValueError("replay has no market event at or after Thesis fill time")
        final_state_digest = _sha256(self._final_state_wire(steps[-1]))
        output = ReplayOutput(
            input_digest=replay.run_identity.manifest_sha256,
            run_identity_digest=replay.run_identity.digest,
            strategy_version=replay.run_identity.strategy_version,
            thesis_version=replay.run_identity.thesis_version,
            decision_digest=state.decision_digest,
            journal_digest=EMPTY_JOURNAL_DIGEST,
            final_state_digest=final_state_digest,
        )
        verification = ReplayVerification(
            run_identity=replay.run_identity,
            output=output,
        )
        return TradeManagementReplayResult(
            run_identity=replay.run_identity,
            steps=tuple(steps),
            verification=verification,
        )

    @staticmethod
    def _validate_input(replay: TradeManagementReplayInput) -> None:
        identity = replay.run_identity
        thesis = replay.thesis
        if identity.manifest_sha256 != build_market_manifest_digest(replay.events):
            raise ValueError("Replay manifest digest does not match Historical Tick artifacts")
        if identity.canonical_event_schema_version != MARKET_EVENT_SCHEMA_VERSION:
            raise ValueError("Replay canonical event schema version mismatch")
        expected_versions = {
            "strategy_id": thesis.draft.strategy_id,
            "strategy_version": thesis.draft.strategy_version,
            "thesis_type": thesis.draft.thesis_type,
            "thesis_version": thesis.draft.thesis_version,
        }
        for field_name, expected in expected_versions.items():
            if getattr(identity, field_name) != expected:
                raise ValueError(f"Replay {field_name} does not match TradeThesis")
        if identity.guard_policy_version != replay.risk_policy.version:
            raise ValueError("Replay guard policy version does not match RiskPolicy")
        previous_watermark: tuple[object, int] | None = None
        event_ids: set[str] = set()
        for event in replay.events:
            if event.stream_kind is not MarketStreamKind.TICK or not isinstance(
                event.payload, TickEvent
            ):
                raise ValueError("Trade Management replay accepts Historical Tick only")
            if "SYNTHETIC" in event.source_mode.upper():
                raise ValueError("synthetic ticks are prohibited")
            if event.session_id != thesis.draft.session_id:
                raise ValueError("Replay event session does not match TradeThesis")
            if event.symbol != thesis.draft.symbol:
                raise ValueError("Replay event symbol does not match TradeThesis")
            watermark = (event.event_at, event.ingress_sequence)
            if previous_watermark is not None and watermark <= previous_watermark:
                raise ValueError("Historical Tick events must be strictly ordered")
            previous_watermark = watermark
            if event.event_id in event_ids:
                raise ValueError("Historical Tick event IDs must be unique")
            event_ids.add(event.event_id)

    @staticmethod
    def _final_state_wire(step: TradeManagementReplayStep) -> dict[str, object]:
        context = step.market_context
        recommendation = step.recommendation_result.recommendation
        return {
            "version": TRADE_MANAGEMENT_REPLAY_VERSION,
            "source_event_id": step.source_event_id,
            "thesis_status": step.evaluation.status.value,
            "highest_price_since_entry": (
                None
                if context.highest_price_since_entry is None
                else canonical_decimal_string(context.highest_price_since_entry)
            ),
            "post_entry_volume_shares": context.post_entry_volume_shares,
            "volume_sample_count": context.volume_sample_count,
            "completed_bar_count": context.completed_bar_count,
            "completed_bars_below_vwap": context.completed_bars_below_vwap,
            "consecutive_completed_bars_below_vwap": (
                context.consecutive_completed_bars_below_vwap
            ),
            "consecutive_completed_bars_below_breakout": (
                context.consecutive_completed_bars_below_breakout
            ),
            "active_recommendation_id": (
                None if recommendation is None else recommendation.recommendation_id
            ),
            "eligibility_id": (
                None if step.eligibility is None else step.eligibility.eligibility_id
            ),
        }
