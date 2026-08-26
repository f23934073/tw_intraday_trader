"""Infrastructure adapters for the uninstalled PR-TM-012C1 external runner."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import date, datetime, time
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

from market_data.equity_calendar import ReviewedEquityCalendar
from runtime.trade_management_artifact_io import (
    digest_path,
    require_complete_artifact_pair,
    write_json_digest_pair_exclusive,
)
from runtime.trade_management_external_git import run_git_head, run_git_status
from runtime.trade_management_external_process import (
    run_c0_entrypoint,
    run_c1_entrypoint,
)
from runtime.trade_management_external_supervisor import (
    CommandPlan,
    ExecutionSpec,
    OwnershipAlreadyHeld,
    ProcessResult,
    SOURCE_FILES,
    SOURCE_FILENAMES,
    SUPERVISOR_SPEC_VERSION,
    SupervisorBlocked,
)
from runtime.trade_management_runtime_identity import runtime_code_identity


TAIPEI = ZoneInfo("Asia/Taipei")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_APPROVED_FILES = frozenset(
    {
        "python_executable",
        "resolved_python_executable",
        "pyproject",
        "dependency_lock",
        "supervisor_script",
        "supervisor_core",
        "supervisor_adapters",
        "process_allowlist",
        "git_allowlist",
        "sandbox_profile",
        "launchd_plist",
        "provider_egress_inventory",
        "sandbox_denial_rehearsal",
        "codex_automation_pause_evidence",
    }
)
EXACT_APPROVED_RELATIVE_PATHS = {
    "python_executable": ".venv/bin/python",
    "pyproject": "pyproject.toml",
    "supervisor_script": "scripts/run_trade_management_shadow_external_supervisor.py",
    "supervisor_core": "runtime/trade_management_external_supervisor.py",
    "supervisor_adapters": "runtime/trade_management_external_adapters.py",
    "process_allowlist": "runtime/trade_management_external_process.py",
    "git_allowlist": "runtime/trade_management_external_git.py",
    "sandbox_profile": "architecture/deployment/trade_management_shadow_external.sb",
    "launchd_plist": "architecture/deployment/com.stevehuang.trade-management-shadow.plist",
    "provider_egress_inventory": "architecture/deployment/review_evidence/provider_egress_inventory.json",
    "sandbox_denial_rehearsal": "architecture/deployment/review_evidence/sandbox_denial_rehearsal.json",
    "codex_automation_pause_evidence": "architecture/deployment/review_evidence/codex_automation_pause_evidence.json",
}
ALLOWED_DEPENDENCY_LOCK_NAMES = frozenset(
    {"uv.lock", "poetry.lock", "Pipfile.lock", "requirements.lock"}
)
SECRET_KEYS = frozenset(
    {
        "SHIOAJI_API_KEY",
        "SJ_API_KEY",
        "SHIOAJI_SECRET",
        "SJ_SECRET_KEY",
        "SJ_SEC_KEY",
        "LOCAL_PAPER_DATABASE_URL",
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL",
        "SJ_SIMULATION",
    }
)
SAFE_INHERITED_ENV_KEYS = (
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "TMPDIR",
)


class LocalSupervisorAdapter:
    """Narrow local adapter; it has no provider, Journal, Risk, or order imports."""

    def __init__(
        self,
        *,
        spec_path: Path,
        spec: ExecutionSpec,
        approved_files: Mapping[str, Mapping[str, str]],
    ) -> None:
        self._spec_path = spec_path
        self._spec = spec
        self._approved_files = {
            role: dict(item) for role, item in approved_files.items()
        }
        self._child_environment: dict[str, str] | None = None

    def now(self) -> datetime:
        return datetime.now(TAIPEI)

    def acquire_ownership(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        started_at: datetime,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        _require_secure_runtime_root(spec.ownership_lock_root)
        payload = {
            "artifact_type": "TradeManagementShadowExternalOwnershipLock",
            "version": SUPERVISOR_SPEC_VERSION,
            "market_date": plan.market_date.isoformat(),
            "session_id": plan.session_id,
            "supervisor_pid": os.getpid(),
            "started_at": started_at.isoformat(),
            "approved_commit": spec.approved_commit,
            "automatic_stale_lock_removal": False,
            "production_shadow_gate": "NOT_PASSED",
        }
        content = (_canonical_json(payload) + "\n").encode("utf-8")
        root_descriptor = os.open(spec.ownership_lock_root, os.O_RDONLY)
        try:
            try:
                descriptor = os.open(
                    plan.paths.ownership_lock.name,
                    os.O_CREAT
                    | os.O_EXCL
                    | os.O_WRONLY
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError as error:
                raise OwnershipAlreadyHeld("MARKET_DATE_ALREADY_OWNED") from error
            try:
                os.write(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            os.close(root_descriptor)
        _fsync_directory(plan.paths.ownership_lock.parent)
        return {
            "lock_path": str(plan.paths.ownership_lock),
            "lock_sha256": _sha256_bytes(content),
            "stale_lock_auto_removed": False,
        }

    def calendar_evidence(
        self,
        *,
        spec: ExecutionSpec,
        market_date: date,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        _require_regular_file(spec.calendar_path, reject_final_symlink=True)
        observed_digest = _sha256_file(spec.calendar_path)
        if observed_digest != spec.calendar_sha256:
            raise SupervisorBlocked("REVIEWED_CALENDAR_DIGEST_MISMATCH")
        calendar = ReviewedEquityCalendar.from_path(spec.calendar_path)
        return {
            "trading_day": calendar.is_trading_day(market_date),
            "schema_version": calendar.schema_version,
            "calendar_sha256": observed_digest,
            "timezone": calendar.timezone,
        }

    def verify_static_admission(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        observed_at: datetime,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        _require_preopen_time(observed_at, market_date=plan.market_date)
        if spec.approved_at > observed_at:
            raise SupervisorBlocked("EXECUTION_SPEC_APPROVAL_TIME_AFTER_ADMISSION")
        _require_output_roots_outside_checkout(spec)
        _require_runtime_path_separation(spec, spec_path=self._spec_path)
        for root in (spec.artifact_root, spec.records_root):
            _require_secure_runtime_root(root)
        _require_no_checkout_dotenv(spec.project_root)
        head, identity = self._verify_runtime_unchanged(spec)
        if not spec.python_executable.samefile(
            Path(self._approved_files["python_executable"]["path"])
        ):
            raise SupervisorBlocked("APPROVED_PYTHON_PATH_MISMATCH")
        self._child_environment = _load_minimal_child_environment(
            spec.environment_file
        )
        _require_absent_run_targets(plan)
        _ensure_run_root(spec, plan)
        return {
            "approved_commit": head,
            "runtime_code_identity": identity,
            "approval_spec_sha256": spec.spec_digest,
            "approved_file_sha256": {
                role: item["sha256"]
                for role, item in sorted(self._approved_files.items())
            },
            "environment_file_mode": "0600",
            "dsn_separation_verified": True,
            "provider_simulation_forced": True,
            "resolved_python_executable": str(spec.python_executable.resolve()),
            "source_checkout_write_allowed": False,
        }

    def run_c0(self, *, spec: ExecutionSpec, plan: CommandPlan) -> ProcessResult:
        _require_same_spec(spec, self._spec)
        self._verify_runtime_unchanged(spec)
        return run_c0_entrypoint(
            plan=plan,
            project_root=spec.project_root,
            environment={
                key: value
                for key, value in self._require_child_environment().items()
                if key != "LOCAL_PAPER_DATABASE_URL"
            },
            now=self.now,
        )

    def verify_c0(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        value, file_digest, sidecar_digest = _read_json_pair(plan.paths.c0_artifact)
        manifest = _mapping(value.get("manifest"), "C0_MANIFEST_MISSING")
        report = _mapping(value.get("readiness_report"), "C0_REPORT_MISSING")
        provider = _mapping(value.get("provider_preflight"), "C0_PROVIDER_MISSING")
        if (
            value.get("artifact_type")
            != "TradeManagementShadowPremarketReadiness"
            or value.get("production_shadow_gate") != "NOT_PASSED"
            or report.get("status") != "READY_FOR_SESSION"
            or report.get("blockers") != []
            or _canonical_digest(manifest) != value.get("manifest_digest")
            or _canonical_digest(report) != value.get("readiness_report_digest")
            or report.get("manifest_digest") != value.get("manifest_digest")
            or sidecar_digest != value.get("readiness_report_digest")
            or manifest.get("market_date") != plan.market_date.isoformat()
            or manifest.get("session_id") != plan.session_id
            or manifest.get("symbol") != spec.symbol
            or manifest.get("connection_session_id")
            != plan.connection_session_id
            or manifest.get("code_identity")
            != spec.approved_runtime_code_identity
            or manifest.get("execution_authority") is not False
            or manifest.get("execution_enabled") is not False
            or manifest.get("evidence_only") is not True
            or manifest.get("provider_simulation") is not True
            or provider.get("subscribe_trade") is not False
            or provider.get("login_succeeded") is not True
            or provider.get("logout_succeeded") is not True
            or provider.get("environment_identity")
            != manifest.get("provider_identity")
        ):
            raise SupervisorBlocked("C0_READY_ARTIFACT_INVALID")
        return {
            "artifact": str(plan.paths.c0_artifact),
            "artifact_sha256": file_digest,
            "readiness_report_digest": sidecar_digest,
            "status": "READY_FOR_SESSION",
            "provider_identity": provider.get("environment_identity"),
        }

    def verify_c1_admission(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
        observed_at: datetime,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        _require_preopen_time(observed_at, market_date=plan.market_date)
        root = plan.paths.canonical_input_root
        promotion_lock = root.parent / f".{plan.market_date.isoformat()}.promotion.lock"
        if promotion_lock.exists():
            raise SupervisorBlocked("C1_CANONICAL_PROMOTION_INCOMPLETE")
        _reject_symlink_components(root, allow_missing=False)
        input_digests: dict[str, str] = {}
        for filename in SOURCE_FILENAMES:
            path = root / filename
            _require_regular_file(path, reject_final_symlink=True)
            input_digests[filename] = _sha256_file(path)
        approval, _, approval_digest = _read_digest_bound_json_pair(
            root / "review_approval.json",
            digest_field="approval_digest",
        )
        bundle, _, bundle_digest = _read_digest_bound_json_pair(
            root / "bundle_manifest.json",
            digest_field="bundle_digest",
        )
        if (
            approval.get("artifact_type")
            != "TradeManagementShadowInputReviewApproval"
            or approval.get("version")
            != "trade-management-shadow-input-approval-v1"
            or approval.get("approval_status")
            != "APPROVED_FOR_CANONICAL_PROMOTION"
            or approval.get("reviewed") is not True
            or approval.get("formal_c1_eligible") is not True
            or approval.get("market_date") != plan.market_date.isoformat()
            or approval.get("runtime_code_identity")
            != spec.approved_runtime_code_identity
            or approval.get("execution_authority") is not False
            or approval.get("execution_enabled") is not False
            or approval.get("evidence_only") is not True
            or approval.get("production_shadow_gate") != "NOT_PASSED"
            or approval_digest != approval.get("approval_digest")
            or not str(approval.get("reviewer_id", "")).strip()
        ):
            raise SupervisorBlocked("C1_REVIEW_APPROVAL_INVALID")
        attempt_id = str(approval.get("attempt_id", ""))
        review_packet_digest = str(approval.get("review_packet_digest", ""))
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", attempt_id) is None
            or SHA256_PATTERN.fullmatch(review_packet_digest) is None
        ):
            raise SupervisorBlocked("C1_REVIEW_REFERENCE_INVALID")
        reviewed_at = _aware_datetime(
            approval.get("reviewed_at"),
            "C1_REVIEW_TIME_INVALID",
        )
        if reviewed_at > observed_at:
            raise SupervisorBlocked("C1_REVIEW_TIME_AFTER_ADMISSION")
        binding = _mapping(
            approval.get("binding"),
            "C1_REVIEW_BINDING_MISSING",
        )
        provenance = _mapping(
            binding.get("risk_snapshot_provenance"),
            "C1_REVIEW_RISK_PROVENANCE_MISSING",
        )
        captured_at = _aware_datetime(
            provenance.get("captured_at"),
            "C1_RISK_CAPTURE_TIME_INVALID",
        )
        if (
            reviewed_at < captured_at
            or binding.get("session_id") != plan.session_id
            or binding.get("symbol") != spec.symbol
            or provenance.get("session_id") != plan.session_id
            or provenance.get("symbol") != spec.symbol
            or provenance.get("market_date") != plan.market_date.isoformat()
        ):
            raise SupervisorBlocked("C1_REVIEW_BINDING_INVALID")
        approved_sources = _mapping(
            approval.get("approved_sources"),
            "C1_APPROVED_SOURCES_MISSING",
        )
        expected_digests = {
            role: input_digests[filename] for role, filename in SOURCE_FILES
        }
        approval_digests = {
            name: str(_mapping(item, "C1_APPROVED_SOURCE_INVALID").get("sha256"))
            for name, item in approved_sources.items()
        }
        if approval_digests != expected_digests:
            raise SupervisorBlocked("C1_APPROVED_SOURCE_DIGEST_MISMATCH")
        if any(
            _mapping(approved_sources[role], "C1_APPROVED_SOURCE_INVALID").get(
                "filename"
            )
            != filename
            for role, filename in SOURCE_FILES
        ):
            raise SupervisorBlocked("C1_APPROVED_SOURCE_FILENAME_MISMATCH")
        if (
            bundle.get("artifact_type")
            != "TradeManagementShadowCanonicalInputBundle"
            or bundle.get("version")
            != "trade-management-shadow-canonical-input-bundle-v1"
            or bundle.get("market_date") != plan.market_date.isoformat()
            or bundle.get("attempt_id") != attempt_id
            or bundle.get("approval_digest") != approval_digest
            or bundle.get("review_packet_digest") != review_packet_digest
            or bundle.get("runtime_code_identity")
            != spec.approved_runtime_code_identity
            or bundle.get("file_digests") != approval_digests
            or bundle.get("execution_authority") is not False
            or bundle.get("execution_enabled") is not False
            or bundle.get("evidence_only") is not True
            or bundle.get("production_shadow_gate") != "NOT_PASSED"
            or bundle_digest != bundle.get("bundle_digest")
        ):
            raise SupervisorBlocked("C1_CANONICAL_BUNDLE_INVALID")
        return {
            "canonical_input_root": str(root),
            "file_sha256": input_digests,
            "review_approval_digest": approval_digest,
            "bundle_manifest_digest": bundle_digest,
            "reviewed": True,
        }

    def run_c1(self, *, spec: ExecutionSpec, plan: CommandPlan) -> ProcessResult:
        _require_same_spec(spec, self._spec)
        self._verify_runtime_unchanged(spec)
        return run_c1_entrypoint(
            plan=plan,
            project_root=spec.project_root,
            environment=self._require_child_environment(),
            now=self.now,
        )

    def verify_c1(
        self,
        *,
        spec: ExecutionSpec,
        plan: CommandPlan,
    ) -> Mapping[str, object]:
        _require_same_spec(spec, self._spec)
        value, file_digest, sidecar_digest = _read_json_pair(plan.paths.c1_artifact)
        session = _mapping(value.get("session_evidence"), "C1_EVIDENCE_MISSING")
        if (
            value.get("artifact_type") != "TradeManagementC1SessionEvidence"
            or value.get("production_shadow_gate") != "NOT_PASSED"
            or sidecar_digest != value.get("session_evidence_digest")
            or value.get("preflight_artifact")
            != str(plan.paths.c0_artifact.resolve())
            or value.get("preflight_sha256")
            != _sha256_file(plan.paths.c0_artifact)
            or value.get("input_approval_artifact")
            != str(
                (plan.paths.canonical_input_root / "review_approval.json").resolve()
            )
            or session.get("session_id") != plan.session_id
            or session.get("status")
            not in {"FINALIZED", "INSUFFICIENT_EVIDENCE"}
            or session.get("execution_authority") is not False
            or session.get("execution_enabled") is not False
            or session.get("evidence_only") is not True
            or session.get("production_shadow_gate") != "NOT_PASSED"
        ):
            raise SupervisorBlocked("C1_TERMINAL_ARTIFACT_INVALID")
        return {
            "artifact": str(plan.paths.c1_artifact),
            "artifact_sha256": file_digest,
            "session_evidence_digest": sidecar_digest,
            "session_status": session.get("status"),
        }

    def artifact_inventory(self, *, plan: CommandPlan) -> Mapping[str, object]:
        paths = {
            "ownership_lock": plan.paths.ownership_lock,
            "c0_artifact": plan.paths.c0_artifact,
            "c0_sidecar": digest_path(plan.paths.c0_artifact),
            "c0_write_lock": plan.paths.c0_artifact.with_suffix(
                ".json.write.lock"
            ),
            "c1_artifact": plan.paths.c1_artifact,
            "c1_sidecar": digest_path(plan.paths.c1_artifact),
            "c1_write_lock": plan.paths.c1_artifact.with_suffix(
                ".json.write.lock"
            ),
            "c0_stdout": plan.paths.c0_stdout,
            "c0_stderr": plan.paths.c0_stderr,
            "c1_stdout": plan.paths.c1_stdout,
            "c1_stderr": plan.paths.c1_stderr,
        }
        return {
            name: {
                "path": str(path),
                "exists": path.is_file(),
                "sha256": _sha256_file(path) if path.is_file() else None,
            }
            for name, path in paths.items()
        }

    def publish_disposition(
        self,
        *,
        plan: CommandPlan,
        disposition: Mapping[str, object],
    ) -> Mapping[str, object]:
        digest = _canonical_digest(disposition)
        if disposition.get("status") == "ALREADY_OWNED":
            target_root = (
                self._spec.artifact_root
                / plan.market_date.isoformat()
                / "lock_contenders"
            )
            _ensure_secure_nested_root(
                self._spec.artifact_root,
                plan.market_date.isoformat(),
                "lock_contenders",
            )
            target = target_root / f"contender-{digest[:20]}-{os.getpid()}.json"
        else:
            _ensure_run_root(self._spec, plan)
            target = plan.paths.disposition
        write_json_digest_pair_exclusive(
            target,
            dict(disposition),
            digest,
        )
        return {
            "artifact": str(target),
            "digest": digest,
        }

    def _require_child_environment(self) -> Mapping[str, str]:
        if self._child_environment is None:
            raise SupervisorBlocked("CHILD_ENVIRONMENT_NOT_ADMITTED")
        return self._child_environment

    def _verify_runtime_unchanged(
        self,
        spec: ExecutionSpec,
    ) -> tuple[str, str]:
        loaded_spec, loaded_files = load_approved_execution_spec(self._spec_path)
        if loaded_spec != spec or loaded_files != self._approved_files:
            raise SupervisorBlocked("EXECUTION_SPEC_CHANGED_AFTER_LOAD")
        _verify_approved_files(
            project_root=spec.project_root,
            approved_files=self._approved_files,
        )
        _require_regular_file(spec.calendar_path, reject_final_symlink=True)
        if _sha256_file(spec.calendar_path) != spec.calendar_sha256:
            raise SupervisorBlocked("REVIEWED_CALENDAR_DIGEST_MISMATCH")
        if _venv_tree_digest(spec.project_root / ".venv") != (
            spec.approved_venv_tree_sha256
        ):
            raise SupervisorBlocked("APPROVED_VENV_TREE_IDENTITY_MISMATCH")
        head = run_git_head(spec.project_root)
        if head != spec.approved_commit:
            raise SupervisorBlocked("APPROVED_COMMIT_MISMATCH")
        if run_git_status(spec.project_root):
            raise SupervisorBlocked("PINNED_CHECKOUT_NOT_CLEAN")
        identity = runtime_code_identity(
            project_root=spec.project_root,
            git_head_value=head,
        )
        if identity != spec.approved_runtime_code_identity:
            raise SupervisorBlocked("APPROVED_RUNTIME_IDENTITY_MISMATCH")
        return head, identity


def load_approved_execution_spec(
    path: Path,
) -> tuple[ExecutionSpec, dict[str, dict[str, str]]]:
    _require_regular_file(path, reject_final_symlink=True)
    _require_owner_only_file(path)
    _require_owner_only_file(digest_path(path))
    value, _, sidecar_digest = _read_json_pair(path)
    claimed_digest = str(value.get("spec_digest", ""))
    unsigned = dict(value)
    unsigned.pop("spec_digest", None)
    if (
        _canonical_digest(unsigned) != claimed_digest
        or sidecar_digest != claimed_digest
    ):
        raise SupervisorBlocked("EXECUTION_SPEC_DIGEST_MISMATCH")
    if (
        value.get("artifact_type")
        != "TradeManagementShadowExternalExecutionApproval"
        or value.get("version") != SUPERVISOR_SPEC_VERSION
        or value.get("approval_status") != "APPROVED_FOR_INSTALLATION"
        or value.get("reviewed") is not True
        or value.get("execution_authority") is not False
        or value.get("execution_enabled") is not False
        or value.get("evidence_only") is not True
        or value.get("production_shadow_gate") != "NOT_PASSED"
        or not str(value.get("reviewer_id", "")).strip()
    ):
        raise SupervisorBlocked("EXECUTION_SPEC_NOT_APPROVED")
    approved_at = datetime.fromisoformat(str(value.get("approved_at")))
    if approved_at.tzinfo is None or approved_at.utcoffset() is None:
        raise SupervisorBlocked("EXECUTION_SPEC_APPROVAL_TIME_INVALID")
    approved_commit = str(value.get("approved_commit", ""))
    if COMMIT_PATTERN.fullmatch(approved_commit) is None:
        raise SupervisorBlocked("EXECUTION_SPEC_COMMIT_INVALID")
    gates = _mapping(value.get("installation_gates"), "INSTALLATION_GATES_MISSING")
    if set(gates) != {
        "provider_egress_inventory_digest",
        "sandbox_denial_rehearsal_digest",
        "codex_automation_pause_evidence_digest",
        "cooperative_termination_disposition",
    }:
        raise SupervisorBlocked("INSTALLATION_GATE_SET_INVALID")
    for name in (
        "provider_egress_inventory_digest",
        "sandbox_denial_rehearsal_digest",
        "codex_automation_pause_evidence_digest",
    ):
        if SHA256_PATTERN.fullmatch(str(gates.get(name, ""))) is None:
            raise SupervisorBlocked("INSTALLATION_GATE_DIGEST_INVALID")
    if gates.get("cooperative_termination_disposition") != "NO_AUTOMATIC_C1_SIGNAL":
        raise SupervisorBlocked("AUTOMATIC_C1_TERMINATION_NOT_APPROVED")
    raw_files = _mapping(value.get("approved_files"), "APPROVED_FILES_MISSING")
    if set(raw_files) != REQUIRED_APPROVED_FILES:
        raise SupervisorBlocked("APPROVED_FILE_SET_INVALID")
    approved_files: dict[str, dict[str, str]] = {}
    for role, raw_item in raw_files.items():
        item = _mapping(raw_item, "APPROVED_FILE_INVALID")
        file_path = Path(str(item.get("path", "")))
        digest = str(item.get("sha256", ""))
        if not file_path.is_absolute() or SHA256_PATTERN.fullmatch(digest) is None:
            raise SupervisorBlocked("APPROVED_FILE_INVALID")
        approved_files[role] = {"path": str(file_path), "sha256": digest}
    gate_file_roles = {
        "provider_egress_inventory_digest": "provider_egress_inventory",
        "sandbox_denial_rehearsal_digest": "sandbox_denial_rehearsal",
        "codex_automation_pause_evidence_digest": "codex_automation_pause_evidence",
    }
    if any(
        gates[gate_name] != approved_files[file_role]["sha256"]
        for gate_name, file_role in gate_file_roles.items()
    ):
        raise SupervisorBlocked("INSTALLATION_GATE_FILE_DIGEST_MISMATCH")
    calendar = _mapping(value.get("reviewed_calendar"), "CALENDAR_SPEC_MISSING")
    locations = _mapping(value.get("locations"), "EXECUTION_LOCATIONS_MISSING")
    spec = ExecutionSpec(
        spec_digest=claimed_digest,
        project_root=Path(str(locations.get("project_root", ""))),
        python_executable=Path(
            approved_files["python_executable"]["path"]
        ),
        approved_commit=approved_commit,
        approved_runtime_code_identity=str(
            value.get("approved_runtime_code_identity", "")
        ),
        approved_venv_tree_sha256=str(
            value.get("approved_venv_tree_sha256", "")
        ),
        approved_at=approved_at,
        reviewer_id=str(value.get("reviewer_id", "")),
        calendar_path=Path(str(calendar.get("path", ""))),
        calendar_sha256=str(calendar.get("sha256", "")),
        environment_file=Path(str(locations.get("environment_file", ""))),
        artifact_root=Path(str(locations.get("artifact_root", ""))),
        records_root=Path(str(locations.get("records_root", ""))),
        ownership_lock_root=Path(
            str(locations.get("ownership_lock_root", ""))
        ),
        symbol=str(value.get("symbol", "")),
    )
    expected_calendar = spec.project_root / "config/twse_calendar_2026.json"
    if spec.calendar_path != expected_calendar:
        raise SupervisorBlocked("REVIEWED_CALENDAR_PATH_MISMATCH")
    expected_identity_prefix = f"git:{approved_commit}:source-sha256:"
    identity_digest = spec.approved_runtime_code_identity.removeprefix(
        expected_identity_prefix
    )
    if (
        not spec.approved_runtime_code_identity.startswith(expected_identity_prefix)
        or SHA256_PATTERN.fullmatch(identity_digest) is None
    ):
        raise SupervisorBlocked("EXECUTION_SPEC_RUNTIME_IDENTITY_INVALID")
    if SHA256_PATTERN.fullmatch(spec.approved_venv_tree_sha256) is None:
        raise SupervisorBlocked("EXECUTION_SPEC_VENV_IDENTITY_INVALID")
    return spec, approved_files


def _load_minimal_child_environment(path: Path) -> dict[str, str]:
    _require_regular_file(path, reject_final_symlink=True)
    file_stat = path.stat()
    if stat.S_IMODE(file_stat.st_mode) != 0o600 or file_stat.st_uid != os.getuid():
        raise SupervisorBlocked("ENVIRONMENT_FILE_MUST_BE_OWNER_ONLY")
    parsed = dotenv_values(path, interpolate=False)
    unknown = {key for key, value in parsed.items() if value and key not in SECRET_KEYS}
    if unknown:
        raise SupervisorBlocked("ENVIRONMENT_FILE_KEY_NOT_ALLOWED")
    values = {
        key: str(value)
        for key, value in parsed.items()
        if key in SECRET_KEYS and value is not None and str(value).strip()
    }
    api_keys = {"SHIOAJI_API_KEY", "SJ_API_KEY"} & set(values)
    secret_keys = {"SHIOAJI_SECRET", "SJ_SECRET_KEY", "SJ_SEC_KEY"} & set(values)
    if len(api_keys) != 1 or len(secret_keys) != 1:
        raise SupervisorBlocked("PROVIDER_CREDENTIAL_ALIAS_SET_INVALID")
    fill_dsn = values.get("LOCAL_PAPER_DATABASE_URL", "").strip()
    shadow_dsn = values.get("TRADE_MANAGEMENT_SHADOW_DATABASE_URL", "").strip()
    if not fill_dsn or not shadow_dsn:
        raise SupervisorBlocked("LOCAL_PAPER_AND_SHADOW_DSNS_ARE_REQUIRED")
    if fill_dsn == shadow_dsn:
        raise SupervisorBlocked("SHADOW_DSN_MUST_BE_DEDICATED")
    if values.get("SJ_SIMULATION", "true").lower() != "true":
        raise SupervisorBlocked("PROVIDER_SIMULATION_MUST_BE_TRUE")
    environment = {
        key: os.environ[key]
        for key in SAFE_INHERITED_ENV_KEYS
        if os.environ.get(key)
    }
    environment.update(values)
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "SJ_SIMULATION": "true",
            "TZ": "Asia/Taipei",
        }
    )
    return environment


def _verify_approved_files(
    *,
    project_root: Path,
    approved_files: Mapping[str, Mapping[str, str]],
) -> None:
    if set(approved_files) != REQUIRED_APPROVED_FILES:
        raise SupervisorBlocked("APPROVED_FILE_SET_INVALID")
    for role, item in approved_files.items():
        path = Path(item["path"])
        _require_regular_file(
            path,
            reject_final_symlink=(role != "python_executable"),
        )
        if _sha256_file(path) != item["sha256"]:
            raise SupervisorBlocked(f"APPROVED_FILE_DIGEST_MISMATCH_{role.upper()}")
    for role, relative in EXACT_APPROVED_RELATIVE_PATHS.items():
        if Path(approved_files[role]["path"]) != project_root / relative:
            raise SupervisorBlocked(f"APPROVED_FILE_PATH_MISMATCH_{role.upper()}")
    resolved_python = Path(approved_files["python_executable"]["path"]).resolve()
    if Path(approved_files["resolved_python_executable"]["path"]) != resolved_python:
        raise SupervisorBlocked("RESOLVED_PYTHON_PATH_MISMATCH")
    dependency_lock = Path(approved_files["dependency_lock"]["path"])
    if (
        dependency_lock.parent != project_root
        or dependency_lock.name not in ALLOWED_DEPENDENCY_LOCK_NAMES
    ):
        raise SupervisorBlocked("APPROVED_DEPENDENCY_LOCK_PATH_INVALID")


def _require_absent_run_targets(plan: CommandPlan) -> None:
    targets = (
        plan.paths.run_root,
        plan.paths.c0_artifact,
        digest_path(plan.paths.c0_artifact),
        plan.paths.c0_artifact.with_suffix(".json.write.lock"),
        plan.paths.c1_artifact,
        digest_path(plan.paths.c1_artifact),
        plan.paths.c1_artifact.with_suffix(".json.write.lock"),
        plan.paths.disposition,
        digest_path(plan.paths.disposition),
        plan.paths.disposition.with_suffix(".json.write.lock"),
        plan.paths.c0_stdout,
        plan.paths.c0_stderr,
        plan.paths.c1_stdout,
        plan.paths.c1_stderr,
    )
    if any(path.exists() or path.is_symlink() for path in targets):
        raise SupervisorBlocked("IMMUTABLE_RUN_TARGET_ALREADY_EXISTS")


def _require_output_roots_outside_checkout(spec: ExecutionSpec) -> None:
    for root in (spec.artifact_root, spec.records_root, spec.ownership_lock_root):
        if root.is_relative_to(spec.project_root):
            raise SupervisorBlocked("RUNTIME_WRITE_ROOT_INSIDE_PINNED_CHECKOUT")


def _require_runtime_path_separation(
    spec: ExecutionSpec,
    *,
    spec_path: Path,
) -> None:
    roots = (spec.artifact_root, spec.records_root, spec.ownership_lock_root)
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise SupervisorBlocked("RUNTIME_WRITE_ROOTS_OVERLAP")
    for protected in (spec.environment_file, spec_path):
        if protected.is_relative_to(spec.project_root) or any(
            protected.is_relative_to(root) for root in roots
        ):
            raise SupervisorBlocked("PROTECTED_CONFIG_PATH_INSIDE_WRITABLE_ROOT")


def _ensure_run_root(spec: ExecutionSpec, plan: CommandPlan) -> None:
    _ensure_secure_nested_root(
        spec.artifact_root,
        plan.market_date.isoformat(),
        plan.session_id,
    )


def _ensure_secure_nested_root(base: Path, *parts: str) -> Path:
    _require_secure_runtime_root(base)
    cursor = base
    for part in parts:
        cursor = cursor / part
        try:
            cursor.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _require_secure_runtime_root(cursor)
    return cursor


def _require_no_checkout_dotenv(project_root: Path) -> None:
    if (project_root / ".env").exists() or (project_root / ".env").is_symlink():
        raise SupervisorBlocked("SECONDARY_CHECKOUT_ENVIRONMENT_PRESENT")


def _require_preopen_time(observed_at: datetime, *, market_date: date) -> None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise SupervisorBlocked("SUPERVISOR_CLOCK_MUST_BE_TIMEZONE_AWARE")
    local = observed_at.astimezone(TAIPEI)
    if local.date() != market_date:
        raise SupervisorBlocked("SUPERVISOR_MARKET_DATE_IS_NOT_TODAY")
    if not time(8, 30) <= local.time().replace(tzinfo=None) < time(9):
        raise SupervisorBlocked("SUPERVISOR_OUTSIDE_PREOPEN_WINDOW")


def _read_json_pair(path: Path) -> tuple[dict[str, object], str, str]:
    _require_regular_file(path, reject_final_symlink=True)
    sidecar = require_complete_artifact_pair(path)
    _require_regular_file(sidecar, reject_final_symlink=True)
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict):
        raise SupervisorBlocked("ARTIFACT_MUST_CONTAIN_ONE_OBJECT")
    sidecar_digest = sidecar.read_text(encoding="utf-8").strip()
    if SHA256_PATTERN.fullmatch(sidecar_digest) is None:
        raise SupervisorBlocked("ARTIFACT_SIDECAR_DIGEST_INVALID")
    return value, _sha256_bytes(content), sidecar_digest


def _read_digest_bound_json_pair(
    path: Path,
    *,
    digest_field: str,
) -> tuple[dict[str, object], str, str]:
    value, file_digest, sidecar_digest = _read_json_pair(path)
    claimed = str(value.get(digest_field, ""))
    unsigned = dict(value)
    unsigned.pop(digest_field, None)
    if _canonical_digest(unsigned) != claimed or sidecar_digest != claimed:
        raise SupervisorBlocked("ARTIFACT_CANONICAL_DIGEST_MISMATCH")
    return value, file_digest, sidecar_digest


def _mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SupervisorBlocked(code)
    return value


def _aware_datetime(value: object, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise SupervisorBlocked(code) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SupervisorBlocked(code)
    return parsed


def _require_regular_file(path: Path, *, reject_final_symlink: bool) -> None:
    _reject_symlink_components(path.parent, allow_missing=False)
    if reject_final_symlink and path.is_symlink():
        raise SupervisorBlocked("SYMLINK_PATH_REJECTED")
    if not path.is_file():
        raise SupervisorBlocked("REQUIRED_FILE_MISSING")


def _require_secure_runtime_root(path: Path) -> None:
    _require_regular_directory(path)
    path_stat = path.stat()
    if path_stat.st_uid != os.getuid() or stat.S_IMODE(path_stat.st_mode) != 0o700:
        raise SupervisorBlocked("RUNTIME_ROOT_MUST_BE_OWNER_ONLY")


def _require_owner_only_file(path: Path) -> None:
    _require_regular_file(path, reject_final_symlink=True)
    file_stat = path.stat()
    if file_stat.st_uid != os.getuid() or stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise SupervisorBlocked("APPROVAL_SPEC_PAIR_MUST_BE_OWNER_ONLY")


def _require_regular_directory(path: Path) -> None:
    _reject_symlink_components(path.parent, allow_missing=False)
    if path.is_symlink() or not path.is_dir():
        raise SupervisorBlocked("RUNTIME_ROOT_INVALID")


def _reject_symlink_components(path: Path, *, allow_missing: bool) -> None:
    if not path.is_absolute():
        raise SupervisorBlocked("ABSOLUTE_PATH_REQUIRED")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SupervisorBlocked("SYMLINK_PATH_REJECTED")
        if not cursor.exists():
            if allow_missing:
                return
            raise SupervisorBlocked("REQUIRED_PATH_MISSING")


def _require_same_spec(left: ExecutionSpec, right: ExecutionSpec) -> None:
    if left != right:
        raise SupervisorBlocked("EXECUTION_SPEC_INSTANCE_MISMATCH")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _venv_tree_digest(root: Path) -> str:
    _require_regular_directory(root)
    digest = hashlib.sha256()
    paths = sorted(
        root.rglob("*"),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8")
            digest.update(b"L")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
        elif path.is_file():
            content = path.read_bytes()
            digest.update(b"F")
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        elif path.is_dir():
            digest.update(b"D")
        else:
            raise SupervisorBlocked("VENV_SPECIAL_FILE_REJECTED")
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
