# 資產與持倉三模式功能與 Phase 0 Contract Freeze 報告

- 狀態：**Approved**；`FeePolicyV1`／`RoundingPolicyV1` 已 `FROZEN`，`FreshnessPolicyV1` 仍為唯一 `BLOCKING_EVIDENCE`；`Phase 0: NOT COMPLETE`、`Phase 1: BLOCKED`
- 文件版本：`portfolio-contract-v0.4`
- 日期：2026-08-19（Asia/Taipei）
- 專案：`tw_intraday_trader`
- 目標：在同一個 Dashboard 提供 `LOCAL_PAPER`、`SHIOAJI_SIMULATION`、`BROKER_REAL` 三種帳戶模式的資產、持倉、委託、成交與損益功能，所有 mutation 都經過一致的購買力、持倉、資料健康、Journal 與 concurrency 契約

## 1. 結論

這個功能不需要從零開始。專案已經具備本機模擬現金、限價委託、持倉、即時 Tick／BidAsk 估值、RiskGate、append-only Journal、recovery 與 PostgreSQL adapter 的大部分基礎；目前的問題是這些能力還沒有收斂成同一條正式的資產／下單路徑。

本報告的整體架構已核准：建立一個統一的 `Portfolio` bounded context，對外提供相同的 read model，但保留三個完全隔離的 execution adapters：

```text
                         Dashboard
                             │
                 PortfolioQuery / OrderCommand
                             │
                    OrderApplicationService
                             │
              PortfolioSnapshot → RiskGate → Journal
                             │ approved
          ┌──────────────────┼──────────────────┐
          │                  │                  │
 LocalPaperBroker   ShioajiSimulation   ProductionShioajiBroker
  本機 deterministic       券商模擬環境           真實券商環境
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ↓
                  Orders / Fills / Cash Ledger
                             ↓
                     PortfolioProjection
                             │
                 Tick／BidAsk 即時市值與損益
```

第一版固定只支援台股現股、long-only、`COMMON`、`LMT`、`ROD`。Domain 必須驗證 `quantity_shares > 0` 且 `quantity_shares % 1000 == 0`；零股、融資、融券、當沖與市價單明確拒絕，不可只靠 UI 限制，也不可在 Position 計算中偷偷支援同日買賣。

「即時模式」在 UI 改名為「真實帳戶」，避免把即時行情誤認為真實券商資產。`SHIOAJI_SIMULATION` 是獨立 execution mode，不得與本機紙上撮合或真實帳戶混在一起。第一輪仍不允許真錢委託；即使 Phase 0～4 全部通過，也不會自動解鎖 Phase 5。

## 2. 目前專案已有的能力

### 2.1 可直接沿用

- `simulation/service.py`
  - 預設虛擬現金 1,000 萬元。
  - 支援 BUY／SELL、整張限價單、取消、冪等 key。
  - 成交後維護加權平均成本、現金、持倉及已實現／未實現損益。
  - Shioaji 模式以 BidAsk 判斷可成交價格，Tick 更新市值。
  - callback 只 enqueue，背景 worker 才改狀態，方向正確。
- `dashboard/server.py` 與 `dashboard/static/index.html`
  - 已有 session、projection、orders、positions API。
  - 已有模擬下單、取消、委託與持倉 UI。
  - 持倉已顯示平均成交價、最新價、市值、未實現損益與百分比。
- `trading/risk.py`
  - 已有現金、持倉、pending quantity、單筆額度、部位額度、日損失、資料健康、market open 與 stale book 檢核。
- `trading/application.py`、`trading/journal.py`、`trading/local_paper.py`
  - 已有 journal-first command application、冪等、失敗恢復分類、fill-derived projection 與 checkpoint digest。
- `trading/postgres_journal.py`、`trading/migrations/001_journal.sql`
  - 已有可持久化的 Journal／projection checkpoint adapter。
- `runtime/composition.py`
  - 已有 composition root，可在這裡注入不同 mode 的 adapters。

### 2.2 現況驗證

本次以目前 working tree 執行下列 focused tests：

```text
tests/test_simulation_service.py
tests/test_dashboard_simulation_api.py
tests/test_risk_gate.py
tests/test_order_application.py
tests/test_local_paper_projection.py
tests/test_command_recovery.py

31 passed in 0.30s
```

目前 `.venv` 安裝的 Shioaji 版本是 `1.7.2`。

## 3. 已確認的功能缺口與風險

### 3.1 合併後的最終 P0 contract amendments

| P0 | 凍結契約 | 最終結論 |
|---|---|---|
| P0-1 | Account Mode | `LOCAL_PAPER`／`SHIOAJI_SIMULATION`／`BROKER_REAL` 三種正式 mode |
| P0-2 | Order scope validation | `COMMON` 由 domain 強制 `quantity_shares % 1000 == 0`，不可只靠 UI |
| P0-3 | Fee Policy v1 | 已凍結 `tw_stock_standard_v1`：標準費率、折扣、最低手續費、稅率、calculation unit、rounding、effective date 與 source references |
| P0-4 | Freshness Policy v1 | UI／Risk、Tick／BidAsk、quote／broker accounting 分離；threshold 必須由 calibration evidence 核准，不得猜值 |
| P0-5 | Reservation model | `CashReservation`／`PositionReservation` 與 `CashLedgerEntry` 分離；reservation 不是現金異動 |
| P0-6 | Concurrency | `portfolio_revision` 只做 optimistic UX；資產 correctness 使用 account-level DB transaction／lock |
| P0-7 | Authority | 三種 mode 各自定義 execution、accounting、position 與 local Journal authority |
| P0-8 | Unknown broker side effect | Order lifecycle 增加 `SUBMIT_UNKNOWN`；未 reconcile 前禁止盲目 retry |
| P0-9 | Sell availability | 不把 broker 尚未反映的今日 BUY 加入可賣量；同日買賣／當沖維持不支援 |
| P0-10 | Persistence failure | PostgreSQL 不可用時所有 mutation fail closed；query 只能回最後 verified projection 並標示 stale／degraded |
| P0-11 | Revision validation | account row lock 後、RiskGate 前，必須在同一 transaction 比對 request revision；不符即 rollback 並回 HTTP 409 |
| P0-12 | LOCAL_PAPER ROD expiry | 交易日結束後執行 deterministic、idempotent EOD sweep；未成交餘量轉 `EXPIRED` 並在同一 transaction 釋放 reservation |
| P0-13 | Account close invariant | `CLOSED` 前必須所有 order terminal、active reservations 為零且無待 reconcile side effect；不允許 silent forced-close |
| P0-14 | EOD trigger ownership | 有 DB lease 的 in-process maintenance scheduler 在 `expires_at` 到達後觸發，與 restart catch-up 共用同一個冪等 sweep use case |

### 3.2 Phase 0 Freeze Ledger

| Contract | 狀態 | Phase 1 前的完成條件 |
|---|---|---|
| AccountMode／Authority Matrix | `FROZEN` | 三種 mode 不再合併或隱式切換 |
| PortfolioAccount initialization | `FROZEN` | 正式使用 `INITIALIZING`；startup gate 前禁止使用者 mutation |
| COMMON domain validation | `FROZEN` | constructor／domain tests 可直接驗證 1000 股倍數 |
| Cash／Position Reservation | `FROZEN` | 與 ledger 分離，create／consume／release events 明確 |
| Historical monetary replay | `FROZEN` | reducer 使用 persisted event values；policy 重算只做 audit validation |
| Concurrency／account lock | `FROZEN` | revision 只做 UX；DB transaction 是 correctness boundary |
| Revision check inside transaction | `FROZEN` | row lock 後、RiskGate 前比對；不符 rollback + HTTP 409 |
| Order lifecycle／`SUBMIT_UNKNOWN` | `FROZEN` | unknown side effect 只能 reconcile，不得 retry |
| LOCAL_PAPER ROD EOD sweep | `FROZEN` | 收盤後未成交餘量轉 `EXPIRED`，reservation 與 revision 原子更新，restart 可補跑 |
| LOCAL_PAPER `PENDING_SUBMIT` recovery | `FROZEN` | 同 session 可冪等恢復；跨 `expires_at` 只能 expiry，不讀下一日 quote |
| Account close／`CLOSED` preconditions | `FROZEN` | 所有 order terminal、active reservations = 0、無 `SUBMIT_UNKNOWN`／待對帳 side effect 才能關閉 |
| EOD scheduler／trigger ownership | `FROZEN` | in-process scheduler + DB lease；timer、maintenance backstop 與 restart 都呼叫同一 idempotent use case |
| Sell availability／day-trade policy | `FROZEN` | broker lag 不加回可賣量；same-day sell disabled |
| Persistence failure | `FROZEN` | DB outage query-only；所有 mutation fail closed |
| Reconciliation cancel semantics | `FROZEN` | broker state unknown 時 reconcile-first |
| FeePolicyV1／RoundingPolicyV1 | `FROZEN` | `tw_stock_standard_v1`；標準費率、最低收費、股票交易稅、整元 ROUND_DOWN 與來源已定案 |
| FreshnessPolicyV1 | `BLOCKING_EVIDENCE` | 所有 UI／Risk／broker threshold 依用途 SLA 凍結為明確毫秒值 |

