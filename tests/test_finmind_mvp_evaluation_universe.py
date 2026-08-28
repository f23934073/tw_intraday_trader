"""Offline metadata-only coverage and MVP universe contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from backtest.finmind_snapshot import FinMindSnapshotPlan
from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.evaluation import (
    build_mvp_evaluation_universe,
    build_mvp_price_coverage_audit,
    verify_mvp_evaluation_universe,
    verify_mvp_price_coverage_audit,
)
from institutional_mvp.series import (
    InstitutionalMvpSeriesError,
    load_canonical_artifact,
    publish_content_addressed_json,
)
from scripts.build_finmind_mvp_evaluation_universe import _load_exact_batches


def _digest(value: object) -> str:
    return sha256_text(canonical_json(value))


def _with_identity(body: dict[str, object], prefix: str) -> dict[str, object]:
    digest = _digest(body)
    return {
        "artifact_digest": digest,
        "artifact_id": f"{prefix}-{digest[:20]}",
        **body,
    }


def _fixture() -> tuple[dict[str, object], FinMindSnapshotPlan, dict[str, object]]:
    sessions = tuple(
        (date(2026, 1, 1) + timedelta(days=index)).isoformat()
        for index in range(61)
    )
    symbols = tuple(f"S{index:03d}" for index in range(100))
    partitions: list[dict[str, object]] = []
    ready_count = 0
    empty_count = 0
    for symbol in symbols:
        for session_index, session in enumerate(sessions):
            status = "EMPTY" if symbol == "S099" and session_index == 0 else "READY"
            if status == "READY":
                ready_count += 1
            else:
                empty_count += 1
            partitions.append(
                {
                    "bar_count": 1 if status == "READY" else 0,
                    "canonical_sha256": _digest([symbol, session, status]),
                    "contributing_job_ids": ["job-1"],
                    "first_event_at": None,
                    "last_event_at": None,
                    "session_date": session,
                    "status": status,
                    "symbol": symbol,
                }
            )
    counts = {
        "bar_count": ready_count,
        "empty_partition_count": empty_count,
        "included_partition_count": len(partitions),
        "included_symbol_count": len(symbols),
        "ready_partition_count": ready_count,
    }
    identity = {
        "amount_contract": {"kind": "TEST"},
        "contributing_job_ids": ["job-1"],
        "counts": counts,
        "dataset_id": "dataset-test",
        "included_partitions": partitions,
        "issues": ["CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED"],
        "reference": {
            "dataset": "TaiwanStockInfo",
            "mapping": [
                {
                    "market": "TWSE" if index < 80 else "TPEX",
                    "name": symbol,
                    "symbol": symbol,
                }
                for index, symbol in enumerate(symbols)
            ],
            "mapping_contract": "FINMIND_CURRENT_LISTING_REFERENCE_V1",
            "raw_body_sha256": "1" * 64,
        },
        "research_eligible": False,
        "selection": {"included_symbols": list(symbols)},
        "snapshot_identity_at": "2026-03-01T00:00:00+08:00",
        "source_contract": {
            "end_date": sessions[-1],
            "source": "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
            "source_version": "FINMIND_API_V4",
            "start_date": sessions[0],
            "trading_dates": list(sessions),
        },
        "source_snapshot_digest": "2" * 64,
        "universe_scope": "CURRENT_SNAPSHOT",
        "volume_contract": {"unit": "COMMON_LOTS"},
    }
    selection = {
        "compatible_job_ids": ["job-1"],
        "excluded_jobs": [],
        "excluded_symbols": [
            {
                "extra_session_dates": [],
                "invalid_session_dates": [],
                "missing_session_dates": list(sessions),
                "reason_codes": ["MISSING_SESSION"],
                "symbol": "XEXC",
            }
        ],
        "included_symbols": list(symbols),
        "snapshot_counts": {**counts, "excluded_symbol_count": 1},
    }
    handoff = {"copied_sqlite_sha256": "3" * 64}
    operation = {"actor": "test"}
    snapshot_plan = FinMindSnapshotPlan(
        identity=identity,
        plan_identity_digest=_digest(identity),
        handoff_evidence=handoff,
        handoff_evidence_digest=_digest(handoff),
        selection_audit=selection,
        selection_audit_digest=_digest(selection),
        locators={},
        operation_audit=operation,
        operation_audit_digest=_digest(operation),
    )
    price_reference = {
        "bar_count": ready_count,
        "bars_sha256": "4" * 64,
        "dataset_id": "dataset-test",
        "end_date": sessions[-1],
        "issues": ["CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED"],
        "manifest_digest": "5" * 64,
        "observed_symbol_count": len(symbols),
        "payload_order": "TIMESTAMP_SYMBOL",
        "plan_identity_digest": snapshot_plan.plan_identity_digest,
        "profile": "KBAR_1M_V1",
        "research_eligible": False,
        "selection_audit_digest": snapshot_plan.selection_audit_digest,
        "source": "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        "source_snapshot_digest": identity["source_snapshot_digest"],
        "start_date": sessions[0],
        "storage_format": "JSONL_FULL_V1",
        "universe_scope": "CURRENT_SNAPSHOT",
        "universe_selection": "FINMIND_COMPLETE_SYMBOLS_V1",
    }
    batch_references = []
    for index, session in enumerate(sessions[1:]):
        candidates = [
            {
                "entry_digest": _digest([session, "S000"]),
                "market": "TWSE",
                "rank": 1,
                "symbol": "S000",
            },
            {
                "entry_digest": _digest([session, "X999"]),
                "market": "TPEX",
                "rank": 2,
                "symbol": "X999",
            },
        ]
        batch_references.append(
            {
                "artifact_digest": _digest(["batch", session]),
                "artifact_id": f"batch-{index}",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "source_session": (
                    date.fromisoformat(session) - timedelta(days=1)
                ).isoformat(),
                "target_session": session,
            }
        )
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
            "institutional_candidate_series_observation_allowed": True,
            "evaluation_universe_freeze_allowed": False,
            "outcome_generation_allowed": False,
            "holdout_execution_allowed": False,
            "runtime_strategy_binding_allowed": False,
            "order_submission_allowed": False,
        },
        "limitations": ["CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED"],
        "overlapping_target_session_count": 60,
        "price_dataset_reference": price_reference,
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": "institutional_mvp_candidate_series_v1",
        "series_plan_reference": {
            "artifact_digest": "8" * 64,
            "artifact_id": (
                f"finmind-institutional-mvp-series-plan-v1-{'8' * 20}"
            ),
            "source_sessions_digest": _digest(
                [item["source_session"] for item in batch_references]
            ),
            "target_sessions_digest": _digest(
                [item["target_session"] for item in batch_references]
            ),
        },
        "status": "MVP_INSTITUTIONAL_CANDIDATE_SERIES_OBSERVATION_ONLY",
    }
    series = _with_identity(
        series_body, "finmind-institutional-mvp-candidate-series-v1"
    )
    return price_reference, snapshot_plan, series


def test_coverage_audit_is_metadata_only_and_separates_formal_from_mvp() -> None:
    price_reference, snapshot_plan, series = _fixture()

    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    verify_mvp_price_coverage_audit(
        audit,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )

    assert audit["dataset_coverage"]["acquisition_target_symbol_count"] == 101
    assert audit["symbol_qualification"]["qualified_symbol_count"] == 99
    assert audit["symbol_qualification"]["numeric_gate_pass"] is True
    assert audit["candidate_join"]["included_membership_count"] == 60
    assert audit["candidate_join"]["excluded_membership_count"] == 60
    assert audit["execution_permissions"]["mvp_evaluation_universe_freeze_allowed"] is True
    assert audit["execution_permissions"]["formal_population_freeze_allowed"] is False
    assert audit["evidence_scope"]["price_or_kbar_value_read"] is False
    assert audit["evidence_scope"]["outcome_or_holdout_read"] is False


def test_universe_freeze_contains_only_exact_ready_membership() -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )

    universe = build_mvp_evaluation_universe(
        coverage_audit=audit,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    verify_mvp_evaluation_universe(
        universe,
        coverage_audit=audit,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )

    assert universe["membership_count"] == 60
    assert universe["symbol_count"] == 1
    assert universe["target_session_count"] == 60
    assert {item["symbol"] for item in universe["membership"]} == {"S000"}
    assert universe["research_eligibility"] == {
        "formal_pit_eligible": False,
        "research_eligible": False,
    }
    assert universe["execution_permissions"]["outcome_generation_allowed"] is False
    assert universe["execution_permissions"]["order_submission_allowed"] is False


def test_rehashed_permission_tamper_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    changed = deepcopy(audit)
    changed["execution_permissions"]["outcome_generation_allowed"] = True
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(body, "finmind-mvp-price-coverage-audit-v1")

    with pytest.raises(ValueError, match="differs from exact reconstruction"):
        verify_mvp_price_coverage_audit(
            changed,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=series,
        )


def test_blocked_audit_cannot_freeze_universe() -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    body = dict(audit)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    body["execution_permissions"] = dict(body["execution_permissions"])
    body["execution_permissions"]["mvp_evaluation_universe_freeze_allowed"] = False
    blocked = _with_identity(body, "finmind-mvp-price-coverage-audit-v1")

    with pytest.raises(ValueError, match="differs from exact reconstruction"):
        build_mvp_evaluation_universe(
            coverage_audit=blocked,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=series,
        )


def test_coverage_and_universe_artifacts_publish_idempotently(tmp_path: Path) -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    universe = build_mvp_evaluation_universe(
        coverage_audit=audit,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )

    audit_path, audit_created = publish_content_addressed_json(
        tmp_path, category="coverage_audits", payload=audit
    )
    universe_path, universe_created = publish_content_addressed_json(
        tmp_path, category="evaluation_universes", payload=universe
    )
    _, audit_replay_created = publish_content_addressed_json(
        tmp_path, category="coverage_audits", payload=audit
    )

    assert audit_created is True and universe_created is True
    assert audit_replay_created is False
    assert load_canonical_artifact(audit_path) == audit
    assert load_canonical_artifact(universe_path) == universe


def test_candidate_market_mismatch_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    changed = deepcopy(series)
    changed["batch_references"][0]["candidates"][0]["market"] = "TPEX"
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    with pytest.raises(ValueError, match="market mapping"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=changed,
        )


def test_candidate_series_count_drift_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    changed = deepcopy(series)
    changed["batch_count"] = 59
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    with pytest.raises(ValueError, match="batch count"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=changed,
        )


def test_overlapping_excluded_symbol_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    selection = deepcopy(snapshot_plan.selection_audit)
    selection["excluded_symbols"][0]["symbol"] = "S000"
    changed_plan = replace(
        snapshot_plan,
        selection_audit=selection,
        selection_audit_digest=_digest(selection),
    )

    with pytest.raises(ValueError, match="excluded symbol"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=changed_plan,
            candidate_series=series,
        )


def test_rehashed_arbitrary_audit_cannot_build_universe() -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    changed = deepcopy(audit)
    changed["issues"] = []
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(body, "finmind-mvp-price-coverage-audit-v1")

    with pytest.raises(ValueError, match="differs from exact reconstruction"):
        build_mvp_evaluation_universe(
            coverage_audit=changed,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=series,
        )


def test_rehashed_universe_membership_tamper_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    universe = build_mvp_evaluation_universe(
        coverage_audit=audit,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=series,
    )
    changed = deepcopy(universe)
    changed["limitations"] = []
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(body, "finmind-mvp-evaluation-universe-v1")

    with pytest.raises(ValueError, match="differs from exact audit membership"):
        verify_mvp_evaluation_universe(
            changed,
            coverage_audit=audit,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=series,
        )


def test_snapshot_research_boundary_drift_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    identity = deepcopy(snapshot_plan.identity)
    identity["research_eligible"] = True
    changed_plan = replace(
        snapshot_plan,
        identity=identity,
        plan_identity_digest=_digest(identity),
    )
    changed_reference = deepcopy(price_reference)
    changed_reference["plan_identity_digest"] = changed_plan.plan_identity_digest
    changed_series = deepcopy(series)
    changed_series["price_dataset_reference"] = changed_reference
    body = dict(changed_series)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed_series = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    with pytest.raises(ValueError, match="research boundary"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=changed_reference,
            snapshot_plan=changed_plan,
            candidate_series=changed_series,
        )


def test_candidate_sessions_must_follow_dataset_order() -> None:
    price_reference, snapshot_plan, series = _fixture()
    changed = deepcopy(series)
    first_target = date.fromisoformat(
        changed["batch_references"][0]["target_session"]
    )
    changed["batch_references"][0]["source_session"] = (
        first_target - timedelta(days=2)
    ).isoformat()
    changed["series_plan_reference"]["source_sessions_digest"] = _digest(
        [item["source_session"] for item in changed["batch_references"]]
    )
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    with pytest.raises(ValueError, match="Dataset session order"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=changed,
        )


def test_exact_batch_loader_rejects_path_escape(tmp_path: Path) -> None:
    series = {
        "batch_references": [
            {
                "artifact_digest": "a" * 64,
                "source_session": "2026-08-17",
                "target_session": "../../outside",
            }
        ]
    }

    with pytest.raises(ValueError, match="target_session"):
        _load_exact_batches(tmp_path, series)


def test_exact_batch_loader_rejects_symlinked_batch(tmp_path: Path) -> None:
    target = "2026-08-18"
    source = "2026-08-17"
    digest = "a" * 64
    directory = tmp_path / target / source
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    (directory / f"{digest}.json").symlink_to(outside)
    series = {
        "batch_references": [
            {
                "artifact_digest": digest,
                "source_session": source,
                "target_session": target,
            }
        ]
    }

    with pytest.raises((InstitutionalMvpSeriesError, OSError)):
        _load_exact_batches(tmp_path, series)


def test_exact_batch_loader_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstitutionalMvpSeriesError, match="symlink"):
        _load_exact_batches(linked_root, {"batch_references": []})


def test_candidate_series_permission_tamper_is_rejected() -> None:
    price_reference, snapshot_plan, series = _fixture()
    changed = deepcopy(series)
    changed["execution_permissions"]["outcome_generation_allowed"] = True
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    with pytest.raises(ValueError, match="authority"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=changed,
        )


def test_snapshot_selection_digest_must_match_price_reference() -> None:
    price_reference, snapshot_plan, series = _fixture()
    selection = deepcopy(snapshot_plan.selection_audit)
    selection["excluded_symbols"][0]["symbol"] = "XOTHER"
    changed_plan = replace(
        snapshot_plan,
        selection_audit=selection,
        selection_audit_digest=_digest(selection),
    )

    with pytest.raises(ValueError, match="binding drifted"):
        build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=changed_plan,
            candidate_series=series,
        )


def test_zero_candidate_series_yields_blocked_audit() -> None:
    price_reference, snapshot_plan, series = _fixture()
    changed = deepcopy(series)
    for batch in changed["batch_references"]:
        batch["candidate_count"] = 0
        batch["candidates"] = []
    body = dict(changed)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=changed,
    )

    assert audit["status"] == "BLOCKED"
    assert audit["candidate_join"]["candidate_observation_count"] == 0
    assert audit["candidate_join"]["status"] == "NO_CANDIDATE_OBSERVATIONS"
    assert (
        audit["execution_permissions"]["mvp_evaluation_universe_freeze_allowed"]
        is False
    )


def test_no_qualified_price_symbols_yields_blocked_audit() -> None:
    price_reference, snapshot_plan, series = _fixture()
    identity = deepcopy(snapshot_plan.identity)
    for partition in identity["included_partitions"]:
        partition["status"] = "EMPTY"
        partition["bar_count"] = 0
        partition["canonical_sha256"] = _digest(
            [partition["symbol"], partition["session_date"], "EMPTY"]
        )
    partition_count = len(identity["included_partitions"])
    identity["counts"] = {
        "bar_count": 0,
        "empty_partition_count": partition_count,
        "included_partition_count": partition_count,
        "included_symbol_count": len(identity["selection"]["included_symbols"]),
        "ready_partition_count": 0,
    }
    selection = deepcopy(snapshot_plan.selection_audit)
    selection["snapshot_counts"] = {
        **identity["counts"],
        "excluded_symbol_count": len(selection["excluded_symbols"]),
    }
    changed_plan = replace(
        snapshot_plan,
        identity=identity,
        plan_identity_digest=_digest(identity),
        selection_audit=selection,
        selection_audit_digest=_digest(selection),
    )
    changed_reference = deepcopy(price_reference)
    changed_reference["bar_count"] = 0
    changed_reference["plan_identity_digest"] = changed_plan.plan_identity_digest
    changed_reference["selection_audit_digest"] = changed_plan.selection_audit_digest
    changed_series = deepcopy(series)
    changed_series["price_dataset_reference"] = changed_reference
    body = dict(changed_series)
    body.pop("artifact_digest")
    body.pop("artifact_id")
    changed_series = _with_identity(
        body, "finmind-institutional-mvp-candidate-series-v1"
    )

    audit = build_mvp_price_coverage_audit(
        price_dataset_reference=changed_reference,
        snapshot_plan=changed_plan,
        candidate_series=changed_series,
    )

    assert audit["status"] == "BLOCKED"
    assert audit["symbol_qualification"]["qualified_symbol_count"] == 0
    assert audit["symbol_qualification"]["aggregate_session_coverage_rate"] == (
        "0.000000000000"
    )
