# Quote Freshness Calibration: Preflight and Review Checklist

這是 evidence collection 的操作清單，不是 Portfolio domain contract，也不會凍結
任何 threshold。

## 已完成的本機 preflight（2026-08-19）

- Shioaji optional SDK：可匯入。
- API key 與 secret：只檢查到各自已設定，沒有讀出或輸出其值。
- Host UTC offset：`+08:00`，與 capture 強制使用的 `Asia/Taipei` 一致。
- Tick/BidAsk CLI：可解析 `--help`。
- Evidence writer：exclusive-create 已有 unit test；同一路徑不會覆寫既有
  artifact。
- SDK lifecycle collector：會保存 disconnect/reconnect 和 paired
  Tick/BidAsk acknowledgement；未收齊兩個 acknowledgement 前，觀測值維持
  `PENDING`。

這些項目只表示本機可以準備擷取，**不代表主機時鐘已經和外部時間源同步，也不
代表行情或 broker data 足夠新鮮。** 每次正式 capture 前仍要記錄 NTP／公司時間
服務的同步證據，並保存當次 host offset。

## 每次 capture 前

1. 複製並填妥
   [`cohort_manifest.template.json`](cohort_manifest.template.json)，由 reviewer
   在開始前凍結 high/mid/low symbol 與三個 session window 的 local time 範圍。
   不得因為看到 callback rate 再調整 tier。
2. 確認 manifest 的 symbol/tier 與 CLI 參數逐字一致；`session-window` 必須等於
   manifest 的 label。
3. 檢查當次 host offset 與 NTP／企業時間源同步狀態並把結果寫在 capture review；
   不要把「offset 是 +08:00」當成同步成功。
4. 僅確認 credentials 是否存在；禁止把 `.env` 或 token 印到 terminal、artifact
   或 report。
5. 確認目前不在 maintenance／收盤後時段。沒有預期 callback 的空 capture 只能
   記錄為 session coverage gap，不能當成 stale threshold evidence。

## 執行方式

每個經凍結的 cohort/window 組合都使用獨立 immutable artifact：

```bash
.venv/bin/python scripts/capture_quote_freshness.py \
  --symbol <high-symbol>:high \
  --symbol <mid-symbol>:mid \
  --symbol <low-symbol>:low \
  --session-window <opening|continuous|close> \
  --duration-seconds <reviewer-approved-duration>
```

工具只訂閱 Tick/BidAsk、以 `subscribe_trade=False` 登入、最多可同時擷取 100 檔
成對訂閱，且不會呼叫 order、account、CA 或 trade callback API。

## 每個 artifact 的品質 review

- 驗證 schema、SHA-256、exclusive-create、timezone-aware timestamps，以及
  capture start/end 範圍。
- 依 `symbol × liquidity_tier × session_window × stream_kind` 檢查 observation
  count、missing event time、event-to-callback、callback-to-store、inter-arrival。
- 檢查 source clock skew、monotonic regression、callback error 與 lifecycle
  transition。負 event-to-callback 必須保留並逐項判定，不得 clamp 成 `0 ms`。
- 檢查每個 configured symbol 的 Tick/BidAsk 都收到 paired acknowledgement。
  `PENDING`、`FAILED`、`UNKNOWN` 或 disconnect/reconnect 後沒有重新完成
  acknowledgement 的區段不得用來支持 risk freshness threshold。
- 清楚區分「stream 沒有新成交」與「connection/subscription 不健康」；不能只以
  Tick silence 判斷 stale。
- quote review 不得填寫或推導 broker positions、orders、accounting、buying
  power 四項 SLA。

## Review outcome

只有完整 cohort coverage、artifact integrity、clock/lifecycle disposition 和
資料品質 review 都通過後，reviewer 才能提出 threshold candidate。此 checklist 和
capture tool 都不會自動選擇數字；缺一項仍是 `BLOCKING_EVIDENCE`。
