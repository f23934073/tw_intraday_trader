# Local Paper 證交稅與滑價模型 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`
- 規劃日期：`2026-08-26`
- 執行模式：`LOCAL_PAPER_SIMULATION`
- 交易時段需求：程式實作與自動測試不需要等開盤；真實滑價校準另案，需要多個交易時段 evidence
- 預估工期：4.5～6 個開發日，另加 0.5～1 日獨立 review
- 安全邊界：不新增 Shioaji／券商下單、帳務、CA、trade callback 或 real-money authority

## 1. 結論先講

目前 Local Paper 已有：

- BUY 用 best ask、SELL 用 best bid 的本機撮合；
- best-level volume 限制與 partial fill；
- 買賣手續費、現金、已實現損益；
- Journal、checkpoint、重啟復原與 settings 換 session。

尚缺兩項：

1. SELL 成交未扣證券交易稅。
2. 成交價沒有 BBO 之外的額外不利滑價。

這份計畫完成後，新建立的 Local Paper v2 session 會：

- 只對已證明為 TWSE／TPEX 普通股、現股、非當沖的 SELL fill 課 3‰；
- 以固定 adverse bps 對 BUY/SELL 加入不利滑價，並對齊台股合法升降單位；
- 在 slippage-adjusted price 超出 limit 時維持 pending，不偽造成交；
- 把 gross、commission、tax、net cash effect、BBO reference、slippage 與 policy identity 寫入 immutable fill event；
- 重播時直接使用事件內的已定案金額，不以新政策回算舊交易；
- 保留「沒有真實排隊順位／market impact，不能代表券商成交」的限制。

## 2. 現況與主要缺口

### 2.1 Current source

| 能力 | Current source | 現況 |
|---|---|---|
| Runtime settings | `simulation/settings.py` | `local-paper-settings-v1`；可編輯 cash、daily limit、commission rate/minimum，無 tax/slippage/policy identity |
| 撮合 | `simulation/service.py` | submit、snapshot reconcile、quote worker 三條路徑；BUY=ask、SELL=bid，raw price 達 limit 即成交 |
| 訂單／持倉 | `simulation/models.py` | 保存 fill price/notional/commission；無 tax、reference price、slippage evidence |
| 現金／PnL | `simulation/service.py::_fill` | BUY=`gross+commission`；SELL=`gross-commission`；realized PnL 未扣 tax |
| Journal/replay | `trading/local_paper.py` | `local_paper_fill.v1/v2`；v2 有 gross/commission/net/settings digest，無 tax/slippage/policy versions |
| Composition | `runtime/composition.py` | session metadata pin settings digest；目前 rounding 是 `ROUND_HALF_UP_0.01_TWD` |
| API/UI | `dashboard/server.py`、`dashboard/static/` | settings draft/apply/new-session 已可用；commission 仍可自由編輯 |
| Backtest | `backtest/` | 已有獨立的 fixed sell tax/slippage；但使用 Kbar raw price，沒有 BBO、limit、tick-size 語意 |

### 2.2 P0 gaps

1. **商品分類不足**：Local Paper 只有 symbol/name/market，無法證明普通股或排除 ETF／權證。不能把 3‰ 與普通股 tick table 套到未知商品。
2. **規格版本衝突**：現行 commission 是 cents `ROUND_HALF_UP`，但較新的 `architecture/asset_portfolio_dual_mode_implementation_report.md` 已凍結 `tw_stock_standard_v1`／`twd_round_down_v1`。
3. **三條撮合路徑可能不一致**：slippage 若分散加入，submit、snapshot、quote worker 很容易有一路漏套。
4. **Journal schema 不足**：fill.v2 不能證明 tax/slippage，也不能安全地 silent-widen。
5. **滑價尚未校準**：backtest 的 5 bps 可作為明示假設，不能宣稱是台股即時成交的實證值。

## 3. Scope

### 3.1 In scope

- `TWSE_TPEX_COMMON_STOCK`、現股、非當沖 Local Paper。
- Frozen `FeePolicyV1=tw_stock_standard_v1`：
  - BUY/SELL commission rate `0.001425`；
  - order cumulative minimum commission `20 TWD`；
  - SELL tax rate `0.003`；
  - commission/tax `ROUND_DOWN` 至整元。
