# Findings: PR-008 FinMind PIT Price Integration

## Evidence inventory — 2026-08-24

- The FinMind Sponsor acquisition path is an independent, resumable
  symbol-day SQLite store. Its selected snapshot was materialized separately
  as `dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6`.
- That manifest covers 2023-08-19 through 2026-08-18, uses
  `FINMIND_SPONSOR_TAIWAN_STOCK_KBAR` / `KBAR_1M_V1`, has 182 requested
  symbols, is `CURRENT_SNAPSHOT`, and declares `research_eligible=false`.
- The historical-backtest readiness task confirms the dataset has already been
  used for a Web Atomic Run and strategy outcome was observed. Therefore it is
  an engineering/reference artifact only for PR-008; it is not an unobserved
  formal holdout.
- PR-008 already freezes a general data-coverage policy: PIT eligible plus
  complete institutional and qualified intraday data, with at least 95% symbol
  coverage and at least 99% per-symbol and aggregate session coverage. Final
  eligibility still requires a PIT join and formal coverage audit.
- Existing PR-008 evidence requires a distinct dataset identity whenever a
  secondary source is used. The lost Shioaji scan is not recoverable through
  this FinMind artifact.

## Repository seam — 2026-08-24

- `DatasetAcquisitionManifestV1` deliberately treats price as `MISSING` unless
  a formal immutable artifact satisfies the PR-008 contract. It must not be
  overwritten merely because the separate FinMind snapshot exists.
- The existing `PriceCoverageAuditV1` requires original-protocol, coverage-
  amendment, scan configuration/checkpoint, PIT universe, institutional,
  calendar, reference, and corporate-action lineage before a formal coverage
  claim. The present FinMind dataset supplies none of the missing PIT-side
  identities.
- The existing Sponsor probe validates KBar/Tick semantics on available
  controls, but is `REJECTED_FOR_MISMATCH_RESOLUTION`; it cannot silently be
  upgraded into a selected primary source.
- The smallest safe additive seam is two new immutable PR-008 artifacts and
  one drift-gate test: one records the existing dataset as a non-formal
  engineering reference; the other preregisters a separate PIT price
  acquisition contract with every execution permission false.

## Implemented boundary — 2026-08-24

- `FinMindEngineeringReferenceRegistrationV1` pins the existing Dataset ID,
  source snapshot, plan, payload and manifest digests, while asserting that it
  is neither a formal PR-008 price dataset nor a holdout.
- `FinMindPITPriceAcquisitionContractV1` fixes the eventual source profile,
  date-effective PIT member/session acquisition grain, dual-market scope,
  raw-price/corporate-action policy, coverage thresholds, and the requirement
  for a new Dataset identity. The target date range remains `null` and all
  execution locks remain false.
- Focused drift gates passed: 18 tests across the new integration and existing
  acquisition/coverage/FinMind-probe boundaries.

## Verification — 2026-08-24

- Expanded focused PR-008 suite passed: 31 tests.
- Ruff passed for the new test. JSON parsing, Python compilation, canonical
  digest checks, tracked-file diff checking, and an untracked-file whitespace
  check all passed.
- No existing immutable artifact was modified. The only new files are the two
  PR-008 artifacts, their digest sidecars, their drift test, and this isolated
  plan.
- The registration timestamp was corrected to the actual local artifact-build
  time before final digest verification; the dependent contract digest was then
  recalculated rather than retaining stale lineage.

## Non-goals

- No provider request, credential read, price-payload/outcome read, backtest,
  dataset materialization, or gate unlock is permitted in this scope.

## PIT contract inspection — 2026-08-24

- The existing PIT import boundary is already strict: records require
  date-effective listing/delisting intervals, market, explicit security type,
  industry and market-cap observations available no later than the effective
  date, dual-market coverage, source/content digests, and non-overlapping
  history.
- The importer correctly fails closed for `CURRENT_SNAPSHOT`, missing
  coverage/digests, future classifications, row-count drift, and interval
  overlap. Existing PIT fixtures are test-only; no production snapshot was
  found.
- A current stock-information feed cannot satisfy this contract because it
  cannot prove historical membership, later delistings, historical industry,
  or historical market-cap cohorts. A real initial artifact needs a source with
  historical point-in-time security/reference coverage.

