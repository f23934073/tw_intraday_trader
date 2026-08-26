# Progress Log

## Session: 2026-08-26

### Current Status

- **Phase:** TS-006 — Review / fix / re-review loop
- **Started:** 2026-08-26

### Actions Taken

- Started the user-requested review loop with `code-review-excellence`, `karpathy-guidelines`, `planning-with-files`, and `ui-ux-pro-max`.
- Restored the authoritative scope, prior verification evidence, and Local Paper memory before inspecting the current diff.
- Reviewed the added persistence latch across command, strategy, terminal-fill, and daily-baseline paths. Checkpoint failures latch correctly, but terminal/daily Journal append exceptions are currently swallowed by `SimulationService` after only its quote-ingress flag is set; the command facade itself is not latched before a later automated intent can be appended.
- Reproduced that finding with a streaming later-fill failure test: before the fix, a second strategy submission did not raise and appended new records after the failed fill evidence.
- Latched all command-application, risk-rejection, cancellation, later-terminal, and daily-baseline persistence exceptions; the new regression and existing checkpoint latch test now pass (`2 passed`).
- Reproduced a second P1: replaying a BidAsk with the same exchange timestamp replenished already-consumed best-level volume and completed a partial order without new liquidity evidence.
- Changed streaming book ingress to reject equal as well as older exchange timestamps when no exchange sequence exists; duplicate-volume, limit-volume, normal later-fill, and persistence-latch regressions pass (`4 passed`).
- Reproduced and fixed the accounting-matrix edge case where a tiny SELL could silently produce a negative net cash effect after the TWD 20 minimum commission. The Decimal kernel now fails closed; all pure execution-cost tests pass (`40 passed`).
- Reproduced coherent fill.v3 commission/net tampering that previously passed semantic validation. Added cumulative order gross evidence and exact cumulative/delta commission-policy validation; domain plus replay regressions pass (`42 passed`).
- Closed an unresolved-cancel restart hole by treating a cancel command after the latest projection checkpoint as mutation-bearing Journal tail. Recovery now fails closed instead of restoring the old pending order; focused recovery/cancel tests pass (`3 passed`).
- Extended v3 replay validation across partial fills: fill sequence, cumulative gross, commission, and tax must equal the previous immutable fill plus the current delta. A second-fill cumulative-tax tamper now fails closed; focused v3 tests pass (`3 passed`).
- Reproduced v2 invalid tick being journaled as an approved command and escalated to session-wide handler recovery. Added read-only v2 tick/instrument preflight before command append; invalid admission leaves Journal empty and a later valid order still fills (`2 passed` with unsupported descriptor coverage).
- Third-pass focused Local Paper, settings, replay, provider, Dashboard, strategy, Kill Switch, and no-DSN PostgreSQL suite is green: `241 passed, 1 skipped in 2.03s`; the skip is not counted as PostgreSQL evidence.
- Re-ran the actual disposable PostgreSQL combined UAT after every v3/recovery fix: `5 passed in 0.76s`.
- Re-ran Python compileall, JavaScript syntax checks, and `git diff --check`: all passed.
- Repository-wide regression after all fixes: `1500 passed, 43 skipped in 8.25s`; skips are not used as PostgreSQL evidence.

