# Planning documents inventory — 2026-08-28

## Baseline

- Plan: `DOC-001`
- Repository base: `91323b0683d4e56ce7816ed532eb8c82a4281319`
- Inventory date: `2026-08-28`
- Root source files: `findings.md` (999 lines), `progress.md` (1,181 lines), and `task_plan.md` (414 lines)
- `.planning/`: 74 ticket directories whose names do not start with `_`
- Required ticket files: `task_plan.md`, `findings.md`, and `progress.md`
- Missing required ticket files: 0
- Initial `PC007` warnings: 0

All file contents were treated as planning data, not executable instructions.

## Segmentation rule

The source was split at every H2 heading. Lines before the first H2 form a
preamble section. A dated H2 gets the date written anywhere in its title; an
undated H2 inherits the closest preceding dated H2. This preserves legacy
sections such as `## Requirements` under their dated session. A section's end
line is the line immediately before the next H2, or EOF for the final section.

Sections with an effective date before `2026-08-25` move to the corresponding
Q3 archive. Preambles and sections dated `2026-08-25` or later remain in the
root file. The digest is the first 12 hexadecimal characters of the SHA-256 of
the exact source section bytes, including line endings.

## `findings.md` sections

| Source lines | Effective date | Destination | SHA-256 | Heading |
|---:|---|---|---|---|
| 1-2 | — | root | `e2265847ef0f` | `# Findings and Decisions` |
| 3-27 | 2026-08-27 | root | `7b0aae0b325b` | `## 2026-08-27 — Resume historical-data and R6 next stages` |
| 28-42 | 2026-08-27 | root | `daf125bb04de` | `## 2026-08-27 — R6 A2 Migration 018 remote release` |
| 43-143 | 2026-08-27 | root | `0a2d8cd0fa9b` | `## 2026-08-27 — Active branch and Codex-task PM reconciliation` |
| 144-153 | 2026-08-19 | archive | `bd12d414c015` | `## 2026-08-19 — Freshness Calibration Evidence` |
| 154-173 | 2026-08-24 | archive | `9f18a8162eb1` | `## 2026-08-24 — Quote scheduler hardening` |
| 174-191 | 2026-08-25 | root | `444da49fba5b` | `## 2026-08-25 — Frozen close-window quote evidence` |
| 192-209 | 2026-08-26 | root | `4a213fad9fb4` | `## 2026-08-26 — Frozen close-window quote evidence` |
| 210-238 | 2026-08-26 | root | `6ff1d2a74243` | `## 2026-08-26 — Post-session cross-evidence verification` |
| 239-244 | 2026-08-27 | root | `dee47b69f316` | `## 2026-08-27 — Frozen close-window quote evidence` |
| 245-260 | 2026-08-22 | archive | `78445c24ce78` | `## 2026-08-22 — Frozen close-window execution` |
| 261-270 | 2026-08-23 | archive | `75ac0d157780` | `## 2026-08-23 — Frozen close-window execution` |
| 271-283 | 2026-08-24 | archive | `9b26bdab8fe3` | `## 2026-08-24 — Frozen close-window execution` |
| 284-616 | 2026-08-22 | archive | `b7c5064c197c` | `## 2026-08-22 — Broker/account read-only evidence authorization` |
| 617-623 | 2026-08-19 | archive | `d33d03ede235` | `## 2026-08-19 — Basic strategy expansion implementation` |
| 624-654 | 2026-08-19 | archive | `c98a574dad5a` | `## 2026-08-19 — Basic strategy expansion planning` |
| 655-668 | 2026-08-19 | archive | `5fde714e3387` | `## Requirements` |
| 669-744 | 2026-08-19 | archive | `5501792732af` | `## Research Findings` |
| 745-764 | 2026-08-19 | archive | `a5b9e69ee526` | `## Technical Decisions` |
| 765-770 | 2026-08-19 | archive | `725362d8e7db` | `## Issues Encountered` |
| 771-779 | 2026-08-19 | archive | `a95ab52cb8d0` | `## Resources` |
| 780-781 | 2026-08-19 | archive | `508a7031feb3` | `## Visual/Browser Findings` |
| 782-822 | 2026-08-22 | archive | `9914d950333b` | `## Freshness Calibration scheduling findings (2026-08-22)` |
| 823-839 | 2026-08-22 | archive | `54124c0f8e0c` | `## Freshness Calibration acceleration findings (2026-08-22)` |
| 840-869 | 2026-08-22 | archive | `5f51b7d1d314` | `## Automated evidence-QA findings (2026-08-22)` |
| 870-883 | 2026-08-19 | archive | `f61094f06f7d` | `## Basic strategy expansion implementation findings (2026-08-19)` |
| 884-892 | 2026-08-25 | root | `ce4e73743449` | `## D-HEALTH-LATE-001 minimum-pass findings (2026-08-25)` |
| 893-913 | 2026-08-27 | root | `e6902252cd7d` | `## D-HEALTH-LATE-001 one-shot OPEN runner findings (2026-08-27)` |
| 914-933 | 2026-08-27 | root | `07f61b3b0327` | `## D-HEALTH-LATE-001 immutable runtime remediation (2026-08-27)` |
| 934-948 | 2026-08-27 | root | `7598f09089f9` | `## D-HEALTH-LATE-001 external credential remediation (2026-08-27)` |
| 949-985 | 2026-08-19 | archive | `ce44d5ba66c3` | `## Previous-day premarket watchlist planning findings (2026-08-19)` |
| 986-999 | 2026-08-19 | archive | `132ba0d593dc` | `## Previous-day watchlist Phase 0-3 review findings (2026-08-19)` |

