"""Drift gates for official/licensed intraday source resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "institutional_evaluation" / "acquisition"
ARTIFACT = BASE / "official_or_licensed_intraday_source_resolution_v1_2026-08-21.json"
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")


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


def test_resolution_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == (
        "official_or_licensed_intraday_source_resolution_v1"
    )
    assert artifact["artifact_id"] == (
        "official-or-licensed-intraday-source-resolution-v1-2026-08-21-r1"
    )
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_public_api_fallback_candidates_are_exhausted_not_selected() -> None:
    resolution = _load(ARTIFACT)["public_api_resolution"]
    assert resolution["candidates_exhausted_for_fallback_use_case"] is True
    assert {item["name"] for item in resolution["dispositions"]} == {
        "SHIOAJI",
        "FUGLE",
        "FINMIND_SPONSOR",
    }


def test_direct_exchange_files_are_semantically_fit_but_date_blocked() -> None:
    artifact = _load(ARTIFACT)
    direct = artifact["candidate_assessments"][0]
    assert direct["contract_fit"]["one_minute_ohlcv_reconstructable"] is True
    assert direct["contract_fit"]["vwap_reconstructable"] is True
    assert direct["contract_fit"]["volume_unit"] == "SHARES"
    assert direct["status"] == "PROCUREMENT_CANDIDATE_BLOCKED"
    assert "TWSE_RECENT_ONE_YEAR_UNAVAILABLE" in direct["gaps"]
    assert artifact["decision"]["direct_exchange_candidate_qualified"] is False


def test_daily_pit_support_is_not_misrepresented_as_intraday() -> None:
    tej = _load(ARTIFACT)["candidate_assessments"][2]
    assert tej["candidate_id"] == "TEJ_TQUANT_SUPPORTING_REFERENCE_DATA"
    assert tej["status"] == "SUPPORTING_DATA_CANDIDATE_ONLY"
    assert "REVIEWED_PRICE_PRODUCT_IS_DAILY_NOT_ONE_MINUTE" in tej["gaps"]


def test_next_gate_requires_written_procurement_and_fixed_sample_evidence() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["decision"]["next_gate"] == (
        "PROCUREMENT_RFI_AND_CONTRACT_EVIDENCE_V1"
    )
    questions = set(artifact["procurement_rfi"]["required_written_answers"])
    assert {
        "ORDINARY_EQUITY_AND_LATER_DELISTED_SECURITY_COVERAGE",
        "RAW_DATA_RETENTION_AND_IMMUTABLE_INTERNAL_RESEARCH_RIGHTS",
        "CORRECTION_NOTICE_REVISION_ID_AND_REDELIVERY_POLICY",
    } <= questions
    assert artifact["procurement_rfi"]["sample_exit_gate"]["fixed_symbols"] == [
        "1259",
        "1240",
        "12561",
        "2330",
        "2317",
    ]


def test_resolution_references_exact_upstream_evidence() -> None:
    artifact = _load(ARTIFACT)
    expected = {
        item["artifact_id"]: item["canonical_sha256"]
        for item in artifact["upstream_references"]
    }
    assert expected == {
        "price-provider-coverage-resolution-v1-2026-08-20-r1": (
            BASE.joinpath(
                "price_provider_coverage_resolution_v1_2026-08-20.canonical.sha256"
            ).read_text().strip()
        ),
        "price-symbol-resolution-1259-v1-2026-08-20-r1": (
            BASE.joinpath(
                "price_symbol_resolution_1259_v1_2026-08-20.canonical.sha256"
            ).read_text().strip()
        ),
        "credentialed-intraday-source-probe-result-v1-2026-08-20-r1": (
            BASE.joinpath(
                "credentialed_intraday_source_probe_result_v1_2026-08-20.canonical.sha256"
            ).read_text().strip()
        ),
        "credentialed-finmind-intraday-source-probe-result-v1-2026-08-21-r2": (
            BASE.joinpath(
                "credentialed_finmind_intraday_source_probe_result_v1_2026-08-21_r2.canonical.sha256"
            ).read_text().strip()
        ),
    }


def test_resolution_is_fail_closed_and_reads_no_outcomes() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["status"] == "BLOCKED"
    assert artifact["result"] == {
        "fail_count": 1,
        "insufficient_evidence_count": 4,
        "not_executed_count": 3,
        "pass_count": 5,
        "qualified": False,
        "verdict": "INSUFFICIENT_EVIDENCE",
    }
    assert set(artifact["permissions"].values()) == {False}
    assert _all_keys(artifact).isdisjoint(
        {"return", "pnl", "setup_success", "holdout_result"}
    )
