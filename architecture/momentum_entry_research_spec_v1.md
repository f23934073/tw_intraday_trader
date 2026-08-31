# Momentum Entry Research Specification v1

## 0. 文件狀態與三層時間界線

```text
DOCUMENT_KIND=RESEARCH_SPEC
SYSTEM_ACTIVATION=DISABLED
CURRENT_CONTRACT_IMPLEMENTATION=SLICE1_AND_SLICE2_LANDED
RUNTIME_MIGRATION=NOT_PERFORMED
QUALIFICATION_AUTHORITY=NONE
```

- 本文件是 doc-only 的研究需求、歷史證據、current-as-built overlay 與未決政策登錄；它不是 runtime authority。
- Slice 1 與 Slice 2 的純合約／producer-payload 修補已落在 current main；這不代表 controller、journal、selection 或 qualification 已完成 migration。
- 本文件不修改任何產品程式、設定、資料或 activation 狀態，也不授權任何回測或 LocalPaper 結果升格。
- 原始文件在 `HISTORICAL_BASELINE` 的狀態字樣為 `RESEARCH_SPEC_ONLY / NO_IMPLEMENTATION / NO_ACTIVATION`；其中 `NO_IMPLEMENTATION` 只描述當時文件本身，**不是** current-as-built 仍無 Slice 1/2 implementation 的主張。
- 建立日期：`2026-08-29`；R2 status overlay：`2026-08-31`；R4 doc remediation：`2026-08-31`（僅更正時間分層與已綁 code 事實）。

本文件將事實分為三層，不得互換：

1. `HISTORICAL_BASELINE @ 66e6c3aa… + recorded dirty manifest`：保留原始來源、manifest、觀察與外部 transcript 綁定。
2. `CURRENT_AS_BUILT @ d9151df…`：只以固定的 `d9151df877d1e801e1815ff3f38cccf976690654` commit／`aba8bd9227c6c0948f0a1e8fac32ad67ef8ef41e` tree、repo-local lineage、目前合約與 call path 為準；其後的 `a151795…` exact-six hygiene 只改 repo envelope，不重綁本層。
3. `UNRESOLVED / FUTURE AUTHORITY`：第 4 節的政策值與 runtime migration；歷史觀察與純 DTO 均無權代答。

### 0.1 HISTORICAL_BASELINE 來源綁定

| 項目 | 值 |
|---|---|
| Repo HEAD | `66e6c3aa25b83e84a9bd2cc38fee3cf777b9a931` |
| HEAD summary | `feat(backtest): opt-in backtest-engine-v3-tw formal Taiwan execution/evidence seam` |
| Working tree | **DIRTY**。判定內容來自工作區當下狀態，非 HEAD commit 內容。 |
| 綁定方式 | 逐檔 SHA-256 manifest（見 0.2），**不**使用 dirty 檔案計數 |
| 外部 transcript | `2026-08-29-tw-strategy-settings-consensus-transcript.md` |
| Transcript SHA-256 | `71b044ff85c89fb4e3c203ab86613d1318ed38e6b6a3a7e1f665a8f16c8c1f33` |
| 外部 task ID | `task-042`（僅存在於外部 planner；本文件以外的 repo 內容無此字串，見 0.3） |

> **不使用 dirty 檔案計數的理由**：該計數會被本文件自身的建立與每一次修訂改變（本文件建立前為 34，建立後為 35），是自我指涉且不穩定的量，不足以作為稽核錨點。0.2 的逐檔 manifest 取代之。

> **Traceability finding (P1)**：`task-042` 在 repo 內沒有 planning ID，也沒有 task → base SHA → reviewed paths → commit → evidence 的對照。外部 transcript 一旦遺失，治理來源無法由程式庫自行重建。本文件已以 transcript SHA-256（0.1）、逐檔 manifest（0.2）與全域否定命題檢索記錄（0.3）部分緩解，但 4.9 的決策（規格文件是否應強制綁 clean commit）仍未解。

### 0.2 HISTORICAL_BASELINE 已檢查路徑 manifest

以下是原始文件第 2 節**逐檔判定**的歷史證據基礎，附建立當下 dirty working tree 的逐檔 SHA-256。這些 hash 不得被重標為 current；任一 current 判定一律看 0.3 與 0.7。

| 路徑 | SHA-256 |
|---|---|
| `config/momentum.py` | `61dc86e9ae6c47c4c236e63da025944e4554e54574c40d4ced3d54e1358c774c` |
| `config/local_paper.py` | `cc982e86fc8d1eda8c9a24ceb675a828a88a9f41cb1c6664045a382c13405469` |
| `config/no_overnight.py` | `58de6eb8d12c192fd0298c8ae8339c8c43aced469b5d775a903ac8f19a69f4e5` |
| `signals/models.py` | `b7547101c75e9c2dcb5eda082062301029aeaad1dc6901642f0c7b29e5e93b84` |
| `signals/opening_momentum.py` | `a2613d62b75db78bcb8763e95a11d0c16063ddfba12afb8e74e3b5a50b05aea6` |
| `signals/momentum.py` | `bf31c83c3e3166a4defa90fa978cb69fb9f924129950c8a5847adbd7382e647a` |
| `signals/momentum_state.py` | `5fe39ca777508e1e7a11ee7fa7cdfa4a682711bd03eaa8c7f8d2ab5fbecb5ab1` |
| `signals/projection.py` | `8ee1e3a23a96a5f4556fbf1e90cc88ce1d5fd5921aab5e936ea41eb3509a293c` |
| `features/models.py` | `1fbfda954cf0434f98237204d6c8b43f1b3f54c372d48b5d4628f4aa2703060f` |
| `features/engine.py` | `26f59e9b0d031231474b4776c02244734c874d00867be03dcaddb7f4f1d00434` |
| `simulation/continuous_strategy.py` | `d872a061b6ddb4c73fc63d519a7b52880e8c5689538df6462062f43cc739f123` |
| `simulation/strategy_flow.py` | `6ff9ee0bf995adf63b07060062fcd6ffea967ecbed8bdc1118d7d700c2d9f5d0` |
| `simulation/service.py` | `19ed0a2a86f0c907281836725dc0d56ff00149276e62dc6afe28353d5d16691f` |
| `simulation/execution_policy_tw.py` | `7b4c1daad59fb3f8857577f83dbfa726c622536229633a9943584340f233247d` |
| `runtime/momentum_shadow.py` | `406bbd059d800e9d6e2e364a736fe7cc2ca4ea8056c6b468d8489439a1d290bd` |
| `dashboard/momentum.py` | `a8aef4e084ca378b71730ff8fdcac97b5d851e0fa2edc0e160a4b75ee830e7de` |
| `dashboard/server.py` | `6b96ed1c006c578371f0c940848115063d78992bd4d0c85f769fc2b58d1d7e1c` |
| `candidate/pool.py` | `f66678d560ca54cf308b714e0616dcead9d54336226df9d722ed88b764be9a51` |
| `candidate/rules.py` | `1a4eee7e59ed209d874b8ba267454a6afcb09900d05f459f0cd1f977626cb448` |
| `watchlist/reference_data.py` | `7860e26a3fd5adaaa7550bf142572c5b9544775414782f548a90e7c41ce0254b` |
| `strategy_catalog/service.py` | `03793429f3ff040aec1dd3c9edab118bc3edaf6603b5a7fd5f430f3469aa54fe` |
| `backtest/strategies.py` | `1a61be3e3046b815dc083ce9a6fbfa7c001b3e370f261df16ec3221a444f78a6` |
| `backtest/application.py` | `3ceb42c1e01a3cde1f65eb8796037e5469c24973aa6647e706c6a9c22833b88d` |
| `trading/no_overnight_admission.py` | `47b5efeb3e6e95aec3fd2f60eafba86efcc25886f6cde2993ebe2e2a920ced0f` |
| `position/exit_rules.py` | `ec2cd157fdbda18daa7ce27eed6d89b7d96ab035fb267b3bdaf9b610bc440368` |
| `tests/test_momentum_state_machine.py` | `2e6308d427962e8321cf677958834f9f59101e6839a46c2bd56d8fe9c8a671fc` |
| `architecture/local_paper_tax_slippage_implementation_plan.md` | `926a45373438c50efd011c78108ade5bb39cdfcd50f159168a7758b1c49fe4a7` |
| `architecture/previous_day_premarket_watchlist_implementation_plan.md` | `5e528d63bfb7887bd671c3361d6462c223433335ef0bdf53e3d536074642f3ec` |
| `progress.md` | `cfdb67bd21e76e9f36fc49f047685760c3b71a0d44812b8459eadded5e3716ea` |

