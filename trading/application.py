"""Journal-first command application boundary for future local-paper routing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from trading.canonical_values import (
    canonical_decimal_string,
    require_aware_datetime_string,
    require_canonical_decimal_string,
    require_json_fields,
    require_json_integer,
    require_json_string,
    require_optional_json_string,
)
from trading.exposure import (
    ExecutionReasonCategory,
    ExposureIdentity,
    PositionAction,
)
from trading.journal import JournalAppendResult, JournalRecord, JournalRepository
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionStatus,
)
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskDecision,
    RiskDecisionStatus,
    RiskGate,
    RiskSnapshot,
)


_T = TypeVar("_T")


class ApplicationStatus(StrEnum):
    APPLIED = "APPLIED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    HANDLER_FAILED = "HANDLER_FAILED"


@dataclass(frozen=True)
class ProposedOrderCommand:
    """Normalized order proposal that has not passed Hard Risk admission."""

    command: OrderCommand

    @property
    def command_digest(self) -> str:
        return _canonical_digest(_order_command_payload(self.command))


@dataclass(frozen=True)
class ApprovedOrderCommand:
    """The only command type an execution adapter is allowed to receive."""

    proposal: ProposedOrderCommand
    risk_decision: RiskDecision
    risk_snapshot_digest: str
    effective_policy_digest: str
    approved_at: datetime

    def __post_init__(self) -> None:
        if self.risk_decision.status is not RiskDecisionStatus.APPROVED:
            raise ValueError("只有 Hard Risk APPROVED 的 command 可以進入 adapter")
        for value, field_name in (
            (self.risk_snapshot_digest, "risk_snapshot_digest"),
            (self.effective_policy_digest, "effective_policy_digest"),
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")

    @property
    def command(self) -> OrderCommand:
        return self.proposal.command

    @property
    def risk_decision_digest(self) -> str:
        return _risk_decision_digest(
            proposal=self.proposal,
            risk_decision=self.risk_decision,
            risk_snapshot_digest=self.risk_snapshot_digest,
            effective_policy_digest=self.effective_policy_digest,
        )

    @property
    def risk_decision_id(self) -> str:
        return f"risk-decision-v1:{self.risk_decision_digest}"

    @property
    def approved_command_digest(self) -> str:
        return _canonical_digest(
            {
                "proposed_command_digest": self.proposal.command_digest,
                "risk_decision_digest": self.risk_decision_digest,
                "approved_at": self.approved_at.isoformat(),
            }
        )


class LocalPaperCommandHandler(Protocol):
    """Local-only side-effect port that accepts approved commands only."""

    def submit(self, command: ApprovedOrderCommand) -> Mapping[str, Any]:
        """Apply an already-approved local-paper command."""


class MutationBoundaryCommandHandler(LocalPaperCommandHandler, Protocol):
    """Apply only after final admission at the handler mutation boundary."""

    def submit_with_mutation_admission(
        self,
        command: ApprovedOrderCommand,
        *,
        admission: Callable[[datetime], ExecutionAdmissionDecision],
    ) -> Mapping[str, Any]:
        """Evaluate admission and mutate under one handler-owned boundary."""


class CommandOutcomeRecorder(Protocol):
    """Maps an acknowledged handler result to append-only evidence records."""

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, Any],
    ) -> tuple[JournalRecord, ...]:
        """Return records to append after a successful handler acknowledgement."""


class FinalExecutionAdmissionReader(Protocol):
    """Re-read server-owned execution facts immediately before the handler."""

    def read(
        self,
        command: OrderCommand,
        *,
        expected_revision: str,
    ) -> ExecutionAdmissionDecision:
        """Return the final fail-closed decision for one approved command."""

    def read_at(
        self,
        command: OrderCommand,
        *,
        expected_revision: str,
        evaluated_at: datetime,
    ) -> ExecutionAdmissionDecision:
        """Evaluate using the handler's immutable mutation timestamp."""

    def execute_under_admission_fence(self, operation: Callable[[], _T]) -> _T:
        """Keep guard ownership and state revision stable through mutation."""


