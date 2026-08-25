# Progress Log

## Session: 2026-08-19 — Basic strategy expansion implementation

### Phase 10: Implement basic strategy expansion

- **Status:** in_progress
- Actions taken:
  - Received explicit authorization to implement the approved basic-strategy expansion plan.
  - Activated `planning-with-files` and `karpathy-guidelines`; success criteria are the Phase 10 checklist plus the approved plan Gates.
  - Restored session context and confirmed substantial unrelated worktree changes already exist in historical-download/provider/planning files.
  - Scoped edits to the strategy/backtest/catalog/dashboard surfaces and will preserve unrelated modifications, especially existing README and download/provider work.
- Verification target:
  - Focused new tests pass, full existing suite passes, JavaScript/static/whitespace checks pass, and no Shioaji order or CA path exists in the changes.

## Session: 2026-08-19 — Basic strategy expansion plan

### Phase 9: Basic strategy expansion implementation plan

- **Status:** complete
- Actions taken:
  - Confirmed the request is implementation-plan only; no strategy runtime changes are authorized.
  - Read and activated the `planning-with-files` workflow.
  - Restored the repository's prior planning context and session catch-up output.
  - Reconfirmed the inherited safety boundary: historical research and local paper simulation only; no broker orders or real-money execution.
  - Inventoried the current strategy catalog, executable registry, historical bar contract, deterministic next-bar engine, and focused strategy/backtest tests.
  - Identified the minimum architectural gap: rolling/session/position feature state must be added before the five proposed strategies can be deterministic and reusable.
  - Recorded unrelated existing worktree modifications and limited this task to non-overlapping planning Markdown.
  - Reviewed the existing realtime feature engine and rejected direct reuse for historical Kbars because its input, freshness, and provenance contracts are Tick-specific.
  - Confirmed the existing strategy catalog/API/UI can expose additional fixed-version strategies without a new route or strategy-specific parameter form.
  - Found a blocking capability gap: intraday strategies can currently be selected without a trustworthy per-symbol bar cadence or `required_capabilities` preflight.
  - Scoped the fix to explicit manifest/capability validation plus bounded rolling state; a full streaming backtest rewrite remains outside this plan.
  - Rechecked primary/authoritative sources for ORB, moving-average/trading-range rules, EMA/BBANDS/RSI/ATR definitions, and current TWSE session/cost context.
  - Chose dependency-free Decimal indicator contracts with explicit warm-up semantics rather than adding TA-Lib as a runtime dependency.
  - Authored `architecture/basic_strategy_expansion_implementation_plan.md` with fixed strategy contracts, P0 data gates, engine/context design, phased delivery, migrations, tests, rollout, rollback, and Definition of Done.
  - Kept all five new strategies `EXPERIMENTAL`, preserved legacy default selections, and explicitly excluded broker/real-money execution.
  - Structural validation passed; the first whitespace check found one extra blank line at EOF, which was removed before final verification.
  - Final checks passed: all five strategy IDs and required sections are present, code fences are balanced, and Markdown whitespace checks are clean.
  - Verified this task changed planning Markdown only; no strategy, engine, API, UI, provider, or test implementation was performed.
- Planned output:
  - `architecture/basic_strategy_expansion_implementation_plan.md`
- Files modified so far:
  - `task_plan.md`, `progress.md`, `findings.md` (planning records only)

## Session: 2026-08-18

### Phase 1: Requirements and proposal intake

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - Confirmed the request is review-and-plan only.
  - Read the required planning and code-review skill instructions.
  - Checked memory for relevant project constraints and verified the initial Git state.
  - Created the persistent planning files required for this review.
  - Read the first 520 lines of the attached proposal and inventoried repository files/directories.
  - Identified the first scope conflict: proposed live-money phases versus the inherited research-only boundary.
  - Finished the supplied proposal and read the repository README plus the first portion of the architecture report.
  - Identified that risk admission needs to be mode-independent and that the current system is decision support, not yet an execution system.
- Files created/modified:
  - `task_plan.md` (created)
  - `findings.md` (created)
  - `progress.md` (created)

### Phase 2: Repository architecture trace

- **Status:** complete
- Actions taken:
  - Started tracing current source and test contracts.
  - Inspected current orchestration, latest-snapshot store, provider/config packaging, Candidate/Scoring/Position modules, and dashboard service.
  - Confirmed that current scans are stateless snapshots and positions are manually seeded demonstration data.
  - Read the full market-data provider and data models; recorded timestamp, streaming-contract, client-ownership, and order-normalization gaps relevant to Replay/Simulation.
  - Compared the architecture report's intended Backtest/Shadow/Data Health evolution with the proposed broker-first roadmap.
  - Audited current tests and identified missing deterministic Replay, state-machine, idempotency, persistence, and recovery coverage.
  - Verified Simulation capabilities, callback semantics, odd-lot/emerging-stock exclusions, API limits, subscription cap, and the prohibition on polling snapshot/history APIs as a realtime feed against current official Shioaji documentation.
  - Inspected current settings and packaging boundaries; corrected the SDK constraint evidence to `shioaji>=1.7,<2`.
  - Read the existing dashboard planning record, confirmed its read-only/manual-refresh boundary, and ran the full baseline test suite (`64 passed`).
  - Verified the active Shioaji SDK version (`1.7.2`) and current official pending-submit/order-lot/CA requirements.
  - Completed the optimization review and fixed the target sequence: deterministic data -> decision/risk/journal -> shared Backtest/Replay -> live-data Shadow -> manual Simulation -> automated Simulation.
  - Authored `architecture/execution_layer_v1_implementation_plan.md` with scope, architecture contracts, phased tasks, gates, tests, rollback, file map, and official Shioaji references.
- Files created/modified:
  - None.

### Phases 3-5: Optimization, plan authoring, and verification

- **Status:** complete
- Actions taken:
  - Prioritized proposal changes against current code, tests, prior constraints, and current official Shioaji documentation.
  - Wrote the standalone implementation plan and added exact gates, test strategy, rollback, and file map.
  - Verified the plan includes the current 40-point score ceiling, strict RVOL semantic gap, no-live scope, read-only dashboard boundary, official callback/limit behavior, and no product implementation.
- Files created/modified:
  - `architecture/execution_layer_v1_implementation_plan.md` (created)
  - `task_plan.md`, `findings.md`, `progress.md` (planning records only)

### Phase 6: Web Simulation and Portfolio Plan Extension

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - Restored prior planning context and confirmed the worktree still contains planning artifacts only.
  - Captured the new requirements: manual web simulation orders, purchased-stock information, and a future automated-order path.
  - Chose a shared backend command pipeline so browser and strategy orders cannot bypass safety or audit controls.
  - Inspected the current FastAPI routes, DashboardService, tests, and existing holdings drawer.
  - Confirmed the UI can reuse its current holdings surface, but must replace demo-position data with simulation PortfolioProjection and add a separate order ticket/order-status view.
  - Updated the implementation plan with simulation-only API routes, UI fields, mode/security gates, web acceptance tests, and rollback behavior.
  - Updated automated Simulation so strategy orders reuse the same OrderApplicationService and appear with manual orders in one order/portfolio projection.
  - Verified this turn changed planning Markdown only and did not implement product code.