### 0.3 CURRENT_AS_BUILT manifest

本層固定於 commit `d9151df877d1e801e1815ff3f38cccf976690654`、tree
`aba8bd9227c6c0948f0a1e8fac32ad67ef8ef41e`。`git ls-tree -r --name-only`
的完整 1,476-path list digest 是
`88b9303a7258f850581bde7a44fe6528c46ddca5c0ccc9bc15d948ff4901a617`。
以下 29 個值均由 `git show d9151df:<path>` 的 bytes 計算：

| 路徑 | SHA-256 at `d9151df…` |
|---|---|
| `config/momentum.py` | `61dc86e9ae6c47c4c236e63da025944e4554e54574c40d4ced3d54e1358c774c` |
| `config/local_paper.py` | `cc982e86fc8d1eda8c9a24ceb675a828a88a9f41cb1c6664045a382c13405469` |
| `config/no_overnight.py` | `58de6eb8d12c192fd0298c8ae8339c8c43aced469b5d775a903ac8f19a69f4e5` |
| `signals/models.py` | `b7547101c75e9c2dcb5eda082062301029aeaad1dc6901642f0c7b29e5e93b84` |
| `signals/opening_momentum.py` | `a2613d62b75db78bcb8763e95a11d0c16063ddfba12afb8e74e3b5a50b05aea6` |
| `signals/momentum.py` | `bf31c83c3e3166a4defa90fa978cb69fb9f924129950c8a5847adbd7382e647a` |
| `signals/momentum_state.py` | `211572fb150ecb25aa6de72bcedcad06830db65ac9b0175b365a65d788e5418b` |
| `signals/projection.py` | `8ee1e3a23a96a5f4556fbf1e90cc88ce1d5fd5921aab5e936ea41eb3509a293c` |
| `features/models.py` | `1fbfda954cf0434f98237204d6c8b43f1b3f54c372d48b5d4628f4aa2703060f` |
| `features/engine.py` | `26f59e9b0d031231474b4776c02244734c874d00867be03dcaddb7f4f1d00434` |
| `simulation/continuous_strategy.py` | `d872a061b6ddb4c73fc63d519a7b52880e8c5689538df6462062f43cc739f123` |
| `simulation/strategy_flow.py` | `6ff9ee0bf995adf63b07060062fcd6ffea967ecbed8bdc1118d7d700c2d9f5d0` |
| `simulation/service.py` | `19ed0a2a86f0c907281836725dc0d56ff00149276e62dc6afe28353d5d16691f` |
| `simulation/execution_policy_tw.py` | `7b4c1daad59fb3f8857577f83dbfa726c622536229633a9943584340f233247d` |
| `runtime/momentum_shadow.py` | `406bbd059d800e9d6e2e364a736fe7cc2ca4ea8056c6b468d8489439a1d290bd` |
| `dashboard/momentum.py` | `489025746f9263341b409b87011832830d53ae54601060287faf33fadcdd2ff5` |
| `dashboard/server.py` | `90417b46fbcf9380fe9f4958a42465e188b494e468163ee5b4f73157042ed99d` |
| `candidate/pool.py` | `f66678d560ca54cf308b714e0616dcead9d54336226df9d722ed88b764be9a51` |
| `candidate/rules.py` | `1a4eee7e59ed209d874b8ba267454a6afcb09900d05f459f0cd1f977626cb448` |
| `watchlist/reference_data.py` | `7860e26a3fd5adaaa7550bf142572c5b9544775414782f548a90e7c41ce0254b` |
| `strategy_catalog/service.py` | `03793429f3ff040aec1dd3c9edab118bc3edaf6603b5a7fd5f430f3469aa54fe` |
| `backtest/strategies.py` | `1a61be3e3046b815dc083ce9a6fbfa7c001b3e370f261df16ec3221a444f78a6` |
| `backtest/application.py` | `3ceb42c1e01a3cde1f65eb8796037e5469c24973aa6647e706c6a9c22833b88d` |
| `trading/no_overnight_admission.py` | `47b5efeb3e6e95aec3fd2f60eafba86efcc25886f6cde2993ebe2e2a920ced0f` |
| `position/exit_rules.py` | `ec2cd157fdbda18daa7ce27eed6d89b7d96ab035fb267b3bdaf9b610bc440368` |
| `tests/test_momentum_state_machine.py` | `4c879bd981399c68d554509465a7a05990e61a09ab076e009b268568135c7923` |
| `architecture/local_paper_tax_slippage_implementation_plan.md` | `926a45373438c50efd011c78108ade5bb39cdfcd50f159168a7758b1c49fe4a7` |
| `architecture/previous_day_premarket_watchlist_implementation_plan.md` | `5e528d63bfb7887bd671c3361d6462c223433335ef0bdf53e3d536074642f3ec` |
| `progress.md` | `cfdb67bd21e76e9f36fc49f047685760c3b71a0d44812b8459eadded5e3716ea` |

原始 29 路徑中，current main 的四個 semantic/current drift 是
`signals/momentum_state.py`、`dashboard/momentum.py`、`dashboard/server.py`、
`tests/test_momentum_state_machine.py`。五個 K/S-era 路徑在原始 dirty manifest
中已是後來落地的 bytes，因此不重複計為 current drift。

未納入、且在擴充 gate 分類或 exit specification 時須補入：`scoring/`、`institutional_*/`、`dashboard/static/`、`tests/` 其餘檔案。

### 0.4 HISTORICAL_BASELINE 全域否定命題的證據

