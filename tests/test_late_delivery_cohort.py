from __future__ import annotations

from datetime import date

from market_data.late_delivery_cohort import build_late_delivery_cohort
from market_data.late_delivery_evidence import LateDeliveryCohort


def test_official_quote_source_creates_frozen_seven_symbol_cohort() -> None:
    raw = {
        "fields": ["Security Code", "Trade Value"],
        "data": [
            ["1101", "100"], ["1102", "200"], ["1103", "300"],
            ["1104", "400"], ["1105", "500"], ["1106", "600"],
            ["1107", "700"], ["1108", "800"], ["1109", "900"],
            ["1110", "1000"], ["1111", "1100"], ["1112", "1200"],
            ["1113", "1300"], ["1114", "1400"], ["1115", "1500"],
            ["2330", "1600"], ["2317", "1700"], ["2454", "1800"],
        ],
    }

    manifest = build_late_delivery_cohort(
        raw_response=raw,
        source_date=date(2026, 8, 20),
        source_identity="fixture:twse-mi-index",
    )
    cohort = LateDeliveryCohort.from_mapping(manifest)

    assert cohort.symbols[:3] == ("1101", "1103", "1109")
    assert set(("2330", "2317", "2454")).issubset(cohort.symbols)
    assert {entry.liquidity_tier for entry in cohort.entries} == {"high", "mid", "low"}
    assert manifest["status"] == "FROZEN_FOR_COLLECTION"


def test_official_quote_source_accepts_current_twse_tables_shape() -> None:
    raw = {
        "tables": [
            {"fields": ["Index", "Closing Index"], "data": [["TAIEX", "1"]]},
            {
                "fields": ["Security Code", "Trade Value"],
                "data": [
                    ["1101", "1"], ["1102", "2"], ["1103", "3"],
                    ["1104", "4"], ["2330", "5"], ["2317", "6"], ["2454", "7"],
                ],
            },
        ]
    }

    manifest = build_late_delivery_cohort(
        raw_response=raw,
        source_date=date(2026, 8, 20),
        source_identity="fixture:twse-tables",
    )

    assert len(manifest["symbols"]) == 7
