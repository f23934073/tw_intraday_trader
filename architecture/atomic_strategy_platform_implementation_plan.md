# 原子策略平台 Implementation Plan

## 1. 結論

本計畫將現有「固定程式策略＋Momentum 聚合訊號＋獨立回測目錄」整理成可版本化、可組合、可在 Web 管理、可由回測與本機模擬共同引用的原子策略平台。

### 1.1 實作前 Review Gate

**目前決策：契約層級 APPROVE / GO；實作 Gates G1/G2 已 PASSED；Gates G3/G4/G6 均核准為 `PASSED / MVP CONDITIONAL GO`；Gates G5/G7/G8/G9/G10 為 `PASSED / MVP SCOPED GO`。** B1–B5 契約維持 `REVIEWED / CLOSED`。所有 MVP Gate 只適用於單機、loopback、single-user、trusted PostgreSQL 的 Local Paper／Backtest scope；券商委託與真實交易仍不得開始：

| ID | Blocking contract | 本文件的處理方向 | Gate 狀態 |
|---|---|---|---|
| B1 | 參數化 Feature Request | Strategy Version 解析為 `FeatureRequestSpec`，cache/state 使用參數 digest 隔離 | REVIEWED / CLOSED |
| B2 | Feature Registry source of truth | 共用 Feature Specification，加上不同 runtime/cadence adapter，不新增第三套計算器；Section 22 ownership 已凍結 | REVIEWED / CLOSED |
| B3 | immutable Strategy Version 與 lifecycle 衝突 | PostgreSQL-only persistence；Draft-scoped Publish operation/result mapping、Draft row lock、retry/conflict contract 與同 transaction persistence 已通過 Review | REVIEWED / CLOSED |
| B4 | Risk 不可成為普通策略 member | Proposed/Approved ordering、monotonic merge、完整 exit bypass matrix 已通過 Review | REVIEWED / CLOSED |
| B5 | evaluation persistence 無上限 | 預設只保存重要事件與聚合資料；完整 trace 僅限有界 DEBUG artifact | REVIEWED / CLOSED |

契約 Gate 已關閉後仍維持下列實作邊界：

- Phase 1、Phase 2、Phase 3 已完成；Phase 3 只新增歷史回測 qualification evidence、PostgreSQL persistence 與 Web review，不修改 execution runtime。
- Phase 4 Local Paper Runtime 已通過 G4 的 MVP conditional Review；Phase 5 首批 rolling return／volume acceleration 已通過 G5 scoped Review。後續策略批次仍須分批授權與驗收，且不得新增任何券商委託能力。
- 每一 Phase 仍須通過自己的 migration、determinism、compatibility 與 regression 驗收。
- 先前 `1100 passed, 10 skipped` 不是有效的穩定 G1 證據：Review 在 Asia/Taipei 晚間重現 `8 failed, 1092 passed, 10 skipped`，根因為 wall-clock-dependent fixture 跨日。
- 後續 `0bcf61c` 已讓兩個 affected fixtures 共用 deterministic clock；Phase 13 也已完成其餘 snapshot、durable replay、integrity、migration acceptance 與 test cleanup guard remediation。最新全套證據為 disposable PostgreSQL `1113 passed`，一般無 DSN 模式 `1103 passed, 10 skipped`；最終短 Review 已正式關閉 G1。

核心原則：

1. 每個可獨立驗證的條件是一個原子策略，例如站上 VWAP、突破前高、N 分鐘報酬、N 分鐘量能加速。
2. 不再以「漲停加速」作為包含多個規則的可執行策略；既有 immutable metadata 保留作歷史相容，但不成為新架構的主要抽象。
3. 每個已實作的原子策略一個實作檔案；共用 Feature Specification，並由各 runtime/cadence adapter 計算，不重複定義 VWAP、rolling return、rolling volume 等語意。
4. 程式碼定義演算法、允許參數及驗證規則；Web 設定參數；資料庫保存不可變參數版本與策略組合。
5. 資料庫不得保存或執行任意 Python。每個 `runtime_binding` 必須對應伺服器端 allowlisted Registry。
6. 回測與本機模擬保存完全相同的策略版本、參數、組合及資料／成交假設 snapshot。
7. 本計畫不授權 Shioaji 券商委託、CA、交易回報或真實資金模式。
8. 原子策略平台所有新 persistence 只使用 PostgreSQL；不得寫入或 fallback 到 SQLite。

## 2. 使用者已確認的需求

- 原子策略可單獨回測、單獨啟用，也可與其他策略組合。
- 參數由 Web 表單設定，例如將「2 分鐘報酬 > 1.5%」建立為「3 分鐘報酬 > 2.0%」的新版本。
- 每個策略有固定 `strategy_id`、繁體中文名稱、版本、獨立實作、參數 Schema、資料庫 Record 與回測結果。
- Strategy Set 支援多個原子策略的組合。
- 策略用途與執行時段分開表示。
- 每次回測保留所用策略、版本、參數、資料、成本、引擎及成交模型。
- 盤前篩選、盤中進場、出場及風控形成一條可稽核 pipeline。

## 3. 四層資料模型

### 3.1 Strategy Template

表示伺服器已部署的演算法能力，不包含某次使用者選定的參數值。

必要欄位：

- `strategy_id`
- `display_name_zh_tw`
- `role`
- `session_phase`
- `implementation_version`
- `implementation_digest`
- `parameter_schema`
- `required_capabilities`
- `feature_requirements`
- `runtime_bindings`
- `description_zh_tw`

`runtime_bindings` 不是由 Web 任意輸入的 import path，而是 code-owned allowlist，例如：

```json
{
  "BACKTEST_KBAR_1M": "above_vwap.backtest_kbar_1m_v1",
  "REPLAY_TICK_BIDASK": "above_vwap.replay_tick_bidask_v1",
  "LOCAL_PAPER_TICK_BIDASK": "above_vwap.local_paper_tick_bidask_v1"
}
```

若同一純 evaluation kernel 可安全重用，可以由不同 adapter 共同呼叫；若 feature 語意或 evaluation cadence 不相容，就必須標記為 unavailable 或使用不同 binding identity，不能只靠 `supported_runtime_modes` 宣稱 parity。

### 3.2 Strategy Version

表示 Template 加上一組已驗證的不可變參數。

必要欄位：

- `strategy_version_id`
- `strategy_id`
- `version`
- `parameters_json`
- `parameter_schema_version`
- `template_digest`
- `configuration_digest`
- `change_note`
- `created_by`
- `created_at`
- `published_at`

同一演算法改變參數時建立新 Strategy Version，不修改舊版本。若演算法本身改變，另提高 `implementation_version` 及 `implementation_digest`。

不可變邊界：

- `strategy_version_drafts` 是可修改的獨立 Draft entity；Draft 不是 Strategy Version。
- `strategy_versions` 只在 Publish 成功時新增，保存 canonical parameters、schema/template/implementation digests，之後不可修改。
- `lifecycle_status` 不屬於不可變 Version row 或 configuration digest；目前狀態由 append-only `strategy_version_events` projection 得出。
- Publish 必須在單一 DB transaction 內重新取得 Draft，依當下 code-owned Schema、Template digest、參數 canonicalization、runtime capability 與 binding allowlist 重驗證，再原子寫入 Version 與 Publish event。先前 `/validate` 成功不構成 Publish 授權。
- lifecycle transition 一律 append event，不回寫 Version meaning 或 digest。

### 3.3 Strategy Set / Pipeline

Strategy Set 表示同一決策階段內的組合；Strategy Pipeline 表示不同階段的先後關係。

建議區分：

- Candidate/Filter Set：建立可訂閱／可評估標的集合。
- Entry Set：決定是否建立進場意圖。
- Exit Set：決定是否建立出場意圖。
- Execution Policy Binding：決定限價、有效期、取消與成交模型。
- Hard Risk Policy Binding：Execution Policy 產生完整但不可送出的 ProposedOrderCommand 後永遠執行；只有 admission 通過才形成 ApprovedOrderCommand，且 Risk 不屬於 Strategy Set member。

每個 Strategy Set member 必須保存：

- immutable `strategy_version_id`，不得只存模糊的 `strategy_id`。
- member version/configuration/implementation digest。
- composition order 與 attribution priority。
- member role 必須符合 Set stage；Risk Policy 不得加入 ANY/ALL/AT_LEAST_N。

新 API 不接受只含 raw strategy ID 的 member。既有 `StrategySetSnapshot.entry_strategy_ids/exit_strategy_ids` 只由 legacy compatibility adapter 讀取；舊 completed run 保持原始 config/digest 與舊 engine/binding，不改寫成新格式。

Pipeline 固定順序：

```text
Market Data event
  -> Runtime/Cadence Feature Adapter
  -> Filter Set -> Entry Set
  -> bounded owner-scoped quote watch -> canonical fresh BidAsk ready
  -> TradeIntent
  -> Execution Policy -> ProposedOrderCommand
  -> Hard Risk Admission -> ApprovedOrderCommand
  -> Simulation/Broker Adapter -> Fill -> Position state
                             |
                             v
              next event -> Exit Set -> TradeIntent
              -> Execution Policy -> ProposedOrderCommand
              -> Hard Risk Admission -> ApprovedOrderCommand
              -> Simulation/Broker Adapter -> monitor/terminal

restart -> pure Effective Risk preview -> checkpoint/reconciliation
        -> activation Journal + policy install -> RUNNING or RECOVERY_REQUIRED
```

這是一個持續事件迴圈／position lifecycle state machine，不是一筆訊號走完就結束的單次箭頭。成交後仍必須持續訂閱、評估 Exit Set、執行硬風控與復原，直到 position terminal。

### 3.4 Strategy Run Snapshot

每次回測或本機模擬啟動時，保存完整不可變 snapshot：

- Strategy Pipeline 及所有 member version IDs/digests。
- Template implementation digests。
- 所有參數值。
- Dataset ID、digest、capabilities、日期與 symbol universe。
- Feature Engine version。
- Backtest/Runtime Engine version。
- 資金、部位、手續費、稅、滑價及成交模型。
- Trading calendar、timezone 與 session policy。
- 啟動者、啟動時間、runtime mode 與 run ID。
- 每個 requested Feature 的 spec ID、canonical parameters、parameter digest、adapter identity 與 feature implementation digest。

## 4. 策略分類

不要將時間與用途混成單一 `type`。

### 4.1 Role

v1 建議保留相容並明確定義：

- `FILTER`：建立／縮小候選集合；由既有 `CANDIDATE` 遷移。
- `ENTRY`：產生進場決策。
- `EXIT`：產生出場決策。
- `CONTEXT`：只產生觀察情境；由既有 `SCORE/SIGNAL` metadata 遷移或標記為非執行。

`RISK` 不再是 Strategy Template role，也不是可回測挑選或組合的市場策略。Risk 是獨立的 code-owned Hard Risk Policy bounded context。既有 `CANDIDATE/SCORE/SIGNAL` immutable rows 維持原樣；新 projection 或 compatibility mapping 可將它們顯示為 FILTER/CONTEXT，但不得改寫歷史 row/digest。

### 4.2 Session Phase

- `PRE_MARKET`
- `OPENING`
- `INTRADAY`
- `END_OF_DAY`
- `POST_MARKET`
- `POSITION_LIFECYCLE`
- `ALL_SESSION`

### 4.3 Strategy role 與 order side 邊界

Strategy Template 使用 `ENTRY/EXIT` 表示用途，不再增加重複的 `decision_side=BUY/SELL`。目前 long-only v1 由 Execution Policy 將 ENTRY TradeIntent 轉成 BUY、EXIT TradeIntent 轉成 SELL，並正規化方向、張數、價格、tick、lot 與委託生命週期，產生尚不可送出的 ProposedOrderCommand。Hard Risk Admission 讀取完整 command 與 RiskSnapshot；只有通過後才形成 ApprovedOrderCommand 並交給 Simulation/Broker Adapter。

