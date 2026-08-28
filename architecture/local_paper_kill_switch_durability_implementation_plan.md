# Local Paper Kill Switch 持久化 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`
- 規劃日期：`2026-08-26`
- 執行模式：`LOCAL_PAPER_SIMULATION`
- 交易時段需求：不需要；開發、測試與 PostgreSQL UAT 均可離線執行
- 預估工期：4～5 個開發日，另加 0.5～1 日獨立 review

這份計畫只處理 Kill Switch 的持久化、稽核、重啟復原與 fail-closed admission。它不實作稅費／滑價、不修改 No-Overnight 候選，也不增加 Shioaji／券商下單能力。

## 1. 結論先講

目前的 Kill Switch 能在單一 Dashboard process 內停止新的自動策略意圖，但 process 重啟後會回到未啟用，而且 engage/reset 沒有 durable actor、冪等 operation 或 revision evidence。

目標是把它改成：

1. 使用現有 Trading Journal 保存全域 control events。
2. Dashboard 重啟或 Local Paper settings 換 session 後，仍恢復相同 engaged/revision 狀態。
3. engage/reset 都有 actor、reason、retry-stable idempotency key 與結果證據。
4. reset 必須帶目前 exact revision，過期畫面不能解除較新的緊急停止。
5. Journal/replay 不確定時進入 `RECOVERY_REQUIRED`，禁止自動策略 start 與新 intent。
6. 在 `StrategyPaperFlowService.submit()` 增加最後 admission，關閉 controller check 與 submit 間的競態。
7. 不自動平倉；查詢、人工 cancel、reconciliation 與獨立 No-Overnight 安全流程不受阻擋。

## 2. Current state

### 2.1 已有能力

- `simulation/continuous_strategy.py::LocalPaperKillSwitch`
  - process-local `RLock`、`engaged`、`reason`、`engaged_at`。
  - controller start 前與每次 evaluation 都會檢查。
  - engage 後 controller 進入 `KILLED`，停止 worker 並清除 entry quote watch。
  - reset 後維持 `STOPPED`，不會自動重新啟動。
- `dashboard/server.py`
  - 提供 status、engage、reset routes。
  - mutation 已有 loopback、Origin 與 CSRF 防護。
  - controller/composition 建構及 settings handoff 已由 `_runtime_composition_lock` 序列化。
- `trading/journal.py`、`trading/postgres_journal.py`
  - 已有 append-only records、canonical fingerprint、record/idempotency conflict protection 與 PostgreSQL parity。
- `runtime/composition.py`
  - 是 Local Paper Journal、simulation、command service 與 recovery 的唯一 composition root。

### 2.2 缺口

- Kill Switch 是 module-global memory object；process 重啟會遺失。
- strategy runtime checkpoint 只有存在 `run_id` 時才寫，不能作為全域 Kill Switch authority。
- engage request 只有 reason；reset 沒有 request body。
- actor 只是 start activation 才有，Kill Switch 沒有 durable attribution。
- response-loss retry 沒有 operation key，重送無法證明是同一次操作。
- reset 沒有 expected revision，舊瀏覽器畫面可能清除較新的 incident。
- controller 的早期 check 不是最後 admission；engage 與 `_flow.submit(intent)` 之間存在競態。
- Local Paper settings apply 會建立新 trading session；若控制狀態綁錯 session，可能在換設定時消失。
- memory 測試不能證明跨 process durability；目前 PostgreSQL 測試缺 DSN 時會 skip。

## 3. Scope

### 3.1 In scope

- 全域 Local Paper automated-strategy Kill Switch。
- append-only Journal event、projection replay、revision 與 operation receipt。
- process restart 與 settings-session rotation recovery。
- controller + `StrategyPaperFlowService` final admission。
- engage/reset API、Dashboard 操作、狀態顯示與 retry-stable idempotency。
- memory adapter contract tests與 PostgreSQL destructive UAT。
- failure injection、concurrency、runbook、README 與 Gate evidence。

