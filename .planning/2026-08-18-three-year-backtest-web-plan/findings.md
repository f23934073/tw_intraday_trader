# Findings: Three-year historical backtest web workflow

## Confirmed context

- The current project has historical Kbar display and deterministic replay foundations, but the existing replay output is alert-only rather than portfolio-performance backtesting.
- Existing dashboard provider access and decision calculations are server-side; this boundary should remain.
- A credible result must distinguish strategy correctness from market-data coverage and execution-model assumptions.

## Research log

- The worktree is heavily modified by existing/concurrent work. This plan must not overwrite or normalize those changes; it will add planning documentation only.
- Current package areas already include `market_data/replay.py`, `features/`, `signals/`, `simulation/`, `trading/`, FastAPI routes, and a Vanilla JavaScript dashboard.
- Existing replay tests and `scripts/replay_momentum_signal.py` prove deterministic signal replay, but searches show no historical backtest portfolio engine or performance-report aggregate.
- `SimulationService` currently supports long-only local paper orders and projections, but README explicitly says it omits commissions and taxes and keeps state only in memory. It cannot be used unchanged as a three-year evidence engine.
- The existing dashboard is the correct delivery surface. The new workflow should be a server-side asynchronous backtest job plus read-only result projections; the browser must not acquire provider data or execute strategy code.
- Historical Kbar display is currently fetched on demand per selected symbol. That request path is suitable for chart inspection, not full-universe three-year ingestion.
- The current architecture documentation already recommends one event-driven kernel for historical Backtest and paced Replay, which this plan should preserve.
- The plan must explicitly resolve strategy/data-grain compatibility: the Momentum family consumes intraday event evidence, while a daily-Kbar-only source cannot reproduce Tick/BidAsk-based decisions.
- `ReplayDataset` is deliberately one `session_date` with manifest SHA-256, timezone, instrument references, and ordered Tick/BidAsk envelopes. A three-year run should compose many immutable session partitions instead of creating one enormous mutable file.
- `ReplayRunner` currently validates and ingests events into bar/book/data-health projections and returns digests; it does not call strategy, create fills, maintain cash/positions, or calculate performance.
- `scripts/replay_momentum_signal.py` evaluates only Tick events, runs `FeatureEngine`/`MomentumSignalEngine`/`MomentumStateMachine`, and forces `RiskGateStatus.UNAVAILABLE`. Its `REPLAY_ALERT_ONLY` output is a reusable signal-evidence adapter, not an execution engine.
- Momentum episodes and instrument references are session-scoped. The future engine needs explicit end-of-session behavior: close, carry overnight, or reject an open position according to versioned strategy policy.
- Signal eligibility depends on data-health state and Tick/BidAsk-derived evidence. Missing quote coverage must produce an excluded/blocked observation rather than a profitable synthetic fill.
- `SimulationService` models whole-lot, long-only limit orders with in-memory floats and immediate marketability checks against ask/bid or snapshot price. It does not model commissions, tax, slippage depth, partial fills, corporate actions, or durable run recovery; it should remain an interactive paper adapter, not become the historical accounting core.
- The dashboard is a single FastAPI/Vanilla-JS page with synchronous snapshot/history endpoints and polling for local simulation. A long three-year full-market run requires asynchronous job endpoints, durable progress, cancellation, and result lookup so HTTP requests never stay open for the run duration.
- Existing historical UI uses per-symbol `get_kbars()` calls split into at-most-30-day windows and caches results in process memory. That is appropriate for a selected chart, but a full-universe ingestion job needs a dedicated catalog/store, resumable partition acquisition, rate limiting, and manifest validation.
- The UI already has a top navigation/workspace convention. Backtesting should be a first-class feature view rather than another drawer inside the Candidate detail panel.
- Current strategy features include VWAP, breakout, rolling returns/volume, limit-up distance, aggressor-side/external flow, and order-book features. A data profile must declare which features are exact, derived, unavailable, or disabled for each historical source.
- The legacy Candidate/BuyScore path is a one-shot snapshot: Candidate rules are GapUp or absolute HighVolume; scoring is GapScore plus AboveVWAP; configured exit rules are StopLoss and TakeProfit. It does not define when during a historical session the snapshot is evaluated or when a buy is submitted.
- `run_scan()` also injects a hard-coded demonstration position. A backtest must never reuse that orchestration directly; it needs explicit strategy entry/exit intents and portfolio state derived only from simulated fills.
- Existing architecture planning already specifies the safest first execution grain: completed 1-minute bars, decisions at bar close, and no fill within the same bar. That is a suitable first milestone for deterministic testing, while exact Tick/BidAsk Momentum parity remains a later data-profile gate.
- Existing `Journal`, `Clock`, `RiskGate`, command application, and Decimal local-paper foundations are reusable boundaries. Historical backtest persistence should write separate run/report records and may reuse normalized event/decision/fill records without coupling the core to FastAPI or PostgreSQL.
- The target strategy must be frozen as a versioned bundle: universe policy, Candidate rules, entry threshold/Momentum policy, position sizing, exit rules, end-of-day action, and cost/fill assumptions. Current code does not yet expose that complete bundle.
- Current official Shioaji documentation says stock Tick/Kbar history is available from 2020-03-02 to today, so a three-year source window is possible in principle. Kbars are 1-minute OHLCV/Amount; historical Tick rows include trade price/volume plus best bid/ask and tick type, not the live five-level order-book stream.
- Official usage rules group `snapshots`, `ticks`, and `kbars` under market-data limits (50 calls per 10 seconds), apply daily traffic caps, and recommend after-market queries with caching. Full-universe acquisition must therefore be resumable, usage-aware, throttled well below the ceiling, and never launched as a synchronous browser request.
- A Shioaji-only historical universe may omit symbols that are no longer discoverable as current contracts. The all-market claim needs a date-effective TWSE/TPEX instrument master including delisted/suspended periods, or the UI must visibly label the result as current-active-universe and survivorship-biased.
- Trading costs must be effective-dated. Official sources distinguish stock sell tax, day-trade sell tax, ETF tax, and broker-specific commission schedules; the engine must not hard-code one timeless percentage across all products and dates.
- Corporate actions must be represented by date-effective reference prices/actions. Raw previous close alone would create false gaps around ex-right/ex-dividend dates.

