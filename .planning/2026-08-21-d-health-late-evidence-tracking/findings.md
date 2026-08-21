# Findings & Decisions

## Requirements
- Implement D-HEALTH-LATE-001 as real-market, data-only Tick/BidAsk evidence collection.
- Do not modify Health, Admission, Freshness, watermark, market-event, or trading logic.
- Preserve flags-off, subscribe_trade=false, disconnected order path, and unchanged consumer authority.
- Capture at OPEN (09:00–09:30), MID (10:30–11:00), and CLOSE (13:00–13:30); retain all outcomes.
- Track individual late events and daily summaries by stream, symbol, and phase. Do not set thresholds.
- High-liquidity seed symbols are 2330, 2317, and 2454. Medium/low symbols require provenance-backed selection rather than inference.

## Initial Evidence
- Clock correction removed the prior systematic host-clock offset. The corrected Case A attempt had zero source-ahead timestamps but one natural BidAsk late delivery.
- The current Health contract degrades every OUT_OF_ORDER event and blocks new admission. This behavior must be observed, not changed.
- The existing Case A/B harness is intentionally single-symbol and classification-driven, so it is not itself the D-HEALTH-LATE collection interface.

## Repository Findings
- `ShioajiMomentumStream` already supports independent paired Tick/BidAsk subscribe requests per symbol and connects with `subscribe_trade=False`.
- `HistoricalQualificationCapture` creates a canonical queue, durable JSONL journal, projection state, and exact replay evidence, but only accepts one symbol and applies Case A/B classification.
- The existing Freshness collector is multi-symbol but writes a separate in-memory calibration artifact; it does not produce canonical journal/disposition/projection evidence and must not replace the new collector.
- A prior-completed-session TWSE-backed Freshness manifest demonstrates a provenance pattern for high/mid/low labels. It contains only three symbols and does not satisfy this report's 6–9-symbol target.
- The worktree is already dirty with substantial unrelated work. New changes must stay scoped to D-HEALTH-LATE files and must not overwrite existing edits.
- The Codex app exposes `automation_update`; schedule creation will be deferred until the daily runner exists and has passing tests.
- `automation_update` requires a `mode` discriminator; the first schema probe made no change and returned the valid modes.
- The canonical journal records INGRESS before projection and pairs every market ingress with a durable DISPOSITION. This makes an offline ledger extractor sufficient to preserve late-delivery ordering and effects.
- The capture worker must subscribe all symbols before opening the common capture gate; callbacks received before the paired acknowledgements remain pre-boundary evidence rather than silently entering the journal.
- Exact replay's existing artifact contracts already accept an ordered list of references, subscriptions, and bootstrap symbols, so no replay-contract revision is required for a multi-symbol collector.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| `OUT_OF_ORDER_REJECTED` is the sole late-delivery observation signal | It is already the durable, contract-compliant source-time regression disposition. |
| Session ledger lives beside the finalized journal; daily summary scans those ledgers | Preserves append-only source evidence and supports idempotent daily aggregation. |
| Session phase derives from `received_ts` in Asia/Taipei | It represents when the runtime experienced the delivery condition. |
| Consecutive count is per `(symbol, stream_kind)` and resets on an applied disposition for that key | This makes clustering observable without a threshold or health interpretation. |
| New collector finalizes/replays sessions but never classifies Case A/B | Collection success is artifact integrity and replay parity, not Health state. |

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- User-supplied report: `/Users/stevehuang-work/.codex/attachments/638335e3-6714-4417-86c6-06976fbadcd2/pasted-text.txt`
- Existing qualification CLI: `market_data/qualification_capture_cli.py`
- Existing capture runtime: `market_data/qualification_capture.py`
