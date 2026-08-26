from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from runtime import trade_management_external_process as process_guard
from runtime import trade_management_external_git as git_guard
from runtime.trade_management_external_adapters import (
    LocalSupervisorAdapter,
    REQUIRED_APPROVED_FILES,
    _load_minimal_child_environment,
    _require_runtime_path_separation,
    _venv_tree_digest,
    load_approved_execution_spec,
)
from runtime import trade_management_external_adapters as adapter_module
from runtime.trade_management_external_supervisor import (
    ExecutionSpec,
    OwnershipAlreadyHeld,
    ProcessResult,
    SupervisorBlocked,
    build_command_plan,
    run_supervisor,
)


TAIPEI = ZoneInfo("Asia/Taipei")
MARKET_DATE = date(2026, 8, 27)
PREOPEN = datetime(2026, 8, 27, 8, 35, tzinfo=TAIPEI)


def _spec(tmp_path: Path) -> ExecutionSpec:
    return ExecutionSpec(
        spec_digest="a" * 64,
        project_root=(tmp_path / "checkout").absolute(),
        python_executable=(tmp_path / "checkout/.venv/bin/python").absolute(),
        approved_commit="b" * 40,
        approved_runtime_code_identity=f"git:{'b' * 40}:source-sha256:{'c' * 64}",
        approved_venv_tree_sha256="e" * 64,
        approved_at=PREOPEN - timedelta(days=1),
        reviewer_id="independent-reviewer",
        calendar_path=(tmp_path / "checkout/config/calendar.json").absolute(),
        calendar_sha256="d" * 64,
        environment_file=(tmp_path / "secrets/shadow.env").absolute(),
        artifact_root=(tmp_path / "runtime/artifacts").absolute(),
        records_root=(tmp_path / "runtime/records").absolute(),
        ownership_lock_root=(tmp_path / "runtime/locks").absolute(),
        symbol="2330",
    )


class FakePorts:
    def __init__(self) -> None:
        self.current = PREOPEN
        self.calls: list[str] = []
        self.trading_day = True
        self.acquire_error: Exception | None = None
        self.c0_returncode = 0
        self.c1_returncode = 0
        self.c1_status = "INSUFFICIENT_EVIDENCE"
        self.c0_error: Exception | None = None
        self.c1_admission_error: Exception | None = None
        self.inventory_error: Exception | None = None
        self.published: dict[str, object] | None = None

    def now(self) -> datetime:
        return self.current

    def acquire_ownership(self, **_) -> dict[str, object]:
        self.calls.append("acquire")
        if self.acquire_error:
            raise self.acquire_error
        return {"lock_sha256": "1" * 64}

    def calendar_evidence(self, **_) -> dict[str, object]:
        self.calls.append("calendar")
        return {"trading_day": self.trading_day, "calendar_sha256": "2" * 64}

    def verify_static_admission(self, **_) -> dict[str, object]:
        self.calls.append("static")
        return {"runtime_code_identity": "identity"}

    def run_c0(self, **_) -> ProcessResult:
        self.calls.append("run_c0")
        return ProcessResult("C0", self.c0_returncode, self.current, self.current)

    def verify_c0(self, **_) -> dict[str, object]:
        self.calls.append("verify_c0")
        if self.c0_error:
            raise self.c0_error
        return {"status": "READY_FOR_SESSION"}

    def verify_c1_admission(self, **_) -> dict[str, object]:
        self.calls.append("c1_admission")
        if self.c1_admission_error:
            raise self.c1_admission_error
        return {"reviewed": True}

    def run_c1(self, **_) -> ProcessResult:
        self.calls.append("run_c1")
        return ProcessResult("C1", self.c1_returncode, self.current, self.current)

    def verify_c1(self, **_) -> dict[str, object]:
        self.calls.append("verify_c1")
        return {"session_status": self.c1_status}

    def artifact_inventory(self, **_) -> dict[str, object]:
        self.calls.append("inventory")
        if self.inventory_error:
            raise self.inventory_error
        return {"ownership_lock": {"exists": True}}

    def publish_disposition(self, *, disposition, **_) -> dict[str, object]:
        self.calls.append("publish")
        self.published = dict(disposition)
        return {"artifact": "/fixture/disposition.json", "digest": "3" * 64}


