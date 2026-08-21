"""Drift gates for the active Shioaji provider-coverage scan configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "research/institutional_evaluation/acquisition/price_coverage_scan_configuration_v1_2026-08-21.json"
CONFIG_DIGEST = CONFIG.with_suffix(".canonical.sha256")
AMENDMENT = ROOT / "research/institutional_evaluation/protocols/formal_evaluation_coverage_amendment_v1_2026-08-21.json"
AMENDMENT_DIGEST = AMENDMENT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_scan_configuration_digest_and_coverage_amendment_lineage_are_frozen() -> None:
    config = _load(CONFIG)
    amendment = _load(AMENDMENT)
    amendment_digest = AMENDMENT_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(config)) == CONFIG_DIGEST.read_text(encoding="utf-8").strip()
    assert config["coverage_amendment"] == {
        "artifact_id": amendment["artifact_id"],
        "canonical_sha256": amendment_digest,
    }


def test_configuration_pins_provider_job_and_metadata_only_checkpoint_snapshot() -> None:
    config = _load(CONFIG)
    job = config["job"]
    provider = config["provider"]
    checkpoint = config["checkpoint_snapshot"]

    assert job["target_count"] == 2738
    assert job["universe_selection"] == "ALL_CURRENT"
    assert provider["adapter_class"] == "market_data.provider.ShioajiProvider"
    assert provider["sdk_package"] == "shioaji"
    assert provider["sdk_version"] == "1.7.2"
    assert checkpoint["checkpointed_partition_count"] == 542
    assert checkpoint["nonempty_partition_count"] == 468
    assert checkpoint["typed_price_data_unavailable_count"] == 2
    assert checkpoint["legacy_empty_revalidation_pending_count"] == 72
    assert len(checkpoint["checkpoint_metadata_sha256"]) == 64


def test_reason_policy_and_scope_cannot_promote_intermediate_scan_to_formal_coverage() -> None:
    config = _load(CONFIG)

    assert config["missing_reason_policy"] == {
        "DATA_COVERAGE_EXCLUDED": "ONLY_AFTER_FINAL_PIT_COVERAGE_AUDIT",
        "PRICE_DATA_UNAVAILABLE": "RESOLVED_PROVIDER_EMPTY_OBSERVATION",
        "SYMBOL_MAPPING_ERROR": "RESOLUTION_REQUIRED_BEFORE_EXCLUSION",
        "TEMPORARY_FETCH_FAILURE": "RETRY_OR_RESOLUTION_REQUIRED_BEFORE_EXCLUSION",
        "TIMEOUT_OR_RATE_LIMITED": "RETRY_OR_RESOLUTION_REQUIRED_BEFORE_EXCLUSION",
        "UNCLASSIFIED_LEGACY_EMPTY": "REVALIDATION_REQUIRED_BEFORE_EXCLUSION",
    }
    assert config["scope"] == {
        "formal_pit_denominator_available": False,
        "outcome_fields_read": False,
        "price_values_read_for_decision": False,
        "purpose": "PROVIDER_COVERAGE_OBSERVATION_ONLY",
        "research_eligible": False,
    }
    assert all(value is False for value in config["execution_lock"].values())
