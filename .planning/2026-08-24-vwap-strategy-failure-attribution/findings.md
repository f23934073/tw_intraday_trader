# Findings: VWAP Strategy Failure Attribution

## Confirmed baseline before fresh analysis

- The FinMind Dataset bridge G5 is complete and must remain unchanged.
- The completed baseline Run is `run-91ad87981676414da87b928398fa43c9` over 28,325,340 one-minute bars.
- Stored result digest is `60c29af24fd67ef9c3952118e3f157f5fab62a81e33a6f9b955bc8b5e76f57bc`.
- Dataset digest is `ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29`, bound at revision 1.
- The amount contract is `DERIVED_CLOSE_X_VOLUME_PROXY`; this is exploratory evidence, not authentic turnover.
- The run closed 6,321 trades with 1,550 wins and 4,771 losses.
- Net P&L was `-9,869,688.98731875` from initial cash of 10,000,000; final equity was `130,311.01268125` and maximum drawdown was about `-98.70%`.
- Qualification was `INSUFFICIENT_EVIDENCE`; the strategy is not eligible for Local Paper or real-money execution.

## R1 verified baseline identity

- PostgreSQL confirms the Run is `COMPLETED`, progress `1`, with no error, and its stored Run/config/Dataset/result digests match the G5 handoff.
- Frozen execution policy: starting cash 10,000,000; position fraction 10%; minimum lot 1,000 shares; commission 0.1425%; sell tax 0.3%; slippage 5 bps; engine `backtest-engine-v2`.
- Exact ENTRY member is Version `c2d5ca63-a871-482b-bc70-b3f81a48f5ba` of `above_vwap_entry`; exit is `end_of_day_exit_v1` under `ANY` composition.
- Feature evidence confirms completed 1-minute close-volume weighted proxy VWAP, not authentic turnover VWAP.
- Frozen Version parameters are `minimum_distance_bps=0`, `entry_window_start=09:01`, and `entry_window_end=12:45`; the Version/configuration/implementation digests match the Run snapshot.
- Result summary reports 1,665,150 VWAP evaluations, 128,802 triggers, 100,171 blocked evaluations, but only 6,321 primary trades. This large conversion gap requires order/rejection attribution before interpreting trade P&L.
- OOS starts 2025-08-18: 602 trades, 109 wins, 493 losses, gross P&L `-18,219.675`, net P&L `-67,154.958643125`, and Profit Factor `0.1685`.
- Normalized trade payloads preserve gross P&L, net P&L, entry/exit commissions, sell tax, holding minutes, exact decisions, and VWAP feature input evidence, so cost and semantic attribution can be computed without reconstructing market data.
- The first chronological trade shows the intended execution semantics: VWAP decision at 09:02, entry at next 1-minute bar open at 09:03 with slippage/cost, then forced EOD close at 13:30.
- Qualification persistence uses `request_json`, `protocol_json`, and `evidence_json`; the research-family tables already support a durable Bonferroni attempt budget and a stable research baseline identity.

## Initial hypotheses to test, not conclusions

1. `above_vwap_entry_v1` models a persistent state (price above VWAP), not a cross-up event, so it may emit too many low-specificity entries.
2. Portfolio/cash limits may admit only a deterministic subset of simultaneously triggered symbols, creating symbol-order bias.
3. Round-trip costs may dominate a weak or negative gross edge.
4. Forced end-of-day exits and next-bar fill semantics may amplify losses.
5. CURRENT_SNAPSHOT survivorship, partial universe, raw unadjusted prices, present-day metadata, and proxy amount restrict interpretation but should not be used to excuse an otherwise negative measured result.

## R2 first-pass decomposition

