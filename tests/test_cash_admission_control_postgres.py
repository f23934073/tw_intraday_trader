from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import shutil
import subprocess
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest

from backtest.application import BacktestApplicationService
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
    CashAdmissionControlConflict,
    CashAdmissionControlIntegrityError,
    CashAdmissionControlNotAccepted,
    build_cash_admission_postflight,
    build_cash_admission_preflight,
    build_research_control_snapshot,
    cash_admission_identity_validation_digest,
    entry_signal_multiplicity_digest,
    recompute_backtest_result_digest,
)
from backtest.dataset import HistoricalDatasetCatalog


_TAIPEI = ZoneInfo("Asia/Taipei")


def _baseline_result() -> dict[str, object]:
    fill = {
        "fill_id": "fill-entry-1",
        "decision_id": "decision-entry-1",
        "symbol": "2330",
        "side": "ENTRY",
        "filled_at": "2026-08-21T09:02:00+08:00",
        "price": 101.0,
        "shares": 1000,
        "commission": 143.925,
        "tax": 0.0,
        "total_cost": 143.925,
        "source": "NEXT_BAR_OPEN",
    }
    orders = [
        {
            "order_id": "baseline-entry-1",
            "decision_id": "decision-entry-1",
            "symbol": "2330",
            "side": "ENTRY",
            "status": "FILLED",
            "reason": "下一根 Kbar 開盤成交",
            "created_at": "2026-08-21T09:01:00+08:00",
            "filled_at": "2026-08-21T09:02:00+08:00",
            "fill": deepcopy(fill),
            "shares": 1000,
            "primary_strategy_id": "version-vwap",
            "triggered_strategy_ids": ["version-vwap"],
            "execution_horizon": "INTRADAY_NEXT_BAR",
        }
    ]
    result: dict[str, object] = {
        "decisions": [],
        "fills": [fill],
        "trades": [],
        "orders": orders,
        "daily_equity": [],
        "strategy_counts": {},
        "unresolved_positions": [],
        "summary": {"verdict": "INSUFFICIENT_EVIDENCE"},
    }
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    return result


