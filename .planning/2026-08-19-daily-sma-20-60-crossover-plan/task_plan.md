# Task Plan: Daily SMA20 / SMA60 Crossover Strategy

## Goal

Execute the approved G0 Provider/daily-source qualification for an experimental daily-Kbar SMA(20)/SMA(60) strategy, preserving reproducibility and keeping all broker/live-order behaviour out of scope.

## Current Phase

Phase 9: Derived daily dataset and SMA strategy implementation — complete

## Phases

### Phase 1: Requirements and repository discovery
- [x] Confirm that dashboard MA20/MA60 is display-only SMA, not an executable signal.
- [x] Confirm that the only executable moving-average entry is session-reset EMA(5)/EMA(20) on 1-minute Kbars.
- [x] Trace daily-dataset capability and cross-session state requirements.
- [x] Record implementation boundaries and non-goals.
- **Status:** complete

### Phase 2: Contract design
- [x] Freeze daily SMA20/SMA60 crossover, timing, warm-up, and duplicate-signal semantics.
- [x] Define dataset capability, strategy version, catalog, and engine compatibility contracts.
- **Status:** complete

### Phase 3: Implementation plan authoring
- [x] Define dependency-ordered implementation phases, exact code areas, and data migrations.
- [x] Define test, rollout, rollback, and research qualification gates.
- **Status:** complete

### Phase 4: Plan verification
- [x] Cross-check every planned edit against current code and existing strategy-expansion contracts.
- [x] Confirm this task changed planning Markdown only.
- **Status:** complete

### Phase 5: Delivery
- [x] Deliver the standalone plan and summarize key design choices.
- **Status:** complete

### Phase 6: Incorporate P0 review contracts
- [x] Compare the four supplied P0 contracts against the current engine and dataset code.
- [x] Amend the plan with pending-order horizon, price-adjustment, Decimal canonicalization, and session-resolution contracts.
- [x] Add a G2.5 execution-semantic gate and refine strategy-evidence versus aggregated-decision tests.
- [x] Re-verify that this remains a plan-only change.
- **Status:** complete

### Phase 7: G0 Provider and daily-source qualification
- [x] Restore plan context and record the current dirty worktree as an external baseline.
- [x] Trace existing capture, Kbar mapping, historical-download, and artifact-validation seams.
- [x] Define and implement replayable G0 fixture/report schemas without strategy code.
- [x] Obtain or explicitly fail-close on actual Shioaji/Provider source evidence; never fabricate qualification inputs.
- [x] Validate timestamp, raw numeric representation, resolved session date, session completeness, chunk boundaries, and artifact digests.
- [x] Publish a qualification result that selects `EXPLICIT_SOURCE_DAILY_V1`, `DERIVED_FINALIZED_SESSION_V1`, or `BLOCKED`.
- [x] Run focused verification and scope audit; update the plan with the G0 outcome.
- **Status:** complete (`BLOCKED`: source finalization is unproven)

### Phase 8: G0 source-completion reconciliation
- [x] Restore the blocked G0 evidence, current dirty-worktree baseline, and the explicit no-SMA gate.
- [x] Identify an authoritative, replayable daily close/volume source that can independently prove a completed TWSE session.
- [x] Implement an isolated reconciliation capture and offline qualifier that compares raw Shioaji intraday aggregation to that evidence without weakening the raw-float rule.
- [x] Capture a historical completed session, validate aggregate OHLCV/session/date/digest equality, and regenerate the G0 qualification result.
- [x] Run focused regression and offline replay checks, then report whether G0 can select `DERIVED_FINALIZED_SESSION_V1`.
- **Status:** complete (`DERIVED_FINALIZED_SESSION_V1` selected)

### Phase 9: Derived daily dataset and SMA strategy implementation
- [x] Promote the G0-selected `DERIVED_FINALIZED_SESSION_V1` contract into the implementation input; keep raw adjustment, common-lot volume, and regular-session scope explicit.
- [x] Reconcile the approved daily architecture plan with the current concurrently modified backtest code, then identify non-overlapping implementation seams.
- [x] Implement sealed derived-daily lineage, canonical Decimal/session metadata, and `KBAR_DAILY` capability with legacy digest compatibility.
- [x] Implement completed-day SMA20/SMA60 feature state, golden/death strategies, and explicit daily next-bar execution horizon without changing legacy intraday semantics.
- [x] Extend service/catalog serialization and default-off selection, then add deterministic unit/integration/regression tests.
- [x] Run focused/full verification, record the remaining research limitations, and report the completed strategy slice.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat MA as daily SMA rather than existing intraday EMA | The dashboard's MA20/MA60 uses source daily Kbar closing prices, while the executable strategy is EMA(5/20) on session-reset one-minute Kbars. |
| Add a separate experimental strategy version | Changing `ema_crossover_entry_v1` would silently alter its indicator, cadence, warm-up, and historical-reproduction contract. |
| Keep MA state across trading sessions | A 20/60-day moving average cannot be computed from the engine's current per-session feature state. |
| Require a new `KBAR_DAILY` capability | The current daily-looking profile exposes only `OHLCV`; this must not be conflated with a verified complete daily series. |
| Signal on a completed daily close and execute on the next eligible bar open | It retains the engine's existing no-look-ahead, next-bar execution model. |
| Do not change the chart API or use its response as a backtest input | Chart history is on-demand/provider-backed; backtests use sealed datasets and must stay reproducible. |
| Preserve `is_last_bar` as a session-close concept and add a distinct terminal-data concept | In the current engine every daily bar is session-last; using it for a daily death-cross would incorrectly fill at the same close. |
| Give pending orders explicit execution horizons | The current pending map survives sessions already, but daily `NEXT_BAR_OPEN` must be protected from session-end exit behaviour without changing intraday semantics. |
| Move only `SESSION_CLOSE` fills onto the session-last branch | A daily death cross must create `DAILY_NEXT_BAR` pending even though every daily bar is session-last. |
| Keep P0 fields additive for legacy serialization but mandatory for new daily manifests | This preserves old sealed digests while making adjustment, session and canonicalization evidence auditable for new SMA runs. |
| G0 may create evidence artifacts and qualification code only | No SMA indicators, strategy definitions, dashboard changes, broker order API, CA, or account call is authorized in this phase. |
| An unavailable or ambiguous Provider yields `BLOCKED`, not a synthetic pass | Source qualification must be based on an actual captured provider payload or an existing immutable capture with sufficient fields. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| No stored memory entry matched this MA20/MA60 strategy task | Used current repository evidence and did not import assumptions from unrelated project history. |
