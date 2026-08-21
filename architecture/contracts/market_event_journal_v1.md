# `market-event-journal-v1` contract

Status: `FROZEN` for the P1.1 durable-journal slice.

This contract preserves the canonical market-data timeline. It does not change
MarketDataStore, Candidate, Score, Position, Freshness thresholds, Shioaji
runtime ownership, or consumer authority.

## Artifact layout

```text
records/market_events/<session_date>/<session_id>/
├── records.jsonl
└── manifest.json
```

The session directory and both files use exclusive-create behavior. An
existing session is never overwritten.

`records.jsonl` is the sole authoritative timeline. Tick, BidAsk,
dispositions, and system incidents are not split into separate files.

## Record order and identity

- Every row is canonical UTF-8 JSON terminated by `\n`.
- `record_index` starts at 1 and increases by exactly 1 for every JSONL row.
- Pipeline ingress indices remain internal adapter inputs.
- A `DISPOSITION.ingress_record_index` points to the global journal
  `record_index` of its preceding `INGRESS` row.
- Recorded ingress/lifecycle `ingress_sequence` values are strictly increasing;
  gaps are allowed because failed admission attempts consume a sequence.
- Source-event time may move backward. Such an event remains evidence and its
  semantic rejection is preserved in `DISPOSITION`.

## Record types

### `INGRESS`

```json
{
  "record_type": "INGRESS",
  "record_index": 1,
  "event": {}
}
```

`event` is the complete frozen `market-event-v1` envelope. No event identity,
source, timestamp, sequence, or payload field is rewritten for recording.

### `DISPOSITION`

```json
{
  "record_type": "DISPOSITION",
  "record_index": 2,
  "ingress_record_index": 1,
  "event_id": "...",
  "result": {
    "status": "APPLIED",
    "event_id": "...",
    "symbol": "2330",
    "stream_kind": "TICK",
    "previous_watermark": null,
    "new_watermark": {
      "event_time": "2026-08-20T09:00:01+08:00",
      "ingress_sequence": 1
    },
    "projection_applied": true,
    "reason": null,
    "health_before": "HEALTHY",
    "health_after": "HEALTHY"
  }
}
```

Rejected, duplicate, invalid, and out-of-order events are retained. A
finalized session requires exactly one disposition for every market ingress.

### `SYSTEM_INCIDENT`

```json
{
  "record_type": "SYSTEM_INCIDENT",
  "record_index": 3,
  "incident": {
    "event_id": "...",
    "session_id": "...",
    "incident_type": "RECONNECT",
    "occurred_at": "2026-08-20T09:00:02+08:00",
    "ingress_sequence": 2,
    "source_identity": "...",
    "reason": "...",
    "symbol": null,
    "raw_event_code": null,
    "raw_info": null
  }
}
```

P1.1 first-slice wiring maps dequeued `LifecycleIngressMessage` values to this
record type. Production queue-overflow and derived health-transition wiring
remain outside this flags-off slice.

## Durability boundary

For each row:

```text
write
  ↓
flush
  ↓
fsync
  ↓
return to pipeline
```

An `INGRESS` cannot reach `MarketDataIngestor` until this boundary succeeds.
Write, flush, or `fsync` failure closes admission through the existing pipeline
failure path, blocks DataHealth, and leaves the session `INCOMPLETE`.

Group commit is not part of v1. It requires a separate evidence-backed change.

## Manifest lifecycle

The writer durably creates an initial manifest with:

```text
status = INCOMPLETE
incomplete_reason = SESSION_OPEN
```

Only a queue-drained session with a disposition for every market ingress can
atomically replace it with `FINALIZED`.

The manifest contains:

- journal and market-event schemas;
- session ID/date/timezone and producer/source metadata;
- record count and first/last record index;
- exact `records.jsonl` SHA-256;
- accepted/rejected/incident counts;
- expected Bar/Book/Health digests supplied at finalization;
- queue-drained and finalization evidence;
- an incomplete reason when applicable.

File existence does not prove completeness. Only a verified `FINALIZED`
manifest may enter deterministic replay qualification.

## P1.1 first-slice verifier

The CLI command is:

```bash
python -m market_data.replay_cli \
  --session records/market_events/2026-08-20/<session_id> \
  --verify
```

It returns non-zero for incomplete, corrupt, tampered, truncated,
non-canonical, schema-invalid, out-of-order-row, or broken-disposition-link
artifacts.

This first CLI slice verifies durable artifact integrity. It intentionally does
not claim projection replay: exact projection replay requires the original
instrument-reference/bootstrap inputs, whose journal contract is not frozen in
this slice. The CLI reports that boundary explicitly.

P1.1b extends the same command without changing Journal v1: supplying finalized
`--bootstrap` and `--instrument-reference` artifacts activates
`projection-state-v1` exact mode. Journal-only invocation retains this P1.1a
integrity behavior.