### 3.2 Non-goals

- 不處理一般 stop 的 durable audit；另案執行。
- 不實作證交稅、手續費調整、滑價或真實排隊順位。
- 不自動 cancel、flatten 或賣出既有部位。
- 不修改或依賴 PR-NO-006 frozen worktree。
- 不實作 broker order、CA、trade callback、`place_order` 或 real-money execution。
- 不新增 authentication/RBAC；`actor_id` 在現階段是 loopback single-user 的稽核 attribution，不是已驗證身分。
- 不宣稱 multi-process、multi-worker、HA 或 distributed lease 安全。
- 不將 memory backend 宣稱為 restart durable。

## 4. Safety invariants

1. **Journal authority**：PostgreSQL 模式下，append-only control events 是唯一 durable truth；checkpoint 只能是可重建的最佳化。
2. **Stable scope**：控制狀態使用固定 control session，不跟 Local Paper trading session 一起輪替。
3. **Fail closed**：Journal 無法讀寫、event 無法 replay、revision 不連續或 metadata 衝突時，狀態為 `RECOVERY_REQUIRED`，自動 start/intent 都禁止。
4. **Engage monotonic-safe**：任何 operator 都可送出新的 engage/reaffirm；不要求 expected revision。
5. **Reset strict**：reset 必須符合目前 exact engaged revision；stale reset 永遠不能清除較新的 engage/reaffirm。
6. **Idempotent retry**：相同 idempotency key + 相同語意 payload 回傳同一 operation receipt；相同 key + 不同 payload 回 `409`，不得改狀態。
7. **No false restart**：reset 只解除 latch並使 controller 維持 `STOPPED`；不得自動恢復 `RUNNING`。
8. **Linearized intent admission**：engage 成功回傳後，任何較晚的 automated intent 不得寫入 strategy intent Journal 或進入 command service。
9. **Pre-existing command semantics**：在 engage linearization 前已 admission 的 command 屬於既有操作；本任務不取消或偽造其結果。
10. **Risk-reducing independence**：查詢、人工 cancel、reconciliation 與 No-Overnight safety path 不得因本 switch 被封鎖。
11. **No synthetic evidence**：不得以 controller state、UI 顯示或 memory test 代替 PostgreSQL restart evidence。
12. **Authority boundary**：所有 event 明示 `execution_boundary=LOCAL_ONLY`；不得新增券商 authority。

## 5. Target architecture

```text
Dashboard engage/reset
  -> loopback + Origin + CSRF
  -> DurableLocalPaperKillSwitch
       -> stable control Journal session
       -> append local_paper_kill_switch_*.v1 event
       -> update in-process projection
  -> ContinuousPaperStrategyController state update

Automated intent
  -> ContinuousPaperStrategyController early check
  -> StrategyPaperFlowService final admission
       -> DurableLocalPaperKillSwitch admission lock/state
       -> strategy intent Journal
       -> LocalPaperCommandService
       -> RiskGate
       -> SimulationService

Process restart
  -> RuntimeComposition
  -> open/validate stable control session
  -> strict replay of control events
  -> construct controller only after recovery
```

建議新增兩層：

- `trading/kill_switch.py`：純 contract、event factory、strict projector/replay。
- `simulation/kill_switch.py`：Journal-first application service、single-process linearization、status 與 fail-closed state。

不要增加另一個 SQLite/JSON control store，也不要把 Kill Switch 塞進 strategy `run_id` checkpoint。

## 6. Durable contract

### 6.1 Stable Journal session

建議固定：

```text
session_id = local-paper-global-control-v1
mode = LOCAL_PAPER_CONTROL
```

Immutable metadata 至少包含：

```json
{
  "contract_version": "local-paper-kill-switch-control-v1",
  "control_scope": "GLOBAL_AUTOMATED_LOCAL_PAPER",
  "execution_boundary": "LOCAL_ONLY",
  "restart_policy": "STRICT_EVENT_REPLAY",
  "writer_model": "SINGLE_PROCESS"
}
```