- `FixedAdverseSlippagePolicyV1`：session-pinned bps、普通股 tick-size adjustment、limit protection。
- 新 settings/session/fill schema、cash/PnL、Journal、checkpoint、replay、API/UI 與文件。
- Memory contract tests與 PostgreSQL restart UAT。

### 3.2 Non-goals

- 不實作 1.5‰ 現股當沖優惠；它需要同一券商／帳戶／營業日／標的資格及相同數量 lineage。
- 不支援 ETF、ETN、權證、債券、興櫃、零股專屬五檔或其他商品成本政策。
- 不模擬真實 queue priority、多檔深度、market impact、成交機率或 broker rebates。
- 不改變回測成交模型；本任務只做 Local Paper，避免把 Kbar 與 BBO execution 強行共用。
- 不修改舊 Journal monetary truth，不把 fill.v1/v2 升寫為 v3。
- 不建立真實下單、券商帳務或 real-money promotion path。

## 4. Frozen policy 與官方依據

### 4.1 證交稅

- 財政部《證券交易稅條例》第 2 條：公司股票由出賣人按每次實際成交價格課徵 3‰。
- 同條例第 2-2 條：合格現股當沖的 1.5‰ 優惠至 2027-12-31；本 plan 明確排除當沖，不提供 UI toggle。
- 財政部也明示證交稅以實際成交價格計算。

官方來源：

