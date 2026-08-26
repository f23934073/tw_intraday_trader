# R6 Revision 2 G0 Review Request

## Requested disposition

```text
R6 G0: APPROVE / CONTRACT FROZEN
or
R6 G0: REQUEST CHANGES
```

Review source:

- `architecture/r6_atomic_entry_benchmark_v2_implementation_plan.md`

## Review focus

1. Seven slots are fixed before any new result and Bollinger period 10 is not
   silently replaced by Template default 20.
2. Four missing Versions have an explicit post-G0 publication/admission Gate;
   no invented Version ID is treated as durable authority.
3. `FIRST_TRIGGER_PER_SYMBOL_SESSION`, one lot, next same-session observed open,
   same-session terminal close, and common costs are unambiguous.
4. Exact artifact schemas, canonical bytes, multiplicity parity, lifecycle and
   Dataset provenance all fail closed.
5. Absolute zero-edge screening cannot pass merely by outperforming rejected
   VWAP; alpha remains 0.05/20 = 0.0025.
6. The Dataset's exploratory status prevents promotion and Local Paper.
7. Equivalent research cannot reset the attempt budget through a new matrix,
   Version publication, implementation build, or idempotency key.
8. Dedicated replay persistence does not create fake Backtest Runs or weaken
   existing experiment-attempt foreign keys.
9. The identity chain is exact and non-circular: G0 hypothesis specification,
   G1 Version binding, slot, matrix, registration, then artifacts.
10. FAILED/CANCELLED technical recovery reuses one attempt identity under
    revision CAS, never adds sequence/head/budget, and has a fixed retry ceiling.
    Generation 4 has explicit direct terminal rows and exact code guards.
11. Audit clocks cannot change semantic artifact bytes or roots.
12. Results remain redacted until all seven formal slots are accepted across
    repository, API, CLI, filesystem artifact catalog, reports, exports, logs,
    exceptions, and outbox; one unified reader enforces the release row.
13. G4 writes performance evidence only to PostgreSQL quarantine. No public
    filesystem result exists before 7/7; release publishes one all-seven bundle.
    Bundle paths, member order, 10,000-row chunk boundaries, canonical file
    bytes, binary framing, and payload SHA-256 input are exact.
14. G0 approval authorizes G1 only; it does not authorize the 28.3M-bar scan or
    formal replay.

## Current evidence

- Authoritative PostgreSQL contains zero experiment families/attempts.
- Only rolling return, RSI, and Bollinger have published immutable Versions.
- No R6 Draft, Version, family, slot, Run, Replay, or result has been created.
- No Local Paper, provider, broker, CA, trade subscription, or real-money path
  was called.

## Remediation evidence

- Exact frozen roots now exist for research baseline, protocol core, and all
  seven G0 hypothesis specifications; four absent Version IDs are introduced
  only by the downstream G1 Version-binding projection.
- Identity projections have closed key sets and a single upstream-to-downstream
  digest order. Audit/locator/clock fields are excluded.
- Retry transition, revision, generation, error allowlist, ceiling, and
  final-family failure semantics are explicit and do not add an attempt.
- G4 performance rows/manifests/summaries/postflights are PostgreSQL quarantine
  evidence until 7/7. Public product paths share one release reader, and the
  filesystem receives only one post-barrier all-seven bundle.
- Focused current-strategy regression: `38 passed in 0.12s`.
- Trailing whitespace, EOF newline, balanced Markdown fences, and targeted
  diff checks pass for the R6 architecture/planning files.
