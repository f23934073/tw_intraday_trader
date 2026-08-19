from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from config.momentum_stream import MomentumStreamConfig
from dashboard.momentum_stream import MomentumStreamHub


class MutableMomentumService:
    def __init__(self, snapshot: dict) -> None:
        self.current = deepcopy(snapshot)
        self.read_count = 0

    def snapshot(self) -> dict:
        self.read_count += 1
        return deepcopy(self.current)


def momentum_snapshot(*, symbols: tuple[str, ...] = ("2330",)) -> dict:
    items = [
        {
            "symbol": symbol,
            "availability": "EVALUATED",
            "candidate_score": 40,
            "signal": {"evidence_score": 15},
        }
        for symbol in symbols
    ]
    return {
        "status": "live",
        "mode": "REALTIME_SHADOW_ALERT_ONLY",
        "source": {"is_live": True, "as_of": "2026-08-19T10:00:00+08:00"},
        "summary": {
            "candidate_count": len(items),
            "projection_digest": "fixture",
        },
        "items": items,
        "alerts": [],
        "disclaimer": "data only",
        "notice": "fixture",
    }


def stream_config(*, replay_capacity: int = 3) -> MomentumStreamConfig:
    return MomentumStreamConfig(
        enabled=True,
        coalesce_seconds=60,
        heartbeat_seconds=10,
        replay_capacity=replay_capacity,
        send_timeout_seconds=1,
        max_clients=2,
    )


def test_bootstrap_is_cursor_bound_and_unchanged_capture_keeps_revision():
    service = MutableMomentumService(momentum_snapshot())
    hub = MomentumStreamHub(service, config=stream_config())
    try:
        first = hub.bootstrap()

        assert first["stream"]["schema_version"] == "momentum_dashboard_stream_v1"
        assert first["stream"]["revision"] == 1
        assert first["stream"]["stream_id"]
        assert first["items"][0]["item_digest"]

        assert hub.capture_now() is False
        second = hub.bootstrap()
        assert second["stream"]["revision"] == 1
        assert second["stream"]["stream_id"] == first["stream"]["stream_id"]
    finally:
        hub.close()


def test_changed_capture_emits_idempotent_row_delta_and_removal():
    service = MutableMomentumService(momentum_snapshot(symbols=("2330", "2454")))
    hub = MomentumStreamHub(service, config=stream_config())
    try:
        first = hub.bootstrap()
        stream_id = first["stream"]["stream_id"]
        service.current = momentum_snapshot(symbols=("2330", "2603"))
        service.current["items"][0]["signal"]["evidence_score"] = 20

        assert hub.capture_now() is True
        replay = hub.events_after(stream_id, first["stream"]["revision"])

        assert replay.reason is None
        assert len(replay.events) == 1
        event = replay.events[0]
        assert event["base_revision"] == 1
        assert event["revision"] == 2
        assert event["removed_symbols"] == ["2454"]
        assert event["ordered_symbols"] == ["2330", "2603"]
        assert [item["symbol"] for item in event["item_upserts"]] == [
            "2330",
            "2603",
        ]
    finally:
        hub.close()


def test_replay_rejects_stream_restart_future_cursor_and_evicted_gap():
    service = MutableMomentumService(momentum_snapshot())
    hub = MomentumStreamHub(service, config=stream_config(replay_capacity=2))
    try:
        first = hub.bootstrap()
        stream_id = first["stream"]["stream_id"]

        assert hub.events_after("old-stream", 1).reason == "STREAM_CHANGED"
        assert hub.events_after(stream_id, 2).reason == "INVALID_CURSOR"

        for score in (20, 25, 30):
            service.current["items"][0]["signal"]["evidence_score"] = score
            assert hub.capture_now() is True

        assert hub.events_after(stream_id, 1).reason == "REVISION_TOO_OLD"
        replay = hub.events_after(stream_id, 2)
        assert [event["revision"] for event in replay.events] == [3, 4]
    finally:
        hub.close()


def test_client_registration_is_bounded():
    hub = MomentumStreamHub(
        MutableMomentumService(momentum_snapshot()),
        config=stream_config(),
    )
    try:
        assert hub.try_register_client() is True
        assert hub.try_register_client() is True
        assert hub.try_register_client() is False
        hub.unregister_client()
        assert hub.try_register_client() is True
    finally:
        hub.close()


def test_stream_config_parses_feature_flag_and_rejects_invalid_values():
    config = MomentumStreamConfig.from_environment(
        {
            "MOMENTUM_DASHBOARD_WS_ENABLED": "false",
            "MOMENTUM_DASHBOARD_WS_COALESCE_SECONDS": "0.25",
            "MOMENTUM_DASHBOARD_WS_HEARTBEAT_SECONDS": "5",
            "MOMENTUM_DASHBOARD_WS_REPLAY_CAPACITY": "10",
            "MOMENTUM_DASHBOARD_WS_SEND_TIMEOUT_SECONDS": "0.5",
            "MOMENTUM_DASHBOARD_WS_MAX_CLIENTS": "4",
        }
    )

    assert config.enabled is False
    assert config.coalesce_seconds == 0.25
    assert config.replay_capacity == 10
    assert config.max_clients == 4

    with pytest.raises(ValueError, match="boolean flag"):
        MomentumStreamConfig.from_environment(
            {"MOMENTUM_DASHBOARD_WS_ENABLED": "maybe"}
        )


def test_background_watcher_coalesces_service_changes_into_replay():
    service = MutableMomentumService(momentum_snapshot())
    config = replace(stream_config(), coalesce_seconds=0.01)
    hub = MomentumStreamHub(service, config=config)
    try:
        first = hub.bootstrap()
        service.current["items"][0]["signal"]["evidence_score"] = 35

        replay = hub.wait_for_events(
            first["stream"]["stream_id"],
            first["stream"]["revision"],
            timeout=0.2,
        )

        assert replay.reason is None
        assert [event["revision"] for event in replay.events] == [2]
        assert replay.events[0]["item_upserts"][0]["signal"][
            "evidence_score"
        ] == 35
    finally:
        hub.close()
