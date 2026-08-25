"""Drift gates for the documented FinMind PIT/reference semantic disposition."""

from __future__ import annotations

import json
from pathlib import Path

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research/institutional_evaluation/acquisition"
    / "finmind_pit_reference_semantics_resolution_v1_2026-08-24.json"
)


def _load() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_finmind_pit_semantics_resolution_is_digest_frozen() -> None:
    artifact = _load()

    assert sha256_text(canonical_json(artifact)) == ARTIFACT.with_suffix(
        ".canonical.sha256"
    ).read_text(encoding="utf-8").strip()
    assert artifact["schema_version"] == "finmind_pit_reference_semantics_resolution_v1"
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_finmind_is_narrowly_rejected_for_formal_pit_but_not_every_reference_use() -> None:
    artifact = _load()

    assert artifact["decision"] == {
        "finmind_disposition": "REJECTED_FOR_FORMAL_PIT_REFERENCE_USE",
        "finmind_may_remain_partial_reference_component": True,
        "formal_pit_reference_source_selected": False,
        "next_gate": "LICENSED_OR_PROVIDER_WRITTEN_PIT_REFERENCE_SOURCE_RESOLUTION_V1",
        "verdict": "REJECTED_FOR_FORMAL_PIT_REFERENCE_USE",
    }
    assert all(value is False for value in artifact["permissions"].values())
    assert artifact["evidence_scope"] == {
        "additional_provider_requests_executed": False,
        "backtest_executed": False,
        "credential_values_read": False,
        "outcome_fields_read": False,
        "price_or_kbar_payloads_read": False,
        "reviewed_on": "2026-08-24",
    }


def test_finmind_documented_semantics_do_not_meet_required_pit_fields() -> None:
    artifact = _load()

    evidence = {item["dataset"]: item for item in artifact["documentary_evidence"]}
    assert evidence["TaiwanStockInfo"]["formal_pit_assessment"] == (
        "INSUFFICIENT_FOR_LISTED_FROM_LISTED_UNTIL_OR_COMPLETE_MARKET_TRANSFER_TIMELINE"
    )
    assert evidence["TaiwanStockIndustryChain"]["formal_pit_assessment"] == (
        "INCOMPATIBLE_WITH_DATE_EFFECTIVE_INDUSTRY_REQUIREMENT"
    )
    assert evidence["TaiwanStockTradingDate"]["formal_pit_assessment"] == (
        "INSUFFICIENT_TO_PROVE_A_SEPARATE_TWSE_TPEX_CALENDAR_SCOPE"
    )
    assert artifact["pit_contract_requirements"]["required_market_scope"] == [
        "TWSE",
        "TPEX",
    ]
    issue_codes = {issue["code"] for issue in artifact["issues"]}
    assert "PIT_INDUSTRY_AS_OF_SEMANTICS_DOCUMENTED_INCOMPATIBLE" in issue_codes
    assert "PROVIDER_RETENTION_CORRECTION_AND_REVISION_TERMS_NOT_EVIDENCED" in issue_codes
