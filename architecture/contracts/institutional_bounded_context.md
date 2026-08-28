# ADR: Institutional bounded contexts and import direction

## Status

- Decision: `ACCEPTED`
- Plan: `ARCH-001`
- Verified source: `main@91323b0683d4e56ce7816ed532eb8c82a4281319`
- Scope: documentation and static import enforcement only

This ADR does not merge, rename, move, or change the behavior of an
`institutional_*` package. It records the boundaries already present in the
source tree and makes them fail closed in CI.

## Context and lineage

The four similarly named packages are not successive versions of one system.
They share a contracts package and then form two parallel lineages:

```text
                       institutional_data
                       (shared contracts L0)
                         /             \
                        /               \
        lineage A      /                 \      lineage B
                      v                   v
       institutional_research       institutional_mvp
       (diagnostics L1-A)            (MVP evaluation L1-B)
                      |                   |
                      v                   v
       institutional_prior          backtest.*
       (Candidate Prior L2-A)
                      |
                      v
       candidate.previous_session
       (data-only current-session projection)
```

`institutional_mvp` does not evolve from, pass through, or replace
`institutional_research` or `institutional_prior`. Likewise,
`institutional_prior` is not an earlier version of `institutional_mvp`.

## Package positions

| Package | Layer | Lineage | Allowed project dependencies | Consumer | Status |
|---|---|---|---|---|---|
| `institutional_data` | Contracts (L0) | shared base | none | all institutional packages; direct production consumer `config.institutional_mvp` | `STABLE` |
| `institutional_research` | Diagnostics (L1-A) | A | `institutional_data`, `watchlist`, `market_data` | `institutional_prior` | `EXPLORATORY` |
| `institutional_prior` | Candidate Prior (L2-A) | A | `institutional_research`, `institutional_data`, `watchlist` | `candidate.previous_session` | `EXPLORATORY` |
| `institutional_mvp` | MVP Evaluation (L1-B) | B | `institutional_data`, `backtest` | `config.institutional_mvp` | `NON_FORMAL` |

The production consumer column describes direct imports. It does not grant
trading authority. In particular, `candidate.previous_session` verifies the
persisted prior, current-session instrument eligibility, expiry, and false
actionability flags before producing data-only discoveries.

## Import contract

The data-driven `ALLOWED` matrix in
`tests/test_institutional_module_boundaries.py` is the executable form of the
table above. Standard-library and third-party imports are outside this ADR;
institutional and execution-layer imports are governed as follows.

The following directions are forbidden:

- `institutional_data` to any other `institutional_*` package;
- `institutional_research` to `institutional_prior`;
- `institutional_research` to `institutional_mvp`;
- `institutional_prior` to `institutional_mvp`;
- `institutional_mvp` to `institutional_research`;
- `institutional_mvp` to `institutional_prior`;
- any of the four packages to `simulation`, `trading`, `dashboard`, or
  `runtime`.

Imports within a package and the allowed dependencies in the positioning table
remain valid. A new `institutional_*` dependency is forbidden until this ADR,
the `ALLOWED` matrix, package docstrings, and declared-consumer contract are
reviewed together.

The static gate parses source with `ast`; it never imports a package body. A
missing package root, invalid Python syntax, undeclared cross-lineage import,
execution-layer import, or production-consumer drift fails the test. The gate
also contains a synthetic `institutional_prior -> institutional_mvp` violation
to prove the rejection path is live.

## Formalization and retirement evidence

The two lineages have separate evidence histories. Neither may inherit the
other's result or be treated as its next version.

### `institutional_prior`

`institutional_prior` remains `EXPLORATORY`. Its current production consumer is
a data-only Candidate Prior projection, not a BUY signal, BuyScore input,
runtime admission permission, broker instruction, or order instruction.

Formalization may be considered only after all existing frozen gates are met:

1. `architecture/contracts/institutional_population_coverage_v1.md` requires
   complete immutable sources, PIT coverage for TWSE and TPEx, an exact split,
   and at least 60 eligible holdout sessions before outcome generation or
   holdout is allowed.
2. `research/institutional_evaluation/protocols/formal_evaluation_gate_v1.json`
   pins the registered threshold digest, at least 60 sessions, per-arm execution
   minima, both markets, three liquidity cohorts, and the primary
   `COMBINED - PRICE_ONLY` net-expectancy comparison.
3. `architecture/contracts/institutional_formal_evaluation_v0.md` requires the
   untouched holdout to return `PASS`: the session-clustered confidence-interval
   lower bound must be positive and every preregistered guardrail must pass.
   The same contract states that PASS is research evidence only and grants no
   production or real-money authority.

Only a separate owner-approved architecture and rollout decision after that
evidence may change `EXPLORATORY`. `FAIL`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE` cannot be promoted through a subgroup or documentation
change; they trigger a separate decision to retain the research artifact or
retire the Candidate Prior consumer. They never trigger an automatic merge into
`institutional_mvp`.

### `institutional_mvp`

`institutional_mvp` remains `NON_FORMAL`. The minimum of 60 overlapping target
sessions is an input/evidence sufficiency boundary, not a formal-pass claim.
That boundary and the continued false research/formal/runtime/order permissions
are recorded in `.planning/2026-08-20-pr008-review-followup/findings.md` and
`.planning/2026-08-28-institutional-research-main-merge/findings.md`.

The preserved non-formal offline result in the PR-008 follow-up findings does
not support promotion: the institutional filter retained far fewer trades while
its expectancy and profit factor were worse; lower aggregate loss and drawdown
were lower exposure, not evidence of alpha. Formalization therefore requires a
new, explicitly authorized study that satisfies the same PIT population,
preregistration, untouched-holdout, primary-metric, and guardrail contracts
listed above.

If no such study is authorized, or if its frozen verdict is `FAIL`, `BLOCKED`,
or `INSUFFICIENT_EVIDENCE`, the package stays non-formal or is retired by a
separate migration decision. Immutable evidence remains preserved. Any future
consolidation into a formal evaluation context requires a new ADR and migration
plan; it is never an inferred merge with `institutional_prior`.

## New-feature placement decision tree

Ask these questions in order:

1. Is the feature a stable post-close contract, validation rule, official-source
   adapter, or canonical serialization primitive shared by both lineages? Put
   only that contract in `institutional_data`.
2. Is it lineage-A evidence? Put factor diagnostics in
   `institutional_research`; put only a frozen target-session Candidate Prior
   projection in `institutional_prior`.
3. Is it a non-formal offline MVP acquisition/evaluation that uses the existing
   `backtest` seam? Put it in `institutional_mvp`.

If none applies, do not place the feature in an institutional package. In
particular, execution, Dashboard, runtime admission, simulation, trading, or
order behavior requires a separately authorized bounded context and must not be
pulled into either lineage.

## Consequences

- The similar package names no longer imply an evolution chain.
- Cross-lineage and execution-layer imports fail before review or runtime.
- A new production consumer forces the ADR and declared-consumer list to be
  updated explicitly.
- The current production path and low test-file count of
  `institutional_prior` remain visible risks; the scoped gap inventory is in
  `research/institutional_prior_test_gap_2026-08-28.md`.