v1 Hard Risk 不得在 admission 中靜默修改數量或價格：只能完整 approve 或 reject/block。若需要縮量或改價，Execution Policy 必須建立新的 ProposedOrderCommand、command digest 與 idempotency identity，再重新 admission。

若未來支援放空，擴充 position action，例如 `OPEN_LONG/CLOSE_LONG/OPEN_SHORT/CLOSE_SHORT`，不要把 BUY/SELL 塞回 Template role。

## 5. 第一批原子策略

### Entry

- `above_vwap_entry`
- `cross_above_vwap_entry`
- `breakout_previous_high_entry`
- `rolling_return_entry`
- `volume_acceleration_entry`
- `distance_to_price_limit_entry`
- `external_ratio_entry`
- `opening_range_breakout_entry`
- `ema_crossover_entry`
- `rsi_bollinger_reversion_entry`

`above_vwap` 與 `cross_above_vwap` 建議先分開，避免用 `trigger_mode` 將「狀態成立」和「事件穿越」藏在同一策略名稱下；若最後決定合併，必須在 UI 與版本名稱明確顯示 trigger semantics。

### Exit

- `fixed_stop_loss_exit`
- `fixed_take_profit_exit`
- `trailing_stop_exit`
- `atr_stop_exit`
- `below_vwap_exit`
- `time_stop_exit`
- `end_of_day_exit`
- `sma_death_cross_exit`

### Filter / Context

- 前日流動性、跳空、價位、機構資料等 Filter。
- 台指期夜盤等 Context；預設不直接產生委託。

## 6. Feature Layer：共用規格與參數化要求

原子策略不能各自重新定義 VWAP、前高、rolling return、rolling volume、EMA、RSI、ATR 的語意；但 Tick/BidAsk、completed intraday Kbar 與 daily Kbar 的資料能力不同，不能強迫共用一個計算器或宣稱完全 parity。

建立 versioned **Feature Specification Registry**，只負責 feature ID、單位、canonical parameters、as-of、warm-up、missing/stale semantics 與 digest。實際計算由現有 bounded contexts 內的 runtime/cadence adapter 負責：

- Tick/BidAsk adapter：延伸 `features/engine.py` 的即時計算。
- completed intraday Kbar adapter：由 `backtest/features.py` 延伸。
- completed daily Kbar adapter：由 `backtest/daily_features.py` 延伸。

不得新增第三套 `strategy_runtime/feature_registry.py` 計算器。共享的是 Feature Specification 與 normalized `FeatureSnapshot` contract，不代表不同 cadence 的公式、可用資訊或結果必然相等。

第一批 Feature Specifications：

- `vwap_session_v1`
- `previous_intraday_high_v1`
- `rolling_return_v1`
- `rolling_volume_ratio_v1`
- `external_ratio_v1`
- `ema_v1`
- `rsi_v1`
- `bollinger_v1`
- `atr_v1`

每個 Feature Specification 必須定義：

- 來源事件及 cadence。
- completed-data/as-of 語意。
- warm-up。
- 缺值及 stale behavior。
- Decimal/rounding。
- session reset。
- feature version 與 input digest。

### 6.1 Parameterized Feature Request

Strategy Version 的參數必須解析成明確的 `FeatureRequestSpec`。例如使用者將 2 分鐘報酬改成 3 分鐘報酬時，不只是保存 JSON；runtime 必須真的建立 3 分鐘資料窗：

```json
{
  "feature_id": "rolling_return_v1",
  "parameters": {
    "window_minutes": 3
  },
  "parameter_digest": "sha256:..."
}
```

必要契約：

- Strategy Template 提供由 canonical Strategy Version parameters 產生 Feature Request 的 deterministic resolver。
- feature cache/state identity 至少包含 `feature_id + feature_parameter_digest + adapter_identity + symbol + session`；需要時再包含 cadence/runtime，確保 2m 與 3m 永不碰撞。
- runtime/backtest preflight 先彙整所選 exact Strategy Versions 的全部 Feature Requests，驗證 adapter capability，建立／暖機每個唯一 request，缺少任何一項即 fail closed。
- `return_2m`、`volume_2m` 等固定名稱逐步改為帶參數 metadata 的 normalized Feature Snapshot；legacy 欄位只留在 compatibility adapter。
- Feature Request parameters、digest、adapter identity 與 as-of semantics 都進入 Run Snapshot。

Atomic Strategy 只讀 Feature Snapshot，不直接呼叫 Provider 或自行聚合行情。

## 7. Parameter Schema 與 Web 表單

### 7.1 Code-owned Schema

每個策略檔案提供 JSON-compatible Schema，包含：

- 欄位名稱與繁體中文 label/help。
- 型別、單位、default、minimum、maximum。
- enum options。
- required/conditional fields。
- 跨欄位驗證，例如 entry start 必須早於 entry end。
- Schema version。

範例：

```json
{
  "window_minutes": {
    "label": "計算區間",
    "type": "integer",
    "unit": "分鐘",
    "minimum": 1,
    "maximum": 30,
    "default": 2
  },
  "minimum_return_pct": {
    "label": "最低報酬率",
    "type": "decimal",
    "unit": "%",
    "minimum": "0.1",
    "maximum": "20.0",
    "default": "1.5"
  }
}
```

### 7.2 Server Validation

- 瀏覽器 validation 只提供操作回饋；後端必須使用相同 code-owned Schema 再驗證。
- 所有百分比在 API/DB 使用明確人類百分比或 ratio contract，禁止同時接受 `0.015` 與 `1.5` 而不標示單位。
- 時間使用 `HH:MM` 並綁定 `Asia/Taipei`。
- Decimal 以 canonical string 保存。
- 未知欄位、NaN/Infinity、越界值與不相容 capability 一律拒絕。

### 7.3 Lifecycle

Draft 與 immutable Version 必須分離：

```text
Mutable StrategyVersionDraft
  -> transactional publish
Immutable StrategyVersion + PUBLISHED event
  -> REVIEWED -> BACKTESTED -> PAPER_APPROVED -> ACTIVE
                                              -> PAUSED -> RETIRED
```

- Draft 可修改，但不是 Strategy Version，也不能被 run 引用。
- Published Version 不可直接更新 parameters、template/schema/implementation digest 或 status meaning；狀態由 append-only event projection 得出。
- Clone 建立下一個版本。
- Delete 僅允許未 publish 的 Draft；Version 永不刪除，只能 append RETIRED event。
- `/validate` 只回傳當下檢查結果；Publish 必須在同一 transaction 重新驗證並原子建立 Version 與 event，防止 Draft、Schema 或 Template 在兩次請求之間改變。

#### 7.3.1 合法 transition table

| From | Allowed To | 必要 evidence / guard |
|---|---|---|
| `NONE` | `PUBLISHED` | 只能由 Publish transaction 建立；`expected_sequence=0`、event `sequence=1`，包含 canonical config、schema/template/implementation digests |
| `PUBLISHED` | `REVIEWED`, `RETIRED` | REVIEWED 需要 review note/digest；RETIRED 需要 reason |
| `REVIEWED` | `BACKTESTED`, `RETIRED` | BACKTESTED 需要 exact backtest run IDs/snapshot digests |
| `BACKTESTED` | `PAPER_APPROVED`, `RETIRED` | PAPER_APPROVED 需要 qualification evidence IDs/digests |
| `PAPER_APPROVED` | `ACTIVE`, `RETIRED` | ACTIVE 需要 requested runtime binding、activation preflight digest、effective Hard Risk Policy digest |
| `ACTIVE` | `PAUSED` | 需要 pause reason；先停止建立新 TradeIntent，既有 position 依明確 ownership/exit policy 管理 |
| `PAUSED` | `ACTIVE`, `RETIRED` | 回 ACTIVE 必須重新執行 activation preflight；RETIRED 需要 reason |
| `RETIRED` | 無 | terminal；不可恢復、不可重新啟用，只能 clone 成新 Draft/Version |

禁止跳級、倒退或未列出的 transition。`PAUSED -> ACTIVE` 明確允許，但不是單純切換旗標，必須附上新的 preflight/effective-risk evidence。`ACTIVE -> RETIRED` 不可直接執行，必須先 PAUSED，避免 lifecycle event 與仍在執行的 run/position 失去一致性。

#### 7.3.2 Lifecycle event schema

`strategy_version_events` 至少保存：

- `event_id`：不可變 UUID。
- `strategy_version_id`。
- `sequence`：該 Version 從 1 開始、連續遞增。
- `event_type`：`PUBLISHED` 或 `STATUS_TRANSITION`。
- `from_status`、`to_status`；Publish 的 `from_status=null`。
- `evidence_json` 與 `evidence_digest`；內容依 transition table 驗證，不接受任意 executable payload。
- `reason`／`change_note`。
- `actor_id`、`actor_session_id`；v1 即使是 loopback-only 也必須有可稽核 local actor/session。
- `idempotency_key`、`request_digest`。
- `expected_sequence`。
- `occurred_at`、`recorded_at`、`event_digest`。

唯一約束至少包含 `(strategy_version_id, sequence)`、`event_id`，以及 `(strategy_version_id, idempotency_key)`。Event row append 後不可 update/delete；修正只能新增後續合法 event，RETIRED 仍維持 terminal。

#### 7.3.3 Compare-and-append concurrency

**PostgreSQL-only persistence boundary**

原子策略平台的 Template、Draft、Version、Publish Operation、Lifecycle Event/State/Outbox、Strategy Set/Pipeline、Run Snapshot index 與 evaluation retention records **全部只寫 PostgreSQL**。SQLite 不是支援 backend、不是 fallback，也不得承接任何新 atomic-platform mutation/run write。

- 啟動 atomic strategy management/backtest vertical slice 前，`BACKTEST_DATABASE_BACKEND` 必須是 `postgresql` 且 PostgreSQL migrations/preflight 通過；否則相關 mutation/run API fail closed，不得自動建立 SQLite 檔案。
- 現有 SQLite completed-run 資料若需要保留，只能由一次性、唯讀 migration/import 工具匯入 PostgreSQL；匯入後由 PostgreSQL 成為唯一 authority。新平台不得以 SQLite compatibility reader 執行新 run 或 lifecycle mutation。
- PostgreSQL 暫時不可用時回明確 unavailable/health failure；不得降級成本機 SQLite。

可在 transaction 前做 idempotency fast-path read，以減少重播延遲；但 fast path 只在找到相同 key 時提前回傳，查無資料不具權威性。每個 post-publish transition 的 authoritative 流程必須在單一 PostgreSQL transaction 內：

1. `BEGIN` 後以 `SELECT ... FOR UPDATE` 鎖定該 Version 的 `strategy_version_state` row，先取得 lifecycle stream 寫入權。
2. **取得鎖後重新查詢** `(strategy_version_id, idempotency_key)`。相同 key + 相同 `request_digest` 立即回傳原 event/result，不再檢查 caller 的舊 `expected_sequence`；相同 key + 不同 digest 回 `409 IDEMPOTENCY_CONFLICT`。
3. 若不是 replay，才驗證 request 的 `expected_sequence` 等於目前 sequence、`from_status` 等於 projection status；不符回 `409 LIFECYCLE_SEQUENCE_CONFLICT`，並回 current status/sequence。
4. 驗證 transition table、必要 evidence、runtime capability 與 actor 權限邊界。
5. 以 `(strategy_version_id, idempotency_key)` 及 `(strategy_version_id, sequence)` unique constraints 作最後防線，使用不會使 transaction abort 的 PostgreSQL conditional event insert，例如 `INSERT ... ON CONFLICT DO NOTHING`，嘗試寫入 `sequence=current+1`。若沒有 insert row，必須在同一 transaction 依 key 重讀：digest 相同回放原結果，digest 不同回 idempotency conflict，禁止落到 sequence conflict。
6. Event insert 成功後，更新 `strategy_version_state(status, last_sequence, last_event_id, projection_digest)`，並插入 lifecycle outbox row；event、projection、outbox 三者必須在**同一 transaction** commit。

