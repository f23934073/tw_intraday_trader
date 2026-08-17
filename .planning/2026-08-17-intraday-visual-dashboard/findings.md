# Findings & Decisions

## Requirements

- Design a web page that makes the intraday scanner's current outputs easier to understand visually.
- Keep the current Python decision logic intact; this task is a design and implementation plan, not a dashboard implementation.
- Make the visual state honest: the current app performs a one-shot snapshot scan and does not yet stream ticks or submit orders.

## Research Findings

- `app.py` already produces three user-facing result groups: Candidate Pool, score breakdown, and positions with an exit decision.
- `MarketDataStore` is in memory and stores only the latest `StockData` by symbol. It is the natural server-side source for a dashboard snapshot.
- Candidate membership is OR-based across Candidate Rules, and a candidate may have both `AUTO` and `MANUAL` sources.
- Buy scores currently use binary Gap and VWAP rules, so configured maximum score is 40, not the future architecture document's illustrative 100.
- The active worktree contains uncommitted Shioaji improvements: documented credential aliases, TSE plus OTC scans, batched snapshot calls, and snapshot-derived volume, VWAP, and volume-ratio fields. These changes are user-owned and must be preserved.
- FastAPI and Uvicorn are installed in the active Python runtime, but they are not currently declared project dependencies. `pytest` is still absent.
- This repository has no Sites hosting configuration. The dashboard should be implemented as a local Python web surface rather than replacing the project with a standalone hosted site.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Dashboard focus is Watch, Assess, Protect | These map directly to Candidate selection, Buy Score assessment, and Position exit monitoring. |
| Candidate table is the primary navigation | Candidates are the scan's discovery output; selecting one should drive the score and market-detail view. |
| Do not draw a candle chart in the first dashboard | The current model has only one latest snapshot per symbol. A candle chart would fabricate history or require a new data pipeline. |
| Use a score bar and an entry-stop-target range | Both can be calculated truthfully from current fields and rules. |
| Start with a pollable HTTP snapshot endpoint | It matches the one-shot provider/store model; WebSocket is deferred until a reliable event stream exists. |
| Use FastAPI plus static HTML and vanilla JavaScript | The project is currently Python-only. This gives a small read-only dashboard without adding a React or Node build system. |
| Require an explicit page refresh action | The current Shioaji path performs full-market snapshots. Browser polling would trigger uncontrolled provider calls before streaming and rate-limit contracts exist. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| The prior project description no longer matches all Shioaji capabilities | Base the design on the current working-tree code, while treating its uncommitted changes as user-owned. |

## Resources

- `app.py`
- `market_data/models.py`
- `market_data/store.py`
- `market_data/provider.py`
- `candidate/`, `scoring/`, and `position/`
- `architecture/tw_intraday_trader_mvp_architecture_report.md`

## Visual/Browser Findings

- No live browser view exists yet. The mockup will use the current MockProvider values only as a static design state, with its snapshot nature visibly labeled.
- The rendered mockup uses a three-column desktop layout and stacks all sections below 780px. Candidate selection updates the score and latest-snapshot detail locally.

## Dashboard Information Architecture

1. **Header — state before action.** Name, provider, `as of` time, and an explicit `Snapshot only` label. The design must never imply a live feed merely because market numbers are displayed.
2. **Watch — Candidate Pool.** One selectable row per Candidate: symbol, name, source (`AUTO`, `MANUAL`, or both), and total score. This is the dashboard's primary navigation.
3. **Assess — selected Candidate.** Latest snapshot fields, matched Candidate Rules, and an explainable score bar whose maximum is the sum of configured score rules.
4. **Protect — Open Position.** PnL plus a price lane showing stop-loss, entry, latest price, and take-profit. It is independent from Candidate membership.
5. **Footer — Data Health and contract.** Loaded-symbol count, timestamp age, operating mode, and a concise statement that the browser is read-only.

## Proposed Read-Only Snapshot Contract

```text
DashboardSnapshot
  generated_at
  provider: { name, mode: snapshot|streaming, streaming, last_update_at }
  market: { loaded_symbols, expected_symbols, stale_symbols }
  candidates[]
    symbol, name, sources[], matched_rules[]
    stock: { timestamp, price, open, high, low, previous_close, volume, vwap, relative_volume, market }
    score: { total, max, details[] }
  positions[]
    symbol, entry_price, quantity, current_price, pnl_pct, pnl_amount
    exit: { decision, triggered_rules[], stop_price, take_profit_price }
```

`DashboardSnapshot` should be assembled by Python after the scan and read through `GET /api/dashboard/snapshot`. The browser must not calculate score, invoke a provider, or submit an order.

## Delivery Sequence

