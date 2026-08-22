"""Structural contracts for the dashboard's browser-native module graph."""

from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
WORKSPACES = STATIC / "js" / "workspaces"


def test_dashboard_layout_loads_external_css_and_one_module_entrypoint() -> None:
    assert '<link rel="stylesheet" href="/static/css/dashboard.css">' in HTML
    assert (
        '<script type="module" '
        'src="/static/js/app.js?v=20260821-atomic-strategy-v2"></script>'
    ) in HTML
    assert "<style>" not in HTML
    assert "<script>" not in HTML


def test_entrypoint_composes_workspace_modules_instead_of_embedding_them() -> None:
    factories = {
        "candidates": "createCandidateWorkspace",
        "simulation": "createSimulationWorkspace",
        "momentum": "createMomentumWorkspace",
        "backtest": "createBacktestWorkspace",
    }
    for module, factory in factories.items():
        assert f'./workspaces/{module}.js' in APP
        source = (WORKSPACES / f"{module}.js").read_text(encoding="utf-8")
        assert factory in source
    assert len(APP.splitlines()) < 550


def test_workspace_factories_declare_cross_workspace_dependencies() -> None:
    candidates = (WORKSPACES / "candidates.js").read_text(encoding="utf-8")
    momentum = (WORKSPACES / "momentum.js").read_text(encoding="utf-8")
    backtest = (WORKSPACES / "backtest.js").read_text(encoding="utf-8")

    assert "formatSource" in candidates.splitlines()[1]
    assert "formatSource" in momentum.splitlines()[1]
    assert "ruleLabels" in momentum.splitlines()[1]
    assert "setWorkspace" in "\n".join(backtest.splitlines()[:6])
    assert "formatSource" in APP
    assert "ruleLabels" in APP
    assert "setWorkspace" in APP


def test_simulation_workspace_exposes_explicit_automated_strategy_controls() -> None:
    simulation = (WORKSPACES / "simulation.js").read_text(encoding="utf-8")

    for element_id in (
        "automated-strategy-form",
        "automated-strategy-set",
        "automated-stop-loss",
        "automated-take-profit",
        "automated-max-daily-loss",
        "automated-strategy-start",
        "automated-strategy-stop",
        "automated-strategy-kill",
        "automated-strategy-kill-reset",
        "automated-strategy-status",
    ):
        assert f'id="{element_id}"' in HTML
    assert "/api/simulation/automated-strategy/start" in simulation
    assert "/api/simulation/automated-strategy/stop" in simulation
    assert "/api/simulation/automated-strategy/kill-switch" in simulation
    assert "/api/strategy-sets" in simulation
    assert "X-Strategy-CSRF" in simulation
    assert "loadAutomatedStrategyStatus" in simulation
    assert "submitAutomatedStrategy" in simulation
    assert "stopAutomatedStrategy" in simulation
    assert "pollAutomatedStrategyStatus" in APP
    assert (
        './workspaces/simulation.js?v=20260822-share-native-v1'
        in APP
    )


def test_simulation_order_ticket_uses_exact_share_quantity() -> None:
    simulation = (WORKSPACES / "simulation.js").read_text(encoding="utf-8")
    candidates = (WORKSPACES / "candidates.js").read_text(encoding="utf-8")

    assert 'for="order-shares">股數（1～999 股為零股）' in HTML
    assert 'id="order-shares"' in HTML
    assert 'id="order-simulation-boundary"' in HTML
    assert "不代表證交所零股五檔或券商成交" in HTML
    assert "order-simulation-boundary" not in simulation
    assert "order-simulation-boundary" not in candidates
    assert "quantity_shares" in simulation
    assert "order.quantity_shares" in simulation


def test_topbar_exposes_exhausted_shioaji_usage_status() -> None:
    assert 'id="shioaji-usage-status"' in HTML
    assert "/api/dashboard/provider-usage" in APP
    assert "renderProviderUsage" in APP
    assert "loadProviderUsage" in APP
    assert "pollProviderUsage" in APP
    assert "Shioaji 流量已超過" in APP
    assert "window.setInterval(pollProviderUsage, 60000)" in APP