Projection update 在 row lock 內執行，並保留 `last_sequence=expected_sequence` defensive predicate。Conditional insert conflict 後必須在鎖內按 idempotency key 重讀；不得讓 unique violation 使 transaction 留在 aborted state，也不得依賴 application process mutex。

#### 7.3.4 First Publish idempotency identity/result

首次 Publish 尚無 `strategy_version_id`，因此 idempotency scope 固定為 **`(draft_id, idempotency_key)`**，不得套用 post-publish 的 Version scope。

新增 `strategy_publish_operations`：

- `publish_operation_id`
- `draft_id`
- `idempotency_key`
- `request_digest`
- `expected_draft_revision`
- `strategy_version_id`
- `published_event_id`
- `result_digest`
- `committed_at`

Unique constraints：`(draft_id, idempotency_key)` 唯一；每個 `draft_id` 最多只能有一筆 committed publish result。`strategy_version_drafts` 另保存 `revision`、`published_strategy_version_id`、`published_event_id`、`published_operation_id`、`published_at`；Publish 成功後 Draft 不可再修改。

`request_digest` 必須包含 API contract version、`draft_id`、caller 提供的 `expected_draft_revision`、publish request body/actor intent digest。Transaction 內仍要依鎖定後的 Draft 內容重新 canonicalize/validate；request digest 不能取代 Publish revalidation。

Publish authoritative transaction：

1. PostgreSQL `BEGIN`，`SELECT strategy_version_drafts ... FOR UPDATE` 鎖定 Draft。需要分配同一 `strategy_id` 的下一個 version number 時，同 transaction 再鎖定 code-owned Template/version allocator row。
2. 鎖內查詢 `(draft_id, idempotency_key)`：相同 key + 相同 request digest 回放原 `strategy_version_id/published_event_id/result_digest`；相同 key + 不同 digest 回 `409 IDEMPOTENCY_CONFLICT`。
3. 若 Draft 已有 `published_strategy_version_id`，但沒有相同 publish operation/key，回 `409 DRAFT_ALREADY_PUBLISHED`，並回原 Version/Event IDs；即使新 key 的 request digest 相同也不得建立第二個 Version。
4. 驗證 `expected_draft_revision`、current Draft revision、code-owned Schema/Template/binding/capability及 canonical parameters。Revision 不符回 `409 DRAFT_REVISION_CONFLICT`。
5. 在同一 transaction 原子建立 immutable Strategy Version、sequence 1 `PUBLISHED` event、state projection、lifecycle outbox、`strategy_publish_operations` result mapping，並更新 Draft 的 published references。
6. Commit 後才回 response。若 commit 成功但 response 遺失，同一 key/digest retry 必須透過 Draft-scoped operation mapping 回放同一 Version/Event；rollback 則不得留下任何 partial Version、event、outbox、operation或 published reference。

Concurrent Publish disposition：

| Concurrent requests | 結果 |
|---|---|
| 同 Draft、同 key、同 digest | 一筆成功；其他等待 Draft lock 後 replay 同一 Version/Event |
| 同 Draft、同 key、不同 digest | 一筆依先取得 lock 的 request 決定；另一筆 `409 IDEMPOTENCY_CONFLICT` |
| 同 Draft、不同 key | 只允許第一筆建立 Version；其餘等待 lock 後回 `409 DRAFT_ALREADY_PUBLISHED` |
| 不同 Draft、同 strategy | 各自可 publish；version allocator lock 確保 `(strategy_id, version)` 唯一且單調 |

Post-publish transition 才改用 `(strategy_version_id, idempotency_key)` scope；Publish operation key 不得跨 scope 重用來推斷 lifecycle transition。

#### 7.3.5 Transactional outbox

- `strategy_lifecycle_outbox` row 必須與 lifecycle event、`strategy_version_state` projection 在同一 DB transaction 插入；首次 Publish 也遵守相同規則。
- outbox row 至少保存 `outbox_id`、`event_id`、`event_digest`、`topic`、canonical payload/payload digest、`created_at`、delivery status/attempt。`(event_id, topic)` 必須 unique。
- transaction commit 前禁止直接發布 notification。Dispatcher 只讀已 commit 的 pending outbox rows，以 at-least-once 方式傳送；consumer 以 `event_id/event_digest` idempotent。
- crash 發生在 commit 前時 event/projection/outbox 一起回滾；發生在 commit 後、publish 前時 pending outbox 仍可重送，因此不能永久漏通知。
- delivery ack/attempt 可在後續獨立 transaction 更新，但不得修改 lifecycle event 或 original outbox payload。超過重試門檻進 dead-letter/alert，不可刪除證據。

#### 7.3.6 Projection rebuild 與衝突處理

- `strategy_version_events` 是 lifecycle source of truth；`strategy_version_state` 是可刪除重建的 projection，不進入 immutable Version configuration digest。
- rebuild 依 `sequence` 排序，要求從 1 開始連續、`from_status` 與前一個 `to_status` 相符、event/request/evidence digests 有效且每個 transition 合法。
- 同 event/idempotency duplicate 只在 payload digest 完全相同時視為同一事件；digest 不同即資料衝突，禁止自動選一筆。
- sequence gap、非法 transition、digest mismatch 或分叉時，Version projection 進入 `PROJECTION_ERROR`／quarantine，activation 與新 transition fail closed，等待人工修復；不得猜測最新狀態。
- rebuild 完成的 `status/last_sequence/last_event_id/projection_digest` 必須與線上 projection 一致，並提供 deterministic rebuild test。

## 8. Signal Lifecycle Contract

每個 Atomic Strategy 必須明確定義：

- `trigger_semantics`：STATE、CROSS_UP、CROSS_DOWN、EDGE、ONCE_PER_SESSION。
- `evaluation_cadence`：Tick、BidAsk、1m completed Kbar、5m completed Kbar、daily close。
- `confirmation_observations`。
- `signal_ttl_seconds`。
- `cooldown_seconds`。
- `max_triggers_per_symbol_session`。
- `entry_window_start/end`。
- `session_reset_policy`。
- `insufficient_data_behavior`：fail closed。

每次 evaluation 都要在記憶體內回傳：

- `TRIGGERED / NOT_TRIGGERED / INSUFFICIENT_DATA / BLOCKED`。
- observed values。
- threshold/config values。
- input feature versions/digests。
- source/as-of/received timestamps。
- deterministic evaluation digest。

### 8.1 Evaluation retention tiers

「每次都回傳」不等於「每次都寫一筆 DB row」。預設持久化採分級政策：

1. **完整保存**：TradeIntent、TRIGGERED decision、order、fill、position transition、rejection，以及與成交／拒絕相關的 evaluation evidence。
2. **受限保存**：`BLOCKED/INSUFFICIENT_DATA` 保存完整聚合計數、reason breakdown，並依 run/symbol/session/reason 保存有上限的 representative samples。
3. **只聚合**：`NOT_TRIGGERED` 只保存按 strategy version、symbol、session、reason 的 counters/histograms，不為每次 evaluation 建 row。
4. **DEBUG trace**：只有明確開啟的有界 debug run 才保存全量 evaluation trace；必須指定 symbol/date/event bounds、quota、壓縮 partition artifact、到期日與清理政策，且不得成為預設 DB rows。

Run metrics 仍要能計算每個原子策略的 evaluated/triggered/blocked/insufficient、primary attribution 與邊際貢獻；不能以「為了分析」為由無上限保存所有未觸發 evaluation。

## 9. Strategy Set Composition

v1 支援：

- `ANY`
- `ALL`
- `AT_LEAST_N`

`WEIGHTED` 延後至有獨立回測證據及分數正規化 contract 後再加入，避免不同策略輸出尺度不可比較。

組合必須另外定義：

- exact member version IDs。
- evaluation order；需要 per-member attribution 時預設不可 short-circuit。未來只有在不破壞 observability contract 時才能最佳化。
- primary attribution priority。
- blocked/insufficient member 的固定 v1 semantics。
- 同一 event 多個策略觸發只能建立一個 TradeIntent。
- BUY/SELL 同時觸發時，既有持倉的安全 EXIT 優先；新 ENTRY 不可覆蓋 pending EXIT。

v1 composition semantics：

- `ALL`：任一 member 為 BLOCKED/INSUFFICIENT_DATA 時不產生決策，結果保留對應 unavailable 狀態；只有全部 TRIGGERED 才觸發。
- `ANY`：至少一個 TRIGGERED 即觸發，同時保留 blocked/insufficient member counts 與 attribution；若無觸發，依 unavailable members 區分 NOT_TRIGGERED 與無法完整判定。
- `AT_LEAST_N`：TRIGGERED 數達 N 才觸發；若即使所有 unavailable members 都觸發仍不可能達 N，結果為 NOT_TRIGGERED；若仍可能達 N 但缺少資料，結果標記為 unavailable/insufficient，不假裝未觸發。
- Risk Policy 不得作為 member，也不參與上述任何 operator。
- EXIT safety precedence 高於 ENTRY；pending EXIT 不被新 ENTRY 覆蓋。

即使組合未觸發，也透過 per-member aggregate counters 與 bounded samples 分析單獨命中率及邊際貢獻，不預設保存每個 evaluation row。

## 10. Execution、Position 與 Risk

### 10.1 Execution Policy

Strategy 不直接決定 broker order payload。固定 command boundary：

```text
TradeIntent
  -> Execution Policy
  -> ProposedOrderCommand (不可送出)
  -> Hard Risk Admission
  -> ApprovedOrderCommand
  -> Simulation/Broker Adapter
```

`ProposedOrderCommand` 已包含 normalized symbol、side/position action、quantity shares、limit price、order type、TTL/TIF、origin、owner、requested_at、idempotency key 與 command digest，但型別／狀態上禁止被任何 adapter 接受。`ApprovedOrderCommand` 額外包含 risk decision ID、effective policy digest、RiskSnapshot digest、approved_at 與原 proposed command digest；只有它能進入 adapter。

v1 只綁定 Local Paper Simulation Adapter；Broker Adapter 只是未來 port 名稱，本計畫不新增、不啟用任何真實券商 transport。Admission 為 BLOCKED/REJECTED 時不得建立 ApprovedOrderCommand。

現有 `RiskGate.evaluate(OrderCommand, RiskSnapshot)` 的 `OrderCommand` 在 migration 期間視為 proposed input。新 boundary 不得因沿用舊名稱而讓未 admission 的 command 直接進入 `SimulationService`。Risk admission v1 只 approve/reject/block，不修改 command；任何縮量、改價或換 order type 都要回到 Execution Policy 產生新 proposed identity 並重新 admission。

Execution Policy 至少包含：

- position sizing。
- LIMIT price policy。
- order TTL/time-in-force。
- cancel/replace 與是否追價。
- partial-fill policy。
- tick-size/price-limit normalization。
- board-lot/odd-lot policy。
- fees, sell tax, slippage model。

### 10.2 Position Ownership

每個 position lot 保存：

- `entry_run_id`
- `entry_strategy_set_version_id`
- `entry_decision_id`
- `entry_intent_id`
- `owner_policy`

v1 建議：

