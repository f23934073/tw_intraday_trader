# Task Plan: Local Paper 滑價校準 evidence tooling

## Goal
在起始 merge `037197e1a3aadd7a480208f97f291cdcb6ce7a2f` 的後續 exact release baseline `7931d31e53657c4f28e684402589c2b20501c1d9` 獨立 worktree 中，建立不可變、可重播、fail-closed 的 Local Paper model stress/proxy calibration contract、離線分析器與完整測試；不得把 proxy 說成 broker execution slippage。

## Current Phase
Phase 5

## Phases

### Phase 1: 基線與能力盤點
- [x] 將此 worktree 校正到指定 merge commit 並建立 scoped branch
- [x] 盤點 `local_paper_fill.v3`、canonical market-data evidence、Freshness artifacts、Journal/replay、research tooling
- [x] 證明 A/B 校準資料能力與正式 qualification 結論
- **Status:** complete

### Phase 2: Contract 與最小設計
- [x] 定義 versioned/checksummed input manifest、report、status taxonomy
- [x] 定義 timestamp、paired ack、coverage、ordering、clock、book、lineage fail-closed 規則
- [x] 將可重用的既有 artifact adapter 與不得建立第三 pipeline 的界線寫清楚
- **Status:** complete

### Phase 3: 實作與 fixtures
- [x] 實作離線 analyzer 與 CLI
- [x] 支援 symbol/cohort/liquidity/session/side/reference/spread/tick/coverage 分層與 proxy quantiles
- [x] 加入 fixture、golden、property、tamper、replay tests
- **Status:** complete

### Phase 4: 驗證與 read-only dry run
- [x] 執行 focused/full/static/diff checks
- [x] 對現有 immutable artifacts 做 read-only dry run，確認來源未被改寫
- [x] 記錄樣本能力、缺口與後續交易日需求
- **Status:** complete

### Phase 5: Adversarial review 與交付
- [x] 在 review/commit 前 fetch 並納入最新 `origin/main`（PM 提示 `33c9b3a`），解衝突後重跑 validation
- [x] 完成第一輪獨立 adversarial review，確認 3 個 P1、3 個 P2 阻斷項
- [x] 修正 causal BBO/horizon、bounded clock authority、common-stock descriptor/tick eligibility
- [x] 修正 per-symbol paired ack、phase/unique-book coverage、reviewed trading-day lineage
- [x] 修正 fill Journal/range/root lineage、duplicate inflation 與 JSON/checksum 原子封存
- [x] 第二輪 review 關閉原 6 項，但發現 clock evidence content 與 fill repository provenance 仍有 2 個 P2
- [x] 將 clock evidence 改為 session/bound/market-manifest/reviewer-bound schema
- [x] 將 fill evidence 改為只由既有 `JournalRepository.session()/records()` 產生完整 sealed snapshot，再 exact-select fills
- [x] 以 stash `84f111f...` 保存精確 payload，fetch/fast-forward exact `origin/main@7931d31e...` 並無衝突恢復
- [x] 檢查 Shadow fill.v3 / PostgreSQL TIMESTAMPTZ-fingerprint 新語意並重跑全部驗證
- [x] 最終獨立 adversarial review 無未解 P1/P2
- [x] 重跑必要驗證並檢查 scoped diff
- [x] 建立單一 scoped local commit（不 push、不建 PR）
- [x] 準備回報 artifacts、測試、commit 與 A/B 結論
- **Status:** complete

## Success Criteria
- 資料沒有 broker order-fill authority 時，正式狀態必為 `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`。
- Proxy 指標只標示為 `MODEL_STRESS_PROXY`，不得宣稱真實成交滑價或 broker fill promise。
- 所有輸入、輸出與 lineage 都有 version、canonical checksum；tamper/coverage/ordering/clock/book/lineage 不合格均 fail closed。
- 相同 sealed input 重播得到 byte-identical 或 contract 定義的 deterministic output。
- 既有 evidence dry run 不改寫來源，且無 Shioaji/live/broker/account/order/CA/trade callback 行為。
- Focused/full/static/diff checks 通過，adversarial review 無未解 P1/P2。

## Key Questions
1. 現有 artifact 是否真的同時含可比較的 fill reference、fill price 與 canonical Tick/BidAsk 時序？
2. 哪些既有 artifacts 能安全產生 model stress proxy，哪些只能產生 `INSUFFICIENT_EVIDENCE`？
3. 現有 project conventions 對 immutable manifest、digest、exact replay 與 CLI 放置在哪裡？
4. 在不發明 live 數據的前提下，需要幾個後續交易日才有各 session/liquidity cohort 的最低 coverage？

## Decisions Made
| Decision | Rationale |
|---|---|
| A 與 B 以不同 qualification status 表示 | 防止 proxy 被誤讀為實際 broker execution calibration |
| 優先 adapter 既有 canonical evidence 與 fill.v3 | 不建立第三條行情 pipeline |
| 所有不確定或缺欄位狀態 fail closed | Evidence tooling 不可用推測補齊 authority 或資料品質 |
| Scoped branch 固定為 `codex/slippage-calibration-evidence-20260827` | 依監督修正，避免使用先前暫擬分支名 |
| 基線以 fetch 後的 `origin/main`、`FETCH_HEAD`、exact HEAD 與 ancestor checks 共同封存 | 防止 stale local main 或 abbreviated ref 誤判 |
| 本基線的 A 結論固定為 `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED` | 無 broker order-fill authority；fill.v3 是 `execution_authority=false` 的模型結果 |
| 現有 artifacts 的 dry run 允許 `MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED` | Fail-closed 本身是正確 evidence，不得為了輸出 quantile 放寬缺失的 clock/ack/coverage lineage |
| 實作完成後、review/commit 前納入最新 origin/main | PM 已同步 main 前進至 docs-only `33c9b3a`；避免從過時 merge base 交付 |
| 第一輪 adversarial review 為 Request changes | 測試雖全綠，但 causal horizon、clock bound、instrument eligibility、coverage、fill lineage 與 pair sealing 仍可被 adversarial input 繞過，tooling 不得宣稱 complete |
| 最終交付 baseline 更新為 `7931d31e...` | PR #4 已整合 Shadow fill.v3 compatibility 與 PostgreSQL fingerprint/corruption hardening；舊 `33c9b3a` staged review 不再足夠 |

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| 初始 detached HEAD `a6e096a` 不以指定 `037197e` 為 ancestor | 1 | 工作樹乾淨；Phase 1 將只在此 worktree 校正至指定 commit，不帶入 divergent 變更 |
| `git switch` 無法建立 worktree metadata 的 `index.lock`（sandbox `Operation not permitted`） | 1 | 不重試相同 sandbox 操作；依授權使用受控權限 fetch 並建立指定 scoped branch |
| 首次 plan error-log patch context 順序不符 | 1 | 重新讀取 planning files 後使用精確 context 更新 |
| Phase 2 completion patch 的 context 順序不符 | 1 | 分離檔案區塊並用目前內容精確更新 |
| 此 worktree 沒有 `.venv/bin/python`，system Python 又沒有 pytest | 1 | 只讀使用主 repo 既有 `.venv` interpreter，pytest cache/output 仍寫在本 worktree/temp |
| Manifest sealer 在加入 artifact digests 後、加入 content digest 前誤用 sealed validation | 1 | 以 provisional valid digest 完成結構驗證，再交由 write-once sealer 計算正式 digest |
