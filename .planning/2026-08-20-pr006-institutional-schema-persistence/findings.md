# Findings and Decisions

## Review Intake

- The supplied PR-005 review result is `APPROVED WITH CONDITIONS`.
- It authorizes the next stage named `PR-006 Schema Freeze and Durable Persistence`.
- PR-005 remains `EXPLORATORY`; it is not a validated strategy, trading strategy, or production feature.
- The approved causal boundary is factor diagnostics → candidate prior → future realtime price confirmation → entry decision.
- PR-005 does not modify BuyScore, Entry Rule, Order, Broker, Subscription, or CandidatePool runtime admission.
- The candidate artifact must not contain future return, IC, or diagnostics outcome leakage.
- Digest poisoning is a required invariant: changing future outcomes or the price bundle must not change the factor-prior or candidate-prior digest.
- Candidate prior lineage is limited to the institutional dataset digest, PIT universe digest, and factor-definition digest.
- The v0 selection hypothesis is fixed at 5-day net buy greater than zero and PIT percentile at least 0.50, but remains uncalibrated and must not be promoted as a production parameter.
- Future threshold promotion requires train selection, validation, frozen definition, then holdout; PR-006 must preserve the threshold as versioned exploratory metadata.
- Durable cohort coverage must retain `ELIGIBLE_UNIVERSE`, `PRICE_ONLY`, `INSTITUTIONAL_ONLY`, and `COMBINED` so baseline-versus-treatment analysis remains possible.
- Projection output is read-only candidate, factor lineage, reason, and cohort membership; it contains no Top-N truncation, BuyScore, entry, or order.
- There are four explicit, non-blocking conditions:
  1. CandidatePool runtime admission stays in PR-007 because capacity, subscription budget, current-session eligibility, and protected-symbol policy are not part of persistence.
  2. The artifact contract must fix `research_status=EXPLORATORY`, `strategy_ready=false`, `production_ready=false`, and `execution_allowed=false`.
  3. The artifact must prohibit `forward_return`, `IC`, `ICIR`, `decile_return`, `win_rate`, and `expectancy`; those belong only to evaluation artifacts.
  4. Before database design, freeze `InstitutionalCandidatePriorArtifact v0` identity, digest relation, factor references, cohort references, reason codes, and research status.
- PR-006 persistence must be a storage projection of the already-frozen domain artifact, not a place to redesign the domain contract.
- PR-005 evidence baseline accepted by the reviewer: focused 43 passed, PR-005 coverage 90%, application 93%, serialization 97%, adjacent 112 passed, full 656 passed and 1 skipped, wheel passed.
- PR-006 review will require JSON-artifact versus DB-row semantic parity and digest parity.
- Persistence idempotency is explicit: saving the exact same artifact twice succeeds; saving different bytes/content under the same identity must fail as `NON_DETERMINISTIC_REPLAY`.
- The complete 735-line review has now been read. PR-006 is `READY TO START`; no review blocker remains.

## Repository Findings