- 同一 runtime 只允許一個策略組合擁有同一 symbol。
- 自動策略不可處理未標記為自己所有的手動持倉。
- Exit Set 必須綁定 Entry Set 或 position owner。
- 多策略共同觸發只歸屬一次，不重複建立部位。

### 10.3 Risk

Risk 是安全邊界，不是可自由組合、回測擇優或由策略參數放寬的原子策略。

- Pipeline 固定分離 Filter Set、Entry Set、Exit Set、Execution Policy、Hard Risk Policy。
- Hard Risk Policy 在 Execution Policy 產生完整 ProposedOrderCommand 後、任何 adapter 接收前永遠執行；exit/flatten 也必須 admission，但使用下方固定的 risk-reducing bypass matrix。
- Web/DB 只能從 allowlisted policy 選擇，或將限制設定得比 system ceiling 更嚴格；不能放寬 stale-data、daily-loss、position、notional、pending reservation、stream degradation 與 global emergency stop 等硬限制。
- Hard Risk Policy 的 system ceilings、implementation identity 與有效設定必須進入 Run Snapshot/audit，但不得基於回測績效自動 promotion。
- 任何未知 policy、缺設定、stale data、degraded stream 或 risk journal failure 一律 fail closed。

最低硬限制包括單筆 notional、單策略／Strategy Set 資金上限、symbol/sector/market exposure、最大持倉、每日／連續虧損暫停、pending-order reservation、stale/degraded-data gate 與 global emergency stop。

#### 10.3.1 Effective Hard Risk Policy monotonic merge

Policy 分成三層，且合併必須 deterministic：

```text
Code-owned System Hard Ceiling
  + allowlisted deployment policy
  + optional Web/DB stricter override
  -> EffectiveHardRiskPolicy + policy_digest
```

Web/DB 不能新增未知欄位、未知 policy ID 或改變型別。缺少 override 時沿用上一層；任一欄位無法證明不比 system policy 寬鬆即拒絕 publish/activation，不能 fallback 成寬鬆預設。

| 欄位類型 | 例子 | Effective merge | Web/DB 允許方向 |
|---|---|---|---|
| 上限型數值 | `max_order_notional`, `max_position_notional`, `max_strategy_notional`, `max_daily_loss`, `max_open_positions`, `max_pending_notional`, `max_book_age_seconds` | `min(system, deployment, override)` | 只能變小；`max_book_age_seconds` 越小越嚴格 |
| 下限型安全值 | `min_cash_reserve`, `min_required_book_depth` | `max(system, deployment, override)` | 只能變大 |
| allowlist／allowed universe | `allowed_entry_symbols`, `allowed_entry_origins`, `allowed_order_policies` | 集合交集 | 只能移除，不能新增 system 未允許項目 |
| blocklist | `blocked_symbols`, `blocked_strategy_versions`, `global_command_blocked_symbols` | 集合聯集 | 只能新增封鎖；各欄位的 exit bypass 不同，依下一節 matrix |
| require boolean | `require_fresh_book`, `require_market_open`, `entry_emergency_stop` | boolean OR | 只能 `false -> true` |
| allow boolean | `allow_strategy_origin`, `allow_new_entries`, `allow_odd_lot` | boolean AND | 只能 `true -> false` |
| 全域 transport kill | `global_transport_kill_switch` | boolean OR | 只能 `false -> true`，且 entry/exit 都不可略過 |

每一層的 canonical JSON、digest、merge algorithm version 與最後 `effective_policy_digest` 都進入 activation/run snapshot。若 override 與 system ceiling 相比更寬鬆，API 回 `422 RISK_POLICY_NOT_MONOTONIC` 並列出欄位，不得默默截斷後假裝接受。

#### 10.3.2 Entry 與 risk-reducing Exit/Flatten matrix

先依 position ownership 與 proposed command 判斷 action：

- `ENTRY_OR_INCREASE`：會增加絕對曝險。
- `RISK_REDUCING_EXIT`：只減少既有、屬於該 owner 的曝險，且 quantity 不超過 `current_position - pending_exit`。

無法證明是 risk-reducing 時一律按 `ENTRY_OR_INCREASE` 處理。v1 long-only 不接受反手單；SELL 超過可售持倉直接 reject，不把超額部分視為 short entry。

| Hard Risk check | Entry/Increase | Risk-reducing Exit/Flatten | 理由 |
|---|---|---|---|
| command schema、正數 quantity/price、tick/lot/price-limit normalization | 必須通過 | 必須通過 | 無效 command 永不送 adapter |
| position ownership、可售數量、pending duplicate、idempotency | 必須通過 | 必須通過 | 防止賣超、重複 exit 與跨 owner 操作 |
| instrument identity/tradable、adapter/session 可接受委託 | 必須通過 | 必須通過 | adapter 不可執行的委託不能假裝 flatten |
| journal/outbox durability、reconciliation state | 必須健康 | 必須健康 | 無法稽核時 fail closed |
| data health、required fresh book、book age | 必須通過 | 必須通過 | v1 限價由市場資料導出；stale/unavailable 不猜價 |
| `global_transport_kill_switch` | 阻擋 | 阻擋 | 表示所有 command transport 停止 |
| `entry_emergency_stop`, `allow_new_entries`, `allow_strategy_origin` | 套用 | 可略過 | 只禁止新增策略曝險，不應困住既有持倉 |
| daily/連續虧損、max order/position/strategy notional、max positions、cash reserve | 套用 | 可略過 | 這些限制阻止增加曝險；exit 本身降低曝險 |
| `max_pending_notional` | 套用 | 可略過，但仍需通過可售數量與 same-side pending duplicate | 不因 pending-notional ceiling 困住降風險 exit，也不允許重複掛賣 |
| entry allowed universe／entry policy allowlist | 套用 | 可略過，但 symbol 必須是該 owner 的既有持倉 | universe 移除後仍允許平掉已持有部位 |
| `blocked_symbols` | 阻擋 | 可略過，但只限該 owner 的既有持倉且 instrument 仍 tradable | 此欄位定義為策略 entry blocklist；真正全面禁送使用下一列 |
| `blocked_strategy_versions` | 阻擋該版本的新 entry | 可略過，但 exit 必須關聯到由該版本／其 Strategy Set 擁有的 position | 停用有問題的 entry 邏輯時仍要允許安全退場 |
| `global_command_blocked_symbols` | 阻擋 | 阻擋 | 法規、商品停牌或 transport 級全面禁止，任何策略不得 bypass |
| `allow_odd_lot=false` | 阻擋 odd-lot entry／任意 partial exit | 僅可略過以一次關閉該 owner 的 residual odd-lot，且 adapter/runtime 必須明確支援 odd-lot exit | 避免殘股永久無法平倉；不得把例外用於建立或任意切割部位 |

**Fail-closed catch-all：任何未在本 matrix 明確列為「可略過」的 Hard Risk check，對 risk-reducing exit 一律不可 bypass。** 新增 RiskPolicy 欄位時必須同時更新 monotonic merge、此 matrix、RiskDecision evidence 與 entry/exit tests，否則 Schema/activation preflight 拒絕該 policy version。

任何 bypass 都必須在 RiskDecision 中記錄 `action_class=RISK_REDUCING_EXIT`、被略過的 checks、position owner、可售數量與 evidence digest；不是省略執行 Hard Risk Admission。

## 11. Data、Backtest 與 Live/Paper Parity

- 每個策略宣告 required capabilities，API 與 worker/runtime 都 preflight。
- Backtest 使用 completed/as-of data；不可讀未完成 Kbar 或未來值。
- Tick/BidAsk 策略不得宣稱與 Kbar 回測具有完全 parity；需要明確 adapter 或 replay dataset。
- Template 必須明確列出每個 mode/cadence 的 allowlisted runtime binding，例如 `BACKTEST_KBAR_1M`、`BACKTEST_DAILY`、`REPLAY_TICK_BIDASK`、`LOCAL_PAPER_TICK_BIDASK`。
- activation/preflight 依 requested mode 驗證 exact binding、template/implementation digest、Feature Requests 與資料 capability；只有 `supported_runtime_modes` 布林清單不足以授權執行。
- 相同策略版本可在相容模式使用相同純 evaluation kernel，但資料 adapter、clock 與 execution model 獨立；不相容時必須 unavailable 或保存不同 adapter identity。
- Parity 只在 Feature Specification、as-of、cadence 與 decision boundary 都可比較時宣稱；其他情況明確記錄 non-parity。
- Dataset、Feature、Strategy、Set、Engine、Cost 均需 digest。
- 相同 snapshot 重跑結果與 decision digest 必須一致。

## 12. Research 與比較治理

為避免大量參數組合只挑出歷史巧合：

- 固定 train/validation/OOS split。
- 支援 walk-forward。
- 記錄嘗試過的所有 Strategy Version，不只保存最佳結果。
- 比較時固定 universe、data、entry/exit assumptions、capital、costs。
- 設 minimum OOS trades、max drawdown、net-of-cost、stability gate。
- 參數搜尋與正式 promotion 分開；v1 不自動將最佳結果設為 ACTIVE。
- 保存 baseline/challenger 關係與 change note。

## 13. Web Strategy Management

擴充現有「策略目錄」為「策略管理」，包含：

1. Strategy Templates：依 role/session phase/status 搜尋。
2. Parameter Editor：由 Schema 產生表單，顯示單位、限制與資料需求。
3. Version History：clone、diff、change note、digest、生命週期。
4. Strategy Set Builder：選擇 exact versions 與 ANY/ALL/AT_LEAST_N。
5. Backtest Launcher：選 dataset、cost、execution、pipeline snapshot。
6. Qualification：baseline/challenger 與 OOS evidence。
7. Paper Activation：只允許 PAPER_APPROVED，顯示風控、資料健康、run 狀態與 stop control。
8. Audit：顯示建立者、發布者、時間、參數及被哪些 runs 引用。

禁止提供任意 Python、SQL、import path 或未受 Schema 管理的 JSON editor。

v1 Web mutation boundary：

- Template 建立／runtime binding 變更屬於 code deployment，不是 Web mutation。Web 只能針對已部署、allowlisted Template 建立參數 Draft。
- 現有 Dashboard mutation API 尚無 authentication；v1 必須維持 `127.0.0.1` loopback-only、single-user 模式，啟動時拒絕／禁止非 loopback bind，並以 origin/CSRF 防護限制瀏覽器 mutation。
- 若未來要對區網或外網開放，必須先另案完成 authentication、authorization/RBAC、CSRF/origin protection、session/audit，再解除 loopback 限制。
- Publish、activation、pause/stop、kill switch 都是敏感 mutation；在無 auth 的 v1 不得宣稱 Viewer/Researcher/Reviewer/Operator 已被系統強制執行。

## 14. API Contract

建議新增／演進：

```text
GET  /api/strategy-templates
GET  /api/strategy-templates/{strategy_id}
GET  /api/strategy-templates/{strategy_id}/parameter-schema
POST /api/strategy-versions/drafts
PUT  /api/strategy-versions/drafts/{draft_id}
POST /api/strategy-versions/drafts/{draft_id}/validate
POST /api/strategy-versions/drafts/{draft_id}/publish
GET  /api/strategy-versions/{strategy_version_id}
POST /api/strategy-versions/{strategy_version_id}/clone
GET  /api/strategy-versions/{left}/diff/{right}
GET  /api/strategy-versions/{strategy_version_id}/lifecycle
GET  /api/strategy-versions/{strategy_version_id}/lifecycle-events
POST /api/strategy-versions/{strategy_version_id}/lifecycle-transitions
POST /api/strategy-sets
GET  /api/strategy-sets/{strategy_set_version_id}
POST /api/strategy-pipelines
POST /api/backtests/runs
POST /api/simulation/automated-strategy/start
GET  /api/strategy-runs/{run_id}/decisions
```

