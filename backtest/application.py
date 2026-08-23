"""Application service for durable, data-only historical-backtest jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta
from time import sleep
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from backtest.dataset import DatasetCancelled, DatasetManifest, HistoricalDatasetCatalog
from backtest.atomic_strategy_adapter import (
    bind_dataset_feature_evidence,
    resolve_atomic_entry_set,
)
from backtest.comparability import (
    comparability_contract_digest,
    run_comparability_diff,
    verify_run_identity,
)
from backtest.domain import (
    AggregationPolicy,
    BacktestRunConfig,
    RunStatus,
    StrategySetSnapshot,
    digest,
)
from backtest.engine import BacktestCancelled, HistoricalBacktestEngine
from backtest.feature_adapters import verify_vwap_amount_contract
from backtest.dataset_binding import (
    ATOMIC_BACKTEST_DEFAULT,
    AtomicBacktestBindingChanged,
    AtomicBacktestBindingUnavailable,
    DatasetBindingIntegrityError,
)
from backtest.historical_download import IncrementalHistoricalSync
from backtest.metrics import compare_runs, summarize_run
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.qualification import (
    EvaluationWindow,
    MultipleTestingRecord,
    QualificationPolicy,
    QualificationProtocol,
    build_qualification_evidence,
    experiment_family_id,
    research_baseline_identity_digest,
)
from backtest.repository import BacktestRepository
from backtest.repository import BacktestIdempotencyConflict
from backtest.run_control import DurableRunControlProbe, ThrottledProgressReporter
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyRegistry
from atomic_strategies.registry import AtomicStrategyRegistry
from config import backtest as backtest_settings
from market_data.provider import MarketDataProvider
from strategy_catalog.service import StrategyCatalogService
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository
from strategy_catalog.repository import AtomicStrategyRepository
from strategy_catalog.sets import ExactStrategySetSnapshot


_TAIPEI = ZoneInfo("Asia/Taipei")


class IncrementalSyncDeferred(RuntimeError):
    """A scheduler-visible wait state, not an incremental-sync failure."""

    def __init__(self, message: str, *, scheduler_state: str, job_id: str | None = None) -> None:
        super().__init__(message)
        self.scheduler_state = scheduler_state
        self.job_id = job_id


class BacktestApplicationService:
    """Coordinates storage, catalog and pure engine without broker capabilities."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        repository: BacktestRepository | None = None,
        catalog: HistoricalDatasetCatalog | None = None,
        engine: HistoricalBacktestEngine | None = None,
        registry: StrategyRegistry | None = None,
        atomic_repository: AtomicStrategyRepository | None = None,
        atomic_registry: AtomicStrategyRegistry | None = None,
        workers: int = backtest_settings.BACKTEST_WORKERS,
    ) -> None:
        self._provider = provider
        self._registry = registry or StrategyRegistry()
        self._catalog = catalog or HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
        self._repository = repository or self._build_repository()
        self._strategy_catalog = StrategyCatalogService(self._repository, self._registry)
        self._engine = engine or HistoricalBacktestEngine(self._registry)
        self._atomic_repository = atomic_repository
        self._atomic_registry = atomic_registry or AtomicStrategyRegistry()
        if self._atomic_repository is None and isinstance(self._repository, PostgresBacktestRepository):
            pool = self._repository.connection_pool
            if pool is not None:
                self._atomic_repository = PostgresAtomicStrategyRepository(pool=pool)
        self._incremental_sync = IncrementalHistoricalSync(
            provider=provider,
            repository=self._repository,
            catalog=self._catalog,
        )
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="historical-backtest")
        self._closed = False

    @staticmethod
    def _build_repository() -> BacktestRepository:
        database_url = backtest_settings.BACKTEST_DATABASE_URL
        if backtest_settings.BACKTEST_DATABASE_BACKEND == "postgresql":
            try:
                from psycopg_pool import ConnectionPool  # type: ignore[import-not-found]
            except ImportError as error:
                raise RuntimeError(
                    "使用 PostgreSQL 回測資料庫前，請安裝 tw-intraday-trader[postgres]"
                ) from error
            pool = ConnectionPool(
                database_url,
                min_size=1,
                max_size=max(4, backtest_settings.BACKTEST_WORKERS + 2),
                timeout=5,
                open=True,
            )
            return PostgresBacktestRepository(pool=pool, owns_pool=True)
        return SQLiteBacktestRepository(backtest_settings.BACKTEST_DATA_DIR / "backtest.sqlite3")

    def close(self) -> None:
        """Drain workers before releasing the durable connection.

        A server shutdown must not close SQLite/PostgreSQL while a worker is
        half way through an immutable result write.  Active backtests receive a
        cooperative cancellation request and the worker finalizes that status
        at its next deterministic boundary.
        """
        if self._closed:
            return
        self._closed = True
        for run in self._repository.list_runs():
            if run["status"] in {
                RunStatus.QUEUED.value,
                RunStatus.PREFLIGHT.value,
                RunStatus.RUNNING.value,
            }:
                self._repository.update_run(
                    run["run_id"],
                    status=RunStatus.CANCELLING.value,
                    progress_message="服務關閉，正在取消回測",
                )
        for job in self._repository.list_jobs():
            if job["kind"] == IncrementalHistoricalSync.JOB_KIND and job["status"] in {
                RunStatus.QUEUED.value,
                RunStatus.RUNNING.value,
            }:
                self._repository.update_job(
                    job["job_id"],
                    status=RunStatus.CANCELLING.value,
                    progress_message="服務關閉，正在暫停增量同步",
                )
        self._executor.shutdown(wait=True, cancel_futures=False)
        close = getattr(self._repository, "close", None)
        if callable(close):
            close()

    def capabilities(self) -> dict[str, Any]:
        return {
            "enabled": backtest_settings.BACKTEST_ENABLED,
            "provider": type(self._provider).__name__,
            "provider_supports_kbars": self._provider.supports_kbars(),
            "database": (
                "PostgreSQL"
                if backtest_settings.BACKTEST_DATABASE_BACKEND == "postgresql"
                else "SQLite（本機開發）"
            ),
            "modes": ["SIGNAL_STUDY", "PORTFOLIO_SIMULATION"],
            "incremental_sync": {
                "enabled": backtest_settings.BACKTEST_INCREMENTAL_SYNC_ENABLED,
                "timezone": "Asia/Taipei",
                "close_time": backtest_settings.BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME.strftime("%H:%M"),
                "overlap_days": backtest_settings.BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS,
            },
            "safety": "只讀歷史行情；不會啟動券商下單、帳務、CA 或 trade subscription。",
        }

    def strategies(self, side: str | None = None) -> list[dict[str, Any]]:
        return self._strategy_catalog.backtest_strategies(side)

    def strategy_catalog(
        self,
        *,
        role: str | None = None,
        session_phase: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._strategy_catalog.list(
            role=role,
            session_phase=session_phase,
            status=status,
        )

    def save_strategy_definition(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        return self._strategy_catalog.save(payload)

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._repository.list_datasets()

    def create_derived_daily_dataset(
        self,
        *,
        dataset_id: str,
        base_dataset_id: str,
        completion_proofs: Mapping[tuple[str, date], str],
        session_contract: Mapping[str, Any],
        price_adjustment_policy: str = "RAW",
        corporate_action_adjusted: bool = False,
        volume_contract: Mapping[str, Any],
        issues: tuple[str, ...] = (),
    ) -> DatasetManifest:
        """Seal and register a verified daily child dataset for research runs.

        This does not contact a Provider or broker.  The catalog refuses the
        derivation unless each source symbol/session has an explicit completion
        evidence digest, then this service makes the immutable child available
        to the normal capability-gated backtest workflow.
        """

        self._require_enabled()
        base = self._repository.get_dataset(base_dataset_id)
        if base["status"] != "READY":
            raise ValueError("來源 intraday 資料集尚未 READY，不能派生日 K 資料集")
        catalog_base = self._catalog.get_manifest(base_dataset_id)
        if str(base["manifest_digest"]) != catalog_base.manifest_digest:
            raise ValueError("來源 intraday 資料集 manifest digest 已變更，拒絕派生日 K 資料集")
        manifest = self._catalog.create_derived_daily_dataset(
            dataset_id=dataset_id,
            base_dataset_id=base_dataset_id,
            completion_proofs=completion_proofs,
            session_contract=session_contract,
            price_adjustment_policy=price_adjustment_policy,
            corporate_action_adjusted=corporate_action_adjusted,
            volume_contract=volume_contract,
            issues=issues,
        )
        self._repository.upsert_dataset(manifest.to_dict(), "READY")
        return manifest

    def start_incremental_sync(
        self,
        session_date: date,
        *,
        overlap_days: int = backtest_settings.BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS,
    ) -> dict[str, object]:
        """Submit or resume one durable after-close sync for the local date."""

        self._require_enabled()
        job_id = f"dataset-incremental-{session_date:%Y%m%d}"
        try:
            existing = self._repository.get_job(job_id)
        except KeyError:
            existing = None
        if existing is not None and existing["status"] == RunStatus.COMPLETED.value:
            return {
                "job": existing,
                "created": False,
                "state": "SUBMITTED",
                "message": "本交易日增量同步已完成",
            }

        active = [
            job
            for job in self._repository.list_jobs()
            if job["job_id"] != job_id
            and job["kind"] in {
                "DATASET_SYNC",
                "DATASET_DOWNLOAD",
                IncrementalHistoricalSync.JOB_KIND,
            }
            and job["status"] in {
                RunStatus.QUEUED.value,
                RunStatus.RUNNING.value,
                RunStatus.CANCELLING.value,
            }
            and self._job_is_fresh(job)
        ]
        if active:
            blocking = active[0]
            raise IncrementalSyncDeferred(
                f"等待既有資料工作完成：{blocking['job_id']}",
                scheduler_state="BLOCKED_BY_ACTIVE_JOB",
                job_id=str(blocking["job_id"]),
            )

        if existing is None:
            base = next(
                (
                    dataset
                    for dataset in self._repository.list_datasets()
                    if dataset["status"] == "READY"
                    and dataset.get("source") == type(self._provider).__name__
                    and dataset.get("universe_scope") == "CURRENT_SNAPSHOT"
                ),
                None,
            )
            if base is None:
                raise IncrementalSyncDeferred(
                    "尚無 READY 的 Provider 歷史資料集；等待初始三年下載完成",
                    scheduler_state="WAITING_FOR_BASE",
                )
            if date.fromisoformat(str(base["end_date"])) >= session_date:
                job, created = self._repository.create_job_once(
                    {
                        "job_id": job_id,
                        "kind": IncrementalHistoricalSync.JOB_KIND,
                        "status": RunStatus.QUEUED.value,
                        "request": {
                            "provider": type(self._provider).__name__,
                            "session_date": session_date.isoformat(),
                            "base_dataset_id": base["dataset_id"],
                            "base_manifest_digest": base["manifest_digest"],
                            "target_dataset_id": base["dataset_id"],
                            "reason": "BASE_ALREADY_COVERS_SESSION",
                        },
                        "progress": 1.0,
                        "progress_message": "目前資料集已涵蓋本交易日",
                        "created_at": _now(),
                    }
                )
                if created:
                    job = self._repository.update_job(
                        job_id,
                        status=RunStatus.COMPLETED.value,
                        resource_id=base["dataset_id"],
                        progress=1.0,
                        progress_message="同步完成：目前資料集已涵蓋本交易日",
                    )
                return {
                    "job": job,
                    "created": created,
                    "state": "SUBMITTED",
                    "message": "目前資料集已涵蓋本交易日，不需重新下載",
                }
            job, created = self._incremental_sync.create_job(
                base_dataset_id=str(base["dataset_id"]),
                session_date=session_date,
                overlap_days=overlap_days,
            )
        else:
            job = existing
            created = False
            if job["status"] in {RunStatus.QUEUED.value, RunStatus.RUNNING.value} and self._job_is_fresh(job):
                raise IncrementalSyncDeferred(
                    f"增量同步工作仍在執行：{job_id}",
                    scheduler_state="SYNC_IN_PROGRESS",
                    job_id=job_id,
                )

        self._executor.submit(self._run_incremental_sync, str(job["job_id"]))
        return {
            "job": job,
            "created": created,
            "state": "SUBMITTED",
            "message": "已建立收盤後增量同步工作" if created else "已接續收盤後增量同步工作",
        }

    def latest_incremental_job(self) -> dict[str, Any] | None:
        return next(
            (
                job
                for job in self._repository.list_jobs()
                if job["kind"] == IncrementalHistoricalSync.JOB_KIND
            ),
            None,
        )

    def start_dataset_sync(
        self,
        *,
        years: int,
        symbols: list[str] | None,
        symbol_limit: int | None,
    ) -> dict[str, Any]:
        self._require_enabled()
        job_id = f"dataset-job-{uuid4().hex}"
        job = self._repository.create_job(
            {
                "job_id": job_id,
                "kind": "DATASET_SYNC",
                "status": RunStatus.QUEUED.value,
                "request": {"years": years, "symbols": symbols or [], "symbol_limit": symbol_limit},
                "created_at": _now(),
            }
        )
        self._executor.submit(self._run_dataset_sync, job_id, years, symbols, symbol_limit)
        return job

    def dataset_job(self, job_id: str) -> dict[str, Any]:
        return self._repository.get_job(job_id)

    def cancel_dataset_job(self, job_id: str) -> dict[str, Any]:
        job = self._repository.get_job(job_id)
        if job["kind"] != "DATASET_SYNC":
            raise ValueError("這不是歷史資料集工作")
        if job["status"] not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise ValueError("只有尚未完成的資料集工作可以取消")
        return self._repository.update_job(
            job_id,
            status=RunStatus.CANCELLING.value,
            progress_message="正在取消，會在下一個股票下載邊界停止",
        )

    def create_run(
        self,
        *,
        dataset_id: str,
        entry_strategy_ids: list[str],
        exit_strategy_ids: list[str],
        entry_policy: str = "ANY",
        exit_policy: str = "ANY",
        entry_min_trigger_count: int = 1,
        exit_min_trigger_count: int = 1,
        priority_order: list[str] | None = None,
        starting_cash: str = backtest_settings.BACKTEST_DEFAULT_STARTING_CASH,
        position_fraction: str = backtest_settings.BACKTEST_DEFAULT_POSITION_FRACTION,
        commission_rate: str = backtest_settings.BACKTEST_DEFAULT_COMMISSION_RATE,
        sell_tax_rate: str = backtest_settings.BACKTEST_DEFAULT_SELL_TAX_RATE,
        slippage_bps: str = backtest_settings.BACKTEST_DEFAULT_SLIPPAGE_BPS,
        target_win_rate: str = "0.50",
        minimum_oos_trades: int = 30,
        max_drawdown_guardrail: str = "0.20",
        engine_version: str = "backtest-engine-v2",
        idempotency_key: str,
        experiment_id: str | None = None,
        baseline_run_id: str | None = None,
        parent_run_id: str | None = None,
        change_note: str = "",
    ) -> tuple[dict[str, Any], bool]:
        self._require_enabled()
        dataset = self._repository.get_dataset(dataset_id)
        if dataset["status"] != "READY":
            raise ValueError("歷史資料集尚未 READY，不能建立回測")
        strategy_set = StrategySetSnapshot(
            entry_strategy_ids=tuple(entry_strategy_ids),
            exit_strategy_ids=tuple(exit_strategy_ids),
            entry_policy=AggregationPolicy(entry_policy),
            exit_policy=AggregationPolicy(exit_policy),
            entry_min_trigger_count=entry_min_trigger_count,
            exit_min_trigger_count=exit_min_trigger_count,
            priority_order=tuple(priority_order or ()),
        )
        self._validate_strategy_selection(strategy_set, dataset)
        config = BacktestRunConfig(
            dataset_id=dataset_id,
            dataset_digest=str(dataset["manifest_digest"]),
            strategy_set=strategy_set,
            starting_cash=starting_cash,
            position_fraction=position_fraction,
            commission_rate=commission_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            target_win_rate=target_win_rate,
            minimum_oos_trades=minimum_oos_trades,
            max_drawdown_guardrail=max_drawdown_guardrail,
            engine_version=engine_version,
            experiment_id=experiment_id,
            baseline_run_id=baseline_run_id,
            parent_run_id=parent_run_id,
            change_note=change_note,
        )
        record = {
            "run_id": f"run-{uuid4().hex}",
            "idempotency_key": self._validate_idempotency_key(idempotency_key),
            "status": RunStatus.QUEUED.value,
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": dataset_id,
            "dataset_digest": config.dataset_digest,
            "created_at": _now(),
        }
        run, idempotent = self._repository.create_run(record)
        if not idempotent:
            self._executor.submit(self._run_backtest, run["run_id"])
        return run, idempotent

    def create_atomic_run(
        self,
        *,
        strategy_set_version_id: str,
        starting_cash: str = backtest_settings.BACKTEST_DEFAULT_STARTING_CASH,
        position_fraction: str = backtest_settings.BACKTEST_DEFAULT_POSITION_FRACTION,
        commission_rate: str = backtest_settings.BACKTEST_DEFAULT_COMMISSION_RATE,
        sell_tax_rate: str = backtest_settings.BACKTEST_DEFAULT_SELL_TAX_RATE,
        slippage_bps: str = backtest_settings.BACKTEST_DEFAULT_SLIPPAGE_BPS,
        target_win_rate: str = "0.50",
        minimum_oos_trades: int = 30,
        max_drawdown_guardrail: str = "0.20",
        idempotency_key: str,
        change_note: str = "",
        baseline_run_id: str | None = None,
        expected_binding_revision: int | None = None,
        expected_dataset_digest: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        self._require_enabled()
        repository = self._require_atomic_repository()
        key = self._validate_idempotency_key(idempotency_key)
        request_document = self._atomic_run_request_document(
            strategy_set_version_id=strategy_set_version_id,
            starting_cash=starting_cash,
            position_fraction=position_fraction,
            commission_rate=commission_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            target_win_rate=target_win_rate,
            minimum_oos_trades=minimum_oos_trades,
            max_drawdown_guardrail=max_drawdown_guardrail,
            change_note=change_note,
            baseline_run_id=baseline_run_id,
            expected_binding_revision=expected_binding_revision,
            expected_dataset_digest=expected_dataset_digest,
        )
        request_digest = digest(request_document)
        replay = self._repository.get_run_by_idempotency_key(key)
        if replay is not None:
            verify_run_identity(replay)
            replay_config = BacktestRunConfig.from_dict(replay["config"])
            if replay_config.atomic_run_request_digest != request_digest:
                raise BacktestIdempotencyConflict(
                    "相同 idempotency key 的 Atomic Run request 不同"
                )
            return replay, True
        snapshot = repository.get_strategy_set(strategy_set_version_id)
        resolution = resolve_atomic_entry_set(repository, self._atomic_registry, snapshot)
        baseline: dict[str, Any] | None = None
        research_baseline_digest: str | None = None
        family_id: str | None = None
        binding_snapshot: dict[str, Any] | None = None
        if baseline_run_id is not None:
            baseline = self._repository.get_run(baseline_run_id)
            verify_run_identity(baseline)
            if baseline["status"] != RunStatus.COMPLETED.value:
                raise ValueError("Experiment Baseline 必須先完成")
            if baseline["config"].get("atomic_strategy_run_snapshot") is None:
                raise ValueError("Experiment Baseline 必須是 Atomic Run")
            if baseline["config"].get("dataset_amount_contract") is None:
                raise ValueError("Experiment Baseline 缺少 G5 Dataset amount evidence")
            research_baseline_digest = research_baseline_identity_digest(
                baseline["config"]
            )
            family_id = experiment_family_id(research_baseline_digest)
            dataset_id = str(baseline["dataset_id"])
            binding_snapshot = (
                dict(baseline["config"]["dataset_binding_snapshot"])
                if baseline["config"].get("dataset_binding_snapshot") is not None
                else None
            )
        else:
            if expected_binding_revision is None or expected_dataset_digest is None:
                raise AtomicBacktestBindingUnavailable(
                    "建立 standalone Atomic Run 必須提供 binding revision 與 Dataset digest"
                )
            binding = self._repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
            if binding is None:
                raise AtomicBacktestBindingUnavailable(
                    "ATOMIC_BACKTEST_DEFAULT 尚未設定"
                )
            if (
                binding["revision"] != expected_binding_revision
                or binding["dataset_digest"] != expected_dataset_digest
            ):
                raise AtomicBacktestBindingChanged(
                    "ATOMIC_BACKTEST_DEFAULT 已變更，請重新整理後再確認"
                )
            dataset_id = str(binding["dataset_id"])
            binding_snapshot = dict(binding)
        dataset, amount_contract = self._verified_atomic_dataset(
            dataset_id,
            resolution.engine_strategy_set,
            registry=resolution.registry,
            resolution=resolution,
        )
        resolution = self._resolve_bound_atomic_entry_set(
            snapshot,
            amount_contract=amount_contract,
        )
        if baseline_run_id is not None and (
            baseline["dataset_digest"] != dataset["manifest_digest"]
            or baseline["config"].get("dataset_amount_contract") != amount_contract
        ):
            raise ValueError("Experiment Baseline Dataset evidence 已漂移")
        atomic_snapshot = bind_dataset_feature_evidence(
            resolution.run_snapshot,
            dataset_id=dataset_id,
            dataset_digest=str(dataset["manifest_digest"]),
            amount_contract=amount_contract,
        )
        self._validate_strategy_selection(
            resolution.engine_strategy_set,
            dataset,
            registry=resolution.registry,
        )
        config = BacktestRunConfig(
            dataset_id=dataset_id,
            dataset_digest=str(dataset["manifest_digest"]),
            strategy_set=resolution.engine_strategy_set,
            starting_cash=starting_cash,
            position_fraction=position_fraction,
            commission_rate=commission_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            target_win_rate=target_win_rate,
            minimum_oos_trades=minimum_oos_trades,
            max_drawdown_guardrail=max_drawdown_guardrail,
            # Atomic versions reuse the deterministic v2 engine. Their exact
            # implementation identity lives in atomic_strategy_run_snapshot,
            # not in a second engine-version namespace.
            engine_version="backtest-engine-v2",
            experiment_id=family_id,
            baseline_run_id=baseline_run_id,
            research_baseline_digest=research_baseline_digest,
            change_note=change_note,
            atomic_strategy_run_snapshot=atomic_snapshot,
            atomic_run_request=request_document,
            atomic_run_request_digest=request_digest,
            dataset_binding_snapshot=binding_snapshot,
            dataset_amount_contract=amount_contract,
        )
        if baseline is not None:
            config_diff = run_comparability_diff(baseline["config"], config.to_dict())
            if config_diff:
                fields = "、".join(item["field"] for item in config_diff)
                raise ValueError(f"Challenger 與 Baseline 不可比較：{fields}")
        record = {
            "run_id": f"run-{uuid4().hex}",
            "idempotency_key": key,
            "status": RunStatus.QUEUED.value,
            "config": config.to_dict(),
            "config_digest": config.config_digest,
            "dataset_id": dataset_id,
            "dataset_digest": config.dataset_digest,
            "created_at": _now(),
        }
        if baseline is None:
            create_bound = getattr(
                self._repository, "create_atomic_run_from_binding", None
            )
            if not callable(create_bound):
                raise RuntimeError("standalone Atomic Run binding requires PostgreSQL")
            run, idempotent = create_bound(
                record,
                binding_name=ATOMIC_BACKTEST_DEFAULT,
                expected_binding_revision=int(expected_binding_revision),
                expected_dataset_digest=str(expected_dataset_digest),
                request_digest=request_digest,
            )
        else:
            run, idempotent = self._repository.create_run(record)
        if not idempotent:
            self._executor.submit(self._run_backtest, run["run_id"])
        return run, idempotent

    def atomic_backtest_dataset_status(
        self,
        *,
        strategy_set_version_id: str,
        baseline_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the exact server-owned Dataset projection used at submit."""

        self._require_enabled()
        repository = self._require_atomic_repository()
        snapshot = repository.get_strategy_set(strategy_set_version_id)
        resolution = resolve_atomic_entry_set(repository, self._atomic_registry, snapshot)
        binding: dict[str, Any] | None = None
        if baseline_run_id is not None:
            baseline = self._repository.get_run(baseline_run_id)
            verify_run_identity(baseline)
            if baseline["status"] != RunStatus.COMPLETED.value:
                raise ValueError("Experiment Baseline 必須先完成")
            if baseline["config"].get("atomic_strategy_run_snapshot") is None:
                raise ValueError("Experiment Baseline 必須是 Atomic Run")
            if baseline["config"].get("dataset_amount_contract") is None:
                raise ValueError("Experiment Baseline 缺少 G5 Dataset amount evidence")
            dataset_id = str(baseline["dataset_id"])
            resolution_mode = "BASELINE_DATASET"
        else:
            binding = self._repository.get_dataset_binding(ATOMIC_BACKTEST_DEFAULT)
            if binding is None:
                return {
                    "available": False,
                    "binding_name": ATOMIC_BACKTEST_DEFAULT,
                    "code": "DATASET_BINDING_UNAVAILABLE",
                    "message": "ATOMIC_BACKTEST_DEFAULT 尚未設定",
                }
            dataset_id = str(binding["dataset_id"])
            resolution_mode = "DEFAULT_BINDING"
        dataset, amount_contract = self._verified_atomic_dataset(
            dataset_id,
            resolution.engine_strategy_set,
            registry=resolution.registry,
            resolution=resolution,
        )
        if baseline_run_id is not None and (
            baseline["dataset_digest"] != dataset["manifest_digest"]
            or baseline["config"].get("dataset_amount_contract") != amount_contract
        ):
            raise ValueError("Experiment Baseline Dataset evidence 已漂移")
        return {
            "available": True,
            "resolution_mode": resolution_mode,
            "binding_name": binding["binding_name"] if binding is not None else None,
            "binding_revision": binding["revision"] if binding is not None else None,
            "dataset_id": dataset["dataset_id"],
            "dataset_digest": dataset["manifest_digest"],
            "source": dataset["source"],
            "start_date": dataset["start_date"],
            "end_date": dataset["end_date"],
            "symbol_count": len(dataset.get("observed_symbols", ())),
            "bar_count": int(dataset["bar_count"]),
            "capabilities": list(dataset.get("capabilities", ())),
            "amount_kind": amount_contract.get("kind") if amount_contract else None,
            "amount_contract_digest": (
                amount_contract.get("digest") if amount_contract else None
            ),
            "vwap_semantic": (
                amount_contract.get("vwap_semantic") if amount_contract else None
            ),
            "research_eligible": bool(dataset.get("research_eligible")),
            "issues": list(dataset.get("issues", ())),
        }

    def _select_ready_dataset(
        self,
        strategy_set: StrategySetSnapshot,
        *,
        registry: StrategyRegistry,
    ) -> dict[str, Any]:
        self._validate_strategy_selection(strategy_set, registry=registry)
        ready = sorted(
            (
                dataset
                for dataset in self._repository.list_datasets()
                if dataset["status"] == "READY"
            ),
            key=lambda dataset: bool(dataset.get("research_eligible")),
            reverse=True,
        )
        if not ready:
            raise ValueError("尚無 READY 歷史資料快照，不能建立回測")
        for dataset in ready:
            try:
                self._validate_strategy_selection(
                    strategy_set,
                    dataset,
                    registry=registry,
                )
            except ValueError:
                continue
            return dataset
        raise ValueError("目前 READY 歷史資料快照不具備此策略組合所需資料能力")

    def list_runs(self) -> list[dict[str, Any]]:
        return self._repository.list_runs()

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._repository.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        run = self._repository.get_run(run_id)
        if run["status"] not in {RunStatus.QUEUED.value, RunStatus.PREFLIGHT.value, RunStatus.RUNNING.value}:
            raise ValueError("只有尚未完成的回測可以取消")
        return self._repository.update_run(run_id, status=RunStatus.CANCELLING.value, progress_message="正在取消，會在下一個安全事件邊界停止")

    def cancel_atomic_run(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        actor_id: str,
        request_digest: str,
    ) -> tuple[dict[str, Any], bool]:
        cancel = getattr(self._repository, "cancel_atomic_run", None)
        if not callable(cancel):
            raise RuntimeError("atomic Run cancel 需要 PostgreSQL durable repository")
        return cancel(
            run_id,
            idempotency_key=self._validate_idempotency_key(idempotency_key),
            actor_id=actor_id,
            request_digest=request_digest,
        )

    def retry_run(self, run_id: str, *, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        existing = self._repository.get_run(run_id)
        if existing["status"] not in {RunStatus.CANCELLED.value, RunStatus.FAILED.value}:
            raise ValueError("只有已取消或失敗的回測可以重試")
        return self._create_from_config(
            config=existing["config"],
            idempotency_key=idempotency_key,
            parent_run_id=run_id,
            change_note="重新執行原設定",
        )

    def clone_run(
        self,
        run_id: str,
        *,
        overrides: Mapping[str, Any],
        idempotency_key: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        if not change_note.strip():
            raise ValueError("複製並調整回測時必須填寫調整說明")
        existing = self._repository.get_run(run_id)
        if existing["config"].get("atomic_strategy_run_snapshot") is not None:
            allowed_atomic_overrides = {
                "starting_cash",
                "position_fraction",
                "commission_rate",
                "sell_tax_rate",
                "slippage_bps",
                "target_win_rate",
                "minimum_oos_trades",
                "max_drawdown_guardrail",
            }
            unsupported = sorted(set(overrides) - allowed_atomic_overrides)
            if unsupported:
                raise ValueError(
                    "原子策略回測只能調整資金、成本與評估門檻；不可覆寫："
                    + "、".join(unsupported)
                )
        config = _deep_merge(existing["config"], overrides)
        config["parent_run_id"] = run_id
        config["baseline_run_id"] = existing["config"].get("baseline_run_id") or run_id
        config["experiment_id"] = existing["config"].get("experiment_id") or f"experiment-{uuid4().hex}"
        return self._create_from_config(
            config=config,
            idempotency_key=idempotency_key,
            parent_run_id=run_id,
            change_note=change_note,
        )

    def summary(self, run_id: str) -> dict[str, Any]:
        return self._repository.get_result(run_id)["summary"]

    def result(self, run_id: str) -> dict[str, Any]:
        return self._repository.get_result(run_id)

    def trades(self, run_id: str, *, page: int, page_size: int) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 250:
            raise ValueError("page 必須大於 0，page_size 必須介於 1 與 250")
        trades, total = self._repository.list_trades(run_id, offset=(page - 1) * page_size, limit=page_size)
        return {"page": page, "page_size": page_size, "total": total, "trades": trades}

    def trade(self, run_id: str, trade_id: str) -> dict[str, Any]:
        for trade in self._repository.get_result(run_id).get("trades", []):
            if trade["trade_id"] == trade_id:
                return trade
        raise KeyError(f"找不到交易紀錄：{trade_id}")

    def drawdown(self, run_id: str) -> list[dict[str, Any]]:
        """Return an explicit drawdown series rather than making the browser infer it."""
        points = self._repository.get_result(run_id).get("daily_equity", [])
        peak: float | None = None
        output: list[dict[str, Any]] = []
        for point in points:
            equity = float(point["equity"])
            peak = equity if peak is None else max(peak, equity)
            output.append(
                {
                    "date": point["date"],
                    "equity": equity,
                    "peak_equity": peak,
                    "drawdown": (peak - equity) / peak if peak else 0.0,
                }
            )
        return output

    def breakdowns(self, run_id: str) -> dict[str, Any]:
        """Server-side, bounded projections used by the result workspace."""
        result = self._repository.get_result(run_id)
        by_symbol: dict[str, dict[str, Any]] = {}
        for trade in result.get("trades", []):
            row = by_symbol.setdefault(
                str(trade["symbol"]),
                {"symbol": trade["symbol"], "closed_trades": 0, "wins": 0, "net_pnl": 0.0},
            )
            row["closed_trades"] += 1
            row["wins"] += int(float(trade["net_pnl"]) > 0)
            row["net_pnl"] += float(trade["net_pnl"])
        symbols = []
        for row in by_symbol.values():
            row["win_rate"] = row["wins"] / row["closed_trades"] if row["closed_trades"] else 0.0
            symbols.append(row)
        return {
            "symbols": sorted(symbols, key=lambda item: (-item["net_pnl"], item["symbol"])),
            "strategy_attribution": self.summary(run_id).get("strategy_attribution", []),
        }

    def trade_chart(self, run_id: str, trade_id: str, *, radius: int = 40) -> dict[str, Any]:
        """Return provider-independent historical bars and the two fill markers."""
        trade = self.trade(run_id, trade_id)
        run = self._repository.get_run(run_id)
        symbol_bars = [
            bar for bar in self._catalog.load_bars(run["dataset_id"])
            if bar.symbol == trade["symbol"]
        ]
        entry_at = datetime.fromisoformat(str(trade["entry"]["filled_at"]))
        exit_at = datetime.fromisoformat(str(trade["exit"]["filled_at"]))
        selected = [bar for bar in symbol_bars if entry_at <= bar.timestamp <= exit_at]
        if not selected:
            selected = symbol_bars
        start_index = max(0, symbol_bars.index(selected[0]) - radius)
        end_index = min(len(symbol_bars), symbol_bars.index(selected[-1]) + radius + 1)
        return {
            "trade_id": trade_id,
            "symbol": trade["symbol"],
            "bars": [bar.to_dict() for bar in symbol_bars[start_index:end_index]],
            "markers": [
                {"side": "ENTRY", "at": trade["entry"]["filled_at"], "price": trade["entry"]["price"]},
                {"side": "EXIT", "at": trade["exit"]["filled_at"], "price": trade["exit"]["price"]},
            ],
        }

    def export_trades(self, run_id: str) -> list[dict[str, Any]]:
        """Export from the immutable result, never from an active worker buffer."""
        return list(self._repository.get_result(run_id).get("trades", []))

    def strategy_attribution(self, run_id: str, side: str | None = None) -> list[dict[str, Any]]:
        rows = self.summary(run_id).get("strategy_attribution", [])
        if side is None:
            return rows
        normalized = side.strip().upper()
        return [row for row in rows if row["role"] in {normalized, "EVALUATION"}]

    def compare(self, baseline_run_id: str, challenger_run_id: str) -> dict[str, Any]:
        baseline = self._repository.get_run(baseline_run_id)
        challenger = self._repository.get_run(challenger_run_id)
        verify_run_identity(baseline)
        verify_run_identity(challenger)
        if baseline["status"] != RunStatus.COMPLETED.value or challenger["status"] != RunStatus.COMPLETED.value:
            raise ValueError("只有已完成的回測可以比較")
        comparison = compare_runs(
            baseline_run=baseline,
            challenger_run=challenger,
            baseline_result=self._repository.get_result(baseline_run_id),
            challenger_result=self._repository.get_result(challenger_run_id),
        )
        comparison["comparison_id"] = f"comparison-{uuid4().hex}"
        self._repository.save_comparison(comparison)
        return comparison

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        return self._repository.get_comparison(comparison_id)

    def qualify_runs(
        self,
        *,
        baseline_run_id: str,
        challenger_run_id: str,
        protocol: Mapping[str, Any],
        hypothesis_id: str,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        """Persist review-only qualification evidence for completed Atomic Runs."""

        self._require_enabled()
        create = getattr(self._repository, "create_qualification", None)
        if not isinstance(self._repository, PostgresBacktestRepository) or not callable(create):
            raise RuntimeError("Backtest Qualification 只允許寫入 PostgreSQL")
        actor = actor_id.strip()
        note = change_note.strip()
        if not actor:
            raise ValueError("actor_id 不可為空")
        if not note:
            raise ValueError("Qualification 必須填寫研究變更說明")
        hypothesis = hypothesis_id.strip()
        if not hypothesis:
            raise ValueError("hypothesis_id 不可為空")
        primary_window = EvaluationWindow.from_dict(protocol["primary_window"])
        walk_forward_windows = tuple(
            EvaluationWindow.from_dict(item)
            for item in protocol.get("walk_forward_windows", ())
        )
        request_document = {
            "baseline_run_id": baseline_run_id,
            "challenger_run_id": challenger_run_id,
            "hypothesis_id": hypothesis,
            "primary_window": primary_window.to_dict(),
            "walk_forward_windows": [
                item.to_dict() for item in walk_forward_windows
            ],
            "actor_id": actor,
            "change_note": note,
        }
        key = self._validate_idempotency_key(idempotency_key)
        request_digest = digest(request_document)
        replay = getattr(self._repository, "replay_qualification", None)
        if callable(replay):
            existing = replay(
                idempotency_key=key,
                request_digest=request_digest,
            )
            if existing is not None:
                return existing, True
        baseline = self._repository.get_run(baseline_run_id)
        challenger = self._repository.get_run(challenger_run_id)
        verify_run_identity(baseline)
        verify_run_identity(challenger)
        family = self._repository.get_experiment_family_for_run(challenger_run_id)
        selected_baseline_digest = research_baseline_identity_digest(baseline["config"])
        if family["research_baseline_digest"] != selected_baseline_digest:
            raise ValueError("Qualification Baseline 與 authoritative family 不一致")
        if family["family_id"] != experiment_family_id(selected_baseline_digest):
            raise ValueError("Experiment family identity 已漂移")
        if family["comparability_digest"] != comparability_contract_digest(
            baseline["config"]
        ):
            raise ValueError("Experiment family comparability identity 已漂移")
        current_attempt = next(
            (
                item
                for item in family["attempts"]
                if item["run_id"] == challenger_run_id
            ),
            None,
        )
        if current_attempt is None:
            raise ValueError("Challenger 不在 authoritative family history")
        resolved_protocol = QualificationProtocol(
            primary_window=primary_window,
            walk_forward_windows=walk_forward_windows,
            multiple_testing=MultipleTestingRecord(
                family_id=family["family_id"],
                hypothesis_id=hypothesis,
                attempt_number=int(current_attempt["attempt_sequence"]),
                planned_attempts=int(family["planned_attempts"]),
                baseline_run_id=baseline_run_id,
                research_baseline_digest=selected_baseline_digest,
                attempted_run_ids=tuple(
                    str(item["run_id"]) for item in family["attempts"]
                ),
                family_head_sequence=int(family["head_sequence"]),
                family_snapshot_digest=str(family["family_snapshot_digest"]),
                alpha=family["alpha"],
                adjustment_method=family["adjustment_method"],
            ),
            policy=QualificationPolicy.from_dict(family["policy"]),
        )
        attempted = [
            self._repository.get_run(run_id)
            for run_id in resolved_protocol.multiple_testing.attempted_run_ids
        ]
        for run in attempted:
            verify_run_identity(run)
        selected = (baseline, challenger)
        results_by_id: dict[str, dict[str, Any]] = {}
        for run in selected:
            if run["status"] != RunStatus.COMPLETED.value:
                raise ValueError(f"只有已完成的 Run 可以 qualification：{run['run_id']}")
            result = self._repository.get_result(run["run_id"])
            result_digest = result.get("summary", {}).get("result_digest")
            if not result_digest or result_digest != run.get("result_digest"):
                raise ValueError(f"Run result digest 不一致：{run['run_id']}")
            summary_without_digest = dict(result.get("summary", {}))
            summary_without_digest.pop("result_digest", None)
            recomputed = digest(
                {
                    "summary": summary_without_digest,
                    "trades": list(result.get("trades", [])),
                    "equity": list(result.get("daily_equity", [])),
                    "decisions": list(result.get("decisions", [])),
                }
            )
            if recomputed != result_digest:
                raise ValueError(f"Run immutable result 內容與 digest 不一致：{run['run_id']}")
            results_by_id[str(run["run_id"])] = result
        if baseline["dataset_id"] != challenger["dataset_id"]:
            raise ValueError("Baseline 與 Challenger 必須使用同一資料集")
        dataset = self._repository.get_dataset(baseline["dataset_id"])
        try:
            verified_manifest = DatasetManifest.from_dict(dataset)
        except Exception as error:
            raise ValueError("目前資料集 manifest 無法驗證") from error
        if verified_manifest.manifest_digest != str(dataset.get("manifest_digest")):
            raise ValueError("目前資料集 manifest 內容與 digest 不一致")
        if verified_manifest.manifest_digest != str(baseline["dataset_digest"]):
            raise ValueError("目前資料集 manifest 與 Run Snapshot digest 不一致")
        evidence = build_qualification_evidence(
            baseline_run=baseline,
            challenger_run=challenger,
            baseline_result=results_by_id[baseline_run_id],
            challenger_result=results_by_id[challenger_run_id],
            attempted_runs=attempted,
            protocol=resolved_protocol,
            dataset_research_eligible=verified_manifest.research_eligible,
            dataset_start_date=date.fromisoformat(verified_manifest.start_date),
            dataset_end_date=date.fromisoformat(verified_manifest.end_date),
        )
        qualification_id = f"qualification-{uuid5(NAMESPACE_URL, f'tw-intraday-trader:qualification:{key}').hex}"
        return create(
            {
                "qualification_id": qualification_id,
                "idempotency_key": key,
                "request_digest": request_digest,
                "request": request_document,
                "baseline_run_id": baseline_run_id,
                "challenger_run_id": challenger_run_id,
                "protocol_digest": resolved_protocol.protocol_digest,
                "protocol": resolved_protocol.to_dict(),
                "evidence_digest": evidence["evidence_digest"],
                "evidence": evidence,
                "verdict": evidence["verdict"],
                "actor_id": actor,
                "change_note": note,
                "hypothesis_id": hypothesis,
                "family_id": family["family_id"],
                "attempt_number": current_attempt["attempt_sequence"],
                "family_head_sequence": family["head_sequence"],
                "family_snapshot_digest": family["family_snapshot_digest"],
                "family_snapshot": family,
                "created_at": _now(),
            }
        )

    def list_qualifications(self, *, limit: int = 100) -> list[dict[str, Any]]:
        read = getattr(self._repository, "list_qualifications", None)
        if not isinstance(self._repository, PostgresBacktestRepository) or not callable(read):
            raise RuntimeError("Backtest Qualification 只允許讀取 PostgreSQL")
        return read(limit=limit)

    def get_qualification(self, qualification_id: str) -> dict[str, Any]:
        read = getattr(self._repository, "get_qualification", None)
        if not isinstance(self._repository, PostgresBacktestRepository) or not callable(read):
            raise RuntimeError("Backtest Qualification 只允許讀取 PostgreSQL")
        return read(qualification_id)

    def _run_dataset_sync(self, job_id: str, years: int, symbols: list[str] | None, symbol_limit: int | None) -> None:
        if self._repository.get_job(job_id)["status"] == RunStatus.CANCELLING.value:
            self._repository.update_job(job_id, status=RunStatus.CANCELLED.value, progress_message="資料集工作已取消")
            return
        self._repository.update_job(job_id, status=RunStatus.RUNNING.value, progress_message="正在取得歷史 Kbar")
        try:
            manifest = self._catalog.collect_from_provider(
                self._provider,
                years=years,
                symbols=symbols,
                symbol_limit=symbol_limit,
                progress=lambda value, message: self._repository.update_job(job_id, progress=value, progress_message=message),
                cancelled=lambda: self._repository.get_job(job_id)["status"] == RunStatus.CANCELLING.value,
            )
            self._repository.upsert_dataset(manifest.to_dict(), "READY")
            self._repository.update_job(job_id, status=RunStatus.COMPLETED.value, resource_id=manifest.dataset_id, progress=1.0, progress_message="歷史資料集已封存")
        except DatasetCancelled:
            self._repository.update_job(job_id, status=RunStatus.CANCELLED.value, progress_message="資料集工作已取消")
        except Exception as error:
            self._repository.update_job(job_id, status=RunStatus.FAILED.value, error_message=str(error), progress_message="資料集工作失敗")

    def _run_incremental_sync(self, job_id: str) -> None:
        try:
            self._incremental_sync.run(job_id)
        except DatasetCancelled:
            pass
        except Exception:
            # IncrementalHistoricalSync records the durable FAILED status and
            # exact error before returning control to this worker boundary.
            pass

    def _run_backtest(self, run_id: str) -> None:
        progress_reporter: ThrottledProgressReporter | None = None
        try:
            self._transition_run_or_cancel(
                run_id,
                expected_statuses=(RunStatus.QUEUED.value,),
                status=RunStatus.PREFLIGHT.value,
                progress_message="正在驗證資料集與策略版本",
            )
            run = self._repository.get_run(run_id)
            config = BacktestRunConfig.from_dict(run["config"])
            runtime_registry = self._registry
            runtime_engine = self._engine
            resolution = None
            stored_atomic: dict[str, Any] | None = None
            if config.atomic_strategy_run_snapshot is not None:
                stored_atomic = dict(config.atomic_strategy_run_snapshot)
                snapshot = ExactStrategySetSnapshot.from_dict(dict(stored_atomic["strategy_set"]))
                resolution = resolve_atomic_entry_set(
                    self._require_atomic_repository(),
                    self._atomic_registry,
                    snapshot,
                )
                runtime_registry = resolution.registry
                runtime_engine = HistoricalBacktestEngine(runtime_registry)
            dataset, amount_contract = self._verified_atomic_dataset(
                config.dataset_id,
                config.strategy_set,
                registry=runtime_registry,
                resolution=resolution,
            )
            if str(dataset["manifest_digest"]) != config.dataset_digest:
                raise ValueError("歷史資料集 manifest digest 已變更，拒絕執行回測")
            if stored_atomic is not None and resolution is not None:
                resolution = self._resolve_bound_atomic_entry_set(
                    snapshot,
                    amount_contract=amount_contract,
                )
                runtime_registry = resolution.registry
                runtime_engine = HistoricalBacktestEngine(runtime_registry)
                expected_atomic = (
                    bind_dataset_feature_evidence(
                        resolution.run_snapshot,
                        dataset_id=config.dataset_id,
                        dataset_digest=config.dataset_digest,
                        amount_contract=amount_contract,
                    )
                    if "dataset_feature_evidence" in stored_atomic
                    else resolution.run_snapshot
                )
                if expected_atomic != stored_atomic:
                    raise ValueError("atomic backtest run snapshot 已與目前可重建證據不一致")
                if (
                    config.dataset_amount_contract is not None
                    and dict(config.dataset_amount_contract) != amount_contract
                ):
                    raise ValueError("Atomic Run Dataset amount evidence 已漂移")
            manifest = self._catalog.get_manifest(config.dataset_id)
            bars = self._catalog.iter_bars_ordered(config.dataset_id)
            terminal_timestamps = self._catalog.symbol_last_timestamps(
                config.dataset_id
            )
            self._transition_run_or_cancel(
                run_id,
                expected_statuses=(RunStatus.PREFLIGHT.value,),
                status=RunStatus.RUNNING.value,
                progress_message="正在執行 deterministic Kbar 回測",
            )
            progress_reporter = ThrottledProgressReporter(
                self._repository,
                run_id,
            )
            control_probe = DurableRunControlProbe(
                self._repository,
                run_id,
            )
            engine_result = runtime_engine.run(
                config=config,
                bars=bars,
                progress=progress_reporter,
                cancelled=control_probe,
                bars_are_ordered=True,
                total_bars=manifest.bar_count,
                terminal_timestamp_by_symbol=terminal_timestamps,
            )
            progress_reporter.flush()
            raw_result = engine_result.to_dict()
            summary = summarize_run(
                config=config,
                result=engine_result,
                dataset_research_eligible=bool(dataset["research_eligible"]),
                dataset_issues=tuple(dataset.get("issues", ())),
            )
            stored = {**raw_result, "summary": summary}
            self._repository.save_result(run_id, stored)
            self._persist_terminal_run(
                run_id,
                progress_reporter=progress_reporter,
                status=RunStatus.COMPLETED.value,
                progress=1.0,
                progress_message="回測完成",
                result_digest=summary["result_digest"],
            )
        except BacktestCancelled:
            self._persist_terminal_run(
                run_id,
                progress_reporter=progress_reporter,
                status=RunStatus.CANCELLED.value,
                progress_message="回測已取消",
            )
        except Exception as error:
            self._persist_terminal_run(
                run_id,
                progress_reporter=progress_reporter,
                status=RunStatus.FAILED.value,
                error_message=str(error),
                progress_message="回測失敗",
            )

    def _persist_terminal_run(
        self,
        run_id: str,
        *,
        progress_reporter: ThrottledProgressReporter | None,
        **changes: Any,
    ) -> None:
        """Survive a bounded PostgreSQL restart without leaving RUNNING state."""

        last_error: Exception | None = None
        for delay in (0.0, 0.1, 0.25, 0.5, 1.0, 2.0):
            if delay:
                sleep(delay)
            try:
                if progress_reporter is not None:
                    progress_reporter.flush()
                self._repository.update_run(run_id, **changes)
                return
            except Exception as error:
                last_error = error
        assert last_error is not None
        raise last_error

    def _create_from_config(
        self,
        *,
        config: Mapping[str, Any],
        idempotency_key: str,
        parent_run_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
        if config.get("atomic_strategy_run_snapshot") is not None:
            atomic_config = deepcopy(dict(config))
            atomic_config["parent_run_id"] = parent_run_id
            atomic_config["change_note"] = change_note
            atomic_config.pop("atomic_run_request", None)
            atomic_config.pop("atomic_run_request_digest", None)
            parsed = BacktestRunConfig.from_dict(atomic_config)
            stored_atomic = dict(parsed.atomic_strategy_run_snapshot or {})
            snapshot = ExactStrategySetSnapshot.from_dict(
                dict(stored_atomic["strategy_set"])
            )
            resolution = resolve_atomic_entry_set(
                self._require_atomic_repository(),
                self._atomic_registry,
                snapshot,
            )
            if resolution.engine_strategy_set != parsed.strategy_set:
                raise ValueError("atomic backtest strategy set 已與 Run Snapshot 不一致")
            dataset, amount_contract = self._verified_atomic_dataset(
                parsed.dataset_id,
                parsed.strategy_set,
                registry=resolution.registry,
                resolution=resolution,
            )
            resolution = self._resolve_bound_atomic_entry_set(
                snapshot,
                amount_contract=amount_contract,
            )
            if str(dataset["manifest_digest"]) != parsed.dataset_digest:
                raise ValueError("歷史資料集 manifest digest 已變更，拒絕建立回測")
            expected_atomic = (
                bind_dataset_feature_evidence(
                    resolution.run_snapshot,
                    dataset_id=parsed.dataset_id,
                    dataset_digest=parsed.dataset_digest,
                    amount_contract=amount_contract,
                )
                if "dataset_feature_evidence" in stored_atomic
                else resolution.run_snapshot
            )
            if expected_atomic != stored_atomic:
                raise ValueError("atomic backtest run snapshot 已與目前可重建證據不一致")
            if (
                parsed.dataset_amount_contract is not None
                and dict(parsed.dataset_amount_contract) != amount_contract
            ):
                raise ValueError("Atomic Run Dataset amount evidence 已漂移")
            record = {
                "run_id": f"run-{uuid4().hex}",
                "idempotency_key": self._validate_idempotency_key(idempotency_key),
                "status": RunStatus.QUEUED.value,
                "config": parsed.to_dict(),
                "config_digest": parsed.config_digest,
                "dataset_id": parsed.dataset_id,
                "dataset_digest": parsed.dataset_digest,
                "created_at": _now(),
            }
            run, idempotent = self._repository.create_run(record)
            if not idempotent:
                self._executor.submit(self._run_backtest, run["run_id"])
            return run, idempotent
        strategy_set = dict(config["strategy_set"])
        return self.create_run(
            dataset_id=str(config["dataset_id"]),
            entry_strategy_ids=list(strategy_set["entry_strategy_ids"]),
            exit_strategy_ids=list(strategy_set["exit_strategy_ids"]),
            entry_policy=str(strategy_set.get("entry_policy", "ANY")),
            exit_policy=str(strategy_set.get("exit_policy", "ANY")),
            entry_min_trigger_count=int(strategy_set.get("entry_min_trigger_count", 1)),
            exit_min_trigger_count=int(strategy_set.get("exit_min_trigger_count", 1)),
            priority_order=list(strategy_set.get("priority_order", ())),
            starting_cash=str(config.get("starting_cash", backtest_settings.BACKTEST_DEFAULT_STARTING_CASH)),
            position_fraction=str(config.get("position_fraction", backtest_settings.BACKTEST_DEFAULT_POSITION_FRACTION)),
            commission_rate=str(config.get("commission_rate", backtest_settings.BACKTEST_DEFAULT_COMMISSION_RATE)),
            sell_tax_rate=str(config.get("sell_tax_rate", backtest_settings.BACKTEST_DEFAULT_SELL_TAX_RATE)),
            slippage_bps=str(config.get("slippage_bps", backtest_settings.BACKTEST_DEFAULT_SLIPPAGE_BPS)),
            target_win_rate=str(config.get("target_win_rate", "0.50")),
            minimum_oos_trades=int(config.get("minimum_oos_trades", 30)),
            max_drawdown_guardrail=str(config.get("max_drawdown_guardrail", "0.20")),
            engine_version=str(config.get("engine_version", "backtest-engine-v1")),
            idempotency_key=idempotency_key,
            experiment_id=config.get("experiment_id"),
            baseline_run_id=config.get("baseline_run_id"),
            parent_run_id=parent_run_id,
            change_note=change_note,
        )

    def _validate_strategy_selection(
        self,
        strategy_set: StrategySetSnapshot,
        dataset: Mapping[str, Any] | None = None,
        *,
        registry: StrategyRegistry | None = None,
    ) -> None:
        selected_registry = registry or self._registry
        definitions = []
        for strategy_id in strategy_set.entry_strategy_ids:
            definition = selected_registry.definition(strategy_id)
            if definition.side.value != "ENTRY":
                raise ValueError(f"{strategy_id} 不是買入策略")
            definitions.append(definition)
        for strategy_id in strategy_set.exit_strategy_ids:
            definition = selected_registry.definition(strategy_id)
            if definition.side.value != "EXIT":
                raise ValueError(f"{strategy_id} 不是賣出策略")
            definitions.append(definition)
        if dataset is None:
            return
        available = {
            str(capability).strip().upper()
            for capability in dataset.get("capabilities", ())
        }
        for definition in definitions:
            missing = sorted(set(definition.required_capabilities) - available)
            if missing:
                raise ValueError(
                    f"資料集缺少 {definition.strategy_id} 所需能力：{'、'.join(missing)}"
                )

    def _verified_atomic_dataset(
        self,
        dataset_id: str,
        strategy_set: StrategySetSnapshot,
        *,
        registry: StrategyRegistry,
        resolution: Any | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        dataset = self._repository.get_dataset(dataset_id)
        if dataset["status"] != "READY":
            raise ValueError("歷史資料集尚未 READY，不能建立或執行回測")
        registered_manifest = DatasetManifest.from_dict(dataset).to_dict()
        manifest = self._catalog.get_manifest(dataset_id)
        if manifest.to_dict() != registered_manifest:
            raise DatasetBindingIntegrityError(
                "PostgreSQL Dataset 與 filesystem manifest 不一致"
            )
        self._validate_strategy_selection(strategy_set, dataset, registry=registry)
        raw_amount = dataset.get("amount_contract")
        amount_contract = dict(raw_amount) if isinstance(raw_amount, Mapping) else None
        if amount_contract is not None:
            stored_digest = str(amount_contract.get("digest") or "")
            amount_body = dict(amount_contract)
            amount_body.pop("digest", None)
            if not stored_digest or digest(amount_body) != stored_digest:
                raise ValueError("Dataset amount contract digest 不一致")
        requires_vwap = bool(
            resolution is not None
            and any(
                request.get("feature_id") == "vwap_session_v1"
                for strategy in resolution.feature_requests
                for request in strategy.get("requests", ())
                if isinstance(request, Mapping)
            )
        )
        if requires_vwap:
            amount_contract = verify_vwap_amount_contract(amount_contract)
        return dataset, amount_contract

    @staticmethod
    def _atomic_run_request_document(
        *,
        strategy_set_version_id: str,
        starting_cash: str,
        position_fraction: str,
        commission_rate: str,
        sell_tax_rate: str,
        slippage_bps: str,
        target_win_rate: str,
        minimum_oos_trades: int,
        max_drawdown_guardrail: str,
        change_note: str,
        baseline_run_id: str | None,
        expected_binding_revision: int | None,
        expected_dataset_digest: str | None,
    ) -> dict[str, Any]:
        return {
            "contract_version": "atomic-backtest-run-request-v1",
            "strategy_set_version_id": str(strategy_set_version_id),
            "starting_cash": str(starting_cash),
            "position_fraction": str(position_fraction),
            "commission_rate": str(commission_rate),
            "sell_tax_rate": str(sell_tax_rate),
            "slippage_bps": str(slippage_bps),
            "target_win_rate": str(target_win_rate),
            "minimum_oos_trades": int(minimum_oos_trades),
            "max_drawdown_guardrail": str(max_drawdown_guardrail),
            "change_note": str(change_note),
            "baseline_run_id": baseline_run_id,
            "expected_binding_revision": expected_binding_revision,
            "expected_dataset_digest": expected_dataset_digest,
        }

    @staticmethod
    def _validate_idempotency_key(value: str) -> str:
        normalized = value.strip()
        if not 8 <= len(normalized) <= 200:
            raise ValueError("idempotency_key 長度必須介於 8 與 200")
        return normalized

    def _require_atomic_repository(self) -> AtomicStrategyRepository:
        if self._atomic_repository is None:
            raise RuntimeError("atomic Strategy Set 回測只支援 PostgreSQL；目前不可用")
        return self._atomic_repository

    def _resolve_bound_atomic_entry_set(
        self,
        snapshot: ExactStrategySetSnapshot,
        *,
        amount_contract: Mapping[str, Any] | None,
    ):
        return resolve_atomic_entry_set(
            self._require_atomic_repository(),
            self._atomic_registry,
            snapshot,
            dataset_amount_contract=amount_contract,
            require_dataset_amount_contract=True,
        )

    @staticmethod
    def _require_enabled() -> None:
        if not backtest_settings.BACKTEST_ENABLED:
            raise RuntimeError("歷史回測功能目前未啟用")

    @staticmethod
    def _job_is_fresh(job: Mapping[str, Any]) -> bool:
        updated_at = datetime.fromisoformat(str(job["updated_at"]))
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=_TAIPEI)
        age = datetime.now(_TAIPEI) - updated_at.astimezone(_TAIPEI)
        return age <= timedelta(minutes=backtest_settings.BACKTEST_ACTIVE_JOB_STALE_MINUTES)

    def _transition_run_or_cancel(
        self,
        run_id: str,
        *,
        expected_statuses: tuple[str, ...],
        status: str,
        progress_message: str,
    ) -> None:
        run, changed = self._repository.transition_run_status(
            run_id,
            expected_statuses=expected_statuses,
            status=status,
            progress_message=progress_message,
        )
        if changed:
            return
        if run["status"] == RunStatus.CANCELLING.value:
            raise BacktestCancelled("回測工作已取消")
        raise RuntimeError(
            f"回測狀態轉換衝突：預期 {expected_statuses}，實際 {run['status']}"
        )


def _now() -> str:
    return datetime.now(_TAIPEI).isoformat()


def _deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(base))
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(output.get(key), Mapping):
            output[key] = _deep_merge(output[key], value)
        else:
            output[key] = value
    return output
