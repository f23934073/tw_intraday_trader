"""Strict Journal serialization and replay for the no_overnight.v1 projection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from trading.journal import (
    JournalAppendResult,
    JournalRecord,
    JournalRepository,
    ProjectionCheckpoint,
)
from trading.no_overnight import (
    ExposureQuantity,
    FlatProofMode,
    ManagedExposureEvidence,
    NoOvernightEvidence,
    NoOvernightState,
    NoOvernightWouldAction,
    ReconciliationStatus,
    canonical_transition_digest,
    expected_would_actions,
    strict_flat_proof,
)


NO_OVERNIGHT_PROJECTION_NAME = "no_overnight.v1"
NO_OVERNIGHT_EXECUTION_FACT_KIND = "no_overnight_execution_fact_observed.v1"
NO_OVERNIGHT_SNAPSHOT_KIND = "no_overnight_snapshot.v1"
NO_OVERNIGHT_TRANSITION_KIND = "no_overnight_transition.v1"
NO_OVERNIGHT_RECONCILIATION_KIND = "no_overnight_reconciliation.v1"
NO_OVERNIGHT_RESULT_KIND = "no_overnight_result.v1"
NO_OVERNIGHT_BREACH_KIND = "no_overnight_breach.v1"
NO_OVERNIGHT_BREACH_RESOLVED_KIND = "no_overnight_breach_resolved.v1"
NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND = "no_overnight_breach_acknowledged.v1"
_SUPPORTED_KINDS = frozenset(
    {
        NO_OVERNIGHT_EXECUTION_FACT_KIND,
        NO_OVERNIGHT_SNAPSHOT_KIND,
        NO_OVERNIGHT_TRANSITION_KIND,
        NO_OVERNIGHT_RECONCILIATION_KIND,
        NO_OVERNIGHT_RESULT_KIND,
        NO_OVERNIGHT_BREACH_KIND,
        NO_OVERNIGHT_BREACH_RESOLVED_KIND,
        NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
    }
)
_STATE_RANK = {
    NoOvernightState.NORMAL: 0,
    NoOvernightState.NO_NEW_ENTRY: 1,
    NoOvernightState.CANCEL_ENTRY: 2,
    NoOvernightState.FLATTENING: 3,
    NoOvernightState.AGGRESSIVE_EXIT: 4,
    NoOvernightState.FINAL_RECONCILIATION: 5,
    NoOvernightState.CONFIRMED_FLAT: 6,
    NoOvernightState.OVERNIGHT_BREACH: 6,
}


class NoOvernightProjectionError(ValueError):
    """Journal evidence cannot be replayed into one trusted projection."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _record_id(kind: str, identity: str) -> str:
    return uuid5(NAMESPACE_URL, f"{kind}:{identity}").hex


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    if frozenset(payload) != expected:
        raise NoOvernightProjectionError(f"{label} fields mismatch")


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if type(value) is not str or not value.strip():
        raise NoOvernightProjectionError(f"{name} must be a non-empty string")
    return value


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise NoOvernightProjectionError(f"{name} must be null or non-empty string")
    return value


def _integer(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if type(value) is not int or value < 0:
        raise NoOvernightProjectionError(f"{name} must be a non-negative integer")
    return value


def _positive_integer(payload: Mapping[str, Any], name: str) -> int:
    value = _integer(payload, name)
    if value == 0:
        raise NoOvernightProjectionError(f"{name} must be a positive integer")
    return value


def _sha256(payload: Mapping[str, Any], name: str) -> str:
    value = _text(payload, name)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise NoOvernightProjectionError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _aware_datetime(payload: Mapping[str, Any], name: str) -> datetime:
    raw = _text(payload, name)
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as error:
        raise NoOvernightProjectionError(f"{name} is invalid") from error
    if value.tzinfo is None or value.utcoffset() is None:
        raise NoOvernightProjectionError(f"{name} must be timezone-aware")
    if value.isoformat() != raw:
        raise NoOvernightProjectionError(f"{name} is not canonical")
    return value


def _date(payload: Mapping[str, Any], name: str) -> date:
    raw = _text(payload, name)
    try:
        value = date.fromisoformat(raw)
    except ValueError as error:
        raise NoOvernightProjectionError(f"{name} is invalid") from error
    if value.isoformat() != raw:
        raise NoOvernightProjectionError(f"{name} is not canonical")
    return value


def _string_list(payload: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise NoOvernightProjectionError(f"{name} must be a list")
    items = tuple(value)
    if any(type(item) is not str or not item.strip() for item in items):
        raise NoOvernightProjectionError(f"{name} must contain non-empty strings")
    if tuple(sorted(items)) != items or len(set(items)) != len(items):
        raise NoOvernightProjectionError(f"{name} must be sorted and unique")
    return items


_IDENTITY_FIELDS = frozenset({"account_scope_id", "policy_family_id", "session_date"})
_EXECUTION_FIELDS = _IDENTITY_FIELDS | frozenset(
    {"source_journal_sequence", "source_kind", "source_record_id"}
)
_SNAPSHOT_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "managed_exposures",
        "pending_entry_quantity",
        "pending_exit_quantity",
        "unresolved_execution_ids",
        "reconciliation_status",
        "reconciliation_digest",
        "last_fill_journal_sequence",
        "last_execution_fact_journal_sequence",
        "snapshot_covers_through_journal_sequence",
        "snapshot_journal_sequence",
        "snapshot_source_as_of",
        "snapshot_received_at",
    }
)
_TRANSITION_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "policy_version",
        "policy_digest",
        "previous_state",
        "state",
        "revision",
        "planned_at",
        "would_actions",
        "planner_input_digest",
        "transition_digest",
        "flat_proof_mode",
    }
)
_RESULT_FIELDS = _SNAPSHOT_FIELDS | frozenset(
    {
        "policy_version",
        "policy_digest",
        "state",
        "revision",
        "flat_proof_mode",
        "transition_planned_at",
        "result_at",
    }
)
_RECONCILIATION_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "policy_version",
        "policy_digest",
        "reconciliation_status",
        "reconciliation_digest",
        "snapshot_covers_through_journal_sequence",
        "snapshot_journal_sequence",
        "reconciled_at",
        "observe_only",
    }
)
_BREACH_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "policy_version",
        "policy_digest",
        "breach_id",
        "breach_revision",
        "breach_reason",
        "revision_reason",
        "severity",
        "managed_open_quantity",
        "pending_entry_quantity",
        "pending_exit_quantity",
        "unresolved_execution_count",
        "evidence_session_date",
        "evidence_snapshot_journal_sequence",
        "evidence_reconciliation_journal_sequence",
        "evidence_through_journal_sequence",
        "reconciliation_digest",
        "strict_flat_proof_mode",
        "source_result_journal_sequence",
        "breached_at",
    }
)
_BREACH_RESOLVED_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "breach_id",
        "breach_revision",
        "reconciliation_digest",
        "evidence_through_journal_sequence",
        "evidence_snapshot_journal_sequence",
        "evidence_reconciliation_journal_sequence",
        "strict_flat_proof_mode",
        "resolved_session_date",
        "resolved_at",
    }
)
_BREACH_ACKNOWLEDGED_FIELDS = _IDENTITY_FIELDS | frozenset(
    {
        "breach_id",
        "breach_revision",
        "reconciliation_digest",
        "actor_id",
        "idempotency_key",
        "resolution_journal_sequence",
        "acknowledged_session_date",
        "acknowledged_at",
    }
)

