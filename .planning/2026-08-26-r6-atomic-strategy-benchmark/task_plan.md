# Task Plan: R6 Atomic Strategy Benchmark

## Goal

Fairly compare the seven remaining approved atomic ENTRY strategies using one
immutable Dataset, one-lot signal-level replay, identical execution/exit/cost
semantics, server-owned multiple-testing governance, and no lifecycle or
execution mutation.

## Safety boundary

- Research and immutable evidence only.
- No Strategy lifecycle promotion or activation.
- No Local Paper, provider, broker, CA, trade subscription, or real-money path.
- Do not execute the seven formal attempts until G0 independently freezes the
  exact Version/parameter/protocol contract.
- Preserve all unrelated shared-worktree changes and do not modify
  `.planning/.active_plan`.

## Phases

### R6.0: Restore authoritative context

- [x] Reconcile R5 v2 terminal evidence and the superseded R6 v1 design.
- [x] Inventory the seven executable ENTRY Templates, current exact Versions,
  parameters, implementation/specification identities, and required features.
- [x] Reconcile current PostgreSQL experiment-family and Strategy Catalog
  schemas without mutation.
- **Status:** completed

### R6.G0: Freeze benchmark contract

- [x] Freeze seven ordered hypothesis slots before reading any new results.
- [x] Freeze exact Version/parameter/feature identities for every slot,
  including an admission contract for four missing Version IDs.
- [x] Freeze common Dataset, signal extraction, one-lot entry, session-close
  exit, slippage, commission, tax, missing-data, and canonical artifact rules.
- [x] Freeze server-owned family identity, attempt sequence, alpha correction,
  outcome metrics, eligibility thresholds, and tie/multiple-testing handling.
- [x] Define bounded-memory execution, idempotency, cancellation, tamper,
  response-loss, and read-only acceptance contracts.
- [x] Submit G0 candidate for independent Review before product implementation or formal
  replay execution.
- [x] Remove the circular identity graph and freeze exact non-circular
  projections from protocol core through matrix registration and artifacts.
- [x] Freeze same-attempt technical retry/CAS semantics without adding an
  attempt sequence or resetting the multiple-testing budget.
- [x] Remove wall-clock audit fields from immutable artifact identity.
- [x] Extend the 7/7 publication barrier to every product artifact, CLI, log,
  exception, export, comparison, and report read path.
- [x] Add generation-4 `RUNNING/CANCELLING` terminal transitions with exact
  generation and error-code guards.
- [x] Freeze the public bundle member tree, path/order/chunk rules, canonical
  payload byte stream, and reproducible payload SHA-256.
- **Status:** passed historical revision / current execution superseded by the
  frozen A1 contract

### R6.G0-A1: Common cutoff and incomplete-signal amendment

- [x] Reconcile the formal G3 failure with all seven exact Version entry
  windows; confirm the latest end is already exclusive `12:45`.
- [x] Freeze the common Dataset-only symbol/session eligibility rule using
  exact `12:45` entry-reserve and `13:30` terminal-exit anchors.
- [x] Freeze common-mask evidence, exclusion reasons, 95% coverage floor,
  canonical artifact projections, and amended identity digests.
- [x] Define same-family matrix revision 2, zero-attempt CAS, Migration 017,
  and regression requirements without resetting the attempt budget.
- [x] Freeze excluded-session source/reference/runtime state semantics.
- [x] Freeze the exact 31-member G3 root, immutable PostgreSQL preflight
  registration, response-loss replay, and accepted-preflight G4 barrier.
- [x] Freeze additive matrix-protocol companion history and composite
  cross-revision matrix/protocol/slot/attempt/preflight/release referential
  integrity without rewriting revision-1 rows.
- [x] Freeze both exact matrix unique targets: `(matrix_id, family_id)` for
  operation/outbox/slot relationships and the matrix/family/revision triple for
  protocol/release/preflight relationships, with cross-family substitution
  regressions.
- [x] Separate Migration 017 from matrix activation and restrict the latter's
  family mutation to one `active_matrix_revision: 1 -> 2` CAS plus operational
  `updated_at`, with every other family field preserved.
