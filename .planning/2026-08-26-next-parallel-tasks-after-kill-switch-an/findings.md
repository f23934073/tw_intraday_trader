# Findings & Decisions

## Requirements
- 分析剛完成的 Kill Switch 與 Local Paper tax/slippage 兩個獨立任務。
- 提出下一批可以同時處理的工作，清楚標示依賴、衝突、交易時段與外部環境需求。
- 只做分析，不啟動任務、不修改產品程式。

## Research Findings
- 本任務開始前 active plan 是 `2026-08-25-pr-tm-012c1-c1-runtime`；完成後還原。
- 既有 memory 提醒：Local Paper、broker-account authority、Production Shadow Gate 與 real-money execution 必須分開；memory 可能較舊，最終判斷以兩個 current task 與 live repo 為準。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 將「成果整合」視為 Wave 0 | 兩個 task 若仍在不同 worktree，任何後續共同 regression 都不可信。 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- Kill Switch task `01a03dd3-8fb2-7710-a73b-f7903c522c97`
- Tax/slippage task `01a03dee-ef4c-7250-ba0c-761b3e103b31`
- `/Users/stevehuang-work/.codex/memories/MEMORY.md`
# 已完成任務證據

- Kill Switch durability 本機提交：`34fb5250030d170b7909870f086c5693f728a9aa`。
- Local Paper 稅費／滑價本機提交：`99ece089bac488f3b5b2493d626d968193be7b6f`。
- 提交順序為 `origin/main -> Kill Switch -> 稅費／滑價`，因此後者已包含前者；後續任務應從整合後的共同基線分支，避免重複或倒序 cherry-pick。
- 稅費／滑價最終獨立審查為 APPROVE；focused `241 passed, 1 skipped`、PostgreSQL UAT `5 passed`、full regression `1500 passed, 43 skipped`，未解 P1/P2 為 0。
- 真實市場滑價校準仍是後續 evidence 工作，不能把目前的 Local Paper 模型驗證當成真實成交校準。

# 尚待刷新

- Kill Switch 任務最後一個可見回合正在處理共同分支的 push／PR／CI／merge；使用者表示兩個任務已完成，但仍需重新讀取最新狀態，才能判定遠端整合是否已完成。
- FreshnessPolicy、broker/account freshness、No-Overnight 正式 PostgreSQL UAT、Production Shadow C1 live qualification 等 Gate 需以目前 repo/artifact 再確認。

# Current gate 狀態

- 兩個既有任務目前都再次顯示 `inProgress`：Kill Switch 視窗正在補 CI workflow／共同發布，Tax/Slippage 視窗也收到 push branch／建 PR 的要求。這兩個視窗若同時發布同一 branch 會有協作重疊；應以單一發布 owner 完成共同 PR/CI/merge，其他新 code 任務先不要從 `main` 分支。
- 主工作區 `main@a6e096a`，相較 `origin/main` ahead 19，且有大量既有 dirty/untracked 研究與規劃檔；不適合作為下一批獨立任務的乾淨共同基線。
- Freshness evidence 截至 2026-08-26：quote collector 正常且已有 10 個合格結構 artifact，但 normal 13:15–13:35 close artifact 與跨更多交易日證據仍不足；source clock comparability 未解。
- Broker/account freshness 截至 2026-08-26：10 個 artifact 結構與 no-mutation guard 通過，但 positions/accounting 只有 `AUTH_DENIED`／`SOURCE_ERROR`，buying power 無合格 source，orders refresh path 因安全範圍排除；無任何成功 freshness observation。
- 因此八個 FreshnessPolicyV1 thresholds 仍全數 unset，`BLOCKING_EVIDENCE`；Portfolio Phase 1 仍不得啟動。
- Trade Management Shadow C1 runtime code 已完成，但正式 Production Shadow Gate 仍 `NOT_PASSED`；完整 session 必須保持 `execution_enabled=false`，且需 reviewed input bundle、兩個分離 DSN、full-session coverage、PostgreSQL recovery/replay。沒有 authoritative Local Paper BUY fill 時只能記 `INSUFFICIENT_EVIDENCE`，不可製造 fill。
- No-Overnight 設計/實作有多個獨立 PR-NO worktree；仍需窄化確認 PR-NO-004/005/006 各自 Gate 與是否已整合進共同基線。

# Final dependency analysis

- 共同發布 branch `codex/local-paper-tax-slippage-20260826` 已 push，PR #2 已建立；CI／merge 在最後刷新時仍進行中。發布 owner 已在 Kill Switch 視窗處理，不應再開第二個相同發布流程。
- PR-NO-006 branch 目前相較 `origin/main` 為 `21 behind / 7 ahead`；與 Kill Switch + Tax/Slippage 共同候選重疊 19 個核心檔案，包含 `runtime/composition.py`、`simulation/application.py`、`simulation/service.py`、`trading/local_paper.py`、Dashboard 與相關 tests。因此下一步不能直接 merge 舊 No-Overnight branch，必須做 forward-port／rebase、schema reconciliation 與共同 PostgreSQL UAT。
- PR-NO-006 程式與 runner 已獨立 review 通過，但正式 evidence campaign 尚未執行：DISABLED、OBSERVE_ONLY、supervised ENFORCING 與三個 drills 全未完成；PostgreSQL destructive/restart/concurrency UAT 仍是 `WAIVED / NOT RUN / NOT PASSED`。
- PR-NO-006 已為 2026-08-27 舊 code identity 做 conditional preflight GO。若直接執行，證據只資格化舊候選，不資格化含 Kill Switch + fill.v3 的整合版本；整合後仍需重跑 campaign。
- Trade Management Shadow 的 `ExistingPaperFillObserver` 與 `PaperFillThesisBuilder` 目前只接受 `local_paper_fill.v1`。新 Local Paper v2 session 會寫 `local_paper_fill.v3`，所以 C1 即使其他 preflight 成功，也看不到新的 authoritative BUY fill。這是可與 No-Overnight forward-port 平行修的獨立相容性 blocker。
- 每日最大虧損不是全新缺功能：目前已用交易日 opening equity 計算，達限會阻擋新 automated entry、仍允許風險降低 SELL，effective policy 也有 durable activation／restart drift tests。較合理的下一步是整合後做 read-only audit／組合測試；若有 finding 再修，不應先重做一套 daily-loss store。
- 真實滑價仍未校準；可以先做 evidence schema、離線分析與分層規則，但正式校準至少要跨多個交易日／流動性／session period，而且應重用 canonical market-data evidence，不建立第三條行情 pipeline。

# Recommended waves

1. Wave 0（正在做）：PR #2 CI／review／merge，建立唯一共同基線。
2. Wave 1A：No-Overnight forward-port + combined PostgreSQL UAT（code lane）。
3. Wave 1B：Shadow fill.v3 compatibility（code lane，與 1A 低重疊，可平行）。
4. Wave 1C：Freshness quote close evidence + broker/account source diagnosis（evidence lane，已進行，可平行）。
5. Wave 1D：Slippage calibration contract／offline analyzer（research lane，可平行）；實際 live capture 與其他 Shioaji campaign 分時或共用 canonical artifact。
6. Wave 2：在 1A 整合完成後做 daily-loss combined audit、No-Overnight formal campaign 與 Shadow C1 formal session；Portfolio Phase 1 仍等 FreshnessPolicy freeze。
