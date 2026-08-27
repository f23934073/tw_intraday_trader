# Task Plan: Trade Management Shadow fill.v3 compatibility

## Goal
Implement and evidence-verify deterministic, tamper-evident `local_paper_fill.v3` BUY-fill activation for Trade Management Shadow while preserving fill.v1 compatibility and the no-execution/read-only Journal boundary.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture requested scope, safety boundaries, and delivery gates
- [x] Correct stale detached HEAD by fetching `origin/main` and creating authorized scoped branch from exact `037197e...`
- [x] Read current observer/builder schemas and existing tests
- [x] Determine whether fill.v2 has an explicit supported contract
- [x] Document findings and overlap boundaries
- **Status:** complete

### Phase 2: Contract & Regression Design
- [x] Define v3 identity, aggregation, duplicate/conflict, replay, and tamper contract from current source
- [x] Add pre-fix failing tests for single, partial, duplicate/conflict, tamper, restart/replay
- [x] Confirm unchanged legacy fill.v1 coverage
- **Status:** complete

### Phase 3: Scoped Implementation
- [x] Modify only Shadow observer/builder code unless a shared-core overlap is proven necessary
- [x] Preserve provenance, fingerprints, idempotency, session/symbol/side, `execution_authority=false`, and read-only Journal behavior
- [x] Keep C1 `execution_enabled=false`; add no order/broker/trade authority
- **Status:** complete

### Phase 4: Evidence Verification
- [x] Run focused tests and capture pre-fix/post-fix evidence
- [x] Run relevant safe PostgreSQL read-only/restart tests if formal fixtures exist (formal fixture selected but skipped because no explicit disposable DSN; not a PostgreSQL pass)
- [x] Before final review/commit, fetch and integrate latest docs-only `origin/main` (`33c9b3a` reported), resolve conflicts, and rerun all required validation
- [x] Run full regression and static/diff checks
- [x] Self-review and independent adversarial review; resolve all P1/P2
- **Status:** complete

### Phase 5: Delivery
- [x] Review final diff and test evidence
- [x] Prepare one scoped local commit payload only after full verification/review
- [x] Prepare the files, contract, tests, review, overlap, commit, and remaining-gate report without overstating Production Shadow status
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat HEAD mismatch as a discovery gate | User explicitly requires read-only investigation before any implementation when HEAD differs from `037197e...` |
| Keep product edits Shadow-local by default | Avoid overlap with No-Overnight and Local Paper core worktrees |
| Create `codex/shadow-fill-v3-compat-20260827` only from exact `037197e...` | Supervisor clarified saved-project local `main` was stale and explicitly authorized branch correction in this worktree |
| Treat `.planning` as the only baseline-status exception | Both tracked/index product diffs and non-planning untracked-file checks are empty; planning files are mandated task-local working evidence |
| Aggregate v2/v3 only at a terminal integrity-checked `FILLED` order state | Prevents the same command key from producing mutable prefix Thesis identities while keeping the Journal read-only |
| Preserve legacy v1 single-record activation identity exactly | Required backward-compatibility boundary; v1 multiple-record semantics are not silently widened |
| Give v2/v3 aggregate activations a distinct v2 contract | Allows ordered per-record lineage, aggregate fingerprint/id, total quantity, VWAP, and final-fill timestamp without rewriting v1 digests |
| Collapse only exact duplicate records; reject conflicting sequence reuse | Idempotent retry evidence must not double-count, while normal consecutive partial fills remain valid |
| Finish the active focused red/green loop before latest-main integration | PM explicitly asked not to interrupt regression-first flow; final review/commit must use refreshed `origin/main` including docs-only PR #1 |
| Expand scope narrowly to PostgreSQL read-time fingerprint verification | Independent reviewer proved stored fingerprints were not checked on restart; this is required for the requested tamper-evident contract and is outside No-Overnight/Local Paper writer semantics |
| Rework observer around one immutable Journal snapshot | Independent reviewer demonstrated unsafe acceptance when fills and terminal state came from two different reads |
| Make aggregate builder require explicit terminal completion evidence | Prevent public API callers from activating a nonterminal partial prefix |
| Require Shadow remaining quantity to equal aggregate fill quantity | Prevent a valid 1,500-share aggregate from being evaluated as a separately configured 1,000-share position |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Detached HEAD `a6e096a...` differs from requested baseline `037197e...` | Read-only investigation proved divergent histories; supervisor identified stale saved-project local `main` and authorized exact-baseline branch creation |
| `rg` searched three directories that do not exist | Narrowed the next read to the actual `trading/postgres_journal.py` path |
| `.venv/bin/pytest` is absent in this isolated worktree | Locate the configured/shared read-only project environment before rerunning; do not repeat the missing path |
| Unquoted `requirements*.txt` path probe raised zsh `no matches found` | Stopped that probe; the shared project virtualenv was found directly and is sufficient |
| Two multi-file planning status patches missed exact context | Re-read exact phase/files and split subsequent updates by file |
| One multi-file planning patch missed its expected context | Re-read the active plan and applied smaller exact-context updates |
| Shared virtualenv has neither Black nor Ruff installed | Use repository tests, `compileall`, `git diff --check`, AST/static authority tests, and any project-provided scripts; do not claim Black/Ruff evidence |
| PostgreSQL test discovery included absent root `conftest.py` | Used the actual `tests/conftest.py`; formal fixture requires an explicit disposable `TEST_POSTGRES_DSN` |