- ENTRY orders: 6,321 filled and 122,481 rejected for insufficient cash. The fill rate is only `4.908%`; every recorded exit order filled.
- Gross P&L after configured slippage was `-2,607,558.15`. Explicit commission and sell-tax drag was `7,262,130.83731875`, or about `73.58%` of total net loss. Even before explicit fees/tax, gross Profit Factor was only `0.7085`, so transaction cost is a major amplifier but not the root cause of the negative edge.
- `5,148 / 6,321` trades (`81.44%`) entered at 09:03. The median holding time was 267 minutes and the exit was normally the forced 13:30 close. The Run is therefore primarily an opening-entry/full-session-hold experiment, not a broad test of arbitrary intraday VWAP entries.
- All five entry-distance-to-VWAP quintiles lost money. Greater distance above VWAP did not isolate a profitable group in this admitted sample.
- Trades occurred on 690 days; median 11 trades/day and only 108 profitable days (`15.65%`). This is a persistent daily failure, not one isolated tail event.
- Only 145 of the 182 observed symbols traded. The 10 most frequently traded symbols accounted for 1,750 trades (`27.69%`) and `-2,319,981.51` net P&L. Concentration exists, but losses also span the broader admitted universe.
- Annual absolute P&L becomes mechanically smaller as capital is depleted. Year-to-year raw currency P&L must not be interpreted as strategy improvement without normalizing by trade notional/equity.
- Reconstructing the frozen 5 bps per side model gives pre-slippage price P&L `-1,365,500.00`, slippage drag `1,242,058.15`, explicit fees/tax `7,262,130.84`, and total friction `8,504,188.99`. Friction explains about `86.16%` of net loss, but the pre-slippage signal/holding result is still negative.
- Mean trade return was `-0.8095%` and median `-0.8507%`; the negative normalized return persists across 2023-2026, so the shrinking absolute loss is capital depletion rather than recovery.
- Same-day signal-order rank strongly predicts admission: ranks 1-10 filled `39.37%`, ranks 11-20 `19.57%`, ranks 21-50 `4.54%`, and ranks 101+ only `0.73%`. This confirms material deterministic admission bias.
- The engine processes bars by `(timestamp, symbol)`, sizes every candidate at 10% of total equity, then admits only if the remaining cash can fund it. It marks a symbol `entered_today` when the decision is created, so each symbol gets at most one attempt per day even if that order is rejected.
- The strategy kernel is a strict state test `current close > VWAP * (1 + distance)` within a time window. It does not require the prior close to be at/below VWAP, so it is not a cross-up strategy.
- Across all 727 Dataset days, the Run generated an average 177.17 ENTRY signals (median 178) but filled only 8.69 (median 11); aggregate fill rate was `4.9075%`.
- Because the first 09:01 close equals its one-bar VWAP and the engine stops after the first trigger, a separately named cross-up strategy would normally reproduce the same first-above event. It is not a justified next challenger without a different frozen semantic.

## R3 causal disposition

- **High confidence:** the exact strategy set is unusable; its admitted trades are negative before friction and deeply negative after friction.
- **High confidence:** the baseline is not a cash-admission-neutral estimate of
  all VWAP signals because admission is materially controlled by deterministic
  signal order and shared cash.
- **High confidence:** transaction friction amplifies a weak/negative price path; it cannot turn this baseline into a viable strategy by itself.
- **Medium confidence:** the persistent above-VWAP state has low selectivity, as shown by roughly 177 signals per day.
- **Not identified:** the independent effect of EOD exit and intraday path. MFE/MAE or fixed-horizon counterfactuals require a separate immutable bar-path analysis.
- Disposition is `HOLD / NOT ELIGIBLE`, not promotion and not automatic
  lifecycle mutation. A cash-admission-neutral sensitivity Run is required
  before permanently retiring the idea for research.

## R4 next research Gate

- Gate R5 keeps the exact VWAP Version, EOD exit, Dataset, costs, and engine; only capital allocation changes enough to eliminate cash admission bias.
- `starting_cash` and `position_fraction` must be derived before the Run from maximum eligible price, lot size, and maximum daily signals, with at least 20% cash buffer.
- Cash rejection must be exactly zero or the control is invalid.
- If pre-slippage P&L remains non-positive, stop tuning `above_vwap_entry` and proceed to independent atomic strategy benchmarking.
- The later benchmark matrix registers the other seven approved ENTRY strategies as seven predeclared family attempts under one frozen execution protocol. No combinations are tested until an atomic strategy passes screening.

## Decision boundary

- Diagnose from immutable evidence first.
- Do not tune parameters or publish a new Version in response to the baseline result.
- Treat any challenger as a separate family attempt with frozen protocol and untouched OOS data.

## R5/R6 Review remediation

- R5 is now explicitly a `cash-admission-neutral sensitivity control`, not a
  claim that current-equity sizing makes share allocation order-independent.