既有 session metadata 不一致時，composition 必須失敗，不可建立另一個替代 session。

### 6.2 Event kinds

```text
local_paper_kill_switch_engaged.v1
local_paper_kill_switch_reset.v1
```

每一筆 payload 至少包含：

```json
{
  "contract_version": "local-paper-kill-switch-control-v1",
  "action": "ENGAGE | RESET",
  "operation_id": "retry-stable-idempotency-key",
  "actor_id": "local-operator",
  "reason": "operator supplied reason",
  "prior_revision": 2,
  "revision": 3,
  "resulting_state": "ENGAGED | DISENGAGED",
  "execution_boundary": "LOCAL_ONLY"
}
```

規則：

- `record_id = local-paper-kill-switch:{operation_id}`。
- engage/reset 共用同一個 global idempotency scope，避免同一 key 被另一種 action 重用。
- `occurred_at` 使用 server-owned aware clock；不信任 browser timestamp。
- projector 依 Journal append sequence 讀取，並嚴格要求 `prior_revision == current_revision`、`revision == prior_revision + 1`。
- ENGAGE 在已 engaged 時視為 reaffirm，仍新增 revision並更新 reason/actor；因此舊 reset 會自然失效。
- RESET 只接受 `expected_revision == current_revision` 且目前為 engaged。
- retry 先依 operation id 尋找既有 event，再比較語意 payload；不可用新的 server time 重建 record後直接依 fingerprint猜測 retry。

### 6.3 Runtime state

狀態至少包含：

```text
control_state = DISENGAGED | ENGAGED | RECOVERY_REQUIRED
revision
reason
engaged_at
last_transition_at
last_actor_id
last_operation_id
durability = POSTGRESQL | EPHEMERAL_MEMORY
recovered
recovery_error
```

`RECOVERY_REQUIRED` 對 admission 等同 engaged，但不能透過一般 reset route 清除；必須先修復 Journal/replay condition，再由正常 recovery 重建 authoritative state。

### 6.4 Memory backend

- 保留開發與快速測試相容性。
- API/status 必須顯示 `durability=EPHEMERAL_MEMORY`、`restart_safe=false`。
- 不得用 memory 測試通過正式 durability Gate。
- 不在本任務中偷偷切換或 fallback backend；PostgreSQL 設定失敗時沿用現有 composition fail-fast 行為。

## 7. API and Dashboard contract

### 7.1 Engage

```http
POST /api/simulation/automated-strategy/kill-switch
```

```json
{
  "actor_id": "local-operator",
  "idempotency_key": "kill-engage-...",
  "reason": "行情或策略異常"
}
```

### 7.2 Reset

```http
POST /api/simulation/automated-strategy/kill-switch/reset
```

```json
{
  "actor_id": "local-operator",
  "idempotency_key": "kill-reset-...",
  "expected_revision": 3,
  "reason": "已完成檢查並確認解除"
}
```

### 7.3 Response

沿用 controller status，擴充：

```json
{
  "state": "KILLED",
  "decision": "KILL_SWITCH_ENGAGED",
  "kill_switch": {
    "control_state": "ENGAGED",
    "engaged": true,
    "revision": 3,
    "reason": "行情或策略異常",
    "last_actor_id": "local-operator",
    "last_operation_id": "kill-engage-...",
    "durability": "POSTGRESQL",
    "restart_safe": true,
    "recovered": false
  },
  "operation": {
    "idempotent": false,
    "operation_revision": 3
  }
}
```

HTTP mapping：

- 新 transition：`201`
- retry-stable replay：`200`
- stale revision／operation conflict／目前未 engaged：`409`
- 欄位格式錯誤：`422`
- persistence/recovery unavailable：`503`

Dashboard：

- engage/reset 各自保存 pending idempotency key，只有成功後才清除。
- reset 使用畫面目前顯示的 exact revision。
- engaged 時顯示 reason、時間、revision、durability。
- `RECOVERY_REQUIRED` 顯示阻擋訊息並停用 reset/start，不把它顯示為「未啟動」。
- reset 需明確確認與解除原因；成功後仍顯示 `STOPPED / MANUAL_START_REQUIRED`。

