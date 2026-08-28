# Findings: Uncommitted commit packaging

## Initial constraints

- Commit locally by coherent functionality.
- Preserve shared-worktree changes and recheck payloads immediately before commit.
- Do not push.
- Treat skipped external-infrastructure tests as coverage gaps.
- Exclude this task's planning files from product commits.

## Discoveries

- Branch: `codex/organize-uncommitted-20260821`; HEAD `63043aa`; remote tracking branch is six commits behind local HEAD.
- The index was empty at inventory time. All pre-existing changes were unstaged or untracked.
- Tracked changes span 36 files and roughly 3,566 insertions / 207 deletions before untracked files.
- Main mixed ownership boundary: `dashboard/server.py` contains both strategy-set lifecycle routes and VWAP cash-admission routes.
- Strategy-management work is internally cohesive across archive/revision persistence, backtest admission, API, accessible workflow UI, and tests. The UI refactor also includes sealed-draft cloning and editable strategy-set minimum policy.
- VWAP cash-admission work spans backtest domain/application/repositories plus a new migration, research-control module, API/CLI, and tests; some backtest repository hunks may also include persistence refactoring and require exact review.
- The backtest repository result-save refactor is required by the cash-admission postflight transaction; it is not a separate cleanup.
- `backtest/application.py` has one strategy lifecycle hunk (reject archived sets) mixed into the otherwise cash-admission diff.
- `dashboard/server.py` has four ownership areas: strategy archive request; strategy revision/archive routes; cash-admission imports/request/error/route; and one unrelated exception-handler regression.
- Blocking regression found during review: `get_momentum_dashboard_service()` changed `except Exception as error` to `except Exception` but still calls `str(error)`, which would raise `NameError` precisely on the unavailable-service fallback. Restore the exception binding before packaging.
- Freshness scheduling changes and captured evidence form a separate evidence-operations workflow.
- Freshness code adds a bounded 300-second late-launch grace, explicit scheduled-time/delay audit fields, and a launchd-safe absolute runtime path; tests cover on-time, grace-boundary, and expired launches.
- Freshness artifacts are mixed evidence, not all passes: weekend runs are `NO_CAPTURE_NON_TRADING_DAY`, off-window runs fail closed, quote captures exist for 2026-08-24/25, and broker/account observations include constrained gaps such as authorization/source errors and buying-power non-authority.
- Root planning files and the FinMind sponsor planning set contain large ongoing operational histories; they should be attached only to their originating evidence/acquisition commits, never bundled with runtime source by convenience.
- Quote and broker-account artifact inspectors pass structural/hash inspection but return `REVIEW_REQUIRED` with no threshold candidates; the commit message must preserve that disposition.
- Trade-management Shadow evidence is a separate evidence-only commit: 2026-08-24 was blocked by non-empty PostgreSQL evidence; early 2026-08-25 attempts were blocked by PostgreSQL preflight; the final 08:56 premarket artifact was `READY_FOR_SESSION` with `execution_enabled=false`, `qualifying_real_session=false`, and `production_shadow_gate=NOT_PASSED`.
- The trade-management `.sha256` sidecars for premarket artifacts contain the embedded readiness-report digest, not a whole-file SHA-256. The cleanup-backup sidecar is a whole-file digest. This is intentional artifact semantics, not corruption.
- The 27 MB late-delivery OPEN evidence is explicitly `INCOMPLETE`: 35,118 records were retained, the daily evidence admits zero completed sessions, and the report prohibits treating it as qualified evidence.
- Numerous planning, evidence, and acquisition directories are untracked and must be grouped by their originating workflow rather than swept into one documentation commit.
- Migration numbering is valid and contiguous: archive `011`, existing dataset/result migrations `012`/`013`, and cash-admission `014`.
- `WORKFLOW.md` is a Symphony/Linear unattended-orchestration template rooted at `~/code/symphony-workspaces`, not a `tw_intraday_trader` workflow. It is unrelated/ambiguous and should remain uncommitted unless explicitly authorized for this repository.
- Institutional work naturally separates into a credentialed PIT/source-semantics evidence path and a FinMind three-way institutional MVP candidate path; both have code, immutable artifacts, and focused tests.
- Institutional capture metadata persists only endpoint plus non-secret query parameters and explicitly sanitized response headers. Focused credential-pattern scans found no persisted secret value or private-key pattern in the candidate payload.
- Planning-only histories should stay function-specific: live-mode architecture; local-paper odd-lot; local-paper settings; atomic backtest simplification; central no-overnight; FinMind premarket strategy. They should not be collapsed into one generic `docs` commit.
- Focused verification before staging: strategy `32 passed, 16 skipped`; cash admission `22 passed, 7 skipped`; institutional `26 passed`; freshness/Shadow `48 passed`.
- Static verification before staging: `git diff --check`, Python compileall, and Node syntax passed. Ruff is not installed in the project venv.
- Exact isolated staged verification passed for the mixed/dependency-sensitive commits: strategy lifecycle `32 passed, 16 skipped`; VWAP cash admission `25 passed, 13 skipped`; FinMind PIT `17 passed`; institutional MVP `9 passed`; freshness scheduler `10 passed`.
- A concurrent VWAP R5 remediation became visible near the end of packaging. After it stopped changing, its schema-v2 preflight payload was reviewed separately: ordinary `NEXT_BAR_OPEN` now follows the engine's next-observed-symbol-Kbar semantics across sessions, while `DAILY_NEXT_BAR` retains its own boundary. Focused regression passed `12 passed`.
- The final commit count is 15 rather than 14 because that late stable remediation is a functional code/test/contract unit and should not be folded into an earlier evidence or documentation commit.
- Final no-DSN suite passed `1384 passed, 41 skipped`; the skips remain PostgreSQL/external-infrastructure coverage gaps.
- Final index is empty. The only remaining worktree entries are `.planning/.active_plan`, this isolated packaging record, and unrelated `WORKFLOW.md`.
