"""Pure thesis-to-exit recommendation mapping for PR-TM-004.

The caller supplies an immutable Thesis evaluation, active-position facts, and
canonical decision time.  This module returns immutable decision evidence and
has no persistence, risk, position, order, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from trading.thesis_monitor import (
    ThesisEvaluation,
    ThesisReasonCode,
)
from trading.trade_management import (
    ExitAction,
    ExitDecision,
    ExitReason,
    ExitRecommendation,
    ExitRecommendationStatus,
    ThesisStatus,
    TimestampRole,
    TradeLifecycleState,
    TradeTimestamp,
    TRADE_MANAGEMENT_SCHEMA_VERSION,
    build_exit_decision_id,
    build_exit_recommendation_id,
)


EXIT_RECOMMENDATION_ENGINE_VERSION = "exit-recommendation-engine-v1"
_SUPPORTED_REASONS = (ExitReason.THESIS_INVALID, ExitReason.TIME_DECAY)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class ExitPositionContext:
    """Read-only facts for one currently open trade."""

    session_id: str
    trade_id: str
    thesis_id: str
    remaining_quantity_shares: int
    lifecycle_state: TradeLifecycleState
    decided_at: TradeTimestamp
    active_recommendation: ExitRecommendation | None = None
    schema_version: str = TRADE_MANAGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_MANAGEMENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported trade management schema: {self.schema_version}")
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
        ):
            _require_non_empty(value, field_name)
        if self.remaining_quantity_shares <= 0:
            raise ValueError("remaining_quantity_shares must be positive")
        if self.lifecycle_state is not TradeLifecycleState.ACTIVE_POSITION:
            raise ValueError("recommendation requires ACTIVE_POSITION lifecycle state")
        if self.decided_at.role is not TimestampRole.EXIT_DECISION:
            raise ValueError("decided_at must use the EXIT_DECISION role")
        recommendation = self.active_recommendation
        if recommendation is None:
            return
        if recommendation.status is not ExitRecommendationStatus.ACTIVE:
            raise ValueError("position context requires an ACTIVE recommendation")
        for field_name in ("session_id", "trade_id", "thesis_id"):
            if getattr(recommendation, field_name) != getattr(self, field_name):
                raise ValueError(
                    f"active recommendation {field_name} does not match position"
                )
        if any(
            reason not in _SUPPORTED_REASONS
            for reason in recommendation.triggered_reasons
        ):
            raise ValueError(
                "active recommendation contains reasons outside PR-TM-004"
            )
        if recommendation.updated_at.value > self.decided_at.value:
            raise ValueError("active recommendation cannot postdate decided_at")


@dataclass(frozen=True)
class ExitRecommendationResult:
    decision: ExitDecision
    recommendation: ExitRecommendation | None
    recommendation_changed: bool

    def __post_init__(self) -> None:
        if self.decision.action is ExitAction.HOLD:
            if self.recommendation is not None:
                raise ValueError("HOLD result cannot contain a recommendation")
            if self.recommendation_changed:
                raise ValueError("HOLD result cannot change a recommendation")
            return
        if self.recommendation is None:
            raise ValueError("EXIT result requires a recommendation")
        if self.recommendation.trade_id != self.decision.trade_id:
            raise ValueError("recommendation trade_id must match decision")
        if self.recommendation.thesis_id != self.decision.thesis_id:
            raise ValueError("recommendation thesis_id must match decision")
        if (
            self.recommendation_changed
            and self.recommendation.latest_decision_id != self.decision.decision_id
        ):
            raise ValueError("recommendation must reference the current decision")


def _decision_digest(
    evaluation: ThesisEvaluation,
    position: ExitPositionContext,
    exit_policy_version: str,
) -> str:
    payload = {
        "engine_version": EXIT_RECOMMENDATION_ENGINE_VERSION,
        "exit_policy_version": exit_policy_version,
        "evaluation": {
            "evaluation_id": evaluation.evaluation_id,
            "input_digest": evaluation.input_digest,
            "status": evaluation.status.value,
            "reason_codes": [reason.value for reason in evaluation.reason_codes],
            "source_event_id": evaluation.source_event_id,
            "evaluated_at": evaluation.evaluated_at.isoformat,
        },
        "position": {
            "session_id": position.session_id,
            "trade_id": position.trade_id,
            "thesis_id": position.thesis_id,
            "remaining_quantity_shares": position.remaining_quantity_shares,
            "lifecycle_state": position.lifecycle_state.value,
            "decided_at": position.decided_at.isoformat,
            "decision_time_source": position.decided_at.source.value,
            "decision_time_source_identity": position.decided_at.source_identity,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mapped_reasons(
    evaluation: ThesisEvaluation,
    active_recommendation: ExitRecommendation | None,
) -> tuple[ExitReason, ...]:
    if evaluation.status is not ThesisStatus.INVALID:
        return ()
    reason_codes = set(evaluation.reason_codes)
    if ThesisReasonCode.INVALID_LATCHED in reason_codes:
        if active_recommendation is not None:
            return active_recommendation.triggered_reasons
        return (ExitReason.THESIS_INVALID,)

    mapped: set[ExitReason] = set()
    if reason_codes.intersection(
        {
            ThesisReasonCode.BREAKOUT_LEVEL_LOST,
            ThesisReasonCode.VWAP_CONFIRMATION_LOST,
        }
    ):
        mapped.add(ExitReason.THESIS_INVALID)
    if ThesisReasonCode.EXPECTED_BEHAVIOR_EXPIRED in reason_codes:
        mapped.add(ExitReason.TIME_DECAY)
    if not mapped:
        raise ValueError("INVALID ThesisEvaluation has no actionable reason")
    return tuple(reason for reason in _SUPPORTED_REASONS if reason in mapped)


def _merged_reasons(
    current: tuple[ExitReason, ...],
    observed: tuple[ExitReason, ...],
) -> tuple[ExitReason, ...]:
    combined = set(current).union(observed)
    return tuple(reason for reason in _SUPPORTED_REASONS if reason in combined)


@dataclass(frozen=True)
class ExitRecommendationEngine:
    """Map Thesis status evidence to a decision-only recommendation."""

    exit_policy_version: str

    def __post_init__(self) -> None:
        _require_non_empty(self.exit_policy_version, "exit_policy_version")

    def evaluate(
        self,
        evaluation: ThesisEvaluation,
        position: ExitPositionContext,
    ) -> ExitRecommendationResult:
        self._validate_inputs(evaluation, position)
        active = position.active_recommendation
        if evaluation.status is not ThesisStatus.INVALID and active is not None:
            raise ValueError(
                "active recommendation requires an INVALID ThesisEvaluation"
            )

        observed_reasons = _mapped_reasons(evaluation, active)
        action = ExitAction.EXIT if observed_reasons else ExitAction.HOLD
        decision_reasons = (
            _merged_reasons(active.triggered_reasons, observed_reasons)
            if active is not None
            else observed_reasons
        )
        evaluation_digest = _decision_digest(
            evaluation,
            position,
            self.exit_policy_version,
        )
        decision_id = build_exit_decision_id(
            position.session_id,
            position.trade_id,
            evaluation.source_event_id,
            self.exit_policy_version,
            evaluation_digest,
        )
        decision = ExitDecision(
            decision_id=decision_id,
            session_id=position.session_id,
            trade_id=position.trade_id,
            thesis_id=position.thesis_id,
            action=action,
            primary_reason=(decision_reasons[0] if decision_reasons else None),
            triggered_reasons=decision_reasons,
            decided_at=position.decided_at,
            source_event_id=evaluation.source_event_id,
            exit_policy_version=self.exit_policy_version,
            evaluation_digest=evaluation_digest,
        )
        if action is ExitAction.HOLD:
            return ExitRecommendationResult(
                decision=decision,
                recommendation=None,
                recommendation_changed=False,
            )

        if active is None:
            recommendation_id = build_exit_recommendation_id(
                position.session_id,
                position.trade_id,
                self.exit_policy_version,
            )
            recommendation = ExitRecommendation(
                recommendation_id=recommendation_id,
                session_id=position.session_id,
                trade_id=position.trade_id,
                thesis_id=position.thesis_id,
                exit_policy_version=self.exit_policy_version,
                status=ExitRecommendationStatus.ACTIVE,
                first_trigger_decision_id=decision.decision_id,
                first_trigger_event_id=evaluation.source_event_id,
                latest_decision_id=decision.decision_id,
                latest_evidence_event_id=evaluation.source_event_id,
                primary_reason=decision_reasons[0],
                triggered_reasons=decision_reasons,
                created_at=position.decided_at,
                updated_at=position.decided_at,
            )
            recommendation_changed = True
        elif (
            active.primary_reason is decision_reasons[0]
            and active.triggered_reasons == decision_reasons
        ):
            recommendation = active
            recommendation_changed = False
        else:
            recommendation = ExitRecommendation(
                recommendation_id=active.recommendation_id,
                session_id=active.session_id,
                trade_id=active.trade_id,
                thesis_id=active.thesis_id,
                exit_policy_version=active.exit_policy_version,
                status=active.status,
                first_trigger_decision_id=active.first_trigger_decision_id,
                first_trigger_event_id=active.first_trigger_event_id,
                latest_decision_id=decision.decision_id,
                latest_evidence_event_id=evaluation.source_event_id,
                primary_reason=decision_reasons[0],
                triggered_reasons=decision_reasons,
                created_at=active.created_at,
                updated_at=position.decided_at,
            )
            recommendation_changed = True
        return ExitRecommendationResult(
            decision=decision,
            recommendation=recommendation,
            recommendation_changed=recommendation_changed,
        )

    def _validate_inputs(
        self,
        evaluation: ThesisEvaluation,
        position: ExitPositionContext,
    ) -> None:
        for field_name in ("trade_id", "thesis_id"):
            if getattr(evaluation, field_name) != getattr(position, field_name):
                raise ValueError(f"position {field_name} does not match evaluation")
        if position.decided_at.value < evaluation.evaluated_at.value:
            raise ValueError("decided_at cannot predate ThesisEvaluation")
        active = position.active_recommendation
        if (
            active is not None
            and active.exit_policy_version != self.exit_policy_version
        ):
            raise ValueError("active recommendation policy version does not match engine")
