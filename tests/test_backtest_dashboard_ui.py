"""Static contracts for the historical-backtest strategy selector."""

from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
BACKTEST = (STATIC / "js" / "workspaces" / "backtest.js").read_text(encoding="utf-8")


def test_backtest_selector_explains_and_tracks_single_or_multiple_strategies() -> None:
    assert "可選 1 個單獨執行，也可複選多個" in HTML
    assert 'id="backtest-entry-count"' in HTML
    assert 'id="backtest-exit-count"' in HTML
    assert "function syncBacktestStrategyControls(side)" in BACKTEST
    assert 'selectedCount === 1 ? "已選 1 個 · 單一策略"' in BACKTEST
    assert "`已選 ${selectedCount} 個 · 多策略`" in BACKTEST


def test_backtest_selector_validates_at_least_n_against_selected_count() -> None:
    assert "function validateBacktestStrategyPolicy(side, selected)" in BACKTEST
    assert 'policy === "AT_LEAST_N"' in BACKTEST
    assert "minimum > selected.length" in BACKTEST
    assert 'minimum.disabled = policy.value !== "AT_LEAST_N"' in BACKTEST


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


def test_historical_backtest_has_four_accessible_tabs() -> None:
    assert 'role="tablist" aria-label="歷史回測工作流程"' in HTML
    assert HTML.count('role="tab"') == 4
    assert HTML.count('role="tabpanel"') == 4
    for tab_name in (
        "1. 準備歷史資料",
        "2. 設定策略組合",
        "3. 回測工作與結果",
        "4. Baseline／Challenger 比較",
    ):
        assert tab_name in HTML
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


def test_historical_data_tab_shows_automatic_incremental_sync_status() -> None:
    assert 'id="backtest-incremental-status"' in HTML
    assert "/api/backtests/datasets/incremental-sync" in BACKTEST
    assert "收盤後自動增量同步" in HTML


def test_experimental_backtest_strategies_are_not_default_selected() -> None:
    assert 'strategy.status === "ACTIVE"' in BACKTEST
    assert 'strategy.status === "EXPERIMENTAL" ? " · 實驗中"' in BACKTEST
    assert 'missingCapabilities(strategy).length' in BACKTEST
    assert 'missing.length ? "disabled"' in BACKTEST
    assert "dataset.capabilities" in BACKTEST


def test_daily_sma_selection_warns_about_conflicting_eod_exit_without_overriding_user_choice() -> None:
    assert 'id="backtest-daily-sma-warning"' in HTML
    assert "function syncDailySmaExitWarning()" in BACKTEST
    assert "sma_20_60_golden_cross_entry_v1" in BACKTEST
    assert "sma_20_60_death_cross_exit_v1" in BACKTEST
    assert "EOD exit 會在每個日 K 收盤平倉" in BACKTEST
    assert "成交時域" in BACKTEST
