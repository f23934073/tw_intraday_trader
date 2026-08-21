"""Drift gates for the preregistered full PriceCoverageAuditV1 contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/institutional_evaluation/coverage/price_coverage_audit_v1_contract_2026-08-21.json"
CONTRACT_DIGEST = CONTRACT.with_suffix(".canonical.sha256")
CONFIG = ROOT / "research/institutional_evaluation/acquisition/price_coverage_scan_configuration_v1_2026-08-21.json"
CONFIG_DIGEST = CONFIG.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_audit_contract_digest_and_scan_configuration_lineage_are_frozen() -> None:
    contract = _load(CONTRACT)
    config = _load(CONFIG)
    config_digest = CONFIG_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(contract)) == CONTRACT_DIGEST.read_text(encoding="utf-8").strip()
    assert contract["scan_configuration"] == {
        "artifact_id": config["artifact_id"],
        "canonical_sha256": config_digest,
    }


def test_final_audit_requires_complete_lineage_before_formal_coverage_claim() -> None:
    contract = _load(CONTRACT)

    assert set(contract["final_audit_lineage_requirements"]) == {
        "ORIGINAL_FORMAL_EVALUATION_PROTOCOL_DIGEST",
        "COVERAGE_AMENDMENT_DIGEST",
        "PRICE_COVERAGE_SCAN_CONFIGURATION_DIGEST",
        "FINAL_SCAN_CHECKPOINT_METADATA_DIGEST",
        "PIT_UNIVERSE_DIGEST",
        "INSTITUTIONAL_PARTITION_SET_DIGEST",
        "TRADING_CALENDAR_DIGEST",
        "REFERENCE_DATA_DIGEST",
        "CORPORATE_ACTION_DIGEST",
    }
    assert all(value is False for value in contract["execution_lock"].values())


def test_audit_outputs_and_reason_dispositions_are_coverage_only() -> None:
    contract = _load(CONTRACT)
    outputs = contract["output_contract"]

    assert outputs["coverage_gate"] == {
        "minimum_aggregate_session_coverage_rate": "0.99",
        "minimum_per_symbol_session_coverage_rate": "0.99",
        "minimum_symbol_coverage_rate": "0.95",
    }
    assert set(outputs["concentration_dimensions"]) == {
        "MARKET",
        "MARKET_CAP_COHORT",
        "ADV20_LIQUIDITY_COHORT",
        "INDUSTRY_CODE",
        "LISTING_STATUS_ACTIVE_VS_LATER_DELISTED",
    }
    assert contract["missing_reason_disposition"] == {
        "PRICE_DATA_UNAVAILABLE": "ELIGIBLE_FOR_DATA_COVERAGE_EXCLUSION_ONLY_AFTER_FINAL_PIT_AUDIT",
        "PROVIDER_EMPTY_KBAR": "RECORD_AS_PRICE_DATA_UNAVAILABLE",
        "RATE_LIMITED": "RETRY_OR_RESOLUTION_REQUIRED",
        "SYMBOL_MAPPING_ERROR": "RESOLUTION_REQUIRED",
        "TEMPORARY_FETCH_FAILURE": "RETRY_OR_RESOLUTION_REQUIRED",
        "TIMEOUT": "RETRY_OR_RESOLUTION_REQUIRED",
    }
