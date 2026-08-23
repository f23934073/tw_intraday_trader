# Local Paper Runtime Settings Implementation Plan

## 1. Outcome

Add a dedicated `本機模擬設定` page that lets the local operator edit and persist:

- starting cash, default `10,000,000 TWD`;
- daily gross BUY limit, default `2,000,000 TWD`;
- commission rate for BUY and SELL fills, compatibility default `0` and editable as a percentage in the UI;
- optional minimum commission per order, default `0 TWD`.

The values are independent controls. Available cash still limits BUY orders even when the daily BUY limit is higher. The daily BUY limit still limits BUY orders even when available cash is higher.

This plan is for `LOCAL_PAPER_SIMULATION` only. It adds no Shioaji order, cancellation, CA, broker-account, or real-money path.

## 2. Current repository state

- `simulation/service.py` owns a hard-coded `10,000,000` starting-cash default.
- `simulation/application.py` derives several local risk values from starting cash.
- local paper reserves and settles gross notional only; it does not calculate commission or transaction tax.
- `RuntimeComposition.create()` creates one process-wide simulation service and pins starting cash into Journal session metadata.
- the Journal session id is currently fixed as `local-paper-runtime-v1`.
- the dashboard has simulation session/order/position APIs and drawers, but no local-paper settings API or settings page.
- the selected Journal backend may be in-memory, so Journal metadata alone is not a persistent editable-settings store.

## 3. Frozen v1 behavior

### 3.1 Settings contract

Create a typed `LocalPaperRuntimeSettingsV1` contract with canonical Decimal strings:

| Field | Default | Validation | Meaning |
|---|---:|---|---|
| `starting_cash_twd` | `10000000` | finite and `> 0` | Opening cash of a newly applied simulation session |
| `max_daily_buy_notional_twd` | `2000000` | finite and `> 0` | Daily gross BUY budget |
| `commission_rate` | `0` | finite and `0 <= value <= 0.01` | Commission charged on BUY and SELL fills; zero preserves existing sessions until the operator chooses a rate |
| `minimum_commission_twd` | `0` | finite and `>= 0` | Minimum cumulative commission per order |

`max_daily_buy_notional_twd` is not required to be less than starting cash. The two values are intentionally independent gates.

Sell transaction tax remains unchanged and excluded from this annotation-driven v1 scope. It must not be silently bundled into commission.

### 3.2 Daily BUY budget

For one Taiwan trading date:

```text
used BUY budget
= filled BUY gross notional
 + active unfilled BUY reservation at limit price
```

- A new BUY is accepted when `used + new gross notional <= configured limit`.
- A value exactly equal to the limit is allowed.
- SELL proceeds never restore the daily BUY budget.
- Cancelling or expiring an order releases only its unfilled reservation.
- A partial fill permanently consumes its filled gross notional and keeps the remaining limit-price reservation.
- The budget resets at the Taiwan trading-day boundary.
- Restart recovery derives same-day filled BUY notional from Journal fill evidence and active reservations from recovered order state.
- Commission is excluded from this budget calculation; it is handled by the separate available-cash gate.

### 3.3 Commission and cash

Use Decimal arithmetic and one explicit `FeeRoundingPolicyV1`: `ROUND_HALF_UP` to two decimal places.

For an order with cumulative filled gross notional `G`:

```text
cumulative_commission = max(minimum_commission_twd, round(G * commission_rate))
incremental_commission = cumulative_commission - commission_already_charged
```

The minimum is applied once to the cumulative order, not once per partial fill.

- BUY cash debit: `fill gross + incremental commission`.
- SELL cash credit: `fill gross - incremental commission`.
- BUY reservation: remaining limit-price gross plus the remaining estimated commission for the complete order.
- Realized PnL includes both BUY and SELL commission attributable to the closed shares.
- Daily BUY budget continues to count gross BUY notional only.
- `commission_rate=0` and `minimum_commission_twd=0` reproduce the current no-fee behavior.

### 3.4 Settings lifecycle

Settings have separate `draft` and `active` revisions.

