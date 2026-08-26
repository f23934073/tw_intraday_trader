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
- Formal revision 1 demonstrated why preflight sizing is only a candidate
  screen: `C*f` is just sufficient for one lot at the global `P_max`, while the
  engine sizes from current equity. After losses reduce equity, the same
  `position_fraction` can floor expensive symbols below one lot or exceed
  remaining cash. The authoritative Run therefore produced 10,520 cash
  rejections despite the 80% simultaneous-allocation buffer.
- Signal parity is also path-dependent. A pending intraday ENTRY may fill on
  the next observed symbol Kbar in a later session; the resulting position is
  processed before that session's ENTRY evaluation and can suppress a signal
  that exists in the cash-rejected baseline. The invalid control recorded 30
  fewer ENTRY orders, so a future revision cannot assume signal multiplicity is
  invariant when admission changes engine state.

## R5 contract revision 2 design discovery

- Revision 1 cannot be repaired by increasing starting cash or adjusting
  `position_fraction`: both remain tied to current-equity and shared-cash path
  state, so the final order size is not an invariant of the original signal.
- Exact signal parity cannot be proven by running the strategy through the
  portfolio engine again. Different admission changes pending fills and
  positions before later evaluations, which changes the signal stream itself.
- Revision 2 must therefore use the baseline ENTRY multiset as an immutable
  authoritative signal ledger. It must never call strategy evaluation while
  building control outcomes.
- Each ledger item must be replayed as an independent one-lot episode with no
  shared cash, current equity, portfolio position, owner state, or allocation
  ordering. Overlapping episodes are permitted research observations and are
  explicitly not an executable portfolio.
- Revision 2 can answer whether the frozen signal population has signal-level
  economic edge under fixed execution/cost assumptions. It cannot establish
  deployable portfolio performance, buying-power feasibility, or promotion to
  Local Paper.
- The independent exit rule must not be described loosely as "same-day close".
  Entry remains the first observed same-symbol Kbar strictly after the signal;
  exit is the first later same-symbol session-closing Kbar strictly after that
  entry event. If entry occurs on a session's final Kbar, exit moves to the next
  observed session close. Missing entry or exit evidence invalidates the whole
  replay.
- The current `HistoricalBacktestEngine` processes pending fills before
  strategy evaluation and keeps positions across sessions. It is therefore an
  unsuitable application service for revision 2; a separate deterministic
  signal-ledger replay domain/use case must own matching and episode P&L.
- Revision 2 should not create a normal `backtest_run` or publish portfolio
  equity/drawdown metrics. A separate research replay aggregate prevents the
  non-deployable overlapping episodes from entering compare, Qualification, or
  lifecycle paths by accident.
- R6 v1 assumes the accepted R5 portfolio Run and its cash-admission allocation
  are reusable as a canonical Baseline. Revision 1 invalidated that premise, so
  R6 must remain blocked and its execution contract must be reviewed separately
  after R5 revision 2 rather than silently inheriting the new episode semantics.
- Baseline order rows preserve strategy member IDs, not necessarily catalog
  Version IDs. Ledger rows therefore retain exact order member fields while the
  manifest binds the immutable Atomic Strategy Version snapshot.
- Freezing the ledger solves control-vs-baseline parity, but it does not recover
  counterfactual signals that the original baseline portfolio path never
  evaluated. The v2 population must always be labelled
  `baseline-observed signals`.
- Statistical bootstrap/CI semantics are deliberately excluded from revision 2
  rather than leaving user-controlled or implementation-dependent parameters.
  A positive point estimate remains exploratory and cannot qualify the strategy.

## R5 contract revision 2 G0 Review remediation

- Existing `result_digest` covers decisions but not orders/fills. V1 preserved
  only signal multiplicity, so no historical full ENTRY order projection seal
  exists. Revision 2 must use result-digest-bound ENTRY decisions as authority.
- Orders can only be a v2 inception-time derived projection: every authoritative
  ENTRY decision must map to exactly one current ENTRY order by `decision_id`,
  and every current ENTRY order must map back. The new seal must be labelled v2
  inception evidence rather than historical v1 evidence.
- Open-ended phrases such as "at least contains" conflict with exact-schema
  verification. Ledger, manifests, match rows, episodes, and postflight require
  enumerated fields, types, ordering, formatting, and digest projections.
