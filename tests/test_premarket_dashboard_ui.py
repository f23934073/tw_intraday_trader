"""Static contracts for the observation-only TAIFEX premarket panel."""

from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")


def test_premarket_panel_has_accessible_separate_status_regions() -> None:
    assert 'id="premarket-panel"' in HTML
    assert 'id="premarket-content" aria-live="polite" aria-busy="true"' in HTML
    assert 'id="premarket-context-health"' in HTML
    assert 'id="premarket-reconciliation-status"' in HTML
    assert "市場情境，不等於個股開盤預測" in HTML


def test_premarket_renderer_only_formats_backend_projection() -> None:
    assert "function renderPremarketContext(context)" in APP
    assert "renderPremarketContext(snapshot.premarket_context);" in APP
    assert 'context.metrics?.session_move_pct' in APP
    assert 'context.metrics?.provider_reference_change_pct' in APP
    assert "close / open" not in APP
    assert "now >= 05:05" not in APP
    assert "SHIOAJI_CONTRACT_INFO" not in APP


def test_premarket_copy_preserves_evidence_boundaries() -> None:
    assert "Shioaji 參考價" in APP
    assert "TAIFEX 對帳" in APP
    assert "期交所結算價" not in HTML
    assert "FLAT" not in HTML
    assert 'premarketStatusLabels' in APP
    for status in ("READY", "PENDING", "NOT_APPLICABLE", "DEGRADED", "UNAVAILABLE"):
        assert f'{status}:' in APP


def test_premarket_panel_has_narrow_layout_rule() -> None:
    assert ".premarket-grid { grid-template-columns: 1fr; }" in CSS