1. Extract the scan orchestration from `app.py` into a function that returns structured Candidate, score, and position results; retain the current CLI as a renderer of the same result.
2. Add a `dashboard` package containing the snapshot DTO and a read-only service that reads the shared `MarketDataStore` and existing engines.
3. Add FastAPI with `GET /api/dashboard/snapshot` and one responsive static page. Poll the endpoint on a configured UI interval; the server scanner, not the page, owns collection cadence.
4. Verify that CLI and endpoint produce identical Candidate symbols, score breakdowns, PnL, and exit decisions. Add narrow-layout visual QA and missing/stale-data states.
5. Treat streaming, WebSocket fan-out, historical candles, replay, alerts, and every order endpoint as separate later phases.

## Implemented Local Dashboard

- `run_scan()` in `app.py` is now the shared one-shot execution path for both terminal output and the Web service. Candidate scoring, exit-rule evaluation, and PnL are calculated once in Python.
- `DashboardService` caches the latest serialized scan result. `GET /api/dashboard/snapshot` reads the cache; `POST /api/dashboard/refresh` explicitly performs another scan. There is no browser polling and no order route.
- `dashboard/static/index.html` renders a responsive Chinese page with Candidate selection, score details, position stop/entry/current/target markers, data-health text, and a manual `重新掃描` button.
- The local command is `python3 -m dashboard`; the first page load creates a snapshot, and an explicit refresh triggers the next provider call.
- Verified with MockProvider: CLI output, direct dashboard tests, provider tests, homepage, snapshot endpoint, and refresh endpoint passed. The full pytest suite remains unavailable because the active environment lacks pytest.

## Historical Kbar Follow-up

- The user requested historical K charts for the central Candidate detail panel.
- The current dashboard `stock` payload is a single latest `StockData` snapshot. It is sufficient for today's OHLC observation but cannot reconstruct a historical candlestick series.
- The next implementation slice must discover genuine Kbar support in the configured MarketDataProvider path, add an optional history field to the dashboard response, and make missing history visible rather than filling a chart with synthetic bars.
- Shioaji's official historical-market-data documentation exposes `api.kbars(contract, start, end)` with `ts`, `Open`, `High`, `Low`, `Close`, `Volume`, and `Amount`; its date range may not exceed 30 calendar days. Therefore Kbars can remain behind the Provider boundary, while the dashboard limits the longest selection to a 30-day query window.
- Chosen chart contract: the centre panel requests Kbars only for the selected Candidate. `1日` renders intraday bars, while `5日` and `20日` aggregate real intraday bars into daily OHLCV candles. The chart labels its resolution, source, and number of bars, uses volume as a companion panel, and shows an explicit unavailable/empty state.
- Implemented `KBar` as the Provider-owned OHLCV model. `ShioajiProvider` maps source Kbars into this model; `MockProvider` supplies explicitly labelled simulated history only for local development and tests.
- The dashboard exposes a read-only per-Candidate history endpoint, caches each selected symbol/period until the next manual scan, and never adds an order route. Focused service, route, script-syntax, and existing snapshot tests pass; a live Shioaji Kbar request remains untested here because the optional SDK and broker credentials are not installed in this runtime.

## 5-Day Display Investigation

- The user-provided 5-day chart visibly renders five candles but labels the provider query span as `2026-08-08 至 2026-08-17`. The first rendered candle is labelled `8/11`; the presentation therefore mixes a calendar-day fetch window with a five-trading-day view and is misleading even if the returned bars are correct.
- Reproduced the same path with MockProvider: it queries `2026-08-08` through `2026-08-17`, then correctly retains five daily candles dated `2026-08-11`, `2026-08-12`, `2026-08-13`, `2026-08-14`, and `2026-08-17`.
- Corrected the history payload to expose `display_start` and `display_end` from the returned candles. The UI now calls the chart `5日 K`, displays that actual five-trading-day span, and places date labels below their corresponding candles. The wider provider query range remains available in `start` and `end` but is no longer presented as the chart period.

## Three-Month Chart Contract

- The reference chart is a daily OHLCV trend view, not a short intraday chart: approximately three months of daily candles, 5/20/60-day simple moving averages, a volume panel, and visible period high/low markers.
- The chart's question is: "How is the selected stock moving over roughly three months, relative to its short-, medium-, and long-term daily trend and volume?" The selected form remains a candlestick chart with a shared price axis, three direct-labelled MA lines, and a subordinate volume panel.
- Implementation uses a `3月` selector with 65 visible daily bars and a 60-day daily-close warm-up. Because Shioaji limits each Kbar request to 30 calendar days, the service must fetch sequential bounded date windows only when that specific Candidate and period are requested.

