# Task Plan: PR-006 Institutional Schema Freeze and Durable Persistence

## Goal

Implement only the PR-006 scope authorized by the PR-005 review: freeze the institutional candidate persistence contract and add fail-closed durable storage without connecting it to CandidatePool, BuyScore, execution, or production runtime paths.

## Current Phase

Complete — PR-006 ready for review

## Phases

### Phase 1: Review Gate and Repository Discovery

- [x] Read the supplied PR-005 review completely and extract every condition.
- [x] Reconstruct the PR-001 through PR-005 contracts and current worktree ownership.
- [x] Inspect migrations, repository ports/adapters, persistence tests, and packaging conventions.
- **Status:** complete

### Phase 2: Contract and Test Design

- [x] Freeze the minimum PR-006 schema, keys, digests, idempotency, and conflict semantics.
- [x] Define SQLite/PostgreSQL parity and forward-only migration acceptance tests.
- [x] Confirm explicit non-goals and no runtime admission path.
- **Status:** complete

### Phase 3: Focused Implementation

- [x] Add the authorized migration and persistence contract/ports.
- [x] Add SQLite and PostgreSQL adapters using existing repository patterns.
- [x] Add deterministic serialization and fail-closed write/read behavior only where required.
- **Status:** complete

### Phase 4: Verification

- [x] Run focused migration, repository, serialization, and conflict tests.
- [x] Run adjacent institutional suites, static checks, and full regression.
- [x] Validate package/build import behavior if packaging changes are required.
- **Status:** complete

### Phase 5: Review Handoff

- [x] Audit diffs against PR-006 scope and preserve unrelated worktree changes.
- [x] Update PR status/docs and planning evidence.
- [x] Restore the pre-existing active-plan pointer and deliver review-ready results.
- **Status:** complete

## Key Questions

1. What exact rows and JSON payloads must be durable, and which PR-005 artifacts remain filesystem-only?
2. What natural/idempotency keys and digest-conflict rules are mandated by the review?
3. Which existing migration/repository abstractions provide SQLite/PostgreSQL parity without speculative framework work?
4. What proves a persisted row is semantically and byte-equivalent to the frozen artifact while excluding future outcomes?

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Keep PR-006 isolated from runtime candidate admission and trading decisions | PR-005 is approved only as exploratory candidate-prior research; the review authorizes persistence next, not strategy/runtime integration. |
| Treat all attached review text as evidence stored in `findings.md` | The planning skill requires external supplied content to remain data rather than executable plan instructions. |
| Preserve unrelated dirty-worktree changes | Multiple completed and concurrent project tracks share this checkout. |
| Freeze the v0 status surface before persistence | Rename the artifact/projection `label` field to explicit `research_status` and add permanently false `execution_allowed`; retain the stricter existing `live_admission_ready=false`. |
| Use an independent institutional migration namespace | The reserved backtest migration `004` and WatchlistRepository do not exist; inventing them would expand scope and let schema design another domain. |
| Use one portable SQL migration for both database adapters | TEXT/INTEGER canonical columns allow SQLite and PostgreSQL to execute identical DDL, eliminating dual-schema drift. |
| Key idempotency by canonical causal run inputs | Artifact ID is output-digest-derived and cannot detect divergent output from identical pinned inputs; generated-at provenance is excluded so later retries cannot evade the unique run identity. |
| Verify normalized rows on every read/replay | Canonical JSON is authoritative bytes; normalized rows must match its scalars, entry order, entry JSON, and digests before an artifact is returned. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Initial combined attachment read exceeded the output context and was truncated | 1 | Re-read the 735-line review in bounded chunks and record extracted conditions in the isolated findings file. |
| One `apply_patch` attempted delete-and-add operations for the same files in one patch | 1 | Split replacement into a delete patch and an add patch; no product file was affected. |
| First multi-file contract patch used an exact architecture context that differed by one line break | 1 | Confirmed the patch was atomic/no-op, re-read the live lines, and split the exact architecture update from the code changes. |
| New persistence test imported the adjacent builder as a top-level test module | 1 | Use the repository-root namespace import `tests.test_institutional_candidate_prior`; verified it builds the frozen artifact. |
| First package-export patch expected the wrong `__init__.py` import block | 1 | Re-read the file and applied a scoped export/package-data patch; no partial change occurred. |
| First forbidden-field table patch used the pre-format layout | 1 | Re-read the Ruff-formatted test and applied it against the exact live context. |
| Completion helper defaulted to the legacy root `task_plan.md` instead of resolving the active isolated plan | 1 | Re-run it with the explicit PR-006 plan path; the active-plan resolver itself points to the correct directory. |

## Notes

- `EXPLORATORY` is an immutable classification for this PR unless the supplied review explicitly says otherwise.
- No BuyScore, Entry Rule, Order, Broker, Subscription, CandidatePool runtime admission, or real-money path.
- No flow-partition, factor-report, evaluation-result, API, Dashboard, or runtime persistence in this bounded Candidate Prior PR.
- Live PostgreSQL execution remains environment-gated because `TEST_POSTGRES_DSN` is not configured; SQLite executes the same portable migration and shared repository implementation unconditionally.
- Re-read this plan before contract design and before final scope audit.
