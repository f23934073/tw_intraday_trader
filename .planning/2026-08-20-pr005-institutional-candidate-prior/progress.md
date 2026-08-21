# Progress Log

## Session: 2026-08-20

### Current Status
- **Phase:** completed - awaiting PR-005 review gate
- **Started:** 2026-08-20

### Actions Taken
- Read the complete PR-004 review: approved with three non-blocking conditions and explicit authorization for PR-005.
- Activated code-review, file-based planning, and surgical implementation guidance.
- Created an isolated PR-005 plan and froze scope to two Candidate Prior hypotheses with no execution integration.
- Restored root planning/memory context and recorded the concurrent freshness campaign and decision-support/no-real-money boundaries.
- Completed the Python review reference. Typed immutable dataclasses, specific exceptions, exact boundary tests, modern annotations, and focused coverage are required for PR-005.
- Completed the universal quality reference. The design will reuse canonical serialization/artifact contracts, use enums instead of magic strings, keep parameter objects bounded, avoid redundant readiness state where derivable, and fail closed at immutable identity boundaries.
- Completed the architecture review reference. PR-005 will use a small domain/application/serialization split, no DB/web/framework dependency, no strategy registry/factory, and no interface with only one implementation.
- Inspected the approved institutional/previous-day plans and current source. Confirmed the documented previous-session watchlist dependency is plan-only, so PR-005 will stop at an immutable research artifact and read-only projection rather than crossing into runtime admission.
- Completed Phase 1 discovery and froze the v0 rules, ranking, input lineage, cohort memberships, PR-004 condition fields, and protected runtime boundaries before coding.
- Began Phase 2 with the contract split fixed as: a narrow pinned price-momentum input, two explicit v0 hypothesis definitions, one immutable Candidate Prior artifact, and one matched-only read projection.
- Added PR-004's explicit false readiness fields and updated its canonical report contract.
- Added the isolated `institutional_prior` bounded package with frozen 5D hypothesis definitions, pinned price-prior/run manifests, immutable cohort/candidate artifacts, canonical digests, and a read-only non-live projection.
- Implemented the A/B hypothesis builder over PR-004 PIT cross-sectional 5D points. It preserves complete eligible/price/institutional/combined memberships, excludes unprovable price rows fail-closed, and never imports CandidatePool, BuyScore, subscriptions, broker, or runtime code.
- Focused coverage reached 91% for application logic and exposed one semantic gap before adjacent testing: PR-004 cross-sectional points omit null factors, so they cannot serve as the complete eligible-universe denominator. The builder will now require and validate the pinned PIT universe port directly.
- Final source audit exposed a second look-ahead lineage gap: pinning the entire PR-004 report would make PR-005 output sensitive to future forward-outcome bytes. Verification is reopened to introduce a target-only factor-prior snapshot and prove future-data invariance before final review.
- Replaced the direct full-report dependency in the PR-005 contracts/application with a canonical `InstitutionalFactorPriorArtifact`. The projector validates PR-004 bytes/readiness/PIT/definition, then serializes only target-session 5D cross-sectional points plus immutable institutional/universe/definition lineage; it excludes forward outcomes, IC, price bundle, and full report digest. A later institutional bundle receives a new identity and is rejected under the original run manifest.
- Completed the final scope audit, restored tracked egg-info bytes, moved generated `build/` output to `/tmp`, preserved all concurrent worktree edits, and restored `.planning/.active_plan` to `2026-08-19-realtime-dashboard-websocket-plan`.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `.venv/bin/pytest -q tests/test_institutional_factor_diagnostics.py` | Existing PR-004 baseline remains green before edits | 12 passed in 0.17s | PASS |
| PR-004 focused run after readiness fields | New canonical digest should require a golden update only | 11 passed, 1 expected golden-digest failure; new digest `209168...6265` | EXPECTED UPDATE |
| PR-005 + PR-004 focused tests, first run | Only placeholder goldens should fail | 20 passed, 2 placeholder-digest failures; captured both definition digests and artifact digest | EXPECTED UPDATE |
| PR-005 focused coverage before universe-port correction | Inspect untested poison boundaries and denominator completeness | 10 passed; application 91%, package 86%; found incomplete eligible-universe derivation | DESIGN CORRECTION |
| PR-005 + PR-004 focused after denominator correction | Candidate rules, PR-004 conditions, lineage, and readiness stay green | 37 passed in 0.26s | PASS |
| PR-005 focused coverage final | Meet focused contract/poison-gate coverage target | 25 passed; package 90%, application 93%, serialization 97% | PASS |
| Institutional/PIT adjacent regression | PR-001 through PR-004 and shared PIT contracts remain green | 106 passed in 0.40s | PASS |
| Full regression | Entire concurrent worktree remains green | 602 passed, 1 skipped in 2.19s | PASS |
| Isolated wheel build/import | Wheel contains and imports the new package outside checkout | Built SHA256 `1337f5...3b9a`; isolated import found 2 definitions | PASS |
| Compile/import/forbidden-dependency audit | No syntax error or runtime/execution coupling | Compileall passed; imports limited to data/research/watchlist PIT contracts; no runtime/CandidatePool/BuyScore dependency | PASS |
| Future-outcome invariance correction | Appending post-target report points and changing full price/institutional bundle identities must not alter the target factor prior or Candidate Prior | Source report digest changed; factor-prior JSON/digest and final Candidate Prior JSON/digest stayed identical | PASS |
| PR-005 focused coverage after factor-prior split | Restore focused review coverage after adding the safe projection seam | 31 passed; package 90%, application 93%, serialization 97% | PASS |
| Institutional/PIT regression after factor-prior split | All upstream and PR-005 contracts remain green | 112 passed in 0.30s | PASS |
| Full regression after factor-prior split | Entire concurrent worktree remains green | 630 passed, 1 skipped in 2.00s | PASS |
| Final isolated wheel/import | Final look-ahead-safe source is packaged and importable outside checkout | Wheel SHA256 `2ec0fe...527a`; isolated import exposed projector and 2 definitions | PASS |
| Final Ruff gate | New PR-005 scope and touched PR-004 files are lint/format clean | New scope `ruff check` passed; all touched files format clean; PR-004 pre-existing I001/BLE001 excluded from behavioral lint | PASS |

### Errors
| Error | Resolution |
|-------|------------|
| Global `pytest` was not on `PATH` | Use the existing project environment at `.venv/bin/pytest`; no dependency or environment mutation was needed. |
| `.venv/bin/ruff` is absent | Keep compile/test gates running and report lint as unavailable unless an existing non-mutating runner is found. |
| Isolated wheel build initially could not download `setuptools` | Retried with approved network access; wheel build then passed. |
| Local final wheel build without isolation lacked `setuptools.build_meta` and created workspace build/egg-info side effects | Rebuilt successfully with isolated dependencies, then restore tracked egg-info bytes and move the generated build directory out of the workspace before handoff. |
| A later full-suite retry hit a concurrent, incomplete `tests/test_thesis_monitor.py` whose `trading.thesis_monitor` module did not yet exist | Preserve that other scope, keep PR-005 adjacent/focused evidence, and retry after the concurrent writer finishes; do not modify its files. |
| Exact final wheel/import after institutional-lineage pin | Packaged code includes the final provenance field and both definitions | Wheel SHA256 `d56a5d...dfa7`; isolated site-packages import showed `institutional_dataset` in `InstitutionalFactorPrior` and 2 definitions | PASS |
| Unfiltered final full suite after concurrent thesis module completed | Entire current worktree remains green without ignores | 656 passed, 1 skipped in 2.20s | PASS |
