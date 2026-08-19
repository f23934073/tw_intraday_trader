# Progress Log

## Session: 2026-08-19

### Current Status
- **Phase:** 2 - Realtime projection contract
- **Started:** 2026-08-19

### Actions Taken
- Activated an isolated planning record to avoid overwriting concurrent planning work.
- Captured the user-facing contract: realtime evaluation for all candidates with score, qualifying strategies, values, and data freshness.
- Confirmed the existing visible result is a Replay fixture, so the implementation must replace rather than relabel it.
- Traced the existing realtime Shadow runtime, signal/evidence data model, browser polling, and quote-provider boundary.
- Confirmed the exact reuse path: the Shadow runtime supplies full intraday evidence, while the existing local-paper quote stream is intentionally insufficient for Momentum scoring.
- Frozen the implementation contract: scan candidates refresh at a bounded 30-second cadence, then every subscribed candidate score updates from Tick/BidAsk events and is delivered to the browser's existing two-second polling loop. Capacity or warm-up rows stay visible with an unavailable reason.
- Added the server-side live projection wrapper, Shadow alert acknowledgement, endpoint lifecycle ownership, and initial all-candidate table rendering.
- Added a scan-only candidate loader so 30-second candidate refreshes do not invoke premarket artifacts.
- Completed the focused regression, Python compilation, inline JavaScript parsing, whitespace validation, and local browser smoke. With blank credentials the browser showed the explicit live-data-unavailable state and did not fall back to Replay.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Focused realtime projection, API, UI, Shadow, and dashboard tests | Live candidates expose scores, qualifying values, unavailable reasons, acknowledgement, source-safe candidate scan | 29 passed | Pass |
| Python and browser static checks | Updated modules and inline dashboard script parse; no whitespace errors | Passed | Pass |
| Local browser smoke, MockProvider + blank Shioaji credentials | Momentum explicitly shows unavailable; never displays fixture data | `/api/dashboard/momentum` returned 200 and UI showed `即時資料不可用` / `即時盤中動能未啟動`; no console errors | Pass |
| Full suite | No unrelated regressions | 371 passed, 1 skipped, 2 failed in pre-existing daily SMA and premarket artifact paths | Blocked outside task scope |

### Errors
| Error | Resolution |
|-------|------------|
| The old Momentum API test let the ambient provider initialize Shioaji and Python 3.13 segfaulted in its native extension. | Replace the test's implicit global construction with deterministic injected realtime service coverage; do not retry that unsafe path. |
| The initial realtime fake omitted an actual runtime snapshot field and one UI assertion referenced the superseded one-item renderer. | Updated the fake snapshot and assertion to the live candidate-table contract. |
| The capacity-row test exposed a lowercase enum value that bypassed the user-facing availability labels. | Normalize the serialized miss reason to the stable uppercase presentation key. |
| Full suite: a daily SMA test expected one trade but saw zero, and a premarket artifact test hit existing-content integrity mismatch. | These failures are outside the changed files; keep them unmodified and validate this feature with its focused suite. |
