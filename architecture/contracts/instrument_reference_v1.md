# `instrument-reference-v1` contract

Status: `FROZEN` for P1.1b artifact identity and loading semantics.

This artifact answers what each captured symbol represented for one market
session. It is immutable replay input, not an issuer master, corporate-action
history, or replacement for the runtime `InstrumentReferenceStore`.

## Artifact location and root schema

The session directory contains one file:

```text
instrument_reference.json
```

Its root object is:

```json
{
  "schema": "instrument-reference-v1",
  "artifact_id": "01K...",
  "session_id": "20260820-live-a1",
  "session_date": "2026-08-20",
  "timezone": "Asia/Taipei",
  "status": "FINALIZED",
  "source": {
    "provider": "SHIOAJI",
    "source_mode": "CONTRACT_LOOKUP",
    "source_identity": "shioaji-contracts-20260820",
    "captured_at": "2026-08-20T08:50:00+08:00"
  },
  "reference_count": 1,
  "content_sha256": "...",
  "references": []
}
```

`status` is `FINALIZED` or `INCOMPLETE`. Only `FINALIZED` artifacts may enter
exact replay qualification. Existing files are never overwritten.

## Reference entry

Each `references` entry contains exactly:

```json
{
  "instrument_id": "TWSE:2330",
  "symbol": "2330",
  "exchange": "TWSE",
  "security_type": "STOCK",
  "name": "台積電",
  "valid_from": "2026-08-20",
  "valid_to": "2026-08-20",
  "reference_price": "1180.00",
  "limit_up_price": "1295.00",
  "limit_down_price": "1065.00",
  "price_limit_applies": true,
  "trading_unit_shares": 1000,
  "source_updated_at": "2026-08-20",
  "source_identity": "TSE:2330"
}
```

- `instrument_id` is the point-in-time key `<exchange>:<symbol>`. It does not
  claim issuer continuity across symbol, exchange, or corporate-action changes.
- `security_type` is the captured provider-normalized type. Replay does not
  infer it from the symbol.
- `valid_from` and `valid_to` are inclusive. A session-only source may set both
  to `session_date`; that is a bounded statement, not fabricated history.
- Prices are positive base-10 decimal strings. JSON binary floating point is
  forbidden.
- If `price_limit_applies` is true, both limit prices are required and must
  bracket `reference_price`. Otherwise both are null.
- `trading_unit_shares` is a positive integer. Units are shares, not lots.
- `source_identity` preserves the provider key used to obtain the reference.

Entries are unique by both `instrument_id` and `(exchange, symbol)`, and are
sorted by `exchange`, `symbol`, then `instrument_id` before encoding.

## Digest and canonical encoding

The file is canonical UTF-8 JSON with a terminal newline. Object keys are
sorted, separators contain no insignificant whitespace, timestamps are
timezone-aware ISO 8601, and dates use `YYYY-MM-DD`.

`content_sha256` is the lowercase SHA-256 of the canonical JSON encoding of:

```text
schema + artifact_id + session_id + session_date + timezone + source + references
```

The digest excludes `status`, `reference_count`, and `content_sha256` so those
cross-fields can be verified independently. It is distinct from the current
runtime store digest; an exact replay loader projects the artifact into the
runtime model and verifies the expected initial runtime digest declared by
`projection-state-v1`.

## Finalization and replay gates

A `FINALIZED` artifact requires:

- `reference_count == len(references)` and at least one reference;
- `session_date` lies within every entry's validity interval;
- every `source_updated_at` equals `session_date` for v1 live qualification;
- every journal market symbol resolves to exactly one reference;
- all identities, invariants, ordering, and digests validate.

Missing fields, unknown fields, duplicate identities, missing journal symbols,
invalid limits, stale source dates, cross-session identity, or digest mismatch
are fatal. The loader does not fill names, security types, prices, dates,
limits, units, or identities from defaults or current provider data.
