# Findings & Decisions

## Requirements
- Replace the Replay-only ``盤中動能`` view with a live intraday view.
- Continuously evaluate every current candidate with the intraday strategy set.
- Show every candidate's score, matched strategies/rules, and the evaluated values.
- Make source and freshness visible so fixed/replayed data cannot be mistaken for live market data.
- Preserve the repository's data-only/local-paper boundaries: no broker order submission.

## Research Findings
- The existing Momentum page explicitly declares ``REPLAY_ALERT_ONLY`` and ``is_live: false``. Its 8039 / 100 score is derived from an immutable test fixture, not Shioaji.
- The repository already has a Shioaji Tick/BidAsk streaming contract and a ``runtime/momentum_shadow.py`` path. It serializes callback processing, evaluates ``FeatureEngine`` + ``MomentumSignalEngine`` per Tick, exposes ``MomentumProjection`` evidence details, and enforces freshness for both Tick and BidAsk streams.
- The Shadow runtime already exposes discovered/admitted/covered symbols and a per-symbol miss reason. It can therefore distinguish an unscored candidate caused by stream warm-up or capacity from a genuine zero-score candidate.
- The current browser fetches the Momentum API every two seconds, but rerenders only when the server projection digest changes. Replacing the data source preserves the polling mechanism.
- ``ShioajiProvider`` also exposes a simpler Tick/BidAsk quote stream for local-paper positions, but its normalized update lacks the volume and aggressor inputs used by Momentum features. The richer ``ShioajiMomentumStream`` must remain the data source for this score.
- One Shioaji Tick+BidAsk pair consumes two quote subscriptions and the existing provider limit is 200 subscriptions / 100 symbols. The dashboard must list capacity-excluded candidates with a specific unavailable reason rather than falsely claim they were evaluated.
- The primary dashboard refresh also projects the independently evolving premarket context. The realtime candidate loader must call a dedicated scan-only method so its 30-second cadence cannot create or rewrite premarket artifacts.
- Local browser smoke with ``PROVIDER=mock`` and blank Shioaji credentials showed the Momentum workspace's explicit ``即時資料不可用`` / ``即時盤中動能未啟動`` state; it did not render the old 8039 Replay fixture. The main Snapshot page retained an unrelated HTTP 500 from the premarket artifact integrity collision seen in the full regression.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| A projection contains both score and evidence values | A total score alone cannot explain which strategy qualified or why. |
| Candidate symbols, scoring, and stream subscriptions share one server-owned lifecycle | Avoid a browser/frontend view disagreeing with the symbols being evaluated. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
