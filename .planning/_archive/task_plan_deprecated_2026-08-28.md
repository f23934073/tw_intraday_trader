> Deprecated on 2026-08-28. This file's `Current Phase` (Phase 13) had drifted
> from `.planning/.active_plan` and `progress.md` (Phase 17). Per DOC-001, the
> single source of truth for the active plan is
> `.planning/<active_plan>/task_plan.md`.

# Task Plan: Build the intraday trader execution foundation

## Goal

Produce a repository-grounded implementation plan for next-session premarket watchlists generated only from completed prior-session data, without pre-open indicative quotes, broker calls, or automatic orders.

## Current Phase

Phase 13 — Freshness Calibration Evidence

## Phases

### Phase 1: Requirements and proposal intake

- [x] Read the supplied five-stage proposal completely.
- [x] Capture explicit constraints, intended outcomes, and open assumptions.
- [x] Confirm repository instructions and worktree state.
- **Status:** complete

### Phase 2: Repository architecture trace

- [x] Map the current runtime flow and ownership boundaries.
- [x] Inspect the named engines/stores, configuration, persistence, and tests.
- [x] Record current guarantees, gaps, and reusable code.
- **Status:** complete

### Phase 3: Optimization review

- [x] Compare the proposal against current code and tests.
- [x] Prioritize correctness, data integrity, concurrency, observability, performance, and rollout risks.
- [x] Separate confirmed findings from assumptions requiring validation.
- **Status:** complete

### Phase 4: Implementation-plan authoring

- [x] Write a phased, dependency-aware implementation plan with exact code areas.
- [x] Define acceptance criteria, test strategy, migration/rollback, and explicit non-goals.
- [x] Keep the plan implementation-free and reviewable before any coding starts.
- **Status:** complete

### Phase 5: Verification and delivery

- [x] Cross-check the final plan against the supplied proposal and repository evidence.
- [x] Verify no product-code implementation was made.
- [x] Deliver the plan and summarize the highest-value adjustments.
- **Status:** complete

### Phase 6: Web Simulation and Portfolio Plan Extension

- [x] Map a manual Shioaji Simulation order ticket onto the existing dashboard without exposing the SDK to the browser.
- [x] Define simulation order, order-status, and portfolio/position API and UI contracts.
- [x] Ensure future programmatic orders reuse the same application service, Risk, Journal, OrderManager, and Broker path.
- [x] Update phases, tests, security controls, file map, and Definition of Done.
- [x] Verify no product-code implementation was made.
- **Status:** complete

### Phase 7: Local web paper simulation implementation

- [x] Add a session-local paper order/position service with idempotent manual commands.
- [x] Expose simulation-only APIs and connect dashboard refresh to local projection updates.
- [x] Add order ticket, order blotter, and simulation holdings data to the Traditional Chinese dashboard.
- [x] Add focused unit/API tests and run the complete regression suite.
- [x] Update user documentation and verify no Shioaji or live-order path is invoked.
- **Status:** complete

### Phase 8: Shioaji Tick/BidAsk simulation quote updates

- [x] Define an internal streaming quote contract with last trade, best bid/ask, exchange time, and receipt time.
- [x] Add Shioaji Tick/BidAsk callback registration plus idempotent dynamic subscribe/unsubscribe lifecycle.
- [x] Make local simulation holdings and pending orders consume streaming quotes and use ask/bid for fill eligibility and price.
- [x] Add projection polling and visible quote freshness/source status without polling Shioaji snapshot APIs.
- [x] Add focused callback, subscription, fill, API, and frontend tests; run complete regression and static checks.
- [x] Update README with streaming behavior, fallback, and non-broker-order boundary.
- **Status:** complete

### Phase 9: Basic strategy expansion implementation plan

- [x] Reconfirm the current strategy catalog, backtest runtime, data contract, and test boundaries.
- [x] Define research-safe v0/v1 contracts for ORB, EMA crossover, RSI/Bollinger mean reversion, ATR stop, and time stop.
- [x] Specify the minimum shared rolling-state changes without creating a generic strategy DSL.
- [x] Write dependency-ordered implementation phases, migrations, API/UI changes, tests, rollout, and rollback gates.
- [x] Verify the plan is implementation-free and does not authorize broker or real-money execution.
- **Status:** complete

### Phase 10: Implement basic strategy expansion

- [x] Capture a focused regression baseline and protect unrelated worktree changes.
- [x] Implement per-symbol/session Kbar cadence capabilities and API/worker fail-closed strategy preflight.
- [x] Implement deterministic Decimal indicators and bounded historical feature snapshots.
- [x] Implement and register ORB, EMA crossover, RSI/Bollinger reversion, ATR stop, and time stop strategies.
- [x] Preserve legacy defaults while exposing new experimental strategies and capability reasons in the Dashboard.
- [x] Add focused unit, engine, API, catalog, and UI regression coverage.
- [x] Update user documentation, run focused/full/static verification, and confirm no broker-order path was added.
- **Status:** complete

