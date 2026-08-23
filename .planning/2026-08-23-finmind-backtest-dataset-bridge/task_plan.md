# FinMind Backtest Dataset Bridge Task Plan

## Goal

Produce a reviewed, implementation-ready plan for the following data-only path:

```text
FinMind history.sqlite3
→ consistent semantic snapshot
→ immutable Backtest Dataset
→ PostgreSQL ATOMIC_BACKTEST_DEFAULT binding
→ Web Atomic Backtest
```

The original planning task is complete. G1, G2, and G3 are approved. G4
PostgreSQL binding and G5 Web Run remain unauthorized. PostgreSQL, Web, Local
Paper, broker, and real-money behavior remain outside the completed G3 slice.

## Current Status

- G0 Contract Review: approved / contract frozen
- G1 Snapshot Reader: approved / gate passed
- G2 Small Materialization: approved / gate passed
- G3 Full Artifact: approved / gate passed
- G4～G5: not authorized

## Review Findings Closure

| Finding | Revised contract | Status |
|---|---|---|
| Stable replay identity | `dataset_id` and `created_at` derive from the included semantic snapshot; existing final directories are fully verified and reused | Addressed in plan |
| Wrong automatic Dataset | PostgreSQL `ATOMIC_BACKTEST_DEFAULT` is mandatory before the selector-less Web flow is deliverable | Addressed in plan |
| Excessive cancellation reads | Progress writes and durable cancellation reads are both monotonic-time throttled | Addressed in plan |
| Volume token drift | New canonical token is `COMMON_LOTS`; legacy `COMMON_LOT` is read compatibly without rewriting old manifests | Addressed in plan |
| Cross-job duplicates | Same canonical identity is deduplicated only after equality checks; conflicting digests fail closed | Addressed in plan |
| Stale fixed counts | Counts are dynamic snapshot outputs; review-time observations are evidence, not acceptance thresholds | Addressed in plan |
| Timestamp identity contradiction | `manifest.created_at` derives from included `last_event_at`; acquisition timestamps are audit-only | Addressed in plan |
| Plan/execute drift | Execute consumes a saved plan and its exact copied SQLite snapshot | Addressed in plan |
| Binding TOCTOU | Run request carries binding revision and Dataset digest preconditions | Addressed in plan |
| Undefined reference metadata | Required `TaiwanStockInfo` raw artifact, digest, mapping, and fail-closed gaps are frozen | Addressed in plan |
| VWAP proxy ambiguity | Exploratory use is allowed only with amount-contract identity in Dataset, Run, Feature evidence, and comparability | Addressed in plan |
| Locator path identity pollution | Plan identity, locators, and operation audit are separate; only canonical identity enters manifest digest | Addressed in plan |
| Binding activation stale overwrite | Caller expected revision plus durable activation replay protects the default binding | Addressed in plan |
| Dataset ID prefix ambiguity | Dataset ID uses the full lowercase 64-hex SHA-256 digest | Addressed in plan |
| Metadata as-of ambiguity | Sorted per-symbol `(symbol, selected_date, name, market)` mapping enters identity | Addressed in plan |
| SQLite whole-file SHA identity pollution | Copied-file SHA is handoff evidence only and is excluded from plan/Dataset/manifest identity | Addressed in plan |
| Volatile exclusion evidence in immutable identity | Move compatibility/exclusion report to separately digested non-identity `selection_audit`; immutable counts derive only from included projection | G1 Review closed |
| Interrupt leaves orphan snapshot | Catch `BaseException` across owned backup→plan publication and delete only the invocation-owned unpaired snapshot | G1 Review closed |
| Backup return boundary loses ownership token | Register the ownership token through a callback inside backup publication's protected region before returning to the CLI | G1 Review closed |

## Implementation Phases

### Phase 0 — Freeze contracts and reserve migration ownership — COMPLETE

- [x] Approve the semantic snapshot identity and deterministic timestamp rules.
- [x] Freeze `snapshot_identity_at = max(included last_event_at)` and exclude
      acquisition `created_at`/`updated_at` from identity.
- [x] Freeze `dataset-finmind-sponsor-sha256-<full 64-hex digest>` with no
      truncation or collision fallback.
