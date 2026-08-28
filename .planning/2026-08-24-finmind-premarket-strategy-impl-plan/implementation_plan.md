# FinMind 三大法人盤前策略 MVP — Implementation Plan

## 1. Outcome first

建立一條獨立、可稽核的 MVP 流程：每天 T 日收盤後取得 FinMind 三大法人資料，產生 T+1 盤前候選名單；T+1 盤中只有同時通過既有 exact Atomic Strategy Set 的股票，才可進入 Local Paper Simulation。

```text
T 日收盤後 FinMind 法人資料
        ↓
不可覆寫的 Candidate Batch（target = T+1）
        ↓
盤前 CandidatePool／Dashboard observation
        ↓
T+1 exact Atomic Strategy Set 價格確認
        ↓
FinMind candidate gate
        ↓
既有 fresh BidAsk + Hard Risk
        ↓
Local Paper intent only
```

這不是正式 PR-008 holdout，也不開放實單。FinMind 的 current-market mapping、survivorship bias 與非 PIT 限制必須持續顯示。

## 2. MVP strategy hypothesis

### 2.1 Premarket candidate rule

使用已完成的 r2 canonical dealer semantics：

```text
foreign_investor_net_shares > 0
AND investment_trust_net_shares > 0
AND canonical_dealer_net_shares > 0
```

- 依三者合計買超股數由高至低排序。
- 最多 20 檔。
- T 日資料只能用於已解析的下一交易日 T+1。
- 名單在 T+1 收盤後失效，不延用至 T+2。
- 當日名單缺失、digest 錯誤、target session 不符或資料尚未發布時，法人策略 fail closed；其他非本策略功能不受影響。

### 2.2 Intraday confirmation

第一版不新增 FinMind-aware price strategy。建立／選用現有 atomic strategies 的 exact ENTRY Strategy Set，建議先以以下假設進行 Paper MVP：

```text
Entry window: 09:05–10:30

AT_LEAST_N(2 of 3):
1. above_vwap_entry
2. breakout_previous_high_entry
3. volume_acceleration_entry
```

外層條件固定為：

```text
symbol ∈ frozen FinMind T-1 candidate batch
AND exact Atomic Strategy Set = TRIGGERED
```

參數值必須透過既有 Draft → immutable Version → Exact Strategy Set → Paper activation 流程保存；不得寫死在 FinMind adapter。上述 2-of-3 是第一個可驗證 baseline，不代表已證明有超額報酬。

### 2.3 Position and risk boundary

沿用現有 `ContinuousPaperStrategyController`：

- 每個 session 最多一筆自動進場。
- 一張整股 Local Paper 部位。
- 停損、停利、每日最大損失必須由 operator 明確輸入並被 activation digest 固定。
- 13:20 後不再進場、13:25 開始 flatten、13:30 後不得留下策略自動管理中的隔夜部位。
- fresh BidAsk、RiskGate、ownership、kill switch、idempotency 與 journal 路徑全部保留。

## 3. Architecture

### 3.1 Dependency direction

```text
institutional_mvp domain / application
        ↑ ports
FinMind HTTP adapter + file artifact repository

CandidatePool domain
        ↑ adapter
FinMindMvpCandidateSource

ContinuousPaperStrategyController
        ↑ port
SessionCandidateGate
```

FinMind API schema只能存在於 provider adapter／normalizer。CandidatePool、Atomic Strategy 與 Local Paper 只能看到 provider-neutral 的 candidate batch identity、symbol、rank、source session、target session、expiry 與 digest。

### 3.2 New domain contracts

建議新增：

- `InstitutionalMvpCandidateBatchV1`
  - `artifact_id`
  - `artifact_digest`
  - `source_session`
  - `target_session`
  - `generated_at`
  - `expires_at`
  - `candidate_policy_id/digest`
  - `candidates(symbol, market, name, rank, entry_digest)`
  - `limitations`
- `InstitutionalMvpCandidateBatchRepository`
  - `put_immutable(batch)`
  - `get_by_target_session(session)`