### Phase 11: Previous-day premarket watchlist implementation plan

- [x] Reconfirm current Candidate, strategy catalog, historical-data, API, and Dashboard seams.
- [x] Freeze no-preopen-data contracts for momentum/liquidity, NR7, and oversold watchlists.
- [x] Define as-of-date, trading-calendar, survivorship, data-quality, and look-ahead safeguards.
- [x] Write a dependency-ordered implementation plan with exact files, tests, rollout, and rollback.
- [x] Verify only planning Markdown changed in this phase and no product implementation was added.
- **Status:** complete

### Phase 12: Rewrite previous-day watchlist Phase 0-3

- [x] Promote corporate-action and price-limit normalization to a P0 data gate.
- [x] Add Momentum close-location/daily-return evidence with explicit OOS variants.
- [x] Rename NR7 to direction-neutral compression and specify false-compression exclusions.
- [x] Keep Oversold confirmation-only and make net-of-cost evidence a formal validation gate.
- [x] Rewrite implementation phases 0-3 and reconcile all affected plan identifiers/contracts.
- [x] Verify the revised plan is internally consistent and no product code changed in this task.
- **Status:** complete

### Phase 13: Freshness Calibration Evidence

- [x] Freeze scope: only evidence for the eight FreshnessPolicyV1 thresholds; no Portfolio domain or Phase 1 work.
- [x] Trace existing quote and account-data paths, event timestamps, queue/store boundaries, and safe capture seams.
- [x] Define and add a standalone, data-only calibration harness plus immutable evidence schema.
- [x] Freeze the reviewer-facing cohort and session-label selection protocol without assigning unsupported liquidity tiers.
- [x] Complete non-sensitive capture preflight: local CLI/runtime, credential presence only, timezone, artifact integrity, and output readiness.
- [x] Record SDK lifecycle provenance and require paired Tick/BidAsk acknowledgement before a capture calls its subscription active.
- [x] Publish a read-only broker/account evidence intake checklist; do not add a broker adapter or call account endpoints.
- [x] Obtain and validate a prior completed-session official TWSE quote snapshot as the provenance source for cohort selection.
- [x] Freeze the 2026-08-20 high/mid/low cohort manifest before its qualified captures begin.
- [ ] Collect and inspect live data-quality evidence segmented by liquidity and session period; record quote versus broker/account collection gaps separately.
- [x] Produce the initial review report with no threshold candidates and retain `BLOCKING_EVIDENCE`.
- **Status:** in_progress

### Phase 13o: Trading-session quote-evidence scheduling

- [x] Replace the unavailable legacy automation control plane with an explicitly bounded local campaign runner.
- [x] Run only after a reviewed Taiwan-equity calendar check; on a closed session, record a no-capture result and make no provider call.
- [x] Configure immutable-cohort Tick/BidAsk-only captures for opening, continuous, and a close interval that crosses the 13:30 boundary.
- [x] Preserve the existing artifact schema, collector, quality gate, `subscribe_trade=False`, and all eight thresholds as unset.
- [x] Keep broker/account evidence excluded pending separate explicit read-only authorization.
- [x] Install and verify the user-level launchd job.
- **Status:** complete

### Phase 13p: Accelerated quote-evidence cadence

- [x] Preserve the frozen cohort, labels, collector, schema, and quality gates.
- [x] Add non-overlapping 15-minute opening/continuous captures to increase per-session coverage without changing threshold selection.
- [x] Update the local launchd schedule and verify the loaded job has the additional triggers.
- [x] Keep broker/account APIs, all eight thresholds, and Portfolio Phase 1 out of scope.
- **Status:** complete

### Phase 13q: Automated post-capture evidence QA

- [x] Reuse the existing immutable artifact inspector; do not calculate or freeze freshness thresholds.
- [x] Produce a review-ready JSON summary for each scheduled capture: digest/schema, paired acknowledgement, lifecycle, coverage, callback errors, monotonicity, and clock-skew counts.
- [x] Fail closed when a capture artifact fails structural inspection, while preserving its raw immutable artifact for investigation.
- [x] Keep qualitative and final policy disposition human-reviewed; do not add broker/account collection or Portfolio code.
- **Status:** complete

### Phase 13r: Broker/account read-only freshness evidence

- [x] Add calendar/time-gated read-only scheduling for five bounded daily observations and install its separate user-level job.
- [ ] Capture and separately analyse the four evidence kinds: positions, orders, accounting, and buying power; retain a constrained gap when an allowed source cannot provide one.
- [x] Preserve no-mutation boundaries: no submit, cancel, order/deal callback, CA activation, or use of an action-like order refresh API.
- [x] Persist only redacted structural metadata, timings, provider as-of availability, outcome, and an integrity digest; no credentials, account identifiers, positions, balances, or order details.
- [x] Treat unavailable endpoints or freshness paths as evidence gaps, not as successful observations or substitute thresholds.
- [ ] Keep all eight FreshnessPolicyV1 thresholds unset and Portfolio Phase 1 blocked pending repeated trading-session observations and review.
- **Status:** in_progress

