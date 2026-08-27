"""Framework-free no-overnight state, evidence, and transition planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig


class NoOvernightPlanningError(ValueError):
    """Inputs cannot prove a safe deterministic transition."""


class NoOvernightState(StrEnum):
    NORMAL = "NORMAL"
    NO_NEW_ENTRY = "NO_NEW_ENTRY"
    CANCEL_ENTRY = "CANCEL_ENTRY"
    FLATTENING = "FLATTENING"
    AGGRESSIVE_EXIT = "AGGRESSIVE_EXIT"
    FINAL_RECONCILIATION = "FINAL_RECONCILIATION"
    CONFIRMED_FLAT = "CONFIRMED_FLAT"
    OVERNIGHT_BREACH = "OVERNIGHT_BREACH"


class NoOvernightWouldAction(StrEnum):
    WOULD_BLOCK_ENTRY = "WOULD_BLOCK_ENTRY"
    WOULD_CANCEL_ENTRY = "WOULD_CANCEL_ENTRY"
    WOULD_EXIT = "WOULD_EXIT"
    WOULD_RECONCILE = "WOULD_RECONCILE"


class FlatProofMode(StrEnum):
    NEVER_EXPOSED = "NEVER_EXPOSED"
    FILL_DERIVED_CLOSE = "FILL_DERIVED_CLOSE"


class ReconciliationStatus(StrEnum):
    MATCH = "MATCH"
    REQUIRED = "RECONCILIATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


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


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_digest_or_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_sha256(value: str, field_name: str) -> str:
    normalized = _require_digest_or_text(value, field_name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


@dataclass(frozen=True)
class ReviewedSessionWindow:
    session_date: date
    timezone: str
    opens_at: datetime
    closes_at: datetime
    calendar_schema_version: str
    calendar_digest: str

    def __post_init__(self) -> None:
        _require_aware(self.opens_at, "opens_at")
        _require_aware(self.closes_at, "closes_at")
        if self.opens_at >= self.closes_at:
            raise ValueError("reviewed session window is invalid")
        zone = ZoneInfo(self.timezone)
        if self.opens_at.astimezone(zone).date() != self.session_date:
            raise ValueError("reviewed session open date mismatch")
        if self.closes_at.astimezone(zone).date() != self.session_date:
            raise ValueError("reviewed session close date mismatch")
        _require_digest_or_text(
            self.calendar_schema_version,
            "calendar_schema_version",
        )
        _require_digest_or_text(self.calendar_digest, "calendar_digest")


@dataclass(frozen=True, order=True)
class ExposureQuantity:
    exposure_id: str
    quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "exposure_id",
            _require_digest_or_text(self.exposure_id, "exposure_id"),
        )
        if type(self.quantity) is not int or self.quantity < 0:
            raise ValueError("quantity must be a non-negative integer")

    def payload(self) -> dict[str, object]:
        return {"exposure_id": self.exposure_id, "quantity": self.quantity}


@dataclass(frozen=True, order=True)
class ManagedExposureEvidence:
    exposure_id: str
    current_quantity: int
    max_quantity_during_session: int
    authoritative_open_fill_quantity: int
    authoritative_close_fill_quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "exposure_id",
            _require_digest_or_text(self.exposure_id, "exposure_id"),
        )
        for field_name in (
            "current_quantity",
            "max_quantity_during_session",
            "authoritative_open_fill_quantity",
            "authoritative_close_fill_quantity",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.current_quantity > self.max_quantity_during_session:
            raise ValueError("current quantity exceeds session maximum")
        if (
            self.authoritative_close_fill_quantity
            > self.authoritative_open_fill_quantity
        ):
            raise ValueError("close fill quantity exceeds open fill quantity")
        if (
            self.authoritative_open_fill_quantity
            - self.authoritative_close_fill_quantity
            != self.current_quantity
        ):
            raise ValueError("managed quantity is not fill-derived")

    def payload(self) -> dict[str, object]:
        return {
            "exposure_id": self.exposure_id,
            "current_quantity": self.current_quantity,
            "max_quantity_during_session": self.max_quantity_during_session,
            "authoritative_open_fill_quantity": (
                self.authoritative_open_fill_quantity
            ),
            "authoritative_close_fill_quantity": (
                self.authoritative_close_fill_quantity
            ),
        }


@dataclass(frozen=True)
class NoOvernightEvidence:
    session_date: date
    managed_exposures: tuple[ManagedExposureEvidence, ...]
    pending_entry_quantity: tuple[ExposureQuantity, ...]
    pending_exit_quantity: tuple[ExposureQuantity, ...]
    unresolved_execution_ids: tuple[str, ...]
    reconciliation_status: ReconciliationStatus
    reconciliation_digest: str
    last_fill_journal_sequence: int
    last_execution_fact_journal_sequence: int
    snapshot_covers_through_journal_sequence: int
    snapshot_journal_sequence: int
    snapshot_source_as_of: datetime
    snapshot_received_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "managed_exposures",
            tuple(sorted(self.managed_exposures)),
        )
        object.__setattr__(
            self,
            "pending_entry_quantity",
            tuple(sorted(self.pending_entry_quantity)),
        )
        object.__setattr__(
            self,
            "pending_exit_quantity",
            tuple(sorted(self.pending_exit_quantity)),
        )
        normalized_ids = tuple(sorted(self.unresolved_execution_ids))
        if any(not value.strip() for value in normalized_ids):
            raise ValueError("unresolved execution identity must not be empty")
        object.__setattr__(self, "unresolved_execution_ids", normalized_ids)
        for field_name in (
            "last_fill_journal_sequence",
            "last_execution_fact_journal_sequence",
            "snapshot_covers_through_journal_sequence",
            "snapshot_journal_sequence",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.last_fill_journal_sequence > self.last_execution_fact_journal_sequence:
            raise ValueError("last fill sequence exceeds last execution fact")
        _require_aware(self.snapshot_source_as_of, "snapshot_source_as_of")
        _require_aware(self.snapshot_received_at, "snapshot_received_at")
        object.__setattr__(
            self,
            "reconciliation_digest",
            _require_sha256(
                self.reconciliation_digest,
                "reconciliation_digest",
            ),
        )

    def payload(self) -> dict[str, object]:
        return {
            "session_date": self.session_date.isoformat(),
            "managed_exposures": [item.payload() for item in self.managed_exposures],
            "pending_entry_quantity": [
                item.payload() for item in self.pending_entry_quantity
            ],
            "pending_exit_quantity": [
                item.payload() for item in self.pending_exit_quantity
            ],
            "unresolved_execution_ids": list(self.unresolved_execution_ids),
            "reconciliation_status": self.reconciliation_status.value,
            "reconciliation_digest": self.reconciliation_digest,
            "last_fill_journal_sequence": self.last_fill_journal_sequence,
            "last_execution_fact_journal_sequence": (
                self.last_execution_fact_journal_sequence
            ),
            "snapshot_covers_through_journal_sequence": (
                self.snapshot_covers_through_journal_sequence
            ),
            "snapshot_journal_sequence": self.snapshot_journal_sequence,
            "snapshot_source_as_of": self.snapshot_source_as_of.isoformat(),
            "snapshot_received_at": self.snapshot_received_at.isoformat(),
        }

    def constructor_values(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True)
class NoOvernightPlan:
    previous_state: NoOvernightState
    state: NoOvernightState
    revision: int
    planned_at: datetime
    would_actions: tuple[NoOvernightWouldAction, ...]
    flat_proof_mode: str | None
    planner_input_digest: str
    digest: str


def _canonical_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def strict_flat_proof(evidence: NoOvernightEvidence) -> FlatProofMode | None:
    if (
        any(item.current_quantity for item in evidence.managed_exposures)
        or any(item.quantity for item in evidence.pending_entry_quantity)
        or any(item.quantity for item in evidence.pending_exit_quantity)
        or evidence.unresolved_execution_ids
        or evidence.reconciliation_status is not ReconciliationStatus.MATCH
        or evidence.snapshot_covers_through_journal_sequence
        < evidence.last_execution_fact_journal_sequence
    ):
        return None
    if not evidence.managed_exposures or all(
        item.max_quantity_during_session == 0
        and item.authoritative_open_fill_quantity == 0
        and item.authoritative_close_fill_quantity == 0
        for item in evidence.managed_exposures
    ):
        return FlatProofMode.NEVER_EXPOSED
    if all(
        item.current_quantity == 0
        and item.max_quantity_during_session > 0
        and item.authoritative_open_fill_quantity
        == item.authoritative_close_fill_quantity
        for item in evidence.managed_exposures
    ):
        return FlatProofMode.FILL_DERIVED_CLOSE
    return None


def _phase_state(
    *,
    config: NoOvernightPolicyConfig,
    now: datetime,
    evidence: NoOvernightEvidence,
) -> tuple[NoOvernightState, FlatProofMode | None]:
    wall_time = now.timetz().replace(tzinfo=None)
    if wall_time < config.no_new_entry_at:
        return NoOvernightState.NORMAL, None
    if wall_time < config.cancel_entry_at:
        return NoOvernightState.NO_NEW_ENTRY, None
    if wall_time < config.flatten_at:
        return NoOvernightState.CANCEL_ENTRY, None
    if wall_time < config.aggressive_exit_at:
        return NoOvernightState.FLATTENING, None
    if wall_time < config.final_reconciliation_at:
        return NoOvernightState.AGGRESSIVE_EXIT, None
    if wall_time < config.reviewed_session_close:
        return NoOvernightState.FINAL_RECONCILIATION, None
    proof = strict_flat_proof(evidence)
    return (
        NoOvernightState.CONFIRMED_FLAT
        if proof is not None
        else NoOvernightState.OVERNIGHT_BREACH,
        proof,
    )


def expected_would_actions(
    state: NoOvernightState,
) -> tuple[NoOvernightWouldAction, ...]:
    if state is NoOvernightState.NORMAL:
        return ()
    if state is NoOvernightState.NO_NEW_ENTRY:
        return (NoOvernightWouldAction.WOULD_BLOCK_ENTRY,)
    if state is NoOvernightState.CANCEL_ENTRY:
        return (
            NoOvernightWouldAction.WOULD_BLOCK_ENTRY,
            NoOvernightWouldAction.WOULD_CANCEL_ENTRY,
        )
    if state in {
        NoOvernightState.FLATTENING,
        NoOvernightState.AGGRESSIVE_EXIT,
    }:
        return (
            NoOvernightWouldAction.WOULD_BLOCK_ENTRY,
            NoOvernightWouldAction.WOULD_EXIT,
        )
    return (
        NoOvernightWouldAction.WOULD_BLOCK_ENTRY,
        NoOvernightWouldAction.WOULD_RECONCILE,
    )


def canonical_transition_digest(
    *,
    previous_state: NoOvernightState,
    state: NoOvernightState,
    revision: int,
    planned_at: datetime,
    would_actions: tuple[NoOvernightWouldAction, ...],
    flat_proof_mode: str | None,
    planner_input_digest: str,
) -> str:
    """Digest every transition field whose value changes replay semantics."""

    return _canonical_digest(
        {
            "previous_state": previous_state.value,
            "state": state.value,
            "revision": revision,
            "planned_at": planned_at.isoformat(),
            "would_actions": [item.value for item in would_actions],
            "flat_proof_mode": flat_proof_mode,
            "planner_input_digest": planner_input_digest,
        }
    )


def plan_no_overnight_transition(
    *,
    config: NoOvernightPolicyConfig,
    window: ReviewedSessionWindow,
    now: datetime,
    current_state: NoOvernightState,
    current_revision: int,
    evidence: NoOvernightEvidence,
    result_superseded: bool = False,
) -> NoOvernightPlan:
    """Plan one monotonic transition. This function has no I/O or side effects."""

    if config.mode is NoOvernightMode.DISABLED:
        raise NoOvernightPlanningError("disabled policy has no transition plan")
    _require_aware(now, "now")
    if type(current_revision) is not int or current_revision < 0:
        raise NoOvernightPlanningError("current revision is invalid")
    if type(result_superseded) is not bool:
        raise NoOvernightPlanningError("result_superseded must be a boolean")
    if window.timezone != config.timezone:
        raise NoOvernightPlanningError("calendar timezone differs from policy timezone")
    zone = ZoneInfo(config.timezone)
    if now.astimezone(zone).replace(tzinfo=None) != now.replace(tzinfo=None):
        raise NoOvernightPlanningError("server clock timezone must equal policy timezone")
    if now.date() != window.session_date or evidence.session_date != window.session_date:
        raise NoOvernightPlanningError("session identity mismatch")
    if now < window.opens_at:
        raise NoOvernightPlanningError("server clock is before reviewed session open")
    expected_open = datetime.combine(
        window.session_date,
        config.market_open,
        zone,
    )
    expected_close = datetime.combine(
        window.session_date,
        config.reviewed_session_close,
        zone,
    )
    if window.opens_at != expected_open or window.closes_at != expected_close:
        raise NoOvernightPlanningError("reviewed session bounds differ from policy")
    if evidence.snapshot_source_as_of > evidence.snapshot_received_at:
        raise NoOvernightPlanningError("snapshot source time is after receipt")
    if evidence.snapshot_received_at > now:
        raise NoOvernightPlanningError("snapshot receipt is in the future")
    if (
        evidence.snapshot_covers_through_journal_sequence
        < evidence.last_execution_fact_journal_sequence
    ):
        raise NoOvernightPlanningError("snapshot fence is behind execution facts")

    target_state, proof = _phase_state(config=config, now=now, evidence=evidence)
    if _STATE_RANK[target_state] < _STATE_RANK[current_state]:
        raise NoOvernightPlanningError("state transition cannot move backward")
    if current_state is NoOvernightState.OVERNIGHT_BREACH:
        target_state = current_state
        proof = None
    if (
        current_state is NoOvernightState.CONFIRMED_FLAT
        and target_state is NoOvernightState.OVERNIGHT_BREACH
    ):
        target_state = NoOvernightState.OVERNIGHT_BREACH

    actions = expected_would_actions(target_state)
    revision = current_revision + int(
        target_state is not current_state or result_superseded
    )
    input_payload = {
        "config": config.canonical_payload(),
        "policy_digest": config.policy_digest,
        "window": {
            "session_date": window.session_date.isoformat(),
            "timezone": window.timezone,
            "opens_at": window.opens_at.isoformat(),
            "closes_at": window.closes_at.isoformat(),
            "calendar_schema_version": window.calendar_schema_version,
            "calendar_digest": window.calendar_digest,
        },
        "now": now.isoformat(),
        "current_state": current_state.value,
        "current_revision": current_revision,
        "result_superseded": result_superseded,
        "evidence": evidence.payload(),
    }
    input_digest = _canonical_digest(input_payload)
    flat_proof_mode = None if proof is None else proof.value
    return NoOvernightPlan(
        previous_state=current_state,
        state=target_state,
        revision=revision,
        planned_at=now,
        would_actions=actions,
        flat_proof_mode=flat_proof_mode,
        planner_input_digest=input_digest,
        digest=canonical_transition_digest(
            previous_state=current_state,
            state=target_state,
            revision=revision,
            planned_at=now,
            would_actions=actions,
            flat_proof_mode=flat_proof_mode,
            planner_input_digest=input_digest,
        ),
    )
