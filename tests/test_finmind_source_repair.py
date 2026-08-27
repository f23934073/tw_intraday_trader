"""Contracts for provenance-preserving FinMind source repair."""

from __future__ import annotations

import gzip
import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.domain import HistoricalBar, decimal
from backtest.finmind_history import (
    FinMindHistoryStore,
    FinMindResponse,
    normalize_kbar_response,
)
from backtest.finmind_snapshot import FinMindSemanticSnapshotReader
from backtest.finmind_source_repair import (
    ACTIVE,
    QUARANTINED,
    FinMindSourceRepairError,
    FinMindSourceRepairStore,
    load_repair_resolution,
)


SESSION = date(2026, 3, 20)
OBSERVED_AT = datetime(2026, 8, 27, 3, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _response(data: list[dict[str, object]]) -> FinMindResponse:
    body = json.dumps(
        {"status": 200, "msg": "success", "data": data},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return FinMindResponse(http_status=200, body=body, payload=json.loads(body))


def _database(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(path)
    try:
        job_id = store.ensure_job(
            symbols=("9960",),
            start_date=SESSION,
            end_date=SESSION,
            calendar_symbol="2330",
        )
        store.save_calendar(
            job_id,
            response=_response([{"date": SESSION.isoformat(), "stock_id": "2330"}]),
            dates=(SESSION,),
        )
        store.save_partition(
            job_id,
            symbol="9960",
            session_date=SESSION,
            response=_response([]),
            bars=(),
            status="EMPTY",
        )
    finally:
        store.close()
    return path, job_id


def _mixed_database(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "mixed-history.sqlite3"
    store = FinMindHistoryStore(path)
    try:
        job_id = store.ensure_job(
            symbols=("2330", "9960"),
            start_date=SESSION,
            end_date=SESSION,
            calendar_symbol="2330",
        )
        store.save_calendar(
            job_id,
            response=_response([{"date": SESSION.isoformat(), "stock_id": "2330"}]),
            dates=(SESSION,),
        )
        ready_response = _response(
            [
                {
                    "date": SESSION.isoformat(),
                    "minute": "09:00:00",
                    "stock_id": "2330",
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 7,
                }
            ]
        )
        store.save_partition(
            job_id,
            symbol="2330",
            session_date=SESSION,
            response=ready_response,
            bars=normalize_kbar_response(
                ready_response, symbol="2330", session_date=SESSION
            ),
            status="READY",
        )
        store.save_partition(
            job_id,
            symbol="9960",
            session_date=SESSION,
            response=_response([]),
            bars=(),
            status="EMPTY",
        )
    finally:
        store.close()
    return path, job_id


def _open_case(store: FinMindSourceRepairStore, job_id: str) -> dict[str, object]:
    return dict(
        store.open_case(
            job_id=job_id,
            symbol="9960",
            session_date=SESSION,
            reason_code="OFFICIAL_PRICE_FINMIND_EMPTY",
            evidence_kind="TPEX_OFFICIAL_DAILY_CLOSE",
            source_name="TPEx",
            source_uri="https://example.test/tpex/9960/2026-03-20",
            observed_at=OBSERVED_AT,
            evidence_body=b'{"close":"22.90","volume":1000}',
        )
    )


def _minute_bar(*, timestamp: str = "2026-03-20T09:01:00+08:00") -> HistoricalBar:
    return HistoricalBar(
        symbol="9960",
        timestamp=datetime.fromisoformat(timestamp),
        open=decimal("22.90"),
        high=decimal("22.90"),
        low=decimal("22.90"),
        close=decimal("22.90"),
        volume=1,
        amount=decimal("22.90"),
        session_date=SESSION,
    )


def test_daily_evidence_quarantines_without_mutating_original_partition(
    tmp_path: Path,
) -> None:
    path, job_id = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        before = connection.execute(
            """
            SELECT status, raw_sha256, canonical_sha256, raw_payload
            FROM finmind_history_partitions
            WHERE job_id = ? AND symbol = '9960' AND session_date = ?
            """,
            (job_id, SESSION.isoformat()),
        ).fetchone()
    finally:
        connection.close()

    repairs = FinMindSourceRepairStore(path)
    try:
        first = _open_case(repairs, job_id)
        replay = _open_case(repairs, job_id)
        audit = repairs.audit()

        assert first == replay
        assert first["state"] == QUARANTINED
        assert audit == {
            "schema_version": "finmind-source-repair-v1",
            "case_count": 1,
            "state_counts": {"QUARANTINED": 1},
            "active_bar_count": 0,
            "verified_cases": 1,
            "issue_count": 0,
            "issues": [],
        }
    finally:
        repairs.close()

    connection = sqlite3.connect(path)
    try:
        after = connection.execute(
            """
            SELECT status, raw_sha256, canonical_sha256, raw_payload
            FROM finmind_history_partitions
            WHERE job_id = ? AND symbol = '9960' AND session_date = ?
            """,
            (job_id, SESSION.isoformat()),
        ).fetchone()
    finally:
        connection.close()
    assert after == before


def test_daily_only_evidence_cannot_be_reviewed_or_activated(tmp_path: Path) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
        with pytest.raises(
            FinMindSourceRepairError, match="daily-only evidence cannot be approved"
        ):
            repairs.review(
                case_id=str(case["case_id"]),
                evidence_id=str(case["discrepancy_evidence_id"]),
                decision="APPROVE",
                reviewer="reviewer-a",
                rationale="daily close exists",
            )
    finally:
        repairs.close()


def test_open_case_rejects_changed_primary_discrepancy_evidence(
    tmp_path: Path,
) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        _open_case(repairs, job_id)
        with pytest.raises(
            FinMindSourceRepairError,
            match="different discrepancy evidence",
        ):
            repairs.open_case(
                job_id=job_id,
                symbol="9960",
                session_date=SESSION,
                reason_code="OFFICIAL_PRICE_FINMIND_EMPTY",
                evidence_kind="TPEX_OFFICIAL_DAILY_CLOSE",
                source_name="TPEx",
                source_uri="https://example.test/tpex/9960/2026-03-20",
                observed_at=OBSERVED_AT,
                evidence_body=b'{"close":"23.00","volume":2000}',
            )
    finally:
        repairs.close()


def test_minute_candidate_requires_explicit_timestamp_and_target_contract(
    tmp_path: Path,
) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
        with pytest.raises(
            FinMindSourceRepairError,
            match="outside observable regular-session bounds",
        ):
            repairs.propose_minute_evidence(
                case_id=str(case["case_id"]),
                source_name="alternate-provider",
                source_uri="https://example.test/minute/9960",
                observed_at=OBSERVED_AT,
                evidence_body=b"raw-minute-response",
                bars=(_minute_bar(timestamp="2026-03-20T09:00:00+08:00"),),
            )
    finally:
        repairs.close()


def test_minute_candidate_preserves_finmind_amount_contract(tmp_path: Path) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
        with pytest.raises(
            FinMindSourceRepairError,
            match="close times volume proxy contract",
        ):
            repairs.propose_minute_evidence(
                case_id=str(case["case_id"]),
                source_name="alternate-provider",
                source_uri="https://example.test/minute/9960",
                observed_at=OBSERVED_AT,
                evidence_body=b"raw-minute-response",
                bars=(replace(_minute_bar(), amount=decimal("999")),),
            )
    finally:
        repairs.close()


def test_reviewed_minute_evidence_activates_idempotent_overlay(tmp_path: Path) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
        candidate = repairs.propose_minute_evidence(
            case_id=str(case["case_id"]),
            source_name="alternate-provider",
            source_uri="https://example.test/minute/9960",
            observed_at=OBSERVED_AT,
            evidence_body=b"raw-minute-response",
            bars=(_minute_bar(),),
        )
        evidence_id = str(candidate["candidate_evidence_id"])
        replayed_candidate = repairs.propose_minute_evidence(
            case_id=str(case["case_id"]),
            source_name="alternate-provider",
            source_uri="https://example.test/minute/9960",
            observed_at=OBSERVED_AT,
            evidence_body=b"raw-minute-response",
            bars=(_minute_bar(),),
        )
        approved = repairs.review(
            case_id=str(case["case_id"]),
            evidence_id=evidence_id,
            decision="APPROVE",
            reviewer="reviewer-a",
            rationale="minute source includes an exchange-local event timestamp",
        )
        replayed_approval = repairs.review(
            case_id=str(case["case_id"]),
            evidence_id=evidence_id,
            decision="APPROVE",
            reviewer="reviewer-a",
            rationale="minute source includes an exchange-local event timestamp",
        )
        activated = repairs.activate(
            case_id=str(case["case_id"]),
            review_id=str(approved["current_review_id"]),
            actor="dataset-curator",
            change_note="activate reviewed alternate minute evidence",
        )
        replayed_activation = repairs.activate(
            case_id=str(case["case_id"]),
            review_id=str(approved["current_review_id"]),
            actor="dataset-curator",
            change_note="activate reviewed alternate minute evidence",
        )

        assert replayed_candidate == candidate
        assert replayed_approval == approved
        assert replayed_activation == activated
        assert activated["state"] == ACTIVE
        assert repairs.audit()["active_bar_count"] == 1
    finally:
        repairs.close()

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        resolution = load_repair_resolution(
            connection,
            job_id=job_id,
            symbol="9960",
            session_date=SESSION,
        )
    finally:
        connection.close()
    assert resolution is not None and resolution.is_active
    assert [bar.to_dict() for bar in resolution.bars] == [_minute_bar().to_dict()]


def test_audit_detects_repair_evidence_tampering(tmp_path: Path) -> None:
    path, job_id = _database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
        evidence_id = str(case["discrepancy_evidence_id"])
    finally:
        repairs.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            UPDATE finmind_source_repair_evidence
            SET raw_payload = ? WHERE evidence_id = ?
            """,
            (b"not-gzip", evidence_id),
        )
        connection.commit()
    finally:
        connection.close()

    repairs = FinMindSourceRepairStore(path)
    try:
        audit = repairs.audit()
        assert audit["verified_cases"] == 0
        assert audit["issue_count"] == 1
        assert "Not a gzipped file" in audit["issues"][0]
    finally:
        repairs.close()


def test_snapshot_excludes_pending_case_and_streams_active_overlay(
    tmp_path: Path,
) -> None:
    path, job_id = _mixed_database(tmp_path)
    repairs = FinMindSourceRepairStore(path)
    try:
        case = _open_case(repairs, job_id)
    finally:
        repairs.close()

    pending_snapshot = tmp_path / "pending.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(path, pending_snapshot)
    pending = FinMindSemanticSnapshotReader(pending_snapshot).inspect()
    assert pending.included_symbols == ("2330",)
    excluded = next(
        item for item in pending.excluded_symbols if item["symbol"] == "9960"
    )
    assert excluded["reason_codes"] == ["SOURCE_REPAIR_PENDING"]
    assert excluded["repair_pending_session_dates"] == [SESSION.isoformat()]

    repairs = FinMindSourceRepairStore(path)
    try:
        candidate = repairs.propose_minute_evidence(
            case_id=str(case["case_id"]),
            source_name="alternate-provider",
            source_uri="https://example.test/minute/9960",
            observed_at=OBSERVED_AT,
            evidence_body=b"raw-minute-response",
            bars=(_minute_bar(),),
        )
        approved = repairs.review(
            case_id=str(case["case_id"]),
            evidence_id=str(candidate["candidate_evidence_id"]),
            decision="APPROVE",
            reviewer="reviewer-a",
            rationale="verified timestamped minute source",
        )
        repairs.activate(
            case_id=str(case["case_id"]),
            review_id=str(approved["current_review_id"]),
            actor="dataset-curator",
            change_note="activate for snapshot integration test",
        )
    finally:
        repairs.close()

    active_snapshot = tmp_path / "active.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(path, active_snapshot)
    reader = FinMindSemanticSnapshotReader(active_snapshot)
    active = reader.inspect()
    assert active.included_symbols == ("2330", "9960")
    repaired_partition = next(
        item
        for item in active.included_partitions
        if item["symbol"] == "9960"
    )
    assert repaired_partition["status"] == "READY"
    assert repaired_partition["bar_count"] == 1
    assert repaired_partition["repair_lineage"][0]["case_id"] == case["case_id"]
    assert repaired_partition["repair_lineage"][0]["source_name"] == "alternate-provider"

    stock_info_body = json.dumps(
        {
            "status": 200,
            "msg": "success",
            "data": [
                {
                    "date": "2026-08-20",
                    "stock_id": "2330",
                    "stock_name": "台積電",
                    "type": "twse",
                },
                {
                    "date": "2026-08-20",
                    "stock_id": "9960",
                    "stock_name": "邁達康",
                    "type": "tpex",
                },
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    stock_info = tmp_path / "stock-info.json.gz"
    stock_info.write_bytes(gzip.compress(stock_info_body, mtime=0))
    plan = reader.plan(
        stock_info_raw=stock_info,
        actor="test-curator",
        planned_at=OBSERVED_AT,
        source_path=path,
        plan_output_parent=tmp_path,
    )
    assert "ALTERNATE_SOURCE_REPAIR" in plan.identity["issues"]
    with reader.open_symbol_bar_streams(plan) as streams:
        observed = {
            symbol: tuple(stream)
            for symbol, stream in zip(
                plan.identity["selection"]["included_symbols"], streams, strict=True
            )
        }
    assert [bar.to_dict() for bar in observed["9960"]] == [
        {
            **_minute_bar().to_dict(),
            "name": "邁達康",
            "market": "TPEX",
        }
    ]