每個 mutation 接受 idempotency key，並寫入 audit event。

Mutation contract：

- Draft create/update、Publish、Strategy Set create、backtest start 與 local-paper activation 都必須具備明確 idempotency scope、transaction boundary 與 conflict response。
- `POST .../drafts/{draft_id}/publish` 必須包含 `expected_draft_revision` 與 `Idempotency-Key`；scope 是 `(draft_id, key)`，結果由 `strategy_publish_operations` 保存。相同 key/digest replay、不同 digest 回 `409 IDEMPOTENCY_CONFLICT`，已 Publish Draft 的其他 key 回 `409 DRAFT_ALREADY_PUBLISHED`。
- `/validate` 不授權 `/publish`。Publish transaction 內必須依目前 code-owned Template/Schema 重新 canonicalize/validate，驗證 template/implementation digest、runtime bindings/capabilities，並依 Section 7.3.4 原子寫入 immutable Version、Publish event/state/outbox、operation result與 Draft published references。
- post-publish lifecycle transition request 必須包含 `to_status`、`expected_sequence`、`evidence`、`reason`，並使用 `Idempotency-Key`；server 從 projection 取得 `from_status`，以 Section 7.3 PostgreSQL compare-and-append transaction 驗證。鎖內相同 idempotency key/digest replay 優先於 stale sequence conflict；真正 sequence mismatch 才回目前 status/sequence 的 `409`。
- `POST /api/strategy-sets` 的 members 只接受 exact `strategy_version_id` 與預期 digest；拒絕 ambiguous raw strategy ID。
- API 不接受 execution binding、import path 或 executable JSON。這些值只能來自部署中的 allowlisted Template Registry。

## 15. Persistence Migration

現有 PostgreSQL `strategy_definitions` 已是 `(strategy_id, version)` immutable row，可作相容基礎，但目前混合 Template metadata、參數值與 code definition。v1 atomic platform 的下列 migration 只建立於 PostgreSQL。

建議 migration：

1. 新增 `strategy_templates` 保存 code-owned Schema、binding、capabilities 與 implementation digest。
2. 新增獨立、可修改的 `strategy_version_drafts`，包含 revision 與 published result references；Draft 不可被 run/member 引用。
3. 將 `strategy_definitions` 明確升級／映射為 immutable `strategy_versions`；保留舊表或提供相容 view，避免破壞 completed runs。
4. 新增 `strategy_publish_operations`，保存 Draft-scoped idempotency request/result mapping；與 Version/Publish event/state/outbox/Draft references 同 transaction。
5. 新增 append-only `strategy_version_events`、可重建的 `strategy_version_state` projection 與 `strategy_lifecycle_outbox`；event + projection + outbox 必須同 transaction 寫入。Events 具 per-version sequence/idempotency unique constraints，projection 只在 PostgreSQL row-lock compare-and-append transaction 內更新，status 不回寫 immutable Version row/digest。
6. 新增 `strategy_sets` 與 `strategy_set_members`；member FK 指向 exact strategy version，並保存 member/version/implementation digests、order、priority。
7. 新增 `strategy_pipelines` 與 Filter/Entry/Exit、Execution Policy、Hard Risk Policy stage bindings；Risk 不是 member。
8. PostgreSQL `backtest_runs.config_json` 繼續保存完整 snapshot，另可加 run-to-version index table 供查詢，不能用 join 重建歷史 snapshot。
9. evaluation storage 分為 full-detail events、bounded unavailable samples、NOT_TRIGGERED aggregates 與有到期日的 DEBUG artifacts，禁止無上限逐筆保存。
10. 本機模擬增加 durable run/checkpoint contract 前，重啟不得宣稱可自動恢復。
11. 不建立任何 atomic-platform SQLite tables。既有 SQLite completed-run 檔案若要保留，只能一次性唯讀匯入 PostgreSQL並核對 count/digest；新寫入、replay authority 與查詢 authority 全部是 PostgreSQL。

舊的 aggregate Momentum definitions：

- 不刪除、不改 digest。
- 標記為 legacy/deprecated 必須透過新 lifecycle event，不重寫舊 definition meaning。
- 舊 completed runs 繼續使用舊 engine/binding 重現。
- Legacy `StrategySetSnapshot` 由 compatibility adapter 依其原始 raw IDs 與舊 Registry 規則讀取；不把舊 snapshot 轉存成新 exact-version 格式，不改 config/digest。
- 新 Atomic Strategy Runs 不再選用 aggregate bindings。

## 16. Runtime 與可靠性

- 啟動時 resolve exact versions -> resolve parameterized Feature Requests -> validate exact runtime binding/digests -> validate data capabilities -> warm features -> build run snapshot -> start。
- Worker 不可依賴瀏覽器保持開啟。
- 每個 run 有 heartbeat、last evaluated event、last decision、last error、blocked reason。
- Web process restart 與 strategy worker restart 分開治理；不可因頁面重整建立第二個 worker。
- 保存 per-strategy/per-symbol state checkpoint，包含 cooldown、last trigger、position owner 與 pending intent。
- 恢復前 reconciliation orders/positions/journal；不確定時停在 `RECOVERY_REQUIRED`。
- 行情中斷、queue overflow、stale BidAsk、calendar 不確定、Journal failure 一律停止產生新意圖。
- 首次 Entry 不得依賴「已有持倉／active order」才建立行情訂閱。觸發後先以 exact owner 建立最多一檔的 pre-order quote watch，納入既有 `SimulationService` 訂閱 reconciliation；只有 canonical BidAsk cache 已訂閱、完整且 fresh 才可建立 TradeIntent。watch 不建立委託、不繞過 Hard Risk，送單後或 stop／kill 時釋放，active order／position 仍由原訂閱 owner 接手。
- restart 必須先以純函式預覽 Effective Hard Risk evidence，使用其 digest 完成 ownership/checkpoint validation；只有 validation 成功後才允許寫 activation operation 並安裝 policy。失敗啟動不得改寫既有已安裝 policy。
- 提供 per-run stop 與 global kill switch；停止策略不自動清除既有持倉，除非有明確 flatten policy。
- Runtime 是事件迴圈／position lifecycle state machine：每個行情事件更新 Feature Snapshot，依當前 run/position/order state 評估 Filter/Entry/Exit，成交後持續監控直到 terminal；restart 只能經 checkpoint + journal + open order/position reconciliation 回到 RUNNING。
- 所有 entry/exit command 固定走 `TradeIntent -> Execution Policy -> ProposedOrderCommand -> Hard Risk Admission -> ApprovedOrderCommand -> Adapter`；adapter 的公開 port 不接受 proposed type。現有 `OrderCommand` migration adapter 也必須在型別／狀態上證明已 admission。

## 17. Permissions 與 Audit

角色模型僅為未來 multi-user 設計，v1 loopback-only single-user 模式不宣稱已落實 RBAC：

- Viewer：讀取 templates/versions/runs。
- Researcher：建立 DRAFT、回測。
- Reviewer：發布 BACKTESTED/PAPER_APPROVED。
- Operator：啟停本機模擬。

只有在 authentication/authorization enforcement 與對應測試完成後，這些角色才可成為產品權限。此前安全邊界是 loopback-only bind、origin/CSRF protection、idempotent mutation、append-only audit 與 no-real-order。

Audit 至少保存：

- actor、time、action。
- before/after digest。
- change note。
- source IP/session（若未來多使用者）。
- backtest/paper run references。

## 18. Implementation Phases and Gates

### Phase 0 — Review Contract Freeze（已完成）

- B1–B5 已由 Review 標記 `REVIEWED / CLOSED`。
- B3 的 Draft-scoped Publish operation/result mapping、Draft row lock、原結果回放、衝突矩陣、Draft sealing 及同一 PostgreSQL transaction 已通過 Review。
- 凍結 exact-version member、runtime-mode binding、ENTRY/EXIT role、composition unavailable semantics、loopback-only mutation boundary與 legacy compatibility。
- Section 22 package ownership 已凍結；建立舊 catalog/backtest golden snapshots。

Gate G0：**PASSED / GO**。使用者已明確授權開始 Phase 1 實作。

### Phase 1 — 最小 Backtest Vertical Slice（Remediation 中）

只實作足以驗證架構的垂直切片：

- 一至兩個共用 Feature Specifications 及 completed 1m Kbar adapter。
- `above_vwap_entry` 與 `breakout_previous_high_entry`，每個已實作策略一檔。
- Strategy Template、mutable Draft、transactional immutable Publish、append-only event。
- exact-version Strategy Set，v1 僅 ANY/ALL/AT_LEAST_N。
- backtest resolve、Run Snapshot、聚合 attribution 與 bounded evidence retention。
- legacy completed-run compatibility adapter。

Gate G1：**PASSED / GO**。`atomic-backtest-run-snapshot-v2` 已保存 resolved Feature Specification digest、feature implementation digest 與明確 as-of semantics；Publish retry 先走不依賴目前 Registry（包含空 Registry）的 durable PostgreSQL replay；wall-clock fixture、Strategy Set snapshot integrity read validation、全 migration table/constraint/index acceptance，以及 destructive PostgreSQL test cleanup guard 均已補齊。最終驗收為 disposable PostgreSQL 全套 `1113 passed`，以及未設定 DSN 的一般模式 `1103 passed, 10 skipped`；Python compilation 與 whitespace check 通過。最終短 Review另重跑 focused `33 passed, 5 skipped`、一般模式 `1103 passed, 10 skipped`，並確認無剩餘 blocking 或 important finding。

### Phase 2 — Backtest Web Management（完成）

- Schema-driven 繁體中文 Draft 表單、validation、transactional publish、clone/diff。
- exact-version Strategy Set builder 與 Backtest Launcher。
- 維持 loopback-only single-user bind；mutation origin/CSRF、idempotency、audit 測試。

Gate G2：無任意 code/import path/JSON execution；API 不接受 raw strategy ID；browser/API/Publish transaction validation 一致。

目前狀態：**G2 PASSED / GO**。2026-08-22 最終 Review 確認沒有剩餘 blocking 或 important finding，並獨立驗證最後三個 blocker tests `3 passed`、無 DSN full `1114 passed, 15 skipped`、disposable PostgreSQL 17 full `1129 passed`，Python compilation、Dashboard JavaScript syntax 與 `git diff --check` 通過。ASGI HTTP 邊界、完整 Origin 比對及固定測試時鐘均通過 Review；使用者已明確授權開始 Phase 3。Local Paper、模擬交易、Shioaji／券商委託與 real-money execution 仍不在本次範圍。

### Phase 3 — Backtest Qualification（完成；MVP Conditional Go）

- OOS/walk-forward、baseline/challenger、server-owned multiple-testing family ledger、promotion evidence。
- Client 只提交研究假設與固定日期窗；policy、alpha、planned attempts、attempt sequence/history 均由伺服器決定。
- Compare 與 Qualification 共用一份 comparability contract；Run config/result、DatasetManifest、Atomic Snapshot 與 Feature adapter identity 全部 fail closed。
- 每個 Walk-forward fold OOS 必須早於 Primary OOS；final OOS evidence 不得被 fold 重複使用。
- Family 使用 server-derived research-baseline identity，不使用 Baseline Run ID 當 budget identity；等價 Baseline rerun 必須共用同一 family/head/attempt budget。
- 統一 Run identity verifier 同時核對 config digest 及 Run row/config 的 Dataset ID/digest；Baseline、Challenger 與所有 family attempts 一律套用。
- Qualification 保存 immutable canonical family snapshot body 與 digest；detail projection 另外顯示目前 family linkage，不改寫歷史 evidence。
- Run Snapshot 保留 parameterized Feature Request/runtime identity；真正的 rolling Feature runtime state/cache owner 延後到該策略在 Phase 5 實作時再接入，不列為 G3 已完成能力。
- Backtest slice 已完成第二次 implementation Review；核准結果不自動啟用 local paper。