_BREACH_REASONS = frozenset(
    {
        "MANAGED_EXPOSURE_OPEN",
        "PENDING_ORDER",
        "UNRESOLVED_EXECUTION",
        "RECONCILIATION_REQUIRED",
        "STRICT_FLAT_PROOF_MISSING",
    }
)
_BREACH_REVISION_REASONS = _BREACH_REASONS | frozenset(
    {"EVIDENCE_CHANGED", "STRICT_FLAT_REESTABLISHED"}
)


def _identity(payload: Mapping[str, Any]) -> tuple[str, str, date]:
    return (
        _text(payload, "account_scope_id"),
        _text(payload, "policy_family_id"),
        _date(payload, "session_date"),
    )


def _quantity_items(
    payload: Mapping[str, Any],
    name: str,
) -> tuple[ExposureQuantity, ...]:
    raw = payload.get(name)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise NoOvernightProjectionError(f"{name} must be a list")
    result: list[ExposureQuantity] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise NoOvernightProjectionError(f"{name} item must be an object")
        _require_exact_fields(
            item,
            frozenset({"exposure_id", "quantity"}),
            f"{name} item",
        )
        result.append(
            ExposureQuantity(
                exposure_id=_text(item, "exposure_id"),
                quantity=_integer(item, "quantity"),
            )
        )
    if tuple(sorted(result)) != tuple(result):
        raise NoOvernightProjectionError(f"{name} must be canonical sorted")
    return tuple(result)


def _managed_exposures(
    payload: Mapping[str, Any],
) -> tuple[ManagedExposureEvidence, ...]:
    raw = payload.get("managed_exposures")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise NoOvernightProjectionError("managed_exposures must be a list")
    expected = frozenset(
        {
            "exposure_id",
            "current_quantity",
            "max_quantity_during_session",
            "authoritative_open_fill_quantity",
            "authoritative_close_fill_quantity",
        }
    )
    result: list[ManagedExposureEvidence] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise NoOvernightProjectionError("managed_exposures item must be an object")
        _require_exact_fields(item, expected, "managed_exposures item")
        try:
            result.append(
                ManagedExposureEvidence(
                    exposure_id=_text(item, "exposure_id"),
                    current_quantity=_integer(item, "current_quantity"),
                    max_quantity_during_session=_integer(
                        item,
                        "max_quantity_during_session",
                    ),
                    authoritative_open_fill_quantity=_integer(
                        item,
                        "authoritative_open_fill_quantity",
                    ),
                    authoritative_close_fill_quantity=_integer(
                        item,
                        "authoritative_close_fill_quantity",
                    ),
                )
            )
        except ValueError as error:
            raise NoOvernightProjectionError(str(error)) from error
    if tuple(sorted(result)) != tuple(result):
        raise NoOvernightProjectionError("managed_exposures must be canonical sorted")
    return tuple(result)


def _evidence(payload: Mapping[str, Any]) -> NoOvernightEvidence:
    _require_exact_fields(payload, _SNAPSHOT_FIELDS, "no-overnight snapshot")
    try:
        return NoOvernightEvidence(
            session_date=_date(payload, "session_date"),
            managed_exposures=_managed_exposures(payload),
            pending_entry_quantity=_quantity_items(
                payload,
                "pending_entry_quantity",
            ),
            pending_exit_quantity=_quantity_items(
                payload,
                "pending_exit_quantity",
            ),
            unresolved_execution_ids=_string_list(
                payload,
                "unresolved_execution_ids",
            ),
            reconciliation_status=ReconciliationStatus(
                _text(payload, "reconciliation_status")
            ),
            reconciliation_digest=_text(payload, "reconciliation_digest"),
            last_fill_journal_sequence=_integer(
                payload,
                "last_fill_journal_sequence",
            ),
            last_execution_fact_journal_sequence=_integer(
                payload,
                "last_execution_fact_journal_sequence",
            ),
            snapshot_covers_through_journal_sequence=_integer(
                payload,
                "snapshot_covers_through_journal_sequence",
            ),
            snapshot_journal_sequence=_integer(
                payload,
                "snapshot_journal_sequence",
            ),
            snapshot_source_as_of=_aware_datetime(
                payload,
                "snapshot_source_as_of",
            ),
            snapshot_received_at=_aware_datetime(
                payload,
                "snapshot_received_at",
            ),
        )
    except (ValueError, TypeError) as error:
        raise NoOvernightProjectionError(str(error)) from error


