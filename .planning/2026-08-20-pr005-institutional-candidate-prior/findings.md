# Findings & Decisions

## Requirements
- PR-004 is `APPROVED WITH CONDITIONS`; there is no blocking issue and PR-005 is ready to start.
- Before or within PR-005, report semantics must make `EXPLORATORY`, `strategy_ready=false`, and `production_ready=false` unambiguous.
- Do not choose a lookback after seeing diagnostics. Freeze the primary institutional factor at 5D; 1D/3D remain secondary exploratory outcome diagnostics.
- Implement only PR-005-A institutional momentum confirmation and PR-005-B foreign/trust consensus in the first version.
- Both outputs are Candidate Prior evidence, never BUY, entry eligibility, BuyScore contribution, runtime admission, or order instructions.
- `usable_from_session <= target_session` and all PIT/digest/scope poison gates from PR-004 must carry forward.

## Research Findings
- The reviewed pipeline is institutional immutable evidence -> PIT universe -> factor diagnostics -> premarket Candidate Prior -> independent realtime entry features. PR-005 owns only the Candidate Prior stage.
- PR-004 test and packaging gates were accepted: full 550 passed/1 skipped, adjacent 81 passed, focused 12 passed at 93% coverage, and isolated wheel import.
- Previous active planning pointer to restore after PR-005 is `2026-08-19-realtime-dashboard-websocket-plan`.
- The worktree contains concurrent market-event, freshness, trade-management, PR-001 through PR-004, and planning changes; edits must remain isolated to PR-004 readiness fields, a dedicated PR-005 research package/contracts/tests, and package discovery if needed.
- Root planning confirms the broader repository remains decision-support/data-first and has a separate active freshness evidence campaign. PR-005 must not consume that campaign's files or change its status.
- Session catch-up reported only one unsynced read command and no product mutation requiring recovery; the current git status remains the source of truth.
- Code-review guidance requires immutable typed contracts, specific failure codes, reuse of existing artifact seams, pure domain logic, deterministic boundary tests, and no generic strategy registry or runtime interface for two fixed hypotheses.
- Architecture review guidance favors a dedicated cohesive Candidate Prior research domain that depends on existing research artifacts, not on Dashboard, DB, broker, or execution services.
- The institutional architecture says the generic previous-day watchlist artifact and `PreviousSessionWatchlistCandidateSource` are already merged, but repository evidence contradicts that assumption: `watchlist/` currently contains only PIT universe reference/import/serialization code and no previous-session artifact, momentum watchlist implementation, repository, or candidate source.
- PR-005 therefore cannot safely "extend" a nonexistent product artifact or wire a runtime source. The smallest in-scope correction is a research-only price-momentum candidate input contract, institutional Candidate Prior artifact, and read-only projection DTO. CandidatePool/source/subscription integration remains PR-007.
- The approved institutional architecture defines the two hypotheses: momentum confirmation joins existing price-candidate membership with institutional evidence; foreign/trust consensus requires both component 5D ranks positive/non-null. It also requires price-only/flow-only/combined arms for future incremental evaluation, but PR-005 itself must not claim that evaluation passed.
- Publication cutoff/live admission fields belong to later operational admission. PR-005 should preserve target/as-of/generated lineage and mark all output non-live rather than invent a reviewed 08:30 cutoff or live eligibility.
- Existing `CandidateDiscovery` and `CandidatePool` are runtime/subscription-oriented and use mutable pool state. PR-005 will not import or extend them. Its projection is a frozen read-only DTO with artifact and entry references only.
- Existing strategy catalog definitions can represent CANDIDATE metadata, but ACTIVE/EXPERIMENTAL bindings are runtime-oriented and the review rejects a Trading Strategy interpretation. PR-005 hypothesis definitions therefore stay in the research artifact and are not registered in `strategy_catalog`.
- PR-004 already exposes PIT-gated `CrossSectionalPoint` rows. A PR-005 projector must validate the source report's canonical JSON/digest, baseline definition, PIT/scope/cross-sectional eligibility, and universe, then create a separate target-only `ROLLING_NET_SHARES_5D` factor-prior artifact that excludes future outcomes and IC.
- Proposed fixed v0 rule, stated before implementation: one component qualifies only when its 5D rolling net shares are strictly positive and its PIT percentile is at least 0.50. Momentum confirmation requires price-momentum membership plus at least one qualifying foreign/trust component; consensus requires both components to qualify. This threshold is a fixed exploratory hypothesis, not an optimized or production threshold.
- Preserve four cohort memberships for later PR-008 evaluation: eligible input universe, price-only, flow-only, and combined; consensus is an additional hypothesis membership. Only rows matching momentum confirmation and/or consensus appear in the read-only Candidate Prior projection.
- Deterministic candidate ordering will use matched-hypothesis count descending, minimum foreign/trust percentile descending, maximum component percentile descending, price rank ascending with missing last, then market/symbol. It produces a candidate rank, never a probability or BuyScore.
- PR-005 run lineage should pin the target-only factor-prior artifact, price-momentum artifact, PIT universe, calendar, and both hypothesis definitions by ID+SHA256 plus explicit target/as-of/generated timestamps. The full diagnostic report, future price bundle, and outcome bytes must not enter canonical Candidate Prior bytes; the immutable institutional dataset identity remains inside the factor prior for provenance.
- Coverage review found that PR-004 cross-sectional rows are not a complete `eligible_universe`: null/incomplete factor rows are omitted. PR-005 must therefore resolve the exact pinned `EquityUniversePort` at target session, retain every PIT eligible equity as the denominator, and treat missing primary-factor points as non-qualifying rather than silently dropping those symbols.
- The Candidate Prior artifact will retain every resolved PIT eligible row needed for later arm analysis, while its public projection emits only rows matching hypothesis A and/or B. Price candidates outside the exact resolved universe are excluded fail-closed and flagged in artifact issues.
- PR-004 needs only two new serialized readiness booleans, both permanently false in this gate. Its existing `EXPLORATORY` label remains the research-status authority; PR-005 must validate all three semantics before consuming the report.
- A missing foreign or trust component remains missing. Consensus never substitutes zero, and a component qualifies only from an explicit 5D point with positive raw flow and percentile at or above 0.50.
- Final source audit found a look-ahead lineage flaw before handoff: the full PR-004 diagnostic report contains forward outcomes/IC and therefore its digest can change when T+1/T+3/T+5 prices arrive. PR-005 must not pin that full digest. It will instead consume a canonical target-session factor-prior snapshot projected from PR-004 eligibility, immutable institutional/universe/definition lineage, and only T-session 5D cross-sectional points. Future outcome/price bytes under the same institutional input must reproduce the same factor-prior and Candidate Prior digests; a new institutional bundle produces a new prior that cannot substitute under the original run manifest.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use the approved review attachment as the PR-005 scope authority | It explicitly marks PR-005 ready and enumerates the two first-version hypotheses and forbidden integrations. |
| Prefer two explicit hypothesis definitions over an extensible strategy framework | The authorized set is fixed and small; a registry/factory/DSL would add unrequested execution-shaped complexity. |
| Add only a read-only Candidate Prior projection | The expected downstream source does not exist, and implementing CandidatePool admission would cross into PR-007. |
| Model a narrow pinned price-momentum candidate input | PR-005-A needs price-candidate membership but must not reimplement SMA/volume calculations or pretend the unimplemented generic watchlist artifact exists. |
| Use a fixed median percentile threshold with positive raw 5D flow | It is an explicit, neutral v0 research hypothesis defined before evaluation and avoids choosing a high-performing cutoff after diagnostics. |
| Keep arm membership separate from matched hypotheses | Controls remain auditable without being projected as institutional candidates. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- Review attachment: `/Users/stevehuang-work/.codex/attachments/6f37368b-ec88-4f5a-ac69-b0d9d41657c2/pasted-text.txt`
- Approved architecture: `architecture/institutional_premarket_candidate_implementation_plan.md`
