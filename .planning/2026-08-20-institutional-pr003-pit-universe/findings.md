# Findings & Decisions

## Requirements

- PR-002 is approved with two conditions: freeze `InstitutionalPartitionManifest v1` and add `institutional_source_coverage.md`.
- PR-003 is authorized as the next stage, but PR-004 Factor Diagnostics and PR-005 Candidate Strategy must remain blocked.
- PIT records must represent symbol, market, security type, listing interval, date-effective industry, and date-effective market-cap evidence.
- Historical queries must retain delisted/disappeared symbols and must not apply current classifications to older sessions.
- The universe foundation must be shared with the existing previous-day watchlist boundary, not placed under `institutional_data` as a private subsystem.
- `CURRENT_SNAPSHOT` remains explicitly `research_eligible=false`.
- Real-money execution remains prohibited.

## Research Findings

- Repository memory requires decision-support/no-real-money boundaries and semantic verification rather than compilation-only evidence.
- Root planning confirms the previous-day watchlist design already requires a date-effective universe and explicitly rejects inferring historical common-stock eligibility from current `InstrumentReferenceStore` rows.
- Existing `market_data/instrument_reference.py` is a current-session operational reference seam, not a PIT historical universe.
- The worktree is actively changing in unrelated canonical-market-pipeline, freshness-calibration, and trade-management scopes. Preserve all concurrent `market_data/*`, root planning, and non-institutional test changes.
- Relevant stable surfaces to inspect next are the previous-day watchlist implementation plan, `InstrumentReferenceStore`, current premarket contracts, and institutional manifest serialization tests.
- Session catch-up found only one unsynced tool event; no missing PR-003 implementation exists.
- Approved architecture fixes the gate code as `PIT_UNIVERSE_MISSING` and requires current-snapshot inputs to stay `research_eligible=false`; missing PIT evidence blocks cross-sectional rank, matched controls, watchlist compression, and formal research.
- Historical PIT eligibility and current-session subscription eligibility are distinct: PR-003 must not replace `InstrumentReferenceStore.eligible()` in runtime admission.
- A research manifest must retain universe artifact ID plus digest; an ID alone is insufficient lineage.
- Shared contracts may be developed before watchlist runtime exists, but no duplicate calendar/universe abstraction may be created under `institutional_data`.
- Code-review guidance reinforces a small domain contract plus injected query/catalog boundary, avoiding a large manager/service or speculative persistence layer.
- The selected Python/universal review references add concrete implementation constraints: typed immutable contracts, explicit enums instead of magic strings, narrow exception handling, deterministic boundary tests, and reuse of existing canonical digest conventions where domain ownership permits it.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Place PR-003 under a shared `watchlist` boundary, not `institutional_data` | Both approved plans name `EquityUniversePort` as previous-day watchlist reference data; no implementation exists yet, so PR-003 creates only that shared foundation. |
| Keep runtime eligibility separate | `CURRENT_SNAPSHOT` is an evidence mode for research readiness and cannot replace `InstrumentReferenceStore.eligible()` for live subscription admission. |
| Freeze PR-002 with public field/status constants, contract documentation, and golden tests | Exact-field deserialization already fails closed; explicit public constants and a golden digest make accidental v1 drift review-visible. |
| Model source coverage and correction limitations in documentation, not speculative adapter code | The approved condition explicitly requests a matrix, while current adapters already enforce reviewed endpoint, schema, session date, scope notes, and immutable raw evidence. |
| Create `watchlist/reference_data.py` as the shared PR-003 seam | This is the exact file/boundary named by the previous-day watchlist plan. It avoids coupling general PIT reference data to institutional source types. |
| Do not reuse `InstrumentReferenceStore` | It is intentionally current-session and clears at session rollover; PIT history, delisted retention, classifications, and market-cap observations require a separate immutable artifact/query contract. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Planning template replacement patch was rejected | Used targeted updates and recorded the error. |

## Resources

- PR-002 review attachment: `/Users/stevehuang-work/.codex/attachments/4c526d60-70d5-4ee2-84aa-08812c2b923a/pasted-text.txt`
