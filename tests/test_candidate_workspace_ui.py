from pathlib import Path


STATIC = Path(__file__).parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
SIMULATION = (STATIC / "js" / "workspaces" / "simulation.js").read_text(encoding="utf-8")


def test_candidate_list_is_a_dedicated_workspace_not_homepage_content() -> None:
    assert 'data-workspace="candidates"' in HTML
    assert 'id="candidates-view"' in HTML
    assert HTML.index('id="overview-view"') < HTML.index('id="candidates-view"')
    assert HTML.index('id="candidates-view"') < HTML.index('id="candidate-list"')


def test_workspace_switching_supports_candidate_list() -> None:
    assert 'candidatesView.classList.toggle("active", workspace === "candidates")' in APP
    assert '["overview", "candidates", "momentum"]' in APP
    assert 'candidates: ["工作區", "候選清單"' in APP


def test_snapshot_refresh_is_in_the_overview_data_status_card() -> None:
    card_start = HTML.index('class="summary-card data-status-card"')
    card_end = HTML.index("</article>", card_start)
    refresh_button = HTML.index('id="refresh-button"')

    assert card_start < refresh_button < card_end


def test_simulation_ui_exposes_reserved_cash_and_fail_closed_quote_health() -> None:
    assert 'session.stream_health === "BLOCKED"' in SIMULATION
    assert "行情保護已阻擋下單" in SIMULATION
    assert "commissionInclusiveCashReservation" in SIMULATION
    assert "含手續費現金保留" in SIMULATION


def test_local_paper_settings_page_exposes_v2_editable_and_frozen_cost_fields() -> None:
    assert "本機模擬設定" in HTML
    assert 'id="simulation-starting-cash"' in HTML
    assert 'id="simulation-daily-buy-limit"' in HTML
    assert 'id="simulation-slippage-bps"' in HTML
    assert 'id="simulation-commission-rate"' not in HTML
    assert 'id="simulation-minimum-commission"' not in HTML
    assert "固定成本政策" in HTML
    assert "賣出證交稅 0.3%" in HTML
    assert 'fetch("/api/simulation/settings"' in SIMULATION
    assert 'fetch("/api/simulation/settings/apply"' in SIMULATION
    assert "今日剩餘買入額度" in SIMULATION
    assert "session.daily_reserved_buy_notional" in SIMULATION
    assert "今日掛單保留買入額度" in SIMULATION
    assert "含手續費現金保留" in SIMULATION
    assert '"simulation-settings"' in APP


def test_simulation_positions_use_websocket_with_http_fallback() -> None:
    assert 'new WebSocket(simulationWebSocketUrl())' in SIMULATION
    assert 'message.type === "simulation_projection"' in SIMULATION
    assert 'state.simulationSocketState = "fallback"' in SIMULATION
    assert "if (simulationSocketIsOpen()) return;" in SIMULATION
    assert "loadSnapshot(false).finally(bootstrapSimulationStream)" in APP
    assert "/static/js/app.js?v=20260826-local-paper-tax-slippage-v2" in HTML
    assert '"./workspaces/simulation.js?v=20260826-local-paper-tax-slippage-v2"' in APP


def test_pending_simulation_orders_explain_live_quote_state() -> None:
    assert "WAITING_FOR_FIRST_BIDASK" in SIMULATION
    assert "等待首次 Shioaji 五檔" in SIMULATION
    assert "LIMIT_NOT_REACHED" in SIMULATION
    assert "買一／賣一" in SIMULATION


def test_recoverable_orders_expose_retry_and_high_visibility_alerts() -> None:
    assert '["SUBMITTED", "PENDING", "PARTIALLY_FILLED"]' in SIMULATION
    assert 'data-retry-order=' in SIMULATION
    assert '/retry`' in SIMULATION
    assert "重試未成交餘量" in SIMULATION
    assert "simulation.alerts || []" in SIMULATION
    assert "委託警示：${latestAlert.message" in SIMULATION
