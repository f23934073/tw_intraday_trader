import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_data.clock import ReplayClock
from market_data.events import MarketStreamKind, TickEvent
from market_data.health import DataHealthState
from market_data.ingestion import IngestStatus
from market_data.replay import (
    ReplayDatasetLoader,
    ReplayRunner,
    content_sha256,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "8039_2026-08-18_phase2_replay.json"
)
TAIPEI = ZoneInfo("Asia/Taipei")


def test_loader_validates_manifest_and_builds_stable_row_identities():
    dataset = ReplayDatasetLoader().load(FIXTURE)

    assert dataset.manifest.row_count == 5
    assert len(dataset.events) == 5
    assert dataset.events[0].event_id == (
        f"{dataset.manifest.content_sha256}:0"
    )
    assert dataset.events[-1].source_identity.endswith(":4")
    assert [event.stream_kind for event in dataset.events] == [
        MarketStreamKind.TICK,
        MarketStreamKind.BIDASK,
        MarketStreamKind.TICK,
        MarketStreamKind.BIDASK,
        MarketStreamKind.TICK,
    ]
    with pytest.raises(FrozenInstanceError):
        dataset.events[0].symbol = "2330"


def test_8039_fixture_preserves_observed_price_and_cumulative_volume_change():
    dataset = ReplayDatasetLoader().load(FIXTURE)
    ticks = [
        event.payload
        for event in dataset.events
        if isinstance(event.payload, TickEvent)
    ]

    assert str(ticks[0].price) == "272"
    assert str(ticks[-1].price) == "278"
    assert ticks[-1].total_volume_lots - ticks[0].total_volume_lots == 2306
    assert ticks[-1].total_volume_lots == 11112


def test_same_dataset_replays_ten_times_with_one_digest():
    dataset = ReplayDatasetLoader().load(FIXTURE)
    results = [ReplayRunner().run(dataset) for _ in range(10)]

    assert len({result.digest for result in results}) == 1
    assert all(result.event_count == 5 for result in results)
    assert all(
        tuple(item.status for item in result.ingest_results)
        == (IngestStatus.APPLIED,) * 5
        for result in results
    )
    assert all(result.health.state is DataHealthState.HEALTHY for result in results)


def test_manifest_hash_mismatch_fails_before_event_construction(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["events"][0]["price"] = "999"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="content_sha256 mismatch"):
        ReplayDatasetLoader().load(changed)


def test_received_time_reordering_fails_even_with_recomputed_manifest(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["events"][1], raw["events"][2] = (
        raw["events"][2],
        raw["events"][1],
    )
    raw["content_sha256"] = content_sha256(
        raw["references"],
        raw["events"],
    )
    reordered = tmp_path / "reordered.json"
    reordered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="ordered by received_at"):
        ReplayDatasetLoader().load(reordered)


def test_naive_timestamp_fails_even_with_recomputed_manifest(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["events"][0]["event_at"] = "2026-08-18T09:16:00"
    raw["content_sha256"] = content_sha256(
        raw["references"],
        raw["events"],
    )
    naive = tmp_path / "naive.json"
    naive.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="timezone-aware"):
        ReplayDatasetLoader().load(naive)


def test_replay_clock_advances_only_from_explicit_event_time():
    start = datetime(2026, 8, 18, 9, 0, tzinfo=TAIPEI)
    clock = ReplayClock(start)
    clock.sleep_until(start + timedelta(seconds=1))

    assert clock.now() == start + timedelta(seconds=1)
    assert clock.session_date() == start.date()
    with pytest.raises(ValueError, match="cannot move backward"):
        clock.sleep_until(start)
