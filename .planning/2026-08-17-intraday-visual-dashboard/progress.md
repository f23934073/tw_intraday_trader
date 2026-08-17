# Progress Log

## Session: 2026-08-17

### Current Status

- **Phase:** In progress — platform workspace and on-demand positions
- **Started:** 2026-08-17

### Actions Taken

- Inspected the current dashboard-relevant application flow and the project architecture report.
- Checked the worktree before planning; found user-owned modifications in `market_data/models.py`, `market_data/provider.py`, and a new Shioaji provider test.
- Created an isolated planning workspace under `.planning/2026-08-17-intraday-visual-dashboard/`.
- Recorded the dashboard scope: visual decision support only, no change to data collection, scoring, exit rules, or order execution.
- Replaced the generic planning template after the initial context-specific patch failed to match it.
- Created and rendered an interactive dashboard mockup that lets a reviewer select a Candidate and inspect its score breakdown.
- Completed the read-only snapshot contract and implementation sequence. No existing application or trading-logic file was changed.
- User approved implementation. Reopened the plan at Phase 6; the scope remains a local, read-only dashboard with no order path.
- Confirmed FastAPI and Uvicorn are available for local development; no hosting configuration exists. The implementation will use an explicit `重新掃描` action rather than background polling.
- Added shared scan result models, a cached read-only dashboard service, FastAPI endpoints, a responsive Chinese dashboard page, documentation, and focused dashboard tests.
- Initial validation found a local environment setting selecting Shioaji without the optional SDK, plus a typo in the ad-hoc assertion command. Neither is a dashboard code failure; both are recorded before retrying with MockProvider.
- MockProvider CLI output now passes and preserves the prior Candidate scores and `HOLD` decision. The second snapshot diagnostic repeated a display-only bracket typo after its assertions; switch to a simpler diagnostic form.
- The pure dashboard snapshot assertions now pass. Initial local HTTP verification was blocked by sandbox port binding; after approval, the non-interactive server was not retained, so the next verification uses a retained process.
- The retained-session attempt could not preserve a session identifier in this runner. Switch to an isolated start-request-stop verification process rather than leaving a server running.
- Completed temporary MockProvider HTTP checks for the homepage, `GET /api/dashboard/snapshot`, and `POST /api/dashboard/refresh`; every checked route returned valid data.
- Ran the two new dashboard tests directly and the user-owned Shioaji provider tests directly; both sets passed. Confirmed FastAPI 0.117.1 and Uvicorn 0.35.0 satisfy the newly declared runtime ranges.
- User requested historical K charts. Reopened the plan at Phase 9. The implementation boundary is source-backed historical Kbars only; the previous one-snapshot dashboard contract must not invent a time series.
- Inspected the Provider and dashboard service path and verified that it currently exposes only `StockData` snapshots. Consulted Shioaji's official Kbar contract: an on-demand selected-Candidate history route can use genuine OHLCV data and must keep each request within the documented 30-day window.
- A combined implementation patch did not apply because the README wording had diverged from the expected sentence. No source file was changed by that failed patch; inspect the exact README section and split the implementation into smaller targeted patches.
- Added the `KBar` provider model and an explicit optional Kbar contract. `MockProvider` now exposes deterministic simulated chart data for local display; `ShioajiProvider` maps its documented Kbar fields to the shared model and rejects ranges longer than 30 calendar days.
- Added on-demand, per-Candidate history caching and aggregation in `DashboardService`, plus the read-only `/api/dashboard/candidates/{symbol}/history` endpoint. Added service coverage for 5-day history and documented the selectable history view.
- Reworked the central Candidate panel into a source-backed Kbar view with `1日` / `5日` / `20日` controls, price-candle and volume rendering, source/range/resolution labels, explicit empty and unavailable states, and four snapshot-based observation metrics (day position, VWAP deviation, intraday range, relative volume).
- Added focused coverage for 5-minute and daily MockProvider history plus Shioaji Kbar OHLCV/timestamp mapping. Mock history is explicitly labelled in the browser as simulated data.
- Completed final validation: Python compilation, browser-script syntax, focused dashboard/Kbar tests, existing Shioaji snapshot tests, and FastAPI route checks all passed. `git diff --check` passed. A live Shioaji Kbar call was not attempted because this runtime has neither its optional SDK nor configured broker credentials.
- User reported that the 5-day chart looks wrong. From the supplied screenshot, the chart has five candles but the caption shows the wider calendar-date fetch span. Reopened the plan to distinguish the query range from the actual displayed trading-day range before changing code.
- Reproduced the query/aggregation path and confirmed it returns five correct daily bars, from 2026-08-11 through 2026-08-17. Corrected the payload and chart caption to use those displayed dates, fixed the duplicated `5日日 K` label, and aligned X-axis dates with their individual candles.
- Final correction validation passed: Python compilation, browser-script syntax, focused dashboard and Kbar tests, and `git diff --check`.
- User approved the supplied full daily-K reference. Reopened the plan to add a selected-symbol, three-month view with MA5/20/60, volume, and high/low annotations; the history source remains on-demand, bounded, cached, and data-only.
- Re-read the current dashboard service, historical tests, provider contract, static chart renderer, README, and active plan before implementation. Confirmed the current history path makes one provider call and has no indicator payload; the selected change will add only the `3月` on-demand path and preserve the existing 1日／5日／20日 behavior.
- Implemented the `3月` history period: it requests 190 calendar days only for the selected Candidate, divides the provider calls into non-overlapping windows of at most 30 calendar days, and caches the assembled response after de-duplication and daily aggregation.
- Added source-close MA5／MA20／MA60 to the 65 displayed daily candles. The warm-up range means every visible 3-month candle has all three MA values rather than beginning with missing MA60 data.
- Added the `3月` control and price-chart overlays for MA5／20／60, a direct colour legend and latest MA values, plus displayed-period high/low annotations. Existing volume bars and 1日／5日／20日 paths remain intact.
- Updated the local dashboard README and the MockProvider history anchor so the development chart remains continuous across the long-period source windows.
- Final validation passed: Python compilation, all focused dashboard and historical Kbar direct tests, existing Shioaji provider direct tests, browser-script syntax, FastAPI `3月` history route, and `git diff --check`. The first HTTP diagnostic had a shell-quoting-only `NameError` in its final print expression after all assertions had completed; the corrected route check passed.
- User requested a platform-style redesign because long Candidate lists force a manual jump back to the top after selection. Started Phase 12: retain the current data-only contracts, make Candidate browsing and detail inspection independently scrollable, and move positions behind a right-top on-demand control. Interpreting `cicd` as UI/UX from context; no deployment pipeline scope is assumed.
- Replaced the desktop three-column document layout with a viewport-sized two-pane `選股雷達` workspace. Candidate browsing and detail inspection now have separate scroll containers; the selected detail resets to its top while the Candidate list retains its current scroll position.
- Moved the existing position rendering into an initially hidden right-side dialog. The top-right `持倉` button displays the current count and opens it; backdrop click, close button, and Escape all dismiss it. No snapshot field, provider query, score calculation, exit decision, or Kbar path changed.
- Completed focused non-browser validation after the layout change: static JavaScript syntax, Python compilation, existing dashboard snapshot tests, and historical Kbar tests all passed.
- Final workspace validation passed: the homepage serves the new Candidate/detail workspace and hidden position drawer markup; the MockProvider snapshot still contains the current position; the selected-symbol `3月` Kbar route still returns 65 candles; existing Shioaji provider tests and `git diff --check` also passed.
- User requested per-candle detail on pointer hover. Started Phase 13: add a client-side tooltip that reports only the existing source-backed candle values, preserving the current API and all chart controls.
- Added a bounded, pointer-following Kbar tooltip in the existing SVG chart container. It reports date/time, OHLC, and volume for the selected candle; the 3-month chart also reports source-calculated MA5／MA20／MA60. It hides outside the plotted region or when the pointer leaves the chart.
- Final hover validation passed: browser-script syntax, Python compilation, dashboard service tests, historical Kbar tests, and the MockProvider homepage/API check confirming tooltip markup plus the complete source candle fields.
- User requested Candidate prioritization. Started Phase 14: the browser will sort only positive-score Candidates high-to-low without changing backend Candidate membership or scores; detail selection will derive from that same visible collection.
- Implemented Candidate score ordering in the browser. The list filters `total <= 0`, sorts positive total scores descending, uses symbol order only for equal scores, and resolves the selected detail from the same filtered collection.
- Final validation passed: browser script parsing plus a focused `40,20,20,0` sort/filter check, dashboard service tests, MockProvider snapshot/page contract check, and Python compilation.
- User reported Shioaji intraday Kbars beginning at 17:00 instead of the Taiwan market's 09:00. Started Phase 15 as a read-only timestamp diagnosis. Initial official-document search reached the browser connector, but the wrapper-result parser assumed a missing content array and raised a local `TypeError`; retry with raw result inspection rather than treating this as source evidence.
- Confirmed the root cause without modifying application code. Shioaji's documented numeric Kbar example yields 17:01 under the current UTC-to-Taipei conversion but should display 09:01. The source uses a Taipei wall-time interpretation for this numeric field; the browser is correctly rendering the already shifted `+08:00` timestamp. A correction must alter the numeric mapper and the source-representative test together.
- User approved the correction. Started Phase 16: adjust only numeric Shioaji Kbar timestamp mapping and its focused fixture; datetime-valued source handling, dashboard API shape, and all market-data-only boundaries remain unchanged.
- Corrected numeric Shioaji Kbar mapping so it preserves the source's Taiwan market wall time before attaching `Asia/Taipei`. Updated the focused test to use Shioaji's documented 09:01 raw timestamp.
- Final validation passed: Python compilation, historical Kbar tests, direct documented timestamp assertion (`2026-05-18T09:01:00+08:00`), dashboard service tests, and existing Shioaji provider tests. Live broker validation remains unavailable in this runtime because its optional SDK and credentials are not installed.
- User requested that「來源 K 線與成交量」default to 1 日 instead of the current 5 日. Updated the browser state default, the history endpoint fallback, and the local README wording; the 5 日／20 日／3 月 controls remain available.
- Default-period validation passed: static JavaScript syntax, Python compilation, focused dashboard/Kbar tests, direct history-route fallback check, and `git diff --check`.

### Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `python3 app.py` from the preceding project inspection | Mock scan produces Candidate, score, and position output | Passed; design mockup can use this shape | passed |
| `python3 -m pytest tests/ -v` from the preceding project inspection | Unit tests execute | `pytest` is not installed in the active environment | blocked |
| Dashboard mockup render | Fragment wraps as a standalone page without error | Render completed; fragment is 22,976 bytes and contains no network, WebSocket, or escaped-fragment patterns | passed |
| `python3 -m compileall -q app.py dashboard` | New Python modules compile | Passed | passed |
| `python3 app.py` | Default local CLI scan runs | Blocked because the local environment selects Shioaji and the optional SDK is absent | blocked |
| `env PROVIDER=mock python3 app.py` | CLI scan preserves Candidate and Position results | Passed: 3231 scored 40; 2317 position remains `HOLD` | passed |
| Direct `DashboardService(MockProvider())` assertions | Snapshot reflects loaded symbols, score, and exit decision | Passed | passed |
| Local HTTP server in non-interactive command | Serve dashboard page and API | Not retained after the command returned; no endpoint was available to curl | retry |
| Retained local HTTP server session | Preserve a process for curl verification | Runner did not return a usable session identifier | retry |
| Temporary MockProvider homepage and snapshot endpoint | Homepage serves Chinese dashboard and API returns a valid scan | Passed: homepage 200, MockProvider, 4 Candidates | passed |
| Temporary MockProvider refresh endpoint | Explicit refresh scans and returns a valid snapshot | Passed: 4 Candidates and `HOLD` position decision | passed |
| `tests/test_dashboard_service.py` direct calls | Dashboard snapshot and cache behavior hold | Passed | passed |
| `tests/test_shioaji_provider.py` direct calls | Existing user-owned Provider behavior remains valid | Passed | passed |
| Historical Kbar direct tests | Mock intraday/daily history and Shioaji OHLCV mapping work | Passed | passed |
| Dashboard history HTTP route | Valid 20-day Kbar request returns data; invalid period and symbol return 400/404 | Passed | passed |
| Dashboard browser script syntax | Kbar UI JavaScript parses in Node | Passed | passed |
| `git diff --check` | No whitespace errors in tracked changes | Passed | passed |
| 5-day chart correction | Display range derives from first/last returned candles: 2026-08-11 to 2026-08-17 | Passed | passed |
| 3-month Kbar service test | Requests are split to <=30 calendar days; 65 candles include MA5/20/60 warm-up values | Passed | passed |
| 3-month Kbar HTTP route | `GET /api/dashboard/candidates/3231/history?period=3m` returns 65 daily candles and MA fields | Passed: 2026-05-19 to 2026-08-17 | passed |
| Platform workspace page | Homepage contains independent Candidate/detail panes and an initially hidden position drawer | Passed | passed |
| Platform compatibility | Mock snapshot position and selected-symbol 3-month Kbar endpoint retain their existing payloads | Passed | passed |
| Kbar hover detail | Tooltip markup parses; 3-month source candle contains timestamp, OHLCV, and MA5/20/60 fields | Passed | passed |
| Candidate score ordering | 40, 20, 20, 0 renders as C, A, B (descending score, zero hidden, symbol tie-breaker) | Passed | passed |
| Shioaji numeric Kbar timestamp | Documented 1779094860000000000 maps to 2026-05-18T09:01:00+08:00 | Passed | passed |

### Errors

| Error | Resolution |
|-------|------------|
| `python` command is unavailable | Use `python3`; install the `dev` optional dependency before test verification. |
| Initial planning-file patch did not match the generated template | Read the generated file content and used a full replacement patch. |
| Local CLI attempted `ShioajiProvider` without `shioaji` installed | Use `PROVIDER=mock` for local verification or install the broker extra before using the configured Shioaji environment. |
| Ad-hoc snapshot validation command had a mismatched closing bracket | Retry with a multi-line Python script. |
| Multi-line snapshot diagnostic repeated a mismatched list-comprehension bracket | Remove nonessential list printing and retain only service assertions. |
| Sandbox denied the first local port bind; elevated non-interactive server was not retained | Use an approved PTY-backed server session for the endpoint check. |
| Retained server session did not yield a serializable session identifier | Use a self-contained start-request-stop verification command. |
