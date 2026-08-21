# First Two-Market Institutional Dataset Quality Report

## Technical summary

The 2026-08-19 acquisition pilot is **validated for replay but incomplete for
formal research**. One TWSE partition and one TPEx partition were sealed from
official responses, normalized into 2,228 symbol rows, and passed 17,824
contract checks with zero validation issues. The partition-set status is
`VALIDATED_PARTIAL_COVERAGE`.

This evidence is sufficient to move the institutional dataset inventory from
`MISSING` to `PARTIAL`. It is not sufficient to freeze the research population,
generate outcomes, or execute the holdout because only one common session has
been acquired and the PIT equity universe is still unavailable.

## Both market partitions passed the frozen acquisition checks

| Market | Session | Source rows | Normalized rows | Unique symbols | Validation checks | Issues | Raw revision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TWSE | 2026-08-19 | 1,336 | 1,336 | 1,336 | 10,688 PASS | 0 | 1 |
| TPEx | 2026-08-19 | 892 | 892 | 892 | 7,136 PASS | 0 | 2 |
| **Total** | **1 common session** | **2,228** | **2,228** | **2,228 within market** | **17,824 PASS** | **0** | — |

For both partitions, the response date matches the requested session, source
and normalized row counts agree, symbols are unique at
`(market, session_date, symbol)`, all required component fields are present,
and raw, normalized, and manifest digests match their sealed artifacts.

## Scope and metric definitions

- **Grain:** one market, completed trading session, and source symbol.
- **Cohort:** all rows returned by the configured TWSE T86 and TPEx EW products;
  no PIT common-equity eligibility filter is applied at this layer.
- **Coverage:** 2026-08-19 only, with both TWSE and TPEx present.
- **Completeness:** row-count agreement and contract validation within each
  official response; not historical-period completeness.
- **Comparison basis:** source response versus its deterministic normalized
  partition, not strategy performance or price outcomes.

The symbol identifiers include lengths beyond four characters (TWSE: 1,086
four-character, 118 five-character, 132 six-character; TPEx: 770, 7, and 115).
This is not classified as a source defect. It confirms that a later PIT
security-type and listing-history filter is required before percentile,
liquidity-cohort, or matched-control construction.

## Acquisition and validation method

Raw HTTP response bytes were sealed before parsing in the append-only artifact
store. The repository adapters then parsed the saved response under their
market-specific trade-scope contracts, serialized normalized rows and the
partition manifest canonically, and recorded SHA-256 identities in the
partition set.

The official TPEx daily institutional page accepts historical dates in the
page's slash-form date encoding. The acquisition path was verified against the
[TPEx daily institutional report](https://www.tpex.org.tw/zh-tw/mainboard/trading/major-institutional/detail/day.html);
the [TPEx OpenAPI catalog](https://www.tpex.org.tw/openapi/) is useful source
documentation but its current daily feed is not treated as a historical
partition artifact.

## One TPEx response was quarantined without rewriting history

The first TPEx request used `20260819`. The endpoint returned the 2026-08-20
report instead, so validation raised a response-date mismatch and produced no
eligible partition. That raw response remains preserved as revision 1 and is
excluded from the partition set.

The adapter now sends `2026/08/19`; the corrected response became revision 2
and passed all 7,136 checks. This is a source-parameter defect correction, not
strategy tuning, and both revisions remain auditable.

## Limitations and robustness boundary

- One session cannot establish temporal continuity, missing-session rates,
  source stability, correction frequency, or regime coverage. A trend chart
  would therefore be misleading and is intentionally omitted.
- Zero partition issues means the implemented contract passed; it does not
  establish economic eligibility of every source symbol.
- The pilot does not include prices, corporate actions, reference data, a TPEx
  calendar artifact, or a PIT universe, so cross-dataset joins remain untested.
- No outcome fields were read. This report contains no evidence that an
  institutional prior improves the price-only strategy.

## Recommended next steps

1. Acquire the required historical session range with both TWSE and TPEx present
   for every counted session; quarantine partial or mismatched sessions.
2. Run the same digest, row-grain, date, formula, and issue-count gates on every
   partition and produce a new immutable partition-set artifact.
3. Acquire the PIT universe and reference datasets before interpreting mixed
   source symbols as eligible equities.
4. Keep every downstream permission disabled until all required datasets are
   validated and a revised coverage artifact proves their common intersection.

## Further questions

- What exact historical range can all six required dataset families support?
- How often do official responses revise after their first observed version?
- Which source symbols survive the PIT common-equity and liquidity filters on
  each session?
