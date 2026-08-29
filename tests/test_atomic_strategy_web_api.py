from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import dashboard.server as server
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.repository import BacktestIdempotencyConflict
from strategy_catalog.drafts import StrategyDraft
from strategy_catalog.sets import ExactStrategySetSnapshot


class _AtomicServiceProbe:
    def __init__(self) -> None:
        self.template_items = AtomicStrategyRegistry().templates()
        self.created: list[dict[str, object]] = []
        self.audit_events: list[dict[str, object]] = []
        self.strategy_sets: list[ExactStrategySetSnapshot] = []
        self.archived_strategy_set_ids: set[str] = set()

    def templates(self):
        return self.template_items

    def template(self, strategy_id: str):
        return next(item for item in self.template_items if item.strategy_id == strategy_id)

    def list_drafts(self, strategy_id=None):
        return ()

    def list_versions(self, strategy_id=None):
        return ()

    def list_strategy_sets(self):
        return tuple(
            item
            for item in self.strategy_sets
            if item.strategy_set_id not in self.archived_strategy_set_ids
        )

    def save_strategy_set(self, snapshot, **kwargs):
        if any(
            item.strategy_set_version_id == snapshot.strategy_set_version_id
            for item in self.strategy_sets
        ):
            return False
        self.strategy_sets.append(snapshot)
        self.created.append({"strategy_set": snapshot, **kwargs})
        return True

    def get_strategy_set(self, strategy_set_version_id):
        return next(
            item
            for item in self.strategy_sets
            if item.strategy_set_version_id == strategy_set_version_id
        )

    def is_strategy_set_archived(self, strategy_set_version_id):
        return (
            self.get_strategy_set(strategy_set_version_id).strategy_set_id
            in self.archived_strategy_set_ids
        )

    def archive_strategy_set(self, strategy_set_version_id, **kwargs):
        snapshot = self.get_strategy_set(strategy_set_version_id)
        if snapshot.strategy_set_id in self.archived_strategy_set_ids:
            return False
        self.archived_strategy_set_ids.add(snapshot.strategy_set_id)
        self.created.append({"archived_strategy_set": snapshot, **kwargs})
        return True

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
        return (
            {"run_id": "run-atomic-web-1", "status": "QUEUED", "config_digest": "run-digest"},
            False,
        )

    def atomic_backtest_dataset_status(self, **kwargs):
        self.calls.append({"action": "dataset-status", **kwargs})
        return {
            "available": True,
            "resolution_mode": "DEFAULT_BINDING",
            "binding_name": "ATOMIC_BACKTEST_DEFAULT",
            "binding_revision": 4,
            "dataset_id": "dataset-finmind",
            "dataset_digest": "a" * 64,
            "source": "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
            "start_date": "2023-08-21",
            "end_date": "2026-08-21",
            "symbol_count": 174,
            "bar_count": 28_325_340,
            "capabilities": ["OHLCV", "KBAR_1M"],
            "amount_kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
            "amount_contract_digest": "b" * 64,
            "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
            "research_eligible": False,
            "issues": ["AMOUNT_DERIVED_PROXY"],
            "formal_research_readiness": {
                "ready": False,
                "status": "DATA_NOT_READY",
                "reason_codes": ["CURRENT_SNAPSHOT_UNIVERSE"],
                "research_truth_snapshot_digest": "c" * 64,
            },
            "readiness": {
                "platform": {"ready": True, "status": "PLATFORM_READY"},
                "data": {"ready": False, "status": "DATA_NOT_READY"},
                "strategy": {
                    "ready": False,
                    "status": "NO_QUALIFYING_STRATEGY",
                    "qualification_ids": [],
                    "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
                },
            },
        }

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
                "display_status": "NO_QUALIFYING_STRATEGY",
                "strategy_readiness": {
                    "ready": False,
                    "status": "NO_QUALIFYING_STRATEGY",
                    "effect": "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION",
                },
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
        "rsi_oversold_entry",
        "bollinger_lower_reentry_entry",
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

    binding = client.get(
        "/api/backtests/atomic-dataset",
        params={"strategy_set_version_id": "strategy-set-version-exact-1"},
    )
    assert binding.status_code == 200
    assert binding.json()["binding"]["binding_revision"] == 4
    assert binding.json()["binding"]["readiness"]["platform"]["status"] == "PLATFORM_READY"
    assert binding.json()["binding"]["readiness"]["data"]["status"] == "DATA_NOT_READY"
    assert binding.json()["binding"]["readiness"]["strategy"]["status"] == "NO_QUALIFYING_STRATEGY"

    launched = client.post(
        "/api/backtests/runs/atomic",
        headers={
            "Idempotency-Key": "atomic-backtest-request-1",
            "X-Strategy-CSRF": token,
        },
        json={
            "strategy_set_version_id": "strategy-set-version-exact-1",
            "expected_binding_revision": 4,
            "expected_dataset_digest": "a" * 64,
        },
    )
    assert launched.status_code == 201
    assert launched.json()["run"]["run_id"] == "run-atomic-web-1"
    create_call = next(item for item in backtest.calls if "idempotency_key" in item)
    assert create_call["strategy_set_version_id"] == "strategy-set-version-exact-1"
    assert "dataset_id" not in create_call
    assert "entry_strategy_ids" not in create_call
    assert create_call["expected_binding_revision"] == 4
    assert create_call["expected_dataset_digest"] == "a" * 64
    assert atomic.audit_events[-1]["action"] == "ATOMIC_BACKTEST_RUN_CREATE"

    conflict = client.post(
        "/api/backtests/runs/atomic",
        headers={"Idempotency-Key": "atomic-conflict", "X-Strategy-CSRF": token},
        json={
            "strategy_set_version_id": "set-conflict",
            "expected_binding_revision": 4,
            "expected_dataset_digest": "a" * 64,
        },
    )
    assert conflict.status_code == 409
    assert atomic.audit_events[-1]["outcome"] == "CONFLICT"

    diff = client.get("/api/strategy-versions/version-a/diff/version-b")
    assert diff.status_code == 200
    assert diff.json()["diff"]["changes"][0]["parameter"] == "minimum_distance_bps"


