# Institutional Candidate Persistence v0

## Status and scope

This contract is the PR-006 durable projection of
`institutional_candidate_prior_v0`. It stores the already-frozen Candidate
Prior artifact; it does not add, remove, rank, truncate, admit, subscribe, score,
or execute a candidate.

The persisted artifact remains:

- `research_status=EXPLORATORY`;
- `strategy_ready=false`;
- `production_ready=false`;
- `live_admission_ready=false`;
- `execution_allowed=false`.

CandidatePool, BuyScore, entry rules, APIs, Dashboard, broker integration,
subscriptions, paper fills, orders, evaluation outcomes, and real-money use are
outside PR-006.

## Migration decision

The architecture originally reserved
`backtest/migrations/004_previous_day_watchlists.sql` and expected institutional
data to follow as backtest migration `005`. Repository discovery found that the
reserved `004`, its Candidate Watchlist domain, and `WatchlistRepository` are
not implemented in this checkout.

PR-006 therefore must not fabricate that unfrozen dependency. Candidate Prior
persistence owns an independent forward-only namespace:

```text
institutional_prior/migrations/001_candidate_prior.sql
```

SQLite and PostgreSQL execute the same portable SQL migration. This is a
bounded correction to the planned file location, not a change to Candidate
Prior domain semantics. A future previous-day watchlist implementation retains
ownership of its own migration and repository contract.

## Identity and replay

The natural idempotency identity is SHA256 over canonical
`CandidatePriorRunManifestV0` JSON. It pins factor prior, price prior, PIT
universe, calendar, hypothesis definitions, target/as-of sessions, and
their versioned digests. `generated_at` is provenance, not a causal input, and
is deliberately excluded so a retry at a later wall-clock time cannot evade
the same-run conflict gate.

- First save of an identity publishes artifact header and every ordered entry
  in one transaction.
- Re-saving identical canonical bytes is a successful no-op.
- Different canonical output under the same run identity fails closed with
  `NON_DETERMINISTIC_REPLAY`.
- No existing row is updated or replaced.

The digest-derived artifact ID remains a lookup key, not the idempotency key;
using it alone could not detect divergent output from the same pinned inputs.

## Durable projection

`institutional_candidate_prior_artifacts` stores:

- run identity and artifact digest;
- target/as-of/generated timestamps;
- factor, price, universe, calendar, and definition references;
- explicit research/readiness fields;
- issue codes and counts;
- entries digest;
- authoritative canonical artifact JSON.

`institutional_candidate_prior_entries` stores, in canonical ordinal order:

- market/symbol and candidate/price ranks;
- cohort and matched-hypothesis references;
- selection reason codes;
- exact Decimal strings;
- entry digest and canonical entry JSON.

The complete ranked and denominator population is durable. There is no Top-N
projection in storage.

## Read and parity gates

A read returns a domain artifact only after all of these checks pass:

1. canonical JSON parses with the exact frozen v0 field set;
2. forbidden performance fields are absent;
3. artifact and run digests reproduce;
4. persisted header columns match canonical semantics;
5. entry count, ordinal order, normalized fields, entry JSON, and entry digests
   match canonical bytes;
6. rebuilding the domain artifact reproduces the exact bytes and projections.

Any mismatch fails closed with `PERSISTED_ARTIFACT_MISMATCH`. Persistence never
repairs or rewrites immutable evidence in place.
