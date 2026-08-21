"""Create one provenance-backed frozen cohort for passive late evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_data.late_delivery_evidence import LATE_DELIVERY_COHORT_MANIFEST_SCHEMA


TWSE_MI_INDEX_URL = "https://www.twse.com.tw/rwd/en/afterTrading/MI_INDEX"
FIXED_HIGH_SYMBOLS = ("2330", "2317", "2454")
_FIELD_ALIASES = {
    "symbol": ("Security Code", "證券代號"),
    "trade_value": ("Trade Value", "成交金額"),
}
_TIER_PERCENTILES = {
    "mid": (0.45, 0.55),
    "low": (0.05, 0.15),
}


def fetch_twse_daily_quotes(source_date: date) -> tuple[bytes, str]:
    """Fetch the completed-session official daily quotes source over fixed HTTPS."""
    query = urlencode(
        {"date": source_date.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"}
    )
    url = f"{TWSE_MI_INDEX_URL}?{query}"
    request = Request(url, headers={"User-Agent": "tw-intraday-trader-late-evidence"})
    with urlopen(request, timeout=30) as response:  # nosec B310: fixed TWSE HTTPS URL
        return response.read(), url


def build_late_delivery_cohort(
    *,
    raw_response: Mapping[str, object],
    source_date: date,
    source_identity: str,
) -> dict[str, object]:
    """Select fixed high seeds plus deterministic mid/low quote-value bands.

    The rule is deliberately frozen into the artifact.  It makes no judgement
    from capture results and never changes a campaign cohort after collection.
    """
    ranking = _extract_ranking(raw_response)
    by_symbol = {symbol: value for symbol, value in ranking}
    missing = [symbol for symbol in FIXED_HIGH_SYMBOLS if symbol not in by_symbol]
    if missing:
        raise ValueError("official quote source is missing fixed high symbols: " + ",".join(missing))
    selections: list[tuple[str, str, str]] = []
    for symbol in FIXED_HIGH_SYMBOLS:
        selections.append(
            (
                symbol,
                "high",
                f"Fixed high-liquidity seed; official Trade Value: NT${by_symbol[symbol]:,}.",
            )
        )
    selected_symbols = set(FIXED_HIGH_SYMBOLS)
    for tier, percentiles in _TIER_PERCENTILES.items():
        for percentile in percentiles:
            position, (symbol, amount) = _nearest_rank(ranking, percentile, selected_symbols)
            selected_symbols.add(symbol)
            selections.append(
                (
                    symbol,
                    tier,
                    (
                        f"TWSE {source_date.isoformat()} nearest-rank p{int(percentile * 100):02d} "
                        f"Trade Value rank {position}/{len(ranking)}: NT${amount:,}."
                    ),
                )
            )
    if not 6 <= len(selections) <= 9:
        raise AssertionError("late-delivery cohort size is outside its frozen contract")
    digest = hashlib.sha256(
        json.dumps(raw_response, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": LATE_DELIVERY_COHORT_MANIFEST_SCHEMA,
        "status": "FROZEN_FOR_COLLECTION",
        "capture_timezone": "Asia/Taipei",
        "selection_source": {
            "provider": "TWSE",
            "source_date": source_date.isoformat(),
            "source_identity": f"{source_identity}:sha256:{digest}",
        },
        "symbols": [
            {"symbol": symbol, "liquidity_tier": tier, "selection_evidence": evidence}
            for symbol, tier, evidence in sorted(selections)
        ],
        "session_windows": [
            {"phase": "OPEN", "start_local": "09:00", "end_local": "09:30"},
            {"phase": "MID", "start_local": "10:30", "end_local": "11:00"},
            {"phase": "CLOSE", "start_local": "13:00", "end_local": "13:30"},
        ],
    }


def write_frozen_cohort(path: Path, manifest: Mapping[str, object]) -> Path:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("refusing to overwrite a different frozen cohort")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    return path


def _extract_ranking(raw_response: Mapping[str, object]) -> tuple[tuple[str, int], ...]:
    fields, rows = _quote_table(raw_response)
    symbol_index = _field_index(fields, _FIELD_ALIASES["symbol"])
    value_index = _field_index(fields, _FIELD_ALIASES["trade_value"])
    eligible: list[tuple[str, int]] = []
    for row in rows:
        if len(row) <= max(symbol_index, value_index):
            continue
        symbol = str(row[symbol_index]).strip().upper()
        amount = _non_negative_integer(row[value_index])
        if len(symbol) == 4 and symbol.isdigit() and symbol[0] in "123456789" and amount > 0:
            eligible.append((symbol, amount))
    deduplicated = {symbol: amount for symbol, amount in eligible}
    if len(deduplicated) < 7:
        raise ValueError("official quote source does not contain enough eligible securities")
    return tuple(sorted(deduplicated.items(), key=lambda item: (item[1], item[0])))


def _quote_table(raw: Mapping[str, object]) -> tuple[Sequence[object], Sequence[Sequence[object]]]:
    tables = raw.get("tables")
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, Mapping):
                continue
            fields = table.get("fields")
            rows = table.get("data")
            if isinstance(fields, list) and isinstance(rows, list) and _has_quote_fields(fields):
                return fields, [row for row in rows if isinstance(row, list)]
    for field_key, fields in raw.items():
        if not field_key.startswith("fields") or not isinstance(fields, list):
            continue
        suffix = field_key[len("fields"):]
        row_key = "data" + suffix
        rows = raw.get(row_key)
        if isinstance(rows, list) and _has_quote_fields(fields):
            normalized_rows = [row for row in rows if isinstance(row, list)]
            return fields, normalized_rows
    if isinstance(raw.get("fields"), list) and isinstance(raw.get("data"), list):
        return raw["fields"], [row for row in raw["data"] if isinstance(row, list)]
    raise ValueError("official quote source has no Security Code/Trade Value table")


def _has_quote_fields(fields: Sequence[object]) -> bool:
    values = {str(item).strip() for item in fields}
    return any(item in values for item in _FIELD_ALIASES["symbol"]) and any(
        item in values for item in _FIELD_ALIASES["trade_value"]
    )


def _field_index(fields: Sequence[object], aliases: Sequence[str]) -> int:
    values = [str(item).strip() for item in fields]
    for alias in aliases:
        if alias in values:
            return values.index(alias)
    raise ValueError("official quote source field is absent")


def _non_negative_integer(value: object) -> int:
    normalized = str(value).strip().replace(",", "")
    try:
        result = int(normalized)
    except ValueError as error:
        raise ValueError(f"Trade Value is not an integer: {value!r}") from error
    if result < 0:
        raise ValueError("Trade Value cannot be negative")
    return result


def _nearest_rank(
    ranking: tuple[tuple[str, int], ...],
    percentile: float,
    excluded: set[str],
) -> tuple[int, tuple[str, int]]:
    position = max(1, math.ceil(percentile * len(ranking)))
    for offset in range(len(ranking)):
        for candidate in (position - 1 - offset, position - 1 + offset):
            if 0 <= candidate < len(ranking) and ranking[candidate][0] not in excluded:
                return candidate + 1, ranking[candidate]
    raise ValueError("cannot select a distinct security for the requested percentile")
