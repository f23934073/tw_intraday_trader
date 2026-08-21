# Findings: Paper Sell Safety and Recoverable Orders

## Approved review baseline

- Final disposition before implementation: `Request Changes / NO-GO` for
  unattended paper trading.
- Direct blockers: ownership, executable BidAsk freshness, SELL result
  handling, daily-loss ordering, after-close reconciliation, and controller
  singleton construction.
- Second batch: recoverable order lifecycle with partial fill, timeout, cancel,
  retry, expiry, alerts, and restart recovery.
- A smoke succeeds only on `FILLED` plus closed position; `EXIT_SUBMITTED` is
  insufficient.
- Costs, tax, and slippage block performance conclusions but not a basic
  lifecycle smoke.

## Workspace constraints

- The root planning files belong to an active Freshness Calibration task and
  must not be overwritten.
- The repository is already heavily dirty with user/other-task changes.
  All edits and validation must be scoped to this implementation.
- No `AGENTS.md` was found by the initial repository file scan.

## Precision corrections

- A fresh Tick updates the wrong shared quote timestamp and passes the
  controller freshness gate while the executable BidAsk itself remains old.
- Daily loss uses trading-day opening equity. The policy in this plan includes
  unrealized PnL in both the baseline and current equity.

## Initial repository trace

- Paper execution currently has a hard-coded 15-second recent-book threshold,
  while the continuous controller defaults to 5 seconds and reads a generic
  position quote timestamp.
- `SimulationOrder` currently exposes only `SUBMITTED`, `FILLED`, `CANCELLED`,
  and `REJECTED`; the service transitions only whole orders.
- `trading.trade_management` already defines a richer lifecycle vocabulary,
  including `PARTIALLY_FILLED`, `EXPIRED`, and `RECOVERY_REQUIRED`. Inspect its
  bounded context before introducing any simulator lifecycle type so this work
  does not create a third incompatible state model.
- Existing focused tests cover submit/retry and basic automated entry/exit, but
  the initial search did not find stale-book/fresh-Tick, cross-day baseline,
  controller construction race, after-close reconciliation, or restart
  recovery cases.
- Memory confirms executable-book health must use connection/subscription plus
  BidAsk freshness, and warns against duplicating timestamp/freshness policy.

## Controller defects confirmed from complete control flow

- `_evaluate_locked` returns outside session hours before reading projection,
  positions, or pending orders; after 13:30 no exit reconciliation can occur.
- Daily loss is checked before positions and orders, so a breached loss limit
  blocks risk-reducing SELL handling.
- `_evaluate_position` validates only symbol/quantity, reads the position's
  quote timestamp, ignores the flow result, and always reports
  `EXIT_SUBMITTED`.
- The current daily-loss calculation is `max(0, starting_cash - equity)` with
  no trading-date baseline.
- Controller restart is currently documented as manual start required and all
  run-local counters/intents are process memory, so lifecycle recovery needs an
  explicit persistence seam rather than silently changing startup behavior.

## Simulator execution facts

- BidAsk updates maintain `book_at` and `book_received_at`, while all Tick and
  BidAsk updates advance a generic `received_at`.
- Fill eligibility already uses `book_received_at`; projection/order payloads
  must expose and controller/risk must consume that exact field.
- Whole-order `_fill` mutates cash/position and immediately sets `FILLED`;
  partial execution requires quantity-delta accounting, not just adding an enum.

## Ownership and recovery seams

- Orders already carry an `origin`, and strategy intents carry stable
  `strategy_id`/`strategy_version`, but `SimulationPosition` stores neither an
  owner nor contributing order/intent identity. Ownership must be projected
  into positions at fill time and checked by the controller.
- `StrategyPaperFlowService` journals the strategy intent before routing it to
  `LocalPaperCommandService`; this is the existing durable audit seam for
  automated intent identity.
