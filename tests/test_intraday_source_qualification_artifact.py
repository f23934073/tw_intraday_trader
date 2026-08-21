"""Drift gates for the fail-closed intraday source qualification."""

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
    / "intraday_source_qualification_v1_2026-08-20.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
UPSTREAM = ARTIFACT.with_name("price_provider_coverage_resolution_v1_2026-08-20.json")
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


def test_qualification_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == "intraday_source_qualification_v1"
    assert artifact["artifact_id"] == "intraday-source-qualification-v1-2026-08-20-r1"
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_qualification_references_exact_provider_resolution() -> None:
    artifact = _load(ARTIFACT)
    upstream = _load(UPSTREAM)
    assert artifact["upstream_reference"] == {
        "artifact_id": upstream["artifact_id"],
        "canonical_sha256": UPSTREAM_DIGEST.read_text().strip(),
    }


def test_documentation_match_cannot_select_candidate() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["candidate"]["status"] == "DOCUMENTED_CANDIDATE_NOT_PROBED"
    assert artifact["candidate"]["selected_for_dataset_acquisition"] is False
    assert artifact["result"]["qualified"] is False
    assert artifact["result"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_missing_entitlement_prevents_provider_probe_claim() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["evidence_scope"]["credential_names_found"] == []
    assert artifact["evidence_scope"]["credential_values_read"] is False
    assert artifact["evidence_scope"]["provider_requests_executed"] is False
    checks = {item["check_id"]: item for item in artifact["qualification_checks"]}
    assert checks["ENTITLEMENT_AND_RESEARCH_USE_LICENSE_RECORDED"]["status"] == "FAIL"
    assert checks["SYMBOL_1259_NONEMPTY_FOR_OFFICIAL_CONTROL_SESSION"]["status"] == "NOT_EXECUTED"


def test_probe_protocol_has_fixed_cross_market_controls() -> None:
    artifact = _load(ARTIFACT)
    controls = artifact["probe_protocol"]["fixed_symbols"]
    assert {item["market"] for item in controls} == {"TWSE", "TPEX"}
    assert {item["symbol"] for item in controls} == {"1259", "1240", "12561", "2330", "2317"}
    assert artifact["probe_protocol"]["fixed_control_session"] == "2026-08-18"
    assert artifact["probe_protocol"]["future_session_sample"]["sessions"] is None


def test_semantic_checks_require_observed_evidence() -> None:
    artifact = _load(ARTIFACT)
    checks = {item["check_id"]: item for item in artifact["qualification_checks"]}
    for check_id in (
        "ONE_MINUTE_ASIA_TAIPEI_SESSION_ALIGNMENT_VERIFIED",
        "OHLC_AND_VOLUME_SEMANTICS_RECONCILED",
        "CUMULATIVE_INTRADAY_VWAP_EQUIVALENCE_VERIFIED",
        "VOLUME_NORMALIZED_TO_SHARES",
        "COST_AND_LIQUIDITY_INPUT_COMPATIBILITY_VERIFIED",
    ):
        assert checks[check_id]["evidence_level"] == "DOCUMENTATION_ONLY"
        assert checks[check_id]["status"] == "INSUFFICIENT_EVIDENCE"


def test_qualification_remains_fail_closed_and_outcome_free() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["status"] == "BLOCKED"
    assert set(artifact["permissions"].values()) == {False}
    assert artifact["evidence_scope"]["price_payloads_read"] is False
    assert artifact["evidence_scope"]["outcome_fields_read"] is False
    assert _all_keys(artifact).isdisjoint(
        {"return", "pnl", "setup_success", "holdout_result"}
    )
