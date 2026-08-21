# Findings & Decisions

## Requirements

- Start using today's FinMindTrade Sponsor allowance now, but proceed gradually.
- Rebuild three years of historical data after the prior database was deleted and cannot be recovered.
- Preserve resumability and avoid duplicate API usage.
- Keep acquisition separate from formal validation/OOS outcome generation.
- Continue acquiring three-year data for additional large-cap stocks, with representation across as many industries as practical.
- Base the large-cap and industry choices on current source data and use today's remaining allowance conservatively.

## Confirmed Context

- Referenced task: `確認回測與三年資料` (`01a022e1-fa1c-7833-b070-cdd217911239`).
- The previous Shioaji PostgreSQL dataset was deleted and is not recoverable.
- The previously frozen request covered the current-contract universe of 2,738 instruments from 2023-08-19 through 2026-08-18.
- FinMind Sponsor was previously credential-probed at 6,000 requests per hour.
- Sponsor minute bars use one symbol-day per request; full-market day Parquet is a Sponsor Pro path.
- Existing probes found valid one-minute bars for 2330 and 2317, while some symbols returned empty data.
- The referenced task is concurrently optimizing large-backtest memory use; this acquisition work must not overwrite its files.

## Data Quality Contract

- Intended grain: one canonical row per `(provider, symbol, timestamp)`.
- Required checks: timezone-aware timestamps, deterministic order, unique symbol-timestamps, finite positive OHLC, `low <= open/close <= high`, integral non-negative volume, regular-session bounds, and source/date provenance.
- Empty responses are observations, not successful data partitions.
- Recent or partial dates require explicit labeling; no automatic repair or fabricated bars.

## Open Questions To Resolve From Repository Evidence

- Whether the existing FinMind probe client is production-safe for paced multi-day acquisition.
- Whether the current durable repository is PostgreSQL-only or supports a local immutable fallback after database deletion.
- Whether an authoritative current-contract universe snapshot still exists outside the deleted database.
- Whether the FinMind token/credential is present in the current process environment.
- Whether FinMind exposes remaining allowance directly or only a fixed entitlement limit plus HTTP rate-limit responses.

## Phase 1 Repository Evidence

- `.env` contains a non-empty `FINMIND_API_TOKEN`; the value was not printed.
- The repository has a secret-safe immutable FinMind probe script and offline semantic reconciliation, but no general FinMind historical downloader/provider.
- The existing CLI only accepts `mock` or `shioaji` and creates database-backed durable jobs.
- Backtest configuration defaults to PostgreSQL but supports a SQLite backend; after the old PostgreSQL loss, a new local SQLite repository is a viable durable destination if migrations and job-partition persistence are confirmed.
- `HistoricalDatasetCatalog` stores immutable canonical JSONL manifests under `data/backtest`; it can remain the finalized dataset layer while database job partitions provide resumable staging.
- Existing source qualification artifacts confirm Sponsor KBar success for some controls and provider-empty observations for others, so the new path must not treat HTTP 200 as data success.
- The current worktree has broad concurrent modifications, including the historical downloader and dataset streaming path. New code should be additive where possible and must preserve those changes.
- The existing repository schema keys history partitions by `(job_id, symbol)`, explicitly meaning one complete symbol; it cannot represent Sponsor symbol-day checkpoints without a new/additive store.
- A sealed FinMind 2330 sample contains 266 rows from `09:00` through `13:30`, with `date`, `minute`, `stock_id`, OHLC, and integral `volume`; response envelope is `status=200`, `msg=success`.
- Existing canonicalization can construct `HistoricalBar` from provider `KBar`, but adding a general FinMind `MarketDataProvider` would still force the unsuitable whole-symbol checkpoint behavior.
- The backtest runtime intentionally fails closed on missing PostgreSQL; SQLite is only explicit local-dev/test. The rebuild therefore needs a clearly scoped acquisition store and must not silently claim to replace the authoritative backtest database.
- FinMind's official usage endpoint returns both current `user_count` and `api_request_limit`; the live runner can reserve capacity based on the actual account state instead of assuming 6,000 calls remain.
- Official API documentation confirms `TaiwanStockPrice` accepts a date range. One three-year daily query for a liquid calendar symbol can discover trading dates and avoid wasting KBar calls on weekends and market holidays.
- Existing sealed reconciliation proves FinMind KBar labels are interval starts except `13:30`; canonical event timestamps must add one minute except for the close label to avoid look-ahead and match Shioaji end labels.
- Sealed reconciliation also proves FinMind raw KBar volume is in common lots, not shares; the acquisition metadata must retain that unit explicitly.

## Implementation Success Criteria