Gate G3：**PASSED / MVP CONDITIONAL GO**。使用者已於 2026-08-22 以「開始process」另行明確授權 Phase 4；此授權只涵蓋 Local Paper Runtime，不包含券商委託或 real-money execution。

G3 最終 disposition：**PASSED / MVP CONDITIONAL GO**。G3 核准範圍只適用於單機、loopback、single-user、可信操作者與 trusted PostgreSQL 的人工審核 MVP。Qualification 必須維持 `REVIEW_ONLY_NO_LIFECYCLE_MUTATION`：任何 `ELIGIBLE_FOR_PROMOTION_REVIEW` 只代表可交付人工 Review，不得自動 promotion 或切換 Strategy lifecycle。Phase 4 的 Local Paper 啟動必須是另一個明確、人工、loopback-only 動作，不得由 Qualification 自動觸發。現有 G3 驗證證據為 focused no-DSN `31 passed, 10 skipped`、focused PostgreSQL `8 passed`、full no-DSN `1157 passed, 20 skipped`、full disposable PostgreSQL 17 `1177 passed`；Python compilation、Dashboard JavaScript syntax、browser smoke 與 `git diff --check` 通過。後續 Gate 狀態以各 Phase 小節為準。

MVP Conditional Gate 附帶下列凍結與人工治理條件：

- 凍結目前 qualification policy 與 experiment-family contract；任何 policy/family identity 升版前，必須先設計並驗證既有 `baseline_run_id` uniqueness 的資料遷移／相容處理，不得直接套用新 contract。
- 人工 Review 必須把相同 `bars_sha256` 且研究契約相同的 Dataset 視為同一份研究資料；不得透過重新封存、alias 或更換 Dataset ID 取得新的 family／attempt budget。
- Dataset stable research identity 與 canonical Baseline revalidation 登記為 Phase 3 hardening backlog。兩者在本機可信 MVP 可視為 defense-in-depth，但在 multi-user、非 loopback／外網、auto-promotion 或任何正式交易能力開始前，必須完成、補對抗性測試並重新過 Gate。
- PostgreSQL 被視為 trusted local authority；本 Gate 不涵蓋具備資料庫直接寫入權限的惡意操作者或資料庫被竄改後仍可安全運作的保證。

### Phase 4 — Local Paper Runtime（完成；MVP Conditional Go）

- 將 `continuous_strategy.py` 收斂為 generic paper orchestrator，而不是建立另一套策略／Feature source of truth。
- 使用 selected exact-version Pipeline、Execution Policy、Hard Risk Policy、Journal 與 SimulationService。
- 加入 ownership、checkpoint/recovery、持續 position/exit monitor 與 kill switch。
- generic paper runner 預設 STOPPED、只允許手動 start；Shioaji 維持 market-data-only。

Gate G4：完成 event loop：Feature -> Entry/Exit Intent -> Execution Policy -> ProposedOrderCommand -> Hard Risk -> ApprovedOrderCommand -> BidAsk Fill -> Position/terminal；restart fail closed；完全沒有券商委託 API。

目前狀態：**G4 PASSED / MVP CONDITIONAL GO；PHASE 5 已由使用者另行明確授權**。獨立 Review 確認首次 exact-set `WAITING_BOOK`、每 owner 一檔 quote watch、watch/order/position 訂閱合併、fresh BidAsk 後重新通過 Hard Risk、watch release、subscription concurrency，以及 preview -> checkpoint validation -> activation commit/install 均符合契約；remediation focused tests 為 `70 passed`，`git diff --check` 通過。候選方完整證據仍為 focused Local Paper `112 passed`、無 DSN full `1180 passed, 21 skipped`、disposable PostgreSQL 17 full `1201 passed`。Stop／kill-switch durable actor/idempotency audit保留為單機 MVP hardening backlog，必須在 multi-user、外網、auto-promotion 或 real-money 前補齊並重新過 Gate。Phase 5 的授權只涵蓋逐批原子策略擴充；broker／real-money 工作仍禁止。

### Phase 5 — 逐批擴充策略（首批已通過 G5）

- 先加入 parameterized rolling return 與 volume acceleration。
- 經各自資料能力與 golden tests 後，再考慮 distance-to-limit、external ratio、ORB、EMA、RSI/Bollinger 及 exits。
- 只為實際遷移且有測試的策略新增檔案，不一次建立 speculative stubs。
- 首批 `rolling_return_entry` 與 `volume_acceleration_entry` 各自擁有獨立檔案、Schema、Template 與 parameter-derived Feature Requests；Web／PostgreSQL 沿用 generic Draft/Publish/Version/Set contract。
- completed 1m Kbar adapter 的每個 deque 雖有上限，但首輪 Review 發現 session-keyed map 仍會跨日累積；G5 remediation 必須在 engine session transition 淘汰前一 session，只保留目前 session 的 request/symbol state。
- volume baseline 的凍結語意為「由最新往最舊的連續完整視窗前綴」：僅允許最舊端因開盤暖機不足而缺少 suffix；任何中間／較新的缺口一律 `INSUFFICIENT_DATA`，不得用更舊視窗補足。
- 首批 G5 核准時的 runtime availability 明確為 `BACKTEST_KBAR_1M`；後續 parameterized Local Paper adapter 必須另過 G6，不能由 G5 核准推論可用。

Gate G5：每個已遷移策略有獨立檔案、Schema/Feature Requests、runtime availability、golden tests 與可重現 evidence。

目前狀態：**PHASE 5 FIRST SLICE APPROVED；G5 PASSED / MVP SCOPED GO**。Engine 已透過既有 Registry/adapter boundary 宣告 session transition，completed-Kbar state 會在切換前淘汰舊 session；100-session 測試證明單一 symbol/request 只保留一組 active state。Volume golden tests 證明只缺最舊暖機 suffix 時可依 minimum count 計算，但缺少 09:05 的中間 gap 會以 `baseline_volume_windows_non_contiguous` fail closed。候選驗證為 focused `39 passed, 8 skipped`、無 DSN full `1193 passed, 22 skipped`；獨立 Review 為 focused `36 passed, 8 skipped`、full no-DSN `1193 passed, 22 skipped`，且 `git diff --check` 通過。本輪沒有 PostgreSQL schema/repository 變更，因此沒有重跑 PostgreSQL。此 Gate 只核准首批 rolling return／volume acceleration；後續策略批次、Local Paper parameterized Tick adapter、broker／real-money 工作均不在核准範圍內。

### Phase 6 — Parameterized Local Paper Feature Adapter（完成；MVP Conditional Go）

- 只為 `rolling_return_entry` 與 `volume_acceleration_entry` 啟用 `LOCAL_PAPER_TICK_BIDASK` binding；不新增下一批策略。
- 沿用既有 `MomentumShadowRuntime -> FeatureEngine -> IntradayBarStore`，把 Tick 聚合的完整 1 分 K 投影成 exact `FeatureRequestSpec` evidence；Simulation 不另建行情或 rolling-state pipeline。
- raw Tick 維持 20 分鐘 retention；completed 1m bars 使用獨立 6 小時 bounded retention，涵蓋目前 schema 最大的 `30m * (10 baseline + current)` 需求，session transition 一律清空。
- Controller 只把目前 `PAPER_APPROVED` exact Strategy Set 所需的 parameterized requests 交給 reader；Dashboard snapshot 保存 adapter/request/parameter/specification/implementation/state-key identities 與 missing evidence。
- Atomic Local Paper 對每個 Strategy Version 分別核對 exact request evidence；同一 feature 的 2m/3m 不共用值，identity/parameters/state key 漂移一律 fail closed。
- rolling calculator 與 G5 backtest 共用 `features/rolling.py` 的 completed-Kbar 公式與 volume gap contract；runtime owner 仍分別是 Backtest state 與既有 live FeatureEngine。
- G5 已發布、Template 尚只有 `BACKTEST_KBAR_1M` 的舊 Version 仍可由窄範圍 compatibility rule 重播 Backtest；它不會因部署 G6 自動取得 Local Paper admission。要跑 Paper 必須另建使用目前 Template digest 的 immutable Version。

Gate G6：**PASSED / MVP CONDITIONAL GO**。Parameterized Local Paper 已核准；broker／real-money 明確禁止。候選驗證為 focused no-DSN `95 passed, 8 skipped`、full no-DSN `1203 passed, 22 skipped`、full disposable PostgreSQL 17 `1225 passed`；獨立 Reviewer 另驗證 focused `86 passed, 8 skipped`、Backtest slice `3 passed`、full no-DSN `1203 passed, 22 skipped` 與 `git diff --check`。一次性 PostgreSQL 已停止並清除。

MVP 操作限制：Momentum runtime 與 Dashboard singleton 綁定 process 啟動日，目前沒有跨交易日 hot rollover。Dashboard 若跨日持續執行，新交易日行情會 fail closed；正式加入 session rollover 前，操作者必須在每個交易日開始前重啟 Dashboard。首次實際使用仍須完成盤中真實行情 smoke test。此 Gate 不包含後續策略、Parameterized broker adapter、CA、trade subscription、Shioaji 委託或 real-money execution。

### Phase 7 — Atomic ORB Strategy（Implementation Candidate）

- 下一個最小完整切片只加入 `opening_range_breakout_entry`；它是獨立 ENTRY 策略，不隸屬任何「漲停加速」群組。
- Web／PostgreSQL 參數至少包含開盤區間分鐘數、突破 buffer、最早／最晚進場時間；immutable Version 解析成 exact opening-range Feature Request。
- Backtest 與 Local Paper 共用 completed 1-minute Kbar 的開盤區間公式：從 09:00 起必須存在精確、連續的 N 根完整 Kbar；缺少任一分鐘一律 fail closed，不使用較晚或較舊 Kbar 補足。
- Backtest 仍由 completed-Kbar adapter 擁有 session state；Local Paper 仍由既有 `MomentumShadowRuntime -> FeatureEngine -> IntradayBarStore` 投影 request evidence。不得在 Simulation 建立第二個 ORB calculator 或第三套行情 pipeline。
- `distance_to_limit` 雖已有 live Feature，但 HistoricalBar Dataset 尚未保存當日 verified limit-up reference；external ratio 也缺少可信歷史 aggressor cumulative totals。兩者延後，不得以 live-only 欄位假裝可比較回測。

Gate G7：**PASSED / MVP SCOPED GO**。Atomic ORB Strategy 已核准；broker／real-money 明確禁止。ORB 具備 code-owned Template/Schema、Feature Specification、Backtest/Local Paper bindings、exact request/snapshot identities 與連續區間 golden tests。Equality blocker 已改為嚴格 `current_price > breakout_price`；buffer `0` 且價格等於 opening high 時固定為 `NOT_TRIGGERED`，只有嚴格高於含 buffer 的門檻才會 `TRIGGERED`。候選驗證為 focused `83 passed, 8 skipped`、full no-DSN `1213 passed, 22 skipped`；獨立 Reviewer 另驗證 ORB suite `8 passed`、full no-DSN `1213 passed, 22 skipped` 與 `git diff --check`。本批沒有 migration/repository contract 變更，因此未重建 disposable PostgreSQL；no-DSN 不代表 PostgreSQL integration evidence，但不阻擋此 scoped Gate。此核准不自動授權下一批策略或 push。

### Phase 8 — Atomic EMA Crossover Strategy（完成；MVP Scoped Go）

