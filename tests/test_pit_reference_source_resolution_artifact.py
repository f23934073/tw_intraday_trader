"""Drift gates for the PR-008 PIT/reference source-resolution artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research/institutional_evaluation/acquisition"
    / "pit_reference_source_resolution_v1_2026-08-24.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pit_reference_source_resolution_digest_is_frozen() -> None:
    artifact = _load(ARTIFACT)

    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text(
        encoding="utf-8"
    ).strip()
    assert artifact["schema_version"] == "pit_reference_source_resolution_v1"
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_source_resolution_does_not_promote_any_candidate_or_gate() -> None:
    artifact = _load(ARTIFACT)

    assert artifact["decision"] == {
        "next_gate": "TEJ_PIT_REFERENCE_ENTITLEMENT_AND_METADATA_QUALIFICATION_V1",
        "selected_source": None,
        "verdict": "INSUFFICIENT_EVIDENCE",
    }
    assert all(value is False for value in artifact["permissions"].values())
    assert artifact["evidence_scope"] == {
        "credential_values_read": False,
        "local_credential_names_checked": [
            "TEJ_API_KEY",
            "TEJAPI_KEY",
            "TQUANT_API_KEY",
            "TQUANT_TOKEN",
        ],
        "outcome_fields_read": False,
        "provider_requests_executed": False,
        "reviewed_at": "2026-08-24T09:10:33+08:00",
    }
    assert all(candidate["selected"] is False for candidate in artifact["source_candidates"])


def test_pit_contract_requires_true_historical_coverage_and_sample_evidence() -> None:
    artifact = _load(ARTIFACT)

    assert artifact["contract"] == {
        "required_artifacts": [
            "DATE_EFFECTIVE_PIT_UNIVERSE",
            "SYMBOL_IDENTITY_AND_LISTING_DELISTING_REFERENCE",
            "DAILY_INDUSTRY_AND_MARKET_CAP_REFERENCE",
            "CORPORATE_ACTION_REFERENCE",
            "TWSE_TPEX_TRADING_CALENDAR",
        ],
        "required_market_scope": ["TWSE", "TPEX"],
        "required_security_scope": "ORDINARY_EQUITIES_INCLUDING_LATER_DELISTED_SECURITIES",
        "required_temporal_semantics": "DATE_EFFECTIVE_PRE_OPEN_OR_PRIOR_AVAILABLE_REFERENCE",
    }
    tej = next(
        candidate
        for candidate in artifact["source_candidates"]
        if candidate["candidate_id"] == "TEJ_TQUANT_PIT_REFERENCE_DATASETS"
    )
    assert tej["status"] == "CANDIDATE_PENDING_ENTITLEMENT_AND_QUALIFICATION"
    assert tej["documented_dataset_ids"] == [
        "TWN/APISTOCK",
        "TWN/APISTKATTR",
        "TWN/APISHRACT",
        "TWN/TRADEDAY_TWSE",
    ]
    assert "NO_ACQUIRED_METADATA_OR_RAW_SAMPLE" in tej["gaps"]
    assert "BOUNDED_METADATA_ONLY_SAMPLE_WITH_IMMUTABLE_DIGESTS" in artifact[
        "written_qualification_requirements"
    ]
