from __future__ import annotations

import json

import pytest

from backtest.postgres_repository import PostgresBacktestRepository
from backtest.sqlite_repository import SQLiteBacktestRepository


def _run_record(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "idempotency_key": f"create-{run_id}",
        "status": "RUNNING",
        "config": {"contract": "chunked-result-test"},
        "config_digest": f"config-{run_id}",
        "dataset_id": "dataset-result-chunks",
        "dataset_digest": "dataset-result-chunks-digest",
        "created_at": "2026-08-23T09:00:00+08:00",
    }


def _result() -> dict[str, object]:
    decisions = [
        {
            "decision_id": f"decision-{index:04d}",
            "symbol": "2330",
            "event_at": f"2026-08-23T09:{index % 60:02d}:00+08:00",
            "side": "BUY",
            "sequence": index,
        }
        for index in range(205)
    ]
    trades = [
        {
            "trade_id": f"trade-{index}",
            "symbol": "2330",
            "entry": {"filled_at": "2026-08-23T09:10:00+08:00"},
            "exit": {"filled_at": "2026-08-23T09:20:00+08:00"},
            "net_pnl": float(index),
        }
        for index in range(2)
    ]
    return {
        "decisions": decisions,
        "fills": [{"fill_id": f"fill-{index}"} for index in range(103)],
        "trades": trades,
        "orders": [{"order_id": f"order-{index}"} for index in range(201)],
        "daily_equity": [
            {"date": "2026-08-22", "equity": 1_000_000.0},
            {"date": "2026-08-23", "equity": 1_001_000.0},
        ],
        "strategy_counts": {"entry": {"triggered": 205}},
        "unresolved_positions": [{"symbol": "2317", "quantity": 1000}],
        "summary": {"result_digest": "result-digest", "verdict": "TEST"},
    }


def test_sqlite_result_is_chunked_and_rebuilt_without_large_root_json(tmp_path) -> None:
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    expected = _result()
    try:
        repository.create_run(_run_record("chunked-sqlite"))
        repository.save_result("chunked-sqlite", expected)

        raw = repository._connection.execute(
            "SELECT result_json FROM backtest_results WHERE run_id = ?",
            ("chunked-sqlite",),
        ).fetchone()[0]
        root = json.loads(raw)
        assert "decisions" not in root
        assert root["_storage"]["format"] == "CHUNKED_JSON_V1"
        assert root["_storage"]["fields"]["decisions"]["chunk_count"] == 3
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM backtest_result_chunks WHERE run_id = ?",
            ("chunked-sqlite",),
        ).fetchone()[0] == 11
        assert repository.get_result("chunked-sqlite") == expected
    finally:
        repository.close()


def test_chunk_payload_tamper_fails_closed(tmp_path) -> None:
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    try:
        repository.create_run(_run_record("chunk-tamper"))
        repository.save_result("chunk-tamper", _result())
        repository._connection.execute(
            """
            UPDATE backtest_result_chunks
            SET payload_json = '[{"tampered":true}]'
            WHERE run_id = ? AND field_name = 'decisions' AND chunk_sequence = 0
            """,
            ("chunk-tamper",),
        )
        repository._connection.commit()

        with pytest.raises(ValueError, match="integrity"):
            repository.get_result("chunk-tamper")
    finally:
        repository.close()


def test_postgres_result_chunks_round_trip(postgres_test_connection) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    expected = _result()
    repository.create_run(_run_record("chunked-postgres"))
    repository.save_result("chunked-postgres", expected)

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT result_json, (
                SELECT COUNT(*)
                FROM backtest.backtest_result_chunks
                WHERE run_id = 'chunked-postgres'
            )
            FROM backtest.backtest_results
            WHERE run_id = 'chunked-postgres'
            """
        )
        root, chunk_count = cursor.fetchone()
    assert "decisions" not in root
    assert root["_storage"]["format"] == "CHUNKED_JSON_V1"
    assert chunk_count == 11
    assert repository.get_result("chunked-postgres") == expected
