# P1.1b Historical Qualification Capture Runbook

Status: harness ready; real Case A and natural Case B evidence still pending.

## Safety boundary

This is a standalone data-only process. It asserts every
`FOUNDATION_FEATURE_FLAGS` value is false, logs in with
`subscribe_trade=False`, subscribes only common-lot Tick and BidAsk, and never
imports an order, position, Candidate, Score, or production-runtime authority.
Running it cannot unlock P1.2.

The callback only normalizes and admits an immutable event into the bounded
queue. Durable Journal append (`flush` + `fsync`) still precedes projection.

## Case A command

Start shortly before 09:00. The harness may wait up to ten minutes for regular
session open; it does not admit pre-boundary callbacks.

```bash
.venv/bin/python -m market_data.qualification_capture_cli \
  --symbol 2330 \
  --duration-seconds 300 \
  --case A
```

The command uses existing `.env` credential names. It never prints credentials.
An explicit `--session-id` and `--records-root` may be supplied when required.
Session and prior-session dates come from the reviewed, source-linked
`config/twse_calendar_2026.json`; the TAIFEX calendar is not reused as equity
evidence.

Exit `0` requires both Tick and BidAsk evidence, a normal semantic Health
timeline, a finalized Journal, and all four exact-replay digests matching over
ten runs. Missing streams, callback/queue/recorder failures, rejection,
degraded Health, incomplete artifacts, or replay mismatch return non-zero.

## Case B command

Run the same harness only while waiting for a naturally occurring incident:

```bash
.venv/bin/python -m market_data.qualification_capture_cli \
  --symbol 2330 \
  --duration-seconds 1800 \
  --case B
```

There is intentionally no incident-injection option. A Case B pass requires a
real incident, rejection, or semantic Health degradation from the provider
timeline plus exact replay parity. A normal run requested as Case B fails with
`CAPTURE_CLASSIFIED_CASE_A_NOT_CASE_B` and remains useful only as non-promoting
evidence.

## Output

Each attempt owns one exclusive session directory:

```text
records/market_events/<session_date>/<session_id>/
├── records.jsonl
├── manifest.json
├── instrument_reference.json
├── bootstrap_snapshot.json
├── projection_state.json
└── qualification_report.json
```

Failed attempts may intentionally have fewer files and an `INCOMPLETE`
manifest. Existing artifacts are never overwritten. A successful report still
states `gate_effect: NONE_P1_2_REMAINS_BLOCKED`; Case A and a separately
reviewed natural Case B are both required before changing the architecture
gate.