- `InstitutionalFlowProvider`
  - `fetch_daily_wide(session)`
  - `fetch_current_stock_info()`
- `SessionCandidateGate`
  - `resolve(target_session)`
  - `evaluate(symbol, evaluated_at)`

Batch loader 必須驗證 canonical digest、source/target session、expiry 與 current-market limitation；它不得讀取價格、PnL 或策略 outcome。

## 4. Ordered implementation slices

### PR-MVP-PM-001 — Daily immutable FinMind batch

目標：把目前固定 2026-08-18 的 evidence builder 泛化成每日可執行的 one-shot MVP，而不修改或覆蓋既有 r1/r2 artifacts。

預計檔案：

- 新增 `institutional_mvp/domain.py`
- 新增 `institutional_mvp/ports.py`
- 新增 `institutional_mvp/application.py`
- 新增 `institutional_mvp/finmind_adapter.py`
- 新增 `institutional_mvp/artifacts.py`
- 新增 `config/institutional_mvp.py`
- 新增 `scripts/run_finmind_institutional_mvp_daily.py`
- 保留 `scripts/capture_finmind_institutional_mvp.py` 與 `scripts/build_finmind_institutional_mvp_candidates.py` 不變，作為已封存 evidence replay

CLI：

```text
python scripts/run_finmind_institutional_mvp_daily.py \
  --source-session YYYY-MM-DD \
  --output-root data/institutional_mvp
```

行為：

1. 檢查 `FINMIND_API_TOKEN` 存在與 quota reserve，不保存 token。
2. 只請求 `TaiwanStockInstitutionalInvestorsBuySellWide` 與 `TaiwanStockInfo`。
3. 由 reviewed equity calendar 解析下一交易日；不可直接 `source + 1 day`。
4. 套用 frozen r2 candidate policy。
5. 以 date + content digest 產生不可覆寫 artifact。
6. 同 session 同 bytes 回傳 idempotent replay；同 session 不同 bytes 建立 conflict/new revision，不覆寫。

Exit criteria：

- 週末／休市日不會建立錯誤 target session。
- provider 尚未發布當日資料時回 `SOURCE_NOT_READY`，不拿上一日資料代替。
- quota、schema、mapping 或 digest 錯誤 fail closed。
- 不讀 price/Kbar、return、PnL、holdout；不觸碰 broker。

### PR-MVP-PM-002 — Candidate adapter and shadow admission

目標：將 batch 轉成 CandidatePool discovery，但仍保持 observation-only。

預計檔案：

- `candidate/models.py`
  - 新增 `CandidateSource.FINMIND_INSTITUTIONAL_MVP`
- 新增 `candidate/finmind_mvp.py`
  - `FinMindMvpCandidateSource`
  - `FinMindMvpCandidateBatch`
- 新增 `candidate/finmind_mvp_shadow_admission.py`
- 更新 `candidate/__init__.py`

Discovery mapping：

- `source=FINMIND_INSTITUTIONAL_MVP`
- `best_rank=candidate.rank`
- `rank_types=(FINMIND_THREE_WAY_NET_BUY_V1,)`
- `priority` 由 versioned config 提供，不從買超股數直接推導
- `contribution_ref` 只保存 artifact ID 與 per-entry digest
- `expires_at=T+1 13:30 Asia/Taipei`

Shadow admission 必須維持：

```text
subscription_allowed = false
execution_allowed = false
```

Exit criteria：

- formal `PREVIOUS_SESSION_WATCHLIST` 來源與邏輯完全不變。
- source identity、rank、TTL、entry digest 經 CandidatePool union 後仍存在。
- wrong target session、stale batch、tampered digest、T-day ineligible symbol 全部明確拒絕。
- capacity／overlap／rejection metrics 可重播且 deterministic。

### PR-MVP-PM-003 — Read-only Dashboard workspace

目標：先讓 operator 在盤前看得到當日名單與 readiness，不啟用 quote subscription 或策略執行。

預計檔案：