- R5 requires a dedicated mutation and durable `research_control_snapshot`;
  general Clone and Qualification Challenger semantics are not acceptable.
- The preflight formula is only a candidate-config screen. The completed Run's
  zero cash rejection and exact baseline signal-key parity are authoritative.
- R6 retains the existing server-owned `planned_attempts=20` and adjusted alpha
  `0.0025`; the seven strategies occupy sealed slots 1-7.
- Existing experiment attempts cannot preregister a hypothesis because
  `hypothesis_id` is currently written at Qualification time. R6 therefore
  requires a sealed matrix registration and compare-and-consume slot contract
  before execution is authorized.

## R5 authoritative-control re-review remediation

- R5 no longer accepts operator-supplied `starting_cash` or
  `position_fraction`. The server deterministically derives both from the
  frozen preflight using Decimal floor/ceiling rules and a fixed 80% buffer.
- A `(baseline_run_id, contract_version)` head and sealed registration revision
  admit exactly one authoritative control Run. A different idempotency key
  cannot create a second configuration; an invalid result requires a new
  contract revision and independent Review approval.
- R5 result performance remains hidden until a server-owned postflight verifies
  exact row/status identity, zero missing next bars, all ENTRY orders filled,
  zero non-filled reasons, exact candidate counts, and multiplicity-aware signal
  parity.
- The acceptance SQL now evaluates all conditions in one
  `REPEATABLE READ READ ONLY` snapshot and exits with code 3 on any failure.
- The canonical report artifact now contains a visible superseded notice and no
  longer describes R5 as fully allocation-neutral.
- Independent re-review approved and froze the R5 design. Implementation must
  cryptographically revalidate config/result/Dataset/control snapshots in
  product code; the reviewer SQL remains a second-layer condition audit.

## R5 implementation discovery

- The worktree is heavily shared and already has unrelated edits in
  `backtest/application.py`, `dashboard/server.py`, `backtest.js`, and several
  tests. R5 edits must be surgical and preserve the current working versions.
- Migration `011_strategy_set_archives.sql` exists as an untracked concurrent
  change; tracked migrations already include 012 and 013. R5 will use the next
  available number, 014, without modifying 011.
- Existing architecture already separates domain config, repository port,
  PostgreSQL adapter, application service, and FastAPI routes. R5 should extend
  these boundaries rather than add a parallel engine or persistence stack.
- The current `backtest/application.py` dirty delta only adds archived Strategy
  Set admission, while `dashboard/server.py` and `backtest.js` contain a larger
  concurrent Strategy Set lifecycle/UI change. R5 can avoid frontend edits in
  the first slice and add a dedicated strict API beside the existing Atomic Run
  route without altering those flows.
- Result access is owned by `BacktestApplicationService`, but the individual
  methods currently call the repository directly (`summary`, `result`,
  `trades`, `trade`, `drawdown`, `breakdowns`, `export`, `compare`, and
  `qualify`). R5 therefore needs one private accepted-control guard that every
  result-bearing path invokes; guarding only the Web route would be bypassable.
- The worker currently saves the immutable result before its separate terminal
  Run update. R5 needs a PostgreSQL-only atomic finalize operation that performs
  the server postflight and either publishes the result plus `COMPLETED` in one
  transaction or stores diagnostics plus an invalid terminal status without a
  result row.
- Generic retry/clone paths accept Atomic configs today. A sealed R5 control
  must be rejected by those generic paths so they cannot create a second
  control outside the authoritative registration.
- `BacktestRunConfig` has no research-control evidence field and `RunStatus`
  has no postflight/invalid terminal values. Both need explicit domain support
  so the control identity is part of `config_digest` and an invalid control
  cannot masquerade as a normal failure or completion.
- Chunked result persistence currently opens its own transaction. The shared
  row-writing logic must be extracted into a cursor-scoped helper so the R5
  repository can persist accepted results, registration/postflight evidence,
  and terminal Run state under one PostgreSQL transaction without changing
  legacy save semantics.
- The frozen preflight is an external canonical artifact referenced only by
  digest. Product creation therefore needs a deterministic local artifact
  catalog whose path is merely a locator, while the stored body/digest and all
  baseline/Dataset/strategy/cost identities are revalidated inside the
  PostgreSQL registration transaction.