- `SimulationService` explicitly documents process-memory-only state and the
  current session notice says restart clears orders/positions. Batch 2 must
  replace that claim with a small simulator state repository or restore from a
  complete existing journal projection; an in-memory controller checkpoint
  would not satisfy restart recovery.
- Cancel currently supports only whole `SUBMITTED` orders and does not emit the
  terminal callback, so lifecycle journaling/recovery needs cancellation events
  as well as fill/reject events.

## Risk and command facade

- `RiskGate` already applies daily loss only to BUY, so the controller's
  pre-position daily-loss early return is the remaining SELL-ordering defect.
- `RiskPolicy` already supports `require_fresh_book` and
  `max_book_age_seconds`, but `LocalPaperCommandService` currently leaves the
  requirement disabled and accepts the policy default of 15 seconds.
- `risk_snapshot()` derives `book_age_seconds` from `book_received_at`, which is
  the correct evidence source. A shared local-paper executable-book policy can
  feed controller, RiskGate, and simulator without claiming the still-unfrozen
  global `FreshnessPolicyV1` thresholds.
- The command facade retains original `OrderCommand` objects only in memory.
  Its delayed terminal-order callback cannot journal a restored pending order
  after restart unless command identity is restored from durable records or
  terminal events become self-contained.

## Existing Journal projection limits

- `trading.local_paper` can rebuild cash, positions, and realized PnL from fill
  records and verifies checkpoints, but it does not project pending orders,
  cancellation/rejection state, strategy ownership, or partial-fill deltas.
- Fill idempotency is currently keyed only by `order_id`, which permits one
  whole-order fill but cannot represent multiple partial fills for the same
  order.
- `RuntimeComposition.create()` always generates a new random local-paper
  session and metadata explicitly says `NEW_LOCAL_PAPER_SESSION`; restart
  recovery therefore requires both richer lifecycle records and a deliberate
  resume-session selection contract.
- The dashboard composition singleton is locked, but the automated controller
  global uses a separate unlocked lazy path; a dedicated controller lock or the
  existing composition lock must cover the entire check-and-construct block.

## Session resume constraint

- `JournalRepository` exposes append/replay/checkpoint operations but no session
  enumeration or latest-session lookup. Recovery therefore cannot discover a
  prior random UUID session through the port.
- A deterministic per-trading-date local-paper session identity is the smallest
  viable resume contract, provided `start_session` is retry-stable and session
  metadata/started time are deterministic across restarts.
- Test fixtures force the Journal backend to memory, so restart recovery needs
  explicit repository injection tests (and persistent-adapter contract tests),
  not reliance on the global test environment.

## Retry-stable session and test implications

- Both in-memory and PostgreSQL `start_session()` accept an exact matching
  retry and reject metadata drift. A deterministic trading-date session can
  resume safely only if `started_at` and metadata are deterministic.
- Existing automated-controller tests explicitly assert manual-start recovery.
  Preserve that safety boundary unless a separate persisted operator enablement
  contract is introduced; order/projection recovery can still be automatic and
  controller reconciliation can occur on the next explicit start.
- Current Journal fill tests assume one fill record per order and one checkpoint
  after each terminal outcome. Partial fills require per-fill event identity and
  checkpoint advancement after every mutation.

## Lifecycle contract reuse decision

- Reuse `trading.trade_management.OrderLifecycleState`, its transition table,
  and terminal-state set as the shared lifecycle vocabulary. The simulator will
  adapt its order projection to this contract instead of defining another rich
  enum.
- Timeout and retry are policies/events around existing states: timeout requests
  cancellation; a retry creates a successor order with bounded attempt metadata.
  No speculative `TIMED_OUT` or `RETRYING` state is required.
- `RECOVERY_REQUIRED` is terminal/fail-closed and suitable when restored state
  cannot be proven or a cancel/retry outcome is ambiguous.

## Focused baseline and partial-fill input