def test_closed_date_locks_then_skips_without_any_child(tmp_path: Path) -> None:
    ports = FakePorts()
    ports.trading_day = False

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "SKIPPED_CLOSED_DATE"
    assert ports.calls == ["acquire", "calendar", "inventory", "publish"]
    assert result["process_results"] == []
    assert result["production_shadow_gate"] == "NOT_PASSED"


def test_existing_date_lock_never_runs_calendar_or_child(tmp_path: Path) -> None:
    ports = FakePorts()
    ports.acquire_error = OwnershipAlreadyHeld("MARKET_DATE_ALREADY_OWNED")

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "ALREADY_OWNED"
    assert result["reason_code"] == "MARKET_DATE_ALREADY_OWNED"
    assert ports.calls == ["acquire", "inventory", "publish"]


def test_c0_nonzero_is_terminal_and_never_retried(tmp_path: Path) -> None:
    ports = FakePorts()
    ports.c0_returncode = 2

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "C0_EXIT_NONZERO"
    assert ports.calls.count("run_c0") == 1
    assert "run_c1" not in ports.calls


def test_missing_reviewed_inputs_after_c0_never_starts_c1(tmp_path: Path) -> None:
    ports = FakePorts()
    ports.c1_admission_error = SupervisorBlocked("C1_REVIEW_APPROVAL_INVALID")

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "C1_REVIEW_APPROVAL_INVALID"
    assert ports.calls.count("run_c0") == 1
    assert "run_c1" not in ports.calls


def test_successful_sequence_is_exact_and_gate_remains_not_passed(
    tmp_path: Path,
) -> None:
    ports = FakePorts()

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "C1_TERMINAL"
    assert result["c1_session_status"] == "INSUFFICIENT_EVIDENCE"
    assert ports.calls == [
        "acquire",
        "calendar",
        "static",
        "run_c0",
        "verify_c0",
        "c1_admission",
        "run_c1",
        "verify_c1",
        "inventory",
        "publish",
    ]
    assert result["automatic_retry"] is False
    assert result["execution_authority"] is False
    assert result["execution_enabled"] is False
    assert result["production_shadow_gate"] == "NOT_PASSED"
    assert ports.published is not None
    assert ports.published["production_shadow_gate"] == "NOT_PASSED"


def test_c1_nonzero_is_not_retried_or_verified(tmp_path: Path) -> None:
    ports = FakePorts()
    ports.c1_returncode = 2

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "C1_EXIT_NONZERO"
    assert ports.calls.count("run_c1") == 1
    assert "verify_c1" not in ports.calls


def test_terminal_inventory_failure_downgrades_complete_to_blocked(
    tmp_path: Path,
) -> None:
    ports = FakePorts()
    ports.inventory_error = OSError("fixture")

    result = run_supervisor(spec=_spec(tmp_path), market_date=MARKET_DATE, ports=ports)

    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "TERMINAL_ARTIFACT_INVENTORY_FAILED"
    assert result["evidence"]["artifact_inventory"] == {
        "error_code": "INVENTORY_OSERROR"
    }
    assert ports.calls[-1] == "publish"