class _MutationAdmissionBlocked(Exception):
    def __init__(
        self,
        decision: ExecutionAdmissionDecision | None,
        *,
        recovery_required: bool = False,
    ) -> None:
        super().__init__("order mutation admission blocked")
        self.decision = decision
        self.recovery_required = recovery_required


@dataclass(frozen=True)
class CommandApplicationResult:
    status: ApplicationStatus
    risk: RiskDecision
    journal_sequence: int
    handler_result: Mapping[str, Any] | None = None
    outcome_journal_sequences: tuple[int, ...] = ()
    execution_admission: ExecutionAdmissionDecision | None = None


def _risk_snapshot_payload(snapshot: RiskSnapshot) -> dict[str, object]:
    """Return stable Journal evidence without serializing money as floats."""

    return {
        "data_health_state": snapshot.data_health_state,
        "market_open": snapshot.market_open,
        "instrument_tradable": snapshot.instrument_tradable,
        "available_cash": canonical_decimal_string(snapshot.available_cash),
        "current_position_shares": snapshot.current_position_shares,
        "pending_buy_shares": snapshot.pending_buy_shares,
        "pending_sell_shares": snapshot.pending_sell_shares,
        "daily_realized_pnl": canonical_decimal_string(
            snapshot.daily_realized_pnl
        ),
        "daily_filled_buy_notional": canonical_decimal_string(
            snapshot.daily_filled_buy_notional
        ),
        "pending_buy_notional": canonical_decimal_string(
            snapshot.pending_buy_notional
        ),
        "daily_loss": (
            canonical_decimal_string(snapshot.daily_loss)
            if snapshot.daily_loss is not None
            else None
        ),
        "same_side_pending_order": snapshot.same_side_pending_order,
        "book_age_seconds": snapshot.book_age_seconds,
    }


def _order_command_payload(command: OrderCommand) -> dict[str, object]:
    payload: dict[str, object] = {
        "command_id": command.command_id,
        "session_id": command.session_id,
        "origin": command.origin.value,
        "symbol": command.symbol,
        "side": command.side.value,
        "quantity_shares": command.quantity_shares,
        "limit_price": canonical_decimal_string(command.limit_price),
        "idempotency_key": command.idempotency_key,
        "requested_at": command.requested_at.isoformat(),
        "strategy_id": command.strategy_id,
        "strategy_version": command.strategy_version,
        "attempt": command.attempt,
        "predecessor_order_id": command.predecessor_order_id,
    }
    if command.exposure is not None:
        payload.update(
            {
                "exposure_identity": command.exposure.to_payload(),
                "position_action": command.position_action.value,
                "target_exposure_id": command.target_exposure_id,
                "execution_reason_category": (
                    command.execution_reason_category.value
                ),
                "execution_reason_code": command.execution_reason_code,
            }
        )
    return payload