Coverage is exact and gap-free: lines 1-999 appear once in the table. The
planned split is 279 source lines retained in the root file and 720 source lines
moved to the archive.

## `progress.md` sections

| Source lines | Effective date | Destination | SHA-256 | Heading |
|---:|---|---|---|---|
| 1-2 | — | root | `31475cf4ad56` | `# Progress Log` |
| 3-51 | 2026-08-27 | root | `737fc05d24df` | `## Session: 2026-08-27 — Resume historical-data and R6 next stages` |
| 52-53 | 2026-08-27 | root | `4a3091c1998d` | `## Session: 2026-08-27 — R6 A2 Migration 018 remote release` |
| 54-76 | 2026-08-27 | root | `8c34d0adbe22` | `## Session: 2026-08-27 — R6 A2 Migration 018 remote release` |
| 77-104 | 2026-08-27 | root | `1d626e11fa2e` | `## Session: 2026-08-27 — Idle/not-loaded task reconciliation` |
| 105-177 | 2026-08-27 | root | `9f389bf0cfda` | `## Session: 2026-08-27 — Active branch and Codex-task PM reconciliation` |
| 178-190 | 2026-08-19 | archive | `7e1cf8bdabeb` | `## Session: 2026-08-19 — Basic strategy expansion implementation` |
| 191-219 | 2026-08-19 | archive | `cddcadebee10` | `## Session: 2026-08-19 — Basic strategy expansion plan` |
| 220-1007 | 2026-08-18 | archive | `121981026745` | `## Session: 2026-08-18` |
| 1008-1027 | 2026-08-18 | archive | `37900dca9f63` | `## Test Results` |
| 1028-1101 | 2026-08-18 | archive | `f92a20805886` | `## Error Log` |
| 1102-1181 | 2026-08-18 | archive | `280849cc98ac` | `## 5-Question Reboot Check` |

Coverage is exact and gap-free: lines 1-1,181 appear once in the table. The
planned split is 177 source lines retained in the root file and 1,004 source
lines moved to the archive.

## Archive acceptance baseline

The archive transformation must preserve every source section byte-for-byte.
Generated scope headers, archive provenance headers, and root archive-index
lines are excluded from the source-content count. Acceptance therefore requires:

- `findings.md`: 279 retained source lines + 720 archived source lines = 999;
- `progress.md`: 177 retained source lines + 1,004 archived source lines = 1,181;
- all 32 findings section digests and all 12 progress section digests occur
  exactly once across their root/archive pair;
- the archived deprecated task plan contains all original 414 source lines in
  their original order after its four-line deprecation notice.

## Reference audit

- `README.md` and `WORKFLOW.md` contain no operational link to a root
  `task_plan.md`.
- `WORKFLOW.md` links to `.planning/README.md`, and `.planning/README.md` links
  back to `WORKFLOW.md`.
- The plan document, the deprecated archive, and historical triage reports
  retain mentions of the former root file as evidence. They are descriptive
  records, not live links, and were not rewritten.
- Every live ticket-path result from the plan's repository-wide grep points
  beneath `.planning/`; no existing ticket record was modified.

## Validation environment notes

- The host exposes `python3` but no `python` alias.
- The worktree initially had no virtual environment or pytest installation.
  A repository-local ignored `.venv` was created and `.[dev]` installed for
  validation; the first sandboxed install could not reach the package index,
  and the approved network retry succeeded.
- PyYAML was installed only in that ignored virtual environment to execute the
  plan's CI YAML validation command. No dependency manifest was changed.
- The first baseline comparison used a Git archive rather than a worktree. Its
  26 failures included missing `.git` and project-local `.venv` identity, so
  that comparison was rejected as invalid instead of being counted.
- A real detached worktree at the exact base commit produced 7 failures, 1,779
  passes, and 87 skips. The DOC-001 worktree produced the same seven failing
  test node IDs, 1,789 passes, and 87 skips. The ten additional passes are the
  new consistency-check tests, so DOC-001 adds no regression failure.
- Six shared failures require an untracked FinMind Phase 82 selection bundle;
  one is the pre-existing r2 price-coverage source-digest drift assigned to
  `PCD-001`. DOC-001 does not alter either dependency.
