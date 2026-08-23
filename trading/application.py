"""Journal-first command application boundary for future local-paper routing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from trading.journal import JournalRecord, JournalRepository
from trading.risk import (
    OrderCommand,
    RiskDecision,
    RiskDecisionStatus,
    RiskGate,
    RiskSnapshot,
)


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


class CommandOutcomeRecorder(Protocol):
    """Maps an acknowledged handler result to append-only evidence records."""

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, Any],
    ) -> tuple[JournalRecord, ...]:
        """Return records to append after a successful handler acknowledgement."""


@dataclass(frozen=True)
class CommandApplicationResult:
    status: ApplicationStatus
    risk: RiskDecision
    journal_sequence: int
    handler_result: Mapping[str, Any] | None = None
    outcome_journal_sequences: tuple[int, ...] = ()


def _risk_snapshot_payload(snapshot: RiskSnapshot) -> dict[str, object]:
    """Return stable Journal evidence without serializing money as floats."""

    return {
        "data_health_state": snapshot.data_health_state,
        "market_open": snapshot.market_open,
        "instrument_tradable": snapshot.instrument_tradable,
        "available_cash": str(snapshot.available_cash),
        "current_position_shares": snapshot.current_position_shares,
        "pending_buy_shares": snapshot.pending_buy_shares,
        "pending_sell_shares": snapshot.pending_sell_shares,
        "daily_realized_pnl": str(snapshot.daily_realized_pnl),
        "daily_filled_buy_notional": str(
            snapshot.daily_filled_buy_notional
        ),
        "pending_buy_notional": str(snapshot.pending_buy_notional),
        "daily_loss": (
            str(snapshot.daily_loss) if snapshot.daily_loss is not None else None
        ),
        "same_side_pending_order": snapshot.same_side_pending_order,
        "book_age_seconds": snapshot.book_age_seconds,
    }


def _order_command_payload(command: OrderCommand) -> dict[str, object]:
    return {
        "command_id": command.command_id,
        "session_id": command.session_id,
        "origin": command.origin.value,
        "symbol": command.symbol,
        "side": command.side.value,
        "quantity_shares": command.quantity_shares,
        "limit_price": str(command.limit_price),
        "idempotency_key": command.idempotency_key,
        "requested_at": command.requested_at.isoformat(),
        "strategy_id": command.strategy_id,
        "strategy_version": command.strategy_version,
        "attempt": command.attempt,
        "predecessor_order_id": command.predecessor_order_id,
    }


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
    ) -> None:
        self._journal = journal
        self._risk_gate = risk_gate
        self._handler = handler
        self._outcome_recorder = outcome_recorder

    def apply(
        self,
        command: OrderCommand,
        snapshot: RiskSnapshot,
        *,
        evaluated_at: datetime,
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
        appended = self._journal.append(
            JournalRecord(
                record_id=f"command:{command.command_id}",
                session_id=command.session_id,
                kind="order_command.v1",
                occurred_at=evaluated_at,
                payload={
                    "command_id": command.command_id,
                    "origin": command.origin.value,
                    "symbol": command.symbol,
                    "side": command.side.value,
                    "quantity_shares": command.quantity_shares,
                    "limit_price": str(command.limit_price),
                    "idempotency_key": command.idempotency_key,
                    "strategy_id": command.strategy_id,
                    "strategy_version": command.strategy_version,
                    "attempt": command.attempt,
                    "predecessor_order_id": command.predecessor_order_id,
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
            )
        if risk.status is RiskDecisionStatus.BLOCKED:
            return CommandApplicationResult(
                status=ApplicationStatus.BLOCKED,
                risk=risk,
                journal_sequence=appended.sequence,
            )
        if risk.status is RiskDecisionStatus.REJECTED:
            return CommandApplicationResult(
                status=ApplicationStatus.REJECTED,
                risk=risk,
                journal_sequence=appended.sequence,
            )

        try:
            assert approved is not None
            handler_result = self._handler.submit(approved)
        except Exception as error:
            self._journal.append(
                JournalRecord(
                    record_id=f"command-handler-failure:{command.command_id}",
                    session_id=command.session_id,
                    kind="order_handler_failure.v1",
                    occurred_at=evaluated_at,
                    payload={
                        "command_id": command.command_id,
                        "error_type": type(error).__name__,
                    },
                )
            )
            return CommandApplicationResult(
                status=ApplicationStatus.HANDLER_FAILED,
                risk=risk,
                journal_sequence=appended.sequence,
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
            )
        return CommandApplicationResult(
            status=ApplicationStatus.APPLIED,
            risk=risk,
            journal_sequence=appended.sequence,
            handler_result=handler_result,
            outcome_journal_sequences=outcome_sequences,
        )
