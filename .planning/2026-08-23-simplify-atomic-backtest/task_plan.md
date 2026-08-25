# 簡化原子策略回測流程

## 目標

移除歷史回測頁面的「準備歷史資料」與「舊版固定策略回測」，並讓原子策略回測由伺服器自動鎖定可用的 READY 歷史資料快照，不再要求使用者選擇資料集。

## 邊界

- 保留 PostgreSQL immutable Run、Dataset、Strategy Set 與結果證據鏈。
- 不修改背景 FinMind 三年資料下載流程。
- 不直接讀取仍在變動的 checkpoint／canonical store 執行回測。
- 不修改 Local Paper、券商或 real-money execution。
- 保留工作樹中既有且與本切片無關的變更。

## 階段

- [completed] Phase 1：盤點 Dataset／Atomic Run 契約、FinMind 資料橋接與現有 UI／測試。
- [completed] Phase 2：實作三步 UI、伺服器端自動選取 READY Dataset、移除舊版表單。
- [completed] Phase 3：補齊 API／UI regression，執行互動與全套驗證。

## 驗收條件

1. 歷史回測只顯示「設定策略組合 → 回測工作與結果 → 比較與資格判定」。
2. 不再顯示或提交 Dataset 選擇欄位。
3. Atomic Run 由伺服器決定並保存實際使用的 READY Dataset identity；無 READY Dataset 時 fail closed。
4. 「舊版固定策略回測」整段 UI 與瀏覽器 mutation 路徑移除。
5. 既有結果、比較、Qualification、immutable snapshot 契約不退化。

## Errors Encountered

- 首次讀取參照 task 時使用 `turnLimit=20`，超過工具上限 10；改為 10 後成功讀取。
- 首輪 focused test 有 1 個舊 assertion 仍要求 clone 流程包含 `if (atomic)`；Atomic-only 流程已改為 fail-closed `if (!atomic)`，同步更新測試後重跑。

## 驗證結果

- Focused regression：`39 passed, 3 skipped`。
- Full no-DSN regression：`1255 passed, 23 skipped`。
- Python compilation、Dashboard JavaScript syntax、`git diff --check`：通過。
- 本機 Browser：三個 workflow tab 均可切換；「準備歷史資料」與「舊版固定策略回測」DOM count 都是 0；console error 為 0。
- 未設定 `TEST_POSTGRES_DSN`，因此 PostgreSQL-only tests 本輪未執行。