- [x] Freeze Plan `identity`／`locators`／`operation_audit` separation; paths and
      host evidence never enter immutable identity.
- [x] Freeze copied SQLite SHA under separate `handoff_evidence`; manifest and
      plan identity never retain it.
- [x] Approve cross-job deduplication/conflict semantics.
- [x] Freeze `COMMON_LOTS` as the new canonical volume enum.
- [x] Freeze the required `TaiwanStockInfo` raw artifact and v1 mapping rules.
- [x] Freeze the sorted per-symbol reference mapping projection; do not use one
      aggregate metadata as-of date as authority.
- [x] Freeze proxy VWAP as exploratory-only evidence with no Qualification.
- [x] Confirm the current migration tip and ownership of untracked
      `011_strategy_set_archives.sql` before allocating the binding migration.
- [x] Keep the FinMind snapshot `CURRENT_SNAPSHOT` and
      `research_eligible=false`.

### Phase 1 — Snapshot reader and dry-run — COMPLETE / G1 PASSED

- [x] Add an online SQLite backup boundary so the downloader may continue.
- [x] Build a read-only semantic snapshot from compatible jobs.
- [x] Select only complete symbols; exclude partial and invalid identities.
- [x] Detect and reconcile cross-job duplicates under the frozen rules.
- [x] Emit dynamic counts, exclusions, source lineage, stable timestamp, and
      source snapshot digest through `--plan`.
- [x] Persist the copied SQLite snapshot and canonical plan artifact, including
      their independent digests.
- [x] Verify exact plan→execute bytes with handoff evidence while allowing a
      separately planned semantic rebuild to retain the same immutable identity.
- [x] Allow locator relocation only after exact content-digest verification;
      manifest saves identity projection, never raw paths/full plan body.
- [x] Keep `--execute` unavailable in G1; the frozen future boundary requires
      `--execute --plan-file` and forbids reopening live acquisition state.
- [x] Add focused snapshot-reader tests.
- [x] Separate volatile selection/exclusion evidence from immutable identity.
- [x] Clean up invocation-owned snapshot/plan artifacts on `BaseException`.
- [x] Register snapshot ownership before backup publication returns to its caller.

### Phase 2 — Small bounded-memory materialization — COMPLETE / G2 PASSED

- [x] Extend the existing HistoricalDatasetCatalog rather than create another
      replay pipeline.
- [x] Stream validated per-symbol inputs through a timestamp/symbol k-way merge.
- [x] Persist canonical volume and amount-proxy contracts.
- [x] Use a deterministic dataset ID and deterministic manifest timestamp.
- [x] Verify same-snapshot reruns return the exact same manifest digest.
- [x] Verify same canonical data with different audit timestamps／SQLite bytes
      keeps source, plan, Dataset, payload, and manifest identity unchanged.
- [x] Add concurrent-first-writer and existing-directory replay tests.
- [x] Reject non-canonical `bars.jsonl` bytes even if payload and manifest
      digests are rewritten consistently.
- [x] Reject unknown or non-canonical FinMind manifest fields/bytes.

### Phase 3 — Full snapshot materialization

Status: COMPLETE / G3 APPROVED / GATE PASSED

- [x] Run `--plan` against the copied source snapshot.
- [x] Record dynamic included/excluded counts and required disk estimate.
- [x] Materialize the complete selected snapshot to a temporary directory.
- [x] Verify payload order, count, checksum, source snapshot digest, and
      manifest digest before atomic publication.
- [x] Do not register or activate an incomplete artifact.

### Phase 4 — PostgreSQL immutable registration and default binding

- [ ] Add the next conflict-free numbered migration for
      `backtest_dataset_bindings`.
- [ ] Add immutable Dataset registration with same-digest replay and
      different-digest conflict behavior.
- [ ] Transactionally bind `ATOMIC_BACKTEST_DEFAULT` only to a verified READY
      Dataset and exact manifest digest.
- [ ] Require expected binding revision, activation idempotency key, actor, and
      change note; first creation uses expected `0` and produces revision `1`.