- Equal total counts cannot prove identity parity. Postflight must verify
  bidirectional multiset equality at decision-ledger, ledger-match,
  match-episode, episode-modeled-entry, and episode-modeled-exit boundaries,
  including explicit duplicate-match rejection.
- Remediation makes ENTRY decisions the only historical signal authority.
  `signal_id` is decision-based; each ledger row binds the full source decision
  digest, and the manifest binds an exact decision-id/digest projection.
- Current orders are verified in both directions against decisions, but their
  projection is sealed only at v2 inception. The registration transaction
  recomputes that seal and later reads must reproduce it.
- All immutable schemas now have exact key sets and a shared canonical wire
  format: UTF-8 canonical JSON/JSONL, Taipei second-resolution timestamps,
  normalized Decimal strings, fixed precision/rounding, explicit row order,
  byte SHA-256, and body-without-self digest rules.
- Postflight parity uses `(sequence, signal_id, semantic_key)` grouped
  multiplicities. It checks both directions at six boundaries and stores every
  difference count, so equal-count substitution cannot pass.

## R5 revision 2 exact-contract re-review reopening

- The first three G0 blockers are closed, but exact-contract Review found three
  new internal contradictions; G0 remains not passed and not frozen.
- The Match manifest's two-field multiplicity token conflicts with the frozen
  three-field `(sequence, signal_id, semantic_key)` token used by section 8.1.
- `FINITE` Profit Factor lacks an exact quotient, scale-18 quantization,
  `ROUND_HALF_EVEN`, and canonical Decimal normalization contract.
- The authoritative decision projection preserves durable order, so its rows
  cannot be reordered without invalidating baseline identity. Reorder stability
  applies only to unpublished derived/external-sort chunks before canonical
  publication.
- The Match manifest now uses the same exact three-field layer token and
  `r5-layer-parity-projection-v2` schema as Result/Postflight; every
  `*_signal_multiplicity_digest` shares that definition.
- `FINITE` Profit Factor now freezes positive/negative `net_pnl` sums, Decimal
  division, scale-18 `ROUND_HALF_EVEN` quantization, normalization, zero cases,
  and fail-closed overflow behavior.
- Tests now distinguish raw authoritative-decision reorder, which invalidates
  baseline identity, from unpublished derived-chunk reorder, which must converge
  to the same canonical publication digest.
- **Disposition:** all three exact-contract Review fixes applied; ready for a
  short G0 re-review. G0 remains not passed/frozen, and no product code,
  migration, PostgreSQL state, replay execution, R6, Local Paper, provider,
  broker, or real-money work is authorized.

## R5 revision 2 G0 approval

- Independent exact-contract Review found no remaining blocker and approved the
  three-field parity identity, finite Profit Factor arithmetic, and split
  authoritative/derived reorder semantics.
- **Disposition:** `R5 v2 Design: APPROVED`; `G0: PASSED / CONTRACT FROZEN`.
- G1-G5 implementation/execution remain separately gated and unauthorized. R6,
  Local Paper, provider, broker, and real-money execution remain blocked.

## R5 revision 2 G1 authorization

- The user explicitly authorized the next phase, interpreted as G1 only: pure
  domain plus immutable filesystem artifacts.
- G1 must remain dependency-inward: domain math and identity cannot import
  PostgreSQL, dashboard, provider, broker, or Local Paper modules. Filesystem
  publication is an outer adapter over exact domain values.
- Success requires deterministic clean-root reconstruction, exact schema and
  canonical-byte rejection, complete layer multiplicity parity, one-lot golden
  math, cross-session matching, bounded streaming state, and interruption-safe
  publication tests.
- G2-G5, migration, application PostgreSQL, the official 28.3M-bar preflight,
  formal replay, R6, Local Paper, provider, broker, and real-money remain
  unauthorized.
- Existing `backtest.domain` already owns `canonical_json()`, `digest()`,
  `HistoricalBar`, and `TradeDecision`; G1 should reuse these values without
  changing their legacy serialization or result digests.
- Existing R5 v1 `research_control.py` demonstrates strict key-set validation
  and canonical artifact reload, but revision 2 needs an isolated bounded
  context because its independent episodes are not Backtest Runs.
