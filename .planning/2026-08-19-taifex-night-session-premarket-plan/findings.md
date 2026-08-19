# Findings & Decisions

## Requirements
- Add TAIFEX futures detection to the premarket portion because the prior evening's night session can affect today's Taiwan cash-equity context.
- Produce a concrete plan and report for review.
- Do not implement product code in this turn.
- Preserve the repository's current no-real-money/order boundary and unrelated dirty worktree changes.

## Research Findings
- Current branch is `main`, tracking `origin/main`.
- The worktree already contains unrelated changes to historical Kbar download/provider code, tests, README, and an existing planning directory; these must remain untouched.
- Prior repository work established a FastAPI/Vanilla-JS dashboard, server-side provider/decision logic, local paper simulation, and Shioaji stock Tick/BidAsk streaming with `subscribe_trade=False`.
- Existing memory is contextual only; current code and current official contracts must be revalidated before the report is finalized.
- The repository has no implemented TAIFEX/futures/night-session adapter or normalized futures context model; the only futures-related references are generic future-data guards and prose.
- `strategy_catalog/service.py` already declares `premarket_gap_watchlist_v1` (`PRE_MARKET`, cutoff `08:50`) but this is a catalog definition, not proof of a running premarket detector.
- Current production paths of interest are `app.py`, `market_data/provider.py`, `market_data/events.py`, `dashboard/service.py`, `dashboard/server.py`, `dashboard/static/index.html`, `config/settings.py`, `strategy_catalog/service.py`, plus market-data health/replay and tests.
- Existing stock gap logic computes cash-session open versus previous cash close. TAIFEX overnight context must remain a separate feature; replacing the stock gap formula would change its meaning.
- The repository already has normalized event envelopes, data-health state, replay primitives, and as-of/future-data guards that can be reused instead of adding a parallel ungoverned path.
- `app.run_scan()` is still a one-shot stock-market scan: it fetches all stock snapshots, applies `GapUpRule`/`HighVolumeRule`, scores candidates, and returns a `ScanResult`; it has no premarket context dependency today.
- `premarket_gap_watchlist_v1` is explicitly `DRAFT`, requires `PREOPEN_INDICATIVE` plus `OHLCV`, and points to `candidate.premarket_gap_up`, but the binding is metadata-only and no implementation was found.
- The normalized streaming layer currently supports stock `TICK` and `BIDASK` payloads whose `event_time.date()` must equal `session_date`. That invariant cannot be reused unchanged for a TAIFEX night session, because trading-date attribution spans the prior calendar evening and the next-day session.
- `DataHealth` already has `STARTING/HEALTHY/DEGRADED/BLOCKED`, staleness, disconnect, ordering, session mismatch, queue, and verified-recovery concepts. A futures detector should project into this safety model or a compatible market-context health projection.
- The current Shioaji provider is stock-oriented. Futures contracts and futures quote streams should be added behind a separate adapter/port or an explicitly generalized provider, not smuggled into stock DTOs.
- `DashboardService.refresh()` directly serializes `run_scan(provider)`; `ScanResult` and `build_dashboard_snapshot()` have no market-context section. The clean UI/API seam is a new server-side `premarket_context` projection, not browser-side futures math.
- `RuntimeComposition` currently owns one stock provider, dashboard service, and local simulation service. Futures acquisition should have its own lifecycle dependency so stock provider shutdown/subscription behavior remains stable.
- `MarketDataProvider` exposes stock snapshots/Kbars and stock Tick/BidAsk streaming. Its Shioaji implementation resolves `Contracts.Stocks` and uses stock-specific callbacks; adding TX futures here would otherwise mix instrument types and subscription budgets.
- Replay infrastructure can currently load only stock `TickEvent`/`BidAskEvent`. A normalized `FuturesSessionSnapshot` artifact may be the smaller first slice; event-level futures replay can follow only if intranight streaming is required.
- The existing dashboard keeps provider operations and calculations server-side, so the TAIFEX overnight delta, basis, and health labels should be serialized by backend code and only rendered in the browser.
- TAIFEX currently lists TX general trading as 08:45-13:45 and after-hours as 15:00-next day 05:00; the expiring contract has no after-hours session on its last trading day.
- TAIFEX explicitly assigns after-hours trading to the next general session. The detector's `trading_date` must therefore be the next valid general-session date, not the event's calendar date.
- TAIFEX documents its exchange opening-reference rule, but the current report has not proven that Shioaji `FuturesInfo.reference` is the same value. The context must call it `provider_reference_price` and keep any TAIFEX settlement value in reconciliation evidence until parity is proven.
- Shioaji exposes futures contracts, including continuous front month `TXFR1`, with `target_code` resolving to a dated contract; contract info includes delivery and last-trading dates. This is valid as-of query-time evidence only and cannot identify a past contract during historical backfill.
- Shioaji documents futures `TickFOPv1` and `BidAskFOPv1` subscriptions with event datetime, close/open/high/low, volume, underlying price, and book fields. This makes a market-data-only streaming detector feasible without enabling trade callbacks or order APIs.
- Shioaji historical Kbars accept futures contracts such as `TXFR1`, so an MVP may query the completed overnight session at/after 05:00 and build a deterministic premarket snapshot; however source date/session semantics still require a live SDK fixture before implementation.
- Shioaji `FuturesInfo` exposes `reference`, limits, `update_date`, delivery/last-trading dates, and continuous alias `target_code`, supporting both baseline validation and rollover metadata.
- Continuous `R1` automatically rolls on delivery date and expired dated contracts may no longer resolve. Live context artifacts pin the as-of resolved code; historical backfill must use dated-contract mapping or explicitly mark identity unresolved and must never stamp past data with today's `TXFR1.target_code`.
- README confirms the existing premarket strategy remains `DRAFT` because pre-open indicative data is not yet available. TAIFEX context can be delivered independently first; it does not make the stock pre-open indicative strategy fully implemented.
- The repository uses typed, versioned, fail-closed hypothesis configuration (`config/momentum.py`) and a central `RuntimeComposition`; the new context should follow the same pattern but omit unapproved direction/FLAT thresholds entirely.
- `StockData` is intentionally only a per-stock market snapshot. TAIFEX fields should not be added to it.
- The current generic `Clock.session_date()` returns the calendar date. The TAIFEX resolver must be a separate exchange-calendar service instead of redefining the global clock contract.
- Dashboard data is cached until explicit refresh, and the same `/api/dashboard/snapshot`/`refresh` payload already feeds the overview. The smallest UI change is a new `premarket_context` block in that payload plus one market-context card/panel; no new browser-side data source is required.
- The overview currently shows four summary cards and a data-health note. A dedicated Traditional Chinese card such as `台指期夜盤` should show signed metrics, close/provider reference, source time, completeness, context health, and reconciliation status without displacing candidate/order/position counters.
- API composition appends simulation projection outside `DashboardService`. The TAIFEX snapshot belongs in `DashboardService`/`ScanResult` context because it is read-only market evidence, not simulation state.
- Tests already assert server-side decision reuse and static UI contracts. New tests should assert exact context serialization, missing/degraded states, and that JavaScript renders rather than computes futures metrics.
- The current provider already centralizes Shioaji login/logout and stock callback lifecycle. For the narrow MVP, adding optional TAIFEX context capability to this provider reuses the single authenticated session; a new independent provider login would add avoidable lifecycle/quota risk.
- Current provider tests use SDK-free fake APIs and `object.__new__` to validate mappings. Futures contract selection, Kbar/session filtering, and unavailable states can follow that pattern without credentials in default CI.
- Existing architecture reports emphasize provider isolation, server-side decisions, simple first slices, explicit data health, and no strategy/provider SDK coupling. The proposed context capability fits these constraints if it remains a separate DTO and does not alter `StockData` or score engines.
- TAIFEX publishes an official annual market calendar, but the page is not itself a machine-stable trading-calendar API. The implementation should vendor/version a validated calendar artifact (with source URL and checksum) or introduce another authoritative calendar adapter; weekday-only logic is insufficient.
- Shioaji's historical tick request uses a `trading date` parameter, which aligns with TAIFEX assignment and may be a clearer way to obtain the final overnight tick than inferring session membership from Kbar calendar dates. Phase 0 must compare `ticks(date=trading_date)` and `kbars` against a real night-session fixture before choosing the query.
- TAIFEX daily reports state after-hours data are displayed by their attributed trading date and are generally produced around 07:00, making them suitable as a delayed reconciliation source, not the primary 05:00-08:50 premarket feed.
- A Monday trading date does not imply a Sunday-night session. TAIFEX's own daily-report example pairs a Friday general session with the next trading date's after-hours label; the resolver must derive the actual previous after-hours window from the exchange calendar (often Friday 15:00-Saturday 05:00 for Monday), not `trading_date - 1 day`.
- The official 2026 TAIFEX calendar is a two-page PDF and explicitly marks non-trading days and expiry dates. It can seed a versioned calendar fixture, but the report notes that actual contract rules remain authoritative.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Create an isolated planning session | Avoid overwriting the active historical-Kbar recovery plan or root legacy planning files. |
| Use exact current code paths and primary-source exchange/SDK documentation | Session boundaries and data-field semantics are correctness-critical and may change. |
| Model TAIFEX context as a separate market-level input | It describes index-futures sentiment and is not a per-stock opening price or guaranteed cash-market direction. |
| Introduce a TAIFEX trading-date/session resolver | Calendar-date equality is wrong for events received after 15:00 and before midnight that belong to the next trading day's night session. |
| Prefer a separate `FuturesMarketDataProvider` port | It isolates `Contracts.Futures`, futures callbacks, contract rollover, and lifecycle from stock snapshot/streaming behavior. |
| Add market context beside candidate scoring before using it as a gate | This preserves current stock ranking semantics and lets evidence quality be measured before changing decisions. |
| MVP queries a candidate completed-session snapshot after the query cutoff | Time eligibility permits a query but does not prove the source is complete or READY. |
| Resolve contract identity according to data time | Live/as-of may persist query-time target; historical backfill needs dated-contract/roll evidence and otherwise remains unresolved. |
| Keep Shioaji reference and TAIFEX settlement as separate typed evidence | Equality has not been proven; any parity result belongs in a separate reconciliation artifact. |
| Keep `premarket_gap_watchlist_v1` in DRAFT after this slice | Futures context alone does not supply the strategy's declared `PREOPEN_INDICATIVE` stock input. |
| Add typed `PremarketContextConfig` with an observation-only default | The repository already uses versioned fail-closed hypothesis settings; unvalidated thresholds must not affect candidates or orders. |
| Include context in the existing dashboard snapshot/refresh contract | It preserves explicit refresh and cache semantics and avoids a second client fetch/race for the same premarket view. |
| Extend the existing provider with an optional, narrow premarket-context capability in MVP | It reuses the current Shioaji session and mirrors optional Kbar/streaming capabilities; extract a dedicated adapter only when broader futures use justifies it. |
| Validate historical ticks versus Kbars before freezing acquisition | Official docs expose both, but only a live fixture can prove exact night-session date boundaries and final-close behavior in this SDK/runtime. |
| Treat exchange daily data as post-session reconciliation | Publication timing is later than the night close, so it cannot be the only premarket dependency. |
| Resolve an explicit session window from the exchange calendar | Weekend and holiday transitions invalidate naive previous-calendar-day logic. |
| Use a two-stage context, but gate stage two separately | A post-session query candidate answers the immediate request once completeness is proven; 08:45-08:50 futures confirmation adds streaming lifecycle and needs separate evidence. |
| Keep only raw signed metrics in v0 | Do not introduce `FLAT`, neutral bands, direction labels, or regime fields before calibration. |
| Version READY completeness evidence in Phase 0 | Query timing and a non-empty response are necessary operational facts but are not proof of finalized session data. |
| Join artifacts only in projection | Keeps acquisition evidence immutable while allowing late TAIFEX reconciliation to appear in the dashboard. |

