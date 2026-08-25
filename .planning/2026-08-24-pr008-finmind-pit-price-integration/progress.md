# Progress Log: PR-008 FinMind PIT Price Integration

## 2026-08-24 — session start

- User authorized handling the safe FinMind-to-PR-008 integration after review
  of the separate three-year acquisition and historical-backtest readiness
  tasks.
- Created an isolated plan without changing `.planning/.active_plan`, which is
  owned by concurrent work.
- Confirmed the initial boundary: use the existing FinMind artifact only as
  engineering/reference evidence; preserve PR-008's unobserved formal outcome.
- Inspected existing PR-008 acquisition/coverage contracts and the current
  FinMind manifest only. The source remains `CURRENT_SNAPSHOT`,
  `research_eligible=false`, partial-market, raw-price, and outcome-observed.
- Selected an additive artifact-plus-drift-test seam. The existing PR-008
  acquisition manifest stays unchanged and its formal price status remains
  `MISSING`.
- Added immutable FinMind engineering-reference registration and a separate
  PIT price-acquisition contract. Both keep every execution permission false;
  neither reads data payloads nor modifies the existing Dataset.
- Added digest sidecars and a focused drift-gate test. The focused integration,
  acquisition, coverage, and Sponsor-probe suite passed: `18 passed`.
- Completed verification: expanded focused suite `31 passed`; Ruff, JSON parse,
  Python compilation, canonical digest validation, and whitespace checks all
  passed. No provider request, data-payload/outcome read, backtest, or gate
  unlock occurred.
- Corrected the artifact registration timestamp to its observed local creation
  time and recalculated the registration and dependent-contract digests before
  rerunning final validation.

## 2026-08-24 — Phase 5 start

- User authorized continuation. Restored the isolated plan after the planning
  skill detected the prior FinMind handoff as unsynced context.
- Confirmed the shared worktree remains materially dirty outside this scope;
  no unrelated file will be modified or staged.
- Chose PIT universe/reference acquisition readiness as the next blocker. The
  repository has strict PIT import/validation code but no sealed production PIT
  snapshot outside fixtures.
- Verified that the importer enforces true date-effective records and rejects a
  current snapshot. The next decision is source resolution, not synthetic
  artifact generation.
- Completed primary-source review: official public pages are insufficient for a
  complete PIT universe, while TEJ is the first credible supporting candidate.
  Next step is a secret-safe local entitlement inventory before any source call.
- Confirmed no TEJ/TQuant credential name is present locally without reading a
  credential value. Added the immutable PIT/reference source-resolution
  artifact and its drift gate; both retain every acquisition and formal gate
  closed.
- Verified the new gate and upstream PIT/reference boundaries: `46 passed`,
  Ruff, JSON parse, Python compilation, canonical digest, and whitespace check
  passed. No current-snapshot surrogate, provider request, price/outcome read,
  or PR-008 unlock occurred.

## 2026-08-24 — Phase 6 entitlement preflight

- Received authorization for the bounded metadata-only TEJ/TQuant
  qualification.
- Rechecked local credential names without reading values; none is present.
  Qualification remains blocked pending a provisioned TEJ/TQuant credential.

## 2026-08-24 — Phase 7 FinMind qualification start

- User authorized use of FinMind instead of waiting for TEJ/TQuant. Restored
  current planning context and inspected the existing FinMind client/capture
  path without provider access.
- The new qualification will use a distinct frozen protocol and staging path;
  it will not invoke the existing KBar downloader, read price payloads, or
  alter FinMind acquisition checkpoints.
- Added and digest-froze the separate PIT/reference-only FinMind protocol plus
  its capture utility and drift gates. It makes eight allowlisted reference
  requests only after a credential and quota preflight, reserves 100 requests,
  preserves no credential value, and reports only envelope/schema/date-range
  summaries.
- Focused local validation passed: `11 passed`; Python compilation and the
  canonical protocol digest check passed. No provider request had occurred at
  that point.

## 2026-08-24 — Phase 7 FinMind qualification complete

