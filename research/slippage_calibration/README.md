# Local Paper 滑價 calibration evidence contract v1

這套工具只回答 Local Paper model stress/proxy 問題。它不連線 Shioaji、不讀 broker account、不下單、不啟用 CA 或 trade callback，也不把 BBO/Tick proxy 或 `local_paper_fill.v3` 稱為真實券商成交滑價。

## Qualification 邊界

報告永遠分開兩種狀態：

- `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`：本 contract 不接受 broker order/fill authority；`local_paper_fill.v3` 的 `execution_authority=false`，不能支持「實盤 5 bps 已校準」。
- `MODEL_STRESS_PROXY_QUALIFIED`：只表示 sealed canonical market evidence 通過本工具的 structural floor，仍不是 broker fill promise。
- `MODEL_STRESS_PROXY_INSUFFICIENT_COVERAGE`：session 本身可用，但 cohort／phase／side／days／samples 不足。
- `MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED`：digest、Journal、exact replay、paired ack、clock、ordering、book、descriptor 或 policy lineage 任一不合格。

目前 `fixed_adverse_bps_v1` 的 5 bps 仍是 `ASSUMPTION_NOT_LIVE_CALIBRATED`。工具完成不等於 threshold、FreshnessPolicyV1 或真實 execution calibration 通過。

## Input contract

`local-paper-slippage-calibration-input-manifest.v1` 會封存：

- Frozen cohort manifest 與 high/mid/low liquidity labels。
- Repository-reviewed TWSE trading calendar；schema、`Asia/Taipei` timezone 與 raw digest 必須精確符合 packaged `config/twse_calendar_2026.json`，且每個 session date 必須在 coverage 內並確為交易日。
- 每個既有 canonical market-data session 的 `manifest.json`、`records.jsonl`、`bootstrap_snapshot.json`、`instrument_reference.json`、`projection_state.json`、`qualification_report.json` 原始 SHA-256。
- 可選、獨立 reviewer 封存的 `local-paper-slippage-clock-disposition.v1`；它綁定並解析 `local-paper-slippage-clock-review-evidence.v1`，核對 session、approved bound、market manifest digest、review method、review time 與 reviewer identity/authority，且 bound 不得超過 versioned policy/horizon。
- 可選 `local-paper-fill-calibration-export.v1`；先由 `seal_fill_journal_snapshot_from_repository()` 只讀既有 `JournalRepository.session()/records()`，封存完整 Local Paper session 與所有 records 的 session root。Fill export 只能選取該 snapshot sequence range 內實際存在的全部 `local_paper_fill.v3`，逐 sequence／fingerprint／record exact match；range 可因其他 session 的 global sequence 而有間隔。Analyzer 會跨 export 拒絕重疊的同源 Journal range，也會在不同 snapshot／sequence 下按 session+record ID、session+fingerprint、idempotency identity 與 order+fill sequence 拒絕重複 evidence。最後再由既有 `LocalPaperFill.from_record()` 重播驗證 v3 monetary/reference/policy/descriptor truth。
- Analyzer、metric、timestamp、percentile、slippage 與 price-tick policy versions。

Manifest 與 report 都有 canonical `content_sha256` 及同名 `.canonical.sha256` sidecar。兩者先在同一目錄完整寫入並 `fsync`，再以 no-clobber hard link 發布；任一發布失敗會回滾本次輸出，已存在的輸出不會被覆寫。

## Fail-closed checks

每個 market session 必須同時通過：

1. 六個來源 artifact 的 manifest-bound SHA-256。
2. `verify_market_event_journal(require_finalized=True)`，且 rejected/out-of-order count 為零。
3. `verify_exact_projection_replay()`。
4. Qualification report 必須為 requested Case A / classification Case A / `PASS`、exact replay passed，且 capture symbol 的 Tick/BidAsk count 要逐 stream 與 canonical Journal 相等，並具 `SUBSCRIBE_ACKED`；同時保留 `subscribe_trade=false`、`order_path=NOT_WIRED`、flags off。
5. Instrument reference 必須是當日 `FINALIZED` 的 `instrument-reference-v1`；每個分析 symbol 都必須是 TSE/TWSE/OTC/TPEX `STK`、1000 股交易單位、價格限制適用，且 reference/limit price 全在普通股 tick grid，並可追到 frozen cohort/liquidity label。
6. Reviewer 封存的 source/receive timestamp comparability disposition；review evidence 內容與 digest 都要可驗，session/bound/market manifest/reviewer lineage 必須一致，實際 absolute skew 不得超過 reviewed、policy 與 horizon 三者中的最小 bound。
7. 每個納入分析的 Tick 都要有先到達且 source event time 也不晚於 Tick 的 non-crossed best Bid/Ask；book age 上限 3 秒，缺 book、stale book 或 causal ordering failure 即整個 session 不可用。
8. 所有 event 的 source/receive time 都落在 manifest 宣告的 Asia/Taipei phase；同一 symbol/stream 的 source/receive timestamp 不得倒退。
9. Tick/BidAsk 與 instrument reference 價格必須在普通股 tick grid；odd-lot 或 simulated market event 不可納入。

