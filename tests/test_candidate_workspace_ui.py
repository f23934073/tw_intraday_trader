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
    assert "已保留 ${formatNumber(session.reserved_cash, 0)} 元掛單額度" in SIMULATION
