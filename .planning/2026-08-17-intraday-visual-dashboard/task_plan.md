# Task Plan: Intraday Visual Dashboard Design

## Goal

Create a reviewable, implementation-ready design for a web dashboard that visualizes the current market scan, Candidate scores, and position exit decisions without changing existing trading logic.

## Current Phase

Phase 17 — Default one-day Kbar view

## Phases

### Phase 1: Requirements & Discovery

- [x] Understand user intent
- [x] Identify constraints and requirements
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Dashboard UX and Information Architecture

- [x] Define the dashboard's primary user questions
- [x] Define page layout, visual hierarchy, and state labels
- [x] Produce an in-conversation dashboard mockup
- **Status:** complete

### Phase 3: Data Contract and Integration Plan

- [x] Define the read-only dashboard snapshot contract
- [x] Map existing Python models to dashboard fields
- [x] State the polling and future streaming boundaries
- **Status:** complete

### Phase 4: Delivery Roadmap

- [x] Sequence the smallest safe implementation slices
- [x] Separate MVP display work from real-time and execution work
- **Status:** complete

### Phase 5: Review Handoff

- [x] Verify the mockup reflects the implemented decision model
- [x] Deliver the design and implementation plan for review
- **Status:** complete

### Phase 6: Snapshot Service and Web Contract

- [x] Extract reusable scan execution from the CLI orchestration
- [x] Build a read-only dashboard snapshot from the existing engines and Store
- [x] Add focused tests that compare dashboard data with decision rules
- **Status:** complete

### Phase 7: Dashboard Page and Server

- [x] Add a local FastAPI server and read-only snapshot endpoint
- [x] Implement the responsive Chinese dashboard page
- [x] Keep provider access and decision calculations on the server
- **Status:** complete

### Phase 8: Verification and Handoff

- [x] Run focused tests; record that the full suite needs the missing pytest dependency
- [x] Run the application and endpoint with MockProvider
- [x] Confirm the existing user-owned Shioaji work remains unchanged
- **Status:** complete

### Phase 9: Historical Kbar Data and Chart

- [x] Confirm which configured providers can return genuine historical Kbars
- [x] Extend the read-only dashboard contract with an optional historical-candle series
- [x] Render a selectable historical candlestick chart and market observations without fabricating history
- [x] Add focused service coverage and verify the MockProvider dashboard path
- **Status:** complete

### Phase 10: 5-Day Kbar Display Diagnosis

- [x] Compare the requested 5-trading-day window with the displayed query range and candle timestamps
- [x] Verify daily aggregation preserves OHLCV order and bar count
- [x] Identify the smallest truthful presentation or data-contract correction
- **Status:** complete

### Phase 11: Three-Month Daily K Chart and Moving Averages

- [x] Fetch selected-symbol history in bounded Kbar requests and retain the required MA warm-up period
- [x] Calculate MA5, MA20, and MA60 from source-backed daily closes
- [x] Add a 3-month daily K view with volume, MA lines, and high/low annotations
- [x] Verify chunk boundaries, indicator windows, API response, and existing dashboard behavior
- **Status:** complete

### Phase 12: Platform Workspace and On-Demand Positions

- [x] Replace the three-column, document-scrolling layout with a persistent Candidate browser and independently scrollable detail workspace
- [x] Reset the detail workspace to its top when a Candidate is selected
- [x] Move positions behind a right-top control and render them in an accessible on-demand side panel
- [x] Preserve existing snapshot, Kbar, score, and position decision data contracts; validate desktop and narrow layouts
- **Status:** complete

### Phase 13: Kbar Hover Detail

- [x] Add a pointer-following detail card to source-backed candlestick charts
- [x] Show the exact displayed candle's date, OHLC, volume, and available moving averages
- [x] Keep tooltip behavior bounded to the chart plot and verify it does not affect the Kbar API or existing selection controls
- **Status:** complete

### Phase 14: Candidate Score Ordering

