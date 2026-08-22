import json
from pathlib import Path

import pytest

from market_data.freshness_calibration import FreshnessCalibrationArtifactError
from market_data.freshness_calibration import CAPTURE_SCHEMA_VERSION
from market_data.freshness_calibration_quality import summarize_post_capture_quality


COHORT = {"2886": "high", "6863": "mid", "1530": "low"}
BASE = "2026-08-20T09:00:00+08:00"


def write_artifact(tmp_path: Path, *, omit: tuple[str, str] | None = None) -> Path:
    observations = []
    transitions = []
    monotonic = 1_000_000
    for symbol, tier in COHORT.items():
        for stream_kind, lifecycle_kind in (("TICK", "TIC"), ("BIDASK", "QUO")):
            transitions.append(
                {
                    "occurred_at": BASE,
                    "connection_state": "CONNECTED",
                    "subscription_state": "ACTIVE",
                    "detail": "Subscribe or Unsubscribe ok",
                    "raw_response_code": 200,
                    "raw_event_code": 16,
                    "raw_info": f"{lifecycle_kind}/v1/STK/*/TSE/{symbol}",
                }
            )
            if (symbol, stream_kind) == omit:
                continue
            observations.append(
                {
                    "symbol": symbol,
                    "liquidity_tier": tier,
                    "session_window": "opening",
                    "stream_kind": stream_kind,
                    "market_event_at": BASE,
                    "callback_received_at": BASE,
                    "store_updated_at": BASE,
                    "callback_received_monotonic_ns": monotonic,
                    "store_updated_monotonic_ns": monotonic + 1,
                    "connection_state": "CONNECTED",
                    "subscription_state": "ACTIVE",
                }
            )
            monotonic += 1_000_000
    payload = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "sdk_version": "test",
        "simulation": True,
        "started_at": BASE,
        "ended_at": "2026-08-20T09:15:00+08:00",
        "session_window": "opening",
        "symbol_tiers": COHORT,
        "store_boundary": "calibration_in_memory_buffer",
        "callback_counts": {"TICK": 3, "BIDASK": 3},
        "callback_errors": [],
        "connection_transitions": transitions,
        "observations": observations,
        "threshold_selection": "PROHIBITED_IN_CAPTURE_ARTIFACT",
    }
    path = tmp_path / "quote.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_post_capture_quality_reports_complete_structural_evidence(tmp_path: Path) -> None:
    report = summarize_post_capture_quality(
        write_artifact(tmp_path),
        expected_symbol_tiers=COHORT,
        expected_session_window="opening",
    )

    assert report["quality_status"] == "REVIEW_REQUIRED"
    assert report["observed_group_count"] == 6
    assert report["missing_groups"] == []
    assert report["paired_acknowledgement"]["missing_groups"] == []
    assert report["threshold_candidates"] is None
    assert report["threshold_selection"] == "NOT_PERFORMED"


def test_post_capture_quality_preserves_partial_coverage_for_review(tmp_path: Path) -> None:
    report = summarize_post_capture_quality(
        write_artifact(tmp_path, omit=("1530", "TICK")),
        expected_symbol_tiers=COHORT,
        expected_session_window="opening",
    )

    assert report["quality_status"] == "REVIEW_REQUIRED_PARTIAL_COVERAGE"
    assert report["observed_group_count"] == 5
    assert report["missing_groups"] == [
        {
            "symbol": "1530",
            "liquidity_tier": "low",
            "session_window": "opening",
            "stream_kind": "TICK",
        }
    ]
    assert report["paired_acknowledgement"]["missing_groups"] == []


def test_post_capture_quality_rejects_invalid_artifact_without_rewriting_it(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(FreshnessCalibrationArtifactError):
        summarize_post_capture_quality(
            path,
            expected_symbol_tiers=COHORT,
            expected_session_window="opening",
        )

    assert path.read_text(encoding="utf-8") == "{}"