def test_command_plan_contains_only_exact_reviewed_entrypoints(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    plan = build_command_plan(spec, MARKET_DATE)

    assert plan.c0_argv[:2] == (
        str(spec.python_executable),
        "scripts/preflight_trade_management_shadow.py",
    )
    assert plan.c1_argv[:2] == (
        str(spec.python_executable),
        "scripts/run_trade_management_shadow_c1.py",
    )
    combined = " ".join((*plan.c0_argv, *plan.c1_argv))
    assert "--skip-provider-login" not in combined
    assert "--skip-rehearsal" not in combined
    assert " -c " not in f" {combined} "
    assert " -m " not in f" {combined} "
    assert "shell" not in combined
    assert plan.c1_argv[plan.c1_argv.index("--case") + 1] == "A"
    assert str(plan.paths.c0_artifact) in plan.c1_argv
    for flag in (
        "--preflight-artifact",
        "--entry-decision",
        "--thesis-draft",
        "--shadow-policy",
        "--risk-snapshot",
        "--input-approval",
        "--connection-session-id",
        "--records-root",
        "--output",
        "--case",
        "--subscribe-ack-timeout-seconds",
        "--preopen-wait-timeout-seconds",
    ):
        assert plan.c1_argv.count(flag) == 1


def test_ownership_lock_is_exclusive_and_retained(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec.ownership_lock_root.mkdir(parents=True, mode=0o700)
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )
    plan = build_command_plan(spec, MARKET_DATE)

    first = adapter.acquire_ownership(spec=spec, plan=plan, started_at=PREOPEN)

    assert plan.paths.ownership_lock.exists()
    assert plan.paths.ownership_lock.stat().st_mode & 0o777 == 0o600
    assert first["stale_lock_auto_removed"] is False
    with pytest.raises(OwnershipAlreadyHeld, match="MARKET_DATE_ALREADY_OWNED"):
        adapter.acquire_ownership(spec=spec, plan=plan, started_at=PREOPEN)
    assert plan.paths.ownership_lock.exists()


def test_lock_contender_disposition_cannot_claim_active_run_root(
    tmp_path: Path,
) -> None:
    spec = _spec(tmp_path)
    spec.artifact_root.mkdir(parents=True, mode=0o700)
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )
    plan = build_command_plan(spec, MARKET_DATE)
    disposition = {
        "status": "ALREADY_OWNED",
        "started_at": PREOPEN.isoformat(),
        "production_shadow_gate": "NOT_PASSED",
    }

    publication = adapter.publish_disposition(
        plan=plan,
        disposition=disposition,
    )

    published_path = Path(str(publication["artifact"]))
    assert published_path.is_file()
    assert published_path.parent.name == "lock_contenders"
    assert not plan.paths.run_root.exists()


def test_child_log_file_is_owner_only_and_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "child.log"

    with process_guard._open_owner_only_exclusive(path) as handle:
        handle.write(b"fixture\n")

    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        process_guard._open_owner_only_exclusive(path)


def test_environment_loader_requires_owner_only_distinct_data_only_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shadow.env"
    path.write_text(
        "\n".join(
            (
                "SHIOAJI_API_KEY=fixture-key",
                "SHIOAJI_SECRET=fixture-secret",
                "LOCAL_PAPER_DATABASE_URL=postgresql://local-paper",
                "TRADE_MANAGEMENT_SHADOW_DATABASE_URL=postgresql://shadow",
                "SJ_SIMULATION=true",
            )
        )
        + "\n"
    )
    path.chmod(0o600)

    environment = _load_minimal_child_environment(path)

    assert environment["SJ_SIMULATION"] == "true"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "HOME" not in environment
    assert set(environment) <= {
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TMPDIR",
        "SHIOAJI_API_KEY",
        "SHIOAJI_SECRET",
        "LOCAL_PAPER_DATABASE_URL",
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL",
        "SJ_SIMULATION",
        "PYTHONHASHSEED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "TZ",
    }


def test_secret_and_approval_spec_cannot_overlap_runtime_write_roots(
    tmp_path: Path,
) -> None:
    base = _spec(tmp_path)
    spec = replace(
        base,
        environment_file=base.artifact_root / "shadow.env",
    )

    with pytest.raises(
        SupervisorBlocked,
        match="PROTECTED_CONFIG_PATH_INSIDE_WRITABLE_ROOT",
    ):
        _require_runtime_path_separation(
            spec,
            spec_path=(tmp_path / "approval.json").absolute(),
        )

    overlapping = replace(base, records_root=base.artifact_root / "records")
    with pytest.raises(SupervisorBlocked, match="RUNTIME_WRITE_ROOTS_OVERLAP"):
        _require_runtime_path_separation(
            overlapping,
            spec_path=(tmp_path / "approval.json").absolute(),
        )


@pytest.mark.parametrize(
    "extra_line,mode,error_code",
    (
        ("UNREVIEWED=value", 0o600, "ENVIRONMENT_FILE_KEY_NOT_ALLOWED"),
        ("SJ_SIMULATION=false", 0o600, "PROVIDER_SIMULATION_MUST_BE_TRUE"),
        ("", 0o644, "ENVIRONMENT_FILE_MUST_BE_OWNER_ONLY"),
    ),
)
def test_environment_loader_fails_closed(
    tmp_path: Path,
    extra_line: str,
    mode: int,
    error_code: str,
) -> None:
    path = tmp_path / "shadow.env"
    lines = [
        "SHIOAJI_API_KEY=fixture-key",
        "SHIOAJI_SECRET=fixture-secret",
        "LOCAL_PAPER_DATABASE_URL=postgresql://same",
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL=postgresql://other",
    ]
    if extra_line:
        lines.append(extra_line)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(mode)

    with pytest.raises(SupervisorBlocked, match=error_code):
        _load_minimal_child_environment(path)