@dataclass
class NoOvernightProjection:
    account_scope_id: str | None = None
    policy_family_id: str | None = None
    session_date: date | None = None
    policy_version: str | None = None
    policy_digest: str | None = None
    state: NoOvernightState = NoOvernightState.NORMAL
    revision: int = 0
    would_actions: tuple[NoOvernightWouldAction, ...] = ()
    flat_proof_mode: str | None = None
    last_planner_input_digest: str | None = None
    last_transition_digest: str | None = None
    last_transition_planned_at: datetime | None = None
    evidence: NoOvernightEvidence | None = None
    last_execution_fact_journal_sequence: int = 0
    latest_result_snapshot_fence: int | None = None
    latest_result_revision: int | None = None
    latest_result_journal_sequence: int | None = None
    result_status: str | None = None
    last_reconciliation_status: str | None = None
    last_reconciliation_digest: str | None = None
    last_reconciled_at: datetime | None = None
    last_reconciliation_journal_sequence: int = 0
    breach_id: str | None = None
    breach_revision: int = 0
    breach_reason: str | None = None
    breach_revision_reason: str | None = None
    breach_severity: str | None = None
    breach_managed_open_quantity: int = 0
    breach_pending_entry_quantity: int = 0
    breach_pending_exit_quantity: int = 0
    breach_unresolved_execution_count: int = 0
    breach_evidence_session_date: date | None = None
    breach_evidence_snapshot_journal_sequence: int = 0
    breach_evidence_reconciliation_journal_sequence: int = 0
    breach_evidence_through_journal_sequence: int = 0
    breach_reconciliation_digest: str | None = None
    breach_strict_flat_proof_mode: str | None = None
    breach_record_sequence: int = 0
    breach_revised_at: datetime | None = None
    breach_resolved: bool = False
    breach_resolution_session_date: date | None = None
    breach_resolved_at: datetime | None = None
    breach_resolution_sequence: int = 0
    breach_acknowledged: bool = False
    breach_ack_actor_id: str | None = None
    breach_ack_idempotency_key: str | None = None
    breach_ack_session_date: date | None = None
    breach_acknowledged_at: datetime | None = None
    breach_ack_sequence: int = 0
    breach_invalidation_sequence: int = 0
    last_sequence: int = 0

    def apply(self, appended: JournalAppendResult) -> None:
        record = appended.record
        if appended.sequence <= self.last_sequence:
            raise NoOvernightProjectionError(
                "Journal sequence must be strictly increasing"
            )
        if record.kind not in _SUPPORTED_KINDS:
            raise NoOvernightProjectionError(
                f"unsupported no-overnight record kind: {record.kind}"
            )
        payload = record.payload
        if record.kind == NO_OVERNIGHT_EXECUTION_FACT_KIND:
            _require_exact_fields(payload, _EXECUTION_FIELDS, "execution fact")
            self._bind_identity(*_identity(payload))
            source_sequence = _integer(payload, "source_journal_sequence")
            _text(payload, "source_kind")
            _text(payload, "source_record_id")
            if source_sequence <= self.last_execution_fact_journal_sequence:
                raise NoOvernightProjectionError(
                    "execution fact sequence must be strictly increasing"
                )
            self.last_execution_fact_journal_sequence = source_sequence
            if (
                self.latest_result_snapshot_fence is not None
                and source_sequence > self.latest_result_snapshot_fence
            ):
                self.result_status = "SUPERSEDED"
            if (
                self.breach_id is not None
                and source_sequence > self.breach_evidence_through_journal_sequence
            ):
                self._invalidate_breach_handling(appended.sequence)
        elif record.kind == NO_OVERNIGHT_SNAPSHOT_KIND:
            self._bind_identity(*_identity(payload))
            evidence = _evidence(payload)
            if evidence.snapshot_journal_sequence != 0:
                raise NoOvernightProjectionError(
                    "snapshot event sequence must be unassigned before append"
                )
            if (
                evidence.last_execution_fact_journal_sequence
                != self.last_execution_fact_journal_sequence
            ):
                raise NoOvernightProjectionError(
                    "snapshot execution fact fence does not match projection"
                )
            self.evidence = replace(
                evidence,
                snapshot_journal_sequence=appended.sequence,
            )
            if self.breach_id is not None and (
                evidence.last_execution_fact_journal_sequence
                != self.breach_evidence_through_journal_sequence
                or evidence.reconciliation_digest != self.breach_reconciliation_digest
            ):
                self._invalidate_breach_handling(appended.sequence)
        elif record.kind == NO_OVERNIGHT_TRANSITION_KIND:
            _require_exact_fields(payload, _TRANSITION_FIELDS, "transition")
            self._bind_identity(*_identity(payload))
            self._bind_policy(
                _text(payload, "policy_version"),
                _sha256(payload, "policy_digest"),
            )
            previous = NoOvernightState(_text(payload, "previous_state"))
            state = NoOvernightState(_text(payload, "state"))
            revision = _integer(payload, "revision")
            if previous is not self.state or revision != self.revision + 1:
                raise NoOvernightProjectionError("transition lineage mismatch")
            if _STATE_RANK[state] < _STATE_RANK[previous]:
                raise NoOvernightProjectionError("transition cannot move backward")
            if (
                previous is NoOvernightState.OVERNIGHT_BREACH
                and state is not NoOvernightState.OVERNIGHT_BREACH
            ):
                raise NoOvernightProjectionError(
                    "transition cannot release OVERNIGHT_BREACH"
                )
            actions = tuple(
                NoOvernightWouldAction(value)
                for value in _string_list(payload, "would_actions")
            )
            if actions != expected_would_actions(state):
                raise NoOvernightProjectionError(
                    "transition would actions do not match state"
                )
            flat_proof_mode = _optional_text(payload, "flat_proof_mode")
            if state is NoOvernightState.CONFIRMED_FLAT:
                try:
                    FlatProofMode(flat_proof_mode)
                except (TypeError, ValueError) as error:
                    raise NoOvernightProjectionError(
                        "confirmed-flat transition proof is invalid"
                    ) from error
                if self.evidence is None:
                    raise NoOvernightProjectionError(
                        "terminal transition is missing snapshot evidence"
                    )
                expected_proof = strict_flat_proof(self.evidence)
                if expected_proof is None or flat_proof_mode != expected_proof.value:
                    raise NoOvernightProjectionError(
                        "transition proof does not match snapshot evidence"
                    )
            elif flat_proof_mode is not None:
                raise NoOvernightProjectionError(
                    "non-flat transition cannot carry a flat proof"
                )
            elif state is NoOvernightState.OVERNIGHT_BREACH:
                if self.evidence is None:
                    raise NoOvernightProjectionError(
                        "terminal transition is missing snapshot evidence"
                    )
                if (
                    previous is not NoOvernightState.OVERNIGHT_BREACH
                    and strict_flat_proof(self.evidence) is not None
                ):
                    raise NoOvernightProjectionError(
                        "initial breach transition requires non-flat evidence"
                    )
            planned_at = _aware_datetime(payload, "planned_at")
            planner_input_digest = _sha256(payload, "planner_input_digest")
            transition_digest = _sha256(payload, "transition_digest")
            expected_digest = canonical_transition_digest(
                previous_state=previous,
                state=state,
                revision=revision,
                planned_at=planned_at,
                would_actions=actions,
                flat_proof_mode=flat_proof_mode,
                planner_input_digest=planner_input_digest,
            )
            if transition_digest != expected_digest:
                raise NoOvernightProjectionError("transition digest mismatch")
            self.state = state
            self.revision = revision
            self.would_actions = actions
            self.flat_proof_mode = flat_proof_mode
            self.last_planner_input_digest = planner_input_digest
            self.last_transition_digest = transition_digest
            self.last_transition_planned_at = planned_at
        elif record.kind == NO_OVERNIGHT_RECONCILIATION_KIND:
            _require_exact_fields(
                payload,
                _RECONCILIATION_FIELDS,
                "reconciliation",
            )
            self._bind_identity(*_identity(payload))
            self._bind_policy(
                _text(payload, "policy_version"),
                _sha256(payload, "policy_digest"),
            )
            status = ReconciliationStatus(_text(payload, "reconciliation_status"))
            digest = _sha256(payload, "reconciliation_digest")
            covers_through = _integer(
                payload,
                "snapshot_covers_through_journal_sequence",
            )
            snapshot_sequence = _integer(
                payload,
                "snapshot_journal_sequence",
            )
            reconciled_at = _aware_datetime(payload, "reconciled_at")
            if payload.get("observe_only") is not True:
                raise NoOvernightProjectionError(
                    "PR-NO-002 reconciliation must be observe-only"
                )
            if self.evidence is None or (
                covers_through != self.evidence.snapshot_covers_through_journal_sequence
                or snapshot_sequence != self.evidence.snapshot_journal_sequence
                or digest != self.evidence.reconciliation_digest
                or status is not self.evidence.reconciliation_status
            ):
                raise NoOvernightProjectionError(
                    "reconciliation does not match snapshot evidence"
                )
            self.last_reconciliation_status = status.value
            self.last_reconciliation_digest = digest
            self.last_reconciled_at = reconciled_at
            self.last_reconciliation_journal_sequence = appended.sequence
        elif record.kind == NO_OVERNIGHT_RESULT_KIND:
            _require_exact_fields(payload, _RESULT_FIELDS, "result")
            self._bind_identity(*_identity(payload))
            self._bind_policy(
                _text(payload, "policy_version"),
                _sha256(payload, "policy_digest"),
            )
            state = NoOvernightState(_text(payload, "state"))
            revision = _integer(payload, "revision")
            result_evidence = _evidence({key: payload[key] for key in _SNAPSHOT_FIELDS})
            flat_proof_mode = _optional_text(payload, "flat_proof_mode")
            transition_planned_at = _aware_datetime(
                payload,
                "transition_planned_at",
            )
            _aware_datetime(payload, "result_at")
            if state is not self.state or revision != self.revision:
                raise NoOvernightProjectionError("result transition lineage mismatch")
            if self.evidence is None or result_evidence != self.evidence:
                raise NoOvernightProjectionError("result snapshot evidence mismatch")
            if transition_planned_at != self.last_transition_planned_at:
                raise NoOvernightProjectionError("result transition timestamp mismatch")
            if flat_proof_mode != self.flat_proof_mode:
                raise NoOvernightProjectionError(
                    "result proof does not match transition proof"
                )
            if (
                result_evidence.snapshot_covers_through_journal_sequence
                < self.last_execution_fact_journal_sequence
            ):
                raise NoOvernightProjectionError(
                    "result snapshot fence is behind execution facts"
                )
            if (
                self.result_status == "SUPERSEDED"
                and self.latest_result_revision is not None
                and revision <= self.latest_result_revision
            ):
                raise NoOvernightProjectionError(
                    "superseded result requires a newer transition revision"
                )
            if state is NoOvernightState.CONFIRMED_FLAT:
                proof = strict_flat_proof(result_evidence)
                if proof is None or flat_proof_mode != proof.value:
                    raise NoOvernightProjectionError(
                        "confirmed-flat result proof does not match evidence"
                    )
            elif state is NoOvernightState.OVERNIGHT_BREACH:
                if flat_proof_mode is not None:
                    raise NoOvernightProjectionError(
                        "overnight-breach result cannot carry a flat proof"
                    )
            else:
                raise NoOvernightProjectionError("result state must be terminal")
            self.latest_result_snapshot_fence = (
                result_evidence.snapshot_covers_through_journal_sequence
            )
            self.latest_result_revision = revision
            self.latest_result_journal_sequence = appended.sequence
            self.result_status = "CURRENT"
        elif record.kind == NO_OVERNIGHT_BREACH_KIND:
            self._apply_breach(appended)
        elif record.kind == NO_OVERNIGHT_BREACH_RESOLVED_KIND:
            self._apply_breach_resolution(appended)
        else:
            self._apply_breach_acknowledgement(appended)
        self.last_sequence = appended.sequence

    def _apply_breach(self, appended: JournalAppendResult) -> None:
        payload = appended.record.payload
        _require_exact_fields(payload, _BREACH_FIELDS, "breach")
        self._bind_identity(*_identity(payload))
        self._bind_policy(
            _text(payload, "policy_version"),
            _sha256(payload, "policy_digest"),
        )
        if self.state is not NoOvernightState.OVERNIGHT_BREACH:
            raise NoOvernightProjectionError(
                "breach requires an OVERNIGHT_BREACH projection"
            )
        breach_id = _text(payload, "breach_id")
        expected_id = breach_id_for(
            account_scope_id=self.account_scope_id or "",
            policy_family_id=self.policy_family_id or "",
            originating_session_date=self.session_date or date.min,
        )
        if breach_id != expected_id:
            raise NoOvernightProjectionError("breach identity mismatch")
        revision = _positive_integer(payload, "breach_revision")
        if revision != self.breach_revision + 1:
            raise NoOvernightProjectionError("breach revision lineage mismatch")
        breach_reason = _text(payload, "breach_reason")
        revision_reason = _text(payload, "revision_reason")
        if breach_reason not in _BREACH_REASONS:
            raise NoOvernightProjectionError("breach reason is invalid")
        if revision_reason not in _BREACH_REVISION_REASONS:
            raise NoOvernightProjectionError("breach revision reason is invalid")
        if self.breach_reason is not None and breach_reason != self.breach_reason:
            raise NoOvernightProjectionError("originating breach reason changed")
        if revision == 1 and revision_reason != breach_reason:
            raise NoOvernightProjectionError(
                "initial breach revision reason must match breach reason"
            )
        if _text(payload, "severity") != "CRITICAL":
            raise NoOvernightProjectionError("breach severity must be CRITICAL")
        managed_quantity = _integer(payload, "managed_open_quantity")
        pending_entry = _integer(payload, "pending_entry_quantity")
        pending_exit = _integer(payload, "pending_exit_quantity")
        unresolved = _integer(payload, "unresolved_execution_count")
        evidence_session_date = _date(payload, "evidence_session_date")
        if evidence_session_date < (self.session_date or date.min):
            raise NoOvernightProjectionError(
                "breach evidence session predates originating session"
            )
        snapshot_sequence = _positive_integer(
            payload,
            "evidence_snapshot_journal_sequence",
        )
        reconciliation_sequence = _positive_integer(
            payload,
            "evidence_reconciliation_journal_sequence",
        )
        evidence_through = _integer(
            payload,
            "evidence_through_journal_sequence",
        )
        reconciliation_digest = _sha256(payload, "reconciliation_digest")
        flat_proof = _optional_text(payload, "strict_flat_proof_mode")
        if flat_proof is not None:
            try:
                FlatProofMode(flat_proof)
            except ValueError as error:
                raise NoOvernightProjectionError(
                    "breach strict flat proof is invalid"
                ) from error
            if any((managed_quantity, pending_entry, pending_exit, unresolved)):
                raise NoOvernightProjectionError(
                    "flat breach revision carries non-flat quantities"
                )
            if revision_reason != "STRICT_FLAT_REESTABLISHED":
                raise NoOvernightProjectionError(
                    "flat breach revision reason is invalid"
                )
        elif revision > 1 and revision_reason == "STRICT_FLAT_REESTABLISHED":
            raise NoOvernightProjectionError(
                "flat breach revision is missing strict proof"
            )
        source_result_sequence = _integer(
            payload,
            "source_result_journal_sequence",
        )
        breached_at = _aware_datetime(payload, "breached_at")
        if (
            appended.record.record_id
            != _record_id(
                NO_OVERNIGHT_BREACH_KIND,
                _canonical_digest(dict(payload)),
            )
            or appended.record.occurred_at != breached_at
            or appended.record.idempotency_scope
            != f"{appended.record.session_id}:breach-revision"
            or appended.record.idempotency_key != str(revision)
        ):
            raise NoOvernightProjectionError("breach Journal identity mismatch")
        if max(snapshot_sequence, reconciliation_sequence, source_result_sequence) >= (
            appended.sequence
        ):
            raise NoOvernightProjectionError(
                "breach evidence must precede the breach record"
            )
        if revision == 1:
            if (
                self.result_status != "CURRENT"
                or self.latest_result_journal_sequence is None
                or source_result_sequence != self.latest_result_journal_sequence
            ):
                raise NoOvernightProjectionError(
                    "initial breach is not bound to the current terminal result"
                )
        elif source_result_sequence != 0:
            raise NoOvernightProjectionError(
                "later breach revision must use evidence revision provenance"
            )
        if revision > 1 and (
            evidence_through == self.breach_evidence_through_journal_sequence
            and reconciliation_digest == self.breach_reconciliation_digest
        ):
            raise NoOvernightProjectionError(
                "breach revision does not carry new evidence"
            )
        if revision > 1 and (
            evidence_session_date < (self.breach_evidence_session_date or date.min)
            or snapshot_sequence <= self.breach_evidence_snapshot_journal_sequence
            or reconciliation_sequence
            <= self.breach_evidence_reconciliation_journal_sequence
            or evidence_through < self.breach_evidence_through_journal_sequence
            or self.breach_revised_at is None
            or breached_at < self.breach_revised_at
        ):
            raise NoOvernightProjectionError(
                "breach revision evidence must move monotonically forward"
            )
        if self.breach_id is not None:
            self._invalidate_breach_handling(appended.sequence)
        self.breach_id = breach_id
        self.breach_revision = revision
        self.breach_reason = breach_reason
        self.breach_revision_reason = revision_reason
        self.breach_severity = "CRITICAL"
        self.breach_managed_open_quantity = managed_quantity
        self.breach_pending_entry_quantity = pending_entry
        self.breach_pending_exit_quantity = pending_exit
        self.breach_unresolved_execution_count = unresolved
        self.breach_evidence_session_date = evidence_session_date
        self.breach_evidence_snapshot_journal_sequence = snapshot_sequence
        self.breach_evidence_reconciliation_journal_sequence = reconciliation_sequence
        self.breach_evidence_through_journal_sequence = evidence_through
        self.breach_reconciliation_digest = reconciliation_digest
        self.breach_strict_flat_proof_mode = flat_proof
        self.breach_record_sequence = appended.sequence
        self.breach_revised_at = breached_at

    def _apply_breach_resolution(self, appended: JournalAppendResult) -> None:
        payload = appended.record.payload
        _require_exact_fields(
            payload,
            _BREACH_RESOLVED_FIELDS,
            "breach resolution",
        )
        self._bind_identity(*_identity(payload))
        self._require_latest_breach_target(payload)
        flat_proof = _text(payload, "strict_flat_proof_mode")
        if self.breach_strict_flat_proof_mode is None or (
            flat_proof != self.breach_strict_flat_proof_mode
            or _integer(payload, "evidence_through_journal_sequence")
            != self.breach_evidence_through_journal_sequence
            or _positive_integer(
                payload,
                "evidence_snapshot_journal_sequence",
            )
            != self.breach_evidence_snapshot_journal_sequence
            or _positive_integer(
                payload,
                "evidence_reconciliation_journal_sequence",
            )
            != self.breach_evidence_reconciliation_journal_sequence
        ):
            raise NoOvernightProjectionError(
                "breach resolution does not bind strict flat evidence"
            )
        resolved_session_date = _date(payload, "resolved_session_date")
        resolved_at = _aware_datetime(payload, "resolved_at")
        if (
            appended.record.record_id
            != _record_id(
                NO_OVERNIGHT_BREACH_RESOLVED_KIND,
                _canonical_digest(dict(payload)),
            )
            or appended.record.occurred_at != resolved_at
            or appended.record.idempotency_scope != f"{self.breach_id}:resolution"
            or appended.record.idempotency_key
            != f"{self.breach_revision}:{self.breach_reconciliation_digest}"
        ):
            raise NoOvernightProjectionError(
                "breach resolution Journal identity mismatch"
            )
        if resolved_at.date() != resolved_session_date:
            raise NoOvernightProjectionError("breach resolution date mismatch")
        if resolved_session_date < (self.breach_evidence_session_date or date.min):
            raise NoOvernightProjectionError("breach resolution predates its evidence")
        if self.breach_revised_at is None or resolved_at < self.breach_revised_at:
            raise NoOvernightProjectionError("breach resolution predates its revision")
        if appended.sequence <= self.breach_record_sequence:
            raise NoOvernightProjectionError(
                "breach resolution must follow its revision"
            )
        if self.breach_resolved:
            raise NoOvernightProjectionError("breach revision is already resolved")
        self.breach_resolved = True
        self.breach_resolution_session_date = resolved_session_date
        self.breach_resolved_at = resolved_at
        self.breach_resolution_sequence = appended.sequence

    def _apply_breach_acknowledgement(
        self,
        appended: JournalAppendResult,
    ) -> None:
        payload = appended.record.payload
        _require_exact_fields(
            payload,
            _BREACH_ACKNOWLEDGED_FIELDS,
            "breach acknowledgement",
        )
        self._bind_identity(*_identity(payload))
        self._require_latest_breach_target(payload)
        if not self.breach_resolved:
            raise NoOvernightProjectionError(
                "breach acknowledgement requires resolution"
            )
        if (
            _positive_integer(payload, "resolution_journal_sequence")
            != self.breach_resolution_sequence
        ):
            raise NoOvernightProjectionError(
                "breach acknowledgement resolution fence mismatch"
            )
        if self.breach_acknowledged:
            raise NoOvernightProjectionError("breach revision is already acknowledged")
        actor_id = _text(payload, "actor_id")
        idempotency_key = _text(payload, "idempotency_key")
        acknowledged_session_date = _date(
            payload,
            "acknowledged_session_date",
        )
        acknowledged_at = _aware_datetime(payload, "acknowledged_at")
        if (
            appended.record.record_id
            != _record_id(
                NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
                _canonical_digest(dict(payload)),
            )
            or appended.record.occurred_at != acknowledged_at
            or appended.record.idempotency_scope != f"{self.breach_id}:acknowledgement"
            or appended.record.idempotency_key != idempotency_key
        ):
            raise NoOvernightProjectionError(
                "breach acknowledgement Journal identity mismatch"
            )
        if acknowledged_at.date() != acknowledged_session_date:
            raise NoOvernightProjectionError("breach acknowledgement date mismatch")
        if acknowledged_session_date < (
            self.breach_resolution_session_date or date.min
        ):
            raise NoOvernightProjectionError(
                "breach acknowledgement predates resolution"
            )
        if self.breach_resolved_at is None or acknowledged_at < self.breach_resolved_at:
            raise NoOvernightProjectionError(
                "breach acknowledgement predates resolution"
            )
        if appended.sequence <= self.breach_resolution_sequence:
            raise NoOvernightProjectionError(
                "breach acknowledgement must follow resolution"
            )
        self.breach_acknowledged = True
        self.breach_ack_actor_id = actor_id
        self.breach_ack_idempotency_key = idempotency_key
        self.breach_ack_session_date = acknowledged_session_date
        self.breach_acknowledged_at = acknowledged_at
        self.breach_ack_sequence = appended.sequence

    def _require_latest_breach_target(self, payload: Mapping[str, Any]) -> None:
        if self.breach_id is None or (
            _text(payload, "breach_id") != self.breach_id
            or _positive_integer(payload, "breach_revision") != self.breach_revision
            or _sha256(payload, "reconciliation_digest")
            != self.breach_reconciliation_digest
        ):
            raise NoOvernightProjectionError("breach target is not the latest revision")

    def _invalidate_breach_handling(self, sequence: int) -> None:
        if self.breach_resolved or self.breach_acknowledged:
            self.breach_invalidation_sequence = sequence
        self.breach_resolved = False
        self.breach_resolution_session_date = None
        self.breach_resolved_at = None
        self.breach_resolution_sequence = 0
        self.breach_acknowledged = False
        self.breach_ack_actor_id = None
        self.breach_ack_idempotency_key = None
        self.breach_ack_session_date = None
        self.breach_acknowledged_at = None
        self.breach_ack_sequence = 0

    def _bind_identity(
        self,
        account_scope_id: str,
        policy_family_id: str,
        session_date: date,
    ) -> None:
        identity = (
            self.account_scope_id,
            self.policy_family_id,
            self.session_date,
        )
        incoming = (account_scope_id, policy_family_id, session_date)
        if identity == (None, None, None):
            self.account_scope_id, self.policy_family_id, self.session_date = incoming
            return
        if identity != incoming:
            raise NoOvernightProjectionError("projection identity mismatch")

    def _bind_policy(self, policy_version: str, policy_digest: str) -> None:
        if self.policy_version is None and self.policy_digest is None:
            self.policy_version = policy_version
            self.policy_digest = policy_digest
            return
        if (self.policy_version, self.policy_digest) != (
            policy_version,
            policy_digest,
        ):
            raise NoOvernightProjectionError("projection policy revision mismatch")

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())

    @property
    def legacy_digest(self) -> str:
        """Digest of the exact PR-NO-004 projection checkpoint payload."""

        return _canonical_digest(self.legacy_payload())

    def legacy_payload(self) -> dict[str, object]:
        return {
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "session_date": (
                None if self.session_date is None else self.session_date.isoformat()
            ),
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "state": self.state.value,
            "revision": self.revision,
            "would_actions": [item.value for item in self.would_actions],
            "flat_proof_mode": self.flat_proof_mode,
            "last_planner_input_digest": self.last_planner_input_digest,
            "last_transition_digest": self.last_transition_digest,
            "last_transition_planned_at": (
                None
                if self.last_transition_planned_at is None
                else self.last_transition_planned_at.isoformat()
            ),
            "evidence": None if self.evidence is None else self.evidence.payload(),
            "last_execution_fact_journal_sequence": (
                self.last_execution_fact_journal_sequence
            ),
            "latest_result_snapshot_fence": self.latest_result_snapshot_fence,
            "latest_result_revision": self.latest_result_revision,
            "result_status": self.result_status,
            "last_reconciliation_status": self.last_reconciliation_status,
            "last_reconciliation_digest": self.last_reconciliation_digest,
            "last_reconciled_at": (
                None
                if self.last_reconciled_at is None
                else self.last_reconciled_at.isoformat()
            ),
            "last_sequence": self.last_sequence,
        }

    def payload(self) -> dict[str, object]:
        return {
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "session_date": (
                None if self.session_date is None else self.session_date.isoformat()
            ),
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "state": self.state.value,
            "revision": self.revision,
            "would_actions": [item.value for item in self.would_actions],
            "flat_proof_mode": self.flat_proof_mode,
            "last_planner_input_digest": self.last_planner_input_digest,
            "last_transition_digest": self.last_transition_digest,
            "last_transition_planned_at": (
                None
                if self.last_transition_planned_at is None
                else self.last_transition_planned_at.isoformat()
            ),
            "evidence": None if self.evidence is None else self.evidence.payload(),
            "last_execution_fact_journal_sequence": (
                self.last_execution_fact_journal_sequence
            ),
            "latest_result_snapshot_fence": self.latest_result_snapshot_fence,
            "latest_result_revision": self.latest_result_revision,
            "latest_result_journal_sequence": self.latest_result_journal_sequence,
            "result_status": self.result_status,
            "last_reconciliation_status": self.last_reconciliation_status,
            "last_reconciliation_digest": self.last_reconciliation_digest,
            "last_reconciled_at": (
                None
                if self.last_reconciled_at is None
                else self.last_reconciled_at.isoformat()
            ),
            "last_reconciliation_journal_sequence": (
                self.last_reconciliation_journal_sequence
            ),
            "breach_id": self.breach_id,
            "breach_revision": self.breach_revision,
            "breach_reason": self.breach_reason,
            "breach_revision_reason": self.breach_revision_reason,
            "breach_severity": self.breach_severity,
            "breach_managed_open_quantity": (self.breach_managed_open_quantity),
            "breach_pending_entry_quantity": (self.breach_pending_entry_quantity),
            "breach_pending_exit_quantity": (self.breach_pending_exit_quantity),
            "breach_unresolved_execution_count": (
                self.breach_unresolved_execution_count
            ),
            "breach_evidence_session_date": (
                None
                if self.breach_evidence_session_date is None
                else self.breach_evidence_session_date.isoformat()
            ),
            "breach_evidence_snapshot_journal_sequence": (
                self.breach_evidence_snapshot_journal_sequence
            ),
            "breach_evidence_reconciliation_journal_sequence": (
                self.breach_evidence_reconciliation_journal_sequence
            ),
            "breach_evidence_through_journal_sequence": (
                self.breach_evidence_through_journal_sequence
            ),
            "breach_reconciliation_digest": self.breach_reconciliation_digest,
            "breach_strict_flat_proof_mode": (self.breach_strict_flat_proof_mode),
            "breach_record_sequence": self.breach_record_sequence,
            "breach_revised_at": (
                None
                if self.breach_revised_at is None
                else self.breach_revised_at.isoformat()
            ),
            "breach_resolved": self.breach_resolved,
            "breach_resolution_session_date": (
                None
                if self.breach_resolution_session_date is None
                else self.breach_resolution_session_date.isoformat()
            ),
            "breach_resolved_at": (
                None
                if self.breach_resolved_at is None
                else self.breach_resolved_at.isoformat()
            ),
            "breach_resolution_sequence": self.breach_resolution_sequence,
            "breach_acknowledged": self.breach_acknowledged,
            "breach_ack_actor_id": self.breach_ack_actor_id,
            "breach_ack_idempotency_key": self.breach_ack_idempotency_key,
            "breach_ack_session_date": (
                None
                if self.breach_ack_session_date is None
                else self.breach_ack_session_date.isoformat()
            ),
            "breach_acknowledged_at": (
                None
                if self.breach_acknowledged_at is None
                else self.breach_acknowledged_at.isoformat()
            ),
            "breach_ack_sequence": self.breach_ack_sequence,
            "breach_invalidation_sequence": self.breach_invalidation_sequence,
            "last_sequence": self.last_sequence,
        }