## Review Corrections
- `provider_reference_price` is Shioaji-sourced evidence; it is not labelled as TAIFEX settlement.
- `ContextArtifact` is immutable acquisition/normalization output. `ReconciliationArtifact` is a separate later artifact that references the context digest and records external comparison results. Dashboard projection may join them without mutating either artifact.
- Historical backfill contract identity is resolved as of the historical trading date from a dated-contract/roll mapping. If that proof is absent, identity remains `UNRESOLVED`; current `TXFR1.target_code` is forbidden.
- `05:05` is `query_not_before`, not a readiness threshold. READY requires successful acquisition plus explicit session-completeness, timestamp-window, contract-identity, and required-field evidence frozen by Phase 0 qualification.
- V0 exposes signed points and percentage metrics only. It has no `FLAT` threshold or categorical direction/regime output.
- The revised report replaces ambiguous `overnight_return_pct` with `session_move_pct`, `session_range_pct`, and source-qualified `provider_reference_change_pct`; `settlement_change_pct` exists only after qualified TAIFEX reconciliation evidence is present.
- Context readiness and reconciliation status are orthogonal: a Context Artifact can be READY while reconciliation is PENDING, and reconciliation mismatch cannot mutate context health.
- Historical continuous-series observations may be retained with `resolved_contract_code=null`; retaining price evidence is preferable to inventing past contract identity.

