# Task Plan: FinMind Institutional Premarket Strategy MVP

## Goal

Produce a repository-grounded implementation plan for turning the existing
FinMind post-close institutional candidate artifact into a next-session
premarket CandidatePool input and paper-simulation-only strategy constraint.
This turn is plan-only: no runtime, strategy, API, database, or UI code changes.

## Scope boundaries

- FinMind institutional data is available after T-day close and may be used no
  earlier than T+1.
- Institutional flow is a candidate prior/filter, not an independent order
  trigger.
- Initial execution target is observation and local paper simulation only.
- Formal PR-008 PIT, coverage, holdout, and production gates remain unchanged.
- No live broker order, subscription expansion, or production strategy binding
  is authorized by this plan.

## Phases

### Phase 1: Current architecture and seams — in progress

- [ ] Inspect the sealed FinMind MVP artifact and its builder/normalizer.
- [ ] Inspect CandidatePool source/admission boundaries.
- [ ] Inspect existing entry strategy, paper simulation, scheduler, and UI seams.

### Phase 2: Premarket strategy contract — pending

- [ ] Define T/T+1 timing and anti-lookahead rules.
- [ ] Define candidate/filter semantics and failure behavior.
- [ ] Define minimal configuration and immutable identities.

### Phase 3: Implementation slices — pending

- [ ] Specify modules, interfaces, migrations/config, and wiring changes.
- [ ] Specify tests and observable acceptance criteria per slice.
- [ ] Define rollout gates from observation to paper simulation.

### Phase 4: Deliverable — pending

- [ ] Write the final implementation plan with ordered PRs, file targets,
  verification commands, risks, and explicit non-goals.

## Decisions

| Decision | Rationale |
|---|---|
| Plan-only turn | The user explicitly requested an implementation plan first. |
| Use CandidatePool as the integration boundary | It already distinguishes discovery from an entry signal. |
| Keep FinMind adapter outside strategy core | Provider formats belong at the infrastructure edge; strategy logic should consume a provider-neutral prior. |

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| None | 0 | N/A |
