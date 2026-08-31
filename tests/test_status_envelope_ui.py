"""Executed browser contracts for the shared StatusEnvelope store and renderer."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from dashboard import status_envelope as se
from tests.test_status_envelope import (
    FORMAL_17,
    NOW,
    comparison,
    controller,
    cost_snapshot,
    dataset_binding,
    kill,
    no_overnight,
    readiness,
    run,
    session,
)

STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
APP = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
RENDERER_PATH = STATIC / "js" / "status_envelope.js"
RENDERER = RENDERER_PATH.read_text(encoding="utf-8")
SIMULATION_PATH = STATIC / "js" / "workspaces" / "simulation.js"
WORKSPACE_PATHS = [
    STATIC / "js" / "workspaces" / name
    for name in ("candidates.js", "simulation.js", "backtest.js")
]
WORKSPACES = "\n".join(path.read_text(encoding="utf-8") for path in WORKSPACE_PATHS)


def _status_set(
    *,
    strategy_set_version_id: str | None = None,
    formal_codes: list[str] | None = None,
    kill_state: str = "DISENGAGED",
    quote_health: str = "HEALTHY",
    no_overnight_state: str = "NORMAL",
    local_state: str = "STOPPED",
) -> dict[str, Any]:
    selected = (
        dataset_binding(list(formal_codes or [])) if strategy_set_version_id is not None else None
    )
    ready = readiness(data=not formal_codes)
    builders = {
        "backtest_platform": lambda: se.backtest_platform_envelope(ready, now=NOW),
        "formal_dataset": lambda: se.formal_dataset_envelope(
            ready,
            now=NOW,
            selected_dataset=selected,
            strategy_set_version_id=strategy_set_version_id,
        ),
        "strategy_qualification": lambda: se.strategy_qualification_envelope(ready, now=NOW),
        "local_paper_runtime": lambda: se.local_paper_runtime_envelope(
            controller(local_state), now=NOW
        ),
        "quote_ingress": lambda: se.quote_ingress_envelope(session(quote_health), now=NOW),
        "kill_switch": lambda: se.kill_switch_envelope(kill(kill_state), now=NOW),
        "no_overnight": lambda: se.no_overnight_envelope(no_overnight(no_overnight_state), now=NOW),
        "market_shadow": lambda: se.market_shadow_envelope(now=NOW),
    }
    return se.build_status_envelope_set(builders, now=NOW)


def _entity_set(builders: dict[str, Any], subjects: tuple[str, ...]) -> dict[str, Any]:
    return se.build_status_envelope_set(builders, now=NOW, subjects=subjects)


def _node_payloads() -> dict[str, Any]:
    generic = _status_set()
    set_a = _status_set(strategy_set_version_id="set-A")
    set_b = _status_set(strategy_set_version_id="set-B", formal_codes=list(FORMAL_17))
    critical = _status_set(
        strategy_set_version_id="set-B",
        formal_codes=list(FORMAL_17),
        kill_state="ENGAGED",
    )
    recovered = _status_set(strategy_set_version_id="set-B", formal_codes=list(FORMAL_17))
    running_local = _status_set(
        strategy_set_version_id="set-B",
        formal_codes=list(FORMAL_17),
        local_state="RUNNING",
    )
    multiple = _status_set(
        strategy_set_version_id="set-B",
        formal_codes=list(FORMAL_17),
        quote_health="BLOCKED",
        no_overnight_state="OVERNIGHT_BREACH",
    )

    def run_set(state: str) -> dict[str, Any]:
        raw = run(state, run_id="run-1")
        return _entity_set(
            {
                "backtest_run": lambda: se.backtest_run_envelope(raw, now=NOW),
                "cost_snapshot": lambda: se.cost_snapshot_envelope(cost_snapshot(), now=NOW),
            },
            ("backtest_run", "cost_snapshot"),
        )

    comparisons: dict[str, Any] = {}
    for comparison_id, verdict, diff in (
        ("cmp-not", "NOT_COMPARABLE", [{"field": "dataset_digest"}]),
        ("cmp-no-clear", "NO_CLEAR_EVIDENCE", []),
        ("cmp-likely", "LIKELY_IMPROVED", []),
        ("cmp-late-a", "NO_CLEAR_EVIDENCE", []),
        ("cmp-late-b", "LIKELY_IMPROVED", []),
    ):
        raw = {
            **comparison(verdict, diff),
            "comparison_id": comparison_id,
        }
        comparisons[comparison_id] = _entity_set(
            {"backtest_comparison": lambda raw=raw: se.backtest_comparison_envelope(raw, now=NOW)},
            ("backtest_comparison",),
        )

    bad_digest = deepcopy(set_b)
    bad_digest["envelopes"]["formal_dataset"]["digest"] = "0" * 64
    return {
        "generic": generic,
        "setA": set_a,
        "setB": set_b,
        "badDigest": bad_digest,
        "critical": critical,
        "recovered": recovered,
        "runningLocal": running_local,
        "multiple": multiple,
        "runs": {
            "queued": run_set("QUEUED"),
            "running": run_set("RUNNING"),
            "completed": run_set("COMPLETED"),
            "failed": run_set("FAILED"),
        },
        "comparisons": comparisons,
    }


def _canonical_vectors() -> list[dict[str, str]]:
    values = [
        {
            "z": [None, True, 9_007_199_254_740_991, "中文", "emoji 😀"],
            "a": {"nested_b": 'quote"slash\\', "nested_a": False},
        },
        {"array": ["1", "0", "0.0000001", "42"], "null_value": None},
    ]
    result = []
    for value in values:
        canonical = se.canonical_json(value)
        result.append(
            {
                "httpJson": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                "canonical": canonical,
                "digest": hashlib.sha256(canonical.encode()).hexdigest(),
            }
        )
    return result


def _run_node_contract() -> subprocess.CompletedProcess[str]:
    template = r"""
