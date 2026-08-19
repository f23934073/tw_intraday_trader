# Progress Log

## Session: 2026-08-19

### Current Status
- **Phase:** 7 - G0 Provider and daily-source qualification
- **Started:** 2026-08-19

### Actions Taken
- Created an isolated planning workspace so the existing premarket-watchlist plan remains intact.
- Confirmed the dashboard's daily SMA display and the backtest's distinct intraday EMA crossover implementation.
- Identified cross-session daily feature state as the main design seam to investigate before writing the plan.
- Confirmed that current daily datasets cannot be selected by a dedicated capability, while the service already performs strategy capability preflight before queueing and before execution.
- Confirmed that sealed dataset bars and the engine's later-timestamp fill rule support a daily-close signal with next-daily-open execution.
- Identified the source-resolution gap: the Provider contract does not declare a Kbar interval, so daily capability needs an explicit sealed-dataset derivation/import contract instead of heuristic request-span inference.
- Identified an existing UI interaction: the default end-of-day exit is incompatible with a long-horizon MA hold unless the user intentionally selects it.
- Authored the standalone plan at `architecture/daily_sma_20_60_crossover_implementation_plan.md`, including source qualification, sealed daily-data lineage, daily feature state, two-direction signal contracts, gates, tests, rollout, and rollback.
- Verified the plan contains all required sections and no trailing whitespace. Scope audit found only the new standalone plan, its isolated planning records, and the active-plan pointer were changed by this task; existing product-code edits remain untouched.
- Restored planning context after the supplied review. Confirmed P0-1 is a concrete exit-timing issue: pending entries already survive sessions, but a daily death-cross exit would currently be forced to same-session EOD close because each daily bar is `is_last_bar`.
- Recorded all four requested P0 contracts before updating the implementation plan; no product code has been changed.
- Revised the standalone plan with `INTRADAY_NEXT_BAR` / `DAILY_NEXT_BAR` / `SESSION_CLOSE` horizons, a true terminal-data concept, `RAW` adjustment policy, canonical Decimal evidence, calendar-backed resolved session dates, and the new G2.5 execution gate.
- Separated SMA trigger-evidence assertions from aggregation-policy decision assertions, and added result-summary attribution requirements.
- Verified all four P0 contracts and G2.5 are present in the plan, with no trailing whitespace. Targeted scope audit confirms this review revision only changed the plan artifacts and active-plan pointer; no product source or tests were edited.
- User approved G0 execution only. Restored the plan, captured the dirty-worktree baseline (28 tracked files changed plus existing untracked work), and constrained this phase to replayable source-qualification evidence and fail-closed reporting.
- Reused the repository's offline quote-capture/qualification conventions as design input, while confirming its live samples cannot substitute for Kbar source evidence.
- Identified the required capture boundary: record raw Shioaji Kbar field types and textual representations before the provider's normal mapping loses that information.
- Implemented an isolated raw-Kbar capture schema and offline qualification/replay path. It stores raw Python types plus `repr`/`str`, SHA-256 row digests, a versioned TWSE session contract, resolved sessions, coverage evidence, and fail-closed result artifacts under `research/daily_kbar_g0/`.
- Performed the live, market-data-only Shioaji capture for 2330: 2026-08-18 full-day, 2026-08-19 partial-day, and 2026-08-17/18 chunk-boundary samples. No order path, strategy, dataset capability, dashboard, or existing Provider mapping was changed.
- G0 selected `BLOCKED`: the existing Provider request has no interval and supplies intraday bars; completed historical coverage and repeated raw digests do not constitute a provider finalization signal. The only prospective source path is `DERIVED_FINALIZED_SESSION_V1` after that missing proof is supplied.
- User requested continued implementation. Added Phase 8, constrained to an authoritative daily-close reconciliation that can resolve the exact G0 source-completion blocker; the SMA/strategy/dashboard gate remains in force.
- Identified the official TWSE `STOCK_DAY` monthly report as the potential independent end-of-session source, while recording its published multi-session volume scope as a contract question to qualify rather than silently collapsing it into Shioaji regular-session volume.
- Compared the existing full-session fixture with the official 2026-08-18 row: OHLC matches exactly, while raw volume does not. This establishes the need for an explicit Shioaji volume-unit/session-scope verdict in the reconciliation artifact.
- Added a deterministic reconciliation schema which requires raw Kbar `Amount`, proves common-lot volume by checking each `Amount / (Volume * 1000)` against its bar's high/low range, and compares the aggregated session with raw official TWSE `STOCK_DAY` output. It keeps official daily total scope separate from the observed 09:01–13:30 regular-session Kbar scope.
- Updated G0's root qualifier so successful official reconciliation can select `DERIVED_FINALIZED_SESSION_V1`; `RAW_CORPORATE_ACTION_UNADJUSTED` now correctly remains a formal-research blocker rather than an operational G0 blocker.
- Captured and replayed actual Phase 8 evidence: all 266 Shioaji minute bars passed the Amount/common-lot check, and their OHLC exactly matches the raw official TWSE 2026-08-18 daily-report row. The official whole-day amount/volume mismatch is saved as a documented scope difference, not erased.
- G0 root qualification now selects `DERIVED_FINALIZED_SESSION_V1` with no G0 blockers. The resulting daily data must retain raw price adjustment, common-lot volume, and regular-session-only contracts if later implemented.
- Final Phase 8 replay and scope audit passed: 12 focused tests pass, the root report selects `DERIVED_FINALIZED_SESSION_V1`, `git diff --check` and the targeted trailing-whitespace scan are clean, and this phase added only isolated G0 modules/scripts/tests/artifacts plus its planning records.
- User requested continued implementation after the G0 result. Began Phase 9 from the selected derived-daily source contract; strategy implementation remains research-only and must avoid overlapping the concurrent backtest changes until their current seams are rechecked.
- Added the derived-daily catalog path and deterministic tests for lineage, canonical decimal representation, session metadata, unchanged parent payload, and missing-proof rejection. Focused dataset/import verification now passes (3 tests).
- Added bounded, Decimal-only completed-daily SMA feature state; registered experimental SMA20/SMA60 golden-entry and death-exit definitions; and propagated `DAILY_NEXT_BAR` through evaluations, decisions, pending orders, fills, and serialized order payloads. Legacy order payloads omit the new field.
- First SMA integration run exposed a cross-session guard defect: the engine resets its per-symbol event index on each session, which prevented a one-bar daily session from evaluating the close after an overnight entry fill. The daily fill path now permits that completed-close evaluation while retaining the legacy intraday first-bar guard.
- Confirmed that the existing `StrategyCatalogService` bootstraps registry definitions and the application service already checks `required_capabilities` both before queueing and before worker execution. Added the two deployed SMA execution bindings to its allowlist; next work is a service-level derived-dataset registration and full end-to-end coverage.
- Added `BacktestApplicationService.create_derived_daily_dataset()`: it accepts only explicit per-session evidence digests plus the G0-derived session/RAW/volume contracts, seals through the catalog, and registers the immutable child as `READY`. It performs no Provider, broker, account, corporate-action, or order call.
- Focused daily/data/catalog/core/strategy regression now passes (25 tests). It covers warm-up and crossing equality, daily entry/exit timing, end-of-data unfilled status, catalog bootstrapping, daily capability preflight rejection, child sealing/registration, and a worker-run closed trade.
- Confirmed the remaining Phase 9 adapters: a thin CLI must consume an exact proof bundle and upsert the sealed child, while the existing capability-aware UI needs only a non-blocking SMA-versus-EOD-exit warning. Neither requires a browser calculation or a new backtest read API.
- Completed the CLI proof-bundle adapter, immutable re-run contract checks, selector warning, result decision-horizon rendering, and README operator guidance. A derived child requires a READY registered parent whose database manifest digest matches the sealed file manifest; it is then registered `READY` only after successful catalog sealing.
- Final scoped verification passed: 35 tests cover daily derivation, CLI, SMA execution, catalog, UI, core engine, and prior strategy expansion; `git diff --check` and `compileall` are clean. Full `pytest -q` was 383 passed, 1 skipped, 1 failed only in the existing `premarket` immutable-artifact test; its untracked artifact was preserved.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Markdown structure | Contract, data, engine, phases, tests, file map, rollout and DoD are present | All ten plan sections present | Pass |
| Whitespace scan | No blank-line whitespace or trailing whitespace in new plan records | No matches | Pass |
| Scope audit | No product implementation for this planning request | Only planning Markdown and `.planning/.active_plan` changed by this task | Pass |
| P0 review incorporation | Four P0 contracts, G2.5, evidence/aggregation split all explicit | All required contracts located in the revised plan | Pass |
| Raw Kbar qualification unit and artifact replay | Raw type preservation, session coverage, finalization fail-closed semantics, output replay | 2 focused tests passed | Pass |
| Provider regression | Existing Shioaji Provider behavior remains compatible | 9 focused tests passed | Pass |
| Compile check | New G0 modules/scripts compile | `compileall` succeeded | Pass |
| Phase 8 offline reconciliation | Common-lot Amount proof and official OHLC comparison | 3 focused tests passed | Pass |
| Phase 8 live capture and root replay | Shioaji Amount/Volume unit, official TWSE OHLC completion evidence, derived source path | `DERIVED_FINALIZED_SESSION_V1` selected | Pass |
| Focused regression and compile check | G0 fixtures, Provider mapping, new reconciliation modules and scripts | 12 tests passed; `compileall` succeeded | Pass |