- The initial revision is deliberately the only implemented creation path.
  Opening a later revision remains Review-gated and is out of this slice; an
  invalid revision is terminal and generic retry/clone cannot reopen it.
- Engine ENTRY orders already preserve the canonical postflight key fields
  (`symbol`, `created_at`, `primary_strategy_id`, ordered
  `triggered_strategy_ids`) and final status/fill evidence. R5 can compare
  grouped key multiplicities without changing the engine or adding a second
  execution projection.
- Cash rejection is represented by any ENTRY order whose final status is not
  `FILLED`; the postflight must reject all such statuses generically rather
  than matching localized reason text.
- The Dashboard already has a strict Pydantic request base and the same
  loopback/same-origin/CSRF mutation boundary used by Atomic Run creation.
  R5 can add one API route without weakening or duplicating Web security.
- The frozen document shows `idempotency_key` in the request body while the
  existing Atomic mutation convention uses the `Idempotency-Key` header. R5
  will require the header at HTTP, inject that key into the canonical service
  request, and keep caller-controlled sizing fields impossible via
  `extra="forbid"`.
- Existing `result_digest` intentionally covers summary, trades, equity, and
  decisions, but not order/fill chunks. R5 now revalidates that established
  digest and separately binds the baseline ENTRY signal multiplicity digest
  into the canonical preflight, so tampering either performance evidence or
  parity evidence fails closed.
- Qualification has a durable response-loss replay path. The R5 acceptance
  guard is intentionally placed after that replay and before current Run/family
  evaluation, preserving historical mutation replay while still preventing a
  never-accepted control from entering a new Qualification.
- Accepted performance access now reconstructs both the established result
  digest and the control ENTRY multiplicity digest before returning any
  summary/equity/trade/export projection. This prevents a post-acceptance
  result-row or chunk rewrite from relying solely on the registration verdict.
- PostgreSQL integration confirmed that the durable head/registration/operation
  transaction produces one authoritative control under different-key races,
  while response replay remains durable and invalid/tampered results fail
  closed without publishing performance.
- The preflight order projection can be a single-pass iterable. Signal
  multiplicity is accumulated during the primary pass rather than attempting
  to consume the source a second time.

## R5 implementation Review remediation

- The accepted read gate revalidates the established performance digest and
  signal-key multiplicity, but those identities omit ENTRY final status and
  actual fills. An accepted result can therefore be rewritten from `FILLED` to
  `REJECTED` with fills removed while retaining the old postflight verdict.
- The smallest durable correction is a canonical admission projection digest
  over all ENTRY order status/reason identity and all ENTRY fill multiplicity.
  It must be stored inside the digested postflight and recomputed from the
  current result on every accepted performance read.
- The remediation uses the complete canonical ENTRY order and ENTRY fill
  objects, preserving their list order, and bumps the postflight schema to v2.
  This binds status, reason, shares, IDs, timestamps, prices, costs, and source
  rather than relying on a fragile allowlist of admission fields.
- The formal acceptance SQL still reads counts from the old snapshot shape and
  postflight from result summary. Migration 014 stores preflight/postflight in
  the registration row, with counts under `preflight.statistics`; actual fill
  count must come from `fills` chunks.
- Chunked persistence always creates a typed manifest and only creates payload
  rows for non-empty arrays. SQL therefore counts actual ENTRY fills from
  `backtest_result_chunks(field_name='fills')`; zero fills correctly yields
  zero rows without requiring a synthetic empty chunk.
- The provider-free preflight CLI validates matching stored digest fields but
  does not recompute the baseline result digest before scanning bars. It must
  fail early on semantic result tamper.
- Remediation verification confirms the formal SQL accepts a valid Migration
  014 registration and exits non-zero after the actual ENTRY fill chunk is
  removed. The runtime read gate separately rejects a self-consistent durable
  order/fill chunk rewrite after acceptance.
- Follow-up Review found that successful engine orders carry a non-empty
  explanatory `reason`, `filled_at`, and embedded `fill`. The SQL rejection
  reason count must therefore be scoped to non-FILLED orders; the positive
  PostgreSQL fixture must preserve the real FILLED shape.
- PostgreSQL verification confirms the corrected predicate does not confuse a
  FILLED explanatory reason with a rejection reason, while non-FILLED reason
  evidence and actual fill-count failures remain fail closed.

## R5 authorized execution discovery