import { createStatusEnvelopeWorkspace } from __MODULE__;

const payloads = __PAYLOADS__;
const vectors = __VECTORS__;
function assert(condition, message) { if (!condition) throw new Error(message); }

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  toggle(value, force) {
    const next = force === undefined ? !this.values.has(value) : Boolean(force);
    if (next) this.values.add(value); else this.values.delete(value);
    return next;
  }
  contains(value) { return this.values.has(value); }
}
class Element {
  constructor(id = "") {
    this.id = id; this.innerHTML = ""; this.textContent = ""; this.hidden = false;
    this.dataset = {}; this.className = ""; this.classList = new ClassList();
    this.attributes = new Map(); this.dateTime = "";
  }
  setAttribute(key, value) { this.attributes.set(key, String(value)); }
  getAttribute(key) { return this.attributes.get(key) || null; }
  hasAttribute(key) { return this.attributes.has(key); }
  removeAttribute(key) { this.attributes.delete(key); }
  querySelectorAll() { return []; }
}
const ids = [
  "status-envelope-panel", "status-envelope-topbar", "status-envelope-last-valid",
  "mobile-read-only-banner", "mobile-read-only-reason", "status-envelope-alert",
  "status-envelope-announcement", "status-envelope-matrix", "status-envelope-cards"
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
const media = { matches: true, addEventListener() {} };
let fetchImpl = async () => { throw new Error("fetch handler missing"); };
const urls = [];
globalThis.HTMLElement = Element;
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.matchMedia = () => media;
globalThis.document = {
  visibilityState: "visible", body: new Element("body"), documentElement: new Element("html"),
  getElementById: (id) => elements[id] || null,
  querySelectorAll: () => []
};
globalThis.fetch = (resource, options) => fetchImpl(resource, options);
const response = (payload, ok = true, status = 200) => ({
  ok, status, json: async () => structuredClone(payload)
});
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[character]);
const workspace = createStatusEnvelopeWorkspace({ escapeHtml });

assert(!elements["mobile-read-only-banner"].hidden, "mobile first-load state hid reason");
assert(elements["mobile-read-only-reason"].textContent.includes("手機仍維持唯讀"), "mobile first-load fallback reason missing");
let firstLoadMutationBlocked = false;
try { await fetch("/first-load-mutation", { method: "POST" }); } catch (error) { firstLoadMutationBlocked = error.name === "NotAllowedError"; }
assert(firstLoadMutationBlocked, "mobile first-load mutation reached transport");
media.matches = false;
workspace.applyMobileReadOnlyPolicy();

fetchImpl = async (url) => { urls.push(String(url)); return response(payloads.generic); };
await workspace.loadStatusEnvelopes(null);
assert(!workspace.isActionAllowed("formal_dataset", "create_formal_backtest"), "generic Formal scope authorized create");

let resolveA;
let resolveB;
const promiseA = new Promise((resolve) => { resolveA = resolve; });
const promiseB = new Promise((resolve) => { resolveB = resolve; });
fetchImpl = async (url) => {
  urls.push(String(url));
  if (String(url).includes("set-A")) return promiseA;
  if (String(url).includes("set-B")) return promiseB;
  throw new Error(`unexpected scope URL ${url}`);
};
const loadA = workspace.setStrategySetVersionId("set-A");
const loadB = workspace.setStrategySetVersionId("set-B");
resolveB(response(payloads.setB));
await loadB;
resolveA(response(payloads.setA));
await loadA;
assert(workspace.getCurrentStatusEnvelope("formal_dataset").identity.strategy_set_version_id === "set-B", "late A replaced B");
assert(!workspace.isActionAllowed("formal_dataset", "create_formal_backtest"), "S06 raw-ready fallback authorized create");
const formalMarkup = workspace.renderWorkspaceEnvelope("formal_dataset");
for (const code of payloads.setB.envelopes.formal_dataset.reason_codes) assert(formalMarkup.includes(code), `missing S06 code ${code}`);
fetchImpl = async (url) => { urls.push(String(url)); return response(payloads.setB); };
workspace.pollStatusEnvelopes();
await new Promise((resolve) => setImmediate(resolve));
assert(urls.at(-1).includes("strategy_set_version_id=set-B"), "visible poll lost B scope");

workspace.renderStatusEnvelopes(payloads.multiple);
const rawHealthy = { stream_health: "HEALTHY", websocket: "open" };
assert(rawHealthy.stream_health === "HEALTHY" && !workspace.isActionAllowed("quote_ingress", "submit_order"), "raw quote health upgraded blocked envelope");
workspace.markStatusEnvelopesUnavailable("503");
const rawRunning = { state: "RUNNING", run_id: "raw-run" };
assert(rawRunning.state === "RUNNING" && workspace.getCurrentStatusEnvelope("local_paper_runtime") === null, "raw RUNNING survived unavailable envelope");
assert(!workspace.isActionAllowed("local_paper_runtime", "start_automated_strategy"), "stale runtime authorized mutation");
assert(elements["status-envelope-cards"].innerHTML.includes("token-unavailable"), "stale set preserved green cards");

