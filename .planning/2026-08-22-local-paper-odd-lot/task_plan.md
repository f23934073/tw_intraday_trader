# Task Plan: Local paper odd-lot support

## Goal

Allow the existing local paper simulation to submit, fill, recover, and display exact share quantities, including Taiwan odd lots of 1-999 shares, without adding any broker or real-money order path.

## Current Phase

Complete

## Success Criteria

- Manual simulation accepts exact positive integer share quantities such as 1, 999, 1000, and 1500.
- Strategy-paper commands can carry the same exact-share quantity; the existing continuous strategy may retain its fixed 1000-share policy.
- Risk, Journal, retry, partial-fill, recovery, order projection, and position projection preserve exact shares without floor division or rounding.
- Existing whole-lot callers and persisted payloads remain readable where practical.
- No CA activation, `place_order`, trade subscription, Shioaji Simulation order, or real-money order path is added.
- The odd-lot safety boundary remains visible after every dynamic projection render.
- Manual and strategy HTTP APIs reject JSON booleans and other non-integer quantity types.
- The simulation ES-module cache key changes with the share-input contract.
- Focused tests and the relevant full regression pass.

## Phases

### Phase 1: Quantity contract discovery

- [x] Trace all order quantity inputs, persistence payloads, reducers, matching, retries, and UI projections.
- [x] Record pre-existing user changes in overlapping files and protect them.
- [x] Establish a focused baseline.
- **Status:** complete

### Phase 2: Contract and regression tests

- [x] Choose the smallest backward-compatible exact-share contract.
- [x] Add failing tests for manual odd-lot, strategy odd-lot, partial fill, retry, and recovery.
- **Status:** complete

### Phase 3: Implementation

- [x] Implement exact-share core and adapter behavior.
- [x] Update API and Traditional Chinese UI to input/display shares.
- [x] Update documentation without changing broker boundaries.
- **Status:** complete

### Phase 4: Verification

- [x] Run focused Python and frontend checks.
- [x] Run relevant/full regression and inspect the final diff for scope.
- **Status:** complete

### Phase 5: Delivery

- [x] Confirm plan completion and summarize behavior, tests, and boundaries.
- **Status:** complete

### Phase 6: Request Changes remediation

- [x] Add regression tests for persistent safety copy, strict HTTP quantities, and the module cache key.
- [x] Apply the smallest UI/API/cache-buster fixes.
- [x] Rerun focused frontend/API tests, static gates, and relevant regression.
- **Status:** complete

### Phase 7: Scoped commit

- [x] Resolve the exact share-native hunks against the mixed worktree.
- [x] Stage only the reviewed odd-lot implementation and cache chain; exclude planning and unrelated work.
- [x] Verify the staged diff, rerun staged-scope checks, and create one commit without pushing.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Scope is local paper simulation only | The current repository intentionally has no broker execution path, and Shioaji Simulation does not support odd lots. |
| Canonical quantity is integer shares | Odd lots cannot be represented safely by the current integer-lot model; exact shares already match `OrderCommand` and position contracts. |
| Preserve existing unrelated worktree changes | The shared branch contains extensive user work that is outside this request. |
| Add `quantity_shares` and retain legacy `lots` input | New commands stay exact while existing callers and older persisted states remain readable. |
| Keep the continuous Momentum controller fixed at 1,000 shares | Its one-lot risk policy is an independent product constraint; enabling odd-lot capability does not silently change strategy sizing. |
| Treat the review's three findings as commit-blocking follow-up | Each finding directly affects the just-added odd-lot contract and can be fixed without widening scope. |
| Keep `#order-preview` dynamic and add a sibling static warning | Avoids duplicate renderer changes and makes the safety boundary impossible for current projection writers to overwrite. |
| Use one strict positive integer alias for both shares and legacy lots | Prevents Pydantic boolean/string coercion consistently at both manual and strategy HTTP boundaries. |
| Keep `.planning/` out of the runtime commit | Planning artifacts are workflow evidence, not part of the approved product scope. |
| Use index-only patch staging for mixed files | Interactive whole-file staging risks including atomic-strategy/backtest hunks that share the same files. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Root planning files belong to a separate Freshness task | 1 | Created an isolated plan directory without changing `.planning/.active_plan`. |
| New odd-lot regression suite failed at the six expected unsupported boundaries | 1 | Proceed with the share-native implementation; 39 existing tests remained green. |
| First UI patch inserted the order quantity declaration into the positions mapper | 1 | Inspected the rendered source context, moved the declaration into the order mapper, and left position rendering unchanged. |
| Verification-command discovery referenced an absent Makefile | 1 | Used the repository's documented pytest, compileall, Node, and dashboard-JS checks instead. |
| Default dashboard environment retried an unavailable local PostgreSQL service | 1 | Ran the UI smoke test with explicit SQLite, memory Journal, disabled incremental sync, and MockProvider settings. |
| Port 8000 was already occupied by another local Python process | 1 | Preserved that process and used isolated port 8001 for the smoke test. |
| Full regression has one unrelated migration-order assertion | 1 | Confirmed it comes from pre-existing untracked migration 008 and a modified migration test, then reran all other tests with only that assertion deselected. |
| Initial HTTP red test reached the default Shioaji native provider and segfaulted | 1 | Isolated both validation tests with `MockProvider`; do not repeat the unsafe default-provider test path. |
| Initial `git add` could not create `.git/index.lock` in the workspace sandbox | 1 | Retried the authorized scoped staging operation with Git-write approval; do not repeat sandboxed index writes. |
| Sandboxed `git add -p` collected README choices but its internal `git apply` could not write the index | 1 | README remained unstaged; rerun interactive staging itself with explicit Git index approval. |
