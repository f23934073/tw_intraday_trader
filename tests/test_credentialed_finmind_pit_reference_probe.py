"""Drift gates for the credentialed FinMind PIT/reference qualification result."""

from __future__ import annotations

import json
from pathlib import Path

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research/institutional_evaluation/acquisition"
CAPTURE = ACQUISITION / "credentialed_finmind_pit_reference_probe_capture_v1_2026-08-24-r1/capture_manifest.json"
RESULT = ACQUISITION / "credentialed_finmind_pit_reference_probe_result_v1_2026-08-24.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_finmind_pit_reference_result_and_capture_are_digest_verified() -> None:
    for artifact in (CAPTURE, RESULT):
        assert sha256_text(canonical_json(_load(artifact))) == artifact.with_suffix(
            ".canonical.sha256"
        ).read_text(encoding="utf-8").strip()


def test_finmind_pit_reference_probe_verifies_access_but_does_not_select_source() -> None:
    result = _load(RESULT)

    assert result["decision"] == {
        "authentication": "VERIFIED",
        "bounded_dataset_entitlement": "VERIFIED",
        "formal_pit_reference_source_selected": False,
        "next_gate": "FINMIND_PIT_REFERENCE_SEMANTICS_AND_TERMS_RESOLUTION_V1",
        "verdict": "INSUFFICIENT_EVIDENCE",
    }
    assert all(value is False for value in result["permissions"].values())
    assert result["evidence_scope"] == {
        "backtest_executed": False,
        "capture_manifest_metadata_read": True,
        "credential_value_persisted": False,
        "outcome_fields_read": False,
        "price_or_kbar_payloads_read": False,
        "raw_provider_payloads_read_during_result_build": False,
    }


def test_finmind_pit_reference_result_preserves_schema_evidence_and_blockers() -> None:
    result = _load(RESULT)

    evidence = result["observed_schema_evidence"]
    assert evidence["security_identity"]["field_names"] == [
        "date",
        "industry_category",
        "stock_id",
        "stock_name",
        "type",
    ]
    assert evidence["delisting"]["field_names"] == ["date", "stock_id", "stock_name"]
    assert evidence["market_cap_early"]["field_names"] == [
        "date",
        "market_value",
        "stock_id",
    ]
    assert evidence["trading_calendar_twse_control"]["row_count"] == 3
    assert evidence["trading_calendar_tpex_control"]["row_count"] == 3
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert "PIT_LISTING_START_AND_MARKET_TRANSFER_HISTORY_NOT_OBSERVED" in issue_codes
    assert "PIT_INDUSTRY_CLASSIFICATION_AS_OF_SEMANTICS_NOT_OBSERVED" in issue_codes
    assert "FULL_HISTORICAL_PIT_COVERAGE_NOT_OBSERVED_FROM_BOUNDED_PROBE" in issue_codes