def order_command_from_record(record: JournalRecord) -> OrderCommand:
    """Read a v1/v2 command while keeping v2 identity fields strict."""

    if record.kind not in {"order_command.v1", "order_command.v2"}:
        raise ValueError("record is not an order command")
    payload = record.payload
    if record.kind == "order_command.v1":
        return OrderCommand(
            command_id=str(payload["command_id"]),
            session_id=record.session_id,
            origin=CommandOrigin(str(payload["origin"])),
            symbol=str(payload["symbol"]),
            side=CommandSide(str(payload["side"])),
            quantity_shares=int(payload["quantity_shares"]),
            limit_price=Decimal(str(payload["limit_price"])),
            idempotency_key=str(payload["idempotency_key"]),
            requested_at=(
                datetime.fromisoformat(str(payload["requested_at"]))
                if payload.get("requested_at") is not None
                else record.occurred_at
            ),
            strategy_id=(
                str(payload["strategy_id"])
                if payload.get("strategy_id") is not None
                else None
            ),
            strategy_version=(
                str(payload["strategy_version"])
                if payload.get("strategy_version") is not None
                else None
            ),
            attempt=int(payload.get("attempt") or 1),
            predecessor_order_id=(
                str(payload["predecessor_order_id"])
                if payload.get("predecessor_order_id") is not None
                else None
            ),
        )

    required = frozenset(
        {
            "command_id",
            "session_id",
            "origin",
            "symbol",
            "side",
            "quantity_shares",
            "limit_price",
            "idempotency_key",
            "requested_at",
            "strategy_id",
            "strategy_version",
            "attempt",
            "predecessor_order_id",
            "exposure_identity",
            "position_action",
            "target_exposure_id",
            "execution_reason_category",
            "execution_reason_code",
        }
    )
    allowed = required | frozenset(
        {
            "risk_status",
            "risk_reasons",
            "risk_policy_version",
            "risk_snapshot",
            "proposed_command_digest",
            "risk_snapshot_digest",
            "effective_risk_policy",
            "effective_risk_policy_digest",
            "risk_decision_id",
            "risk_decision_digest",
            "approved_command_digest",
            "command_state",
            "no_overnight_admission",
        }
    )
    require_json_fields(
        payload,
        required=required,
        allowed=allowed,
        field_name="v2 order command",
    )
    payload_session_id = require_json_string(payload["session_id"], "session_id")
    if payload_session_id != record.session_id:
        raise ValueError("session_id must match Journal record")
    command_id = require_json_string(payload["command_id"], "command_id")
    origin = CommandOrigin(require_json_string(payload["origin"], "origin"))
    symbol = require_json_string(payload["symbol"], "symbol")
    side = CommandSide(require_json_string(payload["side"], "side"))
    quantity_shares = require_json_integer(
        payload["quantity_shares"], "quantity_shares"
    )
    if quantity_shares <= 0:
        raise ValueError("quantity_shares must be positive")
    limit_price = require_canonical_decimal_string(
        payload["limit_price"],
        "limit_price",
        positive=True,
    )
    idempotency_key = require_json_string(
        payload["idempotency_key"], "idempotency_key"
    )
    requested_at = require_aware_datetime_string(
        payload["requested_at"], "requested_at"
    )
    strategy_id = require_optional_json_string(
        payload["strategy_id"], "strategy_id"
    )
    strategy_version = require_optional_json_string(
        payload["strategy_version"], "strategy_version"
    )
    attempt = require_json_integer(payload["attempt"], "attempt")
    predecessor_order_id = require_optional_json_string(
        payload["predecessor_order_id"], "predecessor_order_id"
    )
    exposure = None
    position_action = None
    target_exposure_id = None
    execution_reason_category = None
    execution_reason_code = None
    raw_exposure = payload["exposure_identity"]
    if not isinstance(raw_exposure, Mapping):
        raise ValueError("exposure_identity must be an object")
    exposure = ExposureIdentity.from_payload(raw_exposure)
    position_action = PositionAction(
        require_json_string(payload["position_action"], "position_action")
    )
    target_exposure_id = require_optional_json_string(
        payload["target_exposure_id"], "target_exposure_id"
    )
    execution_reason_category = ExecutionReasonCategory(
        require_json_string(
            payload["execution_reason_category"],
            "execution_reason_category",
        )
    )
    execution_reason_code = require_json_string(
        payload["execution_reason_code"], "execution_reason_code"
    )
    raw_admission = payload.get("no_overnight_admission")
    if raw_admission is not None:
        if not isinstance(raw_admission, Mapping):
            raise ValueError("no_overnight_admission must be an object or null")
        admission = ExecutionAdmissionDecision.from_payload(raw_admission)
        if admission.final_check:
            raise ValueError("order command cannot contain final admission")
    return OrderCommand(
        command_id=command_id,
        session_id=payload_session_id,
        origin=origin,
        symbol=symbol,
        side=side,
        quantity_shares=quantity_shares,
        limit_price=limit_price,
        idempotency_key=idempotency_key,
        requested_at=requested_at,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        attempt=attempt,
        predecessor_order_id=predecessor_order_id,
        exposure=exposure,
        position_action=position_action,
        target_exposure_id=target_exposure_id,
        execution_reason_category=execution_reason_category,
        execution_reason_code=execution_reason_code,
    )


