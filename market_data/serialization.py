"""Strict canonical JSON codec for ``market-event-v1`` envelopes."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)


_ENVELOPE_FIELDS = frozenset(
    {
        "event_id",
        "schema_version",
        "session_id",
        "session_date",
        "source",
        "source_mode",
        "stream_kind",
        "symbol",
        "event_at",
        "received_at",
        "ingress_sequence",
        "source_identity",
        "payload",
        "raw_capture_id",
    }
)
_PAYLOAD_COMMON_FIELDS = frozenset(
    {
        "event_id",
        "source",
        "symbol",
        "session_date",
        "event_time",
        "received_at",
        "ingress_sequence",
        "suspended",
        "simulated_trade",
        "intraday_odd",
    }
)
_TICK_FIELDS = _PAYLOAD_COMMON_FIELDS | {
    "price",
    "tick_volume_lots",
    "total_volume_lots",
    "average_price",
    "intraday_high",
    "intraday_low",
    "raw_tick_type",
    "aggressor_side",
    "buy_aggressor_total_lots",
    "sell_aggressor_total_lots",
}
_BIDASK_FIELDS = _PAYLOAD_COMMON_FIELDS | {
    "bid_prices",
    "bid_volume_lots",
    "ask_prices",
    "ask_volume_lots",
}


def serialize_event_envelope(envelope: EventEnvelope) -> str:
    """Return stable JSON without relying on dataclass implementation details."""
    return json.dumps(
        _event_envelope_to_dict(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _event_envelope_to_dict(envelope: EventEnvelope) -> dict[str, object]:
    payload = envelope.payload
    common: dict[str, object] = {
        "event_id": payload.event_id,
        "source": payload.source.value,
        "symbol": payload.symbol,
        "session_date": payload.session_date.isoformat(),
        "event_time": payload.event_time.isoformat(),
        "received_at": payload.received_at.isoformat(),
        "ingress_sequence": payload.ingress_sequence,
        "suspended": payload.suspended,
        "simulated_trade": payload.simulated_trade,
        "intraday_odd": payload.intraday_odd,
    }
    if isinstance(payload, TickEvent):
        payload_dict = {
            **common,
            "price": str(payload.price),
            "tick_volume_lots": payload.tick_volume_lots,
            "total_volume_lots": payload.total_volume_lots,
            "average_price": (
                str(payload.average_price)
                if payload.average_price is not None
                else None
            ),
            "intraday_high": str(payload.intraday_high),
            "intraday_low": str(payload.intraday_low),
            "raw_tick_type": payload.raw_tick_type,
            "aggressor_side": payload.aggressor_side.value,
            "buy_aggressor_total_lots": payload.buy_aggressor_total_lots,
            "sell_aggressor_total_lots": payload.sell_aggressor_total_lots,
        }
    elif isinstance(payload, BidAskEvent):
        payload_dict = {
            **common,
            "bid_prices": [str(value) for value in payload.bid_prices],
            "bid_volume_lots": list(payload.bid_volume_lots),
            "ask_prices": [str(value) for value in payload.ask_prices],
            "ask_volume_lots": list(payload.ask_volume_lots),
        }
    else:  # pragma: no cover - EventEnvelope rejects unsupported payloads.
        raise TypeError("unsupported market event payload")
    return {
        "event_id": envelope.event_id,
        "schema_version": envelope.schema_version,
        "session_id": envelope.session_id,
        "session_date": envelope.session_date.isoformat(),
        "source": envelope.source.value,
        "source_mode": envelope.source_mode,
        "stream_kind": envelope.stream_kind.value,
        "symbol": envelope.symbol,
        "event_at": envelope.event_at.isoformat(),
        "received_at": envelope.received_at.isoformat(),
        "ingress_sequence": envelope.ingress_sequence,
        "source_identity": envelope.source_identity,
        "payload": payload_dict,
        "raw_capture_id": envelope.raw_capture_id,
    }


def deserialize_event_envelope(value: str) -> EventEnvelope:
    """Parse only the frozen v1 field set and reject inferred/defaulted data."""
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise ValueError("market event envelope must be a JSON object")
    _require_exact_fields(raw, _ENVELOPE_FIELDS, "envelope")
    schema_version = _string(raw, "schema_version")
    if schema_version != MARKET_EVENT_SCHEMA_VERSION:
        raise ValueError(f"unsupported market event schema: {schema_version}")

    stream_kind = MarketStreamKind(_string(raw, "stream_kind"))
    payload_raw = raw["payload"]
    if not isinstance(payload_raw, dict):
        raise ValueError("market event payload must be a JSON object")
    payload = _payload_from_dict(payload_raw, stream_kind)
    raw_capture_id = raw["raw_capture_id"]
    if raw_capture_id is not None and not isinstance(raw_capture_id, str):
        raise ValueError("raw_capture_id must be a string or null")
    return EventEnvelope(
        event_id=_string(raw, "event_id"),
        schema_version=schema_version,
        session_id=_string(raw, "session_id"),
        session_date=_date(raw, "session_date"),
        source=MarketEventSource(_string(raw, "source")),
        source_mode=_string(raw, "source_mode"),
        stream_kind=stream_kind,
        symbol=_string(raw, "symbol"),
        event_at=_datetime(raw, "event_at"),
        received_at=_datetime(raw, "received_at"),
        ingress_sequence=_integer(raw, "ingress_sequence"),
        source_identity=_string(raw, "source_identity"),
        payload=payload,
        raw_capture_id=raw_capture_id,
    )


def _payload_from_dict(
    raw: Mapping[str, object],
    stream_kind: MarketStreamKind,
) -> TickEvent | BidAskEvent:
    common = {
        "event_id": _string(raw, "event_id"),
        "source": MarketEventSource(_string(raw, "source")),
        "symbol": _string(raw, "symbol"),
        "session_date": _date(raw, "session_date"),
        "event_time": _datetime(raw, "event_time"),
        "received_at": _datetime(raw, "received_at"),
        "ingress_sequence": _integer(raw, "ingress_sequence"),
        "suspended": _boolean(raw, "suspended"),
        "simulated_trade": _boolean(raw, "simulated_trade"),
        "intraday_odd": _boolean(raw, "intraday_odd"),
    }
    if stream_kind is MarketStreamKind.TICK:
        _require_exact_fields(raw, _TICK_FIELDS, "tick payload")
        average_price = raw["average_price"]
        return TickEvent(
            **common,
            price=_decimal_string(raw, "price"),
            tick_volume_lots=_integer(raw, "tick_volume_lots"),
            total_volume_lots=_integer(raw, "total_volume_lots"),
            average_price=(
                None
                if average_price is None
                else _decimal_string(raw, "average_price")
            ),
            intraday_high=_decimal_string(raw, "intraday_high"),
            intraday_low=_decimal_string(raw, "intraday_low"),
            raw_tick_type=_integer(raw, "raw_tick_type"),
            aggressor_side=AggressorSide(_string(raw, "aggressor_side")),
            buy_aggressor_total_lots=_optional_integer(
                raw,
                "buy_aggressor_total_lots",
            ),
            sell_aggressor_total_lots=_optional_integer(
                raw,
                "sell_aggressor_total_lots",
            ),
        )
    _require_exact_fields(raw, _BIDASK_FIELDS, "bidask payload")
    return BidAskEvent(
        **common,
        bid_prices=_decimal_string_list(raw, "bid_prices"),
        bid_volume_lots=_integer_list(raw, "bid_volume_lots"),
        ask_prices=_decimal_string_list(raw, "ask_prices"),
        ask_volume_lots=_integer_list(raw, "ask_volume_lots"),
    )


def _require_exact_fields(
    raw: Mapping[str, object],
    expected: frozenset[str] | set[str],
    label: str,
) -> None:
    actual = set(raw)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(
            f"{label} fields do not match contract; "
            f"missing={missing}, unknown={unknown}"
        )


def _string(raw: Mapping[str, object], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _integer(raw: Mapping[str, object], field_name: str) -> int:
    value = raw.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _optional_integer(
    raw: Mapping[str, object],
    field_name: str,
) -> int | None:
    return None if raw.get(field_name) is None else _integer(raw, field_name)


def _boolean(raw: Mapping[str, object], field_name: str) -> bool:
    value = raw.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _date(raw: Mapping[str, object], field_name: str) -> date:
    return date.fromisoformat(_string(raw, field_name))


def _datetime(raw: Mapping[str, object], field_name: str) -> datetime:
    return datetime.fromisoformat(_string(raw, field_name))


def _decimal_string(raw: Mapping[str, object], field_name: str) -> Decimal:
    value = raw.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a decimal string")
    return Decimal(value)


def _decimal_string_list(
    raw: Mapping[str, object],
    field_name: str,
) -> tuple[Decimal, ...]:
    values = raw.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"{field_name} must contain decimal strings")
    return tuple(Decimal(value) for value in values)


def _integer_list(
    raw: Mapping[str, object],
    field_name: str,
) -> tuple[int, ...]:
    values = raw.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError(f"{field_name} must contain integers")
    return tuple(values)
