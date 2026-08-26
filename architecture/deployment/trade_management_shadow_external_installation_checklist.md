# PR-TM-012C1 external runner installation checklist

Status: **DRAFT — NOT APPROVED — NOT INSTALLED — NOT ENABLED**
Production Shadow Gate: **NOT_PASSED**

This checklist cannot authorize a formal run. Complete it in a clean runtime checkout and submit the rendered files, digests, and denial evidence for independent review.

## Required review package

- [ ] Clean checkout is pinned to one approved 40-character commit; `git status --porcelain --untracked-files=all` is empty before the market-date lock is acquired.
- [ ] The virtual environment is pre-built, immutable during the run, and bound by its complete tree digest, venv and resolved Python executable paths/digests, and a real dependency-lock digest.
- [ ] The reviewed calendar, supervisor script/core/adapters/process allowlist, rendered sandbox profile, rendered launchd plist, and `pyproject.toml` digests are exact.
- [ ] Runtime write roots, approval spec/sidecar, and the owner-only secret file are outside the pinned checkout; roots are `0700`, files are `0600`, and the checkout contains no `.env` fallback.
- [ ] The secret contains exactly one Shioaji API-key alias, one secret alias, distinct Local Paper and Shadow DSNs, and `SJ_SIMULATION=true`; no secret appears in plist, approval spec, logs, or artifacts.
- [ ] Provider egress and loopback endpoint inventory is captured; the rendered sandbox permits only reviewed endpoints and denial tests prove other destinations fail.
- [ ] Closed-date, missing-input, C0-blocked, no-fill, exact child graph, lock contention, stale-lock, crash retention, and source-write denial fixtures pass in the rendered sandbox.
- [ ] The existing Codex automation is paused or converted to a monitor, with immutable evidence bound into the approval spec.
- [ ] No automatic C1 signal is configured. Emergency termination remains an explicit operator action and retains lock, logs, Journal, and incomplete artifacts.
- [ ] An independent reviewer renders a new approval JSON, calculates its canonical `spec_digest`, writes an exclusive `.sha256` sidecar, and sets `APPROVED_FOR_INSTALLATION` only after every item above passes.

## Installation and rollback gate

- Do not copy, load, bootstrap, enable, or start the plist while the template contains placeholders, `Disabled=true`, the profile denies all network, or the approval spec is absent/`NOT_APPROVED`.
- Installation must use the reviewed rendered paths without a shell wrapper or environment-variable expansion.
- Rollback unloads only this user service. It never deletes locks, logs, C0/C1 artifacts, canonical inputs, records, database rows, or the pinned checkout.
- A completed single day remains evidence-only and cannot change Production Shadow Gate from `NOT_PASSED`.