- Files created/modified:
  - `task_plan.md`, `findings.md`, `progress.md` (updated planning records)
  - `architecture/execution_layer_v1_implementation_plan.md` (pending update)

### Phase 7: Local web paper simulation implementation

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - User authorized implementation after reviewing the plan.
  - Restored the planning context with the installed session catch-up helper.
  - Scoped the first deliverable to an explicitly labelled, session-local paper simulator: no Shioaji authentication, no broker order SDK calls, and no live-money route.
  - Defined verification targets: idempotent manual orders, separately projected orders and holdings, existing regression compatibility, and UI disclosure of local/session-only behaviour.
  - Inspected the current FastAPI/dashboard contracts, package configuration, README, and static dashboard structure. Confirmed that scan positions are hard-coded demo data, so simulation state will be returned in a separate projection without breaking existing scan tests.
  - Verified that the installed FastAPI test client is unavailable because its expected `httpx2` dependency is absent; will use focused service tests without changing dependencies for this feature.
  - Added focused service/API-contract tests. The first API test attempt triggered `ShioajiProvider` from the ambient provider setting and hit a Python 3.13 native-extension segmentation fault; tests now explicitly inject `MockProvider` so they do not initialize external SDK code.
  - Fixed the first focused-test failure: a new sell order was counted as its own pending reservation before availability validation, causing every sell to be rejected. The availability check now excludes the order currently being validated.
  - Implemented the dashboard order drawer, local order blotter, simulation holdings drawer, candidate-to-ticket prefill, and browser-side local projection refreshes.
  - Ran JavaScript syntax validation and dashboard/service tests (`10 passed`). Started the dashboard with `MockProvider` and visually verified the accessible candidate-to-order-ticket flow; no browser test order was submitted.
  - Documentation patch initially used an incorrect project-tree context and was rejected without modifying README; will re-read the exact README sections and apply a scoped replacement.
  - Updated README and the implementation plan with the explicit local-paper semantics and the remaining Shioaji scope.
  - Completed final regression and syntax checks: `71 passed`; dashboard JavaScript syntax check passed; `git diff --check` passed.

### Phase 8: Shioaji Tick/BidAsk simulation quote updates

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - User explicitly authorized replacing manual snapshot refreshes with Shioaji Tick/BidAsk subscriptions.
  - Restored the existing planning context and preserved the uncommitted local-simulation implementation.
  - Scoped the change to market data: local paper orders stay local and no Shioaji order API is authorized.
  - Defined initial verification targets: bounded dynamic subscriptions, callback normalization, ask/bid fills, browser projection updates, stale-state visibility, and full regression compatibility.
  - Inspected the current `StockData`, `SimulationService`, simulation models/tests, provider tests, package bounds, and installed Shioaji package layout.
  - Chose a separate normalized streaming-quote model to avoid expanding the general Candidate/scoring snapshot contract.
  - Verified the installed 1.7.2 type stubs and current official stock-streaming callback/subscribe documentation.
  - Added the internal `RealtimeQuoteUpdate` contract and Shioaji callback/subscription lifecycle.
  - Changed Shioaji login to `subscribe_trade=False`; this stream slice still does not register order callbacks or call order APIs.
  - Added the simulator quote worker, separate Tick/BidAsk ordering, best ask/bid fill logic, bounded-symbol subscription synchronization, stream health projection, and shutdown cleanup.
  - Added a unified local simulation projection endpoint so browser refreshes do not call Shioaji snapshot/account APIs.
  - Updated the browser to poll only the local projection every two seconds while visible, show stream/wait/error state, and display latest trade plus best bid/ask and quote time.
  - First compile and focused compatibility run passed (`10 passed`), confirming the existing MockProvider simulation and snapshot provider contracts remain intact before adding stream-specific tests.
  - Added stream-specific tests for callback normalization, idempotent paired subscriptions, BidAsk fills, Tick marking, per-stream ordering, cancellation unsubscribe, and the unified API projection.
  - Completed a real Shioaji 1.7.2 login/callback/close smoke with `streaming=True` and no stream error.
  - Real 4946 Tick/BidAsk subscriptions were acknowledged, but the 10-second observation window contained no quote event; will retry callback payload verification with a more liquid symbol.
  - Real 2330 provider smoke received both normalized Tick and BidAsk updates.
  - Browser UI showed `Shioaji 即時行情`, one active subscription, and advancing quote time after a local 2330 order; however the marketable order remained pending, reproduced in a standalone service smoke. Investigation remains active.
  - Confirmed the pending test was correct: live best bid/ask was 2380/2385 while the test BUY limit was 2000. A 3000 local-paper limit filled at ask 2385, then Tick marked the position at 2380 with -5,000 unrealized PnL; UI displayed current bid/ask and quote time with no console errors.
  - Browser-driven local test state was discarded when the test server stopped.
  - Added explicit Provider close/logout and confirmed a second real FastAPI shutdown completed without the prior native-thread warning.
  - Re-reviewed the final provider/service/API/frontend paths and preserved unrelated concurrent momentum/signal worktree changes.
  - Final compile, complete regression, JavaScript parse, and whitespace checks passed (`100 passed`).
- Errors encountered:
  - Attempted a non-existent `check-session.sh` helper before reading the installed skill; switched to the documented `session-catchup.py` helper.

### Phase 13: Freshness Calibration Evidence

- **Status:** in_progress
- **Started:** 2026-08-19
- Actions taken:
  - Restored the completed repository planning context and opened a calibration-only phase.
  - Confirmed the user-approved baseline: P0-1 through P0-14 and Fee/Rounding remain frozen; only FreshnessPolicyV1 may change after evidence review.
  - Activated data-quality review for eight independent thresholds and separated quote/executable data from broker/account evidence.
  - Preserved the existing market-data-only boundary: no Portfolio Phase 1, broker order, CA, trade callback, or real-money path is authorized by this task.
  - Located reusable quote evidence seams: normalized `RealtimeQuoteUpdate`, the data-only Shioaji quote capture, digest-validated artifacts, and parity qualification utilities.
  - Identified the initial collection gap: no implemented broker/account read capture path exists in the current market-data-only runtime, so those four thresholds cannot be derived from quote data.
  - Inspected the two existing 20-second parity artifacts: one has no callbacks and the other has clock-skew observations but lacks store, connection, liquidity, and session evidence. Neither can support a threshold.
  - Completed safe-seam tracing: calibration will subscribe Tick/BidAsk only, record an explicit in-memory evidence-store boundary, and retain source clock skew rather than attempting a product-side change.
  - Added an immutable `freshness_calibration_quote_v1` artifact path, offline
    analysis, and a bounded Tick/BidAsk-only CLI. It never imports Portfolio,
    order, or account APIs and its analysis explicitly has no threshold output.
  - Revalidated old captures: `8039` has zero observations; `2330` has 116
    observations with 96 negative source-latency values. The report therefore
    retains `BLOCKING_EVIDENCE` for all eight thresholds.
  - Rendered and validated the technical initial evidence report with the two
    collection gaps as a partial snapshot.
  - Verification passed: 16 focused calibration/parity/artifact tests, CLI
    help, compilation, artifact inspection smoke test, and whitespace check.
