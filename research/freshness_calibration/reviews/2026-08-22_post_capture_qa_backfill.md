# Post-capture structural QA backfill — 2026-08-22

## Purpose and grain

This is a read-only structural QA backfill over the eight immutable
Tick/BidAsk freshness artifacts captured on 2026-08-20 and 2026-08-21. One row
below represents one capture artifact. It does not select any threshold,
qualify a session regime, or change `FreshnessPolicyV1`.

The QA checks digest/schema, frozen-cohort group coverage, per-symbol
Tick/BidAsk acknowledgement, per-observation `CONNECTED/ACTIVE` lifecycle,
callback errors, callback-monotonic regressions, and retained source-clock
skew. Source-clock skew is an anomaly/provenance count only, never a latency
SLA input.

## Results

| Artifact | Session label | Rows | Frozen-group coverage | QA disposition | Material observation |
|---|---|---:|---:|---|---|
| `quote_20260820T090534+0800.json` | `continuous_discovery` | 494 | 0/6 | `REVIEW_REQUIRED_WITH_QUALITY_ISSUES` | Discovery cohort; excluded from frozen-cohort evidence. |
| `quote_20260820T091616+0800.json` | `opening` | 1,048 | 6/6 | `REVIEW_REQUIRED_WITH_QUALITY_ISSUES` | All rows are pre-lifecycle-fix non-`CONNECTED/ACTIVE`; retained as rejected raw evidence. |
| `quote_20260820T092834+0800.json` | `opening` | 117 | 3/6 | `REVIEW_REQUIRED_PARTIAL_COVERAGE` | Valid lifecycle and acknowledgement, incomplete opening callbacks. |
| `quote_20260820T093046+0800.json` | `continuous` | 1,513 | 6/6 | `REVIEW_REQUIRED` | Structurally complete; needs human cross-session review. |
| `quote_20260820T095444+0800.json` | `continuous` | 1,621 | 6/6 | `REVIEW_REQUIRED` | Structurally complete; needs human cross-session review. |
| `quote_20260820T101439+0800.json` | `continuous` | 1,872 | 6/6 | `REVIEW_REQUIRED` | Structurally complete; needs human cross-session review. |
| `quote_20260820T130116+0800.json` | `close` | 2,092 | 5/6 | `REVIEW_REQUIRED_PARTIAL_COVERAGE` | Low-cohort Tick absent; does not cross 13:30. |
| `quote_20260821T130144+0800.json` | `close` | 1,497 | 5/6 | `REVIEW_REQUIRED_PARTIAL_COVERAGE` | Repeats low-cohort Tick absence; does not cross 13:30. |

All artifacts had zero callback errors and zero callback-monotonic regressions.
Source-clock-skew observations remain present in every artifact and are not
used to infer a transport latency threshold.

## Disposition

The automated QA agrees with the prior human review: three continuous samples
are structurally complete; close evidence remains partial; and no historical
artifact is promoted into a threshold decision. New scheduler captures will
append the same structural summary to their run record. A human review still
owns qualitative evidence disposition and any future `FreshnessPolicyV1`
freeze.

```text
FreshnessPolicyV1: BLOCKING_EVIDENCE
Phase 0:           NOT COMPLETE
Phase 1:           BLOCKED
```
