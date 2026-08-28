"""Focused tests for the frozen-input non-formal institutional A/B diagnostic."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import HistoricalBar
from backtest.engine import HistoricalBacktestEngine
from backtest.finmind_snapshot import FinMindSnapshotPlan
from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.diagnostic import (
    FrozenCatalogBarView,
    InstitutionalMvpDiagnosticError,
    build_offline_ab_plan,
    build_offline_ab_result,
    build_run_config,
    institutional_entry_eligibility,
    price_only_entry_eligibility,
    source_code_identities,
    verify_offline_ab_plan,
    verify_offline_ab_result,
)
from institutional_mvp.series import (
    dataset_reference,
    load_canonical_artifact,
    publish_content_addressed_json,
)


TAIPEI = ZoneInfo("Asia/Taipei")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _digest(value: object) -> str:
    return sha256_text(canonical_json(value))


def _identity(body: dict[str, object], prefix: str) -> dict[str, object]:
    digest = _digest(body)
    return {
        "artifact_digest": digest,
        "artifact_id": f"{prefix}-{digest[:20]}",
        **body,
    }


def _sessions() -> list[date]:
    values: list[date] = []
    cursor = date(2026, 5, 22)
    while len(values) < 61:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor += timedelta(days=1)
    return values


def _bars(sessions: list[date]) -> list[HistoricalBar]:
    output: list[HistoricalBar] = []
    prior_close = {"S000": Decimal("100"), "S001": Decimal("80")}
    for session in sessions:
        for symbol, market in (("S000", "TWSE"), ("S001", "TPEX")):
            opened = prior_close[symbol] * Decimal("1.03")
            values = (
                (9, 0, opened, opened, opened, opened),
                (9, 1, opened, opened + 2, opened, opened + 2),
                (13, 29, opened + 2, opened + 3, opened + 1, opened + 2),
                (13, 30, opened + 2, opened + 3, opened + 1, opened + 2),
            )
            for hour, minute, opened_bar, high, low, close in values:
                output.append(
                    HistoricalBar(
                        symbol=symbol,
                        name=symbol,
                        market=market,
                        timestamp=datetime(
                            session.year,
                            session.month,
                            session.day,
                            hour,
                            minute,
                            tzinfo=TAIPEI,
                        ),
                        open=opened_bar,
                        high=high,
                        low=low,
                        close=close,
                        volume=100_000,
                        amount=close * 100_000,
                        session_date=session,
                    )
                )
            prior_close[symbol] = opened + 2
    return output


def _fixture(tmp_path: Path) -> dict[str, object]:
    sessions = _sessions()
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    bars = _bars(sessions)
    manifest = catalog.create_imported_dataset(
        bars=bars,
        source="FINMIND_TEST_FIXTURE",
        universe_scope="CURRENT_SNAPSHOT",
        research_eligible=False,
        issues=("CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",),
    )
    symbols = ["S000", "S001"]
    partitions = []
    by_key: dict[tuple[str, str], list[HistoricalBar]] = {}
    for bar in bars:
        by_key.setdefault((bar.symbol, bar.session_date.isoformat()), []).append(bar)
    for symbol in symbols:
        for session in sessions:
            selected = by_key[(symbol, session.isoformat())]
            partitions.append(
                {
                    "bar_count": len(selected),
                    "canonical_sha256": _digest(
                        [bar.to_dict() for bar in selected]
                    ),
                    "contributing_job_ids": ["job-test"],
                    "first_event_at": selected[0].timestamp.isoformat(),
                    "last_event_at": selected[-1].timestamp.isoformat(),
                    "session_date": session.isoformat(),
                    "status": "READY",
                    "symbol": symbol,
                }
            )
    counts = {
        "bar_count": len(bars),
        "empty_partition_count": 0,
        "included_partition_count": len(partitions),
        "included_symbol_count": len(symbols),
        "ready_partition_count": len(partitions),
    }
    selection = {
        "compatible_job_ids": ["job-test"],
        "excluded_jobs": [],
        "excluded_symbols": [],
        "included_symbols": symbols,
        "snapshot_counts": {**counts, "excluded_symbol_count": 0},
    }
    amount_body = {
        "is_actual_turnover": False,
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
    }
    identity = {
        "amount_contract": {
            "digest": _digest(amount_body),
            **amount_body,
        },
        "contributing_job_ids": ["job-test"],
        "counts": counts,
        "dataset_id": manifest.dataset_id,
        "included_partitions": partitions,
        "issues": list(manifest.issues),
        "reference": {
            "dataset": "TaiwanStockInfo",
            "mapping": [
                {"market": "TWSE", "name": "S000", "symbol": "S000"},
                {"market": "TPEX", "name": "S001", "symbol": "S001"},
            ],
            "mapping_contract": "FINMIND_CURRENT_LISTING_REFERENCE_V1",
            "raw_body_sha256": "b" * 64,
        },
        "research_eligible": False,
        "selection": {"included_symbols": symbols},
        "snapshot_identity_at": "2026-08-18T20:00:00+08:00",
        "source_contract": {
            "end_date": sessions[-1].isoformat(),
            "source": manifest.source,
            "source_version": "TEST_V1",
            "start_date": sessions[0].isoformat(),
            "trading_dates": [session.isoformat() for session in sessions],
        },
        "source_snapshot_digest": "c" * 64,
        "universe_scope": "CURRENT_SNAPSHOT",
        "volume_contract": {"unit": "COMMON_LOTS"},
    }
    snapshot_plan = FinMindSnapshotPlan(
        identity=identity,
        plan_identity_digest=_digest(identity),
        handoff_evidence={"kind": "TEST"},
        handoff_evidence_digest=_digest({"kind": "TEST"}),
        selection_audit=selection,
        selection_audit_digest=_digest(selection),
        locators={},
        operation_audit={"kind": "TEST"},
        operation_audit_digest=_digest({"kind": "TEST"}),
    )
    projected_manifest = replace(
        manifest,
        source_snapshot_digest=identity["source_snapshot_digest"],
        plan_identity_digest=snapshot_plan.plan_identity_digest,
        universe_selection="FINMIND_COMPLETE_SYMBOLS_V1",
        profile="KBAR_1M_V1",
        capabilities=(
            "OHLCV",
            "KBAR_INTRADAY",
            "SESSION_BOUNDARIES",
            "KBAR_1M",
        ),
    )
    price_reference = dataset_reference(
        projected_manifest.to_dict(),
        selection_audit_digest=snapshot_plan.selection_audit_digest,
    )
    batch_references = []
    membership = []
    for index, (source, target) in enumerate(zip(sessions, sessions[1:])):
        symbol = symbols[index % 2]
        candidate = {
            "entry_digest": _digest([target.isoformat(), symbol]),
            "market": "TWSE" if symbol == "S000" else "TPEX",
            "rank": 1,
            "symbol": symbol,
        }
        batch_digest = _digest([source.isoformat(), target.isoformat()])
        batch_references.append(
            {
                "artifact_digest": batch_digest,
                "artifact_id": f"batch-{index}",
                "candidate_count": 1,
                "candidates": [candidate],
                "source_session": source.isoformat(),
                "target_session": target.isoformat(),
            }
        )
        membership.append(
            {
                "candidate_batch_digest": batch_digest,
                "candidate_entry_digest": candidate["entry_digest"],
                "price_partition_digest": next(
                    row["canonical_sha256"]
                    for row in partitions
                    if row["symbol"] == symbol
                    and row["session_date"] == target.isoformat()
                ),
                "source_session": source.isoformat(),
                "symbol": symbol,
                "target_session": target.isoformat(),
            }
        )
    source_sessions = [row["source_session"] for row in batch_references]
    target_sessions = [row["target_session"] for row in batch_references]
    series_body = {
        "batch_count": 60,
        "batch_references": batch_references,
        "change_policy": "IMMUTABLE_APPEND_ONLY_REVISIONS",
        "evidence_scope": {
            "backtest_or_holdout_read": False,
            "institutional_flow_fields_read": True,
            "price_or_kbar_read": False,
            "return_or_pnl_read": False,
        },
        "execution_permissions": {
            "evaluation_universe_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "institutional_candidate_series_observation_allowed": True,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "runtime_strategy_binding_allowed": False,
        },
        "overlapping_target_session_count": 60,
        "price_dataset_reference": price_reference,
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": "institutional_mvp_candidate_series_v1",
        "series_plan_reference": {
            "artifact_digest": "d" * 64,
            "artifact_id": f"finmind-institutional-mvp-series-plan-v1-{'d' * 20}",
            "source_sessions_digest": _digest(source_sessions),
            "target_sessions_digest": _digest(target_sessions),
        },
        "status": "MVP_INSTITUTIONAL_CANDIDATE_SERIES_OBSERVATION_ONLY",
    }
    series = _identity(
        series_body, "finmind-institutional-mvp-candidate-series-v1"
    )
    qualification = {
        "qualified_symbol_count": 2,
        "qualified_symbol_digest": _digest(tuple(symbols)),
    }
    coverage_body = {
        "candidate_series_reference": {
            "artifact_digest": series["artifact_digest"],
            "artifact_id": series["artifact_id"],
        },
        "execution_permissions": {
            "formal_population_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "mvp_evaluation_universe_freeze_allowed": True,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "runtime_strategy_binding_allowed": False,
        },
        "price_dataset_reference": price_reference,
        "schema_version": "finmind_mvp_price_coverage_audit_v1",
        "status": "PASS_FOR_NON_FORMAL_MVP_FREEZE_ONLY",
        "symbol_qualification": qualification,
    }
    coverage = _identity(
        coverage_body, "finmind-mvp-price-coverage-audit-v1"
    )
    universe_body = {
        "coverage_audit_reference": {
            "artifact_digest": coverage["artifact_digest"],
            "artifact_id": coverage["artifact_id"],
        },
        "execution_permissions": {
            "formal_population_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "mvp_universe_observation_allowed": True,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "production_allowed": False,
            "runtime_strategy_binding_allowed": False,
        },
        "membership": membership,
        "membership_count": len(membership),
        "membership_digest": _digest(membership),
        "price_dataset_reference": price_reference,
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": "mvp_evaluation_universe_v1",
        "status": "FROZEN_NON_FORMAL_MVP",
    }
    universe = _identity(universe_body, "finmind-mvp-evaluation-universe-v1")
    formal_protocol = json.loads(
        (PROJECT_ROOT / "research/institutional_evaluation/protocols/formal_evaluation_gate_v1.json").read_text()
    )
    dependencies = {
        "price_dataset_reference": price_reference,
        "dataset_manifest": projected_manifest,
        "snapshot_plan": snapshot_plan,
        "candidate_series": series,
        "coverage_audit": coverage,
        "evaluation_universe": universe,
        "formal_protocol": formal_protocol,
        "code_identities": source_code_identities(PROJECT_ROOT),
    }
    return {
        "catalog": catalog,
        "dependencies": dependencies,
        "universe": universe,
    }


def test_plan_freezes_one_outer_filter_difference_and_no_formal_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    dependencies = fixture["dependencies"]
    plan = build_offline_ab_plan(**dependencies)
    verify_offline_ab_plan(plan, **dependencies)

    assert plan["membership"]["target_session_count"] == 60
    assert plan["bar_view"]["context_session_count"] == 61
    assert plan["bar_view"]["expected_bar_count"] == 488
    assert plan["comparison_contract"]["only_permitted_arm_difference"] == (
        "ENTRY_ELIGIBILITY_PREDICATE"
    )
    assert plan["execution_permissions"] == {
        "formal_outcome_generation_allowed": False,
        "holdout_execution_allowed": False,
        "non_formal_offline_ab_execution_allowed": True,
        "order_submission_allowed": False,
        "production_allowed": False,
        "provider_call_allowed": False,
        "runtime_strategy_binding_allowed": False,
    }


def test_rehashed_permission_tamper_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    dependencies = fixture["dependencies"]
    plan = build_offline_ab_plan(**dependencies)
    changed = deepcopy(plan)
    changed["execution_permissions"]["holdout_execution_allowed"] = True
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _identity(body, "institutional-mvp-offline-ab-plan-v1")

    with pytest.raises(InstitutionalMvpDiagnosticError, match="authority"):
        verify_offline_ab_plan(changed, **dependencies)


def test_catalog_view_and_two_arm_result_are_exact_and_non_formal(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    dependencies = fixture["dependencies"]
    universe = fixture["universe"]
    plan = build_offline_ab_plan(**dependencies)
    view = FrozenCatalogBarView(fixture["catalog"], plan)
    config = build_run_config(plan)
    engine = HistoricalBacktestEngine()
    price = engine.run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=price_only_entry_eligibility(plan),
    )
    institutional = engine.run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=institutional_entry_eligibility(plan, universe),
    )
    result = build_offline_ab_result(
        plan=plan,
        evaluation_universe=universe,
        price_only_result=price,
        institutional_result=institutional,
    )
    verify_offline_ab_result(
        result,
        plan=plan,
        evaluation_universe=universe,
        price_only_result=price,
        institutional_result=institutional,
    )

    assert result["status"] == "NON_FORMAL_MVP_OBSERVATION_ONLY"
    assert result["arms"]["price_only"]["closed_trade_count"] > result["arms"][
        "institutional_filter"
    ]["closed_trade_count"]
    assert result["execution_permissions"]["holdout_execution_allowed"] is False
    assert result["execution_permissions"]["order_submission_allowed"] is False
    assert result["comparison"]["interpretation"] == (
        "OBSERVED_ASSOCIATION_ONLY_NO_FORMAL_INFERENCE"
    )

    changed_universe = deepcopy(universe)
    changed_universe["membership"] = changed_universe["membership"][:-1]
    changed_universe["membership_count"] = len(changed_universe["membership"])
    changed_universe["membership_digest"] = _digest(
        changed_universe["membership"]
    )
    changed_body = dict(changed_universe)
    changed_body.pop("artifact_digest")
    changed_body.pop("artifact_id")
    changed_universe = _identity(
        changed_body, "finmind-mvp-evaluation-universe-v1"
    )
    with pytest.raises(InstitutionalMvpDiagnosticError, match="result universe"):
        build_offline_ab_result(
            plan=plan,
            evaluation_universe=changed_universe,
            price_only_result=price,
            institutional_result=institutional,
        )

    unresolved_price = deepcopy(price)
    unresolved_price.unresolved_positions.append({"symbol": "S000"})
    with pytest.raises(
        InstitutionalMvpDiagnosticError, match="unresolved positions"
    ):
        build_offline_ab_result(
            plan=plan,
            evaluation_universe=universe,
            price_only_result=unresolved_price,
            institutional_result=institutional,
        )


def test_plan_and_result_publish_append_only(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "fixture")
    dependencies = fixture["dependencies"]
    universe = fixture["universe"]
    plan = build_offline_ab_plan(**dependencies)
    view = FrozenCatalogBarView(fixture["catalog"], plan)
    config = build_run_config(plan)
    price = HistoricalBacktestEngine().run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=price_only_entry_eligibility(plan),
    )
    institutional = HistoricalBacktestEngine().run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=institutional_entry_eligibility(plan, universe),
    )
    result = build_offline_ab_result(
        plan=plan,
        evaluation_universe=universe,
        price_only_result=price,
        institutional_result=institutional,
    )

    plan_path, plan_created = publish_content_addressed_json(
        tmp_path / "artifacts", category="diagnostic_plans", payload=plan
    )
    result_path, result_created = publish_content_addressed_json(
        tmp_path / "artifacts", category="diagnostic_results", payload=result
    )
    _, plan_replay_created = publish_content_addressed_json(
        tmp_path / "artifacts", category="diagnostic_plans", payload=plan
    )

    assert plan_created is True and result_created is True
    assert plan_replay_created is False
    assert load_canonical_artifact(plan_path) == plan
    assert load_canonical_artifact(result_path) == result
