from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import (
    BacktestRunConfig,
    HistoricalBar,
    RunStatus,
    StrategySetSnapshot,
    canonical_json,
    digest,
)
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.research_control import (
    CONTROL_CONTRACT_VERSION as V1_CONTROL_CONTRACT_VERSION,
    build_cash_admission_postflight,
    build_cash_admission_preflight,
    build_research_control_snapshot,
    entry_signal_multiplicity_digest,
    recompute_backtest_result_digest,
)
from backtest.research_replay.application import (
    REQUEST_SCHEMA_VERSION,
    SignalReplayApplicationService,
    SignalReplayConflict,
    SignalReplayNotAccepted,
)
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.domain import (
    CONTROL_CONTRACT_VERSION,
    ObservedBar,
    ResearchReplayIntegrityError,
    build_ledger,
    build_ledger_manifest,
    build_match_manifest,
    build_match_plan,
    build_order_derivation,
    build_postflight,
    build_replay,
    build_result_manifest,
)
from backtest.research_replay.postgres_repository import (
    SignalReplayPostgresRepository,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _decision(index: int, symbol: str) -> dict[str, object]:
    return {
        "decision_id": f"decision-{index}",
        "symbol": symbol,
        "side": "ENTRY",
        "event_at": "2026-08-21T09:01:00+08:00",
        "policy": "ANY",
        "triggered_strategy_ids": ["above_vwap_entry_v1"],
        "primary_strategy_id": "above_vwap_entry_v1",
        "evaluations": [],
        "execution_horizon": "INTRADAY_NEXT_BAR",
    }


def _order(decision: dict[str, object], index: int) -> dict[str, object]:
    return {
        "order_id": f"order-{index}",
        "decision_id": decision["decision_id"],
        "symbol": decision["symbol"],
        "side": "ENTRY",
        "status": "FILLED",
        "reason": "下一根 Kbar 開盤成交",
        "created_at": decision["event_at"],
        "execution_horizon": "INTRADAY_NEXT_BAR",
        "primary_strategy_id": decision["primary_strategy_id"],
        "triggered_strategy_ids": decision["triggered_strategy_ids"],
        "shares": 1000,
        "fill": None,
        "filled_at": "2026-08-21T09:02:00+08:00",
    }


def _request(preflight_digest: str, *, note: str = "seal R5 v2 replay"):
    return {
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "preflight_digest": preflight_digest,
        "expected_registration_revision": 0,
        "actor_id": "local-researcher",
        "change_note": note,
    }


def _setup(
    postgres_test_connection,
    tmp_path: Path,
):
    backtests = PostgresBacktestRepository(postgres_test_connection)
    bars_by_symbol: list[list[HistoricalBar]] = []
    for symbol, name, entry, closing in (
        ("2317", "鴻海", "100", "110"),
        ("2330", "台積電", "100", "90"),
    ):
        bars_by_symbol.append(
            [
                HistoricalBar(
                    symbol=symbol,
                    timestamp=datetime(2026, 8, 21, 9, minute, tzinfo=_TAIPEI),
                    session_date=datetime(2026, 8, 21).date(),
                    open=Decimal(price),
                    high=Decimal(price),
                    low=Decimal(price),
                    close=Decimal(price),
                    volume=100,
                    name=name,
                    market="TWSE",
                )
                for minute, price in ((2, entry), (3, closing))
            ]
        )
    catalog = HistoricalDatasetCatalog(tmp_path / "dataset")
    source_digest = digest({"source": "r5-v2-postgres-test"})
    dataset_id = f"dataset-finmind-sponsor-sha256-{source_digest}"
    amount_contract: dict[str, object] = {
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "is_actual_turnover": False,
        "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
    }
    amount_contract["digest"] = digest(amount_contract)
    plan_identity = {
        "dataset_id": dataset_id,
        "source_snapshot_digest": source_digest,
    }
    manifest = catalog.create_finmind_snapshot_dataset(
        dataset_id=dataset_id,
        symbol_streams=bars_by_symbol,
        created_at=datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI),
        source="FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        requested_symbols=("2317", "2330"),
        expected_bar_count=4,
        start_date="2026-08-21",
        end_date="2026-08-21",
        issues=("AMOUNT_DERIVED_PROXY",),
        volume_contract={"unit": "COMMON_LOTS"},
        amount_contract=amount_contract,
        source_snapshot_digest=source_digest,
        plan_identity=plan_identity,
        plan_identity_digest=digest(plan_identity),
    )
    backtests.register_immutable_dataset(manifest.to_dict())
    strategy_set = StrategySetSnapshot(
        entry_strategy_ids=("above_vwap_entry_v1",),
        exit_strategy_ids=("end_of_day_exit_v1",),
    )
    atomic_body = {
        "contract_version": "atomic-backtest-run-snapshot-v2",
        "strategy_set": {"strategy_set_version_id": "set-vwap"},
        "feature_adapter_identity": {"adapter": "test"},
    }
    atomic_snapshot = {**atomic_body, "snapshot_digest": digest(atomic_body)}
    binding_snapshot = {
        "binding_name": "ATOMIC_BACKTEST_DEFAULT",
        "revision": 1,
        "dataset_id": dataset_id,
        "dataset_digest": manifest.manifest_digest,
    }
    config = BacktestRunConfig(
        dataset_id=dataset_id,
        dataset_digest=manifest.manifest_digest,
        strategy_set=strategy_set,
        starting_cash="10000000",
        position_fraction="0.10",
        commission_rate="0.001425",
        sell_tax_rate="0.003",
        slippage_bps="5",
        engine_version="backtest-engine-v2",
        atomic_strategy_run_snapshot=atomic_snapshot,
        dataset_binding_snapshot=binding_snapshot,
        dataset_amount_contract=amount_contract,
    )
    decisions = [_decision(1, "2317"), _decision(2, "2330")]
    orders = [_order(decision, index) for index, decision in enumerate(decisions, 1)]
    result: dict[str, object] = {
        "decisions": decisions,
        "fills": [],
        "trades": [],
        "orders": orders,
        "daily_equity": [],
        "strategy_counts": {},
        "unresolved_positions": [],
        "summary": {"verdict": "INSUFFICIENT_EVIDENCE"},
    }
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    baseline, _ = backtests.create_run(
        {
            "run_id": "run-baseline-r5-v2",
            "idempotency_key": "baseline-r5-v2-create",
            "status": RunStatus.RUNNING.value,
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": dataset_id,
            "dataset_digest": manifest.manifest_digest,
            "created_at": "2026-08-25T09:00:00+08:00",
        }
    )
    backtests.save_result(baseline["run_id"], result)
    baseline = backtests.update_run(
        baseline["run_id"],
        status=RunStatus.COMPLETED.value,
        result_digest=result["summary"]["result_digest"],
        progress=1.0,
        progress_message="complete",
    )
    signal_digest = entry_signal_multiplicity_digest(orders)
    v1_identity = {
        "baseline_run_id": baseline["run_id"],
        "baseline_config_digest": baseline["config_digest"],
        "baseline_result_digest": baseline["result_digest"],
        "dataset_id": dataset_id,
        "dataset_digest": manifest.manifest_digest,
        "dataset_manifest_digest": manifest.manifest_digest,
        "dataset_bars_sha256": manifest.bars_sha256,
        "dataset_binding_revision": 1,
        "strategy_set_snapshot_digest": digest(config.strategy_set.to_dict()),
        "atomic_strategy_run_snapshot_digest": atomic_snapshot["snapshot_digest"],
        "dataset_amount_contract_digest": digest(amount_contract),
        "engine_version": config.engine_version,
        "commission_rate": str(config.commission_rate),
        "sell_tax_rate": str(config.sell_tax_rate),
        "slippage_bps": str(config.slippage_bps),
        "min_lot_shares": config.min_lot_shares,
    }
    v1_preflight = build_cash_admission_preflight(
        identity=v1_identity,
        s_max=2,
        p_max="100",
        candidate_order_count=2,
        matched_next_bar_count=2,
        missing_next_bar_count=0,
        baseline_signal_multiplicity_digest=signal_digest,
    )
    control, _ = backtests.create_run(
        {
            "run_id": "run-invalid-r5-v1-control",
            "idempotency_key": "invalid-r5-v1-control",
            "status": "INVALID_CASH_ADMISSION_CONTROL",
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": dataset_id,
            "dataset_digest": manifest.manifest_digest,
            "created_at": "2026-08-25T09:01:00+08:00",
        }
    )
    control_snapshot = build_research_control_snapshot(
        preflight=v1_preflight,
        actor_id="reviewer",
        change_note="invalid v1 control",
        created_at="2026-08-25T09:01:00+08:00",
    )
    v1_postflight = build_cash_admission_postflight(
        baseline_orders=orders,
        control_result={"orders": [], "fills": []},
        preflight=v1_preflight,
        control_run_id=control["run_id"],
        control_config_digest=control["config_digest"],
        control_result_digest="f" * 64,
        identity_validation_digest="e" * 64,
    )
    assert v1_postflight["verdict"] == "INVALID"
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO backtest.backtest_cash_admission_control_heads (
                baseline_run_id, contract_version, current_revision, status
            ) VALUES (%s, %s, 1, 'INVALID')
            """,
            (baseline["run_id"], V1_CONTROL_CONTRACT_VERSION),
        )
        cursor.execute(
            """
            INSERT INTO backtest.backtest_cash_admission_control_registrations (
                baseline_run_id, contract_version, revision, control_run_id,
                preflight_digest, preflight_json, sizing_digest, sizing_json,
                research_control_snapshot_digest,
                research_control_snapshot_json, status, actor_id, change_note,
                postflight_digest, postflight_json
            ) VALUES (
                %s, %s, 1, %s, %s, %s::jsonb, %s, %s::jsonb,
                %s, %s::jsonb, 'INVALID', 'reviewer', 'invalid v1 control',
                %s, %s::jsonb
            )
            """,
            (
                baseline["run_id"],
                V1_CONTROL_CONTRACT_VERSION,
                control["run_id"],
                v1_preflight["artifact_digest"],
                canonical_json(v1_preflight),
                digest(v1_preflight["sizing"]),
                canonical_json(v1_preflight["sizing"]),
                control_snapshot["snapshot_digest"],
                canonical_json(control_snapshot),
                v1_postflight["postflight_digest"],
                canonical_json(v1_postflight),
            ),
        )
    postgres_test_connection.commit()

    ledger = build_ledger(baseline_run_id=baseline["run_id"], decisions=decisions)
    derivation = build_order_derivation(ledger_rows=ledger.rows, orders=orders)
    ledger_identity = {
        "baseline_run_id": baseline["run_id"],
        "baseline_config_digest": baseline["config_digest"],
        "baseline_result_digest": baseline["result_digest"],
        "v1_preflight_digest": v1_preflight["artifact_digest"],
        "v1_signal_multiplicity_digest": signal_digest,
        "v1_invalid_postflight_digest": v1_postflight["postflight_digest"],
        "atomic_strategy_run_snapshot_digest": atomic_snapshot["snapshot_digest"],
        "dataset_id": dataset_id,
        "dataset_digest": manifest.manifest_digest,
        "dataset_manifest_digest": manifest.manifest_digest,
        "dataset_bars_sha256": manifest.bars_sha256,
        "dataset_binding_revision": 1,
        "dataset_amount_contract_digest": digest(amount_contract),
    }
    ledger_manifest = build_ledger_manifest(
        identity=ledger_identity, ledger=ledger, order_derivation=derivation
    )
    observed = [
        ObservedBar.from_historical_bar(
            bar, source_json=canonical_json(bar.to_dict()).encode("utf-8")
        )
        for stream in bars_by_symbol
        for bar in stream
    ]
    observed.sort(key=lambda item: (item.timestamp, item.symbol))
    match = build_match_plan(ledger_rows=ledger.rows, bars=observed)
    match_manifest = build_match_manifest(
        ledger_manifest=ledger_manifest, match_plan=match
    )
    artifacts = ReplayArtifactStore(tmp_path / "replays")
    artifacts.publish_ledger(
        manifest=ledger_manifest,
        ledger_rows=ledger.rows,
        order_rows=derivation.rows,
    )
    artifacts.publish_match_plan(manifest=match_manifest, match_rows=match.rows)
    replay_repository = SignalReplayPostgresRepository(postgres_test_connection)
    service = SignalReplayApplicationService(
        repository=replay_repository, artifacts=artifacts
    )
    return {
        "backtests": backtests,
        "repository": replay_repository,
        "service": service,
        "artifacts": artifacts,
        "baseline": baseline,
        "ledger": ledger,
        "derivation": derivation,
        "ledger_manifest": ledger_manifest,
        "match": match,
        "match_manifest": match_manifest,
        "config": config,
    }


def _create(context, key="replay-create-key-0001", note="seal R5 v2 replay"):
    return context["service"].create_replay(
        baseline_run_id=context["baseline"]["run_id"],
        idempotency_key=key,
        request=_request(
            context["match_manifest"]["match_plan_manifest_digest"], note=note
        ),
    )


def test_g3_preflight_evidence_read_is_repeatable_and_creates_no_replay_state(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)

    evidence = context["repository"].load_preflight_evidence(
        context["baseline"]["run_id"]
    )

    assert evidence.identity["baseline_run_id"] == context["baseline"]["run_id"]
    assert evidence.dataset_manifest["dataset_id"] == context["config"].dataset_id
    assert evidence.ledger.rows == context["ledger"].rows
    assert evidence.order_derivation.rows == context["derivation"].rows
    with postgres_test_connection.cursor() as cursor:
        for table in (
            "r5_signal_ledger_replay_heads",
            "r5_signal_ledger_replay_registrations",
            "r5_signal_ledger_replay_operations",
            "r5_signal_ledger_replay_results",
            "r5_signal_ledger_replay_result_chunks",
        ):
            cursor.execute(f"SELECT COUNT(*) FROM backtest.{table}")
            assert cursor.fetchone()[0] == 0


def test_postgresql_replay_and_different_key_noop_are_durable(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)

    first, first_replay = _create(context)
    same, same_replay = _create(context)
    other, other_replay = _create(context, key="replay-create-key-0002")

    assert first_replay is False
    assert same_replay is True
    assert other_replay is True
    assert first == same == other
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_heads")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_registrations"
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_operations"
        )
        assert cursor.fetchone()[0] == 2


def test_postgresql_same_key_different_digest_conflicts(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    _create(context)

    with pytest.raises(SignalReplayConflict, match="request 不同"):
        _create(context, note="changed request")


def test_cancelling_status_cannot_be_overwritten_by_worker(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    created, _ = _create(context)
    replay_id = created["replay_id"]
    context["service"].start_replay(replay_id)
    context["service"].cancel_replay(replay_id)

    with pytest.raises(SignalReplayConflict, match="STATUS_CONFLICT"):
        context["service"].mark_failed(
            replay_id, progress="0.5", error_message="late worker failure"
        )

    assert context["service"].get_replay(replay_id)["status"] == "CANCELLING"


def test_baseline_config_drift_blocks_replay_read(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    created, _ = _create(context)
    drifted = dict(context["baseline"]["config"])
    drifted["commission_rate"] = "0.9"
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.backtest_runs
            SET config_json = %s::jsonb, config_digest = %s
            WHERE run_id = %s
            """,
            (
                canonical_json(drifted),
                digest(drifted),
                context["baseline"]["run_id"],
            ),
        )
    postgres_test_connection.commit()

    with pytest.raises(ResearchReplayIntegrityError, match="v1 preflight"):
        context["service"].get_replay(created["replay_id"])