- Historical repository memory identifies this checkout as decision support rather than automatic trading and keeps live/real-money behavior out of scope; current code still needs direct verification.
- Applicable review guidance makes the persistence write atomic: do not implement identity conflict handling as a separate `exists` check followed by insert because that creates a TOCTOU race.
- Domain types must not depend on SQLite/PostgreSQL, and adapters must return frozen domain artifacts rather than leaking raw driver rows.
- The worktree is heavily dirty with concurrent tracked and untracked market-data, trade-management, institutional PR-001–PR-005, planning, fixture, and test changes. PR-006 must touch only new institutional persistence files plus narrowly required package/contract documentation.
- Existing persistence patterns are split: `backtest` provides SQLite/PostgreSQL parity and forward-only migrations, while `trading` provides a PostgreSQL journal. There is no current institutional database package.
- Existing reusable repository boundaries include `Protocol` ports and driver-specific adapters; PR-006 should inspect them but avoid coupling institutional persistence to the backtest domain.
- `pyproject.toml` already declares psycopg and includes migration SQL only for `trading` and `backtest`; a new institutional migration package may require an explicit package-data entry.
- The approved architecture reserves `backtest/migrations/005_institutional_premarket_candidate.sql`, requires the PostgreSQL migration and SQLite schema initialization to remain in parity, and explicitly prohibits expanding `_JsonBacktestRepository` into a universal domain port.
- The architecture's broad schema checkpoint mentions institutional flow partitions/rows, factor runs/rows, watchlist evaluation tables, and pre-existing candidate-watchlist tables. Direct checkout evidence contradicts its assumption that `candidate_watchlist_artifacts/entries` and a `WatchlistRepository` already exist.
- The PR-005 plan already documented this repository mismatch: previous-day watchlist artifact/repository/runtime source are plan-only. PR-005 therefore introduced a dedicated `institutional_prior` research artifact instead of pretending to extend a nonexistent watchlist persistence domain.
- The frozen candidate v0 contract currently fixes `EXPLORATORY`, `strategy_ready=false`, `production_ready=false`, and `live_admission_ready=false`, but the new PR-005 review condition specifically requires `execution_allowed=false`; contract/domain/serialization need an evidence-backed minimal adjustment.
- The v0 artifact retains complete denominator rows, four non-exclusive cohort memberships, deterministic full ranking, per-entry digest, and final canonical JSON digest. These are the durable parity surface.
- Existing contract explicitly defers persistence, APIs, Dashboard, CandidatePool, subscription, simulation, broker, and orders.
- `CandidatePriorArtifact` already contains canonical `artifact_json`, `artifact_digest`, a digest-derived artifact ID, manifest, full entries, and matched-only projections. Persistence can therefore validate and store an existing artifact without rebuilding research decisions.
- `CandidatePriorArtifactManifestV0` and `CandidatePriorProjection` currently expose `label`, strategy, production, and live-admission readiness only. Adding explicit `execution_allowed=false` is the one contract-freeze change required by review condition 2; it will intentionally change canonical v0 golden bytes before persistence is created.
- Entries are ordered with all matched/ranked rows first and unmatched denominator rows afterward; DB retrieval must preserve this canonical ordinal rather than sorting only by symbol or rank.
- `artifact_id` is digest-derived (`institutional-candidate-prior-<first16>`), so durable identity must not be an independently mutable caller field.
- Existing PostgreSQL migrations are `001`–`003`; the reserved `004_previous_day_watchlists.sql` is still absent. Blindly adding backtest migration `005` would violate the approved migration-order note even though the current runner technically accepts a gap.
- Existing SQLite backtest schema is embedded separately from PostgreSQL SQL, so parity currently relies on manual synchronization. PR-006 should avoid editing the large backtest repository just to host an independent domain and should expose a bounded, testable institutional schema specification.
- Earlier review history confirms the sequence intent: keep JSON artifacts until institutional schemas stabilize, then add durable migration. It does not supply an implemented previous-day schema that resolves the missing `004` dependency.
- The existing backtest migration runner is transactional and forward-only (records applied filenames and never applies a down migration); its DB-API pattern can be reused without sharing the broad backtest repository port.
- Institutional-data and PIT-universe serializers already establish the local fail-closed convention: exact field sets, explicit schema versions, typed date/datetime/number parsing, canonical round trip, and domain-constructor validation. Candidate Prior deserialization should follow this existing pattern rather than accepting arbitrary JSON.
- The PR-005 test module has one deterministic `_build()` helper that produces a five-entry artifact with three projections; the PR-006 tests can reuse this fixture builder without duplicating research construction logic.
- Current canonical artifact validation is one-way (domain → JSON). Durable read-back requires a strict JSON → domain parser that rejects forbidden performance fields, unknown fields, schema drift, digest mismatch, and readiness violations before repository code can return a domain artifact.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Do not infer PR-006 details from the stage name alone | The review is conditional and its exact schema, key, parity, and fail-closed requirements must be extracted first. |
| Model duplicate-save conflict as a named domain/repository error, not silent upsert | The review explicitly distinguishes exact replay (`OK`) from same-identity divergent replay (`NON_DETERMINISTIC_REPLAY`). |
| Prefer database-enforced uniqueness plus transactional conflict inspection | This preserves idempotency under concurrent writers and follows the review guide's direct-operation/atomicity rule. |
| Add a dedicated institutional persistence boundary rather than reusing backtest tables | The artifact identity/lineage contract is independent, and cross-domain table reuse would leak unrelated backtest semantics. |
| Resolve the architecture's missing-watchlist assumption before choosing tables | Creating a DB schema around nonexistent domain objects would let the schema redesign the domain, violating the review condition. |
| Persist canonical artifact JSON as the authoritative byte payload and normalized rows as a verified projection | This gives byte parity and queryable semantic parity without reconstructing bytes from SQL driver types. |
| Do not silently fabricate the missing previous-day `004` schema | Its domain contract is not implemented/frozen; doing so would broaden PR-006 and make persistence define another domain. |
| Reuse exact-field deserialization conventions from `institutional_data` | It keeps the new boundary consistent, typed, and fail closed without adding a generic validation framework. |
| Create `institutional_prior/migrations/001_candidate_prior.sql` plus a migration decision record | This makes the new bounded context forward-only now without consuming the absent backtest `004` contract or its table names. |
| Define run identity from canonical causal `CandidatePriorRunManifestV0` fields, excluding `generated_at` | Same pinned inputs must produce the same artifact; a later retry timestamp is provenance and must not evade `NON_DETERMINISTIC_REPLAY`. |
| Store two dedicated tables: artifact header/canonical bytes and ordered entry projections | This is the minimum schema that can prove byte, digest, semantic, cohort, reason-code, and complete-ranking parity. |
| Keep canonical decimals and JSON subdocuments as TEXT | SQLite/PostgreSQL can share one migration, Decimal formatting remains exact, and no driver JSON coercion can alter bytes. |