- Focused pre-change baseline: 57 tests passed across simulation service,
  command facade, local-paper projection, strategy flow, continuous controller,
  dashboard API, runtime composition, and RiskGate.
- `RealtimeQuoteUpdate` currently carries only best prices, not displayed bid/ask
  quantities. A realistic partial-fill simulator needs optional best-level share
  quantities propagated from BidAsk; otherwise partial fills can only be a test
  hook or arbitrary synthetic split.
- Existing simulation-service tests are small and whole-fill oriented, making
  them a suitable place to add price-level quantity, remaining quantity,
  cancellation-after-partial, and expiry contracts.

## BidAsk quantity source

- Shioaji BidAsk callbacks and the canonical market-event path already carry
  level volumes, but the lightweight `RealtimeQuoteUpdate` adapter currently
  drops them before the paper simulator.
- Extend the existing paper adapter with optional best-level volume in lots and
  convert it to shares at the simulator boundary. Absence preserves legacy
  whole-fill behavior; presence caps each fill delta and enables real partial
  fill tests without synthetic split hooks.

## Provider adapter detail

- `ShioajiProvider._on_bidask_stk_v1` currently normalizes only first best
  prices even though the raw callback exposes `bid_volume` and `ask_volume`.
  Add optional first-level volume normalization alongside price normalization.
- Existing stream tests expect pending state text and subscription behavior;
  lifecycle expansion must update active-state predicates and UI labels without
  regressing these transport guarantees.

## Dirty-worktree ownership

- The current simulation/controller/runtime features are themselves largely
  uncommitted work. Patches must be exact-context edits on the live files; do
  not restore them toward `HEAD` or refactor adjacent dashboard/provider work.
- Existing dashboard tests already include an eight-thread runtime-composition
  race case, but no equivalent controller-construction race. Add a dedicated
  barrier test while preserving the composition test.

## Executable-book RiskGate scope

- Applying mandatory book freshness to all local-paper BUY commands would
  deadlock first subscription: the simulator subscribes after accepting a
  pending symbol. Preserve the generic RiskPolicy default for both sides, but
  configure local paper to require the shared threshold for SELL commands.
- The direct safety probes now fail exactly as expected: seven failures cover
  six controller defects plus the singleton race; 21 related tests still pass.

## Ownership propagation path

- `OrderCommand` is the clean application boundary between strategy flow and
  the simulation adapter. Add optional strategy identity there, include it in
  `order_command.v1`, and pass it through the adapter to order/position state.
  This keeps ownership auditable and avoids side-channel maps.

## Recoverable lifecycle implementation

- Every order transition now emits a durable `local_paper_order_state.v1`
  snapshot. Partial fills emit quantity-delta fill records with a monotonic
  per-order fill sequence, so replay does not collapse multiple executions.
- The simulator now treats `PENDING` and `PARTIALLY_FILLED` as active states,
  reserves only the unfilled remainder, times out to `CANCELLED`, expires to
  `EXPIRED`, and creates bounded successor orders for retry.
- Runtime composition rebuilds the fill projection and latest order states from
  the journal, then restores cash, positions, reservations, idempotency,
  trading-day baseline, and recovery alerts. Automated strategy execution
  itself remains manual-start-required after a process restart.
- Optional best-level BidAsk volume is propagated through the realtime adapter
  and consumed per update, enabling real multi-lot incremental fills.
- Focused lifecycle tests now cover volume-capped partial fills, timeout plus
  successor retry, expiry alerts, and same-day restart/idempotency recovery.

## Operator surface gap

- The projection already returns lifecycle alerts, but the dashboard currently
  ignores them. Surface the newest unresolved alert in simulation health and
  the order preview so timeout/expiry/recovery failures are visible.
- The API currently exposes submit and cancel only. Add a retry endpoint that
  delegates to the existing bounded successor-order command, plus retry actions
  only for `CANCELLED` and `EXPIRED` rows.
