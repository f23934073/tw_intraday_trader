# Findings: Local paper odd-lot support

## Requirements

- Enable exact-share local paper simulation, including 1-999-share odd lots.
- Preserve the local-only, no-broker-execution boundary.
- Cover manual and strategy-paper entry points while keeping the fixed one-lot continuous strategy policy unchanged unless exact-share plumbing requires an internal rename.

## Initial Findings

- The current Dashboard and API accept integer `lots`; the UI labels 1 lot as 1,000 shares.
- `LocalPaperCommandService` multiplies lots by 1,000 before creating `OrderCommand`.
- `SimulationOrder.quantity` derives shares as `lots * 1_000`.
- `LocalPaperSimulationCommandAdapter` rejects quantities not divisible by 1,000 and floor-divides before submission.
- The runtime is `LOCAL_PAPER_SIMULATION`; README and routes explicitly prohibit Shioaji order calls.
- The worktree already contains unrelated modified files, including README, Dashboard, backtest, and strategy-catalog work. Changes must be surgical and overlap-aware.
- Matching, cash reservation, sellable-quantity checks, fills, positions, and Risk snapshots already operate in shares after `SimulationOrder.quantity`; the lossy boundaries are input, model storage, retry, rejection projection, and restore.
- `LocalPaperCommandService.retry_order` currently converts `remaining_quantity // 1_000`, so an odd-lot remainder would be truncated unless retry becomes share-native.
- `trading.local_paper` rebuilds an order projection from the canonical Journal `quantity_shares`, but derives legacy `lots` with floor division; recovery must retain `quantity_shares` as authoritative.
- The quote book exposes available quantity in shares internally (`*_available_quantity`), so partial fills can support odd lots without changing the matching algorithm.
- Existing projections expose `quantity` and `remaining_quantity` in shares. Adding an explicit `quantity_shares` field while retaining `quantity` is compatible and makes the contract unambiguous.
- `OrderCommand` and its Journal record already use `quantity_shares`, so the application boundary can become share-native without a Journal schema migration.
- `SimulationService` restore currently reconstructs `SimulationOrder(lots=int(raw["lots"]))`; order-state records need an additive `quantity_shares` field and a legacy fallback from `quantity`/`lots`.
- Risk rejection projection also takes `lots`, so rejected odd-lot commands would otherwise display the wrong quantity even though the Risk decision is share-native.
- Existing `lots` is part of persisted order-state payloads and tests. The safe path is an additive exact-share field with legacy whole-lot input compatibility, not reinterpreting `lots` as shares.
- Continuous strategy intentionally enforces exactly 1,000 shares and may keep that policy; only the shared strategy intent/command transport needs exact-share support.
- Strategy intent currently persists both `lots` and derived `quantity_shares`. A versioned additive contract can accept `quantity_shares`, keep legacy `lots` for old callers, and always journal exact shares.
- No tests assert a projected `order["lots"]` value; most tests only pass `lots=` into service constructors. This permits preserving legacy input while making projection `quantity_shares` authoritative.
- The Dashboard order card is the only product consumer that displays `order.lots`; it can switch directly to the already share-based `quantity`/new `quantity_shares` field.
- `SimulationService.restore_state` is the only constructor path that reads old `raw["lots"]`; a fallback chain of `quantity_shares`, then `quantity`, then `lots * 1000` supports old and new Journal states.
- Direct `StrategyPaperIntent(...)` construction is used only in one test helper plus two validation tests; changing the dataclass to canonical `quantity_shares` is manageable if a computed `lots` property preserves the continuous-strategy assertions.
- Streaming book depth enters as lots and is correctly converted to shares at the quote boundary. An odd-lot order can therefore be partially filled by existing 1,000-share depth; a targeted odd-lot partial-fill test should use a 1,500-share order to prove a 1,000/500 split.
- Recovery-required order synthesis already starts from Journal `quantity_shares`; adding `quantity_shares` to its order-state mapping removes the current floor-division ambiguity.
- `OrderCommandHandler` still advertises lot input and should be updated additively to accept optional `quantity_shares` plus legacy `lots` so type-level ports match the implementation.
- `dashboard/static/js/app.js` only declares the old `orderLots` element and does not use it elsewhere; the active behavior lives in `workspaces/simulation.js`. Removing the stale declaration avoids a dangling DOM lookup after the input id changes.
- All Python order submissions use keyword arguments, so reordering keyword-only parameters to place required price/idempotency fields before optional share/lot compatibility fields is safe.
- Current Shioaji streaming explicitly subscribes regular Tick/BidAsk and drops callbacks where `intraday_odd=True`. Exact-share paper orders therefore use the existing regular-book reference fill model; they are not a simulation of the exchange odd-lot order book.
- Adding true odd-lot market-book routing would require a distinct subscription identity, quote-state partition, units contract, and subscription-budget change. That is materially broader than enabling exact-share local paper orders and is not required for the current scoped change.
- The UI and README must state that odd-lot fills are local reference-price simulations, not Shioaji Simulation or actual TWSE odd-lot executions.
- Browser verification confirmed the end-to-end manual path preserves 125 shares across the form, POST request, order projection, fill message, and position projection.
- The worktree's unrelated untracked migration 008 makes one existing migration-order test expect a stale last-version value; deselecting only that assertion leaves 1,131 passing tests and 16 intentional skips.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Trace recovery and retry before editing | Floor division in retry or persisted lot-only records could silently lose odd shares even if submission accepts them. |
| Add boundary tests before product edits | Exact-share defects are semantic and need proof at 1, 999, 1000, partial-fill, and restart boundaries. |
| Preserve `lots` only as a legacy whole-lot input/projection | Avoid breaking existing clients and old Journal states while making `quantity_shares` authoritative for all new commands. |

