# Task Plan: VWAP Strategy Failure Attribution

## Goal

Explain why the completed atomic `above_vwap_entry_v1` backtest failed, using its immutable PostgreSQL evidence, then freeze a research-safe next experiment. This phase must not change the completed FinMind Dataset bridge, promote the strategy, start Local Paper, or add broker/real-money execution.

## Scope

- Baseline Run: `run-91ad87981676414da87b928398fa43c9`
- Baseline Dataset: `dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6`
- Strategy: atomic `above_vwap_entry_v1`
- Evidence sources: immutable Run config/snapshot/result chunks, Dataset manifest, binding revision, and Qualification record.

## Non-goals

- No parameter search or strategy optimization before failure attribution is frozen.
- No modification of the G0-G5 FinMind Dataset bridge contracts or artifacts.
- No strategy lifecycle promotion, automated activation, Local Paper, broker, or real-money work.
- No claim that exploratory CURRENT_SNAPSHOT results are formal OOS evidence.

## Phases

### R0: Freeze attribution contract

- [x] Isolate this work from the repository's active shared planning task.
- [x] Freeze baseline Run, Dataset, safety boundaries, and decision outputs.
- [x] Define evidence-first analysis that does not mutate the baseline.
- **Status:** complete

### R1: Verify baseline evidence

- [x] Re-read the durable Run, config, snapshot, result, and qualification rows.
- [x] Reconfirm relevant digests and the exact execution/cost policy.
- [x] Confirm no provider/broker dependency is required for attribution.
- **Status:** complete

### R2: Decompose failure

- [x] Separate gross strategy edge from commission, tax, and slippage drag.
- [x] Attribute performance by year, symbol, entry time, holding time, and trade-day concentration.
- [x] Measure signal-to-fill conversion, rejection causes, cash/exposure saturation, and deterministic ordering effects.
- [x] Distinguish strategy semantics from engine/data limitations.
- **Status:** complete

### R3: Freeze causal findings

- [x] Rank supported causes and explicitly reject unsupported explanations.
- [x] Record Dataset limitations separately from algorithmic/execution causes.
- [x] Set the current strategy to `HOLD / NOT ELIGIBLE` pending one
  cash-admission-neutral control.
- **Status:** complete

### R4: Define the next research Gate

- [x] Select cash-admission-neutral replay as the first controlled hypothesis
  without changing the baseline Version.
- [x] Freeze control variables, family/attempt boundaries, costs, and acceptance thresholds.
- [x] Produce an implementation-ready research plan without running or promoting it.
- **Status:** complete

### R4.1: Remediate R5/R6 pre-implementation Review

- [x] Rename R5 to a cash-admission-neutral sensitivity control and remove the
  unsupported claim of fully allocation-neutral sizing.
- [x] Freeze a dedicated R5 mutation, immutable preflight artifact, lineage, and
  post-Run zero-rejection acceptance contract.
- [x] Keep the existing server-owned 20-attempt Bonferroni family policy.
- [x] Define a sealed seven-slot R6 matrix registration consumed under the
  authoritative family lock.
- [x] Add executable SQL templates for R5 identity, signal coverage, rejection,
  and family-policy verification.
- **Status:** complete

### R4.2: Close authoritative-control and acceptance gaps

- [x] Make R5 `C/f` server-derived and deterministic; remove caller-controlled
  sizing parameters.
- [x] Freeze one sealed authoritative control per baseline＋contract revision,
  with durable replay, head CAS, and Review-gated revision semantics.
- [x] Require server postflight before publishing any control performance.
- [x] Convert the reviewer SQL into a fail-closed, multiplicity-aware Gate over
  one repeatable-read snapshot.
- [x] Rebuild the interactive report with a visible superseded notice and the
  corrected cash-admission-neutral terminology.
- **Status:** complete / ready for short re-review

### R5: Implement authoritative cash-admission control

- [x] Add pure Decimal sizing/preflight/postflight domain contracts.
- [x] Add PostgreSQL migration for head, sealed registration, operations, and
  postflight evidence.
- [x] Implement repository transactions for replay, head CAS, one authoritative
  Run, and terminal postflight publication.