本文件包含數個「repo 中不存在 X」形式的命題。這類命題**無法**由 0.2 的逐檔 manifest 證明，因為 manifest 只涵蓋已選檔案。以下記錄產生各命題的確切檢索，複驗時須以相同命令重跑。

| 命題 | 檢索命令 | 建立當下結果 |
|---|---|---|
| `task-042` 無 repo-local lineage | `rg -l 'task-042' .` | 僅 `architecture/momentum_entry_research_spec_v1.md`（即本文件自身，6 處）。**本文件以外為零。** |
| `simulation/execution_policy_tw` 無 product consumer | `rg -l 'from simulation\.execution_policy_tw\|import simulation\.execution_policy_tw' --glob '!build/**' .` | 僅 `tests/test_local_paper_execution_policy_tw.py` |
| `simulation/service.py` 無證交稅 | `rg -c 'tax' simulation/service.py` | 無相符 |

> **限制**：上述檢索在 dirty working tree 上執行，且未記錄檔案集合的整體 digest。要讓全域否定命題真正可稽核，須改綁 clean commit 並記錄 `git ls-files` 的 digest。此為 4.9 的未決項。

### 0.5 Repo-local lineage

本表把原始需求 SHA、純合約 package、工程候選、獨立 gates 與 landed commits
放在同一份可隨正常 clone 取得的文件中。外部 task ledger 仍是 audit history，
但不再是理解 lineage 的唯一來源。

| 階段 | Repo-local record |
|---|---|
| User decision | task045 選定原始規格 SHA `d1da76240facea45e1d3d70f13970f0b199760d2a25a71fa78a9358dc647b26f`；沒有 activation、qualification、broker 或 live-trading authority。 |
| Architecture/package | tasks047/049/053/058/059 固定 pure contracts、G1–G7、D1–D6 gates 與 Slice 1 packages。 |
| Slice 1 engineering | task051 6-path producer/payload candidate `7bb4414b8f17fa25d8b241b6a7757a5d04529d435f5ac1d416d0def60e29479e`；task052 corrected contract digest `c88f75db25c96f9ac6758ad4991c9d32642d8728cd85c755c30f3ba798a37b81`；ordered 15-path aggregate `20dcb9e4624edcc5568be15adf1f308886e77e1a6b5b6d1ae36d4248720a3c8a`。 |
| Slice 1 gates/final | Oscar054 與 Michael060 approved 同一 aggregate；Kelly055 與 Dwight056 passed；Oscar057 commit `1a2b673ba783accf7407df9fb38df3477bd8c81f`，parent `66e6c3aa25b83e84a9bd2cc38fee3cf777b9a931`。 |
| Slice 2 plan | task062 plan SHA `be304d640793607b36c2f0b9797421a4dfe758baeae2ca5a71dc556bc78e009f`；task135 addendum SHA `30d862de2ea4e076e04516078a5ca6a0b7868689b3604e59ff5763965209a26d`；M-T8 lock `301441422bc16e600c0c7095ffc8346a27052d33948b3adb60f567090ecd4e53`。 |
| Slice 2 engineering/fix history | tasks068/074/172/175/180/183 是 bounded dependency-firewall correction chain。被 supersede 的 candidate/verdict identity 只屬 audit history，沒有舊 approval 可沿用。 |
| Slice 2 final candidate | task183 exact 7-path aggregate `5c405b83af468877fc900b06c515726befa0d717505a5e4a4b8d3077c75babce`；status digest `5d9707e14339a3d9d427d84df8d8495570e9076fb4a6feb6d9cce47502435d9c`。 |
| Slice 2 gates/final | Oscar184 與 Michael185 approved 同一 aggregate；Amy178 與 Dwight179 passed；task073 commit `d9151df877d1e801e1815ff3f38cccf976690654`，tree `aba8bd9227c6c0948f0a1e8fac32ad67ef8ef41e`，parent `ffe6a68f5cff8c121ed26eb88b8fb45c5f1a0ed2`。 |

### 0.6 Current ownership and authority at `d9151df…`

| Authority / component | Current role |
|---|---|
| 本文件 | Reviewed doc-only integration 後，作為 canonical research requirements、historical evidence、status overlay 與 unresolved-policy register；不是 runtime authority。 |
| `signals/entry_specification.py` | Pure structural EntrySpecification contract；不是 controller consumer 或 qualification authority。 |
| `signals/gate_taxonomy.py` | Pure gate-declaration contract；G7 row 相對於 landed producer/payload closure 已 stale，且不是 runtime-wired authority。 |
| `signals/selection.py` | Pure selection/candidate-evidence contract；兩條 current selection path 都尚未 migration。 |
| `signals/decision_evidence.py` | Pure decision-evidence/envelope contract；既有 controller/journal path 尚未 migration。 |
| `signals/_contract_wire.py` | Slice 2 private shared sentinel/wire/digest helper；沒有 product 或 policy authority。 |
| `signals/momentum_state.py` | Current stage 與 episode closure facts 的 canonical lifecycle producer。 |
| `dashboard/momentum.py` | Current realtime/read-model transport；evaluated 與 unavailable shapes 都有穩定的 `episode` 欄位。 |
| `simulation/continuous_strategy.py` | Actual current runtime consumer；仍不讀 `episode.status`，也不匯入四個 pure contract modules。 |
| 第 4 節 / D1–D6 | 仍由既有 product/requirement/human authority 決定；本次 doc revision 無權填值。 |

### 0.7 CURRENT_AS_BUILT §2 status matrix

Primary state 只允許 `CLOSED`、`STILL_CURRENT`、
`CONTRACT_ONLY_NOT_WIRED`、`UNRESOLVED_POLICY`。第 2 節保留原始歷史
觀察，本表才是 `d9151df…` 的 current 判定。