- Alert payloads already have stable `code`, `message`, `severity`, `order_id`,
  and timestamp fields, so the dashboard can render them without inventing a
  second alert model.

## Partial-fill edge case

- A BidAsk level with an explicit zero available quantity currently marks the
  update as having filled even though `_fill` correctly performs no mutation.
  Guard the fill/consume/result path on a positive fill quantity so downstream
  stream change detection remains truthful.

## Test extension points

- The dashboard route tests already build a real local composition with
  `MockProvider`, so submit at a non-marketable price, cancel, then retry can
  verify the API contract without a fake command service.
- The lifecycle test helper exposes a mutable Taipei clock and injectable
  in-memory journal, making retry exhaustion, partial-cancel, cross-day equity,
  and restart-recovery cases deterministic.

## Missing acknowledgement recovery

- `latest_local_paper_order_states` intentionally synthesizes a terminal
  `RECOVERY_REQUIRED` order when an `APPROVED` command has no durable simulator
  order-state acknowledgement. Runtime restore converts that reason into a
  high-severity `RECOVERY_REQUIRED` alert.
- A deterministic failure-window test can append such an approved command to
  the stable runtime session, advance the projection checkpoint, then recreate
  the composition and assert fail-closed recovery rather than command replay.

## Adapter coverage targets

- `tests/test_journal.py` and `tests/test_postgres_journal_unit.py` are the
  focused contract locations for the newly added `session(session_id)` lookup.
- The Shioaji paper-stream normalization probe lives in
  `tests/test_realtime_quote_stream.py`; extend it to assert first-level bid/ask
  volume instead of relying only on simulator-crafted updates.
- The PostgreSQL lookup selects `started_at`, `mode`, JSON metadata text, and
  schema version in one transaction; its unit fake needs parameter-aware
  `execute` plus a representative four-column row to validate reconstruction.

## Freshness coverage matrix

- Existing tests now cover stale executable-book rejection separately in the
  generic RiskGate, controller decision path, and simulator fill path. Add one
  command-facade integration case so the local-paper SELL policy wiring itself
  is proven, not inferred from its components.

## Final-review persistence gap

- Daily opening equity is currently copied into order-state snapshots only.
  A restart on a day with no order transition can therefore lose the frozen
  trading-day baseline, especially for an overnight position. Persist the
  daily risk baseline as its own Journal record and restore it independently of
  order ordering before claiming cross-day restart safety.
- The simulator's operator notice still says restart clears orders and
  positions, which is now false under checkpointed runtime composition. Update
  the notice to describe local Journal recovery without implying broker state.

## Callback lock-order risk

- Quote fills, snapshot refresh fills, and timeout/expiry currently invoke the
  Journal terminal handler while holding the simulation lock. Command submit
  holds the command lock before acquiring the simulation lock, so a concurrent
  fill can invert the lock order and deadlock. Capture immutable order payloads
  under the simulation lock, then invoke Journal handlers after releasing it.
- Apply the same outside-lock rule to the new daily-baseline handler so
  cross-day persistence does not add another lock inversion.

## Daily baseline contents

- Restore must preserve both opening equity and the cumulative realized-PnL
  value at the moment the day baseline was frozen. Otherwise an intraday
  restart silently resets `daily_realized_pnl` even if opening equity survives.

## Partial-fill compatibility

- Downstream thesis activation treats `local-paper-fill:{order_id}:{occurred_at}`
  as the canonical record identity. Keep that public identity while retaining
  per-fill sequence idempotency; ensure each order's fill update timestamp is
  strictly monotonic so multiple partial executions cannot collide.
- Preserve the historical bare `order_id` idempotency key for fill sequence 1,
  which is the activation-compatible entry fill. Later partial deltas use a
  sequence suffix, avoiding collisions without breaking single-fill consumers.

## Unattended readiness boundary

