# Findings & Decisions

## Requirements

- Implement TWSE and TPEx adapters, immutable raw capture, fixture replay, and normalized PR-001 artifacts.
- Quarantine wrong-session responses, schema drift, empty responses, scope mismatch, and formula errors.
- Raw bytes and SHA-256 must remain available even when parsing fails.
- Same market/session/scope with changed content creates a new revision; never overwrite.
- Do not implement feature calculation, ranking, watchlist generation, CandidatePool integration, persistence migration, PR-003 PIT universe, API, UI, or broker behavior.
- Retain Real Money prohibited and Candidate Prior versus Entry separation.
- Rename PR-004 to Institutional Factor Diagnostics and PR-005 to Premarket Candidate Strategy Research in the plan.

## Research Findings

- The approved attachment explicitly authorizes `PR-002 — Official Source Adapter Implementation`.
- It defines the adapter boundary as `Official Source -> Institutional Artifact`.
- The three additional exit gates are date pollution, raw immutability after parse failure, and immutable source revisions.
- PR-001 already supplies strict canonical flow/manifest serialization, SHA-256, formula validation, optional-component semantics, and partition identity checks; PR-002 should compose these rather than duplicate them.
- Existing repository artifact code uses content-addressed IDs, append-only `setdefault` semantics, locks, and fail-closed rehydration. PR-002 can reuse those design principles without importing the separate premarket bounded context.
- The current worktree gained unrelated P1 canonical-event planning files in addition to Freshness changes; preserve all of them.
- No institutional raw/source adapter fixtures exist yet; current institutional fixtures start at normalized PR-001 JSON.
- Official TPEx OpenAPI advertises `GET /tpex_3insti_daily_trading` as the per-stock three-institution daily detail source; the official detail page also states the published total formula and original-trade correction policy already modeled by PR-001.
- TPEx's public page documents history availability and confirms foreign dealer amounts are already counted under dealer totals, so must not be double-counted.
- Direct web-tool opens of the Swagger/raw endpoint were blocked by the sites' access/safe-URL behavior; use official endpoint responses through approved shell/network only if needed, while preserving fixture-first acceptance.
- A read-only official TWSE probe confirmed the historical JSON response shape: `stat`, `date`, `title`, `hints`, `fields`, and `data`; T86 has 19 ordered columns and comma-formatted share strings.
- The official TWSE response includes ETFs and other non-ordinary-equity symbols, confirming PR-002 must normalize source data without pretending PIT equity eligibility.
- The official TPEx Swagger confirms `GET /tpex_3insti_daily_trading`, tagged as `上櫃股票三大法人買賣明細資訊`, with JSON/CSV responses using the OpenAPI component schema of the same name.
- The exact TPEx component has 20 string fields and the live official endpoint currently returns a top-level list; dates use ROC `YYYMMDD` such as `1150819`, and numeric shares are plain signed digit strings.
- TPEx provides foreign ex-dealer, foreign dealer, trust, dealer total buy/sell/net, and published total. It does not provide a complete proprietary/hedge triplet, so PR-002 must set those optional PR-001 fields to null rather than infer them from the oddly named extra dealer field.
- The official TWSE T86 shape provides proprietary and hedge triplets plus dealer total net; dealer total buy/sell can be exactly derived as the sum of those published component buy/sell values and reconciled against the published dealer net.
- The implementation plan freezes `TWSE_T86_FINAL_WITH_BLOCK_V1` and `TPEX_DAILY_ORIGINAL_TRADES_V1`; PR-002 must reject caller scope IDs that do not match the adapter contract.
- The official TPEx historical page source references `insti/dailyTrade`; OpenAPI remains a latest cross-check rather than the canonical historical source.
- Existing network code uses fixed HTTPS URLs with stdlib `urllib.request`; PR-002 can follow that dependency-free pattern while keeping fetch transport injectable for tests.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Inspect existing artifact/catalog patterns before designing new files | Reuse repository conventions and avoid a second persistence architecture. |
| Fixture-first, no live fetch required for acceptance | Official endpoints are volatile and network access is not needed to prove parser/capture semantics. |
| Keep new artifact/revision code inside `institutional_data` | Reuse behavior, not the unrelated `premarket` domain namespace. |
| Treat official field sets as parser-version contracts | Missing or unexpected source fields are schema drift and must quarantine. |
| Do not infer TPEx dealer component splits | The official OpenAPI response lacks complete proprietary/hedge triplets; unknown must remain null. |
| Make `usable_from_session` an application input | PR-002 has no approved trading-calendar implementation and must not guess next sessions with calendar-day arithmetic. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Official Swagger/direct endpoint opens returned 403 or safe-URL errors | Record the official endpoint discovery and continue with primary official pages/search; use a read-only HTTP probe only if schema fields remain unresolved. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/e8876e75-3161-4742-82c5-da8ab8105886/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/architecture/institutional_premarket_candidate_implementation_plan.md`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/institutional_data/`
# TPEx historical endpoint discovery update

