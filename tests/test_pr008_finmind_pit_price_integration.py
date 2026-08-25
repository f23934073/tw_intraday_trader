"""Drift gates for the PR-008 FinMind engineering/PIT acquisition boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research/institutional_evaluation/acquisition"
REFERENCE = ACQUISITION / "finmind_engineering_reference_registration_v1_2026-08-24.json"
REFERENCE_DIGEST = REFERENCE.with_suffix(".canonical.sha256")
CONTRACT = ACQUISITION / "finmind_pit_price_acquisition_contract_v1_2026-08-24.json"
CONTRACT_DIGEST = CONTRACT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_finmind_pr008_artifact_digests_are_frozen() -> None:
    for artifact, digest_path in ((REFERENCE, REFERENCE_DIGEST), (CONTRACT, CONTRACT_DIGEST)):
        assert sha256_text(canonical_json(_load(artifact))) == digest_path.read_text(
            encoding="utf-8"
        ).strip()


def test_registration_freezes_engineering_only_dataset_identity() -> None:
    reference = _load(REFERENCE)
    dataset = reference["dataset_reference"]

    assert reference["schema_version"] == "finmind_engineering_reference_registration_v1"
    assert dataset["dataset_id"] == (
        "dataset-finmind-sponsor-sha256-"
        "88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6"
    )
    assert dataset["artifact_path"].endswith("/manifest.json")
    assert len(dataset["manifest_digest"]) == 64
    assert len(dataset["bars_sha256"]) == 64
    assert dataset["universe_scope"] == "CURRENT_SNAPSHOT"
    assert set(dataset["issues"]) == {
        "AMOUNT_DERIVED_PROXY",
        "CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",
        "PARTIAL_MARKET_UNIVERSE",
        "RAW_PRICE_UNADJUSTED",
        "REFERENCE_METADATA_CURRENT_NOT_PIT",
    }
    assert reference["classification"] == {
        "existing_dataset_is_formal_pr008_price_dataset": False,
        "formal_holdout_eligible": False,
        "outcome_observation_recorded": True,
        "outcome_values_recorded_in_this_artifact": False,
        "purpose": "ENGINEERING_REFERENCE_AND_PIT_ACQUISITION_IMPLEMENTATION_BASELINE",
        "research_eligible": False,
    }
    assert all(value is False for value in reference["permissions"].values())


def test_pit_contract_requires_new_identity_and_all_missing_lineage() -> None:
    contract = _load(CONTRACT)

    assert contract["schema_version"] == "finmind_pit_price_acquisition_contract_v1"
    assert contract["status"] == "PREREGISTERED_BLOCKED"
    assert contract["dataset_identity_policy"] == {
        "existing_engineering_dataset_id": (
            "dataset-finmind-sponsor-sha256-"
            "88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6"
        ),
        "must_be_distinct_from_existing_engineering_dataset": True,
        "new_dataset_identity_required_after_acquisition": True,
        "silent_cross_provider_mixing_allowed": False,
    }
    assert contract["current_input_status"] == {
        "corporate_actions": "MISSING",
        "existing_finmind_dataset": "ENGINEERING_REFERENCE_ONLY",
        "historical_institutional_partitions": "MISSING",
        "pit_universe": "MISSING",
        "reference_data": "MISSING",
        "trading_calendar": "PARTIAL",
    }
    assert all(value is False for value in contract["execution_lock"].values())
    assert contract["pit_acquisition_contract"]["target_date_range"] is None
    assert set(contract["prerequisites"]) == {
        "PIT_UNIVERSE_ARTIFACT_WITH_DATE_EFFECTIVE_SECURITY_IDENTITY",
        "HISTORICAL_INSTITUTIONAL_PARTITION_SET_ARTIFACT",
        "TWSE_AND_TPEX_CALENDAR_ARTIFACT",
        "REFERENCE_DATA_ARTIFACT_WITH_SYMBOL_CONTINUITY",
        "CORPORATE_ACTION_ARTIFACT",
        "FROZEN_TARGET_DATE_RANGE_AND_CHRONOLOGICAL_SPLIT",
        "UNOBSERVED_FORMAL_HOLDOUT_DECLARATION",
        "SOURCE_ENTITLEMENT_AND_RETENTION_EVIDENCE",
        "PIT_ACQUISITION_PLAN_DIGEST",
    }


def test_contract_preserves_coverage_policy_and_vwap_requirements() -> None:
    contract = _load(CONTRACT)

    assert contract["formal_coverage_gate"] == {
        "minimum_aggregate_session_coverage_rate": "0.99",
        "minimum_per_symbol_session_coverage_rate": "0.99",
        "minimum_symbol_coverage_rate": "0.95",
        "required_concentration_dimensions": [
            "MARKET",
            "MARKET_CAP_COHORT",
            "ADV20_LIQUIDITY_COHORT",
            "INDUSTRY_CODE",
            "LISTING_STATUS_ACTIVE_VS_LATER_DELISTED",
        ],
    }
    acquisition = contract["pit_acquisition_contract"]
    assert acquisition["market_scope"] == ["TWSE", "TPEX"]
    assert acquisition["required_security_scope"] == (
        "DATE_EFFECTIVE_PIT_ORDINARY_EQUITIES_INCLUDING_LATER_DELISTED_SECURITIES"
    )
    assert acquisition["vwap_evidence_requirement"] == (
        "QUALIFIED_TICK_RECONSTRUCTION_OR_SEPARATELY_VALIDATED_AMOUNT_CONTRACT;_"
        "KBAR_ONLY_IS_INSUFFICIENT"
    )