不合格 session 不會貢獻 metrics。若 session 合格但 coverage 不足，quantiles 只放在 `diagnostic_model_stress_metrics`，並標示 `DIAGNOSTIC_ONLY_NOT_BROKER_FILL_PROMISE`。

## Metrics 與分層

分組維度是 symbol、frozen cohort/liquidity tier、OPENING/CONTINUOUS/CLOSE、BUY/SELL、BEST_ASK/BEST_BID。每組輸出 sample/day coverage 與 nearest-rank p50/p90/p95/p99：

- top-of-book spread bps；
- reference price 的普通股 tick-size bps；
- crossing half-spread bps；
- manifest horizon 到期後第一筆 Tick 相對 BBO reference 的 adverse movement bps；該 Tick 還必須落在 bounded tolerance 內。只有 target 前 Tick、沒有觀察穿越 target，視為 right-censored，不得計入 adverse coverage。

可選 fill.v3 export 只輸出 configured/realized model bps 與 diagnostic slippage cost，解讀固定為 `LOCAL_PAPER_MODEL_OUTPUT_NOT_BROKER_EXECUTION`。現行 v3 沒有 exact BBO event identity，因此不把 fill 與 market event 強行 join。

## Structural coverage floor

Contract 不能低於：

- OPENING 09:00–09:30、CONTINUOUS 09:30–13:00、CLOSE 13:00–13:30；
- BUY 與 SELL；
- high、mid、low liquidity；
- frozen cohort 每個 symbol／phase／side 至少 30 個 reference samples、30 個有 horizon 的 adverse samples；
- 每組至少 5 個 reviewed 不同交易日、30 個不同 BBO identities，且 EARLY/MIDDLE/LATE 三個等長 phase buckets 都有樣本。

這是 evidence floor，不是統計充分性或 production threshold。以目前 repository artifacts 而言，需要至少 **5 個後續合格交易日**，而且每天都要補齊三個 phase 與所有 liquidity tiers；若任一日缺 Tick/BidAsk、clock disposition、exact replay 或 close coverage，該日不能計入對應 group，所需日數會增加。

## Offline commands

所有命令都只讀來源 artifact；輸出必須是新路徑。

```bash
python scripts/analyze_local_paper_slippage.py seal-clock-disposition \
  --draft /reviewed/clock_disposition.draft.json \
  --output /sealed/clock_disposition.json

python scripts/analyze_local_paper_slippage.py seal-fill-export \
  --draft /readonly-export/local_paper_fill_v3.draft.json \
  --output /sealed/local_paper_fill_v3.json

python scripts/analyze_local_paper_slippage.py seal-input \
  --draft /analysis/input_manifest.draft.json \
  --output /analysis/input_manifest.json

python scripts/analyze_local_paper_slippage.py analyze \
  --manifest /analysis/input_manifest.json \
  --output /analysis/report.json
```

`seal-fill-export` 的 draft 必須先引用 sealed Journal snapshot。Snapshot 沒有接受任意 JSON draft 的 CLI；只能由程式內 `seal_fill_journal_snapshot_from_repository(repository=..., ...)` 對既有 repository 執行只讀 `session()/records()` 後建立，repository kind 由 concrete adapter 自動判定，呼叫者不能自稱 PostgreSQL。本 task 只在 isolated unit-test model 產生 v3 fixture、先真正 append 到 `InMemoryJournalRepository` 再驗證此邊界；這類 snapshot 固定產生 `FILL_EXPORT_TEST_FIXTURE_ONLY`，不能讓分析 qualified。此 task 沒有連線 PostgreSQL，也沒有啟動 runtime 或真實下單。

`input_manifest.template.json`、`clock_disposition.template.json`、`clock_review_evidence.template.json` 與 `fill_export.template.json` 是格式範例；template 不是 evidence，只有 sealed JSON + sidecar 才是 analyzer input。Fill export 不得加入 snapshot range 不存在的 record，也不得在單一或多個 exports 間重複／重疊同一 Journal range、record、fingerprint、idempotency 或 order-fill identity；manifest 不得重複引用同一 export path 或 export id。

## Future live evidence boundary（本 task 未授權執行）

未來若另行授權 live quote evidence，優先讓既有 Freshness／late-delivery collector 產生同一份 canonical Journal、bootstrap、instrument reference、projection state 與 exact replay artifacts，再由本工具只讀分析。不得新增另一個 callback/queue/recorder pipeline。

Capture 入口仍屬既有 `market_data.late_delivery_capture_cli`／Freshness scheduled runner；任何含 provider connection 的實際參數與時段都必須另案審核。若無法共用同一次 canonical capture，OPENING、CONTINUOUS、CLOSE 必須與既有 Freshness capture 錯開，避免同時建立重複 Shioaji subscriptions。Local Paper fill export 必須從既有 Journal read-only 匯出；禁止為取得樣本而建立訂單或合成 fills。
