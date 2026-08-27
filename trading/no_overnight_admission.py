"""Pure no-overnight admission contracts for exposure-increasing commands."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from trading.exposure import HoldingHorizon
from trading.no_overnight import NoOvernightState
from trading.risk import CommandSide, OrderCommand


EXECUTION_ADMISSION_SCHEMA_VERSION = "no_overnight_execution_admission_v2"


class ExecutionAdmissionStatus(StrEnum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class ExecutionAdmissionReason(StrEnum):
    CUTOFF = "NO_OVERNIGHT_CUTOFF"
    OPEN_BREACH = "NO_OVERNIGHT_OPEN_BREACH"
    RECOVERY_REQUIRED = "NO_OVERNIGHT_RECOVERY_REQUIRED"
    UNCLASSIFIED_CONFLICT = "NO_OVERNIGHT_UNCLASSIFIED_CONFLICT"
    SESSION_CLOSED = "NO_OVERNIGHT_SESSION_CLOSED"
    INSTRUMENT_NOT_TRADABLE = "NO_OVERNIGHT_INSTRUMENT_NOT_TRADABLE"
    BOOK_UNAVAILABLE = "NO_OVERNIGHT_BOOK_UNAVAILABLE"
    EXIT_DEADLINE = "NO_OVERNIGHT_EXIT_DEADLINE"
    GUARD_UNHEALTHY = "NO_OVERNIGHT_GUARD_UNHEALTHY"
    STATE_REVISION_CHANGED = "NO_OVERNIGHT_STATE_REVISION_CHANGED"
    IDENTITY_CONFLICT = "NO_OVERNIGHT_IDENTITY_CONFLICT"


_CUTOFF_STATES = frozenset(
    {
        NoOvernightState.NO_NEW_ENTRY,
        NoOvernightState.CANCEL_ENTRY,
        NoOvernightState.FLATTENING,
        NoOvernightState.AGGRESSIVE_EXIT,
        NoOvernightState.FINAL_RECONCILIATION,
        NoOvernightState.CONFIRMED_FLAT,
        NoOvernightState.OVERNIGHT_BREACH,
    }
)
_RECOVERY_REASONS = frozenset(
    {
        ExecutionAdmissionReason.RECOVERY_REQUIRED,
        ExecutionAdmissionReason.GUARD_UNHEALTHY,
        ExecutionAdmissionReason.STATE_REVISION_CHANGED,
        ExecutionAdmissionReason.IDENTITY_CONFLICT,
    }
)


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_digest(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class ExecutionAdmissionSnapshot:
    """Server-owned facts that can change between proposal and side effect."""

    evaluated_at: datetime
    session_date: date
    state: NoOvernightState
    state_revision: int
    policy_digest: str
    calendar_digest: str
    session_open: bool
    instrument_tradable: bool
    executable_book_ready: bool
    guard_owned: bool
    guard_healthy: bool
    recovery_required: bool = False
    breach_latched: bool = False
    breach_session_date: date | None = None
    breach_revision: int = 0

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if type(self.state_revision) is not int or self.state_revision < 0:
            raise ValueError("state_revision must be a non-negative integer")
        if type(self.breach_revision) is not int or self.breach_revision < 0:
            raise ValueError("breach_revision must be a non-negative integer")
        if self.breach_session_date is not None and type(
            self.breach_session_date
        ) is not date:
            raise ValueError("breach_session_date must be a date or null")
        if self.breach_latched and (
            self.breach_session_date is None or self.breach_revision <= 0
        ):
            raise ValueError("latched breach requires its session and revision")
        if not self.breach_latched and (
            self.breach_session_date is not None or self.breach_revision != 0
        ):
            raise ValueError("unlatched breach cannot carry a breach fence")
        if (
            self.breach_session_date is not None
            and self.breach_session_date > self.session_date
        ):
            raise ValueError("breach_session_date cannot be in the future")
        _require_digest(self.policy_digest, "policy_digest")
        if not self.calendar_digest.strip():
            raise ValueError("calendar_digest must not be empty")
        for field_name in (
            "session_open",
            "instrument_tradable",
            "executable_book_ready",
            "guard_owned",
            "guard_healthy",
            "recovery_required",
            "breach_latched",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"{field_name} must be a boolean")

    @property
    def admission_revision(self) -> str:
        """Immutable revision fence; excludes mutable book/input digests."""

        return _digest(
            {
                "schema_version": EXECUTION_ADMISSION_SCHEMA_VERSION,
                "session_date": self.session_date.isoformat(),
                "state": self.state.value,
                "state_revision": self.state_revision,
                "policy_digest": self.policy_digest,
                "calendar_digest": self.calendar_digest,
                "breach_latched": self.breach_latched,
                "breach_session_date": (
                    None
                    if self.breach_session_date is None
                    else self.breach_session_date.isoformat()
                ),
                "breach_revision": self.breach_revision,
            }
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "evaluated_at": self.evaluated_at.isoformat(),
            "session_date": self.session_date.isoformat(),
            "state": self.state.value,
            "state_revision": self.state_revision,
            "policy_digest": self.policy_digest,
            "calendar_digest": self.calendar_digest,
            "session_open": self.session_open,
            "instrument_tradable": self.instrument_tradable,
            "executable_book_ready": self.executable_book_ready,
            "guard_owned": self.guard_owned,
            "guard_healthy": self.guard_healthy,
            "recovery_required": self.recovery_required,
            "breach_latched": self.breach_latched,
            "breach_session_date": (
                None
                if self.breach_session_date is None
                else self.breach_session_date.isoformat()
            ),
            "breach_revision": self.breach_revision,
            "admission_revision": self.admission_revision,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "ExecutionAdmissionSnapshot":
        required = {
            "evaluated_at",
            "session_date",
            "state",
            "state_revision",
            "policy_digest",
            "calendar_digest",
            "session_open",
            "instrument_tradable",
            "executable_book_ready",
            "guard_owned",
            "guard_healthy",
            "recovery_required",
            "breach_latched",
            "breach_session_date",
            "breach_revision",
            "admission_revision",
        }
        if set(payload) != required:
            raise ValueError("execution admission snapshot fields are invalid")
        string_fields = (
            "evaluated_at",
            "session_date",
            "state",
            "policy_digest",
            "calendar_digest",
            "admission_revision",
        )
        if any(type(payload[field]) is not str for field in string_fields):
            raise ValueError("execution admission snapshot string field is invalid")
        if payload["breach_session_date"] is not None and type(
            payload["breach_session_date"]
        ) is not str:
            raise ValueError("execution admission breach session is invalid")
        boolean_fields = (
            "session_open",
            "instrument_tradable",
            "executable_book_ready",
            "guard_owned",
            "guard_healthy",
            "recovery_required",
            "breach_latched",
        )
        if any(type(payload[field]) is not bool for field in boolean_fields):
            raise ValueError("execution admission snapshot boolean field is invalid")
        if any(
            type(payload[field]) is not int
            for field in ("state_revision", "breach_revision")
        ):
            raise ValueError("execution admission snapshot revision is invalid")
        evaluated_at = datetime.fromisoformat(str(payload["evaluated_at"]))
        snapshot = cls(
            evaluated_at=evaluated_at,
            session_date=date.fromisoformat(str(payload["session_date"])),
            state=NoOvernightState(str(payload["state"])),
            state_revision=int(payload["state_revision"]),
            policy_digest=str(payload["policy_digest"]),
            calendar_digest=str(payload["calendar_digest"]),
            session_open=bool(payload["session_open"]),
            instrument_tradable=bool(payload["instrument_tradable"]),
            executable_book_ready=bool(payload["executable_book_ready"]),
            guard_owned=bool(payload["guard_owned"]),
            guard_healthy=bool(payload["guard_healthy"]),
            recovery_required=bool(payload["recovery_required"]),
            breach_latched=bool(payload["breach_latched"]),
            breach_session_date=(
                None
                if payload["breach_session_date"] is None
                else date.fromisoformat(str(payload["breach_session_date"]))
            ),
            breach_revision=int(payload["breach_revision"]),
        )
        if snapshot.admission_revision != payload["admission_revision"]:
            raise ValueError("execution admission snapshot revision conflicts")
        return snapshot


@dataclass(frozen=True)
class ExecutionAdmissionDecision:
    status: ExecutionAdmissionStatus
    reasons: tuple[ExecutionAdmissionReason, ...]
    admission_revision: str
    snapshot: ExecutionAdmissionSnapshot
    final_check: bool

    def __post_init__(self) -> None:
        _require_digest(self.admission_revision, "admission_revision")
        if self.admission_revision != self.snapshot.admission_revision:
            raise ValueError("admission revision does not match snapshot")
        if self.status is ExecutionAdmissionStatus.APPROVED:
            if self.reasons:
                raise ValueError("approved admission must not have reasons")
        elif not self.reasons:
            raise ValueError("non-approved admission requires reasons")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("admission reasons must not contain duplicates")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": EXECUTION_ADMISSION_SCHEMA_VERSION,
            "status": self.status.value,
            "reasons": [reason.value for reason in self.reasons],
            "admission_revision": self.admission_revision,
            "final_check": self.final_check,
            "snapshot": self.snapshot.to_payload(),
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "ExecutionAdmissionDecision":
        required = {
            "schema_version",
            "status",
            "reasons",
            "admission_revision",
            "final_check",
            "snapshot",
        }
        if set(payload) != required:
            raise ValueError("execution admission decision fields are invalid")
        if payload["schema_version"] != EXECUTION_ADMISSION_SCHEMA_VERSION:
            raise ValueError("execution admission schema is unsupported")
        if type(payload["status"]) is not str:
            raise ValueError("execution admission status is invalid")
        raw_reasons = payload["reasons"]
        if not isinstance(raw_reasons, (list, tuple)) or any(
            type(reason) is not str for reason in raw_reasons
        ):
            raise ValueError("execution admission reasons are invalid")
        if type(payload["admission_revision"]) is not str:
            raise ValueError("execution admission revision is invalid")
        if type(payload["final_check"]) is not bool:
            raise ValueError("execution admission final_check is invalid")
        raw_snapshot = payload["snapshot"]
        if not isinstance(raw_snapshot, Mapping):
            raise ValueError("execution admission snapshot is invalid")
        return cls(
            status=ExecutionAdmissionStatus(str(payload["status"])),
            reasons=tuple(
                ExecutionAdmissionReason(str(reason)) for reason in raw_reasons
            ),
            admission_revision=str(payload["admission_revision"]),
            snapshot=ExecutionAdmissionSnapshot.from_payload(raw_snapshot),
            final_check=bool(payload["final_check"]),
        )


def evaluate_execution_admission(
    *,
    command: OrderCommand,
    config: NoOvernightPolicyConfig,
    snapshot: ExecutionAdmissionSnapshot,
    expected_revision: str | None = None,
    final_check: bool = False,
) -> ExecutionAdmissionDecision:
    """Evaluate central or final admission without I/O or side effects."""

    if final_check and expected_revision is None:
        raise ValueError("final admission requires expected_revision")
    if expected_revision is not None:
        _require_digest(expected_revision, "expected_revision")
    if config.mode is not NoOvernightMode.ENFORCING:
        if command.side is not CommandSide.BUY:
            return ExecutionAdmissionDecision(
                status=ExecutionAdmissionStatus.APPROVED,
                reasons=(),
                admission_revision=snapshot.admission_revision,
                snapshot=snapshot,
                final_check=final_check,
            )
        reasons: list[ExecutionAdmissionReason] = []
        if expected_revision is not None and (
            expected_revision != snapshot.admission_revision
        ):
            reasons.append(ExecutionAdmissionReason.STATE_REVISION_CHANGED)
        if snapshot.recovery_required:
            reasons.append(ExecutionAdmissionReason.RECOVERY_REQUIRED)
        if snapshot.breach_latched:
            reasons.append(ExecutionAdmissionReason.OPEN_BREACH)
        normalized_reasons = tuple(dict.fromkeys(reasons))
        if normalized_reasons:
            status = (
                ExecutionAdmissionStatus.RECOVERY_REQUIRED
                if any(
                    reason in _RECOVERY_REASONS
                    for reason in normalized_reasons
                )
                else ExecutionAdmissionStatus.BLOCKED
            )
            return ExecutionAdmissionDecision(
                status=status,
                reasons=normalized_reasons,
                admission_revision=snapshot.admission_revision,
                snapshot=snapshot,
                final_check=final_check,
            )
        return ExecutionAdmissionDecision(
            status=ExecutionAdmissionStatus.APPROVED,
            reasons=(),
            admission_revision=snapshot.admission_revision,
            snapshot=snapshot,
            final_check=final_check,
        )

    exposure_increasing = command.side is CommandSide.BUY
    if exposure_increasing and expected_revision is not None and (
        expected_revision != snapshot.admission_revision
    ):
        return ExecutionAdmissionDecision(
            status=ExecutionAdmissionStatus.RECOVERY_REQUIRED,
            reasons=(ExecutionAdmissionReason.STATE_REVISION_CHANGED,),
            admission_revision=snapshot.admission_revision,
            snapshot=snapshot,
            final_check=final_check,
        )

    reasons: list[ExecutionAdmissionReason] = []
    exposure = command.exposure
    zone = ZoneInfo(config.timezone)
    if (
        command.requested_at.astimezone(zone).date() != snapshot.session_date
        or snapshot.evaluated_at.astimezone(zone).date() != snapshot.session_date
    ):
        reasons.append(ExecutionAdmissionReason.IDENTITY_CONFLICT)
    if exposure is None or (
        exposure.account_scope_id != config.account_scope_id
        or exposure.policy_family_id != config.policy_family_id
    ):
        reasons.append(ExecutionAdmissionReason.IDENTITY_CONFLICT)
    if snapshot.policy_digest != config.policy_digest:
        reasons.append(ExecutionAdmissionReason.IDENTITY_CONFLICT)
    if (
        command.side is CommandSide.BUY
        and exposure is not None
        and exposure.holding_horizon is not HoldingHorizon.UNCLASSIFIED_LEGACY
        and exposure.entry_session_date != snapshot.session_date
    ):
        reasons.append(ExecutionAdmissionReason.IDENTITY_CONFLICT)
    if exposure_increasing and snapshot.recovery_required:
        reasons.append(ExecutionAdmissionReason.RECOVERY_REQUIRED)
    if exposure_increasing and (
        not snapshot.guard_owned or not snapshot.guard_healthy
    ):
        reasons.append(ExecutionAdmissionReason.GUARD_UNHEALTHY)
    if not snapshot.session_open:
        reasons.append(ExecutionAdmissionReason.SESSION_CLOSED)
    if not snapshot.instrument_tradable:
        reasons.append(ExecutionAdmissionReason.INSTRUMENT_NOT_TRADABLE)
    if not snapshot.executable_book_ready:
        reasons.append(ExecutionAdmissionReason.BOOK_UNAVAILABLE)

    if (
        not exposure_increasing
        and command.execution_reason_code == "NO_OVERNIGHT_EXIT"
    ):
        requested_wall_time = (
            command.requested_at.astimezone(zone).timetz().replace(tzinfo=None)
        )
        evaluated_wall_time = (
            snapshot.evaluated_at.astimezone(zone).timetz().replace(tzinfo=None)
        )
        if (
            requested_wall_time >= config.final_reconciliation_at
            or evaluated_wall_time >= config.final_reconciliation_at
        ):
            reasons.append(ExecutionAdmissionReason.EXIT_DEADLINE)

    if exposure_increasing:
        if (
            snapshot.breach_latched
            or snapshot.state is NoOvernightState.OVERNIGHT_BREACH
        ):
            reasons.append(ExecutionAdmissionReason.OPEN_BREACH)
        if exposure is not None:
            if exposure.holding_horizon is HoldingHorizon.UNCLASSIFIED_LEGACY:
                reasons.append(ExecutionAdmissionReason.UNCLASSIFIED_CONFLICT)
            if exposure.no_overnight_managed:
                requested_wall_time = (
                    command.requested_at.astimezone(zone).timetz().replace(tzinfo=None)
                )
                evaluated_wall_time = (
                    snapshot.evaluated_at.astimezone(zone).timetz().replace(tzinfo=None)
                )
                if (
                    requested_wall_time >= config.no_new_entry_at
                    or evaluated_wall_time >= config.no_new_entry_at
                    or snapshot.state in _CUTOFF_STATES
                ):
                    reasons.append(ExecutionAdmissionReason.CUTOFF)

    normalized_reasons = tuple(dict.fromkeys(reasons))
    if not normalized_reasons:
        status = ExecutionAdmissionStatus.APPROVED
    elif any(reason in _RECOVERY_REASONS for reason in normalized_reasons):
        status = ExecutionAdmissionStatus.RECOVERY_REQUIRED
    else:
        status = ExecutionAdmissionStatus.BLOCKED
    return ExecutionAdmissionDecision(
        status=status,
        reasons=normalized_reasons,
        admission_revision=snapshot.admission_revision,
        snapshot=snapshot,
        final_check=final_check,
    )