## Implementation Authorization
- On 2026-08-19 the user explicitly authorized implementation of the revised report.
- Authorized scope is the report's Phase 0-3 observation path: core contracts, calendar/identity rules, provider acquisition seam, immutable artifacts, Dashboard projection, Traditional Chinese UI, and tests.
- Phase 4 research promotion, 08:45-08:50 confirmation streaming, Candidate/Score/RiskGate changes, simulation decisions, and any broker-order behavior remain outside this implementation.
- A query at or after 05:05 must remain PENDING or DEGRADED unless the implemented source-completeness predicate has qualified evidence; implementation convenience cannot weaken this rule.
- The architecture-patterns skill reinforces a domain/application/adapter split, but the implementation should match this repository's existing module style and avoid a broad directory refactor.
- The karpathy-guidelines skill requires surgical changes, explicit assumptions, and testable success criteria; unrelated dirty files must be preserved even where they overlap planned seams.

## Implementation Baseline
- The current worktree contains substantial unrelated in-progress strategy and historical-Kbar changes. Overlapping files include `README.md`, `dashboard/static/index.html`, `market_data/provider.py`, `strategy_catalog/service.py`, and `tests/test_shioaji_provider.py`.
- All overlapping edits must be incremental and context-specific. No reset, checkout, whole-file replacement, or cleanup of adjacent code is authorized.
- Repository memory confirms the existing Shioaji session is market-data-only (`subscribe_trade=False`) and owns explicit streaming shutdown/logout. The futures acquisition seam must reuse that boundary and must not add trade callbacks, CA activation, broker orders, or a second unmanaged login.
- Repository memory also confirms dashboard assembly belongs server-side in `dashboard/service.py` and `dashboard/server.py`, while the browser should only render the projection.
- No current repository `AGENTS.md` or `RULES.md` was found; the project runtime contract is in `pyproject.toml` and existing tests.
- `pyproject.toml` package discovery currently omits `premarket*`; adding the new package requires a scoped packaging update or installed builds will silently exclude it.
- The approved implementation report is explicitly Phase 0-3 only and requires a lazy dashboard query path, immutable separated artifacts, observation-only UI, and no automatic 05:05 scheduler.
- Live source qualification cannot be inferred from public SDK documentation. Code may expose a fail-closed Shioaji capability, but `READY` must be impossible unless qualified completeness evidence is supplied by the source/result contract.
- Concurrent edits added Shioaji Kbar timeout/retry behavior and new experimental backtest strategies. The TAIFEX patch must preserve the timeout constants, `_is_kbar_timeout`, provider retry flow, UI capability controls, and catalog bindings exactly.
- `MarketDataProvider` already acts as the driven port and `ShioajiProvider` is the adapter. A narrow optional `supports_premarket_context()` / `get_taifex_night_session()` capability can match repository style while returning a `premarket` domain DTO; the premarket domain must not import `market_data.provider`.
- `MockProvider` can supply deterministic futures fixtures for default CI, but mock completeness must be explicitly tagged as fixture-qualified rather than implying Shioaji production qualification.
- `DashboardService` owns cached stock snapshots and only queries on first snapshot or explicit refresh. Injecting an optional `PremarketContextService` lets the same refresh build a server-side `premarket_context` projection without altering `ScanResult`, stock candidate logic, or browser calculations.
- `RuntimeComposition.create()` is the single wiring point and already accepts injected services for tests. It can construct the premarket service once and pass it to `DashboardService`; no FastAPI route or second provider login is needed.
- The strategy catalog supports non-order `SIGNAL` metadata. `taifex_overnight_context_v0` should be `EXPERIMENTAL`, bind to a metadata-only builtin capability, and coexist with the unchanged `premarket_gap_watchlist_v1` DRAFT row.
- Existing dashboard service tests establish object-identity cache behavior. Premarket tests should preserve that behavior and separately prove one provider query per completed cache key.
- Existing capture artifacts validate immutable bytes and SHA256 but do not provide a generic writer/repository. The premarket slice can keep canonical immutable domain artifacts and an injected in-memory artifact repository first; durable raw capture remains a qualification action, not an implicit filesystem side effect during dashboard refresh.
- `ShioajiProvider.get_kbars()` is stock-specific only at contract lookup; its timeout, quota guard, Kbar mapping, and Taiwan wall-time conversion are reusable for a futures-contract query if extracted carefully without changing existing behavior.
- The UI already has a four-card overview followed by candidate/detail content. The premarket panel should be inserted between the overview summary and candidate workspace, with new CSS/classes and one renderer fed only from `snapshot.premarket_context`.
- Dashboard JavaScript centralizes rendering in `render(snapshot)` and has reusable escaping/number/percent/time formatters. The new renderer can format backend values without adding session, completeness, or return calculations.
- Existing UI tests are static contract checks plus a dedicated Node syntax script. Add a focused premarket static contract test and run the shared JavaScript checker after the incremental HTML patch.
- The repository has an existing `.venv` with pytest; use `.venv/bin/python` for all verification instead of ambient Python 3.13.
- Focused pre-change baseline is green: 27 tests passed across dashboard service, runtime composition, Shioaji provider, strategy catalog, and backtest UI contracts.

