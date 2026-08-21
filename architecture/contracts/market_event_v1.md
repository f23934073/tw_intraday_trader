# `market-event-v1` Contract

Status: frozen for P1 Canonical Market Event Pipeline.

## Discriminator and version

- `schema_version` must equal `market-event-v1`.
- `stream_kind` is the payload discriminator and must be `TICK` or `BIDASK`.
- v1 does not add duplicate `event_type` or `payload_version` fields.
- Unknown versions, missing fields, and unknown fields fail closed.

## Envelope fields

| Field | Contract |
|---|---|
| `event_id` | Non-empty event identity; preserved by recording and replay |
| `schema_version` | Exactly `market-event-v1` |
| `session_id` | Non-empty runtime market-session identity |
| `session_date` | ISO date matching the payload and `event_at` date |
| `source` | Original market-data provenance; replay must not rewrite it |
| `source_mode` | Adapter/SDK quote mode, not replay-runner mode |
| `stream_kind` | `TICK` or `BIDASK`; must match the payload type |
| `symbol` | Canonical symbol matching the payload |
| `event_at` | Timezone-aware source event time |
| `received_at` | Timezone-aware callback receipt wall time |
| `ingress_sequence` | Non-negative admission sequence matching the payload |
| `source_identity` | Non-empty provider/source evidence identity |
| `payload` | Full immutable Tick or BidAsk payload |
| `raw_capture_id` | String evidence link or `null`; never inferred |

The envelope and payload must agree on `event_id`, `source`, `symbol`,
`session_date`, event time, received time, and ingress sequence.

## Canonical JSON

- Field names are fixed and explicitly enumerated.
- Object keys are sorted and separators contain no extra whitespace.
- Decimal values are JSON strings, never binary floating-point numbers.
- Dates and datetimes use ISO-8601; datetimes include a UTC offset.
- Enum values use their declared uppercase string values.
- BidAsk tuple order is preserved as JSON array order.
- `raw_capture_id` is always present and may be `null`.

The executable codec is `market_data.serialization`. Golden artifacts are:

- `tests/fixtures/market_events/v1/tick.json`
- `tests/fixtures/market_events/v1/bidask.json`

## Ordering boundary

`ingress_sequence` is transport admission evidence, not a global exchange
timeline. Semantic watermarks remain independent for each
`(session_id, symbol, stream_kind)`. Tick and BidAsk are not reordered against
each other.

## Change rule

Any incompatible field, payload, source-time, or discriminator change requires
a new schema version and new golden fixtures. v1 readers must not guess defaults
for newer data.