`BLOCKING_EVIDENCE` 不是交給 Phase 1 猜預設值。現在只有 `FreshnessPolicyV1` 尚未 `FROZEN`；必須先完成第 5.5 節 calibration、保存 evidence artifact 並核准 thresholds，Phase 1 才能開始。

### 3.3 目前 implementation 與 P0 contract 的差距

1. **未成交買單沒有預留現金**：多筆掛單目前可以各自通過、合計超過總資產，直到撮合時才可能被拒絕。
2. **Web 下單繞過 RiskGate 與 Journal**：`/api/simulation/orders` 仍直接呼叫 `SimulationService.submit_order()`。
3. **模擬資產重啟即消失**：現金、委託、持倉、損益與冪等 key 都在 process memory。
4. **目前沒有 Shioaji account／order adapter**：現有 Provider 固定 `subscribe_trade=False`，沒有 CA、trade callback、order API 或 accounting reconciliation。
5. **真實可買金額不能只讀一個欄位**：銀行餘額、電子交易額度、T／T+1／T+2 交割款與 pending orders 必須分開保存證據。
6. **金額仍使用 `float`**：Phase 1 必須改成 `Decimal` 與穩定的 decimal-string serialization。

### P1：完整 MVP 應納入

- 只有 full fill，沒有 partial fill、cancelled remaining quantity、broker reject／expired／reconciliation-required。
- 不計手續費、最低手續費、折扣、證交稅與滑價。
- 沒有 cash ledger，無法解釋現金為何變動。
- 沒有模擬帳戶建立／重設／入金／出金 API。
- UI 只在下單提示列顯示可用虛擬現金，沒有完整資產總覽。
- 現有兩套 position model：`position/` 的決策 view 與 `simulation/` 的成交持倉；需要由統一 projection 產生前者，不能互相寫入。
- Simulation 行情 queue 是 unbounded `SimpleQueue`；若資產／下單被視為 operational state，overflow／stale 必須可觀測並 fail closed。
- 多 request／callback 的一致性目前只靠 process lock；切到 PostgreSQL 後需有 account-level transaction／optimistic revision。

## 4. 三模式與 Authority Matrix

| 項目 | `LOCAL_PAPER` | `SHIOAJI_SIMULATION` | `BROKER_REAL` |
|---|---|---|---|
| 初始現金／風險資本 | 使用者設定 | 建立 mode 時設定的 simulation risk capital，寫入 Journal；不可宣稱是 broker bank cash | 券商／銀行帳務讀取，不可手改 |
| 委託執行 | `LocalPaperBrokerAdapter` | Shioaji simulation order API | Production Shioaji order API；Phase 5 前停用 |
| 成交來源 | deterministic local fill model | Shioaji simulation order／deal event | Broker order／deal event |
| 持倉來源 | Journal 中已確認的 fills | broker simulation positions + fills reconcile | broker positions + fills reconcile |
| 即時估值 | Tick／BidAsk | Tick／BidAsk | Tick／BidAsk |
| 購買力 | cash balance - active reservations | Journal-derived simulation risk capital - active reservations；broker reject 仍是 execution truth | conservative broker buying-power evidence + local reservations |
| 重啟恢復 | Journal replay + checkpoint | Journal replay後與 Shioaji simulation reconcile | Journal replay後與 production broker reconcile |
| 可修改本金 | 只能走受控 ledger command | 不可手改 | 不可手改 |

### 4.1 Authority Matrix

| Mode | Execution authority | Accounting／position authority | PostgreSQL Journal 的角色 |
|---|---|---|---|
| `LOCAL_PAPER` | `LocalPaperBrokerAdapter` | Journal events + deterministic reducer | authoritative audit、recovery、cash/order/position projection |
| `SHIOAJI_SIMULATION` | Shioaji simulation | Orders／fills／positions 以 Shioaji simulation 為準；simulation risk capital 由本地 versioned ledger 管理 | audit、recovery、callback dedupe、risk-capital reducer 與 reconciled projection；不可覆蓋 broker execution truth |
| `BROKER_REAL` | Production broker | Broker account／positions／orders／fills | audit、recovery、local projection；差異只能 reconcile，不可自行改 broker truth |

「PostgreSQL Journal 是 authority」只完整適用於 `LOCAL_PAPER`。另外兩種 mode 的 broker side effect 與 broker account state 以 broker 為最終權威，Journal 負責證據、恢復、去重與本地 read model。

真實模式再拆兩個 capability，避免「能看資產」自動等於「能下真錢單」：

- `BROKER_ACCOUNT_READ_ENABLED`：讀取真實資產、庫存、委託與損益。
- `BROKER_LIVE_ORDER_ENABLED`：允許真實送單；預設必須是 `false`。

### 4.2 PortfolioAccount status contract

Account health 與 execution capability 是兩個維度；`READ_ONLY` 不是錯誤狀態，`DEGRADED` 也不能被當成可繼續沿用舊資料下單。

| Status | 觸發條件 | Query | Mutation／RiskGate |
|---|---|---|---|
| `INITIALIZING` | 新建 account，或 process startup 正在執行 Journal replay、checkpoint validation、broker reconciliation、EOD catch-up 與 freshness bootstrap | 可有限度回 last verified projection；新 account 無 verified projection 時只回 identity／progress，不產生估算帳務 | 所有使用者 mutation 回 `ACCOUNT_INITIALIZING`／`TEMPORARILY_UNAVAILABLE`；maintenance／recovery use case 可執行 |
| `ACTIVE` | persistence 可用、startup replay／reconciliation 完成，且 mode 所需 evidence 符合 active policy | 最新 verified projection | 仍須通過 mode capability、revision、freshness 與完整 RiskGate |
| `READ_ONLY` | policy／operator 主動關閉 risk-increasing mutation，例如 `BROKER_REAL` Phase 4、kill switch 或 live-order capability OFF；系統本身不必故障 | 允許，顯示 capability reason；background refresh／reconciliation 可繼續 | 新單、資本與帳戶 mutation 回 `ACCOUNT_READ_ONLY`／`POLICY_DISABLED`；只有明確 capability 允許且 broker state verified 的 cancel／reconcile 可繼續，不能只隱藏 UI 按鈕 |
| `DEGRADED` | DB、broker read source、quote connection 或 required evidence 暫時不可用／過期，但尚未發現帳務衝突或未知 broker side effect | 只回最後 verified projection，必須帶 `fresh=false`、`as_of`、stale reasons；health probe／refresh 可繼續 | 任何依賴失效 source 的 mutation fail closed；DB outage 時全部 mutation 拒絕。回最具體 reason（例如 `PERSISTENCE_UNAVAILABLE`），無專用 reason 才回 `ACCOUNT_DEGRADED`／`TEMPORARILY_UNAVAILABLE` |
| `RECONCILIATION_REQUIRED` | 已知 mismatch、callback gap、checkpoint parity failure，或 `SUBMIT_UNKNOWN` 造成可能存在未知 broker side effect | 允許，顯示差異與最後 verified source | 依第 5.10 節只允許 reconcile-first 的受限操作；禁止新 BUY／盲目 retry |
| `CLOSED` | 帳戶／session 已明確關閉；terminal | 只允許 audit／history | 全部 mutation 拒絕 |

State transition 必須保存原因、actor／source、occurred-at 與 revision：