def execution_fact_observed_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    source_journal_sequence: int,
    source_kind: str,
    source_record_id: str,
    occurred_at: datetime,
) -> JournalRecord:
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": session_date.isoformat(),
        "source_journal_sequence": source_journal_sequence,
        "source_kind": source_kind,
        "source_record_id": source_record_id,
    }
    identity = f"{session_date}:{source_journal_sequence}:{source_record_id}"
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_EXECUTION_FACT_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_EXECUTION_FACT_KIND,
        occurred_at=occurred_at,
        payload=payload,
        idempotency_scope=f"{session_id}:execution-fact",
        idempotency_key=str(source_journal_sequence),
    )


def snapshot_record(*, session_id: str, payload: Mapping[str, Any]) -> JournalRecord:
    received_at = datetime.fromisoformat(str(payload["snapshot_received_at"]))
    digest = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_SNAPSHOT_KIND, digest),
        session_id=session_id,
        kind=NO_OVERNIGHT_SNAPSHOT_KIND,
        occurred_at=received_at,
        payload=payload,
        idempotency_scope=f"{session_id}:snapshot",
        idempotency_key=digest,
    )


def transition_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    policy_version: str,
    policy_digest: str,
    previous_state: NoOvernightState,
    state: NoOvernightState,
    revision: int,
    planned_at: datetime,
    would_actions: tuple[str, ...],
    planner_input_digest: str,
    transition_digest: str,
    flat_proof_mode: str | None,
) -> JournalRecord:
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": session_date.isoformat(),
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "previous_state": previous_state.value,
        "state": state.value,
        "revision": revision,
        "planned_at": planned_at.isoformat(),
        "would_actions": list(would_actions),
        "planner_input_digest": planner_input_digest,
        "transition_digest": transition_digest,
        "flat_proof_mode": flat_proof_mode,
    }
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_TRANSITION_KIND, transition_digest),
        session_id=session_id,
        kind=NO_OVERNIGHT_TRANSITION_KIND,
        occurred_at=planned_at,
        payload=payload,
        idempotency_scope=f"{session_id}:transition",
        idempotency_key=planner_input_digest,
    )