### Errors
| Error | Resolution |
|-------|------------|
| Initial artifact-replay assertion used the former result shape after `RAW_CORPORATE_ACTION_UNADJUSTED` was moved from G0 blockers to formal-research blockers | Replayed the existing raw fixtures with the new qualifier before re-running the deterministic test; no raw evidence was changed. |
| First derived-dataset test run exposed a missing `Decimal` import and a one-bar fixture that correctly did not satisfy the intraday-parent guard | Added the import and made the missing-proof fixture genuinely intraday; focused tests pass. |
| Initial daily SMA cross-session integration test produced no closed trade | The exit guard compared session-local event indexes. Adjusted the guard narrowly for a `DAILY_NEXT_BAR_OPEN` fill and will re-run the full focused regression set. |
| Daily SMA application integration fixture was rejected before derivation | Its chosen ID omitted the catalog's required `dataset-` prefix. Corrected the test fixture; the existing dataset-ID contract remains unchanged. |
| Documentation search included an obsolete root `server.py` path | `rg` reported the absent path; documentation work uses the actual `README.md`, `dashboard/`, and test locations instead. No product behavior was affected. |
| Initial proof-bundle CLI test omitted optional `issues` | The parser defaulted it to a Python tuple but validated only JSON arrays. Changed the default to an empty list so omitted optional issues are accepted. |
| Full test suite stopped at one premarket artifact integrity failure | `data/premarket/raw/301fa2256fed2d78936b166cbbe9710c6997be285bf9dbc9f45cb57f2fa0adf3.json` existed outside Git with bytes that differ from the test's deterministic artifact. This is unrelated to daily SMA changes; no delete, overwrite, or premarket modification was performed. |