- [x] Freeze exact database revision checks plus non-null matrix-bound
  operation/outbox, exact outbox-operation, and exact transition/operation/
  outbox-to-attempt aggregate foreign keys.
- [x] Freeze one family-row lock boundary across Migration 017, activation,
  preflight registration, and attempt admission.
- [x] Freeze build-binding v2 with exact algorithm, preflight, and ordered
  Migration 016/017 source manifests so runtime code cannot self-declare its
  implementation identity.
- [x] Freeze exact eligibility-anchor timestamp serialization and canonical
  Dataset source-row digest bytes, excluding the JSONL LF.
- [x] Obtain independent G0 Amendment A1 Review before changing product code,
  creating matrix revision 2, or rerunning G3.
- **Status:** passed / contract frozen; implementation explicitly authorized
  and in progress

### R6.G1: Version admission plus pure domain and artifact implementation

- [x] Revalidate and idempotently publish the four missing immutable Strategy
  Versions at lifecycle `PUBLISHED` only.
- [x] Record each Version ID, publish event, lifecycle sequence/projection,
  actor, and durable operation result for independent G1 Review.
- [x] Implement approved framework-free identity, signal extraction, matching,
  one-lot economic, metric, disposition, and canonical artifact primitives.
- [x] Add golden parity, identity, missing-data, canonical-byte, and
  bounded-memory regressions.
- [x] Submit the complete G1 candidate for independent Review before opening
  PostgreSQL family/matrix work.
- [x] Remediate semantic bundle re-verification, strict evidence booleans,
  durable Version/event/operation rebuild, and quantized daily compounding.
- [x] Re-submit the remediated G1 candidate for independent Review.
- [x] Verify every physical bundle chunk's actual row count and boundary
  sequences against its descriptor.
- [x] Use one canonical 18-decimal drawdown for both disposition comparison
  and summary serialization.
- [x] Re-submit the second remediated G1 candidate for independent Review.
- **Status:** complete / independently approved and Formal Gate passed

### R6.G2: PostgreSQL family and application implementation

- [x] Persist the sealed seven-slot family, monotonic attempts, immutable
  operation results, and fail-closed result visibility.
- [x] Add concurrency, idempotency, tamper, cancellation, and security tests.
- [x] Keep formal Dataset preflight and performance payload publication outside
  the G2 application boundary.
- [x] Rebuild transition response-loss results from the immutable request plus
  exact operation outbox, rejecting synchronized result/outbox substitution.
- [x] Enforce the frozen non-observational diagnostic-code allowlist at both
  PostgreSQL write and application read boundaries.
- [x] Rebuild the complete G1 Template/Draft/Version/event/projection/
  operation/outbox publication graph before matrix seal.
- [x] Replace caller-selected status/outcome transitions with server-owned
  failure mapping and explicit cancellation/retry/seal commands.
- [x] Obtain independent Formal Gate Review before authorizing G3.
- **Status:** passed / independently approved

### R6.G3: Full-Dataset preflight

- [x] Implement one-pass bounded Dataset evaluation for seven isolated
  strategy/Feature runtimes.
- [x] Implement all-or-none G3 preflight registration without consuming family
  head or attempt sequence; formal application PostgreSQL registration is not
  executed yet.
- [ ] Generate and audit all seven signal ledgers/match plans without provider,
  broker, lifecycle, or result publication.
- **Status:** implementation candidate verified; formal full-Dataset rerun is
  blocked because the application PostgreSQL DSN is not configured

### R6.G4: Formal seven-attempt replay

- [ ] Execute exactly the seven pre-registered attempts and publish canonical
  immutable results.
- [ ] Run formal SQL and independently verify all identities, parity, costs,
  and zero external calls.
- **Status:** blocked on G3

### R6.G5: Comparative research disposition

- [ ] Apply the frozen common thresholds and multiple-testing correction.
- [ ] Record reject/hold/exploratory-candidate outcomes without lifecycle
  mutation or Local Paper activation.
- **Status:** blocked on G4

## Current status

