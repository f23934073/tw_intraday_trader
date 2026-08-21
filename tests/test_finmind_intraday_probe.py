"""Offline semantic gates for the Sponsor-entitled FinMind r2 capture."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from institutional_research.finmind_intraday_probe import (
    build_finmind_probe_result,
    inspect_symbol,
    reconcile_control,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "institutional_evaluation" / "acquisition"
FINMIND = BASE / "credentialed_finmind_intraday_source_probe_capture_v1_2026-08-21-r2"
REFERENCE = BASE / "credentialed_intraday_source_reference_capture_v1_2026-08-20-r1"
PROTOCOL = BASE / "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21_r2.json"


def _payload(symbol: str, dataset: str) -> dict[str, object]:
    manifest = json.loads((FINMIND / "capture_manifest.json").read_text())
    record = next(
        item
        for item in manifest["records"]
        if item["symbol"] == symbol and item["dataset"] == dataset
    )
    return json.loads((FINMIND / record["body_file"]).read_bytes())


def test_target_and_sparse_control_are_observed_empty() -> None:
    for symbol in ("1259", "12561"):
        observation = inspect_symbol(
            symbol=symbol,
            kbar_payload=_payload(symbol, "TaiwanStockKBar"),
            tick_payload=_payload(symbol, "TaiwanStockPriceTick"),
        )
        assert observation["kbar_count"] == 0
        assert observation["tick_count"] == 0


def test_available_controls_reconstruct_exactly() -> None:
    for symbol, market in (("1240", "TPEX"), ("2330", "TWSE"), ("2317", "TWSE")):
        comparison = reconcile_control(
            symbol=symbol,
            market=market,
            kbar_payload=_payload(symbol, "TaiwanStockKBar"),
            tick_payload=_payload(symbol, "TaiwanStockPriceTick"),
            reference_capture=json.loads(
                (REFERENCE / f"shioaji_{symbol}.capture.json").read_text()
            ),
        )
        assert comparison["semantic_pass"] is True
        assert comparison["tick_kbar_mismatch_count"] == 0
        assert comparison["reference_ohlcv_mismatch_count"] == 0
        assert Decimal(comparison["vwap_absolute_difference"]) == 0
        assert comparison["volume_hypothesis"] == (
            "RAW_VOLUME_IS_COMMON_LOTS_MULTIPLY_BY_1000"
        )


def test_result_is_narrow_rejection_with_fail_closed_permissions() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    result = build_finmind_probe_result(
        protocol=protocol,
        protocol_digest=PROTOCOL.with_suffix(".canonical.sha256").read_text().strip(),
        finmind_capture_dir=FINMIND,
        reference_capture_dir=REFERENCE,
    )
    assert result["result"] == {
        "all_available_control_semantics_passed": True,
        "all_fixed_controls_available": False,
        "cross_market_semantics_passed": True,
        "dataset_entitlement_verified": True,
        "source_qualified": False,
        "source_selected": False,
        "target_1259_nonempty": False,
        "verdict": "REJECTED_FOR_MISMATCH_RESOLUTION",
    }
    assert all(value is False for value in result["permissions"].values())