## Primary-source resolution — 2026-08-24

- TWSE and TPEx public pages establish useful current-listing, recent-listing,
  delisting, and daily-pricing evidence, but the reviewed public routes do not
  establish a single complete, date-effective dual-market history with daily
  market-cap/industry/reference revision semantics.
- TEJ's published TQuant catalog describes daily pre-open security attributes
  (`TWN/APISTKATTR`), daily stock attributes including market-cap/corporate-
  action fields (`TWN/APISHRACT`), and security attributes
  (`TWN/APISTOCK`) across TWSE, TPEx, and delisted securities. This is a
  promising PIT/reference-source candidate, not acquired data or entitlement
  evidence.
- A TEJ candidate must still pass secret-safe local entitlement detection,
  written retention/revision terms, a bounded metadata-only schema/sample
  qualification, and immutable raw/normalized artifact validation before it
  can populate the formal PIT universe.

## PIT-source resolution verification — 2026-08-24

- The source-resolution artifact pins the FinMind PIT contract, existing
  coverage evidence, and prior official/licensed intraday review without
  selecting TEJ or any public source.
- Focused validation passed: 46 tests across the new source-resolution gate,
  PIT import contract, FinMind boundary, acquisition, coverage amendment, and
  official/licensed source artifacts. Ruff, JSON parsing, Python compilation,
  and digest validation also passed.

## Entitlement preflight — 2026-08-24

- Research-owner authorization now covers bounded TEJ/TQuant metadata-only
  qualification.
- A second secret-safe inventory found no `TEJ_API_KEY`, `TEJAPI_KEY`,
  `TQUANT_API_KEY`, or `TQUANT_TOKEN` in the local environment or `.env`.
  No anonymous provider request was issued, and no credential value was read.

## FinMind qualification path — 2026-08-24

- The existing `FinMindApiClient` supports authenticated `/api/v4/data`
  requests and correctly separates quota, transport, HTTP, JSON-status, and
  data-array failures. It can be reused only after a new PIT/reference-specific
  protocol is frozen.
- Existing FinMind code proves `TaiwanStockInfo` and
  `TaiwanStockMarketValue` are queried as reference metadata. The PIT probe
  must explicitly avoid `TaiwanStockKBar`, `TaiwanStockPrice`,
  `TaiwanStockPriceAdj`, `TaiwanStockPriceTick`, and every strategy/outcome
  path.
- The prior intraday probe's capture pattern can be adapted only with a new
  output directory and a new protocol identity. No existing immutable capture
  or mutable KBar-history checkpoint may be reused or overwritten.

## Frozen FinMind PIT/reference probe — 2026-08-24

- `CredentialedFinMindPITReferenceProbeProtocolV1` is now digest-frozen as
  `9ae68fbb2192c0b092718c3c271dbf427b29af50b9d466bd13cc19fcdae04937`.
  It contains exactly eight authenticated, non-price requests: security
  identity, delisting, two historical market-cap dates, TWSE/TPEx trading-date
  controls, and TWSE/TPEx dividend controls.
- The frozen allowlist excludes every price, KBar, adjusted-price, and tick
  dataset. It reserves 100 requests after the probe, uses a distinct immutable
  raw-response directory, and keeps source selection, PIT acquisition, Price
  Dataset, Population Freeze, and outcome generation locked.
- Local verification passed: 11 focused tests, Python compilation, and the
  protocol canonical digest check. The workspace-level Ruff runner later
  passed for the new code. No provider request had occurred at this point.

## Credentialed probe result — 2026-08-24

- The FinMind Sponsor usage preflight passed with 2,246 requests remaining;
  the frozen eight-request probe was therefore allowed while reserving 100
  requests. All eight requests returned HTTP 200, JSON status 200, and an
  array-shaped payload. Capture manifest digest and all eight raw-response
  byte hashes validate.
- The immutable capture confirms schema access for `TaiwanStockInfo`,
  `TaiwanStockDelisting`, two historical `TaiwanStockMarketValue` dates,
  TWSE/TPEx control queries for `TaiwanStockTradingDate`, and TWSE/TPEx
  controls for `TaiwanStockDividend`. The raw bodies were captured under the
  frozen protocol; later validation used byte hashing only and result building
  read manifest metadata only, not raw row values.
