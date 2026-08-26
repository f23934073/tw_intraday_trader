"""Pure control-plane contract for the PR-TM-012C1 external runner."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Protocol


SUPERVISOR_SPEC_VERSION = "trade-management-shadow-external-execution-v1"
SOURCE_FILES = (
    ("entry_decision", "live_entry_decision.json"),
    ("thesis_draft", "trade_thesis_draft.json"),
    ("shadow_policy", "shadow_policy.json"),
    ("risk_snapshot", "risk_snapshot.json"),
)
SOURCE_FILENAMES = tuple(filename for _, filename in SOURCE_FILES)
SYMBOL_PATTERN = re.compile(r"[0-9A-Z][0-9A-Z._-]{1,15}\Z")


class SupervisorState(StrEnum):
    LOCK_ACQUIRE = "LOCK_ACQUIRE"
    CALENDAR_CHECK = "CALENDAR_CHECK"
    C0_READY_TO_START = "C0_READY_TO_START"
    C0_RUNNING = "C0_RUNNING"
    C0_COMPLETE = "C0_COMPLETE"
    C1_READY_TO_START = "C1_READY_TO_START"
    C1_RUNNING = "C1_RUNNING"
    TERMINAL = "TERMINAL"


class SupervisorStatus(StrEnum):
    ALREADY_OWNED = "ALREADY_OWNED"
    SKIPPED_CLOSED_DATE = "SKIPPED_CLOSED_DATE"
    BLOCKED = "BLOCKED"
    C1_TERMINAL = "C1_TERMINAL"


class SupervisorBlocked(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OwnershipAlreadyHeld(SupervisorBlocked):
    pass


@dataclass(frozen=True)
class ExecutionSpec:
    spec_digest: str
    project_root: Path
    python_executable: Path
    approved_commit: str
    approved_runtime_code_identity: str
    approved_venv_tree_sha256: str
    approved_at: datetime
    reviewer_id: str
    calendar_path: Path
    calendar_sha256: str
    environment_file: Path
    artifact_root: Path
    records_root: Path
    ownership_lock_root: Path
    symbol: str

    def __post_init__(self) -> None:
        if (
            len(self.spec_digest) != 64
            or len(self.calendar_sha256) != 64
            or len(self.approved_venv_tree_sha256) != 64
        ):
            raise ValueError("execution spec digests must be SHA-256 values")
        if (
            not self.approved_commit
            or not self.approved_runtime_code_identity
            or not self.reviewer_id.strip()
        ):
            raise ValueError("approved runtime identity is required")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("execution spec approval time must be timezone-aware")
        if SYMBOL_PATTERN.fullmatch(self.symbol) is None:
            raise ValueError("execution spec symbol is invalid")
        for path in (
            self.project_root,
            self.python_executable,
            self.calendar_path,
            self.environment_file,
            self.artifact_root,
            self.records_root,
            self.ownership_lock_root,
        ):
            if not path.is_absolute():
                raise ValueError("execution spec paths must be absolute")


@dataclass(frozen=True)
class SupervisorPaths:
    run_root: Path
    ownership_lock: Path
    c0_artifact: Path
    c1_artifact: Path
    disposition: Path
    c0_stdout: Path
    c0_stderr: Path
    c1_stdout: Path
    c1_stderr: Path
    canonical_input_root: Path


@dataclass(frozen=True)
class CommandPlan:
    market_date: date
    session_id: str
    connection_session_id: str
    c0_argv: tuple[str, ...]
    c1_argv: tuple[str, ...]
    paths: SupervisorPaths

    @property
    def argv_digests(self) -> dict[str, str]:
        return {
            "C0": _canonical_digest(list(self.c0_argv)),
            "C1": _canonical_digest(list(self.c1_argv)),
        }


@dataclass(frozen=True)
class ProcessResult:
    role: str
    returncode: int
    started_at: datetime
    completed_at: datetime
    pid: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "returncode": self.returncode,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "pid": self.pid,
        }


class SupervisorPorts(Protocol):
    def now(self) -> datetime: ...

    def acquire_ownership(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        started_at: datetime,
    ) -> Mapping[str, object]: ...

    def calendar_evidence(
        self,
        *,
        spec: ExecutionSpec,
        market_date: date,
    ) -> Mapping[str, object]: ...

    def verify_static_admission(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        observed_at: datetime,
    ) -> Mapping[str, object]: ...

    def run_c0(self, *, spec: ExecutionSpec, plan: CommandPlan) -> ProcessResult: ...

    def verify_c0(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
    ) -> Mapping[str, object]: ...

    def verify_c1_admission(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        observed_at: datetime,
    ) -> Mapping[str, object]: ...

    def run_c1(self, *, spec: ExecutionSpec, plan: CommandPlan) -> ProcessResult: ...

    def verify_c1(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
    ) -> Mapping[str, object]: ...

    def artifact_inventory(
        self,
        *,
        plan: CommandPlan,
    ) -> Mapping[str, object]: ...

    def publish_disposition(
        self,
        *,
        plan: CommandPlan,
        disposition: Mapping[str, object],
    ) -> Mapping[str, object]: ...


def build_command_plan(spec: ExecutionSpec, market_date: date) -> CommandPlan:
    compact_date = market_date.strftime("%Y%m%d")
    session_id = f"tm-shadow-{compact_date}-{spec.symbol}"
    connection_session_id = f"shioaji-{compact_date}-tm-shadow-a"
    run_root = spec.artifact_root / market_date.isoformat() / session_id
    input_root = (
        spec.project_root
        / "research"
        / "trade_management_shadow"
        / "session_inputs"
        / market_date.isoformat()
    )
    paths = SupervisorPaths(
        run_root=run_root,
        ownership_lock=spec.ownership_lock_root / f"{market_date.isoformat()}.lock",
        c0_artifact=run_root / "c0_premarket.json",
        c1_artifact=run_root / "c1_session.json",
        disposition=run_root / "supervisor_disposition.json",
        c0_stdout=run_root / "c0.stdout.log",
        c0_stderr=run_root / "c0.stderr.log",
        c1_stdout=run_root / "c1.stdout.log",
        c1_stderr=run_root / "c1.stderr.log",
        canonical_input_root=input_root,
    )
    python = str(spec.python_executable)
    c0_argv = (
        python,
        "scripts/preflight_trade_management_shadow.py",
        "--market-date",
        market_date.isoformat(),
        "--symbol",
        spec.symbol,
        "--session-id",
        session_id,
        "--connection-session-id",
        connection_session_id,
        "--code-identity",
        spec.approved_runtime_code_identity,
        "--output",
        str(paths.c0_artifact),
    )
    c1_argv = (
        python,
        "scripts/run_trade_management_shadow_c1.py",
        "--preflight-artifact",
        str(paths.c0_artifact),
        "--entry-decision",
        str(input_root / SOURCE_FILES[0][1]),
        "--thesis-draft",
        str(input_root / SOURCE_FILES[1][1]),
        "--shadow-policy",
        str(input_root / SOURCE_FILES[2][1]),
        "--risk-snapshot",
        str(input_root / SOURCE_FILES[3][1]),
        "--input-approval",
        str(input_root / "review_approval.json"),
        "--connection-session-id",
        connection_session_id,
        "--records-root",
        str(spec.records_root / market_date.isoformat() / session_id),
        "--output",
        str(paths.c1_artifact),
        "--case",
        "A",
        "--subscribe-ack-timeout-seconds",
        "30",
        "--preopen-wait-timeout-seconds",
        "1800",
    )
    return CommandPlan(
        market_date=market_date,
        session_id=session_id,
        connection_session_id=connection_session_id,
        c0_argv=c0_argv,
        c1_argv=c1_argv,
        paths=paths,
    )


def run_supervisor(
    *,
    spec: ExecutionSpec,
    market_date: date,
    ports: SupervisorPorts,
) -> dict[str, object]:
    """Run exactly one no-retry supervisor state machine."""

    plan = build_command_plan(spec, market_date)
    started_at = ports.now()
    state_history = [SupervisorState.LOCK_ACQUIRE.value]
    evidence: dict[str, object] = {}
    process_results: list[dict[str, object]] = []
    status = SupervisorStatus.BLOCKED
    reason_code = "UNEXPECTED_SUPERVISOR_FAILURE"
    c1_status: object = None

    try:
        evidence["ownership"] = dict(
            ports.acquire_ownership(
                spec=spec,
                plan=plan,
                started_at=started_at,
            )
        )
        state_history.append(SupervisorState.CALENDAR_CHECK.value)
        calendar = dict(
            ports.calendar_evidence(spec=spec, market_date=market_date)
        )
        evidence["calendar"] = calendar
        if calendar.get("trading_day") is not True:
            status = SupervisorStatus.SKIPPED_CLOSED_DATE
            reason_code = "REVIEWED_CALENDAR_CLOSED_DATE"
        else:
            state_history.append(SupervisorState.C0_READY_TO_START.value)
            evidence["static_admission"] = dict(
                ports.verify_static_admission(
                    spec=spec,
                    plan=plan,
                    observed_at=ports.now(),
                )
            )
            state_history.append(SupervisorState.C0_RUNNING.value)
            c0_result = ports.run_c0(spec=spec, plan=plan)
            process_results.append(c0_result.to_dict())
            if c0_result.returncode != 0:
                raise SupervisorBlocked("C0_EXIT_NONZERO")
            state_history.append(SupervisorState.C0_COMPLETE.value)
            evidence["c0"] = dict(ports.verify_c0(spec=spec, plan=plan))
            state_history.append(SupervisorState.C1_READY_TO_START.value)
            evidence["c1_admission"] = dict(
                ports.verify_c1_admission(
                    spec=spec,
                    plan=plan,
                    observed_at=ports.now(),
                )
            )
            state_history.append(SupervisorState.C1_RUNNING.value)
            c1_result = ports.run_c1(spec=spec, plan=plan)
            process_results.append(c1_result.to_dict())
            if c1_result.returncode != 0:
                raise SupervisorBlocked("C1_EXIT_NONZERO")
            c1_evidence = dict(ports.verify_c1(spec=spec, plan=plan))
            evidence["c1"] = c1_evidence
            c1_status = c1_evidence.get("session_status")
            status = SupervisorStatus.C1_TERMINAL
            reason_code = "C1_TERMINAL_ARTIFACT_VERIFIED"
    except OwnershipAlreadyHeld as error:
        status = SupervisorStatus.ALREADY_OWNED
        reason_code = error.code
    except SupervisorBlocked as error:
        status = SupervisorStatus.BLOCKED
        reason_code = error.code
    except Exception as error:  # fail closed without leaking exception values
        status = SupervisorStatus.BLOCKED
        reason_code = f"UNEXPECTED_{type(error).__name__.upper()}"

    state_history.append(SupervisorState.TERMINAL.value)
    try:
        evidence["artifact_inventory"] = dict(ports.artifact_inventory(plan=plan))
    except Exception as error:
        evidence["artifact_inventory"] = {
            "error_code": f"INVENTORY_{type(error).__name__.upper()}"
        }
        status = SupervisorStatus.BLOCKED
        reason_code = "TERMINAL_ARTIFACT_INVENTORY_FAILED"
    disposition: dict[str, object] = {
        "artifact_type": "TradeManagementShadowExternalSupervisorDisposition",
        "version": SUPERVISOR_SPEC_VERSION,
        "status": status.value,
        "reason_code": reason_code,
        "market_date": market_date.isoformat(),
        "session_id": plan.session_id,
        "connection_session_id": plan.connection_session_id,
        "started_at": started_at.isoformat(),
        "completed_at": ports.now().isoformat(),
        "state_history": state_history,
        "argv_sha256": plan.argv_digests,
        "process_results": process_results,
        "evidence": evidence,
        "c1_session_status": c1_status,
        "automatic_retry": False,
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    publication = dict(
        ports.publish_disposition(plan=plan, disposition=disposition)
    )
    disposition["publication"] = publication
    return disposition


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
