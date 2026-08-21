# `bootstrap-snapshot-v1` contract

Status: `FROZEN` for P1.1b empty-session reconstruction.

This immutable artifact preserves the market/session context known before the
first journal event. It is not an alternate event log and does not manufacture
Tick, BidAsk, Bar, or Book state.

## Artifact location and root schema

The session directory contains one file:

```text
bootstrap_snapshot.json
```

Its root object is:

```json
{
  "schema": "bootstrap-snapshot-v1",
  "artifact_id": "01K...",
  "session_id": "20260820-live-a1",
  "session_date": "2026-08-20",
  "timezone": "Asia/Taipei",
  "status": "FINALIZED",
  "source": {
    "provider": "SHIOAJI",
    "source_mode": "SNAPSHOT_BOOTSTRAP",
    "source_identity": "snapshot-20260820-085500"
  },
  "captured_at": "2026-08-20T08:55:00+08:00",
  "received_at": "2026-08-20T08:55:01+08:00",
  "journal_boundary": {},
  "calendar": {},
  "coverage": {},
  "subscriptions": [],
  "symbols": [],
  "projection_seed_mode": "EMPTY_SESSION",
  "content_sha256": "..."
}
```

`status` is `FINALIZED` or `INCOMPLETE`. Only `FINALIZED` is exact-replay
eligible. Existing files are never overwritten.

## Journal boundary

`journal_boundary` contains exactly:

```json
{
  "first_record_index": 1,
  "first_ingress_sequence": 1,
  "projection_started_at": "2026-08-20T08:59:59+08:00"
}
```

The artifact must have been received no later than `projection_started_at`, and
the declared boundary must match the journal. Replay preserves these recorded
times; it never replaces them with the current clock.

## Calendar and coverage

`calendar` contains a stable calendar ID/version, `session_phase`,
`scheduled_open`, and `scheduled_close`. Both schedule timestamps are
timezone-aware and must cover `projection_started_at` and all journal events.

`coverage` contains sorted, unique `required_instrument_ids`,
`captured_instrument_ids`, and `missing_instrument_ids`. A finalized artifact
requires captured equals required and missing is empty. Each ID must resolve in
the paired `instrument-reference-v1` artifact.

## Symbol context

Each sorted `symbols` entry contains exactly:

```json
{
  "instrument_id": "TWSE:2330",
  "symbol": "2330",
  "prior_session_date": "2026-08-19",
  "previous_close": "1175.00",
  "previous_session_volume_lots": 27543,
  "source_identity": "snapshot:TSE:2330"
}
```

Prices are positive decimal strings. Volume is a non-negative integer in lots.
Values must come from the captured artifact; replay does not derive them from
the first Tick or from current provider data.

The current float-based `StockData` is a compatibility source, not this
contract. In particular, conversion-time `datetime.now()` is not valid
bootstrap provenance.

## Initial subscription state

Each sorted `subscriptions` entry contains `instrument_id`, `stream_kind`,
`state`, `effective_at`, and `evidence_identity`. `stream_kind` is `TICK` or
`BIDASK`; `state` uses the frozen subscription lifecycle vocabulary. `UNKNOWN`
or missing evidence makes the artifact incomplete.

Only state effective before the journal boundary belongs here. Subscribe ACK,
timeout, reconnect, resync, or unsubscribe transitions after the boundary must
remain ordered journal evidence and must not be backfilled into this file.

## Seed authority

P1.1b v1 freezes `projection_seed_mode` to `EMPTY_SESSION`:

- Bar starts with no bars, ticks, watermarks, or cumulative-volume state.
- Book starts with no events, snapshots, or watermarks.
- DataHealth initialization is defined by `projection-state-v1`.
- `previous_close` and previous-session volume are context for later consumers;
  they do not create synthetic intraday market events or projection entries.

A live session restored from prior in-process or persisted Bar/Book/Health state
is not representable by this v1 contract. Exact replay must fail with
`RESTORED_STATE_UNSUPPORTED`, not silently replay it as empty.

## Digest and finalization gates

Canonical JSON and SHA-256 rules match `instrument-reference-v1`.
`content_sha256` covers every root field except `status` and
`content_sha256` itself.

A finalized artifact requires valid session/timezone identity, complete symbol
coverage, matching reference identities, valid calendar/boundary ordering,
known subscription states, and a valid digest. Missing, synthetic, incomplete,
tampered, cross-session, post-boundary, or restored-state inputs are fatal.
