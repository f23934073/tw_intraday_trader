from pathlib import Path


STATIC = Path(__file__).parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
SIMULATION = (STATIC / "js" / "workspaces" / "simulation.js").read_text(
    encoding="utf-8"
)
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")


def test_no_overnight_card_is_explicitly_non_enforcing_and_accessible() -> None:
    assert "收盤風控" in HTML
    assert 'class="summary-card no-overnight-card"' in HTML
    assert 'role="status"' in HTML
    assert 'aria-atomic="true"' in HTML
    assert "renderNoOvernight(snapshot.no_overnight)" in APP
    assert "僅觀察" in SIMULATION
    assert "未啟用" in SIMULATION
    assert "不阻擋、不取消、不送單" in SIMULATION
    assert 'mode === "ENFORCING"' in SIMULATION
    assert "禁止新當沖、取消未成交當沖買單" in SIMULATION
    assert 'holding_horizon: orderSide.value === "BUY" ? "INTRADAY"' in SIMULATION
    assert ".no-overnight-card .summary-card-note" in CSS


def test_no_overnight_breach_ui_exposes_latest_resolved_ack_only() -> None:
    assert 'id="overview-no-overnight-breach"' in HTML
    assert 'id="overview-no-overnight-breach-meta"' in HTML
    assert 'id="overview-no-overnight-ack"' in HTML
    assert 'type="button"' in HTML
    assert 'aria-describedby="overview-no-overnight-breach-meta"' in HTML
    assert "breach?.resolved && !breach?.acknowledged" in SIMULATION
    assert "breach.breach_revision" in SIMULATION
    assert "breach.reconciliation_digest" in SIMULATION
    assert "latest revision" in SIMULATION
    assert "下一個已覆核交易日" in SIMULATION
    assert "歷史紀錄仍會保留" in SIMULATION
    assert "data-clear-breach" not in SIMULATION
    assert "/clear" not in SIMULATION


def test_no_overnight_ack_uses_local_mutation_security_and_refreshes_status() -> None:
    assert (
        "/api/simulation/no-overnight/breaches/${encodeURIComponent(breach.breach_id)}/acknowledge"
        in SIMULATION
    )
    assert "pendingBreachAckTarget !== target" in SIMULATION
    assert 'pendingBreachAckKey = newIdempotencyKey("breach-ack")' in SIMULATION
    assert "|| !refreshed.resolved" in SIMULATION
    assert '"Idempotency-Key": pendingBreachAckKey' in SIMULATION
    assert '"X-Strategy-CSRF": localMutationCsrf' in SIMULATION
    assert 'actor_id: "local-operator"' in SIMULATION
    assert 'fetch("/api/simulation/no-overnight", { cache: "no-store" })' in SIMULATION
    assert ".no-overnight-breach-ack:focus-visible" in CSS
    assert ".no-overnight-breach-ack:disabled" in CSS