def _setup_baseline(
    repository: PostgresBacktestRepository,
    tmp_path: Path,
    identity: str,
) -> tuple[dict[str, object], dict[str, object]]:
    catalog = HistoricalDatasetCatalog(tmp_path / identity)
    bars = [
        HistoricalBar(
            symbol="2330",
            name="台積電",
            market="TWSE",
            timestamp=datetime(2026, 8, 21, 9, minute, tzinfo=_TAIPEI),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=100,
        )
        for minute, price in ((1, 100), (2, 101))
    ]
    source_digest = digest({"source": identity})
    dataset_id = f"dataset-finmind-sponsor-sha256-{source_digest}"
    amount_contract: dict[str, object] = {
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "is_actual_turnover": False,
        "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
    }
    amount_contract["digest"] = digest(amount_contract)
    plan_identity = {"dataset_id": dataset_id, "source_snapshot_digest": source_digest}
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
        amount_contract=amount_contract,
        source_snapshot_digest=source_digest,
        plan_identity=plan_identity,
        plan_identity_digest=digest(plan_identity),
    )
    repository.register_immutable_dataset(manifest.to_dict())
    strategy_set = StrategySetSnapshot(
        entry_strategy_ids=("version-vwap",),
        exit_strategy_ids=("exit-eod",),
    )
    atomic_body = {
        "contract_version": "atomic-backtest-run-snapshot-v2",
        "strategy_set": {"strategy_set_version_id": "set-version-vwap"},
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
    baseline_run_id = f"baseline-{identity}"
    baseline, _ = repository.create_run(
        {
            "run_id": baseline_run_id,
            "idempotency_key": f"create-{baseline_run_id}",
            "status": RunStatus.RUNNING.value,
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": dataset_id,
            "dataset_digest": manifest.manifest_digest,
            "created_at": "2026-08-25T09:00:00+08:00",
        }
    )
    baseline_result = _baseline_result()
    repository.save_result(baseline_run_id, baseline_result)
    baseline = repository.update_run(
        baseline_run_id,
        status=RunStatus.COMPLETED.value,
        result_digest=baseline_result["summary"]["result_digest"],
        progress=1.0,
        progress_message="complete",
    )
    preflight = build_cash_admission_preflight(
        identity={
            "baseline_run_id": baseline_run_id,
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
        },
        s_max=1,
        p_max="101",
        candidate_order_count=1,
        matched_next_bar_count=1,
        missing_next_bar_count=0,
        baseline_signal_multiplicity_digest=entry_signal_multiplicity_digest(
            baseline_result["orders"]
        ),
    )
    return baseline, preflight


def _control_record(
    baseline: dict[str, object],
    preflight: dict[str, object],
    *,
    idempotency_key: str,
    run_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    snapshot = build_research_control_snapshot(
        preflight=preflight,
        actor_id="reviewer",
        change_note="sealed R5 control",
        created_at="2026-08-25T09:01:00+08:00",
    )
    config_document = deepcopy(baseline["config"])
    config_document.update(
        {
            "starting_cash": preflight["sizing"]["starting_cash"],
            "position_fraction": preflight["sizing"]["position_fraction"],
            "experiment_id": None,
            "baseline_run_id": None,
            "research_baseline_digest": None,
            "parent_run_id": baseline["run_id"],
            "change_note": "sealed R5 control",
            "research_control_snapshot": snapshot,
        }
    )
    config = BacktestRunConfig.from_dict(config_document)
    request = {
        "request_schema_version": "cash-admission-control-request-v1",
        "control_contract_version": "cash-admission-control-v1",
        "preflight_digest": preflight["artifact_digest"],
        "expected_registration_revision": 0,
        "idempotency_key": idempotency_key,
        "actor_id": "reviewer",
        "change_note": "sealed R5 control",
    }
    return (
        {
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "status": RunStatus.QUEUED.value,
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": config.dataset_id,
            "dataset_digest": config.dataset_digest,
            "created_at": "2026-08-25T09:01:00+08:00",
        },
        request,
    )


def _create_control(
    repository: PostgresBacktestRepository,
    baseline: dict[str, object],
    preflight: dict[str, object],
    *,
    idempotency_key: str,
    run_id: str,
):
    record, request = _control_record(
        baseline,
        preflight,
        idempotency_key=idempotency_key,
        run_id=run_id,
    )
    return repository.create_cash_admission_control(
        record,
        request=request,
        request_digest=digest(request),
        preflight=preflight,
    )


def _finalize_accepted_control(
    repository: PostgresBacktestRepository,
    *,
    baseline: dict[str, object],
    preflight: dict[str, object],
    control: dict[str, object],
) -> dict[str, object]:
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.QUEUED.value,),
        status=RunStatus.PREFLIGHT.value,
        progress_message="preflight",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.PREFLIGHT.value,),
        status=RunStatus.RUNNING.value,
        progress_message="running",
    )
    result = _baseline_result()
    result["orders"][0]["order_id"] = f"{control['run_id']}-entry-1"
    result["fills"][0]["fill_id"] = f"{control['run_id']}-fill-1"
    result["orders"][0]["fill"]["fill_id"] = result["fills"][0]["fill_id"]
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    current_control = repository.get_run(control["run_id"])
    postflight = build_cash_admission_postflight(
        baseline_orders=_baseline_result()["orders"],
        control_result=result,
        preflight=preflight,
        control_run_id=control["run_id"],
        control_config_digest=current_control["config_digest"],
        control_result_digest=result["summary"]["result_digest"],
        identity_validation_digest=cash_admission_identity_validation_digest(
            baseline_run=baseline,
            control_run=current_control,
            preflight=preflight,
        ),
    )
    repository.finalize_cash_admission_control(
        control["run_id"],
        result=result,
        postflight=postflight,
    )
    return result


