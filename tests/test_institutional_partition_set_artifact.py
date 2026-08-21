"""Drift and replay gates for the first institutional partition-set artifact."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from institutional_data.artifacts import (
    DirectoryInstitutionalRawArtifactStore,
    InstitutionalRawArtifactKey,
)
from institutional_data.domain import InstitutionalMarket
from institutional_data.serialization import (
    canonical_json,
    deserialize_flow_rows,
    deserialize_partition_manifest,
    flow_rows_sha256,
    sha256_text,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = (
    ROOT / "research" / "institutional_evaluation" / "datasets" / "institutional"
)
PARTITION_SET = (
    DATASET_ROOT
    / "partition_sets"
    / "institutional_partition_set_v1_2026-08-19.json"
)
PARTITION_SET_DIGEST = PARTITION_SET.with_suffix(".canonical.sha256")
ACQUISITION_R2 = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "dataset_acquisition_manifest_v1_2026-08-20_r2.json"
)
ACQUISITION_R2_DIGEST = ACQUISITION_R2.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def _normalized_paths(partition: dict[str, Any]) -> tuple[Path, Path]:
    directory = (
        DATASET_ROOT
        / "normalized"
        / partition["market"].lower()
        / "2026-08-19"
    )
    stem = partition["partition_id"]
    return directory / f"{stem}.flows.json", directory / f"{stem}.manifest.json"


def test_partition_set_digest_and_partial_coverage_are_frozen() -> None:
    artifact = _load(PARTITION_SET)
    expected = PARTITION_SET_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(artifact)) == expected
    assert artifact["schema_version"] == "institutional_partition_set_v1"
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"
    assert artifact["status"] == "VALIDATED_PARTIAL_COVERAGE"
    assert artifact["formal_history_complete"] is False
    assert artifact["coverage"] == {
        "end_date": "2026-08-19",
        "markets": ["TWSE", "TPEX"],
        "session_count": 1,
        "start_date": "2026-08-19",
    }


def test_partition_set_replays_two_validated_market_partitions() -> None:
    partitions = _load(PARTITION_SET)["partitions"]

    assert {partition["market"] for partition in partitions} == {"TWSE", "TPEX"}
    assert sum(partition["normalized_row_count"] for partition in partitions) == 2228

    for partition in partitions:
        flow_path, manifest_path = _normalized_paths(partition)
        rows = deserialize_flow_rows(flow_path.read_text(encoding="utf-8"))
        manifest_json = manifest_path.read_text(encoding="utf-8")
        manifest = deserialize_partition_manifest(manifest_json)

        assert partition["status"] == "VALIDATED"
        assert partition["validation_issue_count"] == 0
        assert len(rows) == partition["normalized_row_count"]
        assert len({row.symbol for row in rows}) == len(rows)
        assert {row.market.value for row in rows} == {partition["market"]}
        assert {row.session_date.isoformat() for row in rows} == {"2026-08-19"}
        assert {row.partition_id for row in rows} == {partition["partition_id"]}
        assert flow_rows_sha256(rows) == partition["normalized_sha256"]
        assert sha256_text(canonical_json(json.loads(manifest_json))) == (
            partition["partition_manifest_sha256"]
        )
        assert manifest.partition_id == partition["partition_id"]
        assert manifest.raw_artifact_id == partition["raw_artifact_id"]
        assert manifest.raw_sha256 == partition["raw_sha256"]


def test_raw_revisions_preserve_quarantine_and_include_only_correct_tpex() -> None:
    store = DirectoryInstitutionalRawArtifactStore(DATASET_ROOT / "raw")
    tpex_key = InstitutionalRawArtifactKey(
        market=InstitutionalMarket.TPEX,
        session_date=date(2026, 8, 19),
        source_product="TPEX_INSTI_DAILY_EW",
        trade_scope_id="TPEX_DAILY_ORIGINAL_TRADES_V1",
    )
    revisions = store.revisions(tpex_key)
    included = {
        partition["raw_artifact_id"] for partition in _load(PARTITION_SET)["partitions"]
    }

    assert len(revisions) == 2
    assert dict(revisions[0].request_parameters)["date"] == "20260819"
    assert revisions[0].artifact_id not in included
    assert dict(revisions[1].request_parameters)["date"] == "2026/08/19"
    assert revisions[1].artifact_id in included

    for partition in _load(PARTITION_SET)["partitions"]:
        raw = store.get(partition["raw_artifact_id"])
        assert raw is not None
        assert raw.revision == partition["raw_revision"]
        assert raw.raw_sha256 == partition["raw_sha256"]


def test_acquisition_r2_promotes_only_institutional_to_partial() -> None:
    manifest = _load(ACQUISITION_R2)
    expected = ACQUISITION_R2_DIGEST.read_text(encoding="utf-8").strip()
    partition_set_digest = PARTITION_SET_DIGEST.read_text(encoding="utf-8").strip()
    institutional = manifest["datasets"]["institutional"]

    assert sha256_text(canonical_json(manifest)) == expected
    assert institutional == {
        "acquired_markets": ["TWSE", "TPEX"],
        "artifact_count": 1,
        "artifact_id": "institutional-partition-set-v1-2026-08-19-pilot",
        "canonical_sha256": partition_set_digest,
        "coverage_end": "2026-08-19",
        "coverage_start": "2026-08-19",
        "planned_sources": institutional["planned_sources"],
        "required_markets": ["TWSE", "TPEX"],
        "row_count": 2228,
        "status": "PARTIAL",
    }
    issue_codes = {issue["code"] for issue in manifest["issues"]}
    assert "INSTITUTIONAL_PARTITIONS_MISSING" not in issue_codes
    assert "INSTITUTIONAL_HISTORY_INCOMPLETE" in issue_codes
    assert all(issue["severity"] == "BLOCKING" for issue in manifest["issues"])
    assert manifest["gate"] == {
        "composite_manifest_allowed": False,
        "coverage_revision_allowed": False,
        "holdout_allowed": False,
        "outcome_generation_allowed": False,
        "population_freeze_allowed": False,
        "status": "BLOCKED",
    }


def test_partition_set_and_acquisition_r2_contain_no_outcome_fields() -> None:
    forbidden = {
        "executed",
        "execution_count",
        "expectancy",
        "fill_price",
        "gross_return",
        "net_expectancy",
        "net_return",
        "pnl",
        "price_value",
        "setup_qualified",
        "win_rate",
    }

    assert _all_keys(_load(PARTITION_SET)).isdisjoint(forbidden)
    assert _all_keys(_load(ACQUISITION_R2)).isdisjoint(forbidden)
    assert _load(ACQUISITION_R2)["inspection_scope"]["outcome_fields_read"] is False
