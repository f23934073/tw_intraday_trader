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

目前 checkout 沒有 broker account read adapter 或 polling/callback capture
path。因此以下四個值沒有資料來源，仍是獨立 blocker，絕對不能從 quote
artifact 推導：

- `broker_positions_stale_after_ms`
- `broker_orders_stale_after_ms`
- `broker_accounting_stale_after_ms`
- `buying_power_stale_after_ms`

當 read-only broker source 已另行核准後，每個 endpoint 的證據都必須保存
`request_started_at`、`response_received_at`、`source_as_of_at`、
`projection_updated_at`、source status 與錯誤／timeout。它需要獨立的 capture
schema、digest 與 review；本資料夾的 quote 工具不會呼叫或模擬這些 API。

## Freeze rule

一份或多份 capture 不會自動凍結 threshold。只有在原始 artifact integrity、
完整分層覆蓋、clock-skew/error disposition、資料品質 review，以及明確的人為
門檻決議都完成後，才能將 `FreshnessPolicyV1` 從 `BLOCKING_EVIDENCE` 改成
`FROZEN`。