def no_overnight_result_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    policy_version: str,
    policy_digest: str,
    state: NoOvernightState,
    revision: int,
    flat_proof_mode: str | None,
    evidence: NoOvernightEvidence,
    transition_planned_at: datetime,
    result_at: datetime,
) -> JournalRecord:
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        **evidence.payload(),
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "state": state.value,
        "revision": revision,
        "flat_proof_mode": flat_proof_mode,
        "transition_planned_at": transition_planned_at.isoformat(),
        "result_at": result_at.isoformat(),
    }
    if evidence.session_date != session_date:
        raise ValueError("result evidence session identity mismatch")
    identity = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_RESULT_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_RESULT_KIND,
        occurred_at=result_at,
        payload=payload,
        idempotency_scope=f"{session_id}:result",
        idempotency_key=f"{revision}:{identity}",
    )


def no_overnight_reconciliation_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    policy_version: str,
    policy_digest: str,
    evidence: NoOvernightEvidence,
    reconciled_at: datetime,
) -> JournalRecord:
    if evidence.session_date != session_date:
        raise ValueError("reconciliation evidence session identity mismatch")
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": session_date.isoformat(),
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "reconciliation_status": evidence.reconciliation_status.value,
        "reconciliation_digest": evidence.reconciliation_digest,
        "snapshot_covers_through_journal_sequence": (
            evidence.snapshot_covers_through_journal_sequence
        ),
        "snapshot_journal_sequence": evidence.snapshot_journal_sequence,
        "reconciled_at": reconciled_at.isoformat(),
        "observe_only": True,
    }
    identity = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_RECONCILIATION_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_RECONCILIATION_KIND,
        occurred_at=reconciled_at,
        payload=payload,
        idempotency_scope=f"{session_id}:reconciliation",
        idempotency_key=f"{evidence.snapshot_journal_sequence}:{identity}",
    )


