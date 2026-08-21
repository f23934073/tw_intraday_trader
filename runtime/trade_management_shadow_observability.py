"""Read-only observability and readiness evidence for Trade Management Shadow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum

from trading.canonical_values import canonical_decimal_string
from trading.trade_management_shadow import ShadowParityStatus


SHADOW_OBSERVABILITY_VERSION = "trade-management-shadow-observability-v1"


class ShadowOperationHealth(StrEnum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    RECOVERING = "RECOVERING"
    FINALIZED = "FINALIZED"


class ShadowReadinessStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"


class ShadowReadinessReason(StrEnum):
    SESSION_NOT_FINALIZED = "SESSION_NOT_FINALIZED"
    INSUFFICIENT_FINALIZED_SESSIONS = "INSUFFICIENT_FINALIZED_SESSIONS"
    INSUFFICIENT_OBSERVATION_TIME = "INSUFFICIENT_OBSERVATION_TIME"
    INSUFFICIENT_DECISION_RECORDS = "INSUFFICIENT_DECISION_RECORDS"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    EVENT_BACKLOG_PRESENT = "EVENT_BACKLOG_PRESENT"
    PARITY_DIVERGENCE = "PARITY_DIVERGENCE"
    PARITY_RATE_BELOW_THRESHOLD = "PARITY_RATE_BELOW_THRESHOLD"
    WRITER_FAILURE_LIMIT_EXCEEDED = "WRITER_FAILURE_LIMIT_EXCEEDED"
    RECOVERY_TIME_EXCEEDED = "RECOVERY_TIME_EXCEEDED"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_non_negative(value: int | Decimal, field_name: str) -> None:
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True)
class ShadowOperationMetrics:
    version: str
    session_id: str
    observed_at: datetime
    health: ShadowOperationHealth
    admitted_message_count: int
    processed_message_count: int
    pending_market_event_count: int
    oldest_pending_event_age_seconds: Decimal | None
    applied_event_count: int
    rejected_event_count: int
    decision_record_count: int
    durable_decision_count: int
    pending_evidence_count: int
    oldest_pending_age_seconds: Decimal | None
    writer_failure_count: int
    recovery_count: int
    last_recovery_seconds: Decimal | None
    observation_seconds: Decimal
    finalized: bool
    finalization_persisted: bool
    parity_status: ShadowParityStatus | None
    first_divergent_sequence: int | None

    def __post_init__(self) -> None:
        if self.version != SHADOW_OBSERVABILITY_VERSION:
            raise ValueError("unsupported Shadow observability version")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        for value, field_name in (
            (self.admitted_message_count, "admitted_message_count"),
            (self.processed_message_count, "processed_message_count"),
            (self.pending_market_event_count, "pending_market_event_count"),
            (self.applied_event_count, "applied_event_count"),
            (self.rejected_event_count, "rejected_event_count"),
            (self.decision_record_count, "decision_record_count"),
            (self.durable_decision_count, "durable_decision_count"),
            (self.pending_evidence_count, "pending_evidence_count"),
            (self.writer_failure_count, "writer_failure_count"),
            (self.recovery_count, "recovery_count"),
            (self.observation_seconds, "observation_seconds"),
        ):
            _require_non_negative(value, field_name)
        if self.processed_message_count > self.admitted_message_count:
            raise ValueError("processed messages exceed admitted messages")
        if self.pending_market_event_count > (
            self.admitted_message_count - self.processed_message_count
        ):
            raise ValueError("pending market events exceed pending messages")
        if self.pending_market_event_count == 0:
            if self.oldest_pending_event_age_seconds is not None:
                raise ValueError("empty market backlog cannot have an age")
        elif self.oldest_pending_event_age_seconds is None:
            raise ValueError("pending market events require oldest age")
        if self.oldest_pending_event_age_seconds is not None:
            _require_non_negative(
                self.oldest_pending_event_age_seconds,
                "oldest_pending_event_age_seconds",
            )
        if self.applied_event_count + self.rejected_event_count > self.processed_message_count:
            raise ValueError("market result counts exceed processed messages")
        if self.durable_decision_count + self.pending_evidence_count > self.decision_record_count:
            raise ValueError("evidence counts exceed emitted decisions")
        if self.pending_evidence_count == 0:
            if self.oldest_pending_age_seconds is not None:
                raise ValueError("empty pending evidence cannot have an age")
        elif self.oldest_pending_age_seconds is None:
            raise ValueError("pending evidence requires oldest age")
        if self.oldest_pending_age_seconds is not None:
            _require_non_negative(
                self.oldest_pending_age_seconds,
                "oldest_pending_age_seconds",
            )
        if self.recovery_count == 0:
            if self.last_recovery_seconds is not None:
                raise ValueError("no recovery cannot have a duration")
        elif self.last_recovery_seconds is None:
            raise ValueError("recovery count requires last duration")
        if self.last_recovery_seconds is not None:
            _require_non_negative(self.last_recovery_seconds, "last_recovery_seconds")
        if self.finalized != (self.health is ShadowOperationHealth.FINALIZED):
            raise ValueError("FINALIZED health must match finalized flag")
        if self.finalization_persisted and not self.finalized:
            raise ValueError("persisted finalization requires finalized session")
        if self.finalized and self.parity_status is None:
            raise ValueError("finalized session requires parity status")
        if not self.finalized and self.parity_status is not None:
            raise ValueError("active session cannot report final parity")
        if self.parity_status is ShadowParityStatus.MATCHED:
            if self.first_divergent_sequence is not None:
                raise ValueError("MATCHED parity cannot have divergent sequence")
        elif self.parity_status is ShadowParityStatus.DIVERGED:
            if self.first_divergent_sequence is None or self.first_divergent_sequence <= 0:
                raise ValueError("DIVERGED parity requires positive divergent sequence")
        elif self.first_divergent_sequence is not None:
            raise ValueError("active session cannot have divergent sequence")

    @property
    def lost_evidence_count(self) -> int:
        return (
            self.decision_record_count
            - self.durable_decision_count
            - self.pending_evidence_count
        )

    @property
    def evidence_complete(self) -> bool:
        return (
            self.finalized
            and self.finalization_persisted
            and self.pending_evidence_count == 0
            and self.lost_evidence_count == 0
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "session_id": self.session_id,
                "observed_at": self.observed_at.isoformat(),
                "health": self.health.value,
                "admitted_message_count": self.admitted_message_count,
                "processed_message_count": self.processed_message_count,
                "pending_market_event_count": self.pending_market_event_count,
                "oldest_pending_event_age_seconds": (
                    None
                    if self.oldest_pending_event_age_seconds is None
                    else canonical_decimal_string(
                        self.oldest_pending_event_age_seconds
                    )
                ),
                "applied_event_count": self.applied_event_count,
                "rejected_event_count": self.rejected_event_count,
                "decision_record_count": self.decision_record_count,
                "durable_decision_count": self.durable_decision_count,
                "pending_evidence_count": self.pending_evidence_count,
                "oldest_pending_age_seconds": (
                    None
                    if self.oldest_pending_age_seconds is None
                    else canonical_decimal_string(self.oldest_pending_age_seconds)
                ),
                "writer_failure_count": self.writer_failure_count,
                "recovery_count": self.recovery_count,
                "last_recovery_seconds": (
                    None
                    if self.last_recovery_seconds is None
                    else canonical_decimal_string(self.last_recovery_seconds)
                ),
                "observation_seconds": canonical_decimal_string(
                    self.observation_seconds
                ),
                "finalized": self.finalized,
                "finalization_persisted": self.finalization_persisted,
                "parity_status": (
                    None if self.parity_status is None else self.parity_status.value
                ),
                "first_divergent_sequence": self.first_divergent_sequence,
            }
        )


@dataclass(frozen=True)
class ShadowReadinessPolicy:
    version: str
    min_finalized_sessions: int
    min_total_observation_seconds: Decimal
    min_total_decision_records: int
    min_parity_rate: Decimal
    max_writer_failures: int
    max_recovery_seconds: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("readiness policy version must not be empty")
        if self.min_finalized_sessions <= 0:
            raise ValueError("min_finalized_sessions must be positive")
        if self.min_total_decision_records <= 0:
            raise ValueError("min_total_decision_records must be positive")
        for value, field_name in (
            (self.min_total_observation_seconds, "min_total_observation_seconds"),
            (self.min_parity_rate, "min_parity_rate"),
            (self.max_writer_failures, "max_writer_failures"),
            (self.max_recovery_seconds, "max_recovery_seconds"),
        ):
            _require_non_negative(value, field_name)
        if self.min_parity_rate > Decimal("1"):
            raise ValueError("min_parity_rate must be between zero and one")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "min_finalized_sessions": self.min_finalized_sessions,
                "min_total_observation_seconds": canonical_decimal_string(
                    self.min_total_observation_seconds
                ),
                "min_total_decision_records": self.min_total_decision_records,
                "min_parity_rate": canonical_decimal_string(self.min_parity_rate),
                "max_writer_failures": self.max_writer_failures,
                "max_recovery_seconds": canonical_decimal_string(
                    self.max_recovery_seconds
                ),
            }
        )


@dataclass(frozen=True)
class ShadowReadinessReport:
    report_id: str
    input_digest: str
    policy_version: str
    status: ShadowReadinessStatus
    reasons: tuple[ShadowReadinessReason, ...]
    finalized_session_count: int
    total_observation_seconds: Decimal
    total_decision_records: int
    durable_decision_count: int
    pending_evidence_count: int
    pending_market_event_count: int
    lost_evidence_count: int
    matched_session_count: int
    diverged_session_count: int
    divergent_session_ids: tuple[str, ...]
    parity_rate: Decimal
    evidence_complete: bool
    execution_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.input_digest.strip():
            raise ValueError("readiness report identity must not be empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        if self.execution_enabled:
            raise ValueError("readiness evidence cannot enable execution")
        if self.status is ShadowReadinessStatus.READY and self.reasons:
            raise ValueError("READY report cannot have failure reasons")
        if self.status is ShadowReadinessStatus.NOT_READY and not self.reasons:
            raise ValueError("NOT_READY report requires failure reasons")
        if self.matched_session_count + self.diverged_session_count > self.finalized_session_count:
            raise ValueError("parity counts exceed finalized sessions")
        if len(self.divergent_session_ids) != self.diverged_session_count:
            raise ValueError("divergent session identities do not match count")
        _require_non_negative(self.parity_rate, "parity_rate")
        if self.parity_rate > Decimal("1"):
            raise ValueError("parity_rate must be between zero and one")


class ShadowReadinessEvaluator:
    """Classify immutable Shadow evidence without changing runtime authority."""

    __slots__ = ()

    def evaluate(
        self,
        policy: ShadowReadinessPolicy,
        sessions: tuple[ShadowOperationMetrics, ...],
    ) -> ShadowReadinessReport:
        ordered = tuple(sorted(sessions, key=lambda item: item.session_id))
        if len({item.session_id for item in ordered}) != len(ordered):
            raise ValueError("readiness sessions must be unique")
        finalized = tuple(item for item in ordered if item.finalized)
        total_observation = sum(
            (item.observation_seconds for item in finalized),
            Decimal("0"),
        )
        total_decisions = sum(item.decision_record_count for item in finalized)
        durable = sum(item.durable_decision_count for item in finalized)
        pending = sum(item.pending_evidence_count for item in ordered)
        pending_market = sum(item.pending_market_event_count for item in ordered)
        lost = sum(item.lost_evidence_count for item in ordered)
        matched = sum(
            item.parity_status is ShadowParityStatus.MATCHED for item in finalized
        )
        diverged = sum(
            item.parity_status is ShadowParityStatus.DIVERGED for item in finalized
        )
        divergent_session_ids = tuple(
            item.session_id
            for item in finalized
            if item.parity_status is ShadowParityStatus.DIVERGED
        )
        with localcontext() as context:
            context.prec = 28
            parity_rate = (
                Decimal(matched) / Decimal(len(finalized))
                if finalized
                else Decimal("0")
            )
        writer_failures = sum(item.writer_failure_count for item in ordered)
        recovery_durations = tuple(
            item.last_recovery_seconds
            for item in ordered
            if item.last_recovery_seconds is not None
        )
        max_recovery = max(recovery_durations, default=Decimal("0"))
        evidence_complete = bool(ordered) and all(
            item.evidence_complete for item in ordered
        )

        failures: set[ShadowReadinessReason] = set()
        if len(finalized) != len(ordered):
            failures.add(ShadowReadinessReason.SESSION_NOT_FINALIZED)
        if len(finalized) < policy.min_finalized_sessions:
            failures.add(ShadowReadinessReason.INSUFFICIENT_FINALIZED_SESSIONS)
        if total_observation < policy.min_total_observation_seconds:
            failures.add(ShadowReadinessReason.INSUFFICIENT_OBSERVATION_TIME)
        if total_decisions < policy.min_total_decision_records:
            failures.add(ShadowReadinessReason.INSUFFICIENT_DECISION_RECORDS)
        if not evidence_complete:
            failures.add(ShadowReadinessReason.EVIDENCE_INCOMPLETE)
        if pending_market:
            failures.add(ShadowReadinessReason.EVENT_BACKLOG_PRESENT)
        if diverged:
            failures.add(ShadowReadinessReason.PARITY_DIVERGENCE)
        if parity_rate < policy.min_parity_rate:
            failures.add(ShadowReadinessReason.PARITY_RATE_BELOW_THRESHOLD)
        if writer_failures > policy.max_writer_failures:
            failures.add(ShadowReadinessReason.WRITER_FAILURE_LIMIT_EXCEEDED)
        if max_recovery > policy.max_recovery_seconds:
            failures.add(ShadowReadinessReason.RECOVERY_TIME_EXCEEDED)

        reasons = tuple(
            reason for reason in ShadowReadinessReason if reason in failures
        )
        input_digest = _digest(
            {
                "observability_version": SHADOW_OBSERVABILITY_VERSION,
                "policy_digest": policy.digest,
                "session_digests": [item.digest for item in ordered],
            }
        )
        return ShadowReadinessReport(
            report_id="shadow_readiness_v1_" + input_digest,
            input_digest=input_digest,
            policy_version=policy.version,
            status=(
                ShadowReadinessStatus.READY
                if not reasons
                else ShadowReadinessStatus.NOT_READY
            ),
            reasons=reasons,
            finalized_session_count=len(finalized),
            total_observation_seconds=total_observation,
            total_decision_records=total_decisions,
            durable_decision_count=durable,
            pending_evidence_count=pending,
            pending_market_event_count=pending_market,
            lost_evidence_count=lost,
            matched_session_count=matched,
            diverged_session_count=diverged,
            divergent_session_ids=divergent_session_ids,
            parity_rate=parity_rate,
            evidence_complete=evidence_complete,
        )