workspace.renderStatusEnvelopes(payloads.runningLocal);
assert(workspace.renderWorkspaceEnvelope("local_paper_runtime").includes("pipeline_snapshot_digest"), "runtime provenance missing");
workspace.renderStatusEnvelopes(payloads.recovered);
fetchImpl = async () => response(payloads.badDigest);
let digestRejected = false;
try { await workspace.loadStatusEnvelopes("set-B"); } catch { digestRejected = true; }
assert(digestRejected && workspace.isStatusEnvelopeStale(), "digest invalid did not fail closed");
assert(!workspace.isActionAllowed("no_overnight", "acknowledge_breach_by_revision"), "invalid digest left ACK enabled");
workspace.renderStatusEnvelopes(payloads.recovered);
const rawNoOvernight = { status: { revision: workspace.getCurrentStatusEnvelope("no_overnight").revision + 1 }, acknowledgement: { required_phrase: "fixture" } };
assert(rawNoOvernight.status.revision !== workspace.getCurrentStatusEnvelope("no_overnight").revision, "revision mismatch fixture invalid");

let runMode = "queued";
fetchImpl = async (url) => {
  urls.push(String(url));
  if (String(url).includes("backtest-runs")) {
    if (runMode === "503") return response({ detail: { code: "STATUS_ENVELOPE_UNAVAILABLE" } }, false, 503);
    return response(payloads.runs[runMode]);
  }
  throw new Error(`unexpected entity URL ${url}`);
};
await workspace.loadEntityStatus("backtest_run", "run-1");
assert(workspace.isEntityActionAllowed("backtest_run", "run-1", "cancel_run"), "QUEUED cancel unavailable");
assert(!workspace.isEntityActionAllowed("backtest_run", "run-1", "view_results"), "QUEUED exposed results");
runMode = "running"; await workspace.loadEntityStatus("backtest_run", "run-1");
assert(!workspace.isEntityActionAllowed("backtest_run", "run-1", "view_results"), "RUNNING exposed results");
runMode = "completed"; await workspace.loadEntityStatus("backtest_run", "run-1");
assert(workspace.isEntityActionAllowed("backtest_run", "run-1", "view_results"), "COMPLETED hid results");
assert(workspace.getCurrentEntityEnvelope("backtest_run", "run-1").identity.progress === "0", "progress is not canonical decimal string");
runMode = "failed"; await workspace.loadEntityStatus("backtest_run", "run-1");
assert(workspace.isEntityActionAllowed("backtest_run", "run-1", "retry_run"), "FAILED retry unavailable");
runMode = "503";
try { await workspace.loadEntityStatus("backtest_run", "run-1"); } catch {}
assert(workspace.getCurrentEntityEnvelope("backtest_run", "run-1") === null, "entity 503 remained current");
assert(workspace.renderEntityEnvelope("backtest_run", "run-1").includes("最後有效"), "entity 503 lost stale provenance");

fetchImpl = async (url) => {
  urls.push(String(url));
  const id = decodeURIComponent(String(url).split("/").at(-1));
  return response(payloads.comparisons[id]);
};
await workspace.loadEntityStatus("backtest_comparison", "cmp-not");
assert(!workspace.isEntityActionAllowed("backtest_comparison", "cmp-not", "view_outcome_deltas"), "NOT_COMPARABLE exposed delta");
await workspace.loadEntityStatus("backtest_comparison", "cmp-no-clear");
assert(workspace.isEntityActionAllowed("backtest_comparison", "cmp-no-clear", "view_outcome_deltas"), "NO_CLEAR hid raw delta detail");
assert(!workspace.isEntityActionAllowed("backtest_comparison", "cmp-no-clear", "create_qualification_evidence"), "NO_CLEAR triggered qualification");
await workspace.loadEntityStatus("backtest_comparison", "cmp-likely");
assert(workspace.isEntityActionAllowed("backtest_comparison", "cmp-likely", "create_qualification_evidence"), "LIKELY hid qualification action");

let resolveLateComparisonA;
const lateComparisonAResponse = new Promise((resolve) => { resolveLateComparisonA = resolve; });
fetchImpl = async (url) => {
  urls.push(String(url));
  if (String(url).endsWith("cmp-late-a")) return lateComparisonAResponse;
  if (String(url).endsWith("cmp-late-b")) return response(payloads.comparisons["cmp-late-b"]);
  if (String(url).endsWith("cmp-wrong")) return response(payloads.comparisons["cmp-not"]);
  throw new Error(`unexpected late entity URL ${url}`);
};
const lateComparisonA = workspace.loadEntityStatus("backtest_comparison", "cmp-late-a");
await workspace.loadEntityStatus("backtest_comparison", "cmp-late-b");
resolveLateComparisonA(response(payloads.comparisons["cmp-late-a"]));
await lateComparisonA;
assert(workspace.getEntityEnvelope("backtest_comparison", "cmp-late-a") === null, "late inactive entity response was cached");
let identityRejected = false;
try { await workspace.loadEntityStatus("backtest_comparison", "cmp-wrong"); } catch { identityRejected = true; }
assert(identityRejected && workspace.getCurrentEntityEnvelope("backtest_comparison", "cmp-wrong") === null, "entity identity mismatch did not fail closed");

workspace.renderStatusEnvelopes(payloads.critical);
workspace.renderStatusEnvelopes(payloads.recovered);
assert(elements["status-envelope-alert"].textContent === "", "unchanged Formal BLOCKED replayed assertive text");
assert(elements["status-envelope-announcement"].textContent.includes("Kill switch"), "kill recovery not announced politely");
assert(!elements["status-envelope-announcement"].textContent.includes("Formal Dataset"), "unchanged Formal replayed politely");
workspace.renderStatusEnvelopes(payloads.multiple);
const aggregate = elements["status-envelope-alert"].textContent;
assert(aggregate.includes("行情 ingress") && aggregate.includes("收盤風控"), "multiple assertive changes were not aggregated");
assert(aggregate.indexOf("行情 ingress") < aggregate.indexOf("收盤風控"), "assertive aggregation order is unstable");
workspace.renderStatusEnvelopes(payloads.multiple);
assert(elements["status-envelope-alert"].textContent === "" && elements["status-envelope-announcement"].textContent === "", "same digest replayed");
fetchImpl = async (url) => {
  const id = decodeURIComponent(String(url).split("/").at(-1));
  return response(payloads.comparisons[id]);
};
await workspace.loadEntityStatus("backtest_comparison", "cmp-not");
await workspace.loadEntityStatus("backtest_comparison", "cmp-likely");
await workspace.loadEntityStatus("backtest_comparison", "cmp-not");
assert(!elements["status-envelope-alert"].textContent.includes("cmp-not"), "switching entity replayed old id");

