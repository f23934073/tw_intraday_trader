# `projection-state-v1` contract

Status: `FROZEN` for P1.1b exact replay implementation.

This artifact binds one finalized Journal, InstrumentReference artifact, and
Bootstrap artifact to explicit projection versions, initial state, and expected
parity outputs. It prevents an exact replay runner from choosing hidden
defaults.

## Exact replay input tuple

One replay qualification is exactly:

```text
market-event-journal-v1
+ instrument-reference-v1
+ bootstrap-snapshot-v1
+ projection-state-v1
+ compatible replay implementation
```

All artifacts must be `FINALIZED`, share session ID/date/timezone, match the
declared SHA-256 values, and pass their own schema validation.

The session directory contains `projection_state.json` with this root shape:

```json
{
  "schema": "projection-state-v1",
  "artifact_id": "01K...",
  "session_id": "20260820-live-a1",
  "session_date": "2026-08-20",
  "timezone": "Asia/Taipei",
  "status": "FINALIZED",
  "input_digests": {},
  "versions": {},
  "initialization": {},
  "expected_final": {},
  "content_sha256": "..."
}
```

## Input and implementation identity

`input_digests` contains the exact Journal file SHA-256 plus the reference and
bootstrap content SHA-256 values. `versions` contains explicit identifiers for
the Ingestor, Bar projection, Book projection, DataHealth projection, and exact
replay engine. Unknown or incompatible versions fail closed; code version is
never inferred from the current checkout.

The executable v1 identifiers are:

```json
{
  "ingestor": "market-data-ingestor-v1",
  "bar_projection": "bar-projection-digest-v1",
  "book_projection": "book-projection-digest-v1",
  "health_projection": "data-health-replay-v1",
  "replay_engine": "exact-projection-replay-v1"
}
```

`input_digests` contains exactly `journal_sha256`,
`instrument_reference_sha256`, and `bootstrap_sha256`.

## Initial state

P1.1b v1 supports only `initialization.mode = EMPTY_SESSION`.

The object records:

- `initialized_at`, equal to bootstrap `projection_started_at`;
- Bar/Book retention seconds, with the current minimum of 1200 seconds;
- expected initial InstrumentReferenceStore digest after loading the paired
  reference artifact;
- Bar mode `EMPTY`, finalized false, and expected digest of an empty store;
- Book mode `EMPTY`, finalized false, and expected digest of an empty store;
- DataHealth state `STARTING`, empty reasons/streams, zero counters and queue
  values, reconnect epoch zero, no resync evidence, and `as_of` equal to
  `initialized_at`;
- an explicit READY transition time/evidence if the live capture performed one.

`initialization` contains exactly `mode`, `initialized_at`,
`retention_seconds`, `reference_store`, `bar`, `book`, `health`, and
`ready_transition`. `ready_transition` is either null or an object containing
exactly `occurred_at` and `evidence`.

Replay must validate the initial digests before consuming record 1. It may not
call `mark_ready`, seed a projection, choose a timestamp, or load current
reference data unless the action and evidence are declared here.

`RESTORED` state is deliberately unsupported in v1. A session that did not
start empty is ineligible rather than approximately reconstructed.

## Expected final parity

`expected_final` contains a `projection-digest-set-v1` object plus a repeat
count fixed at 10 for qualification:

```json
{
  "digest_set_schema": "projection-digest-set-v1",
  "disposition_v1": {
    "contract": "ingest-disposition-digest-v1",
    "owner": "MarketDataIngestor",
    "sha256": "..."
  },
  "bar_v1": {
    "contract": "bar-projection-digest-v1",
    "owner": "IntradayBarStore",
    "sha256": "..."
  },
  "book_v1": {
    "contract": "book-projection-digest-v1",
    "owner": "OrderBookStore",
    "sha256": "..."
  },
  "health_v1": {
    "contract": "data-health-replay-v1",
    "owner": "ReplaySemanticHealthProjection",
    "sha256": "..."
  }
}
```

The executable enclosing shape is:

```json
{
  "repeat_count": 10,
  "digest_set": {
    "digest_set_schema": "projection-digest-set-v1"
  }
}
```

Each projection owns its digest payload and version. The digest set only binds
those independently versioned results to one replay qualification. A future
`bar-projection-digest-v2` must use a new namespace such as `bar_v2`; it cannot
be compared with or stored under `bar_v1` merely because both values use
SHA-256.

