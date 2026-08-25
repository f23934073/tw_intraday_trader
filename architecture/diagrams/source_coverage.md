# Source Coverage Matrix

```text
source_snapshot: main@657c3bbc117af1c2909175dfc799bce7e8be07ca
captured_at: 2026-08-25T11:25:47+0800
```

## Package Inventory

`pyproject.toml` 的 installable package 清單是 coverage 的主 inventory source：[pyproject.toml](../../pyproject.toml)。

| Package | Covered by diagrams | Source anchors |
| --- | --- | --- |
| `market_data` | 01, 02, 06, 08, 09, 15, 20, 21 | [provider.py](../../market_data/provider.py), [events.py](../../market_data/events.py), [ingestion.py](../../market_data/ingestion.py), [journal.py](../../market_data/journal.py), [replay.py](../../market_data/replay.py), [shioaji_momentum_stream.py](../../market_data/shioaji_momentum_stream.py) |
| `candidate` | 03, 07, 08, 16 | [engine.py](../../candidate/engine.py), [pool.py](../../candidate/pool.py), [shadow_admission.py](../../candidate/shadow_admission.py) |
| `scoring` | 03, 07, 10 | [engine.py](../../scoring/engine.py), [rules.py](../../scoring/rules.py) |
| `position` | 03, 07, 11 | [manager.py](../../position/manager.py), [exit_rules.py](../../position/exit_rules.py) |
| `config` | 04, 05, 12, 13, 15, 21 | [backtest.py](../../config/backtest.py), [trading_persistence.py](../../config/trading_persistence.py), [momentum_stream.py](../../config/momentum_stream.py), [premarket.py](../../config/premarket.py), [local_paper.py](../../config/local_paper.py) |
| `dashboard` | 02, 05, 06, 09, 10, 11, 12, 14, 21 | [server.py](../../dashboard/server.py), [service.py](../../dashboard/service.py), [momentum.py](../../dashboard/momentum.py), [momentum_stream.py](../../dashboard/momentum_stream.py), [static/js/app.js](../../dashboard/static/js/app.js) |
| `runtime` | 02, 05, 08, 11, 20, 21 | [composition.py](../../runtime/composition.py), [momentum_shadow.py](../../runtime/momentum_shadow.py), [trade_management_shadow.py](../../runtime/trade_management_shadow.py), [trade_management_live_capture.py](../../runtime/trade_management_live_capture.py), [trading_persistence.py](../../runtime/trading_persistence.py) |
| `simulation` | 04, 11, 12, 17 | [application.py](../../simulation/application.py), [service.py](../../simulation/service.py), [continuous_strategy.py](../../simulation/continuous_strategy.py), [atomic_runtime.py](../../simulation/atomic_runtime.py), [strategy_flow.py](../../simulation/strategy_flow.py), [settings.py](../../simulation/settings.py) |
| `signals` | 08, 09, 12 | [momentum.py](../../signals/momentum.py), [models.py](../../signals/models.py), [projection.py](../../signals/projection.py), [momentum_state.py](../../signals/momentum_state.py) |
| `trading` | 04, 11, 17, 20 | [journal.py](../../trading/journal.py), [risk.py](../../trading/risk.py), [local_paper.py](../../trading/local_paper.py), [trade_management_shadow.py](../../trading/trade_management_shadow.py), [trade_management_replay.py](../../trading/trade_management_replay.py), [shadow_evidence_journal.py](../../trading/shadow_evidence_journal.py) |
| `features` | 08, 09, 12 | [engine.py](../../features/engine.py), [specifications.py](../../features/specifications.py), [bollinger.py](../../features/bollinger.py), [ema.py](../../features/ema.py), [opening_range.py](../../features/opening_range.py), [rolling.py](../../features/rolling.py), [rsi.py](../../features/rsi.py) |
| `backtest` | 02, 05, 13, 14, 18, 21 | [application.py](../../backtest/application.py), [engine.py](../../backtest/engine.py), [dataset.py](../../backtest/dataset.py), [finmind_history.py](../../backtest/finmind_history.py), [scheduler.py](../../backtest/scheduler.py), [postgres_repository.py](../../backtest/postgres_repository.py), [sqlite_repository.py](../../backtest/sqlite_repository.py), [qualification.py](../../backtest/qualification.py) |
| `strategy_catalog` | 10, 12, 14, 18 | [application.py](../../strategy_catalog/application.py), [service.py](../../strategy_catalog/service.py), [lifecycle.py](../../strategy_catalog/lifecycle.py), [sets.py](../../strategy_catalog/sets.py), [postgres_repository.py](../../strategy_catalog/postgres_repository.py), [paper_activation.py](../../strategy_catalog/paper_activation.py) |
| `atomic_strategies` | 09, 10, 12, 14 | [registry.py](../../atomic_strategies/registry.py), [protocol.py](../../atomic_strategies/protocol.py), [feature_requests.py](../../atomic_strategies/feature_requests.py), [entries](../../atomic_strategies/entries) |
| `premarket` | 06, 15, 21 | [service.py](../../premarket/service.py), [qualification.py](../../premarket/qualification.py), [taifex_reconciliation.py](../../premarket/taifex_reconciliation.py), [artifacts.py](../../premarket/artifacts.py), [calendar.py](../../premarket/calendar.py) |
| `institutional_data` | 16, 19 | [application.py](../../institutional_data/application.py), [sources.py](../../institutional_data/sources.py), [artifacts.py](../../institutional_data/artifacts.py), [validation.py](../../institutional_data/validation.py) |
| `institutional_research` | 16, 19 | [application.py](../../institutional_research/application.py), [inputs.py](../../institutional_research/inputs.py), [domain.py](../../institutional_research/domain.py), [evaluation/application.py](../../institutional_research/evaluation/application.py) |
| `institutional_prior` | 16, 19 | [application.py](../../institutional_prior/application.py), [domain.py](../../institutional_prior/domain.py), [repository.py](../../institutional_prior/repository.py), [sql_repository.py](../../institutional_prior/sql_repository.py), [migrations/001_candidate_prior.sql](../../institutional_prior/migrations/001_candidate_prior.sql) |
| `watchlist` | 07, 16 | [reference_data.py](../../watchlist/reference_data.py), [import_adapter.py](../../watchlist/import_adapter.py), [serialization.py](../../watchlist/serialization.py) |