media.matches = true;
workspace.markStatusEnvelopesUnavailable("503");
assert(!elements["mobile-read-only-banner"].hidden, "mobile first failure hid reason");
assert(elements["mobile-read-only-reason"].textContent.length > 0, "mobile server policy reason missing");
let mutationBlocked = false;
try { await fetch("/mutation", { method: "POST" }); } catch (error) { mutationBlocked = error.name === "NotAllowedError"; }
assert(mutationBlocked, "mobile mutation reached transport");
media.matches = false;
workspace.applyMobileReadOnlyPolicy();
assert(elements["mobile-read-only-banner"].hidden, "desktop retained mobile banner");
assert(!document.documentElement.classList.contains("mobile-read-only"), "desktop remained inert");

for (const vector of vectors) {
  const parsedHttpJson = JSON.parse(vector.httpJson);
  const canonical = workspace.canonicalJson(parsedHttpJson);
  assert(canonical === vector.canonical, "Python/Node canonical bytes differ");
  assert(await workspace.sha256(canonical) === vector.digest, "Python/Node SHA differs");
}
for (const invalid of [1.5, -0, Number.MAX_SAFE_INTEGER + 1]) {
  let rejected = false;
  try { workspace.validateSignedValue({ value: invalid }); } catch { rejected = true; }
  assert(rejected, `signed negative accepted: ${invalid}`);
}
"""
    script = (
        template.replace("__MODULE__", json.dumps(RENDERER_PATH.as_uri()))
        .replace("__PAYLOADS__", json.dumps(_node_payloads(), ensure_ascii=False))
        .replace("__VECTORS__", json.dumps(_canonical_vectors(), ensure_ascii=False))
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mjs", dir="/private/tmp", encoding="utf-8", delete=False
        ) as handle:
            handle.write(script)
            temporary_path = Path(handle.name)
        return subprocess.run(
            ["node", str(temporary_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _run_simulation_settings_contract(
    scenario: str = "fresh",
    module_path: Path = SIMULATION_PATH,
) -> subprocess.CompletedProcess[str]:
    template = r"""
import { createSimulationWorkspace } from __MODULE__;

function assert(condition, message) { if (!condition) throw new Error(message); }
function deferred() {
  let resolve;
  const promise = new Promise((next) => { resolve = next; });
  return { promise, resolve };
}
async function flush() {
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
}

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  toggle(value, force) {
    const next = force === undefined ? !this.values.has(value) : Boolean(force);
    if (next) this.values.add(value); else this.values.delete(value);
    return next;
  }
  contains(value) { return this.values.has(value); }
}

class Element {
  constructor(id = "") {
    this.id = id; this.innerHTML = ""; this._textContent = ""; this.textContentWrites = 0;
    this.hidden = false;
    this.value = ""; this.disabled = false; this.required = false; this.inert = false;
    this.dataset = {}; this.style = {}; this.className = ""; this.classList = new ClassList();
    this.attributes = new Map(); this.listeners = new Map(); this.offsetParent = {};
  }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }
  async trigger(type) {
    const event = { preventDefault() {} };
    for (const listener of this.listeners.get(type) || []) await listener(event);
  }
  set textContent(value) { this._textContent = String(value); this.textContentWrites += 1; }
  get textContent() { return this._textContent; }
  setAttribute(key, value) { this.attributes.set(key, String(value)); }
  getAttribute(key) { return this.attributes.get(key) || null; }
  hasAttribute(key) { return this.attributes.has(key); }
  removeAttribute(key) { this.attributes.delete(key); }
  querySelectorAll() { return []; }
  focus() {}
}

const settingsPayload = {
  csrf_token: "csrf", revision: 3, has_unapplied_changes: true,
  active: {
    starting_cash_twd: 10000000, max_daily_buy_notional_twd: 2000000,
    commission_rate: 0.001425, minimum_commission_twd: 20
  },
  draft: {
    starting_cash_twd: 12000000, max_daily_buy_notional_twd: 2500000,
    commission_rate: 0.001425, minimum_commission_twd: 20
  },
  apply_blockers: {
    automated_strategy_running: false,
    managed_exposure_count: 0, pending_entry_quantity: 0, pending_exit_quantity: 0,
    unresolved_execution_count: 0, open_breach: false, identity_mismatch: false
  }
};
const rawPayload = {
  schema_version: "no_overnight_dashboard.v1",
  status: {
    mode: "ENFORCED", state: "NORMAL", revision: 7, breach_latched: false,
    would_actions: [], stable_reasons: [], flat_proof_mode: null,
    evidence_snapshot_digest: null
  },
  acknowledgement: {
    available: false, required_phrase: null, acknowledged: false,
    acknowledged_at: null, acknowledged_by: null
  },
  apply_blockers: {
    managed_exposure_count: 0, pending_entry_quantity: 0, pending_exit_quantity: 0,
    unresolved_execution_count: 0, open_breach: false, identity_mismatch: false
  },
  settings_rotation: { available: true, reason: null },
  evidence: { execution_snapshot: null, strict_flat: null },
  exposures: { managed: [], excluded: [] }
};