1. `儲存設定` validates and atomically persists a new draft revision. It does not mutate the active account.
2. `套用並建立新模擬帳戶` pins that revision into a new Journal session and makes it active only after the new session and initial checkpoint are valid.
3. The prior session remains immutable and replayable; append a terminal session record rather than deleting it.
4. Applying is blocked while an automated strategy is running.
5. When positions or active orders exist, the API requires an explicit reset confirmation and the UI lists what will be left in the archived session.
6. If creation of the replacement session fails, the old runtime and active-session pointer remain unchanged.

There is no in-place hot mutation. This prevents starting cash, fee policy, and pending-order reservations from changing underneath an active or recoverable session.

## 4. Persistence and compatibility

### 4.1 Editable settings repository

Add a small port and an atomic file-backed adapter:

- `config/local_paper.py`: defaults, typed environment/path configuration, and validation constants.
- `simulation/settings.py`: settings contract, revision digest, repository protocol, and JSON adapter using temporary-file plus atomic replace.
- default path: `data/local_paper/settings_v1.json`.
- add `data/local_paper/` to `.gitignore`.

The JSON document stores schema version, revision, active settings, draft settings, active Journal session id, and update timestamp. Writes use optimistic revision checks so two browser tabs cannot silently overwrite one another.

### 4.2 Immutable Journal binding

Every new Journal session metadata snapshot includes:

- settings schema and revision;
- settings digest;
- starting cash;
- daily BUY limit;
- commission rate;
- minimum commission;
- fee rounding policy;
- `execution_boundary=LOCAL_ONLY`.

Add new fee-bearing records rather than changing historical fingerprints:

- keep `local_paper_fill.v1` replay semantics unchanged with commission `0`;
- write `local_paper_fill.v2` for new settings-bound sessions, including gross, commission, net cash effect, cumulative order commission, and settings digest;
- advance the projection schema/checkpoint name for fee-aware sessions while retaining the v1 reader.

Legacy `local-paper-runtime-v1` sessions remain readable under a compatibility policy and are never automatically rewritten or reset. The settings page prompts the operator to apply a v1 settings revision to create the first settings-bound session.

## 5. Backend implementation phases

### Phase A — Settings domain and repository

Files:

- `config/local_paper.py`
- `simulation/settings.py`
- `.gitignore`

Work:

- add typed settings, canonical serialization, validation, revision digest, and defaults;
- implement atomic file persistence and optimistic concurrency;
- fail closed on corrupt or unsupported settings documents;
- add unit tests for defaults, validation, concurrent revisions, atomic recovery, and corrupt files.

### Phase B — Session lifecycle and composition

Files:

- `runtime/composition.py`
- `dashboard/server.py`
- `simulation/continuous_strategy.py` only if a read-only running-state guard is needed
- `trading/local_paper.py`

Work:

- replace the fixed active-session assumption with a bounded local-paper session manager;
- pin one immutable settings revision to each new Journal session;
- create the replacement runtime before switching the active-session pointer;
- retain the old session and checkpoint on success or failure;
- block apply while an automated strategy is running;
- make restart recovery load the active session and its pinned settings digest.

### Phase C — Daily BUY enforcement

Files:

- `trading/risk.py`
- `trading/application.py`
- `simulation/application.py`
- `simulation/service.py`
- `trading/local_paper.py`

Work:

- add `max_daily_buy_notional` to the pinned policy;
- add filled and active-reserved BUY notional to `RiskSnapshot` and Journal risk evidence;
- reject over-limit BUY commands with `DAILY_BUY_NOTIONAL_LIMIT`;
- enforce the same invariant in `SimulationService` so direct calls cannot bypass the command facade;
- recover same-day usage and reset only on trading-date rollover;
- expose limit, filled, reserved, used, and remaining values in the simulation session projection.

### Phase D — Commission-aware accounting

Files:

- `simulation/models.py`
- `simulation/service.py`
- `trading/local_paper.py`
- `simulation/application.py`

Work:

- add cumulative gross/commission fields to order state;
- reserve BUY gross plus estimated commission;
- settle BUY/SELL cash and realized PnL with incremental commission;
- write and replay `local_paper_fill.v2` deterministically;
- preserve zero-fee v1 replay and verify checkpoint compatibility.