- The G1 matcher can remain bounded by ledger/current-symbol state while
  streaming ordered bars: confirm each session close when the next session for
  that symbol arrives, then finalize the last observed bar at EOF. An entry on
  the confirmed closing bar remains open until the next session close.
- Artifact publication will use sequence-keyed external chunk sorting, exact
  canonical JSONL bytes, SHA-256 manifests, same-digest replay verification,
  and `BaseException` cleanup. Paths and temporary names remain outside identity.

## R5 revision 2 G1 candidate findings

- The production matcher is a one-pass iterator over canonical ledger rows and
  ordered bars. It retains only per-symbol waiting/pending state and the latest
  relevant bar; the convenience `build_match_plan()` collector is not the
  formal large-Dataset composition boundary.
- Filesystem payload publication now uses bounded fan-in external merge rather
  than opening an unbounded number of chunks. Canonical output remains ordered
  by frozen sequence and rejects duplicate sequence/signal identity.
- Match, modeled Entry/Exit, and Episode identifiers are reconstructed from
  their frozen projections. Result reload also rebuilds row lineage, one-lot
  economics, and summary, so self-consistent local SHA/manifest tampering cannot
  expose altered metrics.
- Match evidence distinguishes successful entry from complete entry/exit match:
  `matched_entry = matched_exit + missing_exit`, and
  `signal_count = matched_entry + missing_entry`.
- G1 remains a candidate pending independent Review. No PostgreSQL, migration,
  Web/API, official Dataset scan, replay registration/execution, R6, Local
  Paper, provider, broker, or real-money work was added.

## R5 revision 2 G1 Review remediation

- Review reproduced that a `ReplayBuild` calculated under one set of costs can
  be published under a different caller-supplied `cost_identity_digest`.
  Replay economics must carry their own exact cost projection/digest, and
  manifest/postflight must compare against it rather than trusting parameters.
- `ObservedBar.source_json` is currently canonical but not authoritative: its
  parsed symbol/time/session/OHLCV projection can disagree with the values used
  by matching. The boundary must require exact raw bytes and compare the full
  parsed `HistoricalBar` projection before accepting its digest.
- Only missing or explicit null `execution_horizon` may normalize to
  `INTRADAY_NEXT_BAR`; empty string, false, zero, and every other alias must be
  rejected in both decision-ledger and order-derivation construction.
- **Disposition:** G1 reopened as `REMEDIATION REQUIRED / GATE NOT PASSED`;
  G2-G5, R6, Local Paper, provider, broker, and real-money remain unauthorized.
- Cost validation is intentionally redundant at three boundaries: ReplayBuild
  construction/manifest binding, pre-publication artifact reconstruction, and
  postflight current-row reconstruction. The result manifest schema remains
  frozen because the existing `cost_identity_digest` is now made authoritative
  rather than adding another public field.
- Full source authority is checked by comparing exact canonical bytes to
  `HistoricalBar.from_dict(...).to_dict()` canonical bytes. This prevents
  unknown fields and JSON type aliases such as boolean volume from disappearing
  during parsing before the matcher-visible fields are compared.

## R5 revision 2 G1 approval and G2 authorization

- Independent short re-review approved G1 with no additional finding. The
  accepted evidence is `26 passed` focused, `42 passed, 6 skipped` related R5,
  and `1419 passed, 41 skipped` on the then-current shared no-DSN worktree.
- Formal R5 v2 progress is now 33.3%; this approval covers only pure domain and
  immutable artifact behavior.
- The user explicitly authorized G2. The scoped boundary is PostgreSQL plus
  application use cases: idempotency, head locking/revision CAS, baseline/v1/
  Dataset/order-seal revalidation, status CAS, terminal result publication,
  result redaction, and tamper/security tests.
- Migration inventory currently ends at 014, so G2 owns candidate migration
  `015_r5_signal_ledger_replays.sql`; the number must be rechecked immediately
  before publication because the worktree is shared.
- G3 full preflight, G4 formal replay, G5 disposition, R6, Local Paper,
  provider, broker, and real-money execution remain unauthorized.

## R5 revision 2 G2 candidate findings

