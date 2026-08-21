import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from watchlist.import_adapter import (
    CanonicalPitEquityUniverseImportAdapter,
    EquityUniverseImportError,
)
from watchlist.reference_data import (
    PIT_UNIVERSE_MISSING,
    SURVIVORSHIP_LIMITED,
    DateEffectiveEquityRecord,
    EquityUniverseArtifact,
    EquityUniverseSnapshot,
    MarketCapCohort,
    SnapshotEquityUniverse,
    UniverseEvidenceMode,
)
from watchlist.serialization import (
    EQUITY_UNIVERSE_MANIFEST_SCHEMA_VERSION,
    EQUITY_UNIVERSE_SNAPSHOT_SCHEMA_VERSION,
    EquityUniverseSerializationError,
    deserialize_manifest,
    deserialize_snapshot,
    manifest_sha256,
    serialize_manifest,
    serialize_snapshot,
    snapshot_sha256,
)


FIXTURES = Path(__file__).parent / "fixtures" / "watchlist"
SNAPSHOT_PATH = FIXTURES / "pit_equity_universe_snapshot_v1.json"
MANIFEST_PATH = FIXTURES / "pit_equity_universe_manifest_v1.json"
EXPECTED_SNAPSHOT_SHA256 = (
    "c21e82dbd550f1f4e7e05102f538342039b95a09996fec780a173efce0dee7b1"
)