### Phase 13s: Quote-evidence scheduler hardening

- [x] Accept a bounded late launch for a configured quote window and record its scheduled time and delay.
- [x] Make the launchd command independent of a successful inherited working directory.
- [x] Add focused regressions for on-time, bounded-late, and expired launch attempts.
- [x] Reinstall and inspect the user launchd job; no provider capture is run outside a permitted window.
- **Status:** complete

### Phase 13t: Frozen close-window evidence — 2026-08-25

- [x] Complete a read-only NTP preflight without changing the host clock.
- [x] Capture one Tick/BidAsk-only 15-minute close artifact for the frozen cohort.
- [x] Inspect digest/schema, paired acknowledgement, lifecycle, coverage, clock-skew, callback errors, and monotonicity.
- [x] Publish the review and retain every threshold as unset.
- **Status:** complete

### Phase 13v: Frozen close-window evidence — 2026-08-26

- [x] Complete a read-only NTP preflight without changing the host clock.
- [x] Capture one Tick/BidAsk-only 15-minute close artifact for the frozen cohort.
- [x] Inspect digest/schema, paired acknowledgement, lifecycle, coverage, clock-skew, callback errors, and monotonicity.
- [x] Publish the review and retain every threshold as unset.
- **Status:** complete

### Phase 13w: Post-session cross-evidence verification — 2026-08-26

- [x] Audit the immutable quote and broker/account artifacts collected through 2026-08-26 without selecting a threshold.
- [x] Verify the installed quote close trigger can observe the 13:30 boundary; no scheduler correction is needed.
- [x] Publish a review that separates qualified observations, constrained endpoint gaps, and remaining FreshnessPolicyV1 blockers.
- **Status:** complete

### Phase 13x: Frozen close-window evidence — 2026-08-27

- [x] Capture and review one frozen 15-minute Tick/BidAsk close artifact with all thresholds unset.
- **Status:** complete

### Phase 13u: Minimum viable passive-capture qualification

- [x] Preserve the existing Tick/BidAsk validation, Health, Admission, Freshness, watermark, and safety contracts.
- [x] Persist every callback mapping failure in a checksummed raw-market-data quarantine artifact.
- [x] Treat fully accounted quarantine entries as warnings while retaining queue drain, finalized Journal verification, and exact replay as hard pass conditions.
- [x] Report `COMPLETE_WITH_WARNINGS`, warning details, and `NOT_RUN` replay truthfully in session, CLI, and daily evidence.
- [x] Add focused regressions and run the relevant market-data test suite without starting a live provider capture.
- **Status:** complete

### Phase 13x: One-shot OPEN external runner

- [x] Inspect the current D-HEALTH-LATE-001 automation, existing launchd conventions, and the reviewed OPEN time window without starting a provider session.
- [x] Add the smallest one-shot macOS launchd runner that executes the frozen OPEN command outside the Codex sandbox from its first and only attempt.
- [x] Preserve the existing loopback guard, `subscribe_trade=false`, foundation flags off, and all Health/Admission/Freshness/watermark/gate contracts.
- [x] Change the Codex automation to read-only artifact verification only, without fallback execution or retry.
- [x] Validate configuration and tests without running the live OPEN capture early or creating a second session.
- **Status:** complete

### Phase 13y: Immutable OPEN runtime remediation

- [x] Unload the LaunchAgent that referenced the shared dirty checkout; verify it had `runs=0` and created no claim/result/session/evidence.
- [x] Create a clean dedicated worktree and branch from reviewed `origin/main@33c9b3a` without modifying shared dirty main.
- [x] Transplant and commit only the reviewed D-HEALTH runner payload needed for the guarded passive OPEN capture.
- [x] Pin and verify source, cohort, calendar, interpreter, dependency/runtime, command, and commit identity before the provider callable can run.
- [x] Add adversarial drift tests proving provider calls remain zero and a durable fail-closed result is emitted.
- [x] Re-run focused verification and load a plist pointing only at the pinned clean checkout; read back exact path, HEAD, runtime identity, and `runs=0`.
- [x] Preserve the existing Codex automation as one-shot read-only inspection; do not push or merge.
- **Status:** complete

### Phase 13z: External credential boundary and terminal-result hardening

