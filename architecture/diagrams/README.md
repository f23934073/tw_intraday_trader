# Current-State 架構圖集

```text
source_snapshot: main@657c3bbc117af1c2909175dfc799bce7e8be07ca
captured_at: 2026-08-25T11:25:47+0800
baseline_note: origin/main was verified by `git ls-remote` at the same SHA; local `.git` mutation was not permitted, so the atlas was produced in-place from the checked-out source.
```

本圖集描述目前 repository 的可回查實作狀態。專案定位是 modular monolith，部分 runtime 以 Ports/Adapters seam 與 event-driven workers 分工；本文不宣稱它是嚴格 Clean Architecture。

## 圖例

| 狀態 | 語意 |
| --- | --- |
| Implemented | 目前 source 已接線，會在對應 entrypoint 或 CLI 中使用。 |
| Experimental/Research | 已實作研究、實驗、Backtest 或 evidence 流程，但不可視為 production-ready 或 live promotion。 |
| Observe-only | 只產生觀察、投影或 evidence，不改候選、風控、委託、帳務或 broker 狀態。 |
| Planned/Not wired | source 中以設定、計畫或安全邊界存在，但目前未接上 runtime；圖中以虛線表示。 |
| External system | Browser、Shioaji、FinMind、TWSE、TPEX、TAIFEX 等 process 外部系統。 |
| Persistent store | PostgreSQL、SQLite、filesystem immutable artifacts 或 process-local memory；每種 durability/authority 需分開判讀。 |

## 閱讀順序

1. 先讀 01-05，建立系統邊界、process topology、bounded context、authority 與 entrypoint lifecycle 的共同語彙。
2. 再讀 06-12，理解 Dashboard、Scanner、canonical market data、FeatureEngine、Strategy Catalog、Local Paper 與 automated Local Paper 的即時流程。
3. 接著讀 13-16，分開看 FinMind/Dataset、Backtest、TAIFEX 夜盤與法人研究資料流。
4. 最後讀 17-21，核對 persistence、Trade Management Shadow、scheduler、health check 與 trust boundary。

## 圖表索引