| Finding | Primary state | Current statement and evidence at `d9151df…` |
|---|---|---|
| §2.1 hard vs scored evidence | `STILL_CURRENT` | 四個 `triggered` terms 與 35 fixed / 65 optional / threshold 70 語意仍成立（`signals/opening_momentum.py:81-86`；`config/momentum.py:195-212`）。 |
| §2.2 Opening vs Limit-Up readiness | `STILL_CURRENT` | Opening default 仍 fail-closed；09:10 後 Limit-Up family 可觸發（`config/momentum.py:202`；`signals/opening_momentum.py:145`；`signals/momentum.py:96,198`）。 |
| §2.3(a) evaluation status | `STILL_CURRENT` | 仍是 alpha-bearing gate。 |
| §2.3(b) acceleration confirmation | `STILL_CURRENT` | Current v0 下仍是 config-dependent duplicate。 |
| §2.3(c) enabled families | `STILL_CURRENT` | 未型別化邊界上的 defensive contract，不是另一個 alpha predicate。 |
| §2.3(d) availability/data-health/price | `STILL_CURRENT` | Defensive-contract characterization 仍成立；Limit-Up 的 current data-health propagation 已由 `features/engine.py:152-165` 與 `signals/momentum.py:86-100,198-200` 確認：non-`HEALTHY` 或 `data_health.as_of < current_tick.received_at`（stale）會令 `required_inputs_valid=false`，因此不得 `TRIGGERED`。僅防禦驗證應留在 controller 或移至顯式 payload 契約層的政策仍未決。 |
| §2.3(e) close-tick stage + realtime episode transport defect | `CLOSED` | `CLOSED_BY_SLICE1` at `1a2b673…`：public close update 回到 WATCH，realtime payload 攜帶 episode（`signals/momentum_state.py:487-527`，決定性 return `:518-527`、WATCH `:522`；`dashboard/momentum.py:358-420`，unavailable `episode=None` at `:382`、evaluated episode at `:398`）。Closure tests：`tests/test_momentum_state_machine.py:380-381`、`tests/test_momentum_projection.py:203-207`、`tests/test_realtime_momentum_dashboard_service.py:178-179,242-248`。 |
| §3.6 dual `current_stage` + `episode.status` consumption | `CONTRACT_ONLY_NOT_WIRED` | Payload 已提供欄位，但 controller `simulation/continuous_strategy.py:602-617`（尤其 `:608-615`）只讀 stage/signal/data/price，不讀 `episode.status`；這不是舊 producer/payload P1。 |
| G7 declaration in `signals/gate_taxonomy.py` | `CONTRACT_ONLY_NOT_WIRED` | `:194-213` 仍寫 `EFFECTIVE_UNSOUND` 並嵌入已關閉 bypass；它是 stale contract metadata，須另開 digest-changing code follow-up，本文件不改 code row。 |
| §2.4 selection mismatch | `STILL_CURRENT` | Legacy score/symbol 與 Atomic symbol-only selection 仍不同且 runtime path 未版本化（`simulation/continuous_strategy.py:642,715`）。 |
| `signals/selection.py` remedy | `CONTRACT_ONLY_NOT_WIRED` | Pure policy/evidence DTO 已存在，但兩條 runtime path 都沒有 consumer。 |
| §2.5 decision-evidence comparability | `STILL_CURRENT` | Legacy/exit gaps 與 non-equivalent sample evidence 仍在（`simulation/continuous_strategy.py:649,741,873`；`simulation/strategy_flow.py:26,44,147`）。 |
| `signals/decision_evidence.py` remedy | `CONTRACT_ONLY_NOT_WIRED` | Contract 已存在，但 controller/journal migration 尚未發生。 |
| §2.6 signal evidence vector | `STILL_CURRENT` | Signal details/digest evidence 仍存在；缺口仍是 trade lineage。 |
| §2.7 universe/candidate admission gaps | `STILL_CURRENT` | Skeleton 存在，amount/spread/depth/participation/capacity facts 仍缺。 |
| §2.7 policy choices | `UNRESOLVED_POLICY` | Universe、capacity、liquidity 與 lifecycle values 仍未決。 |
| §2.8 cost/execution gaps | `STILL_CURRENT` | LocalPaper zero defaults、simulation tax path 缺席、test-only v3 seam 與 0/42 qualification 仍為 current facts；Atomic defaults 在 `dashboard/server.py:514-520`，non-Atomic request 另見 `:357-370`。 |
| §2.8 cost/execution choices | `UNRESOLVED_POLICY` | 沒有 cost、slippage、seam cutover 或 admission choice 得到授權。 |
| §2.9 eligibility vs intent split | `STILL_CURRENT` | Shadow opportunity 與 controller intent 仍不是一個 canonical decision object。 |
| §2.10 exit generations | `STILL_CURRENT` | 三個 governance generations 仍在。 |
| §2.10 consolidation/ablation choices | `UNRESOLVED_POLICY` | 本文件沒有選擇 exit consolidation 或 strategy value。 |

Slice 2 保留 public DTO/digest behavior，增加 shared helper 與 dependency
firewall；它沒有解決上述 runtime gaps，也沒有把 pure DTO 變成 runtime authority。

### 0.8 G7 三層狀態

1. `HISTORICAL_BASELINE @ 66e6c3aa…`：G7 曾是 `EFFECTIVE_UNSOUND`，因 close tick 可同時暴露 `ACCELERATING + INVALIDATED`，且 realtime shape 不含 episode status。
2. `CURRENT_AS_BUILT @ d9151df…`：該已知 producer/transport bypass 已由 Slice 1 關閉；`signals/momentum_state.py:487-527` 回報 public `current_stage=WATCH`，`dashboard/momentum.py:358-420` 輸出穩定 `episode` 欄位。文件層可稱 G7 是有效的 lifecycle/re-entry gate，已知 bypass 已關閉。
3. Current contract metadata：`signals/gate_taxonomy.py:194-213` 仍固定歷史 class/bypass 文字。這個 doc-only R2 不改 `GateClass`、row 或 digest；必須由另一個 bounded code card 決定如何更正。

---

## 1. 目的與邊界

### 1.1 目的

現有 Momentum 進場邏輯散落在 signal、state machine、controller 三層，其中「哪些條件是硬性門檻、哪些是可互相補償的加權證據、哪些實際上不構成任何約束」沒有單一權威來源。本文件的目的是把這件事寫清楚，作為後續 baseline / challenger 設計與 ablation 的前置條件。

在本文件所列欄位固定之前，「一次只改一項」在方法論上無法成立，因為改動者無從得知自己改的是哪一層、是否有第二層在同一方向上抵銷或放大該改動。

### 1.2 邊界

- 本文件**不**評價策略是否有效，也不主張任何進場邏輯應該保留或移除。
- 本文件**不**取代 task-042 的量尺工作（成本、資料、execution snapshot、qualification chain）。在該量尺完成前，任何依本規格產生的回測結果僅為 exploratory。
- 本文件**不**處理 sizing、風控額度、部位管理與資金配置。
- 出場只在「治理世代分裂」一節被描述，完整 Exit Specification 另立。

---

## 2. HISTORICAL_BASELINE 現況判定（原始觀察）

以下保留原始 dirty-manifest observation。此節內的「現況」、重現值與
`path:line` 都只綁 `HISTORICAL_BASELINE @ 66e6c3aa… + recorded dirty
manifest`，不得當成 `d9151df…` 的 current claim；current 結論與 citation
以 0.3、0.7、0.8 為準。

### 2.1 進場的硬門檻遠少於表面所示

`OpeningMomentumSignal.evaluate` 的 `triggered` 條件（`signals/opening_momentum.py:81`）只有四項：

1. `required` 欄位全部 `VALID` 且 `data_health` 為 `HEALTHY`（無 block reason）
2. `evidence_score >= trigger_evidence_score`（`70`）
3. `price_above_vwap is True`
4. `breakout is True`

`min_return_2m` 與 `max_distance_to_limit` **不是**觸發條件。它們是加權證據項，數值未達門檻時只是不得分。

`OPENING_MOMENTUM_HYPOTHESIS_V0` 權重（`config/momentum.py:195` 起）：

| 規則 | 分數 | 是否硬性 |
|---|---|---|
| `price_above_vwap` | 15 | **是** |
| `breakout` | 20 | **是** |
| `return_2m` | 15 | 否 |
| `distance_to_limit` | 20 | 否 |
| `opening_volume_context` | 20 | 否 |
| `external_ratio_rising` | 10 | 否（且非 required-block 欄位） |
| 合計 | 100 | 門檻 70 |

