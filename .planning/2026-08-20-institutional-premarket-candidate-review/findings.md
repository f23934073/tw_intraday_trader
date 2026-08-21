# Findings & Decisions

## Requirements
- Review 使用者提供的三大法人盤前觀察名單策略提案，不能只做文字潤飾。
- 以目前 checkout 的 domain、服務、資料、回測、API/UI 與測試 seam 為依據。
- 撰寫可執行且有驗收 gate 的 implementation plan；不修改產品程式。
- 保持 research / paper-simulation only；Production strategy HOLD、Real-money PROHIBITED。

## Research Findings
- 附件把法人資料定位為 `Premarket Candidate Prior`，開盤後仍由 Gap/RVOL/VWAP/ORB 等即時訊號決定 entry；方向上符合現有 decision-support 架構。
- 附件新增四個 P0：trade-scope alignment、歷史 `usable_from_session`、分市場 completeness、法人類型分離；這些需逐一對照目前程式是否已有 seam。
- Root worktree 有使用者既有 freshness calibration 程式、測試與 evidence 變更，本次不得觸碰。
- Repository 已有 `candidate/` bounded area（models/engine/pool/sources）與 `CandidateSource`；附件的 candidate merge 概念應延伸現有 seam，不另造第二套候選模型。
- Repository 已有完整的 `architecture/previous_day_premarket_watchlist_implementation_plan.md`，其中已規劃 `watchlist/` bounded context、artifact/repository/application 與 `PreviousSessionWatchlistCandidateSource`。法人 plan 必須擴充這份架構，避免重複建置 watchlist platform。
- Shioaji Tick+BidAsk provider 目前明定最多同時監控 100 檔；附件建議 30-80 檔在 provider 上限內，但仍需與 manual/position/scanner 保留名額及 subscription eviction policy 一起設計，不能把 80 視為固定安全值。
- 現有 strategy catalog 已支援 `required_capabilities`，適合表達 TWSE/TPEx 分市場 readiness；不能只用一個粗粒度 `INSTITUTIONAL_FLOW` capability。
- `Candidate` 已原生支援多個 `sources` 與 `matched_rules`，所以附件的 `sources=[...]` 不需要改 domain 形狀；但現有 enum 尚無法人／前日 watchlist source。
- `CandidateDiscovery` 已有 immutable-ish `evidence` mapping、rank types、best rank、priority、TTL，且 `CandidatePool` 會合併來源並以 priority/rank 排序。法人 adapter 應產生 discovery，不應直接把 `PremarketScore` 塞進 `BuyScoreEngine`。
- `CandidatePoolEntry` 目前不保留各 contribution 的 evidence；若 Dashboard 要顯示 foreign/trust ranks、策略 matched rules 與 artifact digest，需要獨立 watchlist detail projection/repository，或對 pool entry 增加可稽核 contribution summary。只把 score 映射為 `priority` 會遺失理由與版本。
- `SubscriptionManager` 已提供 protected source、最小停留、capacity eviction、ack timeout 與 fail-closed capacity accounting；institutional candidates 應走這條既有路徑。固定「名單 30-80 檔」要改成 `ranked candidates + reviewed max_symbols/headroom`，由 manager 決定實際訂閱集合。
- `ShioajiProvider.sync_quote_subscriptions()` 是同一 provider 的最終操作 seam；目前 local simulation 只送持倉／掛單 symbols，而 momentum runtime 才使用 CandidatePool/SubscriptionManager。implementation plan 必須明確限制法人 watchlist 接到 momentum candidate runtime，不能意外改變 simulation service 的持倉／掛單訂閱語意。
- 現有 `watchlist/` 尚未實作；法人功能依賴既有 previous-day watchlist plan 的 Phase 0-2（calendar、PIT universe、corporate action、daily derivation、artifact/repository）。若另起一套法人 pipeline，會重複 calendar/universe/artifact/persistence 並造成兩套 as-of 規則。
- 現有 `DatasetManifest` 能保存 capabilities、lineage、session/price/volume contract 與 research eligibility，但 provider historical collection 明確是 `CURRENT_SNAPSHOT`、不含下市股票、不可作 survivorship-free 正式證據。法人 factor/OOS 研究必須使用 date-effective universe；當日前瞻名單可允許 current snapshot，但要標 `research_eligible=false`。
- 現有 `InstrumentReferenceStore` 只處理 current-session reference/limits，沒有 security type、listing/delisting、industry 或 market-cap effective ranges，不能滿足普通股篩選與 industry/size-neutral ranking。
- 附件提出 industry-neutral／market-cap-neutral rank，卻沒有把 PIT classification／size snapshot 納入 P0 contract。這是 formal research blocker；沒有 date-effective sector/size digest 時只能做 raw rank 並標記 confounding-limited。
- 既有 previous-day watchlist plan 已定義 `CandidateSource.PREVIOUS_SESSION_WATCHLIST`。建議沿用這個 source，將 `institutional_foreign_rank_5d_v0` 等放在 matched strategy IDs/evidence；新增 `CandidateSource.INSTITUTIONAL` 會把「產生時點／生命週期」與「因子種類」混成兩套 source taxonomy。
- Candidate quality 的正式問題是 institutional watchlist 是否提高既有 intraday setup 的 hit rate／net expectancy。只訂閱 shortlisted symbols 的 live runtime 無法觀察未入選母體的 setup denominator；Formal Validation 必須用完整歷史 intraday universe 或 deterministic matched-control dataset，不能用 paper shadow 的 shortlist 結果冒充全市場 lift。
- 現有 backtest engine 支援 daily-next-bar 與 intraday-next-bar，但沒有「T-1 watchlist artifact gate → T 日 intraday setup」的 paired evaluation contract。需要獨立 `WatchlistEvaluationService`/report，把 immutable candidate artifact 與既有 intraday decisions/outcomes join；不要把 premarket score 注入 `StrategyContext` 當 entry signal。
- 附件的 80/90 percentile 與加權 score 是研究假說，不是已驗證門檻。若在 factor diagnostics 前固定為產品 score，會產生 circular selection/data snooping。初版應先輸出 continuous ranks與 deciles；門檻/權重只可由 train/validation 選版，holdout 不回填。
- 現有 Dashboard momentum runtime 的 `_dashboard_candidate_discoveries()` 會把 Dashboard 候選全部重新標成 `CandidateSource.AUTO`，並以既有 BuyScore 當 subscription priority。即使上游回傳 institutional source，這條 adapter 也會遺失來源與法人 evidence；法人 artifact 應透過獨立 `PreviousSessionWatchlistCandidateSource` 注入 runtime，或修正 adapter 產生各原始 source contribution，不能偽裝成 AUTO。
- Dashboard momentum 的 subscription config 目前 `account_subscription_limit=200`、Tick+BidAsk、`reserved_headroom=0`，即最多 100 symbols 且沒有預留。institutional rollout 必須先凍結 reviewed headroom 與 source priority；不能讓 80 檔盤前名單吃滿容量並使 scanner/active monitoring 失去空間。
- Momentum runtime 會為每個欲訂閱 symbol 取得 current-session `InstrumentReference` 並要求 eligible；這是可重用的 fail-closed admission gate。法人前日名單不應繞過它，也不應因前日 PIT universe eligible 就假設 T 日仍可訂閱。
- `candidate_snapshot_loader` 現在服務的是既有即時 candidate snapshot，並把 BuyScore 映射為優先序。將 premarket score 混進該 payload 會把 Candidate Prior 與 Entry Quality 再次耦合；plan 應保留兩個 read model，再在 CandidatePool contribution 層合併。
- `BuyScoreEngine` 的 input 僅是即時 `StockData`，details 只描述即時 scoring rules；此邊界正好支持附件的「Premarket Score 不得直接變 BuyScore」。法人 score/rank 應留在 watchlist artifact/detail API，BuyScore 不新增法人 rule。
- `StrategyContext` 與 `HistoricalBacktestEngine` 目前逐 bar 建立 intraday/daily price features，並直接評估 entry/exit；沒有 watchlist eligibility 欄位。為避免 Candidate Prior 被實作成 entry trigger，plan 不修改 `StrategyContext`，而是在 run/evaluation population layer 以 target-session artifact 篩選或標記 cohort。
- Backtest capability preflight 目前只看單一 dataset manifest 的 capability set。法人研究需要 composite manifest（price/intraday bars + institutional partitions + PIT universe/classification + calendar）；若只是把多個 capability 字串塞進 price dataset，lineage 會失真。
- TWSE 官方 T86 公開查詢頁目前標示自 2012-05-02 提供；TWSE Data E-Shop 官方商品則明示每日 18:00 產製不含鉅額 TWT86UC、20:00 產製含鉅額 TWTAIUC，自 2004-09-09 起，且授權區分內部／外部使用。source/scope/license 必須進 manifest，不能把公開與付費檔視為可互換 byte source。
- TPEx 官方頁明示三大法人合計 = 外陸資淨買（不含外資自營商） + 投信淨買 + 自營商淨買；外資自營商已計入自營商，因此不能再加一次。資料依當日原始成交統計，不依錯帳／更正帳號調整後資料。這兩個公式與 correction policy 都應是 normalization fail-closed contract。
- TPEx 官方逐股明細自 2007-04-20 起提供，且官方說明本身提到 ETF，證明 endpoint universe 不能直接等同普通股母體；仍需 PIT security type filter。
- 2026-08-19 的 TWSE T86 官方頁目前明示包含一般、零股、盤後定價、鉅額，排除拍賣／標購，並使用原始成交、非錯帳更正後資料。由於官方付費商品另有 18:00 不含鉅額與 20:00 含鉅額兩版本，ingestion 必須解析並保存每次 response 的 scope note；建議 premarket canonical scope 固定為 final-with-block after 20:00，歷史/live 不能混用不同 scope。
- 附件建議的 `net_buy_ratio` / `flow_adv20_ratio` 在目前專案不能直接列為 formal feature：現有 Shioaji/derived OHLCV volume contract 未證明包含與 T86 完全相同的一般＋零股＋盤後定價＋鉅額範圍。若 denominator scope 不相容，feature status 必須是 `SCOPE_INCOMPATIBLE`，不得計算後只加 warning。
- 第一階段可保留 exact component share counts、component self-normalized ratio（例如 net / gross institutional shares，需明確定義零分母）與 size/industry-bucket ranks作 diagnostics；任何用 market volume/ADV 的 variant 要等 compatible denominator dataset 通過 reconciliation 才具有 formal eligibility。
- 現有 SQL migrations 是 forward-only `001`-`003`；previous-day watchlist plan 已預留 `004_previous_day_watchlists.sql`。法人資料應以該 migration 為 dependency，再新增 `005_institutional_premarket_candidate.sql`，不能另建重複的 watchlist artifact/entry tables。
- SQLite backtest repository 另有內嵌 schema 初始化路徑；實作 schema 時必須同時更新 PostgreSQL migration 與 SQLite schema/adapter tests，避免只在其中一種 storage 可用。
- 現有 `_JsonBacktestRepository` 已承擔大量 backtest persistence。法人 row/partition/diagnostic 若全部塞入同一 port 會擴大責任；應新增 `InstitutionalFlowRepository`，watchlist artifact 則沿用既有計畫的 `WatchlistRepository`，adapter 可共用 connection factory。
- `pyproject.toml` package discovery 尚未包含未實作的 `watchlist*` 或未來 `institutional_data*`；Phase 0 必須加入 package include 並驗證 wheel 內容，否則 editable checkout 可跑、部署 artifact 會缺 package。
- 現有 `config/settings.py` 是 MVP 常數集合；法人 feature flag、cutoff、coverage/scope requirements 與 strategy spec 應分別進 `config/watchlist.py`、`config/institutional.py`，不要繼續堆入全域 settings。
- Strategy catalog 的 executable binding 是 explicit allowlist。法人 strategy definition 在 callable 與 binding 尚未完成前只能標 `DRAFT`/`EXPERIMENTAL`；不可先宣稱 executable，否則 catalog/UI 會高估 readiness。
- 附件提出的晚到資料處理仍缺 active-session freeze。需定義盤前 cutoff：cutoff 前發布且通過 manifest gate 的 artifact 才能進 T 日 active pool；cutoff 後的重抓或修正只能作 audit/research，不得在盤中改寫 candidate cohort。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 以 severity-first review 撰寫 | 先處理會造成 look-ahead、母體偏誤、subscription 超限或不相容 API 的問題。 |
| 沿用 `PREVIOUS_SESSION_WATCHLIST` source | Source 表達生命週期；法人因子由 strategy ID、artifact 與 evidence 表達。 |
| 法人 persistence 使用獨立 repository port | 避免擴大既有 backtest repository，並讓 live ingestion 與 research storage 共用明確 contract。 |
| 初版不發布機率式 PremarketScore | 在 OOS calibration 前僅提供 continuous rank/percentile/tier，避免把任意加權分數誤讀為勝率。 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 第一個官方 web 搜尋呼叫沒有回傳可讀 content | 改用較小的官方查詢／直接開啟官方頁面，並把來源結果記錄在 findings；不依賴無輸出的呼叫。 |

## Resources
- 使用者附件 `pasted-text.txt`。
- 現有 `tw_intraday_trader` source/tests/architecture。
- TWSE / TPEx 官方三大法人資料說明。
