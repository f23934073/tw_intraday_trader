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

- Broad combined inspection is too noisy for reliable evidence in this
  worktree. Calendar, artifact, and FinMind test conventions must be inspected
  independently before implementation.
- `institutional_mvp.finmind` is already a pure, deterministic normalization
  seam and the existing tests pin dealer-component semantics, exact source
  session dates, ranking, and provider-neutral candidate dictionaries.
- The pure parser intentionally accepts a successful envelope with zero rows
  and returns no flows. The daily acquisition application must distinguish an
  empty source response as `SOURCE_NOT_READY` before candidate selection so a
  provider delay cannot be published as a valid zero-candidate batch.
- Existing immutable-observation tests use
  `institutional_data.serialization.canonical_json` and `sha256_text`; the new
  repository should reuse those canonicalization rules rather than introduce a
  second digest format.
- `backtest.finmind_history.FinMindApiClient` already provides secret-safe
  `usage()` and validated `data()` calls, including explicit quota and response
  errors. It can be wrapped by the infrastructure adapter; the application and
  domain layers do not need to import `backtest`.
- The only reviewed equity calendar is
  `market_data.equity_calendar.ReviewedEquityCalendar` backed by the 2026 TWSE
  artifact. It validates coverage and supports prior-session resolution, but
  has no next-session method and is not evidence of TPEx calendar coverage.
  PR-001 will inject a tiny next-session resolver over this reviewed calendar,
  fail closed at its coverage boundary, and label it as an operational TWSE
  proxy with `research_eligible=false` rather than claim formal TWSE+TPEx PIT
  coverage.
- The TAIFEX next-session implementation is futures-specific and is not a
  valid equity-calendar dependency for this MVP.
- `config.twse_calendar_2026` exposes only the reviewed artifact path; the new
  daily config can follow this side-effect-free constant/module style.
- The frozen capture script already proves secret-safe quota preflight, strict
  dataset allowlisting, raw-body hashing, staged directory creation, and
  atomic `os.replace`. The daily path should reuse the reusable client and the
  same safety properties without modifying or importing that fixed-session
  script.
- Daily artifact storage will use one canonical JSON document with an embedded
  digest and a content-addressed filename. Publishing will use a same-directory
  temporary file, file `fsync`, atomic no-clobber `os.link`, parent-directory
  `fsync`, and cleanup; this avoids a JSON/sidecar split-brain state.
- Exact canonical replay is idempotent. A different digest for the same
  source/target session is retained as a new revision, but target-session lookup
  must fail closed until a caller explicitly pins one digest; no implicit
  "latest" selection is allowed.
- Daily readiness rules are now explicit: empty institutional wide data is
  `SOURCE_NOT_READY` and creates no batch; wrong source dates are errors;
  non-empty flow data with zero three-way-positive candidates is a valid empty
  published batch. Empty or wholly unmapped `TaiwanStockInfo` is a mapping
  failure, not a valid empty batch.
- Because the current pure parser skips unmapped rows, the daily evidence must
  preserve source row count, mapped row count, and unmapped count. A zero-mapped
  result is fail closed.
- The approved batch contract requires artifact identity/digest, source and
  target sessions, generated/expiry timestamps, candidate-policy identity and
  digest, provider-neutral entries with per-entry digests, and explicit
  limitations. Target-session expiry remains 13:30 Asia/Taipei.
- No standalone candidate-policy artifact was found under the initially
  expected acquisition filename. The existing sealed builder must be inspected
  for the actual frozen policy locator before wiring the daily config; no new
  policy values will be invented silently.
- The frozen r2 policy is under `research/institutional_evaluation/mvp` with
  canonical digest `48db0097...18a`. Its rule, dealer formula, mapping, ranking,
  limit 20, permissions, and limitations are reusable, but its session dates
  and input capture are deliberately fixed to the sealed 2026-08-18 evidence.
- Daily operation therefore needs an embedded effective-policy projection that
  pins the full r2 artifact ID/digest, copies and validates only those frozen
  rule fields, and replaces the evidence-specific dates with the explicit
  source session plus reviewed next-session binding. The effective projection
  gets its own canonical digest inside every batch.
- Adversarial review found that top-level digest validation alone is
  insufficient: a canonically re-digested payload could carry a candidate count
  inconsistent with its list or other internally inconsistent session/count
  fields. The loader must revalidate semantic invariants, not only hashes.
- Calendar schema/timezone pinning also needs the reviewed source digest pinned
  before any provider request. The current reviewed artifact digest is
  `1671338c8247f7f5344657912f469fce111b82b9be0dea1d61d21eb6d3a3593a`.
- Review also found that exact digest lookup accepted glob metacharacters,
  replay identity ignored derived candidate drift, adapter row counts were not
  cross-checked against raw envelopes, and quota preflight lacked a
  cross-process acquisition lock. These are correctness boundaries, not
  optional polish, and must be closed before PR-001 handoff.
- The daily all-market request will preserve the credentialed fixed-capture
  contract (`start_date` only). The parser still rejects a returned date that
  differs from the explicit source session.

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

## Runtime strategy and scheduling seams — 2026-08-25

