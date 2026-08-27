"""FinMind-only daily institutional candidate observations for the MVP path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping


class FinMindMvpSchemaError(ValueError):
    """The bounded FinMind MVP response does not satisfy the frozen mapping."""


@dataclass(frozen=True)
class FinMindMvpFlow:
    symbol: str
    name: str
    market: str
    session_date: date
    usable_from_session: date
    foreign_investor_net_shares: int
    investment_trust_net_shares: int
    dealer_net_shares: int

    @property
    def three_way_net_shares(self) -> int:
        return (
            self.foreign_investor_net_shares
            + self.investment_trust_net_shares
            + self.dealer_net_shares
        )


@dataclass(frozen=True)
class FinMindMvpCandidate:
    rank: int
    symbol: str
    name: str
    market: str
    source_session: date
    usable_from_session: date
    foreign_investor_net_shares: int
    investment_trust_net_shares: int
    dealer_net_shares: int
    three_way_net_shares: int

    def to_dict(self) -> dict[str, object]:
        return {
            "dealer_net_shares": self.dealer_net_shares,
            "foreign_investor_net_shares": self.foreign_investor_net_shares,
            "investment_trust_net_shares": self.investment_trust_net_shares,
            "market": self.market,
            "name": self.name,
            "rank": self.rank,
            "source_session": self.source_session.isoformat(),
            "symbol": self.symbol,
            "three_way_net_shares": self.three_way_net_shares,
            "usable_from_session": self.usable_from_session.isoformat(),
        }


def parse_finmind_mvp_flows(
    *,
    wide_payload: bytes,
    stock_info_payload: bytes,
    session_date: date,
    usable_from_session: date,
) -> tuple[FinMindMvpFlow, ...]:
    """Join one daily wide-flow response to a current FinMind market mapping."""
    if usable_from_session <= session_date:
        raise ValueError("usable_from_session must follow the source session")
    wide_rows = _data_rows(wide_payload, "TaiwanStockInstitutionalInvestorsBuySellWide")
    mapping = _latest_current_mapping(stock_info_payload)
    flows: list[FinMindMvpFlow] = []
    seen: set[str] = set()
    for row in wide_rows:
        symbol = _text(row.get("stock_id"), "stock_id").upper()
        if symbol in seen:
            raise FinMindMvpSchemaError(f"duplicate stock_id in wide flow: {symbol}")
        seen.add(symbol)
        observed_date = _date(row.get("date"), "date")
        if observed_date != session_date:
            raise FinMindMvpSchemaError("wide flow response date differs from request")
        identity = mapping.get(symbol)
        if identity is None:
            continue
        foreign_net = _net(
            row,
            buy_field="Foreign_Investor_buy",
            sell_field="Foreign_Investor_sell",
        )
        trust_net = _net(
            row,
            buy_field="Investment_Trust_buy",
            sell_field="Investment_Trust_sell",
        )
        dealer_net = _dealer_total_net(row)
        flows.append(
            FinMindMvpFlow(
                symbol=symbol,
                name=identity[0],
                market=identity[1],
                session_date=session_date,
                usable_from_session=usable_from_session,
                foreign_investor_net_shares=foreign_net,
                investment_trust_net_shares=trust_net,
                dealer_net_shares=dealer_net,
            )
        )
    return tuple(sorted(flows, key=lambda item: (item.market, item.symbol)))


def select_three_way_buy_candidates(
    flows: tuple[FinMindMvpFlow, ...], *, limit: int | None = None
) -> tuple[FinMindMvpCandidate, ...]:
    """Rank symbols where foreign, trust, and dealer net buying are all positive."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when supplied")
    ranked = sorted(
        (
            flow
            for flow in flows
            if flow.foreign_investor_net_shares > 0
            and flow.investment_trust_net_shares > 0
            and flow.dealer_net_shares > 0
        ),
        key=lambda item: (-item.three_way_net_shares, item.market, item.symbol),
    )
    if limit is not None:
        ranked = ranked[:limit]
    return tuple(
        FinMindMvpCandidate(
            rank=index,
            symbol=flow.symbol,
            name=flow.name,
            market=flow.market,
            source_session=flow.session_date,
            usable_from_session=flow.usable_from_session,
            foreign_investor_net_shares=flow.foreign_investor_net_shares,
            investment_trust_net_shares=flow.investment_trust_net_shares,
            dealer_net_shares=flow.dealer_net_shares,
            three_way_net_shares=flow.three_way_net_shares,
        )
        for index, flow in enumerate(ranked, start=1)
    )


