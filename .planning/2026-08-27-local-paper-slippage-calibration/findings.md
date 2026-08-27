# Findings: Local Paper 滑價校準

## Requirements
- 只在本 task worktree 工作；基線必須是 main merge commit `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`。
- 不啟動 Shioaji/live capture，不碰 broker/account/order/CA/trade callback，不 push、不建 PR。
- 建立 immutable/versioned/checksummed input manifest、analysis report、qualification taxonomy。
- 重用 canonical market-data/immutable capture 與 `local_paper_fill.v3`，不得建立第三行情 pipeline。
- Analyzer 必須分層並驗證 timestamp comparability、paired Tick/BidAsk ack、coverage、out-of-order、clock skew、missing book、policy/version/descriptor lineage。
- 產出可重播 proxy metrics/quantiles，但只屬 model stress evidence。
- Fixture/golden/property/tamper/replay、focused/full/static/diff checks、read-only dry run、adversarial review。

## Initial Baseline Finding
- 初始 worktree 為乾淨 detached HEAD `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`。
- `git merge-base --is-ancestor 037197e... HEAD` 回傳 1；共同 ancestor 是 `657c3bb`。
- `037197e` 是 `origin/main` merge commit：`Merge pull request #2 from .../codex/local-paper-tax-slippage-20260826`。
- 因此初始狀態不符合使用者基線；需先只在此 worktree 校正至 `037197e`。

## Corrected Baseline Evidence
- `git fetch --no-tags origin main` 成功；`origin/main` 與 `FETCH_HEAD` 均為 `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`。
- 在此 worktree 建立 `codex/slippage-calibration-evidence-20260827`；HEAD 精確為 `037197e`。
- 指定 ancestry：`34fb5250030d170b7909870f086c5693f728a9aa`、`99ece089bac488f3b5b2493d626d968193be7b6f`、`786f45212f822ae0514957adac748c00fb6a95fa` 均為 HEAD ancestors。
- `git diff --name-only 037197e` 為空；status 唯一內容是本 task 的 untracked isolated plan directory，沒有 `a6e096a` 產品碼差異。

## Research Findings
- `trading/local_paper.py` 定義 `LOCAL_PAPER_FILL_V3_KIND = "local_paper_fill.v3"`，v3 evidence 已包含 `reference_price`、`reference_source`、`configured_slippage_bps`、`realized_slippage_bps`、`slippage_cost`、`slippage_policy_version` 與 monetary/descriptor fields，且 replay 會驗證 fixed adverse slippage。
- README 明示現行 5 bps 是 `ASSUMPTION_NOT_LIVE_CALIBRATED`；模型缺 queue priority、depth、market impact、fill probability 與 broker accounting，因此不能支持 A 類真實 execution calibration。
- Canonical market evidence 已存在於 `records/market_events/...`，包含 checksummed manifest、instrument reference、canonical Journal/exact replay 路徑；應做離線 adapter，而不是新建 capture/ingress。
- Freshness research 已有 opening/continuous/close artifacts、paired Tick/BidAsk acknowledgement 與 source-clock/coverage disposition；其 threshold 尚未完成，不可沿用為已通過的 slippage threshold。
- Repository 內有 canonical SHA-256 sidecar 與 immutable research artifact conventions，可重用 canonical JSON digest 寫法。
- 初步搜尋未證明 repo 內有真實 broker order/fill authority 的成交樣本；正式 Gate 暫定 A=`ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`，待 targeted inventory 確認。
- Targeted 搜尋顯示 repository 內沒有 persisted `local_paper_fill.v3` artifact；只有 unit/integration tests 產生 v3 record。這代表現有 immutable market artifacts 與 fill.v3 目前沒有可直接 join 的同日實例。
- `local_paper_fill.v3` 強制 `execution_authority is False`，其 `fill_price` 是 frozen `fixed_adverse_bps_v1` 的 deterministic model output，不能反向當成實際成交 calibration target。
- 現有 `records/market_events` 有 finalized 與 incomplete Journal。2026-08-24 opening artifact 有 35,118 records 且包含相鄰 Tick/BidAsk，但 manifest 是 `INCOMPLETE`；正式 analyzer 必須拒絕，不能因 record 很多而放寬。
- Finalized Journal manifest 必須有 queue drained、finalized time、records SHA-256 與 bar/book projection digest；可作 B 類 proxy 的 sealed input候選，仍需再驗 timestamp/paired ack/coverage/lineage。
- 兩個 5 分鐘 `hqual` Journal 都 finalized/exact replay pass、Tick/BidAsk 皆有樣本，但 qualification report 為 `FAIL/CASE_B`；一個 60 秒 `tm-postfix` 是 `PASS/CASE_A`，仍只有單一 symbol、continuous phase、單日且沒有 fill.v3。
- Freshness scheduled evidence 有 opening/continuous paired acknowledgements，但 status 是 `REVIEW_REQUIRED_PARTIAL_COVERAGE`，low-liquidity `1530/TICK` 缺失且 source-clock skew 大量保留；沒有 qualified close evidence。它不能替未來 slippage manifest 自動背書。
- Phase 1 正式結論：A 不合格；B 的 analyzer/tooling 值得建立，但 current repository artifacts 只適合 read-only fail-closed dry run，不足以作 qualified multi-cohort/multi-phase calibration。