- [x] Filter zero-score Candidates from the browser list
- [x] Sort visible Candidates by descending total score with a deterministic symbol tie-breaker
- [x] Keep selected detail aligned with the first visible Candidate and verify the existing snapshot contract remains unchanged
- **Status:** complete

### Phase 15: Shioaji Kbar Timestamp Diagnosis

- [x] Trace source timestamp conversion and browser rendering for the reported 17:00 intraday start
- [x] Compare the observed offset with documented Shioaji timestamp semantics
- [x] Report a confirmed cause before changing time-zone conversion code
- **Status:** complete

### Phase 16: Shioaji Kbar Timestamp Correction

- [x] Preserve numeric Shioaji Kbar values as Taiwan market wall time before attaching `Asia/Taipei`
- [x] Replace the conventional-UTC test fixture with a source-representative Kbar timestamp fixture
- [x] Verify the documented 09:01 source example, existing Kbar mapping, and dashboard APIs
- **Status:** complete

### Phase 17: Default One-Day Kbar View

- [x] Set the browser's initial history period to 1 day
- [x] Align the history API default and local documentation with the browser default
- [x] Verify the default selection and existing selectable periods remain intact
- **Status:** complete

## Key Questions

1. Which current outputs require a visual representation instead of another text table?
2. How should the UI distinguish a one-shot market snapshot from future live streaming?
3. What is the smallest web integration that does not duplicate market or trading logic in the browser?

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| A single dashboard is the first screen | The existing program has one scan cycle, one Candidate list, and a small position list; a multi-page product would add navigation without aiding the MVP decision flow. |
| Make data freshness explicit | The current system is a snapshot scan, not a live stream. The UI must not imply live trading readiness. |
| Keep browser access read-only | Candidate selection, scoring, and exit decisions remain Python responsibilities; the browser presents a prepared snapshot. |
| Visualize score breakdown and position risk range | These directly explain the two decisions users need to make: whether to watch a candidate and whether to hold or exit a position. |
| Use FastAPI plus static HTML and vanilla JavaScript for the first web slice | It keeps the first dashboard in the existing Python runtime and avoids adding a Node or SPA build pipeline before the product proves it needs one. |
| Poll the dashboard API, never the provider from the browser | A browser refresh must read a prepared decision snapshot. Provider login, batching, rate limits, and future streaming are server responsibilities. |
| Historical candles must be optional source-backed data | The existing snapshot model cannot truthfully reconstruct past OHLC bars. The dashboard may show a Kbar series only when a Provider returns it, and must expose data gaps otherwise. |
| A period label must describe displayed bars, not only the provider query range | A 5-day chart may query extra calendar days to cover weekends, but visible date labels must use the actual first and last candle timestamps. |
| The long chart uses 65 displayed daily candles plus a 60-day indicator warm-up | This approximates the supplied three-month chart while keeping MA60 mathematically defined at the start of the visible series. The extra source window is fetched only for the selected symbol in <=30-day Kbar requests and cached. |
| Candidate navigation uses a fixed workspace pane, while position monitoring opens on demand | A platform should not make the selected detail dependent on the document's prior scroll position, and positions are a separate task rather than a permanently visible third column. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Initial planning-file patch did not match the generated template | Read the generated files, then replaced them with the design-specific plan. |
| pytest is unavailable in the current Python 3 environment | This affects test execution, not the dashboard design. Record it for implementation verification. |
| Default CLI validation selected Shioaji from the local environment while its SDK is not installed | Use the explicit MockProvider validation path; production Shioaji installation remains an optional dependency. |
| Dashboard snapshot ad-hoc assertion had repeated bracket typos in its diagnostic output | The assertions themselves completed before the malformed display statement; replace the diagnostic with a minimal no-list-comprehension script. |
| Sandbox denied binding the local dashboard port | Retry the local-only HTTP verification with approved port binding and a retained interactive server session. |
| Retained-session orchestration did not expose a serializable session identifier | Use one self-contained verification process that starts the local server, calls its routes, and stops it before return. |