## Entrypoint And Runtime Coverage

| Entrypoint/runtime | Covered by diagrams | Source anchors |
| --- | --- | --- |
| `app.py` synchronous scanner | 02, 05, 07 | [app.py::main/run_scan/build_provider](../../app.py) |
| `python -m dashboard` / `dashboard.server` FastAPI runtime | 02, 05, 06, 11, 12, 14, 21 | [dashboard/__main__.py](../../dashboard/__main__.py), [dashboard/server.py](../../dashboard/server.py) |
| `runtime.composition` Local Paper composition root | 02, 05, 11, 17 | [runtime/composition.py::RuntimeComposition.create](../../runtime/composition.py) |
| Realtime market-data / Momentum worker | 02, 06, 08, 09 | [dashboard/momentum.py::create_realtime_momentum_dashboard_service](../../dashboard/momentum.py), [runtime/momentum_shadow.py::MomentumShadowRuntime](../../runtime/momentum_shadow.py), [market_data/shioaji_momentum_stream.py](../../market_data/shioaji_momentum_stream.py) |
| Historical Backtest composition / workers / scheduler | 02, 05, 13, 14, 18, 21 | [backtest/application.py::BacktestApplicationService](../../backtest/application.py), [backtest/engine.py::HistoricalBacktestEngine](../../backtest/engine.py), [backtest/scheduler.py::AfterCloseIncrementalScheduler](../../backtest/scheduler.py) |
| Acquisition CLIs | 13, 15, 16 | [download_finmind_sponsor_history.py](../../scripts/download_finmind_sponsor_history.py), [download_backtest_history.py](../../scripts/download_backtest_history.py), [capture_finmind_institutional_mvp.py](../../scripts/capture_finmind_institutional_mvp.py), [capture_taifex_night_context.py](../../scripts/capture_taifex_night_context.py) |
| Qualification CLIs | 08, 13, 15, 20, 21 | [capture_quote_freshness.py](../../scripts/capture_quote_freshness.py), [qualify_shioaji_daily_kbar_g0.py](../../scripts/qualify_shioaji_daily_kbar_g0.py), [capture_taifex_night_qualification.py](../../scripts/capture_taifex_night_qualification.py), [preflight_trade_management_shadow.py](../../scripts/preflight_trade_management_shadow.py) |
| Replay CLIs | 08, 09, 20 | [replay_momentum_signal.py](../../scripts/replay_momentum_signal.py), [market_data/replay_cli.py](../../market_data/replay_cli.py), [trading/trade_management_replay.py](../../trading/trade_management_replay.py) |
| Migration CLIs | 14, 17, 18, 19 | [migrate_backtest_sqlite_to_postgres.py](../../scripts/migrate_backtest_sqlite_to_postgres.py), [backtest/migrations.py](../../backtest/migrations.py), [trading/migrations.py](../../trading/migrations.py), [institutional_prior/migrations.py](../../institutional_prior/migrations.py) |

## External Systems And Stores

| System/store | Covered by diagrams | Authority and durability notes |
| --- | --- | --- |
| Browser | 01, 06, 10, 11, 12, 14, 21 | Loopback UI/API client only; strategy mutations use Origin/CSRF checks. |
| Shioaji | 01, 02, 06, 08, 09, 11, 15, 20, 21 | Market data adapter; current source logs in with `subscribe_trade=False` for Momentum; no CA, no `place_order`, no trade callback path is wired. |
| FinMind | 01, 13, 16 | Acquisition/research source; token stays in environment and is not represented as an artifact. |
| TWSE | 01, 07, 13, 16, 21 | Market/reference and official source boundary, depending on flow. |
| TPEX | 01, 13, 16 | Market/reference and institutional source boundary. |
| TAIFEX | 01, 06, 15, 21 | Night-session context and official reconciliation source; observe-only. |
| PostgreSQL logical schemas | 01, 11, 13, 14, 17, 18, 19, 21 | `trading`, `backtest`, and institutional prior stores have separate authority and migration paths. |
| SQLite acquisition/local-dev stores | 13, 14, 18, 19 | FinMind `history.sqlite3` is mutable acquisition storage; backtest SQLite is local-dev durable repository, not the PostgreSQL promotion authority. |
| Filesystem immutable artifacts | 08, 13, 15, 16, 19, 20 | JSON/JSONL evidence, manifests, replay datasets, premarket and institutional artifacts; digest checked where implemented. |
| Process-local memory | 02, 04, 06, 08, 11, 12, 17, 21 | Runtime projection/cache/control state only; no cross-process recovery unless backed by a durable repository. |