- `BacktestApplicationService` builds a PostgreSQL pool whose repository applies
  numbered migrations, and its R5 worker reads the immutable ordered Dataset,
  builds server postflight, and atomically finalizes through the R5 repository.
- The formal preflight CLI intentionally does not load `.env`; execution must
  inject the existing application environment without printing the DSN. A
  `MockProvider` will be supplied to the service so any accidental provider
  dependency remains local and observable rather than reaching FinMind or a
  broker.
- Application repository initialization applies forward-only migrations; the
  preflight itself remains read-only. Dataset binding authority is the
  `backtest.backtest_dataset_bindings` head plus immutable revision audit, so
  baseline config/binding evidence can be compared without following the
  current head.
- Formal preflight found 10 unmatched candidates. Durable baseline orders have
  only 6,321 FILLED entries and 122,481 cash-rejected entries; there are no
  other status/reason groups. Rejected signals stop at 12:44 because the frozen
  strategy entry window ends at 12:45, so the missing cases need exact
  symbol/session diagnosis rather than an assumption that they are 13:25
  terminal signals.
- Exact diagnostic evidence shows all 10 candidates occur at the last observed
  Kbar for that symbol/session. One was actually FILLED on the next session:
  1240 signalled at 2024-09-09 10:25 and filled at 2024-09-10 09:01 with
  `source=NEXT_BAR_OPEN`.
- The frozen engine only enforces a session-date boundary for
  `DAILY_NEXT_BAR`; ordinary intraday `NEXT_BAR_OPEN` remains pending until the
  next observed symbol Kbar, including the next session. The R5 preflight's
  same-calendar-date filter is therefore a correctness bug and must be aligned
  with baseline engine semantics before any registration is sealed.
- The corrected preflight is schema v2 and binds
  `NEXT_OBSERVED_SYMBOL_KBAR_V1` into algorithm identity. This makes the
  previously generated same-session artifact fail closed rather than silently
  changing the meaning of its digest.
- The official schema-v2 preflight completed against the immutable 28,325,340
  Kbar Dataset with artifact digest
  `fc6a682dafc831bd15234bcf75c68d6a715c9dbd90a8a78bdc1075b405bb2879`.
  All 128,802 candidates matched the next observed symbol Kbar and
  `missing_next_bar_count=0`; deterministic sizing remains
  `C=4,465,307,372` and `f=0.004387155994`.
- Canonical catalog reload and domain verification reproduce the schema-v2
  artifact exactly. Application PostgreSQL still has none of the Migration 014
  tables, so no head, registration, operation, or Control Run was written while
  the changed preflight contract awaits independent re-review.

## Evidence storage discovery

- `backtest.backtest_trades` is the normalized trade-grain projection and supports direct symbol/time/P&L segmentation.
- `backtest.backtest_result_chunks` owns the large decision, order, fill, trade, and daily-equity arrays used to reconstruct the immutable result.
- `backtest.backtest_qualifications` preserves the reviewer verdict and protocol evidence separately from the Run result.
- The application runtime uses `BACKTEST_DATABASE_URL`; the attribution queries must be read-only and must not use `TEST_POSTGRES_DSN` or create fixtures.
- The PostgreSQL schema stores Run identity separately from result summary and normalized decisions/trades/daily equity. Result chunks are limited to 100 items and typed by a fixed allowlist, so aggregate checks can be reconciled against both projections.
- Docker status is not observable inside the current sandbox. This is an access limitation only; database availability still needs a direct read-only connection check.
- Escalated read-only inspection confirmed the healthy `tsg-single-db` container and the existing `tw_intraday_trader` database. No fixture database or schema mutation is needed.
- The first qualification query used an incorrect assumed column name (`reasons_json`) and failed read-only. The table schema will be inspected before retrying; no data was changed.
- Migration inspection resolved that query error: reasons are inside canonical evidence/request projections rather than a standalone `reasons_json` column.
- The baseline has no row in `backtest_qualifications`; `INSUFFICIENT_EVIDENCE` is the Run summary verdict. A new research family/qualification has not yet been created.
- A first lookup guessed schema `strategy_catalog.strategy_versions` and failed read-only. The actual catalog migration/table name must be located before reading frozen parameters.
- The authoritative table is `backtest.strategy_versions`; the corrected lookup succeeded and resolved the parameter evidence.