- 新增 `dashboard/institutional_mvp.py`
- `dashboard/server.py`
  - 新增唯讀 `GET /api/institutional-mvp/candidates/current`
- `dashboard/static/js/workspaces/candidates.js`
- `dashboard/static/index.html`
- UI contract tests

顯示：

- source session、target session、generated at、artifact digest 短碼
- READY / MISSING / STALE / DIGEST_MISMATCH / WRONG_SESSION
- rank、symbol、name、market
- 「FinMind current mapping／非 PIT／盤後資料／Paper MVP only」標籤
- shadow admission capacity/rejection counts

Exit criteria：

- GET 不觸發 provider request。
- refresh 不改 candidate artifact。
- panel 不改 BuyScore、RiskGate、subscription 或 order。
- 缺資料時 UI 清楚顯示 unavailable，不沿用舊名單。

### PR-MVP-PM-004 — Local Paper candidate gate

目標：以明確 opt-in 將 frozen batch 接到 exact Atomic Strategy Set 的 Local Paper entry path。

預計檔案：

- 新增 `simulation/candidate_gate.py`
- `simulation/continuous_strategy.py`
- `simulation/atomic_runtime.py`（僅在需要 pin gate evidence 時調整 projection decision）
- `simulation/strategy_flow.py`（保留／擴充 decision evidence）
- `dashboard/server.py`
- `dashboard/static/js/workspaces/simulation.js`

新增啟動參數：

```text
candidate_gate_mode = DISABLED | FINMIND_MVP_REQUIRED
candidate_batch_artifact_id
candidate_batch_digest
```

啟動 preflight：

1. artifact digest 正確。
2. batch target session 等於 current reviewed session。
3. batch 尚未過期。
4. exact Strategy Set 已 PAPER_APPROVED 且 runtime binding 完整。
5. FinMind candidate count 未超過 reviewed subscription budget。

執行順序：

```text
atomic projection evaluation
        ↓
triggered decisions
        ↓
SessionCandidateGate(symbol)
        ↓ allowed only
fresh BidAsk preparation
        ↓
Hard Risk / Local Paper intent
```

Intent evidence 必須同時 pin：

- exact Strategy Set/pipeline digest
- atomic decision digest
- candidate batch artifact ID/digest
- candidate entry digest/rank
- gate mode/version/decision digest
- source session/target session

Exit criteria：

- triggered 但不在名單內：`BLOCKED_CANDIDATE_GATE`，零 intent。
- 在名單內但 atomic 未觸發：`WAITING_SIGNAL`，零 intent。
- stale/missing/wrong-session batch：start 或 entry fail closed，零 intent。
- allowed symbol 仍必須通過 fresh BidAsk、Hard Risk、cash/daily limit、idempotency。
- controller restart 從 checkpoint 恢復同一 batch digest；digest 漂移拒絕 resume。
- raw strategy-intent HTTP route 仍為 404。

### PR-MVP-PM-005 — Controlled subscription and Paper rollout

目標：在 owner 明確啟用時，讓 approved FinMind candidates 進入 live observation subscription，並完成端到端 local-paper rehearsal。

預計檔案：

- 新增 `dashboard/candidate_composition.py`
- `dashboard/momentum.py`
  - preserve declared source; 不再將所有 composite rows 強制轉成 `AUTO`
- `runtime/momentum_shadow.py`
- `market_data/subscriptions.py`（預期只補 evidence/test，不改 capacity semantics）
- end-to-end tests

Feature flag：

```text
FINMIND_INSTITUTIONAL_MVP_ENABLED=false
FINMIND_INSTITUTIONAL_MVP_PAPER_GATE_ENABLED=false
FINMIND_INSTITUTIONAL_MVP_MAX_CANDIDATES=20
```

第一階段只開第一個 flag，顯示／shadow；第二階段才由 operator 同時啟用 paper gate。實單路徑沒有對應 flag。

Exit criteria：