- [x] Add application use cases and strict HTTP boundary without exposing
  caller-controlled `C/f`.
- [x] Enforce result redaction and block comparison/export/Qualification/R6
  until postflight acceptance.
- [x] Add unit, API, tamper, concurrency, and PostgreSQL regression coverage.
- [x] Run focused, no-DSN full, PostgreSQL focused/full where available,
  compilation, JavaScript, migration, and whitespace checks.
- [x] Bind accepted postflight evidence to current ENTRY order status and actual
  fill multiplicity on every performance read.
- [x] Align the formal acceptance SQL with Migration 014 and add PostgreSQL
  positive/negative SQL acceptance regressions.
- [x] Recompute baseline semantic result identity in the preflight CLI before
  scanning the immutable Dataset.
- [x] Re-run focused, no-DSN full, disposable PostgreSQL full, compilation,
  CLI, and whitespace verification after remediation.
- [x] Restrict formal rejection-reason counts to non-FILLED orders and verify a
  real engine-shaped FILLED order with reason/embedded fill passes PostgreSQL.
- **Status:** SQL reason remediation complete / ready for independent re-review

### R5.1: Execute the authorized authoritative control

- [ ] Verify application PostgreSQL, Migration 014, immutable baseline Run,
  Dataset registration/binding, and local Dataset artifact without providers.
- [ ] Create and save the canonical provider-free preflight for the approved
  baseline.
- [ ] Create or replay the sole authoritative R5 control using the frozen
  operation identity; record derived `C/f` and Run identity.
- [ ] Wait for the worker terminal state without invoking providers, Local
  Paper, broker, or R6.
- [ ] Verify server postflight, formal acceptance SQL, result/digest identity,
  zero provider/broker calls, and the R5 decision matrix outcome.
- **Status:** explicitly authorized / preflight in progress

## Gate

This phase passes only when the failure attribution is reproducible from immutable evidence and the next experiment cannot reuse the same evidence as both hypothesis-generation and validation. Passing this phase authorizes research implementation only; it does not authorize Local Paper or broker execution.

## Final status

```text
R0-R4: COMPLETE
Failure Attribution: COMPLETE
Gate R5 design: APPROVED / CONTRACT FROZEN
Gate R5 implementation: REMEDIATION COMPLETE / READY FOR INDEPENDENT RE-REVIEW
Gate R5 execution: AUTHORIZED / IN PROGRESS
Gate R6 contract remediation: ACCEPTED BY PRIOR REVIEW
Gate R6 execution: NOT AUTHORIZED
```

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Qualification query assumed `reasons_json`, but the table uses a different schema | 1 | Inspect migration 008/009/010 and query the canonical request/evidence columns instead. |
| Source inspection targeted nonexistent `backtest/execution.py` | 1 | `rg` located execution pricing in `backtest/engine.py`; continue from the actual owner. |
| Strategy Version lookup assumed nonexistent `strategy_catalog.strategy_versions` | 1 | Locate the authoritative catalog migration/table before querying parameters. |
| Portable artifact rejected waterfall `series` | 1 | Remove the redundant unsupported field and retain explicit x/y encodings. |
| Portable artifact table sorted by undeclared `priority` | 1 | Declare the existing audit field as a table column. |
| `horizontalBar` used visual rather than canonical encoding axes | 1 | Keep category on x and numeric measure on y; the renderer owns orientation. |
| Sandboxed Chromium exited before report QA completed | 1 | Re-run the identical validated builder with local browser permission; desktop/narrow/source-interaction verification passed. |
| Technical-report specification was first resolved from the wrong skill-relative directory | 1 | Locate and read `build-report/specifications/technical-report.md` before editing the artifact. |
| PostgreSQL 17 `psql` ignored the argument to `\quit 3`, so a rejected Gate still exited 0 | 1 | Use an explicit SQL assertion under `ON_ERROR_STOP`; the negative probe now rolls back and exits 3. |
| Final multi-file planning patch used stale findings context | 1 | Split the status/evidence update into exact per-file patches; product code and tests were unaffected. |
| R5 diagnostic script could not import repository modules when executed from `.planning` | 1 | Insert the resolved project root into `sys.path` before importing application modules; no DB or Dataset scan had started. |
