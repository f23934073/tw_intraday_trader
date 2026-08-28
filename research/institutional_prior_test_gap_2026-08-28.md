# Institutional Prior test-gap inventory — 2026-08-28

## Status and scope

- Plan: `ARCH-001`, Phase 5
- Source: `main@91323b0683d4e56ce7816ed532eb8c82a4281319`
- Production consumer: `candidate/previous_session.py`
- Outcome: inventory and follow-up ticket only; no production refactor or
  additional behavioral test is authorized by this phase.

`institutional_prior` is directly imported by only three test files even though
it feeds the current-session Candidate Prior decision path:

- `tests/test_institutional_candidate_prior.py`;
- `tests/test_institutional_candidate_persistence.py`;
- `tests/test_institutional_candidate_shadow_admission.py`.

That file count is a useful warning but is not equivalent to low line coverage.
The focused run below provides the more precise baseline.

## Focused evidence

Command:

```text
.venv/bin/python -m pytest \
  tests/test_institutional_candidate_prior.py \
  tests/test_institutional_candidate_persistence.py \
  tests/test_institutional_candidate_shadow_admission.py \
  --cov=institutional_prior --cov-report=term-missing -q
```

Result: `75 passed, 1 skipped`; 930 statements, 78 missed, 92% total line
coverage.

| Module | Statements | Missed | Coverage | Main evidence |
|---|---:|---:|---:|---|
| `__init__.py` | 5 | 0 | 100% | package exports |
| `application.py` | 184 | 12 | 93% | factor-prior projection and Candidate Prior builder |
| `domain.py` | 316 | 39 | 88% | immutable contracts and fail-closed validation |
| `migrations.py` | 29 | 4 | 86% | SQLite forward-only/idempotent migration |
| `postgres_repository.py` | 8 | 2 | 75% | PostgreSQL test is conditional and skipped without a DSN |
| `repository.py` | 13 | 0 | 100% | repository protocol and persistence error |
| `serialization.py` | 238 | 11 | 95% | canonical round-trip, poison fields, digest/replay checks |
| `sql_repository.py` | 122 | 10 | 92% | exercised primarily through SQLite |
| `sqlite_repository.py` | 15 | 0 | 100% | save/get/reopen/conflict/rollback behavior |

No PostgreSQL connection was attempted. The one skip preserves that boundary.

## Production call path and risk order

```text
candidate.previous_session.PreviousSessionWatchlistCandidateSource.discover
  -> CandidatePriorRepository.get(artifact_id)
  -> CandidatePriorArtifact.manifest.run and actionability flags
  -> CandidatePriorArtifact.projections
  -> current-session InstrumentReferenceStore.eligible(symbol)
  -> data-only CandidateDiscovery records
```

The adapter rejects missing artifacts, target-session mismatch, invalid expiry,
and any true strategy/production/live-admission/execution flag. It never turns
the prior into an order instruction. Because this path affects which symbols
enter data-only shadow consideration, defects can still change a production
decision even though trading authority remains false.

Risk is ordered as follows:

1. **High — repository-to-adapter handoff.** Adapter behavior uses an in-memory
   repository double, while durable SQLite persistence is tested separately.
   There is no one-test proof that a persisted/reopened artifact flows through
   `CandidatePriorRepository.get` into the current-session adapter unchanged.
2. **High when PostgreSQL is selected — adapter parity.** The PostgreSQL
   constructor/path is the conditional skip. No application PostgreSQL or real
   DSN may be used to close this gap; it needs a disposable, separately
   authorized CI fixture.
3. **Medium — poison/validation branches.** `domain.py`, `application.py`, and
   `sql_repository.py` retain unexecuted fail-closed branches. Current coverage
   is substantial, but the missed branches should be classified by invariant
   before adding tests.
4. **Low — canonical helpers.** Serialization helpers are mostly exercised
   indirectly through artifact builders and canonical round trips. Their public
   surface is covered, but some helper-specific error paths are indirect only.

## Complete public surface inventory

Touch labels:

- `DIRECT`: named or constructed directly by a focused test;
- `INDIRECT`: executed through a directly tested builder, artifact, or concrete
  repository path;
- `CONTRACT`: exercised by a structurally compatible repository double or
  downstream consumer rather than instantiated itself;
- `CONDITIONAL_SKIP`: a test exists but did not execute in the required
  provider/database-free environment.

