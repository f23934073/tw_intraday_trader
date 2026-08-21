"""Pre-payload drift gates for the Sponsor-asserted FinMind r2 probe."""

from __future__ import annotations

import json
from pathlib import Path

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research" / "institutional_evaluation" / "acquisition"
R1 = ACQUISITION / (
    "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21.json"
)
R2 = ACQUISITION / (
    "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21_r2.json"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_r2_has_new_identity_and_canonical_digest() -> None:
    r2 = _load(R2)
    assert r2["artifact_id"] == (
        "credentialed-finmind-intraday-source-probe-protocol-v1-2026-08-21-r2"
    )
    assert sha256_text(canonical_json(r2)) == (
        R2.with_suffix(".canonical.sha256").read_text().strip()
    )


def test_sponsor_is_owner_assertion_not_observed_entitlement() -> None:
    authentication = _load(R2)["authentication"]
    assert authentication["owner_asserted_account_level"] == "SPONSOR"
    assert authentication["owner_assertion_is_not_observed_entitlement"] is True
    assert authentication["credential_value_may_be_persisted"] is False


def test_r2_requests_are_byte_semantically_equal_to_r1() -> None:
    assert _load(R2)["fixed_requests"] == _load(R1)["fixed_requests"]
    assert _load(R2)["http_contract"] == _load(R1)["http_contract"]


def test_r2_inherits_all_semantic_and_decision_rules_without_change() -> None:
    r1_digest = R1.with_suffix(".canonical.sha256").read_text().strip()
    r2 = _load(R2)
    assert r2["semantic_protocol_reference"]["canonical_sha256"] == r1_digest
    assert r2["semantic_protocol_reference"][
        "kbar_tick_volume_vwap_rules_changed"
    ] is False
    assert r2["decision_policy_reference"] == {
        "canonical_sha256": r1_digest,
        "rules_changed": False,
    }


def test_r2_references_immutable_denied_r1_result() -> None:
    result = ACQUISITION / (
        "credentialed_finmind_intraday_source_probe_result_v1_2026-08-21.json"
    )
    assert _load(R2)["prior_denied_result_reference"]["canonical_sha256"] == (
        result.with_suffix(".canonical.sha256").read_text().strip()
    )
