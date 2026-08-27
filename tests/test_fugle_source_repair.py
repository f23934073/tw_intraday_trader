from __future__ import annotations

from datetime import date

import pytest

from backtest.fugle_source_repair import (
    FUGLE_LABEL_CONVERSION,
    FugleSourceRepairCandidateError,
    build_fugle_repair_candidate,
)


SESSION = date(2026, 3, 20)
REFERENCE = {
    "amount_twd": 22900,
    "close": "22.90",
    "high": "22.90",
    "low": "22.90",
    "open": "22.90",
    "transactions": 1,
    "volume_shares": 1000,
}


def _payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "symbol": "9960",
        "exchange": "TPEx",
        "market": "OTC",
        "timeframe": "1",
        "data": list(rows),
    }


def _row(timestamp: str = "2026-03-20T09:00:00+08:00") -> dict[str, object]:
    return {
        "date": timestamp,
        "open": 22.9,
        "high": 22.9,
        "low": 22.9,
        "close": 22.9,
        "volume": 1,
        "average": 22.9,
        "turnover": 22900,
    }


def test_builds_exact_daily_reconciled_observable_minute_candidate() -> None:
    result = build_fugle_repair_candidate(
        _payload(_row()),
        symbol="9960",
        session_date=SESSION,
        official_reference=REFERENCE,
    )

    assert len(result.bars) == 1
    assert result.bars[0].timestamp.isoformat() == "2026-03-20T09:01:00+08:00"
    assert result.bars[0].amount == result.bars[0].close * result.bars[0].volume
    assert result.validation["fugle_label_conversion"] == FUGLE_LABEL_CONVERSION
    assert result.validation["safe_to_propose"] is True
    assert set(result.validation["checks"].values()) == {True}


def test_accepts_missing_turnover_only_for_one_flat_official_transaction() -> None:
    row = _row()
    row.pop("turnover")
    result = build_fugle_repair_candidate(
        _payload(row),
        symbol="9960",
        session_date=SESSION,
        official_reference=REFERENCE,
    )

    assert result.validation["amount_reconciliation_kind"] == (
        "OFFICIAL_SINGLE_TRANSACTION_FLAT_BAR_DERIVATION"
    )
    assert result.validation["source_turnover_twd"] is None
    assert result.validation["reconciled_amount_twd"] == "22900.0"


def test_rejects_missing_turnover_for_multiple_official_transactions() -> None:
    row = _row()
    row.pop("turnover")
    reference = dict(REFERENCE, transactions=2)
    with pytest.raises(FugleSourceRepairCandidateError, match="turnover is absent"):
        build_fugle_repair_candidate(
            _payload(row),
            symbol="9960",
            session_date=SESSION,
            official_reference=reference,
        )


def test_closing_auction_label_stays_at_1330() -> None:
    result = build_fugle_repair_candidate(
        _payload(_row("2026-03-20T13:30:00+08:00")),
        symbol="9960",
        session_date=SESSION,
        official_reference=REFERENCE,
    )

    assert result.bars[0].timestamp.isoformat() == "2026-03-20T13:30:00+08:00"


def test_rejects_daily_volume_mismatch() -> None:
    row = _row()
    row["volume"] = 2
    with pytest.raises(FugleSourceRepairCandidateError, match="volume_exact_match"):
        build_fugle_repair_candidate(
            _payload(row),
            symbol="9960",
            session_date=SESSION,
            official_reference=REFERENCE,
        )


def test_rejects_daily_turnover_mismatch() -> None:
    row = _row()
    row["turnover"] = 22899
    with pytest.raises(FugleSourceRepairCandidateError, match="amount_exact_match"):
        build_fugle_repair_candidate(
            _payload(row),
            symbol="9960",
            session_date=SESSION,
            official_reference=REFERENCE,
        )


def test_rejects_empty_or_timezone_naive_payload() -> None:
    with pytest.raises(FugleSourceRepairCandidateError, match="no minute rows"):
        build_fugle_repair_candidate(
            _payload(),
            symbol="9960",
            session_date=SESSION,
            official_reference=REFERENCE,
        )

    with pytest.raises(FugleSourceRepairCandidateError, match="lacks timezone"):
        build_fugle_repair_candidate(
            _payload(_row("2026-03-20T09:00:00")),
            symbol="9960",
            session_date=SESSION,
            official_reference=REFERENCE,
        )