## Current TAIFEX Calendar Verification
- The official TAIFEX 2026 market calendar remains the base source and marks non-trading days, including the special 2026-02-12 and 2026-02-13 pre-Lunar-New-Year closures.
- TAIFEX separately announced the full 2026-02-12 through 2026-02-22 closure window and the 2026-06-19 Dragon Boat Festival closure.
- TAIFEX's current announcements also show an emergency 2026-07-10 typhoon closure. Therefore the annual PDF alone is insufficient; the vendored artifact must carry an as-of date and explicit exceptional closure set.
- The 2026 weekday closures required by the current artifact are 2026-01-01; 2026-02-12, 13, 16-20, 27; 2026-04-03, 06; 2026-05-01; 2026-06-19; 2026-07-10; 2026-09-25, 28; 2026-10-09, 26; and 2026-12-25.
- A target Monday session begins after the previous valid general trading day and can end on Saturday at 05:00. `query_not_before` must be derived as `session_end + 5 minutes`, not as 05:05 on the target trading date.

## Current Shioaji Contract Verification
- Current Shioaji 1.7 documentation uses `api.contracts.get("TXFR1")` for the provider-neutral Contract and `api.contracts.info(contract)` for `FuturesInfo`; the Contract carries `target_code`, while FuturesInfo carries `delivery_month`, `last_trading_date`, `reference`, and `update_date`.
- The documented futures Kbar call is the same `api.kbars(contract, start, end, timeout)` API used for stocks. The adapter can reuse the repository's bounded Kbar query mechanics after resolving a futures Contract.
- Shioaji documents continuous R1 historical prices and automatic rollover, but that does not provide past per-row contract identity. The dashboard's live/as-of Context may persist current `target_code`; historical backfill must continue using the separate dated resolver or remain `UNRESOLVED`.
- The Shioaji adapter now resolves `api.contracts.get/info`, reuses the existing bounded Kbar query path, preserves the provider-reference name, and deliberately reports completeness `UNKNOWN`; focused provider/context tests pass.

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| First combined planning-file patch used a table row in the wrong section as context | Re-read the exact file tails and applied a narrower patch without repeating the failed context. |