def finmind_mvp_row_count(payload: bytes, dataset: str) -> int:
    """Validate one FinMind envelope and return its observed row count."""
    return len(_data_rows(payload, dataset))


def _data_rows(payload: bytes, dataset: str) -> list[Mapping[str, Any]]:
    try:
        envelope = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinMindMvpSchemaError(f"{dataset} response is not valid JSON") from error
    if not isinstance(envelope, Mapping):
        raise FinMindMvpSchemaError(f"{dataset} response envelope must be an object")
    if envelope.get("status") != 200:
        raise FinMindMvpSchemaError(f"{dataset} response status is not 200")
    rows = envelope.get("data")
    if not isinstance(rows, list):
        raise FinMindMvpSchemaError(f"{dataset} response data must be a list")
    if not all(isinstance(row, Mapping) for row in rows):
        raise FinMindMvpSchemaError(f"{dataset} rows must be objects")
    return rows


def _latest_current_mapping(payload: bytes) -> dict[str, tuple[str, str]]:
    rows = _data_rows(payload, "TaiwanStockInfo")
    observations: dict[str, list[tuple[date, str, str]]] = {}
    for row in rows:
        symbol = _text(row.get("stock_id"), "stock_id").upper()
        market = _text(row.get("type"), "type").lower()
        if market not in {"twse", "tpex"}:
            continue
        name = _text(row.get("stock_name"), "stock_name")
        try:
            observed_at = _date(row.get("date"), "date")
        except FinMindMvpSchemaError:
            continue
        observations.setdefault(symbol, []).append((observed_at, name, market))
    resolved: dict[str, tuple[str, str]] = {}
    for symbol, values in observations.items():
        latest = max(item[0] for item in values)
        identities = {(name, market) for observed, name, market in values if observed == latest}
        if len(identities) != 1:
            raise FinMindMvpSchemaError(f"ambiguous current market mapping: {symbol}")
        name, market = next(iter(identities))
        resolved[symbol] = (name, "TWSE" if market == "twse" else "TPEX")
    return resolved


def _net(row: Mapping[str, Any], *, buy_field: str, sell_field: str) -> int:
    return _integer(row.get(buy_field), buy_field) - _integer(row.get(sell_field), sell_field)


def _dealer_total_net(row: Mapping[str, Any]) -> int:
    """Normalize FinMind's component encoding without double-counting legacy fields."""
    self_buy = _integer(row.get("Dealer_self_buy"), "Dealer_self_buy")
    self_sell = _integer(row.get("Dealer_self_sell"), "Dealer_self_sell")
    hedging_buy = _integer(row.get("Dealer_Hedging_buy"), "Dealer_Hedging_buy")
    hedging_sell = _integer(row.get("Dealer_Hedging_sell"), "Dealer_Hedging_sell")
    if any((self_buy, self_sell, hedging_buy, hedging_sell)):
        return (self_buy - self_sell) + (hedging_buy - hedging_sell)
    return _net(row, buy_field="Dealer_buy", sell_field="Dealer_sell")


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise FinMindMvpSchemaError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value)
    raise FinMindMvpSchemaError(f"{field_name} must be an integer")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinMindMvpSchemaError(f"{field_name} must be a non-empty string")
    return value.strip()


def _date(value: object, field_name: str) -> date:
    try:
        return date.fromisoformat(_text(value, field_name))
    except ValueError as error:
        raise FinMindMvpSchemaError(f"{field_name} must be ISO date") from error
