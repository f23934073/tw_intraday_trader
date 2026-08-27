# R6 A2 / Migration 018 clean-branch packaging review

## Disposition

```text
Packaging review: APPROVED
A2 contract: APPROVED / FROZEN
Source-only audit: VERIFIED / 0.995893643087254413
Migration 018: VERIFIED / SCHEMA ONLY
Revision 3 activation: NOT AUTHORIZED / NOT PERFORMED
G3 preflight: NOT AUTHORIZED / NOT PERFORMED
Local Paper / Broker / Real-money: PROHIBITED
```

## Source boundary

- Base: freshly re-fetched `origin/main` at
  `7931d31e53657c4f28e684402589c2b20501c1d9`.
- Branch: `codex/r6-a2-migration018-20260827`.
- R6 G1/G2 and A1 were transplanted as the minimum semantic dependency
  closure because current `origin/main` does not contain the R6 package.
- A2, the canonical source-only audit, Migration 018, adapters, scripts,
  tests, and current remediation documentation were transplanted by owned
  file and hunk.
- R5 / Migration 015, Shadow, price coverage, D-HEALTH, PM, Local Paper,
  provider, broker, real-money, and shared dirty-main changes are excluded.
- Historical 2026-08-26 R6 workpad files are excluded because their running
  status is stale and they are not runtime dependencies.

## Immutable audit evidence

```text
audit_digest:
  2e4f8590d0de3f963e4d41bc17d87fd859809053f9f2206015ba69d46863131d
canonical_file_sha256:
  7139ac8430693c14ca7317245616e39b7e0a559fdf30d23607114a26ecd0a71b
source_bar_count: 28,325,340
observed_symbol_session_count: 132,234
eligible_symbol_session_count: 131,691
eligible_symbol_session_ratio: 0.995893643087254413
family_head_sequence: 0
attempt_count: 0
```

The tracked artifact bytes match the tracked SHA-256 sidecar, parse through
`verify_eligibility_audit()`, and equal the verifier's canonical bytes.

## Verification evidence

- Focused no-DSN: `94 passed, 28 skipped`.
- Full no-DSN on the final base: `1603 passed, 71 skipped`.
- Disposable PostgreSQL 17 focused: `32 passed`.
- Disposable PostgreSQL 17 full on a fresh final container: `1674 passed`.
- Migration ordering, idempotent replay, and state-drift rejection are covered
  by the PostgreSQL suite.
- Python compilation and the apply/audit/supervisor CLI help paths passed.
- Canonical audit checksum/replay passed independently.
- The disposable PostgreSQL container was stopped and removed after testing.

The clean-checkout tests use an explicit `R6_TEST_DATASET_MANIFEST_PATH` only
for the canonical immutable Dataset manifest locator. The manifest bytes and
identity are not mocked or rewritten. Supervisor start tests use the running
test interpreter rather than assuming a checkout-local `.venv` exists.

## Production Backtest database read-only evidence

The application Backtest database was inspected in one repeatable-read,
read-only transaction and rolled back:

```text
migration_count: 18
latest_migration: 018_r6_dynamic_entry_reserve.sql
active_matrix_revision: 2
family_head_sequence: 0
attempt_count: 0
preflight_count: 0
audit_registration_count: 0
revision3_matrix_count: 0
release_state: NOT_READY
```

The production Backtest database was never used as `TEST_POSTGRES_DSN`.

## Independent adversarial review

The review checked semantic source ownership, dependency closure, A2 reserve
and signal-mask boundaries, canonical audit authority, migration
preconditions/postconditions, clean-checkout assumptions, prohibited
dependency leakage, and durable-state drift. It found two packaging-only test
assumptions (checkout-local `.venv` and checkout-local immutable Dataset
manifest), both fixed without changing production behavior. No blocking or
important finding remains.

This approval authorizes only the mergeable local package. It does not
authorize push, merge, audit registration, revision-3 activation, G3 preflight,
Local Paper, broker, or real-money execution.