| # | 圖 | Mermaid source | SVG |
| --- | --- | --- | --- |
| 01 | C4 System Context | [01_system_context.mmd](src/01_system_context.mmd) | [01_system_context.svg](rendered/01_system_context.svg) |
| 02 | Runtime/Process Topology | [02_runtime_process_topology.mmd](src/02_runtime_process_topology.mmd) | [02_runtime_process_topology.svg](rendered/02_runtime_process_topology.svg) |
| 03 | Backend Module/Bounded Context Map | [03_backend_module_context_map.mmd](src/03_backend_module_context_map.mmd) | [03_backend_module_context_map.svg](rendered/03_backend_module_context_map.svg) |
| 04 | Execution Modes 與 Authority Boundary | [04_execution_modes_authority_boundary.mmd](src/04_execution_modes_authority_boundary.mmd) | [04_execution_modes_authority_boundary.svg](rendered/04_execution_modes_authority_boundary.svg) |
| 05 | Entrypoint、Composition Root 與 Process Lifecycle | [05_entrypoint_composition_lifecycle.mmd](src/05_entrypoint_composition_lifecycle.mmd) | [05_entrypoint_composition_lifecycle.svg](rendered/05_entrypoint_composition_lifecycle.svg) |
| 06 | Dashboard Frontend、REST API 與 WebSocket | [06_dashboard_rest_websocket.mmd](src/06_dashboard_rest_websocket.mmd) | [06_dashboard_rest_websocket.svg](rendered/06_dashboard_rest_websocket.svg) |
| 07 | Scanner：Watchlist → Candidate → Buy Score → Position | [07_scanner_candidate_score_position.mmd](src/07_scanner_candidate_score_position.mmd) | [07_scanner_candidate_score_position.svg](rendered/07_scanner_candidate_score_position.svg) |
| 08 | Canonical Market Data：Tick/BidAsk → Queue → Journal → Projection → Replay | [08_canonical_market_data_pipeline.mmd](src/08_canonical_market_data_pipeline.mmd) | [08_canonical_market_data_pipeline.svg](rendered/08_canonical_market_data_pipeline.svg) |
| 09 | FeatureEngine → Atomic Strategy/Momentum Signal → Web Projection | [09_feature_signal_web_projection.mmd](src/09_feature_signal_web_projection.mmd) | [09_feature_signal_web_projection.svg](rendered/09_feature_signal_web_projection.svg) |
| 10 | Strategy Template/Draft/Version/Strategy Set Lifecycle | [10_strategy_catalog_lifecycle.mmd](src/10_strategy_catalog_lifecycle.mmd) | [10_strategy_catalog_lifecycle.svg](rendered/10_strategy_catalog_lifecycle.svg) |
| 11 | Local Paper：Command → Journal → RiskGate → Simulation → Fill | [11_local_paper_command_journal_fill.mmd](src/11_local_paper_command_journal_fill.mmd) | [11_local_paper_command_journal_fill.svg](rendered/11_local_paper_command_journal_fill.svg) |
| 12 | Automated Local Paper、Kill Switch、交易時段與強制出場 | [12_automated_local_paper_controls.mmd](src/12_automated_local_paper_controls.mmd) | [12_automated_local_paper_controls.svg](rendered/12_automated_local_paper_controls.svg) |
| 13 | FinMind/Provider Acquisition → Immutable Dataset → Default Binding | [13_finmind_dataset_binding.mmd](src/13_finmind_dataset_binding.mmd) | [13_finmind_dataset_binding.svg](rendered/13_finmind_dataset_binding.svg) |
| 14 | Backtest Run → Worker → Result Chunks → Comparison/Qualification | [14_backtest_worker_results_qualification.mmd](src/14_backtest_worker_results_qualification.mmd) | [14_backtest_worker_results_qualification.svg](rendered/14_backtest_worker_results_qualification.svg) |
| 15 | TAIFEX 夜盤 Context、Qualification 與官方 Reconciliation | [15_taifex_night_context_qualification.mmd](src/15_taifex_night_context_qualification.mmd) | [15_taifex_night_context_qualification.svg](rendered/15_taifex_night_context_qualification.svg) |
| 16 | Institutional Data → PIT Research → Candidate Prior → Shadow Admission | [16_institutional_prior_shadow_admission.mmd](src/16_institutional_prior_shadow_admission.mmd) | [16_institutional_prior_shadow_admission.svg](rendered/16_institutional_prior_shadow_admission.svg) |
| 17 | Trading Journal/Local Paper Logical ERD | [17_trading_journal_local_paper_erd.mmd](src/17_trading_journal_local_paper_erd.mmd) | [17_trading_journal_local_paper_erd.svg](rendered/17_trading_journal_local_paper_erd.svg) |
| 18 | Backtest/Strategy Catalog Logical ERD | [18_backtest_strategy_catalog_erd.mmd](src/18_backtest_strategy_catalog_erd.mmd) | [18_backtest_strategy_catalog_erd.svg](rendered/18_backtest_strategy_catalog_erd.svg) |
| 19 | Institutional Prior/Artifact Persistence Logical ERD | [19_institutional_prior_artifact_erd.mmd](src/19_institutional_prior_artifact_erd.mmd) | [19_institutional_prior_artifact_erd.svg](rendered/19_institutional_prior_artifact_erd.svg) |
| 20 | Trade Management Shadow、Replay 與 Evidence Qualification | [20_trade_management_shadow_evidence.mmd](src/20_trade_management_shadow_evidence.mmd) | [20_trade_management_shadow_evidence.svg](rendered/20_trade_management_shadow_evidence.svg) |
| 21 | Configuration、Scheduler、Health Check、Security/Trust Boundary | [21_config_scheduler_health_security.mmd](src/21_config_scheduler_health_security.mmd) | [21_config_scheduler_health_security.svg](rendered/21_config_scheduler_health_security.svg) |

## Source Coverage

覆蓋矩陣見 [source_coverage.md](source_coverage.md)。每張 `.mmd` 檔案開頭也有目的、閱讀方式、source anchors、runtime/authority 注意事項與同一份 source snapshot。
