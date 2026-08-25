# Task Plan: PR-008 FinMind PIT Price Integration

## Goal

Safely register the existing FinMind Sponsor three-year dataset as a
non-formal, engineering-reference artifact for PR-008, and implement the
fail-closed contract required to acquire a distinct PIT-compatible FinMind
price dataset. This work must not consume provider quota, read outcomes, run a
backtest, or change any formal evaluation lock.

## Current status

- Original formal protocol and coverage amendment remain frozen.
- The existing FinMind dataset is immutable but `CURRENT_SNAPSHOT` and
  `research_eligible=false`; it cannot be the formal PR-008 population.
- The PR-008 Price Dataset / Population Freeze / Outcome gates remain blocked.

## Phases

### Phase 1: Scope and evidence inventory

- [x] Read the related FinMind history and historical-backtest readiness tasks.
- [x] Preserve the boundary between observed strategy outcomes and PR-008's
  unobserved formal outcome.
- [x] Record the relevant artifact identities and non-eligibility rationale.

### Phase 2: Repository contract inspection

- [x] Locate existing PR-008 dataset-acquisition, coverage-audit, and manifest
  schemas plus their test conventions.
- [x] Identify the smallest additive seam for a PIT-specific FinMind acquisition
  specification without modifying the existing immutable dataset.

### Phase 3: Implement fail-closed FinMind integration artifacts

- [x] Add a versioned PR-008 FinMind source-registration artifact that labels
  the current dataset as engineering-only and outcome-observed.
- [x] Add a PIT-compatible acquisition contract that requires date-effective
  universe input, dual-market coverage, calendar/reference/corporate-action
  lineage, and a separate resulting dataset identity.
- [x] Add canonical digest/drift tests and keep all downstream permissions false.

### Phase 4: Verification and handoff

- [x] Run focused contract/artifact tests, compile, digest checks, and a scoped
  diff review.
- [x] Report the exact remaining external data gates without claiming research
  readiness.

### Phase 5: PIT universe and reference-data acquisition readiness

- [x] Restore the completed FinMind integration context and preserve concurrent
  worktree changes.
- [x] Inspect the reusable PIT import contract and the existing acquisition
  plan for source, temporal, and security-identity requirements.
- [x] Decide whether a truthful first artifact can be acquired locally or must
  remain a source-resolution block.
- [x] Implement only the next fail-closed PIT acquisition artifact or adapter
  supported by the discovered evidence.
- [x] Verify the new PIT scope without creating a current-snapshot surrogate.

### Phase 6: TEJ/TQuant metadata qualification

- [x] Receive research-owner authorization for a bounded metadata-only
  qualification.
- [x] Perform a secret-safe local entitlement preflight.
- [ ] Run the frozen metadata-only qualification after a TEJ/TQuant credential
  is provisioned.

### Phase 7: FinMind PIT/reference metadata qualification

- [x] Receive research-owner authorization to use the existing FinMind Sponsor
  credential for a bounded metadata-only probe.
- [x] Revalidate the existing FinMind client and prevent reuse of price/KBar
  acquisition code paths.
- [x] Freeze an allowlisted non-price request set, response-capture policy, and
  no-outcome execution locks before provider access.
- [x] Execute the frozen probe only after secret-safe token preflight and
  positive request-budget preflight.
- [x] Validate schema, historical range, dual-market/delisting coverage, and
  revision evidence; emit an immutable result without selecting a source.

### Phase 8: FinMind PIT/reference semantics and terms resolution

- [x] Restore the completed credentialed-probe evidence and inspect the strict
  PIT import contract.
- [x] Resolve the documented listing-history, industry-as-of, calendar-scope,
  and source-term constraints without an unnecessary second provider probe.
- [x] Preserve a distinct immutable semantics-resolution result; no additional
  provider request is authorized or needed after a decisive semantic conflict.
- [x] Determine whether FinMind can produce a formal PIT/reference artifact;
  keep Price Dataset, Population Freeze, and outcomes locked unless every PIT
  requirement is explicitly satisfied.

### Phase 9: FinMind institutional MVP

- [x] Record the research-owner scope change: deliver a clearly labelled MVP,
  not a formal PIT/holdout result.
- [x] Inspect the existing institutional normalization and candidate seams, then
  freeze the minimum FinMind daily-flow MVP contract.
- [x] Implement a separate read-only FinMind MVP institutional adapter and
  candidate ranking path without modifying the formal PR-008 gate.
- [x] Run a bounded Sponsor probe only if necessary to verify the official
  daily-flow schema; preserve a small immutable MVP capture.
- [x] Verify the MVP path and document its current-universe, post-close, and
  non-formal limitations.

## Decisions

| Decision | Rationale |
|---|---|
| Do not reuse the FinMind current-snapshot dataset as a PR-008 holdout | Its strategy outcome has already been observed and its universe is not PIT. |
| Do not mix FinMind with the lost Shioaji scan lineage | Provider/source identity and checkpoint lineage must remain explicit. |
| Do not acquire new data in this task | A PIT target range and source universe require a frozen plan before provider quota may be spent. |
| Start the next phase with PIT/reference, not price | It is the first prerequisite that determines the formal denominator and prevents survivorship substitution. |
| Do not issue an anonymous TEJ/TQuant request | Authorization does not establish an account entitlement; anonymous responses would not be qualification evidence. |
| Probe FinMind reference datasets separately from KBar acquisition | The existing KBar history job and its mutable checkpoints must not be touched by PIT/reference qualification. |
| Treat credentialed FinMind access as qualification evidence, not PIT qualification | The bounded probe observes access and selected schemas only; it cannot prove full date-effective security/reference history or source terms. |
| Probe unresolved PIT semantics in a new revision | The prior immutable capture cannot be rewritten to add requests or reinterpret its narrow request set. |
| Separate FinMind MVP from PR-008 formal evaluation | The user accepts a practical MVP, while formal PIT/coverage/holdout evidence must remain frozen and blocked. |
| Normalize FinMind dealer flow with a component-first fallback | Component fields frequently encode the same dealer flow as the legacy fields, so adding both would double-count. |

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| None | 0 | N/A |
| Incorrect PIT importer paths | 1 | Locate the actual module with `rg --files`; do not assume a legacy filename. |
| Test command path typo | 1 | Use `.venv/bin/python`, not the `.venv/bin` directory. |
| Plan patch context mismatch | 1 | Re-read the current tails and apply the smaller exact patch. |
| MVP flow ordering test mismatch | 1 | Preserve the implementation's documented `(market, symbol)` ordering in the fixture assertion. |
| MVP protocol digest drift during construction | 1 | Regenerate the canonical sidecar after adding the frozen usable-from session. |
| MVP builder used JSON lowercase booleans | 1 | Replace them with Python booleans before the first immutable output write. |
| Verification shell reused zsh's reserved `status` variable | 1 | Use a task-specific exit variable for the untracked whitespace check. |
| Directory given to `git diff --no-index --check` | 1 | Check each new artifact file individually; directory mode is not a whitespace check. |
