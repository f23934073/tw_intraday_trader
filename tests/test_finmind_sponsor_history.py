"""Contracts for paced, symbol-day checkpointed FinMind Sponsor history."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest.finmind_history import (
    FinMindHistoryStore,
    FinMindResponse,
    FinMindSponsorDownloader,
    FinMindUsage,
    normalize_kbar_response,
    select_industry_market_value_leaders,
)


def _response(data: list[dict[str, object]]) -> FinMindResponse:
    body = json.dumps({"status": 200, "msg": "success", "data": data}).encode()
    return FinMindResponse(
        http_status=200,
        body=body,
        payload=json.loads(body),
    )


def _daily_rows(*values: str) -> list[dict[str, object]]:
    return [{"date": value, "stock_id": "2330"} for value in values]


def _kbar(symbol: str, session_date: date, minute: str = "09:00:00") -> dict[str, object]:
    return {
        "date": session_date.isoformat(),
        "minute": minute,
        "stock_id": symbol,
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 7,
    }


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, date, date | None]] = []

    def usage(self) -> FinMindUsage:
        return FinMindUsage(user_count=100, api_request_limit=6000)

    def data(
        self,
        *,
        dataset: str,
        data_id: str,
        start_date: date,
        end_date: date | None = None,
    ) -> FinMindResponse:
        self.calls.append((dataset, data_id, start_date, end_date))
        if dataset == "TaiwanStockPrice":
            return _response(_daily_rows("2026-08-17", "2026-08-18"))
        return _response([_kbar(data_id, start_date)])


def _job(store: FinMindHistoryStore) -> str:
    return store.ensure_job(
        symbols=("2330", "2317"),
        start_date=date(2026, 8, 17),
        end_date=date(2026, 8, 18),
        calendar_symbol="2330",
    )


def test_normalization_uses_observable_end_labels_and_preserves_close() -> None:
    session = date(2026, 8, 18)
    bars = normalize_kbar_response(
        _response([
            _kbar("2330", session, "09:00:00"),
            _kbar("2330", session, "13:30:00"),
        ]),
        symbol="2330",
        session_date=session,
    )

    assert [bar.timestamp.isoformat() for bar in bars] == [
        "2026-08-18T09:01:00+08:00",
        "2026-08-18T13:30:00+08:00",
    ]
    assert [bar.volume for bar in bars] == [7, 7]


def test_delayed_closing_auction_uses_1333_as_observable_close() -> None:
    session = date(2025, 3, 24)
    bars = normalize_kbar_response(
        _response([_kbar("2330", session, "13:33:00")]),
        symbol="2330",
        session_date=session,
    )

    assert bars[0].timestamp.isoformat() == "2025-03-24T13:33:00+08:00"


def test_stored_invalid_response_can_be_revalidated_without_api_call(
    tmp_path: Path,
) -> None:
    store = FinMindHistoryStore(tmp_path / "history.sqlite3")
    try:
        job_id = store.ensure_job(
            symbols=("2330",),
            start_date=date(2025, 3, 24),
            end_date=date(2025, 3, 24),
            calendar_symbol="2330",
        )
        response = _response([_kbar("2330", date(2025, 3, 24), "13:33:00")])
        store.save_partition(
            job_id,
            symbol="2330",
            session_date=date(2025, 3, 24),
            response=response,
            bars=(),
            status="INVALID",
            error_message="old contract",
        )

        result = store.revalidate_invalid(job_id)

        assert result["repaired_partitions"] == 1
        assert store.load_partition_bars(
            job_id, "2330", date(2025, 3, 24)
        )[0].timestamp.isoformat() == "2025-03-24T13:33:00+08:00"
    finally:
        store.close()


def test_each_symbol_day_is_checkpointed_and_resume_spends_no_duplicate_request(
    tmp_path: Path,
) -> None:
    store = FinMindHistoryStore(tmp_path / "history.sqlite3")
    client = _FakeClient()
    downloader = FinMindSponsorDownloader(
        client=client,
        store=store,
        sleeper=lambda _seconds: None,
    )
    try:
        job_id = _job(store)
        first = downloader.run(
            job_id,
            max_requests=3,
            reserve_requests=500,
            pace_seconds=0,
        )
        assert first["batch_requests_spent"] == 3
        assert first["checkpointed_symbol_days"] == 2
        calls_after_first = list(client.calls)

        second = downloader.run(
            job_id,
            max_requests=2,
            reserve_requests=500,
            pace_seconds=0,
        )

        assert second["batch_requests_spent"] == 2
        assert second["checkpointed_symbol_days"] == 4
        assert second["status"] == "COMPLETED"
        assert client.calls[: len(calls_after_first)] == calls_after_first
        assert len(set(client.calls)) == len(client.calls)
        assert store.load_partition_bars(
            job_id, "2317", date(2026, 8, 17)
        )[0].timestamp.isoformat() == "2026-08-17T09:01:00+08:00"
        assert store.audit(job_id) == {
            "job_id": job_id,
            "checkpointed_partitions": 4,
            "verified_partitions": 4,
            "total_bars": 4,
            "first_event_at": "2026-08-17T09:01:00+08:00",
            "last_event_at": "2026-08-18T09:01:00+08:00",
            "issue_count": 0,
            "issues": [],
        }
    finally:
        store.close()


def test_reserve_margin_can_prevent_all_data_requests(tmp_path: Path) -> None:
    store = FinMindHistoryStore(tmp_path / "history.sqlite3")
    client = _FakeClient()
    client.usage = lambda: FinMindUsage(user_count=5900, api_request_limit=6000)  # type: ignore[method-assign]
    downloader = FinMindSponsorDownloader(client=client, store=store)
    try:
        job_id = _job(store)
        result = downloader.run(
            job_id,
            max_requests=100,
            reserve_requests=100,
            pace_seconds=0,
        )
        assert result["batch_requests_spent"] == 0
        assert result["status"] == "PAUSED"
        assert client.calls == []
    finally:
        store.close()


def test_job_without_calendar_is_not_reconciled_as_complete(tmp_path: Path) -> None:
    store = FinMindHistoryStore(tmp_path / "history.sqlite3")
    try:
        job_id = store.ensure_job(
            symbols=("1101",),
            start_date=date(2026, 8, 17),
            end_date=date(2026, 8, 18),
            calendar_symbol="2330",
        )

        result = store.reconcile_completion(job_id)

        assert result["status"] == "QUEUED"
        assert result["trading_date_count"] == 0
        assert result["checkpointed_symbol_days"] == 0
    finally:
        store.close()


def test_invalid_duplicate_minute_is_rejected() -> None:
    session = date(2026, 8, 18)
    row = _kbar("2330", session)
    try:
        normalize_kbar_response(
            _response([row, row]), symbol="2330", session_date=session
        )
    except ValueError as error:
        assert "duplicate minute" in str(error)
    else:
        raise AssertionError("duplicate FinMind minutes must fail")


def test_industry_leaders_use_latest_listing_and_latest_market_value_date() -> None:
    stock_info = _response(
        [
            {
                "date": "2020-01-01",
                "stock_id": "1111",
                "stock_name": "舊市場",
                "industry_category": "食品工業",
                "type": "emerging",
            },
            {
                "date": "2026-08-20",
                "stock_id": "1111",
                "stock_name": "甲公司",
                "industry_category": "食品工業",
                "type": "twse",
            },
            {
                "date": "2026-08-20",
                "stock_id": "2222",
                "stock_name": "乙公司",
                "industry_category": "食品工業",
                "type": "tpex",
            },
            {
                "date": "2026-08-20",
                "stock_id": "3333",
                "stock_name": "丙公司",
                "industry_category": "航運業",
                "type": "twse",
            },
            {
                "date": "2026-08-20",
                "stock_id": "3333",
                "stock_name": "丙公司",
                "industry_category": "電子工業",
                "type": "twse",
            },
            {
                "date": "2026-08-20",
                "stock_id": "0050",
                "stock_name": "ETF",
                "industry_category": "ETF",
                "type": "twse",
            },
            {
                "date": "2026-08-20",
                "stock_id": "4444",
                "stock_name": "歧義公司",
                "industry_category": "航運業",
                "type": "twse",
            },
            {
                "date": "2026-08-20",
                "stock_id": "4444",
                "stock_name": "歧義公司",
                "industry_category": "航運業",
                "type": "tpex",
            },
            {
                "date": None,
                "stock_id": "5555",
                "stock_name": "缺日期公司",
                "industry_category": "食品工業",
                "type": "twse",
            },
        ]
    )
    market_value = _response(
        [
            {"date": "2026-08-19", "stock_id": "1111", "market_value": 999},
            {"date": "2026-08-20", "stock_id": "1111", "market_value": 100},
            {"date": "2026-08-20", "stock_id": "2222", "market_value": 200},
            {"date": "2026-08-20", "stock_id": "3333", "market_value": 150},
            {"date": "2026-08-20", "stock_id": "0050", "market_value": 500},
            {"date": "2026-08-20", "stock_id": "4444", "market_value": 999},
            {"date": "2026-08-20", "stock_id": "5555", "market_value": 999},
            {"date": "2026-08-20", "stock_id": "6666", "market_value": 0},
        ]
    )

    leaders = select_industry_market_value_leaders(
        stock_info_response=stock_info,
        market_value_response=market_value,
        already_complete_symbols=("3333",),
    )

    assert [leader.to_dict() for leader in leaders] == [
        {
            "industry": "航運業",
            "symbol": "3333",
            "name": "丙公司",
            "market": "twse",
            "market_value": 150,
            "market_value_date": "2026-08-20",
            "already_complete": True,
        },
        {
            "industry": "食品工業",
            "symbol": "2222",
            "name": "乙公司",
            "market": "tpex",
            "market_value": 200,
            "market_value_date": "2026-08-20",
            "already_complete": False,
        },
    ]