- `StrategyContext` contains price/bar/features only; it has no candidate-prior
  field. This confirms the first MVP should not add FinMind attributes to every
  atomic/backtest strategy evaluation.
- `ContinuousPaperStrategyController._evaluate_atomic_entry` receives the full
  atomic projection, selects triggered candidates, prepares a fresh BidAsk
  watch, then journals a local-paper intent with decision evidence. The correct
  paper gate is immediately after exact Strategy Set evaluation and before
  quote preparation: keep only symbols allowed by a pinned FinMind candidate
  batch and add that batch identity/gate decision to intent evidence.
- Filtering only at this late point is insufficient for market-data coverage:
  the live Momentum projection currently derives candidates from
  `DashboardService.realtime_candidate_snapshot`, and
  `_dashboard_candidate_discoveries` converts every row to `AUTO`. A separate
  MVP candidate adapter/composition step must preserve source identity and feed
  eligible symbols into the live observation pool before atomic evaluation.
- The repository has an after-close backtest incremental scheduler, but no
  institutional daily scheduler. For MVP, a deterministic one-shot CLI after
  close is the smallest operable boundary; embedded background scheduling can
  wait until the manual/replay path is stable.
- The candidate artifact should be loaded once at session activation, pin its
  digest into the Local Paper activation/runtime checkpoint, and remain fixed
  for that session. Hot-reloading a changed list after seeing intraday behavior
  would make the strategy irreproducible.

## Existing atomic strategy reuse — 2026-08-25

- The deployed atomic entry catalog already includes provider-neutral price
  strategies such as above-VWAP, prior-high breakout, EMA crossover, rolling
  return, volume acceleration, RSI oversold, and Bollinger re-entry, with
  `LOCAL_PAPER_TICK_BIDASK` bindings where admitted. The MVP should compose a
  reviewed exact Strategy Set from existing strategies instead of introducing
  a FinMind-aware price kernel.
- Recommended first paper hypothesis is a two-layer AND across contexts, not a
  new atomic member: `symbol in frozen FinMind T-1 batch` AND `existing exact
  Strategy Set is TRIGGERED`. Within the price Strategy Set, retain its own
  configured `ANY`/`ALL`/`AT_LEAST_N` semantics.
- Existing tests already cover source preservation, candidate evidence
  references, residual capacity, Local Paper activation, CSRF protection,
  exact-set resolution, and one-intent idempotency. New tests should extend
  these seams with allowed/rejected/stale FinMind batch cases rather than
  creating a parallel order path.
- The dashboard Momentum service accepts a candidate snapshot loader and its
  tests use injected fake loaders/runtime. This provides a low-risk test seam
  for a composite snapshot that adds FinMind candidates while preserving their
  explicit source and without a live provider.

## Daily acquisition design — 2026-08-25

- `FinMindApiClient` already separates authentication, usage preflight, quota,
  HTTP, payload-status, and array-shape errors and accepts a requested date.
  The daily MVP can wrap this client rather than duplicating transport code.
- Keep the core dependency clean by defining an institutional-flow provider
  port in `institutional_mvp` and implementing a FinMind adapter at the edge.
  The use case accepts bytes/rows plus a reviewed session resolver; it does not
  import Dashboard, Local Paper, or broker modules.
- The existing after-close scheduler is process-local and only excludes
  weekends; it does not prove a reviewed TWSE/TPEx trading session. Reusing it
  directly for institutional evidence would risk holiday/date mistakes. The
  first MVP release should expose a manual/idempotent one-shot CLI with an
  explicit `--source-session`, then add scheduled automation only after a
  calendar-aware due rule is covered by tests.
- Daily artifacts must use date- and digest-derived identities rather than the
  current hard-coded 2026-08-18 paths. Repeated execution for the same session
  should replay the identical artifact or fail on conflicting bytes; it must
  never overwrite a prior candidate list.

## Implementation intake — 2026-08-25

- The shared worktree contains unrelated active changes across market-data,
  trade-management, root planning files, and tests. PR-MVP-PM-001 must avoid
  every overlapping file except newly scoped institutional MVP/config/CLI/test
  paths and the isolated plan.
- The fixed evidence capture/builder remains a valid regression reference but
  is not the daily implementation target. New code should reuse pure
  normalization behavior and stable serialization conventions without
  modifying the frozen evidence files.

## PR-MVP-PM-001 review corrections — 2026-08-25

- Adversarial review reproduced three blocking gaps despite a green test suite:
  the loader accepted a non-next target session, accepted a truncated candidate
  projection, and readers could observe a linked artifact before directory
  fsync failure rolled the publication back.
- The smallest architecture correction is to inject the already reviewed equity
  calendar into the file repository, keep domain verification framework-free,
  and make repository reads share the publication lock.
- Two operational corrections remain in scope: validate the frozen calendar
  scope before any provider call, and map permanent FinMind authorization or
  entitlement errors to a non-retryable coded failure.
- FinMind can report a retryable condition in a payload-level status while the
  HTTP envelope remains 200. Classification must use the effective status:
  402 is quota, 408/429/5xx remain retryable, and only a genuinely successful
  but unusable HTTP-200 contract is a permanent response-invalid failure.
