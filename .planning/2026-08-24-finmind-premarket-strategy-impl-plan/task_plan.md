# Task Plan: FinMind Institutional Premarket Strategy MVP

## Goal

Implement the approved FinMind post-close institutional MVP in ordered slices,
starting with PR-MVP-PM-001: a date-parameterized, immutable daily Candidate
Batch and explicit one-shot CLI. CandidatePool, Dashboard, Local Paper, formal
PR-008, subscriptions, broker, and order paths remain outside this first slice.

## Scope boundaries

- FinMind institutional data is available after T-day close and may be used no
  earlier than T+1.
- Institutional flow is a candidate prior/filter, not an independent order
  trigger.
- Initial execution target is observation and local paper simulation only.
- Formal PR-008 PIT, coverage, holdout, and production gates remain unchanged.
- No live broker order, subscription expansion, or production strategy binding
  is authorized by this plan.

## Phases

### Phase 1: Current architecture and seams — complete

- [x] Inspect the sealed FinMind MVP artifact and its builder/normalizer.
- [x] Inspect CandidatePool source/admission boundaries.
- [x] Inspect existing entry strategy, paper simulation, scheduler, and UI seams.

### Phase 2: Premarket strategy contract — complete

- [x] Define T/T+1 timing and anti-lookahead rules.
- [x] Define candidate/filter semantics and failure behavior.
- [x] Define minimal configuration and immutable identities.

### Phase 3: Implementation slices — complete

- [x] Specify modules, interfaces, migrations/config, and wiring changes.
- [x] Specify tests and observable acceptance criteria per slice.
- [x] Define rollout gates from observation to paper simulation.

### Phase 4: Deliverable — complete

- [x] Write the final implementation plan with ordered PRs, file targets,
  verification commands, risks, and explicit non-goals.

### Phase 5: PR-MVP-PM-001 implementation — complete

- [x] Reconfirm existing FinMind, calendar, serialization, artifact, and test
  conventions without touching unrelated dirty-worktree changes.
- [x] Add framework-free daily batch domain and provider/repository ports.
- [x] Add FinMind and immutable file adapters plus application service.
- [x] Add explicit `--source-session` one-shot CLI with secret-safe quota
  preflight and reviewed next-session resolution.
- [x] Add unit/integration tests for dates, not-ready, idempotency, conflict,
  digests, permissions, and no-price/no-order boundaries.
- [x] Run focused and relevant regression verification; document what was and
  was not executed.

### Phase 6: PR-MVP-PM-001 review corrections — complete

- [x] Require exact reviewed next-session semantics on every artifact load.
- [x] Prevent readers from observing a publication before its commit completes.
- [x] Require the published candidate count to equal the frozen limit projection.
- [x] Validate calendar scope before provider access and distinguish permanent
  FinMind authorization failures from temporary failures.
- [x] Add adversarial regression tests and rerun focused, lint, and full-suite
  verification without any live provider, price, outcome, broker, or order call.

## Decisions

| Decision | Rationale |
|---|---|
| Plan-only turn | The user explicitly requested an implementation plan first. |
| Use CandidatePool as the integration boundary | It already distinguishes discovery from an entry signal. |
| Keep FinMind adapter outside strategy core | Provider formats belong at the infrastructure edge; strategy logic should consume a provider-neutral prior. |
| Use FinMind as a frozen outer candidate gate | Existing atomic price strategies remain provider-neutral and keep their exact-version lifecycle. |
| Start daily operation with an explicit CLI | Existing scheduler lacks a reviewed holiday/session resolver for this evidence path. |
| Default every runtime flag to off | Observation can ship before quote subscriptions or Local Paper automation are authorized. |
| Keep PR-MVP-PM-001 manual and explicit | Daily source-session input and reviewed calendar resolution are easier to verify before background scheduling. |
| Preserve the existing fixed-session evidence builder | General daily operation gets a new path; immutable r1/r2 evidence is not rewritten. |
| Publish a single canonical content-addressed JSON artifact | Embedding the digest and using atomic no-clobber publish avoids JSON/sidecar inconsistency while preserving revisions. |
| Treat changed bytes for the same session as a retained conflict revision | Evidence remains append-only, while downstream resolution must explicitly pin a digest rather than silently choose latest. |
| Derive a daily effective policy from the sealed r2 rule fields | The r2 rule/limit/permissions remain pinned, while its evidence-specific 2026-08-18 dates and capture identity are not falsely reused as a daily contract. |

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Combined MVP/calendar inspection exceeded the output budget, so its truncated output is not accepted as evidence. | 1 | Split subsequent inspection into narrow file/function reads and rely only on complete outputs. |
| A shell inspection used an unmatched `requirements*.txt` glob under zsh; that command segment did not run. | 1 | Avoid optional globs and query known files or `rg --files` results explicitly. |
| A context-light patch initially inserted the public row-count helper inside the selector body. | 1 | Inspected the exact function boundary and immediately moved the helper after the selector return before running tests. |
| The first post-lock focused run had one CLI fake whose constructor signature did not include the new acquisition lock path. | 1 | Updated the fake boundary; production code had compiled and the other 21 tests passed. |
| Pre-write semantic verification initially received domain `date/datetime` objects while the persisted verifier consumes canonical ISO strings. | 1 | Canonical-roundtrip the batch before pre-write verification and publication; focused suite then passed 33 tests. |
| New adversarial correction suite failed `5 failed, 1 passed` before production changes. | 1 | This is the expected red baseline; implement each narrowly and rerun the same six tests. |
