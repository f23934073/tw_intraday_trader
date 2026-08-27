# R6 G3 Eligibility Remediation Plan

## Goal

修正 R6 G3 在 immutable FinMind Dataset 上因固定 `12:45` Kbar anchor
覆蓋率不足而 deterministic fail 的契約與執行流程，同時維持：

- 七個策略共用同一個、純 Dataset 衍生的 eligibility 邊界；
- 同 session next-observed-bar entry；
- 不補合成 Kbar、不 carry overnight、不依績效排除樣本；
- family head `0`、attempts `0`，G4 維持關閉；
- 任何 protocol identity 變更先經獨立 Review，再實作新的 additive revision。

## Current disposition

```text
R6 G3 revision 2: FAILED / DETERMINISTIC ELIGIBILITY CONTRACT MISMATCH
Formal preflight: 0
Formal attempts: 0 / 7
G4-G5: NOT AUTHORIZED
A2 code candidate: APPROVED / CONTRACT FROZEN
Migration 018: APPLIED / SCHEMA ONLY
Matrix revision 3: NOT CREATED
```

## Phases

### Phase 0: Operational containment

- [x] 經明確授權後卸載目前會重複啟動的 launchd job。
- [x] 保留目前 staging 與 stderr/status evidence，不覆用為正式 artifact。
- [x] 修正 supervisor one-shot claim，讓同一 run root 最多執行一次。

### Phase 1: Source-only eligibility audit

- [x] 對完整 28,325,340 根 immutable Kbar 只做 timestamp/cadence audit。
- [x] 輸出 exact observed/eligible/excluded、missing reserve/13:30、年度與 symbol 分布。
- [x] 驗證 sparse minute bars 是來源語意，而非 materialization 遺漏。
- [x] 產生 canonical diagnostic artifact；不得建立 preflight/attempt。
- [x] 實作 source-only audit 與 canonical replay verifier；正式全量執行仍待 Review。

### Phase 2: Freeze Amendment A2

- [x] 將固定 exact-12:45 reserve 改為 source-derived session reserve：
  `entry_reserve_at = last observed same-symbol Kbar at or before 12:45`。
- [x] 只有 `signal_at < entry_reserve_at` 才可評估，保證 next observed entry
  存在且不晚於 12:45。
- [x] `13:30` terminal exit 仍必須 exact，缺少時共同排除。
- [x] eligibility mask 在任何策略 runtime 前建立，七個 slot 共用。
- [x] 完整 dry-run 後保留 `minimum_eligible_ratio = 0.95`；不得為過 Gate
  直接調低門檻。
- [x] 凍結 schema、reason codes、digests、identity dependency 與負向測試。
- [x] 完成獨立 Review，取得 `A2 CONTRACT FROZEN`。
- [x] 建立 exact Amendment A2 implementation candidate 與 Review 文件。

### Phase 3: Additive implementation

- [ ] 新增 protocol/build-binding/algorithm identities，不覆寫 revision 2。
- [x] 以 forward-only Migration 018 擴充 revision-3 schema；未建立 matrix，head/attempts 仍為 0。
- [x] 更新 preflight source-only eligibility 與 artifact verifier candidate。
- [x] 增加 sparse-bar、late reserve、missing exit、cross-session、synthetic-bar 負向測試。
- [x] 更新 versioned preflight eligibility 與 artifact verifier candidate。
- [x] 增加 sparse reserve、reserve boundary、missing source boundary 與 audit tamper 測試。
- [x] 修正 supervisor 同一 run root 自動重跑問題。

### Phase 4: Formal execution

- [x] 先執行 source-only audit並驗證完整 Dataset count/SHA/EOF。
- [ ] 再執行一次正式七-slot G3 preflight。
- [ ] 獨立驗證 artifact、PostgreSQL registration、head `0`、attempts `0`。
- [ ] 另行 Review 通過後才授權 G4。

## Prohibited shortcuts

- 不把 `0.95` 任意改成目前觀測到的比例。
- 不 forward-fill 或製造 `12:45`/`13:30` Kbar。
- 不依某一策略是否觸發或績效好壞選擇 symbol-session。
- 不把失敗 staging 當成可續跑的 immutable authority。
- 不在本 remediation 中啟動 G4、Local Paper、broker 或 real-money。

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `rg` 搜尋整個 `data/backtest` manifest 產生過大輸出 | 1 | 後續只讀 exact manifest path/fields，不再廣域搜尋大型 canonical manifests。 |
| launchd submitted job 在非零 exit 後自動重跑 | 3 runs | 已卸載 job；加入 `O_EXCL` durable worker claim，同一 run root 的後續 invocation 在任何 DB/Dataset 操作前安全返回。 |
| A2 audit 未綁定 durable family scope，且 audit/preflight 各自累積 anchors | Review 1 | Audit v2 封存 revision-2 scope 與 candidate identities；兩條路徑共用同一 source accumulator，並加入 scope/totals/parity 負向測試。 |
