"""Pure extended-validation evidence for Trade Management Shadow.

This module classifies finalized Shadow evidence and controlled operational
drills.  It cannot persist evidence, influence decisions, or enable execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from runtime.trade_management_shadow_observability import (
    ShadowOperationMetrics,
    ShadowReadinessEvaluator,
    ShadowReadinessPolicy,
    ShadowReadinessReport,
    ShadowReadinessStatus,
)
from trading.canonical_values import canonical_decimal_string
from trading.trade_management_shadow import ShadowParityStatus


SHADOW_VALIDATION_VERSION = "trade-management-shadow-validation-v1"


class ShadowSourceClass(StrEnum):
    LIVE_MARKET = "LIVE_MARKET"
    TEST_FIXTURE = "TEST_FIXTURE"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"


class ShadowOperationalDrillType(StrEnum):
    JOURNAL_RECOVERY = "JOURNAL_RECOVERY"
    PARITY_DIVERGENCE = "PARITY_DIVERGENCE"


class ShadowValidationStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class ShadowValidationReason(StrEnum):
    BASE_READINESS_NOT_READY = "BASE_READINESS_NOT_READY"
    INSUFFICIENT_COMPLETE_SESSIONS = "INSUFFICIENT_COMPLETE_SESSIONS"
    INSUFFICIENT_MARKET_DATES = "INSUFFICIENT_MARKET_DATES"
    NON_LIVE_MARKET_SOURCE = "NON_LIVE_MARKET_SOURCE"
    SESSION_COVERAGE_INCOMPLETE = "SESSION_COVERAGE_INCOMPLETE"
    SESSION_EVIDENCE_INCOMPLETE = "SESSION_EVIDENCE_INCOMPLETE"
    CHECKPOINT_RECOVERY_MISMATCH = "CHECKPOINT_RECOVERY_MISMATCH"
    RECOVERY_DRILL_MISSING = "RECOVERY_DRILL_MISSING"
    RECOVERY_DRILL_FAILED = "RECOVERY_DRILL_FAILED"
    DIVERGENCE_DRILL_MISSING = "DIVERGENCE_DRILL_MISSING"
    DIVERGENCE_DRILL_FAILED = "DIVERGENCE_DRILL_FAILED"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_digest(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class ShadowSessionSource:
    source_class: ShadowSourceClass
    provider: str
    provider_version: str
    connection_session_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.provider, "provider"),
            (self.provider_version, "provider_version"),
            (self.connection_session_id, "connection_session_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "source_class": self.source_class.value,
                "provider": self.provider,
                "provider_version": self.provider_version,
                "connection_session_id": self.connection_session_id,
            }
        )


@dataclass(frozen=True)
class ShadowValidationSession:
    version: str
    session_id: str
    market_date: date
    source: ShadowSessionSource
    coverage_started_at: datetime
    coverage_ended_at: datetime
    metrics: ShadowOperationMetrics
    durable_projection_digest: str
    recovered_projection_digest: str

    def __post_init__(self) -> None:
        if self.version != SHADOW_VALIDATION_VERSION:
            raise ValueError("unsupported Shadow validation version")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if self.metrics.session_id != self.session_id:
            raise ValueError("validation session does not match operation metrics")
        _require_aware(self.coverage_started_at, "coverage_started_at")
        _require_aware(self.coverage_ended_at, "coverage_ended_at")
        if self.coverage_ended_at <= self.coverage_started_at:
            raise ValueError("coverage must have positive duration")
        if self.coverage_started_at.date() != self.market_date:
            raise ValueError("coverage start must match market_date")
        if self.coverage_ended_at.date() != self.market_date:
            raise ValueError("coverage end must match market_date")
        if self.metrics.observed_at.date() != self.market_date:
            raise ValueError("operation metrics must match market_date")
        if self.metrics.observation_seconds < self.coverage_seconds:
            raise ValueError("operation observation cannot be shorter than coverage")
        for value, field_name in (
            (self.durable_projection_digest, "durable_projection_digest"),
            (self.recovered_projection_digest, "recovered_projection_digest"),
        ):
            _require_digest(value, field_name)

    @property
    def coverage_seconds(self) -> Decimal:
        return Decimal(str((self.coverage_ended_at - self.coverage_started_at).total_seconds()))

    @property
    def checkpoint_recovery_verified(self) -> bool:
        return self.durable_projection_digest == self.recovered_projection_digest

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "session_id": self.session_id,
                "market_date": self.market_date.isoformat(),
                "source_digest": self.source.digest,
                "coverage_started_at": self.coverage_started_at.isoformat(),
                "coverage_ended_at": self.coverage_ended_at.isoformat(),
                "metrics_digest": self.metrics.digest,
                "durable_projection_digest": self.durable_projection_digest,
                "recovered_projection_digest": self.recovered_projection_digest,
            }
        )


@dataclass(frozen=True)
class ShadowOperationalDrill:
    version: str
    drill_id: str
    drill_type: ShadowOperationalDrillType
    started_at: datetime
    completed_at: datetime
    failure_detected: bool
    fail_closed_observed: bool
    recovery_verified: bool
    investigation_completed: bool
    first_divergent_sequence: int | None
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.version != SHADOW_VALIDATION_VERSION:
            raise ValueError("unsupported Shadow validation version")
        if not self.drill_id.strip():
            raise ValueError("drill_id must not be empty")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.completed_at, "completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("drill completion cannot precede start")
        _require_digest(self.evidence_digest, "evidence_digest")
        if self.drill_type is ShadowOperationalDrillType.JOURNAL_RECOVERY:
            if self.first_divergent_sequence is not None:
                raise ValueError("recovery drill cannot have divergent sequence")
        elif self.first_divergent_sequence is not None and self.first_divergent_sequence <= 0:
            raise ValueError("divergent sequence must be positive")

    @property
    def passed(self) -> bool:
        common = self.failure_detected and self.fail_closed_observed
        if self.drill_type is ShadowOperationalDrillType.JOURNAL_RECOVERY:
            return common and self.recovery_verified
        return (
            common
            and self.investigation_completed
            and self.first_divergent_sequence is not None
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "drill_id": self.drill_id,
                "drill_type": self.drill_type.value,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
                "failure_detected": self.failure_detected,
                "fail_closed_observed": self.fail_closed_observed,
                "recovery_verified": self.recovery_verified,
                "investigation_completed": self.investigation_completed,
                "first_divergent_sequence": self.first_divergent_sequence,
                "evidence_digest": self.evidence_digest,
            }
        )


@dataclass(frozen=True)
class ShadowValidationPolicy:
    version: str
    min_complete_sessions: int
    min_distinct_market_dates: int
    min_session_coverage_seconds: Decimal
    require_live_market_source: bool
    require_recovery_drill: bool
    require_divergence_drill: bool

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("validation policy version must not be empty")
        if self.min_complete_sessions <= 0:
            raise ValueError("min_complete_sessions must be positive")
        if self.min_distinct_market_dates <= 0:
            raise ValueError("min_distinct_market_dates must be positive")
        if not self.min_session_coverage_seconds.is_finite():
            raise ValueError("min_session_coverage_seconds must be finite")
        if self.min_session_coverage_seconds <= 0:
            raise ValueError("min_session_coverage_seconds must be positive")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "min_complete_sessions": self.min_complete_sessions,
                "min_distinct_market_dates": self.min_distinct_market_dates,
                "min_session_coverage_seconds": canonical_decimal_string(
                    self.min_session_coverage_seconds
                ),
                "require_live_market_source": self.require_live_market_source,
                "require_recovery_drill": self.require_recovery_drill,
                "require_divergence_drill": self.require_divergence_drill,
            }
        )


@dataclass(frozen=True)
class ShadowValidationReport:
    report_id: str
    input_digest: str
    policy_version: str
    status: ShadowValidationStatus
    reasons: tuple[ShadowValidationReason, ...]
    readiness_report: ShadowReadinessReport
    complete_session_count: int
    distinct_market_dates: tuple[date, ...]
    incomplete_session_ids: tuple[str, ...]
    non_live_session_ids: tuple[str, ...]
    passed_drill_ids: tuple[str, ...]
    failed_drill_ids: tuple[str, ...]
    execution_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.input_digest.strip():
            raise ValueError("validation report identity must not be empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        if self.execution_enabled:
            raise ValueError("validation evidence cannot enable execution")
        if self.status is ShadowValidationStatus.PASSED and self.reasons:
            raise ValueError("PASSED report cannot have failure reasons")
        if self.status is ShadowValidationStatus.FAILED and not self.reasons:
            raise ValueError("FAILED report requires failure reasons")


class ShadowValidationEvaluator:
    """Aggregate immutable session and drill evidence without side effects."""

    __slots__ = ()

    def evaluate(
        self,
        policy: ShadowValidationPolicy,
        readiness_policy: ShadowReadinessPolicy,
        sessions: tuple[ShadowValidationSession, ...],
        drills: tuple[ShadowOperationalDrill, ...],
    ) -> ShadowValidationReport:
        ordered_sessions = tuple(sorted(sessions, key=lambda item: item.session_id))
        ordered_drills = tuple(sorted(drills, key=lambda item: item.drill_id))
        if len({item.session_id for item in ordered_sessions}) != len(ordered_sessions):
            raise ValueError("validation sessions must be unique")
        if len({item.drill_id for item in ordered_drills}) != len(ordered_drills):
            raise ValueError("operational drills must be unique")

        readiness = ShadowReadinessEvaluator().evaluate(
            readiness_policy,
            tuple(item.metrics for item in ordered_sessions),
        )
        coverage_incomplete = tuple(
            item.session_id
            for item in ordered_sessions
            if item.coverage_seconds < policy.min_session_coverage_seconds
        )
        evidence_incomplete = tuple(
            item.session_id
            for item in ordered_sessions
            if not item.metrics.evidence_complete
            or item.metrics.parity_status is not ShadowParityStatus.MATCHED
        )
        checkpoint_mismatch = tuple(
            item.session_id
            for item in ordered_sessions
            if not item.checkpoint_recovery_verified
        )
        incomplete_ids = tuple(
            sorted(set(coverage_incomplete + evidence_incomplete + checkpoint_mismatch))
        )
        non_live_ids = tuple(
            item.session_id
            for item in ordered_sessions
            if item.source.source_class is not ShadowSourceClass.LIVE_MARKET
        )
        qualifying_sessions = tuple(
            item
            for item in ordered_sessions
            if item.session_id not in incomplete_ids
            and (
                not policy.require_live_market_source
                or item.session_id not in non_live_ids
            )
        )
        complete_session_count = len(qualifying_sessions)
        distinct_dates = tuple(
            sorted({item.market_date for item in qualifying_sessions})
        )

        recovery_drills = tuple(
            item
            for item in ordered_drills
            if item.drill_type is ShadowOperationalDrillType.JOURNAL_RECOVERY
        )
        divergence_drills = tuple(
            item
            for item in ordered_drills
            if item.drill_type is ShadowOperationalDrillType.PARITY_DIVERGENCE
        )
        passed_drill_ids = tuple(item.drill_id for item in ordered_drills if item.passed)
        failed_drill_ids = tuple(item.drill_id for item in ordered_drills if not item.passed)

        failures: set[ShadowValidationReason] = set()
        if readiness.status is ShadowReadinessStatus.NOT_READY:
            failures.add(ShadowValidationReason.BASE_READINESS_NOT_READY)
        if complete_session_count < policy.min_complete_sessions:
            failures.add(ShadowValidationReason.INSUFFICIENT_COMPLETE_SESSIONS)
        if len(distinct_dates) < policy.min_distinct_market_dates:
            failures.add(ShadowValidationReason.INSUFFICIENT_MARKET_DATES)
        if policy.require_live_market_source and non_live_ids:
            failures.add(ShadowValidationReason.NON_LIVE_MARKET_SOURCE)
        if coverage_incomplete:
            failures.add(ShadowValidationReason.SESSION_COVERAGE_INCOMPLETE)
        if evidence_incomplete:
            failures.add(ShadowValidationReason.SESSION_EVIDENCE_INCOMPLETE)
        if checkpoint_mismatch:
            failures.add(ShadowValidationReason.CHECKPOINT_RECOVERY_MISMATCH)
        if policy.require_recovery_drill:
            if not recovery_drills:
                failures.add(ShadowValidationReason.RECOVERY_DRILL_MISSING)
            elif not all(item.passed for item in recovery_drills):
                failures.add(ShadowValidationReason.RECOVERY_DRILL_FAILED)
        if policy.require_divergence_drill:
            if not divergence_drills:
                failures.add(ShadowValidationReason.DIVERGENCE_DRILL_MISSING)
            elif not all(item.passed for item in divergence_drills):
                failures.add(ShadowValidationReason.DIVERGENCE_DRILL_FAILED)

        reasons = tuple(reason for reason in ShadowValidationReason if reason in failures)
        input_digest = _digest(
            {
                "validation_version": SHADOW_VALIDATION_VERSION,
                "policy_digest": policy.digest,
                "readiness_policy_digest": readiness_policy.digest,
                "readiness_report_id": readiness.report_id,
                "session_digests": [item.digest for item in ordered_sessions],
                "drill_digests": [item.digest for item in ordered_drills],
            }
        )
        return ShadowValidationReport(
            report_id="shadow_validation_v1_" + input_digest,
            input_digest=input_digest,
            policy_version=policy.version,
            status=(
                ShadowValidationStatus.PASSED
                if not reasons
                else ShadowValidationStatus.FAILED
            ),
            reasons=reasons,
            readiness_report=readiness,
            complete_session_count=complete_session_count,
            distinct_market_dates=distinct_dates,
            incomplete_session_ids=incomplete_ids,
            non_live_session_ids=non_live_ids,
            passed_drill_ids=passed_drill_ids,
            failed_drill_ids=failed_drill_ids,
        )
