"""Structural contracts for the dashboard's browser-native module graph."""

from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
WORKSPACES = STATIC / "js" / "workspaces"


def test_dashboard_layout_loads_external_css_and_one_module_entrypoint() -> None:
    assert '<link rel="stylesheet" href="/static/css/dashboard.css">' in HTML
    assert '<script type="module" src="/static/js/app.js"></script>' in HTML
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
    assert "setWorkspace" in backtest.splitlines()[1]
    assert "formatSource" in APP
    assert "ruleLabels" in APP
    assert "setWorkspace" in APP