- The replay aggregate is independent of normal Backtest Runs. Compare,
  Qualification, worker, and Strategy lifecycle code therefore cannot interpret
  an independent one-lot replay as portfolio evidence.
- Operation replay must precede current baseline and artifact validation. This
  safely returns the original result after response loss; different keys still
  re-enter full current-evidence validation.
- Registration request JSON/digest is immutable audit identity, not mutable
  metadata. Actor or change-note drift fails before a status or economics
  response is returned.
- PostgreSQL is the sole durable adapter. Head, registration, operation result,
  terminal postflight, result root, and chunks are transactionally consistent;
  there is no SQLite fallback.
- The small synthetic replay reaches `INVALID` because the frozen Gate requires
  128,802 authoritative signals. This proves redaction and absence of result
  rows without weakening the formal full-Dataset constant.
- Formal G2 remains open for independent Review. G3 full-Dataset preflight, G4
  replay execution, G5 disposition, R6, Local Paper, provider, broker, and
  real-money work remain blocked.

## R5 revision 2 G2 Review remediation

- Independent Review reproduced three scoped findings: operation-result scope
  substitution, cancellation progress regression, and numeric revision aliases.
- A self-consistent operation result digest is insufficient. Response-loss
  replay must additionally bind the stored result to the queried baseline,
  request preflight, current registration, replay ID, and head revision.
- `RUNNING -> CANCELLING` is an operator signal, not a progress update. The
  repository must preserve its already durable progress and only the worker's
  terminal `CANCELLED` transition may write a final progress value.
- JSON integer semantics are exact: booleans, floats, Decimal aliases, and
  coercible strings must be rejected for request and operation revisions.
- **Disposition:** `G2 REMEDIATION REQUIRED / FORMAL GATE NOT PASSED`; formal
  progress remains 33.3%, and all downstream execution/trading authority stays
  blocked.
- Remediation closes the operation identity substitution at five independent
  boundaries: baseline, request preflight, replay registration, head revision,
  and ledger manifest. A missing foreign replay is normalized to an integrity
  failure rather than leaking a lookup result.
- Progress preservation is owned by the repository transaction through
  `COALESCE(NULL::numeric, progress)`; the application cannot accidentally
  synthesize a new progress value for cancellation.
- **Updated disposition:** `G2 REMEDIATION CANDIDATE / INDEPENDENT RE-REVIEW
  REQUIRED`. Formal Gate and progress do not advance before approval.

## R5 revision 2 G2 approval

- Independent short re-review approved all three remediation boundaries with no
  new finding.
- Accepted reviewer evidence: PostgreSQL 17 remediation integration
  `15 passed`, full no-DSN `1482 passed, 56 skipped`, compilation, and
  `git diff --check`.
- **Disposition:** `G2 APPROVED / FORMAL GATE PASSED`; formal progress is 50%.
  This approval does not itself authorize G3, formal Replay, R6, Local Paper,
  broker, real-money, push, or any unrelated shared-worktree change.

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

## 2026-08-25 R5 revision 2 G3 authorization

- The user authorized G3 only after scoped commit `3ff0182`; G4 formal Replay,
  G5 disposition, R6, Local Paper, providers, brokers, and real-money remain
  outside the active scope.
- The existing pure matcher streams the full Dataset and retains only bounded
  per-symbol waiting/pending state; the 128,802 derived match rows are then
  published through the existing external-sort artifact boundary.
- G3 requires exact raw `bars.jsonl` bytes for entry/exit lineage. The new
  Dataset adapter verifies PostgreSQL registration against the local canonical
  manifest, exact HistoricalBar bytes, timestamp/symbol order, count, and
  payload SHA-256 while streaming.
- Baseline evidence is read in a repeatable-read, read-only PostgreSQL
  transaction with migration application disabled. The preflight composition
  has no strategy-evaluation, provider, broker, or simulation port.

## 2026-08-25 R5 revision 2 G3 execution evidence

- Formal preflight completed in one invocation over all `28,325,340` canonical
  Kbars with Dataset payload SHA-256
  `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d`.
- Ledger manifest digest is
  `b393bb79c917a446d836ee776ebe32fb25e3cf4da2761ee023db632ce2fa72a6`;
  match-plan/preflight digest is
  `65e16a54e8508c7f4489a95270f35f2cf8c06c3af7ccbad3b82e3300f19a7e58`.