def test_environment_loader_rejects_same_dsn(tmp_path: Path) -> None:
    path = tmp_path / "shadow.env"
    path.write_text(
        "SHIOAJI_API_KEY=fixture-key\n"
        "SHIOAJI_SECRET=fixture-secret\n"
        "LOCAL_PAPER_DATABASE_URL=postgresql://same\n"
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL=postgresql://same\n"
    )
    path.chmod(0o600)

    with pytest.raises(SupervisorBlocked, match="SHADOW_DSN_MUST_BE_DEDICATED"):
        _load_minimal_child_environment(path)


def test_environment_loader_does_not_interpolate_parent_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("UNREVIEWED_SECRET", "must-not-expand")
    path = tmp_path / "shadow.env"
    path.write_text(
        "SHIOAJI_API_KEY=${UNREVIEWED_SECRET}\n"
        "SHIOAJI_SECRET=fixture-secret\n"
        "LOCAL_PAPER_DATABASE_URL=postgresql://local\n"
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL=postgresql://shadow\n"
    )
    path.chmod(0o600)

    environment = _load_minimal_child_environment(path)

    assert environment["SHIOAJI_API_KEY"] == "${UNREVIEWED_SECRET}"


def test_not_approved_spec_is_rejected_before_any_runtime_action(
    tmp_path: Path,
) -> None:
    path = tmp_path / "approval.json"
    unsigned = {
        "artifact_type": "TradeManagementShadowExternalExecutionApproval",
        "version": "trade-management-shadow-external-execution-v1",
        "approval_status": "NOT_APPROVED",
        "reviewed": False,
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    digest = _canonical_digest(unsigned)
    path.write_text(json.dumps({**unsigned, "spec_digest": digest}))
    path.with_suffix(".json.sha256").write_text(digest + "\n")
    path.chmod(0o600)
    path.with_suffix(".json.sha256").chmod(0o600)

    with pytest.raises(SupervisorBlocked, match="EXECUTION_SPEC_NOT_APPROVED"):
        load_approved_execution_spec(path)


def test_approved_spec_binds_installation_gate_digests_to_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / "approval.json"
    checkout = (tmp_path / "checkout").absolute()
    approved_files = {
        role: {
            "path": str(checkout / f"fixture/{role}"),
            "sha256": "1" * 64,
        }
        for role in REQUIRED_APPROVED_FILES
    }
    unsigned = {
        "artifact_type": "TradeManagementShadowExternalExecutionApproval",
        "version": "trade-management-shadow-external-execution-v1",
        "approval_status": "APPROVED_FOR_INSTALLATION",
        "reviewed": True,
        "reviewer_id": "independent-reviewer",
        "approved_at": PREOPEN.isoformat(),
        "approved_commit": "b" * 40,
        "approved_runtime_code_identity": f"git:{'b' * 40}:source-sha256:{'c' * 64}",
        "approved_venv_tree_sha256": "e" * 64,
        "symbol": "2330",
        "reviewed_calendar": {
            "path": str(checkout / "config/twse_calendar_2026.json"),
            "sha256": "d" * 64,
        },
        "locations": {
            "project_root": str(checkout),
            "environment_file": str((tmp_path / "secrets.env").absolute()),
            "artifact_root": str((tmp_path / "artifacts").absolute()),
            "records_root": str((tmp_path / "records").absolute()),
            "ownership_lock_root": str((tmp_path / "locks").absolute()),
        },
        "approved_files": approved_files,
        "installation_gates": {
            "provider_egress_inventory_digest": "2" * 64,
            "sandbox_denial_rehearsal_digest": "1" * 64,
            "codex_automation_pause_evidence_digest": "1" * 64,
            "cooperative_termination_disposition": "NO_AUTOMATIC_C1_SIGNAL",
        },
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    digest = _canonical_digest(unsigned)
    path.write_text(json.dumps({**unsigned, "spec_digest": digest}))
    path.with_suffix(".json.sha256").write_text(digest + "\n")
    path.chmod(0o600)
    path.with_suffix(".json.sha256").chmod(0o600)

    with pytest.raises(
        SupervisorBlocked,
        match="INSTALLATION_GATE_FILE_DIGEST_MISMATCH",
    ):
        load_approved_execution_spec(path)


def test_c1_admission_recomputes_review_approval_payload_digest(
    tmp_path: Path,
) -> None:
    spec = _spec(tmp_path)
    plan = build_command_plan(spec, MARKET_DATE)
    root = plan.paths.canonical_input_root
    root.mkdir(parents=True)
    source_digests: dict[str, str] = {}
    for role, filename in (
        ("entry_decision", "live_entry_decision.json"),
        ("thesis_draft", "trade_thesis_draft.json"),
        ("shadow_policy", "shadow_policy.json"),
        ("risk_snapshot", "risk_snapshot.json"),
    ):
        content = f"{role}\n".encode()
        (root / filename).write_bytes(content)
        source_digests[role] = hashlib.sha256(content).hexdigest()
    unsigned = {
        "artifact_type": "TradeManagementShadowInputReviewApproval",
        "approval_status": "APPROVED_FOR_CANONICAL_PROMOTION",
        "reviewed": True,
        "formal_c1_eligible": True,
        "market_date": MARKET_DATE.isoformat(),
        "runtime_code_identity": spec.approved_runtime_code_identity,
        "approved_sources": {
            role: {"filename": filename, "sha256": source_digests[role]}
            for role, filename in (
                ("entry_decision", "live_entry_decision.json"),
                ("thesis_draft", "trade_thesis_draft.json"),
                ("shadow_policy", "shadow_policy.json"),
                ("risk_snapshot", "risk_snapshot.json"),
            )
        },
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    digest = _canonical_digest(unsigned)
    tampered = {**unsigned, "reviewer_id": "tampered", "approval_digest": digest}
    approval_path = root / "review_approval.json"
    approval_path.write_text(json.dumps(tampered))
    approval_path.with_suffix(".json.sha256").write_text(digest + "\n")
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )

    with pytest.raises(
        SupervisorBlocked,
        match="ARTIFACT_CANONICAL_DIGEST_MISMATCH",
    ):
        adapter.verify_c1_admission(
            spec=spec,
            plan=plan,
            observed_at=PREOPEN,
        )


def test_c1_admission_accepts_only_digest_bound_reviewed_bundle(
    tmp_path: Path,
) -> None:
    spec = _spec(tmp_path)
    plan = build_command_plan(spec, MARKET_DATE)
    root = plan.paths.canonical_input_root
    root.mkdir(parents=True)
    source_digests: dict[str, str] = {}
    approved_sources: dict[str, dict[str, str]] = {}
    for role, filename in (
        ("entry_decision", "live_entry_decision.json"),
        ("thesis_draft", "trade_thesis_draft.json"),
        ("shadow_policy", "shadow_policy.json"),
        ("risk_snapshot", "risk_snapshot.json"),
    ):
        content = f"{role}\n".encode()
        (root / filename).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        source_digests[role] = digest
        approved_sources[role] = {"filename": filename, "sha256": digest}
    binding = {
        "session_id": plan.session_id,
        "symbol": spec.symbol,
        "risk_snapshot_provenance": {
            "captured_at": (PREOPEN - timedelta(minutes=4)).isoformat(),
            "session_id": plan.session_id,
            "symbol": spec.symbol,
            "market_date": MARKET_DATE.isoformat(),
        },
    }
    approval_digest = _write_digest_bound_json(
        root / "review_approval.json",
        {
            "artifact_type": "TradeManagementShadowInputReviewApproval",
            "version": "trade-management-shadow-input-approval-v1",
            "approval_status": "APPROVED_FOR_CANONICAL_PROMOTION",
            "reviewed": True,
            "formal_c1_eligible": True,
            "reviewer_id": "independent-reviewer",
            "reviewed_at": (PREOPEN - timedelta(minutes=3)).isoformat(),
            "attempt_id": "reviewed-attempt-01",
            "review_packet_digest": "f" * 64,
            "market_date": MARKET_DATE.isoformat(),
            "runtime_code_identity": spec.approved_runtime_code_identity,
            "binding": binding,
            "approved_sources": approved_sources,
            "execution_authority": False,
            "execution_enabled": False,
            "evidence_only": True,
            "production_shadow_gate": "NOT_PASSED",
        },
        digest_field="approval_digest",
    )
    bundle_digest = _write_digest_bound_json(
        root / "bundle_manifest.json",
        {
            "artifact_type": "TradeManagementShadowCanonicalInputBundle",
            "version": "trade-management-shadow-canonical-input-bundle-v1",
            "market_date": MARKET_DATE.isoformat(),
            "attempt_id": "reviewed-attempt-01",
            "approval_digest": approval_digest,
            "review_packet_digest": "f" * 64,
            "runtime_code_identity": spec.approved_runtime_code_identity,
            "file_digests": source_digests,
            "execution_authority": False,
            "execution_enabled": False,
            "evidence_only": True,
            "production_shadow_gate": "NOT_PASSED",
        },
        digest_field="bundle_digest",
    )
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )

    evidence = adapter.verify_c1_admission(
        spec=spec,
        plan=plan,
        observed_at=PREOPEN,
    )

    assert evidence["reviewed"] is True
    assert evidence["review_approval_digest"] == approval_digest
    assert evidence["bundle_manifest_digest"] == bundle_digest


def test_runtime_is_reverified_immediately_before_each_entrypoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    spec = _spec(tmp_path)
    plan = build_command_plan(spec, MARKET_DATE)
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )
    adapter._child_environment = {"TZ": "Asia/Taipei"}
    checks: list[str] = []
    runs: list[str] = []
    monkeypatch.setattr(
        adapter,
        "_verify_runtime_unchanged",
        lambda _: checks.append("runtime") or (spec.approved_commit, "identity"),
    )
    monkeypatch.setattr(
        adapter_module,
        "run_c0_entrypoint",
        lambda **_: runs.append("C0")
        or ProcessResult("C0", 0, PREOPEN, PREOPEN),
    )
    monkeypatch.setattr(
        adapter_module,
        "run_c1_entrypoint",
        lambda **_: runs.append("C1")
        or ProcessResult("C1", 0, PREOPEN, PREOPEN),
    )

    adapter.run_c0(spec=spec, plan=plan)
    adapter.run_c1(spec=spec, plan=plan)

    assert checks == ["runtime", "runtime"]
    assert runs == ["C0", "C1"]