## External Constraints

- TWSE supports one-share units for odd-lot trading.
- Shioaji production orders use an explicit odd-lot order type, but Shioaji Simulation officially does not support odd-lot orders.

## Request Changes Follow-up

- The initial safety copy lives inside `#order-preview`, which both simulation and candidate projection renders overwrite; the immutable boundary needs a separate DOM element.
- Pydantic's coercive `int` accepts JSON `true` as `1` before domain validation. Both manual-order and strategy-intent request models need strict positive integer fields, plus HTTP-level negative tests.
- `app.js` still imports `simulation.js` with the pre-share-input cache key. A new cache key must be asserted by the module-structure test.
- The worktree remains heavily mixed with unrelated atomic-strategy/backtest changes; only review-linked lines and tests should be edited.
- `#order-preview` is intentionally the dynamic cash/alert line in both workspace modules, so the smallest safe fix is to keep that id and add a sibling static safety paragraph rather than changing both renderers.
- The server already imports Pydantic `Field`, so strict positive validation can use `Annotated[int, Field(strict=True, gt=0)]` without adding a custom validator.
- HTTP negative coverage should exercise the FastAPI/Pydantic boundary with `TestClient`; direct request-model construction does not prove JSON booleans are rejected.
- After the fix, both boolean HTTP tests return Pydantic `int_type` errors at `body.quantity_shares`; they no longer enter the command or provider path.
- The static boundary is now a sibling of dynamic `#order-preview`, and neither projection module references its id.
- The simulation import key is now `20260822-share-native-v1` and is pinned by the module-structure test.
- Unlike the preceding run, the current shared-worktree full regression has no migration-order failure: 1,135 tests passed and 16 skipped. Report the current clean result rather than carrying forward the stale exception.
- Real-browser verification after the initial dashboard projection rendered showed dynamic `#order-preview` as available cash while the sibling boundary remained visible with the full no-exchange-book/no-broker text.

## Scoped Commit Findings

- The core simulation/runtime/local-paper files and their focused tests contain only the reviewed share-native changes and can be staged as whole files.
- `dashboard/static/js/workspaces/simulation.js` has one unrelated blank-line deletion; stage all functional hunks but exclude that whitespace hunk.
- README contains two odd-lot hunks followed by unrelated qualification documentation; stage only the local-paper description and strategy-intent examples.
- `index.html` contains the odd-lot form hunk, extensive unrelated backtest/strategy UI, and the top-level app cache-key hunk. Per the approved reminder, stage the form and top-level cache key together with the nested simulation import.
- `app.js` contains the nested simulation cache key and stale `orderLots` removal plus unrelated atomic-strategy state; stage only the two odd-lot/cache hunks.
- `test_dashboard_module_structure.py` must stage the top-level entrypoint expectation, nested simulation cache expectation, and odd-lot form test while excluding the unrelated backtest import assertion change.