## Resources
- Repository: `/Users/stevehuang-work/Documents/tw_intraday_trader`
- Memory registry: `/Users/stevehuang-work/.codex/memories/MEMORY.md`
- Report: `architecture/taifex_night_session_premarket_implementation_plan.md`

## Continuation findings

- The implemented V0 repository is append-only only within one process; restart recovery and raw source retention remain absent.
- A separate daily-Kbar qualification workflow appeared concurrently in the shared worktree. It is not a TAIFEX dependency and must not be modified or reused implicitly.
- Continued implementation remains observation-only. Durable evidence and reconciliation may enrich the dashboard projection, but cannot become Candidate, Score, RiskGate, simulation, or broker-order input.
- The repository already ignores `data/backtest/` but not a premarket evidence directory. Use a dedicated `data/premarket/` path and add only that path to `.gitignore`.
- `SourceObservation` currently retains only `raw_source_digest`; the canonical SDK-derived payload is discarded. Durable raw evidence therefore requires an optional canonical `raw_source_json` carried by the provider-neutral observation and validated against its SHA256.
- Use one `PremarketArtifactRepository` port with in-memory and content-addressed filesystem adapters. Services depend on the port; RuntimeComposition selects the filesystem adapter. Context and Reconciliation remain separate files and raw payloads are keyed only by source digest.
- Content-addressed filenames plus exclusive create preserve append-only semantics. Rehydration must rebuild typed artifacts and revalidate their canonical digest instead of trusting stored JSON fields.