## Technical Decisions
| Decision | Rationale |
|---|---|
| 預設正式 A 狀態為 `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`，只有受權威 broker fill input 支持才可能改變 | 本 task 明確禁止 broker execution authority，且 proxy 不能替代實際成交 |
| Analyzer 讀 sealed artifact paths，不負責 capture | 保持 canonical ingress 單一路徑並確保 dry run read-only |
| Input manifest 綁定 cohort、每個 canonical session 的六個 artifact digest、可選 clock disposition 與可選 fill.v3 export | 同時驗證 byte integrity、exact replay、quality/ack、descriptor、clock 與 fill lineage |
| 固定最低結構 coverage：OPENING/CONTINUOUS/CLOSE、BUY/SELL、high/mid/low、每 group 30 個 reference/adverse、30 個 unique BBO、EARLY/MIDDLE/LATE buckets、5 個 reviewed trading days | 這是 evidence 結構 floor，不宣稱統計充分或 production threshold；manifest 只可提高，不能放寬 |
| 無 reviewed clock disposition、任何 out-of-order/rejected record、missing book、digest/version/descriptor mismatch 都使 session 不可用 | 符合 fail-closed 要求；不從不合格 session 產生可用 calibration metrics |
| 未達 coverage 但 session 本身合格時，可輸出明示 `DIAGNOSTIC_ONLY_NOT_CALIBRATION` 的 deterministic metrics | 保留可重播研究訊號，同時阻止被誤用成已校準參數 |
| `local_paper_fill.v3` metrics 單列為 model-output diagnostics，不與 BBO proxy 混成 broker execution truth | v3 fill price 是固定模型結果，且現有 schema 沒有可證明 exact BBO event join 的 identity |
| Session phase 固定為 OPENING 09:00–09:30、CONTINUOUS 09:30–13:00、CLOSE 13:00–13:30（Asia/Taipei） | 覆蓋完整日內三層，並與既有 OPEN/CLOSE collection 邊界相容 |
| Horizon 使用 target 到期後第一筆 Tick，且必須在 bounded tolerance 內；BBO 同時要求 receive/source causal ordering 與 3 秒最大 age | 防止 target 前最後 Tick、source-future book、stale/reused BBO 或 right-censored sample 虛增 coverage |
| Clock disposition 綁 independent review artifact digest，bound 不得超過 1 秒 policy/horizon | 防止以任意巨大 self-sealed clock bound 取消 timestamp comparability |
| 第二輪前的 declarative fill source metadata/root 設計已 superseded | 它雖能防 sealed artifact tamper/duplicate，仍不能證明 submitted record 實際存在於 Repository |
| 第三版 fill provenance 不接受任意 source metadata draft；只能呼叫 `seal_fill_journal_snapshot_from_repository()` 讀既有 Repository session/records，封存完整 session root，export 再 exact-select range 內全部 v3 fills | 第二輪 reviewer 證明 declarative store-root 仍可用 synthetic record 自我宣告；repository snapshot 才能把存在性綁到既有 Journal authority |
| Clock review evidence 使用 versioned parsed schema，綁 session、bound、market manifest、review method/time 與 reviewer identity/authority | 第二輪 reviewer 證明只驗任意檔案 SHA 仍是 self-asserted；內容必須 fail-closed 驗證 |

## Issues Encountered
| Issue | Resolution |
|---|---|
| Worktree 初始基線錯誤 | 記錄後校正到指定 merge commit |
| Sandbox 禁止寫入 `/Users/stevehuang-work/Documents/tw_intraday_trader/.git/worktrees/tw_intraday_trader2/index.lock` | 產品碼未變更；依明確授權用受控權限操作本 worktree metadata |
| Scoped branch 首次檢查回傳 ref 不存在 | 符合監督條件「如同名不存在」；隨後從 exact commit 建立 |

