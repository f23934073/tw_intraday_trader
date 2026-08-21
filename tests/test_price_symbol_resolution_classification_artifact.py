"""Drift gates for the fail-closed symbol 1259 classification."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "price_symbol_resolution_1259_v1_2026-08-20.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
UPSTREAM = ARTIFACT.with_name("price_acquisition_resolution_v1_2026-08-20.json")
UPSTREAM_DIGEST = UPSTREAM.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {
            nested
            for child in value.values()
            for nested in _all_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _all_keys(child)}
    return set()


def test_symbol_resolution_artifact_has_stable_digest_and_identity() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == "price_symbol_resolution_classification_v1"
    assert artifact["identity"] == {
        "job_id": "dataset-download-f914feaddea04e37b3cbdcfce2b0179b",
        "market": "TPEX",
        "name": "安心",
        "provider": "ShioajiProvider",
        "requested_end_date": "2026-08-18",
        "requested_start_date": "2023-08-19",
        "symbol": "1259",
    }
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_symbol_resolution_references_exact_price_resolution_revision() -> None:
    artifact = _load(ARTIFACT)
    upstream = _load(UPSTREAM)
    assert artifact["resolution_reference"] == {
        "artifact_id": upstream["artifact_id"],
        "canonical_sha256": UPSTREAM_DIGEST.read_text().strip(),
    }


def test_official_evidence_rejects_structural_no_data() -> None:
    artifact = _load(ARTIFACT)
    evidence = artifact["evidence"]
    assert date.fromisoformat(evidence["official_listing"]["listing_date"]) < date.fromisoformat(
        artifact["identity"]["requested_start_date"]
    )
    assert evidence["official_daily_report"]["report_date"] == artifact["identity"][
        "requested_end_date"
    ]
    assert evidence["official_daily_report"]["requested_date_honored"] is True
    assert evidence["official_daily_report"]["symbol_row_count"] == 1
    assert artifact["classification"]["security_data_disposition"] == "NOT_STRUCTURAL_NO_DATA"


def test_provider_mismatch_has_bounded_probe_and_market_controls() -> None:
    artifact = _load(ARTIFACT)
    evidence = artifact["evidence"]
    assert artifact["classification"]["decision"] == "SYMBOL_SPECIFIC_PROVIDER_COVERAGE_MISMATCH"
    assert evidence["bounded_provider_probe"]["persisted"] is False
    assert evidence["bounded_provider_probe"]["bar_count"] == 0
    assert evidence["provider_contract"]["exchange"] == "OTC"
    assert evidence["provider_contract"]["security_type"] == "STK"
    assert all(item["market"] == "TPEX" for item in evidence["same_job_tpex_controls"]["partitions"])
    assert all(item["bar_count"] > 0 for item in evidence["same_job_tpex_controls"]["partitions"])


def test_unknown_root_cause_cannot_authorize_retry_or_exclusion() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["classification"]["root_cause"] == "UNKNOWN_WITHIN_PROVIDER_PATH"
    assert artifact["status"] == "BLOCKED"
    assert set(artifact["permissions"].values()) == {False}
    assert "Repeat the unchanged full resume request." in artifact["recommended_resolution"][
        "forbidden_actions"
    ]


def test_classification_contains_no_price_or_outcome_values() -> None:
    keys = _all_keys(_load(ARTIFACT))
    assert keys.isdisjoint(
        {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "return",
            "pnl",
            "setup_success",
            "holdout_result",
        }
    )
