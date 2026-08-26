"""Drift gates for the fresh, metadata-only PR-008 r3 job lineage."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import date
from pathlib import Path

from backtest.domain import canonical_json
from backtest.price_coverage_initialization import ContractTarget, prepare_fresh_job


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research/institutional_evaluation/acquisition"
TARGET = ACQUISITION / "price_coverage_target_order_v1_2026-08-26-r3.json"
CONFIG = ACQUISITION / "price_coverage_scan_configuration_v2_2026-08-26-r3.json"
REV2 = (
    ACQUISITION
    / "price_coverage_scan_configuration_v2_2026-08-26-r3-rev2.json"
)
ACTIVATION = (
    ACQUISITION
    / "price_coverage_scan_activation_v1_2026-08-26-r3.json"
)
R2 = ACQUISITION / "price_coverage_scan_configuration_v1_2026-08-21-r2.json"

TARGET_DIGEST = "61dc598c47e3168f67c36862606d12b3bad2fce709e58d1a7543e663c0453827"
CONFIG_DIGEST = "a970a91d22501f4ec670d2c3e40e7ac71c9405ce9031c881bb639034f8c29c5b"
REV2_DIGEST = "f44d1e87a81fd9aedded1d7bc1a42e2032d564e437431fe47f5d62fcf3db27af"
ACTIVATION_DIGEST = "ce5ecd701915309664320832df89201666083d0e5147488139a2048055e50c4f"
R2_DIGEST = "d60502f51897bdf4492717ec49f07b52b09c5f7f60b8c5764d10b4295dc22797"
JOB_ID = "dataset-download-r3-e9981217a1d36c213e121db3ebaa26e7"
REQUEST_DIGEST = "f04d7e78ba5c79390bf471c53741efbadf061aafd89abe5682654a9594047256"
ORDER_DIGEST = "470032790f69f25a98a61d13686598776dcc1d8819379427113ebcc44305331e"
TARGET_COUNT = 2781


def _read_regular_no_follow(path: Path, *, encoding: str) -> str:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        file_stat = os.fstat(descriptor)
        assert stat.S_ISREG(file_stat.st_mode)
        assert file_stat.st_nlink == 1
        with os.fdopen(descriptor, "r", encoding=encoding, closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(_read_regular_no_follow(path, encoding="utf-8"))


def _canonical_digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _sidecar(path: Path) -> str:
    return _read_regular_no_follow(
        path.with_suffix(".canonical.sha256"),
        encoding="ascii",
    )


def test_r3_artifacts_and_predecessor_are_immutable_exact() -> None:
    assert _canonical_digest(_load(TARGET)) == TARGET_DIGEST
    assert _sidecar(TARGET) == f"{TARGET_DIGEST}\n"
    assert _canonical_digest(_load(CONFIG)) == CONFIG_DIGEST
    assert _sidecar(CONFIG) == f"{CONFIG_DIGEST}\n"
    assert _canonical_digest(_load(REV2)) == REV2_DIGEST
    assert _sidecar(REV2) == f"{REV2_DIGEST}\n"
    assert _canonical_digest(_load(ACTIVATION)) == ACTIVATION_DIGEST
    assert _sidecar(ACTIVATION) == f"{ACTIVATION_DIGEST}\n"
    assert _canonical_digest(_load(R2)) == R2_DIGEST
    assert _sidecar(R2) == f"{R2_DIGEST}\n"


def test_target_manifest_preserves_complete_index_zero_contract_order() -> None:
    target = _load(TARGET)
    rows = target["targets"]

    assert target["schema_version"] == "price_coverage_target_order_v1"
    assert target["lineage"] == {
        "mode": "FRESH_R3_NO_CHECKPOINT_REUSE",
        "predecessor_checkpoint_inheritance_allowed": False,
        "summary_merge_with_r0_r1_r2_allowed": False,
    }
    assert len(rows) == TARGET_COUNT
    assert [row["target_index"] for row in rows] == list(range(TARGET_COUNT))
    assert [row["symbol"] for row in rows] == sorted(row["symbol"] for row in rows)
    assert len({row["symbol"] for row in rows}) == TARGET_COUNT
    assert {row["market"] for row in rows} == {"TWSE", "TPEX"}
    assert all(set(row) == {"target_index", "symbol", "name", "market"} for row in rows)
    assert _canonical_digest(rows) == ORDER_DIGEST
    assert target["target_order"] == {
        "canonical_sha256": ORDER_DIGEST,
        "projection_fields": ["target_index", "symbol", "name", "market"],
        "target_count": TARGET_COUNT,
    }
    assert target["scope"] == {
        "historical_kbar_requests_issued": False,
        "order_submission_allowed": False,
        "outcome_fields_read": False,
        "price_values_read": False,
        "trade_subscription_allowed": False,
    }


def test_r3_configuration_reconstructs_the_exact_fresh_job_identity() -> None:
    target = _load(TARGET)
    config = _load(CONFIG)
    prepared = prepare_fresh_job(
        targets=tuple(
            ContractTarget(row["symbol"], row["name"], row["market"])
            for row in target["targets"]
        ),
        provider_environment_identity=(
            target["source"]["provider_environment_identity"]
        ),
        end_date=date(2026, 8, 18),
    )

    assert prepared.job_id == JOB_ID
    assert prepared.request_canonical_sha256 == REQUEST_DIGEST
    assert prepared.target_order_canonical_sha256 == ORDER_DIGEST
    assert config["job"] == {
        "checkpointed_partition_count": 0,
        "job_id": JOB_ID,
        "job_kind": "DATASET_DOWNLOAD",
        "request_canonical_sha256": REQUEST_DIGEST,
        "requested_end_date": "2026-08-18",
        "requested_start_date": "2023-08-19",
        "retry_symbol": None,
        "start_target_index": 0,
        "state_at_registration": "QUEUED",
        "target_count": TARGET_COUNT,
        "universe_selection": "ALL_CURRENT_CONTRACT_CATALOG_V1",
    }
    assert config["target_order"] == {
        "manifest_artifact_id": "price-coverage-target-order-v1-2026-08-26-r3",
        "manifest_canonical_sha256": TARGET_DIGEST,
        "projection_fields": ["target_index", "symbol", "name", "market"],
        "target_order_canonical_sha256": ORDER_DIGEST,
    }


def test_r3_pins_reconstructable_clean_production_source_paths() -> None:
    config = _load(CONFIG)
    snapshot = config["source_snapshot"]
    commit = snapshot["repository_commit"]

    assert subprocess.run(
        ["git", "cat-file", "-t", commit],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "commit"
    assert snapshot["repository_tree_oid"] == subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert snapshot["pinned_source_paths_clean"] is True
    assert snapshot["repository_worktree_clean"] is False

    for entry in snapshot["files"]:
        path = entry["path"]
        committed = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(committed).hexdigest() == entry["content_sha256"]
        assert subprocess.run(
            ["git", "rev-parse", f"{commit}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() == entry["git_blob_oid"]


def test_r3_keeps_every_runtime_and_research_gate_disabled() -> None:
    config = _load(CONFIG)

    assert config["status"] == "FROZEN_JOB_CREATED_SCAN_NOT_AUTHORIZED"
    assert config["lineage"] == {
        "inherited_checkpoint_count": 0,
        "inherited_observation_count": 0,
        "mode": "FRESH_RESTART_NO_CHECKPOINT_INHERITANCE",
        "predecessor_configuration": {
            "artifact_id": "price-coverage-scan-configuration-v1-2026-08-21-r2",
            "canonical_sha256": R2_DIGEST,
        },
        "predecessor_disposition": "ABANDONED_DURABLE_JOB_UNRECOVERABLE",
        "summary_merge_with_old_lineage_allowed": False,
    }
    assert config["activation"]["historical_kbar_requests_allowed"] is False
    assert all(value is False for value in config["execution_lock"].values())
    assert config["provider_environment"] == {
        "adapter_class": "market_data.provider.ShioajiProvider",
        "credential_values_stored": False,
        "historical_query": "Shioaji.kbars",
        "provider": "shioaji",
        "sdk_package": "shioaji",
        "sdk_version": "1.7.2",
        "simulation": True,
        "subscribe_trade": False,
    }


def test_r3_artifacts_contain_no_secret_or_price_payload_fields() -> None:
    target = _load(TARGET)
    config = _load(CONFIG)
    rev2 = _load(REV2)
    activation = _load(ACTIVATION)
    serialized = canonical_json(
        {
            "target": target,
            "config": config,
            "rev2": rev2,
            "activation": activation,
        }
    ).lower()

    for forbidden in (
        '"shioaji_api_key":',
        '"shioaji_secret":',
        '"authorization":',
        '"account_id":',
        '"bars_payload":',
        '"return_pct":',
        '"pnl":',
        '"holdout_outcome":',
    ):
        assert forbidden not in serialized


def test_r3_activation_is_raw_scan_only_and_reconstructs_pinned_sources() -> None:
    activation = _load(ACTIVATION)
    snapshot = activation["source_snapshot"]
    commit = snapshot["repository_commit"]

    assert activation["status"] == (
        "AUTHORIZED_FOR_HISTORICAL_KBAR_COVERAGE_SCAN"
    )
    assert activation["authorized_by"] == "research-owner"
    assert activation["authorized_at"] == "2026-08-26T10:29:59+08:00"
    assert activation["activation"] == {
        "exact_digest_required_on_every_resume": True,
        "generic_resume_allowed": False,
        "historical_kbar_requests_allowed": True,
        "repository_wide_lock_required_for_process_lifetime": True,
        "scan_authorized": True,
    }
    assert all(value is False for value in activation["execution_lock"].values())
    assert activation["scope"] == {
        "outcome_read_allowed": False,
        "price_payload_inspection_allowed": False,
        "purpose": "RAW_PRICE_COVERAGE_INVENTORY_ONLY",
        "research_eligible": False,
        "return_or_pnl_read_allowed": False,
    }
    assert subprocess.run(
        ["git", "cat-file", "-t", commit],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "commit"
    assert snapshot["repository_tree_oid"] == subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    for entry in snapshot["files"]:
        committed = subprocess.run(
            ["git", "show", f"{commit}:{entry['path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(committed).hexdigest() == entry["content_sha256"]
        assert subprocess.run(
            ["git", "rev-parse", f"{commit}:{entry['path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() == entry["git_blob_oid"]


def test_r3_rev2_quarantines_original_registration_without_overwrite() -> None:
    rev2 = _load(REV2)

    assert rev2["status"] == "QUARANTINED_PREPARED_JOB_SCAN_NOT_AUTHORIZED"
    assert rev2["supersedes_for_activation"] == {
        "artifact_id": "price-coverage-scan-configuration-v2-2026-08-26-r3",
        "canonical_sha256": CONFIG_DIGEST,
        "disposition": (
            "HISTORICAL_REGISTRATION_EVIDENCE_ONLY_NOT_ACTIVATION_AUTHORITY"
        ),
    }
    assert rev2["activation"] == {
        "activation_rule": "NEW_REVIEWED_REVISION_AND_OWNER_AUTHORIZATION_REQUIRED",
        "dedicated_activation_runner_available": False,
        "generic_resume_allowed": False,
        "historical_kbar_requests_allowed": False,
        "scan_authorized": False,
    }
    assert all(value is False for value in rev2["execution_lock"].values())


def test_r3_rev2_pins_exact_prepared_job_metadata_and_zero_outputs() -> None:
    snapshot = _load(REV2)["job_metadata_snapshot"]

    assert snapshot == {
        "created_at": "2026-08-26T09:14:41.094249+08:00",
        "database_authority": "POSTGRESQL_BACKTEST_SCHEMA_METADATA_ONLY",
        "error_message": None,
        "job_id": JOB_ID,
        "job_kind": "PRICE_COVERAGE_PREPARED",
        "partition_count": 0,
        "progress": 0.0,
        "progress_message": (
            "Fresh r3 prepared; generic Kbar resume prohibited; "
            "dedicated activation required"
        ),
        "resource_id": None,
        "retry_symbol": None,
        "status": "PREPARED",
        "target_count": TARGET_COUNT,
        "target_dataset_count": 0,
        "target_dataset_id": "dataset-r3-e9981217a1d36c213e121db3ebaa26e7",
        "updated_at": "2026-08-26 01:30:53.833323+00",
    }


def test_r3_rev2_records_unresolved_provenance_and_release_blockers() -> None:
    rev2 = _load(REV2)

    assert rev2["initial_registration_evidence_limits"] == {
        "acquisition_lock_evidence": "NOT_RECORDED",
        "initializer_git_reconstruction": "NOT_AVAILABLE",
        "symlink_safe_publication_evidence": "NOT_ESTABLISHED_RETROACTIVELY",
    }
    assert rev2["source_provenance"]["initializer_at_initial_registration"] == {
        "attribution_to_initial_executed_bytes": "NOT_PROVEN",
        "classification": "POST_HOC_ONLY_NOT_GIT_RECONSTRUCTABLE",
    }
    assert rev2["source_provenance"]["security_remediation_at_revision"][
        "reproducible_from_git"
    ] is False
    assert set(rev2["release_blockers"]) == {
        "INITIALIZER_SOURCE_NOT_GIT_RECONSTRUCTABLE",
        "SECURITY_REMEDIATION_SOURCE_NOT_COMMITTED",
        "DEDICATED_R3_ACTIVATION_RUNNER_NOT_IMPLEMENTED",
        "ACTIVATION_SOURCE_SNAPSHOT_NOT_FROZEN",
        "OWNER_SCAN_AUTHORIZATION_NOT_GRANTED",
    }
