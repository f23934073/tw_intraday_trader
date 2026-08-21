"""Durable, evidence-only Journal adapter for Trade Management Shadow v1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from trading.canonical_values import canonical_decimal_string
from trading.journal import (
    JournalAppendResult,
    JournalRecord,
    JournalRepository,
    ProjectionCheckpoint,
)
from trading.risk import (
    ExecutionEligibilityStatus,
    RiskReason,
    RiskSnapshot,
)
from trading.thesis_monitor import MarketContextStatus, ThesisReasonCode
from trading.trade_management import ExitAction, ExitReason, ThesisStatus
from trading.trade_management_shadow import (
    ShadowDecisionRecord,
    ShadowDecisionSession,
    ShadowParityStatus,
)


SHADOW_EVIDENCE_SCHEMA_VERSION = "shadow-evidence-v1"
SHADOW_EVIDENCE_SERIALIZER_VERSION = "shadow-evidence-json-v1"
SHADOW_EVIDENCE_PROJECTION_NAME = "shadow_evidence.v1"


class ShadowEvidenceJournalKind(StrEnum):
    DECISION_RECORDED = "shadow_decision_recorded.v1"
    SESSION_FINALIZED = "shadow_session_finalized.v1"


class ShadowEvidenceRetentionMode(StrEnum):
    RETAIN_ALL = "RETAIN_ALL"


@dataclass(frozen=True)
class ShadowEvidenceRetentionPolicy:
    version: str = "shadow-evidence-retention-v1"
    mode: ShadowEvidenceRetentionMode = ShadowEvidenceRetentionMode.RETAIN_ALL
    compaction_allowed: bool = False

    def __post_init__(self) -> None:
        if self.version != "shadow-evidence-retention-v1":
            raise ValueError("unsupported retention policy version")
        if self.mode is ShadowEvidenceRetentionMode.RETAIN_ALL and self.compaction_allowed:
            raise ValueError("RETAIN_ALL policy prohibits compaction")


DEFAULT_SHADOW_RETENTION_POLICY = ShadowEvidenceRetentionPolicy()


class ShadowEvidenceJournalError(ValueError):
    """A Shadow evidence artifact or replay stream violates the v1 contract."""


def _require_digest(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ShadowDecisionEvidence:
    record_id: str
    session_id: str
    trade_id: str
    thesis_id: str
    source_event_id: str
    occurred_at: datetime
    config_digest: str
    source_event_digest: str
    risk_snapshot_digest: str
    decision_chain_digest: str
    step_sequence: int
    market_context: Mapping[str, object]
    risk_snapshot: RiskSnapshot
    evaluation_id: str
    evaluation_input_digest: str
    evaluation_status: ThesisStatus
    evaluation_reasons: tuple[ThesisReasonCode, ...]
    exit_decision_id: str
    exit_action: ExitAction
    exit_reasons: tuple[ExitReason, ...]
    recommendation_id: str | None
    recommendation_reason: ExitReason | None
    eligibility_id: str | None
    eligibility_status: ExecutionEligibilityStatus | None
    eligibility_reasons: tuple[RiskReason, ...]
    eligible_quantity_shares: int | None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.record_id, "record_id"),
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
            (self.source_event_id, "source_event_id"),
            (self.evaluation_id, "evaluation_id"),
            (self.exit_decision_id, "exit_decision_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        for value, field_name in (
            (self.config_digest, "config_digest"),
            (self.source_event_digest, "source_event_digest"),
            (self.risk_snapshot_digest, "risk_snapshot_digest"),
            (self.decision_chain_digest, "decision_chain_digest"),
            (self.evaluation_input_digest, "evaluation_input_digest"),
        ):
            _require_digest(value, field_name)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.step_sequence <= 0:
            raise ValueError("step_sequence must be positive")
        if len(self.evaluation_reasons) != len(set(self.evaluation_reasons)):
            raise ValueError("evaluation_reasons must not contain duplicates")
        if len(self.exit_reasons) != len(set(self.exit_reasons)):
            raise ValueError("exit_reasons must not contain duplicates")
        if len(self.eligibility_reasons) != len(set(self.eligibility_reasons)):
            raise ValueError("eligibility_reasons must not contain duplicates")
        if self.recommendation_id is None:
            if self.recommendation_reason is not None:
                raise ValueError("recommendation reason requires recommendation ID")
        elif self.recommendation_reason is None:
            raise ValueError("recommendation ID requires recommendation reason")
        eligibility_values = (
            self.eligibility_id,
            self.eligibility_status,
            self.eligible_quantity_shares,
        )
        if self.eligibility_id is None:
            if any(value is not None for value in eligibility_values[1:]) or self.eligibility_reasons:
                raise ValueError("eligibility fields require eligibility ID")
        elif any(value is None for value in eligibility_values[1:]):
            raise ValueError("eligibility ID requires status and quantity")
        elif self.eligibility_status is ExecutionEligibilityStatus.ELIGIBLE:
            if self.eligible_quantity_shares <= 0 or self.eligibility_reasons:
                raise ValueError("ELIGIBLE evidence requires quantity and no reasons")
        elif self.eligible_quantity_shares != 0 or not self.eligibility_reasons:
            raise ValueError("non-eligible evidence requires reasons and zero quantity")
        if self.risk_snapshot_digest != _canonical_digest(
            _risk_wire(self.risk_snapshot)
        ):
            raise ValueError("risk_snapshot_digest does not match RiskSnapshot")
        if self.market_context.get("source_event_id") != self.source_event_id:
            raise ValueError("market context source event does not match evidence")
        if self.exit_action is ExitAction.HOLD:
            if self.exit_reasons or self.recommendation_id is not None:
                raise ValueError("HOLD evidence cannot contain exit authority")
        elif not self.exit_reasons or self.recommendation_id is None:
            raise ValueError("EXIT evidence requires reasons and recommendation")
        if self.eligibility_id is not None and self.recommendation_id is None:
            raise ValueError("eligibility requires recommendation evidence")
        object.__setattr__(self, "market_context", _freeze_mapping(self.market_context))


@dataclass(frozen=True)
class ShadowSessionFinalizationEvidence:
    session_id: str
    trade_id: str
    thesis_id: str
    config_digest: str
    manifest_sha256: str
    record_count: int
    final_decision_chain_digest: str
    replay_decision_digest: str
    replay_output_digest: str
    run_identity_digest: str
    parity_status: ShadowParityStatus
    first_divergent_sequence: int | None
    finalized_at: datetime

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.session_id, "session_id"),
            (self.trade_id, "trade_id"),
            (self.thesis_id, "thesis_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        for value, field_name in (
            (self.config_digest, "config_digest"),
            (self.manifest_sha256, "manifest_sha256"),
            (self.final_decision_chain_digest, "final_decision_chain_digest"),
            (self.replay_decision_digest, "replay_decision_digest"),
            (self.replay_output_digest, "replay_output_digest"),
            (self.run_identity_digest, "run_identity_digest"),
        ):
            _require_digest(value, field_name)
        if self.record_count <= 0:
            raise ValueError("record_count must be positive")
        if self.finalized_at.tzinfo is None or self.finalized_at.utcoffset() is None:
            raise ValueError("finalized_at must be timezone-aware")
        if self.parity_status is ShadowParityStatus.MATCHED:
            if self.first_divergent_sequence is not None:
                raise ValueError("MATCHED finalization cannot have divergence")
            if self.final_decision_chain_digest != self.replay_decision_digest:
                raise ValueError("MATCHED finalization requires equal decision digests")
        elif self.first_divergent_sequence is None:
            raise ValueError("DIVERGED finalization requires a sequence")


@dataclass(frozen=True)
class ShadowEvidenceJournalEvent:
    kind: ShadowEvidenceJournalKind
    decision: ShadowDecisionEvidence | None = None
    finalization: ShadowSessionFinalizationEvidence | None = None

    def __post_init__(self) -> None:
        if self.kind is ShadowEvidenceJournalKind.DECISION_RECORDED:
            if self.decision is None or self.finalization is not None:
                raise ValueError("decision event requires only decision evidence")
        elif self.finalization is None or self.decision is not None:
            raise ValueError("finalization event requires only finalization evidence")


def _market_context_wire(record: ShadowDecisionRecord) -> dict[str, object]:
    context = record.step.market_context
    return {
        "source_event_id": context.source_event_id,
        "data_status": context.data_status.value,
        "health_state": context.health_state,
        "highest_price_since_entry": (
            None
            if context.highest_price_since_entry is None
            else canonical_decimal_string(context.highest_price_since_entry)
        ),
        "post_entry_volume_shares": context.post_entry_volume_shares,
        "volume_baseline_shares": (
            None
            if context.volume_baseline_shares is None
            else canonical_decimal_string(context.volume_baseline_shares)
        ),
        "volume_sample_count": context.volume_sample_count,
        "completed_bar_count": context.completed_bar_count,
        "completed_bars_below_vwap": context.completed_bars_below_vwap,
        "consecutive_completed_bars_below_vwap": context.consecutive_completed_bars_below_vwap,
        "consecutive_completed_bars_below_breakout": context.consecutive_completed_bars_below_breakout,
        "prior_status": None if context.prior_status is None else context.prior_status.value,
    }


def _risk_wire(snapshot: RiskSnapshot) -> dict[str, object]:
    return {
        "data_health_state": snapshot.data_health_state,
        "market_open": snapshot.market_open,
        "instrument_tradable": snapshot.instrument_tradable,
        "available_cash": canonical_decimal_string(snapshot.available_cash),
        "current_position_shares": snapshot.current_position_shares,
        "pending_buy_shares": snapshot.pending_buy_shares,
        "pending_sell_shares": snapshot.pending_sell_shares,
        "daily_realized_pnl": canonical_decimal_string(snapshot.daily_realized_pnl),
        "same_side_pending_order": snapshot.same_side_pending_order,
        "book_age_seconds": snapshot.book_age_seconds,
    }


def _decision_evidence(record: ShadowDecisionRecord) -> ShadowDecisionEvidence:
    step = record.step
    recommendation = step.recommendation_result.recommendation
    eligibility = step.eligibility
    return ShadowDecisionEvidence(
        record_id=record.record_id,
        session_id=step.market_context.session_id,
        trade_id=step.market_context.trade_id,
        thesis_id=step.market_context.thesis_id,
        source_event_id=step.source_event_id,
        occurred_at=step.evaluation.evaluated_at.value,
        config_digest=record.config_digest,
        source_event_digest=record.source_event_digest,
        risk_snapshot_digest=record.risk_snapshot_digest,
        decision_chain_digest=record.decision_chain_digest,
        step_sequence=step.sequence,
        market_context=_market_context_wire(record),
        risk_snapshot=record.risk_snapshot,
        evaluation_id=step.evaluation.evaluation_id,
        evaluation_input_digest=step.evaluation.input_digest,
        evaluation_status=step.evaluation.status,
        evaluation_reasons=step.evaluation.reason_codes,
        exit_decision_id=step.recommendation_result.decision.decision_id,
        exit_action=step.recommendation_result.decision.action,
        exit_reasons=step.recommendation_result.decision.triggered_reasons,
        recommendation_id=(None if recommendation is None else recommendation.recommendation_id),
        recommendation_reason=(None if recommendation is None else recommendation.primary_reason),
        eligibility_id=None if eligibility is None else eligibility.eligibility_id,
        eligibility_status=None if eligibility is None else eligibility.status,
        eligibility_reasons=() if eligibility is None else eligibility.reasons,
        eligible_quantity_shares=(None if eligibility is None else eligibility.eligible_quantity_shares),
    )


def _finalization_evidence(session: ShadowDecisionSession) -> ShadowSessionFinalizationEvidence:
    if not session.records:
        raise ValueError("Shadow session requires decision records")
    first = session.records[0]
    last = session.records[-1]
    return ShadowSessionFinalizationEvidence(
        session_id=first.step.market_context.session_id,
        trade_id=first.step.market_context.trade_id,
        thesis_id=first.step.market_context.thesis_id,
        config_digest=first.config_digest,
        manifest_sha256=session.manifest_sha256,
        record_count=len(session.records),
        final_decision_chain_digest=session.parity.shadow_decision_digest,
        replay_decision_digest=session.parity.replay_decision_digest,
        replay_output_digest=session.replay_result.verification.output.digest,
        run_identity_digest=session.replay_result.run_identity.digest,
        parity_status=session.parity.status,
        first_divergent_sequence=session.parity.first_divergent_sequence,
        finalized_at=last.step.evaluation.evaluated_at.value,
    )


def _evidence_wire(value: ShadowDecisionEvidence | ShadowSessionFinalizationEvidence) -> dict[str, object]:
    if isinstance(value, ShadowDecisionEvidence):
        return {
            "schema_version": SHADOW_EVIDENCE_SCHEMA_VERSION,
            "contract_type": "ShadowDecisionEvidence",
            "payload": {
                "record_id": value.record_id,
                "session_id": value.session_id,
                "trade_id": value.trade_id,
                "thesis_id": value.thesis_id,
                "source_event_id": value.source_event_id,
                "occurred_at": value.occurred_at.isoformat(timespec="microseconds"),
                "config_digest": value.config_digest,
                "source_event_digest": value.source_event_digest,
                "risk_snapshot_digest": value.risk_snapshot_digest,
                "decision_chain_digest": value.decision_chain_digest,
                "step_sequence": value.step_sequence,
                "market_context": dict(value.market_context),
                "risk_snapshot": _risk_wire(value.risk_snapshot),
                "evaluation": {
                    "evaluation_id": value.evaluation_id,
                    "input_digest": value.evaluation_input_digest,
                    "status": value.evaluation_status.value,
                    "reasons": [item.value for item in value.evaluation_reasons],
                },
                "exit_decision": {
                    "decision_id": value.exit_decision_id,
                    "action": value.exit_action.value,
                    "reasons": [item.value for item in value.exit_reasons],
                },
                "recommendation": (
                    None
                    if value.recommendation_id is None
                    else {
                        "recommendation_id": value.recommendation_id,
                        "primary_reason": value.recommendation_reason.value,
                    }
                ),
                "eligibility": (
                    None
                    if value.eligibility_id is None
                    else {
                        "eligibility_id": value.eligibility_id,
                        "status": value.eligibility_status.value,
                        "reasons": [item.value for item in value.eligibility_reasons],
                        "eligible_quantity_shares": value.eligible_quantity_shares,
                    }
                ),
            },
        }
    return {
        "schema_version": SHADOW_EVIDENCE_SCHEMA_VERSION,
        "contract_type": "ShadowSessionFinalizationEvidence",
        "payload": {
            "session_id": value.session_id,
            "trade_id": value.trade_id,
            "thesis_id": value.thesis_id,
            "config_digest": value.config_digest,
            "manifest_sha256": value.manifest_sha256,
            "record_count": value.record_count,
            "final_decision_chain_digest": value.final_decision_chain_digest,
            "replay_decision_digest": value.replay_decision_digest,
            "replay_output_digest": value.replay_output_digest,
            "run_identity_digest": value.run_identity_digest,
            "parity_status": value.parity_status.value,
            "first_divergent_sequence": value.first_divergent_sequence,
            "finalized_at": value.finalized_at.isoformat(timespec="microseconds"),
        },
    }


def _serialize_evidence(value: ShadowDecisionEvidence | ShadowSessionFinalizationEvidence) -> str:
    return json.dumps(_evidence_wire(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_id(session_id: str, kind: ShadowEvidenceJournalKind, identity: str) -> str:
    canonical = "\x1f".join(("shadow-evidence-journal-id-v1", session_id, kind.value, identity))
    return f"shadow_evidence_v1_{hashlib.sha256(canonical.encode()).hexdigest()}"


def _journal_record(
    kind: ShadowEvidenceJournalKind,
    evidence: ShadowDecisionEvidence | ShadowSessionFinalizationEvidence,
    *,
    identity: str,
    occurred_at: datetime,
    retention: ShadowEvidenceRetentionPolicy,
) -> JournalRecord:
    evidence_json = _serialize_evidence(evidence)
    record_id = _record_id(evidence.session_id, kind, identity)
    return JournalRecord(
        record_id=record_id,
        session_id=evidence.session_id,
        kind=kind.value,
        occurred_at=occurred_at,
        payload={
            "evidence_digest": hashlib.sha256(evidence_json.encode()).hexdigest(),
            "evidence_json": evidence_json,
            "retention_mode": retention.mode.value,
            "retention_policy_version": retention.version,
            "serializer_version": SHADOW_EVIDENCE_SERIALIZER_VERSION,
        },
        idempotency_scope=f"{evidence.session_id}:shadow_evidence:{kind.value}",
        idempotency_key=record_id,
    )


def journal_record_for_shadow_decision(
    record: ShadowDecisionRecord,
    *,
    retention: ShadowEvidenceRetentionPolicy = DEFAULT_SHADOW_RETENTION_POLICY,
) -> JournalRecord:
    evidence = _decision_evidence(record)
    return _journal_record(
        ShadowEvidenceJournalKind.DECISION_RECORDED,
        evidence,
        identity=evidence.record_id,
        occurred_at=evidence.occurred_at,
        retention=retention,
    )


def journal_record_for_shadow_session(
    session: ShadowDecisionSession,
    *,
    retention: ShadowEvidenceRetentionPolicy = DEFAULT_SHADOW_RETENTION_POLICY,
) -> JournalRecord:
    evidence = _finalization_evidence(session)
    return _journal_record(
        ShadowEvidenceJournalKind.SESSION_FINALIZED,
        evidence,
        identity=evidence.manifest_sha256,
        occurred_at=evidence.finalized_at,
        retention=retention,
    )


_JOURNAL_PAYLOAD_FIELDS = frozenset({
    "evidence_digest",
    "evidence_json",
    "retention_mode",
    "retention_policy_version",
    "serializer_version",
})
_TOP_FIELDS = frozenset({"schema_version", "contract_type", "payload"})
_DECISION_FIELDS = frozenset({
    "record_id", "session_id", "trade_id", "thesis_id", "source_event_id",
    "occurred_at", "config_digest", "source_event_digest", "risk_snapshot_digest",
    "decision_chain_digest", "step_sequence", "market_context", "risk_snapshot",
    "evaluation", "exit_decision", "recommendation", "eligibility",
})
_MARKET_FIELDS = frozenset({
    "source_event_id", "data_status", "health_state", "highest_price_since_entry",
    "post_entry_volume_shares", "volume_baseline_shares", "volume_sample_count",
    "completed_bar_count", "completed_bars_below_vwap",
    "consecutive_completed_bars_below_vwap",
    "consecutive_completed_bars_below_breakout", "prior_status",
})
_RISK_FIELDS = frozenset({
    "data_health_state", "market_open", "instrument_tradable", "available_cash",
    "current_position_shares", "pending_buy_shares", "pending_sell_shares",
    "daily_realized_pnl", "same_side_pending_order", "book_age_seconds",
})
_EVALUATION_FIELDS = frozenset({"evaluation_id", "input_digest", "status", "reasons"})
_EXIT_FIELDS = frozenset({"decision_id", "action", "reasons"})
_RECOMMENDATION_FIELDS = frozenset({"recommendation_id", "primary_reason"})
_ELIGIBILITY_FIELDS = frozenset({"eligibility_id", "status", "reasons", "eligible_quantity_shares"})
_FINALIZATION_FIELDS = frozenset({
    "session_id", "trade_id", "thesis_id", "config_digest", "manifest_sha256",
    "record_count", "final_decision_chain_digest", "replay_output_digest",
    "replay_decision_digest",
    "run_identity_digest", "parity_status", "first_divergent_sequence", "finalized_at",
})


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ShadowEvidenceJournalError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_fields(value: object, fields: frozenset[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or frozenset(value) != fields:
        raise ShadowEvidenceJournalError(f"invalid {name} fields")
    return value


def _string(value: Mapping[str, object], name: str) -> str:
    item = value[name]
    if not isinstance(item, str) or not item:
        raise ShadowEvidenceJournalError(f"{name} must be a non-empty string")
    return item


def _integer(value: Mapping[str, object], name: str, *, optional: bool = False) -> int | None:
    item = value[name]
    if optional and item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int):
        raise ShadowEvidenceJournalError(f"{name} must be an integer")
    return item


def _boolean(value: Mapping[str, object], name: str) -> bool:
    item = value[name]
    if not isinstance(item, bool):
        raise ShadowEvidenceJournalError(f"{name} must be boolean")
    return item


def _decimal(value: Mapping[str, object], name: str) -> Decimal:
    raw = _string(value, name)
    parsed = Decimal(raw)
    if canonical_decimal_string(parsed) != raw:
        raise ShadowEvidenceJournalError(f"{name} is not canonical Decimal")
    return parsed


def _enum_list(enum_type, value: Mapping[str, object], name: str) -> tuple:
    raw = value[name]
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ShadowEvidenceJournalError(f"{name} must be a string list")
    try:
        result = tuple(enum_type(item) for item in raw)
    except ValueError as error:
        raise ShadowEvidenceJournalError(f"unsupported {name}") from error
    if len(result) != len(set(result)):
        raise ShadowEvidenceJournalError(f"{name} must not contain duplicates")
    return result


def _decision_from_wire(payload: dict[str, object]) -> ShadowDecisionEvidence:
    _require_fields(payload, _DECISION_FIELDS, "decision evidence")
    market = _require_fields(payload["market_context"], _MARKET_FIELDS, "market context")
    risk = _require_fields(payload["risk_snapshot"], _RISK_FIELDS, "risk snapshot")
    evaluation = _require_fields(payload["evaluation"], _EVALUATION_FIELDS, "evaluation")
    exit_decision = _require_fields(payload["exit_decision"], _EXIT_FIELDS, "exit decision")
    recommendation_raw = payload["recommendation"]
    recommendation_id = recommendation_reason = None
    if recommendation_raw is not None:
        recommendation = _require_fields(recommendation_raw, _RECOMMENDATION_FIELDS, "recommendation")
        recommendation_id = _string(recommendation, "recommendation_id")
        recommendation_reason = ExitReason(_string(recommendation, "primary_reason"))
    eligibility_raw = payload["eligibility"]
    eligibility_id = eligibility_status = eligible_quantity = None
    eligibility_reasons: tuple[RiskReason, ...] = ()
    if eligibility_raw is not None:
        eligibility = _require_fields(eligibility_raw, _ELIGIBILITY_FIELDS, "eligibility")
        eligibility_id = _string(eligibility, "eligibility_id")
        eligibility_status = ExecutionEligibilityStatus(_string(eligibility, "status"))
        eligibility_reasons = _enum_list(RiskReason, eligibility, "reasons")
        eligible_quantity = _integer(eligibility, "eligible_quantity_shares")
    market_copy = dict(market)
    MarketContextStatus(_string(market, "data_status"))
    _string(market, "source_event_id")
    _string(market, "health_state")
    if market["prior_status"] is not None:
        ThesisStatus(str(market["prior_status"]))
    for name in ("highest_price_since_entry", "volume_baseline_shares"):
        if market[name] is not None:
            _decimal(market, name)
    _integer(market, "completed_bar_count")
    for name in (
        "post_entry_volume_shares",
        "volume_sample_count",
        "completed_bars_below_vwap",
        "consecutive_completed_bars_below_vwap",
        "consecutive_completed_bars_below_breakout",
    ):
        _integer(market, name, optional=True)
    return ShadowDecisionEvidence(
        record_id=_string(payload, "record_id"),
        session_id=_string(payload, "session_id"),
        trade_id=_string(payload, "trade_id"),
        thesis_id=_string(payload, "thesis_id"),
        source_event_id=_string(payload, "source_event_id"),
        occurred_at=datetime.fromisoformat(_string(payload, "occurred_at")),
        config_digest=_string(payload, "config_digest"),
        source_event_digest=_string(payload, "source_event_digest"),
        risk_snapshot_digest=_string(payload, "risk_snapshot_digest"),
        decision_chain_digest=_string(payload, "decision_chain_digest"),
        step_sequence=int(_integer(payload, "step_sequence")),
        market_context=market_copy,
        risk_snapshot=RiskSnapshot(
            data_health_state=_string(risk, "data_health_state"),
            market_open=_boolean(risk, "market_open"),
            instrument_tradable=_boolean(risk, "instrument_tradable"),
            available_cash=_decimal(risk, "available_cash"),
            current_position_shares=int(_integer(risk, "current_position_shares")),
            pending_buy_shares=int(_integer(risk, "pending_buy_shares")),
            pending_sell_shares=int(_integer(risk, "pending_sell_shares")),
            daily_realized_pnl=_decimal(risk, "daily_realized_pnl"),
            same_side_pending_order=_boolean(risk, "same_side_pending_order"),
            book_age_seconds=_integer(risk, "book_age_seconds", optional=True),
        ),
        evaluation_id=_string(evaluation, "evaluation_id"),
        evaluation_input_digest=_string(evaluation, "input_digest"),
        evaluation_status=ThesisStatus(_string(evaluation, "status")),
        evaluation_reasons=_enum_list(ThesisReasonCode, evaluation, "reasons"),
        exit_decision_id=_string(exit_decision, "decision_id"),
        exit_action=ExitAction(_string(exit_decision, "action")),
        exit_reasons=_enum_list(ExitReason, exit_decision, "reasons"),
        recommendation_id=recommendation_id,
        recommendation_reason=recommendation_reason,
        eligibility_id=eligibility_id,
        eligibility_status=eligibility_status,
        eligibility_reasons=eligibility_reasons,
        eligible_quantity_shares=eligible_quantity,
    )


def _finalization_from_wire(payload: dict[str, object]) -> ShadowSessionFinalizationEvidence:
    _require_fields(payload, _FINALIZATION_FIELDS, "finalization evidence")
    first_divergence = _integer(payload, "first_divergent_sequence", optional=True)
    return ShadowSessionFinalizationEvidence(
        session_id=_string(payload, "session_id"),
        trade_id=_string(payload, "trade_id"),
        thesis_id=_string(payload, "thesis_id"),
        config_digest=_string(payload, "config_digest"),
        manifest_sha256=_string(payload, "manifest_sha256"),
        record_count=int(_integer(payload, "record_count")),
        final_decision_chain_digest=_string(payload, "final_decision_chain_digest"),
        replay_decision_digest=_string(payload, "replay_decision_digest"),
        replay_output_digest=_string(payload, "replay_output_digest"),
        run_identity_digest=_string(payload, "run_identity_digest"),
        parity_status=ShadowParityStatus(_string(payload, "parity_status")),
        first_divergent_sequence=first_divergence,
        finalized_at=datetime.fromisoformat(_string(payload, "finalized_at")),
    )


def read_shadow_evidence_record(record: JournalRecord) -> ShadowEvidenceJournalEvent | None:
    try:
        kind = ShadowEvidenceJournalKind(record.kind)
    except ValueError:
        if record.kind.startswith("shadow_"):
            raise ShadowEvidenceJournalError(f"unsupported Shadow evidence kind: {record.kind}")
        return None
    if frozenset(record.payload) != _JOURNAL_PAYLOAD_FIELDS:
        raise ShadowEvidenceJournalError("invalid Shadow evidence Journal payload fields")
    if record.payload["serializer_version"] != SHADOW_EVIDENCE_SERIALIZER_VERSION:
        raise ShadowEvidenceJournalError("unsupported Shadow evidence serializer")
    if record.payload["retention_mode"] != ShadowEvidenceRetentionMode.RETAIN_ALL.value:
        raise ShadowEvidenceJournalError("unsupported Shadow evidence retention mode")
    if record.payload["retention_policy_version"] != DEFAULT_SHADOW_RETENTION_POLICY.version:
        raise ShadowEvidenceJournalError("unsupported Shadow evidence retention policy")
    evidence_json = record.payload["evidence_json"]
    evidence_digest = record.payload["evidence_digest"]
    if not isinstance(evidence_json, str) or not isinstance(evidence_digest, str):
        raise ShadowEvidenceJournalError("invalid Shadow evidence payload types")
    if hashlib.sha256(evidence_json.encode()).hexdigest() != evidence_digest:
        raise ShadowEvidenceJournalError("Shadow evidence digest mismatch")
    try:
        raw = json.loads(evidence_json, object_pairs_hook=_pairs_no_duplicates)
        top = _require_fields(raw, _TOP_FIELDS, "Shadow evidence envelope")
        if top["schema_version"] != SHADOW_EVIDENCE_SCHEMA_VERSION:
            raise ShadowEvidenceJournalError("unsupported Shadow evidence schema")
        payload = top["payload"]
        if not isinstance(payload, dict):
            raise ShadowEvidenceJournalError("Shadow evidence payload must be an object")
        if kind is ShadowEvidenceJournalKind.DECISION_RECORDED:
            if top["contract_type"] != "ShadowDecisionEvidence":
                raise ShadowEvidenceJournalError("decision contract type mismatch")
            decision = _decision_from_wire(payload)
            expected = _journal_record(
                kind,
                decision,
                identity=decision.record_id,
                occurred_at=decision.occurred_at,
                retention=DEFAULT_SHADOW_RETENTION_POLICY,
            )
            event = ShadowEvidenceJournalEvent(kind=kind, decision=decision)
        else:
            if top["contract_type"] != "ShadowSessionFinalizationEvidence":
                raise ShadowEvidenceJournalError("finalization contract type mismatch")
            finalization = _finalization_from_wire(payload)
            expected = _journal_record(
                kind,
                finalization,
                identity=finalization.manifest_sha256,
                occurred_at=finalization.finalized_at,
                retention=DEFAULT_SHADOW_RETENTION_POLICY,
            )
            event = ShadowEvidenceJournalEvent(kind=kind, finalization=finalization)
    except (TypeError, ValueError) as error:
        if isinstance(error, ShadowEvidenceJournalError):
            raise
        raise ShadowEvidenceJournalError(f"cannot decode Shadow evidence record {record.record_id}") from error
    if record.fingerprint != expected.fingerprint:
        raise ShadowEvidenceJournalError(f"non-canonical Shadow evidence record {record.record_id}")
    return event


class ShadowEvidenceProjection:
    def __init__(self) -> None:
        self._decisions: list[ShadowDecisionEvidence] = []
        self._record_ids: set[str] = set()
        self._source_event_ids: set[str] = set()
        self._finalization: ShadowSessionFinalizationEvidence | None = None
        self._session_id: str | None = None
        self._last_sequence = 0

    @property
    def decisions(self) -> tuple[ShadowDecisionEvidence, ...]:
        return tuple(self._decisions)

    @property
    def finalization(self) -> ShadowSessionFinalizationEvidence | None:
        return self._finalization

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def apply(self, result: JournalAppendResult) -> None:
        if result.sequence <= self._last_sequence:
            raise ShadowEvidenceJournalError("Journal sequence must be strictly increasing")
        event = read_shadow_evidence_record(result.record)
        if event is not None:
            self._apply_event(event)
        self._last_sequence = result.sequence

    def _apply_event(self, event: ShadowEvidenceJournalEvent) -> None:
        evidence = event.decision or event.finalization
        assert evidence is not None
        if self._session_id is None:
            self._session_id = evidence.session_id
        elif evidence.session_id != self._session_id:
            raise ShadowEvidenceJournalError("projection cannot mix Journal sessions")
        if event.decision is not None:
            decision = event.decision
            if self._finalization is not None:
                raise ShadowEvidenceJournalError("decision cannot be recorded after finalization")
            if decision.step_sequence != len(self._decisions) + 1:
                raise ShadowEvidenceJournalError("Shadow decision step sequence is not contiguous")
            if decision.record_id in self._record_ids or decision.source_event_id in self._source_event_ids:
                raise ShadowEvidenceJournalError("Shadow decision evidence was journaled twice")
            if self._decisions:
                previous = self._decisions[-1]
                if (decision.trade_id, decision.thesis_id, decision.config_digest) != (
                    previous.trade_id,
                    previous.thesis_id,
                    previous.config_digest,
                ):
                    raise ShadowEvidenceJournalError("Shadow decision identity changed")
                if decision.occurred_at < previous.occurred_at:
                    raise ShadowEvidenceJournalError("Shadow decision time moved backward")
            self._decisions.append(decision)
            self._record_ids.add(decision.record_id)
            self._source_event_ids.add(decision.source_event_id)
            return
        finalization = event.finalization
        assert finalization is not None
        if self._finalization is not None:
            raise ShadowEvidenceJournalError("Shadow session was finalized twice")
        if finalization.record_count != len(self._decisions):
            raise ShadowEvidenceJournalError("Shadow finalization record count mismatch")
        if not self._decisions:
            raise ShadowEvidenceJournalError("Shadow finalization requires decisions")
        first = self._decisions[0]
        last = self._decisions[-1]
        if (
            finalization.trade_id != first.trade_id
            or finalization.thesis_id != first.thesis_id
            or finalization.config_digest != first.config_digest
            or finalization.final_decision_chain_digest != last.decision_chain_digest
            or finalization.finalized_at != last.occurred_at
        ):
            raise ShadowEvidenceJournalError("Shadow finalization does not match decision chain")
        self._finalization = finalization

    @property
    def digest(self) -> str:
        payload = {
            "projection_name": SHADOW_EVIDENCE_PROJECTION_NAME,
            "schema_version": SHADOW_EVIDENCE_SCHEMA_VERSION,
            "session_id": self._session_id,
            "last_sequence": self._last_sequence,
            "retention_policy": {
                "version": DEFAULT_SHADOW_RETENTION_POLICY.version,
                "mode": DEFAULT_SHADOW_RETENTION_POLICY.mode.value,
                "compaction_allowed": False,
            },
            "decisions": [_evidence_wire(item) for item in self._decisions],
            "finalization": None if self._finalization is None else _evidence_wire(self._finalization),
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def append_shadow_session_evidence(
    journal: JournalRepository,
    session: ShadowDecisionSession,
) -> tuple[JournalAppendResult, ...]:
    records = [journal_record_for_shadow_decision(item) for item in session.records]
    records.append(journal_record_for_shadow_session(session))
    return tuple(journal.append(record) for record in records)


def rebuild_shadow_evidence_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    require_checkpoint: bool = True,
) -> ShadowEvidenceProjection:
    checkpoint = journal.latest_checkpoint(session_id, SHADOW_EVIDENCE_PROJECTION_NAME)
    if require_checkpoint and checkpoint is None:
        raise ShadowEvidenceJournalError("Shadow evidence recovery requires a checkpoint")
    projection = ShadowEvidenceProjection()
    checkpoint_digest = projection.digest if checkpoint is not None and checkpoint.journal_sequence == 0 else None
    for result in journal.records(session_id):
        projection.apply(result)
        if checkpoint is not None and result.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest
    if checkpoint is not None:
        if checkpoint_digest is None:
            raise ShadowEvidenceJournalError("Shadow evidence checkpoint sequence is absent from Journal")
        if checkpoint_digest != checkpoint.digest:
            raise ShadowEvidenceJournalError("Shadow evidence checkpoint digest mismatch")
    return projection


def write_shadow_evidence_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
) -> ShadowEvidenceProjection:
    projection = rebuild_shadow_evidence_projection(
        journal,
        session_id=session_id,
        require_checkpoint=False,
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=session_id,
            projection_name=SHADOW_EVIDENCE_PROJECTION_NAME,
            journal_sequence=projection.last_sequence,
            digest=projection.digest,
        )
    )
    return projection
