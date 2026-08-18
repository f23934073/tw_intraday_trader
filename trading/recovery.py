"""Read-only classification of command outcomes from append-only Journal evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trading.journal import JournalRepository
from trading.local_paper import LOCAL_PAPER_FILL_KIND


class CommandRecoveryStatus(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class CommandRecovery:
    command_id: str
    status: CommandRecoveryStatus
    command_sequence: int | None
    evidence_sequences: tuple[int, ...]
    reasons: tuple[str, ...]


def classify_command_recovery(
    journal: JournalRepository,
    *,
    session_id: str,
    command_id: str,
) -> CommandRecovery:
    """Classify only proven outcomes; all uncertain paths remain fail-closed."""

    if not command_id.strip():
        raise ValueError("command_id must not be empty")
    results = journal.records(session_id)
    command = next(
        (
            result
            for result in results
            if result.record.kind == "order_command.v1"
            and result.record.payload.get("command_id") == command_id
        ),
        None,
    )
    if command is None:
        return CommandRecovery(
            command_id=command_id,
            status=CommandRecoveryStatus.NOT_FOUND,
            command_sequence=None,
            evidence_sequences=(),
            reasons=("command_not_found",),
        )

    risk_status = command.record.payload.get("risk_status")
    if risk_status == "BLOCKED":
        return _result(command_id, CommandRecoveryStatus.BLOCKED, command.sequence)
    if risk_status == "REJECTED":
        return _result(command_id, CommandRecoveryStatus.REJECTED, command.sequence)

    evidence = tuple(
        result
        for result in results
        if result.sequence > command.sequence
        and result.record.payload.get("command_id") == command_id
    )
    fill = next(
        (
            result
            for result in evidence
            if result.record.kind == LOCAL_PAPER_FILL_KIND
        ),
        None,
    )
    if fill is not None:
        return _result(
            command_id,
            CommandRecoveryStatus.FILLED,
            command.sequence,
            evidence_sequences=tuple(result.sequence for result in evidence),
        )

    reasons = ["outcome_not_proven"]
    if any(
        result.record.kind == "order_handler_failure.v1" for result in evidence
    ):
        reasons.append("handler_failure_recorded")
    return _result(
        command_id,
        CommandRecoveryStatus.RECOVERY_REQUIRED,
        command.sequence,
        evidence_sequences=tuple(result.sequence for result in evidence),
        reasons=tuple(reasons),
    )


def _result(
    command_id: str,
    status: CommandRecoveryStatus,
    command_sequence: int,
    *,
    evidence_sequences: tuple[int, ...] = (),
    reasons: tuple[str, ...] = (),
) -> CommandRecovery:
    return CommandRecovery(
        command_id=command_id,
        status=status,
        command_sequence=command_sequence,
        evidence_sequences=evidence_sequences,
        reasons=reasons,
    )