## Three-Month Implementation

- `DashboardService` now obtains the long source range as consecutive, non-overlapping windows of at most 30 calendar days, de-duplicates bars by timestamp, aggregates them to daily OHLCV, then caches the selected symbol and period as before.
- The 3-month response fetches 190 calendar days to obtain 65 visible daily bars and enough prior daily closes for MA60. MA5, MA20, and MA60 are calculated server-side from the source-backed daily close series before the visible range is sliced.
- The browser adds a `3月` selector and overlays the three moving-average lines with direct colour labels. The existing volume panel is retained, and the maximum high plus minimum low in the displayed range are annotated on the price panel.
- The MockProvider now uses a fixed history anchor for an instance, so its synthetic chart remains continuous when the dashboard requests multiple source windows. Its browser label still identifies that data as simulated.

## Platform Workspace Redesign

- The supplied desktop screenshot confirms the current grid treats Candidate browsing, detail inspection, and positions as peer columns. When the Candidate list grows taller than the viewport, selecting a row at its lower end leaves the detail above the viewport.
- The revised interaction is a two-pane `選股雷達` workspace: the Candidate list owns its own scroll area, the selected detail owns a separate scroll area, and selection resets that detail area to its top. This keeps lookup and inspection in one task flow.
- Positions remain source-backed from the existing snapshot but become an on-demand task: a right-top `持倉` button shows the current count and opens a keyboard-dismissible side panel containing all positions and their existing exit-decision presentation. No position API or decision rule changes are needed.
- The user wrote `cicd` in a layout request. The implementation assumes this means the platform UI/UX redesign; no CI/CD pipeline or deployment configuration will change unless separately requested.

## Kbar Hover Contract

- The chart payload already provides a displayed candle's timestamp, open, high, low, close, and volume. The `3月` payload additionally provides server-calculated MA5, MA20, and MA60; shorter windows omit those fields rather than inventing indicators in the browser.
- Hovering therefore maps the pointer's X coordinate to the existing displayed-candle index. The floating card must report that exact payload record, including the chart resolution in its date label, and hide outside the price/volume plot area.

## Kbar Hover Implementation

- The chart now uses its fixed SVG viewBox and existing candle spacing to map the pointer's X coordinate to exactly one displayed candle. It only activates inside the combined price and volume plot area and is dismissed when the pointer exits the SVG.
- The tooltip reports date/time, open, high, low, close, and volume for every chart period. It appends MA5, MA20, and MA60 only when the backend supplied them, so the browser does not fabricate unavailable indicators.

## Candidate Score Ordering Contract

- Candidate scores are already calculated by the backend snapshot. This UI-only change filters `score.total <= 0` and orders the remaining items by descending `score.total`; equal scores use the stock symbol as a stable secondary ordering rule.
- Selection must use the same filtered list as rendering. Otherwise a previously selected zero-score Candidate could remain in the detail panel after being removed from the left pane.

## Candidate Score Ordering Implementation

- The dashboard now derives a visible Candidate collection in the browser by filtering positive total scores, sorting high-to-low, then resolving selection, list rendering, and detail rendering from that same collection.
- A focused JavaScript check confirmed `40, 20, 20, 0` is rendered as score order `40, 20, 20` with symbols used only as the stable tie-breaker. The backend snapshot API remains unchanged.

## Shioaji Kbar Timestamp Diagnosis

- The 17:00 intraday start is a confirmed eight-hour server-side offset. The current numeric `ts` mapper creates a UTC datetime, then converts it to Asia/Taipei. The browser correctly displays the resulting `+08:00` ISO timestamp; it is not applying a second incorrect conversion.
- Shioaji's current Kbar documentation shows numeric `ts=1779094860000000000` alongside a displayed 2026-05-18 09:01 Kbar. Running the current mapper on that documented value returns 2026-05-18T17:01:00+08:00. Treating the decoded time as a Taipei wall time instead returns 2026-05-18T09:01:00+08:00, matching the documentation and the expected market session.
- The existing timestamp test uses a conventional UTC nanosecond value for 01:00 UTC and therefore cannot reveal Shioaji's numeric-Kbar wall-time convention. No time-zone code was modified during diagnosis; a future fix should change the numeric Shioaji Kbar mapping and its test together.

## Shioaji Kbar Timestamp Correction

- Numeric Kbar parsing now decodes the source's numeric value as a wall-clock datetime and attaches `Asia/Taipei` without a UTC-to-Taipei conversion. Datetime-valued source handling remains untouched.
- The focused mapping test now uses the documented `1779094860000000000` source value and asserts `2026-05-18T09:01:00+08:00`. Focused Kbar, dashboard service, and existing Shioaji provider tests passed.