def _run_acceptance_sql(
    *,
    postgres_test_dsn: str,
    baseline_run_id: str,
    control_run_id: str,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("psql")
    if executable is None:
        pytest.skip("psql is required for formal R5 acceptance SQL regression")
    sql_path = (
        Path(__file__).parents[1]
        / ".planning"
        / "2026-08-24-vwap-strategy-failure-attribution"
        / "r5_control_acceptance_queries.sql"
    )
    return subprocess.run(
        [
            executable,
            postgres_test_dsn,
            "-X",
            "-v",
            f"baseline_run_id={baseline_run_id}",
            "-v",
            f"control_run_id={control_run_id}",
            "-f",
            str(sql_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_postgres_control_is_unique_replayable_and_published_atomically(
    postgres_test_connection,
    tmp_path,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "accepted")
    control, replayed = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-create-1",
        run_id="control-accepted",
    )
    assert replayed is False

    same, replayed = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-create-2",
        run_id="must-not-exist",
    )
    assert replayed is True
    assert same["run_id"] == control["run_id"]

    different = build_cash_admission_preflight(
        identity=preflight["identity"],
        s_max=1,
        p_max="102",
        candidate_order_count=1,
        matched_next_bar_count=1,
        missing_next_bar_count=0,
        baseline_signal_multiplicity_digest=preflight["statistics"][
            "baseline_signal_multiplicity_digest"
        ],
    )
    with pytest.raises(CashAdmissionControlConflict, match="ALREADY_SEALED"):
        _create_control(
            repository,
            baseline,
            different,
            idempotency_key="r5-create-different",
            run_id="must-not-exist-2",
        )

    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.QUEUED.value,),
        status=RunStatus.PREFLIGHT.value,
        progress_message="preflight",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.PREFLIGHT.value,),
        status=RunStatus.RUNNING.value,
        progress_message="running",
    )
    result = _baseline_result()
    result["orders"][0]["order_id"] = "control-entry-1"
    result["fills"][0]["fill_id"] = "control-fill-1"
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    current_control = repository.get_run(control["run_id"])
    postflight = build_cash_admission_postflight(
        baseline_orders=_baseline_result()["orders"],
        control_result=result,
        preflight=preflight,
        control_run_id=control["run_id"],
        control_config_digest=current_control["config_digest"],
        control_result_digest=result["summary"]["result_digest"],
        identity_validation_digest=cash_admission_identity_validation_digest(
            baseline_run=baseline,
            control_run=current_control,
            preflight=preflight,
        ),
    )
    registration = repository.finalize_cash_admission_control(
        control["run_id"],
        result=result,
        postflight=postflight,
    )
    assert registration["status"] == "ACCEPTED"
    assert repository.get_run(control["run_id"])["status"] == RunStatus.COMPLETED.value
    assert repository.get_result(control["run_id"])["summary"] == result["summary"]
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM backtest_cash_admission_control_registrations")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM backtest_cash_admission_control_operations")
        assert cursor.fetchone()[0] == 2


def test_postgres_invalid_postflight_never_publishes_performance(
    postgres_test_connection,
    tmp_path,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "invalid")
    control, _ = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-invalid",
        run_id="control-invalid",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.QUEUED.value,),
        status=RunStatus.PREFLIGHT.value,
        progress_message="preflight",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.PREFLIGHT.value,),
        status=RunStatus.RUNNING.value,
        progress_message="running",
    )
    result = _baseline_result()
    result["orders"][0]["status"] = "REJECTED"
    result["orders"][0]["reason"] = "not display-text dependent"
    result["fills"] = []
    result["summary"]["result_digest"] = recompute_backtest_result_digest(result)
    current_control = repository.get_run(control["run_id"])
    postflight = build_cash_admission_postflight(
        baseline_orders=_baseline_result()["orders"],
        control_result=result,
        preflight=preflight,
        control_run_id=control["run_id"],
        control_config_digest=current_control["config_digest"],
        control_result_digest=result["summary"]["result_digest"],
        identity_validation_digest=cash_admission_identity_validation_digest(
            baseline_run=baseline,
            control_run=current_control,
            preflight=preflight,
        ),
    )
    registration = repository.finalize_cash_admission_control(
        control["run_id"],
        result=result,
        postflight=postflight,
    )
    assert registration["status"] == "INVALID"
    assert repository.get_run(control["run_id"])["status"] == (
        RunStatus.INVALID_CASH_ADMISSION_CONTROL.value
    )
    with pytest.raises(KeyError):
        repository.get_result(control["run_id"])