- The official daily-detail page declares the logical action `insti/dailyTrade`; the first `global.js` probe did not expose `API_PATTERN`, so URL construction must be traced through the page's table runtime before freezing the production endpoint.
- Do not substitute the latest-only OpenAPI feed for the canonical historical adapter. It may be retained only as a latest-session reconciliation source.
- `tables.js` builds `apiAction` by replacing `{LANG}` and `{ACTION}` in the page-supplied pattern, then sends a POST with form fields plus `response=json`. The page therefore consumes a session-addressable POST API, not the latest-only OpenAPI endpoint.
- The canonical TPEx form contract is now exact: `type=Daily`, `sect=EW` for all securities excluding warrants and bull/bear certificates, and `date=YYYYMMDD`. The rendered table has 24 modern columns and the endpoint returns a two-table envelope for old/new schema eras.
- `API_PATTERN` resolves to `/www/{LANG}/{ACTION}`, so the production historical route is `POST https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade`.
- A live 2026-08-19 probe returned `stat` implicitly absent but a top-level `columnNum=25`, `tables`, table `date=115/08/19`, 24 fields and 24-value rows. The modern table indexes are: symbol/name; foreign-ex-dealer triplet; foreign-dealer triplet; combined-foreign triplet; trust triplet; dealer-proprietary triplet; dealer-hedge triplet; dealer-total triplet; published total.
- PR-001 already supplies immutable normalized row/manifest contracts, deterministic canonical JSON and formula/partition validation. PR-002 can stay surgical by adding acquisition/artifact/adapter boundaries and composing the existing validators.
- Existing normalized contracts require a caller-provided `usable_from_session` strictly after the source session; adapters must accept it explicitly and must not invent a trading calendar rule.
- Packaging already includes `institutional_data*`; PR-002 needs no dependency change. The production HTTP client can follow the repository's fixed-HTTPS `urllib.request` convention and remain dependency-free.
- Raw storage must key revisions by market/session/source-product/scope while identity is content-addressed. Identical bytes should deduplicate; different bytes for the same logical key must append a new revision.
- The approved source scopes are `TWSE_T86_FINAL_WITH_BLOCK_V1` and `TPEX_DAILY_ORIGINAL_TRADES_V1`. TWSE uses final data with block trades; TPEx uses the `EW` product and original-trade correction policy.
- PR-001 tests use plain immutable dataclasses and focused fixture helpers. PR-002 tests should follow that style, avoiding mocks where an injected replay transport or raw bytes suffice.
- The final approval explicitly requires raw evidence to survive parser failure and differing content for the same logical source key to append `revision++`; PR-002 must therefore include an immutable raw artifact store boundary even though database persistence remains deferred to PR-006.
- TWSE exact envelope keys are `data,date,fields,hints,notes,selectType,stat,title,total`; live sample has 19 fields, 1,336 rows and 19 values per row.
- TPEx exact envelope keys are `columnNum,date,stat,tables,template`; the live modern response has two table slots, table 0 with 24 fields/892 rows and exact metadata keys, while table 1 is `{}` for the inactive legacy schema.
- TPEx metadata is `stat=ok`, top-level `date=YYYYMMDD`, `template=/template/insti/dailyTrade`, and `columnNum=25`; table metadata reports ordinary, block, odd-lot and investment-trust omnibus volumes.
- TWSE metadata is `stat=OK`, `selectType=ALLBUT0999`, `hints=單位：股`, and notes explicitly freeze included general/odd-lot/after-hours fixed-price/block versus excluded auction/tender plus original-trade correction semantics.
- The TPEx 24-column historical product publishes all component triplets, including dealer proprietary and hedge. PR-002 should parse these instead of degrading to the latest-only OpenAPI's unsplit dealer totals.
- Raw persistence belongs at a store port with in-memory and directory-backed implementations; PR-006 still owns database schema and durable normalized-row parity.
- Reviewed fixture rows are frozen from the official 2026-08-19 responses: TWSE symbols `2330`/`2317`, TPEx `006201`/`6488`. Fixtures will keep the official envelope and those unchanged row values while reducing row count metadata to the captured subset.
- Implemented raw artifact identity as logical source key plus content SHA256. Same bytes deduplicate; changed bytes append a revision. The directory store uses exclusive file creation and reload-time digest/schema verification.
- Implemented official adapters with fixed HTTPS endpoints, exact request-scope parameters, exact envelope/field gates, date checks, numeric normalization and component mappings. Network fetch remains separate from parse so raw sealing can occur first.
- The application seals raw bytes before any scope check or parser call, then returns a manifest for every attempt. Structural/source errors and formula/partition errors converge on `QUARANTINED`; only a clean existing PR-001 validation report becomes `VALIDATED`.
- `usable_from_session` remains mandatory caller input at both live-fetch and fixture-replay entry points.
- Reviewed fixture samples retain exact official row values and source envelope markers while reducing `total/totalCount` to the two selected rows; their filenames explicitly identify them as reviewed samples rather than full raw downloads.
- Gate tests now cover both valid source replays, exact component mapping, date pollution, schema drift, empty response, scope mismatch, formula failure, raw survival and immutable source revision behavior.
- The repository has no `python` shim in PATH; verification must use the existing `.venv/bin/python` (or explicit `python3`) to match prior project runs.
- Focused institutional suite passes all 50 tests. Ruff is not installed in `.venv`; locate the repository's established lint runner before declaring style verification.
- A system Ruff binary is available at the Python 3.13 installation. Static checks pass; formatter reports five new files need mechanical formatting.
- After formatting, Ruff passes and all 50 focused tests still pass. `git diff --check` reports no whitespace defects in PR-002 files.
- The worktree contains unrelated freshness/P1/planning changes; PR-002 verification and any later commit must stay path-scoped.
- Adversarial review tightened raw revision type validation and made directory path components collision-resistant with a content suffix.
- Focused coverage is 89% overall; critical validation is 100%, application 92%, artifact storage 89%, and source adapters 80%. Remaining source misses are mostly live transport/error-defense branches rather than accepted replay gates.
- The architecture plan now records PR-002 approval/implementation, all three added exit gates, and the approved PR-004/PR-005 names while preserving the no-feature/no-strategy/no-CandidatePool boundary.
- Full repository regression passes: `470 passed, 1 skipped`.
- Bytecode compilation passes. Wheel build initially hit sandbox denial on the shared uv cache, then succeeded with approved cache access; the built wheel includes all seven `institutional_data` modules.
- Isolated import from the built wheel succeeds and exposes both frozen scope IDs.
- Live smoke exposed a Python 3.13/TPEx TLS interoperability issue: the official TPEx chain is rejected under `VERIFY_X509_STRICT` for missing Subject Key Identifier. CA validation and hostname checking must remain enabled; only the strict-chain flag may be cleared in a dedicated HTTPS context.
- Added the bounded TLS compatibility context. Its regression test proves `check_hostname=True`, `CERT_REQUIRED`, and only `VERIFY_X509_STRICT` cleared; focused adapter/store tests pass `14/14`.
- Live adapter ingestion now passes against both official 2026-08-19 products: TWSE `VALIDATED` with 1,336 rows and TPEx `VALIDATED` with 892 rows, both with zero issues.
- A subsequent full-suite rerun was interrupted during collection by a newly present unrelated `test_market_event_contract_freeze.py` importing an absent `MARKET_EVENT_SCHEMA_VERSION`; this was not present in the earlier `470 passed, 1 skipped` run and is outside PR-002 scope.
- Worktree provenance confirms that test and its fixtures are untracked concurrent additions timestamped after the earlier clean full run; `market_data/events.py` is older and unmodified. Excluding only that unrelated collection blocker yields `471 passed, 1 skipped`; PR-002 focus yields `51 passed`.
- Final wheel rebuilt after the TLS fix. Isolated import loads from the wheel, with peer validation `True`, hostname validation `True`, and strict-chain compatibility flag `False` as designed.
- Wheel building generated an untracked `build/` tree and refreshed tracked `tw_intraday_trader.egg-info` from unrelated current worktree additions. These are build byproducts, not PR-002 deliverables, and must be removed/restored without touching concurrent source changes.
- The generated build tree was moved to `/private/tmp` and egg-info content was restored; only the original file's no-final-newline byte remains to restore mechanically.
- Final cleanup restored egg-info byte-for-byte and removed all workspace build byproducts. Final PR-002 lint/format/compile checks pass and the focused suite passes `51/51`.
- A final whole-worktree run remains blocked by another concurrent untracked test, now `test_canonical_market_pipeline.py` importing a not-yet-created `market_data.pipeline`. This confirms an actively changing unrelated scope; PR-002 focused evidence remains clean and the earlier stable full run remains the valid regression baseline.
