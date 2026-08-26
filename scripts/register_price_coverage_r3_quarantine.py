"""Publish append-only metadata evidence for the fail-closed fresh-r3 job."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.application import BacktestApplicationService
from backtest.domain import canonical_json
from backtest.price_coverage_initialization import (
    PREPARED_JOB_KIND,
    PREPARED_JOB_STATUS,
    PREPARED_PROGRESS_MESSAGE,
    PriceCoverageInitializationError,
    assert_no_secret_values,
    locked_artifact_store,
)


ACQUISITION_ROOT = PROJECT_ROOT / "research/institutional_evaluation/acquisition"
TARGET_NAME = "price_coverage_target_order_v1_2026-08-26-r3.json"
ORIGINAL_CONFIG_NAME = "price_coverage_scan_configuration_v2_2026-08-26-r3.json"
REVISION_NAME = "price_coverage_scan_configuration_v2_2026-08-26-r3-rev2.json"
TARGET_DIGEST = "61dc598c47e3168f67c36862606d12b3bad2fce709e58d1a7543e663c0453827"
ORIGINAL_CONFIG_DIGEST = (
    "a970a91d22501f4ec670d2c3e40e7ac71c9405ce9031c881bb639034f8c29c5b"
)
REQUEST_DIGEST = "f04d7e78ba5c79390bf471c53741efbadf061aafd89abe5682654a9594047256"
ORDER_DIGEST = "470032790f69f25a98a61d13686598776dcc1d8819379427113ebcc44305331e"
JOB_ID = "dataset-download-r3-e9981217a1d36c213e121db3ebaa26e7"
TARGET_DATASET_ID = "dataset-r3-e9981217a1d36c213e121db3ebaa26e7"
TARGET_COUNT = 2781
POST_HOC_SOURCE_PATHS = (
    "backtest/price_coverage_initialization.py",
    "scripts/create_price_coverage_r3_job.py",
    "scripts/quarantine_price_coverage_r3_job.py",
    "scripts/register_price_coverage_r3_quarantine.py",
    "backtest/historical_download.py",
    "scripts/download_backtest_history.py",
)


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _post_hoc_source_snapshot() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative in POST_HOC_SOURCE_PATHS:
        path = PROJECT_ROOT / relative
        content = path.read_bytes()
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
        ).returncode == 0
        status = subprocess.run(
            ["git", "status", "--short", "--", relative],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        files.append(
            {
                "path": relative,
                "post_hoc_content_sha256": hashlib.sha256(content).hexdigest(),
                "git_tracked_at_revision": tracked,
                "git_status_at_revision": status or "CLEAN",
                "attribution_to_initial_executed_bytes": "NOT_PROVEN",
            }
        )
    return {
        "classification": "POST_HOC_ONLY_NOT_GIT_RECONSTRUCTABLE",
        "reproducible_from_git": False,
        "files": files,
    }


def _require_exact_job(repository: Any) -> dict[str, Any]:
    job = repository.get_job(JOB_ID)
    if (
        job["job_id"] != JOB_ID
        or job["kind"] != PREPARED_JOB_KIND
        or job["status"] != PREPARED_JOB_STATUS
        or float(job["progress"]) != 0.0
        or job["progress_message"] != PREPARED_PROGRESS_MESSAGE
        or job["resource_id"] is not None
        or job["error_message"] is not None
        or _digest(job["request"]) != REQUEST_DIGEST
        or job["request"].get("lineage_mode") != "FRESH_R3_NO_CHECKPOINT_REUSE"
        or job["request"].get("coverage_scan_mode") is not True
        or job["request"].get("target_dataset_id") != TARGET_DATASET_ID
        or job["request"].get("target_order_canonical_sha256") != ORDER_DIGEST
        or len(job["request"].get("instruments", [])) != TARGET_COUNT
        or "retry_symbol" in job["request"]
    ):
        raise PriceCoverageInitializationError(
            "Fresh r3 prepared job metadata does not match the quarantine contract"
        )
    if repository.list_history_partitions(JOB_ID):
        raise PriceCoverageInitializationError(
            "Fresh r3 prepared job unexpectedly has history partitions"
        )
    try:
        repository.get_dataset(TARGET_DATASET_ID)
    except KeyError:
        pass
    else:
        raise PriceCoverageInitializationError(
            "Fresh r3 target Dataset unexpectedly exists"
        )
    return job


def _build_revision(
    *,
    target: dict[str, Any],
    original: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_id": "price-coverage-scan-configuration-v2-2026-08-26-r3-rev2",
        "schema_version": "price_coverage_scan_configuration_v2",
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "status": "QUARANTINED_PREPARED_JOB_SCAN_NOT_AUTHORIZED",
        "registered_at": str(job["updated_at"]),
        "supersedes_for_activation": {
            "artifact_id": original["artifact_id"],
            "canonical_sha256": ORIGINAL_CONFIG_DIGEST,
            "disposition": (
                "HISTORICAL_REGISTRATION_EVIDENCE_ONLY_NOT_ACTIVATION_AUTHORITY"
            ),
        },
        "lineage": {
            "mode": "FRESH_RESTART_NO_CHECKPOINT_INHERITANCE",
            "target_manifest_artifact_id": target["artifact_id"],
            "target_manifest_canonical_sha256": TARGET_DIGEST,
            "target_order_canonical_sha256": ORDER_DIGEST,
            "request_canonical_sha256": REQUEST_DIGEST,
            "inherited_checkpoint_count": 0,
            "inherited_observation_count": 0,
            "summary_merge_with_old_lineage_allowed": False,
        },
        "job_metadata_snapshot": {
            "job_id": job["job_id"],
            "job_kind": job["kind"],
            "status": job["status"],
            "progress": job["progress"],
            "progress_message": job["progress_message"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "resource_id": job["resource_id"],
            "error_message": job["error_message"],
            "partition_count": 0,
            "target_dataset_count": 0,
            "retry_symbol": None,
            "target_count": TARGET_COUNT,
            "target_dataset_id": TARGET_DATASET_ID,
            "database_authority": "POSTGRESQL_BACKTEST_SCHEMA_METADATA_ONLY",
        },
        "source_provenance": {
            "scan_runtime_at_initial_registration": original["source_snapshot"],
            "initializer_at_initial_registration": {
                "classification": "POST_HOC_ONLY_NOT_GIT_RECONSTRUCTABLE",
                "attribution_to_initial_executed_bytes": "NOT_PROVEN",
            },
            "security_remediation_at_revision": _post_hoc_source_snapshot(),
        },
        "initial_registration_evidence_limits": {
            "acquisition_lock_evidence": "NOT_RECORDED",
            "symlink_safe_publication_evidence": "NOT_ESTABLISHED_RETROACTIVELY",
            "initializer_git_reconstruction": "NOT_AVAILABLE",
        },
        "security_remediation": {
            "prepared_job_kind_enforced_in_database": True,
            "generic_downloader_kind_rejection": True,
            "generic_lineage_guard_present_in_worktree": True,
            "generic_cli_metadata_preflight_before_provider_present_in_worktree": True,
            "no_follow_locked_artifact_publisher_present_in_worktree": True,
            "claims_initial_execution_used_remediated_code": False,
        },
        "activation": {
            "scan_authorized": False,
            "historical_kbar_requests_allowed": False,
            "generic_resume_allowed": False,
            "dedicated_activation_runner_available": False,
            "activation_rule": "NEW_REVIEWED_REVISION_AND_OWNER_AUTHORIZATION_REQUIRED",
        },
        "execution_lock": {
            "dataset_materialization_allowed": False,
            "formal_coverage_audit_allowed": False,
            "population_freeze_allowed": False,
            "outcome_generation_allowed": False,
            "holdout_allowed": False,
            "order_submission_allowed": False,
            "trade_subscription_allowed": False,
        },
        "release_blockers": [
            "INITIALIZER_SOURCE_NOT_GIT_RECONSTRUCTABLE",
            "SECURITY_REMEDIATION_SOURCE_NOT_COMMITTED",
            "DEDICATED_R3_ACTIVATION_RUNNER_NOT_IMPLEMENTED",
            "ACTIVATION_SOURCE_SNAPSHOT_NOT_FROZEN",
            "OWNER_SCAN_AUTHORIZATION_NOT_GRANTED",
        ],
        "scope": {
            "purpose": "R3_JOB_SECURITY_QUARANTINE_METADATA_ONLY",
            "research_eligible": False,
            "provider_built": False,
            "historical_payload_read": False,
            "price_values_read": False,
            "outcome_fields_read": False,
        },
    }


def main() -> None:
    repository = None
    with locked_artifact_store(ACQUISITION_ROOT) as store:
        target = store.load(TARGET_NAME)
        original = store.load(ORIGINAL_CONFIG_NAME)
        if _digest(target) != TARGET_DIGEST:
            raise PriceCoverageInitializationError("Fresh r3 target manifest drifted")
        if _digest(original) != ORIGINAL_CONFIG_DIGEST:
            raise PriceCoverageInitializationError("Original r3 configuration drifted")
        try:
            repository = BacktestApplicationService._build_repository()
            job = _require_exact_job(repository)
            revision = _build_revision(target=target, original=original, job=job)
            secrets = tuple(
                os.environ.get(name, "")
                for name in (
                    "SHIOAJI_API_KEY",
                    "SHIOAJI_SECRET",
                    "SJ_API_KEY",
                    "SJ_SECRET_KEY",
                    "SJ_SEC_KEY",
                )
            )
            assert_no_secret_values((revision,), secrets)
            revision_digest = store.publish(REVISION_NAME, revision)
        finally:
            if repository is not None:
                repository.close()
    print(
        json.dumps(
            {
                "configuration_digest": revision_digest,
                "historical_payload_read": False,
                "job_id": JOB_ID,
                "job_kind": PREPARED_JOB_KIND,
                "job_status": PREPARED_JOB_STATUS,
                "provider_built": False,
                "scan_authorized": False,
                "status": "QUARANTINED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