- Ran the frozen Sponsor quota preflight with a secret-safe token path: 2,246
  requests remained, satisfying the eight-request probe plus a 100-request
  reserve.
- Captured and sealed all eight allowlisted reference requests in a distinct
  immutable directory. All returned HTTP 200 / JSON status 200 with a data
  array. No forbidden price, KBar, adjusted-price, or tick dataset was
  requested.
- Verified the capture-manifest digest and each raw-response byte hash without
  parsing raw provider rows. Generated an immutable result from manifest
  metadata only. It verifies bounded authentication/dataset entitlement but
  remains `INSUFFICIENT_EVIDENCE` for a formal PIT/reference source.
- Completed verification: `75 passed` across focused PR-008/PIT/FinMind tests;
  workspace Ruff, Python compilation, JSON parsing, canonical digest checks,
  and whitespace checks passed. All formal execution locks remain false.

## 2026-08-24 — Phase 8 FinMind semantics/terms start

- User asked to continue. Restored the completed bounded-probe result and the
  strict PIT requirements before deciding the next request set.
- The first direct path lookup used legacy filenames and failed; this is logged
  as a non-provider discovery error. The next step is to locate the actual
  importer module rather than retrying an assumed path.
- Located the actual strict PIT contract in `watchlist/reference_data.py` and
  reviewed FinMind's official API documentation. Documentary evidence confirms
  that the first probe cannot prove all required PIT intervals or terms; no
  additional FinMind request has been made.
- Added immutable `FinMindPITReferenceSemanticsResolutionV1` rather than a
  second provider probe. Official documented current-industry semantics are
  incompatible with PR-008 PIT requirements; missing listing/transfer and
  source-term evidence reinforces the narrow formal-PIT rejection.
- Verified the artifact and its prior boundaries: expanded focused suite
  `78 passed`, Ruff, Python compilation, JSON, canonical digest, and
  whitespace checks passed. No provider quota was spent during Phase 8, and
  every formal gate remains locked.

## 2026-08-24 — Phase 9 FinMind MVP start

- User changed the objective from a full formal research-data foundation to a
  practical FinMind MVP. Added an explicit separate MVP phase; the original
  PR-008 protocol and all formal gates remain untouched.
- Inspected existing source/candidate seams. The MVP will use a separate
  FinMind normalization path rather than weakening the official TWSE/TPEx
  institutional contract or formal candidate prior.
- Froze and locally verified the FinMind institutional MVP contract and
  isolated parser/candidate tests. Usage preflight passed with 3,351 requests;
  the two-request immutable MVP capture completed successfully.
- The captured flow response is one date but contains 20,529 rows, so the
  initial one-row-per-symbol parser is intentionally blocked on duplicate
  symbols. Next is a metadata/structure audit before defining any aggregation.
- Audit confirms every flow `stock_id` is unique; 2,267 map to current
  TWSE/TPEx records. r1's zero-candidate dry run exposed the modern FinMind
  dealer-component split. Preserve r1 and create a separate r2 candidate
  policy using the documented dealer total rather than retrying the provider.
- Confirmed the r2 total must include legacy, self, and hedging dealer net
  components. The next implementation step is local-only parsing and artifact
  building from the sealed capture; it will make no additional provider call.
- Corrected the implementation rule after a local-only encoding audit: use
  self-plus-hedging when present, otherwise the legacy pair. This avoids
  double-counting the 703 rows where FinMind's legacy fields duplicate the
  component values.
- Added an r1 superseded zero-observation record, a digest-frozen r2 component
  fallback policy, and an immutable local-only builder. The r2 build sealed a
  17-symbol post-close candidate observation from 2,267 current-mapped rows;
  it made no provider call and read no price, return, PnL, or holdout data.
- Focused parser/capture tests passed (`8 passed`), artifact/capture/policy/
  result canonical hashes passed, and compilation passed. Ruff was not
  executed because no Ruff binary is available in the present environment.
- Added a replay drift gate for the sealed candidate observation. The final
  focused MVP plus formal-boundary selection passed (`16 passed`); Python
  compilation and tracked/untracked whitespace checks also passed. The
  intermediate verification-shell errors were corrected before final checks.
