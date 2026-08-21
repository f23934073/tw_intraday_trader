# Task Plan: Partial historical backtest pilot

## Goal

Use only already checkpointed Shioaji partitions to create a clearly labelled exploratory backtest dataset, while preserving formal validation/holdout locks and continuing the original download job later without data loss.

## Current Phase

Phase 4 — Live pilot and continuation

## Phases

### Phase 1: Partition and runtime audit

- [x] Reconnect to the configured backtest entry and diagnose its current database identity.
- [x] Confirm the durable job status and retry symbol from sealed acquisition artifacts.
- [x] Define a deterministic eligibility rule for the exploratory dataset.
- **Status:** complete

### Phase 2: Exploratory pilot materialization

- [x] Add an additive CLI/service path that reads checkpointed partitions only.
- [x] Enforce an explicit in-sample date ceiling and exploratory-only manifest issues.
- [x] Refuse empty, unavailable, insufficient-coverage, or checksum-invalid partitions.
- **Status:** complete

### Phase 3: Verification

- [x] Add focused fixture tests for selection, clipping, immutability, and formal-research locks.
- [x] Run focused backtest/downloader regressions and static checks.
- **Status:** complete

### Phase 4: Live pilot and continuation

- [ ] Materialize a bounded pilot from the authoritative repository if it is reachable.
- [ ] Resume the existing Shioaji job only when the Provider allowance permits it.
- [x] Preserve the exact retry point and report the current database-entry blocker.
- **Status:** blocked by external database entry

## Decisions Made

| Decision | Rationale |
|---|---|
| Keep this plan isolated and leave `.planning/.active_plan` unchanged | The active quota-badge plan and broad dirty worktree belong to existing work. |
| Create a new dataset id instead of finalizing the original job | The original job remains an incomplete coverage observation and must continue from the same checkpoints. |
| Keep the pilot exploratory and in-sample only | Partial current-contract coverage cannot support all-market, survivorship-free, validation, or holdout claims. |
| Do not purchase or activate FinMind Sponsor Pro | The user chose the staged Shioaji workflow. |

## Errors Encountered

| Error | Resolution |
|---|---|
| Initial PostgreSQL read was refused because the local listener was not ready | Recheck listener state once, then reconnect read-only only after it is present. |
| Port 5090 later belonged to a newly created unrelated `tsg-single-db` volume; its databases contain no `backtest` schema | Do not stop or mutate the unrelated container. Preserve the builder and wait for the original PostgreSQL/tunnel entry to be restored. |
| Current local SQLite archive contains zero jobs and zero partitions | Do not fabricate a pilot or restart from SQLite; the authoritative 678 partitions must be reachable first. |