| Module | Public function or class | Test touch | Production-path risk |
|---|---|---|---|
| `application.py` | `project_institutional_factor_prior` | `DIRECT` | medium; upstream artifact construction |
| `application.py` | `InstitutionalCandidatePriorBuilder` | `DIRECT` | medium; produces consumed artifact |
| `domain.py` | `CandidatePriorInputError` | `DIRECT` | medium; fail-closed errors |
| `domain.py` | `CandidatePriorHypothesis` | `DIRECT` | low |
| `domain.py` | `ComponentMatchPolicy` | `INDIRECT` | low |
| `domain.py` | `EvaluationCohort` | `DIRECT` | low |
| `domain.py` | `CandidatePriorDefinition` | `INDIRECT` | medium; frozen definition identity |
| `domain.py` | `candidate_prior_definitions` | `DIRECT` | medium; frozen hypothesis set |
| `domain.py` | `PriceMomentumCandidate` | `DIRECT` | low |
| `domain.py` | `PriceMomentumPrior` | `DIRECT` | medium; input lineage |
| `domain.py` | `PriceMomentumPriorArtifact` | `DIRECT` | medium; input lineage |
| `domain.py` | `InstitutionalFactorPrior` | `INDIRECT` | medium; input lineage |
| `domain.py` | `InstitutionalFactorPriorArtifact` | `DIRECT` | medium; input lineage |
| `domain.py` | `CandidatePriorRunManifestV0` | `DIRECT` | high; target/as-of identity consumed downstream |
| `domain.py` | `CandidatePriorEntryPayload` | `INDIRECT` | medium; canonical candidate facts |
| `domain.py` | `CandidatePriorEntry` | `INDIRECT` | medium; canonical entry digest |
| `domain.py` | `CandidatePriorArtifactManifestV0` | `INDIRECT` | high; actionability flags consumed downstream |
| `domain.py` | `CandidatePriorProjection` | `INDIRECT` | high; rows consumed by current-session adapter |
| `domain.py` | `CandidatePriorArtifact` | `DIRECT` | high; repository/adapter handoff object |
| `migrations.py` | `migration_files` | `DIRECT` | medium; durable schema identity |
| `migrations.py` | `apply_migrations` | `DIRECT` | medium; durable schema application |
| `postgres_repository.py` | `PostgresCandidatePriorRepository` | `CONDITIONAL_SKIP` | high when PostgreSQL adapter is selected |
| `repository.py` | `CandidatePriorPersistenceError` | `DIRECT` | medium; fail-closed persistence |
| `repository.py` | `CandidatePriorRepository` | `CONTRACT` | high; direct production dependency |
| `serialization.py` | `CandidatePriorSerializationError` | `DIRECT` | medium; fail-closed bytes boundary |
| `serialization.py` | `serialize_candidate_prior_definition` | `INDIRECT` | low |
| `serialization.py` | `candidate_prior_definition_sha256` | `DIRECT` | medium; definition identity |
| `serialization.py` | `candidate_prior_definition_identity` | `DIRECT` | medium; definition identity |
| `serialization.py` | `serialize_candidate_prior_run_manifest` | `INDIRECT` | medium; run identity |
| `serialization.py` | `candidate_prior_run_identity_sha256` | `DIRECT` | high; persistence conflict identity |
| `serialization.py` | `serialize_price_momentum_prior` | `INDIRECT` | low |
| `serialization.py` | `build_price_momentum_prior_artifact` | `DIRECT` | medium; input artifact |
| `serialization.py` | `serialize_institutional_factor_prior` | `INDIRECT` | low |
| `serialization.py` | `build_institutional_factor_prior_artifact` | `INDIRECT` | medium; input artifact |
| `serialization.py` | `serialize_candidate_prior_entry_payload` | `INDIRECT` | low |
| `serialization.py` | `build_candidate_prior_entry` | `INDIRECT` | medium; entry digest |
| `serialization.py` | `serialize_candidate_prior_entries` | `INDIRECT` | low |
| `serialization.py` | `candidate_prior_entries_sha256` | `DIRECT` | medium; artifact integrity |
| `serialization.py` | `serialize_candidate_prior_artifact` | `INDIRECT` | medium; durable bytes |
| `serialization.py` | `build_candidate_prior_artifact` | `DIRECT` | high; durable handoff artifact |
| `serialization.py` | `deserialize_candidate_prior_artifact` | `DIRECT` | high; repository load boundary |
| `sql_repository.py` | `SqlCandidatePriorRepository` | `INDIRECT` | high; concrete durable get/save behavior |
| `sqlite_repository.py` | `SQLiteCandidatePriorRepository` | `DIRECT` | high; tested concrete durable adapter |

All 43 public top-level functions/classes are included. Private helpers and
methods are represented by their owning public class/function and the module
coverage table rather than being mislabeled as public API.

## Follow-up ticket

**Ticket:** `ARCH-001-FU-001 — Harden Candidate Prior production-path coverage`

**Status:** `OPEN / BACKLOG_RECORD` in this report. No external tracker, PR, or
remote repository was mutated by ARCH-001.

**Authorized future scope requires a separate task:**

1. Add a provider-free integration test that saves and reopens one artifact
   through `SQLiteCandidatePriorRepository`, then passes that exact repository
   to `PreviousSessionWatchlistCandidateSource` and verifies artifact, rank,
   entry-digest, session, eligibility, and false actionability parity.
2. Classify the 78 missed lines by invariant; add only table-driven poison tests
   for reachable identity, PIT, actionability, replay, transaction, and row
   parity branches.
3. Under an explicitly supplied disposable CI DSN, run PostgreSQL migration,
   save/get/replay/conflict parity. Never use the application database or infer
   PostgreSQL authorization from this ticket.

**Acceptance:** the durable repository-to-adapter handoff is proven, every added
test is deterministic and provider-free except the explicitly disposable
PostgreSQL job, and no package/API/runtime behavior changes are needed merely to
raise a coverage number.

**Non-goals:** package merge, rename, production refactor, provider access,
market-data access, trading, or changes to fail-closed actionability semantics.
