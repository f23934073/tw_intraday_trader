from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import HistoricalBar, digest
from backtest.research_replay.application import SignalReplayPreflightService
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.dataset_adapter import CanonicalFullDatasetAdapter
from backtest.research_replay.domain import ResearchReplayIntegrityError
from backtest.research_replay.ports import BaselinePreflightEvidence
from scripts.preflight_vwap_signal_ledger_replay import (
    ProviderFreeExternalCallAudit,
    _parser,
    _write_audit,
)
from scripts.audit_vwap_signal_ledger_replay import audit_preflight
from scripts.execute_vwap_signal_ledger_replay import _parser as _execute_parser
from tests.test_signal_ledger_replay_domain import (
    _bar,
    _decision,
    _identity,
    _order,
)
from backtest.research_replay.domain import build_ledger, build_order_derivation


_TAIPEI = ZoneInfo("Asia/Taipei")


class _Dataset:
    def __init__(self, bars):
        self._bars = tuple(bars)

    def iter_observed_bars(self):
        return iter(self._bars)


class _Audit:
    def __init__(self, *, provider: int = 0):
        self.provider = provider

    def snapshot(self):
        return {
            "strategy_evaluation_count": 0,
            "provider_call_count": self.provider,
            "broker_call_count": 0,
        }


def _evidence() -> BaselinePreflightEvidence:
    decisions = [
        _decision("decision-1", "2317", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)),
        _decision("decision-2", "2330", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)),
    ]
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=decisions)
    derivation = build_order_derivation(
        ledger_rows=ledger.rows,
        orders=[_order(item, index) for index, item in enumerate(decisions, 1)],
    )
    return BaselinePreflightEvidence(
        identity=_identity(),
        dataset_manifest={},
        ledger=ledger,
        order_derivation=derivation,
    )


def _bars():
    return [
        _bar("2317", datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI), opened="100", closed="100"),
        _bar("2330", datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI), opened="100", closed="100"),
        _bar("2317", datetime(2026, 8, 21, 9, 3, tzinfo=_TAIPEI), opened="100", closed="110"),
        _bar("2330", datetime(2026, 8, 21, 9, 3, tzinfo=_TAIPEI), opened="100", closed="90"),
    ]


def test_g3_service_publishes_complete_provider_free_preflight(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(SignalReplayPreflightService, "_FROZEN_SIGNAL_COUNT", 2)
    service = SignalReplayPreflightService(
        artifacts=ReplayArtifactStore(tmp_path / "artifacts", chunk_size=1)
    )

    result = service.build_full_preflight(
        evidence=_evidence(),
        dataset=_Dataset(_bars()),
        external_calls=ProviderFreeExternalCallAudit(),
    )

    assert result.match_manifest["signal_count"] == 2
    assert result.match_manifest["matched_entry_count"] == 2
    assert result.match_manifest["matched_exit_count"] == 2
    assert result.match_manifest["missing_entry_count"] == 0
    assert result.match_manifest["missing_exit_count"] == 0
    assert result.match_manifest["duplicate_match_count"] == 0
    assert result.ledger_path.is_dir()
    assert result.match_plan_path.is_dir()
    assert result.to_audit_dict()["provider_call_count"] == 0

    audit_path = tmp_path / "preflight-audit.json"
    _write_audit(audit_path, result.to_audit_dict())
    verified = audit_preflight(
        artifact_root=tmp_path / "artifacts",
        preflight_digest=result.match_manifest["match_plan_manifest_digest"],
        operation_audit=audit_path,
    )
    assert verified["verified"] is True
    assert verified["ledger_minus_match_count"] == 0
    assert verified["match_minus_ledger_count"] == 0

    for field, forged_value in (
        ("schema_version", "r5-signal-ledger-preflight-operation-audit-v1"),
        ("baseline_run_id", "run-forged"),
        ("dataset_id", "forged-dataset"),
        ("dataset_digest", "e" * 64),
        ("dataset_bars_sha256", "f" * 64),
    ):
        forged_audit = {**result.to_audit_dict(), field: forged_value}
        forged_path = tmp_path / f"forged-{field}.json"
        _write_audit(forged_path, forged_audit)
        with pytest.raises(ResearchReplayIntegrityError):
            audit_preflight(
                artifact_root=tmp_path / "artifacts",
                preflight_digest=result.match_manifest[
                    "match_plan_manifest_digest"
                ],
                operation_audit=forged_path,
            )


def test_g3_service_rejects_nonzero_external_call_evidence_before_publication(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(SignalReplayPreflightService, "_FROZEN_SIGNAL_COUNT", 2)
    root = tmp_path / "artifacts"
    service = SignalReplayPreflightService(artifacts=ReplayArtifactStore(root))

    with pytest.raises(ResearchReplayIntegrityError, match="啟動前"):
        service.build_full_preflight(
            evidence=_evidence(),
            dataset=_Dataset(_bars()),
            external_calls=_Audit(provider=1),
        )

    assert not root.exists()


def test_canonical_dataset_adapter_preserves_exact_source_bytes(tmp_path) -> None:
    bars = [
        HistoricalBar(
            symbol="2330",
            timestamp=datetime(2026, 8, 21, 9, minute, tzinfo=_TAIPEI),
            session_date=datetime(2026, 8, 21).date(),
            open=Decimal(price),
            high=Decimal(price),
            low=Decimal(price),
            close=Decimal(price),
            volume=100,
            name="台積電",
            market="TWSE",
        )
        for minute, price in ((1, "100"), (2, "101"))
    ]
    root = tmp_path / "datasets"
    catalog = HistoricalDatasetCatalog(root)
    source_digest = digest({"source": "g3-adapter-test"})
    dataset_id = f"dataset-finmind-sponsor-sha256-{source_digest}"
    identity = {"dataset_id": dataset_id, "source_snapshot_digest": source_digest}
    manifest = catalog.create_finmind_snapshot_dataset(
        dataset_id=dataset_id,
        symbol_streams=(bars,),
        created_at=datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI),
        source="FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        requested_symbols=("2330",),
        expected_bar_count=2,
        start_date="2026-08-21",
        end_date="2026-08-21",
        issues=("AMOUNT_DERIVED_PROXY",),
        volume_contract={"unit": "COMMON_LOTS"},
        amount_contract={"kind": "DERIVED_CLOSE_X_VOLUME_PROXY"},
        source_snapshot_digest=source_digest,
        plan_identity=identity,
        plan_identity_digest=digest(identity),
    )
    adapter = CanonicalFullDatasetAdapter(
        root=root,
        registered_manifest=manifest.to_dict(),
        progress_every=1,
    )

    observed = list(adapter.iter_observed_bars())

    assert [item.bar for item in observed] == bars
    assert all(b"\n" not in item.source_json for item in observed)


def test_canonical_dataset_adapter_rejects_payload_byte_tamper(tmp_path) -> None:
    bars = [
        HistoricalBar(
            symbol="2330",
            timestamp=datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI),
            session_date=datetime(2026, 8, 21).date(),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=100,
            name="台積電",
            market="TWSE",
        )
    ]
    root = tmp_path / "datasets"
    catalog = HistoricalDatasetCatalog(root)
    source_digest = digest({"source": "g3-adapter-tamper"})
    dataset_id = f"dataset-finmind-sponsor-sha256-{source_digest}"
    identity = {"dataset_id": dataset_id, "source_snapshot_digest": source_digest}
    manifest = catalog.create_finmind_snapshot_dataset(
        dataset_id=dataset_id,
        symbol_streams=(bars,),
        created_at=datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI),
        source="FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        requested_symbols=("2330",),
        expected_bar_count=1,
        start_date="2026-08-21",
        end_date="2026-08-21",
        issues=("AMOUNT_DERIVED_PROXY",),
        volume_contract={"unit": "COMMON_LOTS"},
        amount_contract={"kind": "DERIVED_CLOSE_X_VOLUME_PROXY"},
        source_snapshot_digest=source_digest,
        plan_identity=identity,
        plan_identity_digest=digest(identity),
    )
    adapter = CanonicalFullDatasetAdapter(
        root=root, registered_manifest=manifest.to_dict()
    )
    payload = root / dataset_id / "bars.jsonl"
    payload.write_bytes(b"\n" + payload.read_bytes())

    with pytest.raises(ResearchReplayIntegrityError, match="不可空白"):
        list(adapter.iter_observed_bars())