def test_venv_tree_digest_changes_with_content_and_symlink_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".venv"
    (root / "lib").mkdir(parents=True)
    package = root / "lib/package.py"
    package.write_text("value = 1\n")
    (root / "python").symlink_to("lib/package.py")
    before = _venv_tree_digest(root)

    package.write_text("value = 2\n")
    after_content = _venv_tree_digest(root)
    (root / "python").unlink()
    (root / "python").symlink_to("lib/other.py")
    after_symlink = _venv_tree_digest(root)

    assert len({before, after_content, after_symlink}) == 3


def test_c1_terminal_artifact_rejects_execution_authority(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    plan = build_command_plan(spec, MARKET_DATE)
    plan.paths.run_root.mkdir(parents=True)
    plan.paths.c0_artifact.write_text("c0\n")
    session_digest = "e" * 64
    value = {
        "artifact_type": "TradeManagementC1SessionEvidence",
        "preflight_artifact": str(plan.paths.c0_artifact.resolve()),
        "preflight_sha256": hashlib.sha256(b"c0\n").hexdigest(),
        "input_approval_artifact": str(
            (plan.paths.canonical_input_root / "review_approval.json").resolve()
        ),
        "session_evidence": {
            "session_id": plan.session_id,
            "status": "INSUFFICIENT_EVIDENCE",
            "execution_authority": True,
            "execution_enabled": False,
            "evidence_only": True,
            "production_shadow_gate": "NOT_PASSED",
        },
        "session_evidence_digest": session_digest,
        "production_shadow_gate": "NOT_PASSED",
    }
    plan.paths.c1_artifact.write_text(json.dumps(value))
    plan.paths.c1_artifact.with_suffix(".json.sha256").write_text(
        session_digest + "\n"
    )
    adapter = LocalSupervisorAdapter(
        spec_path=tmp_path / "spec.json",
        spec=spec,
        approved_files={},
    )

    with pytest.raises(SupervisorBlocked, match="C1_TERMINAL_ARTIFACT_INVALID"):
        adapter.verify_c1(spec=spec, plan=plan)


def test_process_guard_uses_exact_git_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(argv, *, cwd, timeout):
        calls.append((list(argv), cwd))
        return SimpleNamespace(
            args=argv,
            returncode=0,
            stdout="abc123\n",
            stderr="",
        )

    monkeypatch.setattr(git_guard, "_run_git", fake_run)

    assert git_guard.run_git_head(tmp_path) == "abc123"
    assert git_guard.run_git_status(tmp_path) == "abc123\n"
    assert calls == [
        (["/usr/bin/git", "rev-parse", "HEAD"], tmp_path),
        (["/usr/bin/git", "status", "--porcelain", "--untracked-files=all"], tmp_path),
    ]
    environment = git_guard._git_environment()
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"
    assert environment["GIT_CONFIG_VALUE_0"] == "false"


def test_process_guard_denies_changed_rehearsal_target_without_subprocess(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called = False

    def forbidden(*_, **__):
        nonlocal called
        called = True

    monkeypatch.setattr(process_guard, "_run_captured_allowed", forbidden)
    project_root = Path(__file__).resolve().parents[1]

    with pytest.raises(RuntimeError, match="C0_REHEARSAL_ARGV_DENIED"):
        process_guard.run_c0_rehearsal(
            python_executable=str(project_root / ".venv/bin/python"),
            project_root=project_root,
            targets=("tests/not-reviewed.py",),
        )
    assert called is False


def test_c0_internal_children_receive_only_role_specific_environment(
    monkeypatch,
) -> None:
    for key, value in {
        "SHIOAJI_API_KEY": "api-key",
        "SHIOAJI_SECRET": "secret",
        "LOCAL_PAPER_DATABASE_URL": "local-dsn",
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL": "shadow-dsn",
        "TZ": "Asia/Taipei",
    }.items():
        monkeypatch.setenv(key, value)

    provider = process_guard._selected_environment(process_guard.PROVIDER_ENV_KEYS)
    rehearsal = process_guard._selected_environment(
        process_guard.SAFE_CHILD_ENV_KEYS
    )

    assert provider["SHIOAJI_API_KEY"] == "api-key"
    assert provider["SHIOAJI_SECRET"] == "secret"
    assert "LOCAL_PAPER_DATABASE_URL" not in provider
    assert "TRADE_MANAGEMENT_SHADOW_DATABASE_URL" not in provider
    assert "SHIOAJI_API_KEY" not in rehearsal
    assert "SHIOAJI_SECRET" not in rehearsal
    assert "LOCAL_PAPER_DATABASE_URL" not in rehearsal
    assert "TRADE_MANAGEMENT_SHADOW_DATABASE_URL" not in rehearsal


def test_c0_timeout_sends_sigterm_to_process_group_without_sigkill(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    spec = replace(
        _spec(tmp_path),
        project_root=project_root,
        python_executable=project_root / ".venv/bin/python",
    )
    plan = build_command_plan(spec, MARKET_DATE)
    plan.paths.run_root.mkdir(parents=True)
    signals: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 4321

        def __init__(self) -> None:
            self.wait_count = 0

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count == 1:
                raise process_guard.subprocess.TimeoutExpired("fixture", timeout)
            return -15

    monkeypatch.setattr(
        process_guard.subprocess,
        "Popen",
        lambda *_, **__: FakeProcess(),
    )
    monkeypatch.setattr(
        process_guard.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )
    monkeypatch.setattr(process_guard, "_process_group_exists", lambda _: False)

    with pytest.raises(SupervisorBlocked, match="C0_TIMEOUT_TERMINATED"):
        process_guard.run_c0_entrypoint(
            plan=plan,
            project_root=project_root,
            environment={"TZ": "Asia/Taipei"},
            now=lambda: PREOPEN,
        )

    assert signals == [(4321, process_guard.signal.SIGTERM)]
    source = Path(process_guard.__file__).read_text(encoding="utf-8")
    assert "SIGKILL" not in source
    assert ".kill(" not in source


def test_c0_internal_child_timeout_never_falls_back_to_unbounded_wait(
    monkeypatch,
    tmp_path: Path,
) -> None:
    signals: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 5432
        returncode = None

        def __init__(self) -> None:
            self.communicate_timeouts: list[int] = []

        def communicate(self, timeout=None):
            self.communicate_timeouts.append(timeout)
            raise process_guard.subprocess.TimeoutExpired("fixture", timeout)

    process = FakeProcess()
    monkeypatch.setattr(
        process_guard.subprocess,
        "Popen",
        lambda *_, **__: process,
    )
    monkeypatch.setattr(
        process_guard.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    with pytest.raises(RuntimeError, match="REHEARSAL_TIMEOUT_TERMINATION_PENDING"):
        process_guard._run_captured_allowed(
            "REHEARSAL",
            ["fixture"],
            cwd=tmp_path,
            timeout=7,
            env={},
        )

    assert process.communicate_timeouts == [7, process_guard.TERMINATION_GRACE_SECONDS]
    assert signals == [(5432, process_guard.signal.SIGTERM)]


def test_git_timeout_never_falls_back_to_unbounded_wait(
    monkeypatch,
    tmp_path: Path,
) -> None:
    signals: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 6543
        returncode = None

        def __init__(self) -> None:
            self.communicate_timeouts: list[int] = []

        def communicate(self, timeout=None):
            self.communicate_timeouts.append(timeout)
            raise git_guard.subprocess.TimeoutExpired("fixture", timeout)

    process = FakeProcess()
    monkeypatch.setattr(git_guard.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(
        git_guard.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    with pytest.raises(RuntimeError, match="GIT_TIMEOUT_TERMINATION_PENDING"):
        git_guard._run_git(
            [git_guard.GIT_EXECUTABLE, "rev-parse", "HEAD"],
            cwd=tmp_path,
            timeout=3,
        )

    assert process.communicate_timeouts == [3, git_guard.TERMINATION_GRACE_SECONDS]
    assert signals == [(6543, git_guard.signal.SIGTERM)]


def test_supervisor_import_and_subprocess_boundaries() -> None:
    project_root = Path(__file__).resolve().parents[1]
    files = {
        "core": project_root / "runtime/trade_management_external_supervisor.py",
        "adapters": project_root / "runtime/trade_management_external_adapters.py",
        "process": project_root / "runtime/trade_management_external_process.py",
        "git": project_root / "runtime/trade_management_external_git.py",
        "script": project_root
        / "scripts/run_trade_management_shadow_external_supervisor.py",
        "c0": project_root / "scripts/preflight_trade_management_shadow.py",
        "identity": project_root / "runtime/trade_management_runtime_identity.py",
    }
    forbidden_roots = {
        "trading",
        "simulation",
        "position",
        "shioaji",
        "psycopg",
        "psycopg_pool",
    }
    subprocess_importers: set[str] = set()
    for role, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        if role in {"core", "adapters", "process", "script", "identity"}:
            assert imported_roots.isdisjoint(forbidden_roots), (
                role,
                imported_roots,
            )
        if "subprocess" in imported_roots:
            subprocess_importers.add(role)
    assert subprocess_importers == {"git", "process"}


def test_input_workflow_import_does_not_load_shadow_process_capability() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; "
        "import scripts.prepare_trade_management_shadow_inputs; "
        "names=('runtime.trade_management_external_process',"
        "'runtime.trade_management_external_supervisor',"
        "'runtime.trade_management_external_adapters'); "
        "print([name for name in names if name in sys.modules])"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "[]"


def test_deployment_material_is_explicitly_disabled_and_unapproved() -> None:
    project_root = Path(__file__).resolve().parents[1]
    deployment = project_root / "architecture/deployment"
    approval = json.loads(
        (deployment / "trade_management_shadow_external_execution_approval.template.json")
        .read_text(encoding="utf-8")
    )
    plist = (
        deployment / "com.stevehuang.trade-management-shadow.plist.template"
    ).read_text(encoding="utf-8")
    sandbox = (
        deployment / "trade_management_shadow_external.sb.template"
    ).read_text(encoding="utf-8")

    assert approval["approval_status"] == "NOT_APPROVED"
    assert approval["reviewed"] is False
    assert approval["production_shadow_gate"] == "NOT_PASSED"
    assert "<key>Disabled</key>\n  <true/>" in plist
    assert "NOT INSTALLED" in plist
    assert "(deny network*)" in sandbox
    assert "NOT INSTALLED" in sandbox


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_digest_bound_json(
    path: Path,
    unsigned: dict[str, object],
    *,
    digest_field: str,
) -> str:
    digest = _canonical_digest(unsigned)
    path.write_text(json.dumps({**unsigned, digest_field: digest}))
    path.with_suffix(".json.sha256").write_text(digest + "\n")
    return digest
