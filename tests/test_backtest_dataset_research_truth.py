"""Immutable Dataset research-truth and v3 snapshot-binding tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtest.application import BacktestApplicationService
from backtest.cost_policy_tw import build_cost_policy_snapshot, verify_cost_policy_snapshot
from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog
from backtest.domain import BacktestRunConfig, StrategySetSnapshot, canonical_json, digest
from backtest.execution_policy_tw import (
    build_execution_policy_snapshot,
    verify_execution_policy_snapshot,
)
from backtest.qualification import experiment_family_id, research_baseline_identity_digest
from backtest.research_truth import (
    ResearchTruthUnavailable,
    build_research_truth_snapshot,
    require_formal_research_truth,
    research_readiness_projection,
    verify_research_truth_snapshot,
)
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MockProvider
from tests.test_backtest_no_lookahead_close import _bars


FIXTURE_ROOT = Path("tests/fixtures/backtest/tw_research_truth_v1")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _sealed(contract: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in contract.items() if key != "snapshot_digest"}
    return {**body, "snapshot_digest": digest(body)}


def _formal_manifest(base: DatasetManifest) -> DatasetManifest:
    fixture = _fixture("pass_manifest.json")
    contract_names = (
        "universe_contract",
        "listing_contract",
        "session_contract",
        "calendar_contract",
        "closing_auction_event_contract",
        "corporate_action_contract",
        "reference_price_contract",
        "price_limit_contract",
        "volume_contract",
        "amount_contract",
        "special_regime_contract",
        "completeness_contract",
        "execution_calibration_contract",
        "slippage_calibration_contract",
    )
    contracts = {name: dict(fixture[name]) for name in contract_names}
    completeness = dict(contracts["completeness_contract"])
    completeness.update(start_date=base.start_date, end_date=base.end_date)
    contracts["completeness_contract"] = _sealed(completeness)
    return DatasetManifest.from_dict(
        {
            **base.to_dict(include_digest=False),
            "universe_scope": "DATE_EFFECTIVE",
            "research_eligible": True,
            "issues": [],
            **contracts,
        }
    )


def test_sealed_pass_manifest_round_trips_and_builds_deterministic_truth() -> None:
    raw = _fixture("pass_manifest.json")
    manifest = DatasetManifest.from_dict(raw)

    assert manifest.to_dict() == raw
    snapshots = [build_research_truth_snapshot(manifest) for _ in range(3)]
    assert snapshots[1:] == [snapshots[0], snapshots[0]]
    verified = require_formal_research_truth(snapshots[0], manifest=manifest)
    assert verified["status"] == "VERIFIED"
    assert verified["closing_auction_event_contract"] == {
        "status": "VERIFIED",
        "event_time": "13:30:00+08:00",
        "price_semantics": "AUCTION_ONLY",
        "volume_semantics": "AUCTION_ONLY",
    }
    assert research_readiness_projection(verified)["status"] == "DATA_READY"


def test_current_snapshot_manifest_remains_readable_but_formal_truth_fails() -> None:
    raw = _fixture("fail_current_snapshot_manifest.json")
    manifest = DatasetManifest.from_dict(raw)

    assert manifest.to_dict() == raw
    snapshot = build_research_truth_snapshot(manifest)
    verified = verify_research_truth_snapshot(snapshot, manifest=manifest)
    assert verified["status"] == "FAIL_CLOSED"
    assert verified["reason_codes"][:3] == [
        "CURRENT_SNAPSHOT_UNIVERSE",
        "MANIFEST_NOT_RESEARCH_ELIGIBLE",
        "MANIFEST_ISSUES_PRESENT",
    ]
    assert research_readiness_projection(verified)["status"] == "DATA_NOT_READY"
    with pytest.raises(ResearchTruthUnavailable, match="FORMAL_DATA_FAIL"):
        require_formal_research_truth(verified)


def test_missing_drifted_or_unknown_contract_fails_closed() -> None:
    raw = _fixture("pass_manifest.json")
    drifted = dict(raw)
    auction = dict(drifted["closing_auction_event_contract"])
    auction["price_semantics"] = "MIXED_SESSION"
    drifted["closing_auction_event_contract"] = auction
    missing = dict(raw)
    missing.pop("calendar_contract")
    unknown = dict(raw)
    calendar = dict(unknown["calendar_contract"])
    calendar["contract_version"] = "tw-calendar-unknown"
    unknown["calendar_contract"] = _sealed(calendar)

    cases = (
        (drifted, "INVALID_CLOSING_AUCTION_EVENT_CONTRACT"),
        (missing, "MISSING_CALENDAR_CONTRACT"),
        (unknown, "INVALID_CALENDAR_CONTRACT"),
    )
    for manifest_document, expected_reason in cases:
        snapshot = build_research_truth_snapshot(DatasetManifest.from_dict(manifest_document))
        assert snapshot["status"] == "FAIL_CLOSED"
        assert expected_reason in snapshot["reason_codes"]


def test_v3_run_creation_binds_exactly_three_frozen_snapshots(tmp_path: Path) -> None:
    catalog_root = tmp_path / "datasets"
    catalog = HistoricalDatasetCatalog(catalog_root)
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    base = catalog.create_imported_dataset(
        bars=_bars(),
        source="formal-fixture",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    manifest = _formal_manifest(base)
    (catalog_root / base.dataset_id / "manifest.json").write_text(
        canonical_json(manifest.to_dict()) + "\n",
        encoding="utf-8",
    )
    repository.upsert_dataset(manifest.to_dict(), "READY")
    service = BacktestApplicationService(
        MockProvider(), repository=repository, catalog=catalog, workers=1
    )
    try:
        run, replayed = service.create_run(
            dataset_id=manifest.dataset_id,
            entry_strategy_ids=["legacy_gap_volume_vwap_entry_v1"],
            exit_strategy_ids=["take_profit_exit_v1", "end_of_day_exit_v1"],
            priority_order=[
                "take_profit_exit_v1",
                "end_of_day_exit_v1",
                "legacy_gap_volume_vwap_entry_v1",
            ],
            minimum_oos_trades=1,
            engine_version="backtest-engine-v3-tw",
            idempotency_key="formal-v3-bind-1",
        )
        config = run["config"]

        assert replayed is False
        assert set(config) >= {
            "execution_policy_snapshot",
            "cost_policy_snapshot",
            "research_truth_snapshot",
        }
        assert {key for key in config if key.endswith("_policy_snapshot")} == {
            "execution_policy_snapshot",
            "cost_policy_snapshot",
        }
        assert {key for key in config if key.endswith("truth_snapshot")} == {
            "research_truth_snapshot"
        }
        verify_execution_policy_snapshot(config["execution_policy_snapshot"])
        verify_cost_policy_snapshot(config["cost_policy_snapshot"])
        require_formal_research_truth(config["research_truth_snapshot"], manifest=manifest)
    finally:
        service.close()


def test_v3_run_creation_rejects_current_snapshot_before_queueing(tmp_path: Path) -> None:
    catalog_root = tmp_path / "datasets"
    catalog = HistoricalDatasetCatalog(catalog_root)
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    manifest = DatasetManifest.from_dict(_fixture("fail_current_snapshot_manifest.json"))
    dataset_root = catalog_root / manifest.dataset_id
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        canonical_json(manifest.to_dict()) + "\n",
        encoding="utf-8",
    )
    repository.upsert_dataset(manifest.to_dict(), "READY")
    service = BacktestApplicationService(
        MockProvider(), repository=repository, catalog=catalog, workers=1
    )
    try:
        with pytest.raises(ResearchTruthUnavailable, match="FORMAL_DATA_FAIL"):
            service.create_run(
                dataset_id=manifest.dataset_id,
                entry_strategy_ids=["legacy_gap_volume_vwap_entry_v1"],
                exit_strategy_ids=["end_of_day_exit_v1"],
                engine_version="backtest-engine-v3-tw",
                idempotency_key="formal-v3-current-snapshot-fail",
            )
        assert repository.list_runs() == []
    finally:
        service.close()


def test_v3_challenger_uses_server_derived_experiment_family(tmp_path: Path) -> None:
    catalog_root = tmp_path / "datasets"
    catalog = HistoricalDatasetCatalog(catalog_root)
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    base = catalog.create_imported_dataset(
        bars=_bars(),
        source="formal-family-fixture",
        universe_scope="DATE_EFFECTIVE",
        research_eligible=True,
    )
    manifest = _formal_manifest(base)
    (catalog_root / base.dataset_id / "manifest.json").write_text(
        canonical_json(manifest.to_dict()) + "\n",
        encoding="utf-8",
    )
    repository.upsert_dataset(manifest.to_dict(), "READY")
    baseline_config = BacktestRunConfig(
        dataset_id=manifest.dataset_id,
        dataset_digest=manifest.manifest_digest,
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("end_of_day_exit_v1",),
        ),
        engine_version="backtest-engine-v3-tw",
        execution_policy_snapshot=build_execution_policy_snapshot(
            participation_calibration_digest="a" * 64
        ),
        cost_policy_snapshot=build_cost_policy_snapshot(
            slippage_bps="5", slippage_calibration_digest="b" * 64
        ),
        research_truth_snapshot=build_research_truth_snapshot(manifest),
    )
    baseline = repository.create_run(
        {
            "run_id": "run-formal-v3-baseline",
            "idempotency_key": "formal-v3-baseline-create",
            "status": "QUEUED",
            "config": baseline_config.to_dict(),
            "config_digest": baseline_config.config_digest,
            "dataset_id": manifest.dataset_id,
            "dataset_digest": manifest.manifest_digest,
            "created_at": "2026-08-29T12:00:00+08:00",
        }
    )[0]
    repository.update_run(baseline["run_id"], status="COMPLETED")
    service = BacktestApplicationService(
        MockProvider(), repository=repository, catalog=catalog, workers=1
    )
    try:
        challenger, _ = service.create_run(
            dataset_id=manifest.dataset_id,
            entry_strategy_ids=["momentum_breakout_entry_v1"],
            exit_strategy_ids=["end_of_day_exit_v1"],
            engine_version="backtest-engine-v3-tw",
            baseline_run_id=baseline["run_id"],
            idempotency_key="formal-v3-challenger-create",
        )
        baseline_digest = research_baseline_identity_digest(baseline_config.to_dict())

        assert challenger["config"]["research_baseline_digest"] == baseline_digest
        assert challenger["config"]["experiment_id"] == experiment_family_id(baseline_digest)
    finally:
        service.close()