def test_strategy_set_revision_and_archive_preserve_exact_history(monkeypatch) -> None:
    atomic = _AtomicServiceProbe()
    monkeypatch.setattr(server, "get_atomic_strategy_service", lambda: atomic)
    client = TestClient(server.app)
    token = client.get("/api/atomic-strategies/capabilities").json()["csrf_token"]
    headers = {"Idempotency-Key": "strategy-set-create-web-1", "X-Strategy-CSRF": token}
    payload = {
        "display_name_zh_tw": "精確版本組合",
        "stage": "ENTRY",
        "policy": "AT_LEAST_N",
        "minimum_trigger_count": 1,
        "members": [
            {
                "strategy_version_id": "version-web-1",
                "strategy_id": "above_vwap_entry",
                "configuration_digest": "configuration-digest",
                "implementation_digest": "implementation-digest",
                "member_order": 0,
                "attribution_priority": 0,
            }
        ],
        "actor_id": "reviewer",
        "change_note": "建立初版",
    }

    created = client.post("/api/strategy-sets", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    base = created.json()["strategy_set"]

    no_csrf = client.post(
        f"/api/strategy-sets/{base['strategy_set_version_id']}/revisions",
        headers={"Idempotency-Key": "strategy-set-revise-web-1"},
        json=payload | {"change_note": "調整顯示名稱"},
    )
    assert no_csrf.status_code == 403

    revised = client.post(
        f"/api/strategy-sets/{base['strategy_set_version_id']}/revisions",
        headers={"Idempotency-Key": "strategy-set-revise-web-1", "X-Strategy-CSRF": token},
        json=payload | {"display_name_zh_tw": "精確版本組合新版", "change_note": "調整顯示名稱"},
    )
    assert revised.status_code == 201, revised.text
    revision = revised.json()["strategy_set"]
    assert revision["strategy_set_id"] == base["strategy_set_id"]
    assert revision["version_number"] == 2
    assert client.get(f"/api/strategy-sets/{base['strategy_set_version_id']}").status_code == 200

    archived = client.request(
        "DELETE",
        f"/api/strategy-sets/{revision['strategy_set_version_id']}",
        headers={"Idempotency-Key": "strategy-set-archive-web-1", "X-Strategy-CSRF": token},
        json={"actor_id": "reviewer", "change_note": "不再提供新回測使用"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    assert client.get("/api/strategy-sets").json()["strategy_sets"] == []
    assert client.get(f"/api/strategy-sets/{base['strategy_set_version_id']}").status_code == 200


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
        },
    )
    assert unknown.status_code == 422

    for path, body in (
        ("/api/backtests/runs/run-1/cancel", {"idempotency_key": "cancel-1"}),
        ("/api/backtests/runs/run-1/retry", {"idempotency_key": "retry-1"}),
        (
            "/api/backtests/runs/run-1/clone",
            {"idempotency_key": "clone-1", "change_note": "test", "overrides": {}},
        ),
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
        json=payload | {"protocol": payload["protocol"] | {"policy": {"minimum_oos_trades": 1}}},
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
    assert created.json()["qualification"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert created.json()["qualification"]["display_status"] == "NO_QUALIFYING_STRATEGY"
    call = backtest.calls[-1]
    assert call["action"] == "qualification"
    assert call["hypothesis_id"] == "v2-beats-v1"
    assert call["protocol"]["primary_window"]["oos_start"] == "2026-01-01"
    assert atomic.audit_events[-1]["action"] == "BACKTEST_QUALIFICATION_CREATE"
    assert atomic.audit_events[-1]["after_digest"] == "qualification-evidence-digest"
