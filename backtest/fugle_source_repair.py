"""Fail-closed normalization for Fugle minute source-repair candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from backtest.domain import HistoricalBar
from backtest.finmind_history import TAIPEI


FUGLE_SOURCE_NAME = "FUGLE_HISTORICAL_CANDLES"
FUGLE_ENDPOINT_TEMPLATE = (
    "https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}"
)
FUGLE_LABEL_CONVERSION = "START_PLUS_ONE_MINUTE_EXCEPT_13_30_V1"


class FugleSourceRepairCandidateError(ValueError):
    """The Fugle payload cannot safely repair the requested partition."""


@dataclass(frozen=True)
class FugleRepairCandidate:
    bars: tuple[HistoricalBar, ...]
    validation: Mapping[str, Any]


def build_fugle_repair_candidate(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    session_date: date,
    official_reference: Mapping[str, Any],
) -> FugleRepairCandidate:
    """Validate one raw Fugle session and convert start labels to end labels."""

    if str(payload.get("symbol")) != symbol:
        raise FugleSourceRepairCandidateError("Fugle payload symbol mismatch")
    if str(payload.get("timeframe")) != "1":
        raise FugleSourceRepairCandidateError("Fugle payload is not one-minute data")
    if str(payload.get("market")).upper() != "OTC":
        raise FugleSourceRepairCandidateError("Fugle payload is not OTC regular market")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise FugleSourceRepairCandidateError("Fugle payload has no minute rows")

    expected_open = _decimal(official_reference.get("open"), "official open")
    expected_high = _decimal(official_reference.get("high"), "official high")
    expected_low = _decimal(official_reference.get("low"), "official low")
    expected_close = _decimal(official_reference.get("close"), "official close")
    expected_volume_shares = _integer(
        official_reference.get("volume_shares"), "official volume_shares"
    )
    expected_amount = _decimal(
        official_reference.get("amount_twd"), "official amount_twd"
    )
    expected_transactions = _integer(
        official_reference.get("transactions"), "official transactions"
    )

    source_timestamps: list[datetime] = []
    bars: list[HistoricalBar] = []
    turnover_values: list[Decimal | None] = []
    total_volume_lots = 0
    latest_average: Decimal | None = None
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            raise FugleSourceRepairCandidateError(
                f"Fugle minute row {index} is not an object"
            )
        source_timestamp = _timestamp(item.get("date"), session_date)
        source_timestamps.append(source_timestamp)
        event_timestamp = _observable_minute_end(source_timestamp)
        open_price = _decimal(item.get("open"), f"row {index} open")
        high = _decimal(item.get("high"), f"row {index} high")
        low = _decimal(item.get("low"), f"row {index} low")
        close = _decimal(item.get("close"), f"row {index} close")
        volume = _integer(item.get("volume"), f"row {index} volume")
        if volume <= 0:
            raise FugleSourceRepairCandidateError(
                f"Fugle minute row {index} volume must be positive"
            )
        if item.get("turnover") is None:
            turnover_values.append(None)
        else:
            turnover = _decimal(item.get("turnover"), f"row {index} turnover")
            if turnover <= 0:
                raise FugleSourceRepairCandidateError(
                    f"Fugle minute row {index} turnover must be positive"
                )
            turnover_values.append(turnover)
        latest_average = _decimal(item.get("average"), f"row {index} average")
        total_volume_lots += volume
        bars.append(
            HistoricalBar(
                symbol=symbol,
                timestamp=event_timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                amount=close * volume,
                session_date=session_date,
            )
        )

    if source_timestamps != sorted(source_timestamps) or len(source_timestamps) != len(
        set(source_timestamps)
    ):
        raise FugleSourceRepairCandidateError(
            "Fugle source timestamps must be unique and strictly increasing"
        )
    event_timestamps = [bar.timestamp for bar in bars]
    if event_timestamps != sorted(event_timestamps) or len(event_timestamps) != len(
        set(event_timestamps)
    ):
        raise FugleSourceRepairCandidateError(
            "Fugle observable minute-end timestamps collide after label conversion"
        )

    observed_open = bars[0].open
    observed_high = max(bar.high for bar in bars)
    observed_low = min(bar.low for bar in bars)
    observed_close = bars[-1].close
    observed_volume_shares = total_volume_lots * 1000
    assert latest_average is not None
    official_vwap = expected_amount / Decimal(expected_volume_shares)
    average_tolerance = max(Decimal("0.01"), official_vwap * Decimal("0.0001"))
    source_turnover_twd: Decimal | None
    if all(value is not None for value in turnover_values):
        source_turnover_twd = sum(
            (value for value in turnover_values if value is not None), Decimal(0)
        )
        reconciled_amount = source_turnover_twd
        amount_reconciliation_kind = "SOURCE_REPORTED_TURNOVER"
    elif any(value is not None for value in turnover_values):
        raise FugleSourceRepairCandidateError(
            "Fugle turnover is present for only part of the session"
        )
    else:
        sole = bars[0]
        if not (
            expected_transactions == 1
            and len(bars) == 1
            and sole.open == sole.high == sole.low == sole.close
        ):
            raise FugleSourceRepairCandidateError(
                "Fugle turnover is absent without a single flat-price official transaction"
            )
        source_turnover_twd = None
        reconciled_amount = sole.close * Decimal(sole.volume * 1000)
        amount_reconciliation_kind = (
            "OFFICIAL_SINGLE_TRANSACTION_FLAT_BAR_DERIVATION"
        )
    checks = {
        "amount_exact_match": reconciled_amount == expected_amount,
        "close_exact_match": observed_close == expected_close,
        "high_exact_match": observed_high == expected_high,
        "latest_average_within_tolerance": (
            abs(latest_average - official_vwap) <= average_tolerance
        ),
        "low_exact_match": observed_low == expected_low,
        "open_exact_match": observed_open == expected_open,
        "volume_exact_match": observed_volume_shares == expected_volume_shares,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise FugleSourceRepairCandidateError(
            "Fugle session does not reconcile to official daily evidence: "
            + ", ".join(failed)
        )

    validation = {
        "bar_count": len(bars),
        "amount_reconciliation_kind": amount_reconciliation_kind,
        "checks": checks,
        "first_event_at": bars[0].timestamp.isoformat(),
        "fugle_label_conversion": FUGLE_LABEL_CONVERSION,
        "last_event_at": bars[-1].timestamp.isoformat(),
        "latest_average": str(latest_average),
        "official_vwap": str(official_vwap),
        "safe_to_propose": True,
        "reconciled_amount_twd": str(reconciled_amount),
        "source_turnover_twd": (
            str(source_turnover_twd) if source_turnover_twd is not None else None
        ),
        "source_total_volume_lots": total_volume_lots,
        "source_total_volume_shares": observed_volume_shares,
    }
    return FugleRepairCandidate(bars=tuple(bars), validation=validation)


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise FugleSourceRepairCandidateError(f"{label} is not numeric") from error
    if not result.is_finite():
        raise FugleSourceRepairCandidateError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise FugleSourceRepairCandidateError(f"{label} must be an integer")
    return int(number)


def _timestamp(value: object, session_date: date) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise FugleSourceRepairCandidateError(
            "Fugle timestamp is not ISO-8601"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FugleSourceRepairCandidateError("Fugle timestamp lacks timezone")
    local = parsed.astimezone(TAIPEI)
    local_time = local.timetz().replace(tzinfo=None)
    if local.date() != session_date or not time(9, 0) <= local_time <= time(13, 30):
        raise FugleSourceRepairCandidateError(
            "Fugle timestamp is outside the target regular session"
        )
    if local.second or local.microsecond:
        raise FugleSourceRepairCandidateError("Fugle timestamp is not minute-aligned")
    return local


def _observable_minute_end(source_timestamp: datetime) -> datetime:
    if source_timestamp.timetz().replace(tzinfo=None) == time(13, 30):
        return source_timestamp
    return source_timestamp + timedelta(minutes=1)