- `CredentialedFinMindPITReferenceProbeResultV1` has verdict
  `INSUFFICIENT_EVIDENCE`, not rejection: authenticated bounded access is
  verified, but the probe does not establish date-effective listing/start and
  market-transfer history, PIT industry classifications, a whole-market
  TWSE/TPEx calendar contract, full historical coverage, or
  correction/retention/revision terms. It selects no source and keeps every
  acquisition/formal-evaluation permission false.
- Verification after capture passed: 75 focused PR-008/PIT/FinMind tests,
  Ruff, Python compilation, JSON parsing, canonical-digest validation, and
  whitespace checks. No KBar/price/tick request, strategy execution,
  backtest, return/PnL/holdout read, Price Dataset, Population Freeze, or
  outcome generation occurred.

## FinMind semantics/terms documentary review — 2026-08-24

- FinMind's official complete API reference documents `TaiwanStockInfo` as a
  market-membership table rather than a full listing-history table: an
  emerging-board row is frozen when a stock transfers, while the TWSE/TPEx row
  carries the current date. This supports current-market resolution but does
  not supply each listing start, delisting interval, or a complete historical
  market-transfer timeline required by the repository PIT contract.
- The same official reference documents `TaiwanStockMarketValue` from
  2004-01-01 with only `date`, `stock_id`, and `market_value`; `TaiwanStockDelisting`
  from 2001-01-01 with only `date`, `stock_id`, and `stock_name`; and
  `TaiwanStockIndustryChain` as a current industry-chain table explicitly
  stated to use current classifications for historical dates. Those documented
  semantics cannot create date-effective industry labels or ordinary-equity
  membership on their own.
- The public API reference documents endpoint/schema/tier behavior and a
  status page, but the reviewed documentation does not state retention,
  correction, or revision guarantees suitable for pinning a formal research
  artifact. Terms must be obtained as written provider evidence before any
  source selection.
- This supports a narrow next probe only for `TaiwanStockMarketValueWeight`
  (whose documented `type` supports dated market membership),
  `TaiwanStockSuspended`, and `TaiwanStockIndustryChain`; it cannot remove the
  listing-history or revision/retention blockers. No new provider request has
  occurred in Phase 8.

## FinMind formal PIT disposition — 2026-08-24

- The strict repository contract requires date-effective listing and version
  intervals, explicit common-stock classification, industry and market-cap
  evidence no later than each effective date, plus dual-market coverage and
  immutable correction/revision provenance.
- `FinMindPITReferenceSemanticsResolutionV1` is digest-frozen as
  `9b2f93a1ddcdedd2d9a9efeb9b9c729490fc57b67a3ed250c8ae860503720bfa`.
  It makes the narrow verdict `REJECTED_FOR_FORMAL_PIT_REFERENCE_USE`, while
  retaining FinMind as a possible partial reference component for non-PIT
  uses. The rejection comes from documented source semantics, not a failed
  account entitlement or quality judgment.
- No further FinMind API call is warranted for this gate: additional schema
  samples cannot repair the documented use of current industry classifications
  for historical dates, nor add missing listing/transfer intervals. The next
  source gate returns to a licensed or provider-written PIT reference product
  with explicit time-validity and retention/revision evidence.
- Expanded focused validation passed: 78 tests across the new semantic result,
  prior credentialed probe, PIT contract, integration boundaries, acquisition
  gates, coverage protocol, and source resolution; Ruff, JSON parsing,
  compilation, canonical digest, and whitespace checks passed. No additional
  provider call, price/KBar/tick payload, outcome, or backtest was used.

## MVP scope amendment — 2026-08-24

- The research owner now explicitly accepts a non-formal MVP using only the
  practical subset FinMind can supply. This is a scope change, not a revision
  of the frozen PR-008 formal protocol: current-universe/survivorship limits,
  post-close availability, incomplete coverage, and observed outcomes must be
  displayed rather than hidden.
- The MVP target is a read-only daily institutional-flow candidate ranking,
  separate from the formal Candidate Prior and formal holdout. It may use
  FinMind daily institutional data after a small frozen schema capture; it
  must not claim a full PIT universe, production trading authority, or formal
  strategy validation.