def breach_id_for(
    *,
    account_scope_id: str,
    policy_family_id: str,
    originating_session_date: date,
) -> str:
    if not account_scope_id.strip() or not policy_family_id.strip():
        raise ValueError("breach identity must not be empty")
    if type(originating_session_date) is not date:
        raise ValueError("breach session date is invalid")
    identity = (
        f"{account_scope_id}:{policy_family_id}:{originating_session_date.isoformat()}"
    )
    return uuid5(NAMESPACE_URL, f"no-overnight-breach:{identity}").hex


def no_overnight_breach_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    originating_session_date: date,
    policy_version: str,
    policy_digest: str,
    breach_id: str,
    breach_revision: int,
    breach_reason: str,
    revision_reason: str,
    evidence: NoOvernightEvidence,
    evidence_session_date: date,
    evidence_reconciliation_journal_sequence: int,
    source_result_journal_sequence: int,
    breached_at: datetime,
) -> JournalRecord:
    if evidence.session_date != evidence_session_date:
        raise ValueError("breach evidence session identity mismatch")
    proof = strict_flat_proof(evidence)
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": originating_session_date.isoformat(),
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "breach_id": breach_id,
        "breach_revision": breach_revision,
        "breach_reason": breach_reason,
        "revision_reason": revision_reason,
        "severity": "CRITICAL",
        "managed_open_quantity": sum(
            item.current_quantity for item in evidence.managed_exposures
        ),
        "pending_entry_quantity": sum(
            item.quantity for item in evidence.pending_entry_quantity
        ),
        "pending_exit_quantity": sum(
            item.quantity for item in evidence.pending_exit_quantity
        ),
        "unresolved_execution_count": len(evidence.unresolved_execution_ids),
        "evidence_session_date": evidence_session_date.isoformat(),
        "evidence_snapshot_journal_sequence": (evidence.snapshot_journal_sequence),
        "evidence_reconciliation_journal_sequence": (
            evidence_reconciliation_journal_sequence
        ),
        "evidence_through_journal_sequence": (
            evidence.snapshot_covers_through_journal_sequence
        ),
        "reconciliation_digest": evidence.reconciliation_digest,
        "strict_flat_proof_mode": None if proof is None else proof.value,
        "source_result_journal_sequence": source_result_journal_sequence,
        "breached_at": breached_at.isoformat(),
    }
    identity = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_BREACH_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_BREACH_KIND,
        occurred_at=breached_at,
        payload=payload,
        idempotency_scope=f"{session_id}:breach-revision",
        idempotency_key=str(breach_revision),
    )