- 下一個最小完整切片只加入 `ema_crossover_entry`；它是獨立 ENTRY 策略，預設語意為 EMA(5) 由下往上穿越 EMA(20)。
- Web／PostgreSQL immutable Version 保存 `fast_period`、`slow_period`、最早／最晚進場時間；必須驗證 `fast_period < slow_period`，並解析成 exact `ema_cross_up_v1` Feature Request。
- Backtest 與 Local Paper 共用 completed 1-minute Kbar 的 SMA-seeded EMA recurrence。觸發邊界固定為 previous fast `<=` previous slow 且 current fast `>` current slow；不是只要 fast 位於 slow 上方就重複觸發。
- EMA 使用從 09:00 到目前完整 bar 的有序 session prefix；暖機不足或任一中間分鐘缺失均 fail closed。Runtime state／history 必須維持 bounded one-session retention。
- Local Paper 沿用既有 `MomentumShadowRuntime -> FeatureEngine -> IntradayBarStore` request projection；Simulation 只驗證 exact evidence，不建立第二個 EMA calculator 或第三套行情 pipeline。
- Feature evidence 保存 crossover boolean 與 previous/current fast/slow EMA；request、parameters、Specification、implementation、adapter、cadence、session identity 漂移一律 fail closed。

Gate G8：**PASSED / MVP SCOPED GO**。EMA implementation 已核准。候選驗證為 focused `61 passed`、full no-DSN `1222 passed, 22 skipped`、Python compilation 與 `git diff --check` 通過；獨立 Reviewer 另驗證 EMA focused `41 passed`、full no-DSN `1222 passed, 22 skipped` 與 `git diff --check`。第一次 full run 只因 sandbox artifact 寫入限制失敗，改用獨立 `/tmp` 目錄後同套測試通過。本批沒有 migration/repository contract 變更，因此沒有新增 PostgreSQL integration evidence。此核准不包含 RSI/Bollinger、distance-to-limit、external-ratio、Exit、broker、CA、trade subscription、Shioaji 委託、real-money execution 或 push。

### Phase 9 — Atomic RSI Oversold Strategy（Completed）

- 下一個最小完整切片只加入 `rsi_oversold_entry`。既有 `rsi_bollinger_reversion_entry_v0` 不直接遷移，因 RSI 超賣與 Bollinger 下軌重返是兩個應獨立回測的原子條件。
- Web／PostgreSQL immutable Version 保存 `rsi_period`、`oversold_threshold`、最早／最晚進場時間，並解析成 exact `wilder_rsi_v1` Feature Request。
- Backtest 與 Local Paper 共用 completed 1-minute Kbar 的 Wilder gain/loss recurrence。當目前 RSI 小於或等於 oversold threshold 時觸發；flat input 固定為 50、全漲為 100、全跌為 0。
- RSI 使用從 09:00 到目前完整 bar 的有序 session prefix；暖機需要 `rsi_period + 1` 根，任何中間分鐘缺失均 fail closed，history/state 維持 bounded one-session retention。
- Local Paper 沿用既有 `MomentumShadowRuntime -> FeatureEngine -> IntradayBarStore` request projection；Simulation 只驗證 exact evidence，不建立第二個 RSI calculator 或第三套行情 pipeline。
- Bollinger lower-band re-entry 延後為獨立 Atomic Strategy，之後才能透過 Strategy Set 與 RSI 自由組合及分別比較回測效果。

Gate G9：**PASSED / MVP SCOPED GO**。RSI implementation 已核准。候選驗證為 focused `72 passed`、full no-DSN `1233 passed, 22 skipped`、Python compilation 與 `git diff --check` 通過；獨立 Reviewer 另驗證 RSI focused `45 passed`、full no-DSN `1233 passed, 22 skipped`、Python compilation 與 `git diff --check`。本批沒有 migration/repository contract 變更，因此沒有新增 PostgreSQL integration evidence。RSI 專屬跨 session state-count 與非有限／超出 0–100 evidence 的 fail-closed regression 列為非阻擋 hardening。此核准不含 Bollinger、Exit、distance-to-limit、external-ratio、broker、CA、trade subscription、Shioaji 委託、real-money execution 或 push。

### Phase 10 — Atomic Bollinger Lower-Band Re-entry Strategy（Completed）

- 此切片只新增 `bollinger_lower_reentry_entry`；RSI 超賣維持獨立 Strategy Version，兩者只能透過 exact Strategy Set 選擇性組合。
- Web／PostgreSQL immutable Version 保存 `bollinger_period`、`stddev_multiplier`、最早／最晚進場時間，並解析成 exact `bollinger_lower_reentry_v1` Feature Request。
- Bollinger Bands 使用 completed 1-minute closes 的 population variance。只有 previous close 嚴格低於 previous lower band，且 current close 大於或等於 current lower band 的跨越事件才觸發；持續位於同一側不得重複觸發。
- Feature 需 `bollinger_period + 1` 根從 09:00 起連續完整的一分鐘 Kbar，以重建 previous/current bands；暖機不足或 session prefix 中間缺分鐘一律 fail closed。
- Backtest 與 Local Paper 共用一個 runtime-neutral 公式，並沿用既有 request-aware owners；Simulation 只驗證與消費 boolean projection，不建立第二套 Bollinger calculator 或第三套行情 pipeline。
- Evidence 保存 previous/current close、middle/upper/lower bands、period 與 multiplier；request、parameters、Specification、implementation、adapter、cadence、session identity 漂移一律 fail closed。

Gate G10：**PASSED / MVP SCOPED GO**。Bollinger implementation 已核准。候選驗證為 focused `83 passed`、full no-DSN `1246 passed, 22 skipped`、Python compilation 與 `git diff --check` 通過；獨立 Reviewer 另驗證 Bollinger focused `49 passed`、full no-DSN `1246 passed, 22 skipped`、Python compilation 與 `git diff --check`。Commit 前已把 `BollingerReentryFeatureValue` 補入 FeatureEngine result type union；此項只修正型別契約，不改 runtime 行為或 Feature identity。本批沒有 migration/repository contract 變更，因此沒有新增 PostgreSQL integration evidence。此核准不含 Exit、distance-to-limit、external-ratio、broker、CA、trade subscription、Shioaji 委託、real-money execution 或 push。

## 19. Test Matrix

- Parameter Schema unit/cross-field/canonicalization tests。
- 3m/2.0% 等 Strategy parameters 解析成正確 Feature Request，不會仍使用固定 2m window。
- Feature Request/state-key identity unit tests：2m 與 3m、不同 adapter/cadence 產生不同 identity；G5 驗收 Backtest state owner，G6 另驗收既有 live FeatureEngine 的 request-aware projection，不以 helper test取代 runtime evidence。
- Template/Draft/Version/Event transaction、digest、immutable conflict與 Publish TOCTOU tests。
- Lifecycle legal/illegal transition table、PAUSED reactivation preflight、RETIRED terminal與 projection deterministic rebuild/gap/fork quarantine tests。
- PostgreSQL post-publish concurrency suites：兩個相同 Version/key 同時送達必須 replay 同一成功 event；不同 digest 必須 idempotency conflict；不同 key/stale sequence 必須 sequence conflict。
- PostgreSQL first-Publish concurrency/retry suites：同 Draft/key/digest replay 同一 Version/Event、同 key/different digest conflict、different key `DRAFT_ALREADY_PUBLISHED`、commit 後 response-loss retry，以及不同 Draft 同 strategy 的 unique/monotonic version allocation。
- Persistence preflight tests：atomic-platform write path 在 SQLite 設定或 PostgreSQL unavailable 時 fail closed，且不建立／更新 SQLite；一次性 legacy import 只讀 SQLite、寫 PostgreSQL並核對 counts/digests。
- Migration acceptance tests：編號 migration SQL 必須由現有 runner 實際套用到 disposable PostgreSQL，驗證所有 table、constraint、index 與重複執行行為；repository 不得在 runtime 臨時建立 schema。
- PostgreSQL test-environment tests：`tests/conftest.py` 提供明確 opt-in 的 disposable PostgreSQL fixture，隔離 schema/database 並在 unavailable 時以可辨識條件 skip；不得以全域 SQLite override 偽裝 PostgreSQL contract tests。
- Transactional outbox crash tests：commit 前 crash 三者皆無、commit 後 publish 前 crash 保留 pending outbox、dispatcher at-least-once duplicate 由 event ID 去重。
- Registry allowlist、exact runtime binding/implementation digest mismatch tests。
- Feature Specification、各 adapter formula、warm-up、session reset、stale/missing 與明確 non-parity tests。
- 每個 Atomic Strategy TRIGGERED/NOT/INSUFFICIENT/BLOCKED tests。
- Signal lifecycle dedup/cooldown/TTL/max trigger tests。
- ANY/ALL/AT_LEAST_N 的 blocked/insufficient/impossible-to-reach-N、priority、EXIT precedence與 attribution tests。
- Risk 不能成為 Strategy Set member；adapter 拒絕 ProposedOrderCommand；Hard Risk 永遠執行；numeric/set/boolean monotonic merge 與寬鬆 override rejection tests。
- Entry 與 risk-reducing exit matrix tests：明確覆蓋 `max_pending_notional`、`blocked_symbols`、`blocked_strategy_versions`、`global_command_blocked_symbols`、`allow_odd_lot`，並驗證未列 check 預設不可 bypass。
- Migration/backward compatibility/completed-run replay tests。
- Legacy raw-ID snapshot 只走 compatibility adapter；新 API 拒絕 raw ID，舊 config/digest 不被改寫。
- Dataset capability API/worker double preflight tests。
- Backtest future-mutation/look-ahead/determinism tests。
- Fee/tax/slippage/tick-size/limit/partial-fill tests。
- Position ownership/manual-position isolation tests。
- Restart/recovery/idempotency/duplicate-worker tests。
- Web dynamic form/version diff/clone/publish/set builder interaction tests。
- Evaluation retention tests：NOT_TRIGGERED 只聚合、bounded sample quota、DEBUG bounds/expiry、artifact quota。
- Security tests：unknown fields、unknown binding、arbitrary path/code payload rejected、non-loopback bind rejected、origin/CSRF mutation protected。
- Full regression and browser smoke。

## 20. Observability

最低 metrics/logs：

- per strategy version evaluated/triggered/not/insufficient/blocked。
- per set matched and primary attribution。
- signal-to-intent、intent-to-order、order-to-fill latency。
- stale/missing capability/Risk rejection原因。
- strategy run heartbeat/state/restart count。
- open positions/pending orders by owner。
- realized/unrealized PnL by strategy version/set/run。
- backtest vs paper drift indicators。
- Schema validation、publish、activation audit events。
- evaluation persistence rows/artifact bytes、bounded sample quota、DEBUG trace quota/expiry/cleanup failures。
- lifecycle outbox pending age、delivery attempts、dead-letter count、dispatcher lag，以及 Publish replay/conflict counts。

Metrics 的 NOT_TRIGGERED 數量來自聚合 counters/histograms；Observability 不要求無界逐筆 evaluation rows。

## 21. Rollout and Rollback

Rollout：

1. 先完成 B3 next 實作前 Review；B3 未關閉不寫產品程式。
2. PostgreSQL migrations/preflight 與必要的 legacy SQLite -> PostgreSQL 一次性匯入先完成；SQLite 不接受任何新寫入。
3. 只做 backtest vertical slice，不更改既有策略／本機模擬執行。
4. Shadow bootstrap 新 Templates/Versions，核對 digests，開放 above-VWAP、breakout 單獨與組合回測。
5. 完成 backtest qualification 與 implementation review 後，才逐一遷移其他 Atomic Strategies。
6. Local paper 必須另行授權，最後才接，generic runner 預設 STOPPED/manual start。

Rollback：