- The Journal backend still defaults to process-memory. Restart recovery is
  only durable when `TRADING_JOURNAL_BACKEND=postgresql` is explicitly
  configured and healthy; the runtime correctly fails closed instead of
  falling back when PostgreSQL is selected.
- The automated controller intentionally reports
  `restart_behavior=MANUAL_START_REQUIRED`, and lifecycle alerts are local
  API/dashboard state rather than an external paging channel. These remain
  operational NO-GO conditions for genuinely unattended host/process restart,
  even though order/projection recovery is now implemented.
- README persistence text still describes new-session/no-hydration behavior and
  must be updated to the stable checkpointed session contract.

## Phase 5 intake

- Current base commit is `6f7a8424270a1688b3dcd3fbd12116107ee415a6`.
- Both previously failing tests are untracked and their dependencies are wholly
  inside dirty/untracked `backtest/`, `strategy_catalog/`, `config/backtest.py`,
  and atomic-strategy work. None belongs to the paper-sell implementation
  surface, but isolation still needs runtime reproduction before attribution.
- The atomic-backtest files changed again after the prior full-suite run, so
  rerun the two failures in the live worktree before constructing an isolated
  snapshot; stale failure text is not acceptable evidence.
- No `DATABASE_URL` or `POSTGRESQL_DSN` is present in the current shell.
  `pg_isready` and Docker CLI are installed, so Phase 5 can first check for an
  already-running local PostgreSQL service, then use a disposable database only
  if explicitly available and safe.

## Phase 5 isolation evidence

- An isolated `/tmp` snapshot was built from base commit `6f7a842` and overlaid
  only with the current `backtest/`, the migration test, and test configuration;
  no simulation, trading, runtime, dashboard, or Phase 5 product files were
  overlaid.
- In that isolated snapshot, `tests/test_backtest_sqlite_postgres_migration.py`
  reproduces the same migration-list mismatch: `1 failed, 3 passed`. This is
  sufficient evidence that the remaining full-suite failure belongs to the
  independent dirty atomic-backtest slice, not the paper-sell implementation.
- The live atomic-strategy test now passes after concurrent changes, so the
  earlier missing-ENTRY failure is resolved rather than merely attributed.
- Default `pg_isready` returns exit 2 (no local server response). Docker daemon
  inspection is blocked by sandbox access to the user socket and requires an
  explicit escalation before a disposable PostgreSQL UAT environment can be
  considered.

## Phase 5 UAT harness design

- Disposable PostgreSQL container `tw-intraday-phase5-pg-01a02373` is mapped to
  `127.0.0.1:61243`. A host `pg_isready` call currently sees no response; check
  readiness inside the container to distinguish startup from sandboxed host
  networking.
- The six UAT scenarios already have deterministic production-path tests:
  ownership and stale-book/controller handling in
  `test_continuous_paper_strategy.py`, reject/retry and partial fill in
  `test_recoverable_simulation_orders.py`, the 13:30 boundary in the continuous
  controller suite, and a new explicit real-PostgreSQL restart test still to be
  added.
- `RuntimeComposition.close()` closes the simulation, Journal adapter, and
  provider. A restart UAT must therefore create a genuinely new psycopg
  connection and repository for each runtime generation, rather than reusing
  one in-memory adapter or live connection.

## Phase 5 PostgreSQL UAT result

- Added `scripts/run_phase5_paper_sell_uat.py`; it requires an explicit
  `TEST_POSTGRES_DSN` and exits 2 when absent, so PostgreSQL recovery can never
  be accidentally certified by the memory adapter.
- Added a real PostgreSQL acceptance that closes and recreates three independent
  runtime generations/connections. It verifies a filled position, pending
  order, 100,000 cash reservation, idempotent replay, timeout cancellation,
  released reservation, and restored `ORDER_TIMEOUT_CANCELLED` alert.
- Against disposable PostgreSQL 16 Alpine on localhost, the complete frozen UAT
  matrix passes: `7 passed in 0.33s`.