### Phase E — Settings API

Files:

- `dashboard/server.py`
- `tests/test_dashboard_simulation_api.py`

Endpoints:

- `GET /api/simulation/settings`: active/draft values, revisions, apply blockers, current session summary, and loopback CSRF token.
- `PUT /api/simulation/settings`: validate and save a draft using the expected body revision plus loopback/origin and CSRF guards.
- `POST /api/simulation/settings/apply`: apply the draft to a new session, requiring explicit reset confirmation when necessary.

Return canonical decimal strings for configuration values. Use `409` for stale revisions or active-session blockers and `422` for invalid values.

### Phase F — Settings page and session visibility

Files:

- `dashboard/static/index.html`
- `dashboard/static/js/app.js`
- `dashboard/static/js/workspaces/simulation.js`
- `dashboard/static/css/dashboard.css`
- `tests/test_candidate_workspace_ui.py`

Work:

- add `本機模擬設定` under the existing local-paper sidebar section;
- show active values separately from the editable draft;
- use labelled number inputs for starting cash, daily BUY limit, commission percentage, and minimum commission;
- show that commission applies to BUY and SELL while the daily budget excludes it;
- show apply blockers and require a typed/explicit confirmation before archiving a non-empty current session;
- display `今日已使用／剩餘買入額度` and current commission policy in the normal simulation projection;
- update visible disclosure: this remains local paper and never changes broker settings.

### Phase G — Documentation and regression

Files:

- `README.md`
- relevant API/UI/runtime tests listed below

Work:

- document configuration persistence, apply/reset semantics, formulas, and legacy compatibility;
- remove the outdated statement that local paper never calculates commission;
- retain the explicit no-Shioaji-order boundary.

## 6. Test plan

### Settings

- defaults load when no settings file exists;
- both cash and daily limit can be edited independently;
- zero and invalid/non-finite values fail closed;
- commission allows zero and valid configured rates;
- stale revision update returns conflict;
- corrupt settings file does not silently fall back and trade.

### Daily BUY budget

- exactly at the configured limit is allowed; one cent over is rejected;
- aggregation works across orders, symbols, manual orders, and automated strategy orders;
- active pending orders reserve budget;
- cancel/expire releases only unfilled budget;
- partial fills retain correct filled plus remaining usage;
- SELL never restores budget;
- restart preserves same-day usage;
- the next Taiwan trading date resets usage;
- direct `SimulationService` calls cannot bypass the limit.

### Commission

- BUY cash and reservation include commission;
- SELL proceeds and realized PnL subtract commission;
- partial fills charge the configured minimum once per order;
- zero-fee configuration matches legacy calculations;
- restart/replay reproduces exact cash, positions, PnL, and commission totals;
- v1 historical fills continue to replay with commission zero.

### Settings apply

- saving a draft does not change the active session;
- applying a clean draft creates and switches to a new settings-bound session;
- active automated strategy blocks apply;
- non-empty session requires explicit confirmation;
- failed new-session creation leaves the old session active;
- old Journal evidence remains queryable and unchanged.

### Focused regression files

- `tests/test_simulation_service.py`
- `tests/test_local_paper_command_service.py`
- `tests/test_local_paper_projection.py`
- `tests/test_recoverable_simulation_orders.py`
- `tests/test_risk_gate.py`
- `tests/test_order_application.py`
- `tests/test_runtime_composition.py`
- `tests/test_strategy_paper_flow.py`
- `tests/test_dashboard_simulation_api.py`
- `tests/test_candidate_workspace_ui.py`
- `tests/test_realtime_quote_stream.py`

Then run the complete repository suite, JavaScript syntax validation, Python compilation, and `git diff --check`.

## 7. Acceptance criteria