- [ ] Freeze stale revision as 409, same-target current-revision as no-op, and
      durable same-key replay as revision-neutral.
- [ ] Add PostgreSQL concurrency, replay, conflict, and unavailable tests.
- [ ] Do not fallback to SQLite.

### Phase 5 — Run resolver and Web projection

- [ ] Keep response-loss replay on the original Run Dataset.
- [ ] Keep Challenger Runs on the Baseline Dataset.
- [ ] Resolve new standalone Atomic Runs exclusively through the default
      binding and capability validation.
- [ ] Fail closed for missing, stale, non-READY, or incompatible bindings.
- [ ] Make the Web status render the actual binding, not an independently
      guessed preferred Dataset.
- [ ] Preserve all Dataset identity in the immutable Run snapshot.
- [ ] Require `expected_binding_revision` and `expected_dataset_digest` for new
      standalone Run creation; mismatch returns 409 without creating a Run.
- [ ] Resolve same-key response-loss replay before reading current binding.
- [ ] Preserve amount kind/digest in Run, Feature evidence, and comparability.
- [ ] Add Backtest-runtime `vwap_session_v1` amount-contract preflight; generic
      `OHLCV` alone is insufficient, while Local Paper keeps its own binding.

### Phase 6 — Large-run operational throttling

- [ ] Keep cheap in-process cancellation checks at the existing event cadence.
- [ ] Poll durable Run cancellation state at most once per configured monotonic
      interval, default one second.
- [ ] Write progress at most once per configured interval or meaningful
      progress delta; always flush terminal states.
- [ ] Keep operational timing outside deterministic result/config digests.
- [ ] Prove timestamp-major payloads avoid external sorting.

### Phase 7 — End-to-end acceptance

- [ ] Run focused no-DSN tests.
- [ ] Run disposable PostgreSQL migration/concurrency tests.
- [ ] Materialize one real full semantic snapshot and record its dynamic
      evidence.
- [ ] Register and activate the exact Dataset in PostgreSQL.
- [ ] Confirm the Web displays the bound Dataset identity.
- [ ] Complete one Atomic Run against the bound full Dataset.
- [ ] Verify no FinMind, Shioaji, account, broker order, CA, or trade
      subscription call occurs during backtest.

## Gates

| Gate | Pass condition |
|---|---|
| G0 Contract | All Phase 0 identities, locator exclusions, activation CAS/replay, conflict rules, units, and migration ownership are frozen |
| G1 Snapshot | Saved plan and copied source are deterministic, digest-linked, and reject conflicting or incomplete identities |
| G2 Materialization | Small same-snapshot replay is byte/digest stable and bounded-memory |
| G3 Full Artifact | Full dynamic snapshot is atomically sealed and independently verified |
| G4 PostgreSQL | Immutable registration and default binding pass disposable PostgreSQL tests |
| G5 Web Run | Web resolves the exact binding and completes a full Atomic Run with bounded DB control traffic |

## Explicit Non-goals

- Date-effective full-market or survivorship-free research eligibility.
- Corporate-action adjusted price history.
- Automatic Dataset promotion without a successful full verification.
- Browser Dataset selection or browser-triggered acquisition.
- Local Paper, Shioaji order simulation, broker orders, or real money.
- Refactoring the unrelated Strategy Set revision/archive work.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| Review-time counts changed from 159 to 160 while acquisition continued | 1 | Treat all counts as snapshot output and keep observations out of fixed acceptance gates |
| Initial patch did not match one findings paragraph | 1 | No files changed; split the update into exact smaller patches |
| Combined remediation patch targeted one file twice | 1 | No files changed; consolidated each file into one atomic patch update |
| Sandbox denied `ps` during G3 preflight | 1 | Process enumeration is unnecessary; rely on SQLite online backup and source mtime evidence |
| Reviewer observed 161 symbols after plan remediation | 1 | Keep the observation as evidence only; no gate compares against it |
| Repository search used an unmatched `requirements*.txt` zsh glob | 1 | The search made no changes; subsequent searches use `rg --files` or quoted explicit paths |
| One parallel source read used a misspelled repository path | 1 | Retried once with the verified workspace path; no write occurred |
