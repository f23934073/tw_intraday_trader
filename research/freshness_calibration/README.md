# Freshness Calibration Evidence

這個資料夾只存 FreshnessPolicyV1 的可重播證據；它不會修改 Portfolio
domain，也不會送出委託、讀取下單 callback 或執行任何 real-money 動作。

正式擷取前請先使用：

- [`cohort_manifest.template.json`](cohort_manifest.template.json)：凍結 cohort
  labels 與 capture windows。
- [`preflight_and_review_checklist.md`](preflight_and_review_checklist.md)：本機
  preflight、artifact review 與 fail-closed 條件。
- [`broker_account_readonly_intake.md`](broker_account_readonly_intake.md)：獨立
  broker/account evidence 的 read-only 授權前提與必要時間欄位。

## Quote / executable market data

使用 `scripts/capture_quote_freshness.py` 在盤中擷取 Tick 與 BidAsk。
每一次 capture 必須由 reviewer 明確標記 symbol 的 liquidity tier 與
session window；工具不自行把股票分類，也不自行選擇任何 stale threshold。

```bash
python scripts/capture_quote_freshness.py \
  --symbol 2330:high \
  --symbol <reviewer-selected-mid-symbol>:mid \
  --symbol <reviewer-selected-low-symbol>:low \
  --session-window open \
  --duration-seconds 900
```

輸出的 JSON 用 exclusive-create 寫入 `research/captures/freshness_quote/`，
並保存下列原始欄位：

- `market_event_at`、`callback_received_at`、`store_updated_at`
- monotonic callback/store timestamps
- Tick/BidAsk kind、symbol、liquidity tier、session window
- connection/subscription lifecycle 與 callback error

分析結果只會產生每個分組的 event-to-callback、callback-to-store、
inter-arrival 分布（nearest-rank p50/p95/p99）與品質計數。負的
event-to-callback 值是 source clock skew evidence，會保留在 artifact 和
distribution 中，不能被歸零或忽略。

### 交易日排程

`scripts/run_scheduled_quote_freshness.py` 是唯一允許由本機排程啟動的
wrapper。它先以 `config/twse_calendar_2026.json` 驗證交易日，才會載入
frozen cohort、做五次唯讀 NTP preflight，並呼叫 Tick/BidAsk-only capture。
休市日、行事曆未涵蓋、非排定分鐘或 NTP preflight 失敗時，均不會初始化
Shioaji，而會留下可稽核的 no-capture record。

排程窗口固定為（每日六段）：

- 09:00–09:15：`opening`；
- 09:15–09:30：`opening`；
- 10:00–10:15：`continuous`；
- 11:00–11:15：`continuous`；
- 12:00–12:15：`continuous`；
- 13:15–13:35：`close`，保留收盤後五分鐘僅為觀察 13:30 session boundary。

macOS launchd 定義存於
`scripts/launchd/com.stevehuang.tw-intraday-trader.freshness-calibration.plist`。
它每天在三個起始時間喚醒 wrapper；實際資料供應商呼叫仍由 reviewed
calendar fail-closed 決定。執行紀錄會寫入
`research/freshness_calibration/scheduled_runs/`，原始 evidence artifact
仍只會寫入 `research/captures/freshness_quote/`。

每個成功擷取都會在 run record 附上 `post_capture_quality`：digest/schema、
Tick/BidAsk acknowledgement、per-row lifecycle、group coverage、callback
error、monotonicity 與 clock-skew 的結構性摘要。它只會回傳
`REVIEW_REQUIRED` 或更具體的 partial/quality-issue 狀態；不會選 threshold、
不會取代人工 review，無效 artifact 則標記 `CAPTURE_INVALID` 並保留原始檔。

已安裝的 user-level service 名稱為
`com.stevehuang.tw-intraday-trader.freshness-calibration`。電腦必須在各個
起始時間附近保持登入且喚醒；若稍後才恢復，runner 會安全地記成
`NO_CAPTURE_OFF_SCHEDULE`，不會拿延後的時間補抓成原定 session evidence。

`store_updated_at` 的邊界是 calibration 的 in-memory buffer，不是假裝已經
存在的 Portfolio projection。若 Phase 1 未來採不同 queue/store path，必須在
該 path 重做同樣的 instrumentation；這份資料不能冒充它的延遲 SLA。

在高／中／低流動性和開盤／一般盤中／近收盤的資料都經過 review 前，下列四個
值維持未設定：

- `ui_tick_stale_after_ms`
- `ui_bidask_stale_after_ms`
- `risk_tick_stale_after_ms`
- `risk_bidask_stale_after_ms`

## Broker / account evidence

broker/account source 已由 owner 另行授權為 read-only evidence collection。
以下四個值仍是獨立 blocker，絕對不能從 quote artifact 推導：

- `broker_positions_stale_after_ms`
- `broker_orders_stale_after_ms`
- `broker_accounting_stale_after_ms`
- `buying_power_stale_after_ms`

`scripts/run_scheduled_broker_account_freshness.py` 是此 evidence 的唯一排程
wrapper。它先檢查 reviewed calendar 和精確排程分鐘，才會讀取本機 credentials
並初始化 Shioaji。非交易日與非排程分鐘都留下 no-capture record，且不會讀取
credentials 或呼叫 provider。每個交易日執行五次：09:35、10:30、11:30、12:30、
13:20（Asia/Taipei）。每次只進行一次 positions、accounting、account-balance
read；不重試、不設 callback。

`scripts/launchd/com.stevehuang.tw-intraday-trader.broker-account-freshness.plist`
是對應的 user-level launchd 定義。它只會寫入 redacted artifact
`research/captures/freshness_broker_account/` 與 run record；schema、SHA-256、
four-kind limitations 和 review 方法請見
[`broker_account_capture_contract.md`](broker_account_capture_contract.md)。

在目前的 authorization 下，`ORDERS` 仍保留為明確 constrained gap，因為新鮮
broker order state 需要被排除的 `update_status` 或 trade callback。`account_balance`
也只表示 account-balance endpoint，不會被偽裝成 documented buying power。因此
這兩類不能選 threshold，除非日後另有適當授權與 source authority evidence。

## Freeze rule

一份或多份 capture 不會自動凍結 threshold。只有在原始 artifact integrity、
完整分層覆蓋、clock-skew/error disposition、資料品質 review，以及明確的人為
門檻決議都完成後，才能將 `FreshnessPolicyV1` 從 `BLOCKING_EVIDENCE` 改成
`FROZEN`。