- manual/position/active episode 保有既有 capacity 優先權。
- candidate cap、subscription headroom 與 eviction reason 清楚可見。
- provider subscription 失敗不會繞過 candidate gate 或下單。
- full Paper rehearsal 完整保存 Candidate → Atomic Decision → Intent → Risk → Order → Fill → Position → Exit lineage。

### PR-MVP-PM-006 — Metrics and decision gate

目標：累積 MVP evidence，決定是否值得進一步做正式 backtest／PR-008 bridge；不在這個 PR 偷看後修改已執行 session 的規則。

至少保存：

- 每日候選數與 market 分布
- source readiness/staleness/mapping exclusions
- atomic triggered / candidate-gate blocked counts
- quote/risk/order rejection reasons
- paper fills、closed positions、日內 PnL（僅 Paper 結果）
- baseline exact Strategy Set identity與 candidate policy digest

評估方式：

- 先累積至少 20 個交易日 observation。
- 再累積至少 20 個交易日 Local Paper，規則期間內不變。
- 比較 `price-only exact set` 與 `FinMind candidate gate + same exact set`，兩邊使用同一風控與費用設定。
- 結果只標示 MVP evidence；正式 PIT/holdout 仍走原 PR-008。

## 5. Test plan

### Unit

- dealer component/fallback semantics，不重複計算。
- source → next reviewed session resolution。
- artifact canonical digest/idempotency/conflict。
- candidate source/rank/TTL/entry digest mapping。
- gate allowed/not-allowed/stale/wrong-session。
- feature flag default-off。

### Integration

- fake FinMind provider → immutable batch，零網路測試。
- batch → CandidatePool union → shadow metrics。
- Dashboard GET/UI projection 不觸發 provider。
- exact atomic trigger + candidate allowed → one Local Paper intent。
- exact atomic trigger + candidate rejected → zero intent。
- restart/checkpoint digest drift → fail closed。

### Regression

- existing formal institutional prior/shadow tests。
- CandidatePool/scanner/manual/position tests。
- atomic strategy publish/set/paper activation tests。
- continuous local-paper/RiskGate/order recovery/no-overnight tests。
- dashboard simulation CSRF and disabled raw intent route tests。

建議 verification：

```text
pytest -q tests/test_finmind_institutional_mvp.py ...new MVP tests...
pytest -q tests/test_candidate_pool.py tests/test_institutional_candidate_shadow_admission.py
pytest -q tests/test_atomic_paper_runtime.py tests/test_continuous_paper_strategy.py
pytest -q tests/test_dashboard_simulation_api.py tests/test_recoverable_simulation_orders.py
python -m py_compile <changed Python files>
ruff check <changed Python files>  # only if Ruff is installed
git diff --check
```

## 6. Rollout gates

```text
G0  Daily CLI + immutable artifact replay
        ↓
G1  Read-only Dashboard + shadow admission
        ↓ owner approval
G2  Session-pinned candidate gate, decision-only
        ↓ owner approval
G3  Local Paper automated intents
        ↓ 20+ trading sessions and review
G4  Decide whether to fund formal historical/PIT evaluation
```

任何 gate 失敗只關閉 FinMind MVP path；不得把 stale batch 當作 empty batch，也不得自動退回 price-only mode 後繼續送單。

## 7. Explicit non-goals

- 不把 FinMind MVP 宣稱為正式 PIT universe。
- 不修改 PR-008 protocol/coverage/holdout digest。
- 不用 T 日收盤後法人資料產生 T 日進場。
- 不建立 FinMind 直接買入策略。
- 不新增或恢復 raw strategy-intent HTTP endpoint。
- 不開放 broker real-money order。
- 不在本階段建立嵌入式每日 scheduler；先用 explicit one-shot CLI。

## 8. Recommended implementation order

先做 PR-MVP-PM-001、002、003。這三個 PR 完成後，使用者已能每天取得並查看盤前法人名單，且沒有任何策略副作用。通過 observation review 後再做 PR-MVP-PM-004、005，把名單變成 Local Paper 的 session-pinned eligibility gate。最後用 PR-MVP-PM-006 決定是否值得投入正式歷史/PIT研究。
