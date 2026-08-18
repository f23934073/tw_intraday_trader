# Findings & Decisions

## Requirements
- Automatically synchronize historical Kbars after the Taiwan market closes.
- Download only incremental/recent data rather than the complete three-year range each day.
- Preserve prior immutable datasets and database-backed backtest lineage.
- Keep the process resumable and observable; browser reads must not trigger synchronization.
- Continue to use Provider-backed Kbars and Asia/Taipei timestamps.

## Research Findings
- The current CLI freezes `start_date` and `end_date` at job creation, downloads one compressed symbol partition at a time, then seals a new immutable dataset.
- A completed `--resume` job returns its existing manifest; it cannot advance that dataset to a new date.
- Dashboard candidate history is fetched on demand and cached until an explicit dashboard refresh; it is separate from backtest datasets.
- The realtime one-minute `IntradayBarStore` is session-memory state with finite retention and is not a historical-dataset persistence path.
- The workspace contains extensive uncommitted prior work. Changes for this task must stay surgical and preserve all unrelated files.
- `HistoricalDatasetCatalog.load_bars()` verifies the full immutable JSONL checksum and sorts bars for the engine, while `create_provider_dataset_from_partitions()` seals symbol-grouped partitions in streaming order.
- `BacktestApplicationService` owns the repository, catalog, and a bounded worker pool; this is the appropriate application boundary for scheduler submission and read-only sync status.
- The current FastAPI lifespan only performs shutdown cleanup and does not initialize/start a scheduler. Backtest service creation is lazy, so an automatic scheduler must deliberately create the service at startup when enabled.
- The current job repository supports generic JSON request payloads but lacks job listing/idempotent creation by session. A small repository query is needed to detect active work and an existing scheduled session.
- The resumable downloader stores one compressed delta partition per symbol and already provides the required crash-safe checkpoint mechanism; incremental sync should reuse its encoding/decoding behavior rather than introduce a second checkpoint format.
- Configuration currently has no scheduling or incremental-sync settings.
- Existing dataset jobs are generic durable records with JSON request payloads; deterministic `job_id` plus atomic create-if-absent can provide cross-thread/process session idempotency without a new table.
- Existing full provider datasets are stored as a complete `bars.jsonl`. Copying this potentially huge file every day would defeat incremental sync; daily versions should be immutable delta layers referencing a parent dataset.
- A manifest extension can remain backward-compatible by defaulting old manifests to `JSONL_FULL_V1`; incremental manifests can use `JSONL_DELTA_V1`, parent id, delta count, and per-symbol last timestamps.
- Current `load_bars()` already materializes all bars for the backtest engine. Layered loading does not worsen that engine boundary, while avoiding daily disk duplication.
- Existing resumable job tests use SQLite and MockProvider with real catalog files, providing a good location for incremental version/dedup/resume contracts.
- The local server starts through a single `uvicorn.run("dashboard.server:app")`; no reload/multi-worker flag is configured by the project entrypoint.
- There is currently no READY dataset in the live SQLite database. Two full-download jobs are marked RUNNING, so automatic incremental sync must remain in `WAITING_FOR_BASE`/`BLOCKED_BY_ACTIVE_JOB` until bootstrap finishes.
- The Postgres adapter already applies forward-only SQL migrations, but the proposed generic-job extension does not require a schema migration.
- `ON CONFLICT(job_id) DO NOTHING` works through the shared SQLite/PostgreSQL DB-API adapter and gives the scheduler an atomic deterministic session claim.
- MockProvider seed plus next-day sync confirms a one-day overlap request produces only rows strictly newer than the parent watermark; the child adds exactly two bars while the base remains byte/logically unchanged.
- No-new-bar sync completes the durable job with the base dataset as `resource_id` and does not create an empty delta directory or dataset row.
- `BacktestApplicationService.start_incremental_sync()` now owns base selection, active-job exclusion, async worker submission, and same-session resume/idempotency; the scheduler remains unaware of Provider/SQL details.
- Legacy full manifests without compact symbol watermarks are scanned line-by-line with incremental SHA-256 verification, avoiding a second full in-memory copy before the first daily delta.
- Shutdown changes active incremental jobs to `CANCELLING`; the worker converts that into durable `PAUSED` state at a symbol/provider boundary for the next schedule to resume.
- The backtest drawer already refreshes capabilities, datasets, strategies, and runs in one `Promise.all`; adding the read-only incremental-sync status there is enough to expose schedule state without a new page or manual trigger.
- The data-preparation tab has a concise explanatory paragraph and dataset rows; it can show schedule status beside the existing full bootstrap controls and mark delta versions with parent/new-bar metadata.
- The scheduler now reads durable job status after submission: RUNNING is displayed without resubmission, COMPLETED becomes a terminal session state, and FAILED/PAUSED/CANCELLED is resubmitted with the same deterministic job so saved symbol partitions are reused.
- If a newly READY base already has `end_date >= session_date`, the application records a completed no-op job without calling `get_market_stocks()` or `get_kbars()` again.
- The isolated real FastAPI lifespan smoke returned HTTP 200 with `enabled=true`, timezone `Asia/Taipei`, close time `14:30`, and `WAITING_FOR_BASE`; shutdown completed normally.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| New immutable dataset per successful market session | Keeps old run reproducibility while making a latest version available. |
| Durable sync job/session key | Process restarts and scheduler polling must not launch duplicate downloads for the same date. |
| Weekday scheduling plus no-new-bars no-op | There is no exchange-calendar dependency; Provider data remains the final truth on holidays. |
| Reuse `BacktestApplicationService` as scheduler-facing facade | It already owns worker lifetime and durable backtest dependencies; FastAPI remains delivery/wiring only. |
| Reuse the generic job table and history partition table | The JSON request can carry base dataset/session/overlap without a schema migration unless a unique durable session claim proves necessary. |
| Store daily versions as parent plus delta layers | Avoids rewriting and duplicating the complete three-year JSONL dataset every day. |
| Include per-symbol last timestamps in new manifests | Daily fetch ranges can be computed without rescanning the full parent after the first legacy upgrade. |
| Filter fetched overlap to timestamps strictly newer than each symbol's parent watermark | Prevents duplicate rows and keeps logical bar counts exact while retaining a one-day query overlap. |
| Keep automatic bootstrap out of scope | Starting a new three-year full-market download automatically could duplicate the two currently active jobs and consume Provider quota unexpectedly. |
| A completed no-op session points to its base dataset | This records that the session was checked without inventing an empty dataset version. |
| Treat fresh full-download jobs as scheduler deferrals, not failures | Prevents duplicate quota use while keeping the scheduler polling until bootstrap work finishes. |
| Add status to the existing historical-data tab | The scheduler is operational infrastructure, not a fifth backtest workflow; a separate page would be unnecessary. |
| Poll durable job status after submission | A transient failure must resume during the same market session rather than wait for a process restart or the next day. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Both a legacy web full sync and the resumable CLI job were observed running concurrently | Do not mutate running jobs; new scheduling logic must refuse overlapping active dataset work. |
| Looked for `backtest/migrations/__init__.py`, but migrations are provided by a sibling module/file layout | Use `rg --files backtest` before the next migration inspection; no product change was made. |
| Initial isolated Uvicorn bind was blocked by the filesystem/network sandbox | Used approved localhost execution for the same Mock-only smoke; no external network or live Provider was used. |

## Resources
- `backtest/historical_download.py`
- `backtest/dataset.py`
- `backtest/repository.py`
- `dashboard/server.py`
- `scripts/download_backtest_history.py`
