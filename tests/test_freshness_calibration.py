import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta

import pytest

from market_data.freshness_calibration import (
    CAPTURE_SCHEMA_VERSION,
    ConnectionState,
    FreshnessCalibrationArtifactError,
    LiveQuoteFreshnessCapture,
    QuoteFreshnessObservation,
    QuoteStreamKind,
    SubscriptionState,
    _write_json_once,
    analyze_quote_freshness_payload,
    inspect_quote_freshness_artifact,
)


TAIPEI = datetime.fromisoformat("2026-08-19T09:00:00+08:00").tzinfo
assert TAIPEI is not None
BASE = datetime(2026, 8, 19, 9, 0, tzinfo=TAIPEI)


def observation(
    *,
    stream_kind: QuoteStreamKind,
    event_delta_ms: int,
    callback_monotonic_ns: int,
) -> QuoteFreshnessObservation:
    callback = BASE + timedelta(milliseconds=event_delta_ms)
    return QuoteFreshnessObservation(
        symbol="2330",
        liquidity_tier="high",
        session_window="open",
        stream_kind=stream_kind,
        market_event_at=BASE,
        callback_received_at=callback,
        store_updated_at=callback + timedelta(milliseconds=1),
        callback_received_monotonic_ns=callback_monotonic_ns,
        store_updated_monotonic_ns=callback_monotonic_ns + 1_000_000,
        connection_state=ConnectionState.CONNECTED,
        subscription_state=SubscriptionState.ACTIVE,
    )


def payload(
    observations: list[QuoteFreshnessObservation],
    *,
    complete: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "callback_errors": [],
        "observations": observations,
    }
    if complete:
        result.update(
            {
                "started_at": BASE,
                "ended_at": BASE + timedelta(seconds=1),
                "session_window": "open",
                "symbol_tiers": {"2330": "high"},
                "store_boundary": "calibration_in_memory_buffer",
                "threshold_selection": "PROHIBITED_IN_CAPTURE_ARTIFACT",
                "callback_counts": {"TICK": 1, "BIDASK": 0},
                "connection_transitions": [],
            }
        )
    return result


def test_analysis_keeps_clock_skew_and_separates_tick_bidask_groups() -> None:
    report = analyze_quote_freshness_payload(
        payload(
            [
                observation(
                    stream_kind=QuoteStreamKind.TICK,
                    event_delta_ms=-5,
                    callback_monotonic_ns=1_000_000,
                ),
                observation(
                    stream_kind=QuoteStreamKind.TICK,
                    event_delta_ms=10,
                    callback_monotonic_ns=4_000_000,
                ),
                observation(
                    stream_kind=QuoteStreamKind.BIDASK,
                    event_delta_ms=7,
                    callback_monotonic_ns=2_000_000,
                ),
            ]
        )
    )

    assert report["review_status"] == "REVIEW_REQUIRED"
    assert report["threshold_candidates"] is None
    tick = next(group for group in report["groups"] if group["stream_kind"] == "TICK")
    assert tick["source_clock_skew_count"] == 1
    assert tick["event_to_callback_ms"]["min"] == -5.0
    assert tick["inter_arrival_ms"]["p50"] == 3.0
    assert report["missing_stream_kinds"] == []


def test_empty_capture_is_insufficient_and_does_not_fill_thresholds() -> None:
    report = analyze_quote_freshness_payload(payload([]))

    assert report["review_status"] == "INSUFFICIENT_EVIDENCE"
    assert report["threshold_candidates"] is None
    assert report["missing_stream_kinds"] == ["TICK", "BIDASK"]


def test_artifact_inspection_is_digest_backed_and_rejects_unaware_timestamps(tmp_path) -> None:
    artifact = tmp_path / "freshness.json"
    encode = lambda value: (
        value.isoformat()
        if isinstance(value, datetime)
        else value.value
        if hasattr(value, "value")
        else asdict(value)
        if is_dataclass(value)
        else value
    )
    artifact.write_text(json.dumps(payload([observation(
        stream_kind=QuoteStreamKind.TICK,
        event_delta_ms=5,
        callback_monotonic_ns=1_000_000,
    )], complete=True), default=encode), encoding="utf-8")

    inspection = inspect_quote_freshness_artifact(artifact)

    assert inspection["artifact_name"] == "freshness.json"
    assert inspection["sha256"]
    assert inspection["analysis"]["review_status"] == "REVIEW_REQUIRED"

    invalid = payload([observation(
        stream_kind=QuoteStreamKind.TICK,
        event_delta_ms=5,
        callback_monotonic_ns=1_000_000,
    )])
    invalid["observations"][0] = {
        **json.loads(json.dumps(invalid["observations"][0], default=encode)),
        "callback_received_at": "2026-08-19T09:00:01",
    }
    with pytest.raises(FreshnessCalibrationArtifactError, match="timezone-aware"):
        analyze_quote_freshness_payload(invalid)


