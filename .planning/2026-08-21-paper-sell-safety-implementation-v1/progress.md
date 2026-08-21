# Progress: Paper Sell Safety and Recoverable Orders

## 2026-08-21

- Read `planning-with-files`, `karpathy-guidelines`, and
  `architecture-patterns` completely.
- Read the referenced Codex task and recovered the current review context.
- Inspected the dirty-worktree summary and preserved all unrelated changes.
- Created this isolated plan instead of replacing the root Freshness
  Calibration planning files.
- Completed the first symbol/state search and memory quick pass.
- Traced controller, simulator, RiskGate, command facade, Journal projection,
  runtime composition, and existing focused tests.
- Next: inspect the reusable lifecycle contract and run the focused baseline;
  then write failing acceptance tests before production edits.
- First baseline invocation failed before collection because `pytest` was not on
  `PATH`; no tests or product code ran.
- Confirmed `.venv/bin/python` exists and `pyproject.toml` declares pytest.
- Focused baseline passed: `57 passed in 0.48s`.
- Added the six direct-safety acceptance probes plus the singleton race test.
  Expected red result: 7 failed and 21 passed; every failure maps to an approved
  blocker, with no unexpected regression.
- Phase 1 complete. Phase 2 direct safety fixes started.
- Six direct safety fixes completed. Added simulator-level ownership and stale
  book integration tests in addition to controller probes.
- Batch 1 focused verification passed: `74 passed in 0.70s`.
- Phase 3 recoverable order lifecycle started.
- Added four batch-2 acceptance tests. Expected red result: 4 failed, covering
  missing PENDING transition, lifecycle policy parameters, partial fill,
  timeout/retry/expiry/alerts, and same-day restart restoration.
- Implemented Batch 2 core lifecycle and durable restore path. The lifecycle
  acceptance suite now passes: `4 passed`.
- Expanded focused suite after Batch 2 core: `78 passed in 0.80s`.
- Added controller-side bounded retry for cancelled/expired automated exits;
  continuous-strategy suite passes: `18 passed`.
- `python -m compileall -q simulation trading runtime dashboard market_data`
  passes.
- Next: expose retry/recovery alerts through API/dashboard, then add retry
  exhaustion, cross-day, missing-ack recovery, and adapter contract tests.
- Added retry API/dashboard actions and surfaced the newest lifecycle alert in
  simulation health and the operator preview.
- Added zero-volume, partial-cancel, retry-exhaustion, cross-day opening-equity,
  and retry-route tests. Lifecycle plus dashboard API verification passes:
  `19 passed`.
- Added missing-command-acknowledgement fail-closed restart coverage; the
  recoverable lifecycle suite now passes `9 passed` including actual local
  command-facade stale-book SELL rejection.
- Added in-memory/PostgreSQL session-lookup contracts and Shioaji best-level
  volume normalization assertions. Combined adapter/lifecycle/dashboard suite:
  `43 passed` before the final freshness integration case.
- Final review found and fixed two recovery concerns: trading-day baselines now
  have their own durable Journal record (including opening equity, unrealized
  PnL policy, and opening realized PnL), and asynchronous Journal callbacks now
  run after releasing the simulation lock.
- Added a cross-day then same-day runtime-restart baseline test. Updated focused
  runtime/command/strategy/dashboard suite passes: `39 passed`.
- Added a deterministic callback lock-order regression test; the recoverable
  lifecycle suite now passes `11 passed`.
- Dashboard JavaScript syntax check, Python compileall, and `git diff --check`
  all pass after the operator/recovery changes.
- Expanded safety/recovery/dashboard focused regression passes: `119 passed`.
- Full-suite collection is currently blocked by an unrelated pre-existing
  trade-management fixture: `tests/test_trade_management_live_capture.py`
  raises `paper fill record identity is not canonical` at module import.
- Full suite excluding that one collection blocker reached `1067 passed, 4
  skipped, 13 failed`. Ten failures share the partial-fill record-ID
  compatibility issue, two are expected test-contract updates for strategy
  ownership/order-state journaling, and one is an unrelated backtest migration
  expectation for existing `005_atomic_strategy_platform.sql`.
- Restored downstream thesis compatibility while retaining partial-fill
  uniqueness: first fill preserves legacy idempotency, later deltas are
  sequence-suffixed, and fill timestamps are monotonic. The affected
  order-application/thesis/operational/live-capture/lifecycle set passes:
  `42 passed`.
- Full repository regression now reaches `1094 passed, 7 skipped, 2 failed`.
  Both remaining failures are unrelated dirty-worktree atomic-backtest work:
  one fixture produces no ENTRY decision, and one migration expectation omits
  the existing `005_atomic_strategy_platform.sql` file.
- Added same-day restart verification for realized PnL against the persisted
  opening baseline, plus static UI contracts for active states, retry, and
  visible lifecycle alerts.
- Final task-focused regression passes: `152 passed in 0.79s`. Dashboard JS
  syntax and `git diff --check` remain clean.
- Updated README to match the checkpointed stable-session recovery contract,
  partial-fill lifecycle, quote-cache limitation, PostgreSQL requirement for
  cross-process durability, and manual controller restart boundary.
- Final reassessment: the seven code-level blocking findings are addressed, but
  genuinely unattended operation remains `NO-GO` until durable PostgreSQL is
  mandatory/verified, controller enablement has an approved restart policy,
  and lifecycle alerts reach an external monitored channel.
- Phase 5 started after user approval. Added Phase 6 backlog items for durable
  controller enablement, mandatory PostgreSQL, and external alert delivery;
  none of those unattended changes are authorized in Phase 5.
- Phase 5 success is frozen as isolated failure attribution plus six rerunnable
  operator UAT cases, including real PostgreSQL restart recovery.
- Live rerun of the two prior failures now has `4 passed, 1 failed`: concurrent
  atomic-strategy changes fixed the missing ENTRY case. Only the migration-list
  expectation remains (`005_atomic_strategy_platform.sql` exists but the test
  expects through `004`).
- PostgreSQL environment probe confirms `TEST_POSTGRES_DSN` is absent. The
  command's final readiness check used zsh's reserved `status` variable; this
  was a probe-script error after pytest, not a product/test failure.
- Added the Phase 5 runner, real PostgreSQL three-generation restart test, and
  README invocation. Without a DSN, the test skips and the runner exits 2.
- Pulled official `postgres:16-alpine` and started the explicitly named
  disposable container `tw-intraday-phase5-pg-01a02373`.
- Real Phase 5 operator UAT passes all frozen targets: `7 passed in 0.33s`.
- Final task-focused regression passes: `152 passed, 1 skipped in 0.86s`; the
  skip is the DSN-gated PostgreSQL test, which passed separately against the
  disposable real database.
- Latest full repository regression is green after concurrent atomic-backtest
  fixes: `1100 passed, 10 skipped in 6.15s`.
- Phase 5 is complete. Repository test health is green; merge packaging remains
  pending because this is still a large mixed, uncommitted dirty worktree.
- Stopped and auto-removed disposable container
  `tw-intraday-phase5-pg-01a02373`; Docker inspection confirms no container with
  that name remains. The downloaded PostgreSQL image stays in the local cache.