## External source notes

- Shioaji historical market data: https://sinotrade.github.io/tutor/market_data/historical/
- Shioaji use restrictions: https://sinotrade.github.io/tutor/limit/
- Ministry of Finance stock transaction tax overview: https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-knowledge/rwG2M1N
- TWSE ex-right/ex-dividend reference information: https://www.twse.com.tw/zh/announcement/ex-right/cal.html

## Final planning outcome

- The standalone plan is `architecture/three_year_backtest_web_implementation_plan.md`.
- It defines Phase 0–8: contracts, immutable datasets, deterministic strategy kernel, execution/accounting, metrics, durable jobs/APIs, Web UI, full-scale rollout, and Momentum historical capability work.
- It retains the existing HighVolume-based strategy as a named legacy version and creates any RVOL variant under a different strategy id.
- It requires seven user strategy/economic/deployment parameters before a result can be labeled formal evidence, while allowing clearly labeled research defaults for fixtures and UI development.

## Extension requirements: multi-strategy and durable comparison

- Entry and exit selections must be independent multi-select sets; one combined strategy field cannot explain which side of a trade was triggered.
- Default composition should be `ANY`: one selected strategy can create a decision. `ALL` and `AT_LEAST_N` are useful explicit alternatives, but must be part of the immutable run snapshot.
- Multiple triggers at the same event must create one aggregated trade decision, not duplicate orders. The decision stores every triggered strategy and selects a deterministic primary reason by configured priority.
- Every selected strategy on a decision event needs status and evidence, including strategies that did not trigger or were blocked; full-period ordinary `NOT_TRIGGERED` counts can be aggregated to avoid billions of PostgreSQL rows, with an optional immutable Parquet debug stream.
- The user now requires durable historical comparison. Platform mode should use PostgreSQL as the authoritative run/evidence/result repository; SQLite should be retained only for local development and tests.
- A meaningful adjustment comparison requires the same dataset, universe, date range, execution model, costs, capital, and split. If these differ, the UI must label the runs non-comparable or explain the normalized comparison.
- Strategy contribution must separate primary-attributed PnL from participated-in trades so one multi-trigger trade is not counted as multiple copies of PnL.
- Effectiveness evidence should use OOS KPI deltas and a trading-session-clustered bootstrap interval; the UI must describe this as an associated backtest difference rather than proof of causality.

## Execution inventory: 2026-08-18

- `dashboard/server.py` has one global FastAPI app, a lifespan hook, and direct function-style routes that tests call without TestClient. The new backtest namespace should keep that style and be feature-flagged independently of the local simulation routes.
- `RuntimeComposition` deliberately creates only `DashboardService`, `SimulationService`, in-memory Journal, and provider. Backtest composition must remain separate so it cannot start quote streaming or call the paper-order path.
- `MarketDataProvider` already exposes server-side `get_market_stocks()` and a 30-calendar-day-bounded `get_kbars()` seam. `ShioajiProvider` supports Kbars; `MockProvider` supplies deterministic daily bars for ranges and 5-minute bars for a single session.
- Current dependencies are FastAPI/std-lib with optional `psycopg`; no dataframe or Parquet package is installed. The implementation needs an immutable JSONL fallback and may use Parquet only when an optional dependency is available.
- Existing PostgreSQL migration style lives in `trading/migrations.py` and uses a DB-API connection/cursor. Backtest can follow that pattern while defaulting local development to a durable SQLite file.
- `dashboard/static/index.html` is one non-module Vanilla JS file. Historical backtest should be an independent workspace panel, not a change to candidate rendering or the existing source-Kbar tooltip contract.
- Worktree already has extensive unrelated dashboard, market-data, runtime, and planning changes. New files should be additive where possible; only targeted server/index/README/pyproject integration is authorised.

