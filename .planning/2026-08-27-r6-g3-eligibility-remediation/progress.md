# Progress

## 2026-08-27 diagnosis

- Confirmed two deterministic full-scan failures and a third automatic rerun.
- Confirmed the current run is active but cannot be considered healthy progress.
- Captured a read-only prefix snapshot of the active eligibility rows.
- Measured a `0.789205541` eligibility ratio; exact `12:45` absence accounts for
  nearly all exclusions, while exact `13:30` absence is rare.
- Identified the root cause as an overly strict exact-anchor assumption against
  sparse trade-derived minute bars.
- Drafted the source-derived reserve-time Amendment A2 plan.
- No product code, database row, Gate state, process, or launchd job was changed.

## 2026-08-27 authorized containment

- Unloaded `com.tw-intraday-trader.r6-g3-preflight`; PID 1978 is no longer
  present and `launchd` no longer has the job loaded.
- Preserved the 488 MB interrupted staging tree at
  `data/backtest/atomic_entry_benchmark/interrupted/r6-g3-ee922f94872044869d9040dac84262ab-ended-20260827T085739+0800.tmp`.
- Added an atomic `O_EXCL` worker claim. A launchd re-invocation for the same
  run root now returns before credentials, PostgreSQL, or Dataset scanning and
  cannot overwrite the first worker's terminal evidence.
- Supervisor regression: `11 passed`.
- Migration 018, matrix revision 3, PostgreSQL state, and formal G3 execution
  remain untouched.

## 2026-08-27 A2 implementation candidate

- Added revisioned eligibility row/manifest and preflight-root schemas. Revision
  2 remains readable; revision 3 selects the last observed same-symbol Kbar at
  or before `12:45` as the reserve.
- The reserve Kbar can fill a prior signal but is never evaluated as a signal.
  The exact `13:30` terminal exit remains mandatory.
- Added a source-only audit service and CLI. It binds Dataset EOF/count/SHA,
  A2 semantics, total/yearly eligibility counts, canonical ratios, and an
  immutable audit digest without running any strategy or writing PostgreSQL.
- Added `effective_status=INTERRUPTED` projection for stale RUNNING evidence
  after an unloaded job; raw historical status remains unchanged.
- Focused verification: `48 passed, 21 skipped` for the atomic benchmark scope;
  the skipped cases require PostgreSQL. Latest pure A2/supervisor subset:
  `32 passed`.
- Created `architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md` as the
  independent Review candidate.
- No Migration 018 exists, no matrix revision 3 was created, no source-only
  full scan was started, and no formal preflight/attempt was written.

## 2026-08-27 A2 independent Review remediation

- First review found unbound durable scope and duplicated source-anchor
  accumulation; both were fixed before execution.
- Audit v2 now binds family/matrix/baseline/build/Dataset state, head `0`,
  attempts `0`, candidate protocol, and audit implementation identities.
- Audit and formal preflight share `_SessionEligibilityAccumulator`.
- Added sorted symbol projections and exact total verification.
- Focused re-review: `35 passed`.
- Broad atomic benchmark no-DSN re-review: `85 passed, 21 skipped`.
- Python compilation, CLI help, and scoped `git diff --check`: passed.
- Disposition: `A2 APPROVED / CONTRACT FROZEN`; full source-only audit may run
  exactly once. Migration 018 remains prohibited unless ratio is at least 0.95.

## 2026-08-27 source-only full audit

- Dry-run revalidated active matrix revision `2`, family head `0`, attempts `0`,
  and the registered 28,325,340-bar Dataset.
- Executed the source-only audit exactly once; no automatic retry occurred.
- Source EOF/count/SHA and canonical artifact verification passed.
- Coverage is `0.995893643087254413` (`131,691 / 132,234`), above `0.95`.
- Artifact digest:
  `2e4f8590d0de3f963e4d41bc17d87fd859809053f9f2206015ba69d46863131d`.
- Audit breakdown: missing reserve `17`, missing earlier signal observation `43`,
  missing exact terminal exit `520`; exclusions may overlap.
- Formal attempts remain `0`. Migration 018 design/testing is now permitted.

## 2026-08-27 Migration 018

- Added forward-only `018_r6_dynamic_entry_reserve.sql` with revision-3 schema
  admission and a durable eligibility-audit authority table.
- The migration is schema-only; it does not create or activate matrix revision
  3 and does not register an audit or preflight.
- Pure/focused verification: `31 passed, 1 skipped` before PostgreSQL.
- Disposable PostgreSQL 17 final run: `26 passed`; an earlier Docker-disk-full
  run was discarded and not counted as evidence.
- Full no-DSN suite: `1735 passed, 88 skipped`.
- Production dry-run revalidated the exact audit and state, then Migration 018
  applied once.
- Read-only post-check: 18 migrations, active revision `2`, head/attempts `0/0`,
  release `NOT_READY`, and zero revision-3 matrices/preflights/audit rows.
