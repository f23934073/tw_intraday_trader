# Progress: FinMind Institutional Premarket Strategy MVP

## 2026-08-24

- User requested a plan before implementation.
- Started an isolated planning workspace without changing the repository's
  active-plan pointer or any runtime code.
- Selected `planning-with-files` for durable execution planning and
  `architecture-patterns` for dependency and adapter boundaries.
- Inspected the FinMind normalizer/immutable builder and backtest strategy
  engine. Confirmed the current builder is a fixed-session evidence tool, not
  a daily job, and selected a provider-neutral pre-strategy candidate boundary
  for the plan.
- Inspected CandidatePool, the formal previous-session adapter, shadow
  admission, and local-paper entry points. Identified the need for a distinct
  MVP source/adapter and confirmed that paper execution must stay behind the
  existing exact Strategy Set and RiskGate services.
- Inspected the exact atomic Local Paper evaluation path and scheduler/UI
  indices. Located the gate point before quote preparation and confirmed that
  MVP should begin with a one-shot after-close CLI plus session-pinned artifact,
  not a new background scheduler.
- Inspected the atomic strategy registry and relevant candidate/local-paper
  tests. Decided to reuse an exact existing price Strategy Set and model the
  FinMind list as an outer session-pinned eligibility gate.
- Inspected the reusable FinMind client, existing capture script, after-close
  scheduler, and file layout. Defined a port/adapter daily acquisition design
  and deferred embedded scheduling until a reviewed calendar-aware version.
- Completed the repository-grounded strategy contract and implementation plan.
  It contains six ordered PR slices, exact module seams, anti-lookahead and
  failure semantics, test/acceptance criteria, default-off feature flags, and
  staged rollout from immutable daily artifact to Local Paper evidence.
- No runtime, provider, strategy, database, UI, subscription, broker, or order
  code was modified in this planning turn.

## 2026-08-25 — PR-MVP-PM-001 start

- User authorized implementation. Restored the isolated plan and added Phase 5
  for the first approved slice only.
- Session catchup found the prior plan handoff plus a materially dirty shared
  worktree. Current unrelated market-data, trade-management, root planning,
  and test changes will be preserved; this slice will touch only the
  institutional MVP/config/new CLI/new tests and this isolated plan.
- Success criteria are now explicit: date-parameterized daily artifact,
  reviewed T+1 session, content-addressed immutability/idempotency, quota and
  schema fail-closed behavior, and no CandidatePool/Dashboard/Paper/order side
  effects.
- A combined MVP/calendar read exceeded the output budget. No conclusion was
  accepted from the truncated output; follow-up inspection is split into
  narrow, independently reviewable reads.
- Reconfirmed the existing pure FinMind normalizer and its drift tests. Daily
  acquisition will wrap it instead of modifying the frozen fixed-session
  evidence path.
- Reconfirmed reusable canonical JSON/digest and FinMind HTTP/quota seams. The
  reviewed TWSE calendar can support a fail-closed operational next-session
  adapter, while its lack of TPEx evidence remains explicit in batch metadata.
- Reconfirmed the existing fixed capture's quota, allowlist, redaction,
  staging, and atomic-publish safety properties; the new daily path will keep
  these properties behind reusable adapters.
- Completed read-only convention audits for calendar, artifacts, and focused
  FinMind tests. The implementation contract is now narrow enough to code
  without altering frozen evidence or unrelated dirty-worktree files.
- Implemented the PR-MVP-PM-001 domain, ports, reviewed T+1 calendar method,
  FinMind adapter, application service, atomic content-addressed repository,
  config/policy projection, and explicit one-shot CLI.
- Added focused application, adapter, artifact, CLI, and calendar tests. Initial
  verification passed: compile PASS, focused pytest `21 passed`, and scoped
  `git diff --check` PASS.
- Ruff is not installed in the workspace virtual environment, so lint remains
  `NOT_EXECUTED`; no Ruff pass is claimed.
- Hardened policy permission typing and interruption cleanup. A simulated
  interrupt immediately after atomic link now removes the owned destination;
  the focused interruption test passes.
- Adversarial read-only review found two real pre-handoff gaps: loader semantic
  invariants and pre-provider calendar digest pinning. Both are being corrected
  before broader regression verification.
- Expanded the correction scope to the other review findings: strict exact-pin
  digest validation, semantic replay comparison, raw/count cross-checking,
  start-date-only FinMind request semantics, empty-wide short circuit, and an
  acquisition-wide process lock around quota preflight plus both requests.
- Implemented those corrections and added adversarial tests for recomputed
  semantic tampering, wildcard/uppercase/malformed digests, derived-candidate
  drift under the same source fingerprint, raw/count mismatch, exact quota
  boundary, and empty-wide short circuit.
- Added Asia/Taipei expiry enforcement, candidate-count upper bounds, exact
  provider/calendar semantics, pre-write lineage verification, and no-artifact
  failure tests. After canonicalizing the in-memory batch before pre-write
  verification, compile passes and the focused suite is `33 passed`.
- Final relevant regression including the sealed capture/builder path passed
  `36 tests`. The complete repository suite passed `1465 passed, 49 skipped`
  in 16.14 seconds; no failures were waived or reclassified.
- Independent code, architecture, and adversarial test-gap re-reviews all
  returned APPROVED after the corrections. Final CLI help and scoped whitespace
  checks pass; the no-match trailing-whitespace scan exited 1 as expected.
- PR-MVP-PM-001 is complete. No live FinMind call, price/Kbar, return/PnL,
  holdout, broker, order, CandidatePool, Dashboard, or Local Paper path was
  exercised or changed.

## 2026-08-25 — PR-MVP-PM-001 review corrections

- User authorized correction of the review findings. Added Phase 6 and kept the
  scope to the three reproduced artifact blockers plus the two reported
  operational classification issues.
- Baseline before correction remains green: focused `36 passed`, full
  `1465 passed, 49 skipped`, global Ruff PASS, and scoped diff check PASS.
- No live FinMind/provider call or price, return, PnL, holdout, broker, order,
  CandidatePool, Dashboard, or Local Paper action is authorized in this phase.
- Added one regression test for each reported finding. The expected red run was
  `5 failed, 1 passed`: exact-next, complete candidate projection, reader
  visibility, pre-provider scope, and permanent provider classification all
  reproduced; the CLI permanent-code behavior already passed.
- Implemented the five scoped corrections. The strengthened adversarial matrix
  passes `11 tests`; the complete PR-MVP-PM-001/sealed-replay set passes
  `47 tests`, and scoped Ruff passes.
- Final independent review found one additional payload-envelope edge case:
  HTTP 200 with FinMind payload status 402/408/429/5xx was being treated as a
  permanent invalid response. Added the expected red cases, classified 402 as
  quota and 408/429/5xx as temporary, and added a CLI WAIT/75 regression.
- Final verification passes: exact classification matrix `11 passed`, the six
  PR-MVP-PM-001/sealed-replay files `51 passed`, scoped Ruff and diff checks
  PASS, CLI help PASS, and all repository tests outside the concurrent,
  untracked signal-ledger application test pass `1475 passed, 52 skipped`.
  The unfiltered suite reports two unrelated failures in
  `tests/test_signal_ledger_replay_application.py`; they are preserved and not
  reclassified as PR-MVP-PM-001 failures.
- Three independent final re-reviews returned APPROVED. No live FinMind call,
  price/Kbar, return/PnL, holdout, broker, order, CandidatePool, Dashboard, or
  Local Paper path was exercised or changed.