強制項固定貢獻 35 分，可選項池 65 分，只需再取得 35 分即達標。因此：

- `distance_to_limit` 完全失敗 → 15+20+10 = 45，總分 **80**，仍觸發。
- `return_2m` 完全失敗 → 20+20+10 = 50，總分 **85**，仍觸發。

**判定**：現行 Opening / Limit-Up hypothesis 的正確描述是「VWAP 之上 + 突破為硬門檻，短線報酬、漲停距離、量能、外盤採可互相補償的加權分數」，而非「兩分鐘動能且接近漲停的 AND 策略」。若外部文件或 task-042 以後者描述研究對象，則實作與假說語意不一致。

### 2.2 Opening family 預設 fail-closed，Limit-Up family 不然

- `OPENING_MOMENTUM_HYPOTHESIS_V0.opening_volume_context_mode = None`（`config/momentum.py`），而 `_required_block_reasons` 在 `not runtime_ready` 時無條件加入 `opening_volume_context_mode_unconfigured`（`signals/opening_momentum.py:145`）。因此 09:00–09:10 的 Opening family 恆為 `INSUFFICIENT_DATA`，不可能觸發。
- `MomentumSignalEngine.evaluate` 在 `event_time >= 09:10` 路由到 `LimitUpMomentumSignal`（`signals/momentum.py:198`）。
- `LimitUpMomentumHypothesisConfig` 沒有 `opening_volume_context_mode` 欄位，`LimitUpMomentumSignal` 的狀態判斷只有 `if not snapshot.required_inputs_valid`（`signals/momentum.py:96`），**沒有 runtime_ready 這一層**。

**判定**：不可陳述為「整套 Momentum runtime 不產生訊號」。正確範圍是：預設設定下 Opening family 完全 fail-closed；09:10 之後的 Limit-Up family 可正常觸發。

### 2.3 Controller 各 gate 的實際約束力不一

`ContinuousPaperStrategyController` 的候選過濾（`simulation/continuous_strategy.py:610` 起）逐項判定如下。分類定義見 3.2。

**(a) `evaluation_status == "TRIGGERED"`：有效 alpha gate，且是唯一一個。**
本項承載 2.1 所述的全部進場假設（VWAP、突破、加權分數門檻）。不得從有效約束清單中移除。

**(b) `momentum_acceleration_confirmed`：config 相依重複。**
該旗標為 `family.confirms_acceleration(primary)`（`signals/opening_momentum.py:112`、`signals/momentum.py:118`），`primary = components[-1]`，而 family enum 值只在 `if triggered:` 時被 append 到 components 尾端；`acceleration_signals` 只含該 family enum 值（`config/momentum.py:57`）。故現行 v0 設定下與 (a) 等價。`acceleration_signals` 改為包含非 family 值時即恢復約束力，因此屬 config 相依而非結構恆真。

**(c) `_ENABLED_SIGNAL_FAMILIES`：防禦性契約檢查。**
`SignalFamily` enum 只有 `OPENING_MOMENTUM` 與 `LIMIT_UP_MOMENTUM` 兩個值（`signals/models.py:19`），白名單（`simulation/continuous_strategy.py:31`）涵蓋全部兩個值。新增第三個 family 須修改 enum 與 engine 程式，非改 config 可達，因此在**合法 producer domain 內屬結構重複**。

但 controller 接收的是未型別化的 `Mapping`，本項仍是跨模組邊界上拒絕不符契約輸入的 fail-closed 防線，故不適用「結構恆真 → 移除」的處置。歸類為防禦性契約檢查。

**(d) `availability == "EVALUATED"`、`signal.data_health == "HEALTHY"`、`price.status == "VALID"`：防禦性契約檢查（部分待複驗）。**

- `availability`：`_serialize_candidate` 在 `projection is None` 時輸出 `current_stage: None`、`signal: None`（`dashboard/momentum.py:369` 起），而 controller 已先行 `if not signal or not price: continue`。故本項由 signal/price 非 None 所隱含。
- `data_health`（`HISTORICAL_BASELINE`）：Opening family 於 `data_health` 非 `HEALTHY` 時會加入 block reason 而無法 `TRIGGERED`（`signals/opening_momentum.py`），故由 (a) 隱含。Limit-Up family 走 `snapshot.required_inputs_valid`（`features/models.py:146`）；原始觀察當時將其記為「須以 `features/engine.py` 複驗後才可定案」。
- **Current closure link**（`CURRENT_AS_BUILT @ d9151df…`）：複驗已完成。`features/engine.py:152-165` 對 non-`HEALTHY` 或 `data_health.as_of < current_tick.received_at`（stale）加入 block reason，並令 `required_inputs_valid=false`；`signals/momentum.py:86-100,198-200` 在 `event_time >= 09:10` 時路由至使用該旗標的 Limit-Up evaluator，因此這兩種 data-health 狀態不得 `TRIGGERED`。這是已綁 code 事實，不回答未來 defensive-validation placement policy。
- `price.status`：controller 讀的是 `item["intraday"]["price"]`，與 signal 內部使用的 feature 為不同序列化物件，故本項屬跨物件一致性檢查，非獨立 alpha predicate。

**(e) `_ENABLED_STAGES`：HISTORICAL_BASELINE 有效但不健全（effective but unsound）。**

> **Current closure link**：本小節以下重現只屬歷史。0.7 的 §2.3(e)
> `CLOSED` row 記錄 `CLOSED_BY_SLICE1 @ 1a2b673…`；0.7 的 §3.6 row
> 另保留 controller 尚未消費 `episode.status` 的
> `CONTRACT_ONLY_NOT_WIRED` residual。

白名單為 `{"ACCELERATING", "NEAR_LIMIT_UP", "LIMIT_TOUCHED"}`（`simulation/continuous_strategy.py:32`），`STRONG` 與 `WATCH` 不在其中。

*有約束力的路徑*：episode 因 invalidation 關閉時，`_close_episode` 依 `MOMENTUM_STATE_HYPOTHESIS_V0.cooldown`（2 分鐘）設定 `cooldown_until`（`signals/momentum_state.py:263` 起）。cooldown 期間 `_evaluate_without_active` 的 `can_create` 為 False，`current_stage` 落回 `base_stage`（`STRONG` 或 `WATCH`，`signals/momentum_state.py:222`）。因此即使新訊號仍為 `TRIGGERED`，stage gate 仍會擋下。此路徑有測試覆蓋（`tests/test_momentum_state_machine.py`）。

*不健全的路徑*：洩漏發生在 episode 關閉的該一 tick，且橫跨三個物件層級：