## 8. Failure matrix

| 情境 | 必須結果 |
|------|----------|
| PostgreSQL 啟動不可用 | composition/ready fail；不建立 controller、不接受 automated start |
| control session metadata 衝突 | `RECOVERY_REQUIRED` 或 composition fail；不得另建替代 session |
| event schema/revision replay 失敗 | `RECOVERY_REQUIRED`；start/intent/reset 全部阻擋 |
| engage Journal append 失敗 | API `503`；process-local 狀態進入 blocking recovery state；不得繼續 intent |
| reset Journal append 失敗 | 保持 engaged；API `503` |
| engage response 遺失後重送 | 回原 operation receipt，狀態不重複變更 |
| 同 operation key、不同 actor/action/reason | `409`；零新 event、零 state mutation |
| stale reset revision | `409`；仍 engaged |
| engage 與 intent 競態 | 由同一 admission lock 定義先後；engage 回傳後不得出現較晚 intent |
| engage 後 controller checkpoint 失敗 | durable switch 仍 authoritative；自動 intent 仍 blocked |
| settings apply 換 trading session | control state/revision完全不變 |
| process restart while engaged | recovery 後第一個 status 即 engaged；start 回 `409` |
| reset 成功後 process restart | recovery 為 disengaged，但 controller 仍 `STOPPED` |
| memory backend restart | 不宣稱恢復；status 明示 ephemeral |

## 9. Implementation phases

### KS-001 — Domain contract and Journal replay

預估：0.5～1 日。

修改：

- 新增 `trading/kill_switch.py`。
- 新增 `tests/test_kill_switch_domain.py`。

內容：

1. 定義 event kinds、stable session metadata、state/revision與 exception taxonomy。
2. 實作 canonical record factories。
3. 實作 strict replay/projector。
4. 實作 operation lookup、same-key semantic comparison與 operation receipt。
5. 不新增 SQL migration；使用現有 `journal_sessions`、`journal_records`。

Acceptance：

- empty Journal 得到 revision 0 / disengaged。
- engage、reaffirm、reset replay deterministic。
- stale reset、revision gap、unknown control event、metadata conflict fail closed。
- same-key same-payload retry成功；same-key different-payload conflict。
- 所有 payload canonical、timezone-aware，明示 LOCAL_ONLY。

### KS-002 — Durable application service and composition recovery

依賴：KS-001。預估：1～1.5 日。

修改：

- 新增 `simulation/kill_switch.py`。
- 修改 `runtime/composition.py`。
- 修改 `runtime/ports.py`（只有確實需要共用 protocol 時）。
- 修改 `tests/test_runtime_composition.py`。
- 新增 `tests/test_kill_switch_service.py`。

內容：

1. 建立 `DurableLocalPaperKillSwitch`，持有 Journal、Clock、projection與單一 linearization lock。
2. RuntimeComposition 建立/驗證 stable control session並在 controller 可見前 strict replay。
3. settings replacement 重用同一 service或以同一 stable Journal state重建；不得綁新 trading session。
4. persistence/replay failure 進入 `RECOVERY_REQUIRED`。
5. memory backend status 明示 ephemeral；PostgreSQL 不可 silent fallback。

Acceptance：

- 用同一 InMemory Journal重建 composition，可模擬 recovery契約。
- settings session輪替不改 engaged/revision。
- malformed replay不能產生 default-disengaged controller。
- close/recreate不自動 reset。

### KS-003 — Controller, final admission, API and Dashboard

依賴：KS-002。預估：1～1.5 日。

修改：

- 修改 `simulation/continuous_strategy.py`。
- 修改 `simulation/strategy_flow.py`。
- 修改 `dashboard/server.py`。
- 修改 `dashboard/static/js/workspaces/simulation.js`。
- 視需要修改 `dashboard/static/index.html`。
- 修改 `tests/test_continuous_paper_strategy.py`。
- 修改 `tests/test_strategy_paper_flow.py`。
- 修改 `tests/test_dashboard_simulation_api.py`。
- 修改 `tests/test_dashboard_module_structure.py`。