- UI 隱藏新 activation，不刪版本、runs或audit。
- 停用 generic paper runner，保留 PostgreSQL completed-run reader；尚未匯入的舊 SQLite 檔案只能離線唯讀搬移，不可成為 runtime reader/authority。
- migration只 forward-add tables/columns；不改寫舊 digests。
- 不將新 run 悄悄降級到舊 engine；不相容時 fail closed。

## 22. File Map

不要建立廣泛的 `strategy_runtime/` package 複製現有 `strategy_catalog`、`features`、`backtest`、`simulation` 職責。第二次 Review 已接受並凍結下列 ownership：

- `strategy_catalog`：Template、Draft、immutable Version、Schema、lifecycle event、allowlisted binding。
- `atomic_strategies`：只保存 runtime-agnostic evaluation protocol、allowlisted strategy registry 與每個已實作原子策略；不擁有 Feature 計算、pipeline、lifecycle 或 execution。
- `features`：共用 Feature Specifications 與 live Tick/BidAsk adapters。
- `backtest`：completed Kbar adapters、歷史 evaluation engine、run snapshot與 attribution。
- `simulation`：generic local-paper orchestration；不得成為策略或 Feature 第二來源。

Phase 1 最小預計新增／拆分：

```text
backtest/migrations/005_atomic_strategy_platform.sql
strategy_catalog/drafts.py
strategy_catalog/lifecycle.py
strategy_catalog/parameter_schema.py
strategy_catalog/repository.py
strategy_catalog/postgres_repository.py
strategy_catalog/application.py
strategy_catalog/sets.py
atomic_strategies/
  protocol.py
  registry.py
  feature_requests.py
  entries/
    above_vwap.py
    breakout_previous_high.py
features/specifications.py
backtest/feature_adapters.py
backtest/atomic_strategy_adapter.py
tests/test_strategy_templates.py
tests/test_strategy_versions.py
tests/test_strategy_composition.py
tests/test_parameterized_feature_requests.py
tests/test_atomic_strategy_backtest_slice.py
tests/test_strategy_publish_idempotency.py
tests/test_strategy_postgres_persistence.py
tests/test_strategy_migrations.py
```

Phase 1 預計修改：

```text
strategy_catalog/domain.py
strategy_catalog/service.py
backtest/domain.py
backtest/engine.py
backtest/application.py
backtest/repository.py
backtest/postgres_repository.py
backtest/sqlite_postgres_migration.py  # 僅一次性唯讀 legacy import
config/backtest.py
runtime/composition.py
.env.example
tests/conftest.py
pyproject.toml
README.md
```

Phase 1 PostgreSQL 測試基礎必須使用 disposable database/schema，並由環境變數明確 opt-in；現有一般單元測試可保留自己的隔離方式，但 atomic-platform persistence、migration、row-lock、concurrency 與 fail-closed tests 不得被全域 SQLite 設定取代。`pyproject.toml` 明列測試 dependency，README 說明本機／CI PostgreSQL test setup 與不啟用時的 skip 訊息。

Phase 2 已加入且由 Gate G2 管理的檔案：

```text
backtest/migrations/006_atomic_strategy_web_management.sql
backtest/migrations/007_atomic_strategy_audit_contract.sql
strategy_catalog/web_projection.py
dashboard/server.py
dashboard/static/index.html
dashboard/static/css/dashboard.css
dashboard/static/js/app.js
dashboard/static/js/mutation_keys.js
dashboard/static/js/workspaces/backtest.js
tests/test_atomic_strategy_web_api.py
tests/test_atomic_strategy_web_backtest.py
tests/test_atomic_strategy_web_ui.py
```

Phase 3 已加入且由 Gate G3 管理的檔案：

```text
backtest/migrations/008_backtest_qualification.sql
backtest/migrations/009_backtest_experiment_families.sql
backtest/migrations/010_backtest_experiment_family_identity.sql
backtest/comparability.py
backtest/qualification.py
backtest/application.py
backtest/repository.py
backtest/postgres_repository.py
features/specifications.py
backtest/atomic_strategy_adapter.py
dashboard/server.py
dashboard/static/index.html
dashboard/static/css/dashboard.css
dashboard/static/js/app.js
dashboard/static/js/workspaces/backtest.js
README.md
tests/test_backtest_qualification.py
tests/test_backtest_qualification_postgres.py
tests/test_parameterized_feature_requests.py
tests/test_atomic_strategy_web_api.py
tests/test_atomic_strategy_web_ui.py
tests/test_strategy_migrations.py
tests/test_backtest_sqlite_postgres_migration.py
```

Phase 4 另行核准後才修改 `simulation/continuous_strategy.py`、`simulation/strategy_flow.py`。剩餘策略檔案只在該策略實際遷移與測試時新增，不先建立 speculative 空殼。

Phase 5 首批已加入且由 Gate G5 管理的檔案：

```text
atomic_strategies/entries/rolling_return.py
atomic_strategies/entries/volume_acceleration.py
atomic_strategies/feature_requests.py
atomic_strategies/registry.py
features/specifications.py
backtest/features.py
backtest/feature_adapters.py
backtest/atomic_strategy_adapter.py
backtest/engine.py
backtest/strategies.py
tests/test_atomic_strategy_phase5.py
tests/test_parameterized_feature_requests.py
tests/test_strategy_templates.py
tests/test_atomic_strategy_web_api.py
tests/test_atomic_paper_runtime.py
tests/test_strategy_publish_idempotency.py
```

Phase 6 parameterized Local Paper candidate 修改／新增：

```text
atomic_strategies/compatibility.py
features/rolling.py
features/models.py
features/engine.py
market_data/intraday_bar_store.py
runtime/momentum_shadow.py
dashboard/momentum.py
dashboard/server.py
simulation/atomic_runtime.py
simulation/continuous_strategy.py
atomic_strategies/entries/rolling_return.py
atomic_strategies/entries/volume_acceleration.py
backtest/features.py
tests/test_local_paper_parameterized_features.py
tests/test_momentum_shadow_runtime.py
tests/test_realtime_momentum_dashboard_service.py
tests/test_atomic_paper_runtime.py
tests/test_continuous_paper_strategy.py
tests/test_atomic_strategy_phase5.py
tests/test_strategy_templates.py
tests/test_strategy_publish_idempotency.py
```

以上 ownership 是 v1 frozen contract。`atomic_strategies/` 是窄範圍 pure-kernel owner，不得成長為重複 catalog/feature/backtest/simulation 的廣泛 runtime package。Feature Specification 固定放在既有頂層 `features/` owner，不建立第三套 calculator；任何 owner 變更都必須先修改本計畫並重新 Review，不能在實作中臨時漂移。

## 23. Definition of Done

1. 每個已實作 Atomic Strategy 有獨立檔案、stable ID、Template、Schema及 golden tests；不先建立 speculative strategy stubs。
2. 使用者可在 Web 依 Schema 建立／修改 Draft、驗證、clone，並以 transaction 內重驗證 publish 不可變參數版本。
3. 資料庫只保存 definitions/configurations/compositions/audit，不執行任意 code。
4. Strategy Sets 只引用 exact versions/digests 並支援語意已凍結的 ANY/ALL/AT_LEAST_N；Risk 不是 member。
5. 每次回測保存完整 run snapshot，可使用相同 digest重現。
6. 可單獨比較 Atomic Strategies，也可分析組合與 primary attribution。
7. 共用 Feature Specification 是語意 source of truth；每個 cadence/runtime 使用明確 adapter，只有相容語意才宣稱 parity。
8. Strategy parameters 會 deterministic 解析成 Feature Requests；2m/3m 等 feature state/cache 以 parameter digest 隔離並進入 snapshot。
9. UI/API/worker/runtime都拒絕不相容資料、模糊 raw strategy ID 或未知 runtime binding/digest。
10. Draft、immutable Version 與 append-only lifecycle event 分離；首次 Publish 以 `(draft_id, idempotency_key)` 保存 operation/result mapping，Publish 無 TOCTOU window；post-publish lifecycle 使用 lock 內 idempotency replay、PostgreSQL row lock、event/projection/outbox 同 transaction 與 deterministic projection rebuild，既有 Version 不被 status mutation 改寫。
11. NOT_TRIGGERED 只聚合；BLOCKED/INSUFFICIENT samples 有上限；全量 DEBUG trace 有 bounds/quota/expiry，預設不逐筆寫 DB。
12. v1 Web 維持 loopback-only single-user；未實作 auth/RBAC 前拒絕非 loopback exposure，不宣稱角色權限已 enforcement。
13. generic local-paper runner可載入 approved exact-version Pipeline，而非硬編碼 Momentum，且需另行 Gate 核准。
14. Position ownership、manual isolation、Hard Risk、Journal、idempotency與recovery都有測試；command 固定經 Proposed -> Admission -> Approved boundary，adapter 拒絕未核准 command，Hard Risk monotonic merge、所有 declared-control exit bypass 與 fail-closed catch-all 不可由 Web/DB 放寬。
15. 模擬成交包含費用、稅、滑價、tick size、price limit及委託生命週期 contract，或明確標示未實作並禁止績效 promotion。
16. 重啟不會靜默重複下單；不確定狀態進入 RECOVERY_REQUIRED。
17. 舊 strategy definitions、raw-ID snapshots、completed runs及digests未被覆寫，仍由 legacy compatibility path 重現。
18. 全套 regression、migration、API、UI、deterministic replay及browser smoke通過。
19. 全程不呼叫 Shioaji券商下單、CA或真實帳務 API。
20. 原子策略平台所有新資料只寫 PostgreSQL；SQLite 不可作 writer、runtime authority 或 PostgreSQL fallback。

## 24. 建議的 v1 預設決策

- Strategy Version Draft entity 可修改；Publish 建立 immutable Version。
- 首次 Publish 使用 Draft-scoped operation/result mapping；同 key/digest replay、不同 digest conflict、其他 key 回 DRAFT_ALREADY_PUBLISHED。
- Lifecycle 使用 Section 7.3 合法 transition table、append-only event、lock 內 idempotency replay及 PostgreSQL compare-and-append；event/projection/outbox 同 transaction，RETIRED terminal，PAUSED -> ACTIVE 必須重新 preflight。
- Composition 先做 ANY/ALL/AT_LEAST_N；WEIGHTED 延後。
- ALL/ANY/AT_LEAST_N 使用第 9 節的 blocked/insufficient semantics，預設不 short-circuit attribution。
- Risk 不是 Strategy member；command 固定走 Execution Policy -> ProposedOrderCommand -> Hard Risk -> ApprovedOrderCommand -> Adapter。
- Hard Risk code-owned；Web/DB 依 Section 10.3 的 min/max/intersection/union/OR/AND 規則只能收緊限制，無法證明 monotonic 即拒絕。
- v1 同 symbol只允許一個自動 Strategy Set owner。
- 自動策略不可管理手動持倉。
- 第一個 implementation slice 只做 completed 1m Kbar backtest、above-VWAP、breakout previous high 與 exact-version Set；先不接 local paper。
- rolling return/volume acceleration 必須先完成 parameterized Feature Request/cache isolation，再加入。
- Backtest vertical slice 通過 Review 且另行授權後，才接現有 Tick/BidAsk local-paper adapter；不宣稱 Kbar/Tick parity。
- Web v1 維持 `127.0.0.1` loopback-only；無 auth/RBAC 前不得開放網路存取。
- NOT_TRIGGERED 預設只保存聚合 metrics；完整 evaluation trace 僅限有界 DEBUG artifact。
- 本機模擬啟動預設為手動，重啟預設 RECOVERY_REQUIRED/STOPPED，直到 durable recovery完成。
- Atomic strategy persistence 固定 PostgreSQL-only；不存在 SQLite writer 或 automatic fallback。