| 層級 | 觀察到的內容 |
|---|---|
| `MomentumStateUpdate` | `current_stage=ACCELERATING` 與 `episode_closed_status=INVALIDATED` 並存（`signals/momentum_state.py` `_close_episode` 回傳 `closed.current_stage`，同時已將 `_watch_stage` 設為 `WATCH`） |
| `MomentumProjection` | `current_stage=ACCELERATING`，其 `episode.status=INVALIDATED` |
| Realtime dashboard payload | 輸出 `current_stage`，**不輸出 episode status**（historical `_serialize_candidate`，`dashboard/momentum.py:369` 起） |

Controller 要求 `snapshot.status == "live"` 且 `source.is_live is True`（historical `simulation/continuous_strategy.py:590` 起），因此消費的正是上表第三列的 realtime payload。**歷史問題不只是 controller 未檢查 episode status，而是當時輸入契約根本不提供該欄位**。舊 `dashboard/momentum.py:867` citation 在 current main 已是 `signal.digest`；current serializer/episode evidence 改見 `dashboard/momentum.py:358-420`，full projection episode 現在位於 `:869`。

已重現的觀察值：`update ACCELERATING INVALIDATED` / `projection ACCELERATING INVALIDATED`。

**HISTORICAL_BASELINE 判定**：先前將 stage gate 判為恆真是錯誤的。當時結論是：(a) 為唯一 alpha gate；(b) 為 config 相依重複；(c)(d) 為防禦性契約檢查；(e) 為有效但不健全，存在一個 tick 的洩漏窗口。該窗口的 producer/transport 部分目前已依 0.7 關閉。

**HISTORICAL_BASELINE 衍生缺陷 (P1)**：`current_stage` 與 `episode.status` 可在同一次 update 中不一致，且當時 realtime 輸入契約未攜帶 episode status。此 producer/payload P1 已由 Slice 1 關閉；current residual 是 controller 未讀欄位與 stale G7 metadata，分別見 0.7、0.8。

### 2.4 兩條路徑的 selection function 不同，且都未版本化

| 路徑 | 排序 | 位置 |
|---|---|---|
| 舊 Momentum | `evidence_score DESC` → `symbol ASC` | `simulation/continuous_strategy.py:642` |
| Atomic Strategy Set | `symbol ASC`（**完全不看分數**） | `simulation/continuous_strategy.py:715` |

兩者皆取 `[0]`，每次只進場一檔，且排序規則為程式內常數，無 policy digest、無版本、無設定入口。

由 2.1，不同 evidence pattern 只要同分即被視為等價；由此表，兩條路徑對「同分」的處理甚至不一致。持久化只保留被選中的 intent，未保存合格候選全集、各檔 evidence signature、完整排序結果、淘汰原因與 selection policy digest，因此 selection counterfactual 事後無法重建。

### 2.5 Decision evidence 同 schema、不同完整度

`StrategyPaperIntent` 的 `decision_evidence` 是同一 dataclass 的 optional 欄位（`simulation/strategy_flow.py:44`），`schema_version` 固定為 `strategy-paper-intent-v1`（`simulation/strategy_flow.py:26`）。

| Intent | `decision_evidence` | 位置 |
|---|---|---|
| 舊 Momentum 進場 | **無**（僅 `intent_id` 內嵌 32 字元 digest 前綴） | `simulation/continuous_strategy.py:649` |
| Atomic Strategy Set 進場 | 有（pipeline / pipeline_digest / strategy_set_decision / pre_order_quote_watch） | `simulation/continuous_strategy.py:732`, `:741` |
| 出場（兩條路徑共用） | **無** | `simulation/continuous_strategy.py:873` |

序列化條件為 `if self.decision_evidence is not None`（`simulation/strategy_flow.py:147`），因此：

- `decision_evidence=None` → journal 中欄位缺席。
- `decision_evidence={}` → journal 中明確寫入 `"decision_evidence": {}`。

**空 dict 與欄位缺席是可區分的。** 真正無法區分的是同為「欄位缺席」的兩種來源：舊路徑依設計刻意不帶，與新路徑應帶而因缺陷漏帶。

**判定（P1）**：`Formal sample comparability is broken before cost evaluation: legacy and Atomic intents share a schema but not an equivalent decision-evidence contract.` 且沒有任何一條完整往返（進場 + 出場）具備完整 evidence。若 qualification 僅驗證 `strategy-paper-intent-v1`，會把不可比較的樣本混入同一統計。`evidence_completeness` 之所以必須是顯式欄位，理由不是「三種情況相同」，而是欄位缺席無法自證其成因。

### 2.6 訊號層 evidence vector 存在

`SignalResult.details` 保留每一規則的 passed/failed、observed value、threshold、awarded points、來源時間與 missing reason，並進入 signal digest 與 dashboard projection。缺口不在訊號層，而在 2.5 所述的持久化交易 lineage。

### 2.7 母體與 CandidatePool：骨架存在，admission 缺席

**已存在**：`watchlist/reference_data.py` 提供 PIT 母體合約（`DateEffectiveEquityRecord`、`EquityUniverseSnapshot` / `Manifest` / `Artifact`、`UniverseEvidenceMode`、`formal_research_allowed` gate）；`candidate/pool.py` 提供 TTL、grace period、scanner observation hysteresis、priority / rank、pinned 與 active episode 保護。

**仍缺**：
- `candidate/rules.py` 只有 gap%、絕對成交量、相對成交量門檻；**無成交金額、BidAsk spread、深度、order participation 上限**。
- `CandidatePoolConfig` 只有 `version` / `grace_period` / `scanner_min_observations`；**無 `max_candidates` 或 `max_symbols` 容量政策**。
- 有 PIT 合約不等於已有針對目標研究期間、已驗證且覆蓋完整的 PIT artifact。
- `architecture/previous_day_premarket_watchlist_implementation_plan.md` 所列三個盤前觀察名單策略仍為計畫；`watchlist/` 實際只有 `import_adapter.py`、`reference_data.py`、`serialization.py`。

### 2.8 成本與執行：舊 runtime 為主，v3-tw seam 為 test-only

- `LOCAL_PAPER_DEFAULT_COMMISSION_RATE = "0"`、`LOCAL_PAPER_DEFAULT_MINIMUM_COMMISSION_TWD = "0"`（`config/local_paper.py`）。
- `simulation/service.py` 全檔無 `tax`，亦無 BBO 之外的滑價。
- `architecture/local_paper_tax_slippage_implementation_plan.md:3` 狀態為 `PLAN_ONLY / NOT_IMPLEMENTED`；該計畫自身載明 5 bps「不能宣稱是台股即時成交的實證值」。
- `simulation/execution_policy_tw.py:82` 的 `TwLocalPaperExecutionPolicyAdapter` 雖具 commission / tax / slippage，但唯一 importer 為 `tests/test_local_paper_execution_policy_tw.py`，**無 product composition consumer**，且僅提供 `allocate_close_long()`，未覆蓋完整 BUY / SELL 生命週期。`backtest/*` 匯入的是同名但不同的 `backtest.execution_policy_tw`，不可作為 simulation 端已接線之證據。
- `AtomicBacktestRunRequest` 的 `commission_rate` / `sell_tax_rate` / `slippage_bps`（historical anchor `dashboard/server.py:502`）為**可覆寫的 request defaults**，非凍結 policy；current main anchor 是 `dashboard/server.py:514-520`，non-Atomic request 則是 `:357-370`。
- 滑價校準目前為 `0/42 required groups qualified`（`progress.md`）。