def test_formal_acceptance_sql_accepts_valid_registration_and_rejects_missing_fill(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "acceptance-sql")
    control, _ = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-acceptance-sql",
        run_id="control-acceptance-sql",
    )
    _finalize_accepted_control(
        repository,
        baseline=baseline,
        preflight=preflight,
        control=control,
    )

    accepted = _run_acceptance_sql(
        postgres_test_dsn=postgres_test_dsn,
        baseline_run_id=baseline["run_id"],
        control_run_id=control["run_id"],
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "R5_ACCEPTED" in accepted.stdout

    with postgres_test_connection.transaction():
        with postgres_test_connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM backtest_result_chunks
                WHERE run_id = %s AND field_name = 'fills'
                """,
                (control["run_id"],),
            )
            assert cursor.rowcount == 1

    rejected = _run_acceptance_sql(
        postgres_test_dsn=postgres_test_dsn,
        baseline_run_id=baseline["run_id"],
        control_run_id=control["run_id"],
    )
    assert rejected.returncode != 0
    assert "R5_REJECTED" in rejected.stdout


def test_postgres_accepted_read_rejects_self_consistent_admission_chunk_tamper(
    postgres_test_connection,
    tmp_path,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "accepted-tamper")
    control, _ = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-accepted-tamper",
        run_id="control-accepted-tamper",
    )
    _finalize_accepted_control(
        repository,
        baseline=baseline,
        preflight=preflight,
        control=control,
    )

    with postgres_test_connection.transaction():
        with postgres_test_connection.cursor() as cursor:
            cursor.execute(
                "SELECT result_json FROM backtest_results WHERE run_id = %s",
                (control["run_id"],),
            )
            root = deepcopy(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT payload_json
                FROM backtest_result_chunks
                WHERE run_id = %s AND field_name = 'orders' AND chunk_sequence = 0
                """,
                (control["run_id"],),
            )
            orders = deepcopy(cursor.fetchone()[0])
            orders[0]["status"] = "REJECTED"
            orders[0]["reason"] = "tampered after acceptance"
            order_digest = digest(orders)
            cursor.execute(
                """
                UPDATE backtest_result_chunks
                SET payload_json = %s::jsonb, payload_digest = %s
                WHERE run_id = %s AND field_name = 'orders' AND chunk_sequence = 0
                """,
                (canonical_json(orders), order_digest, control["run_id"]),
            )
            cursor.execute(
                """
                DELETE FROM backtest_result_chunks
                WHERE run_id = %s AND field_name = 'fills'
                """,
                (control["run_id"],),
            )
            root["_storage"]["fields"]["orders"]["chunks"][0][
                "payload_digest"
            ] = order_digest
            root["_storage"]["fields"]["fills"] = {
                "item_count": 0,
                "chunk_count": 0,
                "chunks": [],
            }
            cursor.execute(
                """
                UPDATE backtest_results
                SET result_json = %s::jsonb
                WHERE run_id = %s
                """,
                (canonical_json(root), control["run_id"]),
            )

    assert repository.get_result(control["run_id"])["orders"][0]["status"] == (
        "REJECTED"
    )
    service = object.__new__(BacktestApplicationService)
    service._repository = repository
    with pytest.raises(CashAdmissionControlNotAccepted, match="integrity conflict"):
        service._verified_result(control["run_id"])


def test_postgres_control_result_tamper_fails_before_finalize(
    postgres_test_connection,
    tmp_path,
) -> None:
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "tamper")
    control, _ = _create_control(
        repository,
        baseline,
        preflight,
        idempotency_key="r5-tamper",
        run_id="control-tamper",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.QUEUED.value,),
        status=RunStatus.PREFLIGHT.value,
        progress_message="preflight",
    )
    repository.transition_run_status(
        control["run_id"],
        expected_statuses=(RunStatus.PREFLIGHT.value,),
        status=RunStatus.RUNNING.value,
        progress_message="running",
    )
    result = _baseline_result()
    current_control = repository.get_run(control["run_id"])
    postflight = build_cash_admission_postflight(
        baseline_orders=_baseline_result()["orders"],
        control_result=result,
        preflight=preflight,
        control_run_id=control["run_id"],
        control_config_digest=current_control["config_digest"],
        control_result_digest=result["summary"]["result_digest"],
        identity_validation_digest=cash_admission_identity_validation_digest(
            baseline_run=baseline,
            control_run=current_control,
            preflight=preflight,
        ),
    )
    result["summary"]["verdict"] = "TAMPERED"
    with pytest.raises(CashAdmissionControlIntegrityError, match="result digest"):
        repository.finalize_cash_admission_control(
            control["run_id"],
            result=result,
            postflight=postflight,
        )


def test_postgres_concurrent_different_keys_create_one_authoritative_control(
    postgres_test_connection,
    postgres_test_dsn,
    tmp_path,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    repository = PostgresBacktestRepository(postgres_test_connection)
    baseline, preflight = _setup_baseline(repository, tmp_path, "concurrent")
    barrier = Barrier(2)

    def launch(index: int):
        connection = psycopg.connect(postgres_test_dsn)
        worker_repository = PostgresBacktestRepository(connection)
        try:
            record, request = _control_record(
                baseline,
                preflight,
                idempotency_key=f"r5-concurrent-{index}",
                run_id=f"control-concurrent-{index}",
            )
            barrier.wait(timeout=5)
            return worker_repository.create_cash_admission_control(
                record,
                request=request,
                request_digest=digest(request),
                preflight=preflight,
            )
        finally:
            worker_repository.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(launch, (1, 2)))

    assert {outcome[0]["run_id"] for outcome in outcomes} in (
        {"control-concurrent-1"},
        {"control-concurrent-2"},
    )
    assert sorted(outcome[1] for outcome in outcomes) == [False, True]
    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM backtest_cash_admission_control_heads")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM backtest_cash_admission_control_registrations")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM backtest_cash_admission_control_operations")
        assert cursor.fetchone()[0] == 2
        cursor.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE run_id LIKE 'control-concurrent-%'"
        )
        assert cursor.fetchone()[0] == 1