function response(payload, ok = true, status = 200) {
  return { ok, status, json: async () => structuredClone(payload) };
}

function createHarness({ settingsResponses, rawResponses }) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };
  const appShell = element("app-shell");
  const urls = [];
  const settingsQueue = [...settingsResponses];
  const rawQueue = [...rawResponses];
  const statusListeners = [];
  let settingsRequests = 0;
  let rawRequests = 0;
  let applyPosts = 0;
  const applyRequests = [];
  let confirmCalls = 0;
  globalThis.HTMLElement = Element;
  globalThis.window = globalThis;
  globalThis.window.confirm = () => { confirmCalls += 1; return true; };
  globalThis.document = {
    visibilityState: "visible",
    getElementById: (id) => element(id),
    querySelector: (selector) => selector === ".app-shell" ? appShell : null
  };
  globalThis.requestAnimationFrame = (callback) => callback();
  globalThis.fetch = async (resource, options = {}) => {
    const url = String(resource);
    const method = String(options.method || "GET").toUpperCase();
    urls.push(url);
    if (url === "/api/simulation/settings" && method === "GET") {
      settingsRequests += 1;
      if (!settingsQueue.length) throw new Error(`unexpected settings request ${settingsRequests}`);
      return await settingsQueue.shift();
    }
    if (url === "/api/simulation/no-overnight/status" && method === "GET") {
      rawRequests += 1;
      if (!rawQueue.length) throw new Error(`unexpected raw request ${rawRequests}`);
      return await rawQueue.shift();
    }
    if (url === "/api/simulation/settings/apply" && method === "POST") {
      applyPosts += 1;
      applyRequests.push({
        headers: structuredClone(options.headers || {}),
        body: String(options.body || "")
      });
      return response({ detail: "test transport stop after observing POST" }, false, 409);
    }
    throw new Error(`unexpected ${method} ${url}`);
  };
  const statusEnvelope = (subject) => ({
    subject, revision: subject === "no_overnight" ? 7 : 1,
    status: "READY", status_glyph: "✓", status_label: "Ready", reason_codes: []
  });
  const statusEnvelopes = {
    getCurrentStatusEnvelope: statusEnvelope,
    getStatusEnvelope: statusEnvelope,
    isStatusEnvelopeStale: () => false,
    renderInlineStatus: () => "<span>Ready</span>",
    renderWorkspaceEnvelope: () => "<div>Ready</div>",
    isActionAllowed: () => false,
    areActionsAllowed: () => false,
    loadStatusEnvelopes: async () => null,
    subscribe: (listener) => { statusListeners.push(listener); }
  };
  const workspace = createSimulationWorkspace({
    state: { snapshot: null }, statusEnvelopes,
    escapeHtml: (value) => String(value),
    formatNumber: (value) => String(value),
    formatPercent: (value) => String(value),
    formatQuoteTime: (value) => String(value),
    newIdempotencyKey: () => "key",
    setWorkspace: () => {}
  });
  return {
    element,
    urls,
    workspace,
    emitStatus(type, subject = null) {
      statusListeners.forEach((listener) => listener({ type, payload: { subject } }));
    },
    get settingsRequests() { return settingsRequests; },
    get rawRequests() { return rawRequests; },
    get applyPosts() { return applyPosts; },
    get applyRequests() { return applyRequests; },
    get confirmCalls() { return confirmCalls; }
  };
}