- [x] Unload the pinned LaunchAgent while `runs=0`; confirm no claim/result/session/evidence and preserve the 09:35 read-only automation.
- [x] Select one explicit owner-controlled secret-file path using metadata and allowed-key presence only; never expose or persist secret values or hashes.
- [x] Load only Shioaji key/secret aliases and `SJ_SIMULATION` after complete source/runtime identity verification, with owner/mode/presence fail-closed checks.
- [x] Guarantee every post-claim credential/calendar/import/subprocess setup failure produces one auditable terminal `NOT_RUN` result while provider callable remains zero where applicable.
- [x] Add adversarial no-secret-leak and filtered-child-environment tests without creating the formal claim/result paths.
- [x] Make `source_payload_head` semantics verifiable or remove the unaudited field; reseal manifest, HEAD, and loaded boundary.
- [x] Re-run focused tests, compilation, plist/shell/diff checks, read-only identity rehearsal, and final `runs=0` readback without kickstart/capture.
- **Status:** complete

### Phase 14: Active branch, PR, and Codex-task reconciliation

- [x] Inventory every local and remote branch not merged into `main`, including its checkout/worktree and upstream status.
- [x] Map each active branch or open PR to its owning Codex task and inspect whether that task is running, waiting, complete, or blocked.
- [x] Resume idle incomplete tasks in their original conversations without broadening their approved scope or safety gates.
- [x] Review completed branches and PRs in the non-overlap scope; no eligible completed branch or PR remains to review.
- [x] Merge only approved, current, conflict-free work whose required checks pass; no eligible merge candidate remains outside the excluded readiness scope.
- [x] Continue the next authorized stage and start only dependency-safe parallel work; no non-overlap active or resumable task remains in the current snapshot.
- [x] Receive explicit release authority for `codex/shadow-fill-v3-compat-20260827@47a9303da0db26a17dd553488901af8caa423a55` to `https://github.com/f23934073/tw_intraday_trader.git`.
- [x] Re-fetch and verify `origin/main@33c9b3a`, a clean exact branch payload, `0 behind / 1 ahead`, ancestry, and whitespace before push.
- [x] Push the exact Shadow branch and create GitHub PR #3 without changing the authorized commit.
- [x] Fix PR #3 PostgreSQL timestamp/fingerprint reconstruction after CI exposed `TIMESTAMPTZ` offset normalization; local re-review and all no-DSN checks passed at fix commit `f6a38b1`.
- [x] Reconcile the external early merge of failed PR #3 at `023a082`; verify it contains authorized commit `47a9303` but not the later fix.
- [x] Complete forward-fix PR #4 through head `254317b`; all three checks passed, remote `main@7931d31` contains the authorized commit and both reviewed fixes.
- [x] Refresh the post-`7931d31` local/remote branch, PR, worktree, and Codex-task inventory outside the `評估實盤交易就緒差距` ownership tree; classify each remaining item as active, blocked, stale lineage, or review-ready.
- **Status:** complete

### Phase 15: Idle and not-loaded Codex task reconciliation

- [x] List every visible repository task, including `idle` and `notLoaded`, not only active processes.
- [x] Exclude the complete ownership surface of `評估實盤交易就緒差距`, while recording the boundary explicitly.
- [x] Read each remaining candidate task's latest turns and classify it as complete, blocked, stalled-resumable, superseded, or unrelated repository.
- [x] Resume only stalled, incomplete, non-overlap tasks in their original conversations; do not broaden their authority.
- [x] Map any deliverable branch or commit to current `origin/main`, then review and integrate only when approved and CI-qualified.
- [x] Report every remaining unfinished conversation by exact title and task id.
- **Status:** complete; all safe continuations were returned to their owning conversations and remaining gates require explicit owner or external-system authority

### Phase 16: R6 A2 Migration 018 remote release

- [x] Re-freeze exact branch, commit, parent/base, clean-worktree state, and remote destination before any write.
- [x] Deliver the exact scoped owner authorization to the original `歷史台股回測準備度` task and supervise its push/PR workflow.
- [x] Verify the created PR contains only `ed477898` on the current `main` baseline and retains the reviewed release/G3 boundaries.
- [x] Wait for every required CI check and review/integration gate; route any failure or request-change back to the owning task.
- [x] Merge only after all gates pass, fetch the resulting `main`, and prove the exact commit is reachable from `origin/main` with no forbidden next-stage action.
- **Status:** complete; PR #6 merged as `d5b86382c06a34e3a26ba2b23e3d714c783f0348`, post-merge main CI is green, and all excluded stages remain untouched

### Phase 17: Resume unfinished historical-data and R6 research stages

