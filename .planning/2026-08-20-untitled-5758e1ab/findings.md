# Findings & Decisions

## Requirements
- 分析如何取得台灣上市／上櫃三大法人逐股資料。
- 將資料轉為可回測、可評審的策略輸入，而非只顯示在 UI。
- 交付完整 report；包含來源、欄位、時序、策略、風險、實作階段與驗收。
- 本次不修改產品程式。

## Research Findings
- 目前 `tw_intraday_trader` 的 `StockData`、Candidate、Score、backtest `StrategyContext` 與 executable registry 都沒有三大法人欄位或策略；唯一文字命中把「三大法人期貨部位」列為既有夜盤計畫的 out of scope。
- 過去另一個 `tw_stock_qt` 工作流曾實作 TWSE T86 盤後確認；可重用的設計教訓是：盤中資金流只能標為 proxy、T86 必須保持 `post_close` 語意、raw/normalized artifacts 要可重跑，且 component total 不一致應 fail closed。這些是先驗提示，仍需用本次官方資料與目前 checkout 驗證。
- 現有 backtest `HistoricalBar` 僅含 OHLCV/amount/market/session time；`StrategyContext` 由 bar、盤中 features、daily SMA 與 position context 組成。法人資料適合新增獨立 `InstitutionalFeatureSnapshot`，由 engine 依 `available_at <= decision_at` 注入，而不是改寫 Kbar 或即時 `StockData`。
- 現有 `DatasetManifest` 已有 capabilities、lineage、SHA-256、research eligibility 與 issues，可擴充成 price dataset + institutional dataset 的 immutable composite input；strategy catalog 已支援 required capabilities 與版本不可變。
- TWSE 官網 T86 提供逐股三大法人日報，公開查詢頁標示資料自 2012-05-02 提供；官方付費 TWT86UC/TWTAIUC 檔自 2004-09-09，分別於交易日 18:00（不含鉅額）與 20:00（含鉅額）產製。
- TWSE T86 欄位拆分外陸資（不含外資自營商）、外資自營商、投信、自營商自行買賣、自營商避險及三大法人合計；付費說明明確指出 TWT86UC 不含鉅額、TWTAIUC 含鉅額。
- TPEx 官網逐股明細自 2007-04-20 起提供，並明示三大法人合計 = 外資及陸資淨買（不含自營商）+ 投信淨買 + 自營商淨買；外資自營商因已計入自營商，不再加進合計。
- TWSE 歷史查詢實際 endpoint 為 `/rwd/zh/fund/T86?date=YYYYMMDD&selectType=...&response=json`；2026-08-19 的 `ALL` response 有 15,211 列、19 欄，且混有 ETF／權證等商品，不能把 `ALL` 直接當普通股母體。
- TWSE 2026-08-19 的 2330 樣本通過合計檢查：外陸資（不含外資自營商） -7,417,943 股、投信 -668,410 股、自營商 +719,342 股，合計 -7,367,011 股。
- TPEx 歷史 endpoint `/www/zh-tw/insti/dailyTrade?date=YYYY/MM/DD&type=Daily&sect=EW` 已驗證可指定日期；2026-08-19 response 為 `stat=ok`、892 列、25 欄。`EW` 雖排除權證與牛熊證，仍可含 ETF／債券等非普通股，仍須 point-in-time security master 二次篩選。
- TPEx OpenAPI `GET /tpex_3insti_daily_trading` 已驗證只能作最新資料監看；欄位英文名稱有重複／易誤解情況，不宜直接作歷史正規化的唯一 canonical source。
- 現有 Shioaji contract reference 是 current-only，且 `InstrumentReference` 沒有歷史 security type、上市／下市有效區間；若直接拿目前合約反查歷史母體，會產生 survivorship bias。
- 實證文獻並不一致：部分台灣共同基金 herding 研究觀察到買進後延續，但早期日資料研究未發現三類法人交易能影響報酬。策略應視為待驗證假說，不可把文獻直接轉成固定門檻或獲利保證。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 將「資料日期」與「系統可觀測時間」分開保存 | 法人日資料是盤後資料，回測不得在同日盤中使用。 |
| 上市與上櫃使用各自官方來源，再正規化 | 兩市場發布介面與欄位可能不同，不應假設單一 endpoint 覆蓋全市場。 |
| 先把法人資料做成獨立 domain input，不擴充 `StockData` | `StockData` 是即時行情快照；盤後法人資料有不同時序與 lineage。 |
| 初版以 cross-sectional rank 與 consensus/persistence 假說為主 | 相對排名比固定股數門檻更能跨股價、市值與成交量；仍須以成交量正規化。 |
| 自營商避險只作風險／分歧特徵，不作主要方向訊號 | 避險流量可能反映衍生品與造市需求，方向解讀較弱。 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Web opener 對帶 query 的 TWSE/TPEX JSON URL 判定為 unsafe，無法直接讀 response | 改用官方頁面／Swagger 搜尋證據，並準備用唯讀 `curl` 實際驗證 endpoint。 |

## Resources
- 本專案策略 catalog、`StockData`、Candidate/Score 與 backtest registry。
- TWSE、TPEX 官方公開資料與說明頁（待查核）。