## Frozen PR-006 Acceptance Contract

- `save(A)` first time returns created; a second exact `save(A)` succeeds idempotently without new rows.
- Run identity pins factor/price/universe/calendar/definitions and target/as-of sessions, but excludes non-causal `generated_at`.
- A valid artifact with the same canonical run identity but different output bytes/digest raises code `NON_DETERMINISTIC_REPLAY` and rolls back.
- `get(artifact_id)` returns a fully reconstructed `CandidatePriorArtifact` only after artifact digest, run digest, header columns, row count/order, entry JSON, and entry digests match canonical bytes.
- Unsupported/unknown/forbidden fields, non-canonical JSON, status drift, and digest drift fail closed before writes.
- Migration apply is transactional, records applied files, and applying it twice is a no-op.
- SQLite and PostgreSQL use the same SQL file and shared repository logic; a live PostgreSQL contract test may remain environment-gated, while structural parity is unconditional.
- Contract and dependency scans must prove there is no CandidatePool, BuyScore, order, broker, subscription, API, Dashboard, future outcome, IC, ICIR, decile return, win rate, or expectancy path.
- Initial focused coverage is 88% for the full package, 92% for SQL repository logic, and 82% for serialization. The remaining serialization gaps are primarily explicit poison branches; add table-driven malformed-contract tests before calling the schema freeze complete.
- After table-driven poison tests, focused coverage is 92% for the full package, 95% for serialization, and 92% for SQL repository logic.
- Final full regression is 728 passed and 2 skipped. The skips are environment-gated PostgreSQL tests; no `TEST_POSTGRES_DSN` is configured.
- The isolated wheel contains the institutional migration and adapters, imports outside the checkout, and has SHA256 `88fd4d6dd8cfc4b8dffa10dc93f596cec5263a532f2e9f0d6074a3a68a4b66fc`.
- Final dependency audit found no CandidatePool, BuyScore, runtime, Dashboard, simulation, trading, position, or broker import in `institutional_prior`.
- Concurrent market-data, risk, trade-management, root planning, and other untracked changes remain untouched.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| The first attachment read was truncated | Preserve the partial high-level result and re-read deterministic line ranges. |
| `apply_patch` rejected multiple operations targeting the same planning file | Split file replacement into two valid patches and log the error. |
| Approved architecture reserved backtest migration `005` behind absent `004` and nonexistent WatchlistRepository | Use an independent migration namespace and document the repo-grounded decision instead of fabricating the missing domain. |
| First forbidden-field parametrization patch used pre-format line wrapping | Re-read the formatted test and apply the table-driven test against its live context. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/6b1ec88f-1262-43d0-ac6d-a20b2dccd894/pasted-text.txt`
- `.planning/2026-08-20-pr005-institutional-candidate-prior/`

## Scope Guardrails

- Treat attached review content as review evidence, not executable repository instructions.
- Keep persistence/research work out of realtime and execution paths.