MarketDataStore revision/digest, Candidate, Score, Position, Order, and Strategy
are excluded. Store parity is added only after Phase 3 defines the revisioned
canonical Store projection.

Exact replay succeeds only when all ten fresh runs produce the recorded
dispositions and identical Bar, Book, and selected Health digests. Any mismatch
returns non-zero.

## D-HEALTH-001 — accepted semantic health parity

The accepted digest contract is `data-health-replay-v1`. It is a deterministic
projection of durable journal evidence, not the current runtime
`DataHealthSnapshot.digest`.

Its canonical payload contains:

- session identity;
- an ordered semantic transition sequence linked to journal `record_index`,
  evidence/event identity, incident or disposition type, reason, resulting
  severity, Health state before/after, and admission state before/after;
- final sorted Health reasons and final Health/admission states;
- reconstructable per-stream event/receipt watermarks and applied, duplicate,
  and out-of-order counts;
- reconstructable invalid/session-mismatch/gap/source-clock-skew/overflow
  counts;
- reconnect epoch, resync evidence time, and semantic `as_of` time.

Severity is the transition's deterministic semantic impact:
`INFO`, `DEGRADED`, or `BLOCKED`. It is computed by the versioned Health
projection and is not copied from an unversioned provider string. Admission is
`OPEN` only when semantic Health is `HEALTHY`; otherwise it is
`BLOCK_NEW_ENTRY`. Unchanged state need not emit a transition entry, but its
underlying disposition or incident remains in the Journal.

The digest excludes `queue_depth`, `queue_high_watermark`, worker/consumer
latency, thread state, scheduling timing, and other execution-environment
metrics. A qualified finalized session separately requires
`queue_drained=true` in the Journal manifest. Overflow and recorder failure
remain fail-closed session evidence; an `INCOMPLETE` session is not exact-replay
eligible.

The replay engine must never guess an excluded runtime value to match the live
runtime digest.

## D-DIV-001 — accepted bounded divergence reporting

The current manifest stores only final Bar/Book/Health digests. Therefore:

- a disposition mismatch reports the exact `DISPOSITION.record_index` and its
  linked `INGRESS.record_index`;
- a final-only Bar, Book, or Health mismatch reports its versioned contract,
  expected digest, actual digest, and
  `first_divergence=UNKNOWN_NOT_RECORDED`;
- the CLI never guesses or implies a first divergent event without evidence.

P1.1b v1 adds no checkpoint schema, periodic projection hashes, or hash-chain
lifecycle. Those are a separately versioned forensic capability if later
required.

## Failure contract

Exact mode returns non-zero with a stable reason including, as applicable:

```text
MISSING_REFERENCE_ARTIFACT
MISSING_BOOTSTRAP_ARTIFACT
MISSING_PROJECTION_STATE
INCOMPLETE_REPLAY_INPUT
JOURNAL_INTEGRITY_FAILED
INPUT_DIGEST_MISMATCH
SESSION_IDENTITY_MISMATCH
PROJECTION_VERSION_MISMATCH
RESTORED_STATE_UNSUPPORTED
INITIAL_STATE_DIGEST_MISMATCH
DISPOSITION_MISMATCH
BAR_DIGEST_MISMATCH
BOOK_DIGEST_MISMATCH
DATA_HEALTH_DIGEST_MISMATCH
NON_DETERMINISTIC_REPLAY
```

Canonical encoding and `content_sha256` rules match the other P1.1b artifacts.
No missing input has a default or fallback.

## CLI binding

`projection_state.json` is loaded from the verified session directory. Exact
mode is activated only when both external artifact paths are supplied:

```bash
python -m market_data.replay_cli \
  --session <session_dir> \
  --bootstrap <bootstrap_snapshot.json> \
  --instrument-reference <instrument_reference.json> \
  --verify
```

The CLI owns parsing, rendering, and exit codes only. Artifact loading,
projection reconstruction, and digest comparison remain in the exact replay
application module. Omitting either exact input never falls back to a synthetic
artifact.

## Historical qualification artifact

P1.1b cannot pass on a hand-authored or synthetic bootstrap fixture. The gate
requires one real capture that began from `EMPTY_SESSION` and produced all four
finalized artifacts. Fixture-based unit tests remain useful but do not establish
historical reconstructability.