def no_overnight_breach_resolved_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    originating_session_date: date,
    breach_id: str,
    breach_revision: int,
    reconciliation_digest: str,
    evidence_through_journal_sequence: int,
    evidence_snapshot_journal_sequence: int,
    evidence_reconciliation_journal_sequence: int,
    strict_flat_proof_mode: str,
    resolved_session_date: date,
    resolved_at: datetime,
) -> JournalRecord:
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": originating_session_date.isoformat(),
        "breach_id": breach_id,
        "breach_revision": breach_revision,
        "reconciliation_digest": reconciliation_digest,
        "evidence_through_journal_sequence": (evidence_through_journal_sequence),
        "evidence_snapshot_journal_sequence": (evidence_snapshot_journal_sequence),
        "evidence_reconciliation_journal_sequence": (
            evidence_reconciliation_journal_sequence
        ),
        "strict_flat_proof_mode": strict_flat_proof_mode,
        "resolved_session_date": resolved_session_date.isoformat(),
        "resolved_at": resolved_at.isoformat(),
    }
    identity = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_BREACH_RESOLVED_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_BREACH_RESOLVED_KIND,
        occurred_at=resolved_at,
        payload=payload,
        idempotency_scope=f"{breach_id}:resolution",
        idempotency_key=f"{breach_revision}:{reconciliation_digest}",
    )


def no_overnight_breach_acknowledged_record(
    *,
    session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    originating_session_date: date,
    breach_id: str,
    breach_revision: int,
    reconciliation_digest: str,
    actor_id: str,
    resolution_journal_sequence: int,
    acknowledged_session_date: date,
    acknowledged_at: datetime,
    idempotency_key: str,
) -> JournalRecord:
    payload = {
        "account_scope_id": account_scope_id,
        "policy_family_id": policy_family_id,
        "session_date": originating_session_date.isoformat(),
        "breach_id": breach_id,
        "breach_revision": breach_revision,
        "reconciliation_digest": reconciliation_digest,
        "actor_id": actor_id,
        "idempotency_key": idempotency_key,
        "resolution_journal_sequence": resolution_journal_sequence,
        "acknowledged_session_date": acknowledged_session_date.isoformat(),
        "acknowledged_at": acknowledged_at.isoformat(),
    }
    identity = _canonical_digest(payload)
    return JournalRecord(
        record_id=_record_id(NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND, identity),
        session_id=session_id,
        kind=NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
        occurred_at=acknowledged_at,
        payload=payload,
        idempotency_scope=f"{breach_id}:acknowledgement",
        idempotency_key=idempotency_key,
    )