內容：

1. 移除 `dashboard.server` 的 process-global raw switch，改由 composition 注入 durable service。
2. Controller engage/reset 接收完整 operation metadata。
3. `StrategyPaperFlowService.submit()` 在 strategy intent Journal append前做最後 admission，並與 engage/reset共用 linearization boundary。
4. 保留 cancel/query/reconciliation與 No-Overnight safety seam；不新增 flatten。
5. API request 使用 `extra=forbid`，保留 loopback/Origin/CSRF。
6. Dashboard保存 retry key、傳 expected revision、顯示 durable/recovery狀態。

Acceptance：

- engage成功後 start與新 automated intent都 blocked。
- engage/submit concurrency測試證明線性順序；engage回傳後沒有 later intent。
- reset不會自動 start。
- response-loss retry不建立第二筆 event。
- stale reset保持 engaged。
- manual order/cancel與 read APIs沒有被 Kill Switch新增阻擋。
- No-Overnight相關檔案與 frozen worktree零修改。

### KS-004 — PostgreSQL UAT, operations and Gate

依賴：KS-003。預估：1 日，另加獨立 review 0.5～1 日。

修改：

- 新增 `tests/test_kill_switch_postgres.py`。
- 新增 `architecture/local_paper_kill_switch_runbook.md`。
- 更新 `README.md`。

UAT 必須使用明確的一次性 `TEST_POSTGRES_DSN`：

1. fresh schema套 migrations。
2. Process A engage並保存 event/revision。
3. 關閉 Process A；Process B使用同一 DB重建。
4. 第一個 status即 engaged，automated start被拒絕。
5. 重送 engage key驗證 idempotent；衝突 payload驗證 `409`。
6. stale reset驗證仍 engaged。
7. valid reset後關閉；Process C重建為 disengaged + controller stopped。
8. 進行 settings-session rotation並再次驗證 control revision不變。
9. 注入 DB failure、replay corruption與並行操作，確認 fail closed。
10. 保存命令、exit code、pass/skip counts、Journal records與recovery摘要；不得包含 DSN/secrets。

Gate：

- `Implementation Review = PASSED`
- `Focused tests = PASSED`
- `Full no-DSN suite = PASSED`，但 skip 不算 PostgreSQL evidence
- `PostgreSQL destructive UAT = PASSED`，不可 waiver後仍稱完成
- `Restart recovery = PASSED`
- `Settings rotation = PASSED`
- `Concurrency/failure injection = PASSED`
- `Broker/live scope audit = PASSED`

## 10. Verification commands

實作者應先以當下 repository重新確認實際檔名，再執行等價命令：

```bash
.venv/bin/pytest -q \
  tests/test_kill_switch_domain.py \
  tests/test_kill_switch_service.py \
  tests/test_continuous_paper_strategy.py \
  tests/test_strategy_paper_flow.py \
  tests/test_runtime_composition.py \
  tests/test_dashboard_simulation_api.py \
  tests/test_dashboard_module_structure.py

TEST_POSTGRES_DSN='postgresql://…一次性測試資料庫…' \
  .venv/bin/pytest -q tests/test_kill_switch_postgres.py

.venv/bin/pytest -q
.venv/bin/ruff check trading simulation runtime dashboard tests
node --check dashboard/static/js/workspaces/simulation.js
git diff --check
```

另外執行 scope scan，確認沒有 `place_order`、CA、trade callback、`subscribe_trade=True`、broker mutation 或 PR-NO-006變更。

## 11. Rollout and rollback

### Rollout