def test_response_loss_replay_precedes_current_baseline_revalidation(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    first, _ = _create(context)
    drifted = dict(context["baseline"]["config"])
    drifted["commission_rate"] = "0.9"
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.backtest_runs
            SET config_json = %s::jsonb, config_digest = %s
            WHERE run_id = %s
            """,
            (
                canonical_json(drifted),
                digest(drifted),
                context["baseline"]["run_id"],
            ),
        )
    postgres_test_connection.commit()

    replayed, was_replayed = _create(context)

    assert was_replayed is True
    assert replayed == first
    with pytest.raises(ResearchReplayIntegrityError, match="v1 preflight"):
        _create(context, key="replay-create-key-0002")


@pytest.mark.parametrize(
    "foreign_projection",
    (
        {"baseline_run_id": "run-foreign-baseline"},
        {"preflight_digest": "e" * 64},
        {"replay_id": "replay-foreign"},
        {"revision": 2},
        {"ledger_manifest_digest": "f" * 64},
    ),
    ids=("baseline", "preflight", "replay", "head-revision", "ledger"),
)
def test_operation_replay_result_is_bound_to_authoritative_scope(
    postgres_test_connection, tmp_path, foreign_projection
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    first, _ = _create(context)
    tampered = {**first, **foreign_projection}
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.r5_signal_ledger_replay_operations
            SET result_json = %s::jsonb, result_digest = %s
            WHERE baseline_run_id = %s AND idempotency_key = %s
            """,
            (
                canonical_json(tampered),
                digest(tampered),
                context["baseline"]["run_id"],
                "replay-create-key-0001",
            ),
        )
    postgres_test_connection.commit()

    with pytest.raises(ResearchReplayIntegrityError, match="operation result scope"):
        _create(context)