def test_g3_cli_contract_is_provider_free_and_help_is_available() -> None:
    help_text = _parser().format_help()
    source = (
        __import__("scripts.preflight_vwap_signal_ledger_replay", fromlist=["x"])
        .__file__
    )
    assert "--baseline-run-id" in help_text
    text = Path(source).read_text(encoding="utf-8")
    for prohibited in ("shioaji", "market_data", "broker", "simulation"):
        assert f"import {prohibited}" not in text


def test_g4_cli_contract_has_no_execution_override_or_external_port() -> None:
    help_text = _execute_parser().format_help()
    source = Path(
        __import__(
            "scripts.execute_vwap_signal_ledger_replay", fromlist=["x"]
        ).__file__
    ).read_text(encoding="utf-8")

    for required in (
        "--baseline-run-id",
        "--preflight-digest",
        "--idempotency-key",
        "--actor-id",
        "--change-note",
    ):
        assert required in help_text
    for prohibited_option in (
        "--shares",
        "--commission-rate",
        "--sell-tax-rate",
        "--slippage-bps",
        "--dataset-id",
        "--strategy-id",
    ):
        assert prohibited_option not in help_text
    for prohibited_import in ("shioaji", "market_data", "broker", "simulation"):
        assert f"import {prohibited_import}" not in source
    assert 'current["status"] == "CANCELLING"' in source
    assert "service.mark_cancelled(" in source


def test_g4_formal_sql_is_read_only_multiplicity_aware_and_fail_closed() -> None:
    sql = Path(
        ".planning/2026-08-24-vwap-strategy-failure-attribution/"
        "r5_v2_replay_acceptance_queries.sql"
    ).read_text(encoding="utf-8")

    assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY" in sql
    assert sql.count("EXCEPT ALL") == 4
    assert "expected_result_manifest_digest is required" in sql
    assert "expected_postflight_digest is required" in sql
    for evidence in (
        "diagnostic_counts_match",
        "diagnostic_differences_zero",
        "diagnostic_duplicates_zero",
        "diagnostic_multiplicity_chain_matches",
        "exact_terminal_schemas_match",
    ):
        assert evidence in sql
    assert "condition.value <> 'true'::jsonb" in sql
    assert "1 / CASE WHEN :'r5_v2_gate_ok'::boolean THEN 1 ELSE 0 END" in sql