1. KS-001～KS-003各自獨立 review，不把 broad green suite當 Gate。
2. 先在 memory adapter跑 contract tests；status必須明示 non-durable。
3. 再用 disposable PostgreSQL完成 KS-004。
4. 先部署到 supervised Local Paper，確認重啟與 settings rotation。
5. 通過後才能把 README 的 Kill Switch durable gap改為已完成；一般 stop durable audit仍保留為 backlog。

### Rollback

- engaged或`RECOVERY_REQUIRED`時禁止直接回滾到不認得 durable events的舊版本，因舊程式會把它誤認成 disengaged。
- 回滾前必須確認 controller stopped、沒有自動 worker、沒有 pending automated entry，且 authoritative state為 disengaged。
- PostgreSQL Journal events保留，不刪除、不重寫。
- 若 rollout失敗，保持自動策略停用並修正 forward；不要清空 Journal來恢復服務。

## 12. Parallelization

可以同時進行：

- KS-001 contract實作期間，另一人可準備 reviewer-only adversarial cases與runbook草稿。
- KS-002完成介面後，Dashboard UI與PostgreSQL UAT fixture可平行準備。
- 稅費／滑價可在另一個獨立 branch進行，但不得共用本任務檔案或 commit。

不可同時／必須依序：

- KS-002必須等KS-001 contract凍結。
- KS-003 final admission必須等KS-002 service API穩定。
- KS-004正式UAT必須使用已review且commit固定的候選。
- 不可修改正在等待交易日capture的PR-NO-006 worktree。

## 13. Definition of Done

- [ ] engage/reset都有 actor、reason、idempotency與revision evidence。
- [ ] engaged狀態跨完整 process restart恢復。
- [ ] settings換session不清除或回退revision。
- [ ] stale reset與conflicting retry均fail closed。
- [ ] engage/submit競態有永久測試。
- [ ] Journal/replay failure進入`RECOVERY_REQUIRED`，不呈現disengaged。
- [ ] reset後仍需人工start。
- [ ] manual cancel/query/reconciliation與No-Overnight安全流程未被阻擋。
- [ ] memory狀態明示ephemeral。
- [ ] PostgreSQL destructive UAT實際通過，沒有以skip/waiver代替。
- [ ] README/runbook/source與Dashboard狀態一致。
- [ ] 無broker/live authority變更。
- [ ] 未修改PR-NO-006 frozen worktree。
- [ ] 已完成獨立code review且沒有P1/P2 finding。

## 14. 建議獨立任務標題

```text
實作 Local Paper Kill Switch 持久化與重啟復原
```

## 15. 可直接貼到新任務的 Prompt

```text
請依照以下 implementation plan 實作 Local Paper Kill Switch 持久化：

/Users/stevehuang-work/Documents/tw_intraday_trader/architecture/local_paper_kill_switch_durability_implementation_plan.md

工作要求：
1. 先完整閱讀計畫與目前 source，重新確認 branch、HEAD、dirty worktree與實際檔名。
2. 使用獨立 branch/worktree；base必須包含目前main的Local Paper、Journal與automated strategy功能。不要修改PR-NO-006 frozen worktree，也不要混入主worktree既有變更。
3. 只做Kill Switch durability；一般stop持久化、稅費／滑價、No-Overnight、broker/live都不在範圍。
4. 依KS-001 → KS-004順序執行；每階段完成focused tests與review後再進下一階段。
5. 使用現有Trading Journal作為唯一durable truth；不得建立第二個JSON/SQLite控制狀態。
6. Journal/replay不確定時fail closed為RECOVERY_REQUIRED；reset必須exact revision；response-loss retry必須idempotent。
7. 在StrategyPaperFlowService加入最後automated-intent admission，並補engage/submit concurrency永久測試。
8. 保留loopback/Origin/CSRF與LOCAL_PAPER_SIMULATION邊界；不得新增任何Shioaji/broker order authority。
9. PostgreSQL UAT需要明確的一次性TEST_POSTGRES_DSN；缺DSN時只能回報BLOCKED/NOT PASSED，不得用skip或waiver宣稱完成。
10. 不要自行push；完成實作、測試與scope audit後先交付review摘要。
```
