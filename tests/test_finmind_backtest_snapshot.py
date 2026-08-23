"""Contracts for the immutable FinMind-to-backtest snapshot plan."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog
from backtest.domain import canonical_json
from backtest.finmind_history import (
    FinMindHistoryStore,
    FinMindResponse,
    normalize_kbar_response,
)
from backtest.finmind_snapshot import (
    FinMindSemanticSnapshotReader,
    FinMindSnapshotConflict,
    FinMindSnapshotError,
    FinMindSnapshotPlan,
    load_snapshot_plan,
    save_snapshot_plan,
    verify_snapshot_plan_handoff,
)
from scripts.materialize_finmind_backtest_dataset import (
    create_snapshot_plan,
    execute_snapshot_plan,
    main as plan_cli_main,
)


SESSION_1 = date(2026, 8, 17)
SESSION_2 = date(2026, 8, 18)
SESSION_3 = date(2026, 8, 19)
PLANNED_AT = datetime.fromisoformat("2026-08-23T12:00:00+08:00")


def _response(data: list[dict[str, object]]) -> FinMindResponse:
    body = json.dumps(
        {"status": 200, "msg": "success", "data": data},
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    return FinMindResponse(http_status=200, body=body, payload=json.loads(body))


def _calendar_response(*dates: date) -> FinMindResponse:
    return _response(
        [{"date": value.isoformat(), "stock_id": "2330"} for value in dates]
    )


def _kbar(symbol: str, session_date: date, *, close: int = 101) -> dict[str, object]:
    return {
        "date": session_date.isoformat(),
        "minute": "09:00:00",
        "stock_id": symbol,
        "open": 100,
        "high": max(102, close),
        "low": min(99, close),
        "close": close,
        "volume": 7,
    }


def _write_stock_info(path: Path, rows: list[dict[str, object]]) -> Path:
    body = json.dumps(
        {"status": 200, "msg": "success", "data": rows},
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    path.write_bytes(gzip.compress(body, mtime=0))
    return path


def _stock_info_row(
    symbol: str,
    name: str,
    *,
    market: str = "twse",
    observed: str = "2026-08-20",
    industry: str = "半導體業",
) -> dict[str, object]:
    return {
        "date": observed,
        "stock_id": symbol,
        "stock_name": name,
        "type": market,
        "industry_category": industry,
    }


def _save_partition(
    store: FinMindHistoryStore,
    job_id: str,
    symbol: str,
    session_date: date,
    *,
    close: int = 101,
    status: str = "READY",
) -> None:
    rows = [] if status == "EMPTY" else [_kbar(symbol, session_date, close=close)]
    response = _response(rows)
    bars = (
        normalize_kbar_response(
            response,
            symbol=symbol,
            session_date=session_date,
        )
        if status != "INVALID"
        else ()
    )
    store.save_partition(
        job_id,
        symbol=symbol,
        session_date=session_date,
        response=response,
        bars=bars,
        status=status,
        error_message="fixture invalid" if status == "INVALID" else None,
    )


def _save_partition_rows(
    store: FinMindHistoryStore,
    job_id: str,
    symbol: str,
    session_date: date,
    *,
    closes: tuple[int, ...] = (101, 102),
) -> None:
    rows = []
    for minute, close in enumerate(closes):
        row = _kbar(symbol, session_date, close=close)
        row["minute"] = f"09:{minute:02d}:00"
        rows.append(row)
    response = _response(rows)
    bars = normalize_kbar_response(
        response,
        symbol=symbol,
        session_date=session_date,
    )
    store.save_partition(
        job_id,
        symbol=symbol,
        session_date=session_date,
        response=response,
        bars=bars,
        status="READY",
    )


def _create_job(
    store: FinMindHistoryStore,
    symbols: tuple[str, ...],
    *,
    dates: tuple[date, ...] = (SESSION_1, SESSION_2),
) -> str:
    job_id = store.ensure_job(
        symbols=symbols,
        start_date=min(dates),
        end_date=max(dates),
        calendar_symbol="2330",
    )
    store.save_calendar(
        job_id,
        response=_calendar_response(*dates),
        dates=dates,
    )
    return job_id


def _plan(
    source: Path,
    snapshot: Path,
    stock_info: Path,
    *,
    actor: str = "test-researcher",
):
    FinMindSemanticSnapshotReader.backup_source(source, snapshot)
    return FinMindSemanticSnapshotReader(snapshot).plan(
        stock_info_raw=stock_info,
        actor=actor,
        planned_at=PLANNED_AT,
        source_path=source,
        plan_output_parent=snapshot.parent,
    )


def test_online_backup_freezes_source_before_later_partitions(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        first_job = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, first_job, "2330", session_date)
        snapshot = tmp_path / "snapshot.sqlite3"
        FinMindSemanticSnapshotReader.backup_source(source, snapshot)

        second_job = _create_job(store, ("2317", "2330"))
        for symbol in ("2317", "2330"):
            for session_date in (SESSION_1, SESSION_2):
                _save_partition(store, second_job, symbol, session_date)
    finally:
        store.close()

    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電"), _stock_info_row("2317", "鴻海")],
    )
    plan = FinMindSemanticSnapshotReader(snapshot).plan(
        stock_info_raw=stock_info,
        actor="test-researcher",
        planned_at=PLANNED_AT,
        source_path=source,
        plan_output_parent=tmp_path,
    )

    assert plan.identity["selection"]["included_symbols"] == ["2330"]
    assert plan.identity["counts"]["included_symbol_count"] == 1


def test_plan_excludes_partial_and_invalid_symbols_but_accepts_empty(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2317", "2330", "9999"))
        _save_partition(store, job_id, "2330", SESSION_1)
        _save_partition(store, job_id, "2330", SESSION_2, status="EMPTY")
        _save_partition(store, job_id, "2317", SESSION_1)
        _save_partition(store, job_id, "9999", SESSION_1, status="INVALID")
        _save_partition(store, job_id, "9999", SESSION_2)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )

    plan = _plan(source, tmp_path / "snapshot.sqlite3", stock_info)

    assert plan.identity["selection"]["included_symbols"] == ["2330"]
    excluded = {
        item["symbol"]: set(item["reason_codes"])
        for item in plan.selection_audit["excluded_symbols"]
    }
    assert excluded == {
        "2317": {"MISSING_SESSION"},
        "9999": {"INVALID_PARTITION"},
    }
    assert plan.identity["counts"]["ready_partition_count"] == 1
    assert plan.identity["counts"]["empty_partition_count"] == 1
    assert plan.identity["counts"]["bar_count"] == 1


def test_equal_cross_job_duplicates_are_deduplicated_with_full_lineage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        first_job = _create_job(store, ("2330",))
        second_job = _create_job(store, ("2317", "2330"))
        for job_id in (first_job, second_job):
            for session_date in (SESSION_1, SESSION_2):
                _save_partition(store, job_id, "2330", session_date)
        _save_partition(store, second_job, "2317", SESSION_1)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )

    plan = _plan(source, tmp_path / "snapshot.sqlite3", stock_info)

    partitions = plan.identity["included_partitions"]
    assert len(partitions) == 2
    assert all(
        row["contributing_job_ids"] == sorted((first_job, second_job))
        for row in partitions
    )


def test_conflicting_cross_job_duplicate_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        first_job = _create_job(store, ("2330",))
        second_job = _create_job(store, ("2317", "2330"))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, first_job, "2330", session_date)
            _save_partition(
                store,
                second_job,
                "2330",
                session_date,
                close=102 if session_date == SESSION_2 else 101,
            )
        _save_partition(store, second_job, "2317", SESSION_1)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "snapshot.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(source, snapshot)

    with pytest.raises(FinMindSnapshotConflict, match="2330/2026-08-18"):
        FinMindSemanticSnapshotReader(snapshot).plan(
            stock_info_raw=stock_info,
            actor="test-researcher",
            planned_at=PLANNED_AT,
            source_path=source,
            plan_output_parent=tmp_path,
        )


def test_incompatible_job_is_reported_without_entering_identity(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        included_job = _create_job(store, ("2330",))
        excluded_job = _create_job(store, ("2317", "2330"))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, included_job, "2330", session_date)
    finally:
        store.close()
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            "UPDATE finmind_history_jobs SET volume_unit = 'SHARES' WHERE job_id = ?",
            (excluded_job,),
        )
        connection.commit()
    finally:
        connection.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )

    plan = _plan(source, tmp_path / "snapshot.sqlite3", stock_info)

    assert plan.selection_audit["compatible_job_ids"] == [included_job]
    assert plan.selection_audit["excluded_jobs"] == [
        {"job_id": excluded_job, "reason_codes": ["UNSUPPORTED_VOLUME_UNIT"]}
    ]


def test_excluded_symbol_progress_changes_audit_but_not_immutable_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(
            store,
            ("2317", "2330"),
            dates=(SESSION_1, SESSION_2, SESSION_3),
        )
        for session_date in (SESSION_1, SESSION_2, SESSION_3):
            _save_partition(store, job_id, "2330", session_date)
        _save_partition(store, job_id, "2317", SESSION_1)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )

    first = _plan(source, tmp_path / "snapshot-1.sqlite3", stock_info)

    store = FinMindHistoryStore(source)
    try:
        _save_partition(store, job_id, "2317", SESSION_2)
    finally:
        store.close()
    second = _plan(source, tmp_path / "snapshot-2.sqlite3", stock_info)

    assert first.identity == second.identity
    assert first.plan_identity_digest == second.plan_identity_digest
    assert (
        first.identity["source_snapshot_digest"]
        == second.identity["source_snapshot_digest"]
    )
    assert first.identity["dataset_id"] == second.identity["dataset_id"]
    assert "excluded_symbol_count" not in first.identity["counts"]
    assert "compatible_job_ids" not in first.identity
    assert "excluded_symbols" not in first.identity["selection"]
    assert first.selection_audit != second.selection_audit
    assert first.selection_audit_digest != second.selection_audit_digest
    assert len(first.selection_audit["excluded_symbols"][0]["observed_partitions"]) == 1
    assert len(second.selection_audit["excluded_symbols"][0]["observed_partitions"]) == 2


def test_reference_mapping_collapses_industry_rows_and_rejects_ambiguity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    snapshot = tmp_path / "snapshot.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(source, snapshot)
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [
            _stock_info_row("2330", "台積電", industry="半導體業"),
            _stock_info_row("2330", "台積電", industry="電子工業"),
        ],
    )

    plan = FinMindSemanticSnapshotReader(snapshot).plan(
        stock_info_raw=stock_info,
        actor="test-researcher",
        planned_at=PLANNED_AT,
        source_path=source,
        plan_output_parent=tmp_path,
    )
    assert plan.identity["reference"]["mapping"] == [
        {
            "market": "TWSE",
            "name": "台積電",
            "selected_date": "2026-08-20",
            "symbol": "2330",
        }
    ]

    ambiguous = _write_stock_info(
        tmp_path / "ambiguous.json.gz",
        [
            _stock_info_row("2330", "台積電"),
            _stock_info_row("2330", "不同名稱"),
        ],
    )
    with pytest.raises(FinMindSnapshotError, match="ambiguous.*2330"):
        FinMindSemanticSnapshotReader(snapshot).plan(
            stock_info_raw=ambiguous,
            actor="test-researcher",
            planned_at=PLANNED_AT,
            source_path=source,
            plan_output_parent=tmp_path,
        )


def test_semantic_identity_ignores_audit_timestamps_and_sqlite_bytes(
    tmp_path: Path,
) -> None:
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    plans = []
    for index in (1, 2):
        source = tmp_path / f"history-{index}.sqlite3"
        store = FinMindHistoryStore(source)
        try:
            job_id = _create_job(store, ("2330",))
            for session_date in (SESSION_1, SESSION_2):
                _save_partition(store, job_id, "2330", session_date)
        finally:
            store.close()
        if index == 2:
            connection = sqlite3.connect(source)
            try:
                connection.execute(
                    "UPDATE finmind_history_jobs SET created_at = ?, updated_at = ?",
                    ("2040-01-01T00:00:00+08:00", "2040-01-02T00:00:00+08:00"),
                )
                connection.execute(
                    "UPDATE finmind_history_partitions SET created_at = ?, updated_at = ?",
                    ("2040-01-01T00:00:00+08:00", "2040-01-02T00:00:00+08:00"),
                )
                connection.execute("PRAGMA user_version = 17")
                connection.commit()
            finally:
                connection.close()
        plans.append(
            _plan(source, tmp_path / f"snapshot-{index}.sqlite3", stock_info)
        )

    assert plans[0].identity == plans[1].identity
    assert plans[0].plan_identity_digest == plans[1].plan_identity_digest
    assert plans[0].identity["dataset_id"] == (
        "dataset-finmind-sponsor-sha256-"
        + plans[0].identity["source_snapshot_digest"]
    )
    assert len(plans[0].identity["source_snapshot_digest"]) == 64
    assert (
        plans[0].handoff_evidence["copied_sqlite_sha256"]
        != plans[1].handoff_evidence["copied_sqlite_sha256"]
    )
    assert plans[0].handoff_evidence_digest != plans[1].handoff_evidence_digest


def test_saved_plan_verifies_digests_and_exact_handoff_bytes(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "snapshot.sqlite3"
    plan = _plan(source, snapshot, stock_info)
    plan_path = tmp_path / "snapshot-plan.json"
    save_snapshot_plan(plan, plan_path)

    loaded = load_snapshot_plan(plan_path)
    verify_snapshot_plan_handoff(
        loaded,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )

    snapshot.write_bytes(snapshot.read_bytes() + b"changed")
    with pytest.raises(FinMindSnapshotError, match="handoff SHA-256 mismatch"):
        verify_snapshot_plan_handoff(
            loaded,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )


def test_raw_partition_digest_drift_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            """
            UPDATE finmind_history_partitions
            SET raw_sha256 = ?
            WHERE symbol = '2330' AND session_date = ?
            """,
            ("0" * 64, SESSION_1.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "snapshot.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(source, snapshot)

    with pytest.raises(FinMindSnapshotError, match="raw partition digest mismatch"):
        FinMindSemanticSnapshotReader(snapshot).plan(
            stock_info_raw=stock_info,
            actor="test-researcher",
            planned_at=PLANNED_AT,
            source_path=source,
            plan_output_parent=tmp_path,
        )


def test_plan_cli_creates_copy_and_plan_without_materializing_dataset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "plan" / "source.sqlite3"
    plan_path = tmp_path / "plan" / "snapshot-plan.json"

    plan_cli_main(
        [
            "--plan",
            "--source",
            str(source),
            "--stock-info-raw",
            str(stock_info),
            "--snapshot-out",
            str(snapshot),
            "--plan-out",
            str(plan_path),
            "--actor",
            "test-researcher",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    saved = load_snapshot_plan(plan_path)
    assert snapshot.is_file()
    assert output["dataset_id"] == saved.identity["dataset_id"]
    assert output["included_symbol_count"] == 1
    assert not (tmp_path / "datasets").exists()


def test_failed_plan_removes_its_new_snapshot_and_publishes_no_plan(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    ambiguous = _write_stock_info(
        tmp_path / "ambiguous.json.gz",
        [
            _stock_info_row("2330", "台積電"),
            _stock_info_row("2330", "不同名稱"),
        ],
    )
    snapshot = tmp_path / "plan" / "source.sqlite3"
    plan_path = tmp_path / "plan" / "snapshot-plan.json"

    with pytest.raises(FinMindSnapshotError, match="ambiguous.*2330"):
        create_snapshot_plan(
            source=source,
            stock_info_raw=ambiguous,
            snapshot_out=snapshot,
            plan_out=plan_path,
            actor="test-researcher",
            planned_at=PLANNED_AT,
        )

    assert not snapshot.exists()
    assert not plan_path.exists()


@pytest.mark.parametrize("interrupt_type", (KeyboardInterrupt, SystemExit))
def test_interrupted_plan_removes_its_new_snapshot_and_publishes_no_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_type: type[BaseException],
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    store.close()
    stock_info = _write_stock_info(tmp_path / "stock-info.json.gz", [])
    snapshot = tmp_path / "plan" / "source.sqlite3"
    plan_path = tmp_path / "plan" / "snapshot-plan.json"

    def interrupt_plan(*args: object, **kwargs: object) -> None:
        raise interrupt_type

    monkeypatch.setattr(FinMindSemanticSnapshotReader, "plan", interrupt_plan)

    with pytest.raises(interrupt_type):
        create_snapshot_plan(
            source=source,
            stock_info_raw=stock_info,
            snapshot_out=snapshot,
            plan_out=plan_path,
            actor="test-researcher",
            planned_at=PLANNED_AT,
        )

    assert not snapshot.exists()
    assert not plan_path.exists()


def test_interrupted_backup_removes_only_its_published_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    store.close()
    snapshot = tmp_path / "snapshot.sqlite3"
    real_link = os.link

    def interrupt_after_link(source_path: Path, destination_path: Path) -> None:
        real_link(source_path, destination_path)
        raise KeyboardInterrupt

    monkeypatch.setattr("backtest.finmind_snapshot.os.link", interrupt_after_link)

    with pytest.raises(KeyboardInterrupt):
        FinMindSemanticSnapshotReader.backup_source(source, snapshot)

    assert not snapshot.exists()


def test_interrupt_at_backup_return_boundary_removes_owned_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    store.close()
    stock_info = _write_stock_info(tmp_path / "stock-info.json.gz", [])
    snapshot = tmp_path / "plan" / "source.sqlite3"
    plan_path = tmp_path / "plan" / "snapshot-plan.json"
    real_backup = FinMindSemanticSnapshotReader.backup_source

    def backup_then_interrupt(
        source_path: Path,
        snapshot_path: Path,
        *,
        on_published: Callable[[Path], None] | None = None,
    ) -> None:
        real_backup(
            source_path,
            snapshot_path,
            on_published=on_published,
        )
        raise KeyboardInterrupt

    monkeypatch.setattr(
        FinMindSemanticSnapshotReader,
        "backup_source",
        backup_then_interrupt,
    )

    with pytest.raises(KeyboardInterrupt):
        create_snapshot_plan(
            source=source,
            stock_info_raw=stock_info,
            snapshot_out=snapshot,
            plan_out=plan_path,
            actor="test-researcher",
            planned_at=PLANNED_AT,
        )

    assert not snapshot.exists()
    assert not plan_path.exists()


def test_interrupt_after_plan_publication_preserves_complete_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date)
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "plan" / "source.sqlite3"
    plan_path = tmp_path / "plan" / "snapshot-plan.json"
    real_save = save_snapshot_plan

    def save_then_interrupt(plan: FinMindSnapshotPlan, path: Path) -> None:
        real_save(plan, path)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "scripts.materialize_finmind_backtest_dataset.save_snapshot_plan",
        save_then_interrupt,
    )

    with pytest.raises(KeyboardInterrupt):
        create_snapshot_plan(
            source=source,
            stock_info_raw=stock_info,
            snapshot_out=snapshot,
            plan_out=plan_path,
            actor="test-researcher",
            planned_at=PLANNED_AT,
        )

    assert snapshot.is_file()
    assert plan_path.is_file()
    verify_snapshot_plan_handoff(
        load_snapshot_plan(plan_path),
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )


def test_plan_fails_when_no_complete_symbol_has_a_ready_bar(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2330",))
        for session_date in (SESSION_1, SESSION_2):
            _save_partition(store, job_id, "2330", session_date, status="EMPTY")
    finally:
        store.close()
    stock_info = _write_stock_info(
        tmp_path / "stock-info.json.gz",
        [_stock_info_row("2330", "台積電")],
    )
    snapshot = tmp_path / "snapshot.sqlite3"
    FinMindSemanticSnapshotReader.backup_source(source, snapshot)

    with pytest.raises(FinMindSnapshotError, match="EMPTY_DATASET"):
        FinMindSemanticSnapshotReader(snapshot).plan(
            stock_info_raw=stock_info,
            actor="test-researcher",
            planned_at=PLANNED_AT,
            source_path=source,
            plan_output_parent=tmp_path,
        )


def test_existing_snapshot_or_plan_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "history.sqlite3"
    store = FinMindHistoryStore(source)
    store.close()
    snapshot = tmp_path / "snapshot.sqlite3"
    snapshot.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        FinMindSemanticSnapshotReader.backup_source(source, snapshot)

    plan_path = tmp_path / "snapshot-plan.json"
    plan_path.write_text("keep\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        save_snapshot_plan(
            object(),  # type: ignore[arg-type]
            plan_path,
        )


def _create_materialization_plan(
    root: Path,
) -> tuple[Path, Path, Path, FinMindSnapshotPlan]:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "history.sqlite3"
    store = FinMindHistoryStore(source)
    try:
        job_id = _create_job(store, ("2317", "2330"))
        for symbol in ("2317", "2330"):
            for session_date in (SESSION_1, SESSION_2):
                _save_partition_rows(store, job_id, symbol, session_date)
    finally:
        store.close()
    stock_info = _write_stock_info(
        root / "stock-info.json.gz",
        [_stock_info_row("2317", "鴻海"), _stock_info_row("2330", "台積電")],
    )
    snapshot = root / "plan" / "source.sqlite3"
    plan_path = root / "plan" / "snapshot-plan.json"
    plan = create_snapshot_plan(
        source=source,
        stock_info_raw=stock_info,
        snapshot_out=snapshot,
        plan_out=plan_path,
        actor="test-researcher",
        planned_at=PLANNED_AT,
    )
    return snapshot, stock_info, plan_path, plan


def test_execute_materializes_timestamp_major_dataset_and_replays_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, stock_info, plan_path, plan = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"

    manifest = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    dataset_dir = dataset_root / manifest.dataset_id
    manifest_bytes = (dataset_dir / "manifest.json").read_bytes()
    payload_bytes = (dataset_dir / "bars.jsonl").read_bytes()
    rows = [json.loads(line) for line in payload_bytes.splitlines()]
    keys = [(row["timestamp"], row["symbol"]) for row in rows]

    assert keys == sorted(keys)
    assert len(keys) == plan.identity["counts"]["bar_count"] == 8
    assert manifest.payload_order == "TIMESTAMP_SYMBOL"
    assert manifest.created_at == datetime.fromisoformat(
        plan.identity["snapshot_identity_at"]
    )
    assert manifest.source_snapshot_digest == plan.identity["source_snapshot_digest"]
    assert manifest.plan_identity == plan.identity
    assert manifest.plan_identity_digest == plan.plan_identity_digest
    assert manifest.volume_contract == {"unit": "COMMON_LOTS"}
    assert manifest.amount_contract == plan.identity["amount_contract"]
    assert manifest.profile == "KBAR_1M_V1"
    assert "KBAR_1M" in manifest.capabilities
    manifest_text = manifest_bytes.decode("utf-8")
    assert "copied_sqlite" not in manifest_text
    assert "handoff_evidence" not in manifest_text
    assert "selection_audit" not in manifest_text
    assert "locators" not in manifest_text

    replay = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    assert replay == manifest
    assert (dataset_dir / "manifest.json").read_bytes() == manifest_bytes
    assert (dataset_dir / "bars.jsonl").read_bytes() == payload_bytes

    def reject_external_sort(*args: object, **kwargs: object) -> None:
        raise AssertionError("timestamp-major FinMind payload must not external-sort")

    monkeypatch.setattr(
        HistoricalDatasetCatalog,
        "_iter_external_ordered",
        reject_external_sort,
    )
    replayed_bars = list(
        HistoricalDatasetCatalog(dataset_root).iter_bars_ordered(manifest.dataset_id)
    )
    assert len(replayed_bars) == manifest.bar_count


def test_execute_cli_uses_saved_plan_locators_without_postgres(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _snapshot, _stock_info, plan_path, plan = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"

    plan_cli_main(
        [
            "--execute",
            "--plan-file",
            str(plan_path),
            "--dataset-root",
            str(dataset_root),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["dataset_id"] == plan.identity["dataset_id"]
    assert output["manifest_digest"]
    assert (dataset_root / output["dataset_id"] / "bars.jsonl").is_file()


def test_execute_is_deterministic_across_clean_dataset_roots(tmp_path: Path) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    first_root = tmp_path / "datasets-a"
    second_root = tmp_path / "datasets-b"

    first = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=first_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    second = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=second_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )

    assert first.dataset_id == second.dataset_id
    assert first.manifest_digest == second.manifest_digest
    assert (first_root / first.dataset_id / "bars.jsonl").read_bytes() == (
        second_root / second.dataset_id / "bars.jsonl"
    ).read_bytes()


def test_semantic_rebuilds_with_different_sqlite_bytes_have_same_dataset(
    tmp_path: Path,
) -> None:
    materialized: list[tuple[DatasetManifest, bytes, bytes]] = []
    for index in (1, 2):
        root = tmp_path / f"rebuild-{index}"
        root.mkdir()
        source = root / "history.sqlite3"
        store = FinMindHistoryStore(source)
        try:
            job_id = _create_job(store, ("2317", "2330"))
            for symbol in ("2317", "2330"):
                for session_date in (SESSION_1, SESSION_2):
                    _save_partition_rows(store, job_id, symbol, session_date)
        finally:
            store.close()
        if index == 2:
            connection = sqlite3.connect(source)
            try:
                connection.execute(
                    "UPDATE finmind_history_jobs SET created_at = ?, updated_at = ?",
                    ("2040-01-01T00:00:00+08:00", "2040-01-02T00:00:00+08:00"),
                )
                connection.execute(
                    "UPDATE finmind_history_partitions SET created_at = ?, updated_at = ?",
                    ("2040-01-01T00:00:00+08:00", "2040-01-02T00:00:00+08:00"),
                )
                connection.execute("PRAGMA user_version = 29")
                connection.commit()
            finally:
                connection.close()
        stock_info = _write_stock_info(
            root / "stock-info.json.gz",
            [_stock_info_row("2317", "鴻海"), _stock_info_row("2330", "台積電")],
        )
        snapshot = root / "plan" / "source.sqlite3"
        plan_path = root / "plan" / "snapshot-plan.json"
        plan = create_snapshot_plan(
            source=source,
            stock_info_raw=stock_info,
            snapshot_out=snapshot,
            plan_out=plan_path,
            actor="test-researcher",
            planned_at=PLANNED_AT,
        )
        manifest = execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=root / "datasets",
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )
        dataset_dir = root / "datasets" / manifest.dataset_id
        materialized.append(
            (
                manifest,
                (dataset_dir / "manifest.json").read_bytes(),
                (dataset_dir / "bars.jsonl").read_bytes(),
            )
        )
        assert plan.handoff_evidence["copied_sqlite_sha256"]

    first, second = materialized
    assert first[0].dataset_id == second[0].dataset_id
    assert first[0].manifest_digest == second[0].manifest_digest
    assert first[1:] == second[1:]


def test_existing_finmind_dataset_identity_conflict_fails_closed(tmp_path: Path) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    manifest = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    manifest_path = dataset_root / manifest.dataset_id / "manifest.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["source_snapshot_digest"] = "0" * 64
    tampered_manifest = DatasetManifest.from_dict(tampered)
    tampered["manifest_digest"] = tampered_manifest.manifest_digest
    manifest_path.write_text(canonical_json(tampered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="immutable identity conflict"):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )


def test_existing_finmind_dataset_payload_tamper_fails_closed(tmp_path: Path) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    manifest = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    payload_path = dataset_root / manifest.dataset_id / "bars.jsonl"
    rows = [json.loads(line) for line in payload_path.read_bytes().splitlines()]
    rows[0]["close"] = "100"
    rows[0]["amount"] = "700"
    tampered_payload = "".join(canonical_json(row) + "\n" for row in rows).encode()
    payload_path.write_bytes(tampered_payload)
    manifest_path = dataset_root / manifest.dataset_id / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["bars_sha256"] = hashlib.sha256(tampered_payload).hexdigest()
    raw_manifest["manifest_digest"] = DatasetManifest.from_dict(
        raw_manifest
    ).manifest_digest
    manifest_path.write_text(canonical_json(raw_manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="payload/source conflict"):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )


def test_existing_finmind_dataset_rejects_noncanonical_blank_payload_line(
    tmp_path: Path,
) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    manifest = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    dataset_dir = dataset_root / manifest.dataset_id
    payload_path = dataset_dir / "bars.jsonl"
    tampered_payload = b"\n" + payload_path.read_bytes()
    payload_path.write_bytes(tampered_payload)
    manifest_path = dataset_dir / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["bars_sha256"] = hashlib.sha256(tampered_payload).hexdigest()
    raw_manifest["manifest_digest"] = DatasetManifest.from_dict(
        raw_manifest
    ).manifest_digest
    manifest_path.write_text(canonical_json(raw_manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="canonical JSONL"):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )


def test_existing_finmind_dataset_rejects_unknown_manifest_fields(
    tmp_path: Path,
) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    manifest = execute_snapshot_plan(
        plan_file=plan_path,
        dataset_root=dataset_root,
        snapshot_file=snapshot,
        stock_info_raw=stock_info,
    )
    manifest_path = dataset_root / manifest.dataset_id / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["locators"] = {"copied_sqlite_path": "/forbidden/path"}
    manifest_path.write_text(canonical_json(raw_manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest schema or canonical bytes"):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )


def test_concurrent_first_writers_converge_to_one_dataset(tmp_path: Path) -> None:
    snapshot, stock_info, plan_path, _plan_value = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"

    def execute() -> DatasetManifest:
        return execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        manifests = tuple(pool.map(lambda _index: execute(), range(2)))

    assert manifests[0] == manifests[1]
    assert [path.name for path in dataset_root.iterdir()] == [
        manifests[0].dataset_id
    ]


def test_disk_preflight_rejects_before_dataset_temp_is_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, stock_info, plan_path, plan = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    monkeypatch.setattr(
        "backtest.dataset.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )

    with pytest.raises(ValueError, match="disk space is insufficient"):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )

    assert not (dataset_root / plan.identity["dataset_id"]).exists()
    assert list(dataset_root.glob(".*.tmp")) == []


def test_interrupted_materialization_removes_only_its_temp_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, stock_info, plan_path, plan = _create_materialization_plan(
        tmp_path / "source"
    )
    dataset_root = tmp_path / "datasets"
    real_iter = FinMindSemanticSnapshotReader._iter_symbol_bars

    def interrupting_iter(*args: object, **kwargs: object):
        for bar in real_iter(*args, **kwargs):
            yield bar
            raise KeyboardInterrupt

    monkeypatch.setattr(
        FinMindSemanticSnapshotReader,
        "_iter_symbol_bars",
        staticmethod(interrupting_iter),
    )

    with pytest.raises(KeyboardInterrupt):
        execute_snapshot_plan(
            plan_file=plan_path,
            dataset_root=dataset_root,
            snapshot_file=snapshot,
            stock_info_raw=stock_info,
        )

    assert not (dataset_root / plan.identity["dataset_id"]).exists()
    assert list(dataset_root.glob(".*.tmp")) == []