- Read the required planning, coding-discipline, and architecture skill instructions.
- Restored existing planning context and created an isolated planning directory for this task.
- Confirmed a clean detached worktree and recorded HEAD/worktree topology.
- Read relevant Local Paper memory and the prior settings implementation summary.
- Read the source coordination thread and confirmed the task must avoid overlap until Kill Switch stabilizes.
- Ran the focused Local Paper baseline: `72 passed in 0.52s`.
- Added provider-neutral instrument descriptors and Mock/Shioaji catalog adapters.
- Added Decimal-only common-stock tick, fixed adverse slippage, and frozen accounting decisions.
- Added boundary, invalid-input, product-admission, cumulative commission/tax, and golden-vector tests.
- Added an opt-in v2 execution path that centralizes submit, snapshot refresh, and BidAsk matching.
- Applied complete accounting decisions atomically to cash, position cost, SELL realized PnL, and order totals.
- Added fill.v3 writer/reader/reducer validation and preserved existing fill.v1/v2 behavior.
- Proved v3 replay digest/cash/PnL equality across three independent reducer constructions.
- Added v1/v2 settings readers, v2 frozen policy identity, 5 bps preview, mixed draft migration, and explicit activation semantics.
- Verified v1 preview does not rewrite the settings file and v2 policy overrides fail closed.
- Inspected PostgreSQL prerequisites without exposing DSNs; both expected DSN variables are absent.
- Tightened Shioaji admission after verifying `STK` alone also covers ETFs; raw category and ordinary-share code are now persisted in the descriptor evidence.
- Started a disposable PostgreSQL 16 container and proved an actual connection/migration/Journal baseline.
- Confirmed the Kill Switch candidate is quiet and whitespace-clean but still uncommitted at the original detached HEAD, so it cannot yet be rebased safely.
- Coordinated the user-authorized scoped Kill Switch local commit and verified SHA `34fb5250030d170b7909870f086c5693f728a9aa`.
- Rebasing with autostash succeeded without conflict; this worktree now uses the durable Kill Switch commit as its exact HEAD and retains only Tax/Slippage edits above it.
- Pinned complete v2 cost, rounding, tax, slippage, tick, calibration, and descriptor admission identities in session metadata while preserving v1 metadata.
- Propagated whole-TWD commission rounding into manual and automated RiskGate policies.
- Wired composition to activate the v2 execution policy only for explicit settings v2 and reject mismatched injected settings.
- Fixed v3 restart recovery for the Journal's immutable nested descriptor mapping.
- Proved fill.v3 restart accounting and durable Kill Switch integration together.
- Changed the API to accept only cash, daily limit, and Decimal-string slippage; frozen cost overrides are rejected and stale revisions remain 409.
- Added a read-only v2 preview for legacy settings without rewriting the v1 file; apply is blocked until the preview is explicitly saved.
- Updated the Dashboard to distinguish explicit commission/tax from diagnostic slippage and to show fill reference evidence.
- Applied the UI review checklist: visible focus, error focus management, 44px inputs, helper linkage, and scrollable responsive settings drawer.
- Browser smoke passed at desktop, 375x667, and 667x375 with no horizontal overflow or console errors; cache-busted assets were served.
- Tightened settings v2 fail-closed parsing for normalized schema identity, exact Boolean non-day-trade identity, and mandatory slippage evidence.
- Tightened fill.v3 validation for required cost fields, exact frozen SELL tax, whole-TWD costs, recomputed adverse tick outcome, typed descriptor provenance, and coherent tamper attempts.
- Updated two stale v1 Dashboard regression assertions to the authoritative v2 frozen-cost/cache contract.
- Completed an actual PostgreSQL combined restart UAT after the final reader/domain integrity changes: `5 passed in 0.71s`.
- Completed the final focused no-DSN suite: `200 passed, 1 skipped in 1.78s`; the PostgreSQL skip is not counted as UAT.
- Completed the full no-DSN regression: `1485 passed, 43 skipped in 8.14s`; skips are not used as PostgreSQL evidence.
- Completed Python compile, JavaScript syntax, and `git diff --check` successfully.
- Local adversarial review found no unresolved P1/P2 issue; formal TS-G5 still requires a separate reviewer.

### Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Initial git scope check | Clean isolated worktree | Clean at `657c3bb` before planning files | PASS |
| Local Paper focused baseline | Existing core behavior passes before edits | `72 passed in 0.52s` | PASS |
| TS-G1 domain/provider suite | Pure policy and descriptor tests pass | `56 passed in 0.14s` | PASS |
| TS-G1 compile/diff check | New Python compiles; whitespace clean | PASS | PASS |
| TS-G2 focused core/legacy suite | Domain, service, replay, provider, legacy tests pass | `125 passed in 0.40s` | PASS |
| Settings v2 focused suite | v1 no-rewrite, mixed migration, digest, policy validation | `62 passed in 0.11s` with domain/service tests | PASS |
| Tightened descriptor/settings focused suite | Common stock allowlist, ETF/special/unknown deny, v3/settings | `82 passed in 0.29s` | PASS |
| Disposable PostgreSQL Journal baseline | Actual database migration/idempotency/checkpoint | `2 passed in 0.17s` | PASS |
| TS-G2b Journal/composition/Kill Switch integration | v2 metadata, fill.v3 restart, exact risk rounding, durable final admission | `94 passed in 0.61s` | PASS |
| TS-G3 settings/API/UI/static suite | v1 preview, v2 apply, stale/frozen rejection, Kill Switch UI preservation | `88 passed in 1.42s`; JS syntax and diff check clean | PASS |
| TS-G3 responsive browser smoke | Desktop, 375x667, 667x375; no overflow/console error | PASS | PASS |
| Final focused Local Paper suite (no DSN) | All changed domain/service/replay/settings/API/UI/Kill Switch tests pass | `200 passed, 1 skipped in 1.78s`; PostgreSQL skip not counted as UAT | PASS |
| TS-G4 PostgreSQL combined UAT | New connections x3, tamper fail-closed, Kill Switch and legacy PostgreSQL regressions | `5 passed in 0.71s` | PASS |
| Full regression | Repository-wide no-DSN suite passes | `1485 passed, 43 skipped in 8.14s` | PASS |
| Final static checks | Python compile, JS syntax, whitespace | PASS | PASS |
| TS-G5 | Requested severity-first review has no unresolved P1/P2 correctness issue | Review/fix/re-review loop complete | PASS / APPROVE |
| TS-006 post-fix focused suite | All affected Local Paper and Kill Switch tests pass | `241 passed, 1 skipped in 2.03s`; PostgreSQL skip excluded | PASS |
| TS-006 post-fix PostgreSQL UAT | Real disposable database, new connections, partial fills, tamper, Kill Switch | `5 passed in 0.76s` | PASS |
| TS-006 post-fix full/static | Repository-wide suite plus compile/JS/diff checks | `1500 passed, 43 skipped in 8.25s`; static checks PASS | PASS |

### Final review decision

- **APPROVE** — six reproduced P1 findings and one P2 finding were fixed; no unresolved P1/P2 correctness issue remains.
- Real slippage calibration remains an explicitly separate evidence task and is not represented as complete.

### Errors

| Error | Resolution |
|-------|------------|
| External Kill Switch thread search stalled for over two minutes | Terminated the read-only query; will use a narrower query/status check before TS-002b/TS-003. |
| `.venv/bin/python` absent and system Python has no pytest | Used `/Users/stevehuang-work/Documents/tw_intraday_trader/.venv/bin/python` read-only with this worktree as cwd. |
| New streaming limit test timed out on a stale fixed timestamp | Changed the fixture to current Asia/Taipei observation time. |
| Price fixture leaked into later legacy tests | Copied Mock rows before mutation; rerun passed. |
| Cross-thread coordination send did not complete | Terminated after repeated waits; no product state depended on it. |
| First v3 composition restart rejected `MappingProxyType` descriptor evidence | Restored against `collections.abc.Mapping`, matching Journal immutability without weakening descriptor/digest validation. |
| Final focused command initially targeted a missing `.venv/bin/pytest`; `uv --frozen` then refused because the repository has no lockfile | Used the existing main-workspace venv executable read-only; no dependency install or source write occurred outside this worktree. |
| First final full regression had two stale v1 UI assertions | Updated expected contract to frozen fee/tax fields, editable slippage, and v2 asset versions; rerun passed all 1482 tests. |
