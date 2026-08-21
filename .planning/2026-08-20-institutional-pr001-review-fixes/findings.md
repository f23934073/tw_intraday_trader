# Findings & Decisions

## Requirements

- Add a dedicated `PR-003 PIT Equity Universe Foundation` and renumber later PRs.
- PIT ownership must cover symbol, market, security type, listing interval, date-effective industry and market cap, effective interval, and source digest.
- Freeze `PIT_UNIVERSE_MISSING`: raw/per-symbol time-series diagnostics allowed; cross-sectional ranking, compression, neutralization, matched controls, and formal research blocked.
- `ResearchRunManifest v0` must carry ID plus digest for price, institutional, and universe datasets, and version plus digest for strategy definitions.
- Dealer total/component validation must distinguish PASS, FAIL, NOT_APPLICABLE, and UNKNOWN_COMPONENT without quarantining unsplit-but-valid source rows.
- Resolve the document status contradiction through actual code review and exit-gate evidence.
- Keep PR-002 on HOLD; do not implement an adapter, schema, strategy, CandidatePool, API, UI, or trading path.

## Research Findings

- The review retains Candidate Prior versus BuyScore separation, a single watchlist pipeline, fail-closed scope mismatch, and full-universe/matched-control evidence requirements.
- Repository memory confirms this checkout is a decision-support system and real-money paths remain out of scope.
- Another repository's T86 implementation is context only; its aggregate equality is not a substitute for this PR's dealer-component NULL contract.
- Universal review guidance supports a typed enum rather than magic validation strings and cautions against redundant derived state.
- Python review guidance favors immutable dataclasses/default factories, precise types, edge-case tests, and specific failure semantics; the reconciliation result should therefore be a frozen typed value rather than an unstructured message.
- The supplied review is fully read: the only architectural blocker is promotion of PIT equity universe work into an explicit PR and exit gate; it explicitly instructs retaining the T-1 prior to T-day realtime confirmation boundary and not adding institutional rank to BuyScore.
- Current `validate_flow_row()` silently skips every optional component formula and the dealer split reconciliation when values are absent; callers receive no way to distinguish unknown data from a passed check.
- Current `ValidationReport` contains only issues, and `validate_partition()` discards any non-issue row metadata. A typed check tuple must therefore be aggregated at both row and partition levels if statuses are to be observable downstream.
- Domain construction already guarantees each optional buy/sell/net triplet is all present or all absent. It permits proprietary present with hedge absent (and vice versa), so dealer split reconciliation must be NOT_APPLICABLE whenever either group is unavailable.
- Serialization already preserves optional components as JSON null and validates strict fields; no flow schema change is needed for this review fix.
- The plan currently assigns feature research to PR-003 despite marking PIT rank as blocked, uses ID-only `ResearchRunManifest v0`, and ends with stale text saying review only approved starting PR-001.
- The existing previous-day watchlist plan already defines `EquityUniversePort` with DATE_EFFECTIVE versus CURRENT_SNAPSHOT evidence levels. New PR-003 must implement/extend that shared contract and its reference-data ownership, not create a second institutional-only universe subsystem.
- Re-review found one minor stringly-typed detail in the new code: a multi-field dealer mismatch was joined into the singular `ValidationCheck.field`. Individual issues already carry the exact fields, so the aggregate check should leave `field=None` instead of inventing a comma-delimited field name.
- The offline pip wheel command regenerated tracked `.egg-info` from the whole current dirty worktree and created `build/`. These generated changes are verification side effects, not PR-001 source; restore only the four previously clean egg-info files and remove only the newly generated build directory.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Expose typed reconciliation results on `ValidationReport` | Callers need to distinguish unknown/not-applicable from validation failure without parsing strings. |
| Keep `ValidationReport.is_valid` issue-based | NOT_APPLICABLE and UNKNOWN_COMPONENT are evidence states, not reasons to quarantine a valid row. |
| Represent the dealer split check separately from each component's buy-sell formula | A missing optional component differs semantically from a failed formula. |
| Preserve existing callers with a default empty reconciliation tuple | The new result data should be backwards compatible. |
| Put `ValidationStatus` and `ValidationCheck` in the validation module | These are validation outputs, not source-row data and do not belong in the serialized domain schema. |
| Aggregate row checks into partition reports | Partition validation is the normal gate and must not hide UNKNOWN_COMPONENT or NOT_APPLICABLE evidence. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Review-guide output was truncated when two long references were read together | Re-read each required reference in bounded chunks before editing code. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/3ab881c0-b649-46ab-a342-2d954f4019d8/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/architecture/institutional_premarket_candidate_implementation_plan.md`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/institutional_data/`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/tests/test_institutional_*.py`