- Files created/modified:
  - `task_plan.md` (Phase 13 added)
  - `findings.md` (calibration requirements and initial decisions added)
  - `progress.md` (this entry added)
  - `market_data/freshness_calibration.py` (data-only capture and analysis)
  - `scripts/capture_quote_freshness.py` (bounded capture CLI)
  - `tests/test_freshness_calibration.py` (focused contract tests)
  - `research/freshness_calibration/README.md` (capture and review runbook)

### Phase 13a: Calibration collection preparation

- **Status:** in_progress
- **Started:** 2026-08-19
- Actions taken:
  - User authorized the non-Phase-1 preparation slice only: cohort/session protocol, non-sensitive capture preflight, data-quality checklist, and a read-only broker/account intake checklist.
  - Restored the active plan and reconfirmed the dirty worktree has broad unrelated strategy/dashboard changes; this slice will remain isolated to calibration artifacts and tests.
  - Ran a non-sensitive local preflight: Shioaji SDK and both credential
    categories are present, and the host offset matches `Asia/Taipei`; no secret
    values or network/broker calls were made.
  - Revalidated the current stream cap and data-only login path. Found a
    reusable SDK lifecycle callback seam that must be captured as evidence.
  - Confirmed the lifecycle model has explicit disconnect/reconnect and
    subscription acknowledgement/failure states; capture work will add those
    provenance records before the next live run.
  - Confirmed the tested SDK lifecycle callback codes needed for a conservative
    calibration lifecycle record.
  - Added lifecycle provenance to the data-only quote capture. A configured
    symbol remains `PENDING` until both Tick (`TIC`) and BidAsk (`QUO`) SDK
    acknowledgements arrive; disconnect/reconnect and raw lifecycle inputs are
    persisted for later review.
  - Published reviewer-facing cohort/session manifest, preflight/review
    checklist, and broker/account read-only intake. They establish collection
    readiness only; no liquidity tier, threshold, or broker adapter was added.
  - Verification passed: JSON template validation, 25 focused tests, CLI help,
    compilation, and whitespace check.

### Phase 13b: Live quote discovery capture

- **Status:** in_progress
- Actions taken:
  - At 2026-08-20 09:05 Asia/Taipei, started a 120-second data-only live
    Tick/BidAsk capture for `2330`, labelled `discovery` rather than assigned
    an unsupported liquidity tier.
  - The sandbox blocked the SDK native client before it could create a
    subscription; reran the identical capture in the approved local runtime.
  - Produced `research/captures/freshness_quote/quote_20260820T090534+0800.json`.
    Its initial review has 494 observations (474 BidAsk, 20 Tick), no missing
    stream kind, and no proposed threshold.
  - Source event timestamps exhibit material clock skew (353/474 BidAsk and
    20/20 Tick observations with a negative event-to-callback value), so this
    capture must be retained as raw evidence rather than treated as an SLA.
  - A read-only post-capture NTP sample recorded host-clock provenance
    (`+58.825 ms +/- 53.094 ms`); it neither adjusted the clock nor established
    the provider event-clock offset required to interpret source latency.
  - Wrote the durable review at
    `research/freshness_calibration/reviews/2026-08-20_0905_discovery_review.md`.
    It records lifecycle success, collector-buffer timing, data-quality limits,
    and the unchanged evidence gates without proposing a threshold.
  - Regression and hygiene verification after capture/reporting passed:
    25 focused freshness/capture/stream tests and `git diff --check`.

### Phase 13c: Qualified cohort provenance

- **Status:** in_progress
- Actions taken:
  - Restored planning context after the discovery capture and reconfirmed the
    only remaining work is Freshness Calibration Evidence.
  - User authorized continued intraday evidence work. Began an auditable cohort
    selection path based on official prior completed-session trading value,
    rather than inferred liquidity or callback outcomes.
  - Validated the downloaded 2026-08-19 official TWSE multi-table response and
    derived the fixed 1,086-row completed-session universe. Its p10/p50/p90
    trade-value anchors are `1530`/`6863`/`2886`; manifest creation and paired
    stream acknowledgement will occur before qualifying their first capture.
  - Frozen and JSON-validated
    `cohort_manifest_2026-08-20_twse_2026-08-19.json`; the saved source SHA-256
    matches the inspected official snapshot. Captured the frozen three-symbol
    cohort for ten minutes in the `opening` window after a read-only NTP
    preflight (`+54.431 ms +/- 49.857 ms`).
  - Initial collector review reports 1,048 observations across all six
    required symbol/stream groups. Artifact digest, timestamp range, lifecycle,
    per-row state, and data-quality disposition are the next verification step.
  - Inspection found a calibration-harness state-propagation defect: all six
    groups retain `CONNECTED/PENDING` despite per-symbol paired acknowledgements.
    The 09:16 artifact is immutable raw evidence but excluded from qualified
    threshold review. Will add a multi-symbol lifecycle test, repair only the
    capture instrumentation, then recapture with the same frozen manifest.
  - Repaired lifecycle state propagation and added a multi-symbol regression;
    focused calibration tests now pass (`7 passed`). A 70-second opening
    recapture verified `CONNECTED/ACTIVE` rows after all paired acknowledgements
    (digest `65edf0a…1c110b`). It is partial coverage only: high has Tick/BidAsk,
    mid has BidAsk, and low has no callbacks in that short window.
  - Next: run the unchanged frozen cohort in the `continuous` window and retain
    any sparse low-tier behavior as data quality / coverage evidence.
  - Completed the 15-minute `continuous` capture. Artifact
    `quote_20260820T093046+0800.json` passed digest/schema, paired-ack, complete
    six-group coverage, ACTIVE-state, error, timestamp, and monotonic checks;
    it has 1,513 observations. Published its data-quality review at
    `research/freshness_calibration/reviews/2026-08-20_0930_continuous_review.md`.
  - The review retains all eight thresholds as unset: sparse mid/low Ticks are
    real observed cadence, source clock skew remains unresolved, and broker /
    account capture remains separately unavailable.

### Phase 13d: Close-window scheduling and evidence readiness

- **Status:** in_progress
- Actions taken:
  - Restored the active calibration plan after the continuous capture; its next
    valid quote window is 13:00–13:30 Asia/Taipei.
  - Inspected the app automation capability. The first read used an unsupported
    action field; the tool returned the valid `view/create/update/delete` mode
    contract. Will inspect existing automation state before adding any one-time
    close-window heartbeat.
  - Confirmed no matching existing automation. Created and verified one active,
    one-time thread heartbeat named `Freshness close-window capture` for the
    remaining 13:00–13:30 close window. Its prompt is limited to NTP provenance,
    frozen-cohort Tick/BidAsk collection, artifact review, and planning records;
    it explicitly prohibits broker/account/order/CA/trade-callback APIs and
    Portfolio Phase 1.
