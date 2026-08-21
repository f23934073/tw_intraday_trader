# Findings & Decisions

## Requirements

- PR-003 is approved with conditions and PR-004 is explicitly ready to start.
- PR-004 must answer whether foreign/trust flow contains repeatable information; it must not define an executable strategy.
- Initial factors: foreign/trust net, positive-day count, consecutive-day count, and self-normalized flow.
- Diagnostics: coverage, null rate, daily distribution, 1D/3D/5D forward returns, rank IC, ICIR, and decay.
- Same institutional + PIT universe + price digests must reproduce the same output digest.
- Without validated PIT universe digest, raw per-symbol diagnostics may run but rank/decile/selection/formal research must be absent.
- Every report/result must be labeled `EXPLORATORY`.
- No consensus score, Top-10%-buy rule, ML, candidate strategy, watchlist/runtime/order integration, or real money.

## Research Findings

- Repository memory and current root plan preserve decision-support/no-real-money boundaries; current implementation status must still be verified from source and tests.
- The worktree contains concurrent freshness-calibration and canonical-market-pipeline changes; this task must not edit those surfaces.
- Prior active planning pointer to restore is `2026-08-19-realtime-dashboard-websocket-plan`.
- PR-003 completed a shared pinned PIT universe and fail-closed `research_members`; PR-004 should consume that port rather than duplicate universe logic.
- Python review guidance requires immutable typed result contracts, specific failure modes, deterministic boundary tests, no mutable defaults, and focused coverage rather than loosely typed dictionaries.
- Universal/architecture review guidance favors a cohesive research domain with pure functions and small dataclasses, reuse of existing digest/PIT contracts, no generic manager/service, no database/API coupling, and no strategy-registry abstraction for a fixed first factor family.
- The approved architecture fixes the baseline at exact foreign-ex-dealer and investment-trust shares, rolling positive/consecutive days, and `net / (buy + sell)` self-normalization; volume/ADV normalization, acceleration, surprise, dealer factors, consensus compression, and strategy thresholds remain deferred.
- Existing `DatasetManifest` provides a price dataset ID/digest and `HistoricalBar` can carry completed daily adjusted closes, but PR-004 should consume a narrow research price DTO rather than import the backtest engine/strategy catalog into the research domain.
- `InstitutionalFlowDaily` already carries partition identity, scope, availability, raw lineage, and exact component fields. PR-004 can validate sealed normalized rows against `InstitutionalPartitionManifest.normalized_sha256` without changing PR-001/002 contracts.
- The PR-003 `EquityUniversePort.resolve(session)` returns pinned content digest, active records, research members, and explicit PIT gates. A single bad/missing PIT session should fail closed for the entire run's cross-sectional output while leaving per-symbol diagnostics visible.
- No reusable rank-IC/ICIR implementation exists. Existing percentile helpers are float/market-health specific, so PR-004 needs a small Decimal-only research statistics module rather than coupling to realtime freshness or feature engines.
- Full-suite baseline collection is currently blocked by an unrelated concurrent `tests/test_market_event_journal.py` importing the not-yet-present `market_data.journal`. Do not patch or work around that scope; retain focused PR-004 regression evidence and retry the full suite at delivery.
- Availability timing is explicit: a partition's factor point is dated on `usable_from_session`, not its source `session_date`. Five-session windows use only sealed source partitions available by that target session, and daily forward outcomes begin at the target session close.
- One PIT failure poisons cross-sectional output for the entire report. A partial report cannot silently mix eligible and ineligible dates while retaining rank/IC claims.
- A source-session-only rolling window was insufficient for delayed publications. The factor engine now requires each source partition in the five-session window to satisfy `usable_from_session <= factor target session`; a poison test proves a delayed partition stays null rather than leaking into the factor.
- Canonical Decimal text was initially sensitive to the caller's global precision. The application boundary now fixes precision at 36 digits, and the golden report is byte-identical even when the caller uses precision 9.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Create a dedicated `institutional_research` package | Keeps research-only factor/report code separate from `institutional_data`, `watchlist`, backtest execution, and runtime/trading packages. |
| Use a narrow `DailyAdjustedClose` input | Makes price outcome semantics explicit and avoids importing the backtest engine/strategy catalog into the research domain. |
| Use `ResearchRunManifestV0` with price/institutional/universe/factor-definition identities | Meets the approved reproducibility gate while keeping formal composite lineage explicitly out of scope. |
| Use fixed baseline definition v0 | Components, five-session lookback, and 1D/3D/5D horizons are code-owned and digest-pinned; no optimizer or threshold configuration is added. |
| Emit per-symbol points separately from PIT-gated cross-sectional diagnostics | Missing PIT can still expose raw/time-series diagnostics without leaking ranks, percentiles, deciles, outcomes, or IC. |
| Compute all statistics with `Decimal` | Avoids binary-float drift in canonical report bytes and repeated-run digests. |
| Keep formal eligibility false | PR-004 has no `CompositeResearchInputManifest`, preregistration, holdout, cost, or strategy definition; every result remains `EXPLORATORY`. |
| Use nearest-rank distribution percentiles and average-tie Spearman ranks | The rules are deterministic with `Decimal` and can be documented/tested without a scientific-computing dependency. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Full baseline collection failed on missing concurrent `market_data.journal` | Record as an external worktree blocker; do not edit canonical market journal work. Retry later after the concurrent owner completes it. |
| First delayed-partition test rebuilt row bytes but retained the old normalized digest | Recomputed only the affected partition manifest digest; input validation correctly rejected the inconsistent fixture before factor execution. |
| Project virtualenv cannot import the configured setuptools build backend | Used system Python's already-installed setuptools without build isolation or downloads; verified all eight research package files and an isolated wheel import. |

## Resources

- PR-003 review attachment: `/Users/stevehuang-work/.codex/attachments/b62b91f1-6f66-4042-ac87-799ad83fe647/pasted-text.txt`
- Approved architecture: `architecture/institutional_premarket_candidate_implementation_plan.md`