- The settings page can persistently edit starting cash, daily BUY limit, commission rate, and minimum commission.
- The page clearly distinguishes saved draft values from the currently active session values.
- Applying new values never rewrites or silently resets the old account; it creates a new auditable session.
- With cash `10,000,000` and daily BUY limit `2,000,000`, gross BUYs above the daily aggregate are rejected even when cash remains.
- SELL never restores the daily BUY budget.
- Commission affects cash reservation, settlement, and realized PnL but not daily gross BUY-budget consumption.
- Restart recovery reproduces exact settings, usage, commission, cash, orders, and positions.
- Existing v1 Journal evidence and checkpoints remain verifiable.
- Manual and automated local-paper orders use the same settings-bound Risk and accounting path.
- Runtime lookup and every Journal-mutating dashboard action share one lifecycle lease; settings apply rechecks blockers only after older actions drain.
- `local_paper_session_archive.v1` is terminal for the archived session; no later command, fill, cancellation, state, or checkpoint evidence may be appended.
- No Shioaji order/account mutation path is added.

## 8. Rollout and rollback

Roll out with compatibility defaults: `commission_rate=0` and `minimum_commission_twd=0` preserve the pre-feature cash behavior until the operator saves and applies a settings revision. When no settings file exists, the repository exposes defaults without writing user state. Static asset versions are advanced with the feature so the settings UI is not served from a stale browser cache.

Rollback disables new settings-bound session creation and removes the UI entry, but keeps v2 readers available. Never remove the v2 replay path while v2 Journal sessions exist. Existing sessions and settings files are retained; rollback must not rewrite or delete them.

## 9. Explicit non-goals

- broker buying-power configuration;
- Shioaji Simulation or live-money order submission;
- broker commission synchronization;
- sell transaction tax or slippage configuration in this v1 slice;
- retroactively applying fees or daily limits to historical fills;
- changing backtest cost settings or results.

## 10. Implementation status — 2026-08-23 — Independently Accepted

- Implemented: persistent active/draft settings, independent daily gross BUY enforcement, commission-aware accounting, settings API, and Traditional Chinese settings/session UI.
- Legacy remediation complete: the compatibility detector accepts the exact pre-feature metadata shape (`starting_cash`, `execution_boundary=LOCAL_ONLY`, `journal_backend`, and `restart_policy`) and replays v1 fill/checkpoint evidence, while every partial new settings-binding field still fails closed.
- Stream remediation complete: public replacement activation reports Provider startup/subscription failures, and settings apply performs a state-preserving old→new handler handoff before settings pointer/archive/global commit. Any failure restores the same old simulation object, handler, subscriptions, quote watch, and BidAsk cache.
- Runtime-command remediation complete: one reentrant composition lease now spans service lookup and the full submit/cancel/retry, controller mutation, quote refresh, projection reconciliation, and trading-day rollover action. Settings apply uses the same lock, so it cannot inspect blockers or archive until older mutations finish.
- Deterministic concurrency evidence pauses an old-runtime BUY inside the route, observes settings apply waiting on the lifecycle lock, then proves the unconfirmed apply rechecks the filled position and returns 409. A later confirmed reset leaves `local_paper_session_archive.v1` as the final old-session record.
- TWD-cent precision is enforced, daily gross reservation and commission-inclusive cash reservation have distinct UI labels, and settings-bound zero/nonzero-fee fills always emit the complete `local_paper_fill.v2` evidence contract.
- Verification record: Phase 7 feature-focused regression `182 passed`; the complete suite is `1331 passed, 33 skipped`. Python compilation, both JavaScript syntax checks, and `git diff --check` pass.
- Independent acceptance record: third-P1 deterministic regression `1 passed`; local-paper regression selection `163 passed`; automated/atomic selection `64 passed`; complete suite `1331 passed, 33 skipped`. Python compilation, both JavaScript syntax checks, `git diff --check`, all seven implementation phases, active-plan preservation, settings-artifact absence, and broker-boundary scan were independently confirmed.
- Acceptance status: `Approve`. All three reported P1 boundaries are closed and the local-paper runtime settings implementation is independently accepted.
- Acceptance scope: local-paper runtime settings only. This approval does not accept or certify unrelated concurrent worktree changes.
- Preserved boundary: local paper only; no Shioaji or real-broker order/account mutation path was added.
