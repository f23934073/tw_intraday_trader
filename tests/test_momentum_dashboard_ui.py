from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
MOMENTUM = (STATIC / "js" / "workspaces" / "momentum.js").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")


def test_momentum_dashboard_has_truthful_labels_and_accessible_region():
    assert 'id="momentum-status"' in HTML
    assert 'id="momentum-content" aria-live="polite" aria-busy="true"' in HTML
    assert "Realtime Shadow" in HTML
    assert "即時 Tick／BidAsk" in MOMENTUM
    assert "候選盤中策略評估清單" in MOMENTUM
    assert "已成立規則與值" in MOMENTUM
    assert "100% 會漲停" not in MOMENTUM


def test_momentum_dashboard_reads_local_projection_and_acknowledges_alerts():
    assert 'fetch("/api/dashboard/momentum", { cache: "no-store" })' in MOMENTUM
    assert 'new WebSocket(momentumWebSocketUrl(stream))' in MOMENTUM
    assert 'message.type === "delta"' in MOMENTUM
    assert 'message.type === "resync_required"' in MOMENTUM
    assert "WebSocket 即時推送" in MOMENTUM
    assert "HTTP 輪詢備援" in MOMENTUM
    assert "/api/dashboard/momentum/alerts/${encodeURIComponent(alertId)}" in MOMENTUM
    assert 'method: "POST"' in MOMENTUM
    assert "function renderMomentum(momentum)" in MOMENTUM
    assert "function pollMomentumProjection()" in MOMENTUM
    assert "if (momentumSocketIsOpen()) return;" in MOMENTUM
    assert "state.momentumRenderKey !== momentum.summary?.projection_digest" in MOMENTUM


def test_momentum_dashboard_does_not_compute_signal_or_stage_in_browser():
    assert "momentum_acceleration_confirmed" not in MOMENTUM
    assert "volume_acceleration_2m /" not in MOMENTUM
    assert "LIMIT_UP_MOMENTUM =" not in MOMENTUM
    assert "signal.evidence_score" in MOMENTUM
    assert "detail.observed_value" in MOMENTUM
    assert "item.current_stage_label" in MOMENTUM


def test_momentum_dashboard_has_narrow_layout_rules():
    assert ".momentum-layout { grid-template-columns: 1fr; }" in CSS
    assert ".momentum-candidate-table" in CSS


def test_momentum_rows_open_an_accessible_detail_dialog():
    assert 'id="momentum-detail-dialog"' in HTML
    assert 'aria-labelledby="momentum-detail-heading"' in HTML
    assert 'id="momentum-detail-close"' in HTML
    assert 'data-momentum-symbol="${escapeHtml(item.symbol)}"' in MOMENTUM
    assert 'class="momentum-row-trigger"' in MOMENTUM
    assert "function openMomentumDialog(symbol)" in MOMENTUM
    assert "function closeMomentumDialog" in MOMENTUM
    assert "momentumDetailDialog.showModal()" in MOMENTUM
    assert "state.momentumDialogSymbol" in MOMENTUM


def test_momentum_detail_opens_existing_local_paper_order_ticket():
    assert 'id="momentum-detail-order"' in HTML
    assert "function openOrderTicketFromMomentum()" in MOMENTUM
    assert 'intradayPrice?.status === "VALID"' in MOMENTUM
    assert "services.openOrderTicket(item.symbol, price)" in MOMENTUM
    assert 'momentumDetailOrder.addEventListener("click", openOrderTicketFromMomentum)' in APP
    assert ".momentum-detail-order" in CSS


def test_momentum_dialog_uses_server_projection_and_survives_polling():
    assert "function renderMomentumDialog" in MOMENTUM
    assert "function syncMomentumDialog" in MOMENTUM
    assert "item.intraday" in MOMENTUM
    assert "signal.details" in MOMENTUM
    assert "detail.status" in MOMENTUM
    assert "detail.source_as_of" in MOMENTUM
    assert "momentumDetailBody.scrollTop" in MOMENTUM
    assert "syncMomentumDialog(momentum)" in MOMENTUM
    assert "focusedMomentumSymbol" in MOMENTUM
    assert "/api/dashboard/momentum/${encodeURIComponent" not in MOMENTUM