def _canonical_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _risk_decision_digest(
    *,
    proposal: ProposedOrderCommand,
    risk_decision: RiskDecision,
    risk_snapshot_digest: str,
    effective_policy_digest: str,
) -> str:
    return _canonical_digest(
        {
            "proposed_command_digest": proposal.command_digest,
            "risk_snapshot_digest": risk_snapshot_digest,
            "effective_policy_digest": effective_policy_digest,
            "status": risk_decision.status.value,
            "reasons": [reason.value for reason in risk_decision.reasons],
            "approved_quantity_shares": risk_decision.approved_quantity_shares,
            "policy_version": risk_decision.policy_version,
            "evaluated_at": risk_decision.evaluated_at.isoformat(),
        }
    )


class OrderApplicationService:
    """Records a command decision before it can reach a side-effect adapter."""

    def __init__(
        self,
        *,
        journal: JournalRepository,
        risk_gate: RiskGate,
        handler: LocalPaperCommandHandler,
        outcome_recorder: CommandOutcomeRecorder | None = None,
        final_admission_reader: FinalExecutionAdmissionReader | None = None,
    ) -> None:
        self._journal = journal
        self._risk_gate = risk_gate
        self._handler = handler
        self._outcome_recorder = outcome_recorder
        self._final_admission_reader = final_admission_reader

    def apply(
        self,
        command: OrderCommand,
        snapshot: RiskSnapshot,
        *,
        evaluated_at: datetime,
        execution_admission: ExecutionAdmissionDecision | None = None,
    ) -> CommandApplicationResult:
        proposed = ProposedOrderCommand(command)
        risk_snapshot_payload = _risk_snapshot_payload(snapshot)
        risk_snapshot_digest = _canonical_digest(risk_snapshot_payload)
        effective_policy_digest = self._risk_gate.policy_digest
        effective_policy_payload = self._risk_gate.policy_payload
        risk = self._risk_gate.evaluate(
            proposed.command,
            snapshot,
            evaluated_at=evaluated_at,
        )
        risk_decision_digest = _risk_decision_digest(
            proposal=proposed,
            risk_decision=risk,
            risk_snapshot_digest=risk_snapshot_digest,
            effective_policy_digest=effective_policy_digest,
        )
        approved = (
            ApprovedOrderCommand(
                proposal=proposed,
                risk_decision=risk,
                risk_snapshot_digest=risk_snapshot_digest,
                effective_policy_digest=effective_policy_digest,
                approved_at=evaluated_at,
            )
            if risk.status is RiskDecisionStatus.APPROVED
            else None
        )
        command_payload = _order_command_payload(command)
        appended = self._journal.append(
            JournalRecord(
                record_id=f"command:{command.command_id}",
                session_id=command.session_id,
                kind=(
                    "order_command.v2"
                    if command.exposure is not None
                    else "order_command.v1"
                ),
                occurred_at=evaluated_at,
                payload={
                    **command_payload,
                    "risk_status": risk.status.value,
                    "risk_reasons": [reason.value for reason in risk.reasons],
                    "risk_policy_version": risk.policy_version,
                    "risk_snapshot": risk_snapshot_payload,
                    "proposed_command_digest": proposed.command_digest,
                    "risk_snapshot_digest": risk_snapshot_digest,
                    "effective_risk_policy": effective_policy_payload,
                    "effective_risk_policy_digest": effective_policy_digest,
                    "risk_decision_id": f"risk-decision-v1:{risk_decision_digest}",
                    "risk_decision_digest": risk_decision_digest,
                    "approved_command_digest": (
                        approved.approved_command_digest
                        if approved is not None
                        else None
                    ),
                    "command_state": "PROPOSED",
                    "no_overnight_admission": (
                        execution_admission.to_payload()
                        if execution_admission is not None
                        else None
                    ),
                },
                idempotency_scope=f"{command.session_id}:order_command",
                idempotency_key=command.idempotency_key,
            )
        )
        if appended.idempotent:
            return CommandApplicationResult(
                status=ApplicationStatus.RECOVERY_REQUIRED,
                risk=risk,
                journal_sequence=appended.sequence,
                execution_admission=execution_admission,
            )
        if risk.status is RiskDecisionStatus.BLOCKED:
            return CommandApplicationResult(
                status=ApplicationStatus.BLOCKED,
                risk=risk,
                journal_sequence=appended.sequence,
                execution_admission=execution_admission,
            )
        if risk.status is RiskDecisionStatus.REJECTED:
            return CommandApplicationResult(
                status=ApplicationStatus.REJECTED,
                risk=risk,
                journal_sequence=appended.sequence,
                execution_admission=execution_admission,
            )

        if execution_admission is not None and (
            execution_admission.status is not ExecutionAdmissionStatus.APPROVED
        ):
            return CommandApplicationResult(
                status=(
                    ApplicationStatus.RECOVERY_REQUIRED
                    if execution_admission.status
                    is ExecutionAdmissionStatus.RECOVERY_REQUIRED
                    else ApplicationStatus.BLOCKED
                ),
                risk=risk,
                journal_sequence=appended.sequence,
                execution_admission=execution_admission,
            )

        assert approved is not None
        handler_result: Mapping[str, Any]
        if self._final_admission_reader is not None:
            if execution_admission is None:
                self._append_final_admission_failure(
                    command,
                    occurred_at=evaluated_at,
                    error_type="MISSING_INITIAL_ADMISSION",
                )
                return CommandApplicationResult(
                    status=ApplicationStatus.RECOVERY_REQUIRED,
                    risk=risk,
                    journal_sequence=appended.sequence,
                )
            initial_admission = execution_admission
            try:
                preflight_admission = self._final_admission_reader.read(
                    command,
                    expected_revision=initial_admission.admission_revision,
                )
                self._validate_final_admission(
                    initial=initial_admission,
                    final=preflight_admission,
                )
            except Exception as error:
                self._append_final_admission_failure(
                    command,
                    occurred_at=evaluated_at,
                    error_type=type(error).__name__,
                )
                return CommandApplicationResult(
                    status=ApplicationStatus.RECOVERY_REQUIRED,
                    risk=risk,
                    journal_sequence=appended.sequence,
                    execution_admission=initial_admission,
                )
            if preflight_admission.status is not ExecutionAdmissionStatus.APPROVED:
                final_record = self._append_final_admission(
                    command,
                    initial=initial_admission,
                    final=preflight_admission,
                )
                return CommandApplicationResult(
                    status=(
                        ApplicationStatus.RECOVERY_REQUIRED
                        if final_record.idempotent
                        or preflight_admission.status
                        is ExecutionAdmissionStatus.RECOVERY_REQUIRED
                        else ApplicationStatus.BLOCKED
                    ),
                    risk=risk,
                    journal_sequence=appended.sequence,
                    execution_admission=preflight_admission,
                )

            boundary_submit = getattr(
                self._handler,
                "submit_with_mutation_admission",
                None,
            )
            boundary_read = getattr(self._final_admission_reader, "read_at", None)
            boundary_execute = getattr(
                self._final_admission_reader,
                "execute_under_admission_fence",
                None,
            )
            if (
                not callable(boundary_submit)
                or not callable(boundary_read)
                or not callable(boundary_execute)
            ):
                self._append_final_admission_failure(
                    command,
                    occurred_at=evaluated_at,
                    error_type="MUTATION_BOUNDARY_UNAVAILABLE",
                )
                return CommandApplicationResult(
                    status=ApplicationStatus.RECOVERY_REQUIRED,
                    risk=risk,
                    journal_sequence=appended.sequence,
                    execution_admission=initial_admission,
                )

            boundary_admission: ExecutionAdmissionDecision | None = None

            def admit_at(mutation_at: datetime) -> ExecutionAdmissionDecision:
                nonlocal boundary_admission
                try:
                    decision = boundary_read(
                        command,
                        expected_revision=initial_admission.admission_revision,
                        evaluated_at=mutation_at,
                    )
                    self._validate_final_admission(
                        initial=initial_admission,
                        final=decision,
                    )
                except Exception as error:
                    self._append_final_admission_failure(
                        command,
                        occurred_at=mutation_at,
                        error_type=type(error).__name__,
                    )
                    raise _MutationAdmissionBlocked(
                        None,
                        recovery_required=True,
                    ) from error
                boundary_admission = decision
                final_record = self._append_final_admission(
                    command,
                    initial=initial_admission,
                    final=decision,
                )
                if final_record.idempotent:
                    raise _MutationAdmissionBlocked(
                        decision,
                        recovery_required=True,
                    )
                if decision.status is not ExecutionAdmissionStatus.APPROVED:
                    raise _MutationAdmissionBlocked(decision)
                try:
                    confirmed = boundary_read(
                        command,
                        expected_revision=initial_admission.admission_revision,
                        evaluated_at=mutation_at,
                    )
                    self._validate_final_admission(
                        initial=initial_admission,
                        final=confirmed,
                    )
                except Exception as error:
                    self._append_final_admission_failure(
                        command,
                        occurred_at=mutation_at,
                        error_type=type(error).__name__,
                    )
                    raise _MutationAdmissionBlocked(
                        None,
                        recovery_required=True,
                    ) from error
                if confirmed.status is not ExecutionAdmissionStatus.APPROVED:
                    boundary_admission = confirmed
                    self._append_final_admission_failure(
                        command,
                        occurred_at=mutation_at,
                        error_type="POST_FINAL_ADMISSION_FENCE_CHANGED",
                    )
                    raise _MutationAdmissionBlocked(
                        confirmed,
                        recovery_required=True,
                    )
                return decision

            try:
                handler_result = boundary_execute(
                    lambda: boundary_submit(
                        approved,
                        admission=admit_at,
                    )
                )
            except _MutationAdmissionBlocked as blocked:
                final_admission = blocked.decision or initial_admission
                return CommandApplicationResult(
                    status=(
                        ApplicationStatus.RECOVERY_REQUIRED
                        if blocked.recovery_required
                        or final_admission.status
                        is ExecutionAdmissionStatus.RECOVERY_REQUIRED
                        else ApplicationStatus.BLOCKED
                    ),
                    risk=risk,
                    journal_sequence=appended.sequence,
                    execution_admission=final_admission,
                )
            except Exception as error:
                if boundary_admission is None:
                    self._append_final_admission_failure(
                        command,
                        occurred_at=evaluated_at,
                        error_type=type(error).__name__,
                    )
                    return CommandApplicationResult(
                        status=ApplicationStatus.RECOVERY_REQUIRED,
                        risk=risk,
                        journal_sequence=appended.sequence,
                        execution_admission=initial_admission,
                    )
                return self._handler_failure_result(
                    command,
                    risk=risk,
                    journal_sequence=appended.sequence,
                    occurred_at=evaluated_at,
                    error=error,
                    execution_admission=boundary_admission or initial_admission,
                )
            if boundary_admission is None:
                self._append_final_admission_failure(
                    command,
                    occurred_at=evaluated_at,
                    error_type="MUTATION_ADMISSION_NOT_EVALUATED",
                )
                return CommandApplicationResult(
                    status=ApplicationStatus.RECOVERY_REQUIRED,
                    risk=risk,
                    journal_sequence=appended.sequence,
                    handler_result=handler_result,
                    execution_admission=initial_admission,
                )
            execution_admission = boundary_admission
        else:
            try:
                handler_result = self._handler.submit(approved)
            except Exception as error:
                return self._handler_failure_result(
                    command,
                    risk=risk,
                    journal_sequence=appended.sequence,
                    occurred_at=evaluated_at,
                    error=error,
                    execution_admission=execution_admission,
                )

        try:
            outcome_records = (
                self._outcome_recorder.records_for(command, handler_result)
                if self._outcome_recorder is not None
                else ()
            )
            outcome_sequences = tuple(
                self._journal.append(record).sequence for record in outcome_records
            )
        except Exception:
            # The handler may already have applied a local-paper side effect.
            # Do not retry it or report a safely completed command until recovery
            # can reconcile the command record with handler/projection evidence.
            return CommandApplicationResult(
                status=ApplicationStatus.RECOVERY_REQUIRED,
                risk=risk,
                journal_sequence=appended.sequence,
                handler_result=handler_result,
                execution_admission=execution_admission,
            )
        return CommandApplicationResult(
            status=ApplicationStatus.APPLIED,
            risk=risk,
            journal_sequence=appended.sequence,
            handler_result=handler_result,
            outcome_journal_sequences=outcome_sequences,
            execution_admission=execution_admission,
        )

    def _handler_failure_result(
        self,
        command: OrderCommand,
        *,
        risk: RiskDecision,
        journal_sequence: int,
        occurred_at: datetime,
        error: Exception,
        execution_admission: ExecutionAdmissionDecision | None,
    ) -> CommandApplicationResult:
        self._journal.append(
            JournalRecord(
                record_id=f"command-handler-failure:{command.command_id}",
                session_id=command.session_id,
                kind="order_handler_failure.v1",
                occurred_at=occurred_at,
                payload={
                    "command_id": command.command_id,
                    "error_type": type(error).__name__,
                },
            )
        )
        return CommandApplicationResult(
            status=ApplicationStatus.HANDLER_FAILED,
            risk=risk,
            journal_sequence=journal_sequence,
            execution_admission=execution_admission,
        )

    def _append_final_admission_failure(
        self,
        command: OrderCommand,
        *,
        occurred_at: datetime,
        error_type: str,
    ) -> None:
        self._journal.append(
            JournalRecord(
                record_id=f"final-admission-failure:{command.command_id}",
                session_id=command.session_id,
                kind="no_overnight_final_admission_failure.v1",
                occurred_at=occurred_at,
                payload={
                    "command_id": command.command_id,
                    "error_type": error_type,
                },
            )
        )

    def _append_final_admission(
        self,
        command: OrderCommand,
        *,
        initial: ExecutionAdmissionDecision,
        final: ExecutionAdmissionDecision,
    ) -> JournalAppendResult:
        return self._journal.append(
            JournalRecord(
                record_id=f"final-admission:{command.command_id}",
                session_id=command.session_id,
                kind="no_overnight_final_admission.v1",
                occurred_at=final.snapshot.evaluated_at,
                payload={
                    "command_id": command.command_id,
                    "idempotency_key": command.idempotency_key,
                    "expected_admission_revision": initial.admission_revision,
                    "decision": final.to_payload(),
                },
                idempotency_scope=(
                    f"{command.session_id}:no-overnight-final-admission"
                ),
                idempotency_key=command.command_id,
            )
        )

    @staticmethod
    def _validate_final_admission(
        *,
        initial: ExecutionAdmissionDecision,
        final: ExecutionAdmissionDecision,
    ) -> None:
        if not final.final_check:
            raise ValueError("final admission reader returned an initial decision")
        if final.snapshot.evaluated_at < initial.snapshot.evaluated_at:
            raise ValueError("final admission time moved backwards")
        if (
            final.status is ExecutionAdmissionStatus.APPROVED
            and final.admission_revision != initial.admission_revision
        ):
            raise ValueError("approved final admission revision changed")