## MVP dealer-field resolution — 2026-08-24

- The sealed `TaiwanStockInstitutionalInvestorsBuySellWide` capture includes
  the legacy dealer pair plus `Dealer_self_*` and `Dealer_Hedging_*` fields.
  Treating only the legacy pair as dealer flow produced an r1 no-candidate
  observation and would understate the provider's available dealer data.
- The MVP therefore preserves that r1 observation and uses an explicitly
  versioned r2 canonical dealer rule. This is an MVP field-semantics
  correction only; it neither changes the frozen PR-008 protocol nor makes a
  price, return, or holdout claim.
- A sealed-payload structure check shows legacy dealer fields are often a
  fallback encoding rather than an independent component: 19,823 rows have
  zero legacy fields with non-zero self/hedging fields, and 703 rows have the
  legacy values equal to the component totals. The r2 implementation must use
  self-plus-hedging when either component is present and otherwise use the
  legacy pair; it must not add both encodings together.

## MVP candidate observation — 2026-08-24

- The local-only r2 build validates all capture/policy/raw-response digests
  before parsing. It joined 2,267 daily-flow rows to the current TWSE/TPEX
  mapping and produced 17 three-way-net-buy candidate observations for the
  2026-08-18 post-close session, usable no earlier than 2026-08-19.
- `FinMindInstitutionalMvpCandidateObservationV1` is digest-frozen as
  `7e764985c7ae5bd92dafaf4762e61125a15ae889a455c80f5eb172c4cb177276`.
  It explicitly prevents orders, production binding, outcomes, formal PIT,
  formal candidate prior, and holdout use. It is a daily watchlist artifact,
  not a validated trading strategy.

## MVP implementation seam — 2026-08-24

- The existing `institutional_data` path is intentionally tied to official
  TWSE/TPEx responses and strict trade-scope/reconciliation semantics. It
  should not be modified or relabelled as FinMind data.
- FinMind documents a daily wide institutional table with foreign, investment
  trust, and dealer component columns but no market per row. For the MVP, an
  independent adapter will join the wide table to the latest
  `TaiwanStockInfo` mapping and explicitly label that join as
  `CURRENT_MARKET_MAPPING`.
- The MVP rule will be transparent and read-only: keep only symbols with
  positive foreign, investment-trust, and dealer net flow, then rank by their
  summed net shares for the next session. This is a candidate observation list,
  not a formal Candidate Prior, an order, or a validated backtest strategy.

## MVP bounded capture r1 — 2026-08-24

- FinMind Sponsor quota preflight passed with 3,351 remaining requests. The
  frozen two-request capture completed successfully and was sealed separately
  from PR-008 formal artifacts. It contains one 2026-08-18 daily wide-flow
  response (20,529 rows) and one current stock-info response (4,308 rows).
- The wide-flow response is correctly single-date, but its row count proves
  the MVP cannot assume one row per `stock_id`. The initial parser therefore
  fails closed on duplicate symbols rather than silently choosing or summing a
  row. The next implementation step is a value-free duplicate-structure audit
  and an explicit aggregation rule or an MVP block.
- The stock-info response has dated historical/current mapping rows and 32
  null/invalid date observations. The adapter already excludes invalid mapping
  dates and labels the remaining mapping as `CURRENT_MARKET_MAPPING`; it does
  not infer PIT membership.

## MVP r1 structure and rule resolution — 2026-08-24

- The 20,529 flow rows are 20,529 distinct `stock_id` values, not duplicate
  symbol rows; all required foreign/trust/dealer base fields are integer typed.
  2,267 rows join to the explicit current TWSE/TPEx mapping.
- Applying r1's literal `Dealer_buy - Dealer_sell` interpretation returned zero
  three-way-buy candidates. This is a semantic issue, not a data failure:
  current FinMind schema also publishes `Dealer_self_*` and
  `Dealer_Hedging_*`, while its documentation distinguishes the legacy
  combined dealer columns from later component columns.
- r1 capture and its zero-candidate result remain preserved. A new immutable
  candidate-policy revision will define dealer total as the sum of legacy,
  proprietary, and hedging net flows. It can derive a new MVP observation from
  the same sealed raw r1 capture without a redundant provider request.
