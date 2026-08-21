# PIT Equity Universe v1 Contracts

Status: PR-003 foundation. This contract supplies research reference data; it
does not generate factors, candidates, orders, or runtime subscriptions.

## Snapshot records

`pit_equity_universe_snapshot_v1` fixes each date-effective record to:

- `symbol`, `name`, `market`, and `security_type`;
- listing interval `listed_from <= session < listed_until`;
- version interval `effective_from <= session < effective_to`;
- `industry_code`, `industry_name`, and `industry_as_of`;
- `market_cap_twd`, `market_cap_cohort`, and `market_cap_as_of`;
- row-level `source_digest`.

Both upper bounds are exclusive and may be `null` for an open interval.
Industry and market-cap evidence cannot be dated after `effective_from`.
Unknown, missing, overlapping, or internally inconsistent records fail closed.

Only an explicit `COMMON_STOCK` record is eligible for the ordinary-equity
research universe. Symbol length or today's instrument list is never used to
infer historical security type.

## Manifest and revision evidence

`pit_equity_universe_manifest_v1` binds snapshot identity to source/revision,
license note, correction policy, retrieval/availability, coverage dates and
markets, row count, source digest, content digest, and validation status.

The query port is constructed around one pinned immutable snapshot. A corrected
source creates another `source_revision` and `snapshot_id`; it does not mutate a
snapshot already referenced by content digest.

## Research gate

`DATE_EFFECTIVE` evidence can be research-eligible only when status, coverage,
row count, and both digests validate for the requested session. A
`CURRENT_SNAPSHOT` is always `research_eligible=false` and reports both
`PIT_UNIVERSE_MISSING` and `SURVIVORSHIP_LIMITED`.

Missing coverage/digest, an out-of-range session, a digest mismatch, overlapping
records, or an unvalidated artifact reports `PIT_UNIVERSE_MISSING`. In that
state `research_members` is empty and cross-sectional diagnostics, matched
controls, and formal research are explicitly disallowed.

## Runtime separation

This contract does not replace `market_data.instrument_reference`.
`InstrumentReferenceStore.eligible()` remains the current-session source for
live subscription admission and price-limit behavior.

Any incompatible field or evidence-rule change requires a new schema version
and new golden fixtures; v1 readers reject missing and unknown fields.
