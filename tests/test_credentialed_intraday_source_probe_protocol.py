"""Drift gates for the pre-payload credentialed intraday source probe."""

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
    / "credentialed_intraday_source_probe_protocol_v1_2026-08-20.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
UPSTREAM = ARTIFACT.with_name("intraday_source_qualification_v1_2026-08-20.json")
UPSTREAM_DIGEST = UPSTREAM.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_protocol_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == "credentialed_intraday_source_probe_protocol_v1"
    assert artifact["artifact_id"] == (
        "credentialed-intraday-source-probe-protocol-v1-2026-08-20-r1"
    )
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_protocol_references_exact_qualification_artifact() -> None:
    artifact = _load(ARTIFACT)
    upstream = _load(UPSTREAM)
    assert artifact["upstream_reference"] == {
        "artifact_id": upstream["artifact_id"],
        "canonical_sha256": UPSTREAM_DIGEST.read_text().strip(),
    }


def test_owner_approved_vwap_tolerance_is_frozen() -> None:
    tolerance = _load(ARTIFACT)["vwap_reconciliation"]["tolerance"]
    assert tolerance == {
        "absolute_twd": "0.01",
        "formula": "max(0.01 TWD, reference_vwap * 0.0001)",
        "relative_fraction": "0.0001",
    }


def test_probe_scope_is_fixed_before_payload_access() -> None:
    probe = _load(ARTIFACT)["fixed_probe"]
    assert probe["session_date"] == "2026-08-18"
    assert [item["symbol"] for item in probe["symbols"]] == [
        "1259",
        "1240",
        "12561",
        "2330",
        "2317",
    ]
    assert probe["request"] == {
        "fields": "open,high,low,close,volume,average",
        "from": "2026-08-18",
        "sort": "asc",
        "timeframe": "1",
        "to": "2026-08-18",
    }


def test_protocol_forbids_secret_persistence_and_silent_fill() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["credential_policy"]["credential_value_may_be_logged"] is False
    assert artifact["credential_policy"]["credential_value_may_be_persisted"] is False
    assert artifact["missing_bar_policy"]["synthetic_zero_volume_fill_allowed"] is False
    assert artifact["decision_policy"]["unknown_or_unclassified_result"] == (
        "INSUFFICIENT_EVIDENCE"
    )


def test_protocol_requires_cross_market_reconciliation() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["decision_policy"]["minimum_cross_market_vwap_controls"] == {
        "TPEX": 1,
        "TWSE": 1,
    }
    assert artifact["normalization_policy"]["volume"]["normalization"] == (
        "MULTIPLY_BY_1000"
    )