- [財政部主管法規共用系統：證券交易稅條例](https://law-out.mof.gov.tw/LawContent.aspx?KeyWord=&id=FL006079)
- [財政部稅務入口網：買賣股票](https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-knowledge/rwG2M1N)
- [TWSE：當日沖銷交易專區](https://www.twse.com.tw/zh/products/system/day-trading.html)

### 4.2 股票升降單位

普通股票價格級距：

| 價格 | Tick size |
|---:|---:|
| `< 10` | `0.01` |
| `10 <= price < 50` | `0.05` |
| `50 <= price < 100` | `0.1` |
| `100 <= price < 500` | `0.5` |
| `500 <= price < 1000` | `1` |
| `>= 1000` | `5` |

來源：[TWSE 集中市場交易制度介紹](https://www.twse.com.tw/zh/products/system/trading.html)

### 4.3 專案既有 frozen baseline

`architecture/asset_portfolio_dual_mode_implementation_report.md` 已把 Local Paper v1 成本範圍凍結為普通股、現股、非當沖，並指定：

```text
fee_policy_version      = tw_stock_standard_v1
rounding_policy_version = twd_round_down_v1
commission_rate         = 0.001425
minimum_commission      = 20 TWD
sell_tax_rate           = 0.003
money_quantum           = 1 TWD
commission_rounding     = ROUND_DOWN
tax_rounding            = ROUND_DOWN
```

這份 implementation 不重新討論上述值，只負責落實與版本化。

## 5. Target contracts

### 5.1 Instrument admission

新增 provider-neutral read-only descriptor：

```text
LocalPaperInstrumentDescriptorV1
  symbol
  exchange_raw
  security_type_raw
  normalized_product_class = COMMON_STOCK | UNSUPPORTED | UNKNOWN
  source_identity
```

規則：

1. `MarketDataProvider` 提供 optional descriptor method；default 是 unavailable，不猜測。
2. `MockProvider` 對固定測試股票回傳明確 common-stock fixture。
3. `ShioajiProvider` 只讀已載入的 contract catalog，正規化 exchange/security type；不呼叫 account、order 或額外 snapshot。
4. 只有明確 `TWSE/TPEX + COMMON_STOCK` 可以進入 v2 cost execution。
5. `UNKNOWN/UNSUPPORTED` 在 order admission 回 `UNSUPPORTED_COST_POLICY_SCOPE`，不 fallback 為 3‰。
6. Fill event 保存 raw descriptor snapshot/source identity，確保 audit 不依賴日後 catalog 狀態。

在實作前先以目前 pin 的 Shioaji SDK contract fixture，凍結 raw security-type mapping；未經測試的 raw value 不加入 allowlist。

### 5.2 Cost calculation

使用高精度 `Decimal`，任何 monetary result 先完整算完再 mutation：

```text
fill_gross = fill_price * fill_quantity

cumulative_raw_commission
  = cumulative_order_gross * 0.001425

cumulative_commission
  = max(20, ROUND_DOWN_TO_1_TWD(cumulative_raw_commission))
    when cumulative_order_gross > 0

commission_delta
  = cumulative_commission - already_booked_commission

fill_tax
  = 0                                      for BUY
  = ROUND_DOWN_TO_1_TWD(fill_gross * 0.003) for SELL

BUY net_cash_effect  = -(fill_gross + commission_delta)
SELL net_cash_effect = +(fill_gross - commission_delta - fill_tax)
```

Tax calculation unit 是一筆 immutable execution/fill event；`cumulative_order_tax` 只是已發生 fill tax 的加總，不重新 round。

Realized PnL：

```text
SELL realized_pnl_delta
  = (fill_price - average_entry_price) * quantity
    - allocated_entry_commission
    - exit_commission_delta
    - fill_tax
```

Slippage 已反映在 `fill_price`，不得再從 cash 或 PnL 另扣一次。

### 5.3 Fixed adverse slippage

新增獨立版本：

```text
slippage_policy_version = fixed_adverse_bps_v1
configured_slippage_bps = 5       # v2 draft default
allowed_range            = 0..100
calibration_status       = ASSUMPTION_NOT_LIVE_CALIBRATED
price_tick_policy        = tw_common_stock_tick_v1
```

Reference price：

- streaming BUY：best ask；`reference_source=BEST_ASK`
- streaming SELL：best bid；`reference_source=BEST_BID`
- Mock/snapshot compatibility：snapshot price；`reference_source=SNAPSHOT_COMPATIBILITY`

演算法：

```text
BUY raw_adverse_price  = reference_price * (1 + bps / 10000)
SELL raw_adverse_price = reference_price * (1 - bps / 10000)

BUY adjusted_price  = adverse ceiling to next valid common-stock tick
SELL adjusted_price = adverse floor to previous valid common-stock tick
```

限制：

1. Reference、limit 與 adjusted price 都必須符合普通股 tick policy。
2. `bps=0` 時 adjusted price 等於 reference，保留現有 BBO 行為。
3. BUY adjusted price `> limit` 或 SELL adjusted price `< limit`：不成交、不消耗 best-level volume，order 保持 pending，waiting reason=`SLIPPAGE_ADJUSTED_LIMIT_NOT_REACHED`。
4. 不把 adjusted price hard-cap 到 limit，因為 best-level evidence 無法證明 limit price 有可成交量。
5. `slippage_cost = abs(fill_price-reference_price) * quantity` 只作診斷；另存 realized slippage bps，不納入 explicit fee/tax totals。
6. 任一 Decimal/tick/policy/instrument integrity error：這次不成交並 fail closed；不可退回 raw BBO 成交。

### 5.4 Golden accounting example

使用普通股、`5 bps`、100 股：

```text
BUY reference=100.0
  raw adverse=100.05
  legal adjusted fill=100.5
  gross=10,050
  commission=max(20, floor(14.32125))=20
  cash debit=10,070

SELL reference=110.0
  raw adverse=109.945
  legal adjusted fill=109.5
  gross=10,950
  commission=max(20, floor(15.60375))=20
  tax=floor(32.85)=32
  cash credit=10,898

realized PnL
  = (109.5-100.5)*100 - 20 - 20 - 32
  = 828
```

BUY limit 至少需 `100.5`，SELL limit 至多需 `109.5`；否則保持 pending。

### 5.5 Fill event v3

新增 `local_paper_fill.v3`，不要修改 v1/v2 fingerprint。Payload 至少包含：

```text
order_id, fill_sequence, symbol, name, side
quantity_shares, fill_price
reference_price, reference_source
configured_slippage_bps, realized_slippage_bps, slippage_cost
gross_amount
commission, cumulative_order_commission
tax, cumulative_order_tax
net_cash_effect
fee_policy_version, rounding_policy_version
slippage_policy_version, price_tick_policy_version
settings_digest
instrument_descriptor_snapshot, instrument_descriptor_digest
fill_source, provider_identity, execution_authority=false
```

Validation：

- BUY tax 必須是 0；SELL net cash 必須等於 gross - commission - tax。
- Stored price 必須是合法 tick 且未違反 limit。
- `slippage_cost` 必須能由 stored reference/fill/quantity 重建，但 replay 不把它再扣款。
- v3 缺 policy identity、descriptor、tax 或 reference evidence 時，recovery 失敗；不可降級成 v2。
- Reducer 使用 persisted gross/commission/tax/net truth；calculator 只供新 fill 與 audit test。

### 5.6 Settings v2

`local-paper-settings-v2` 可編輯：

- `starting_cash_twd`
- `max_daily_buy_notional_twd`
- `slippage_bps`

唯讀且納入 digest/session metadata：

- `security_scope=TWSE_TPEX_COMMON_STOCK`
- `order_condition=CASH`
- `day_trade=false`
- `commission_rate=0.001425`
- `minimum_commission_twd=20`
- `sell_tax_rate=0.003`
- fee/rounding/slippage/tick policy versions
- `calibration_status=ASSUMPTION_NOT_LIVE_CALIBRATED`

UI 不再把 commission/tax 顯示為可任意調整的情境參數。未來若要支援券商折扣，應新增 explicit `commission_discount` 與新的 policy version，不能改寫 `tw_stock_standard_v1`。

### 5.7 Migration and compatibility

1. Reader 同時支援 settings v1/v2、fill v1/v2/v3。
2. v1 settings file 不在啟動時自動改寫；舊 active session 繼續按 persisted v1/v2 金額 replay。
3. 第一次開啟 v2 settings 時，draft 只沿用 v1 的 starting cash/daily limit；fee policy 改為 frozen standard，slippage default 5 bps，畫面明示尚未套用。
4. Operator 按「套用並建立新帳戶」後才建立 v2 session；沿用既有 active-order/position confirmation 與 archive lifecycle。
5. v2 session metadata 必須完整匹配 settings digest/policy versions；partial binding 一律 fail closed。
6. 舊 session 不補 tax、不套 slippage、不重建 monetary fields。
7. v2 code rollback 時若 active session 已含 fill.v3，舊 binary 不可安全接管；停止 mutation、保留 Journal，採 forward fix 或部署支援 v3 reader 的版本。

## 6. Target data flow

```text
Order command
  -> Risk + instrument scope admission
  -> current snapshot/BidAsk reference
  -> FixedAdverseSlippagePolicyV1
  -> common-stock tick adjustment
  -> adjusted limit check
  -> best-level quantity decision
  -> immutable FillAccountingDecision
       gross / commission / tax / net cash
       reference / slippage / policies / descriptor
  -> apply Simulation order/cash/position state atomically in lock
  -> local_paper_fill.v3 Journal event
  -> verified checkpoint
  -> API/UI projections

Restart
  -> validate session metadata/settings digest
  -> replay v1/v2/v3 using persisted monetary truth
  -> verify checkpoint digest
  -> restore exact cash/positions/PnL/order cost totals
```

不新增第三條行情或成本 pipeline。

## 7. Implementation phases

### TS-000 — Rebase 與 scope guard（0.25～0.5 日）

前置：

- 在獨立 worktree/branch 實作；不直接改目前 dirty main worktree。
- 先做 `git status`、baseline focused tests 與 source snapshot。
- Core 工作可立即開始；進入 `simulation/application.py`、`runtime/composition.py`、`dashboard/server.py` 或 Dashboard 靜態檔前，先等正在執行的 Kill Switch candidate 穩定，再 rebase。
- Rebase 後重新盤點 API/UI/composition contract；不要覆蓋 Kill Switch durable-control changes。

Gate TS-G0：

- 變更範圍明確、沒有挾帶其他 dirty changes。
- Existing Local Paper focused suite baseline 結果已記錄。
- Kill Switch 重疊檔案已有確定 base。

### TS-001 — Instrument、cost 與 slippage pure domain（0.75～1 日，可立刻平行）

Files：

- `market_data/models.py`
- `market_data/provider.py`
- `simulation/execution_costs.py`（new）
- `tests/test_local_paper_execution_costs.py`（new）
- `tests/test_shioaji_provider.py`

Work：

- 加入 provider-neutral instrument descriptor與 default-unavailable provider seam。
- Mock/Shioaji adapter 提供 raw descriptor；凍結 explicit common-stock mapping。
- 實作 `tw_common_stock_tick_v1`：validity、adverse ceiling/floor、tier boundary。
- 實作 immutable `SlippageDecision` 與 `FillAccountingDecision`。
- 實作 frozen commission/tax/rounding kernel；全程 Decimal，拒絕 NaN/Infinity/negative。
- 不修改 backtest execution；必要時只用 golden vector 驗證 formula identity。

Tests：

- 所有 tick tiers 與 9.99/10/49.95/50/99.9/100/499.5/500/999/1000 boundaries。
- BUY ceiling、SELL floor、0 bps、1/5/100 bps。
- invalid tick/descriptor/unsupported product fail closed。
- commission minimum/cumulative delta、SELL-only tax、whole-TWD ROUND_DOWN。
- 本文件 golden example 精確相等。

Gate TS-G1：pure tests 全綠；無 float arithmetic；未知商品不會產生 cost decision。

### TS-002a — Simulation core 與 fill.v3（1～1.5 日，可在 TS-G1 後平行）

Files：

- `simulation/models.py`
- `simulation/service.py`
- `trading/local_paper.py`
- `tests/test_realtime_quote_stream.py`
- `tests/test_recoverable_simulation_orders.py`
- `tests/test_local_paper_projection.py`

Work：

- 在 order state 加 cumulative/last tax、reference、slippage diagnostic 與 policy identity。
- 把 submit、snapshot reconcile、quote worker 三條撮合入口集中到單一 execution decision。
- 先完整計算 decision，再在同一 lock 更新 cash/order/position/PnL；任何錯誤不做 partial mutation。
- slippage 超限保持 pending；只有成功 fill 才消耗 best-level volume。
- BUY cash、SELL cash、realized PnL 納入 persisted commission/tax，slippage 不重扣。
- 加入 fill.v3 writer/reader/projector/digest，v1/v2 reader 保持原義。
- 更新 order/session/position projection，分開呈現 explicit tax/fee 與 diagnostic slippage。

Tests：

- zero-bps compatibility、BUY/SELL adverse fill、limit miss、stale book、zero volume。
- partial fill 逐筆 tax、order cumulative commission/tax、cancel/retry remainder。
- odd lot、minimum commission、daily buy budget、cash reservation。
- tampered v3 tax/net/reference/policy/descriptor 皆 recovery error。
- v1/v2 golden Journal replay 結果完全不變。
- cash/PnL/slippage no-double-count conservation properties。

Gate TS-G2：同一 Journal replay 三次的 cash、positions、realized PnL、order totals、projection digest 完全相同。

### TS-002b — Journal-first application integration（0.5 日；Kill Switch rebase 後）

Files：

- `simulation/application.py`
- `runtime/composition.py`
- `tests/test_runtime_composition.py`
- `tests/test_strategy_paper_flow.py`

Work：

- 讓 command outcome recorder 寫 fill.v3 完整 evidence。
- Session metadata pin settings/cost/slippage/tick versions與 descriptor policy。
- Recovery 把 tax/cost totals 還原至 SimulationService。
- 保留 Kill Switch final admission/control wiring；不覆蓋其 stable control session。
- Journal/checkpoint 失敗時沿用 fail-closed `RECOVERY_REQUIRED`，不得 fallback 為 v2 或 memory。

Gate TS-G2b：重啟後 exact state 與 Journal 一致；Kill Switch engage/restart tests 仍綠。

### TS-003 — Settings v2、API 與 Dashboard（1～1.25 日；與 Kill Switch UI 串行）

Files：

- `config/local_paper.py`
- `simulation/settings.py`
- `dashboard/server.py`
- `dashboard/static/index.html`
- `dashboard/static/js/app.js`
- `dashboard/static/js/workspaces/simulation.js`
- `tests/test_local_paper_settings.py`
- `tests/test_dashboard_simulation_api.py`
- `tests/test_dashboard_module_structure.py`

Work：

- 加入 v1/v2 reader、v2 draft/apply/new-session migration。
- v2 只允許編輯 cash/daily limit/slippage bps；顯示 frozen fee/tax/rounding policy。
- 顯示 `5 bps（尚未用實盤校準）`，不可標示為預測或保證成交成本。
- Session/order/detail 顯示累積 commission、tax、reference price、fill price、diagnostic slippage。
- API 使用 Decimal string，禁止 frontend round-trip float 改變 digest。
- 沿用 optimistic revision、CSRF、loopback、apply blockers與 replacement handoff。
- 更新 static asset version，避免舊 browser bundle 對新 schema。

Gate TS-G3：v1 settings 啟動不改檔；顯式 apply 才建立 v2；兩 tabs stale revision 回 409；UI 可清楚分辨稅費與滑價假設。

### TS-004 — Verification、PostgreSQL UAT 與文件（1～1.25 日）

Files：

- `tests/test_local_paper_postgres.py` 或現有 PostgreSQL Local Paper suite
- `README.md`
- 必要的 runbook/evidence Markdown

Verification：

1. Focused domain/service/Journal/settings/API/UI tests。
2. 完整 regression suite、compile、JS syntax、`git diff --check`。
3. Disposable PostgreSQL：
   - 建 v2 session；
   - BUY partial fills；
   - SELL partial/full fills；
   - 關閉 runtime；
   - 使用新 connection 重建至少三次；
   - 每次比較 session metadata、Journal kinds、checkpoint digest、cash、positions、realized PnL、commission/tax/slippage totals。
4. Failure injection：corrupt v3 payload、settings digest mismatch、unsupported product、Journal append/checkpoint failure。
5. Re-run Kill Switch focused tests，確認兩項工作整合後 final admission/recovery 仍 fail closed。

Documentation：

- README 改為「已納入普通股非當沖 3‰ tax 與固定 adverse slippage」。
- 繼續明示沒有真實排隊、market impact、券商 accounting 或 real-money authority。
- 記錄政策版本、migration、UAT command/result/artifact path。

Gate TS-G4：PostgreSQL UAT 必須實際 PASS；缺 DSN 的 skip 只能算 focused/no-DSN check，不得標為正式完成。

### TS-005 — Independent review（0.5～1 日）

Review checklist：

- policy/version/source 是否一致；
- product classification 是否 fail closed；
- tax/slippage 是否在 cash/PnL double count；
- limit/tick/partial fill 是否 deterministic；
- v1/v2 replay 是否完全相容；
- Kill Switch integration 是否保留；
- PostgreSQL evidence 是否來自新 connection/restart；
- UI 是否沒有誤導為真實券商成本。

Gate TS-G5：無 P1/P2 correctness finding，才能標記 Local Paper tax/slippage implementation complete。

## 8. 可平行與必須串行的工作

| 工作 | 與目前 Kill Switch 同時做 | 原因 |
|---|---|---|
| TS-001 instrument/cost/slippage pure domain | 可以 | 新檔與 provider seam 為主，衝突低 |
| TS-002a models/service/fill.v3 core | 可以，但保持 scoped commits | 主要不碰 Dashboard/composition；`simulation/service.py` 需留意對方實際 diff |
| Pure tests、golden vectors、PostgreSQL UAT fixture 準備 | 可以 | 可先準備，正式 UAT 等整合完成 |
| `simulation/application.py`、`runtime/composition.py` | 等 Kill Switch candidate 穩定後 | 兩任務都會改 Journal/recovery/admission wiring |
| `dashboard/server.py`、Simulation settings UI | 等 Kill Switch UI 穩定後 | 高機率同區塊衝突 |
| 最終 full regression/PostgreSQL UAT/review | 必須在合併後 | 要驗證兩項安全功能的組合行為 |

建議日程：

| 時間 | Tax/slippage task | Kill Switch task |
|---|---|---|
| Day 1 | TS-000、TS-001 | 繼續 durable core |
| Day 2 | TS-002a core/tests | composition/API/UI |
| Day 3 | 等 candidate 後 rebase，TS-002b | focused verification |
| Day 4 | TS-003 settings/API/UI | review/fixes |
| Day 5 | TS-004 PostgreSQL UAT/full regression | 合併後共同 regression |
| Day 5.5～7 | TS-005 independent review/fixes | 必要時共同修正 |

## 9. Test matrix

### Domain

- common stock descriptor allow；unknown/ETF/warrant deny。
- tick validity 與所有 tier boundaries。
- BUY/SELL adverse rounding，0/1/5/100 bps。
- invalid/negative/NaN/Infinity bps、price、gross、rate。
- frozen commission/tax rounding與 golden accounting example。

### Execution

- Raw BBO 達 limit，但 adjusted price 超限：pending、volume 不減。
- Adjusted price等於 limit：依可見 best-level volume partial fill。
- 多次 BidAsk、out-of-order/stale book、zero volume。
- snapshot compatibility 明示 reference source。
- BUY reservation 足以支付 limit gross + commission；SELL tax 不會使 cash credit 為負而未被偵測。

### Accounting

- BUY tax 永遠 0；SELL tax 唯一扣一次。
- Commission cumulative minimum 只收一次，不因 partial fill 重複收 20 元。
- Slippage 已在 price，不再進 explicit cash debit/credit。
- Partial sell allocation、full close、multiple symbols、odd lots。
- `cash + market value`、realized/unrealized/daily loss invariants。

### Journal/recovery

- v1/v2 legacy fixtures不變。
- v3 round-trip、tamper detection、idempotent append。
- settings/policy/descriptor digest mismatch fail closed。
- checkpoint before/after partial fill；三次 new-process reconstruction。
- PostgreSQL migration/connection failure不 fallback memory。

### API/UI

- v1 draft migration、v2 apply、stale revision 409、active position confirmation。
- Frozen fee fields read-only；slippage range validation 422。
- Order/session projection顯示 commission/tax/slippage 分類。
- Browser bundle/cache version、keyboard/focus、錯誤訊息與安全 disclosure。

## 10. Rollout and rollback

### Rollout

1. 先發布 v1/v2/v3 reader 與 pure calculator，不切 active session。
2. 在 memory/Mock 建 v2 smoke session。
3. 在 disposable PostgreSQL 完成 UAT。
4. Operator 顯式 apply，建立新的 v2 Local Paper session。
5. 先以 `slippage_bps=5` 收集 Local Paper evidence；畫面持續標示未校準。
6. 真實滑價 calibration 另開 evidence task，至少跨多個交易日、流動性層級與 opening/continuous/close 時段，再考慮新 policy version。

### Rollback

- Apply 前：可直接停用新 UI；舊 v1 session不受影響。
- 已建立 v2 但尚無 fill.v3：封存 v2 session並切回舊 active pointer，保留 Journal。
- 已有 fill.v3：不得讓不支援 v3 的舊 binary 接管；停止 mutation，保留 evidence，部署 forward fix 或支援 v3 reader 的版本。
- 任何 rollback 都不刪 Journal、不回算 monetary values、不重用已封存 session ID。

## 11. Definition of Done

- [ ] 只有可證明的 TWSE/TPEX ordinary stock 能使用新成本政策。
- [ ] BUY/SELL slippage 使用同一 pure decision，合法 tick 且不突破 limit。
- [ ] SELL tax、commission、cash、PnL 與 partial fills 全部 Decimal deterministic。
- [ ] Slippage 不會被現金／PnL double count。
- [ ] fill.v3 完整保存 monetary truth、reference、slippage、policy與 descriptor evidence。
- [ ] v1/v2 history replay 完全不變；v3 tamper fail closed。
- [ ] settings v1 不自動改寫；顯式 apply 才建立 v2 session。
- [ ] Kill Switch durable/restart/final-admission tests 仍通過。
- [ ] Focused/full/static checks 全綠。
- [ ] PostgreSQL new-connection restart UAT 實際通過；不是 skip/waiver。
- [ ] README 仍明示 local-only、無 queue/market-impact/broker authority。
- [ ] Independent review 無未解 P1/P2 correctness finding。

## 12. 獨立任務啟動提示詞

```text
請依 architecture/local_paper_tax_slippage_implementation_plan.md 實作 Local Paper 證交稅與固定 adverse slippage。

執行限制：
1. 先建立獨立 worktree/branch，不要直接改目前 dirty main worktree。
2. 先確認正在進行的 Local Paper Kill Switch candidate 狀態。TS-001 與 TS-002a core 可先做；進入 simulation/application.py、runtime/composition.py、dashboard/server.py、dashboard/static/index.html、dashboard/static/js/workspaces/simulation.js 前，必須以穩定的 Kill Switch candidate rebase，保留 durable control/final admission。
3. 嚴格遵守 plan 的 common-stock、cash、non-day-trade scope；未知商品、ETF、權證不得 fallback 套 3‰。
4. 不修改舊 fill.v1/v2 monetary truth；新增 fill.v3 與 settings v2。
5. Slippage 只反映在 fill price，不能再次從 cash/PnL 扣除；adjusted price 超限時保持 pending且不消耗 book volume。
6. 不新增 Shioaji/order/account/CA/trade callback 或 real-money path。
7. 每完成一個 Gate 更新 isolated planning files，執行對應 focused tests；最後必須跑 full regression、JS/static checks、git diff --check 與實際 PostgreSQL restart UAT。
8. 缺 PostgreSQL DSN、只跑 memory、suite skip 或 waiver 都不能宣稱 TS-G4 PASS。
9. 不 push，除非使用者另外明確授權。

交付時回報：
- 實際修改檔案與 policy/schema versions；
- 每個 TS Gate 結果；
- PostgreSQL UAT command、結果與 evidence path；
- Kill Switch 組合 regression；
- 尚未完成的真實滑價 calibration（不得包裝成已完成）。
```
