# Findings & Decisions

## Requirements
- 僅規劃 Local Paper 證交稅與滑價；不實作、不建立 broker／真實下單路徑。
- 計畫必須能由另一獨立任務直接執行，包含檔案範圍、相依順序、測試、migration、rollback 與完成條件。
- 稅費與滑價必須可稽核、可重播、Decimal deterministic，且 cash／PnL 不得重複扣除。
- 與正在進行的 Kill Switch 工作避開檔案衝突；核心計算可平行，composition/API/UI 後接。

## Research Findings
- Root planning context 仍在 Freshness Calibration 工作；本任務已建立隔離的 `.planning/2026-08-26-local-paper-tax-slippage-implementation-/`。
- Worktree 有大量既有變更與未追蹤 artifacts，均視為使用者／其他任務所有；本輪只碰隔離 planning 檔與新的 architecture plan。
- 前次 active plan 是 `2026-08-25-pr-tm-012c1-c1-runtime`，完成後必須還原。
- `simulation/settings.py` 目前是 `local-paper-settings-v1`，只有 starting cash、每日買進上限、commission rate 與最低手續費；尚無稅率、滑價或成本政策版本。
- `simulation/service.py::_stream_execution_price` 直接以 BUY=best ask、SELL=best bid 作為成交參考，表示 spread 已經反映在成交價；新增 slippage 必須定義為 BBO 之外的額外不利移動，避免重複計算 spread。
- `_fill` 目前 BUY 現金扣 `gross + commission`；SELL 現金加 `gross - commission`，realized PnL 扣買進分攤 commission 與賣出 commission，但尚未扣 sell tax。
- 訂單目前持久化 `filled_notional`、累積／末筆 commission 與 fill price；持倉只有剩餘買進 commission 成本。稅額、BBO reference、slippage 診斷值與 policy identity 都尚未納入模型／projection。
- 回測已有固定 `sell_tax_rate` 與 `slippage_bps`，但其模型多處直接做百分比運算；可考慮共用純 Decimal cost kernel，不能直接假設其 rounding／limit-price／BBO 語意適用 Local Paper。
- `WORKFLOW.md` 是 Symphony/Linear 無人值守 ticket 流程；目前是使用者直接要求的 plan-only 對話，沒有指定 Linear ticket，因此不執行 ticket mutation、commit、push 或 PR。
- `runtime/composition.py` 以 Journal session metadata 綁定 Local Paper settings，並在啟動時讀 records/checkpoint 復原；成本政策 identity 必須進 session metadata/digest，不能只留在 Dashboard draft。
- `simulation/application.py` 是 journal-first command facade，fill 後會寫 checkpoint；計畫需要讓新的 tax/slippage fill evidence 與 checkpoint 同步進化，並保留 append-only/replay 決定性。
- 回測 replay 目前以 `entry=raw*(1+slippage)`、`exit=raw*(1-slippage)`，再以 fill gross 乘 commission/tax；沒有 Local Paper limit-price 約束、BBO reference 或台股合法跳動單位。共用範圍應限於 Decimal 成本／政策 identity，不強迫共用兩種不同 execution model。
- 目前狹義搜尋尚未確認 repo 有可直接重用的台股 price tick quantizer；若沒有，slippage 後價格不可隨意以 0.01 元 round，必須新增明確 Taiwan listed-common-stock tick policy 或在無法合法量化時 fail closed。
- 財政部現行《證券交易稅條例》（2025-01-02 修正）第 2 條：公司股票由出賣人按每次實際成交價格課徵 3‰；第 2-2 條把合格上市／上櫃現股當沖相同數量部分降為 1.5‰，有效至民國 116 年 12 月 31 日（2027-12-31）。
- 當沖優惠不是單純的使用者偏好：官方條件包含同一證券商、同一帳戶、同一營業日、現款買進／現券賣出、同種類同數量及符合當沖作業規定。Local Paper 沒有 broker/account authority，因此優惠稅率只能在本機成交 lineage 與標的資格都可證明時模擬；缺證據時採一般 3‰，不可樂觀套 1.5‰。
- TWSE 官方列出的股票升降單位是依價格級距 0.01／0.05／0.1／0.5／1／5 元；slippage 後 BUY 應向不利方向上調到合法 tick、SELL 應向不利方向下調，同時不得突破使用者 limit price。
- 官方來源確認證交稅以每次實際成交價格為基礎，但本次檢索沒有找到足以凍結「每一 partial fill 稅額如何取整」的普通台股明文。計畫應把 rounding 先列為需由 broker statement/官方格式或既有 frozen RoundingPolicyV1 驗證的 Gate，而不是憑常識選一種。
- 專案的 `architecture/asset_portfolio_dual_mode_implementation_report.md` 已正式凍結 `FeePolicyV1=tw_stock_standard_v1` 與 `RoundingPolicyV1=twd_round_down_v1`：適用範圍是上市櫃普通股票、現股、**非當沖**，commission 1.425‰、最低 20 元、SELL tax 3‰，commission/tax 皆整元 `ROUND_DOWN`。因此本計畫不重新設計或引入 1.5‰ 當沖，僅把既有 frozen policy 實作到 Local Paper；當沖另案。
- Frozen policy 已定義 commission 為 order-level cumulative delta，Fill/Ledger event 原子保存 `gross_amount`、`commission`、`tax`、`net_amount`、fee/rounding policy versions；replay 直接採 persisted monetary truth，不用當前 calculator 重算歷史事件。
- `trading/local_paper.py` 已有 `local_paper_fill.v1` 與帶 settings digest/accounting evidence 的 `local_paper_fill.v2`。新增成本欄位宜發布新 kind（例如 `local_paper_fill.v3`），不能偷偷改 v2 schema；v1/v2 保持可讀，v3 嚴格驗證 tax/net/policy identity。
- 目前 projection BUY/SELL 只以 commission 建 cash/realized PnL；新增 v3 reducer 必須讀 persisted tax，SELL cash=`gross-commission-tax`、realized PnL 再扣 tax，舊 v1/v2 tax=0 以保持 replay 相容。
- 現行已實作的 Local Paper settings/commission 仍沿用較早 plan 的 `ROUND_HALF_UP_0.01_TWD` 與可編輯 rate/minimum；這和後來 frozen `tw_stock_standard_v1` 的整元 `ROUND_DOWN` 有明確衝突。新計畫不能只加 tax 而繼續宣稱 fee policy 一致，必須建立 settings/cost-policy v2 並明確標示 legacy v1 compatibility。
- Migration 應只影響新建 session：舊 `local-paper-settings-v1`/fill.v2 session 按原 Decimal 金額 replay；新 session pin `cost_policy_version=tw_stock_standard_v1`、`rounding_policy_version=twd_round_down_v1` 與 slippage policy identity，且不得回算或改寫舊事件。
- Kill Switch 計畫會修改 `runtime/composition.py`、`dashboard/server.py`、`dashboard/static/js/workspaces/simulation.js`、`dashboard/static/index.html`、`simulation/application.py` 與相關 tests/docs。Tax/slippage 的純 domain kernel、tick policy、`simulation/models.py`、`simulation/service.py`、`trading/local_paper.py` 可先在獨立 worktree 平行；composition/API/UI 整合應等 Kill Switch candidate 穩定後 rebase 再做。
- 目前測試已有 restart commission/cash/PnL、settings-bound session metadata、legacy v1 fill recovery、partial-fill 與 Dashboard settings lifecycle，這些是稅費／滑價 regression 的直接擴充點。
- 全 repo Python 搜尋未找到可重用的台股普通股 price-tick quantizer；計畫需新增獨立純函式與 tier-boundary golden tests，不能把 BidAsk 或 Kbar 類別誤當 tick-size policy。
- Dashboard 現在允許直接編輯 commission rate/minimum，settings save/apply 會建立新 session。V2 UI 應把 frozen commission/tax/rounding 顯示為唯讀「參考成本政策」，只讓 operator 編輯起始現金、每日買入額度與明確標示未校準的 slippage scenario。
- Settings apply 已有 optimistic revision、active-order/position confirmation、strategy-running blocker 與 replacement-composition handoff。Tax/slippage 應沿用此 lifecycle，不新增第二套 settings store 或 hot mutation。
- `SimulationService` 有三個會觸發撮合的入口（submit 時、snapshot reconcile、quote worker）。目前都是先用 raw snapshot/BBO 判斷 limit 再 fill；實作時必須集中成單一 `ExecutionQuote -> SlippageDecision` 路徑，並以 slippage-adjusted合法 tick price 再判斷 limit，避免某一路徑漏套模型。
- 若 adverse adjusted price 超出限價，保守語意是維持 pending 並回 `SLIPPAGE_ADJUSTED_LIMIT_NOT_REACHED`，不把價格硬 cap 到 limit；因為 best-level evidence 並不能證明 limit price 還有可成交量。只有實際 fill 才消耗 best-level volume。
- Mock/snapshot compatibility 仍可離線測試，但 fill event 必須明示 `reference_source=SNAPSHOT_COMPATIBILITY`；Shioaji path 則是 `BEST_ASK`/`BEST_BID`。兩者都套相同 fixed adverse-bps/tick/limit contract，不宣稱真實排隊順位。
- README 已明示 Local Paper 尚未計證交稅、滑價與真實排隊順位；完成後可移除前兩項限制，但「無真實排隊／market impact、非券商成交」仍必須保留。
- `StockData` 只有 `market`，Simulation 的 streaming identity 只有 `(symbol, name)`；沒有 ordinary-stock vs ETF/warrant 等可用於 `tw_stock_standard_v1` 的 durable product classification。若直接對所有 symbol 課 3‰，會對非普通股套錯稅率。
- Momentum stream 可從 Shioaji contract 取得 `security_type`，但其 `InstrumentReference` 本身也沒有保存該欄，且這條 market-data qualification pipeline 不是 Local Paper 的現成 instrument authority。計畫需要新增最小 read-only `LocalPaperInstrumentDescriptor` port（exchange/security_type/source identity），不能偷接 Momentum runtime 或以股票代碼格式猜商品。
- MockProvider 測試要顯式提供普通股 descriptor；Shioaji adapter 從既有 contract catalog 讀 identity/classification，不增加 snapshot/account/order API。分類缺失或不在 TWSE/TPEX common-stock scope 時，v2 下單 fail closed，不能 fallback 為 3‰。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 交易時段不是程式實作前置條件 | 純計算、Journal、replay、API 與 UI 測試可離線完成；只有真實滑價校準需要盤中 evidence。 |
| 法定稅率與優惠資格以官方來源為準 | 屬時間敏感的財務／法規資料，必須查核 current primary sources。 |
| Slippage 嵌入成交價，不另扣現金 | 這可讓 cash/PnL 只扣 explicit commission/tax，避免 slippage double count。 |
| 共用成本 kernel，不共用撮合時機 | Backtest 以 Kbar raw price 建模；Local Paper 以即時 BBO/partial-fill/limit 撮合，只有計算政策可共享。 |
| V1 僅實作 frozen 非當沖 3‰ tax | 專案已把 `tw_stock_standard_v1` scope 定為非當沖；擴增 1.5‰ eligibility 會超出本任務且需要標的／帳戶／fill lineage 新契約。 |
| 發布新 fill event schema，不修改 v2 | Journal 是 immutable replay truth；silent schema widening 會讓舊 replay 與 integrity check 失真。 |
| 新 session 升級 cost settings/schema，舊 session compatibility-only | 避免用新 rounding/tax/slippage 重新解釋舊 Journal 金額。 |
| 核心先平行、整合後串行 | 避免和已啟動的 Kill Switch 工作同改 composition/API/UI 造成高衝突合併。 |
| Frozen fee fields 在 v2 UI 唯讀，slippage 獨立可調 | 法定/reference cost 不能被當成情境參數；滑價是本機未校準模型，兩者 provenance 必須分開。 |
| Slippage 後再做 limit admission，超限不成交 | 不可用 raw BBO 達價就承諾一筆超過 limit 的成交，也不可假設 limit 價有未知深度。 |
| Product classification 是 cost admission 的 P0 gate | 3‰ 與 ordinary-stock tick table 不能套到 ETF、權證或未知商品。 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `session-catchup.sh` 不存在 | 使用已安裝 skill 的 `session-catchup.py`。 |

## Resources
- `/Users/stevehuang-work/.codex/skills/planning-with-files/SKILL.md`
- Repository source files and tests (to be enumerated during Phase 1)
- 財政部《證券交易稅條例》：https://law-out.mof.gov.tw/LawContent.aspx?KeyWord=&id=FL006079
- 財政部稅務入口網「買賣股票」：https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-knowledge/rwG2M1N
- TWSE「當日沖銷交易專區」：https://www.twse.com.tw/zh/products/system/day-trading.html
- TWSE「集中市場交易制度介紹」：https://www.twse.com.tw/zh/products/system/trading.html