## Shioaji qualification verification

- Current official Shioaji documentation defines `api.ticks(contract, date=trading_date, query_type=AllDay, timeout=...)`; the date is explicitly the trading date, and TXFR1 is a documented futures code.
- The same official page states historical Tick/Kbar queries consume bandwidth, are intended for after-market analysis, and must not be polled as realtime data. The qualification workflow must therefore be an explicit one-shot CLI, not part of the dashboard refresh loop.
- Tick fields available for comparison are `ts`, `close`, `volume`, bid/ask fields, and tick type. Kbar fields are `ts`, OHLC, Volume, and Amount.
- A same-session Tick/Kbar aggregate match and repeated source stability are useful evidence but still do not constitute an official Shioaji finalization marker. Qualification reports must end in an explicit unqualified state until reviewed source-completion evidence is frozen.
- The existing unrelated daily-equity G0 workflow follows the same fail-closed principle, but this TAIFEX implementation will keep its contracts in the `premarket` bounded context and will not import or modify that concurrent module.
- The 2026-08-19 live capture returned 831 filtered Kbars and 20,946 night-session ticks. With the initial filter, Tick versus Kbar close differed by -9 and volume by +12.
- Raw evidence proves Shioaji emitted a Kbar at exactly `05:00` with close 44,527 and volume 12; the adapter's `< session_end` filter excluded it. Kbar timestamps are minute-end labels: the first night Kbar is `15:01` for the first minute and the final Kbar is `05:00`.
- The provider adapter must therefore select source Kbars with `session_start < timestamp <= session_end` and normalize each `NightBar.timestamp` to minute start. The application service can then retain its provider-neutral `[start, end)` event-time contract.
- Historical ticks can share an identical timestamp, which is visible in official examples and the live capture. Qualification ordering must allow nondecreasing Tick timestamps and reject only actual backward movement.

## TAIFEX reconciliation verification

- The official TAIFEX daily futures report identifies the 2026-08-19 after-hours TX 202608 session as 2026-08-18 15:00 through 2026-08-19 05:00 and reports open 45,137, high 45,208, low 44,424, close 44,527, and volume 28,126.
- The after-hours table renders settlement as `-`. This is absence of a TAIFEX night-session settlement value, not evidence that the Shioaji reference price equals settlement.
- TAIFEX states that reported volume includes spread and block-trade contracts. The captured Shioaji Tick/Kbar aggregate has not been proven to use that same basis, so volume must be retained as official evidence but excluded from equality until its basis is qualified.
- A reconciliation parser must join the TAIFEX `delivery_month` to the Context Artifact's dated contract identity. It must not compare TAIFEX product/month strings directly to Shioaji's resolved code, and it must never resolve historical evidence from the current `TXFR1.target_code`.
- A price match with an unqualified volume basis is `PARTIAL`, not `MATCHED`; it cannot mutate Context health or satisfy READY.
- A live 2026-08-19 current/as-of Context resolved `TXFR1` to `TXFH6` / delivery month `202608` and observed OHLC 45,137 / 45,208 / 44,424 / 44,527 with Shioaji Kbar volume 27,692. It remained `PENDING` because source completeness is still unqualified.
- The live official TAIFEX report returned the same four OHLC values, null after-hours settlement, and volume 28,126. Reconciliation produced zero OHLC deltas and `PARTIAL` with `TAIFEX_VOLUME_BASIS_UNQUALIFIED`; the 434-contract volume difference was retained but not treated as a mismatch.
