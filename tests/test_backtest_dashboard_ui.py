"""Static contracts for the Atomic-only historical-backtest workflow."""

from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
BACKTEST = (STATIC / "js" / "workspaces" / "backtest.js").read_text(encoding="utf-8")


def test_backtest_uses_published_atomic_strategy_sets_only() -> None:
    assert 'id="atomic-backtest-form"' in HTML
    assert 'id="atomic-backtest-set"' in HTML
    assert 'id="backtest-run-form"' not in HTML
    assert "舊版固定策略回測" not in HTML
    assert "selectedBacktestStrategies" not in BACKTEST


def test_backtest_does_not_require_manual_dataset_selection_or_preparation() -> None:
    for removed_id in (
        "backtest-tab-data",
        "backtest-panel-data",
        "backtest-sync-years",
        "backtest-sync",
        "backtest-dataset-list",
        "atomic-backtest-dataset",
    ):
        assert f'id="{removed_id}"' not in HTML
    assert 'id="atomic-backtest-dataset-status"' in HTML
    assert "/api/backtests/datasets/sync" not in BACKTEST
    assert "dataset_id: atomicBacktestDataset.value" not in BACKTEST


def test_dashboard_uses_collapsible_left_navigation_and_neutral_homepage() -> None:
    assert 'id="app-sidebar"' in HTML
    assert 'id="sidebar-toggle"' in HTML
    assert 'data-workspace="overview"' in HTML
    assert 'data-workspace="backtest"' in HTML
    assert 'data-workspace="positions"' in HTML
    assert 'id="overview-candidate-count"' in HTML
    assert 'id="overview-data-status"' in HTML
    assert 'id="momentum-view"' in HTML
    assert HTML.index('id="overview-view"') < HTML.index('id="momentum-view"')
    assert "function setWorkspace(workspace)" in APP


def test_historical_backtest_has_three_accessible_tabs() -> None:
    assert 'role="tablist" aria-label="歷史回測工作流程"' in HTML
    assert HTML.count("data-backtest-tab=") == 3
    assert HTML.count("data-backtest-panel=") == 3
    for tab_name in (
        "1. 設定策略組合",
        "2. 回測工作與結果",
        "3. Baseline／Challenger 比較",
    ):
        assert tab_name in HTML
    assert 'id="backtest-tab-setup" type="button" role="tab" aria-selected="true"' in HTML
    assert "function setBacktestTab(tabName)" in APP


def test_full_page_workspace_keeps_sidebar_gap_and_mobile_toggle_layered() -> None:
    assert "left: 266px" in CSS
    assert "width: calc(100vw - 266px)" in CSS
    assert "top: 18px" in CSS
    assert ".app-shell.sidebar-mobile-open .sidebar-toggle" in CSS
    assert "z-index: 31" in CSS


def test_mobile_navigation_keeps_aria_state_in_sync_with_the_hidden_sidebar() -> None:
    assert "function syncSidebarToggle()" in APP
    assert "function closeMobileSidebar()" in APP
    assert 'window.addEventListener("resize", syncSidebarToggle)' in APP
    assert "syncSidebarToggle();" in APP


def test_atomic_launcher_reports_server_managed_dataset_readiness() -> None:
    assert "/api/backtests/atomic-dataset" in BACKTEST
    assert "ATOMIC_BACKTEST_DEFAULT" in BACKTEST
    assert "expected_binding_revision" in BACKTEST
    assert "expected_dataset_digest" in BACKTEST
    assert 'dataset.status === "READY"' not in BACKTEST
    assert '/api/backtests/datasets"' not in BACKTEST


def test_formal_readiness_is_split_into_platform_data_and_strategy() -> None:
    for readiness_id in (
        "backtest-platform-readiness",
        "backtest-data-readiness",
        "backtest-strategy-readiness",
    ):
        assert f'id="{readiness_id}"' in HTML
    assert "projection?.status" in BACKTEST
    assert "NO_QUALIFYING_STRATEGY" in BACKTEST
    assert "formal_research_readiness" in BACKTEST
    assert "不會改變 lifecycle" in BACKTEST


def test_formal_result_ui_consumes_summary_formal_evidence_only() -> None:
    assert "const formalEvidence = summary.formal_evidence || null;" in BACKTEST
    assert "data.formal_evidence" not in BACKTEST
    assert "summary.formal_evidence" in HTML
    assert "120 個 active dates" in HTML
    assert "至少 4 個 Walk-forward folds" in HTML
    assert "至少 3/4 正向" in HTML


def test_legacy_runs_are_read_only_in_the_atomic_clone_flow() -> None:
    assert "舊版 Run 只保留查閱" in BACKTEST
    assert "backtestRunRequest" not in BACKTEST
