"""Drift gates for the fail-closed price-provider coverage resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "price_provider_coverage_resolution_v1_2026-08-20.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
UPSTREAM = ARTIFACT.with_name("price_symbol_resolution_1259_v1_2026-08-20.json")
UPSTREAM_DIGEST = UPSTREAM.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {
            nested for child in value.values() for nested in _all_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _all_keys(child)}
    return set()


def test_provider_resolution_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == "price_provider_coverage_resolution_v1"
    assert artifact["artifact_id"] == "price-provider-coverage-resolution-v1-2026-08-20-r1"
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_provider_resolution_references_exact_symbol_classification() -> None:
    artifact = _load(ARTIFACT)
    upstream = _load(UPSTREAM)
    assert artifact["symbol_resolution_reference"] == {
        "artifact_id": upstream["artifact_id"],
        "canonical_sha256": UPSTREAM_DIGEST.read_text().strip(),
    }


def test_current_provider_support_does_not_claim_per_symbol_completeness() -> None:
    current = _load(ARTIFACT)["provider_review"]["current_provider"]
    assert current["documented_request_scope"] == "STK_WITH_TSE_OR_OTC_EXCHANGE"
    assert current["per_symbol_completeness_guarantee_found"] is False
    assert current["status"] == "UNRESOLVED_FOR_SYMBOL_1259"


def test_alternatives_are_candidates_not_selected_datasets() -> None:
    artifact = _load(ARTIFACT)
    alternatives = artifact["provider_review"]["alternatives"]
    assert artifact["decision"]["alternative_source_selected"] is None
    assert alternatives[0]["name"] == "FUGLE_HISTORICAL_CANDLES"
    assert alternatives[0]["status"] == "QUALIFICATION_CANDIDATE"
    assert all(item["status"] != "VALIDATED" for item in alternatives)


def test_provider_mismatch_cannot_be_silently_excluded_or_mixed() -> None:
    artifact = _load(ARTIFACT)
    policy = artifact["policy"]
    assert "EMPTY_PROVIDER_RESPONSE" in policy["forbidden_exclusion_evidence"]
    assert policy["source_mixing_policy"].startswith("NO_SILENT_MIXING")
    assert artifact["permissions"]["provider_mismatch_exclusion_allowed"] is False


def test_qualification_gate_freezes_strategy_input_semantics() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["contract"]["required_cadence"] == "ONE_MINUTE"
    assert artifact["contract"]["volume_normalization_unit"] == "SHARES"
    criteria = set(artifact["qualification_gate"]["acceptance_criteria"])
    assert {
        "CUMULATIVE_INTRADAY_VWAP_EQUIVALENCE_VERIFIED",
        "PIT_ELIGIBLE_AND_DELISTED_SYMBOL_POLICY_VERIFIED",
        "SOURCE_PRECEDENCE_AND_NO_SILENT_MIXING_POLICY_FROZEN",
    } <= criteria


def test_resolution_remains_fail_closed_and_reads_no_outcomes() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["status"] == "BLOCKED"
    assert set(artifact["permissions"].values()) == {False}
    assert artifact["evidence_scope"] == {
        "inspection_only": True,
        "outcome_fields_read": False,
        "price_payloads_read": False,
        "provider_requests_executed": False,
        "reviewed_at": "2026-08-20T18:10:00+08:00",
    }
    assert _all_keys(artifact).isdisjoint(
        {"return", "pnl", "setup_success", "holdout_result"}
    )
