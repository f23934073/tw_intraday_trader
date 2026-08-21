# Institutional Source Coverage

Status: PR-002 reviewed source coverage. This matrix describes acquisition
evidence only; it does not establish a historical equity universe or strategy
eligibility.

| Market | Official source | Canonical product / parser | Reviewed trade scope | Component coverage | Status |
|---|---|---|---|---|---|
| TWSE | T86 | `TWSE_T86_FINAL` / `twse_t86_json_v1` | `TWSE_T86_FINAL_WITH_BLOCK_V1`: general, odd-lot, after-hours fixed-price, and block trades; auction and tender excluded; original trades | Foreign ex-dealer, foreign dealer, investment trust, dealer proprietary, dealer hedge, dealer total | `VALIDATED` |
| TPEx | daily institutional detail, `Daily` + `EW` | `TPEX_INSTI_DAILY_EW` / `tpex_insti_daily_trade_v1` | `TPEX_DAILY_ORIGINAL_TRADES_V1`: ordinary, block, and odd-lot trades for the reviewed EW response; original trades | Foreign ex-dealer, foreign dealer, investment trust, dealer proprietary, dealer hedge, dealer total | `VALIDATED` |

## Evidence and interpretation

- Both adapters preserve raw response bytes before parsing and bind normalized
  output to raw and normalized SHA-256 digests.
- Endpoint, request parameters, response session, reviewed schema, row count,
  source notes, formulas, and scope markers fail closed to quarantine.
- `VALIDATED` means the captured response matches the reviewed product contract.
  It does not mean every returned symbol is an ordinary equity or is eligible
  for cross-sectional research.
- Publication time is not inferred from the payload. `first_observed_at`,
  `retrieved_at`, and the caller-supplied next eligible
  `usable_from_session` are retained separately.

## Unsupported or limited cases

- Historical source schemas outside the reviewed parser versions are not
  automatically accepted. Schema changes require a new parser/contract review.
- Corrected-account histories are unsupported. Both current contracts describe
  original-trade statistics; later official corrections must be captured as a
  new immutable raw revision rather than overwriting evidence.
- A missing component is representable by the normalized contract and is
  reported as `UNKNOWN_COMPONENT` or `NOT_APPLICABLE` where appropriate. The
  reviewed TWSE and TPEx products currently expose the component splits listed
  in the matrix; consumers must not synthesize a missing split from dealer total.
- Source coverage does not provide date-effective security type, listing or
  delisting history, industry classification, market capitalization, or an
  expected equity-symbol denominator.
- Cross-market numerator/denominator comparisons remain unsupported unless
  their trade-scope compatibility is explicitly assessed.
- License/redistribution rights are not established by adapter validation and
  must be reviewed before redistributing captured official payloads.

Until a validated PR-003 artifact supplies point-in-time coverage and a pinned
universe digest, cross-sectional diagnostics, matched controls, formal research,
watchlist generation, and strategy claims remain blocked by
`PIT_UNIVERSE_MISSING`.
