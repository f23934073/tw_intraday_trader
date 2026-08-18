"""Application service for durable, data-only historical-backtest jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from backtest.dataset import DatasetCancelled, HistoricalDatasetCatalog
from backtest.domain import (
    AggregationPolicy,
    BacktestRunConfig,
    RunStatus,
    StrategySetSnapshot,
)
from backtest.engine import BacktestCancelled, HistoricalBacktestEngine
from backtest.historical_download import IncrementalHistoricalSync
from backtest.metrics import compare_runs, summarize_run
from backtest.postgres_repository import PostgresBacktestRepository
from backtest.repository import BacktestRepository
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyRegistry
from config import backtest as backtest_settings
from market_data.provider import MarketDataProvider
from strategy_catalog.service import StrategyCatalogService


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
        workers: int = backtest_settings.BACKTEST_WORKERS,
    ) -> None:
        self._provider = provider
        self._registry = registry or StrategyRegistry()
        self._catalog = catalog or HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
        self._repository = repository or self._build_repository()
        self._strategy_catalog = StrategyCatalogService(self._repository, self._registry)
        self._engine = engine or HistoricalBacktestEngine(self._registry)
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
        if database_url.startswith(("postgres://", "postgresql://")):
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as error:
                raise RuntimeError(
                    "使用 PostgreSQL 回測資料庫前，請安裝 tw-intraday-trader[postgres]"
                ) from error
            return PostgresBacktestRepository(psycopg.connect(database_url))
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
            "database": "PostgreSQL" if backtest_settings.BACKTEST_DATABASE_URL.startswith(("postgres://", "postgresql://")) else "SQLite（本機開發）",
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
        self._validate_strategy_selection(strategy_set)
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

    def list_runs(self) -> list[dict[str, Any]]:
        return self._repository.list_runs()

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._repository.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        run = self._repository.get_run(run_id)
        if run["status"] not in {RunStatus.QUEUED.value, RunStatus.PREFLIGHT.value, RunStatus.RUNNING.value}:
            raise ValueError("只有尚未完成的回測可以取消")
        return self._repository.update_run(run_id, status=RunStatus.CANCELLING.value, progress_message="正在取消，會在下一個安全事件邊界停止")

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
        try:
            self._raise_if_run_cancelling(run_id)
            self._repository.update_run(run_id, status=RunStatus.PREFLIGHT.value, progress_message="正在驗證資料集與策略版本")
            run = self._repository.get_run(run_id)
            config = BacktestRunConfig.from_dict(run["config"])
            dataset = self._repository.get_dataset(config.dataset_id)
            bars = self._catalog.load_bars(config.dataset_id)
            self._raise_if_run_cancelling(run_id)
            self._repository.update_run(run_id, status=RunStatus.RUNNING.value, progress_message="正在執行 deterministic Kbar 回測")
            engine_result = self._engine.run(
                config=config,
                bars=bars,
                progress=lambda value, message: self._repository.update_run(run_id, progress=value, progress_message=message),
                cancelled=lambda: self._repository.get_run(run_id)["status"] == RunStatus.CANCELLING.value,
            )
            raw_result = engine_result.to_dict()
            summary = summarize_run(
                config=config,
                result=engine_result,
                dataset_research_eligible=bool(dataset["research_eligible"]),
                dataset_issues=tuple(dataset.get("issues", ())),
            )
            stored = {**raw_result, "summary": summary}
            self._repository.save_result(run_id, stored)
            self._repository.update_run(run_id, status=RunStatus.COMPLETED.value, progress=1.0, progress_message="回測完成", result_digest=summary["result_digest"])
        except BacktestCancelled:
            self._repository.update_run(run_id, status=RunStatus.CANCELLED.value, progress_message="回測已取消")
        except Exception as error:
            self._repository.update_run(run_id, status=RunStatus.FAILED.value, error_message=str(error), progress_message="回測失敗")

    def _create_from_config(
        self,
        *,
        config: Mapping[str, Any],
        idempotency_key: str,
        parent_run_id: str,
        change_note: str,
    ) -> tuple[dict[str, Any], bool]:
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
            idempotency_key=idempotency_key,
            experiment_id=config.get("experiment_id"),
            baseline_run_id=config.get("baseline_run_id"),
            parent_run_id=parent_run_id,
            change_note=change_note,
        )

    def _validate_strategy_selection(self, strategy_set: StrategySetSnapshot) -> None:
        for strategy_id in strategy_set.entry_strategy_ids:
            if self._registry.definition(strategy_id).side.value != "ENTRY":
                raise ValueError(f"{strategy_id} 不是買入策略")
        for strategy_id in strategy_set.exit_strategy_ids:
            if self._registry.definition(strategy_id).side.value != "EXIT":
                raise ValueError(f"{strategy_id} 不是賣出策略")

    @staticmethod
    def _validate_idempotency_key(value: str) -> str:
        normalized = value.strip()
        if not 8 <= len(normalized) <= 200:
            raise ValueError("idempotency_key 長度必須介於 8 與 200")
        return normalized

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

    def _raise_if_run_cancelling(self, run_id: str) -> None:
        if self._repository.get_run(run_id)["status"] == RunStatus.CANCELLING.value:
            raise BacktestCancelled("回測工作已取消")


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
