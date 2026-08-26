"""Durable Local Paper Kill Switch contracts and strict Journal replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from trading.journal import (
    JOURNAL_SCHEMA_VERSION,
    JournalAppendResult,
    JournalRecord,
    JournalSession,
)


KILL_SWITCH_CONTRACT_VERSION = "local-paper-kill-switch-control-v1"
KILL_SWITCH_CONTROL_SESSION_ID = "local-paper-global-control-v1"
KILL_SWITCH_CONTROL_MODE = "LOCAL_PAPER_CONTROL"
KILL_SWITCH_IDEMPOTENCY_SCOPE = "local-paper-kill-switch-control-v1"
KILL_SWITCH_ENGAGED_KIND = "local_paper_kill_switch_engaged.v1"
KILL_SWITCH_RESET_KIND = "local_paper_kill_switch_reset.v1"
KILL_SWITCH_EXECUTION_BOUNDARY = "LOCAL_ONLY"
KILL_SWITCH_CONTROL_METADATA = MappingProxyType(
    {
        "contract_version": KILL_SWITCH_CONTRACT_VERSION,
        "control_scope": "GLOBAL_AUTOMATED_LOCAL_PAPER",
        "execution_boundary": KILL_SWITCH_EXECUTION_BOUNDARY,
        "restart_policy": "STRICT_EVENT_REPLAY",
        "writer_model": "SINGLE_PROCESS",
    }
)
_PAYLOAD_FIELDS = frozenset(
    {
        "contract_version",
        "action",
        "operation_id",
        "actor_id",
        "reason",
        "prior_revision",
        "revision",
        "resulting_state",
        "execution_boundary",
    }
)


class KillSwitchAction(StrEnum):
    ENGAGE = "ENGAGE"
    RESET = "RESET"


class KillSwitchControlState(StrEnum):
    DISENGAGED = "DISENGAGED"
    ENGAGED = "ENGAGED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class KillSwitchContractError(ValueError):
    """A control session or event violates the frozen durable contract."""


class KillSwitchReplayError(KillSwitchContractError):
    """The durable event stream cannot be projected with certainty."""


class KillSwitchOperationConflict(KillSwitchContractError):
    """An operation id was reused for different operator semantics."""


@dataclass(frozen=True)
class KillSwitchOperationReceipt:
    action: KillSwitchAction
    operation_id: str
    actor_id: str
    reason: str
    prior_revision: int
    revision: int
    resulting_state: KillSwitchControlState
    occurred_at: datetime
    journal_sequence: int

    def to_dict(self, *, idempotent: bool) -> dict[str, object]:
        return {
            "action": self.action.value,
            "operation_id": self.operation_id,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "prior_revision": self.prior_revision,
            "operation_revision": self.revision,
            "resulting_state": self.resulting_state.value,
            "occurred_at": self.occurred_at.isoformat(),
            "journal_sequence": self.journal_sequence,
            "idempotent": idempotent,
        }


@dataclass(frozen=True)
class KillSwitchProjection:
    control_state: KillSwitchControlState
    revision: int
    reason: str | None
    engaged_at: datetime | None
    last_transition_at: datetime | None
    last_actor_id: str | None
    last_operation_id: str | None
    last_journal_sequence: int
    operation_receipts: Mapping[str, KillSwitchOperationReceipt]

    @property
    def engaged(self) -> bool:
        return self.control_state is KillSwitchControlState.ENGAGED

    @property
    def admission_blocked(self) -> bool:
        return self.control_state is not KillSwitchControlState.DISENGAGED


def kill_switch_control_session(*, started_at: datetime) -> JournalSession:
    """Build the one stable, process-independent control Journal session."""

    return JournalSession(
        session_id=KILL_SWITCH_CONTROL_SESSION_ID,
        started_at=started_at,
        mode=KILL_SWITCH_CONTROL_MODE,
        metadata=dict(KILL_SWITCH_CONTROL_METADATA),
    )


def validate_kill_switch_control_session(session: JournalSession) -> None:
    """Reject a same-id session whose immutable authority metadata drifted."""

    if session.session_id != KILL_SWITCH_CONTROL_SESSION_ID:
        raise KillSwitchReplayError("kill switch control session id is invalid")
    if session.schema_version != JOURNAL_SCHEMA_VERSION:
        raise KillSwitchReplayError(
            "kill switch control session schema version is invalid"
        )
    if session.mode != KILL_SWITCH_CONTROL_MODE:
        raise KillSwitchReplayError("kill switch control session mode is invalid")
    if dict(session.metadata) != dict(KILL_SWITCH_CONTROL_METADATA):
        raise KillSwitchReplayError("kill switch control session metadata conflicts")


def kill_switch_record(
    *,
    action: KillSwitchAction,
    operation_id: str,
    actor_id: str,
    reason: str,
    prior_revision: int,
    occurred_at: datetime,
) -> JournalRecord:
    """Build one canonical transition after retry lookup and state validation."""

    if not isinstance(action, KillSwitchAction):
        raise KillSwitchContractError("kill switch action is invalid")
    normalized_operation_id = _normalized_text(
        operation_id,
        field_name="operation_id",
        max_length=96,
    )
    normalized_actor_id = _normalized_text(
        actor_id,
        field_name="actor_id",
        max_length=128,
    )
    normalized_reason = _normalized_text(
        reason,
        field_name="reason",
        max_length=500,
    )
    _revision(prior_revision, field_name="prior_revision")
    revision = prior_revision + 1
    kind = (
        KILL_SWITCH_ENGAGED_KIND
        if action is KillSwitchAction.ENGAGE
        else KILL_SWITCH_RESET_KIND
    )
    resulting_state = (
        KillSwitchControlState.ENGAGED
        if action is KillSwitchAction.ENGAGE
        else KillSwitchControlState.DISENGAGED
    )
    return JournalRecord(
        record_id=f"local-paper-kill-switch:{normalized_operation_id}",
        session_id=KILL_SWITCH_CONTROL_SESSION_ID,
        kind=kind,
        occurred_at=occurred_at,
        payload={
            "contract_version": KILL_SWITCH_CONTRACT_VERSION,
            "action": action.value,
            "operation_id": normalized_operation_id,
            "actor_id": normalized_actor_id,
            "reason": normalized_reason,
            "prior_revision": prior_revision,
            "revision": revision,
            "resulting_state": resulting_state.value,
            "execution_boundary": KILL_SWITCH_EXECUTION_BOUNDARY,
        },
        idempotency_scope=KILL_SWITCH_IDEMPOTENCY_SCOPE,
        idempotency_key=normalized_operation_id,
    )


def replay_kill_switch(
    session: JournalSession,
    records: Iterable[JournalAppendResult],
) -> KillSwitchProjection:
    """Strictly rebuild the authoritative state from append-order events."""

    validate_kill_switch_control_session(session)
    control_state = KillSwitchControlState.DISENGAGED
    revision = 0
    reason: str | None = None
    engaged_at: datetime | None = None
    last_transition_at: datetime | None = None
    last_actor_id: str | None = None
    last_operation_id: str | None = None
    last_journal_sequence = 0
    receipts: dict[str, KillSwitchOperationReceipt] = {}

    for appended in records:
        if appended.sequence <= last_journal_sequence:
            raise KillSwitchReplayError(
                "kill switch Journal sequence must be strictly increasing"
            )
        record = appended.record
        payload = record.payload
        if record.session_id != KILL_SWITCH_CONTROL_SESSION_ID:
            raise KillSwitchReplayError("kill switch event belongs to another session")
        if record.schema_version != JOURNAL_SCHEMA_VERSION:
            raise KillSwitchReplayError(
                "kill switch event schema version is invalid"
            )
        if record.kind not in {KILL_SWITCH_ENGAGED_KIND, KILL_SWITCH_RESET_KIND}:
            raise KillSwitchReplayError(
                f"unknown kill switch control event: {record.kind}"
            )
        if frozenset(payload) != _PAYLOAD_FIELDS:
            raise KillSwitchReplayError("kill switch event payload fields are invalid")
        if payload.get("contract_version") != KILL_SWITCH_CONTRACT_VERSION:
            raise KillSwitchReplayError("kill switch event contract version is invalid")
        if payload.get("execution_boundary") != KILL_SWITCH_EXECUTION_BOUNDARY:
            raise KillSwitchReplayError(
                "kill switch event authority boundary is invalid"
            )

        try:
            action = KillSwitchAction(str(payload.get("action", "")))
            resulting_state = KillSwitchControlState(
                str(payload.get("resulting_state", ""))
            )
        except ValueError as error:
            raise KillSwitchReplayError("kill switch event state is invalid") from error
        expected_kind = (
            KILL_SWITCH_ENGAGED_KIND
            if action is KillSwitchAction.ENGAGE
            else KILL_SWITCH_RESET_KIND
        )
        expected_result = (
            KillSwitchControlState.ENGAGED
            if action is KillSwitchAction.ENGAGE
            else KillSwitchControlState.DISENGAGED
        )
        if record.kind != expected_kind or resulting_state is not expected_result:
            raise KillSwitchReplayError("kill switch event action does not match kind")

        operation_id = _payload_text(payload, "operation_id", 96)
        actor_id = _payload_text(payload, "actor_id", 128)
        transition_reason = _payload_text(payload, "reason", 500)
        prior_revision = _payload_revision(payload, "prior_revision")
        event_revision = _payload_revision(payload, "revision")
        if prior_revision != revision or event_revision != prior_revision + 1:
            raise KillSwitchReplayError("kill switch revision is not contiguous")
        if (
            action is KillSwitchAction.RESET
            and control_state is not KillSwitchControlState.ENGAGED
        ):
            raise KillSwitchReplayError("kill switch reset has no engaged state")
        if record.record_id != f"local-paper-kill-switch:{operation_id}":
            raise KillSwitchReplayError("kill switch record id is invalid")
        if (
            record.idempotency_scope != KILL_SWITCH_IDEMPOTENCY_SCOPE
            or record.idempotency_key != operation_id
        ):
            raise KillSwitchReplayError("kill switch idempotency identity is invalid")
        if operation_id in receipts:
            raise KillSwitchReplayError("kill switch operation id was journaled twice")

        receipt = KillSwitchOperationReceipt(
            action=action,
            operation_id=operation_id,
            actor_id=actor_id,
            reason=transition_reason,
            prior_revision=prior_revision,
            revision=event_revision,
            resulting_state=resulting_state,
            occurred_at=record.occurred_at,
            journal_sequence=appended.sequence,
        )
        receipts[operation_id] = receipt
        control_state = resulting_state
        revision = event_revision
        reason = transition_reason if action is KillSwitchAction.ENGAGE else None
        engaged_at = record.occurred_at if action is KillSwitchAction.ENGAGE else None
        last_transition_at = record.occurred_at
        last_actor_id = actor_id
        last_operation_id = operation_id
        last_journal_sequence = appended.sequence

    return KillSwitchProjection(
        control_state=control_state,
        revision=revision,
        reason=reason,
        engaged_at=engaged_at,
        last_transition_at=last_transition_at,
        last_actor_id=last_actor_id,
        last_operation_id=last_operation_id,
        last_journal_sequence=last_journal_sequence,
        operation_receipts=MappingProxyType(receipts),
    )


def matching_operation_receipt(
    projection: KillSwitchProjection,
    *,
    action: KillSwitchAction,
    operation_id: str,
    actor_id: str,
    reason: str,
    expected_revision: int | None = None,
) -> KillSwitchOperationReceipt | None:
    """Return a retry receipt or reject conflicting operation-id reuse."""

    normalized_operation_id = _normalized_text(
        operation_id,
        field_name="operation_id",
        max_length=96,
    )
    receipt = projection.operation_receipts.get(normalized_operation_id)
    if receipt is None:
        return None
    normalized_actor_id = _normalized_text(
        actor_id,
        field_name="actor_id",
        max_length=128,
    )
    normalized_reason = _normalized_text(reason, field_name="reason", max_length=500)
    expected = receipt.prior_revision if action is KillSwitchAction.RESET else None
    if (
        receipt.action is not action
        or receipt.actor_id != normalized_actor_id
        or receipt.reason != normalized_reason
        or expected_revision != expected
    ):
        raise KillSwitchOperationConflict(
            "kill switch operation id conflicts with existing request"
        )
    return receipt


def _normalized_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise KillSwitchContractError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise KillSwitchContractError(f"{field_name} must not be empty")
    if len(normalized) > max_length:
        raise KillSwitchContractError(f"{field_name} is too long")
    return normalized


def _revision(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KillSwitchContractError(f"{field_name} must be a non-negative integer")
    return value


def _payload_text(payload: Mapping[str, Any], field_name: str, max_length: int) -> str:
    try:
        persisted = payload[field_name]
        normalized = _normalized_text(
            persisted,
            field_name=field_name,
            max_length=max_length,
        )
        if persisted != normalized:
            raise KillSwitchContractError(f"{field_name} must be canonical")
        return normalized
    except (KeyError, KillSwitchContractError) as error:
        raise KillSwitchReplayError(f"kill switch {field_name} is invalid") from error


def _payload_revision(payload: Mapping[str, Any], field_name: str) -> int:
    try:
        return _revision(payload[field_name], field_name=field_name)
    except (KeyError, KillSwitchContractError) as error:
        raise KillSwitchReplayError(f"kill switch {field_name} is invalid") from error