```text
R5 v2: COMPLETE / RESEARCH REJECT
R6 G0 historical revision: PASSED
R6 G0 Amendment A1: PASSED / CONTRACT FROZEN
R6 G1: PASSED
R6 G2: PASSED
R6 G3: IMPLEMENTATION VERIFIED / FORMAL EXECUTION BLOCKED ON APPLICATION DSN
Formal progress: 50%
Remaining: 50%
R6 formal replay: 0 / 7 / NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Template inventory assumed `StrategyTemplate.required_features` | 1 | Inspect the actual dataclass and derive Feature Requests through the deployed implementation/evaluation boundary instead. |
| Shell search used an unmatched `docker-compose*` glob under zsh | 1 | Use `rg --files`/explicit existing paths rather than an unresolved shell glob. |
| Feature inventory assumed `FeatureRequestSpec.to_dict()` | 1 | Use the frozen explicit request projection fields (`feature_id`, parameters, parameter/request digests) defined by the Feature Request domain. |
| Docker inventory could not access the daemon socket in the sandbox | 1 | Retry the same read-only container listing with explicit sandbox escalation; no container operation was attempted. |
| Strategy Set inventory used historical column names `policy`, `priority_order_json`, and member `role` | 1 | The read-only transaction aborted before row reads; rerun with actual `aggregation_policy`, snapshot JSON, and `member_role` columns. |
| Lifecycle projection inventory used stale column name `sequence` | 1 | Inspect the table schema read-only and rerun with authoritative `last_sequence`; the failed transaction made no change. |
| Parameter inventory assumed `ParameterSchema.parameters_digest()` | 1 | Use the catalog's canonical parameter projection with `canonical_digest(parameters)`, matching Publish behavior. |
| A diagnostic `rg` pattern contained Markdown backticks and zsh evaluated their contents | 1 | Use single-quoted or backtick-free search patterns; no workspace state changed. |
| Identity reconciliation searched for unformatted bar count `28325340` while the document uses `28,325,340` | 1 | Compare the canonical human-formatted count while retaining exact numeric verification from the manifest. |
| Initial skill/context read used a mistyped worktree path | 1 | Re-run against the exact `/Users/stevehuang-work/Documents/tw_intraday_trader` path; no workspace read or write occurred in the failed invocation. |
| Full durable replay rejected the existing RSI sealed Draft | 1 | Verified that the historical Draft was valid at revision 5 with publish expected revision 4; rebuilt the generic invariant `current revision = expected revision + 1` rather than hard-coding revision 2. |
| Direct diagnostic expected `BACKTEST_DATABASE_URL` in the shell environment | 1 | Read the already-supported settings object, which loads the repository `.env`, instead of assuming the variable is exported by the shell. |
| Full shared-worktree regression failed in `test_trade_management_external_readiness.py` because the assertion treats the field name `provider_secret_alias_count` as if it contained the secret value | 1 | Preserve the unrelated concurrent Trade Management work; record `1655 passed, 65 skipped, 1 failed` and run an explicit all-other-tests regression without modifying that scope. |
| First Gate-status patch used lowercase `formal replay` while the existing progress line uses `Formal Replay` | 1 | Confirmed the failed patch applied no changes; split the update into exact-context patches and preserved all Gate boundaries. |
| G3 initially surfaced `match sequence drift` at the first session boundary | 2 | Reproduced with the formal Dataset and replaced the ambiguous ordering symptom with fail-fast incomplete-coverage evidence; slot 1 signal sequence 101 has an entry but no later same-session exit bar. No artifact or attempt was published. |
| Review search used Markdown backticks inside a double-quoted shell command | 1 | The shell attempted command substitution for `UPDATE`; no workspace state changed. Subsequent searches avoid executable backticks. |
| First autonomous-review patch used a wrapped sentence that did not exactly match the file | 1 | `apply_patch` failed atomically with no file change; split the edit into smaller exact-context patches. |
| Build-binding patch assumed a non-exact nearby sentence | 1 | `apply_patch` failed atomically; applied the source-manifest and registration edits as smaller exact-context patches. |
| Scoped A1 `git add` could not create `.git/index.lock` in the sandbox | 1 | Retry the same exact five-path staging command with explicit Git-index escalation; unrelated paths remain excluded. |
| First A1 domain/application focused run retained the historical algorithm digest assertion | 1 | Preserve the historical v1 constant in code and update the current A1 regression to the frozen v2 digest while adding explicit v1 compatibility coverage. |
