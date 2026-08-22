from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import dashboard.server as server
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.repository import BacktestIdempotencyConflict
from strategy_catalog.drafts import StrategyDraft


class _AtomicServiceProbe:
    def __init__(self) -> None:
        self.template_items = AtomicStrategyRegistry().templates()
        self.created: list[dict[str, object]] = []
        self.audit_events: list[dict[str, object]] = []

    def templates(self):
        return self.template_items

    def template(self, strategy_id: str):
        return next(item for item in self.template_items if item.strategy_id == strategy_id)

    def list_drafts(self, strategy_id=None):
        return ()

    def list_versions(self, strategy_id=None):
        return ()

    def list_strategy_sets(self):
        return ()

    def diff_versions(self, left_id, right_id):
        return {
            "left_strategy_version_id": left_id,
            "right_strategy_version_id": right_id,
            "same_strategy": True,
            "changes": [{"parameter": "minimum_distance_bps", "left": "10", "right": "20"}],
        }

    def create_draft(self, strategy_id, parameters, **kwargs):
        self.created.append({"strategy_id": strategy_id, "parameters": parameters, **kwargs})
        now = datetime(2026, 8, 21, tzinfo=timezone.utc)
        template = self.template(strategy_id)
        canonical = template.validate_parameters(parameters)
        return StrategyDraft(
            draft_id="draft-web-1",
            strategy_id=strategy_id,
            revision=1,
            parameters=canonical,
            parameters_digest="parameters-digest",
            change_note=str(kwargs.get("change_note", "")),
            created_by=str(kwargs["actor_id"]),
            updated_by=str(kwargs["actor_id"]),
            created_at=now,
            updated_at=now,
        )

    def record_audit_event(self, **event):
        self.audit_events.append(event)
        return event

    def list_audit_events(self, limit=100):
        return tuple(self.audit_events[:limit])


