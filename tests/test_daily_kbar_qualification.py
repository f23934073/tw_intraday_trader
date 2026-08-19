from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from market_data.daily_kbar_qualification import (
    DailySourcePath,
    build_capture_artifact,
    build_chunk_boundary_artifact,
    build_session_contract,
    qualify_daily_kbar_source,
    read_json,
)
from market_data.daily_kbar_reconciliation import (
    TWSE_STOCK_DAY_FIELDS,
    build_twse_stock_day_capture,
    reconcile_completed_session,
)


def _raw(timestamp_values: list[int]):
    count = len(timestamp_values)
    return {
        "ts": timestamp_values,
        "Open": [100.0] * count,
        "High": [101.0] * count,
        "Low": [99.0] * count,
        "Close": [Decimal("100.50")] * count,
        "Volume": [1000] * count,
    }


def _capture(name: str, timestamps: list[int]):
    return build_capture_artifact(
        capture_name=name,
        symbol="2330",
        query_start=date(2026, 8, 18),
        query_end=date(2026, 8, 18),
        queried_at=datetime.fromisoformat("2026-08-19T12:00:00+08:00"),
        sdk_version="test",
        raw_kbars=_raw(timestamps),
    )


def _timestamp(hour: int, minute: int, day: int = 18) -> int:
    # These synthetic values follow the Provider's documented Taiwan-wall-time
    # timestamp convention: epoch components are deliberately not UTC shifted.
    return int(
        datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1_000_000_000
    )


def test_g0_preserves_raw_float_type_and_fails_closed_without_finalization():
    full = _capture("full", [_timestamp(9, 0), _timestamp(13, 30)])
    partial = _capture("partial", [_timestamp(9, 0), _timestamp(12, 0, 19)])
    daily = _capture("daily", [_timestamp(9, 0), _timestamp(13, 30)])
    left = _capture("left", [_timestamp(9, 0, 17), _timestamp(13, 30, 17)])
    right = _capture("right", [_timestamp(9, 0), _timestamp(13, 30)])
    boundary = build_chunk_boundary_artifact(
        symbol="2330", sdk_version="test", left=left, right=right
    )
    contract = build_session_contract(
        calendar_version="test-v1",
        source_url="https://example.invalid/twse.csv",
        source_retrieved_at=datetime.fromisoformat("2026-08-19T12:00:00+08:00"),
        official_csv_sha256="a" * 64,
        explicitly_non_trading_dates=[],
    )

    reports = qualify_daily_kbar_source(
        daily_capture=daily,
        full_session_capture=full,
        partial_session_capture=partial,
        chunk_boundary_capture=boundary,
        session_contract=contract,
        now=datetime.fromisoformat("2026-08-19T12:00:00+08:00"),
    )

    assert reports["source_contract"]["daily_capture"]["raw_numeric_representation"]["Open"] == {"builtins.float": 2}
    assert reports["completion_evidence"]["full_session"]["coverage_complete"] is True
    assert reports["completion_evidence"]["full_session"]["is_complete"] is False
    assert reports["completion_evidence"]["same_completed_session_requery"]["all_identical"] is True
    assert reports["source_contract"]["daily_capture"]["timestamp_semantics"] == "WALL_TIME_MAPPING_OBSERVED_NOT_PROVIDER_DOCUMENTED"
    assert reports["qualification_result"]["selected_path"] == DailySourcePath.BLOCKED
    assert reports["qualification_result"]["candidate_path_if_completion_is_later_proven"] == DailySourcePath.DERIVED_FINALIZED_SESSION_V1


def test_checked_in_g0_artifacts_replay_without_shioaji_sdk():
    root = Path(__file__).resolve().parents[1] / "research" / "daily_kbar_g0"
    fixtures = root / "fixtures"
    existing_resolution = read_json(root / "qualification" / "session_resolution.json")
    reports = qualify_daily_kbar_source(
        daily_capture=read_json(fixtures / "shioaji_daily_sample.json"),
        full_session_capture=read_json(fixtures / "shioaji_intraday_full_session_sample.json"),
        partial_session_capture=read_json(fixtures / "shioaji_partial_session_sample.json"),
        chunk_boundary_capture=read_json(fixtures / "shioaji_chunk_boundary_sample.json"),
        session_contract=existing_resolution["session_contract"],
        now=datetime.fromisoformat("2026-08-19T12:17:00+08:00"),
        completion_reconciliation=(
            read_json(root / "qualification" / "twse_daily_reconciliation.json")
            if (root / "qualification" / "twse_daily_reconciliation.json").exists()
            else None
        ),
    )

    assert reports["qualification_result"]["selected_path"] == DailySourcePath.DERIVED_FINALIZED_SESSION_V1
    for name, report in reports.items():
        assert report == read_json(root / "qualification" / f"{name}.json")


def test_official_daily_ohlc_reconciliation_proves_common_lot_kbar_volume():
    session_date = date(2026, 8, 18)
    capture = build_capture_artifact(
        capture_name="reconciliation",
        symbol="2330",
        query_start=session_date,
        query_end=session_date,
        queried_at=datetime.fromisoformat("2026-08-19T12:00:00+08:00"),
        sdk_version="test",
        raw_kbars={
            "ts": [_timestamp(9, 1), _timestamp(13, 30)],
            "Open": [100.0, 101.0],
            "High": [100.0, 101.0],
            "Low": [100.0, 101.0],
            "Close": [100.0, 101.0],
            "Volume": [1, 2],
            "Amount": [100_000.0, 202_000.0],
        },
        extra_fields=("Amount",),
    )
    response = {
        "stat": "OK",
        "date": "20260801",
        "title": "fixture",
        "fields": list(TWSE_STOCK_DAY_FIELDS),
        "data": [["115/08/18", "3,000", "302,000", "100.00", "101.00", "100.00", "101.00", "+1.00", "2", ""]],
        "notes": ["fixture"],
    }
    official = build_twse_stock_day_capture(
        symbol="2330",
        requested_month=session_date.replace(day=1),
        retrieved_at=datetime.fromisoformat("2026-08-19T12:00:00+08:00"),
        raw_response=json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode(),
    )

    result = reconcile_completed_session(
        shioaji_capture=capture,
        twse_capture=official,
        session_date=session_date,
    )

    assert result["status"] == "QUALIFIED_FOR_DERIVED_FINALIZED_SESSION_V1"
    assert result["comparison"]["ohlc_matches"] == {
        "Open": True,
        "High": True,
        "Low": True,
        "Close": True,
    }
    assert result["shioaji_regular_session"]["volume"] == {
        "raw_value": 3,
        "unit": "COMMON_LOT",
        "shares_per_lot": 1000,
        "equivalent_shares": 3000,
        "amount_lot_consistent_rows": 2,
        "amount_lot_eligible_rows": 2,
    }
