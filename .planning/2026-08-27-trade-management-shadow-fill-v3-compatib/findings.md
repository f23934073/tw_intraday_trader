# Findings & Decisions

## Requirements
- Required baseline: merged/main-green commit `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`; investigate any HEAD difference read-only.
- Scope product changes to Shadow observer/builder and tests; avoid `runtime/composition.py`, `simulation/*`, and `trading/local_paper.py` unless proven unavoidable and then record an overlap note first.
- Accept authoritative BUY `local_paper_fill.v3`; preserve fill.v1; support fill.v2 only if current source proves an explicit schema contract.
- Handle v3 partial fills and repeated correlation keys deterministically without arbitrary selection or false conflict; replay and tamper evidence are mandatory.
- Preserve provenance, record fingerprint, command idempotency, session/symbol/side, `execution_authority=false`, and read-only Local Paper Journal.
- C1 stays `execution_enabled=false`; no order/cancel/CA/trade callback/broker authority and no manufactured fill or Thesis.

## Research Findings
- Worktree is detached at `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9` (`feat(r6): implement amendment a1 preflight`), not the requested merge commit. Parent is `ec419329...`; ancestry and provenance still need read-only verification.
- Before discovery, only task-local `.planning/.active_plan` and `.planning/2026-08-27-trade-management-shadow-fill-v3-compatib/` were changed/created by the required planning skill.
- Read-only ancestry check returned false: `037197e...` is not an ancestor of `a6e096a...`. Graph inspection showed `origin/main` at `037197e...`, while local `main` and this detached worktree were on the stale divergent `a6e096a...` line.
- Supervisor confirmed the cause was `create_thread` using saved-project stale local `main` and explicitly authorized this task to fetch/resolve origin and create `codex/shadow-fill-v3-compat-20260827` from exact `037197e...`, without touching the main worktree.
- `git fetch origin main` resolved `FETCH_HEAD=037197e1a3aadd7a480208f97f291cdcb6ce7a2f`; refreshed `origin/main` resolves to the same exact merge commit.
- No local or remote-tracking ref named `codex/shadow-fill-v3-compat-20260827` existed before creation.
- Created local branch `codex/shadow-fill-v3-compat-20260827` at exact `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`; post-switch `git rev-parse HEAD` matches exactly.
- Ancestor checks pass for Local Paper durability commits `34fb5250030d170b7909870f086c5693f728a9aa`, `99ece08`, and `786f45212f822ae0514957adac748c00fb6a95fa` against current HEAD.
- Baseline product cleanliness: unstaged and staged diffs excluding `.planning` are empty, and there are no non-planning untracked files. `git status` contains only required task-local planning metadata (`.planning/.active_plan` and the isolated plan directory).
- `ExistingPaperFillObserver.observe()` currently imports only `LOCAL_PAPER_FILL_KIND` (`v1`), filters one session by exact kind and `command_idempotency_key`, rejects zero records, and treats every `len != 1` as conflict. That contract cannot admit v3 and misclassifies valid multi-record partial fills.
- `PaperFillThesisBuilder.activate()` accepts exactly one `JournalRecord` of v1 kind, parses it through `LocalPaperFill.from_record`, requires BUY/session/symbol/canonical v1 record id/order idempotency/provenance/correlation, then binds provenance and Thesis to that single record's identity, fingerprint, quantity, price, and timestamp.
- Current activation/provenance version strings are v1. The Thesis trade identity and opening fill identity are derived from the single fill record, so multi-fill support requires an explicit aggregate identity/fingerprint contract rather than arbitrary record selection.
- The operational composition docstring and authority split are already data-only: it cannot create fills/orders/positions or reach a broker; observer receives a read-only `JournalRepository` and evidence Journal must be a distinct object.
- Current `LocalPaperFill.from_record()` explicitly dual/tri-reads v1, v2, and v3. v2 has a concrete settings-bound accounting contract (gross/notional, commission, net cash effect, cumulative commission, settings digest); v3 adds tax, slippage/reference/tick policies, instrument descriptor, cumulative gross/tax, and mandatory `execution_authority=false` validation. This is sufficient current-source evidence to support v2 intentionally rather than guessing fields.
- v3 record construction persists one delta per partial fill with `fill_sequence`, per-fill quantity/price/costs, cumulative order gross/commission/tax, command provenance, canonical record identity based on order/time, and idempotency key `order_id` for sequence 1 then `order_id:sequence`.
- Local Paper replay already proves v3 partial lineage by requiring exact consecutive fill sequence and exact cumulative gross/commission/tax. PostgreSQL UAT exercises two BUY fills plus two SELL fills and three fresh-connection reconstructions, including payload corruption rejection.
- Existing Trade Management implementation plan had only frozen the v1 observer rule (zero wait, more than one conflict). A broader older future plan described v1/v2 dual-read but explicitly deferred its runtime cutover; the now-current Local Paper source has since implemented v2/v3 typed readers/writers.
- The source delegation rollout explicitly records that this Wave 1B should preserve v1/v2 compatibility while adding v3 compatibility. Combined with current typed readers, v2 support is an intentional compatibility requirement, not a silent schema widening.
- Downstream code treats `activation_id` and `TradeThesis.opening_fill_id` as opaque identities. No serializer or runtime outside the observer/builder directly inspects `PaperFillProvenance` fields, so an additive lineage contract and a distinct aggregate activation version can remain Shadow-local.
- Live capture starts its evidence Journal at `thesis.filled_at`, rejects market events before that timestamp, and persists `activation_id`. Therefore a multi-fill aggregate must choose one explicit time boundary and stable aggregate identity; arbitrary first/last candidate selection would alter replay admission.
- `local_paper_order_state.v1` provides tamper-evident state payloads, including terminal status, total/remaining quantity, filled quantity, fill sequence, symbol/side/order/idempotency key. `latest_local_paper_order_states(..., require_integrity=True)` is a read-only way to prove a correlated fill set is terminal and complete.
- A terminal order-state boundary avoids mutable prefix activations: without it, observing after partial fill 1 and after partial fill 2 would create two different immutable Thesis identities for the same command key. The observer should wait fail-closed until terminal `FILLED`, then aggregate exactly the terminal sequence/quantity.
- PostgreSQL Journal stores record fingerprints and checks them on append retries, but `records()` reconstructed records without comparing the stored fingerprint column. The adversarial review proved this permits semantically valid provenance rewrites across restart, so the shared read adapter requires one narrow fail-closed comparison.
- Pre-fix run produced seven expected failures: builder rejects v2/v3 kinds, observer filters them out, and builder cannot accept an ordered fill tuple. The new fixture itself successfully generated/validated real settings-bound v2/v3 records before reaching those gates.
- PM reported `origin/main` advanced to docs-only architecture-atlas commit `33c9b3a`. This branch remains scoped to Shadow fill compatibility, but latest main must be fetched/integrated before final review/commit and every required validation rerun afterward.
- The main implementation stays within `trading/paper_thesis_activation.py` and `runtime/trade_management_operational_composition.py`; no overlap with `runtime/composition.py`, `simulation/*`, or `trading/local_paper.py` was needed. A reviewer-proven restart integrity defect requires the separately bounded `trading/postgres_journal.py` read-path change documented below.
- Post-fix focused results: all 7 new regressions pass; all 17 unchanged legacy fill.v1 builder/observer composition tests pass.
- Aggregate provenance now explicitly carries session id, symbol, BUY side, total quantity, common command/source/provider authority, and ordered per-record kind/sequence/id/fingerprint/time/quantity/price; legacy v1 leaves these additive fields empty so its digest payload stays unchanged.
- Refreshed `origin/main` is exactly `33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`, a docs-only merge over `037197e...`; current Shadow files do not overlap its README/architecture-diagram payload.
- Pre-integration content hashes: observer `c0a7025f...`, builder `c5cc52fe...`, new regression file `d5c29474...`. These will be checked after stash/rebase/restore.
- Post-integration HEAD is exactly `33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`; observer, builder, and regression hashes exactly match the pre-integration values. No conflict or implementation-content drift occurred.
- Latest-main regression is green: focused schema/legacy `24 passed`; full no-DSN suite `1507 passed, 43 skipped`. The explicit PostgreSQL selection remains `3 skipped` because no disposable `TEST_POSTGRES_DSN` is configured; this is not PostgreSQL UAT evidence.
- `code-review-excellence` self-review found two test/contract weaknesses before final disposition: same-price partials did not prove VWAP, and aggregate Decimal arithmetic could inherit a caller-modified context. The test now uses two different valid v3 prices, and aggregate parsing/validation/calculation runs inside a fixed 28-digit context.
- Settings-bound activation now rejects implicit coercion for monetary/provenance fields and boolean/non-integer quantity payloads. This preserves the current canonical writer schema instead of guessing types.
- An independent read-only adversarial reviewer has been assigned after the self-review fixes; no commit is allowed until its P1/P2 disposition is resolved.
- Final self-review validation on `33c9b3a`: full suite `1508 passed, 43 skipped`; broad `compileall`, Dashboard JavaScript graph, `git diff --check`, 99-column scan, exact file-scope check, and prohibited execution-authority scan all passed.
- Independent adversarial review disposition: `REQUEST_CHANGES`, P1=0/P2=4. Proven issues: PostgreSQL `records()` ignores stored fingerprint; public builder accepts a nonterminal prefix; observer's two reads can combine stale fills with a later terminal snapshot; `LiveShadowDecisionPolicy` accepts a remaining quantity different from aggregate fill quantity.
- Overlap note: `trading/postgres_journal.py` and its PostgreSQL tests must now change narrowly to compare stored versus reconstructed fingerprints on read. No migration, writer, simulation, Kill Switch, No-Overnight, order, or execution behavior will change.
- PM confirmed the No-Overnight worktree independently has uncommitted `trading/postgres_journal.py` and `tests/test_postgres_journal_unit.py` work. This task neither reads nor adopts that content. Its exact shared-file boundary is: add `fingerprint` to the existing records SELECT, compare it with the reconstructed `JournalRecord.fingerprint`, and raise `JournalConflictError` on mismatch.
- Review fixes are implemented: aggregate builder requires explicit terminal completion evidence; observer takes one Journal snapshot and binds fill plus terminal order-state evidence from it; terminal record id/fingerprint/sequence are included in the aggregate digest; Shadow quantity mismatch fails closed; PostgreSQL reads verify the stored fingerprint.
- Regression evidence for the four review findings: three newly red in-memory tests produced `3 failed`, then `3 passed`; the no-DSN PostgreSQL reader unit test passes both valid replay and payload-tamper rejection. Formal PostgreSQL integration remains skipped without an explicit disposable DSN.
- Closed-loop independent re-review disposition is `APPROVE`, P1=0/P2=0. The reviewer independently reran focused `30 passed`, probed correlated fill tails and terminal-fingerprint identity changes, and authorized one scoped local commit without push.
- Commit-time `git fetch origin main` confirmed `HEAD=origin/main=FETCH_HEAD=33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`; required merge `037197e...` and durability commits `34fb525...`, `99ece08`, and `786f452...` remain ancestors.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| v2/v3 ordering is `fill_sequence=1..N`; occurred times must be monotonic | Reuses the writer/replay lineage already enforced by Local Paper and yields deterministic replay order |
| Aggregate entry price is quantity-weighted fill price; quantity is the exact sum | Avoids arbitrary-record price/quantity and matches executed-position economics |
| Aggregate `filled_at` is the final fill time | The terminal fill set is not authoritative until complete, and live capture must not admit events before aggregate completion |
| Aggregate identity/fingerprint digest the ordered record ids and fingerprints plus semantic totals | Any admitted record/content/order change alters activation identity and preserves every source fingerprint |
| All records in one aggregate must share schema, order, command id/key, source/provider, execution=false, session, symbol, side, and schema-specific policy identity | Prevents mixing monetary/provenance contracts or silently combining unrelated fills |
| Do not modify product code until HEAD provenance is resolved | Directly required by delegation constraints |
| Fetch and branch only after proving no product changes | Preserves task-local planning evidence while preventing accidental loss or carryover of code edits |
| Baseline gate passed; source/test discovery may proceed | Exact commit, named scoped branch, durability ancestors, and product-clean status are all evidenced |
| Support v2 explicitly as well as v1/v3 | Both current `LocalPaperFill` code and delegation roadmap establish an explicit v2 contract/compatibility requirement |
| Bind aggregate identity to terminal order-state evidence | Record id, fingerprint, Journal sequence, status, quantities, correlation key, symbol, side, and time make completion replayable and tamper-evident |
| Read fills and terminal state from one snapshot | Prevents acceptance assembled from different Journal high-water views; terminal evidence must follow every correlated fill in that snapshot |
| Fail when Shadow policy quantity differs from activation | Aggregate fill quantity is authoritative and cannot be silently replaced by independent configuration |
| Keep PostgreSQL overlap to read verification only | Resolves the stored-fingerprint P2 without taking or overwriting No-Overnight migration, writer, or unit-test work |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `rg` included non-existent `adapters/`, `infrastructure/`, and `persistence/` paths | Used actual `trading/postgres_journal.py`; no retry of the same invalid path set |

## Resources
- Required merge commit: `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`
- Initial stale detached HEAD: `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`
- Corrected branch and HEAD: `codex/shadow-fill-v3-compat-20260827` at `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`
