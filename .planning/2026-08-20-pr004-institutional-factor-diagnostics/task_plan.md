# Task Plan: PR-004 Institutional Factor Diagnostics

## Goal
Implement a reproducible, research-only institutional factor diagnostics layer that combines pinned institutional, PIT universe, and daily-price evidence without creating a candidate strategy or runtime integration.

## Current Phase
Complete — awaiting PR-004 review gate

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the PR-003 review approval and PR-004 conditions.
- [x] Inspect the approved PR-004 architecture section and current institutional, PIT universe, and daily-price lineage seams.
- [x] Inventory concurrent worktree changes and freeze protected files.
- **Status:** completed

### Phase 2: Research contracts and lineage
- [x] Define the smallest `ResearchRunManifest v0` with institutional, universe, and price ID+digest plus factor definition digest.
- [x] Define stable `EXPLORATORY` status, execution tiers, issue codes, and deterministic serialization.
- [x] Keep the implementation research-only and independent from watchlist/runtime/trading packages.
- **Status:** completed

### Phase 3: Factor computation and diagnostics
- [x] Implement foreign/trust net, positive days, consecutive days, and self-normalized flow using only completed prior observations.
- [x] Implement coverage, null rate, daily distribution, forward-return 1D/3D/5D, rank IC, ICIR, and decay outputs.
- [x] Require validated PIT evidence for cross-sectional rank/IC while preserving explicitly limited per-symbol diagnostics without PIT.
- **Status:** completed

### Phase 4: Fixtures and poison gates
- [x] Add deterministic fixtures for institutional + universe + price evidence.
- [x] Prove same input bundle yields the same factor/report digest.
- [x] Prove missing/changed universe or price/institutional digest blocks rank/decile/selection outputs and reports `PIT_UNIVERSE_MISSING` or lineage failure.
- [x] Prove future institutional rows, future prices, and future universe revisions do not change an earlier as-of run.
- [x] Prove all outputs stay `EXPLORATORY` and contain no candidate/buy/order semantics.
- **Status:** completed

### Phase 5: Verification and delivery
- [x] Run focused coverage, Ruff/format, compile, wheel/import, and full regression.
- [x] Audit that PR-005 strategy, watchlist generation, CandidatePool, BuyScore, backtest execution, and runtime/order paths remain untouched.
- [x] Update architecture status, restore the prior active planning pointer, and stop at the PR-004 review gate.
- **Status:** completed

## Scope Boundary

- In scope: research-only factor values, diagnostic statistics, deterministic lineage manifests/reports, PIT/no-look-ahead poison gates, fixtures/tests, package/docs.
- Out of scope: thresholds/weights, top-N selection, consensus score, strategy definition, watchlist artifact, CandidatePool, BuyScore, backtest execution, ML, dashboard/runtime integration, broker orders.
- All results: `EXPLORATORY`.
- Real Money: PROHIBITED.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Start PR-004 after the explicit review approval | PR-003 is approved with no blocking issue and the attachment marks PR-004 ready to start. |
| Keep PR-004 diagnostic-only | The review explicitly rejects direct Top 10% buys, consensus scores, ML, and strategy semantics. |
| Pin all three evidence domains by ID+digest | Reproducibility requires institutional + universe + price lineage, not only data values. |
| Fail closed for cross-sectional output without PIT | Per-symbol raw diagnostics may remain visible, but rank/IC/decile/selection require validated PIT coverage. |
| Preserve unrelated worktree changes | Freshness calibration, canonical market pipeline, and other active planning sessions are concurrent scopes. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Full baseline test collection initially hit missing concurrent `market_data.journal` | Preserved the unrelated scope; after that concurrent file arrived, final full regression passed 550 tests with 1 skip. |
| Project `.venv` lacks `setuptools.build_meta` for wheel creation | Built with the system Python's existing setuptools backend and no dependency/network install; wheel content and isolated zip import passed. |