def test_operation_replay_revision_rejects_numeric_alias(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    first, _ = _create(context)
    tampered = {**first, "revision": 1.0}
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.r5_signal_ledger_replay_operations
            SET result_json = %s::jsonb, result_digest = %s
            WHERE baseline_run_id = %s AND idempotency_key = %s
            """,
            (
                canonical_json(tampered),
                digest(tampered),
                context["baseline"]["run_id"],
                "replay-create-key-0001",
            ),
        )
    postgres_test_connection.commit()

    with pytest.raises(ResearchReplayIntegrityError, match="revision"):
        _create(context)


def test_registration_request_projection_tamper_blocks_read(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    created, _ = _create(context)
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.r5_signal_ledger_replay_registrations
            SET actor_id = 'tampered-actor'
            WHERE replay_id = %s
            """,
            (created["replay_id"],),
        )
    postgres_test_connection.commit()

    with pytest.raises(
        ResearchReplayIntegrityError, match="registration immutable evidence"
    ):
        context["service"].get_replay(created["replay_id"])


def test_cancelling_preserves_current_durable_progress(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    created, _ = _create(context)
    running, _ = context["repository"].transition_replay_status(
        created["replay_id"],
        expected_statuses=("SEALED",),
        status="RUNNING",
        progress="0.625",
        progress_message="worker progress",
    )
    assert running["progress"] == "0.625"

    cancelling, _ = context["service"].cancel_replay(created["replay_id"])

    assert cancelling["status"] == "CANCELLING"
    assert cancelling["progress"] == "0.625"


def test_invalid_postflight_is_durable_but_never_publishes_economics(
    postgres_test_connection, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    created, _ = _create(context)
    replay_id = created["replay_id"]
    replay = build_replay(
        match_rows=context["match"].rows,
        min_lot_shares=context["config"].min_lot_shares,
        slippage_bps=context["config"].slippage_bps,
        commission_rate=context["config"].commission_rate,
        sell_tax_rate=context["config"].sell_tax_rate,
    )
    result_manifest = build_result_manifest(
        replay_id=replay_id,
        registration_revision=1,
        ledger_manifest=context["ledger_manifest"],
        match_manifest=context["match_manifest"],
        replay=replay,
        min_lot_shares=context["config"].min_lot_shares,
        slippage_bps=context["config"].slippage_bps,
        commission_rate=context["config"].commission_rate,
        sell_tax_rate=context["config"].sell_tax_rate,
    )
    context["artifacts"].publish_result(
        manifest=result_manifest,
        episode_rows=replay.episodes,
        modeled_entry_rows=replay.modeled_entries,
        modeled_exit_rows=replay.modeled_exits,
    )
    postflight = build_postflight(
        replay_id=replay_id,
        registration_revision=1,
        baseline_result_digest=context["baseline"]["result_digest"],
        ledger_manifest=context["ledger_manifest"],
        match_manifest=context["match_manifest"],
        result_manifest=result_manifest,
        decision_rows=context["ledger"].rows,
        order_rows=context["derivation"].rows,
        ledger_rows=context["ledger"].rows,
        match_rows=context["match"].rows,
        episode_rows=replay.episodes,
        modeled_entry_rows=replay.modeled_entries,
        modeled_exit_rows=replay.modeled_exits,
        min_lot_shares=context["config"].min_lot_shares,
        slippage_bps=context["config"].slippage_bps,
        commission_rate=context["config"].commission_rate,
        sell_tax_rate=context["config"].sell_tax_rate,
        baseline_identity_valid=True,
        v1_invalid_lineage_valid=True,
        order_inception_seal_valid=True,
        ledger_artifact_valid=True,
        match_plan_artifact_valid=True,
        result_artifact_valid=True,
        v1_signal_multiplicity_valid=True,
        strategy_evaluation_count=0,
        provider_call_count=0,
        broker_call_count=0,
    )
    assert postflight["verdict"] == "INVALID"
    context["service"].start_replay(replay_id)

    registration = context["service"].publish_result(
        replay_id,
        result_manifest_digest=result_manifest["result_manifest_digest"],
        postflight=postflight,
    )

    assert registration["status"] == "INVALID"
    with pytest.raises(SignalReplayNotAccepted):
        context["service"].get_economics(replay_id)
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_results"
        )
        assert cursor.fetchone()[0] == 0


def test_different_key_concurrent_creation_has_one_authoritative_replay(
    postgres_test_connection, postgres_test_dsn, tmp_path
) -> None:
    context = _setup(postgres_test_connection, tmp_path)
    postgres_test_connection.commit()
    psycopg_pool = pytest.importorskip("psycopg_pool")
    pool = psycopg_pool.ConnectionPool(
        postgres_test_dsn, min_size=2, max_size=2, open=True
    )
    repository = SignalReplayPostgresRepository(pool=pool)
    service = SignalReplayApplicationService(
        repository=repository, artifacts=context["artifacts"]
    )
    barrier = Barrier(2)

    def create(key):
        barrier.wait()
        return service.create_replay(
            baseline_run_id=context["baseline"]["run_id"],
            idempotency_key=key,
            request=_request(
                context["match_manifest"]["match_plan_manifest_digest"]
            ),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    create,
                    ("concurrent-replay-key-1", "concurrent-replay-key-2"),
                )
            )
    finally:
        pool.close()
    postgres_test_connection.rollback()

    assert len({item[0]["replay_id"] for item in outcomes}) == 1
    assert sorted(item[1] for item in outcomes) == [False, True]
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_heads")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM backtest.r5_signal_ledger_replay_operations"
        )
        assert cursor.fetchone()[0] == 2