- Next:
  - The heartbeat will perform the close-window capture. Continue to preserve
    the independent broker/account evidence blocker until a read-only source
    and environment are explicitly authorized.
  - Wrote `research/freshness_calibration/reviews/2026-08-20_campaign_checkpoint.md`
    after cross-artifact quality checks. It keeps discovery, lifecycle-rejected,
    partial-opening, and qualified-continuous files explicitly segregated and
    records zero duplicate callback keys, out-of-range callback times, or
    callback errors across the current campaign artifacts.
  - Final pre-close verification passed: 26 focused calibration/capture/stream
    tests, manifest JSON validation, and `git diff --check`.
- Next:
  - Acquire and validate the official completed-session source snapshot, freeze
    the derived cohort manifest, and only then run qualified quote captures.
- Next:
  - Verify digest, lifecycle acknowledgement state, and raw schema before
    deciding whether the capture qualifies only as discovery evidence or
    exposes a harness defect.

### Phase 13e: Independent continuous repeat sample

- **Status:** in_progress
- Actions taken:
  - Performed a read-only NTP preflight before the second continuous sample;
    selected host offset was `+47.647 ms +/- 48.080 ms`. This is provenance only
    and did not adjust the system clock or calibrate source event time.
  - The capture control channel returned before its child process completed;
    process inspection found two duplicate retries. Stopped only those later
    duplicate data-only subscriptions and retained the earliest process as the
    sole sample. The retained capture ran 900.514 seconds.
  - Validated `quote_20260820T095444+0800.json`: SHA-256
    `7c937d32d3fc48f46307b880d2feda58e3f1d5449b020f2da1ad12fdd339638c`,
    schema `freshness_calibration_quote_v1`, 1,621 observations, paired
    Tick/BidAsk acknowledgement, six-group coverage, all ACTIVE rows, zero
    callback errors, zero monotonic regressions, zero duplicate composite keys,
    and zero receipts outside the capture interval.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_0954_continuous_repeat_review.md`
    and updated the campaign ledger. The repeated low/mid Tick silence confirms
    only that Tick silence cannot itself signal stale executable data; every
    quote threshold remains unset and all broker/account thresholds remain
    separately blocked.
- Next:
  - Preserve the active 13:00 close-window heartbeat; do not add a second
    heartbeat or change its frozen collection scope.

### Phase 13f: Continued calibration collection

- **Status:** in_progress
- Actions taken:
  - User requested uninterrupted progress. Reconfirmed the sole authorized
    scope is Freshness Calibration Evidence: Tick/BidAsk-only quote artifacts
    may be collected and profiled, while Portfolio Phase 1, account/order/CA /
    trade-callback APIs, and any broker freshness inference remain prohibited.
  - Reapplied the campaign's data-quality method: treat the event grain as one
    callback observation; validate lifecycle state, paired acknowledgements,
    duplicate composite keys, receipt range, timestamp skew, and coverage
    separately from inter-arrival distributions. Preserve each sample as a
    separate artifact rather than pooling it into a threshold claim.
- Next:
  - Start the next non-overlapping continuous sample under the unchanged frozen
    manifest, then inspect it with the same gates. The existing one-time close
    heartbeat remains the only scheduled collection task.

### Phase 13g: Third continuous repeat sample

- **Status:** in_progress
- Actions taken:
  - Ran the unchanged 15-minute Tick/BidAsk-only cohort capture following a
    read-only NTP preflight. The selected host offset was `+33.583 ms +/-
    53.005 ms`; two NTP exchanges timed out but successful samples remained,
    and no system-clock change was made.
  - Validated `quote_20260820T101439+0800.json`: SHA-256
    `181a59b0d9fbd378a70b638f659b0d854a8e5e74b29dd6c2cceeedb321accd6f`,
    1,872 observations, six-group coverage, paired acknowledgement, all
    `CONNECTED/ACTIVE`, zero callback errors, monotonic regressions, duplicate
    composite keys, and out-of-range receipts.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_1014_continuous_third_review.md`
    and updated the campaign ledger. The three same-day continuous samples
    demonstrate material low/mid Tick sparsity while the subscription remains
    active; all thresholds remain unset.
- Next:
  - Continue only through the existing 13:00 close-window heartbeat. Before
    freezing quote thresholds, obtain qualified opening and close coverage,
    multi-day repetition, and source-clock disposition; obtain a separate
    authorized broker/account evidence source for the other four thresholds.

### Phase 13h: Morning continuous data-quality synthesis

- **Status:** in_progress
- Actions taken:
  - Confirmed the active close-window heartbeat remains scheduled for 13:00 and
    is restricted to the frozen cohort and quote-only APIs.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_morning_continuous_data_quality_summary.md`.
    It records event grain, integrity/lifecycle gates, per-sample volume,
    cadence variation, clock limitation, and the separate broker/account gap.
    It neither pools same-day samples into a cutoff nor proposes a threshold.
- Next:
  - Wait for the scheduled close capture and apply the identical quality gate.

### Phase 13i: Pre-close cross-artifact integrity review

- **Status:** in_progress
- Actions taken:
  - Performed a read-only profile of all six immutable quote artifacts. It found
    6,665 total observations, zero duplicate composite callback keys within or
    across artifacts, zero callback receipts outside each artifact range, and
    zero callback errors.
  - Corrected the campaign ledger wording from four to six reviewed artifacts.
    The 09:16 all-PENDING artifact remains explicitly rejected for its known
    instrumentation defect; integrity success does not qualify it as threshold
    evidence.
- Next:
  - Continue only with the scheduled close capture and its separate artifact
    review. P1 remains blocked until the full FreshnessPolicyV1 gate is frozen.

### Phase 13j: Morning evidence reviewer disposition

- **Status:** in_progress
- Actions taken:
  - Recorded the reviewed `PASS` disposition for the morning continuous data:
    collector/lifecycle integrity passed; morning cadence is qualified evidence;
    Tick-only executable-health is rejected; the connection/subscription-plus-
    BidAsk direction is supported without selecting a duration threshold.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_morning_reviewer_disposition.md`
    and linked its detailed status ledger from the campaign checkpoint. No
    collector, cohort, Portfolio contract, risk implementation, or P1 code was
    changed.
- Next:
  - Preserve the scheduled close capture and continue the unchanged measurement
    protocol. P1 remains blocked pending close/multi-session/clock disposition
    plus independently authorized broker/account evidence.

### Phase 13k: Evidence-chain execution order freeze

- **Status:** in_progress
- Actions taken:
  - Recorded the approved execution order: close-window quote evidence,
    cross-session quote evidence, source-clock disposition, then a separately
    authorized broker/account evidence campaign.
  - Added an explicit implementation guardrail: while `FreshnessPolicyV1` is
    not frozen, do not create migrations, Portfolio core, RiskGate freshness
    code, provisional thresholds, or broker/account API calls.
