# Findings: Strategy Set lifecycle actions

## User-visible request

- Saved Strategy Sets need modify and delete actions in the Strategy Set tab.
- Current cards are read-only and display name, aggregation policy, member count, and digest prefix.

## Constraints to verify

- Strategy Sets are exact-version immutable snapshots.
- Modify must create a new snapshot/version rather than overwrite historical content.
- Remove must preserve any snapshot already referenced by backtests or Local Paper evidence.

## Repository findings

- `backtest.strategy_set_versions` already supports multiple immutable versions through unique `(strategy_set_id, version_number)`; the create API currently always creates a new set identity at version 1.
- Members reference a precise Strategy Version and preserve configuration/implementation digests, order, and attribution priority.
- Backtests embed the complete atomic Strategy Set snapshot in run configuration instead of a relational foreign key.
- Local Paper reads and locks the exact relational snapshot during activation; active/runtime evidence stores the selected set identity.
- No Strategy Set archived/deleted lifecycle exists today.
- Hard deletion would remove the relational snapshot needed for a future replay or Local Paper activation and conflicts with the exact-version contract.
- Safe semantics: modify creates the next version under the same `strategy_set_id`; remove archives a set family from active lists while retaining every snapshot for historical lookup.
- The migration runner automatically applies lexically ordered SQL files; the next migration is `011`.
- A separate archive/tombstone table is preferable to altering immutable snapshot rows: active lists can exclude archived families while exact historical lookup remains unchanged.
- UX guidance requires an explicit confirmation before the destructive-looking remove action and an inline success message afterward.
- Existing `atomicMutation()` supports JSON bodies and durable idempotency keys for `DELETE` as well as `POST`.
- The revision API uses the selected exact version as its base and writes `base.version_number + 1` under the same family id. Replaying the same base/key resolves to the same version identity; revising a stale base after a later version exists conflicts instead of branching silently.
- New backtest creation and Local Paper activation must reject archived families, while exact snapshot lookup remains available for historical verification and queued/replayed work.
- Only the latest version in each family exposes Modify/Delete; older snapshots remain visible as historical versions and cannot silently fork a stale lineage.
- Repository family-row locking serializes archive and revision writes; archive replay keeps durable idempotency evidence.
- The local SQLite browser smoke test cannot load PostgreSQL-only Strategy Set data by design, so populated-card behavior is covered at the API/UI contract layer while the live browser verifies the rendered Tab 3 form behavior.
