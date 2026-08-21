"""Fail-closed gates for the first PR-008 uniform coverage audit snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research/institutional_evaluation/coverage/data_coverage_audit_v1_2026-08-21_repository_snapshot.json"
AUDIT_DIGEST = AUDIT.with_suffix(".canonical.sha256")
AMENDMENT = ROOT / "research/institutional_evaluation/protocols/formal_evaluation_coverage_amendment_v1_2026-08-21.json"
AMENDMENT_DIGEST = AMENDMENT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _all_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_coverage_audit_digest_and_amendment_reference_are_frozen() -> None:
    audit = _load(AUDIT)
    amendment = _load(AMENDMENT)
    expected_amendment_digest = AMENDMENT_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(audit)) == AUDIT_DIGEST.read_text(encoding="utf-8").strip()
    assert sha256_text(canonical_json(amendment)) == expected_amendment_digest
    assert audit["amendment"] == {
        "artifact_id": amendment["artifact_id"],
        "canonical_sha256": expected_amendment_digest,
    }


def test_unavailable_population_keeps_all_measurements_and_exclusions_unresolved() -> None:
    audit = _load(AUDIT)

    assert all(value is None for value in audit["coverage_measurements"].values())
    assert audit["exclusions"] == {
        "materialized": False,
        "named_symbol_overrides": [],
        "records": [],
    }
    assert "1259" not in canonical_json(audit)
    assert "12561" not in canonical_json(audit)


def test_blocking_inputs_and_unapproved_concentration_keep_execution_disabled() -> None:
    audit = _load(AUDIT)
    issue_codes = {issue["code"] for issue in audit["issues"]}

    assert issue_codes == {
        "PIT_UNIVERSE_MISSING",
        "FORMAL_PRICE_DATASET_MISSING",
        "INSTITUTIONAL_COMMON_RANGE_INCOMPLETE",
        "CORPORATE_ACTION_REFERENCE_CALENDAR_INCOMPLETE",
        "SYMBOL_COVERAGE_UNRESOLVED",
        "SESSION_COVERAGE_UNRESOLVED",
        "MISSINGNESS_CONCENTRATION_UNRESOLVED",
        "COVERAGE_CONCENTRATION_OWNER_APPROVAL_MISSING",
    }
    assert all(issue["severity"] == "BLOCKING" for issue in audit["issues"])
    assert audit["gate"] == {
        "coverage_policy_preregistered": True,
        "dataset_population_freeze_allowed": False,
        "holdout_allowed": False,
        "missingness_concentration_owner_approved": False,
        "outcome_generation_allowed": False,
        "status": "BLOCKED",
    }


def test_coverage_audit_contains_no_outcome_fields() -> None:
    audit = _load(AUDIT)
    forbidden = {
        "executed",
        "execution_count",
        "expectancy",
        "fill_price",
        "gross_return",
        "net_expectancy",
        "net_return",
        "pnl",
        "price",
        "setup_qualified",
        "win_rate",
    }

    assert audit["inspection_scope"]["outcome_fields_read"] is False
    assert _all_keys(audit).isdisjoint(forbidden)