def test_collector_records_callback_and_explicit_store_boundary() -> None:
    capture = LiveQuoteFreshnessCapture({"2330": "high"}, "continuous")
    capture.transition(
        ConnectionState.CONNECTED,
        SubscriptionState.ACTIVE,
        detail="test",
    )
    event = type(
        "Tick",
        (),
        {"code": "2330", "datetime": BASE, "intraday_odd": False},
    )()

    capture.on_tick(None, event)
    artifact = capture.payload(
        started_at=BASE,
        ended_at=BASE + timedelta(seconds=1),
        simulation=True,
        sdk_version="test",
    )

    assert artifact["store_boundary"] == "calibration_in_memory_buffer"
    assert artifact["callback_counts"] == {"TICK": 1, "BIDASK": 0}
    assert artifact["observations"][0].stream_kind is QuoteStreamKind.TICK


def test_collector_requires_paired_ack_before_marking_a_symbol_active() -> None:
    capture = LiveQuoteFreshnessCapture({"2330": "high"}, "continuous")
    capture.transition(
        ConnectionState.CONNECTED,
        SubscriptionState.PENDING,
        detail="subscribe_requested",
    )
    event = type(
        "Tick",
        (),
        {"code": "2330", "datetime": BASE, "intraday_odd": False},
    )()

    capture.on_lifecycle(200, 16, "TIC/v1/STK/*/TSE/2330", "subscribe")
    capture.on_tick(None, event)
    capture.on_lifecycle(200, 16, "QUO/v1/STK/*/TSE/2330", "subscribe")
    capture.on_tick(None, event)

    states = [item.subscription_state for item in capture.observations]
    assert states == [SubscriptionState.PENDING, SubscriptionState.ACTIVE]
    assert capture.connection_transitions[-1].raw_event_code == 16
    assert capture.connection_transitions[-1].raw_info == "QUO/v1/STK/*/TSE/2330"


def test_collector_preserves_active_symbol_when_another_symbol_is_pending() -> None:
    capture = LiveQuoteFreshnessCapture(
        {"2330": "high", "2317": "mid"},
        "continuous",
    )
    capture.transition(
        ConnectionState.CONNECTED,
        SubscriptionState.PENDING,
        detail="subscribe_requested",
    )
    high_event = type(
        "Tick",
        (),
        {"code": "2330", "datetime": BASE, "intraday_odd": False},
    )()
    mid_event = type(
        "Tick",
        (),
        {"code": "2317", "datetime": BASE, "intraday_odd": False},
    )()

    capture.on_lifecycle(200, 16, "TIC/v1/STK/*/TSE/2330", "subscribe")
    capture.on_lifecycle(200, 16, "QUO/v1/STK/*/TSE/2330", "subscribe")
    capture.on_tick(None, high_event)
    capture.on_tick(None, mid_event)
    capture.on_lifecycle(200, 16, "TIC/v1/STK/*/TSE/2317", "subscribe")
    capture.on_lifecycle(200, 16, "QUO/v1/STK/*/TSE/2317", "subscribe")
    capture.on_tick(None, high_event)
    capture.on_tick(None, mid_event)

    states = [item.subscription_state for item in capture.observations]
    assert states == [
        SubscriptionState.ACTIVE,
        SubscriptionState.PENDING,
        SubscriptionState.ACTIVE,
        SubscriptionState.ACTIVE,
    ]


def test_writer_uses_exclusive_create_for_evidence_artifacts(tmp_path) -> None:
    capture = LiveQuoteFreshnessCapture({"2330": "high"}, "open")
    artifact = capture.payload(
        started_at=BASE,
        ended_at=BASE + timedelta(seconds=1),
        simulation=True,
        sdk_version="test",
    )
    path = tmp_path / "freshness.json"

    _write_json_once(path, artifact)

    with pytest.raises(FileExistsError):
        _write_json_once(path, artifact)
