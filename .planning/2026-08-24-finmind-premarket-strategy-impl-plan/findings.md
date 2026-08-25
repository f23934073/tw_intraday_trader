# Findings: FinMind Institutional Premarket Strategy MVP

## Initial context — 2026-08-24

- The repository already has an immutable FinMind MVP candidate observation
  for session 2026-08-18, usable from 2026-08-19.
- The MVP observation contains 17 three-way-net-buy candidates mapped from
  2,267 current TWSE/TPEx identities. It is explicitly non-formal and keeps
  outcome, order, production, formal PIT, and holdout permissions disabled.
- `CandidatePool` already models discovery separately from a strategy signal.
  The preferred architecture is therefore provider adapter -> neutral
  previous-session candidate batch -> CandidatePool -> existing price strategy.
- The implementation plan must preserve current-universe/survivorship and
  post-close limitations in metadata and UI rather than implying formal PIT
  validity.

## Skill influence

- `planning-with-files` requires a durable plan, discovery log, and progress
  log for this multi-step design task.
- `architecture-patterns` reinforces an inward dependency direction: FinMind
  HTTP/artifact parsing remains an adapter; CandidatePool and strategy consume
  provider-neutral domain objects through a port.

## Current implementation seams — 2026-08-24

- `institutional_mvp/finmind.py` already contains provider normalization and a
  pure three-way-net-buy selector. It is suitable as an adapter/domain helper,
  but its current identity mapping is explicitly current-market only.
- `scripts/build_finmind_institutional_mvp_candidates.py` is a one-shot evidence
  builder: its capture, policy, dates, output filename, and expected digests are
  hard-coded to the 2026-08-18/r2 artifact. Daily operation needs a new
  parameterized acquisition/application service; the frozen evidence builder
  should remain unchanged.
- The backtest engine evaluates entry strategies for every symbol present in
  the selected Dataset. The institutional prior is not currently a field in the
  strategy evaluation contract, so injecting FinMind-specific fields into
  `GapVwapEntryStrategy` would couple strategy core to a provider and is not the
  preferred first slice.
- A cleaner MVP is to resolve an eligible next-session symbol set before
  strategy evaluation/subscription, while leaving the existing price strategy
  definition unchanged. The run/session evidence must pin the candidate-batch
  identity so results remain reproducible.

## Candidate and paper boundaries — 2026-08-24

- `PreviousSessionWatchlistCandidateSource` is intentionally coupled to the
  durable formal `CandidatePriorRepository` schema and T-day
  `InstrumentReferenceStore`. Feeding the looser FinMind MVP JSON through it
  would either fail or falsely label MVP evidence as formal prior evidence.
- `CandidateSource` currently has `PREVIOUS_SESSION_WATCHLIST` but no explicit
  FinMind/MVP source. The plan should add a distinct source identity such as
  `FINMIND_INSTITUTIONAL_MVP`, plus a dedicated artifact loader/adapter that
  emits ordinary `CandidateDiscovery` objects without exposing raw flow fields
  to CandidatePool.
- `CandidatePool` already supplies priority, TTL, rank, evidence references,
  deterministic decisions, and admission hysteresis. The new adapter can reuse
  these capabilities and should expire the batch at the target session close.
- `InstitutionalCandidateShadowAdmission` is currently hard-coded to
  `PREVIOUS_SESSION_WATCHLIST` and explicitly disables subscriptions and
  execution. The MVP should first add observation support without weakening
  that formal path; any real quote-subscription wiring is a later, separate
  local-paper slice.
- Local paper automation is guarded by exact published Atomic Strategy Set
  resolution, runtime bindings, strategy-intent journaling, and RiskGate. The
  plan must integrate through that controller/service path, never by restoring
  the disabled raw strategy-intent HTTP endpoint.
