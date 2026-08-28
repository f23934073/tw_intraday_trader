# Findings & Decisions

## Requirements

- Keep the collector passive: foundation flags off, `subscribe_trade=false`, no order, position, or consumer-authority change.
- Preserve frozen market-event, watermark, Health/Admission, and Freshness contracts.
- Complete D-HEALTH-LATE-001 through real finalized capture artifacts; never fabricate, filter, or overwrite evidence.

## Research Findings

- The retained 2026-08-26 MID session is `COMPLETE`, contains all required reference/projection artifacts, and exact replay passed ten times.
- The retained 2026-08-27 MID session has a finalized journal and a checksummed three-entry callback quarantine, but exact replay rejects a journal event outside its captured session calendar.
- The current capture code already distinguishes fully accounted callback quarantine from a hard callback failure; the immediate blocker is replay input validity, not a request to relax Health semantics.
- The rejected records have event timestamps `11:00:00.042`–`11:00:00.103` with a MID capture phase ending at `11:00`, while the exchange's actual session continues to `13:30`. The bootstrap artifact incorrectly encoded the collection phase as the exchange session calendar.

## Technical Decisions

| Decision | Rationale |
|---|---|
| Diagnose before modifying the adapter | The exact record must establish whether this is timestamp interpretation, stale callback delivery, or an implementation defect. |
| Keep quarantined raw callbacks separate from canonical ingress | Invalid provider payloads cannot be converted into invented Tick/BidAsk market events. |
| Encode the exchange regular session in replay metadata and collection phase separately | `session_phase` already identifies the collection sub-window; exact replay's calendar must describe the official 09:00–13:30 session. |
| Seal the scheduled OPEN run at commit `c4a59ea` | The clean dedicated worktree's manifest and runner/interpreter hashes were verified before the 08:55 LaunchAgent was replaced. |
| Restore CLOSE recurrence at 12:50 on weekdays | It sits inside the existing ten-minute pre-connect allowance and remains an evidence-only command. |

## Issues Encountered

| Issue | Resolution |
|---|---|
| Workspace has unrelated dirty files and a different active planning pointer | Limit edits to this dedicated plan and D-HEALTH files. |
| The dedicated runtime's full suite cannot collect seven FastAPI API modules | Its minimal virtual environment lacks FastAPI; 42 D-HEALTH focused tests pass and the capture path has no FastAPI dependency. |
| Main workspace full suite has one FinMind selection-bundle drift failure | `1749 passed, 88 skipped, 1 failed`; the failing assertion reads mutable FinMind job state outside this scope. |

## Resources

- `records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/`
- `records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/`
- Sealed runtime: `/Users/stevehuang-work/Documents/worktrees/tw_intraday_trader_d_health_open_20260828` at `c4a59eabf81b7c7f0839a9d342ccb2b650e9f529`
- Loaded launch configuration: `research/late_delivery_evidence/runtime/d_health_open_20260828_calendar_fix.launchagent.plist`
