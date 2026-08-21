"""Drift gates for the pre-outcome PR-008 coverage-policy amendment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/institutional_evaluation/protocols/formal_evaluation_gate_v1.json"
PROTOCOL_DIGEST = PROTOCOL.with_suffix(".canonical.sha256")
AMENDMENT = ROOT / "research/institutional_evaluation/protocols/formal_evaluation_coverage_amendment_v1_2026-08-21.json"
AMENDMENT_DIGEST = AMENDMENT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_amendment_digest_and_original_protocol_reference_are_frozen() -> None:
    amendment = _load(AMENDMENT)
    protocol = _load(PROTOCOL)
    expected_protocol_digest = PROTOCOL_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(amendment)) == AMENDMENT_DIGEST.read_text(encoding="utf-8").strip()
    assert sha256_text(canonical_json(protocol)) == expected_protocol_digest
    assert amendment["protocol"] == {
        "artifact_id": protocol["artifact_id"],
        "canonical_sha256": expected_protocol_digest,
    }
    assert amendment["status"] == "PREREGISTERED_PENDING_COVERAGE_AUDIT"


def test_uniform_coverage_rule_and_owner_approved_thresholds_are_exact() -> None:
    amendment = _load(AMENDMENT)
    gate = amendment["coverage_gate"]
    policy = amendment["evaluation_population_policy"]

    assert gate["symbol_coverage"]["minimum_rate"] == "0.95"
    assert gate["covered_symbol_qualification"]["minimum_symbol_session_coverage_rate"] == "0.99"
    assert gate["aggregate_session_coverage"]["minimum_rate"] == "0.99"
    assert policy["exclusion_code"] == "DATA_COVERAGE_EXCLUDED"
    assert policy["named_symbol_overrides"] == []
    assert policy["symbol_specific_exception_allowed"] is False
    assert "1259" not in canonical_json(amendment)
    assert "12561" not in canonical_json(amendment)


def test_missingness_concentration_requires_coverage_only_owner_review() -> None:
    audit = _load(AMENDMENT)["missingness_concentration_audit"]

    assert set(audit["dimensions"]) == {
        "MARKET",
        "MARKET_CAP_COHORT",
        "ADV20_LIQUIDITY_COHORT",
        "INDUSTRY_CODE",
        "LISTING_STATUS_ACTIVE_VS_LATER_DELISTED",
    }
    assert audit["automatic_pass_thresholds"] is None
    assert audit["outcome_fields_allowed"] is False
    assert audit["owner_review_required_before_population_freeze"] is True


def test_amendment_keeps_outcome_and_holdout_fail_closed() -> None:
    amendment = _load(AMENDMENT)
    lock = amendment["execution_lock"]
    attestation = amendment["pre_outcome_attestation"]

    assert lock["dataset_population_freeze_allowed"] is False
    assert lock["outcome_generation_allowed"] is False
    assert lock["holdout_outcome_materialization_allowed"] is False
    assert lock["holdout_execution_allowed"] is False
    assert attestation == {
        "holdout_outcome_materialized": False,
        "outcome_fields_read": False,
        "outcome_generated": False,
        "protocol_execution_locks_verified_false_before_amendment": True,
    }
    assert amendment["reporting_scope"]["claim_all_taiwan_equities_allowed"] is False
