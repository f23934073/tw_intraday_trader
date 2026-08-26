"""Fail-closed activation contract for the fresh-r3 raw price coverage scan."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.domain import canonical_json
from backtest.price_coverage_initialization import FRESH_LINEAGE_MODE


ACTIVATION_SCHEMA_VERSION = "price_coverage_scan_activation_v1"
ACTIVATION_STATUS = "AUTHORIZED_FOR_HISTORICAL_KBAR_COVERAGE_SCAN"
ACTIVE_JOB_KIND = "PRICE_COVERAGE_SCAN"
TARGET_DIGEST = "61dc598c47e3168f67c36862606d12b3bad2fce709e58d1a7543e663c0453827"
QUARANTINE_DIGEST = "f44d1e87a81fd9aedded1d7bc1a42e2032d564e437431fe47f5d62fcf3db27af"
REQUEST_DIGEST = "f04d7e78ba5c79390bf471c53741efbadf061aafd89abe5682654a9594047256"
ORDER_DIGEST = "470032790f69f25a98a61d13686598776dcc1d8819379427113ebcc44305331e"
JOB_ID = "dataset-download-r3-e9981217a1d36c213e121db3ebaa26e7"
TARGET_DATASET_ID = "dataset-r3-e9981217a1d36c213e121db3ebaa26e7"
TARGET_COUNT = 2781
PROVIDER_ENVIRONMENT_IDENTITY = "shioaji:1.7.2:simulation=true"
TARGET_ARTIFACT_NAME = "price_coverage_target_order_v1_2026-08-26-r3.json"
QUARANTINE_ARTIFACT_NAME = (
    "price_coverage_scan_configuration_v2_2026-08-26-r3-rev2.json"
)
ACTIVATION_ARTIFACT_NAME = "price_coverage_scan_activation_v1_2026-08-26-r3.json"
PINNED_ACTIVATION_SOURCE_PATHS = (
    "market_data/provider.py",
    "market_data/models.py",
    "premarket/artifacts.py",
    "premarket/models.py",
    "backtest/domain.py",
    "backtest/repository.py",
    "backtest/postgres_repository.py",
    "backtest/sqlite_repository.py",
    "backtest/dataset.py",
    "backtest/historical_download.py",
    "backtest/price_coverage_initialization.py",
    "backtest/price_coverage_activation.py",
    "backtest/price_coverage_repository.py",
    "scripts/register_price_coverage_r3_activation.py",
    "scripts/run_price_coverage_r3_scan.py",
    "scripts/download_backtest_history.py",
    "config/backtest.py",
)
_EXECUTION_LOCKS = {
    "dataset_materialization_allowed": False,
    "formal_coverage_audit_allowed": False,
    "population_freeze_allowed": False,
    "outcome_generation_allowed": False,
    "holdout_allowed": False,
    "order_submission_allowed": False,
    "trade_subscription_allowed": False,
}


class PriceCoverageActivationError(RuntimeError):
    """Activation evidence or its runtime preconditions failed closed."""


@dataclass(frozen=True)
class VerifiedPriceCoverageActivation:
    activation_digest: str
    job_id: str
    request_digest: str
    provider_environment_identity: str


def build_price_coverage_activation(
    *,
    job: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    authorized_at: datetime,
    authorized_by: str,
) -> dict[str, Any]:
    """Build activation authority only for the exact untouched r3 job."""

    owner = _require_exact_text(authorized_by, "authorized_by")
    if authorized_at.utcoffset() != timedelta(hours=8):
        raise PriceCoverageActivationError(
            "price coverage authorization must use Asia/Taipei offset"
        )
    _verify_prepared_or_bound_job(job, activation_digest=None)
    return {
        "artifact_id": "price-coverage-scan-activation-v1-2026-08-26-r3",
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "status": ACTIVATION_STATUS,
        "authorized_at": authorized_at.isoformat(),
        "authorized_by": owner,
        "lineage": {
            "target_manifest_canonical_sha256": TARGET_DIGEST,
            "quarantine_revision_canonical_sha256": QUARANTINE_DIGEST,
            "request_canonical_sha256": REQUEST_DIGEST,
            "target_order_canonical_sha256": ORDER_DIGEST,
            "predecessor_checkpoint_inheritance_allowed": False,
            "summary_merge_with_r0_r1_r2_allowed": False,
        },
        "job": {
            "job_id": JOB_ID,
            "prepared_job_kind": "PRICE_COVERAGE_PREPARED",
            "active_job_kind": ACTIVE_JOB_KIND,
            "target_dataset_id": TARGET_DATASET_ID,
            "target_count": TARGET_COUNT,
            "start_target_index": 0,
        },
        "source_snapshot": dict(source_snapshot),
        "provider_environment": {
            "provider": "shioaji",
            "adapter_class": "market_data.provider.ShioajiProvider",
            "identity": PROVIDER_ENVIRONMENT_IDENTITY,
            "historical_query": "Shioaji.kbars",
            "simulation": True,
            "subscribe_trade": False,
        },
        "activation": {
            "scan_authorized": True,
            "historical_kbar_requests_allowed": True,
            "generic_resume_allowed": False,
            "exact_digest_required_on_every_resume": True,
            "repository_wide_lock_required_for_process_lifetime": True,
        },
        "execution_lock": dict(_EXECUTION_LOCKS),
        "scope": {
            "purpose": "RAW_PRICE_COVERAGE_INVENTORY_ONLY",
            "research_eligible": False,
            "price_payload_inspection_allowed": False,
            "return_or_pnl_read_allowed": False,
            "outcome_read_allowed": False,
        },
    }


def verify_price_coverage_activation(
    *,
    activation: Mapping[str, Any],
    activation_digest: str,
    target_manifest: Mapping[str, Any],
    quarantine_revision: Mapping[str, Any],
    repository: Any,
    source_root: Path,
) -> VerifiedPriceCoverageActivation:
    """Verify every authority and lineage pin before provider construction."""

    _require_sha256(activation_digest, "activation digest")
    if _digest(activation) != activation_digest:
        raise PriceCoverageActivationError("activation artifact digest mismatch")
    if _digest(target_manifest) != TARGET_DIGEST:
        raise PriceCoverageActivationError("r3 target manifest digest mismatch")
    if _digest(quarantine_revision) != QUARANTINE_DIGEST:
        raise PriceCoverageActivationError("r3 quarantine revision digest mismatch")
    if set(activation) != {
        "artifact_id",
        "schema_version",
        "change_policy",
        "status",
        "authorized_at",
        "authorized_by",
        "lineage",
        "job",
        "source_snapshot",
        "provider_environment",
        "activation",
        "execution_lock",
        "scope",
    }:
        raise PriceCoverageActivationError("activation artifact schema is not exact")
    if (
        activation.get("artifact_id")
        != "price-coverage-scan-activation-v1-2026-08-26-r3"
        or activation.get("schema_version") != ACTIVATION_SCHEMA_VERSION
        or activation.get("change_policy") != "IMMUTABLE_NEW_ARTIFACT_REQUIRED"
        or activation.get("status") != ACTIVATION_STATUS
    ):
        raise PriceCoverageActivationError("activation artifact identity is invalid")
    _require_exact_text(activation.get("authorized_by"), "authorized_by")
    try:
        authorized_at = datetime.fromisoformat(str(activation["authorized_at"]))
    except (KeyError, ValueError) as error:
        raise PriceCoverageActivationError("activation timestamp is invalid") from error
    if authorized_at.utcoffset() != timedelta(hours=8):
        raise PriceCoverageActivationError(
            "activation timestamp must use Asia/Taipei offset"
        )
    expected_lineage = {
        "target_manifest_canonical_sha256": TARGET_DIGEST,
        "quarantine_revision_canonical_sha256": QUARANTINE_DIGEST,
        "request_canonical_sha256": REQUEST_DIGEST,
        "target_order_canonical_sha256": ORDER_DIGEST,
        "predecessor_checkpoint_inheritance_allowed": False,
        "summary_merge_with_r0_r1_r2_allowed": False,
    }
    if activation.get("lineage") != expected_lineage:
        raise PriceCoverageActivationError("activation lineage is not exact")
    if activation.get("job") != {
        "job_id": JOB_ID,
        "prepared_job_kind": "PRICE_COVERAGE_PREPARED",
        "active_job_kind": ACTIVE_JOB_KIND,
        "target_dataset_id": TARGET_DATASET_ID,
        "target_count": TARGET_COUNT,
        "start_target_index": 0,
    }:
        raise PriceCoverageActivationError("activation job binding is not exact")
    if activation.get("provider_environment") != {
        "provider": "shioaji",
        "adapter_class": "market_data.provider.ShioajiProvider",
        "identity": PROVIDER_ENVIRONMENT_IDENTITY,
        "historical_query": "Shioaji.kbars",
        "simulation": True,
        "subscribe_trade": False,
    }:
        raise PriceCoverageActivationError("activation provider contract is not exact")
    if activation.get("activation") != {
        "scan_authorized": True,
        "historical_kbar_requests_allowed": True,
        "generic_resume_allowed": False,
        "exact_digest_required_on_every_resume": True,
        "repository_wide_lock_required_for_process_lifetime": True,
    }:
        raise PriceCoverageActivationError("activation permission set is invalid")
    if activation.get("execution_lock") != _EXECUTION_LOCKS:
        raise PriceCoverageActivationError("downstream execution locks are invalid")
    if activation.get("scope") != {
        "purpose": "RAW_PRICE_COVERAGE_INVENTORY_ONLY",
        "research_eligible": False,
        "price_payload_inspection_allowed": False,
        "return_or_pnl_read_allowed": False,
        "outcome_read_allowed": False,
    }:
        raise PriceCoverageActivationError("activation scope is invalid")
    _verify_target_manifest(target_manifest)
    if quarantine_revision.get("status") != (
        "QUARANTINED_PREPARED_JOB_SCAN_NOT_AUTHORIZED"
    ):
        raise PriceCoverageActivationError("r3 quarantine revision status drifted")
    _verify_git_source_snapshot(
        source_root=source_root,
        snapshot=activation.get("source_snapshot"),
        required_paths=PINNED_ACTIVATION_SOURCE_PATHS,
    )
    job = repository.get_job(JOB_ID)
    _verify_prepared_or_bound_job(job, activation_digest=activation_digest)
    if repository.list_history_partitions(JOB_ID) and job["kind"] == (
        "PRICE_COVERAGE_PREPARED"
    ):
        raise PriceCoverageActivationError(
            "PREPARED r3 job unexpectedly contains history partitions"
        )
    if job.get("resource_id") is not None:
        raise PriceCoverageActivationError("r3 scan job unexpectedly references a Dataset")
    try:
        repository.get_dataset(TARGET_DATASET_ID)
    except KeyError:
        pass
    else:
        raise PriceCoverageActivationError("r3 target Dataset already exists")
    return VerifiedPriceCoverageActivation(
        activation_digest=activation_digest,
        job_id=JOB_ID,
        request_digest=REQUEST_DIGEST,
        provider_environment_identity=PROVIDER_ENVIRONMENT_IDENTITY,
    )


def _verify_prepared_or_bound_job(
    job: Mapping[str, Any],
    *,
    activation_digest: str | None,
) -> None:
    if job.get("job_id") != JOB_ID or _digest(job.get("request")) != REQUEST_DIGEST:
        raise PriceCoverageActivationError("r3 job identity or request digest drifted")
    request = job["request"]
    if (
        request.get("lineage_mode") != FRESH_LINEAGE_MODE
        or request.get("coverage_scan_mode") is not True
        or request.get("target_dataset_id") != TARGET_DATASET_ID
        or request.get("target_order_canonical_sha256") != ORDER_DIGEST
        or len(request.get("instruments", [])) != TARGET_COUNT
    ):
        raise PriceCoverageActivationError("r3 job request contract drifted")
    if job.get("kind") == "PRICE_COVERAGE_PREPARED":
        if (
            job.get("status") != "PREPARED"
            or float(job.get("progress", -1.0)) != 0.0
            or job.get("resource_id") is not None
            or job.get("error_message") is not None
            or job.get("progress_message")
            != (
                "Fresh r3 prepared; generic Kbar resume prohibited; "
                "dedicated activation required"
            )
        ):
            raise PriceCoverageActivationError("r3 PREPARED job state drifted")
        return
    if activation_digest is None or job.get("kind") != ACTIVE_JOB_KIND:
        raise PriceCoverageActivationError("r3 job is neither PREPARED nor dedicated scan")
    if job.get("status") not in {"QUEUED", "RUNNING", "PAUSED", "SCAN_COMPLETE"}:
        raise PriceCoverageActivationError("r3 dedicated scan status is invalid")
    marker = f"[PRICE_COVERAGE_ACTIVATION={activation_digest}]"
    if not str(job.get("progress_message") or "").startswith(marker):
        raise PriceCoverageActivationError("r3 job activation binding drifted")


def _verify_target_manifest(target: Mapping[str, Any]) -> None:
    rows = target.get("targets")
    if not isinstance(rows, list) or len(rows) != TARGET_COUNT:
        raise PriceCoverageActivationError("r3 target manifest count drifted")
    if [row.get("target_index") for row in rows] != list(range(TARGET_COUNT)):
        raise PriceCoverageActivationError("r3 target indices are not contiguous")
    symbols = [str(row.get("symbol") or "") for row in rows]
    if symbols != sorted(symbols) or len(set(symbols)) != TARGET_COUNT:
        raise PriceCoverageActivationError("r3 target order or uniqueness drifted")
    if _digest(rows) != ORDER_DIGEST:
        raise PriceCoverageActivationError("r3 target-order digest drifted")


def _verify_git_source_snapshot(
    *,
    source_root: Path,
    snapshot: object,
    required_paths: Sequence[str],
) -> None:
    if not isinstance(snapshot, Mapping):
        raise PriceCoverageActivationError("activation source snapshot is missing")
    if set(snapshot) != {
        "repository_commit",
        "repository_tree_oid",
        "git_object_format",
        "pinned_source_paths_clean",
        "repository_worktree_clean",
        "files",
    }:
        raise PriceCoverageActivationError("activation source snapshot schema is not exact")
    commit = _require_exact_text(
        snapshot.get("repository_commit"),
        "activation source commit",
    )
    if _git(source_root, "cat-file", "-t", commit) != "commit":
        raise PriceCoverageActivationError("activation source commit is unavailable")
    if snapshot.get("repository_tree_oid") != _git(
        source_root, "rev-parse", f"{commit}^{{tree}}"
    ):
        raise PriceCoverageActivationError("activation source tree drifted")
    if snapshot.get("pinned_source_paths_clean") is not True:
        raise PriceCoverageActivationError("activation source paths were not frozen clean")
    if snapshot.get("git_object_format") != _git(
        source_root, "rev-parse", "--show-object-format"
    ):
        raise PriceCoverageActivationError("activation Git object format drifted")
    if snapshot.get("repository_worktree_clean") is not False:
        raise PriceCoverageActivationError(
            "activation source snapshot worktree declaration is invalid"
        )
    entries = snapshot.get("files")
    if not isinstance(entries, list):
        raise PriceCoverageActivationError("activation source file inventory is invalid")
    by_path = {entry.get("path"): entry for entry in entries if isinstance(entry, Mapping)}
    if set(by_path) != set(required_paths) or len(entries) != len(required_paths):
        raise PriceCoverageActivationError("activation source path set is not exact")
    for relative in required_paths:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise PriceCoverageActivationError("activation source path is unsafe")
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", relative],
            cwd=source_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if status:
            raise PriceCoverageActivationError(
                f"activation source path is dirty: {relative}"
            )
        working = (source_root / relative).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=source_root,
            check=True,
            capture_output=True,
        ).stdout
        entry = by_path[relative]
        if set(entry) != {"path", "git_blob_oid", "content_sha256"}:
            raise PriceCoverageActivationError(
                f"activation source entry schema drifted: {relative}"
            )
        if working != committed:
            raise PriceCoverageActivationError(
                f"activation source is not reconstructable: {relative}"
            )
        if entry.get("content_sha256") != hashlib.sha256(working).hexdigest():
            raise PriceCoverageActivationError(
                f"activation source content digest drifted: {relative}"
            )
        if entry.get("git_blob_oid") != _git(
            source_root, "rev-parse", f"{commit}:{relative}"
        ):
            raise PriceCoverageActivationError(
                f"activation source Git blob drifted: {relative}"
            )


def _git(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise PriceCoverageActivationError("activation Git verification failed") from error


def _require_sha256(value: object, label: str) -> str:
    resolved = str(value)
    if len(resolved) != 64 or any(
        character not in "0123456789abcdef" for character in resolved
    ):
        raise PriceCoverageActivationError(f"{label} must be lowercase SHA-256")
    return resolved


def _require_exact_text(value: object, label: str) -> str:
    resolved = str(value)
    if not resolved or resolved != resolved.strip():
        raise PriceCoverageActivationError(f"{label} must be canonical non-empty text")
    return resolved


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
