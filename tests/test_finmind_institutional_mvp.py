"""Unit tests for the isolated FinMind daily institutional MVP signal."""

from __future__ import annotations

import json
from datetime import date

import pytest

from institutional_mvp.finmind import (
    FinMindMvpSchemaError,
    parse_finmind_mvp_flows,
    select_three_way_buy_candidates,
)


def _payload(data: list[dict[str, object]]) -> bytes:
    return json.dumps({"status": 200, "msg": "success", "data": data}).encode()


def _wide_row(
    symbol: str,
    *,
    foreign: tuple[int, int],
    trust: tuple[int, int],
    dealer: tuple[int, int],
    dealer_self: tuple[int, int] = (0, 0),
    dealer_hedging: tuple[int, int] = (0, 0),
) -> dict[str, object]:
    return {
        "date": "2026-08-18",
        "stock_id": symbol,
        "Foreign_Investor_buy": foreign[0],
        "Foreign_Investor_sell": foreign[1],
        "Investment_Trust_buy": trust[0],
        "Investment_Trust_sell": trust[1],
        "Dealer_buy": dealer[0],
        "Dealer_sell": dealer[1],
        "Dealer_self_buy": dealer_self[0],
        "Dealer_self_sell": dealer_self[1],
        "Dealer_Hedging_buy": dealer_hedging[0],
        "Dealer_Hedging_sell": dealer_hedging[1],
    }


def _stock_info() -> bytes:
    return _payload(
        [
            {
                "date": "2025-01-01",
                "stock_id": "1101",
                "stock_name": "Company A",
                "type": "twse",
            },
            {
                "date": "2025-01-01",
                "stock_id": "6488",
                "stock_name": "Company B",
                "type": "tpex",
            },
            {
                "date": "2024-01-01",
                "stock_id": "6488",
                "stock_name": "Company B",
                "type": "emerging",
            },
        ]
    )


def test_finmind_mvp_selects_only_three_way_net_buy_and_ranks_by_total() -> None:
    flows = parse_finmind_mvp_flows(
        wide_payload=_payload(
            [
                _wide_row(
                    "1101",
                    foreign=(100, 10),
                    trust=(60, 5),
                    dealer=(30, 2),
                    dealer_self=(20, 3),
                    dealer_hedging=(5, 1),
                ),
                _wide_row(
                    "6488",
                    foreign=(40, 10),
                    trust=(10, 2),
                    dealer=(8, 1),
                    dealer_self=(4, 0),
                    dealer_hedging=(3, 1),
                ),
                _wide_row("9999", foreign=(9, 1), trust=(9, 1), dealer=(1, 2)),
            ]
        ),
        stock_info_payload=_stock_info(),
        session_date=date(2026, 8, 18),
        usable_from_session=date(2026, 8, 19),
    )

    assert [(flow.symbol, flow.market) for flow in flows] == [
        ("6488", "TPEX"),
        ("1101", "TWSE"),
    ]
    candidates = select_three_way_buy_candidates(flows)
    assert [candidate.to_dict() for candidate in candidates] == [
        {
            "dealer_net_shares": 21,
            "foreign_investor_net_shares": 90,
            "investment_trust_net_shares": 55,
            "market": "TWSE",
            "name": "Company A",
            "rank": 1,
            "source_session": "2026-08-18",
            "symbol": "1101",
            "three_way_net_shares": 166,
            "usable_from_session": "2026-08-19",
        },
        {
            "dealer_net_shares": 6,
            "foreign_investor_net_shares": 30,
            "investment_trust_net_shares": 8,
            "market": "TPEX",
            "name": "Company B",
            "rank": 2,
            "source_session": "2026-08-18",
            "symbol": "6488",
            "three_way_net_shares": 44,
            "usable_from_session": "2026-08-19",
        },
    ]


def test_finmind_mvp_uses_all_dealer_components_for_three_way_buy() -> None:
    flows = parse_finmind_mvp_flows(
        wide_payload=_payload(
            [
                _wide_row(
                    "1101",
                    foreign=(10, 1),
                    trust=(10, 1),
                    dealer=(0, 0),
                    dealer_self=(4, 1),
                    dealer_hedging=(3, 1),
                )
            ]
        ),
        stock_info_payload=_stock_info(),
        session_date=date(2026, 8, 18),
        usable_from_session=date(2026, 8, 19),
    )

    candidate = select_three_way_buy_candidates(flows)[0]
    assert candidate.dealer_net_shares == 5
    assert candidate.three_way_net_shares == 23


def test_finmind_mvp_uses_legacy_dealer_pair_only_when_components_are_zero() -> None:
    flows = parse_finmind_mvp_flows(
        wide_payload=_payload(
            [
                _wide_row(
                    "1101",
                    foreign=(10, 1),
                    trust=(10, 1),
                    dealer=(10, 1),
                    dealer_self=(4, 1),
                    dealer_hedging=(3, 1),
                ),
                _wide_row(
                    "6488",
                    foreign=(10, 1),
                    trust=(10, 1),
                    dealer=(5, 1),
                ),
            ]
        ),
        stock_info_payload=_stock_info(),
        session_date=date(2026, 8, 18),
        usable_from_session=date(2026, 8, 19),
    )

    candidates = select_three_way_buy_candidates(flows)
    assert [(item.symbol, item.dealer_net_shares) for item in candidates] == [
        ("1101", 5),
        ("6488", 4),
    ]


def test_finmind_mvp_rejects_wrong_session_or_missing_flow_columns() -> None:
    with pytest.raises(FinMindMvpSchemaError, match="response date"):
        parse_finmind_mvp_flows(
            wide_payload=_payload(
                [
                    {
                        **_wide_row(
                            "1101",
                            foreign=(1, 0),
                            trust=(1, 0),
                            dealer=(1, 0),
                        ),
                        "date": "2026-08-17",
                    }
                ]
            ),
            stock_info_payload=_stock_info(),
            session_date=date(2026, 8, 18),
            usable_from_session=date(2026, 8, 19),
        )

    malformed = _wide_row("1101", foreign=(1, 0), trust=(1, 0), dealer=(1, 0))
    del malformed["Dealer_Hedging_sell"]
    with pytest.raises(FinMindMvpSchemaError, match="Dealer_Hedging_sell"):
        parse_finmind_mvp_flows(
            wide_payload=_payload([malformed]),
            stock_info_payload=_stock_info(),
            session_date=date(2026, 8, 18),
            usable_from_session=date(2026, 8, 19),
        )


def test_finmind_mvp_requires_next_session_and_positive_limit() -> None:
    with pytest.raises(ValueError, match="usable_from_session"):
        parse_finmind_mvp_flows(
            wide_payload=_payload(
                [_wide_row("1101", foreign=(1, 0), trust=(1, 0), dealer=(1, 0))]
            ),
            stock_info_payload=_stock_info(),
            session_date=date(2026, 8, 18),
            usable_from_session=date(2026, 8, 18),
        )
    with pytest.raises(ValueError, match="limit"):
        select_three_way_buy_candidates((), limit=0)