class _BacktestProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_atomic_run(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["idempotency_key"] == "atomic-conflict":
            raise BacktestIdempotencyConflict("same key, different digest")
        return ({"run_id": "run-atomic-web-1", "status": "QUEUED", "config_digest": "run-digest"}, False)

    def get_run(self, run_id):
        return {
            "run_id": run_id,
            "status": "FAILED",
            "config_digest": "run-digest",
            "config": {"atomic_strategy_run_snapshot": {"snapshot_digest": "atomic"}},
        }

    def cancel_run(self, run_id):
        self.calls.append({"action": "cancel", "run_id": run_id})
        return self.get_run(run_id) | {"status": "CANCELLING"}

    def cancel_atomic_run(self, run_id, **kwargs):
        self.calls.append({"action": "cancel", "run_id": run_id, **kwargs})
        return (self.get_run(run_id) | {"status": "CANCELLING"}, False)

    def retry_run(self, run_id, *, idempotency_key):
        self.calls.append({"action": "retry", "run_id": run_id, "idempotency_key": idempotency_key})
        return (self.get_run("run-retry-1"), False)

    def clone_run(self, run_id, **kwargs):
        self.calls.append({"action": "clone", "run_id": run_id, **kwargs})
        return (self.get_run("run-clone-1"), False)

    def qualify_runs(self, **kwargs):
        self.calls.append({"action": "qualification", **kwargs})
        return (
            {
                "qualification_id": "qualification-web-1",
                "baseline_run_id": kwargs["baseline_run_id"],
                "challenger_run_id": kwargs["challenger_run_id"],
                "verdict": "INSUFFICIENT_EVIDENCE",
                "evidence_digest": "qualification-evidence-digest",
                "evidence": {"verdict": "INSUFFICIENT_EVIDENCE", "reasons": []},
            },
            False,
        )

    def list_qualifications(self, *, limit=100):
        return []

    def get_qualification(self, qualification_id):
        return {"qualification_id": qualification_id}


def test_atomic_strategy_web_routes_require_csrf_and_use_exact_set(monkeypatch) -> None:
    atomic = _AtomicServiceProbe()
    backtest = _BacktestProbe()
    monkeypatch.setattr(server, "get_atomic_strategy_service", lambda: atomic)
    monkeypatch.setattr(server, "get_backtest_service", lambda: backtest)
    client = TestClient(server.app)

    capabilities = client.get("/api/atomic-strategies/capabilities").json()
    assert capabilities["available"] is True
    token = capabilities["csrf_token"]

    templates = client.get("/api/strategy-templates").json()["templates"]
    assert {item["strategy_id"] for item in templates} == {
        "above_vwap_entry",
        "breakout_previous_high_entry",
        "rolling_return_entry",
        "volume_acceleration_entry",
        "opening_range_breakout_entry",
        "ema_crossover_entry",
    }
    assert templates[0]["parameter_schema"]["fields"]
    assert "runtime_bindings" in templates[0]
    rolling_schema = client.get(
        "/api/strategy-templates/rolling_return_entry/parameter-schema"
    ).json()["parameter_schema"]
    assert rolling_schema["fields"]["window_minutes"]["default"] == 2
    assert rolling_schema["fields"]["minimum_return_pct"]["default"] == "1.5"

    rejected = client.post(
        "/api/strategy-versions/drafts",
        headers={"Idempotency-Key": "draft-web-request-1"},
        json={"strategy_id": "above_vwap_entry", "parameters": {}},
    )
    assert rejected.status_code == 403

    created = client.post(
        "/api/strategy-versions/drafts",
        headers={
            "Idempotency-Key": "draft-web-request-1",
            "X-Strategy-CSRF": token,
        },
        json={"strategy_id": "above_vwap_entry", "parameters": {}},
    )
    assert created.status_code == 201
    assert created.json()["draft"]["draft_id"] == "draft-web-1"
    assert atomic.created[0]["idempotency_key"] == "draft-web-request-1"

    launched = client.post(
        "/api/backtests/runs/atomic",
        headers={
            "Idempotency-Key": "atomic-backtest-request-1",
            "X-Strategy-CSRF": token,
        },
        json={
            "dataset_id": "dataset-ready-1",
            "strategy_set_version_id": "strategy-set-version-exact-1",
        },
    )
    assert launched.status_code == 201
    assert launched.json()["run"]["run_id"] == "run-atomic-web-1"
    assert backtest.calls[0]["strategy_set_version_id"] == "strategy-set-version-exact-1"
    assert "entry_strategy_ids" not in backtest.calls[0]
    assert atomic.audit_events[-1]["action"] == "ATOMIC_BACKTEST_RUN_CREATE"

    conflict = client.post(
        "/api/backtests/runs/atomic",
        headers={"Idempotency-Key": "atomic-conflict", "X-Strategy-CSRF": token},
        json={"dataset_id": "dataset-ready-1", "strategy_set_version_id": "set-conflict"},
    )
    assert conflict.status_code == 409
    assert atomic.audit_events[-1]["outcome"] == "CONFLICT"

    diff = client.get("/api/strategy-versions/version-a/diff/version-b")
    assert diff.status_code == 200
    assert diff.json()["diff"]["changes"][0]["parameter"] == "minimum_distance_bps"


def test_atomic_requests_forbid_unknown_fields_and_protect_run_mutations(monkeypatch) -> None:
    atomic = _AtomicServiceProbe()
    backtest = _BacktestProbe()
    monkeypatch.setattr(server, "get_atomic_strategy_service", lambda: atomic)
    monkeypatch.setattr(server, "get_backtest_service", lambda: backtest)
    client = TestClient(server.app)
    token = client.get("/api/atomic-strategies/capabilities").json()["csrf_token"]

    unknown = client.post(
        "/api/backtests/runs/atomic",
        headers={"Idempotency-Key": "strict-1", "X-Strategy-CSRF": token},
        json={
            "dataset_id": "dataset-1",
            "strategy_set_version_id": "set-1",
            "entry_strategy_ids": ["must-not-be-ignored"],
        },
    )
    assert unknown.status_code == 422

    for path, body in (
        ("/api/backtests/runs/run-1/cancel", {"idempotency_key": "cancel-1"}),
        ("/api/backtests/runs/run-1/retry", {"idempotency_key": "retry-1"}),
        ("/api/backtests/runs/run-1/clone", {"idempotency_key": "clone-1", "change_note": "test", "overrides": {}}),
    ):
        hostile = client.post(path, headers={"Origin": "https://evil.example"}, json=body)
        assert hostile.status_code == 403, (path, hostile.text)

    remote_client = TestClient(server.app, client=("198.51.100.10", 42000))
    remote = remote_client.post(
        "/api/backtests/runs/run-1/retry",
        headers={"X-Strategy-CSRF": token, "Origin": "http://testserver"},
        json={"idempotency_key": "remote-retry-1"},
    )
    assert remote.status_code == 403

    no_csrf = client.post(
        "/api/backtests/runs/run-1/clone",
        headers={"Origin": "http://testserver"},
        json={"idempotency_key": "no-csrf-clone", "change_note": "test", "overrides": {}},
    )
    assert no_csrf.status_code == 403

    accepted = client.post(
        "/api/backtests/runs/run-1/cancel",
        headers={"X-Strategy-CSRF": token},
        json={"idempotency_key": "cancel-ok", "actor_id": "reviewer"},
    )
    assert accepted.status_code == 200
    assert backtest.calls[-1]["actor_id"] == "reviewer"

    accepted_retry = client.post(
        "/api/backtests/runs/run-1/retry",
        headers={"X-Strategy-CSRF": token},
        json={"idempotency_key": "retry-ok", "actor_id": "reviewer"},
    )
    assert accepted_retry.status_code == 201
    assert atomic.audit_events[-1]["actor_id"] == "reviewer"

    audit = client.get("/api/strategy-audit-events?limit=10")
    assert audit.status_code == 200
    assert audit.json()["audit_events"][-1]["action"] == "ATOMIC_BACKTEST_RUN_RETRY"


def test_atomic_http_boundary_rejects_public_host_proxy_and_origin_mismatch(
    monkeypatch,
) -> None:
    atomic = _AtomicServiceProbe()
    backtest = _BacktestProbe()
    monkeypatch.setattr(server, "get_atomic_strategy_service", lambda: atomic)
    monkeypatch.setattr(server, "get_backtest_service", lambda: backtest)
    client = TestClient(server.app)

    public_capabilities = client.get(
        "/api/atomic-strategies/capabilities",
        headers={"Host": "public.example"},
    )
    assert public_capabilities.status_code == 403

    local_capabilities = client.get(
        "/api/atomic-strategies/capabilities",
        headers={"Host": "127.0.0.1:8123"},
    )
    assert local_capabilities.status_code == 200
    token = local_capabilities.json()["csrf_token"]

    public_retry = client.post(
        "/api/backtests/runs/run-1/retry",
        headers={
            "Host": "public.example",
            "X-Strategy-CSRF": token,
        },
        json={"idempotency_key": "public-host-retry"},
    )
    assert public_retry.status_code == 403

    proxied_retry = client.post(
        "/api/backtests/runs/run-1/retry",
        headers={
            "Host": "127.0.0.1:8123",
            "X-Forwarded-Host": "public.example",
            "X-Strategy-CSRF": token,
        },
        json={"idempotency_key": "proxied-host-retry"},
    )
    assert proxied_retry.status_code == 403

    for origin in (
        "https://127.0.0.1:8123",
        "http://127.0.0.1:4443",
    ):
        rejected = client.post(
            "/api/backtests/runs/run-1/retry",
            headers={
                "Host": "127.0.0.1:8123",
                "Origin": origin,
                "X-Strategy-CSRF": token,
            },
            json={"idempotency_key": f"origin-mismatch-{origin}"},
        )
        assert rejected.status_code == 403, (origin, rejected.text)

    accepted = client.post(
        "/api/backtests/runs/run-1/retry",
        headers={
            "Host": "127.0.0.1:8123",
            "Origin": "http://127.0.0.1:8123",
            "X-Strategy-CSRF": token,
        },
        json={"idempotency_key": "same-origin-retry"},
    )
    assert accepted.status_code == 201


def test_backtest_qualification_is_strict_csrf_protected_and_audited(monkeypatch) -> None:
    atomic = _AtomicServiceProbe()
    backtest = _BacktestProbe()
    monkeypatch.setattr(server, "get_atomic_strategy_service", lambda: atomic)
    monkeypatch.setattr(server, "get_backtest_service", lambda: backtest)
    client = TestClient(server.app)
    token = client.get("/api/atomic-strategies/capabilities").json()["csrf_token"]
    payload = {
        "baseline_run_id": "run-baseline",
        "challenger_run_id": "run-challenger",
        "hypothesis_id": "v2-beats-v1",
        "protocol": {
            "contract_version": "backtest-qualification-request-v2",
            "primary_window": {
                "label": "primary",
                "train_start": "2025-01-01",
                "train_end": "2025-06-30",
                "validation_start": "2025-07-01",
                "validation_end": "2025-09-30",
                "oos_start": "2026-01-01",
                "oos_end": "2026-03-31",
            },
            "walk_forward_windows": [],
        },
        "actor_id": "reviewer",
        "change_note": "固定 OOS qualification",
    }

    no_csrf = client.post(
        "/api/backtests/qualifications",
        headers={"Idempotency-Key": "qualification-web-request-1"},
        json=payload,
    )
    assert no_csrf.status_code == 403

    unknown = client.post(
        "/api/backtests/qualifications",
        headers={
            "Idempotency-Key": "qualification-web-request-1",
            "X-Strategy-CSRF": token,
        },
        json=payload | {"import_path": "must-not-be-accepted"},
    )
    assert unknown.status_code == 422

    client_owned_policy = client.post(
        "/api/backtests/qualifications",
        headers={
            "Idempotency-Key": "qualification-web-request-policy",
            "X-Strategy-CSRF": token,
        },
        json=payload
        | {
            "protocol": payload["protocol"]
            | {"policy": {"minimum_oos_trades": 1}}
        },
    )
    assert client_owned_policy.status_code == 422

    created = client.post(
        "/api/backtests/qualifications",
        headers={
            "Idempotency-Key": "qualification-web-request-1",
            "X-Strategy-CSRF": token,
        },
        json=payload,
    )
    assert created.status_code == 201
    assert created.json()["qualification"]["qualification_id"] == "qualification-web-1"
    call = backtest.calls[-1]
    assert call["action"] == "qualification"
    assert call["hypothesis_id"] == "v2-beats-v1"
    assert call["protocol"]["primary_window"]["oos_start"] == "2026-01-01"
    assert atomic.audit_events[-1]["action"] == "BACKTEST_QUALIFICATION_CREATE"
    assert atomic.audit_events[-1]["after_digest"] == "qualification-evidence-digest"
