# No-Overnight × Local Paper semantic forward-port map

## Scope and identities

- Target branch: `codex/no-overnight-integration-20260827`
- Audited port base: `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`
- Final integration parent: `d5b86382c06a34e3a26ba2b23e3d714c783f0348`
- Read-only source: `codex/no-overnight-pr-no-006` at `21fd771d2086122d2c49a5c0bbbbcdb206087bc0`
- Common ancestor: `7f6247c793768aa2c826626a575b19e8b71cbfa0`
- Source commits: `5b26371` → `060fb6a` → `13a9b13` → `57c9fa7` → `067f013` → `ca05fc3` → `21fd771`
- Baseline safety commits that must remain intact: `34fb525` Kill Switch, `99ece089` Tax/Slippage, and `786f452` PostgreSQL CI coverage.
- PostgreSQL compatibility milestone that must remain intact: approved Shadow `47a9303`, timestamp identity `f6a38b1`, and UAT expectation `254317b`, all ancestors of the final parent through `7931d31e`.

This is a semantic port. The old branch is not merged, rebased, or cherry-picked as a unit. Its 2026-08-27 fixtures, reports, and campaign state cannot qualify this integrated code identity.

## Schema collision and migration decision

The old branch and current main both used the spelling `local_paper_fill.v2` for different payloads:

- current main v2 means settings-bound monetary accounting evidence;
- the old branch v2 means exposure identity and No-Overnight action evidence.

Those meanings must not be guessed from current config or silently combined. The integrated contract is:

| Artifact | Integrated treatment |
|---|---|
| `local_paper_fill.v1` | Immutable legacy reader; never rewritten. |
| current-main `local_paper_fill.v2` | Immutable monetary reader; never reinterpreted as exposure identity. |
| `local_paper_fill.v3` | Immutable Tax/Slippage/instrument/settings truth; reader and replay invariants remain unchanged. |
| integrated identity-rich fill | New additive `local_paper_fill.v4`: all v3 monetary/provenance fields plus strict exposure/action identity. It is emitted only by settings v2 Local Paper. |
| old-branch identity-shaped `local_paper_fill.v2` | Historical source artifact only; it is not qualifying integrated evidence and is not accepted as a current managed fill. |
| `local_paper_order_state.v1` | Immutable existing reader. |
| `local_paper_order_state.v2` | Additive strict identity/action state for new integrated commands. |
| `local_paper.v1` | Existing aggregate cash/position/PnL projection remains readable and includes v1/v2/v3/v4 monetary facts. |
| `local_paper.v2` | Additive exposure-keyed projection. One import manifest maps pre-integration aggregate state to `UNCLASSIFIED_LEGACY`; only v4 fills can create/update managed exposure. |

`OBSERVE_ONLY` and `ENFORCING` require settings v2 so managed fills always carry the full v3 monetary truth. A settings-v1 Local Paper session remains usable in `DISABLED` mode but does not manufacture managed identity from legacy facts.

## Control-session decision

The current settings workflow creates a new immutable Local Paper Journal session when a confirmed draft is applied. It therefore cannot be replaced by the old branch's single fixed ledger session.

The integrated layout separates two identities:

1. A code-owned fixed identity anchor stores stable `account_scope_id`, `policy_family_id`, ledger identity, and schema versions. Metadata conflict is `RECOVERY_REQUIRED`; changing config cannot create a new scope to bypass a breach.
2. The active settings-bound ledger session remains the source of order/fill/cash truth. New sessions bind settings schema/revision/digest and the fixed identity anchor. A pre-integration session may enter `local_paper.v2` only through one append-only import manifest and checkpoint; missing or conflicting import/anchor evidence fails closed.

Settings apply does not delete or rewrite old sessions. An unresolved durable breach remains keyed to the fixed scope/family across active-session changes. A settings change is rejected while No-Overnight is active unless a separately reviewed safe controller handoff exists.

Every PostgreSQL Local Paper runtime, including DISABLED/settings v1 downgrade paths, participates in the same advisory mutation guard. A DISABLED in-process settings replacement may reuse that exact healthy guard only while the Dashboard runtime lock excludes concurrent mutations; ownership transfers after durable activation/archive succeeds. A second process cannot use this handoff and fails closed.

The same-process replacement also reuses the exact Kill Switch authority after validating exact Journal, Clock, and durability bindings. Old command and strategy-flow authorities are suspended before the archive transaction and permanently revoked only at commit; rollback restores them. Complete strategy activation and checkpoint writes hold the command-authority lock, so a stale reference cannot append after the archive. Kill Switch references intentionally remain shared, ensuring any stale engage/reset and the replacement's final admission observe one lock, projection, and exact revision sequence.

No new mutable SQL table is planned. Generic Journal sessions, append-only records, projection checkpoints, and the PostgreSQL advisory-lock guard remain the only persistence primitives.

## Non-negotiable safety invariants

