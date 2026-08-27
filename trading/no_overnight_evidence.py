"""Strict, read-only evidence reports for the no-overnight rollout."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from trading.application import order_command_from_record
from trading.exposure import (
    ExecutionReasonCategory,
    ExposureIdentity,
    PositionAction,
)
from trading.journal import JournalAppendResult, JournalRecord, JournalRepository
from trading.journal import JournalSession
from trading.local_paper import (
    LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
    LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
    LOCAL_PAPER_FILL_V4_KIND,
    LOCAL_PAPER_ORDER_STATE_V2_KIND,
    LOCAL_PAPER_V2_PROJECTION_NAME,
    LocalPaperExposureFill,
    latest_local_paper_order_states,
    rebuild_local_paper_v2_projection,
)
from trading.no_overnight import NoOvernightState, ReconciliationStatus
from trading.no_overnight_journal import (
    NO_OVERNIGHT_PROJECTION_NAME,
    NO_OVERNIGHT_TRANSITION_KIND,
    rebuild_no_overnight_projection,
)
from trading.no_overnight_admission import ExecutionAdmissionDecision
from trading.risk import CommandSide


NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA = "no_overnight_session_evidence_v2"
POSTGRES_DESTRUCTIVE_UAT_WAIVER = "WAIVED_NOT_RUN_NOT_PASSED"
_NO_OVERNIGHT_SESSION_ID_PREFIX = "no-overnight-v1-"
_EXPECTED_FILL_SOURCE = "paper_simulation"
NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND = (
    "no_overnight_evidence_window_opened.v1"
)
NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND = (
    "no_overnight_evidence_window_closed.v1"
)


class NoOvernightEvidenceStage(StrEnum):
    DISABLED_BASELINE = "DISABLED_BASELINE"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    SUPERVISED_ENFORCING = "SUPERVISED_ENFORCING"


class NoOvernightEvidenceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class NoOvernightQualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NoOvernightCampaignStatus(StrEnum):
    INCOMPLETE = "INCOMPLETE"
    READY_FOR_INDEPENDENT_REVIEW = "READY_FOR_INDEPENDENT_REVIEW"


class NoOvernightDrillKind(StrEnum):
    RESTART_RECOVERY = "RESTART_RECOVERY"
    DUPLICATE_PROCESS = "DUPLICATE_PROCESS"
    BREACH = "BREACH"


class NoOvernightDrillStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"


class NoOvernightParameterReviewStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FROZEN = "FROZEN"


class NoOvernightParameterReviewPhase(StrEnum):
    PRE_ENFORCEMENT_APPROVAL = "PRE_ENFORCEMENT_APPROVAL"
    POST_UAT_VALIDATION = "POST_UAT_VALIDATION"


@dataclass(frozen=True)
class NoOvernightEvidenceWindowSpec:
    campaign_id: str
    stage: NoOvernightEvidenceStage
    session_date: date
    account_scope_id: str
    policy_family_id: str
    policy_version: str
    policy_digest: str
    calendar_schema_version: str
    calendar_digest: str
    timezone: str
    reviewed_open: datetime
    reviewed_close: datetime
    code_identity: str
    expected_provider_identity: str
    local_paper_session_id: str
    expected_deployment_manifest_digest: str | None = None
    expected_guard_identity: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "account_scope_id",
            "policy_family_id",
            "policy_version",
            "calendar_schema_version",
            "timezone",
            "code_identity",
            "expected_provider_identity",
            "local_paper_session_id",
        ):
            _text(getattr(self, field_name), field_name)
        if not isinstance(self.stage, NoOvernightEvidenceStage):
            raise ValueError("stage is unsupported")
        if type(self.session_date) is not date:
            raise ValueError("session_date must be a date")
        _sha256(self.policy_digest, "policy_digest")
        _sha256(self.calendar_digest, "calendar_digest")
        _optional_sha256(
            self.expected_deployment_manifest_digest,
            "expected_deployment_manifest_digest",
        )
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a recognized IANA timezone") from error
        for field_name in ("reviewed_open", "reviewed_close"):
            value = getattr(self, field_name)
            _aware(value, field_name)
            if value.astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
                raise ValueError(f"{field_name} timezone differs from campaign timezone")
        if self.reviewed_open >= self.reviewed_close:
            raise ValueError("reviewed session window is invalid")
        if (
            self.reviewed_open.date() != self.session_date
            or self.reviewed_close.date() != self.session_date
        ):
            raise ValueError("reviewed window differs from session_date")
        if self.stage is NoOvernightEvidenceStage.SUPERVISED_ENFORCING:
            if self.expected_deployment_manifest_digest is None:
                raise ValueError("supervised ENFORCING requires deployment manifest")
            _text(self.expected_guard_identity, "expected_guard_identity")
        elif (
            self.expected_deployment_manifest_digest is not None
            or self.expected_guard_identity is not None
        ):
            raise ValueError("non-enforcing observation cannot carry guard authority")

    def payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "stage": self.stage.value,
            "session_date": self.session_date.isoformat(),
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "calendar_schema_version": self.calendar_schema_version,
            "calendar_digest": self.calendar_digest,
            "timezone": self.timezone,
            "reviewed_open": self.reviewed_open.isoformat(),
            "reviewed_close": self.reviewed_close.isoformat(),
            "code_identity": self.code_identity,
            "expected_provider_identity": self.expected_provider_identity,
            "local_paper_session_id": self.local_paper_session_id,
            "expected_deployment_manifest_digest": (
                self.expected_deployment_manifest_digest
            ),
            "expected_guard_identity": self.expected_guard_identity,
        }


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be a normalized non-empty string")
    return value


def _sha256(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _optional_sha256(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, field_name)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    field_name: str,
) -> None:
    if frozenset(value) != expected:
        raise ValueError(f"{field_name} fields do not match contract")


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_integer(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field_name)


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _duration_microseconds(later: datetime, earlier: datetime, label: str) -> int:
    delta = later - earlier
    if delta.total_seconds() < 0:
        raise ValueError(f"{label} evidence time moved backwards")
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


@dataclass(frozen=True)
class NoOvernightEvidenceObservation:
    campaign_id: str
    stage: NoOvernightEvidenceStage
    session_date: date
    account_scope_id: str
    policy_family_id: str
    policy_version: str
    policy_digest: str
    calendar_schema_version: str
    calendar_digest: str
    timezone: str
    reviewed_open: datetime
    reviewed_close: datetime
    observed_from: datetime
    observed_through: datetime
    finalized_at: datetime
    code_identity: str
    expected_provider_identity: str
    local_paper_session_id: str
    window_open_journal_sequence: int
    window_open_record_fingerprint: str
    window_close_journal_sequence: int
    window_close_record_fingerprint: str
    expected_deployment_manifest_digest: str | None = None
    expected_guard_identity: str | None = None

    def __post_init__(self) -> None:
        spec = self.window_spec
        zone = ZoneInfo(spec.timezone)
        for field_name in (
            "observed_from",
            "observed_through",
            "finalized_at",
        ):
            value = getattr(self, field_name)
            _aware(value, field_name)
            if value.astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
                raise ValueError(f"{field_name} timezone differs from campaign timezone")
        if self.observed_from > self.observed_through:
            raise ValueError("observation window is invalid")
        if self.finalized_at < self.observed_through:
            raise ValueError("finalized_at predates observation coverage")
        if (
            self.observed_from.date() != self.session_date
            or self.observed_through.date() != self.session_date
        ):
            raise ValueError("observation dates differ from session_date")
        _integer(
            self.window_open_journal_sequence,
            "window_open_journal_sequence",
        )
        _integer(
            self.window_close_journal_sequence,
            "window_close_journal_sequence",
        )
        if (
            self.window_open_journal_sequence <= 0
            or self.window_close_journal_sequence
            <= self.window_open_journal_sequence
        ):
            raise ValueError("evidence window Journal order is invalid")
        _sha256(
            self.window_open_record_fingerprint,
            "window_open_record_fingerprint",
        )
        _sha256(
            self.window_close_record_fingerprint,
            "window_close_record_fingerprint",
        )

    @property
    def window_spec(self) -> NoOvernightEvidenceWindowSpec:
        return NoOvernightEvidenceWindowSpec(
            campaign_id=self.campaign_id,
            stage=self.stage,
            session_date=self.session_date,
            account_scope_id=self.account_scope_id,
            policy_family_id=self.policy_family_id,
            policy_version=self.policy_version,
            policy_digest=self.policy_digest,
            calendar_schema_version=self.calendar_schema_version,
            calendar_digest=self.calendar_digest,
            timezone=self.timezone,
            reviewed_open=self.reviewed_open,
            reviewed_close=self.reviewed_close,
            code_identity=self.code_identity,
            expected_provider_identity=self.expected_provider_identity,
            local_paper_session_id=self.local_paper_session_id,
            expected_deployment_manifest_digest=(
                self.expected_deployment_manifest_digest
            ),
            expected_guard_identity=self.expected_guard_identity,
        )

    def payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "stage": self.stage.value,
            "session_date": self.session_date.isoformat(),
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "calendar_schema_version": self.calendar_schema_version,
            "calendar_digest": self.calendar_digest,
            "timezone": self.timezone,
            "reviewed_open": self.reviewed_open.isoformat(),
            "reviewed_close": self.reviewed_close.isoformat(),
            "observed_from": self.observed_from.isoformat(),
            "observed_through": self.observed_through.isoformat(),
            "finalized_at": self.finalized_at.isoformat(),
            "code_identity": self.code_identity,
            "expected_provider_identity": self.expected_provider_identity,
            "local_paper_session_id": self.local_paper_session_id,
            "window_open_journal_sequence": self.window_open_journal_sequence,
            "window_open_record_fingerprint": (
                self.window_open_record_fingerprint
            ),
            "window_close_journal_sequence": self.window_close_journal_sequence,
            "window_close_record_fingerprint": (
                self.window_close_record_fingerprint
            ),
            "expected_deployment_manifest_digest": (
                self.expected_deployment_manifest_digest
            ),
            "expected_guard_identity": self.expected_guard_identity,
        }


@dataclass(frozen=True)
class NoOvernightEvidenceMetrics:
    local_paper_fill_count: int
    managed_entry_opportunity_count: int
    partial_fill_order_count: int
    cancel_intent_count: int
    cancel_result_count: int
    cancel_latency_sample_count: int
    max_cancel_latency_microseconds: int
    no_overnight_exit_attempt_count: int
    no_overnight_exit_retry_count: int
    no_overnight_exit_fill_count: int
    exit_fill_latency_sample_count: int
    max_exit_fill_latency_microseconds: int
    exit_retry_latency_sample_count: int
    max_exit_retry_latency_microseconds: int
    executable_book_ready_count: int
    executable_book_unavailable_count: int
    synthetic_fill_count: int
    duplicate_exit_side_effect_count: int
    wrong_horizon_liquidation_count: int

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            _integer(getattr(self, field_name), field_name)
        sample_pairs = (
            (
                self.cancel_latency_sample_count,
                self.max_cancel_latency_microseconds,
                self.cancel_result_count,
                "cancel latency",
            ),
            (
                self.exit_fill_latency_sample_count,
                self.max_exit_fill_latency_microseconds,
                self.no_overnight_exit_fill_count,
                "exit fill latency",
            ),
            (
                self.exit_retry_latency_sample_count,
                self.max_exit_retry_latency_microseconds,
                self.no_overnight_exit_retry_count,
                "exit retry latency",
            ),
        )
        for sample_count, maximum, available_count, label in sample_pairs:
            if sample_count > available_count:
                raise ValueError(f"{label} samples exceed available evidence")
            if (sample_count == 0) != (maximum == 0):
                raise ValueError(f"{label} maximum conflicts with sample count")

    def payload(self) -> dict[str, int]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }


def _parameter_metric_reason_codes(
    metrics: NoOvernightEvidenceMetrics,
    *,
    false_positive_review_complete: bool,
) -> set[str]:
    required_samples = {
        "ENTRY_OPPORTUNITY_SAMPLE_MISSING": (
            metrics.managed_entry_opportunity_count
        ),
        "CANCEL_LATENCY_SAMPLE_MISSING": metrics.cancel_latency_sample_count,
        "PARTIAL_FILL_SAMPLE_MISSING": metrics.partial_fill_order_count,
        "EXIT_FILL_LATENCY_SAMPLE_MISSING": (
            metrics.exit_fill_latency_sample_count
        ),
        "EXIT_RETRY_LATENCY_SAMPLE_MISSING": (
            metrics.exit_retry_latency_sample_count
        ),
        "EXECUTABLE_BOOK_SAMPLE_MISSING": (
            metrics.executable_book_ready_count
            + metrics.executable_book_unavailable_count
        ),
    }
    reasons = {
        reason
        for reason, sample_count in required_samples.items()
        if sample_count == 0
    }
    if (
        metrics.synthetic_fill_count
        or metrics.duplicate_exit_side_effect_count
        or metrics.wrong_horizon_liquidation_count
    ):
        reasons.add("ZERO_SAFETY_METRIC_VIOLATED")
    if not false_positive_review_complete:
        reasons.add("FALSE_POSITIVE_REVIEW_MISSING")
    return reasons


@dataclass(frozen=True)
class NoOvernightDrillEvidence:
    campaign_id: str
    kind: NoOvernightDrillKind
    status: NoOvernightDrillStatus
    observed_at: datetime
    evidence_digest: str
    account_scope_id: str
    policy_family_id: str
    policy_digest: str
    deployment_manifest_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "account_scope_id",
            "policy_family_id",
        ):
            _text(getattr(self, field_name), field_name)
        if not isinstance(self.kind, NoOvernightDrillKind):
            raise ValueError("drill kind is unsupported")
        if not isinstance(self.status, NoOvernightDrillStatus):
            raise ValueError("drill status is unsupported")
        _aware(self.observed_at, "observed_at")
        _sha256(self.evidence_digest, "evidence_digest")
        _sha256(self.policy_digest, "policy_digest")
        _sha256(
            self.deployment_manifest_digest,
            "deployment_manifest_digest",
        )

    def _payload_without_digest(self) -> dict[str, object]:
        return {
            "schema_version": "no_overnight_drill_evidence_v1",
            "campaign_id": self.campaign_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "observed_at": self.observed_at.isoformat(),
            "evidence_digest": self.evidence_digest,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "policy_digest": self.policy_digest,
            "deployment_manifest_digest": self.deployment_manifest_digest,
            "activation_authority": "NONE_EVIDENCE_ONLY",
        }

    @property
    def drill_digest(self) -> str:
        return _digest(self._payload_without_digest())

    def payload(self) -> dict[str, object]:
        return {
            **self._payload_without_digest(),
            "drill_digest": self.drill_digest,
        }


@dataclass(frozen=True)
class NoOvernightSessionReport:
    observation: NoOvernightEvidenceObservation
    status: NoOvernightEvidenceStatus
    qualification: NoOvernightQualificationStatus
    reason_codes: tuple[str, ...]
    no_overnight_session_id: str | None
    no_overnight_last_sequence: int | None
    no_overnight_projection_digest: str | None
    no_overnight_checkpoint_sequence: int | None
    no_overnight_checkpoint_digest: str | None
    local_paper_session_id: str
    local_paper_last_sequence: int
    local_paper_projection_digest: str
    local_paper_checkpoint_sequence: int
    local_paper_checkpoint_digest: str
    terminal_state: str | None
    result_status: str | None
    flat_proof_mode: str | None
    reconciliation_status: str | None
    reconciliation_digest: str | None
    breach_id: str | None
    breach_revision: int
    transition_count: int
    metrics: NoOvernightEvidenceMetrics
    postgres_destructive_uat: str = POSTGRES_DESTRUCTIVE_UAT_WAIVER
    schema_version: str = NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA:
            raise ValueError("session evidence schema is unsupported")
        if not isinstance(self.status, NoOvernightEvidenceStatus):
            raise ValueError("evidence status is unsupported")
        if not isinstance(self.qualification, NoOvernightQualificationStatus):
            raise ValueError("qualification status is unsupported")
        normalized_reasons = tuple(sorted(set(self.reason_codes)))
        if normalized_reasons != self.reason_codes or any(
            type(code) is not str
            or not code
            or code != code.strip().upper()
            for code in normalized_reasons
        ):
            raise ValueError("reason_codes must be sorted unique stable codes")
        if self.postgres_destructive_uat != POSTGRES_DESTRUCTIVE_UAT_WAIVER:
            raise ValueError("PostgreSQL destructive UAT waiver cannot be promoted")
        _text(self.local_paper_session_id, "local_paper_session_id")
        _sha256(self.local_paper_projection_digest, "local_paper_projection_digest")
        _sha256(self.local_paper_checkpoint_digest, "local_paper_checkpoint_digest")
        _integer(self.local_paper_last_sequence, "local_paper_last_sequence")
        _integer(
            self.local_paper_checkpoint_sequence,
            "local_paper_checkpoint_sequence",
        )
        _integer(self.breach_revision, "breach_revision")
        _integer(self.transition_count, "transition_count")
        if self.no_overnight_session_id is None:
            if any(
                value is not None
                for value in (
                    self.no_overnight_last_sequence,
                    self.no_overnight_projection_digest,
                    self.no_overnight_checkpoint_sequence,
                    self.no_overnight_checkpoint_digest,
                    self.terminal_state,
                    self.result_status,
                    self.flat_proof_mode,
                    self.reconciliation_status,
                    self.reconciliation_digest,
                    self.breach_id,
                )
            ) or self.breach_revision != 0 or self.transition_count != 0:
                raise ValueError("missing no-overnight session has projected evidence")
        else:
            _text(self.no_overnight_session_id, "no_overnight_session_id")
            _integer(self.no_overnight_last_sequence, "no_overnight_last_sequence")
            _sha256(
                self.no_overnight_projection_digest,
                "no_overnight_projection_digest",
            )
            _integer(
                self.no_overnight_checkpoint_sequence,
                "no_overnight_checkpoint_sequence",
            )
            _sha256(
                self.no_overnight_checkpoint_digest,
                "no_overnight_checkpoint_digest",
            )
        if (
            self.observation.stage is NoOvernightEvidenceStage.DISABLED_BASELINE
            and self.qualification
            is not NoOvernightQualificationStatus.NOT_APPLICABLE
        ):
            raise ValueError("DISABLED baseline cannot qualify rollout")

    def _payload_without_digest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation": self.observation.payload(),
            "status": self.status.value,
            "qualification": self.qualification.value,
            "reason_codes": list(self.reason_codes),
            "no_overnight_session_id": self.no_overnight_session_id,
            "no_overnight_last_sequence": self.no_overnight_last_sequence,
            "no_overnight_projection_digest": self.no_overnight_projection_digest,
            "no_overnight_checkpoint_sequence": (
                self.no_overnight_checkpoint_sequence
            ),
            "no_overnight_checkpoint_digest": self.no_overnight_checkpoint_digest,
            "local_paper_session_id": self.local_paper_session_id,
            "local_paper_last_sequence": self.local_paper_last_sequence,
            "local_paper_projection_digest": self.local_paper_projection_digest,
            "local_paper_checkpoint_sequence": self.local_paper_checkpoint_sequence,
            "local_paper_checkpoint_digest": self.local_paper_checkpoint_digest,
            "terminal_state": self.terminal_state,
            "result_status": self.result_status,
            "flat_proof_mode": self.flat_proof_mode,
            "reconciliation_status": self.reconciliation_status,
            "reconciliation_digest": self.reconciliation_digest,
            "breach_id": self.breach_id,
            "breach_revision": self.breach_revision,
            "transition_count": self.transition_count,
            "metrics": self.metrics.payload(),
            "postgres_destructive_uat": self.postgres_destructive_uat,
            "activation_authority": "NONE_EVIDENCE_ONLY",
        }

    @property
    def report_digest(self) -> str:
        return _digest(self._payload_without_digest())

    def payload(self) -> dict[str, object]:
        return {
            **self._payload_without_digest(),
            "report_digest": self.report_digest,
        }


@dataclass(frozen=True)
class NoOvernightParameterReview:
    campaign_id: str
    account_scope_id: str
    policy_family_id: str
    frozen_policy_version: str
    frozen_policy_digest: str
    frozen_deployment_manifest_digest: str
    code_identity: str
    reviewed_at: datetime
    reviewed_by: str
    review_note_digest: str
    false_positive_review_complete: bool
    status: NoOvernightParameterReviewStatus
    reason_codes: tuple[str, ...]
    session_report_digests: tuple[str, ...]
    metrics: NoOvernightEvidenceMetrics
    review_phase: NoOvernightParameterReviewPhase = (
        NoOvernightParameterReviewPhase.POST_UAT_VALIDATION
    )

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "account_scope_id",
            "policy_family_id",
            "frozen_policy_version",
            "code_identity",
            "reviewed_by",
        ):
            _text(getattr(self, field_name), field_name)
        _sha256(self.frozen_policy_digest, "frozen_policy_digest")
        _sha256(
            self.frozen_deployment_manifest_digest,
            "frozen_deployment_manifest_digest",
        )
        _sha256(self.review_note_digest, "review_note_digest")
        _aware(self.reviewed_at, "reviewed_at")
        if type(self.false_positive_review_complete) is not bool:
            raise ValueError("false_positive_review_complete must be boolean")
        if not isinstance(self.status, NoOvernightParameterReviewStatus):
            raise ValueError("parameter review status is unsupported")
        if not isinstance(self.review_phase, NoOvernightParameterReviewPhase):
            raise ValueError("parameter review phase is unsupported")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("parameter review reasons must be sorted and unique")
        if any(
            type(code) is not str
            or not code
            or code != code.strip().upper()
            for code in self.reason_codes
        ):
            raise ValueError("parameter review reason code is invalid")
        if not self.session_report_digests or tuple(
            sorted(set(self.session_report_digests))
        ) != self.session_report_digests:
            raise ValueError(
                "parameter review report digests must be sorted and unique"
            )
        for digest in self.session_report_digests:
            _sha256(digest, "session_report_digest")
        if (
            self.status is NoOvernightParameterReviewStatus.FROZEN
            and (self.reason_codes or not self.false_positive_review_complete)
        ):
            raise ValueError("frozen parameter review must have complete evidence")
        if (
            self.status is NoOvernightParameterReviewStatus.FROZEN
            and self.review_phase
            is NoOvernightParameterReviewPhase.PRE_ENFORCEMENT_APPROVAL
            and len(self.session_report_digests) < 2
        ):
            raise ValueError(
                "frozen parameter review requires prerequisite stage reports"
            )
        if (
            self.status is NoOvernightParameterReviewStatus.FROZEN
            and self.review_phase
            is NoOvernightParameterReviewPhase.POST_UAT_VALIDATION
            and len(self.session_report_digests) < len(NoOvernightEvidenceStage)
        ):
            raise ValueError(
                "post-UAT parameter review requires all campaign stages"
            )

    def _payload_without_digest(self) -> dict[str, object]:
        return {
            "schema_version": "no_overnight_parameter_review_v2",
            "campaign_id": self.campaign_id,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "frozen_policy_version": self.frozen_policy_version,
            "frozen_policy_digest": self.frozen_policy_digest,
            "frozen_deployment_manifest_digest": (
                self.frozen_deployment_manifest_digest
            ),
            "code_identity": self.code_identity,
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewed_by": self.reviewed_by,
            "review_note_digest": self.review_note_digest,
            "false_positive_review_complete": (
                self.false_positive_review_complete
            ),
            "status": self.status.value,
            "review_phase": self.review_phase.value,
            "reason_codes": list(self.reason_codes),
            "session_report_digests": list(self.session_report_digests),
            "metrics": self.metrics.payload(),
            "activation_authority": "NONE_EVIDENCE_ONLY",
        }

    @property
    def review_digest(self) -> str:
        return _digest(self._payload_without_digest())

    def payload(self) -> dict[str, object]:
        return {
            **self._payload_without_digest(),
            "review_digest": self.review_digest,
        }


@dataclass(frozen=True)
class NoOvernightCampaignReport:
    campaign_id: str
    account_scope_id: str
    policy_family_id: str
    frozen_policy_version: str
    frozen_policy_digest: str
    frozen_deployment_manifest_digest: str
    code_identity: str
    finalized_at: datetime
    status: NoOvernightCampaignStatus
    reason_codes: tuple[str, ...]
    session_report_digests: tuple[str, ...]
    drill_evidence_digests: tuple[str, ...]
    parameter_review_digest: str | None
    stage_report_digests: tuple[tuple[str, tuple[str, ...]], ...] = ()
    drill_kind_digests: tuple[tuple[str, str], ...] = ()
    independent_review_required: bool = True
    unattended_local_paper_allowed: bool = False
    broker_live_ready: bool = False
    postgres_destructive_uat: str = POSTGRES_DESTRUCTIVE_UAT_WAIVER

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "account_scope_id",
            "policy_family_id",
            "frozen_policy_version",
            "code_identity",
        ):
            _text(getattr(self, field_name), field_name)
        _sha256(self.frozen_policy_digest, "frozen_policy_digest")
        _sha256(
            self.frozen_deployment_manifest_digest,
            "frozen_deployment_manifest_digest",
        )
        _aware(self.finalized_at, "finalized_at")
        if not isinstance(self.status, NoOvernightCampaignStatus):
            raise ValueError("campaign status is unsupported")
        normalized_reasons = tuple(sorted(set(self.reason_codes)))
        if normalized_reasons != self.reason_codes:
            raise ValueError("campaign reasons must be sorted and unique")
        if any(
            type(code) is not str
            or not code
            or code != code.strip().upper()
            for code in self.reason_codes
        ):
            raise ValueError("campaign reason code is invalid")
        if not self.session_report_digests:
            raise ValueError("campaign requires session report digests")
        for digest in self.session_report_digests:
            _sha256(digest, "session_report_digest")
        for digest in self.drill_evidence_digests:
            _sha256(digest, "drill_evidence_digest")
        _optional_sha256(self.parameter_review_digest, "parameter_review_digest")
        if tuple(sorted(set(self.session_report_digests))) != (
            self.session_report_digests
        ):
            raise ValueError("session report digests must be sorted and unique")
        if tuple(sorted(set(self.drill_evidence_digests))) != (
            self.drill_evidence_digests
        ):
            raise ValueError("drill evidence digests must be sorted and unique")
        stage_keys: list[str] = []
        mapped_session_digests: list[str] = []
        for entry in self.stage_report_digests:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("campaign stage digest entry is invalid")
            stage, digests = entry
            if type(stage) is not str or stage not in {
                item.value for item in NoOvernightEvidenceStage
            }:
                raise ValueError("campaign stage digest key is invalid")
            if type(digests) is not tuple or tuple(sorted(set(digests))) != digests:
                raise ValueError("campaign stage digests must be sorted and unique")
            for digest in digests:
                _sha256(digest, "stage_report_digest")
            stage_keys.append(stage)
            mapped_session_digests.extend(digests)
        if stage_keys != sorted(set(stage_keys)):
            raise ValueError("campaign stage digest keys must be sorted and unique")
        if self.stage_report_digests and tuple(
            sorted(mapped_session_digests)
        ) != self.session_report_digests:
            raise ValueError("campaign stage mapping conflicts with report digests")
        drill_keys: list[str] = []
        mapped_drill_digests: list[str] = []
        for entry in self.drill_kind_digests:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("campaign drill digest entry is invalid")
            kind, digest = entry
            if type(kind) is not str or kind not in {
                item.value for item in NoOvernightDrillKind
            }:
                raise ValueError("campaign drill digest key is invalid")
            _sha256(digest, "drill_kind_digest")
            drill_keys.append(kind)
            mapped_drill_digests.append(digest)
        if drill_keys != sorted(set(drill_keys)):
            raise ValueError("campaign drill digest keys must be sorted and unique")
        if self.drill_kind_digests and tuple(
            sorted(mapped_drill_digests)
        ) != self.drill_evidence_digests:
            raise ValueError("campaign drill mapping conflicts with drill digests")
        if self.independent_review_required is not True:
            raise ValueError("campaign cannot bypass independent review")
        if self.unattended_local_paper_allowed is not False:
            raise ValueError("campaign report cannot enable unattended Local Paper")
        if self.broker_live_ready is not False:
            raise ValueError("campaign report cannot claim broker/live readiness")
        if self.postgres_destructive_uat != POSTGRES_DESTRUCTIVE_UAT_WAIVER:
            raise ValueError("PostgreSQL destructive UAT waiver cannot be promoted")
        if (
            self.status is NoOvernightCampaignStatus.READY_FOR_INDEPENDENT_REVIEW
            and self.parameter_review_digest is None
        ):
            raise ValueError("review-ready campaign requires parameter review")

    def _payload_without_digest(self) -> dict[str, object]:
        return {
            "schema_version": "no_overnight_campaign_report_v2",
            "campaign_id": self.campaign_id,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "frozen_policy_version": self.frozen_policy_version,
            "frozen_policy_digest": self.frozen_policy_digest,
            "frozen_deployment_manifest_digest": (
                self.frozen_deployment_manifest_digest
            ),
            "code_identity": self.code_identity,
            "finalized_at": self.finalized_at.isoformat(),
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "session_report_digests": list(self.session_report_digests),
            "drill_evidence_digests": list(self.drill_evidence_digests),
            "parameter_review_digest": self.parameter_review_digest,
            "stage_report_digests": {
                stage: list(digests)
                for stage, digests in self.stage_report_digests
            },
            "drill_kind_digests": dict(self.drill_kind_digests),
            "independent_review_required": self.independent_review_required,
            "unattended_local_paper_allowed": self.unattended_local_paper_allowed,
            "broker_live_ready": self.broker_live_ready,
            "postgres_destructive_uat": self.postgres_destructive_uat,
            "activation_authority": "NONE_EVIDENCE_ONLY",
        }
    @property
    def report_digest(self) -> str:
        return _digest(self._payload_without_digest())

    def payload(self) -> dict[str, object]:
        return {
            **self._payload_without_digest(),
            "report_digest": self.report_digest,
        }


def _evidence_window_session_id(
    spec: NoOvernightEvidenceWindowSpec,
) -> str:
    return (
        f"no-overnight-evidence-v1:{spec.campaign_id}:"
        f"{spec.stage.value}:{spec.session_date.isoformat()}"
    )


def open_no_overnight_evidence_window(
    *,
    journal: JournalRepository,
    spec: NoOvernightEvidenceWindowSpec,
    opened_at: datetime,
    latest_allowed_at: datetime | None = None,
    authoritative_now: Callable[[], datetime] | None = None,
) -> JournalAppendResult:
    """Append the pre-open marker used to prove campaign coverage."""

    _aware(opened_at, "opened_at")
    zone = ZoneInfo(spec.timezone)
    if opened_at.astimezone(zone).replace(tzinfo=None) != opened_at.replace(
        tzinfo=None
    ):
        raise ValueError("opened_at timezone differs from campaign timezone")
    if opened_at.date() != spec.session_date or opened_at > spec.reviewed_close:
        raise ValueError("evidence window must open within the reviewed session date")
    session_id = _evidence_window_session_id(spec)
    session = JournalSession(
        session_id=session_id,
        started_at=opened_at,
        mode="NO_OVERNIGHT_EVIDENCE_WINDOW",
        metadata={
            "window_spec": spec.payload(),
            "activation_authority": "NONE_EVIDENCE_ONLY",
        },
    )
    identity = f"{spec.campaign_id}:{spec.stage.value}:{spec.session_date.isoformat()}"
    record = JournalRecord(
        record_id=f"no-overnight-evidence-window-open:{identity}",
        session_id=session_id,
        kind=NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND,
        occurred_at=opened_at,
        payload=spec.payload(),
        idempotency_scope=f"{session_id}:no-overnight-evidence-window-open",
        idempotency_key=identity,
    )
    return journal.start_session_and_append_before(
        session,
        record,
        latest_allowed_at=latest_allowed_at or spec.reviewed_close,
        authoritative_now=authoritative_now,
    )


def close_no_overnight_evidence_window(
    *,
    journal: JournalRepository,
    spec: NoOvernightEvidenceWindowSpec,
    opened: JournalAppendResult,
    closed_at: datetime,
) -> NoOvernightEvidenceObservation:
    """Append the post-close marker and return its strictly bound observation."""

    _aware(closed_at, "closed_at")
    zone = ZoneInfo(spec.timezone)
    if closed_at.astimezone(zone).replace(tzinfo=None) != closed_at.replace(
        tzinfo=None
    ):
        raise ValueError("closed_at timezone differs from campaign timezone")
    if closed_at.date() != spec.session_date or closed_at < spec.reviewed_close:
        raise ValueError("evidence window must close no earlier than reviewed close")
    if (
        opened.record.kind != NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND
        or dict(opened.record.payload) != spec.payload()
    ):
        raise ValueError("evidence window open marker conflicts with spec")
    session_id = _evidence_window_session_id(spec)
    stored_open = next(
        (
            result
            for result in journal.records(session_id)
            if result.sequence == opened.sequence
        ),
        None,
    )
    if stored_open != opened:
        raise ValueError("evidence window open marker is not in the Journal")
    identity = f"{spec.campaign_id}:{spec.stage.value}:{spec.session_date.isoformat()}"
    close_payload = {
        **spec.payload(),
        "open_record_id": opened.record.record_id,
        "open_journal_sequence": opened.sequence,
        "open_record_fingerprint": opened.record.fingerprint,
    }
    closed = journal.append(
        JournalRecord(
            record_id=f"no-overnight-evidence-window-close:{identity}",
            session_id=session_id,
            kind=NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND,
            occurred_at=closed_at,
            payload=close_payload,
            idempotency_scope=(
                f"{session_id}:no-overnight-evidence-window-close"
            ),
            idempotency_key=identity,
        )
    )
    if closed.sequence <= opened.sequence:
        raise ValueError("evidence window close marker precedes open marker")
    return NoOvernightEvidenceObservation(
        **{
            "campaign_id": spec.campaign_id,
            "stage": spec.stage,
            "session_date": spec.session_date,
            "account_scope_id": spec.account_scope_id,
            "policy_family_id": spec.policy_family_id,
            "policy_version": spec.policy_version,
            "policy_digest": spec.policy_digest,
            "calendar_schema_version": spec.calendar_schema_version,
            "calendar_digest": spec.calendar_digest,
            "timezone": spec.timezone,
            "reviewed_open": spec.reviewed_open,
            "reviewed_close": spec.reviewed_close,
            "observed_from": opened.record.occurred_at,
            "observed_through": closed.record.occurred_at,
            "finalized_at": closed.record.occurred_at,
            "code_identity": spec.code_identity,
            "expected_provider_identity": spec.expected_provider_identity,
            "local_paper_session_id": spec.local_paper_session_id,
            "window_open_journal_sequence": opened.sequence,
            "window_open_record_fingerprint": opened.record.fingerprint,
            "window_close_journal_sequence": closed.sequence,
            "window_close_record_fingerprint": closed.record.fingerprint,
            "expected_deployment_manifest_digest": (
                spec.expected_deployment_manifest_digest
            ),
            "expected_guard_identity": spec.expected_guard_identity,
        }
    )


def _validate_evidence_window(
    journal: JournalRepository,
    observation: NoOvernightEvidenceObservation,
) -> None:
    window_session_id = _evidence_window_session_id(observation.window_spec)
    window_session = journal.session(window_session_id)
    expected_metadata = {
        "window_spec": observation.window_spec.payload(),
        "activation_authority": "NONE_EVIDENCE_ONLY",
    }
    if (
        window_session is None
        or window_session.mode != "NO_OVERNIGHT_EVIDENCE_WINDOW"
        or dict(window_session.metadata) != expected_metadata
        or window_session.started_at != observation.observed_from
    ):
        raise ValueError("evidence window session metadata mismatch")
    records = {
        result.sequence: result
        for result in journal.records(window_session_id)
    }
    opened = records.get(observation.window_open_journal_sequence)
    closed = records.get(observation.window_close_journal_sequence)
    if opened is None or closed is None:
        raise ValueError("evidence window marker is missing")
    spec_payload = observation.window_spec.payload()
    if (
        opened.record.kind != NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND
        or dict(opened.record.payload) != spec_payload
        or opened.record.occurred_at != observation.observed_from
        or opened.record.fingerprint
        != observation.window_open_record_fingerprint
    ):
        raise ValueError("evidence window open marker mismatch")
    expected_close_payload = {
        **spec_payload,
        "open_record_id": opened.record.record_id,
        "open_journal_sequence": opened.sequence,
        "open_record_fingerprint": opened.record.fingerprint,
    }
    if (
        closed.record.kind != NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND
        or dict(closed.record.payload) != expected_close_payload
        or closed.record.occurred_at != observation.observed_through
        or closed.record.occurred_at != observation.finalized_at
        or closed.record.fingerprint
        != observation.window_close_record_fingerprint
        or closed.sequence <= opened.sequence
    ):
        raise ValueError("evidence window close marker mismatch")
    matching_kinds = {
        NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND,
        NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND,
    }
    matching = [
        result
        for result in records.values()
        if result.record.kind in matching_kinds
        and result.record.payload.get("campaign_id") == observation.campaign_id
        and result.record.payload.get("stage") == observation.stage.value
        and result.record.payload.get("session_date")
        == observation.session_date.isoformat()
    ]
    if len(matching) != 2:
        raise ValueError("evidence window marker count is invalid")

    zone = ZoneInfo(observation.timezone)
    covered_records = tuple(
        result
        for result in journal.records(observation.local_paper_session_id)
        if result.record.occurred_at.astimezone(zone).date()
        == observation.session_date
    )
    no_overnight_session_id = (
        f"{_NO_OVERNIGHT_SESSION_ID_PREFIX}{observation.session_date.isoformat()}"
    )
    covered_records += journal.records(no_overnight_session_id)
    if any(
        not opened.sequence < result.sequence < closed.sequence
        for result in covered_records
    ):
        raise ValueError("evidence facts fall outside durable window append order")


def _local_paper_evidence(
    journal: JournalRepository,
    observation: NoOvernightEvidenceObservation,
) -> tuple[
    int,
    str,
    int,
    str,
    NoOvernightEvidenceMetrics,
    tuple[str, ...],
    tuple[str, ...],
]:
    session = journal.session(observation.local_paper_session_id)
    if session is None:
        raise ValueError("local-paper v2 evidence session is missing")
    if session.metadata.get("account_scope_id") != observation.account_scope_id or (
        session.metadata.get("policy_family_id") != observation.policy_family_id
    ):
        raise ValueError("local-paper v2 evidence identity mismatch")
    try:
        starting_cash = Decimal(str(session.metadata["starting_cash"]))
    except (InvalidOperation, KeyError, ValueError) as error:
        raise ValueError("local-paper starting cash is invalid") from error
    if not starting_cash.is_finite() or starting_cash <= 0:
        raise ValueError("local-paper starting cash is invalid")
    settings_digest = session.metadata.get("settings_digest")
    if type(settings_digest) is not str:
        raise ValueError("local-paper settings digest is invalid")
    projection = rebuild_local_paper_v2_projection(
        journal,
        session_id=observation.local_paper_session_id,
        starting_cash=starting_cash,
        account_scope_id=observation.account_scope_id,
        policy_family_id=observation.policy_family_id,
        settings_digest=settings_digest,
        require_checkpoint=True,
    )
    checkpoint = journal.latest_checkpoint(
        observation.local_paper_session_id,
        LOCAL_PAPER_V2_PROJECTION_NAME,
    )
    if checkpoint is None or checkpoint.journal_sequence != projection.last_sequence:
        raise ValueError("local-paper evidence requires a current checkpoint")

    zone = ZoneInfo(observation.timezone)
    records = journal.records(observation.local_paper_session_id)
    commands = []
    for appended in records:
        if appended.record.kind != "order_command.v2":
            continue
        command = order_command_from_record(appended.record)
        if command.requested_at.astimezone(zone).date() == observation.session_date:
            commands.append(command)
    no_overnight_commands = tuple(
        command
        for command in commands
        if command.execution_reason_code == "NO_OVERNIGHT_EXIT"
    )
    wrong_horizon = sum(
        command.side is not CommandSide.SELL
        or command.position_action is not PositionAction.CLOSE_LONG
        or command.execution_reason_category
        is not ExecutionReasonCategory.OPERATIONAL_RISK
        or command.exposure is None
        or not command.exposure.no_overnight_managed
        or command.exposure.account_scope_id != observation.account_scope_id
        or command.exposure.policy_family_id != observation.policy_family_id
        or command.target_exposure_id != command.exposure.exposure_id
        for command in no_overnight_commands
    )
    command_ids = {command.command_id for command in no_overnight_commands}
    incomplete_reasons: set[str] = set()
    safety_reasons: set[str] = set()
    fill_count = 0
    no_overnight_fill_count = 0
    synthetic_fill_count = 0
    exit_fill_latencies: list[int] = []
    commands_by_id = {command.command_id: command for command in commands}
    for appended in records:
        record = appended.record
        if record.kind != LOCAL_PAPER_FILL_V4_KIND or (
            record.occurred_at.astimezone(zone).date() != observation.session_date
        ):
            continue
        fill_count += 1
        fill = LocalPaperExposureFill.from_record(record)
        provenance_fields = {
            "fill_source",
            "provider_identity",
            "execution_authority",
        }
        if not provenance_fields.issubset(record.payload):
            incomplete_reasons.add("FILL_PROVENANCE_INCOMPLETE")
        elif (
            record.payload["fill_source"] != _EXPECTED_FILL_SOURCE
            or record.payload["provider_identity"]
            != observation.expected_provider_identity
            or record.payload["execution_authority"] is not False
        ):
            synthetic_fill_count += 1
            safety_reasons.add("SYNTHETIC_OR_EXTERNAL_FILL_DETECTED")
        if fill.execution_reason_code != "NO_OVERNIGHT_EXIT":
            continue
        no_overnight_fill_count += 1
        command_id = record.payload.get("command_id")
        if type(command_id) is not str or command_id not in command_ids:
            incomplete_reasons.add("NO_OVERNIGHT_FILL_COMMAND_LINKAGE_MISSING")
        else:
            exit_fill_latencies.append(
                _duration_microseconds(
                    record.occurred_at,
                    commands_by_id[command_id].requested_at,
                    "exit fill latency",
                )
            )
        if (
            fill.side.value != "SELL"
            or fill.position_action is not PositionAction.CLOSE_LONG
            or not fill.exposure.no_overnight_managed
            or fill.target_exposure_id != fill.exposure.exposure_id
        ):
            wrong_horizon += 1

    states = latest_local_paper_order_states(
        journal,
        session_id=observation.local_paper_session_id,
    )
    side_effect_groups: Counter[tuple[str, int]] = Counter()
    for state in states:
        if (
            state.get("execution_reason_code") != "NO_OVERNIGHT_EXIT"
            or state.get("trading_date") != observation.session_date.isoformat()
        ):
            continue
        target = state.get("target_exposure_id")
        attempt = state.get("attempt")
        if type(target) is not str or type(attempt) is not int:
            incomplete_reasons.add("NO_OVERNIGHT_ORDER_IDENTITY_INCOMPLETE")
            continue
        side_effect_groups[(target, attempt)] += 1
        raw_identity = state.get("exposure_identity")
        if not isinstance(raw_identity, Mapping):
            incomplete_reasons.add("NO_OVERNIGHT_ORDER_IDENTITY_INCOMPLETE")
            continue
        exposure = ExposureIdentity.from_payload(raw_identity)
        if not exposure.no_overnight_managed:
            wrong_horizon += 1
    duplicate_side_effects = sum(
        max(0, count - 1) for count in side_effect_groups.values()
    )
    if duplicate_side_effects:
        safety_reasons.add("DUPLICATE_EXIT_SIDE_EFFECT")
    if wrong_horizon:
        safety_reasons.add("WRONG_HORIZON_LIQUIDATION")

    partial_fill_orders = {
        record.record.payload.get("order_id")
        for record in records
        if record.record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND
        and record.record.occurred_at.astimezone(zone).date()
        == observation.session_date
        and record.record.payload.get("status") == "PARTIALLY_FILLED"
    }
    cancel_intents = {
        record.record.payload.get("cancel_idempotency_key"): record.record.occurred_at
        for record in records
        if record.record.kind == LOCAL_PAPER_CANCEL_INTENT_V2_KIND
        and record.record.occurred_at.astimezone(zone).date()
        == observation.session_date
    }
    cancel_latencies: list[int] = []
    for record in records:
        if record.record.kind != LOCAL_PAPER_CANCEL_RESULT_V2_KIND or (
            record.record.occurred_at.astimezone(zone).date()
            != observation.session_date
        ):
            continue
        key = record.record.payload.get("cancel_idempotency_key")
        intent_at = cancel_intents.get(key)
        if intent_at is None:
            incomplete_reasons.add("CANCEL_LATENCY_LINEAGE_MISSING")
            continue
        cancel_latencies.append(
            _duration_microseconds(
                record.record.occurred_at,
                intent_at,
                "cancel latency",
            )
        )

    order_command_keys: dict[str, str] = {}
    for record in records:
        if record.record.kind != LOCAL_PAPER_ORDER_STATE_V2_KIND:
            continue
        order_id = record.record.payload.get("order_id")
        idempotency_key = record.record.payload.get("idempotency_key")
        if type(order_id) is str and type(idempotency_key) is str:
            existing = order_command_keys.setdefault(order_id, idempotency_key)
            if existing != idempotency_key:
                raise ValueError("order state command lineage conflicts")
    commands_by_key = {command.idempotency_key: command for command in commands}
    retry_latencies: list[int] = []
    for command in no_overnight_commands:
        if command.attempt <= 1:
            continue
        predecessor_key = order_command_keys.get(command.predecessor_order_id or "")
        predecessor = commands_by_key.get(predecessor_key or "")
        if predecessor is None:
            incomplete_reasons.add("EXIT_RETRY_LATENCY_LINEAGE_MISSING")
            continue
        retry_latencies.append(
            _duration_microseconds(
                command.requested_at,
                predecessor.requested_at,
                "exit retry latency",
            )
        )

    book_ready_count = 0
    book_unavailable_count = 0
    for record in records:
        if record.record.kind != "no_overnight_final_admission.v1" or (
            record.record.occurred_at.astimezone(zone).date()
            != observation.session_date
        ):
            continue
        raw_decision = record.record.payload.get("decision")
        if not isinstance(raw_decision, Mapping):
            raise ValueError("final admission evidence is invalid")
        decision = ExecutionAdmissionDecision.from_payload(raw_decision)
        if decision.snapshot.executable_book_ready:
            book_ready_count += 1
        else:
            book_unavailable_count += 1

    cancel_result_count = sum(
        record.record.kind == LOCAL_PAPER_CANCEL_RESULT_V2_KIND
        and record.record.occurred_at.astimezone(zone).date()
        == observation.session_date
        for record in records
    )
    if cancel_result_count != len(cancel_latencies):
        incomplete_reasons.add("CANCEL_LATENCY_EVIDENCE_INCOMPLETE")
    if no_overnight_fill_count != len(exit_fill_latencies):
        incomplete_reasons.add("EXIT_FILL_LATENCY_EVIDENCE_INCOMPLETE")
    retry_count = sum(command.attempt > 1 for command in no_overnight_commands)
    if retry_count != len(retry_latencies):
        incomplete_reasons.add("EXIT_RETRY_LATENCY_EVIDENCE_INCOMPLETE")
    metrics = NoOvernightEvidenceMetrics(
        local_paper_fill_count=fill_count,
        managed_entry_opportunity_count=sum(
            command.side is CommandSide.BUY
            and command.exposure is not None
            and command.exposure.no_overnight_managed
            for command in commands
        ),
        partial_fill_order_count=len(partial_fill_orders - {None}),
        cancel_intent_count=sum(
            record.record.kind == LOCAL_PAPER_CANCEL_INTENT_V2_KIND
            and record.record.occurred_at.astimezone(zone).date()
            == observation.session_date
            for record in records
        ),
        cancel_result_count=cancel_result_count,
        cancel_latency_sample_count=len(cancel_latencies),
        max_cancel_latency_microseconds=max(cancel_latencies, default=0),
        no_overnight_exit_attempt_count=len(no_overnight_commands),
        no_overnight_exit_retry_count=retry_count,
        no_overnight_exit_fill_count=no_overnight_fill_count,
        exit_fill_latency_sample_count=len(exit_fill_latencies),
        max_exit_fill_latency_microseconds=max(exit_fill_latencies, default=0),
        exit_retry_latency_sample_count=len(retry_latencies),
        max_exit_retry_latency_microseconds=max(retry_latencies, default=0),
        executable_book_ready_count=book_ready_count,
        executable_book_unavailable_count=book_unavailable_count,
        synthetic_fill_count=synthetic_fill_count,
        duplicate_exit_side_effect_count=duplicate_side_effects,
        wrong_horizon_liquidation_count=wrong_horizon,
    )
    return (
        projection.last_sequence,
        projection.digest,
        checkpoint.journal_sequence,
        checkpoint.digest,
        metrics,
        tuple(sorted(incomplete_reasons)),
        tuple(sorted(safety_reasons)),
    )


def build_no_overnight_session_report(
    *,
    journal: JournalRepository,
    observation: NoOvernightEvidenceObservation,
) -> NoOvernightSessionReport:
    """Build one derived report without adding Journal or execution mutations."""

    _validate_evidence_window(journal, observation)
    (
        local_last_sequence,
        local_digest,
        local_checkpoint_sequence,
        local_checkpoint_digest,
        metrics,
        local_incomplete,
        local_safety,
    ) = _local_paper_evidence(journal, observation)
    incomplete_reasons = set(local_incomplete)
    safety_reasons = set(local_safety)
    if observation.observed_from > observation.reviewed_open:
        incomplete_reasons.add("SESSION_OPEN_NOT_COVERED")
    if observation.observed_through < observation.reviewed_close:
        incomplete_reasons.add("SESSION_CLOSE_NOT_COVERED")

    session_id = f"{_NO_OVERNIGHT_SESSION_ID_PREFIX}{observation.session_date.isoformat()}"
    no_overnight_session = journal.session(session_id)
    projection = None
    no_overnight_checkpoint = None
    transition_count = 0
    if observation.stage is NoOvernightEvidenceStage.DISABLED_BASELINE:
        if no_overnight_session is not None:
            safety_reasons.add("DISABLED_CONTROLLER_SESSION_PRESENT")
        session_id_value = None
    else:
        session_id_value = session_id
        if no_overnight_session is None:
            raise ValueError("no-overnight evidence session is missing")
        expected_mode = (
            "NO_OVERNIGHT_OBSERVE_ONLY"
            if observation.stage is NoOvernightEvidenceStage.OBSERVE_ONLY
            else "NO_OVERNIGHT_ENFORCING"
        )
        expected_metadata = {
            "account_scope_id": observation.account_scope_id,
            "policy_family_id": observation.policy_family_id,
            "session_date": observation.session_date.isoformat(),
            "policy_version": observation.policy_version,
            "policy_digest": observation.policy_digest,
            "calendar_schema_version": observation.calendar_schema_version,
            "calendar_digest": observation.calendar_digest,
            "timezone": observation.timezone,
            "mode": (
                "OBSERVE_ONLY"
                if observation.stage is NoOvernightEvidenceStage.OBSERVE_ONLY
                else "ENFORCING"
            ),
        }
        if no_overnight_session.mode != expected_mode:
            incomplete_reasons.add("CONTROLLER_MODE_DRIFT")
        for field_name, expected in expected_metadata.items():
            if no_overnight_session.metadata.get(field_name) != expected:
                incomplete_reasons.add("SESSION_METADATA_DRIFT")
        if no_overnight_session.started_at > observation.reviewed_open:
            incomplete_reasons.add("CONTROLLER_STARTED_AFTER_OPEN")
        if observation.stage is NoOvernightEvidenceStage.SUPERVISED_ENFORCING:
            if (
                no_overnight_session.metadata.get("deployment_manifest_digest")
                != observation.expected_deployment_manifest_digest
            ):
                incomplete_reasons.add("DEPLOYMENT_MANIFEST_DRIFT")
            if (
                no_overnight_session.metadata.get("guard_identity")
                != observation.expected_guard_identity
            ):
                incomplete_reasons.add("GUARD_IDENTITY_DRIFT")
            local_session = journal.session(observation.local_paper_session_id)
            if local_session is None or (
                local_session.metadata.get("journal_backend") != "POSTGRESQL"
            ):
                incomplete_reasons.add("POSTGRESQL_AUTHORITY_NOT_PROVEN")
        projection = rebuild_no_overnight_projection(
            journal,
            session_id=session_id,
            require_checkpoint=True,
        )
        no_overnight_checkpoint = journal.latest_checkpoint(
            session_id,
            NO_OVERNIGHT_PROJECTION_NAME,
        )
        if no_overnight_checkpoint is None or (
            no_overnight_checkpoint.journal_sequence != projection.last_sequence
        ):
            raise ValueError("no-overnight evidence requires a current checkpoint")
        transition_count = sum(
            appended.record.kind == NO_OVERNIGHT_TRANSITION_KIND
            for appended in journal.records(session_id)
        )
        if projection.state not in {
            NoOvernightState.CONFIRMED_FLAT,
            NoOvernightState.OVERNIGHT_BREACH,
        } or projection.result_status != "CURRENT":
            incomplete_reasons.add("TERMINAL_RESULT_MISSING")
        if (
            projection.last_reconciliation_status
            != ReconciliationStatus.MATCH.value
        ):
            safety_reasons.add("RECONCILIATION_NOT_MATCHED")
        if projection.state is NoOvernightState.OVERNIGHT_BREACH:
            safety_reasons.add("TERMINAL_OVERNIGHT_BREACH")
        if (
            observation.stage is NoOvernightEvidenceStage.OBSERVE_ONLY
            and metrics.no_overnight_exit_attempt_count > 0
        ):
            safety_reasons.add("OBSERVE_ONLY_SIDE_EFFECT")

    status = (
        NoOvernightEvidenceStatus.INCOMPLETE
        if incomplete_reasons
        else NoOvernightEvidenceStatus.COMPLETE
    )
    if observation.stage is NoOvernightEvidenceStage.DISABLED_BASELINE:
        qualification = NoOvernightQualificationStatus.NOT_APPLICABLE
    elif status is NoOvernightEvidenceStatus.COMPLETE and not safety_reasons:
        qualification = NoOvernightQualificationStatus.QUALIFIED
    else:
        qualification = NoOvernightQualificationStatus.NOT_QUALIFIED
    reasons = tuple(sorted(incomplete_reasons | safety_reasons))
    return NoOvernightSessionReport(
        observation=observation,
        status=status,
        qualification=qualification,
        reason_codes=reasons,
        no_overnight_session_id=session_id_value,
        no_overnight_last_sequence=(
            None if projection is None else projection.last_sequence
        ),
        no_overnight_projection_digest=(
            None if projection is None else projection.digest
        ),
        no_overnight_checkpoint_sequence=(
            None
            if no_overnight_checkpoint is None
            else no_overnight_checkpoint.journal_sequence
        ),
        no_overnight_checkpoint_digest=(
            None
            if no_overnight_checkpoint is None
            else no_overnight_checkpoint.digest
        ),
        local_paper_session_id=observation.local_paper_session_id,
        local_paper_last_sequence=local_last_sequence,
        local_paper_projection_digest=local_digest,
        local_paper_checkpoint_sequence=local_checkpoint_sequence,
        local_paper_checkpoint_digest=local_checkpoint_digest,
        terminal_state=None if projection is None else projection.state.value,
        result_status=None if projection is None else projection.result_status,
        flat_proof_mode=None if projection is None else projection.flat_proof_mode,
        reconciliation_status=(
            None if projection is None else projection.last_reconciliation_status
        ),
        reconciliation_digest=(
            None if projection is None else projection.last_reconciliation_digest
        ),
        breach_id=None if projection is None else projection.breach_id,
        breach_revision=0 if projection is None else projection.breach_revision,
        transition_count=transition_count,
        metrics=metrics,
    )


def _aggregate_evidence_metrics(
    reports: tuple[NoOvernightSessionReport, ...],
) -> NoOvernightEvidenceMetrics:
    totals = {
        field_name: sum(
            getattr(report.metrics, field_name) for report in reports
        )
        for field_name in NoOvernightEvidenceMetrics.__dataclass_fields__
    }
    for field_name in (
        "max_cancel_latency_microseconds",
        "max_exit_fill_latency_microseconds",
        "max_exit_retry_latency_microseconds",
    ):
        totals[field_name] = max(
            (getattr(report.metrics, field_name) for report in reports),
            default=0,
        )
    return NoOvernightEvidenceMetrics(**totals)


def build_no_overnight_parameter_review(
    *,
    reports: tuple[NoOvernightSessionReport, ...],
    frozen_policy_version: str,
    frozen_policy_digest: str,
    frozen_deployment_manifest_digest: str,
    reviewed_at: datetime,
    reviewed_by: str,
    review_note_digest: str,
    false_positive_review_complete: bool,
) -> NoOvernightParameterReview:
    """Freeze reviewed timing samples without accepting caller-supplied metrics."""

    if not reports:
        raise ValueError("parameter review requires session reports")
    _text(frozen_policy_version, "frozen_policy_version")
    _sha256(frozen_policy_digest, "frozen_policy_digest")
    _sha256(
        frozen_deployment_manifest_digest,
        "frozen_deployment_manifest_digest",
    )
    _aware(reviewed_at, "reviewed_at")
    _text(reviewed_by, "reviewed_by")
    _sha256(review_note_digest, "review_note_digest")
    if type(false_positive_review_complete) is not bool:
        raise ValueError("false_positive_review_complete must be boolean")

    prerequisite_stages = {
        NoOvernightEvidenceStage.DISABLED_BASELINE,
        NoOvernightEvidenceStage.OBSERVE_ONLY,
    }
    prerequisite_reports = tuple(
        report
        for report in reports
        if report.observation.stage in prerequisite_stages
    )
    enforcing = tuple(
        report
        for report in reports
        if report.observation.stage
        is NoOvernightEvidenceStage.SUPERVISED_ENFORCING
    )
    review_phase = (
        NoOvernightParameterReviewPhase.POST_UAT_VALIDATION
        if enforcing
        else NoOvernightParameterReviewPhase.PRE_ENFORCEMENT_APPROVAL
    )
    review_reports = reports if enforcing else prerequisite_reports
    first = review_reports[0].observation
    reasons: set[str] = set()
    for report in review_reports:
        observation = report.observation
        if (
            observation.campaign_id != first.campaign_id
            or observation.account_scope_id != first.account_scope_id
            or observation.policy_family_id != first.policy_family_id
        ):
            raise ValueError("parameter review report identity mismatch")
        if observation.code_identity != first.code_identity:
            reasons.add("CODE_IDENTITY_DRIFT")
        if report.status is not NoOvernightEvidenceStatus.COMPLETE:
            reasons.add("SESSION_EVIDENCE_INCOMPLETE")
        if reviewed_at <= observation.finalized_at:
            raise ValueError("parameter review predates session report")
    baseline = tuple(
        report
        for report in review_reports
        if report.observation.stage
        is NoOvernightEvidenceStage.DISABLED_BASELINE
    )
    observed = tuple(
        report
        for report in review_reports
        if report.observation.stage is NoOvernightEvidenceStage.OBSERVE_ONLY
    )
    if not baseline:
        reasons.add("DISABLED_BASELINE_MISSING")
    if any(report.reason_codes for report in baseline):
        reasons.add("DISABLED_BASELINE_SAFETY_FINDING")
    if not observed:
        reasons.add("OBSERVE_ONLY_SESSION_MISSING")
    if any(
        report.qualification is not NoOvernightQualificationStatus.QUALIFIED
        for report in observed
    ):
        reasons.add("OBSERVE_ONLY_NOT_QUALIFIED")
    if baseline and observed and max(
        report.observation.session_date for report in baseline
    ) >= min(report.observation.session_date for report in observed):
        reasons.add("PARAMETER_REVIEW_STAGE_ORDER_INVALID")
    if review_phase is NoOvernightParameterReviewPhase.POST_UAT_VALIDATION:
        if any(
            report.qualification
            is not NoOvernightQualificationStatus.QUALIFIED
            for report in enforcing
        ):
            reasons.add("SUPERVISED_ENFORCING_NOT_QUALIFIED")
        if observed and max(
            report.observation.session_date for report in observed
        ) >= min(report.observation.session_date for report in enforcing):
            reasons.add("PARAMETER_REVIEW_STAGE_ORDER_INVALID")
        for report in enforcing:
            observation = report.observation
            if (
                observation.policy_version != frozen_policy_version
                or observation.policy_digest != frozen_policy_digest
            ):
                reasons.add("FROZEN_POLICY_DRIFT")
            if (
                observation.expected_deployment_manifest_digest
                != frozen_deployment_manifest_digest
            ):
                reasons.add("FROZEN_DEPLOYMENT_MANIFEST_DRIFT")

    metrics = _aggregate_evidence_metrics(review_reports)
    reasons.update(
        _parameter_metric_reason_codes(
            metrics,
            false_positive_review_complete=false_positive_review_complete,
        )
    )
    status = (
        NoOvernightParameterReviewStatus.FROZEN
        if not reasons
        else NoOvernightParameterReviewStatus.INSUFFICIENT_EVIDENCE
    )
    return NoOvernightParameterReview(
        campaign_id=first.campaign_id,
        account_scope_id=first.account_scope_id,
        policy_family_id=first.policy_family_id,
        frozen_policy_version=frozen_policy_version,
        frozen_policy_digest=frozen_policy_digest,
        frozen_deployment_manifest_digest=frozen_deployment_manifest_digest,
        code_identity=first.code_identity,
        reviewed_at=reviewed_at,
        reviewed_by=reviewed_by,
        review_note_digest=review_note_digest,
        false_positive_review_complete=false_positive_review_complete,
        status=status,
        reason_codes=tuple(sorted(reasons)),
        session_report_digests=tuple(
            sorted(report.report_digest for report in review_reports)
        ),
        metrics=metrics,
        review_phase=review_phase,
    )


def build_no_overnight_campaign_report(
    *,
    reports: tuple[NoOvernightSessionReport, ...],
    drills: tuple[NoOvernightDrillEvidence, ...],
    parameter_review: NoOvernightParameterReview | None,
    frozen_policy_version: str,
    frozen_policy_digest: str,
    frozen_deployment_manifest_digest: str,
    finalized_at: datetime,
) -> NoOvernightCampaignReport:
    """Aggregate sealed evidence without granting activation authority."""

    if not reports:
        raise ValueError("campaign requires session reports")
    _text(frozen_policy_version, "frozen_policy_version")
    _sha256(frozen_policy_digest, "frozen_policy_digest")
    _sha256(
        frozen_deployment_manifest_digest,
        "frozen_deployment_manifest_digest",
    )
    _aware(finalized_at, "finalized_at")
    campaign_id = reports[0].observation.campaign_id
    account_scope_id = reports[0].observation.account_scope_id
    policy_family_id = reports[0].observation.policy_family_id
    code_identity = reports[0].observation.code_identity
    reasons: set[str] = set()
    for report in reports:
        observation = report.observation
        if observation.campaign_id != campaign_id:
            raise ValueError("campaign report identity mismatch")
        if (
            observation.account_scope_id != account_scope_id
            or observation.policy_family_id != policy_family_id
        ):
            raise ValueError("campaign scope or policy family mismatch")
        if observation.code_identity != code_identity:
            reasons.add("CODE_IDENTITY_DRIFT")
        if report.status is NoOvernightEvidenceStatus.INCOMPLETE:
            reasons.add("SESSION_EVIDENCE_INCOMPLETE")
        if finalized_at < observation.finalized_at:
            raise ValueError("campaign finalized before session report")

    by_stage = {
        stage: tuple(
            report for report in reports if report.observation.stage is stage
        )
        for stage in NoOvernightEvidenceStage
    }
    baseline = by_stage[NoOvernightEvidenceStage.DISABLED_BASELINE]
    observed = by_stage[NoOvernightEvidenceStage.OBSERVE_ONLY]
    enforcing = by_stage[NoOvernightEvidenceStage.SUPERVISED_ENFORCING]
    if not baseline:
        reasons.add("DISABLED_BASELINE_MISSING")
    if not observed:
        reasons.add("OBSERVE_ONLY_SESSION_MISSING")
    if not enforcing:
        reasons.add("SUPERVISED_ENFORCING_SESSION_MISSING")
    if any(
        report.status is not NoOvernightEvidenceStatus.COMPLETE
        for report in baseline
    ):
        reasons.add("DISABLED_BASELINE_INCOMPLETE")
    if any(report.reason_codes for report in baseline):
        reasons.add("DISABLED_BASELINE_SAFETY_FINDING")
    if any(
        report.qualification is not NoOvernightQualificationStatus.QUALIFIED
        for report in observed
    ):
        reasons.add("OBSERVE_ONLY_NOT_QUALIFIED")
    if any(
        report.qualification is not NoOvernightQualificationStatus.QUALIFIED
        for report in enforcing
    ):
        reasons.add("SUPERVISED_ENFORCING_NOT_QUALIFIED")
    if baseline and observed and max(
        report.observation.session_date for report in baseline
    ) >= min(report.observation.session_date for report in observed):
        reasons.add("CAMPAIGN_STAGE_ORDER_INVALID")
    if observed and enforcing and max(
        report.observation.session_date for report in observed
    ) >= min(report.observation.session_date for report in enforcing):
        reasons.add("CAMPAIGN_STAGE_ORDER_INVALID")
    if any(
        report.metrics.synthetic_fill_count
        or report.metrics.duplicate_exit_side_effect_count
        or report.metrics.wrong_horizon_liquidation_count
        for report in reports
    ):
        reasons.add("ZERO_SAFETY_METRIC_VIOLATED")
    for report in enforcing:
        observation = report.observation
        if (
            observation.policy_version != frozen_policy_version
            or observation.policy_digest != frozen_policy_digest
        ):
            reasons.add("FROZEN_POLICY_DRIFT")
        if (
            observation.expected_deployment_manifest_digest
            != frozen_deployment_manifest_digest
        ):
            reasons.add("FROZEN_DEPLOYMENT_MANIFEST_DRIFT")

    report_digests = tuple(sorted(report.report_digest for report in reports))
    parameter_reports = (*baseline, *observed)
    parameter_report_digests = tuple(
        sorted(report.report_digest for report in parameter_reports)
    )
    parameter_metrics = _aggregate_evidence_metrics(parameter_reports)
    if parameter_review is None:
        reasons.add("PARAMETER_REVIEW_MISSING")
    else:
        if (
            parameter_review.campaign_id != campaign_id
            or parameter_review.account_scope_id != account_scope_id
            or parameter_review.policy_family_id != policy_family_id
        ):
            raise ValueError("parameter review identity mismatch")
        if parameter_review.code_identity != code_identity:
            reasons.add("PARAMETER_REVIEW_CODE_IDENTITY_DRIFT")
        if (
            parameter_review.review_phase
            is not NoOvernightParameterReviewPhase.PRE_ENFORCEMENT_APPROVAL
        ):
            reasons.add("PARAMETER_REVIEW_PHASE_INVALID")
        if parameter_review.session_report_digests != parameter_report_digests:
            reasons.add("PARAMETER_REVIEW_REPORT_SET_DRIFT")
        if parameter_review.metrics != parameter_metrics:
            reasons.add("PARAMETER_REVIEW_METRICS_DRIFT")
        if _parameter_metric_reason_codes(
            parameter_metrics,
            false_positive_review_complete=(
                parameter_review.false_positive_review_complete
            ),
        ):
            reasons.add("PARAMETER_REVIEW_REQUIRED_EVIDENCE_MISSING")
        if (
            parameter_review.frozen_policy_version != frozen_policy_version
            or parameter_review.frozen_policy_digest != frozen_policy_digest
        ):
            reasons.add("PARAMETER_REVIEW_POLICY_DRIFT")
        if (
            parameter_review.frozen_deployment_manifest_digest
            != frozen_deployment_manifest_digest
        ):
            reasons.add("PARAMETER_REVIEW_MANIFEST_DRIFT")
        if (
            parameter_review.status
            is not NoOvernightParameterReviewStatus.FROZEN
        ):
            reasons.add("PARAMETER_REVIEW_NOT_FROZEN")
        if finalized_at < parameter_review.reviewed_at:
            raise ValueError("campaign finalized before parameter review")
        if parameter_reports and parameter_review.reviewed_at <= max(
            report.observation.finalized_at for report in parameter_reports
        ):
            reasons.add("PARAMETER_REVIEW_CAUSAL_ORDER_INVALID")
        if enforcing and parameter_review.reviewed_at >= min(
            report.observation.observed_from for report in enforcing
        ):
            reasons.add("PARAMETER_REVIEW_CAUSAL_ORDER_INVALID")

    drills_by_kind: dict[NoOvernightDrillKind, NoOvernightDrillEvidence] = {}
    for drill in drills:
        if drill.kind in drills_by_kind:
            raise ValueError("campaign contains duplicate drill evidence")
        drills_by_kind[drill.kind] = drill
        if (
            drill.campaign_id != campaign_id
            or drill.account_scope_id != account_scope_id
            or drill.policy_family_id != policy_family_id
        ):
            raise ValueError("drill evidence identity mismatch")
        if (
            drill.policy_digest != frozen_policy_digest
            or drill.deployment_manifest_digest
            != frozen_deployment_manifest_digest
        ):
            reasons.add("DRILL_POLICY_OR_MANIFEST_DRIFT")
        if finalized_at < drill.observed_at:
            raise ValueError("campaign finalized before drill evidence")
        if enforcing and drill.observed_at <= max(
            report.observation.finalized_at for report in enforcing
        ):
            reasons.add("DRILL_CAUSAL_ORDER_INVALID")
    missing_reason = {
        NoOvernightDrillKind.RESTART_RECOVERY: "RESTART_RECOVERY_DRILL_MISSING",
        NoOvernightDrillKind.DUPLICATE_PROCESS: "DUPLICATE_PROCESS_DRILL_MISSING",
        NoOvernightDrillKind.BREACH: "BREACH_DRILL_MISSING",
    }
    for kind, reason in missing_reason.items():
        drill = drills_by_kind.get(kind)
        if drill is None:
            reasons.add(reason)
        elif drill.status is not NoOvernightDrillStatus.PASSED:
            reasons.add(reason.replace("_MISSING", "_NOT_PASSED"))

    status = (
        NoOvernightCampaignStatus.READY_FOR_INDEPENDENT_REVIEW
        if not reasons
        else NoOvernightCampaignStatus.INCOMPLETE
    )
    return NoOvernightCampaignReport(
        campaign_id=campaign_id,
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
        frozen_policy_version=frozen_policy_version,
        frozen_policy_digest=frozen_policy_digest,
        frozen_deployment_manifest_digest=frozen_deployment_manifest_digest,
        code_identity=code_identity,
        finalized_at=finalized_at,
        status=status,
        reason_codes=tuple(sorted(reasons)),
        session_report_digests=report_digests,
        drill_evidence_digests=tuple(
            sorted(drill.drill_digest for drill in drills)
        ),
        parameter_review_digest=(
            None if parameter_review is None else parameter_review.review_digest
        ),
        stage_report_digests=tuple(
            sorted(
                (
                    stage.value,
                    tuple(
                        sorted(report.report_digest for report in by_stage[stage])
                    ),
                )
                for stage in NoOvernightEvidenceStage
            )
        ),
        drill_kind_digests=tuple(
            sorted(
                (kind.value, drill.drill_digest)
                for kind, drill in drills_by_kind.items()
            )
        ),
    )


_OBSERVATION_FIELDS = frozenset(
    {
        "campaign_id",
        "stage",
        "session_date",
        "account_scope_id",
        "policy_family_id",
        "policy_version",
        "policy_digest",
        "calendar_schema_version",
        "calendar_digest",
        "timezone",
        "reviewed_open",
        "reviewed_close",
        "observed_from",
        "observed_through",
        "finalized_at",
        "code_identity",
        "expected_provider_identity",
        "local_paper_session_id",
        "window_open_journal_sequence",
        "window_open_record_fingerprint",
        "window_close_journal_sequence",
        "window_close_record_fingerprint",
        "expected_deployment_manifest_digest",
        "expected_guard_identity",
    }
)
_METRIC_FIELDS = frozenset(NoOvernightEvidenceMetrics.__dataclass_fields__)
_REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "observation",
        "status",
        "qualification",
        "reason_codes",
        "no_overnight_session_id",
        "no_overnight_last_sequence",
        "no_overnight_projection_digest",
        "no_overnight_checkpoint_sequence",
        "no_overnight_checkpoint_digest",
        "local_paper_session_id",
        "local_paper_last_sequence",
        "local_paper_projection_digest",
        "local_paper_checkpoint_sequence",
        "local_paper_checkpoint_digest",
        "terminal_state",
        "result_status",
        "flat_proof_mode",
        "reconciliation_status",
        "reconciliation_digest",
        "breach_id",
        "breach_revision",
        "transition_count",
        "metrics",
        "postgres_destructive_uat",
        "activation_authority",
        "report_digest",
    }
)
_DRILL_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "kind",
        "status",
        "observed_at",
        "evidence_digest",
        "account_scope_id",
        "policy_family_id",
        "policy_digest",
        "deployment_manifest_digest",
        "activation_authority",
        "drill_digest",
    }
)
_PARAMETER_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "account_scope_id",
        "policy_family_id",
        "frozen_policy_version",
        "frozen_policy_digest",
        "frozen_deployment_manifest_digest",
        "code_identity",
        "reviewed_at",
        "reviewed_by",
        "review_note_digest",
        "false_positive_review_complete",
        "status",
        "review_phase",
        "reason_codes",
        "session_report_digests",
        "metrics",
        "activation_authority",
        "review_digest",
    }
)
_CAMPAIGN_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "account_scope_id",
        "policy_family_id",
        "frozen_policy_version",
        "frozen_policy_digest",
        "frozen_deployment_manifest_digest",
        "code_identity",
        "finalized_at",
        "status",
        "reason_codes",
        "session_report_digests",
        "drill_evidence_digests",
        "parameter_review_digest",
        "stage_report_digests",
        "drill_kind_digests",
        "independent_review_required",
        "unattended_local_paper_allowed",
        "broker_live_ready",
        "postgres_destructive_uat",
        "activation_authority",
        "report_digest",
    }
)


def _string_array(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise ValueError(f"{field_name} must be an array of strings")
    return tuple(value)


def _metrics_from_mapping(value: object) -> NoOvernightEvidenceMetrics:
    raw = _mapping(value, "metrics")
    _exact_fields(raw, _METRIC_FIELDS, "metrics")
    return NoOvernightEvidenceMetrics(
        **{
            field_name: _integer(raw[field_name], field_name)
            for field_name in _METRIC_FIELDS
        }
    )


def _stage_report_digest_entries(
    value: object,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    raw = _mapping(value, "stage_report_digests")
    entries: list[tuple[str, tuple[str, ...]]] = []
    for stage, raw_digests in raw.items():
        if stage not in {item.value for item in NoOvernightEvidenceStage}:
            raise ValueError("campaign stage digest key is invalid")
        digests = _string_array(raw_digests, f"{stage} report digests")
        for digest in digests:
            _sha256(digest, "stage_report_digest")
        entries.append((stage, digests))
    return tuple(sorted(entries))


def _drill_kind_digest_entries(
    value: object,
) -> tuple[tuple[str, str], ...]:
    raw = _mapping(value, "drill_kind_digests")
    entries = tuple(
        sorted(
            (
                kind,
                _sha256(digest, "drill_kind_digest"),
            )
            for kind, digest in raw.items()
        )
    )
    if any(kind not in {item.value for item in NoOvernightDrillKind} for kind, _ in entries):
        raise ValueError("campaign drill digest key is invalid")
    return entries


def _validate_ready_campaign_semantics(report: NoOvernightCampaignReport) -> None:
    if report.status is not NoOvernightCampaignStatus.READY_FOR_INDEPENDENT_REVIEW:
        return
    stage_mapping = dict(report.stage_report_digests)
    drill_mapping = dict(report.drill_kind_digests)
    if report.reason_codes:
        raise ValueError("review-ready campaign cannot carry failure reasons")
    if set(stage_mapping) != {stage.value for stage in NoOvernightEvidenceStage}:
        raise ValueError("review-ready campaign stage evidence is incomplete")
    if any(not digests for digests in stage_mapping.values()):
        raise ValueError("review-ready campaign stage evidence is empty")
    if set(drill_mapping) != {kind.value for kind in NoOvernightDrillKind}:
        raise ValueError("review-ready campaign drill evidence is incomplete")
    if report.parameter_review_digest is None:
        raise ValueError("review-ready campaign parameter review is missing")


def _observation_from_mapping(
    raw: Mapping[str, object],
) -> NoOvernightEvidenceObservation:
    _exact_fields(raw, _OBSERVATION_FIELDS, "observation")
    try:
        return NoOvernightEvidenceObservation(
            campaign_id=_text(raw["campaign_id"], "campaign_id"),
            stage=NoOvernightEvidenceStage(_text(raw["stage"], "stage")),
            session_date=date.fromisoformat(_text(raw["session_date"], "session_date")),
            account_scope_id=_text(raw["account_scope_id"], "account_scope_id"),
            policy_family_id=_text(raw["policy_family_id"], "policy_family_id"),
            policy_version=_text(raw["policy_version"], "policy_version"),
            policy_digest=_sha256(raw["policy_digest"], "policy_digest"),
            calendar_schema_version=_text(
                raw["calendar_schema_version"],
                "calendar_schema_version",
            ),
            calendar_digest=_sha256(raw["calendar_digest"], "calendar_digest"),
            timezone=_text(raw["timezone"], "timezone"),
            reviewed_open=datetime.fromisoformat(
                _text(raw["reviewed_open"], "reviewed_open")
            ),
            reviewed_close=datetime.fromisoformat(
                _text(raw["reviewed_close"], "reviewed_close")
            ),
            observed_from=datetime.fromisoformat(
                _text(raw["observed_from"], "observed_from")
            ),
            observed_through=datetime.fromisoformat(
                _text(raw["observed_through"], "observed_through")
            ),
            finalized_at=datetime.fromisoformat(
                _text(raw["finalized_at"], "finalized_at")
            ),
            code_identity=_text(raw["code_identity"], "code_identity"),
            expected_provider_identity=_text(
                raw["expected_provider_identity"],
                "expected_provider_identity",
            ),
            local_paper_session_id=_text(
                raw["local_paper_session_id"],
                "local_paper_session_id",
            ),
            window_open_journal_sequence=_integer(
                raw["window_open_journal_sequence"],
                "window_open_journal_sequence",
            ),
            window_open_record_fingerprint=_sha256(
                raw["window_open_record_fingerprint"],
                "window_open_record_fingerprint",
            ),
            window_close_journal_sequence=_integer(
                raw["window_close_journal_sequence"],
                "window_close_journal_sequence",
            ),
            window_close_record_fingerprint=_sha256(
                raw["window_close_record_fingerprint"],
                "window_close_record_fingerprint",
            ),
            expected_deployment_manifest_digest=_optional_sha256(
                raw["expected_deployment_manifest_digest"],
                "expected_deployment_manifest_digest",
            ),
            expected_guard_identity=_optional_text(
                raw["expected_guard_identity"],
                "expected_guard_identity",
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid no-overnight observation: {error}") from error


def _report_from_mapping(raw: Mapping[str, object]) -> NoOvernightSessionReport:
    _exact_fields(raw, _REPORT_FIELDS, "session evidence report")
    if raw["schema_version"] != NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA:
        raise ValueError("session evidence schema is unsupported")
    if raw["activation_authority"] != "NONE_EVIDENCE_ONLY":
        raise ValueError("session evidence cannot carry activation authority")
    reasons = raw["reason_codes"]
    if not isinstance(reasons, list) or any(type(item) is not str for item in reasons):
        raise ValueError("reason_codes must be an array of strings")
    metrics = _metrics_from_mapping(raw["metrics"])
    report = NoOvernightSessionReport(
        observation=_observation_from_mapping(
            _mapping(raw["observation"], "observation")
        ),
        status=NoOvernightEvidenceStatus(_text(raw["status"], "status")),
        qualification=NoOvernightQualificationStatus(
            _text(raw["qualification"], "qualification")
        ),
        reason_codes=tuple(reasons),
        no_overnight_session_id=_optional_text(
            raw["no_overnight_session_id"],
            "no_overnight_session_id",
        ),
        no_overnight_last_sequence=_optional_integer(
            raw["no_overnight_last_sequence"],
            "no_overnight_last_sequence",
        ),
        no_overnight_projection_digest=_optional_sha256(
            raw["no_overnight_projection_digest"],
            "no_overnight_projection_digest",
        ),
        no_overnight_checkpoint_sequence=_optional_integer(
            raw["no_overnight_checkpoint_sequence"],
            "no_overnight_checkpoint_sequence",
        ),
        no_overnight_checkpoint_digest=_optional_sha256(
            raw["no_overnight_checkpoint_digest"],
            "no_overnight_checkpoint_digest",
        ),
        local_paper_session_id=_text(
            raw["local_paper_session_id"],
            "local_paper_session_id",
        ),
        local_paper_last_sequence=_integer(
            raw["local_paper_last_sequence"],
            "local_paper_last_sequence",
        ),
        local_paper_projection_digest=_sha256(
            raw["local_paper_projection_digest"],
            "local_paper_projection_digest",
        ),
        local_paper_checkpoint_sequence=_integer(
            raw["local_paper_checkpoint_sequence"],
            "local_paper_checkpoint_sequence",
        ),
        local_paper_checkpoint_digest=_sha256(
            raw["local_paper_checkpoint_digest"],
            "local_paper_checkpoint_digest",
        ),
        terminal_state=_optional_text(raw["terminal_state"], "terminal_state"),
        result_status=_optional_text(raw["result_status"], "result_status"),
        flat_proof_mode=_optional_text(
            raw["flat_proof_mode"],
            "flat_proof_mode",
        ),
        reconciliation_status=_optional_text(
            raw["reconciliation_status"],
            "reconciliation_status",
        ),
        reconciliation_digest=_optional_sha256(
            raw["reconciliation_digest"],
            "reconciliation_digest",
        ),
        breach_id=_optional_text(raw["breach_id"], "breach_id"),
        breach_revision=_integer(raw["breach_revision"], "breach_revision"),
        transition_count=_integer(raw["transition_count"], "transition_count"),
        metrics=metrics,
        postgres_destructive_uat=_text(
            raw["postgres_destructive_uat"],
            "postgres_destructive_uat",
        ),
    )
    supplied_digest = _sha256(raw["report_digest"], "report_digest")
    if supplied_digest != report.report_digest:
        raise ValueError("session evidence report digest mismatch")
    return report


def _write_immutable_artifact(
    path: Path,
    payload: Mapping[str, object],
    label: str,
) -> Path:
    encoded = (_canonical_json(payload) + "\n").encode()
    absolute_path, parent_fd = _open_verified_artifact_parent(path, label)
    created = False
    committed = False
    file_fd: int | None = None
    try:
        try:
            file_fd = os.open(
                absolute_path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            created = True
        except FileExistsError:
            existing = _read_regular_artifact_at(
                parent_fd,
                absolute_path.name,
                label,
            )
            if existing != encoded:
                raise ValueError(f"{label} exists with different content")
            return path
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(file_fd, view)
                if written <= 0:
                    raise OSError("artifact write made no progress")
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
            file_fd = None
        os.fsync(parent_fd)
        committed = True
        return path
    except OSError as error:
        raise ValueError(f"{label} path is unsafe or unavailable") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if created and not committed:
            try:
                os.unlink(absolute_path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def _open_verified_artifact_parent(path: Path, label: str) -> tuple[Path, int]:
    try:
        absolute_path = Path(os.path.abspath(os.fspath(path)))
    except TypeError as error:
        raise ValueError(f"{label} path is invalid") from error
    if absolute_path.name in {"", ".", ".."}:
        raise ValueError(f"{label} path must name a file")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(os.sep, flags)
    try:
        for component in absolute_path.parent.parts[1:]:
            next_fd = os.open(
                component,
                flags,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise ValueError(f"{label} parent is not a directory")
        return absolute_path, directory_fd
    except (OSError, ValueError) as error:
        os.close(directory_fd)
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"{label} parent path is unsafe or unavailable") from error


def _read_regular_artifact_at(
    parent_fd: int,
    name: str,
    label: str,
) -> bytes:
    try:
        file_fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        raise ValueError(f"{label} path is unsafe or unavailable") from error
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise ValueError(f"{label} must be a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(file_fd, 64 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(file_fd)


def _read_artifact_bytes(path: Path, label: str) -> bytes:
    absolute_path, parent_fd = _open_verified_artifact_parent(path, label)
    try:
        return _read_regular_artifact_at(parent_fd, absolute_path.name, label)
    finally:
        os.close(parent_fd)


_DirectoryEntryFence = tuple[int, int, int, int, int, int, int]


def _directory_entry_modes(
    directory: Path,
    label: str,
) -> dict[str, _DirectoryEntryFence]:
    _, directory_fd = _open_verified_artifact_parent(
        directory / "__bundle_entry__",
        label,
    )
    try:
        entries: dict[str, _DirectoryEntryFence] = {}
        for name in os.listdir(directory_fd):
            if type(name) is not str or name in {"", ".", ".."}:
                raise ValueError(f"{label} contains an invalid entry")
            try:
                entry = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ValueError(f"{label} entry is unavailable") from error
            entries[name] = (
                entry.st_dev,
                entry.st_ino,
                entry.st_mode,
                entry.st_nlink,
                entry.st_size,
                entry.st_mtime_ns,
                entry.st_ctime_ns,
            )
        return dict(sorted(entries.items()))
    finally:
        os.close(directory_fd)


def write_no_overnight_session_report(
    path: Path,
    report: NoOvernightSessionReport,
) -> Path:
    return _write_immutable_artifact(path, report.payload(), "session evidence report")


def read_no_overnight_session_report(path: Path) -> NoOvernightSessionReport:
    raw = _read_artifact(path, "session evidence report")
    return _report_from_mapping(raw)


def _read_artifact(path: Path, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(_read_artifact_bytes(path, label))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is unreadable") from error
    return _mapping(raw, label)


def write_no_overnight_drill_evidence(
    path: Path,
    drill: NoOvernightDrillEvidence,
) -> Path:
    return _write_immutable_artifact(path, drill.payload(), "drill evidence")


def read_no_overnight_drill_evidence(path: Path) -> NoOvernightDrillEvidence:
    raw = _read_artifact(path, "drill evidence")
    _exact_fields(raw, _DRILL_FIELDS, "drill evidence")
    if raw["schema_version"] != "no_overnight_drill_evidence_v1":
        raise ValueError("drill evidence schema is unsupported")
    if raw["activation_authority"] != "NONE_EVIDENCE_ONLY":
        raise ValueError("drill evidence cannot carry activation authority")
    drill = NoOvernightDrillEvidence(
        campaign_id=_text(raw["campaign_id"], "campaign_id"),
        kind=NoOvernightDrillKind(_text(raw["kind"], "kind")),
        status=NoOvernightDrillStatus(_text(raw["status"], "status")),
        observed_at=datetime.fromisoformat(_text(raw["observed_at"], "observed_at")),
        evidence_digest=_sha256(raw["evidence_digest"], "evidence_digest"),
        account_scope_id=_text(raw["account_scope_id"], "account_scope_id"),
        policy_family_id=_text(raw["policy_family_id"], "policy_family_id"),
        policy_digest=_sha256(raw["policy_digest"], "policy_digest"),
        deployment_manifest_digest=_sha256(
            raw["deployment_manifest_digest"],
            "deployment_manifest_digest",
        ),
    )
    if _sha256(raw["drill_digest"], "drill_digest") != drill.drill_digest:
        raise ValueError("drill evidence digest mismatch")
    return drill


def write_no_overnight_parameter_review(
    path: Path,
    review: NoOvernightParameterReview,
) -> Path:
    return _write_immutable_artifact(path, review.payload(), "parameter review")


def read_no_overnight_parameter_review(path: Path) -> NoOvernightParameterReview:
    raw = _read_artifact(path, "parameter review")
    _exact_fields(raw, _PARAMETER_REVIEW_FIELDS, "parameter review")
    if raw["schema_version"] != "no_overnight_parameter_review_v2":
        raise ValueError("parameter review schema is unsupported")
    if raw["activation_authority"] != "NONE_EVIDENCE_ONLY":
        raise ValueError("parameter review cannot carry activation authority")
    if type(raw["false_positive_review_complete"]) is not bool:
        raise ValueError("parameter review false-positive flag is invalid")
    review = NoOvernightParameterReview(
        campaign_id=_text(raw["campaign_id"], "campaign_id"),
        account_scope_id=_text(raw["account_scope_id"], "account_scope_id"),
        policy_family_id=_text(raw["policy_family_id"], "policy_family_id"),
        frozen_policy_version=_text(
            raw["frozen_policy_version"],
            "frozen_policy_version",
        ),
        frozen_policy_digest=_sha256(
            raw["frozen_policy_digest"],
            "frozen_policy_digest",
        ),
        frozen_deployment_manifest_digest=_sha256(
            raw["frozen_deployment_manifest_digest"],
            "frozen_deployment_manifest_digest",
        ),
        code_identity=_text(raw["code_identity"], "code_identity"),
        reviewed_at=datetime.fromisoformat(_text(raw["reviewed_at"], "reviewed_at")),
        reviewed_by=_text(raw["reviewed_by"], "reviewed_by"),
        review_note_digest=_sha256(
            raw["review_note_digest"],
            "review_note_digest",
        ),
        false_positive_review_complete=raw["false_positive_review_complete"],
        status=NoOvernightParameterReviewStatus(
            _text(raw["status"], "status")
        ),
        review_phase=NoOvernightParameterReviewPhase(
            _text(raw["review_phase"], "review_phase")
        ),
        reason_codes=_string_array(raw["reason_codes"], "reason_codes"),
        session_report_digests=_string_array(
            raw["session_report_digests"],
            "session_report_digests",
        ),
        metrics=_metrics_from_mapping(raw["metrics"]),
    )
    if _sha256(raw["review_digest"], "review_digest") != review.review_digest:
        raise ValueError("parameter review digest mismatch")
    if (
        review.status is NoOvernightParameterReviewStatus.FROZEN
        and _parameter_metric_reason_codes(
            review.metrics,
            false_positive_review_complete=(
                review.false_positive_review_complete
            ),
        )
    ):
        raise ValueError("frozen parameter review evidence is insufficient")
    return review


def write_no_overnight_campaign_report(
    path: Path,
    report: NoOvernightCampaignReport,
) -> Path:
    return _write_immutable_artifact(path, report.payload(), "campaign report")


def _read_no_overnight_campaign_artifact(
    path: Path,
) -> NoOvernightCampaignReport:
    raw = _read_artifact(path, "campaign report")
    _exact_fields(raw, _CAMPAIGN_FIELDS, "campaign report")
    if raw["schema_version"] != "no_overnight_campaign_report_v2":
        raise ValueError("campaign report schema is unsupported")
    if raw["activation_authority"] != "NONE_EVIDENCE_ONLY":
        raise ValueError("campaign report cannot carry activation authority")
    boolean_fields = (
        "independent_review_required",
        "unattended_local_paper_allowed",
        "broker_live_ready",
    )
    if any(type(raw[field_name]) is not bool for field_name in boolean_fields):
        raise ValueError("campaign readiness flag is invalid")
    report = NoOvernightCampaignReport(
        campaign_id=_text(raw["campaign_id"], "campaign_id"),
        account_scope_id=_text(raw["account_scope_id"], "account_scope_id"),
        policy_family_id=_text(raw["policy_family_id"], "policy_family_id"),
        frozen_policy_version=_text(
            raw["frozen_policy_version"],
            "frozen_policy_version",
        ),
        frozen_policy_digest=_sha256(
            raw["frozen_policy_digest"],
            "frozen_policy_digest",
        ),
        frozen_deployment_manifest_digest=_sha256(
            raw["frozen_deployment_manifest_digest"],
            "frozen_deployment_manifest_digest",
        ),
        code_identity=_text(raw["code_identity"], "code_identity"),
        finalized_at=datetime.fromisoformat(_text(raw["finalized_at"], "finalized_at")),
        status=NoOvernightCampaignStatus(_text(raw["status"], "status")),
        reason_codes=_string_array(raw["reason_codes"], "reason_codes"),
        session_report_digests=_string_array(
            raw["session_report_digests"],
            "session_report_digests",
        ),
        drill_evidence_digests=_string_array(
            raw["drill_evidence_digests"],
            "drill_evidence_digests",
        ),
        parameter_review_digest=_optional_sha256(
            raw["parameter_review_digest"],
            "parameter_review_digest",
        ),
        stage_report_digests=_stage_report_digest_entries(
            raw["stage_report_digests"]
        ),
        drill_kind_digests=_drill_kind_digest_entries(
            raw["drill_kind_digests"]
        ),
        independent_review_required=raw["independent_review_required"],
        unattended_local_paper_allowed=raw["unattended_local_paper_allowed"],
        broker_live_ready=raw["broker_live_ready"],
        postgres_destructive_uat=_text(
            raw["postgres_destructive_uat"],
            "postgres_destructive_uat",
        ),
    )
    if _sha256(raw["report_digest"], "report_digest") != report.report_digest:
        raise ValueError("campaign report digest mismatch")
    _validate_ready_campaign_semantics(report)
    return report


def _session_bundle_filename(report: NoOvernightSessionReport) -> str:
    suffix = {
        NoOvernightEvidenceStage.DISABLED_BASELINE: "disabled",
        NoOvernightEvidenceStage.OBSERVE_ONLY: "observe-only",
        NoOvernightEvidenceStage.SUPERVISED_ENFORCING: (
            "supervised-enforcing"
        ),
    }[report.observation.stage]
    return f"{report.observation.session_date.isoformat()}-{suffix}.json"


def _drill_bundle_filename(drill: NoOvernightDrillEvidence) -> str:
    return f"{drill.kind.value.lower().replace('_', '-')}.json"


def _require_bundle_entry(
    entries: Mapping[str, _DirectoryEntryFence],
    name: str,
    *,
    directory: bool,
) -> None:
    entry = entries.get(name)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if entry is None or not expected(entry[2]):
        kind = "directory" if directory else "regular file"
        raise ValueError(f"campaign bundle requires {name} as a {kind}")


def read_no_overnight_campaign_bundle(
    root: Path,
) -> NoOvernightCampaignReport:
    """Strictly rebuild a campaign from its canonical persisted bundle."""

    root = Path(root)
    root_entries = _directory_entry_modes(root, "campaign bundle")
    _require_bundle_entry(root_entries, "sessions", directory=True)
    _require_bundle_entry(root_entries, "drills", directory=True)
    _require_bundle_entry(
        root_entries,
        "campaign_report.json",
        directory=False,
    )
    campaign = _read_no_overnight_campaign_artifact(
        root / "campaign_report.json"
    )
    expected_root_entries = {
        "sessions",
        "drills",
        "campaign_report.json",
    }
    parameter_review: NoOvernightParameterReview | None = None
    if campaign.parameter_review_digest is not None:
        expected_root_entries.add("parameter_review.json")
        _require_bundle_entry(
            root_entries,
            "parameter_review.json",
            directory=False,
        )
        parameter_review = read_no_overnight_parameter_review(
            root / "parameter_review.json"
        )
        if parameter_review.review_digest != campaign.parameter_review_digest:
            raise ValueError("campaign parameter review digest mismatch")
    if "review_notes.sha256" in root_entries:
        if parameter_review is None:
            raise ValueError("campaign review-note digest has no parameter review")
        expected_root_entries.add("review_notes.sha256")
        _require_bundle_entry(
            root_entries,
            "review_notes.sha256",
            directory=False,
        )
        expected_note_digest = f"{parameter_review.review_note_digest}\n".encode()
        if _read_artifact_bytes(
            root / "review_notes.sha256",
            "campaign review-note digest",
        ) != expected_note_digest:
            raise ValueError("campaign review-note digest file mismatch")
    if set(root_entries) != expected_root_entries:
        raise ValueError("campaign bundle contains unexpected root entries")

    session_directory = root / "sessions"
    session_entries = _directory_entry_modes(
        session_directory,
        "campaign session artifacts",
    )
    reports: list[NoOvernightSessionReport] = []
    for name, entry in session_entries.items():
        if not stat.S_ISREG(entry[2]) or not name.endswith(".json"):
            raise ValueError("campaign session artifact is not a JSON file")
        report = read_no_overnight_session_report(session_directory / name)
        if name != _session_bundle_filename(report):
            raise ValueError("campaign session artifact filename is invalid")
        reports.append(report)
    if not reports:
        raise ValueError("campaign bundle requires session artifacts")
    if len({report.report_digest for report in reports}) != len(reports):
        raise ValueError("campaign bundle contains duplicate session reports")
    actual_stage_mapping = tuple(
        sorted(
            (
                stage.value,
                tuple(
                    sorted(
                        report.report_digest
                        for report in reports
                        if report.observation.stage is stage
                    )
                ),
            )
            for stage in NoOvernightEvidenceStage
        )
    )
    if actual_stage_mapping != campaign.stage_report_digests:
        raise ValueError("campaign session mapping mismatch")
    if tuple(sorted(report.report_digest for report in reports)) != (
        campaign.session_report_digests
    ):
        raise ValueError("campaign session digest set mismatch")

    drill_directory = root / "drills"
    drill_entries = _directory_entry_modes(
        drill_directory,
        "campaign drill artifacts",
    )
    drills: list[NoOvernightDrillEvidence] = []
    for name, entry in drill_entries.items():
        if not stat.S_ISREG(entry[2]) or not name.endswith(".json"):
            raise ValueError("campaign drill artifact is not a JSON file")
        drill = read_no_overnight_drill_evidence(drill_directory / name)
        if name != _drill_bundle_filename(drill):
            raise ValueError("campaign drill artifact filename is invalid")
        drills.append(drill)
    if len({drill.kind for drill in drills}) != len(drills):
        raise ValueError("campaign bundle contains duplicate drill kinds")
    actual_drill_mapping = tuple(
        sorted((drill.kind.value, drill.drill_digest) for drill in drills)
    )
    if actual_drill_mapping != campaign.drill_kind_digests:
        raise ValueError("campaign drill mapping mismatch")
    if tuple(sorted(drill.drill_digest for drill in drills)) != (
        campaign.drill_evidence_digests
    ):
        raise ValueError("campaign drill digest set mismatch")

    ordered_reports = tuple(
        sorted(
            reports,
            key=lambda report: (
                report.observation.session_date,
                report.observation.stage.value,
                report.report_digest,
            ),
        )
    )
    ordered_drills = tuple(sorted(drills, key=lambda drill: drill.kind.value))
    rebuilt = build_no_overnight_campaign_report(
        reports=ordered_reports,
        drills=ordered_drills,
        parameter_review=parameter_review,
        frozen_policy_version=campaign.frozen_policy_version,
        frozen_policy_digest=campaign.frozen_policy_digest,
        frozen_deployment_manifest_digest=(
            campaign.frozen_deployment_manifest_digest
        ),
        finalized_at=campaign.finalized_at,
    )
    if rebuilt != campaign:
        raise ValueError("campaign bundle does not reproduce sealed campaign")

    final_root_entries = _directory_entry_modes(root, "campaign bundle")
    if set(final_root_entries) != expected_root_entries:
        raise ValueError("campaign bundle contains unexpected root entries")
    final_session_entries = _directory_entry_modes(
        session_directory,
        "campaign session artifacts",
    )
    final_drill_entries = _directory_entry_modes(
        drill_directory,
        "campaign drill artifacts",
    )
    if (
        final_root_entries != root_entries
        or final_session_entries != session_entries
        or final_drill_entries != drill_entries
    ):
        raise ValueError("campaign bundle changed during validation")
    return campaign


def read_no_overnight_campaign_report(path: Path) -> NoOvernightCampaignReport:
    """Strictly read a campaign artifact and its canonical sibling bundle."""

    path = Path(path)
    artifact = _read_no_overnight_campaign_artifact(path)
    if path.name != "campaign_report.json":
        raise ValueError("campaign report path is not canonical")
    bundle = read_no_overnight_campaign_bundle(path.parent)
    if bundle != artifact:
        raise ValueError("campaign report conflicts with campaign bundle")
    return bundle
