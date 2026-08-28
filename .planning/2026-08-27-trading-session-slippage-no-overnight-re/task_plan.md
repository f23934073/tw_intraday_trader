# Task Plan: Trading-session slippage, No-Overnight campaigns, and release review

## Goal
Start safe, no-real-money evidence collection for slippage and No-Overnight, and prepare formal release reviews for the two exact local commits without push, PR, merge, broker orders, or Gate promotion.

## Current Phase
Phase 3

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm exact branches, commits, task threads, current time, and dirty-worktree boundaries.
- [x] Read the exact slippage and No-Overnight campaign/release runbooks.
- [x] Resolve safe commands, schedules, artifact roots, and qualification rules.
- **Status:** completed

### Phase 2: Parallel Dispatch
- [x] Continue the existing slippage task for trading-session capture and candidate release evidence.
- [x] Continue the existing No-Overnight task for DISABLED/OBSERVE_ONLY campaign execution and candidate release evidence.
- [x] Continue the existing Shadow task as an independent read-only release reviewer for both exact commits.
- **Status:** completed

### Phase 3: Runtime Evidence
- [ ] Start only the safe in-session slippage capture supported by the runbook.
- [x] Resolve partial No-Overnight eligibility: runbook forbids a post-cutoff window, so none was created or backdated.
- [ ] Schedule or prepare full-session DISABLED and OBSERVE_ONLY runs without overlapping incompatible modes.
- **Status:** in_progress

### Phase 4: Release Review
- [x] Verify exact branch/HEAD/base, clean payload, range-diff, tests, and PostgreSQL evidence.
- [x] Obtain independent review verdicts with P1/P2 findings and Gate status.
- [x] Do not publish or merge any branch.
- **Status:** completed

### Phase 5: Supervision & Delivery
- [x] Install a one-time PM supervision heartbeat for the post-close child-task outcomes.
- [ ] Monitor existing tasks until completion or explicit blocker.
- [ ] Record artifact paths, runtime outcomes, incomplete-session boundaries, and next eligible session.
- [ ] Restore the prior active plan after the bounded current work is handed off.
- [ ] Report completion separately from trading qualification and live authority.
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Reuse the three existing tasks | The user asked to execute the follow-on work; duplicate tasks would fragment branch and review history. |
| Today after 12:22 can only contribute partial evidence | A mid-session start cannot satisfy a full-session campaign or complete trading-day calibration. |
| No push, PR, merge, broker order, or Gate promotion | These actions are outside the user's current authorization. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Independent reviewer task was archived | Unarchive the existing task, then send the same read-only review prompt; do not create a duplicate task. |
| Reviewer test temp directory unavailable | Rerun with approved writable non-worktree temp root; do not count the uncollected run as pass or failure. |
| Integrated No-Overnight preflight blocked by active legacy runner | Preserve PID 72965 through close; use one 14:00 read-only continuation heartbeat before creating any new schedule. |