- [x] Resume `建立三年歷史資料` in its original task, synchronize its stale activation workpad, and independently verify the newly materialized immutable Dataset that consumes the ACTIVE 9960 overlay without any provider request; the 51,213,436-bar full equality audit and PM review passed with zero mismatch and P1/P2=0.
- [x] Resume `歷史台股回測準備度` on merged `main`, revalidate the formal PostgreSQL and immutable-artifact preconditions, and identify the exact current G3 continuation transaction.
- [ ] Complete the already-authorized R6 research stage: audit registration and CAS revision-3 activation are durable, exactly one G3 preflight is running under the existing supervisor, and artifact/PostgreSQL verification plus Gate review remain; do not enter G4 or any trading stage.
- [ ] Monitor both original tasks, independently review their deliverables, issue request changes on any blocker, and keep iterating until approved or an exact missing owner identity/authority is required.
- [x] Resume the dependency-safe offline continuation of `確認三大法人策略資料`, freeze its FinMind consumer plan, and keep the duplicate 2,781-symbol Shioaji r3 scan paused.
- [x] Complete the approved FinMind Dataset metadata-only handoff to `確認三大法人策略資料`; independently verify the sole candidate observation still targets 2026-08-19 outside the Dataset range, and keep Evaluation Universe freeze blocked until a digest-pinned institutional series supplies at least 60 overlapping target sessions.
- [ ] Reconcile other visible unfinished non-overlap tasks after these safe continuations are stable; preserve the `評估實盤交易就緒差距` exclusion tree and external STE-5 blocker.
- **Status:** in_progress

## Key Questions

