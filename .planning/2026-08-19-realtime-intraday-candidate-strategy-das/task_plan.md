# Task Plan: Realtime intraday candidate strategy dashboard

## Goal
Continuously evaluate the current candidate pool from live Tick/BidAsk data and show every candidate's intraday score, matched strategies, input values, and data freshness in the existing dashboard.

## Current Phase
Phase 2

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture the required live candidate/strategy visibility and preserve the no-broker-order boundary.
- [x] Trace the existing candidate pool, Momentum replay projection, live Shadow runtime, streaming subscription limits, APIs, and UI seams.
- [x] Record source/freshness and failure-mode contracts in findings.md.
- **Status:** complete

### Phase 2: Realtime projection contract
- [x] Define one server-side projection for all current candidates, including score breakdown, passed rules, evaluated values, source, and freshness.
- [x] Reuse the existing live stream/runtime rather than polling snapshots or retaining the Replay fixture as live data.
- [x] Add fail-closed handling for unavailable/stale stream data and candidate changes.
- **Status:** complete
- **Status:** pending

### Phase 3: Implementation
- [x] Implement the realtime candidate projection and subscription lifecycle.
- [x] Replace the Momentum Replay-only API/UI with the live candidate table and meaningful empty/degraded states.
- [x] Add focused backend, API, and browser-contract tests.
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Run focused deterministic stream/projection/dashboard tests with a fake streaming provider.
- [x] Run relevant regressions, Python/JavaScript checks, and inspect the browser flow if the local runtime can start safely.
- [x] Document exact coverage and any unavailable live-credential validation.
- **Status:** complete

### Phase 5: Delivery
- [x] Recheck the changed-file scope against the user request and preserve unrelated worktree changes.
- [x] Deliver the implemented behavior, validation results, and explicit data-source caveats.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep calculation and provider access server-side | Browser must only render an auditable projection, not invent scores or read broker data directly. |
| Use Tick/BidAsk streaming, not snapshot polling | The user requires intraday updates; the existing Replay fixture is immutable and cannot satisfy that requirement. |
| Keep the change market-data-only | The request expands monitoring and signals, not broker order authority. |
| Refresh the snapshot candidate pool every 30 seconds; refresh scores from ticks | Candidate selection still derives from the existing snapshot scanner, while scores must use the Tick/BidAsk event stream. The two timestamps are exposed separately. |
| Render every current candidate, including explicit unavailable rows | The quote subscription maximum is 100 symbols; capacity and warm-up must not be silently mistaken for zero scores. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Focused Momentum API tests initialized the ambient Shioaji native provider and segfaulted under Python 3.13. | Inject a deterministic live-runtime service into API tests; do not rerun the ambient-provider path. |
| New realtime dashboard test fake lacked the runtime mode field; the UI assertion still named the former one-item expression. | Complete the fake runtime contract and assert the new table's signal expression. |
| Capacity miss reasons are lowercase enum values but the presentation map uses stable uppercase keys. | Normalize the enum value before serializing the availability label. |
| Full regression has unrelated failures in daily SMA expectations and a premarket artifact integrity collision. | Preserve those worktree areas; use a scan-only candidate loader so the new 30-second job does not invoke premarket artifact creation. |