- Every external KBar request commits an immutable `(job_id, symbol, session_date)` checkpoint before the next request.
- Re-running the same job never calls FinMind for `READY` or observed `EMPTY` symbol-days.
- Current FinMind usage is checked first; `max_requests` and a reserve margin jointly cap the batch.
- HTTP/payload quota exhaustion stops cleanly without corrupting the last checkpoint.
- Raw response bytes are gzip-persisted with SHA-256; normalized canonical rows are deterministically re-derived and digest-verified.
- Invalid OHLC, duplicate/non-monotonic minutes, wrong symbol/date, negative/non-integral volume, or out-of-session rows block the partition.

## Live Preflight Evidence

- Official usage endpoint returned `user_count=0`, `api_request_limit=6000`, so 6,000 requests were available before acquisition.
- Exactly one data request was spent to query `TaiwanStockPrice` for calendar symbol 2330 across the frozen range.
- The immutable calendar contains 727 trading dates from the requested `2023-08-19` through `2026-08-18` range.
- The first actionable checkpoint is `2317 / 2023-08-21`; the two-symbol pilot contains 1,454 expected symbol-days.
- After calendar sealing, the store recorded exactly one request and zero KBar partitions.

## First Completed Symbol

- 2317 now has all 727 requested trading-date observations checkpointed: 726 `READY` and one observed `EMPTY`.
- The empty observation is `2025-07-30`; this matches the publicly reported TWSE-approved 2317 trading halt for pending material information, so it is an expected no-trade session rather than a failed FinMind response.
- The 726 non-empty partitions contain 193,083 canonical bars, with 261-266 bars per session and a mean of 265.95.
- Full offline audit re-read and digest-verified all 727 raw partitions with zero integrity or normalization issues.
- Local acquisition database size after the first complete symbol is approximately 3.1 MB.

## Delayed Closing Auction Finding

- 2330/2025-03-24 returned 266 rows but no 13:25-13:30 trades; its final row was `13:33`, OHLC 972, volume 3,636 common lots.
- TWSE's closing-stabilization rule permits an affected security's close to be delayed to 13:33 when the final simulated price moves beyond the threshold.
- Contemporary market reporting confirms 2330 closed at 972 with a 3,636-lot closing sell print that day.
- This is a legitimate regular-session closing auction, not an after-hours fixed-price row. The canonical event time remains 13:33 without a one-minute shift.
- The contract remains fail-closed for any other post-13:30 label.

## Final Verified State

- Job `finmind-sponsor-93e761a34d3f3511` is `COMPLETED` with 1,454/1,454 symbol-day checkpoints across 727 trading dates.
- 2317: 726 `READY`, one expected `EMPTY`, 193,083 canonical bars.
- 2330: 727 `READY`, 193,330 canonical bars.
- Combined: 1,453 `READY`, one expected `EMPTY`, zero invalid/error partitions, 386,413 canonical bars.
- Full offline audit verified all 1,454 raw SHA-256 and canonical digests with zero issues.
- Exact FinMind usage after completion was 1,455/6,000, leaving 4,545 requests in the current allowance window.
- Local SQLite acquisition database size is approximately 6.1 MB and remains git-ignored.
- Full repository verification passed: 1,061 tests passed and 4 were skipped; focused Ruff and whitespace checks passed.
- No formal validation/OOS backtest was started and no broker/order path was touched.

## Diversified Extension Questions

- Confirm the latest usable `TaiwanStockMarketValue` observation and `TaiwanStockInfo` industry field from official FinMind data.
- Decide whether one representative per detailed industry is too sparse or too broad for today's remaining 4,545-request snapshot.
- Calculate the number of complete 727-session symbols that fit after current metadata requests and the 500-request safety reserve.

## Diversified Universe Evidence

- Official FinMind semantics were verified for `TaiwanStockInfo` and the exact-date all-market form of `TaiwanStockMarketValue`.
- Raw metadata was sealed by SHA-256; the latest usable market-value date is 2026-08-20.
- FinMind current stock info contains 603 symbols with simultaneous aggregate and detailed category rows. Aggregate `電子工業`, `化學生技醫療`, and `創新板股票` labels are removed when one detailed industry exists.
- Null-date/incomplete rows, truly ambiguous current identities, non-company categories, non-four-digit symbols, and non-positive market values are excluded.
- The resulting reproducible universe has 40 detailed-industry leaders.
- Completed 2330 represents `半導體業`; completed 2317 represents `其他電子業`.
- Live usage after eight metadata data requests was 1,463/6,000, leaving 4,537.
- With a 500-request reserve, one new calendar call, and 727 symbol-days per stock, five complete symbols fit today's tranche.
- The five highest-market-value missing-industry leaders are 2308 台達電 (`電子零組件業`), 2881 富邦金 (`金融保險`), 1303 南亞 (`塑膠工業`), 2382 廣達 (`電腦及週邊設備業`), and 2345 智邦 (`通信網路業`).
- The 6,000-request account limit is hourly rather than daily. At one request per second the downloader issues at most about 3,600 data calls per hour, so the other 33 missing industries can continue after the first tranche instead of being deferred as a presumed daily quota gap.
