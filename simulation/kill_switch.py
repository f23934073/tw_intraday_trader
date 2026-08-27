"""Journal-first Local Paper Kill Switch application service."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Any, TypeVar

from runtime.clock import Clock
from trading.journal import JournalConflictError, JournalRepository, JournalSession
from trading.kill_switch import (
    KILL_SWITCH_CONTROL_SESSION_ID,
    KillSwitchAction,
    KillSwitchContractError,
    KillSwitchControlState,
    KillSwitchOperationConflict,
    KillSwitchOperationReceipt,
    KillSwitchProjection,
    kill_switch_control_session,
    kill_switch_record,
    matching_operation_receipt,
    replay_kill_switch,
)


_ResultT = TypeVar("_ResultT")


class KillSwitchDurability(StrEnum):
    POSTGRESQL = "POSTGRESQL"
    EPHEMERAL_MEMORY = "EPHEMERAL_MEMORY"


class KillSwitchStateConflict(RuntimeError):
    """The requested transition does not match authoritative control state."""


class KillSwitchAdmissionBlocked(RuntimeError):
    """Automated Local Paper work is blocked by durable control state."""


class KillSwitchPersistenceUnavailable(RuntimeError):
    """A control transition or replay could not be durably verified."""


class DurableLocalPaperKillSwitch:
    """Serialize control transitions and automated-intent final admission."""

    def __init__(
        self,
        *,
        journal: JournalRepository,
        clock: Clock,
        durability: KillSwitchDurability,
        session: JournalSession | None,
        projection: KillSwitchProjection | None,
        recovered: bool,
        recovery_error: str | None = None,
    ) -> None:
        self._journal = journal
        self._clock = clock
        self._durability = durability
        self._session = session
        self._projection = projection
        self._recovered = recovered
        self._recovery_error = recovery_error
        self._lock = RLock()

    @classmethod
    def recover(
        cls,
        *,
        journal: JournalRepository,
        clock: Clock,
        durability: KillSwitchDurability = KillSwitchDurability.EPHEMERAL_MEMORY,
    ) -> DurableLocalPaperKillSwitch:
        """Open the stable control session and fail closed on any uncertainty."""

        session: JournalSession | None = None
        try:
            session = journal.session(KILL_SWITCH_CONTROL_SESSION_ID)
            recovered = session is not None
            if session is None:
                session = kill_switch_control_session(started_at=clock.now())
            journal.start_session(session)
            projection = replay_kill_switch(
                session,
                journal.records(KILL_SWITCH_CONTROL_SESSION_ID),
            )
        except Exception as error:
            return cls(
                journal=journal,
                clock=clock,
                durability=durability,
                session=session,
                projection=None,
                recovered=False,
                recovery_error=_recovery_error(error),
            )
        return cls(
            journal=journal,
            clock=clock,
            durability=durability,
            session=session,
            projection=projection,
            recovered=recovered,
        )

    @property
    def engaged(self) -> bool:
        """Compatibility view: recovery uncertainty blocks like an engagement."""

        with self._lock:
            return self._projection is None or self._projection.admission_blocked

    @property
    def control_state(self) -> KillSwitchControlState:
        with self._lock:
            if self._projection is None:
                return KillSwitchControlState.RECOVERY_REQUIRED
            return self._projection.control_state

    def is_bound_to(
        self,
        *,
        journal: JournalRepository,
        clock: Clock,
        durability: KillSwitchDurability,
    ) -> bool:
        """Validate an in-process handoff without exposing mutable internals."""

        with self._lock:
            return (
                self._journal is journal
                and self._clock is clock
                and self._durability is durability
            )

    def engage(
        self,
        *,
        actor_id: str,
        operation_id: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._lock:
            projection = self._require_projection()
            existing = matching_operation_receipt(
                projection,
                action=KillSwitchAction.ENGAGE,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
            )
            if existing is not None:
                return self._transition_result(existing, idempotent=True)
            return self._append_transition(
                action=KillSwitchAction.ENGAGE,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
                prior_revision=projection.revision,
            )

    def reset(
        self,
        *,
        actor_id: str,
        operation_id: str,
        reason: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise KillSwitchContractError(
                "expected_revision must be a non-negative integer"
            )
        with self._lock:
            projection = self._require_projection()
            existing = matching_operation_receipt(
                projection,
                action=KillSwitchAction.RESET,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
                expected_revision=expected_revision,
            )
            if existing is not None:
                return self._transition_result(existing, idempotent=True)
            if projection.control_state is not KillSwitchControlState.ENGAGED:
                raise KillSwitchStateConflict("kill switch is not engaged")
            if expected_revision != projection.revision:
                raise KillSwitchStateConflict(
                    "kill switch reset revision is stale"
                )
            return self._append_transition(
                action=KillSwitchAction.RESET,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
                prior_revision=projection.revision,
            )

    def assert_start_allowed(self) -> None:
        with self._lock:
            self._assert_admission_allowed()

    def admit_automated_intent(
        self,
        operation: Callable[[], _ResultT],
    ) -> _ResultT:
        """Linearize final admission before intent Journal and command routing."""

        with self._lock:
            self._assert_admission_allowed()
            return operation()

    def status(self) -> dict[str, object]:
        with self._lock:
            projection = self._projection
            control_state = (
                projection.control_state
                if projection is not None
                else KillSwitchControlState.RECOVERY_REQUIRED
            )
            return {
                "control_state": control_state.value,
                "engaged": control_state is not KillSwitchControlState.DISENGAGED,
                "revision": projection.revision if projection is not None else None,
                "reason": projection.reason if projection is not None else None,
                "engaged_at": _iso(
                    projection.engaged_at if projection is not None else None
                ),
                "last_transition_at": _iso(
                    projection.last_transition_at if projection is not None else None
                ),
                "last_actor_id": (
                    projection.last_actor_id if projection is not None else None
                ),
                "last_operation_id": (
                    projection.last_operation_id if projection is not None else None
                ),
                "durability": self._durability.value,
                "restart_safe": self._durability is KillSwitchDurability.POSTGRESQL,
                "recovered": self._recovered,
                "recovery_error": self._recovery_error,
            }

    def _append_transition(
        self,
        *,
        action: KillSwitchAction,
        operation_id: str,
        actor_id: str,
        reason: str,
        prior_revision: int,
    ) -> dict[str, Any]:
        record = kill_switch_record(
            action=action,
            operation_id=operation_id,
            actor_id=actor_id,
            reason=reason,
            prior_revision=prior_revision,
            occurred_at=self._clock.now(),
        )
        try:
            appended = self._journal.append(record)
        except JournalConflictError:
            return self._resolve_append_conflict(
                action=action,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
                expected_revision=(
                    prior_revision if action is KillSwitchAction.RESET else None
                ),
            )
        except Exception as error:
            self._enter_recovery_required(error)
            raise KillSwitchPersistenceUnavailable(
                "kill switch Journal append failed"
            ) from error

        try:
            projection = self._replay_current()
            receipt = projection.operation_receipts[operation_id.strip()]
        except Exception as error:
            self._enter_recovery_required(error)
            raise KillSwitchPersistenceUnavailable(
                "kill switch transition could not be verified"
            ) from error
        self._projection = projection
        self._recovery_error = None
        return self._transition_result(receipt, idempotent=appended.idempotent)

    def _resolve_append_conflict(
        self,
        *,
        action: KillSwitchAction,
        operation_id: str,
        actor_id: str,
        reason: str,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        try:
            projection = self._replay_current()
            self._projection = projection
            self._recovery_error = None
            receipt = matching_operation_receipt(
                projection,
                action=action,
                operation_id=operation_id,
                actor_id=actor_id,
                reason=reason,
                expected_revision=expected_revision,
            )
        except KillSwitchOperationConflict:
            raise
        except Exception as error:
            self._enter_recovery_required(error)
            raise KillSwitchPersistenceUnavailable(
                "kill switch Journal conflict could not be resolved"
            ) from error
        if receipt is None:
            error = RuntimeError("conflicting kill switch record is absent")
            self._enter_recovery_required(error)
            raise KillSwitchPersistenceUnavailable(
                "kill switch Journal conflict could not be resolved"
            ) from error
        return self._transition_result(receipt, idempotent=True)

    def _replay_current(self) -> KillSwitchProjection:
        if self._session is None:
            raise RuntimeError("kill switch control session is unavailable")
        return replay_kill_switch(
            self._session,
            self._journal.records(KILL_SWITCH_CONTROL_SESSION_ID),
        )

    def _require_projection(self) -> KillSwitchProjection:
        if self._projection is None:
            raise KillSwitchPersistenceUnavailable(
                "kill switch recovery is required"
            )
        return self._projection

    def _assert_admission_allowed(self) -> None:
        projection = self._require_projection()
        if projection.control_state is KillSwitchControlState.ENGAGED:
            raise KillSwitchAdmissionBlocked(
                "Local Paper kill switch is engaged"
            )

    def _enter_recovery_required(self, error: Exception) -> None:
        self._projection = None
        self._recovered = False
        self._recovery_error = _recovery_error(error)

    def _transition_result(
        self,
        receipt: KillSwitchOperationReceipt,
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "kill_switch": self.status(),
            "operation": receipt.to_dict(idempotent=idempotent),
        }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _recovery_error(error: Exception) -> str:
    return f"{type(error).__name__}: kill switch Journal recovery failed"