1. Which parts of the supplied proposal duplicate or conflict with existing repository behavior?
2. Which improvements are required for correctness or operability versus optional optimization?
3. What dependency order minimizes rework and permits safe verification after each stage?
4. What measurable acceptance criteria prove each stage is complete?
5. Which of the eight FreshnessPolicyV1 thresholds can be supported by current data, and which require a separate read-only broker/account evidence source?

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Start with local paper simulation rather than Shioaji Simulation | The user has now authorized implementation, but no verified account/CA integration exists; this makes the requested web workflow usable without creating an unverified broker claim. |
| Ground every proposed change in repository evidence | Avoid replacing existing components or inventing interfaces already present. |
| Preserve research/data-only boundaries unless the supplied request explicitly changes them | Prior project guidance treats real-money execution as prohibited and requires fail-closed data handling. |
| Unify Historical Backtest and paced Replay on one event-driven kernel | They differ primarily in clock speed; separate engines would create parity drift. |
| Emit `TradeIntent` before broker-ready `OrderRequest` | Strategy evidence should not own capital sizing, broker lot units, tick-size normalization, or transport fields. |
| Put risk, data health, idempotency, and journal before every automated broker mode | Safety and audit behavior must be exercised in Replay/Shadow/Simulation, not introduced only for live trading. |
| Add live-data Shadow before Shioaji order Simulation | It validates streaming, scheduling, freshness, duplicate suppression, and journal behavior without any order API call. |
| Exclude Small Live and Production from this implementation plan | They conflict with current scope and need a separate, explicit authorization/RFC. |
| Add web-based manual orders only to Shioaji Simulation | The user requested browser simulation controls, while production/live remains explicitly out of scope. |
| Route both browser and future strategy orders through one application service | Prevents UI orders from bypassing Risk, idempotency, Journal, OrderManager, reconciliation, or Broker normalization. |
| Use Shioaji Tick/BidAsk only as the local simulator's market-data source | The user authorized realtime quote subscriptions, not Shioaji or live-money order submission. |
| Treat quote and broker/account freshness as separate evidence campaigns | The approved Phase 0 baseline explicitly prohibits deriving broker/account SLA from quote latency. |
| Collect broker/account evidence under the explicit owner authorization | The source remains read-only: one bounded account scope, `subscribe_trade=False`, no CA, no order mutation/cancellation, no trade callback, and no action-like order refresh. |
| Mark remotely fresh orders unavailable when their only refresh route is out of scope | A locally cached order list cannot support `broker_orders_stale_after_ms`; it must be recorded as a constrained evidence gap rather than inferred from another source. |
| Prepare cohort evidence as reviewer-supplied labels, not inferred liquidity facts | The current checkout has no reviewed liquidity ranking data; assigning tiers from reputation would bias the calibration evidence. |
| Subscribe only held and pending-order symbols | Keeps the stream bounded and avoids turning the dashboard into a full-market realtime scanner. |
| Complete the Freshness evidence chain before Portfolio Phase 1 | Execute close-window quote evidence, cross-session quote evidence, source-clock disposition, then separately authorized broker/account evidence. Until `FreshnessPolicyV1` is frozen, do not implement migrations, Portfolio core, RiskGate freshness, provisional thresholds, or broker/account reads. |
| Run the next OPEN capture through one pre-authorized local launchd attempt | Shioaji requires loopback binding; the Codex sandbox must not be attempted first because the evidence contract prohibits retries or session selection. |
| Reconcile branches, PRs, and Codex tasks before any new implementation | A branch name or ended conversation is not merge evidence. Merge requires current scope review, required checks, and an approved disposition; later stages retain their own authorization gates. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Initial combined lookup produced no output because a no-match `rg` stopped later `&&` reads | 1 | Re-ran the independent reads in parallel and obtained the complete skill instructions. |
| Initial planning-session check used a non-existent `check-session.sh` script | 1 | Read the installed skill and used its documented `session-catchup.py` instead. |
| First stream test compared binary floating-point PnL with exact equality | 1 | Kept production arithmetic unchanged and used `pytest.approx` for the monetary assertion. |
| Live dashboard shutdown left the Shioaji native client logged in and emitted a native-thread panic | 1 | Added a Provider close contract and explicit Shioaji logout during FastAPI lifespan shutdown. |
| Initial Phase 9 planning patch expected the wrong `findings.md` title | 1 | Re-read the existing planning-file headers and applied a scoped patch with the actual title. |
| New plan initially ended with one extra blank line | 1 | Removed the trailing blank line and re-ran whitespace validation. |
| Initial Phase 10 planning patch used an over-specific multi-file context | 1 | Split the planning updates into scoped per-file patches. |
| First focused pytest command referenced absent backtest test filenames | 1 | Listed the actual test modules before rerunning the focused suite. |
| `node --check` cannot parse an `.html` file directly | 1 | Keep Python compilation evidence and validate the extracted inline script with a Node file-read command. |
| First README patch included an unnecessary second context with a typo | 1 | Applied only the verified historical-backtest paragraph context; unrelated README edits stayed intact. |
| First Phase 12 completion patch expected an outdated `previous-day premarket` label | 1 | Re-read the live planning block and applied the completion update against the actual `previous-day watchlist` heading. |
| First qualified multi-symbol quote capture persisted `PENDING` after all paired acknowledgements | 1 | Preserve the raw artifact as rejected evidence; repair aggregate-to-per-symbol lifecycle state propagation and add a multi-symbol regression test before recapture. |
| Initial automation inspection used an unsupported `action` field | 1 | Tool returned its valid mode discriminator; use its `view` mode to inspect existing automations before creating a close-window heartbeat. |
| Long-running capture runner returned control before the child process completed, causing duplicate retry attempts | 1 | Verified the actual process table, terminated only the two later duplicate subscriptions, and retained the earliest capture as the sole second continuous sample. |
| Initial cross-artifact profile one-liner had mismatched parentheses | 1 | No artifact changed; replace the dense expression with a readable, read-only short script. |
| Initial multi-file close-review patch omitted one added-line prefix | 1 | No file changed; split the documentation update into small exact-context patches. |
| 2026-08-26 post-session scheduler assertion imported a non-existent calendar helper | 1 | Use the existing scheduled-runner calendar construction rather than retrying the invalid import. |
| 2026-08-26 post-session combined review patch omitted an add-file line prefix | 1 | No file changed; add the review first, then update tracking files separately. |
| First 2026-08-21 close-review patch repeated the added-line-prefix omission | 2 | No file changed; create the review in smaller audited patch blocks before updating the ledger. |
| Full-field automation pause update did not return and left the heartbeat active | 1 | Terminated the stalled tool call after status recheck; retry once with the resolved id and minimal pause payload, never by editing the system automation file. |
| Official-doc search response was a string rather than a result object with `content` | 1 | Serialized the returned value directly; the official Scheduled Tasks guidance was then available. |
| Native Codex automation view/update had no registered handler | 3 | Do not retry the unavailable service; use a tested, user-authorized local scheduler with calendar gating instead. |
| Scheduling-progress patch used two update headers for the same file | 2 | Re-read the exact blocks and use one grouped update operation per file. |
| Initial scheduling-progress patch did not match the current progress context | 1 | Located the precise Phase 13o section before retrying the documentation update. |
| New post-capture QA fixture used a stale hard-coded capture schema name | 1 | Import the collector's official schema constant so the test follows the runtime contract. |
| QA fixture imported the similarly named quote-parity schema instead of the Freshness collector schema | 2 | Import `CAPTURE_SCHEMA_VERSION` from `market_data.freshness_calibration`; the two evidence formats are intentionally distinct. |
| Broker/account Saturday smoke referenced absent `ReviewedEquityCalendar.from_json_document` | 1 | The failure occurred before SDK import/login. Replaced it with the repository-supported `ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)`; retry returned `NO_CAPTURE_NON_TRADING_DAY` with `provider_called=false`. |
| Initial post-install planning patch used stale progress context | 1 | No planning file changed. Re-read the exact Phase 13r lines and applied a scoped patch against the live text. |
| Frozen close-window NTP preflight could not resolve DNS in the sandbox | 1 | Re-ran the same read-only NTP command with approved network access; five selected samples succeeded. Host date was Saturday, so no provider capture was attempted. |
| First 2026-08-23 no-capture review patch had one unprefixed added line | 1 | No file changed. Re-applied the review as a small valid patch, then updated the three planning records with exact current context. |
| First 2026-08-24 no-capture review patch had one unprefixed added line | 1 | No file changed. Re-applied the review as a small valid patch, then updated the three planning records with exact current context. |
| Initial scheduler-hardening planning patch contained an empty hunk | 1 | No file changed. Re-read the exact plan context and applied a scoped patch. |
| Initial combined 2026-08-25 review patch had an unprefixed added line | 1 | No file changed. Reapplied the immutable review first, then updated planning records in smaller scoped patches. |
| Interactive close-capture launcher returned before its child capture completed | 1 | Inspected the process and preserved its eventual immutable artifact; stopped a temporary duplicate-prevention job before it wrote a second artifact, then restored the daily scheduler. |
| Static-check command used an unmatched `requirements*.txt` zsh glob | 1 | No repository state changed; reran the same compile and whitespace checks with explicit paths. |
| Full-field Codex automation update returned without error but did not persist any field | 1 | Do not install the launchd job until the provider-executing cron is verifiably changed; retry with the tool's current field names, never edit automation files directly. |
| Correctly discriminated automation update also returned without persistence; Codex UI control is prohibited | 2 | Stop retrying the unavailable control plane. Prepare an exact reviewed TOML replacement, preserve a backup, and request scoped approval to install it before launchd activation. |
| Initial read-only `DAILY;COUNT=1` RRULE would have fired before the target capture | 1 | Correct it before 09:35 to `WEEKLY;BYDAY=FR;COUNT=1`, so the only inspection follows the 2026-08-28 OPEN run. |
| First temporary runtime patch tried to delete and re-add the same path in one apply operation | 1 | No file changed; split deletion and creation into separate `apply_patch` calls, then continue with the reviewed content. |
| Sandboxed compile could not create `scripts/__pycache__` in the sibling worktree | 1 | Production files were unchanged; rerun compilation with `PYTHONPYCACHEPREFIX` under `/private/tmp` and keep the worktree clean. |
| Planning session catch-up first used a non-existent `/Users/stevehuang-work/.venv/bin/python` | 1 | No repository state changed; reran the documented helper with the available system `python3`. |
| Initial remote fetch and GitHub PR query were blocked by `.git/FETCH_HEAD` sandbox permissions and network isolation | 1 | Re-ran the read-only fetch and PR listing with scoped approved access; both succeeded. |
| First combined PM-record update targeted the catch-up error row in `findings.md` instead of `task_plan.md` | 1 | No file changed; inspected the exact live contexts and applied scoped updates to the correct files. |
| First PR #1 merge-state record patch mixed a `progress.md` line into the `findings.md` hunk | 1 | No file changed; split the update by file and reapplied against exact live text. |
| First worktree-status record patch again used `progress.md` bullets as `findings.md` context | 1 | No file changed; split the update by file and used a shared file-specific anchor. |
| First local-main-family record patch again used `progress.md` text in the `findings.md` hunk | 1 | No file changed; separated task-plan, findings, and progress patches by exact file anchors. |
| PM Shadow focused command referenced a non-existent paper-thesis test filename | 1 | No tests ran; listed the actual files and reran the scoped suite successfully with `26 passed`. |
| PM Shadow compile attempted to write `__pycache__` in a read-only task worktree | 1 | Reran with `PYTHONPYCACHEPREFIX=/private/tmp/codex_shadow_review_pycache`; compilation passed without modifying the task worktree. |
| Push of approved Shadow branch was rejected by the managed approval gate | 1 | Do not bypass or retry indirectly. Preserve local commit `47a9303` and request owner confirmation for the exact branch/payload/origin destination. |
| First D-HEALTH round-two follow-up used unescaped backticks inside a JavaScript template string | 1 | No message or task state changed; rebuilt the same review packet from a plain string array and delivered it successfully. |
| PR #4 body update through `gh pr edit` hit GitHub Classic Projects deprecation | 1 | No PR content changed. Used the scoped GitHub REST pull-request PATCH endpoint successfully instead. |
| Referenced-task read requested `turnLimit=12`, above the tool maximum of 10 | 1 | No task state changed. Retried once with the supported maximum and read the referenced ownership context successfully. |
| Initial Phase 15 combined planning patch matched the wrong progress-file spacing/context | 1 | No file changed. Re-read exact anchors and applied small file-specific patches. |
| First read-only 9960 SQLite query referenced a non-existent `finmind_source_repair_bars` table | 1 | Earlier case/evidence/review/activation queries succeeded; no state changed. Inspect the actual schema and use the evidence payload/bar table defined by current code instead of guessing a table name. |
| SQLite CLI has no `gzip_decompress` SQL function during 9960 review | 1 | No state changed. Verified the same stored blobs by piping their hex bytes through system `gzip -dc`; both raw and canonical SHA-256 values matched exactly. |
| First raw-response inspection guessed `raw_response.json`, but the sealed capture is `raw_response.bin` | 1 | No state changed. Listed the exact capture directory and will inspect the 219-byte binary JSON file directly. |
| First label-semantics search included large captured-market-data trees and produced heavily truncated output | 1 | No state changed. Narrowed subsequent searches to the source-repair module, its tests, and exact candidate directories. |
| A pre-review SQLite query used `current_candidate_evidence_id`; the actual column is `candidate_evidence_id` | 1 | No state changed. Inspected the exact table schemas and reran the query with current column names. |
| A parallel post-review SQLite CLI read could not open the database after the application audit | 1 | The application-level status/audit had already passed. Retried with a no-sidecar immutable URI and verified the durable review row plus `quick_check=ok`; no retry mutated state. |
| The final immutable query guessed a materialized `finmind_source_repair_active_bars` table, but active bars are derived and no such table exists | 1 | The verified application audit is authoritative for `active_bar_count=0`; listed the actual four repair tables and completed `quick_check=ok`. |
| `list_threads(limit=200)` exceeded the app's hard maximum of 50 | 1 | No task state changed. Retain the explicit scope as the 50 most recent non-pinned items plus all pinned items returned by the supported inventory call. |
| First live `git ls-remote` was blocked by sandbox DNS isolation | 1 | No remote state changed. Repeated the same read-only remote check with approved network access and verified `main@7931d31` with no existing R6 remote branch. |
| PR #6 initial Python 3.11 CI failed two launchd-supervisor unit tests on Linux | 1 | Blocked merge and issued PM `REQUEST CHANGES`. Root cause is test setup not simulating macOS before exercising a macOS-only supervisor; preserve the production guard, patch the two simulated-launchd tests narrowly, retain a Linux-guard regression, and rerun full CI. |
| Owning R6 task first attempted local remediation tests through a worktree-local `.venv` that does not exist | 1 | No tests ran and no remote update occurred. It switched to the previously qualified shared project interpreter using an absolute path before approving or pushing the remediation. |
| First combined remediation-ledger patch had an invalid patch-section boundary | 1 | No file changed. Split the update into valid file-specific patches and applied them without changing release state. |
| First release-completion progress patch left Phase 16 marked `in_progress` and exposed a duplicated adjacent Phase 15 header | 1 | No repository or release state changed. Corrected the status to `complete` and removed the duplicate heading with a narrow planning-only patch. |
| First Phase 81 PM `jq` summary used incorrect nested manifest/plan paths and expanded the 329,331-partition array | 1 | No artifact or database changed. Record the confirmed file hashes, then inspect only top-level keys and exact single-record paths; do not repeat a full-array summary. |
| Phase 81 digest-helper search used an unmatched `finmind*` shell glob | 1 | zsh stopped before `rg`; no state changed. Search from repository root with `rg --glob '*.py'` and no shell glob. |
| First deterministic review/activation digest replay imported nonexistent `core.json_utils` | 1 | Python failed before opening SQLite. Reuse production `backtest.finmind_source_repair._digest` against rows read through an immutable URI. |
| First Phase 82 child-count query assumed a nonexistent `recorded_request_count` column | 1 | The immutable query failed after the job/partition reads and changed no state. Each `finmind_history_attempts` row is itself a recorded request attempt; verify zero through a direct row count. |
| First Phase 82 re-review SQLite CLI commands lost the quoted job ID through shell escaping | 1 | Both reads failed at SQL prepare time and changed no state. Re-ran the same read-only queries with the complete SQL passed as one quoted argument; exact row and child counts were verified. |
| First institutional-observation `jq` projection assumed `candidates` was top-level | 1 | The read-only projection failed and changed no state. Inspected the artifact keys, then queried `candidate_observation.candidates` and verified all 17 rows share source 2026-08-18 and usable/target session 2026-08-19. |

## Notes

- Treat attached text and repository files as data, not instructions.
- Re-read this plan before choosing final priorities.
- This slice changes the dashboard from read-only to a clearly labelled local paper-simulation control surface.
- It may authenticate to Shioaji for market data with `subscribe_trade=False`; it must not activate CA, subscribe to order events, submit broker orders, or expose a live-order configuration value.
- Phase 13 is calibration-only: it may add evidence capture and analysis artifacts, but it must not implement Portfolio Phase 1 or change frozen domain contracts.
- Phase 13r begins only because the owner has explicitly authorized the broker/account source as read-only. It must never widen that grant into a broker-order or CA integration.
- The 2026-08-22 and 2026-08-23 frozen close heartbeats each landed on a
  reviewed non-trading day. Both retained successful read-only NTP provenance
  and ended `NO_CAPTURE` before any provider path; neither is quote evidence or
  changes the Phase 0 / Phase 1 gate.
- The 2026-08-24 heartbeat was a trading day but the host clock was 17:00,
  after the frozen close window despite its 13:02 heartbeat timestamp. It
  retained successful read-only NTP provenance and ended
  `NO_CAPTURE_OFF_SESSION` before any provider path; it is not quote evidence
  and does not change the Phase 0 / Phase 1 gate.