### 2.9 進場 eligibility 與 intent 產生不是同一個 decision object

`runtime/momentum_shadow.py` 建立 `EntryOpportunity` 時硬寫 `RiskGateStatus.UNAVAILABLE`，故 opportunity 恆為 blocked；而 controller 不讀該 opportunity，改讀 projection snapshot 的 `signal` + `current_stage` 自行判斷（`simulation/continuous_strategy.py:600` 起）。畫面上的 entry eligibility 與 controller 是否產生 intent 因此不是同一個 canonical decision。

### 2.10 出場語意分屬三個治理世代

| 路徑 | 參數來源 | 世代 |
|---|---|---|
| `position/exit_rules.py` | 全域 `settings.STOP_LOSS_PCT` / `settings.TAKE_PROFIT_PCT` | 舊式，未版本化 |
| `ContinuousPaperStrategyController` | activation-time stop / take 參數 | 中期 |
| `backtest/strategies.py` | `stop_loss_exit_v1`、`take_profit_exit_v1`、`atr_stop_exit_v1`、`time_stop_exit_v1`、`end_of_day_exit_v1` | 版本化 Atomic |

另須區分：`stop_loss` / `take_profit` 屬策略型出場（有無預測優勢是研究問題）；`entry_cutoff` / `flatten_at` / 不留隔夜倉 / 重試與 final reconciliation 屬 Session / Risk / Execution policy（`config/no_overnight.py`），不是 alpha 出場邏輯。兩者不可混入同一研究問題。

---

## 3. UNRESOLVED / FUTURE AUTHORITY — Entry Specification 骨架

任一進場策略（含 baseline 與每一個 challenger）在進入正式研究前，須以下列 12 欄位完整描述。欄位未填或標為未決者，該策略不得進入 ablation 或 qualification。

Slice 1 已落地 pure structural DTO，Slice 2 已落地 shared wire/helper 與
dependency firewall；這不代表下列政策值已決，也不代表 controller、journal、
selection、qualification 已 migration。

### 3.1 `required_data`

觸發前必須為 `VALID` 的 feature 清單，以及各自的 staleness 上限與 `data_health` 要求。須明確指出哪些欄位「必須有效但數值不必達標」，哪些欄位「缺少時仍可觸發」（現況：`external_ratio` 屬後者）。

### 3.2 `hard_predicates`

必須全部成立才可觸發的條件。**每一項須附一個 falsifying case**，並註明該 case 屬於：

- **合法且可達輸入**：canonical producer 在正常運作下可產生的輸入。只有這類 case 能證明該項為真實決策約束。
- **契約違反輸入**：只有在上游違反契約或跨邊界資料損毀時才會出現。這類 case 不足以證明決策約束，但足以證明防禦價值。

舉不出任一類 case 的項目應移入下方分類並標記處置方式。

**失效性質四分類**：

| 類別 | 定義 | 處置 |
|---|---|---|
| 結構恆真 | 在任何 config 與任何合法 producer output 下皆無約束，亦無防禦價值 | 移除 |
| config 相依重複 | 現行 config 下與另一項等價，改 config 即恢復約束力 | 保留並標註相依對象 |
| 防禦性契約檢查 | 對合法 producer output 不增加決策約束，但負責在跨模組／未型別化邊界拒絕不符合契約的輸入 | 保留，且須明文標註其職責為契約而非決策，避免被誤讀為 alpha gate |
| 有效但不健全 | 有決策約束力，但存在已知繞過路徑 | 保留，並同時記載繞過路徑、影響範圍與修補狀態 |

`CURRENT_AS_BUILT @ d9151df…` 分類（見 0.7、0.8、2.3）：`evaluation_status == TRIGGERED` 為唯一有效 alpha gate；`momentum_acceleration_confirmed` 屬 config 相依重複；`_ENABLED_SIGNAL_FAMILIES`、`availability`、`data_health`、`price.status` 屬防禦性契約檢查，其中 Limit-Up 的 current data-health propagation 已由 `features/engine.py:152-165` 與 `signals/momentum.py:86-100,198-200` 確認。`_ENABLED_STAGES` 的 `HISTORICAL_BASELINE`「有效但不健全」已 `CLOSED_BY_SLICE1 @ 1a2b673…`。Current runtime residual 是 controller 尚未消費 `episode.status`，屬 `CONTRACT_ONLY_NOT_WIRED`；另有獨立的 current contract-metadata residual：`signals/gate_taxonomy.py:194-213` 仍固定舊 `EFFECTIVE_UNSOUND` 與已關閉 bypass 文字，也屬 `CONTRACT_ONLY_NOT_WIRED`，須由另一個 digest-changing code card 處理。

### 3.3 `scored_evidence`

加權證據項清單：規則名、權重、threshold、方向、缺值處理。須標明本欄各項之間可互相補償。

### 3.4 `score_threshold`

觸發分數門檻，以及該門檻與 `hard_predicates` 固定貢獻分數的關係（現況：強制項固定 35 分，門檻 70，可選池 65）。須列出達標的最小組合列舉。

### 3.5 `allowed_evidence_signatures`

允許進場的 evidence pattern 列舉。此欄限定「哪些 pattern 有資格參賽」，使 ablation 有明確定義域。本欄不解決同分排序問題，該問題由 3.7 處理。

### 3.6 `stage_gate`

允許進場的 `MomentumStage` 白名單，以及該閘門相對於 `hard_predicates` 的增量約束。

HISTORICAL_BASELINE 與 current 都保留的增量約束是：透過 episode cooldown 與 `can_create` 條件，擋下 invalidation 後 cooldown 期間的重新進場（見 2.3e 與 0.7）。本欄須明文記載三件事：

1. 白名單內容與各 stage 的進入條件。
2. **生命週期重入控制與 identity idempotency 的交互作用及優先順序**。兩者語意與失效模式不同，不可混為「去重」：
   - *cooldown*：失效後的時間型 re-entry hysteresis，屬生命週期重新武裝。失效模式是時間窗設定不當（過短導致連續追價，過長導致漏掉真實再進場）。
   - *`deduplication_key` / digest*：同一訊號或決策 identity 的冪等去重。失效模式是 identity 定義過寬或過窄（過寬導致漏單，過窄導致重複下單）。
   兩者可能同時阻擋同一筆進場，規格須指明判定順序與各自的記錄欄位。
3. **episode status 一致性要求**：進場判定須同時檢查 `current_stage` 與 `episode.status`。CURRENT_AS_BUILT realtime payload 已攜帶 `episode`（`dashboard/momentum.py:358-420`），但 controller `simulation/continuous_strategy.py:608-615` 尚未消費 `episode.status`；因此這是 `CONTRACT_ONLY_NOT_WIRED`，不是仍待 producer/payload 修補的舊 P1。本文件不實作 consumer migration。

### 3.7 `selection_function`

多檔同時合格時的選取規則。至少須包含：