- Next:
  - The active 13:00 heartbeat remains the immediate next action. A qualified
    close artifact will extend evidence only and cannot independently unblock
    Phase 1.

### Phase 13l: Scheduled close-window collection

- **Status:** in_progress
- Actions taken:
  - The one-time close-window heartbeat triggered at 13:00 Asia/Taipei.
    Reconfirmed the evidence-only boundary: unchanged frozen cohort, Tick/
    BidAsk callbacks with `subscribe_trade=False`, no account/order/CA/
    trade-callback API, no execution, and no Portfolio Phase 1.
- Next:
  - Record read-only NTP provenance, run one 15-minute close capture, then
    validate its immutable artifact before assigning any evidence disposition.

### Phase 13m: Close-window artifact review

- **Status:** in_progress
- Actions taken:
  - Performed read-only NTP provenance before the 13:01 close capture. The
    selected offset was `+32.587 ms +/- 53.185 ms`; successful samples and
    timeout attempts are retained without changing the system clock.
  - Validated `quote_20260820T130116+0800.json`: SHA-256
    `1994292cc3c9868952567283f9dc7b02a8ada8dca03a05e7c131872c8e3aed70`,
    2,092 observations, paired acknowledgement, all ACTIVE rows, zero callback
    errors, zero monotonic regressions, zero duplicate composite keys, and zero
    receipts outside range.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_1301_close_review.md`.
    It is partial close evidence: 1530/Tick has no callback and the 13:01–13:16
    capture ends before the 13:30 market/session boundary. It cannot complete
    the close gate or select a threshold.
- Next:
  - On later completed sessions collect complete close-regime evidence that
    covers the documented session transition, then repeat all regimes across
    dates. Keep broker/account evidence separate and await explicit read-only
    authorization. Phase 1 remains blocked.

### Phase 13n: 2026-08-21 cross-session close collection

- **Status:** in_progress
- Actions taken:
  - A close-window heartbeat triggered for a second completed trading date.
    Reconfirmed the frozen cross-session protocol and the no-Portfolio/no-
    broker-accounting boundary before collection.
- Next:
  - Run one 15-minute close Tick/BidAsk capture, validate its artifact against
    the unchanged quality gate, and retain it as separate date/regime evidence.
  - Session catch-up identifies a broad pre-existing dirty worktree that includes
    product and P1-adjacent paths. Preserve it entirely; this heartbeat remains
    limited to the freshness artifacts, reviews, and planning records.
  - NTP preflight recorded five successful read-only samples (selected
    `+54.899 ms +/- 95.187 ms`) before the 13:01 capture. No system-clock change
    was made and source event time remains outside SLA selection.
  - Validated `quote_20260821T130144+0800.json`: SHA-256
    `d00da28a50d2df53fa120c43a1aebf91cfa1baecca91705f590067898977469e`,
    1,497 all-ACTIVE observations, paired acknowledgement, zero callback errors,
    monotonic regressions, duplicate composite keys, and out-of-range receipts.
  - Published
    `research/freshness_calibration/reviews/2026-08-21_1301_close_review.md`
    and `2026-08-21_cross_session_close_checkpoint.md`. The close sample is
    partial (5/6 callback groups, no 1530 Tick) and ends at 13:16 before the
    13:30 session boundary; it adds cross-session qualitative evidence only.
- Next:
  - Do not infer or implement a threshold. Future work needs a complete
    boundary-crossing close protocol, full cross-date regime evidence,
    source-clock disposition, and separately authorized broker/account reads.
    Phase 1 remains blocked.
  - The one-time heartbeat unexpectedly triggered on a second day despite its
    `COUNT=1` rule. Its configuration still reports `ACTIVE`. Two system-tool
    pause attempts (full then minimal payload) stalled without state change and
    were terminated; no automation file was edited directly. Treat any future
    automated capture as requiring explicit user confirmation until the app
    automation service can be updated successfully.

### Phase 13o: recurring trading-session scheduling (2026-08-22)

- **Status:** in_progress
- User authorized scheduling only the quote-evidence collection campaign.
- Confirmed the existing close heartbeat is still active and its 13:00 trigger
  cannot produce the required 13:30-boundary observation. The replacement
  campaign will use the unchanged cohort/schema/quality gates, require an
  explicit open-session check, and schedule opening, continuous, and
  boundary-crossing close observations. It remains Tick/BidAsk-only with
  `subscribe_trade=False`; broker/account collection and all Portfolio work
  remain excluded.
- The native automation service is unavailable (`No handler registered`), after
  two prior pause attempts stalled. Repository inspection found the reviewed
  `ReviewedEquityCalendar` and confirmed that the raw quote CLI does not
  enforce cohort/calendar/window constraints. Next: add a small testable
  runner that validates all of those constraints before loading the quote
  capture path, then install a local scheduler only after verification.

### Phase 13o: runner and launchd definition verified (2026-08-22)

- Added `market_data/freshness_calibration_schedule.py` and the
  `scripts/run_scheduled_quote_freshness.py` CLI. A reviewed-calendar decision
  happens before manifest parsing, NTP, and any live-capture callable. The
  runner permits only the frozen 2886/6863/1530 cohort, requires five
  read-only NTP successes, and leaves a JSON outcome record for every run.
- Added an exact macOS launchd definition with three starts: 09:15 opening,
  10:00 continuous, and 13:15 close (20 minutes to observe the 13:30
  boundary). It delegates to the runner, which remains the calendar gate.
- Verification: `plutil -lint` passed; focused schedule/freshness/calendar
  tests passed (`14 passed in 0.08s`); a 2026-08-22 Saturday CLI smoke wrote
  `NO_CAPTURE_NON_TRADING_DAY` without running NTP or Shioaji; `git diff
  --check` passed.
- Next: copy/bootstrap the verified user-level LaunchAgent and inspect its
  loaded state. This is the only remaining scheduling step; it does not
  authorize broker/account evidence or Portfolio Phase 1.

### Phase 13o: launchd installed and smoke-verified (2026-08-22)

- Installed the verified plist at
  `/Users/stevehuang-work/Library/LaunchAgents/com.stevehuang.tw-intraday-trader.freshness-calibration.plist`
  and bootstrapped it as the current user. `launchctl print` confirms the
  09:15, 10:00, and 13:15 calendar triggers, working directory, Taiwan time
  zone, and one subsequently completed smoke run.
- The manual smoke intentionally ran at 09:47 rather than a scheduled minute.
  It wrote `NO_CAPTURE_OFF_SCHEDULE`, contained no NTP preflight field, and
  did not initialize Shioaji. This validates the installed service follows the
  same fail-closed runner. A separate CLI smoke already proved the scheduled
  Saturday path returns `NO_CAPTURE_NON_TRADING_DAY` without provider work.
- Phase 13o is complete. Future expected behavior is data-only artifacts on
  reviewed trading days; every artifact still requires the existing quality
  review. The Mac must remain logged in and awake around the configured times;
  a late wake fails closed rather than backfilling a different market window.

### Phase 13p: accelerated quote cadence (2026-08-22)

- **Status:** in_progress
- User requested an earlier completion path. The safe in-scope response is to
  increase same-day quote observations only: add one opening and two
  continuous 15-minute windows while preserving the frozen cohort, collector,
  schema, and quality gates. Cross-date evidence, source-clock disposition,
  broker/account evidence, threshold review, and Portfolio Phase 1 remain
  unchanged gates.
- Updated the runner and launchd definition, then verified `plutil -lint`,
  focused evidence tests (`15 passed in 0.05s`), and `git diff --check`.
  Rebootstrapped the same user-level LaunchAgent; `launchctl print` confirms
  all six expected triggers. No quote capture was manually started and no
  broker/account API was called.
- **Status:** complete

### Phase 13q: automated post-capture evidence QA (2026-08-22)

- **Status:** in_progress
- User authorized completing remaining in-scope work. The next slice reuses
  existing immutable artifact inspection to emit per-capture quality summaries
  and fail closed on a structurally invalid artifact. It is evidence tooling
  only: thresholds remain unset, final review stays human-owned, and no
  broker/account or Portfolio path is introduced.
- Inspected the artifact schema and retained close evidence. The QA summary can
  check all required structural dimensions from immutable fields: digest/schema,
  per-symbol TIC/QUO acknowledgement, per-row lifecycle state, six-group
  coverage, callback errors, monotonic regressions, and source-clock skew.
- Initial QA tests exposed a stale hard-coded schema string in the new fixture;
  no live capture ran. The fixture now imports the collector's schema constant
  before verification is retried.
- The first correction used the similarly named quote-parity schema rather than
  the Freshness collector schema. Located the collector-owned constant and
  corrected the fixture import; no artifact or live API call occurred.
- QA verification passed (`17 passed in 0.09s`) and a Saturday scheduler smoke
  again returned `NO_CAPTURE_NON_TRADING_DAY` without NTP or provider work.
  Backfilled structural QA over all eight retained artifacts and published
  `research/freshness_calibration/reviews/2026-08-22_post_capture_qa_backfill.md`.
  Results agree with prior review and retain all thresholds as unset.
- Added an immutable-byte recheck before summary generation and a regression
  test that invalid evidence raises without rewriting the raw file. Final
  verification passed: focused QA/schedule/freshness/calendar tests
  `18 passed in 0.06s`; Saturday smoke remained `NO_CAPTURE_NON_TRADING_DAY`;
  `git diff --check` passed. Phase 13q is complete.

### Phase 13r: broker/account read-only evidence (2026-08-22)

- **Status:** in_progress
- The owner explicitly authorized read-only broker/account freshness evidence
  and confirmed local Shioaji credentials exist. The approved boundary is
  positions, accounting, and account/buying-power-like reads only; it excludes
  submit, cancel, CA, trade callbacks, and action-like order refresh.
- Started a separate evidence-only design rather than changing the existing
  market-data provider or Portfolio surfaces. The artifact will be redacted
  and integrity-checked; all thresholds remain unset.
- An initial code-path audit found no current broker/account freshness adapter.
  It also confirmed that a locally cached order list cannot establish broker
  order freshness without the excluded provider refresh, so that evidence kind
  will be retained as an explicit availability constraint.
- The worktree contains broad unrelated product, dashboard, backtest, strategy,
  and planning changes across 45 files. Phase 13r will create only its new
  calibration module/script/tests/docs and will not reformat or absorb those
  concurrent changes.
- Restored the active Phase 13 evidence context for the one-time frozen close
  heartbeat. The worktree remains broadly dirty and the heartbeat scope is
  quote-only; this execution will neither use nor modify the new broker/account
  collector, and it retains every threshold as unset.
- Frozen close heartbeat disposition: host time was `2026-08-22 13:01 +08:00
  Sat`, so the reviewed calendar requires `NO_CAPTURE`. Completed the required
  five read-only NTP samples (each selected a valid source; +0.405 to +0.407
  ms offset) but did not initialize Shioaji or enter any quote/account/order/CA
  path. Published
  `research/freshness_calibration/reviews/2026-08-22_1301_close_no_capture_review.md`;
  no quote artifact exists and all artifact-quality checks are N/A rather than
  treated as pass.
- Second frozen close heartbeat disposition: host time was `2026-08-23 13:00
  +08:00 Sun`, again a reviewed non-trading day. The required five read-only
  NTP samples all selected valid sources (+0.595 to +0.601 ms offset), but no
  provider path was entered. Published
  `research/freshness_calibration/reviews/2026-08-23_1300_close_no_capture_review.md`;
  the result remains `NO_CAPTURE`, no quote artifact exists, and all thresholds
  stay unset.
- Trading-day frozen close heartbeat disposition: the host clock was
  `2026-08-24 17:00 +08:00 Mon`, after the close session, rather than the
  heartbeat's 13:02 window. Five read-only NTP samples selected valid sources
  (+0.0367 to +0.0373 ms), but the capture ended `NO_CAPTURE_OFF_SESSION`
  before Shioaji import/login or any quote/account/order/CA operation.
  Published
  `research/freshness_calibration/reviews/2026-08-24_1700_close_no_capture_review.md`;
  no quote artifact exists and all thresholds remain unset.
- Inspected the installed Shioaji 1.7.2 method signatures without logging in.
  The synchronous, callback-free read signatures are available for positions,
  profit/loss, and account balance; `update_status` exists but remains
  explicitly out of scope because it refreshes order state. The configured
  `SJ_SIMULATION` runtime value must be captured as an environment label rather
  than guessed from existing quote artifacts.
- Reconfirmed the quote collector's evidence conventions: immutable exclusive
  JSON creation, a SHA-256 inspector, timezone-aware receipt timestamps, and
  explicit limitations. Phase 13r will use the same integrity/redaction shape
  in a separate module rather than extend the quote schema with account data.
- Added the separate broker/account collector, CLI, capture contract, and
  isolated fakes. Focused verification passed: `22 passed in 0.09s` across the
  new capture and existing quote/calendar evidence tests; Python compilation
  and scoped `git diff --check` also passed. No Shioaji login or broker/account
  endpoint was called during this verification.
- Corrected the CA-required classification so a provider rejection is retained
  as `CA_REQUIRED_BUT_PROHIBITED` rather than being overwritten by the separate
  buying-power limitation. Focused tests still pass (`22 passed in 0.08s`).
- First Saturday CLI smoke failed before SDK import/login because it referenced
  a non-existent calendar constructor. No provider call, credentials, or
  account data was involved; the exact failure is logged in `task_plan.md` and
  needs the established calendar-loading path before a different retry.
- Reused the established `ReviewedEquityCalendar.from_path(...)` construction
  and reran the smoke. It returned `NO_CAPTURE_NON_TRADING_DAY` at
  2026-08-22 10:21 +08:00 with `provider_called=false`; focused tests still
  passed (`22 passed in 0.07s`). This proves the collector fails closed before
  importing Shioaji or reading credentials on a closed date.
- Reviewed the existing local quote launchd shape. Phase 13r will use a
  separate user-level job and a calendar/time-gated wrapper, so a late wake or
  manual off-window invocation cannot silently become an unlabelled broker
  evidence sample. The accelerated plan is five short, non-overlapping
  observations per reviewed trading day: 09:35, 10:30, 11:30, 12:30, and 13:20
  Asia/Taipei. Each sample has three endpoint calls and one explicit orders
  gap; it stays far below the documented burst limit because calls are spaced
  through the session.
- Added the separate broker/account scheduler, scheduled runner, five-window
  launchd template, contract/README update, and fail-closed schedule tests.
  Verification passed: `24 passed in 0.09s`, Python compilation, plist syntax,
  and scoped whitespace validation. A Saturday 09:35 scheduled smoke wrote a
  `NO_CAPTURE_NON_TRADING_DAY` run record with `provider_called=false`; it did
  not import Shioaji or read credentials.
- Installed `/Users/stevehuang-work/Library/LaunchAgents/com.stevehuang.tw-intraday-trader.broker-account-freshness.plist`
  as the separate user-level service
  `com.stevehuang.tw-intraday-trader.broker-account-freshness`. `launchctl`
  confirms all five exact calendar triggers, the repository working directory,
  and the bounded runner command. It has `runs=0` and remains inactive until a
  future trigger; installation itself made no Shioaji login, account read,
  callback, CA, order, or cancellation call.
- Rechecked the capture choices against the current primary Shioaji accounting
  and order-status documentation. It confirms that positions/profit-loss reads
  support synchronous no-callback calls and that fresh `Trade` status requires
  the intentionally excluded `update_status`. `account_balance` reports a
  settlement-account balance and a provider query-time field, not a documented
  buying-power authority.

### Phase 13s: Quote-evidence scheduler hardening (2026-08-24)

- Diagnosed the missed 10:00 continuous window: the scheduler accepted only an
  exact minute, so its 10:01 invocation correctly but unhelpfully ended
  `NO_CAPTURE_OFF_SCHEDULE`.
- Added a bounded five-minute late-launch grace to each frozen quote window.
  Every accepted run retains its original session label and immutable duration,
  and records the planned timestamp plus measured launch delay. A later launch
  still makes no NTP or provider call.
- Replaced the relative launchd command with absolute paths; the runner now
  changes to its own repository root. Removed the launchd `WorkingDirectory`
  setting after proving it produced `getcwd` errors in this environment.
- Focused scheduler tests passed (`10 passed in 0.07s`), Python compilation,
  plist syntax validation, and `git diff --check` passed. A non-session
  launchd smoke exited 0 as `NO_CAPTURE_OFF_SCHEDULE` and produced no new
  stderr output. No Shioaji provider, broker/account, order, CA, or Portfolio
  path was entered.
- **Status:** complete

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Initial scope check | `git status --short --branch` | Clean starting tree | `main...origin/main`, no changes | Pass |
| Baseline regression | `.venv/bin/python -m pytest tests/ -q` | Existing tests pass | 64 passed in 0.10s | Pass |
| Local SDK evidence | Read installed package metadata | Determine active Shioaji version | 1.7.2 | Pass |
| Plan scope audit | Git status | Only Markdown planning artifacts changed | Four untracked `.md` files; no application/config/test changes | Pass |
| Local simulation service and API contracts | Focused pytest files | Fill, idempotency, pending/cancel, sell constraints, dashboard projection | 7 passed | Pass |
| Dashboard compatibility | Focused service/API/dashboard pytest files | Existing snapshot behavior remains intact | 10 passed | Pass |
| Full regression | `.venv/bin/python -m pytest tests/ -q` | All existing and new tests pass | 71 passed in 0.22s | Pass |
| Dashboard JavaScript | Node parser | Static script parses | Passed | Pass |
| Local UI interaction | MockProvider dashboard | Candidate action opens prefilled local order ticket | Passed | Pass |
| Stream-focused regression | Fake streaming provider plus fake Shioaji SDK | Normalize callbacks, pair subscriptions, ask/bid fills, Tick marking, ordering, cancellation and close | 5 stream tests plus related simulation/API tests passed | Pass |
| Real Shioaji callback smoke | Shioaji 1.7.2 simulation environment, `subscribe_trade=False` | Receive Tick and BidAsk without any broker order API | Both callback kinds received for 2330 | Pass |
| Real dashboard flow | Local 2330 paper BUY with live Shioaji market data | Pending below ask; fill above ask; position marks from Tick | 2000 remained pending; 3000 filled at 2385; marked 2380 with -5,000 PnL | Pass |
| Graceful shutdown | Initialized Shioaji dashboard then stop FastAPI | Cancel subscriptions and logout without native panic | Clean application shutdown | Pass |
| Final regression | Full current `tests/` suite | All repository tests pass | 100 passed in 0.31s | Pass |
| Final static checks | Python compile, dashboard JavaScript parse, `git diff --check` | No syntax or whitespace errors | Passed | Pass |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-18 | No-match `rg` stopped later chained reads | 1 | Reissued reads independently and captured all required instructions. |
| 2026-08-18 | `check-session.sh` did not exist in the installed planning skill | 1 | Used the documented `session-catchup.py` helper. |
| 2026-08-18 | FastAPI test client expected unavailable `httpx2` | 1 | Used focused direct route-contract tests rather than adding an unrelated dependency. |
| 2026-08-18 | Ambient Shioaji provider initialization segfaulted under Python 3.13 in a test | 1 | Explicitly injected MockProvider in local API tests; did not exercise external SDK code. |
| 2026-08-18 | Initial README patch had an incorrect project-tree context | 1 | Re-read exact sections and applied a scoped patch. |
| 2026-08-18 | Stream PnL test observed `400.0000000000057` instead of exact `400.0` | 1 | Changed the test to `pytest.approx`; no production logic change was needed. |
| 2026-08-18 | Sandboxed Shioaji smoke could not bind an inter-thread fd | 1 | Re-ran the read-only market-data smoke with approved execution; login/callback setup/close succeeded. |
| 2026-08-18 | Live dashboard shutdown emitted a Shioaji native-thread panic after FastAPI stopped | 1 | Added explicit Provider close/logout to the application lifespan and a focused close test. |

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 8 complete |
| Where am I going? | Await user direction; authenticated Shioaji order Simulation remains a separate unimplemented gate |
| What's the goal? | Use Shioaji Tick/BidAsk to update the local paper simulator without enabling broker orders |
| What have I learned? | See `findings.md` |
| What have I done? | Implemented, documented, and live-verified dynamic Tick/BidAsk subscriptions, local bid/ask fills, UI projection updates, and graceful shutdown |

### Phase 10: Basic strategy expansion implementation

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Re-read the approved implementation plan and recorded the current dirty worktree so unrelated download/provider/planning changes remain untouched.
  - Confirmed the pre-change baseline: focused backtest tests `29 passed`; full suite `326 passed, 1 skipped`.
  - Located all dataset-manifest creation paths and confirmed cadence capabilities are currently inferred inconsistently and only emit `OHLCV`.
  - Confirmed the dashboard currently auto-selects the first entry strategy and every exit strategy; this must change before adding experimental strategies.
  - Added cadence evidence/capability derivation, immutable Decimal feature state, five experimental strategy definitions, engine-v2 context, run/worker capability preflight, and safe dashboard defaults.
  - First focused test command referenced test filenames that do not exist in this checkout; no tests ran and no state changed.
  - Corrected registry ordering so existing API consumers still receive the legacy ACTIVE entry first; focused compatibility tests now pass (`28 passed`).
  - Added six cadence/indicator/strategy/engine/preflight contract tests; all six pass.
  - Python compilation passed. Direct `node --check dashboard/static/index.html` is unsupported because Node does not accept `.html`; an extracted-script check remains pending.
  - Full regression passed after the first implementation slice (`332 passed, 1 skipped`); extracted Dashboard inline JavaScript compiled successfully.
  - Added UI safety assertions, legacy v1/v2 parity, old-manifest digest compatibility, and engine-level ATR entry-snapshot propagation coverage; focused expansion tests now pass (`8 passed`).
  - Updated the historical-backtest README section without altering the user's concurrent downloader documentation changes.
  - Removed obsolete whole-day row-count state, added Taiwan-timezone cadence validation, and made feature input digests depend on computed state rather than only the latest bar.
  - Preserved legacy manifest digests by omitting the new optional cadence field when it was absent from the original JSON.
  - Added explicit catalog metadata assertions for all five experimental one-minute strategies.
  - Completed the final end-to-end worker test for an approved v2 ORB/time-stop run.
  - Final verification passed: full suite `337 passed, 1 skipped`; Python compilation, extracted Dashboard JavaScript compilation, and `git diff --check` all passed.
  - Audited the implementation scope: no CA activation, Shioaji trade subscription, broker order callback, or broker `place_order` path was added.
  - Preserved unrelated downloader/provider/night-session worktree changes and did not create a commit.

### Phase 11: Previous-day premarket watchlist implementation plan

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Restored the completed strategy-expansion context and confirmed the current dirty worktree before planning.
  - Scoped the plan to prior-session historical data only; no pre-open indicative feed, broker API, or product implementation is authorized.
  - Identified three candidate plan contracts from the discussion: previous-day momentum/liquidity, NR7 contraction, and previous-day RSI/Bollinger oversold.
  - Traced the current Candidate snapshot engine, dashboard snapshot/history service, strategy catalog premarket draft, and existing CandidatePool discovery seams.
  - Confirmed the existing Candidate model lacks the historical identity/evidence needed for a reproducible premarket watchlist artifact.
  - Inspected CandidateDiscovery/CandidatePool and selected that discovery contract as the downstream integration seam, with a separate immutable watchlist artifact as source of truth.
  - Confirmed strategy catalog PRE_MARKET/CANDIDATE metadata can represent the new family without mutating `premarket_gap_watchlist_v1`.
  - Detected an apparent checkout inconsistency: premarket tests exist, while the referenced `premarket/` package is not present at the expected filesystem path; investigation remains plan-only.
  - Confirmed no usable TAIFEX premarket package exists in this checkout, so the stock watchlist plan will not depend on it.
  - Identified required foundations absent from the current scheduler/dataset path: exchange trading calendar, complete daily-bar capability, bounded recent-session reads, and explicit operational-versus-research universe semantics.
  - Audited runtime composition, immutable artifact patterns, instrument references, backtest jobs, and the main Dashboard scan path.
  - Noted concurrent untracked TAIFEX premarket files appearing during this planning task; preserved them and excluded them as a hard dependency.
  - Split the intended design into two outputs: a durable evidence-rich watchlist artifact and a lightweight CandidateDiscovery adapter for CandidatePool admission.
  - Rejected extending legacy float/current-snapshot CandidateRule for the new strategies; selected a separate Decimal daily-feature engine with version-owned contracts.
  - Mapped the minimal UI/API/persistence seams and the required offline test layers.
  - Authored `architecture/previous_day_premarket_watchlist_implementation_plan.md` with exact Momentum, NR7, and RSI/Bollinger formulas, deterministic ranks, time/data contracts, persistence, API/UI, scheduler, test, rollout, rollback, and Definition of Done.
  - Sequenced the first implementation slice through Momentum artifact generation before CandidatePool/UI integration or the remaining two strategies.
  - Verified all required strategy IDs and safety contracts are present; planning Markdown has no trailing whitespace and the tracked planning diffs pass `git diff --check`.
  - Confirmed no product implementation was performed by this phase. Concurrent product, TAIFEX, and separate planning changes remain present and untouched in the dirty worktree.
- Planned output:
  - `architecture/previous_day_premarket_watchlist_implementation_plan.md`

### Phase 12: Rewrite previous-day watchlist Phase 0-3

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Received the strategy/data-contract review and explicit authorization to rewrite Phase 0-3 of the existing implementation plan.
  - Re-activated `planning-with-files`, restored unsynced context, and re-read the root planning records.
  - Confirmed this remains a plan-only task; concurrent product, market-data qualification, TAIFEX, dashboard, and other planning changes will remain untouched.
  - Recorded corporate-action normalization, price-limit/one-price classification, Momentum evidence variants, direction-neutral NR7 semantics, Oversold confirmation, and net-of-cost validation as required plan changes.
  - Rewrote Phase 0 as a P0 contract/Formal Gate freeze, Phase 1 as point-in-time reference-data foundations, Phase 2 as corporate-action-aware raw/adjusted derivation, and Phase 3 as the Momentum-only artifact vertical slice.
  - Added four Momentum OOS memberships, market-state rank cohorts, one-price handling, normalized NR7 naming/semantics, confirmation-only Oversold, and gross-to-net cost attribution.
  - Separated immutable raw daily bars from `adjustment_as_of=P` views so future corporate actions cannot rewrite historical candidate artifacts.
  - Reconciled strategy catalog IDs, artifact schema, persistence tables, application workflow, Phase 5/6 semantics, tests, Definition of Done, and the first-reviewable-slice summary with the rewritten Phase 0-3.
  - Final structural checks passed: Phase 0-6 headings remain ordered, 36 code-fence delimiters are balanced, required strategy/gate identifiers are present, no trailing whitespace was found, and tracked planning diffs pass `git diff --check`.
  - Confirmed this task edited only the implementation plan and root planning Markdown; no product code, runtime configuration, migrations, tests, or concurrent worktree files were changed.
  - The first completion patch used an outdated Phase 12 label and failed without changing files; re-read the live block and applied the corrected scoped patch.
- Planned output:
  - Revised `architecture/previous_day_premarket_watchlist_implementation_plan.md` with rewritten Phase 0-3 and consistent cross-references.