## Upstream Synchronization Requirement
- PM 通知 `origin/main` 已由 docs-only architecture PR #1 前進到 `33c9b3a`。
- 不需中斷目前 evidence-only analyzer/CLI 實作；但 adversarial review 與 local commit 前必須 fetch、納入最新 main、解衝突並重跑 required validation。
- 納入 upstream 不會把 tooling existence 改寫成 threshold 或 calibration gate passed。
- Fetch 後 `origin/main`/`FETCH_HEAD` 均為 `33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`；本 branch 由 `037197e` fast-forward，只有 README/architecture atlas upstream 變更，無衝突。

## Final Release Baseline Synchronization
- PM 更新 remote main exact baseline 為 `7931d31e53657c4f28e684402589c2b20501c1d9`；包含 PR #4、`f6a38b1` TIMESTAMPTZ/fingerprint reconstruction 與 `254317b` corruption UAT。
- 同步前完整 staged payload 已以 stash commit `84f111f987a0f38e9516d2e43297b6027679db57` 保存；工作樹清空後 fetch，`FETCH_HEAD`/`origin/main`/branch HEAD 三者 exact 相等。
- `33c9b3a..7931d31` fast-forward 無衝突；恢復 stash 後仍只有原 16 個 scoped staged files，無 unstaged change，stash 暫留至 final commit 後再清理。
- PostgreSQL adapter 的 `session()` / `records(after_sequence=...)` port 未改；新 adapter 會從 storage envelope 還原原始 aware timestamp 並重新驗證 domain fingerprint，corruption 會丟 `JournalConflictError`。這與 snapshot sealer 的 read-only full-session/fingerprint verification 相容，且更 fail closed。
- Exact `7931d31e...` 重驗：slippage + PostgreSQL/Shadow compatibility focused `33 passed, 4 skipped`；final full `1533 passed, 44 skipped in 10.53s`；compileall/template JSON/diff/source-read-only checks 通過；dry replay report/sidecar byte-identical。
- Baseline 更新沒有改變 dry-run qualification：A=`ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`；B=`MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED`；42 expected / 0 qualified / 0 metrics groups，report digest仍為 `6b2fcb46...`。
- Final full suite 後 shared Git metadata 曾包含其他 worktree fetch entries；再次執行單一 `git fetch --no-tags origin main` 後立即驗證 `FETCH_HEAD`/`origin/main`/HEAD 皆 exact `7931d31e...`。產品/staged payload 不受影響。
- 同一獨立 reviewer 在 exact final baseline 做 closed-loop review，確認先前所有 findings 關閉，final disposition=`Approve`、unresolved P1/P2=`0`；focused `33 passed`、cached diff check 與 sealed dry Gate 均通過，review 全程唯讀。

## Implementation and Dry-run Findings
- 新增 `trading/slippage_calibration.py`：純離線 sealing、manifest/report verification、Journal/exact replay、quality/paired ack、clock、descriptor、coverage、BBO/Tick proxy 與 fill.v3 model-output diagnostics。
- 新增 `scripts/analyze_local_paper_slippage.py`：只有 `seal-input`、`seal-clock-disposition`、`seal-fill-export`、`analyze`；沒有 provider/runtime/order path。
- Structural floor 固定不可放寬：每個 frozen cohort symbol × 3 phases × 2 sides，共 42 groups；每組至少 30 reference、30 horizon-adverse samples、5 distinct days。
- 第一輪獨立 adversarial review 為 `Request changes`：3 個 P1（causal/stale/right-censor、unbounded clock、common-stock eligibility）與 3 個 P2（per-symbol ack/coverage、fill source/duplicate lineage、非原子 sidecar）。全部已以 contract 收緊與 negative/qualified-path tests 修正，等待第二輪 disposition。
- 第二輪 review 確認原 6 項皆關閉、無 P1，但仍有 2 P2：任意 clock review content 會通過、fill root 可宣告而不源自 Repository。兩項均已改為 parsed evidence / read-only Repository snapshot，等待第三輪 disposition。
- Focused fixture/golden/property/tamper/replay/atomic/qualified-path tests：`17 passed`。
- Read-only dry run 綁定三個 finalized 2026-08-21 canonical sessions與 reviewed calendar，沒有改寫 records；input digest `06abc070...`、report digest `6b2fcb46...`。
- Dry-run 正式結果：A=`ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`；B=`MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED`。原因包含 quality FAIL、缺 reviewed clock disposition、out-of-order/rejected、缺 fill.v3、coverage 0/42。
- 相同 sealed manifest 的第二次 replay 與原 report/sidecar byte-identical（兩個 `cmp` 都 exit 0）。
- 修正後重驗：focused `17 passed`、full `1517 passed, 43 skipped`、compileall/template JSON/diff check pass、dry-run report byte-identical。

## Resources
- `.planning/2026-08-27-local-paper-slippage-calibration/task_plan.md`