```text
account create／process startup ─────────────────────────────→ INITIALIZING
INITIALIZING ── replay + checkpoint + reconcile + EOD catch-up
                 + freshness bootstrap verified ────────────→ ACTIVE or READ_ONLY
INITIALIZING ── source unavailable ──────────────────────────→ DEGRADED
INITIALIZING ── mismatch／unknown side effect ────────────────→ RECONCILIATION_REQUIRED
ACTIVE ── operator policy／kill switch ─────────────────────→ READ_ONLY
ACTIVE／READ_ONLY ── source unavailable／evidence stale ─────→ DEGRADED
ACTIVE／DEGRADED ── mismatch／unknown broker side effect ────→ RECONCILIATION_REQUIRED
DEGRADED ── source healthy + replay／refresh verified ───────→ previous policy state
RECONCILIATION_REQUIRED ── reconcile + checkpoint verified ─→ ACTIVE or READ_ONLY
ACTIVE／READ_ONLY ── close preconditions verified ───────────→ CLOSED
```

`DEGRADED` 只表示健康／可用性不足；一旦已知帳務衝突或送單結果不明，狀態必須升級為 `RECONCILIATION_REQUIRED`。恢復目標是 `ACTIVE` 還是 `READ_ONLY` 由 capability／operator policy 決定，不由 health probe 自行開啟下單。

### 4.3 CLOSED terminal invariant

第一版不提供 forced-close。`ClosePortfolioAccount` 必須取得 account row lock、執行 revision check，並在同一 transaction 重新驗證：

```text
all orders are terminal
  terminal = FILLED | CANCELLED | REJECTED | EXPIRED

active CashReservation count == 0
active PositionReservation count == 0
no PENDING_SUBMIT
no CANCEL_PENDING
no SUBMIT_UNKNOWN
reconciliation_status == VERIFIED
```

任何條件不成立都 rollback 並回 `ACCOUNT_CLOSE_BLOCKED`，列出 blocking order／reservation IDs；不能把 reservation 丟著、不能把 order 靜默改成 cancelled，也不能在 `DEGRADED`／`RECONCILIATION_REQUIRED` 中因為無法驗證就直接關閉。通過後 append `portfolio_account_closed.v1`、increment revision，才轉為 terminal `CLOSED`。

非零 settled position／cash balance 本身不阻擋 close；close 不是 liquidation，不產生虛構 fill 或 cash adjustment。`CLOSED` projection 只保留 close-time 的 immutable historical snapshot／audit view，不再接受行情 mark 或帳務 mutation。若需求是清空部位，必須在 close 前用正式 order／fill 流程完成。

「重設模擬帳戶」是 orchestration：先停止新單，對每筆未完成 `LOCAL_PAPER` order 走正常 cancel 或第 5.11 節 expiry，確認 reservation 歸零後再 close，最後建立新的 `INITIALIZING` account／session；舊 Journal 不覆寫。Broker mode 的 cancel 必須等 callback／reconciliation 確認 terminal，不能用 local forced-cancel 滿足 close precondition。

## 5. 核心 domain 與計算規則

### 5.1 建議資料模型

```text
AccountMode
  LOCAL_PAPER | SHIOAJI_SIMULATION | BROKER_REAL

PortfolioAccount
  account_id
  mode: AccountMode
  currency: TWD
  status: INITIALIZING | ACTIVE | READ_ONLY | DEGRADED
          | RECONCILIATION_REQUIRED | CLOSED
  revision

CashLedgerEntry
  entry_id, account_id, kind, amount, occurred_at, reference_id
  kind: INITIAL_CAPITAL | DEPOSIT | WITHDRAWAL | BUY_FILL | SELL_FILL
        | COMMISSION | TAX | ADJUSTMENT

CashReservation
  reservation_id, account_id, order_id
  original_amount, remaining_amount
  status: ACTIVE | PARTIALLY_CONSUMED | RELEASED | EXPIRED
  fee_policy_version, created_at, updated_at

PositionReservation
  reservation_id, account_id, order_id, symbol
  original_shares, remaining_shares
  status: ACTIVE | PARTIALLY_CONSUMED | RELEASED | EXPIRED
  created_at, updated_at

Order
  command_id, client_order_id, broker_order_id, account_id, mode
  symbol, side, order_lot, quantity_shares, remaining_shares
  limit_price, time_in_force, status
  trading_session_date, expires_at, submitted_at, updated_at, idempotency_key
  status: CREATED | PENDING_SUBMIT | SUBMITTED | ACCEPTED
          | PARTIALLY_FILLED | FILLED | CANCEL_PENDING | CANCELLED
          | REJECTED | EXPIRED | SUBMIT_UNKNOWN

Fill
  fill_id, order_id, broker_deal_id, quantity_shares, fill_price
  gross_amount, commission, tax, net_amount
  fee_policy_version, rounding_policy_version, occurred_at

Position
  account_id, symbol, order_cond, quantity_shares, available_to_sell_shares
  average_cost, cost_basis, market_price, market_value
  unrealized_pnl, unrealized_pnl_pct, realized_pnl
  quote_as_of, broker_as_of, reconciliation_status

FeePolicyV1
  commission_rate, commission_discount, minimum_commission
  sell_tax_rate, calculation_unit, rounding_policy_version
  effective_from, policy_version, source_reference

RoundingPolicyV1
  money_quantum
  commission_rounding_mode, tax_rounding_mode
  calculation_precision, average_cost_scale, pnl_display_scale
  policy_version

FreshnessPolicyV1
  ui_tick_stale_after_ms, ui_bidask_stale_after_ms
  risk_tick_stale_after_ms, risk_bidask_stale_after_ms
  broker_positions_stale_after_ms, broker_orders_stale_after_ms
  broker_accounting_stale_after_ms, buying_power_stale_after_ms
  policy_version

MarketDataHealth
  last_tick_market_at, last_tick_received_at
  last_bidask_market_at, last_bidask_received_at
  quote_connection_status, subscription_status
```

所有 `Money`／price／cost 使用 `Decimal`；API 使用 canonical decimal string，JavaScript 只做顯示，不當帳務權威。Reservation 是「可用資產的暫時占用」，不是已發生的現金流，因此不得以 `CashLedgerEntry` 的正負金額模擬 reservation。

### 5.2 Order scope 與整張驗證

`OrderCommand` constructor／domain validator 必須同時檢查：

```text
security_type == STOCK
order_condition == CASH
order_lot == COMMON
price_type == LIMIT
time_in_force == ROD
quantity_shares > 0
quantity_shares % 1000 == 0
limit_price > 0
```

任何一項不成立都在 adapter 前拒絕。UI 的 `step=1000` 或「張數」輸入只是 usability，不是安全邊界。第一版也不接受以今日已買進但 broker 尚未反映的庫存進行同日賣出。

### 5.3 Cash／Position Reservation

模擬帳戶現金：

```text
cash_balance
  = initial capital
  + deposits
  - withdrawals
  - settled buy fills
  + settled sell proceeds
  - commissions
  - taxes

active_cash_reservations
  = Σ(active BUY remaining notional + reserved fee buffer)

available_cash
  = cash_balance - active_cash_reservations
```

送出 BUY 前以 `available_cash` 檢核，並在同一 account transaction 建立 `CashReservation`。Partial fill 會 consume 成交所需 notional／fee 並釋放限價與成交價之間不再需要的差額；取消、拒絕、到期或 broker reconcile 證明不再有效時才釋放剩餘 reservation。

SELL 使用獨立 `PositionReservation`：

```text
available_to_sell
  = sellable shares - Σ(active PositionReservation.remaining_shares)
```

Cash／Position reservation 的 create、consume、release 都必須有 immutable Journal event，但不進 cash ledger。相同 idempotency key 不得建立第二份 reservation；callback、cancel 與 reconcile 交錯時也不得 double-release。

### 5.4 FeePolicyV1 與 RoundingPolicy

`LOCAL_PAPER` v1 的適用範圍固定為「上市櫃普通股票、現股、非當沖」，reference policy 現在凍結如下：

```text
FeePolicyV1
  security_scope         = TWSE_TPEX_COMMON_STOCK
  order_condition        = CASH
  day_trade              = false
  commission_rate        = 0.001425
  commission_discount    = 1.0
  commission_applies_to  = BUY | SELL
  minimum_commission     = 20 TWD
  sell_tax_rate          = 0.003
  calculation_unit       = executed gross amount
  partial_fill_semantics = cumulative commission delta
  semantics_source       = PROJECT_DEFINED_REFERENCE_POLICY
  rounding_policy_version = twd_round_down_v1
  effective_from         = 2026-08-19
  policy_version         = tw_stock_standard_v1

RoundingPolicyV1
  money_quantum               = 1 TWD
  commission_rounding_mode    = ROUND_DOWN
  tax_rounding_mode           = ROUND_DOWN
  policy_version              = twd_round_down_v1
```