- Counts are exact: signals `128,802`, matched entries `128,802`, matched exits
  `128,802`, missing entries/exits `0`, duplicate matches `0`.
- Independent artifact reload rebuilt canonical manifests and payloads;
  ledger-minus-match and match-minus-ledger multiplicity are both `0`.
- Strategy evaluation, provider, and broker call counts are all `0`.
- Application PostgreSQL has not applied migration 015; all five R5 v2 Replay
  relations are absent. G3 therefore created no durable Replay state. Applying
  migration 015 belongs to separately authorized G4, not this preflight.
- Full no-DSN passes `1487 passed, 57 skipped`; full disposable PostgreSQL
  17.11 passes `1544 passed`. The disposable database was removed.
- G3 is an implementation/execution candidate only. It requires independent
  Formal Review before progress can advance beyond 50% or G4 can be authorized.

## 2026-08-26 R5 revision 2 G3 Review remediation

- Independent Review found that the operation auditor verified canonical bytes,
  counts, parity, and artifact digests but did not bind its declared baseline
  and Dataset provenance to the immutable ledger and match manifests.
- The auditor now requires the exact operation-audit schema version and exact
  equality for `baseline_run_id`, `dataset_id`, `dataset_digest`, and
  `dataset_bars_sha256` across the audit, ledger manifest, and match manifest.
- Canonical valid-shape substitutions for each provenance field are regression
  tested and fail closed. Digest substitutions use valid 64-hex values so the
  test exercises provenance binding rather than input-shape rejection.
- The existing formal artifacts re-audit successfully with 128,802 signals,
  entries, and exits; both bidirectional parity differences remain zero. No
  Dataset rescan, PostgreSQL mutation, Replay execution, or G4 work occurred.
- **Disposition:** `G3 REMEDIATION CANDIDATE / FORMAL RE-REVIEW REQUIRED`;
  formal progress remains 50%.

## 2026-08-26 R5 revision 2 G3 approval

- Independent short re-review found no new finding and closed the provenance
  blocker after exact schema and three-way immutable-manifest verification.
- Accepted evidence: five canonical valid-shape substitutions fail closed,
  formal 128,802-row artifacts re-audit with `0/0` bidirectional differences,
  focused regression `31 passed`, compilation, and `git diff --check`.
- **Disposition:** `G3 APPROVED / FORMAL GATE PASSED`; formal progress is
  66.7%. G4-G5, R6, Local Paper, broker, and real-money remain separately
  gated.

## 2026-08-26 R5 revision 2 G4 implementation inventory

- G2 already owns durable create/replay, revision CAS, status transitions,
  terminal publication, redaction, and current-evidence reconstruction.
- G4 is missing the provider-free formal execution composition: load the exact
  sealed match plan, derive baseline cost identity, build one-lot episodes,
  publish the immutable result, build postflight, and invoke the existing
  atomic terminal publication boundary.
- Migration 015 remains the latest numbered migration and is the frozen G4
  schema. Applying it to application PostgreSQL is authorized only as part of
  the eventual formal G4 execution.
- The worker/composition must support deterministic continuation from `RUNNING`
  after process loss, but it must not invent a new registration, contract
  revision, Dataset, strategy evaluation, provider, or broker dependency.

## 2026-08-26 R5 revision 2 G4 execution evidence

- One authoritative registration was created for baseline
  `run-91ad87981676414da87b928398fa43c9` at revision 1. Its replay ID is
  `replay-e70d205528ef4e5f891f3d6f3c99997a`.
- Formal result manifest digest is
  `420ef2dd3c3e814e0691eef0531c2c6f787789278675d092b86df3e1f9fa3347`;
  postflight digest is
  `ca041816dd69454ce53d321fa8a78cb0188a267d5ab2b7c864eb58051a557ad9`.
- The terminal state is `ACCEPTED` with exactly 128,802 episodes, modeled
  entries, and modeled exits; provider and broker call counts are zero.
- Formal repeatable-read SQL found one head, registration, operation, and
  result; all terminal evidence matched, all three chunk projections contained
  128,802 items, and four episode/entry/exit `EXCEPT ALL` differences were zero.
