from pathlib import Path


HTML = (
    Path(__file__).resolve().parents[1]
    / "dashboard"
    / "static"
    / "index.html"
).read_text(encoding="utf-8")


def test_momentum_dashboard_has_truthful_labels_and_accessible_region():
    assert 'id="momentum-status"' in HTML
    assert 'id="momentum-content" aria-live="polite" aria-busy="true"' in HTML
    assert "Replay fixture／非即時" in HTML
    assert "Evidence Score 是規則證據，不是漲停機率" in HTML
    assert "Momentum Entry" in HTML
    assert "漲停加速 · ${pendingAlerts.length} 則" in HTML
    assert "100% 會漲停" not in HTML


def test_momentum_dashboard_reads_local_projection_and_acknowledges_alerts():
    assert 'fetch("/api/dashboard/momentum", { cache: "no-store" })' in HTML
    assert "/api/dashboard/momentum/alerts/${encodeURIComponent(alertId)}" in HTML
    assert 'method: "POST"' in HTML
    assert "function renderMomentum(momentum)" in HTML
    assert "function pollMomentumProjection()" in HTML
    assert "state.momentumRenderKey !== momentum.summary?.projection_digest" in HTML


def test_momentum_dashboard_does_not_compute_signal_or_stage_in_browser():
    assert "momentum_acceleration_confirmed" not in HTML
    assert "volume_acceleration_2m /" not in HTML
    assert "LIMIT_UP_MOMENTUM =" not in HTML
    assert "item.signal.evidence_score" in HTML
    assert "item.current_stage_label" in HTML


def test_momentum_dashboard_has_narrow_layout_rules():
    assert ".momentum-layout { grid-template-columns: 1fr; }" in HTML
    assert ".momentum-evidence-grid { grid-template-columns: 1fr; }" in HTML
    assert ".momentum-price-grid { grid-template-columns: repeat(2" in HTML
