import hashlib
import json

import pytest

from market_data.capture_artifacts import (
    CaptureArtifactValidationError,
    inspect_capture_artifact,
    load_capture_artifact,
)
from market_data.quote_qualification import QuoteParityStatus, evaluate_quote_parity
from market_data.shioaji_quote_capture import CAPTURE_SCHEMA_VERSION


def artifact() -> dict[str, object]:
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "symbol": "2330",
        "started_at": "2026-08-18T09:00:00+08:00",
        "ended_at": "2026-08-18T09:00:20+08:00",
        "callback_counts": {"quote": 2, "tick": 1, "bidask": 1},
        "quote_capture": {
            "source_mode": "QUOTE",
            "symbol": "2330",
            "observations": [{"kind": "TRADE"}, {"kind": "BOOK"}],
        },
        "tick_bidask_capture": {
            "source_mode": "TICK_BIDASK",
            "symbol": "2330",
            "observations": [{"kind": "TRADE"}, {"kind": "BOOK"}],
        },
        "preliminary_report": {"status": "INCOMPLETE"},
    }


def write_artifact(tmp_path, payload: dict[str, object]):
    path = tmp_path / "2330_capture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_inspection_returns_digest_and_bounded_capture_metadata(tmp_path) -> None:
    path = write_artifact(tmp_path, artifact())

    manifest = inspect_capture_artifact(path)

    assert manifest.artifact_name == "2330_capture.json"
    assert manifest.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest.byte_length == len(path.read_bytes())
    assert manifest.symbol == "2330"
    assert manifest.quote_observation_count == 2
    assert manifest.tick_bidask_observation_count == 2
    assert manifest.quote_callback_count == 2
    assert manifest.preliminary_status == "INCOMPLETE"


def observation(source_mode: str, kind: str) -> dict[str, object]:
    return {
        "source_mode": source_mode,
        "symbol": "2330",
        "kind": kind,
        "event_time": "2026-08-18T09:00:01+08:00",
        "received_at": "2026-08-18T09:00:02+08:00",
        "is_baseline": False,
        "total_volume_lots": 10 if kind == "TRADE" else None,
        "total_amount": "1000" if kind == "TRADE" else None,
        "last_price": "100" if kind == "TRADE" else None,
        "average_price": "100" if kind == "TRADE" else None,
        "raw_tick_type": 1 if kind == "TRADE" else None,
        "bid_side_total_lots": 5 if kind == "TRADE" else None,
        "ask_side_total_lots": 5 if kind == "TRADE" else None,
        "bid_prices": ["99"] if kind == "BOOK" else [],
        "bid_volume_lots": [10] if kind == "BOOK" else [],
        "ask_prices": ["101"] if kind == "BOOK" else [],
        "ask_volume_lots": [10] if kind == "BOOK" else [],
    }


def rehydratable_artifact() -> dict[str, object]:
    payload = artifact()
    for source_name, source_mode in (
        ("quote_capture", "QUOTE"),
        ("tick_bidask_capture", "TICK_BIDASK"),
    ):
        payload[source_name].update(
            {
                "observations": [
                    observation(source_mode, "TRADE"),
                    observation(source_mode, "BOOK"),
                ],
                "reconnect_attempted": False,
                "continuity_verified_after_reconnect": None,
            }
        )
    return payload


def test_loader_rehydrates_captures_for_offline_parity_evaluation(tmp_path) -> None:
    loaded = load_capture_artifact(write_artifact(tmp_path, rehydratable_artifact()))

    assert loaded.quote_capture.observations[0].last_price == 100
    assert loaded.tick_bidask_capture.observations[1].bid_prices == (99,)
    report = evaluate_quote_parity(
        loaded.quote_capture,
        loaded.tick_bidask_capture,
        criteria=None,
    )
    assert report.status is QuoteParityStatus.INCOMPLETE


def test_loader_rejects_invalid_observation_decimal(tmp_path) -> None:
    payload = rehydratable_artifact()
    payload["quote_capture"]["observations"][0]["last_price"] = "not-a-number"

    with pytest.raises(CaptureArtifactValidationError, match="decimal-compatible"):
        load_capture_artifact(write_artifact(tmp_path, payload))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update({"schema_version": "unknown"}), "schema version"),
        (
            lambda payload: payload["quote_capture"].update({"source_mode": "TICK_BIDASK"}),
            "source mode",
        ),
        (
            lambda payload: payload.update({"ended_at": "2026-08-18T08:59:59+08:00"}),
            "ended before",
        ),
        (
            lambda payload: payload["callback_counts"].update({"quote": -1}),
            "non-negative",
        ),
    ],
)
def test_invalid_capture_shape_fails_closed(tmp_path, mutate, message: str) -> None:
    payload = artifact()
    mutate(payload)

    with pytest.raises(CaptureArtifactValidationError, match=message):
        inspect_capture_artifact(write_artifact(tmp_path, payload))