## Execution outcome: 2026-08-18

- Implemented the executable Phase 0–8 slice in `backtest/`, `config/backtest.py`, `dashboard/server.py`, `dashboard/static/index.html`, README, and focused tests without changing the separate active planning task.
- Direct Provider collection is explicitly labelled `CURRENT_SNAPSHOT` and `research_eligible=false`; its lack of date-effective delisted/universe data prevents a `RESEARCH_PASS` verdict.
- The same engine accepts imported immutable data marked `DATE_EFFECTIVE` and research eligible. Supplying a complete TWSE/TPEX historical instrument master, reference-price/corporate-action treatment, calendar reconciliation, and authorized historical data remains an external data-governance gate rather than something the code can fabricate.
- The browser verifies the new workspace opens and renders Chinese strategy controls against the actual local server. It intentionally did not click the data-acquisition button because the configured live Shioaji provider could consume quota; no new historical data or trade was created by this validation.

## Unified strategy catalog integration: 2026-08-18

- The referenced strategy-inventory task reports a new immutable `strategy_catalog` covering CANDIDATE, SCORE, SIGNAL, ENTRY, and EXIT roles. This is treated as context only until verified against the current checkout.
- Current checkout verification confirms that catalog definitions may describe research or database-authored metadata, while executable historical logic remains restricted to server-owned `StrategyRegistry` bindings.
- A backtest selector must therefore expose only catalog ENTRY/EXIT definitions whose id, version, side, and execution binding match the executable registry. Candidate, score, signal, draft, and unbound database definitions must not be presented as runnable code.
- The existing request contract accepts arrays for entry and exit strategy ids, so one element is a single-strategy selection and multiple elements are a multi-strategy selection. The missing work is explicit UI state, catalog/execution reconciliation, stricter validation, and direct tests for both modes.
- Implementation now annotates the full strategy catalog with `backtest_executable` and a reason when unavailable. The backtest endpoint is fail-closed and returns only exact immutable catalog/runtime matches, preserving the registry order so the existing legacy strategy remains the default entry selection.
- Browser validation with `PROVIDER=mock` confirmed the entry selector transitions from one to two selected strategies, displays the corresponding single/multi label, enables `AT_LEAST_N`, caps N at the selected count, and clamps N back to one when returning to a single strategy.
- No dataset sync or run submission was performed in the browser. API tests created both single-entry/single-exit and multi-entry/multi-exit fixture runs in temporary local repositories.

## Standalone downloader investigation: 2026-08-18

- The reported Web job `dataset-job-08ebb8bd70394c3787ee22b6cd4176fe` is confirmed RUNNING in local SQLite at 376/2738 symbols (13.73%) after roughly 27 minutes.
- Current `HistoricalDatasetCatalog.collect_from_provider()` retains every downloaded `HistoricalBar` in one Python list and only seals/registers the dataset after all symbols finish. `data/backtest/` therefore still contains only the catalog SQLite file while the large in-flight payload exists in server memory.
- The current process is not resumable: closing the server before final sealing loses all fetched bars. Repeated HTTP 200 job polls only report status and do not persist Kbar checkpoints.
- A three-year all-current-symbol Shioaji run issues many 30-calendar-day window calls per symbol and can create hundreds of millions of minute bars. Persisting one database row per Kbar would add excessive SQLite/PostgreSQL row overhead, while an immutable compressed per-symbol partition preserves exact bars, supports restart, and keeps transactions bounded.
- The selected design stores one gzip-compressed canonical JSONL partition per completed symbol in the configured backtest SQLite/PostgreSQL database. The job row holds frozen request/universe metadata; a final streaming seal writes the existing checksum-protected dataset format and registers it READY for the Web UI.
- The script must never call order/account/CA/streaming APIs. It only uses `get_market_stocks()` and bounded `get_kbars()` through `MarketDataProvider`, closes the provider explicitly, and does not download live data in automated tests.
- Final implementation uses the existing `backtest_jobs` table for durable request/status and a new `backtest_history_partitions` table for one gzip/BLOB or gzip/BYTEA payload per symbol. Each payload has SHA-256, bar count, date coverage, instrument metadata, and an optional missing-data reason.
- SQLite now uses WAL plus a five-second busy timeout for short checkpoint writes alongside dashboard reads. PostgreSQL receives a forward-only `003_resumable_history_download.sql` migration.
- Final dataset sealing is deterministic by job id and streams one decompressed symbol partition at a time. A crash after sealing but before database registration can safely reuse the existing manifest on resume.
- Isolated Mock CLI smoke produced two partitions, 522 bars, a READY dataset, and a valid manifest; a completed-job resume returned the existing manifest without refetching.
- The pre-existing Web job remains the old non-checkpointed kind and cannot be converted into a resumable CLI job. At the last read-only check it still reported RUNNING at 407/2738 (14.86%), with its last stored update at 2026-08-18T15:51:56+08:00.