def load_artifact() -> EquityUniverseArtifact:
    snapshot = deserialize_snapshot(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    manifest = deserialize_manifest(MANIFEST_PATH.read_text(encoding="utf-8"))
    return EquityUniverseArtifact(snapshot=snapshot, manifest=manifest)


def test_canonical_snapshot_and_manifest_round_trip_with_stable_digest() -> None:
    artifact = load_artifact()
    snapshot_json = serialize_snapshot(artifact.snapshot)
    manifest_json = serialize_manifest(artifact.manifest)

    assert EQUITY_UNIVERSE_SNAPSHOT_SCHEMA_VERSION == (
        "pit_equity_universe_snapshot_v1"
    )
    assert EQUITY_UNIVERSE_MANIFEST_SCHEMA_VERSION == (
        "pit_equity_universe_manifest_v1"
    )
    assert deserialize_snapshot(snapshot_json) == artifact.snapshot
    assert deserialize_manifest(manifest_json) == artifact.manifest
    assert snapshot_sha256(artifact.snapshot) == EXPECTED_SNAPSHOT_SHA256
    assert artifact.manifest.content_digest == EXPECTED_SNAPSHOT_SHA256
    assert manifest_sha256(artifact.manifest) == manifest_sha256(
        deserialize_manifest(manifest_json)
    )


def test_import_adapter_loads_sealed_bytes_and_historical_queries_are_pit() -> None:
    universe = CanonicalPitEquityUniverseImportAdapter().load(
        snapshot_payload=SNAPSHOT_PATH.read_bytes(),
        manifest_payload=MANIFEST_PATH.read_bytes(),
    )

    historical = universe.resolve(date(2022, 6, 1))
    recent = universe.resolve(date(2024, 6, 1))

    assert historical.research_eligible
    assert {record.symbol for record in historical.active_records} == {
        "A001",
        "B002",
        "C003",
    }
    assert {record.symbol for record in historical.research_members} == {
        "A001",
        "C003",
    }
    historical_c003 = next(
        record for record in historical.research_members if record.symbol == "C003"
    )
    assert historical_c003.industry_code == "ELECTRONICS"
    assert historical_c003.market_cap_cohort is MarketCapCohort.SMALL
    assert historical_c003.industry_as_of == date(2021, 1, 1)
    assert historical_c003.market_cap_as_of == date(2021, 1, 1)

    assert recent.research_eligible
    assert {record.symbol for record in recent.active_records} == {
        "B002",
        "C003",
        "D004",
    }
    assert {record.symbol for record in recent.research_members} == {
        "B002",
        "C003",
        "D004",
    }
    recent_c003 = next(
        record for record in recent.research_members if record.symbol == "C003"
    )
    assert recent_c003.industry_code == "INDUSTRIAL"
    assert recent_c003.market_cap_cohort is MarketCapCohort.LARGE
    assert "A001" not in {record.symbol for record in recent.active_records}
    assert "D004" not in {record.symbol for record in historical.active_records}


def test_future_revision_cannot_mutate_a_pinned_historical_snapshot() -> None:
    base = load_artifact()
    pinned = SnapshotEquityUniverse(base)
    before = pinned.resolve(date(2024, 6, 1))

    current_c003 = next(
        record
        for record in base.snapshot.records
        if record.symbol == "C003" and record.effective_from == date(2023, 1, 1)
    )
    records = tuple(
        replace(record, effective_to=date(2025, 1, 1))
        if record is current_c003
        else record
        for record in base.snapshot.records
    )
    future_c003 = replace(
        current_c003,
        industry_code="FUTURE_CLASSIFICATION",
        industry_name="未來分類",
        industry_as_of=date(2025, 1, 1),
        market_cap_twd=240_000_000_000,
        market_cap_as_of=date(2025, 1, 1),
        effective_from=date(2025, 1, 1),
    )
    revised_snapshot = EquityUniverseSnapshot(
        snapshot_id="pit-universe-reviewed-fixture-v2",
        records=records + (future_c003,),
    )
    revised_manifest = replace(
        base.manifest,
        snapshot_id=revised_snapshot.snapshot_id,
        source_revision=2,
        parent_snapshot_id=base.snapshot.snapshot_id,
        record_count=len(revised_snapshot.records),
        content_digest=snapshot_sha256(revised_snapshot),
    )
    revised = SnapshotEquityUniverse(
        EquityUniverseArtifact(revised_snapshot, revised_manifest)
    )

    assert pinned.resolve(date(2024, 6, 1)) == before
    revised_2024 = revised.resolve(date(2024, 6, 1))
    assert [
        (
            record.symbol,
            record.security_type,
            record.industry_code,
            record.market_cap_cohort,
        )
        for record in revised_2024.research_members
    ] == [
        (
            record.symbol,
            record.security_type,
            record.industry_code,
            record.market_cap_cohort,
        )
        for record in before.research_members
    ]
    future = revised.resolve(date(2025, 6, 1))
    future_c003_result = next(
        record for record in future.research_members if record.symbol == "C003"
    )
    assert future_c003_result.industry_code == "FUTURE_CLASSIFICATION"
    assert snapshot_sha256(base.snapshot) == EXPECTED_SNAPSHOT_SHA256


def test_current_snapshot_is_never_research_eligible() -> None:
    artifact = load_artifact()
    current = SnapshotEquityUniverse(
        EquityUniverseArtifact(
            snapshot=artifact.snapshot,
            manifest=replace(
                artifact.manifest,
                evidence_mode=UniverseEvidenceMode.CURRENT_SNAPSHOT,
            ),
        )
    ).resolve(date(2024, 6, 1))

    assert not current.research_eligible
    assert current.research_members == ()
    assert PIT_UNIVERSE_MISSING in current.issue_codes
    assert SURVIVORSHIP_LIMITED in current.issue_codes
    assert not current.cross_sectional_diagnostics_allowed
    assert not current.matched_controls_allowed
    assert not current.formal_research_allowed
    assert current.active_records


@pytest.mark.parametrize(
    "manifest_change",
    [
        {"coverage_start": None},
        {"coverage_end": None},
        {"covered_markets": frozenset()},
        {"source_digest": None},
        {"content_digest": None},
    ],
)
def test_missing_coverage_or_digest_returns_pit_universe_missing(
    manifest_change: dict[str, object],
) -> None:
    artifact = load_artifact()
    incomplete = EquityUniverseArtifact(
        snapshot=artifact.snapshot,
        manifest=replace(artifact.manifest, **manifest_change),
    )

    resolution = SnapshotEquityUniverse(incomplete).resolve(date(2022, 6, 1))

    assert not resolution.research_eligible
    assert resolution.research_members == ()
    assert PIT_UNIVERSE_MISSING in resolution.issue_codes


def test_out_of_coverage_and_overlapping_records_fail_closed() -> None:
    artifact = load_artifact()
    out_of_coverage = SnapshotEquityUniverse(artifact).resolve(date(2020, 6, 1))
    assert PIT_UNIVERSE_MISSING in out_of_coverage.issue_codes

    c003 = next(
        record
        for record in artifact.snapshot.records
        if record.symbol == "C003" and record.effective_from == date(2023, 1, 1)
    )
    overlapping = replace(c003, industry_code="OVERLAP")
    snapshot = EquityUniverseSnapshot(
        snapshot_id="overlapping-v1",
        records=artifact.snapshot.records + (overlapping,),
    )
    manifest = replace(
        artifact.manifest,
        snapshot_id=snapshot.snapshot_id,
        record_count=len(snapshot.records),
        content_digest=snapshot_sha256(snapshot),
    )
    resolution = SnapshotEquityUniverse(
        EquityUniverseArtifact(snapshot, manifest)
    ).resolve(date(2024, 6, 1))

    assert not resolution.research_eligible
    assert "UNIVERSE_INTERVAL_OVERLAP" in resolution.issue_codes
    assert PIT_UNIVERSE_MISSING in resolution.issue_codes


def test_row_source_digest_must_match_the_manifest_source_digest() -> None:
    artifact = load_artifact()
    first = artifact.snapshot.records[0]
    records = (replace(first, source_digest="b" * 64),) + artifact.snapshot.records[1:]
    snapshot = EquityUniverseSnapshot(snapshot_id="source-conflict-v1", records=records)
    manifest = replace(
        artifact.manifest,
        snapshot_id=snapshot.snapshot_id,
        content_digest=snapshot_sha256(snapshot),
    )

    resolution = SnapshotEquityUniverse(
        EquityUniverseArtifact(snapshot, manifest)
    ).resolve(date(2024, 6, 1))

    assert not resolution.research_eligible
    assert resolution.research_members == ()
    assert "UNIVERSE_SOURCE_DIGEST_MISMATCH" in resolution.issue_codes
    assert PIT_UNIVERSE_MISSING in resolution.issue_codes


def test_import_adapter_rejects_digest_and_row_count_conflicts() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["content_digest"] = "b" * 64
    with pytest.raises(EquityUniverseImportError) as digest_error:
        CanonicalPitEquityUniverseImportAdapter().load(
            snapshot_payload=SNAPSHOT_PATH.read_bytes(),
            manifest_payload=json.dumps(manifest).encode("utf-8"),
        )
    assert digest_error.value.code == "CONTENT_DIGEST_MISMATCH"

    manifest["content_digest"] = EXPECTED_SNAPSHOT_SHA256
    manifest["record_count"] = 5
    with pytest.raises(EquityUniverseImportError) as row_count_error:
        CanonicalPitEquityUniverseImportAdapter().load(
            snapshot_payload=SNAPSHOT_PATH.read_bytes(),
            manifest_payload=json.dumps(manifest).encode("utf-8"),
        )
    assert row_count_error.value.code == "ROW_COUNT_MISMATCH"


def test_imported_manifest_without_digest_stays_visible_but_research_blocked() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["content_digest"] = None
    universe = CanonicalPitEquityUniverseImportAdapter().load(
        snapshot_payload=SNAPSHOT_PATH.read_bytes(),
        manifest_payload=json.dumps(manifest).encode("utf-8"),
    )

    resolution = universe.resolve(date(2022, 6, 1))

    assert resolution.active_records
    assert resolution.research_members == ()
    assert not resolution.research_eligible
    assert PIT_UNIVERSE_MISSING in resolution.issue_codes
    assert "UNIVERSE_DIGEST_MISSING" in resolution.issue_codes


def test_snapshot_schema_drift_and_future_as_of_evidence_fail_closed() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    payload["records"][0]["unexpected"] = True
    with pytest.raises(EquityUniverseSerializationError, match="unexpected fields"):
        deserialize_snapshot(json.dumps(payload))

    valid = load_artifact().snapshot.records[0]
    with pytest.raises(ValueError, match="industry_as_of"):
        replace(valid, industry_as_of=valid.effective_from.replace(year=2026))


def test_record_contract_marks_only_explicit_common_stock_as_eligible() -> None:
    records: tuple[DateEffectiveEquityRecord, ...] = load_artifact().snapshot.records
    b002_history = [record for record in records if record.symbol == "B002"]

    assert [record.equity_eligible for record in b002_history] == [False, True]
