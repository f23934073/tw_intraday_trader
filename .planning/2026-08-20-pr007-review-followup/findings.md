# Findings & Decisions

## Requirements
- PR-007 result is `APPROVED WITH CONDITIONS`; PR-008 Formal Evaluation is `READY TO START`.
- Preserve: shadow admission is not a trading signal, CandidatePool admission is not an entry decision, and Institutional Prior is not BuyScore.
- PR-007 result should explicitly state `mode=SHADOW`, `subscription=false`, and `execution_allowed=false`.
- Shadow admission metrics may include candidate counts, rejection reasons, capacity conflicts, and source overlap; they must not include win rate, profit, expectancy, PnL, or other strategy-performance fields.
- Capacity output must be deterministic for identical inputs/config and must pin `admission_policy_version` in its digest.
- PR-008 must freeze the CandidatePool <- PreviousSessionWatchlistCandidateSource boundary and must not route institutional factors into BuyScore.
- Evaluation arms must preserve `ELIGIBLE_UNIVERSE`, `PRICE_ONLY`, `INSTITUTIONAL_ONLY`, `COMBINED`, and `MATCHED_CONTROL`.
- Primary question: under identical intraday setup and cost definitions, does the institutional prior improve candidate quality or net expectancy versus price-only?

## Research Findings
- The reviewer approved the source adapter, T-day eligibility, bounded evidence reference, protected-capacity logic, stopping before SubscriptionManager, and unchanged scoring contract.
- Existing verification accepted by the reviewer: focused 33 passed, 95% coverage, full 743 passed/2 skipped, and wheel pass.
- PostgreSQL repository verification remains recommended before PR-008 but non-blocking; current environment previously lacked `TEST_POSTGRES_DSN`.
- The supplied attachment ends at line 670 immediately after introducing the strict PR-008 principle; no additional text follows.
- Repository search found no existing PR-008 evaluation artifact/module. Existing `backtest/metrics.py` reports generic trading metrics, while Candidate Prior explicitly forbids performance fields; PR-008 therefore needs a separately versioned evaluation bounded context/artifact.
- The architecture requires full PIT denominator or pre-frozen matched controls, deterministic three-arm comparisons, identical setup/outcome/cost definitions, time-based train/validation/untouched holdout, and a preregistered gate before looking at holdout.
- `TEST_POSTGRES_DSN` is still absent, so the recommended real PostgreSQL repository verification remains unavailable and non-blocking.
- The worktree remains heavily concurrent; PR-008 must use new files plus only surgical PR-007 condition edits.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Do not interpret `admitted=true` as monitoring or execution | PR-007 is a pure shadow decision with no subscription side effect. |
| Separate candidate-quality and execution-quality conclusions | This prevents a better candidate shortlist from being confused with changed entry/exit logic. |
| Create a separately versioned evaluation artifact rather than adding metrics to Candidate Prior | The Candidate Prior v0 schema is frozen and explicitly rejects performance fields. |
| Compare frozen overlapping cohorts, not rewrite Candidate Prior memberships | `COMBINED` remains the price/institutional intersection and `MATCHED_CONTROL` remains non-institutional. |
| Use session-clustered confidence intervals | Same-session symbols are dependent; row-level independent intervals would overstate evidence. |
| Keep owner-selected thresholds mandatory and digest-pinned | Confidence level, samples, turnover, and guardrails must be frozen before holdout rather than selected after results. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `python` command was unavailable | Used the repository `.venv/bin/python` interpreter. |
| Black and Ruff are not installed in the project venv | Used compile checks, test execution, and manual line-length inspection; no dependency was added. |

## Resources
- `/Users/stevehuang-work/.codex/attachments/bc08e59f-fb9a-4636-9268-4539ce480bcc/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/.planning/2026-08-20-pr007-review-followup/`
