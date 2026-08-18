# Task Plan: Project Foundation Optimization implementation plan

## Goal

Continue the approved project-foundation plan through its independently verifiable slices. Preserve API compatibility and the market-data-only/local-paper boundary; do not add broker orders, CA activation, or real-money behavior.

## Current Phase

Phase 19 — final foundation verification (complete)

## Phases

### Phase 1: Context restoration and repository baseline

- [x] Restore existing root and isolated planning context.
- [x] Inspect the shared worktree without modifying concurrent product changes.
- [x] Confirm the current local-paper, streaming, Momentum, and execution-plan boundaries.
- **Status:** complete

### Phase 2: Cross-plan dependency and scope reconciliation

- [x] Map the requested optimization points to current code and existing architecture plans.
- [x] Resolve overlap with the active Limit-Up Momentum plan and the execution-layer plan.
- [x] Freeze scope, non-goals, storage assumptions, and implementation order.
- **Status:** complete

### Phase 3: Implementation-plan authoring

- [x] Write the standalone plan under `architecture/`.
- [x] Define target boundaries, ports, data contracts, phases, review gates, and file map.
- [x] Define acceptance criteria, observability, migration, rollback, and CI strategy.
- **Status:** complete

### Phase 4: Verification and handoff

- [x] Cross-check every requested optimization point against the plan.
- [x] Verify existing Momentum and product files were not modified.
- [x] Run Markdown and whitespace checks and deliver the plan for review.
- **Status:** complete

### Phase 5: Implement approved Phase 0 baseline and CI

- [x] Confirm available local test/tooling runtimes without mutating unrelated environment state.
- [x] Add no-credential GitHub Actions CI for Python tests, compilation, JavaScript parse, and whitespace checks.
- [x] Add explicit, default-off foundation configuration/contract-version freeze without changing runtime behavior.
- [x] Add focused checks for the new configuration and CI workflow assumptions.
- **Status:** complete

### Phase 6: Phase 0 verification and handoff

- [x] Run the full local regression suite using an existing compatible environment when available.
- [x] Run focused configuration/CI static checks and whitespace verification.
- [x] Verify no Journal, Replay, database, RiskGate, broker order, or real-money code was added.
- **Status:** complete

### Phase 7: Continue approved foundation implementation

- [x] Implement Phase 1 composition root and ports without API/payload changes.
- [x] Verify MockProvider/in-memory dashboard startup and API fixture compatibility.
- [x] Continue to the next plan slice only after its local verification passes; keep all live/provider/broker capabilities disabled.
- **Status:** complete

### Phase 8: Phase 2 ordered ingestion and DataHealth integration

- [x] Audit the concurrent normalized event/health/ingestion modules against Phase 2 invariants.
- [x] Reconcile the existing canonical ingest path as observe-only, preserving current snapshot and local-paper projections.
- [x] Preserve the existing UI-only availability display without misrepresenting it as canonical health projection wiring.
- [x] Verify duplicate, out-of-order, session, overflow, Replay, and legacy compatibility behavior.
- **Status:** complete

### Phase 9: Phase 3 journal contract and restart-recovery foundation

- [x] Introduce one shared, framework-free Journal record/append/idempotency contract.
- [x] Add an in-memory adapter and an optional PostgreSQL adapter behind that port; keep persistence disabled by default.
- [x] Add forward-only schema migration artifacts and DB-backed contract tests that require an explicit test DSN.
- [x] Preserve current local-paper process-memory behavior while demonstrating observation-only Journal replay parity for filled orders.
- **Status:** complete

### Phase 10: Phase 5 RiskGate foundation

- [x] Verify the shared immutable Replay fixture runs ten times with one digest.
- [x] Add framework-free, versioned RiskGate contracts and deterministic reason codes.
- [x] Keep strategy-origin commands disabled by default and leave existing routes on their compatibility path.
- [x] Verify pure risk decisions and no API/simulation regressions before any command-path migration.
- **Status:** complete

### Phase 11: Phase 5 command application foundation

- [x] Build a single application service that evaluates RiskGate and appends a command decision before invoking an injected handler.
- [x] Fail closed on an idempotent command record until recovery can prove whether the handler ran.
- [x] Validate command ordering, blocked strategy behavior, handler-failure evidence, legacy local-paper adapter behavior, and no direct Dashboard-route migration.
- **Status:** complete

### Phase 12: Local-paper outcome evidence and recovery parity

- [x] Record a normalized local-paper fill only after the legacy simulator acknowledges a `FILLED` result.
- [x] Rebuild the Decimal local-paper projection from that Journal evidence and verify cash/position parity.
- [x] Return recovery-required if post-handler outcome evidence cannot be recorded; never resend the command.
- **Status:** complete

### Phase 13: Typed DataHealth-to-Risk context adapter

- [x] Build a framework-free adapter from the existing canonical DataHealth read projection to the RiskGate input.
- [x] Verify every non-healthy DataHealth state blocks a new command without changing current Dashboard routes.
- [x] Keep cash, position, market and book data explicit caller-owned inputs; do not fabricate provider state.
- **Status:** complete

### Phase 14: Complete risk-decision evidence