def validate_breach_evidence_reference(
    journal: JournalRepository,
    projection: NoOvernightProjection,
) -> NoOvernightEvidence:
    """Cross-check the latest breach revision against durable snapshot evidence."""

    if (
        projection.breach_id is None
        or projection.breach_evidence_session_date is None
        or projection.breach_reconciliation_digest is None
    ):
        raise NoOvernightProjectionError("breach evidence reference is incomplete")
    evidence_session_id = (
        f"no-overnight-v1-{projection.breach_evidence_session_date.isoformat()}"
    )
    rebuilt = rebuild_no_overnight_projection(
        journal,
        session_id=evidence_session_id,
        require_checkpoint=True,
        _validate_breach_reference=False,
    )
    checkpoint = journal.latest_checkpoint(
        evidence_session_id,
        NO_OVERNIGHT_PROJECTION_NAME,
    )
    if (
        checkpoint is None
        or checkpoint.journal_sequence
        < projection.breach_evidence_reconciliation_journal_sequence
    ):
        raise NoOvernightProjectionError(
            "breach evidence is not covered by a trusted checkpoint"
        )
    records = {
        appended.sequence: appended for appended in journal.records(evidence_session_id)
    }
    snapshot = records.get(projection.breach_evidence_snapshot_journal_sequence)
    reconciliation = records.get(
        projection.breach_evidence_reconciliation_journal_sequence
    )
    if snapshot is None or snapshot.record.kind != NO_OVERNIGHT_SNAPSHOT_KIND:
        raise NoOvernightProjectionError("breach snapshot evidence record is missing")
    if (
        reconciliation is None
        or reconciliation.record.kind != NO_OVERNIGHT_RECONCILIATION_KIND
    ):
        raise NoOvernightProjectionError(
            "breach reconciliation evidence record is missing"
        )
    evidence = replace(
        _evidence(snapshot.record.payload),
        snapshot_journal_sequence=snapshot.sequence,
    )
    reconciliation_payload = reconciliation.record.payload
    _require_exact_fields(
        reconciliation_payload,
        _RECONCILIATION_FIELDS,
        "breach reconciliation evidence",
    )
    if (
        _identity(snapshot.record.payload)
        != (
            projection.account_scope_id,
            projection.policy_family_id,
            projection.breach_evidence_session_date,
        )
        or _identity(reconciliation_payload)
        != (
            projection.account_scope_id,
            projection.policy_family_id,
            projection.breach_evidence_session_date,
        )
        or _integer(reconciliation_payload, "snapshot_journal_sequence")
        != snapshot.sequence
        or _integer(
            reconciliation_payload,
            "snapshot_covers_through_journal_sequence",
        )
        != evidence.snapshot_covers_through_journal_sequence
        or _sha256(reconciliation_payload, "reconciliation_digest")
        != evidence.reconciliation_digest
        or ReconciliationStatus(_text(reconciliation_payload, "reconciliation_status"))
        is not evidence.reconciliation_status
        or reconciliation_payload.get("observe_only") is not True
        or _text(reconciliation_payload, "policy_version") != rebuilt.policy_version
        or _sha256(reconciliation_payload, "policy_digest") != rebuilt.policy_digest
    ):
        raise NoOvernightProjectionError(
            "breach reconciliation does not bind its snapshot"
        )
    proof = strict_flat_proof(evidence)
    if (
        evidence.snapshot_covers_through_journal_sequence
        != projection.breach_evidence_through_journal_sequence
        or evidence.reconciliation_digest != projection.breach_reconciliation_digest
        or sum(item.current_quantity for item in evidence.managed_exposures)
        != projection.breach_managed_open_quantity
        or sum(item.quantity for item in evidence.pending_entry_quantity)
        != projection.breach_pending_entry_quantity
        or sum(item.quantity for item in evidence.pending_exit_quantity)
        != projection.breach_pending_exit_quantity
        or len(evidence.unresolved_execution_ids)
        != projection.breach_unresolved_execution_count
        or (None if proof is None else proof.value)
        != projection.breach_strict_flat_proof_mode
    ):
        raise NoOvernightProjectionError(
            "breach revision does not match referenced evidence"
        )
    reconciled_at = _aware_datetime(reconciliation_payload, "reconciled_at")
    if projection.breach_revised_at is None or projection.breach_revised_at < max(
        evidence.snapshot_received_at,
        reconciled_at,
    ):
        raise NoOvernightProjectionError("breach revision predates referenced evidence")
    if rebuilt.account_scope_id != projection.account_scope_id or (
        rebuilt.policy_family_id != projection.policy_family_id
    ):
        raise NoOvernightProjectionError("breach evidence scope mismatch")
    return evidence


def rebuild_no_overnight_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    require_checkpoint: bool,
    _validate_breach_reference: bool = True,
) -> NoOvernightProjection:
    session = journal.session(session_id)
    if session is None:
        raise NoOvernightProjectionError("no-overnight session is missing")
    required_metadata = (
        "account_scope_id",
        "policy_family_id",
        "session_date",
        "policy_digest",
    )
    if any(
        type(session.metadata.get(field_name)) is not str
        or not str(session.metadata[field_name]).strip()
        for field_name in required_metadata
    ):
        raise NoOvernightProjectionError(
            "no-overnight session identity metadata is incomplete"
        )
    projection = NoOvernightProjection()
    checkpoint = journal.latest_checkpoint(session_id, NO_OVERNIGHT_PROJECTION_NAME)
    if require_checkpoint and checkpoint is None:
        raise NoOvernightProjectionError("no-overnight recovery requires a checkpoint")
    checkpoint_digest = None
    checkpoint_legacy_digest = None
    checkpoint_has_g5_event = False
    g5_event_seen = False
    if checkpoint is not None and checkpoint.journal_sequence == 0:
        checkpoint_digest = projection.digest
        checkpoint_legacy_digest = projection.legacy_digest
    for appended in journal.records(session_id):
        projection.apply(appended)
        if appended.record.kind in {
            NO_OVERNIGHT_BREACH_KIND,
            NO_OVERNIGHT_BREACH_RESOLVED_KIND,
            NO_OVERNIGHT_BREACH_ACKNOWLEDGED_KIND,
        }:
            g5_event_seen = True
        if checkpoint is not None and appended.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest
            checkpoint_legacy_digest = projection.legacy_digest
            checkpoint_has_g5_event = g5_event_seen
    if projection.account_scope_id is not None and (
        projection.account_scope_id != session.metadata["account_scope_id"]
        or projection.policy_family_id != session.metadata["policy_family_id"]
        or projection.session_date.isoformat() != session.metadata["session_date"]
    ):
        raise NoOvernightProjectionError(
            "no-overnight projection/session identity mismatch"
        )
    if projection.policy_digest is not None and (
        projection.policy_digest != session.metadata["policy_digest"]
        or projection.policy_version != session.metadata.get("policy_version")
    ):
        raise NoOvernightProjectionError(
            "no-overnight projection/session policy mismatch"
        )
    if checkpoint is not None:
        if checkpoint_digest is None:
            raise NoOvernightProjectionError(
                "no-overnight checkpoint sequence is absent from Journal"
            )
        legacy_checkpoint_matches = bool(
            not checkpoint_has_g5_event
            and checkpoint_legacy_digest is not None
            and checkpoint.digest == checkpoint_legacy_digest
        )
        if checkpoint.digest != checkpoint_digest and not legacy_checkpoint_matches:
            raise NoOvernightProjectionError("no-overnight checkpoint digest mismatch")
    if (
        require_checkpoint
        and _validate_breach_reference
        and projection.breach_id is not None
    ):
        validate_breach_evidence_reference(journal, projection)
    return projection


def write_no_overnight_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
) -> ProjectionCheckpoint:
    projection = rebuild_no_overnight_projection(
        journal,
        session_id=session_id,
        require_checkpoint=False,
    )
    checkpoint = ProjectionCheckpoint(
        session_id=session_id,
        projection_name=NO_OVERNIGHT_PROJECTION_NAME,
        journal_sequence=projection.last_sequence,
        digest=projection.digest,
    )
    journal.save_checkpoint(checkpoint)
    return checkpoint
