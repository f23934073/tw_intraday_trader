"""Drift gates for the approved provider-coverage continuation policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "research/institutional_evaluation/acquisition/price_coverage_observation_continuation_v1_2026-08-21.json"
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
AMENDMENT = ROOT / "research/institutional_evaluation/protocols/formal_evaluation_coverage_amendment_v1_2026-08-21.json"
AMENDMENT_DIGEST = AMENDMENT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_continuation_policy_digest_and_amendment_lineage_are_frozen() -> None:
    artifact = _load(ARTIFACT)
    amendment = _load(AMENDMENT)
    amendment_digest = AMENDMENT_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text(encoding="utf-8").strip()
    assert sha256_text(canonical_json(amendment)) == amendment_digest
    assert artifact["coverage_amendment"] == {
        "artifact_id": amendment["artifact_id"],
        "canonical_sha256": amendment_digest,
    }


def test_provider_empty_is_observation_not_success_or_exclusion() -> None:
    artifact = _load(ARTIFACT)
    continuation = artifact["continuation"]
    semantics = artifact["evidence_semantics"]

    assert continuation["provider_empty_reason_code"] == "PRICE_DATA_UNAVAILABLE"
    assert continuation["provider_empty_action"] == (
        "WRITE_ZERO_BAR_ERROR_OBSERVATION_AND_CONTINUE"
    )
    assert continuation["explicit_option_required"] is True
    assert continuation["default_downloader_policy_unchanged"] is True
    assert semantics["empty_observation_counts_as_data_success"] is False
    assert semantics["empty_observation_counts_as_formal_evaluation_exclusion"] is False
    assert semantics["empty_observation_counts_as_provider_coverage_evidence"] is True
    assert semantics["named_symbol_special_case"] is False
    assert semantics["synthetic_fill_allowed"] is False


def test_current_snapshot_scan_cannot_unlock_formal_research() -> None:
    artifact = _load(ARTIFACT)

    assert artifact["resulting_staging_constraints"] == {
        "formal_coverage_audit_allowed": False,
        "research_eligible": False,
        "survivorship_free": False,
        "universe_selection": "ALL_CURRENT",
        "use": "PROVIDER_COVERAGE_OBSERVATION_ONLY",
    }
    assert all(value is False for value in artifact["execution_lock"].values())
    assert artifact["evidence_semantics"]["outcome_fields_read"] is False
    assert artifact["evidence_semantics"]["price_values_read_for_decision"] is False