- Only `AUTO_INTRADAY` and `MANUAL_INTRADAY` exposures are managed. `AUTO_SWING`, `MANUAL_LONG`, and `UNCLASSIFIED_LEGACY` remain excluded even when they share a symbol.
- Every close follows exact `target_exposure_id`; symbol aggregate quantity is never an ownership or flatness proof.
- State is monotonic: `NORMAL → NO_NEW_ENTRY → CANCEL_ENTRY → FLATTENING → AGGRESSIVE_EXIT → FINAL_RECONCILIATION → CONFIRMED_FLAT / OVERNIGHT_BREACH`.
- `EXIT_SUBMITTED`, partial fill, cancel, reject, unknown, or retry exhaustion is not flat. `CONFIRMED_FLAT` requires terminal SELL, managed quantity zero, fresh reconciliation `MATCH`, and durable Journal/checkpoint evidence.
- An unresolved durable `OVERNIGHT_BREACH` blocks exposure-increasing BUY across restart and settings-session rotation. SELL, cancel, reconciliation, and recovery remain available through their safety gates.
- Kill Switch durable final admission, exact revision reset, and `RECOVERY_REQUIRED` behavior remain independent and fail closed.
- The result is Local Paper only / no-real-money. It adds no broker order, CA, trade callback, or execution authority.

## File-level port classifications

### Carry forward after direct contract review

These source additions have no competing target implementation and retain their source ownership, subject to the v4/session adaptations above:

- `config/local_paper_identity.py`, `config/no_overnight.py`
- `trading/exposure.py`, `trading/no_overnight.py`, `trading/no_overnight_admission.py`, `trading/no_overnight_journal.py`, `trading/no_overnight_evidence.py`
- `runtime/no_overnight.py`, `runtime/no_overnight_guard.py`, `runtime/no_overnight_evidence_capture.py`
- `scripts/capture_no_overnight_disabled_baseline.py`, `scripts/inspect_no_overnight_evidence.py`
- No-Overnight runbooks and focused source tests.

The source deltas to `runtime/ports.py`, `simulation/application_adapter.py`, `trading/canonical_values.py`, `trading/journal.py`, and `trading/postgres_journal.py` are based on files unchanged on the target side. They can be applied as reviewed additive deltas, then verified against Kill Switch and PostgreSQL tests.

### Manual three-way integration

| Area | Source intent to retain | Target behavior to retain | Resolution |
|---|---|---|---|
| `trading/local_paper.py` | Exposure identity, strict state readers, import manifest, v2 projection/checkpoint | v1/v2/v3 monetary readers, Tax/Slippage validation, daily baseline/archive, settings digest | Add v4 writer/reader and exposure projection; keep all earlier readers byte-semantic and include v4 in aggregate replay. |
| `simulation/service.py` | Exposure-keyed positions, partial/retry identity, exact target exposure | settings v2, fees/tax/slippage, instrument truth, daily budget | Preserve monetary execution first, carry identity through the same fill, and never aggregate exposure ownership by symbol for No-Overnight. |
| `simulation/application.py` | v2 command/admission/cancel/recovery and durable checkpoints | Kill Switch final admission, settings digest, v3 recorder | Order is Journal/admission/Kill Switch guarded; terminal recorder emits v4 under settings v2 and advances both projections atomically. |
| `trading/application.py` / `trading/risk.py` | command v2, horizon/action/target identity, operational SELL exemptions | current risk and Kill Switch-compatible application behavior | Add fields/readers without weakening existing v1 or protective SELL behavior. |
| `runtime/composition.py` | fixed identity, controller/guard/worker, breach recovery | settings sessions, fill.v3 service config, Kill Switch recovery | Use fixed identity anchor plus active settings ledger; recover Kill Switch and No-Overnight independently, then wire one command path. |
| `simulation/continuous_strategy.py` | admission-safe flatten routing | durable Kill Switch synchronization and cost-aware simulation | Preserve Kill Switch as the first automation stop and route managed operational SELL through the central command service. |
| Dashboard/API/JS/CSS | status, breach resolution/ack, read-only projection | settings v2 and Kill Switch controls | Keep both control surfaces with distinct revisions/reason codes; GET never triggers broker/provider account actions. |
| market-data models/provider | reviewed session/tradability capabilities | current Tick/BidAsk/instrument descriptor surfaces | Add only the explicit session/tradability port; no CA, trade callback, or broker order path. |
| overlapping tests | No-Overnight safety assertions | Kill Switch/settings/fill.v3 assertions | Merge fixtures around one v4 integrated truth and retain separate old-reader regressions. |

### Reference only / excluded from code payload

- Old `.planning/2026-08-23…2026-08-26` directories remain source history and are not copied.
- Old campaign reports/artifacts and the scheduled 2026-08-27 evidence identity remain non-qualifying.
- No broker adapter, `place_order`, CA activation, trade callback, synthetic fill, unattended promotion, or real-money mode is introduced.

## Verification gates

Each implementation segment must pass its focused tests and self-review before the next segment. Final verification requires the complete suite, compile/static/JS/diff checks, a demonstrably disposable PostgreSQL database, and an independent adversarial review with no unresolved P1/P2.

DISABLED, OBSERVE_ONLY, supervised ENFORCING full-session campaigns and the three operational drills remain later trading-session Gates. Fixtures and old code evidence cannot pass G6 or production qualification.