- `candidate_set_digest`
- `ranked_candidates`
- `tie_breakers`
- `selected_candidate_id`
- `selection_reason`
- `selection_policy_digest`
- `max_entries_per_session`
- `deduplication_key`

現況兩條路徑排序不一致且皆未版本化（見 2.4）。

### 3.8 `candidate_set_evidence`

進場當下合格候選全集的持久化證據：各檔 evidence signature、完整排序結果、淘汰原因。用於 selection counterfactual。缺少本欄時，即使 `decision_evidence` 完整，仍無法重建「換一種排序會選到誰」。

### 3.9 `entry_decision_digest`

涵蓋 3.1–3.8 全部輸入的單一 digest，作為該筆進場決策的 canonical identity。須說明其涵蓋範圍與計算順序，以及與 `signal.digest` 的關係。

### 3.10 `ablation_cohort_plan`

每次僅改動一個欄位的變更計畫、對照組定義、樣本切分（IS / OOS / walk-forward）、最低交易樣本數、market regime 分層。

### 3.11 `execution_admission_binding`

該策略綁定的 execution 與 cost policy identity：`execution_policy_digest`、`cost_policy_digest`、admission policy、成交模型假設，以及該假設是明示值或校準值。滑價若為明示假設，須明文禁止以其結果宣稱績效。

### 3.12 `qualification_evidence_profile`

正式 qualification 對該策略樣本的准入要求。建議至少要求：

- `decision_evidence_contract_version`
- `evidence_completeness`（**須為寫入時強制填入的顯式欄位，不得由 `decision_evidence` 是否存在推導**，理由見 2.5）
- `signal_digest`
- `evidence_vector_digest`
- `stage_gate_digest`
- `candidate_set_digest`
- `selection_policy_digest`
- `execution_policy_digest`
- `cost_policy_digest`

既有事件維持 replay truth 不變更，另以回溯標註標記為不合格。回溯標註本身須附 provenance：標註時間、依據規則、規則版本。

---

## 4. UNRESOLVED / FUTURE AUTHORITY — 未解決決策

以下僅列出待決問題與判準要求，**不預填任何預設值或建議選項**，以免本文件成為隱性決策來源。每項需經正式決策後才可填入第 3 節對應欄位。

### 4.1 母體

- 上市、上櫃、ETF、其他證券類型各自是否納入？
- 是否強制使用 PIT 成分股？以何種 `UniverseEvidenceMode` 為研究准入下限？
- 上市未滿特定天數、處置股、全額交割、暫停交易、變更交易方法者的排除規則與判定時點為何？
- 目標研究期間的 PIT artifact 是否已存在、已驗證、覆蓋完整？若否，取得路徑為何？

### 4.2 流動性 admission

- 以何者為門檻：成交股數、成交金額、同期 RVOL、BidAsk spread、簿深度、或其組合？
- 策略單量相對可成交量的上限比例為何？
- 門檻於何時點評估（進候選時、觸發時、下單前）？三者不一致時以何者為準？
- 門檻未達時的行為是排除、降級，或僅記錄？

### 4.3 觀察名單生命週期

- 盤前產生、盤中更新，或兩者併行？
- 更新頻率、最大檔數（`CandidatePool` 容量上限）、TTL、移除條件、重新加入 cooldown 各為何？
- 觀察名單策略引擎尚未實作，其實作與本規格的先後順序為何？

### 4.4 硬門檻、重複項與加權證據的取捨

- 哪些條件必須是 AND？哪些可進分數池？判準為何？
- `momentum_acceleration_confirmed` 這項 config 相依重複，應移除、改為真實 predicate，或保留並明文標註相依對象？
- 防禦性契約檢查（`_ENABLED_SIGNAL_FAMILIES`、`availability`、`data_health`、`price.status`）應保留於 controller，或上移至一個顯式的 payload 契約驗證層？若保留，如何避免後續讀者誤判為 alpha gate？
- Limit-Up family 的 current `required_inputs_valid` 已涵蓋 `data_health`：`features/engine.py:152-165` 將 non-`HEALTHY` 或 `data_health.as_of < current_tick.received_at`（stale）轉為 block reason 並令該旗標為 false，`signals/momentum.py:86-100,198-200` 因而不會回傳 `TRIGGERED`。此事實不再是未決題；仍未決的只有 defensive validation 應保留於 controller 或移至顯式 payload 契約層，本文不得填答案。
- `_ENABLED_STAGES` 的已知 producer/transport 洩漏已由 Slice 1 關閉。尚未授權的 current follow-up 是 controller 是否／如何同時檢查 `episode.status`，以及 stale G7 metadata 如何以新的 digest-changing code card 更正；不得在本文填答案。
- 生命週期重入控制（cooldown）與 identity idempotency（digest）的判定順序為何？兩者是否應各自獨立記錄阻擋原因？
- 若保留加權模型，`allowed_evidence_signatures` 的列舉粒度為何？

### 4.5 Selection

- 同分時的 tie-breaker 應具備何種經濟或流動性意義？（現況為股票代號字母序，無此意義）
- 兩條路徑的 selection function 應統一或維持分離？若統一，以何者為準？
- 每 session 進場檔數上限為何？

### 4.6 Evidence 與 qualification

- `evidence_completeness` 的等級如何劃分？各等級的最低欄位集為何？
- 舊事件的回溯標註由誰執行、於何時執行、如何審核？
- 出場 intent 缺少 `decision_evidence` 是否阻擋整筆往返進入 qualification？

### 4.7 成本與執行

- LocalPaper 正式路徑應為舊 runtime 或 v3-tw seam？切換的准入條件為何？
- 滑價在校準完成前，exploratory 結果的可陳述範圍為何？
- `0/42 required groups qualified` 的補足路徑與所需 session 數為何？

### 4.8 出場治理

- 三個世代的 exit 語意應收斂為單一 chain 或維持分離？
- `stop_loss` / `take_profit` 是否納入本輪 ablation，或先固定為常數以隔離進場變因？

### 4.9 Traceability

- 0.5 已把 task045–073 與 bounded Slice 2 fix chain 寫入 repo-local lineage；外部 `task-042` transcript 是否另行匯入 repo-local planning record，仍須獨立決定。
- transcript SHA-256 已計算並填入 0.1。是否要求所有引用外部 transcript 的文件一律比照，且由何機制強制？
- 逐檔 SHA-256 manifest（0.2）是否成為規格文件的標準綁定方式，或改為要求規格文件僅綁 clean commit？兩者的維護成本與失效模式各為何？
- manifest 的複驗由誰、於何時執行？檔案 hash 變動時，對應判定的重新複驗是否為 review 的阻擋條件？

---

## 5. 非目標

- 本文件不建立、修改或啟用任何策略。
- 本文件不變更任何 config、policy、activation 或資料。
- 本文件不宣稱任何既有回測或 LocalPaper 結果具備績效意義。
- 本文件不取代 task-042 的量尺工作，亦不得被引用為繞過該工作的依據。
- 本文件不把 Slice 1/2 pure contracts 宣稱為 runtime migration、qualification authority 或 order behavior 變更。
