from __future__ import annotations

from copy import deepcopy

import pytest

from backtest.research_control import recompute_backtest_result_digest
from scripts.preflight_vwap_cash_admission_control import (
    _verify_baseline_result_identity,
)


def _result() -> dict[str, object]:
    result: dict[str, object] = {
        "summary": {"verdict": "INSUFFICIENT_EVIDENCE"},
        "trades": [],
        "daily_equity": [],
        "decisions": [{"decision_id": "decision-1"}],
        "orders": [{"order_id": "order-1", "side": "ENTRY"}],
        "fills": [],
    }
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    return result


def test_preflight_cli_recomputes_baseline_semantic_result_before_scan() -> None:
    result = _result()
    baseline = {"result_digest": result["summary"]["result_digest"]}

    _verify_baseline_result_identity(baseline, result)

    tampered = deepcopy(result)
    tampered["decisions"][0]["decision_id"] = "tampered"
    with pytest.raises(ValueError, match="semantic result digest"):
        _verify_baseline_result_identity(baseline, tampered)


def test_preflight_cli_rejects_run_row_digest_conflict() -> None:
    result = _result()
    with pytest.raises(ValueError, match="semantic result digest"):
        _verify_baseline_result_identity({"result_digest": "0" * 64}, result)