Evidence 與採用範圍：

| Evidence | 支持的契約 | 限制 |
|---|---|---|
| [永豐金證券手續費率查詢](https://www.sinotrade.com.tw/newweb/Fee_Rate/?market=S) | 上市櫃股票牌告標準費率 `1.425‰`、標準最低手續費 NT$20；2026 優惠費率與最低 NT$1 另列 | promotion／個人折讓不是 replay-stable baseline，因此 v1 不採用 |
| [財政部：買賣股票的證券交易稅稅率](https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/securities-transaction-tax/filing/mM8n39b) | 一般股票賣出證券交易稅 `3‰` | 不延伸到 ETF、當沖、權證或其他商品 |
| [永豐金證券交易成本說明](https://www.sinotrade.com.tw/richclub/Decoding_Stock/video/-65645bd51c0a5012c8480876) | LOCAL_PAPER reference 的費、稅整元無條件捨去 | 這是本機 reference policy，不取代真實券商帳單與折讓結果 |

`effective_from` 是本專案啟用這份 LOCAL_PAPER reference policy 的日期，不宣稱是法規或券商牌告的發布日。Commission 適用於 BUY 與 SELL 兩側的 executed gross amount；證交稅只適用於 SELL executed gross amount。計算必須使用高精度 `Decimal`，且 order-level partial-fill bookkeeping 公式凍結為：

```text
if cumulative_executed_gross == 0:
  cumulative_commission = 0
else:
  cumulative_raw_commission
    = cumulative_executed_gross
      × commission_rate
      × commission_discount

  cumulative_commission
    = max(
        minimum_commission,
        ROUND_DOWN(cumulative_raw_commission)
      )

commission_delta
  = cumulative_commission - already_booked_commission
```

每次新 fill accounting event 只記錄 `commission_delta`，避免每個 partial fill 重複收最低手續費。上述 cumulative-delta 是 `PROJECT_DEFINED_REFERENCE_POLICY`；官方 evidence 支持 rate、最低收費與 rounding，這段 event-bookkeeping algorithm 的 provenance 不宣稱來自券商。Operation 順序必須成為 policy contract 與 golden tests，不能只保存幾個 rate。

三種 mode 的 authority 分工：

- `LOCAL_PAPER`：以 `tw_stock_standard_v1` 作為 versioned authoritative reference policy。
- `SHIOAJI_SIMULATION`：先沿用相同 reference policy 做本地 risk-capital estimate、reservation 與產生新 accounting event；broker simulation 的 execution 結果仍是 execution truth。
- `BROKER_REAL`：本地 policy 只做 pre-trade estimate／reservation；實際 commission、discount／rebate、tax 與 settlement 以 broker accounting 為最終 authority，reconcile 後記錄差異，不回寫竄改原始估算。

內部精度與券商 cash quantum 分開定義：

```text
calculation_precision = high precision Decimal
average_cost_scale    = 6
pnl_display_scale     = 2
```

`average_cost_scale` 與 `pnl_display_scale` 是本系統的 calculation／presentation policy；`pnl_display_scale` 不得提前截斷 ledger 或 risk calculation。產生新 Fill／Ledger event 時，必須原子保存 `gross_amount`、`commission`、`tax`、`net_amount` 與當時的 `fee_policy_version`／`rounding_policy_version`。

Historical replay 的 accounting truth 是 immutable event 內已定案的 monetary values：reducer 直接讀取 persisted `commission`、`tax`、`net_amount` 重建 projection，不載入 policy、不重新計算歷史 fee／tax。Policy version 只作 provenance、audit 與 validation evidence；authoritative fee／tax calculation 只在產生新的 accounting event 時執行。Pre-trade estimate／reservation 可以使用相同 policy，但不是已發生的 accounting truth。

Audit／golden test 可以驗證：

```text
recalculate(fill inputs, stored policy versions)
  == persisted fill monetary values
```

Mismatch 必須標示 validation／integrity failure，但不得讓 reducer 用重算值改寫歷史 projection。Fee／Rounding 已由 `BLOCKING_EVIDENCE` 更新為 `FROZEN`。

### 5.5 FreshnessPolicyV1

UI stale 與 Risk stale 是兩種不同決策：

- UI 可以顯示最後 verified value，但必須附 `STALE`、`as_of` 與 age。
- RiskGate 只接受 `FreshnessPolicyV1` 規定期限內，且 connection／subscription 健康的 book、positions、orders、accounting 與 buying-power evidence。
- Browser polling interval 只決定 UI 多久讀 local projection，不得等於 broker API refresh interval。
- Broker accounting adapter 依自己的 cache／TTL 更新 local projection，多個 browser tabs 不得各自觸發 broker query。

行情健康不得只看「距離最後一筆成交多久」。每個 symbol／subscription 至少保存：

```text
last_tick_market_at
last_tick_received_at
last_bidask_market_at
last_bidask_received_at
quote_connection_status
subscription_status
```

下單所需 order book freshness 的最低契約是：

```text
BOOK_FRESH
  = quote_connection_status == HEALTHY
  AND subscription_status == ACTIVE
  AND last_bidask_received_at exists
  AND now - last_bidask_received_at <= risk_bidask_stale_after_ms
  AND bidask market timestamp passes ordering／clock-skew validation
```

`last_*_market_at` 保存交易所事件時間，`last_*_received_at` 保存本機 callback 接收時間；兩者不能互相覆蓋。沒有新 Tick 可能只代表沒有成交，不能在 BidAsk 仍健康時單獨判定 book 壞掉；Tick freshness 用於 last-trade valuation，BidAsk freshness 用於 executable book／RiskGate。

[Shioaji 官方 streaming 文件](https://sinotrade.github.io/tutor/market_data/streaming/stocks/)證明股票即時行情是 event-driven subscription，Tick 與 BidAsk payload 也包含 `date`／`time`／`datetime`，但文件沒有提供「每 N ms 必有事件」或 callback latency 上限。因此 Phase 0 保留一個 evidence-only 的 **Freshness Calibration Evidence**，不由 Phase 1 猜預設值：

```text
每個 Tick／BidAsk 記錄：
  symbol
  market_event_at
  callback_received_at
  store_updated_at
  event_to_callback_ms
  callback_to_store_ms
  inter_tick_ms
  inter_bidask_ms
  connection_state

觀察分層：
  高／中／低流動性股票
  開盤／一般盤中／接近收盤
```

Calibration artifact 必須記錄樣本日期、symbols／流動性分層、交易時段、sample count、分位數、disconnect／reconnect case、clock source 與 threshold selection rationale。最後分別核准：

```text
ui_tick_stale_after_ms
ui_bidask_stale_after_ms
risk_tick_stale_after_ms
risk_bidask_stale_after_ms

broker_positions_stale_after_ms
broker_orders_stale_after_ms
broker_accounting_stale_after_ms
buying_power_stale_after_ms
```

前四個是 quote freshness；後四個是 broker accounting／order evidence SLA，不能由 quote latency 推導。Phase 0 必須為每個 `*_stale_after_ms` 凍結正整數與用途 SLA；active policy 不允許 `None`。所有 RiskGate tests 只依 versioned policy，不在測試中散落 magic numbers。這仍是 Freeze Ledger 唯一的 `BLOCKING_EVIDENCE`。

### 5.6 持倉價值與損益

```text
market_value
  = quantity_shares × mark_price

cost_basis
  = remaining quantity 的加權平均含費成本

unrealized_pnl
  = market_value - cost_basis

unrealized_pnl_pct
  = unrealized_pnl / cost_basis × 100

equity
  = cash_balance + total_market_value
```

`mark_price` 優先使用符合 UI freshness 的 Tick；若 Tick stale，可顯示最後價格但必須附 `STALE`，且不可用來通過需要新鮮行情的下單風控。買進預估使用符合 Risk freshness 的 ask、賣出預估使用 bid；損益顯示使用 last trade，兩者不可混為一個價格欄位。

使用者要求的「跟原本下單價格增減多少 %」應以持倉的平均成本為基準，而不是最後一筆 order price。UI 可以額外展開每個 tax lot／fill，查看每筆成交自己的報酬。

### 5.7 Shioaji Simulation risk capital

Shioaji Simulation 的目的，是驗證未來 production broker 共用的 execution path，不是驗證真實銀行帳務。其送單前資金 gate 使用建立 account mode 時設定、由 Journal reducer 管理的 versioned `simulation_risk_capital`，再扣除 broker-confirmed fills、fees／tax 與 active cash reservations。

Shioaji simulation order／fill／position 仍以 broker simulation 回報為 execution truth；若本地 risk-capital projection 與 broker execution 結果不一致，進入 reconciliation，不可用本地數字覆蓋 broker order state。

### 5.8 BROKER_REAL 的可買金額

建議產生有證據時間的 `BrokerBuyingPowerSnapshot`：

```text
bank_balance_status / bank_balance
trading_limit / trading_used / trading_available
settlements: T / T+1 / T+2
open_buy_reserved_amount
accounting_as_of / orders_as_of
source_status / stale_reasons
```

`BROKER_REAL` 只在以下條件全部成立時允許 BUY：

- account、CA 與 trade subscription 狀態對該 mode 有效。
- broker accounting、open orders 與 positions 已完成 startup reconciliation。
- trading limits 在官方可查詢時段內取得且未過期。
- 可取得可信的現金／交割證據；若 `account_balance` 不支援該帳戶，不可假裝為 0 或無限額。
- 本地 pending reservation 已計入。
- order notional、position notional、daily loss 與 fresh book 都通過 RiskGate。

如果 buying-power evidence 不完整，狀態是 `UNAVAILABLE`／`STALE`，新 BUY fail closed。讀取資產仍可用；Cancel／SELL 是否可用必須再通過第 5.9、5.10 節的 sellability／reconciliation 規則，不能因為操作看似 risk-reducing 就跳過 broker state 確認。

### 5.9 Sell availability 與當沖邊界

`LOCAL_PAPER`：

```text
available_to_sell
  = reducer confirmed position shares
  - active local PositionReservations
```

`SHIOAJI_SIMULATION`／`BROKER_REAL`：

```text
available_to_sell
  = broker_reported_sellable_shares
  - active local PositionReservations
```

若本地已收到 BUY fill，但 broker positions 尚未反映，第一版**不**自行把該 quantity 加回可賣量；狀態進入 broker lag／reconciliation，SELL fail closed。未來若要支援當沖，必須另加 `DAY_TRADE_ENABLED`、eligible quantity、order condition 與 broker capability contract，不得把同日可賣量藏進普通 `Position.quantity`。

`SHIOAJI_SIMULATION` 與 `BROKER_REAL` 的 read ownership 統一由 `ShioajiAccountAdapter` 負責。它由 composition root 依選定的 Shioaji environment／account 建立，正規化 positions、`broker_reported_sellable_shares`、PnL 與 accounting evidence；`ShioajiSimulationBrokerAdapter` 與 `ProductionShioajiBrokerAdapter` 只負責 command、order/deal callback 與 execution reconciliation，不再各自實作一份 position reader。底層可共享同一個 SDK session／client，但 port responsibility 與 DTO mapping 只能有一套。

### 5.10 Order lifecycle、SUBMIT_UNKNOWN 與 Cancel

```text
CREATED → PENDING_SUBMIT → SUBMITTED／ACCEPTED
                              ├→ PARTIALLY_FILLED → FILLED
                              ├→ CANCEL_PENDING → CANCELLED
                              ├→ REJECTED
                              └→ EXPIRED

PENDING_SUBMIT／broker timeout／connection loss → SUBMIT_UNKNOWN
SUBMIT_UNKNOWN → reconcile → SUBMITTED／ACCEPTED／PARTIALLY_FILLED／FILLED／REJECTED
```

`SUBMIT_UNKNOWN` 不是 terminal failure，也不允許 retry。系統必須先用 client identity、broker order list、deals、callback 與 reconciliation 證明結果；無法證明時 account／order 保持 `RECONCILIATION_REQUIRED`。

`SUBMIT_UNKNOWN` 同時是 canonical Order status 與 API `reason_code`；不再保留第二套 alias。API category 固定為 `TEMPORARILY_UNAVAILABLE`，但 category 不改變 reconcile-first semantics。

在 `RECONCILIATION_REQUIRED` 下：

- Query：允許，但標示最後 verified source／as-of。
- New BUY／risk-increasing order：禁止。
- Cancel：只有 `broker_order_id` 與 broker pending state 可確認時才送 broker cancel；不先假定成功，等待 callback／reconcile。Broker state unknown 時 reconcile-first，不做 local cancel。
- SELL：只有 broker 可確認 sellable inventory 且其他 RiskGate 條件成立時才允許。

### 5.11 LOCAL_PAPER ROD EOD expiry

`ROD` 是當日有效委託。`LOCAL_PAPER` 沒有 broker 幫忙發出到期 callback，因此 Phase 1 必須提供 deterministic `LocalPaperRodExpirySweep`：

1. 以 versioned Taiwan trading calendar 與 `Clock` 判定每筆 order 的 `trading_session_date`／`expires_at`，不以 process 啟動時間或硬編碼 sleep 推算。
2. session 結束後，逐 account 取得相同的 DB row lock；只選取 `LOCAL_PAPER`、`ROD` 且仍有 `remaining_shares` 的 `PENDING_SUBMIT`／`SUBMITTED`／`ACCEPTED`／`PARTIALLY_FILLED` order。
3. 在同一 transaction 將未成交餘量轉為 `EXPIRED`、逐 order append `local_paper_order_expired.v1`，並釋放剩餘 `CashReservation`／`PositionReservation`。
4. 同一 account 同一輪若有多筆 order 到期，全部在一個 transaction 內處理，**account revision 整批只 increment 一次**；沒有任何 state change 的重跑不得 increment revision。
5. 以 order current state + `(account_id, order_id, trading_session_date)` event uniqueness 保證重跑不會 double-expire 或 double-release。
6. Long-running process 由 in-process `PortfolioMaintenanceScheduler` 計算下一個 `expires_at` 並註冊 timer；`Clock.now >= expires_at` 時呼叫 sweep。Scheduler 必須取得 DB-backed lease／advisory lock，確保同一 deployment 只有一個 maintenance owner；定期 backstop scan 也呼叫同一 use case，不另寫第二套 expiry 邏輯。
7. process 在收盤時未運行、timer 漏失或 sweep 中斷，restart recovery 必須在重新開放 mutation routes 前呼叫同一個 idempotent sweep，補跑所有 overdue sessions。外部 cron／manual admin command 若未來加入，也只能是同一 use case 的另一個 trigger。

Sweep liveness 不能成為「過期後仍可成交」的安全邊界。`LocalPaperBrokerAdapter` 在每次執行前都必須先驗證 `Clock.now < order.expires_at` 且 session 相符；不成立時只能呼叫 expiry use case，禁止讀取下一交易日 BidAsk 成交舊單。

`LOCAL_PAPER` startup recovery 對 crash window 的規則：

```text
PENDING_SUBMIT AND now < expires_at
  → 驗證 command／reservation／idempotency state
  → idempotently resume local submission

PENDING_SUBMIT AND now >= expires_at
  → EXPIRED
  → release remaining reservation
  → DO NOT execute against a later-session quote
```

Partial fill 只將 remaining quantity 到期，既有 fills／fees／tax 不回滾。`SHIOAJI_SIMULATION`／`BROKER_REAL` 不由本機 clock 假造 `EXPIRED`；兩者由 broker callback／startup reconciliation 決定，broker 回報延遲期間 reservation 保留並標示 reconciliation 狀態。

## 6. Ports、adapters 與依賴規則

### Domain／application ports

```python
class PortfolioRepository(Protocol): ...
class OrderRepository(Protocol): ...
class JournalRepository(Protocol): ...
class QuoteReadPort(Protocol): ...
class BrokerAccountPort(Protocol): ...
class BrokerOrderPort(Protocol): ...
class Clock(Protocol): ...
class TradingCalendarPort(Protocol): ...
class MaintenanceLeasePort(Protocol): ...
```

### Infrastructure adapters

- `LocalPaperBrokerAdapter`
  - 只負責 deterministic execution；使用相同的 Order lifecycle 與 fills，不再由 UI service 私自維護另一套 state。
- `ShioajiAccountAdapter`
  - 由 composition root 以 Shioaji simulation／production environment 與 selected account 參數化建立。
  - 單獨擁有 `list_positions(Common／Share)`、sellable shares、`list_profit_loss`、`account_balance`、`trading_limits`、`settlements` 等 read path。
  - 只回傳 normalized DTO，不讓 Shioaji SDK type 進入 domain；simulation／production broker adapters 不重複維護 position mapping。
- `ShioajiSimulationBrokerAdapter`
  - 明確使用 Shioaji simulation execution authority，只處理 command、order/deal callback 與 execution reconciliation；驗證未來 production adapter 會走的 path。
- `ProductionShioajiBrokerAdapter`
  - CA activation、order factory、`place_order`、cancel／update、trade subscription、order/deal callback、startup reconciliation。
  - execution-side only；account／position／sellable reads 經 `ShioajiAccountAdapter`。
  - Phase 5 前不可由 composition root 建立可 mutation 的 instance。
- `PostgresPortfolioRepository`
  - 保存 append-only Journal、reservations、account revision 與可重建 projections；不能同時讓 memory state 和 DB state 都自稱權威。
- `PortfolioMaintenanceScheduler`
  - infrastructure trigger；用 `TradingCalendarPort`／`Clock` 安排下一個 expiry，取得 `MaintenanceLeasePort` 後只呼叫 application-layer `ExpireLocalPaperOrdersUseCase`。
  - timer、periodic backstop 與 startup catch-up 不得各自實作 domain transition。

Dependency 必須往內：FastAPI、Shioaji 與 psycopg 只能在 adapters／composition layer；Risk、Money、Order、Fill 與 Portfolio 不 import 它們。

## 7. 建議 API 契約

保留現有 `/api/simulation/*` 作為相容 facade，新的 UI 改用 mode-explicit API：

```text
GET  /api/portfolio/accounts
POST /api/portfolio/paper/accounts
GET  /api/portfolio/{account_id}/projection
GET  /api/portfolio/{account_id}/orders
GET  /api/portfolio/{account_id}/positions
GET  /api/portfolio/{account_id}/ledger

POST /api/portfolio/{account_id}/orders
POST /api/portfolio/{account_id}/orders/{order_id}/cancel

POST /api/portfolio/{account_id}/paper/deposits
POST /api/portfolio/{account_id}/paper/withdrawals
POST /api/portfolio/{account_id}/paper/reset
POST /api/portfolio/{account_id}/close

POST /api/portfolio/{account_id}/broker/reconcile
```

下單 request 至少包含：

```json
{
  "mode": "LOCAL_PAPER",
  "symbol": "2330",
  "side": "BUY",
  "order_lot": "COMMON",
  "quantity_shares": 1000,
  "price_type": "LIMIT",
  "limit_price": "1200.00",
  "time_in_force": "ROD",
  "portfolio_revision": 42,
  "idempotency_key": "..."
}
```

`portfolio_revision` 用來阻擋使用者根據過期資產畫面重複送單；伺服器仍必須在 commit 前重新讀取最新資產與 reservations，不能信任瀏覽器送來的可用金額。

Multi-tab optimistic flow：

```text
Tab A revision 42 ── submit success ──→ revision 43
Tab B revision 42 ── submit ──────────→ HTTP 409 PORTFOLIO_REVISION_CONFLICT
                                            ↓
                                  refetch projection + rerender preview
```

`portfolio_revision` 不是帳務 lock。真正 mutation transaction 必須：

```sql
BEGIN;
SELECT ... FROM portfolio_accounts WHERE account_id = $1 FOR UPDATE;
SELECT prior_result FROM commands
 WHERE account_id = $1 AND idempotency_key = request.idempotency_key;
IF prior_result exists THEN
    COMMIT;
    RETURN prior_result;
END IF;
IF locked_row.revision <> request.portfolio_revision THEN
    ROLLBACK;
    RETURN HTTP 409 PORTFOLIO_REVISION_CONFLICT;
END IF;
-- read latest cash, active reservations, positions and policy evidence
-- evaluate RiskGate
-- append command/event, create reservation, increment revision
COMMIT;
```

Revision 比對必須發生在 row lock **之後**、RiskGate **之前**，而且 mismatch 不得 append event、建立 reservation 或呼叫 broker。所有下單、取消、入金、出金、EOD expiry 與 reservation release 都走相同 account-level serialization contract；多 worker 時也不能只靠 Python process lock。

常見錯誤應使用 stable reason code：

- `INSUFFICIENT_AVAILABLE_CASH`
- `INSUFFICIENT_POSITION`
- `BUYING_POWER_UNAVAILABLE`
- `PORTFOLIO_REVISION_CONFLICT`
- `BOOK_STALE`
- `RECONCILIATION_REQUIRED`
- `LIVE_ORDERING_DISABLED`
- `UNSUPPORTED_ORDER_LOT`
- `UNSUPPORTED_ORDER_CONDITION`
- `PERSISTENCE_UNAVAILABLE`
- `ACCOUNT_INITIALIZING`
- `ACCOUNT_READ_ONLY`
- `ACCOUNT_DEGRADED`
- `ACCOUNT_CLOSE_BLOCKED`
- `SUBMIT_UNKNOWN`

API error 另外回傳 stable `reason_category`：

```json
{
  "reason_code": "UNSUPPORTED_ORDER_LOT",
  "reason_category": "CAPABILITY_NOT_IMPLEMENTED",
  "message": "目前版本僅支援整張 COMMON 委託。"
}
```

第一版 categories：

- `CAPABILITY_NOT_IMPLEMENTED`
- `POLICY_DISABLED`
- `TEMPORARILY_UNAVAILABLE`
- `RISK_REJECTED`
- `DATA_UNAVAILABLE`
- `CONCURRENCY_CONFLICT`

## 8. Dashboard UX

左側新增一個「資產與持倉」工作區，頂部以清楚的三個 mode tabs 隔離：

- `本機模擬`：藍色／中性色，顯示「不會送至券商」。
- `Shioaji 模擬`：顯示 simulation account、broker sync／reconciliation 狀態，不得標成真實帳戶。
- `真實帳戶`：紅色風險標示，顯示 masked account、最後對帳時間與 live-order capability；Phase 5 前只讀。

Account status 必須獨立顯示：`INITIALIZING` 顯示 replay／reconcile／EOD catch-up／freshness bootstrap 進度且停用使用者 mutation；`READ_ONLY` 說明是哪個 policy／capability 關閉操作；`DEGRADED` 顯示 stale source、last verified `as_of` 並停用受影響 mutation；`RECONCILIATION_REQUIRED` 顯示已知差異／未知 side effect 與「先對帳」動作。這些狀態不可共用一個模糊的「暫時不可用」badge。

### 資產摘要

- 總權益
- 現金餘額
- 委託預留
- 可用現金／可買金額
- 股票總市值
- 未實現損益與百分比
- 今日已實現損益
- T／T+1／T+2 交割款（真實模式）
- 資料狀態、行情時間、帳務同步時間與 reconciliation status

### 持倉表

- 股票代碼／名稱
- 庫存股數／可賣股數
- 平均成本
- 最新價
- 市值
- 未實現損益金額／百分比
- 已實現損益
- 買一／賣一
- 行情新鮮度
- 快捷動作：加碼、賣出（仍必須進 OrderApplicationService）

### 下單 ticket

送單前即時顯示：

- 委託金額
- 預估手續費／稅
- 本次預留金額
- 送出前可用現金
- 送出後預估可用現金
- 可賣股數
- RiskGate 結果與明確原因

真實模式需二次確認，確認 Dialog 必須再次列出 masked account、股票、方向、股數、限價及預估總金額。切換三種 mode 或 account 後清空尚未送出的 ticket，避免把本機模擬單、Shioaji 模擬單與真實單混用。

### 模擬本金設定

- 建立模擬帳戶時設定初始本金。
- 建立後不直接覆寫 starting cash；使用「模擬入金／出金」保留 ledger。
- 「重設模擬帳戶」是獨立 destructive action，需確認；必須依第 4.3 節先讓未完成委託 terminal、reservation 歸零再 close，之後建立新的 `INITIALIZING` session，不覆寫舊 Journal。

## 9. Persistence、recovery 與 reconciliation

建議延續專案既有 Journal-first 方向：

1. 每個 order command 先 append，通過 RiskGate 後才呼叫 adapter。
2. order ack、reject、partial fill、fill、cancel 都轉為 immutable Journal record。
3. cash、orders、positions 與 realized PnL 由 Journal reducer 重建；reducer 直接使用 event persisted monetary values，不重新執行歷史 FeePolicy calculation。
4. 每次 projection checkpoint 保存 sequence + digest。
5. 啟動時 account 先進入 `INITIALIZING`；`LOCAL_PAPER` 依序完成 replay、digest validation、overdue EOD sweep、`PENDING_SUBMIT` recovery 與 freshness bootstrap 後才開 mutation routes。
6. Shioaji simulation／真實帳戶 replay 後還要執行 `update_status`／trades／positions reconciliation 與 freshness bootstrap。
7. 任一不一致進入 `RECONCILIATION_REQUIRED`，依第 5.9、5.10 節限制 mutation，不自動覆寫差異。

真實 broker side effect 存在「已送到券商，但本機未收到 ack」的歧義。相同 idempotency key 不可盲目重送；必須先依 client identity、broker trades 與 callbacks 查證，再標記 applied 或交由人工 recovery。

### 9.1 PostgreSQL failure invariant

PostgreSQL unavailable 時不允許 fallback 到 memory mutation：

```text
GET projection
  → 可回最後一次 verified projection
  → status = DEGRADED
  → fresh = false
  → as_of = last verified timestamp

POST order／cancel／deposit／withdrawal／reset
  → reject
  → reason_code = PERSISTENCE_UNAVAILABLE
  → reason_category = TEMPORARILY_UNAVAILABLE
```

這是 P0 invariant。DB 復原後先 replay、驗證 checkpoint／projection parity，再重新開啟 mutation；不做 memory state merge。

## 10. 安全邊界

目前 Dashboard 契約是 loopback single-user。若開真實下單，至少要補：

- `BROKER_LIVE_ORDER_ENABLED=false` 預設關閉，啟動時明確顯示 capability。
- CA path／password、API key 不進 DB、Journal、response 或 log。
- account identity 只顯示遮罩後資訊。
- mutation routes 驗證 Origin／Host，加入 CSRF 防護或同等的 local command token。
- 不允許多 worker／多 replica 同時持有同一真實帳戶 execution authority，除非先實作 leader／lease。
- kill switch：停止新單，但保留查詢、取消與 reconciliation。
- 所有真實命令保存 actor、request id、policy version、risk snapshot 與結果。
- application shutdown 順序：停止接單 → 停止 producer → drain callbacks → flush Journal／checkpoint → unsubscribe trade／quote → logout。

## 11. 實作階段與 gates

### Phase 0 — Contract Freeze

- 凍結 `AccountMode v1`、Money／Decimal serialization 與 `COMMON` 1000 股 domain invariant。
- `FeePolicyV1`／`RoundingPolicyV1` 已以 `tw_stock_standard_v1` 凍結，包含來源、effective date、policy versions 與 mode-specific authority。
- 執行 evidence-only Freshness Calibration；依 quote 與 broker accounting 各自的用途 SLA 凍結 `FreshnessPolicyV1` 全部毫秒值。
- 凍結 immutable monetary event replay、`CashReservation`／`PositionReservation`、Order lifecycle、`SUBMIT_UNKNOWN` 與 reconciliation semantics。
- 凍結三模式 Authority Matrix、`INITIALIZING`／PortfolioAccount status transitions、`CLOSED` preconditions、PostgreSQL failure policy 與 account locking／revision-check contract。
- 凍結 `LOCAL_PAPER` ROD EOD scheduler trigger、expiry、batch revision、`PENDING_SUBMIT` recovery、reservation release 與 restart catch-up contract。
- 凍結 `ReasonCode` + `ReasonCategory` 與 HTTP mapping。
- 明確保留現有 working tree 的其他功能，不混入本功能變更。

Gate：P0-1～P0-14 全部可直接寫成 deterministic unit／property tests；目前只剩 Freshness Calibration artifact 與核准後的 `FreshnessPolicyV1` 毫秒值，不得為 TBD。完成後才可將 `Phase 0: COMPLETE`、`Phase 1: UNBLOCKED`；不再擴張 Phase 0 scope。

### Phase 1 — Portfolio Core + Local Paper v2

- `Decimal`、ledger、獨立 Cash／Position reservations、fees／tax。
- 新 accounting event 依凍結公式計算 fee／tax；replay 只讀 persisted monetary values。
- 完整 Order lifecycle、Position projection、PnL 與 RiskGate。
- 可建立 `INITIALIZING` 的 `LOCAL_PAPER` 帳戶並設定 initial capital；startup gate 通過才轉 `ACTIVE`，後續調整走 ledger。
- `LocalPaperBrokerAdapter` 只負責 deterministic execution，不追求假裝是真實交易所。
- 實作 deterministic `ExpireLocalPaperOrdersUseCase`／`LocalPaperRodExpirySweep`，包含 `PENDING_SUBMIT`、partial-fill remaining expiry、reservation release、batch revision、idempotency、long-running in-process trigger 與 restart catch-up；Phase 1 測試可使用 single-process lease adapter。
- 實作 strict `ClosePortfolioAccount` preconditions；reset 必須先 drain orders／reservations，再建立新 session。

Gate：任何交錯 order／fill／cancel／expiry／close 序列都維持 cash／position conservation；多筆 pending BUY 不可超額，COMMON 非 1000 股倍數一律由 domain 拒絕；跨日未成交 ROD 不得占用 reservation 或用下一交易日行情成交；帶 open order／reservation 的 account 不得 `CLOSED`。

### Phase 2 — Persistence／Recovery／Dashboard

- Dashboard mutation route 全部改走 `OrderApplicationService`。
- PostgreSQL Journal、reservations、projection checkpoint、account revision、maintenance lease 與 DB fail-closed。
- restart recovery、idempotency、ambiguous command recovery、multi-tab HTTP 409、EOD scheduler leader／batch revision flow。
- 新的三模式資產摘要／持倉／委託 projection 與 UI；第一階段只有 `LOCAL_PAPER` 可 mutation。

Gate：`replay(all_events)` 的每個 projection field 都等於 persisted projection，且 digest 相同；corrupted checkpoint、DB outage 與 stale evidence 都 fail closed。

### Phase 3 — Shioaji Simulation

- 正式新增 `SHIOAJI_SIMULATION` account mode 與 adapter。
- CA、trade subscription、place／ack／reject／cancel／fill callbacks、status reconciliation。
- 驗證 partial-capable lifecycle、duplicate／out-of-order callback、disconnect、restart、`SUBMIT_UNKNOWN`。
- `ShioajiAccountAdapter` 經 simulation environment 讀取 positions／sellable shares／accounting；`ShioajiSimulationBrokerAdapter` 維持 execution-side only，兩者不得重複 position mapping。
- 與 local paper 使用同一 command、RiskGate、Journal、reservations 與 Portfolio projection contract。

Gate：所有 execution lifecycle 與 reconciliation cases 通過；這一階段驗證 production broker path，但不宣稱真實銀行帳務已驗證。

### Phase 4 — BROKER_REAL Read-only

- 新增 `BROKER_REAL`，將同一套 `ShioajiAccountAdapter` read contract 綁定 production environment／account；live order capability 保持 OFF。
- 讀取 accounts、positions、profit/loss、trading limits、settlements 與可用時的 account balance。
- 建立正式 `BrokerBuyingPowerSnapshot`、Freshness、Unsupported、Stale 與 Reconciliation projection。
- Broker positions 使用現有 Tick／BidAsk 即時 mark-to-market。
- Browser 只 poll local cached projection；broker accounting API 使用獨立 cache／TTL。

Gate：受控帳戶 accounting contract smoke 通過；多 browser tabs 不會放大 broker API query，缺 evidence 不推測也不解鎖 BUY。

### Phase 5 — 真實委託

這一階段會改變專案目前「無 CA、無 broker order API、無真錢交易」的安全邊界，必須另有明確批准：

- 預設關閉 live ordering。
- 先用小範圍 allowlist 與人工單筆操作。
- 禁止 strategy automated origin。
- 每次 session 需要 operator acknowledgement。
- 完成 rollback／kill switch／incident runbook 後才可啟用。

Gate：新的 Live Trading RFC 與使用者明確授權；P0～P4 全部通過也不能自動開啟。

## 12. 測試與驗收標準

### Domain／property tests

- 任意 order／fill／cancel 序列下 `available_cash >= 0`。
- `cash + reservations + fills + fees/taxes` conservation。
- 可賣股數不會因多筆 pending SELL 變成負數。
- `COMMON` quantity 不是 1000 股倍數時，即使直接呼叫 domain service 也會拒絕。
- 加碼、部分賣出、全部賣出後平均成本與已／未實現損益正確。
- 同 idempotency key 不產生第二次 reservation 或 broker side effect。
- `tw_stock_standard_v1` new-event golden cases 覆蓋 BUY／SELL commission、零成交 commission = 0、最低手續費、整元 `ROUND_DOWN`、SELL-only tax 與 partial-fill cumulative commission delta。
- Replay 直接使用 persisted `commission`／`tax`／`net_amount`；即使 calculator implementation 被替換，歷史 projection 也不變。Audit test 另驗證 stored policy 重算值等於 persisted monetary values。
- Freshness boundary 在 threshold 前後 1ms 有 deterministic 結果；UI stale 與 Risk stale 可不同；沒有新 Tick 但 connection／subscription 與 BidAsk 都 fresh 時，不得誤判 `BOOK_STALE`。
- `INITIALIZING`／`ACTIVE`／`READ_ONLY`／`DEGRADED`／`RECONCILIATION_REQUIRED`／`CLOSED` 的每個允許與禁止 transition 都有 deterministic test；startup gate 前使用者 mutation 全部拒絕。
- `CLOSED` property test 保證不存在 non-terminal order、active reservation 或待 reconcile side effect；任一 precondition 不符回 `ACCOUNT_CLOSE_BLOCKED` 且沒有 state change。
- Decimal、序列化、replay 後完整 projection 與 digest 穩定。

### Concurrency／recovery tests

- 兩筆同時 BUY 競爭同一份現金，只能有可被資產覆蓋的命令成功。
- 兩個 tabs 使用相同 revision，第一筆成功後第二筆收到 HTTP 409 並 refetch。
- Revision mismatch 在 row lock 後、RiskGate／Journal／broker call 前 rollback；assert 沒有 event、reservation、revision increment 或 external side effect。
- account-level DB lock 可跨 worker 保護資產，不依賴 process `RLock`。
- quote callback、cancel 與 fill 交錯不會雙重釋放 reservation。
- process 在 command append、broker call、ack、fill 各階段中止皆有明確 recovery 狀態。
- DB 斷線時 mutation 回 `PERSISTENCE_UNAVAILABLE`；broker timeout 進 `SUBMIT_UNKNOWN`，兩者都不盲目重送。
- LOCAL_PAPER 收盤 sweep 將 `PENDING_SUBMIT`／open／partially-filled ROD remaining quantity 轉 `EXPIRED` 並釋放 reservation；重跑與跨收盤 restart catch-up 都不會 double-release。
- `PENDING_SUBMIT` 在 `now < expires_at` 只冪等恢復同日 submission；在 `now >= expires_at` 只 expiry，assert 沒有 quote read／fill／broker execution。
- Long-running process 不重啟也會由 maintenance scheduler 觸發 EOD sweep；兩個 worker 競爭 lease 時只有 owner 執行。
- 同一 account 多筆 order 同批到期時 events／reservation releases 各自完整，但 account revision 只加 1；idempotent no-op 重跑不加 revision。

### Broker contract tests

- account balance unsupported、trading limits 非查詢時段、settlements timeout 都顯示 typed unavailable，不轉成 0。
- common／odd unit 不混用。
- startup／reconnect reconcile open orders、fills 與 positions。
- callback duplicate／out-of-order 可去重並保持 projection 一致。
- local confirmed BUY 尚未反映至 broker position 時，不會增加可賣 quantity。
- reconciliation-required cancel 只有在 broker order state 可確認時才送出。
- simulation／production 的 positions 與 sellable shares 都只由 environment-scoped `ShioajiAccountAdapter` 正規化，broker execution adapter 不提供第二套讀取結果。

### UI smoke

- 本機模擬／Shioaji 模擬／真實 mode 不會互相殘留 order ticket。
- 可設定模擬本金並看見現金、預留、市值、總權益。
- 掛兩筆超額 BUY 時，第二筆在送單前被清楚拒絕。
- 持倉即時更新市值與相對平均成本的損益百分比。
- stale quote／accounting／reconciliation required 有明顯狀態。
- `INITIALIZING` 顯示 startup step 且沒有可繞過的 mutation；close 被 open order／reservation 阻擋時列出可處理項目。
- 真實下單 capability 關閉時，UI 不出現可繞過的 mutation path。

## 13. Final D1–D10 決策

| Decision | Final |
|---|---|
| D1 「即時」的定義 | ✅ 真實券商帳戶；UI 命名為「真實帳戶」 |
| D2 第一輪是否允許真錢委託 | ✅ 否；先完成 Shioaji Simulation 與 BROKER_REAL read-only |
| D3 第一版商品／訂單 | ✅ 現股、long-only、`COMMON`、`LMT`、`ROD`；domain 強制 1000 股倍數 |
| D4 初始本金 | ✅ 建立 LOCAL_PAPER 時設定，之後只走入金／出金 ledger |
| D5 手續費／稅 | ✅ `tw_stock_standard_v1` 已凍結；promotion 排除，BROKER_REAL 實際帳務仍以券商為準 |
| D6 Authority／persistence | ✅ mode-specific authority；PostgreSQL failure 時 mutation fail closed |
| D7 真實可買金額缺資料 | ✅ fail closed，不以 0／無限額／前次值偷偷替代 |
| D8 自動策略下單 | ✅ disabled；本次只設計人工 command surface |
| D9 零股／融資／融券／當沖 | ✅ 第一版 out of scope，不得讓 domain 偷偷支援 same-day sell |
| D10 Account Modes | ✅ `LOCAL_PAPER`／`SHIOAJI_SIMULATION`／`BROKER_REAL` |

## 14. 官方 Shioaji 契約核對

- `list_positions` 可查證券／期貨未實現損益，證券可指定整股或零股單位：<https://sinotrade.github.io/tutor/accounting/position/>
- `account_balance` 查交割帳戶餘額，但官方註明目前只支援部分銀行／帳戶：<https://sinotrade.github.io/tutor/accounting/account_balance/>
- `trading_limits` 提供電子交易額度及已用／可用金額，官方標示交易日 08:30～15:00 可查：<https://sinotrade.github.io/tutor/accounting/trading_limits/>
- `settlements` 提供 T／T+1／T+2 交割款：<https://sinotrade.github.io/tutor/accounting/settlement/>
- 真實股票下單前需登入並啟用 CA；`place_order` 支援 order lot、condition 與 time in force 等欄位：<https://sinotrade.github.io/tutor/order/Stock/>
- order／deal events 應透過 callback 接收並正規化；預約單有 callback 時機差異：<https://sinotrade.github.io/tutor/callback/orderdeal_event/>
- Shioaji simulation 支援 orders 與 positions／profit-loss，但不支援興櫃與零股模擬下單：<https://sinotrade.github.io/tutor/simulation/>
- 股票行情是 event-driven streaming subscription；Tick／BidAsk 有 market date／time／datetime，但官方沒有提供固定事件間隔或 callback latency SLA：<https://sinotrade.github.io/tutor/market_data/streaming/stocks/>
- 台股上市櫃標準手續費與 2026 promotion 分開公告，標準為 `1.425‰`、上市櫃最低 NT$20：<https://www.sinotrade.com.tw/newweb/Fee_Rate/?market=S>
- 財政部列示一般股票證券交易稅為 `3‰`：<https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/securities-transaction-tax/filing/mM8n39b>

## 15. 最終建議

本報告維持 **Approved**。P0-13 已凍結 strict `CLOSED` preconditions，禁止帶著 open order、active reservation 或待 reconcile side effect 關閉；P0-14 已凍結有 DB lease 的 in-process EOD scheduler，與 periodic backstop／restart catch-up 共用同一冪等 use case。同批多筆到期只 increment account revision 一次。

Event-sourcing authority 也已定案：historical replay 只使用 immutable Fill／Ledger monetary values，policy version 只供 provenance／audit validation；PortfolioAccount 正式增加 `INITIALIZING`；`LOCAL_PAPER PENDING_SUBMIT` 若跨過 `expires_at` 只能 expiry／release，不得使用下一交易日行情成交。依本次 review 要求，現在不開始 Phase 1 code。

`FeePolicyV1`／`RoundingPolicyV1` 已由 evidence 凍結為 `tw_stock_standard_v1`；目前唯一尚未解除的 blocker 是 `FreshnessPolicyV1`。下一步只做 Phase 0 Freshness Calibration Evidence，分開量測 Tick／BidAsk 與 broker accounting SLA，經 review 核准實際毫秒值後，才能正式標記 `Phase 0: COMPLETE`、`Phase 1: UNBLOCKED` 並進入 **Phase 1 — Portfolio Core + Local Paper v2**。