- A same-key response-loss replay returned the same replay/result/postflight
  identities with `replayed=true` and exit 0 after rebuilding current DB and
  artifact evidence. It did not create a second revision or operation.
- The accepted research summary is economically negative: 33,629 wins and
  95,173 losses, profit factor `0.379778394606756598`, pre-slippage P&L
  `-143,770,050`, explicit costs `289,116,272.865185625`, and net P&L
  `-482,357,421.040185625`. G4 acceptance proves replay integrity, not strategy
  eligibility; interpreting these metrics belongs to separately gated G5.
- **Disposition:** `G4 IMPLEMENTED / EXECUTED / FORMAL REVIEW REQUIRED`;
  formal progress remains 66.7% until independent Review.

## 2026-08-26 R5 revision 2 G4 Review findings

- Formal SQL independently recomputes only episode-to-entry and episode-to-exit
  parity. The first four boundaries currently trust stored postflight booleans,
  and the invocation has no externally supplied result/postflight digest anchor.
  A self-consistent terminal-root rewrite can therefore evade the read-only Gate.
- A cancel committed while the replay build is running changes registration to
  `CANCELLING`. Publication then loses its status CAS, while the CLI exception
  handler only terminalizes `RUNNING`, leaving the authoritative replay stuck.
- Required remediation is scoped to SQL evidence, cancellation terminalization,
  and PostgreSQL regressions. The existing immutable Replay artifact should not
  need rebuilding. G5 and all execution integrations remain unauthorized.
- **Disposition:** `G4 REMEDIATION REQUIRED / FORMAL GATE NOT PASSED`; formal
  progress remains 66.7%.

## 2026-08-26 R5 revision 2 G4 remediation evidence

- Formal SQL now requires the externally reviewed result manifest and postflight
  digests. It verifies exact result/summary/postflight/condition/diagnostic
  schemas, manifest lineage, all diagnostic counts, all 12 directional parity
  differences, all seven duplicate counts, and the adjacent parity-digest chain.
- The ledger manifest's `ledger_semantic_multiplicity_digest` is intentionally a
  different canonical projection from `r5-layer-parity-projection-v2`. Formal SQL
  therefore anchors the parity chain to the match manifest's parity digest while
  independently binding ledger-to-match lineage through manifest digest and
  `ledger_rows_sha256` equality.
- A real PostgreSQL fixture proves the strengthened SQL accepts the anchored
  projection, rejects a self-consistent terminal root substitution, and rejects
  a nonzero decision-to-ledger diagnostic even when the substituted postflight
  digest is supplied as the expected root.
- The publication-race regression pauses immediately before terminal CAS, saves
  progress `0.42`, commits cancel, resumes publication, and verifies terminal
  `CANCELLED` with no durable result/postflight row.
- Existing formal response-loss reconstruction returned `replayed=true`, the
  same revision/result/postflight identities, 128,802 episodes, and zero provider
  or broker calls. Strengthened application SQL then passed every evidence flag.
- Full no-DSN regression passes `1555 passed, 61 skipped`; full disposable
  PostgreSQL 17 regression passes `1616 passed`. Compilation, scoped whitespace,
  and `git diff --check` pass, and the disposable container was removed.
- **Disposition:** `G4 REMEDIATION COMPLETE / FORMAL RE-REVIEW REQUIRED`;
  formal progress remains 66.7% and G5 remains unauthorized.

## 2026-08-26 R5 revision 2 G4 independent approval

- Independent short re-review found no new blocking or important finding.
- Formal SQL is externally anchored to the reviewed result and postflight
  digests, verifies exact terminal schemas and all parity boundaries, and
  fails closed on root substitution or diagnostic tampering.
- Concurrent cancellation converges durably to `CANCELLED` with preserved
  progress and without terminal result publication.
- The accepted immutable Replay remains unchanged: result digest
  `420ef2dd3c3e814e0691eef0531c2c6f787789278675d092b86df3e1f9fa3347`,
  128,802 episodes, profit factor `0.379778394606756598`, and net P&L
  `-482,357,421.040185625`.
- **Disposition:** `G4 APPROVED / FORMAL GATE PASSED`; formal progress advances
  to 83.3%. This approval establishes replay integrity only and does not make
  the strategy eligible for promotion, Local Paper, broker, or real-money use.