const scenario = __SCENARIO__;
if (scenario === "fresh") {
  const valid = createHarness({
    settingsResponses: [response(settingsPayload)],
    rawResponses: [response(rawPayload)]
  });
  await valid.workspace.setSimulationSettingsDrawer(true);
  assert(valid.element("simulation-settings-drawer").classList.contains("open"), "settings drawer did not open");
  assert(!valid.element("no-overnight-drawer").classList.contains("open"), "test opened No-Overnight drawer");
  assert(valid.rawRequests === 1, "settings drawer did not explicitly refresh raw detail");
  assert(valid.element("simulation-settings-apply").disabled === false, "valid current envelopes and available rotation did not enable Apply");

  const unavailable = createHarness({
    settingsResponses: [response(settingsPayload)],
    rawResponses: [response({
      detail: {
        code: "NO_OVERNIGHT_STATUS_UNAVAILABLE",
        message: "server-owned raw detail reason"
      }
    }, false, 503)]
  });
  await unavailable.workspace.setSimulationSettingsDrawer(true);
  const unavailableMessage = unavailable.element("simulation-settings-message");
  assert(unavailable.element("simulation-settings-apply").disabled === true, "raw unavailable left Apply enabled");
  assert(unavailableMessage.classList.contains("visible"), "raw unavailable reason was hidden");
  assert(unavailableMessage.textContent.includes("NO_OVERNIGHT_STATUS_UNAVAILABLE"), "server unavailable code missing from settings message");
  assert(unavailableMessage.textContent.includes("server-owned raw detail reason"), "server unavailable message missing from settings message");
} else if (scenario === "malformed") {
  const malformedCases = [
    ["missing-revision", (payload) => { delete payload.revision; }],
    ["string-revision", (payload) => { payload.revision = "3"; }],
    ["fractional-revision", (payload) => { payload.revision = 3.5; }],
    ["unsafe-revision", (payload) => { payload.revision = Number.MAX_SAFE_INTEGER + 1; }],
    ["missing-csrf", (payload) => { delete payload.csrf_token; }],
    ["empty-csrf", (payload) => { payload.csrf_token = ""; }],
    ["wrong-type-csrf", (payload) => { payload.csrf_token = 3; }],
    ["missing-active", (payload) => { delete payload.active; }],
    ["missing-draft", (payload) => { delete payload.draft; }],
    ["wrong-type-active", (payload) => { payload.active = []; }],
    ["missing-starting-cash", (payload) => { delete payload.draft.starting_cash_twd; }],
    ["missing-daily-buy-limit", (payload) => { delete payload.draft.max_daily_buy_notional_twd; }],
    ["missing-commission-rate", (payload) => { delete payload.draft.commission_rate; }],
    ["missing-minimum-commission", (payload) => { delete payload.draft.minimum_commission_twd; }],
    ["unrenderable-setting", (payload) => { payload.active.commission_rate = "not-a-number"; }]
  ].map(([name, mutate]) => {
    const payload = structuredClone(settingsPayload);
    mutate(payload);
    return { name, payload };
  });
  const invalidReason = "⚠ 無法確認最新設定：SETTINGS_RESPONSE_INVALID。目前不能套用。";
  const receipts = [];
  for (const item of malformedCases) {
    const harness = createHarness({
      settingsResponses: [response(item.payload)],
      rawResponses: [response(rawPayload)]
    });
    const apply = harness.element("simulation-settings-apply");
    const message = harness.element("simulation-settings-message");
    await harness.workspace.setSimulationSettingsDrawer(true);
    assert(apply.disabled === true, `${item.name} enabled Apply`);
    assert(message.classList.contains("visible"), `${item.name} hid invalid reason`);
    assert(message.textContent === invalidReason, `${item.name} reason mismatch: ${message.textContent}`);
    assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "false", `${item.name} form remained busy`);
    assert(harness.element("simulation-settings-panel").getAttribute("aria-busy") === "false", `${item.name} panel remained busy`);
    const reasonWrites = message.textContentWrites;
    await apply.trigger("click");
    assert(harness.confirmCalls === 0, `${item.name} opened confirmation`);
    assert(harness.applyPosts === 0, `${item.name} reached Apply POST`);
    assert(harness.applyRequests.length === 0, `${item.name} leaked transport fields`);
    assert(message.textContentWrites === reasonWrites, `${item.name} replayed same invalid reason`);
    receipts.push({
      case: item.name,
      disabled: apply.disabled,
      reason: message.textContent,
      confirmCalls: harness.confirmCalls,
      applyPosts: harness.applyPosts,
      sameReasonReplayWrites: message.textContentWrites - reasonWrites
    });
  }

  const staleSettings = deferred();
  const staleRaw = deferred();
  const currentSettings = deferred();
  const currentRaw = deferred();
  const epochHarness = createHarness({
    settingsResponses: [staleSettings.promise, currentSettings.promise],
    rawResponses: [staleRaw.promise, currentRaw.promise]
  });
  const staleOpen = epochHarness.workspace.setSimulationSettingsDrawer(true);
  await epochHarness.workspace.setSimulationSettingsDrawer(false);
  const currentOpen = epochHarness.workspace.setSimulationSettingsDrawer(true);
  const epochMessage = epochHarness.element("simulation-settings-message");
  const pendingText = epochMessage.textContent;
  const pendingWrites = epochMessage.textContentWrites;
  staleSettings.resolve(response(malformedCases[0].payload));
  staleRaw.resolve(response(rawPayload));
  await staleOpen;
  assert(epochHarness.element("simulation-settings-apply").disabled === true, "prior malformed response enabled current epoch");
  assert(epochMessage.textContent === pendingText, "prior malformed response replaced current pending reason");
  assert(epochMessage.textContentWrites === pendingWrites, "prior malformed response replayed current reason");
  currentSettings.resolve(response(settingsPayload));
  currentRaw.resolve(response(rawPayload));
  await currentOpen;
  assert(epochHarness.element("simulation-settings-apply").disabled === false, "current valid epoch did not recover after prior malformed response");

  const recoverySettings = deferred();
  const recoveryRaw = deferred();
  const recoveryPayload = { ...structuredClone(settingsPayload), revision: 4, csrf_token: "csrf-recovered" };
  const recoveryHarness = createHarness({
    settingsResponses: [response(malformedCases[0].payload), recoverySettings.promise],
    rawResponses: [response(rawPayload), recoveryRaw.promise]
  });
  const recoveryApply = recoveryHarness.element("simulation-settings-apply");
  await recoveryHarness.workspace.setSimulationSettingsDrawer(true);
  assert(recoveryApply.disabled === true, "invalid epoch was transport eligible before recovery");
  await recoveryHarness.workspace.setSimulationSettingsDrawer(false);
  const recoveryOpen = recoveryHarness.workspace.setSimulationSettingsDrawer(true);
  assert(recoveryApply.disabled === true, "cached invalid epoch satisfied later recovery");
  recoverySettings.resolve(response(recoveryPayload));
  await flush();
  assert(recoveryApply.disabled === true, "settings-only valid recovery enabled Apply");
  recoveryRaw.resolve(response(rawPayload));
  await recoveryOpen;
  assert(recoveryApply.disabled === false, "both valid current recovery responses did not enable Apply");
  await recoveryApply.trigger("click");
  assert(recoveryHarness.confirmCalls === 0, "valid recovery unexpectedly opened confirmation");
  assert(recoveryHarness.applyPosts === 1, "valid recovery did not produce exactly one POST");
  const recoveryRequest = recoveryHarness.applyRequests[0];
  assert(recoveryRequest.headers["X-Strategy-CSRF"] === "csrf-recovered", "valid recovery used stale CSRF token");
  assert(JSON.parse(recoveryRequest.body).revision === 4, "valid recovery used stale or non-integer revision");
  console.log(JSON.stringify({
    scenario,
    malformed: receipts,
    priorMalformedIgnored: true,
    recovery: {
      settingsOnlyPosts: 0,
      confirmCalls: recoveryHarness.confirmCalls,
      applyPosts: recoveryHarness.applyPosts,
      revision: JSON.parse(recoveryRequest.body).revision,
      csrf: recoveryRequest.headers["X-Strategy-CSRF"]
    }
  }));
} else if (scenario === "reopen") {
  const staleSettings = deferred();
  const staleRaw = deferred();
  const lateSettings = deferred();
  const lateRaw = deferred();
  const harness = createHarness({
    settingsResponses: [response(settingsPayload), staleSettings.promise, lateSettings.promise],
    rawResponses: [response(rawPayload), staleRaw.promise, lateRaw.promise]
  });
  const apply = harness.element("simulation-settings-apply");
  await harness.workspace.setSimulationSettingsDrawer(true);
  assert(apply.disabled === false, "initial valid open did not enable Apply");
  await harness.workspace.setSimulationSettingsDrawer(false);

  const staleOpen = harness.workspace.setSimulationSettingsDrawer(true);
  assert(apply.disabled === true, "first reopen did not synchronously disable cached Apply");
  await harness.workspace.setSimulationSettingsDrawer(false);
  const reopen = harness.workspace.setSimulationSettingsDrawer(true);
  assert(apply.disabled === true, "reopen did not synchronously disable cached Apply");
  assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "true", "pending form is not busy");
  assert(harness.element("simulation-settings-panel").getAttribute("aria-busy") === "true", "pending panel is not busy");
  assert(harness.element("simulation-settings-message").textContent === "正在確認最新設定與收盤風控狀態；目前不能套用。設定草稿仍可儲存。", "pending copy mismatch");
  assert(harness.settingsRequests === 3, "each reopen did not launch a fresh settings request");
  assert(harness.rawRequests === 3, "each reopen did not launch a fresh raw request");
  await apply.trigger("click");
  assert(harness.confirmCalls === 0, "pending refresh opened confirmation");
  assert(harness.applyPosts === 0, "pending settings/raw refresh reached Apply POST");

  staleSettings.resolve(response(settingsPayload));
  staleRaw.resolve(response(rawPayload));
  await staleOpen;
  assert(apply.disabled === true, "prior-epoch responses satisfied the current reopen epoch");
  await apply.trigger("click");
  assert(harness.confirmCalls === 0, "prior-epoch responses opened confirmation");
  assert(harness.applyPosts === 0, "prior-epoch responses reached Apply POST");

  lateSettings.resolve(response(settingsPayload));
  await flush();
  assert(apply.disabled === true, "settings-only refresh enabled Apply before raw success");
  assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "true", "settings-only form stopped being busy");
  await apply.trigger("click");
  assert(harness.confirmCalls === 0, "settings-only refresh opened confirmation");
  assert(harness.applyPosts === 0, "settings-only refresh reached Apply POST");

  lateRaw.resolve(response(rawPayload));
  await reopen;
  assert(apply.disabled === false, "both current-epoch refreshes did not enable Apply");
  assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "false", "settled form remained busy");
  assert(harness.element("simulation-settings-panel").getAttribute("aria-busy") === "false", "settled panel remained busy");
  assert(harness.element("simulation-settings-message").textContent === "最新狀態已確認。草稿尚未套用；套用會建立新的模擬帳戶。", "eligible copy mismatch");
  await apply.trigger("click");
  assert(harness.applyPosts === 1, "post-refresh positive did not reach exactly one Apply POST");
  console.log(JSON.stringify({
    scenario, pendingPosts: 0, priorEpochPosts: 0, settingsOnlyPosts: 0,
    blockedConfirmCalls: harness.confirmCalls, settledBusy: false,
    postRecoveryPosts: harness.applyPosts
  }));
} else if (scenario === "latch") {
  const harness = createHarness({
    settingsResponses: [response(settingsPayload), response(settingsPayload), response(settingsPayload)],
    rawResponses: [
      response(rawPayload),
      response({
        detail: {
          code: "NO_OVERNIGHT_STATUS_UNAVAILABLE",
          message: "server-owned late raw failure"
        }
      }, false, 503),
      response(rawPayload)
    ]
  });
  const apply = harness.element("simulation-settings-apply");
  await harness.workspace.setSimulationSettingsDrawer(true);
  assert(apply.disabled === false, "initial valid open did not enable Apply");
  await harness.workspace.setSimulationSettingsDrawer(false);

  await harness.workspace.setSimulationSettingsDrawer(true);
  const unavailableMessage = harness.element("simulation-settings-message");
  assert(apply.disabled === true, "raw 503 left Apply enabled");
  assert(unavailableMessage.textContent.includes("NO_OVERNIGHT_STATUS_UNAVAILABLE"), "raw 503 code missing");
  assert(unavailableMessage.textContent.includes("server-owned late raw failure"), "raw 503 message missing");
  const reasonWrites = unavailableMessage.textContentWrites;
  harness.emitStatus("set", "no_overnight");
  assert(unavailableMessage.textContentWrites === reasonWrites, `same-revision raw event replayed local status: ${reasonWrites} -> ${unavailableMessage.textContentWrites}`);
  harness.emitStatus("set", "quote_ingress");
  assert(unavailableMessage.textContentWrites === reasonWrites, `unrelated event replayed local status: ${reasonWrites} -> ${unavailableMessage.textContentWrites}`);
  harness.emitStatus("scope");
  assert(apply.disabled === true, "ordinary StatusEnvelope event cleared raw failure latch");
  assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "false", "settled 503 form remained busy");
  assert(unavailableMessage.textContent.includes("NO_OVERNIGHT_STATUS_UNAVAILABLE"), "status event erased raw 503 code");
  assert(unavailableMessage.textContent.includes("server-owned late raw failure"), "status event erased raw 503 message");
  await apply.trigger("click");
  assert(harness.confirmCalls === 0, "raw latch opened confirmation");
  assert(harness.applyPosts === 0, "cached raw after 503 reached Apply POST");

  await harness.workspace.setSimulationSettingsDrawer(false);
  await harness.workspace.setSimulationSettingsDrawer(true);
  assert(apply.disabled === false, "new current-epoch raw success did not clear latch");
  assert(harness.element("simulation-settings-form").getAttribute("aria-busy") === "false", "recovered form remained busy");
  assert(harness.element("simulation-settings-message").textContent === "最新狀態已確認。草稿尚未套用；套用會建立新的模擬帳戶。", "recovered eligible copy mismatch");
  await apply.trigger("click");
  assert(harness.applyPosts === 1, "post-latch-recovery positive did not reach one Apply POST");
  console.log(JSON.stringify({
    scenario, post503StatusEventPosts: 0, blockedConfirmCalls: harness.confirmCalls,
    sameReasonReplayWrites: 0, postRecoveryPosts: harness.applyPosts
  }));
} else {
  throw new Error(`unknown scenario ${scenario}`);
}
"""
    script = template.replace("__MODULE__", json.dumps(module_path.as_uri())).replace(
        "__SCENARIO__", json.dumps(scenario)
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mjs", dir="/private/tmp", encoding="utf-8", delete=False
        ) as handle:
            handle.write(script)
            temporary_path = Path(handle.name)
        return subprocess.run(
            ["node", str(temporary_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def test_executed_status_store_scope_entity_live_mobile_and_digest_contracts() -> None:
    result = _run_node_contract()
    assert result.returncode == 0, result.stderr


def test_settings_drawer_explicitly_refreshes_raw_gate_and_renders_server_reason() -> None:
    result = _run_simulation_settings_contract()
    assert result.returncode == 0, result.stderr


def test_settings_apply_rejects_malformed_payloads_and_recovers_on_later_epoch() -> None:
    result = _run_simulation_settings_contract("malformed")
    assert result.returncode == 0, result.stderr


def test_settings_apply_transport_waits_for_both_reopen_refreshes() -> None:
    result = _run_simulation_settings_contract("reopen")
    assert result.returncode == 0, result.stderr


def test_settings_apply_raw_503_latch_requires_new_successful_raw_response() -> None:
    result = _run_simulation_settings_contract("latch")
    assert result.returncode == 0, result.stderr


def test_app_is_the_only_composition_root_and_workspaces_receive_one_store() -> None:
    assert 'import { createStatusEnvelopeWorkspace } from "./status_envelope.js";' in APP
    assert APP.count("createStatusEnvelopeWorkspace(") == 1
    assert "const statusEnvelopes = createStatusEnvelopeWorkspace({ escapeHtml });" in APP
    for factory in (
        "createCandidateWorkspace",
        "createSimulationWorkspace",
        "createBacktestWorkspace",
    ):
        composition_line = next(line for line in APP.splitlines() if f"{factory}(" in line)
        assert "statusEnvelopes" in composition_line
    assert "/api/dashboard/status-envelopes" not in WORKSPACES
    assert "createStatusEnvelopeWorkspace" not in WORKSPACES
    assert RENDERER.count("/api/dashboard/status-envelopes") == 3


def test_only_global_status_envelope_live_regions_announce_transitions() -> None:
    assert 'id="status-envelope-alert" role="alert"' in HTML
    assert 'id="status-envelope-announcement" role="status" aria-live="polite"' in HTML
    for element_id in (
        "status-envelope-topbar",
        "status-envelope-last-valid",
        "mobile-read-only-banner",
        "no-overnight-topbar",
        "automated-strategy-status",
        "atomic-backtest-dataset-status",
        "backtest-result",
        "backtest-comparison",
    ):
        start = HTML.index(f'id="{element_id}"')
        tag = HTML[HTML.rfind("<", 0, start) : HTML.find(">", start)]
        assert "aria-live=" not in tag and 'role="status"' not in tag
    assert "no-overnight-status-announcement" not in HTML + WORKSPACES
    assert "function clearGlobalLiveRegions()" in RENDERER
    assert "function arbitrateSetAnnouncements(payload)" in RENDERER


def test_renderer_is_server_copy_only_and_mobile_controls_remain_accessible() -> None:
    for title, _impact, _next, _a11y in se.REASON_CATALOG.values():
        assert title not in RENDERER
    for text, _a11y in se.ADVISORY_CATALOG.values():
        assert text not in RENDERER and text not in HTML
    for token in (
        "ready",
        "running",
        "blocked",
        "critical",
        "unavailable",
        "terminal-success",
    ):
        assert f".token-{token}" in CSS
    assert ".status-envelope-summary { min-height: 44px; }" in CSS
    assert "prefers-reduced-motion" in CSS
    assert "new MutationObserver(applyMobileReadOnlyPolicy)" in RENDERER


def test_retired_browser_status_authority_and_unknown_numeric_fallbacks() -> None:
    forbidden = (
        'session.stream_health === "BLOCKED"',
        "NO_OVERNIGHT_STATE_LABELS",
        "NO_OVERNIGHT_REASON_LABELS",
        "display_status",
        "deltas.expectancy || 0",
        "progress || 0",
        "ATOMIC_BACKTEST_DEFAULT",
    )
    for pattern in forbidden:
        assert pattern not in WORKSPACES
    assert "statusEnvelopes.isActionAllowed" in WORKSPACES
    assert "statusEnvelopes.isEntityActionAllowed" in WORKSPACES
    assert "statusEnvelopes.setStrategySetVersionId" in WORKSPACES
