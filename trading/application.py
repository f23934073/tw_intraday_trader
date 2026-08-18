"""Journal-first command application boundary for future local-paper routing."""

from __future__ import annotations

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


class LocalPaperCommandHandler(Protocol):
    """Side-effect port; the existing simulator is not wired here yet."""

    def submit(self, command: OrderCommand) -> Mapping[str, Any]:
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
        "same_side_pending_order": snapshot.same_side_pending_order,
        "book_age_seconds": snapshot.book_age_seconds,
    }


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
        risk = self._risk_gate.evaluate(
            command,
            snapshot,
            evaluated_at=evaluated_at,
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
                    "risk_status": risk.status.value,
                    "risk_reasons": [reason.value for reason in risk.reasons],
                    "risk_policy_version": risk.policy_version,
                    "risk_snapshot": _risk_snapshot_payload(snapshot),
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
            handler_result = self._handler.submit(command)
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
