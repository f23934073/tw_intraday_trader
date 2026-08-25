"""Build a non-promoting result from the FinMind PIT/reference capture manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402


ACQUISITION_ROOT = PROJECT_ROOT / "research/institutional_evaluation/acquisition"
PROTOCOL_PATH = (
    ACQUISITION_ROOT
    / "credentialed_finmind_pit_reference_probe_protocol_v1_2026-08-24.json"
)
CAPTURE_ROOT = (
    ACQUISITION_ROOT
    / "credentialed_finmind_pit_reference_probe_capture_v1_2026-08-24-r1"
)
RESULT_PATH = (
    ACQUISITION_ROOT
    / "credentialed_finmind_pit_reference_probe_result_v1_2026-08-24.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_verified(path: Path) -> tuple[dict[str, Any], str]:
    artifact = _load_json(path)
    digest = sha256_text(canonical_json(artifact))
    expected = path.with_suffix(".canonical.sha256").read_text(encoding="utf-8").strip()
    if digest != expected:
        raise RuntimeError(f"Digest drift detected for {path.name}")
    return artifact, digest


def _record_by_role(
    records: list[object], role: str
) -> Mapping[str, Any]:
    matches = [
        record
        for record in records
        if isinstance(record, Mapping) and record.get("role") == role
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one captured record for role={role}")
    return matches[0]


def _summary(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "date_field_max": record["date_field_max"],
        "date_field_min": record["date_field_min"],
        "field_names": record["field_names"],
        "http_status": record["http_status"],
        "json_status": record["json_status"],
        "raw_response_sha256": record["raw_response_sha256"],
        "row_count": record["row_count"],
    }


def build_result() -> dict[str, Any]:
    protocol, protocol_digest = _digest_verified(PROTOCOL_PATH)
    manifest, manifest_digest = _digest_verified(CAPTURE_ROOT / "capture_manifest.json")
    if manifest["protocol_reference"]["canonical_sha256"] != protocol_digest:
        raise RuntimeError("Capture manifest does not pin the frozen protocol")
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != 8:
        raise RuntimeError("Capture manifest does not contain the frozen request set")
    if any(
        record.get("http_status") != 200
        or record.get("json_status") != 200
        or record.get("data_array_present") is not True
        for record in records
        if isinstance(record, Mapping)
    ):
        raise RuntimeError("Bounded FinMind probe did not obtain a complete successful envelope")
    if not all(isinstance(record, Mapping) for record in records):
        raise RuntimeError("Capture manifest record shape is invalid")

    return {
        "artifact_id": "credentialed-finmind-pit-reference-probe-result-v1-2026-08-24-r1",
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "decision": {
            "authentication": "VERIFIED",
            "bounded_dataset_entitlement": "VERIFIED",
            "formal_pit_reference_source_selected": False,
            "next_gate": "FINMIND_PIT_REFERENCE_SEMANTICS_AND_TERMS_RESOLUTION_V1",
            "verdict": "INSUFFICIENT_EVIDENCE",
        },
        "evidence_scope": {
            "backtest_executed": False,
            "capture_manifest_metadata_read": True,
            "credential_value_persisted": False,
            "outcome_fields_read": False,
            "price_or_kbar_payloads_read": False,
            "raw_provider_payloads_read_during_result_build": False,
        },
        "issues": [
            {
                "code": "PIT_LISTING_START_AND_MARKET_TRANSFER_HISTORY_NOT_OBSERVED",
                "severity": "BLOCKING",
            },
            {
                "code": "PIT_INDUSTRY_CLASSIFICATION_AS_OF_SEMANTICS_NOT_OBSERVED",
                "severity": "BLOCKING",
            },
            {
                "code": "DUAL_MARKET_GLOBAL_CALENDAR_SEMANTICS_NOT_OBSERVED",
                "severity": "BLOCKING",
            },
            {
                "code": "REFERENCE_REVISION_RETENTION_AND_CORRECTION_TERMS_UNEVIDENCED",
                "severity": "BLOCKING",
            },
            {
                "code": "FULL_HISTORICAL_PIT_COVERAGE_NOT_OBSERVED_FROM_BOUNDED_PROBE",
                "severity": "BLOCKING",
            },
        ],
        "observed_schema_evidence": {
            "corporate_actions_tpex": _summary(
                _record_by_role(records, "TPEX_CORPORATE_ACTION_SCHEMA")
            ),
            "corporate_actions_twse": _summary(
                _record_by_role(records, "TWSE_CORPORATE_ACTION_SCHEMA")
            ),
            "delisting": _summary(
                _record_by_role(records, "LATER_DELISTED_SECURITY_SCHEMA")
            ),
            "market_cap_early": _summary(
                _record_by_role(records, "HISTORICAL_MARKET_CAP_EARLY_SCHEMA")
            ),
            "market_cap_late": _summary(
                _record_by_role(records, "HISTORICAL_MARKET_CAP_LATE_SCHEMA")
            ),
            "security_identity": _summary(
                _record_by_role(records, "SECURITY_IDENTITY_AND_MARKET_SCHEMA")
            ),
            "trading_calendar_tpex_control": _summary(
                _record_by_role(records, "TPEX_TRADING_CALENDAR_SCHEMA")
            ),
            "trading_calendar_twse_control": _summary(
                _record_by_role(records, "TWSE_TRADING_CALENDAR_SCHEMA")
            ),
        },
        "permissions": {
            "corporate_action_artifact_allowed": False,
            "formal_universe_artifact_allowed": False,
            "outcome_generation_allowed": False,
            "pit_reference_acquisition_allowed": False,
            "population_freeze_allowed": False,
            "price_dataset_artifact_allowed": False,
            "source_selection_allowed": False,
        },
        "schema_version": "credentialed_finmind_pit_reference_probe_result_v1",
        "source_evidence": {
            "capture_manifest_canonical_sha256": manifest_digest,
            "captured_request_count": len(records),
            "protocol_canonical_sha256": protocol_digest,
            "usage_preflight": manifest["usage_preflight"],
        },
        "upstream_references": {
            "pit_reference_source_resolution": protocol["source_resolution_reference"],
        },
    }


def main() -> None:
    if RESULT_PATH.exists():
        raise RuntimeError("Immutable FinMind PIT/reference result already exists")
    result = build_result()
    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    RESULT_PATH.with_suffix(".canonical.sha256").write_text(
        sha256_text(canonical_json(result)) + "\n", encoding="utf-8"
    )
    print(f"sealed result={RESULT_PATH}")


if __name__ == "__main__":
    main()