- [x] Persist an immutable, canonical form of every RiskSnapshot alongside each journaled command decision.
- [x] Verify the evidence preserves Decimal values without silently converting money through float.
- [x] Keep the current Dashboard route and legacy simulator behavior unchanged.
- **Status:** complete

### Phase 15: Local-paper checkpoint writer

- [x] Add an explicit full-replay checkpoint writer for a Journal-derived local-paper projection.
- [x] Verify the saved digest supports default fail-closed recovery and detects a later corrupted checkpoint.
- [x] Keep checkpoint writing outside Dashboard request handling and persistence disabled by default.
- **Status:** complete

### Phase 16: Provider qualification read-only audit

- [x] Inspect the existing qualification artifact contracts and acceptance reports without starting a provider connection.
- [x] Identify and implement an offline integrity/shape validator that does not duplicate concurrent capture/normalization work.
- [x] Keep Shioaji capture, broker order APIs, and Dashboard provider behavior untouched.
- **Status:** complete

### Phase 17: Offline capture rehydration

- [x] Parse one validated capture artifact back into typed Quote and Tick+BidAsk captures.
- [x] Verify a reviewed parity criteria set can be evaluated without an SDK, network call, or wall-clock dependency.
- [x] Retain `INCOMPLETE` unless the existing criteria/evidence rules pass; do not select a provider mode.
- **Status:** complete

### Phase 18: Command recovery classification

- [x] Add a read-only classifier for Journal command/failure/fill evidence.
- [x] Correlate application-created local-paper fill evidence to its command without changing the legacy observation-only converter.
- [x] Keep ambiguous or incomplete evidence fail-closed as recovery-required; do not retry a side effect.
- **Status:** complete

### Phase 19: Final foundation verification

- [x] Run the full regression, compilation, Dashboard JavaScript, whitespace, and package-content checks after all new modules.
- [x] Preserve concurrent worktree changes and remove only generated build artifacts from verification.
- [x] Record the remaining live-provider and Dashboard-command migration gates without treating them as complete.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|---|---|
| Plan only; no product implementation | The user explicitly requested an implementation plan before implementation. |
| Use an isolated planning directory | The repository already has an active Momentum plan and a dirty shared worktree. |
| Do not switch `.planning/.active_plan` | Avoid disturbing the active Momentum workflow. |
| Keep one modular monolith with ports/adapters | The repository is still compact; service decomposition would add operational cost without solving the current data-integrity gaps. |
| Reuse existing execution and Momentum contracts | Avoid a second Event, DataHealth, Replay, Risk, or subscription architecture. |
| Preserve market-data-only/local-paper boundaries | No Shioaji broker order or real-money capability is authorized. |
| Start only Phase 0 after user `ok` | The approval follows the plan handoff; later phases remain blocked pending their gates. |
| Adopt D1-D9 plan defaults for Phase 0 | The user did not override the published defaults; the implementation keeps them as explicit, default-off metadata only. |
| Continue beyond Phase 0 | The user explicitly instructed the work to keep going; apply the approved foundation plan slice-by-slice with verification, while preserving all safety boundaries. |
| Stop before live qualification or Dashboard command cutover | The remaining work requires market-hours evidence, reviewed provider criteria, and a canonical runtime RiskSnapshot/session owner; these cannot be inferred from local unit tests. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Active Python environment has no `pytest` | 1 | Treat the prior verified `.venv` baseline as historical evidence and require CI/dev bootstrap in the plan; do not install dependencies during planning. |
| `test_runtime_composition` missed `datetime` after the Journal contract migration | 1 | Restore the test-only import; rerun focused Journal/composition regression. |
| PostgreSQL-only test process exited 5 when every test skipped without `TEST_POSTGRES_DSN` | 1 | Keep the explicit-skip guard and verify it through the full local suite; CI supplies an isolated PostgreSQL service and DSN. |
| `.venv` wheel build could not import `setuptools.build_meta` | 1 | Do not mutate the existing environment; use a system Python build backend for a no-dependency wheel/package-data check. |
| System-Python wheel verification did not locate the generated wheel | 1 | Wheel build itself succeeded; use a fixed temporary output directory and a correctly escaped filename search before inspecting package data. |
| Sandbox denied the first read-only Docker daemon check | 1 | Re-ran the check with scoped approval; local Docker is available, but no project or user database was started. |
| Journal progress patch targeted the root task plan | 1 | No file changed; update only the isolated foundation plan to avoid touching the unrelated active root plan. |
| Local-paper parity test misplaced the corrupted-checkpoint assertions | 1 | Move the assertions back into the recovery test; rerun focused parity and full regression tests. |
| Adapter test expected a filled 2330 buy at an unmarketable limit price | 1 | Use the existing 3231/106.00 marketable MockProvider fixture for adapter parity verification. |
| Generated `build/` cleanup was blocked by a temporary Codex usage limit | 1 | After the quota recovered, remove only the verified agent-created build directory before continuing. |
| Manifest inspection unintentionally attempted deep observation rehydration | 1 | Split bounded metadata inspection from strict offline replay loading; preserve both contracts with focused tests. |
