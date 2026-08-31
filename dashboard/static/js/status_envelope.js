// Single browser reader/renderer for the server-owned StatusEnvelope model.
// Workspaces receive this instance from app.js; they never create a second
// store, fetch status directly, or infer display decisions from raw payloads.
export function createStatusEnvelopeWorkspace({ escapeHtml }) {
  const SUBJECTS = [
    "backtest_platform",
    "formal_dataset",
    "strategy_qualification",
    "local_paper_runtime",
    "quote_ingress",
    "kill_switch",
    "no_overnight",
    "market_shadow"
  ];
  const ENTITY_CONFIG = {
    backtest_run: {
      route: (id) => `/api/dashboard/status-envelopes/backtest-runs/${encodeURIComponent(id)}`,
      subjects: ["backtest_run", "cost_snapshot"],
      identitySubject: "backtest_run",
      identityKey: "run_id"
    },
    backtest_comparison: {
      route: (id) => `/api/dashboard/status-envelopes/backtest-comparisons/${encodeURIComponent(id)}`,
      subjects: ["backtest_comparison"],
      identitySubject: "backtest_comparison",
      identityKey: "comparison_id"
    }
  };
  const SUBJECT_LABELS = {
    backtest_platform: "回測平台",
    formal_dataset: "Formal Dataset",
    strategy_qualification: "策略資格證據",
    local_paper_runtime: "Local Paper 自動策略",
    quote_ingress: "行情 ingress",
    kill_switch: "Kill switch",
    no_overnight: "收盤風控",
    market_shadow: "Market Shadow",
    backtest_run: "Backtest Run",
    cost_snapshot: "成本快照",
    backtest_comparison: "Backtest Comparison"
  };
  const ENVELOPE_KEYS = [
    "schema_version", "subject", "authority", "status", "status_glyph", "status_label",
    "authority_status", "revision", "digest", "as_of", "reason_codes", "reasons", "advisory",
    "allowed_actions", "blocked_actions", "identity", "a11y", "live_region", "client_policy"
  ];
  const REASON_KEYS = ["code", "known", "title", "impact", "next_step", "a11y"];
  const ADVISORY_KEYS = ["code", "text", "a11y"];
  const BLOCKED_ACTION_KEYS = ["action", "reason_code"];
  const MOBILE_POLICY_KEYS = ["mode", "max_width_css_px", "reason_code"];
  const DISPLAY_STATES = [
    "READY", "EMPTY", "RUNNING", "DEGRADED", "BLOCKED", "CRITICAL", "UNAVAILABLE",
    "NOT_EVALUATED", "TERMINAL_FAILED", "TERMINAL_SUCCESS", "TERMINAL_CANCELLED"
  ];
  const A11Y_TOKENS = ["A-INFO", "A-WARN", "A-BLOCK", "A-CRIT"];
  const IDENTITY_KEYS = {
    backtest_platform: [],
    formal_dataset: ["strategy_set_version_id", "dataset_id", "manifest_digest", "research_truth_snapshot_digest"],
    strategy_qualification: ["qualification_ids", "qualification_count", "effect"],
    local_paper_runtime: ["run_id", "pipeline_snapshot_digest", "decision", "restart_behavior", "last_checked_at", "last_action_at", "last_error"],
    quote_ingress: ["quote_mode", "streaming", "last_quote_received_at", "stream_error", "quote_queue_depth", "quote_queue_capacity"],
    kill_switch: ["reason", "engaged_at", "last_transition_at", "durability", "restart_safe", "recovered", "recovery_error"],
    no_overnight: ["mode", "breach_latched", "flat_proof_mode", "evidence_snapshot_digest", "acknowledged", "acknowledged_at"],
    market_shadow: ["execution_enabled"],
    backtest_run: ["run_id", "dataset_id", "dataset_digest", "config_digest", "result_digest", "progress", "progress_message", "updated_at", "error_message"],
    cost_snapshot: ["contract_version", "commission_rate", "slippage_bps", "slippage_calibration_digest", "snapshot_digest"],
    backtest_comparison: ["comparison_id", "baseline_run_id", "challenger_run_id", "comparison_digest", "message", "config_diff_count", "config_diff_fields"]
  };
  const MOBILE_MUTATION_SELECTOR = [
    "form", ".order-ticket-button", "#momentum-detail-order", "#backtest-clone",
    "#backtest-compare", "[data-order-symbol]", "[data-momentum-alert]",
    "[data-cancel-order]", "[data-retry-order]", "[data-strategy-set-delete]",
    "[data-backtest-cancel]", "[data-backtest-retry]"
  ].join(",");

  const panel = document.getElementById("status-envelope-panel");
  const topbar = document.getElementById("status-envelope-topbar");
  const lastValidBanner = document.getElementById("status-envelope-last-valid");
  const mobileReadOnlyBanner = document.getElementById("mobile-read-only-banner");
  const mobileReadOnlyReason = document.getElementById("mobile-read-only-reason");
  const alertRegion = document.getElementById("status-envelope-alert");
  const announcement = document.getElementById("status-envelope-announcement");
  const matrix = document.getElementById("status-envelope-matrix");
  const cards = document.getElementById("status-envelope-cards");
  const mobileQuery = window.matchMedia("(max-width: 700px)");
  const nativeFetch = window.fetch.bind(window);
  const subscribers = new Set();
  const entityRecords = new Map();
  const entityGenerations = new Map();
  const activeEntityIds = new Map();
  const announcedEntityEvents = new Set();
  const previousSetDigests = {};

  let statusEnvelopeSet = null;
  let statusEnvelopeStale = true;
  let renderedDigestKey = null;
  let currentStrategySetVersionId = null;
  let setRequestGeneration = 0;
  let mobilePolicy = null;
  let unavailableAnnounced = false;

  function requestMethod(resource, options) {
    if (options?.method) return String(options.method).toUpperCase();
    if (typeof Request !== "undefined" && resource instanceof Request) return resource.method.toUpperCase();
    return "GET";
  }

  // Mobile is monitor-only before the first envelope. GET/HEAD remain open so
  // status can recover; every mutation is stopped at the transport boundary.
  window.fetch = (resource, options = {}) => {
    const method = requestMethod(resource, options);
    if (mobileQuery.matches && !["GET", "HEAD", "OPTIONS"].includes(method)) {
      const error = new Error(mobilePolicy?.reason_code || "MOBILE_READ_ONLY_MONITOR");
      error.name = "NotAllowedError";
      return Promise.reject(error);
    }
    return nativeFetch(resource, options);
  };

  function hasExactKeys(value, keys) {
    return value && typeof value === "object" && !Array.isArray(value)
      && Object.keys(value).sort().join("|") === [...keys].sort().join("|");
  }

  function hasValidUnicodeScalars(value) {
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xD800 && code <= 0xDBFF) {
        const next = value.charCodeAt(index + 1);
        if (!(next >= 0xDC00 && next <= 0xDFFF)) return false;
        index += 1;
      } else if (code >= 0xDC00 && code <= 0xDFFF) {
        return false;
      }
    }
    return true;
  }

  function validateSignedValue(value) {
    if (value === null || typeof value === "boolean") return;
    if (typeof value === "string") {
      if (!hasValidUnicodeScalars(value)) throw new Error("signed string 不是有效 Unicode scalar sequence");
      return;
    }
    if (typeof value === "number") {
      if (!Number.isSafeInteger(value) || Object.is(value, -0)) throw new Error("signed number 必須是 JS-safe integer 且不可為 negative zero");
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(validateSignedValue);
      return;
    }
    if (value && typeof value === "object") {
      Object.entries(value).forEach(([key, item]) => {
        if (!/^[A-Za-z0-9_]+$/.test(key)) throw new Error("signed object key 必須是 schema-defined ASCII identifier");
        validateSignedValue(item);
      });
      return;
    }
    throw new Error("signed value domain 不合法");
  }

  function expectedIdentityKeys(envelope) {
    if (envelope.status === "UNAVAILABLE") return ["error_type"];
    if (envelope.subject === "formal_dataset" && !Object.hasOwn(envelope.identity, "strategy_set_version_id")) return [];
    if (envelope.subject === "market_shadow" && Object.hasOwn(envelope.identity, "error_type")) return ["execution_enabled", "error_type"];
    return IDENTITY_KEYS[envelope.subject];
  }

  function validateStatusEnvelope(envelope, subject) {
    if (!hasExactKeys(envelope, ENVELOPE_KEYS) || envelope.schema_version !== "status_envelope.v1") throw new Error("狀態信封 keys 不完整");
    if (envelope.subject !== subject || !Object.hasOwn(SUBJECT_LABELS, subject)) throw new Error("狀態信封 subject 不符");
    if (!["EXISTING", "PROPOSED_REQUIRED"].includes(envelope.authority)) throw new Error("狀態信封 authority 不合法");
    if (!DISPLAY_STATES.includes(envelope.status)) throw new Error("狀態信封 status 不合法");
    if (typeof envelope.status_glyph !== "string" || typeof envelope.status_label !== "string") throw new Error("狀態信封 label 不合法");
    if (envelope.authority_status !== null && typeof envelope.authority_status !== "string") throw new Error("authority_status 不合法");
    if (!Number.isSafeInteger(envelope.revision) || envelope.revision < 0) throw new Error("revision 不合法");
    if (typeof envelope.digest !== "string" || !/^[0-9a-f]{64}$/.test(envelope.digest)) throw new Error("digest 不合法");
    if (typeof envelope.as_of !== "string" || !envelope.as_of) throw new Error("as_of 缺失");
    if (!Array.isArray(envelope.reason_codes) || !envelope.reason_codes.every((code) => typeof code === "string" && code)) throw new Error("reason_codes 不合法");
    if (!Array.isArray(envelope.reasons) || envelope.reasons.length !== envelope.reason_codes.length) throw new Error("reasons 未對應 reason_codes");
    envelope.reasons.forEach((reason, index) => {
      if (!hasExactKeys(reason, REASON_KEYS) || reason.code !== envelope.reason_codes[index]
        || typeof reason.known !== "boolean" || !["title", "impact", "next_step"].every((key) => typeof reason[key] === "string")
        || !A11Y_TOKENS.includes(reason.a11y)) throw new Error("reason 條目不合法");
    });
    if (!Array.isArray(envelope.advisory) || !envelope.advisory.every((item) => hasExactKeys(item, ADVISORY_KEYS)
      && typeof item.code === "string" && item.code && typeof item.text === "string" && item.text && A11Y_TOKENS.includes(item.a11y))) throw new Error("advisory 不合法");
    if (!Array.isArray(envelope.allowed_actions) || !envelope.allowed_actions.every((item) => typeof item === "string" && item)) throw new Error("allowed_actions 不合法");
    if (!Array.isArray(envelope.blocked_actions) || !envelope.blocked_actions.every((item) => hasExactKeys(item, BLOCKED_ACTION_KEYS)
      && typeof item.action === "string" && item.action && typeof item.reason_code === "string" && item.reason_code)) throw new Error("blocked_actions 不合法");
    if (!envelope.identity || typeof envelope.identity !== "object" || Array.isArray(envelope.identity)
      || !hasExactKeys(envelope.identity, expectedIdentityKeys(envelope) || [])) throw new Error("identity keys 不合法");
    if (!A11Y_TOKENS.includes(envelope.a11y) || !["polite", "assertive"].includes(envelope.live_region)) throw new Error("a11y 不合法");
    if (!envelope.client_policy || typeof envelope.client_policy !== "object" || Array.isArray(envelope.client_policy)) throw new Error("client_policy 不合法");
    if (subject === "local_paper_runtime" && envelope.status !== "UNAVAILABLE") {
      if (!hasExactKeys(envelope.client_policy, MOBILE_POLICY_KEYS)
        || envelope.client_policy.mode !== "READ_ONLY_MONITOR"
        || envelope.client_policy.max_width_css_px !== 700
        || envelope.client_policy.reason_code !== "MOBILE_READ_ONLY_MONITOR") throw new Error("手機唯讀 policy 不合法");
      if (!envelope.advisory.some((item) => item.code === envelope.client_policy.reason_code)) throw new Error("手機唯讀原因未由 server 提供");
    } else if (Object.keys(envelope.client_policy).length) {
      throw new Error("非 Local Paper subject 不可帶 client policy");
    }
    if (["READY", "EMPTY", "RUNNING"].includes(envelope.status)
      && envelope.reasons.some((reason) => ["A-BLOCK", "A-CRIT"].includes(reason.a11y))) throw new Error("阻擋原因不可搭配就緒狀態");
    validateSignedValue(envelope);
    return envelope;
  }

  function validateStatusEnvelopeSet(payload, subjects = SUBJECTS) {
    if (!hasExactKeys(payload, ["schema_version", "as_of", "envelopes"])
      || payload.schema_version !== "status_envelope_set.v1") throw new Error("狀態信封集合不完整");
    if (typeof payload.as_of !== "string" || !payload.as_of) throw new Error("狀態信封集合缺 as_of");
    if (!hasExactKeys(payload.envelopes, subjects)) throw new Error("狀態信封 subjects 不完整");
    subjects.forEach((subject) => validateStatusEnvelope(payload.envelopes[subject], subject));
    validateSignedValue(payload);
    return payload;
  }

  function canonicalJson(value) {
    validateSignedValue(value);
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  }

  async function sha256(value) {
    const bytes = new TextEncoder().encode(value);
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function validateStatusEnvelopeDigests(payload, subjects = SUBJECTS) {
    await Promise.all(subjects.map(async (subject) => {
      const envelope = payload.envelopes[subject];
      const body = Object.fromEntries(Object.entries(envelope).filter(([key]) => !["digest", "as_of"].includes(key)));
      if (await sha256(canonicalJson(body)) !== envelope.digest) throw new Error(`狀態信封 digest 不符：${subject}`);
    }));
    return payload;
  }

  function tokenClass(envelope) {
    return `token-${envelope.status.toLowerCase().replaceAll("_", "-")}`;
  }

  function shortDigest(digest) {
    return typeof digest === "string" && digest.length > 12 ? `${digest.slice(0, 8)}…${digest.slice(-4)}` : digest;
  }

  function renderStatusSummary(envelope) {
    const raw = envelope.authority_status === null
      ? '<span class="status-envelope-raw unknown">authority_status：未提供</span>'
      : `<code class="status-envelope-raw">${escapeHtml(envelope.authority_status)}</code>`;
    return `<span class="status-envelope-summary ${tokenClass(envelope)}" data-a11y="${escapeHtml(envelope.a11y)}"><span class="status-envelope-glyph" aria-hidden="true">${escapeHtml(envelope.status_glyph)}</span><span>${escapeHtml(envelope.status_label)}</span></span> ${raw}`;
  }

  function renderBlockerList(envelope) {
    if (!envelope.reasons.length) return '<p class="status-envelope-no-reasons">無阻擋原因（依 server 投影）。</p>';
    return `<ul class="status-envelope-reasons" aria-label="阻擋原因 ${envelope.reasons.length} 項">${envelope.reasons.map((reason) => `
      <li class="status-envelope-reason ${reason.known ? "" : "unmapped"}" data-a11y="${escapeHtml(reason.a11y)}">
        <div class="status-envelope-reason-head"><strong>${escapeHtml(reason.title)}</strong> <code class="status-envelope-code">${escapeHtml(reason.code)}</code>${reason.known ? "" : ' <span class="status-envelope-unmapped">未對照文案，原碼保留</span>'}</div>
        ${reason.impact ? `<div class="status-envelope-impact">影響：${escapeHtml(reason.impact)}</div>` : ""}
        ${reason.next_step ? `<div class="status-envelope-next">下一步：${escapeHtml(reason.next_step)}</div>` : ""}
      </li>`).join("")}</ul>`;
  }

  function renderAdvisory(envelope) {
    if (!envelope.advisory.length) return "";
    return `<ul class="status-envelope-advisory">${envelope.advisory.map((item) => `<li data-code="${escapeHtml(item.code)}" data-a11y="${escapeHtml(item.a11y)}">${escapeHtml(item.text)}</li>`).join("")}</ul>`;
  }

  function renderActions(envelope) {
    const allowed = envelope.allowed_actions.map((action) => `<code>${escapeHtml(action)}</code>`).join(" ") || "—";
    const blocked = envelope.blocked_actions.map((item) => `<code>${escapeHtml(item.action)}</code> <span class="status-envelope-muted">（${escapeHtml(item.reason_code)}）</span>`).join("、") || "—";
    return `<dl class="status-envelope-actions"><dt>可做</dt><dd>${allowed}</dd><dt>已阻擋</dt><dd>${blocked}</dd></dl>`;
  }

  function renderProvenanceStrip(envelope) {
    const identity = Object.keys(envelope.identity).sort().map((key) => {
      const value = envelope.identity[key];
      return `<span class="status-envelope-identity-item"><span class="status-envelope-muted">${escapeHtml(key)}</span> <code>${escapeHtml(value === null ? "—" : String(value))}</code></span>`;
    }).join("");
    return `<div class="status-envelope-provenance"><span>${escapeHtml(envelope.authority)}</span><span>rev <code>${escapeHtml(String(envelope.revision))}</code></span><span>digest <code title="${escapeHtml(envelope.digest)}">${escapeHtml(shortDigest(envelope.digest))}</code></span><span>as of <time datetime="${escapeHtml(envelope.as_of)}">${escapeHtml(envelope.as_of)}</time></span>${identity}</div>`;
  }

  function renderEnvelopeBody(envelope) {
    return `${renderStatusSummary(envelope)}${renderAdvisory(envelope)}${renderBlockerList(envelope)}${renderActions(envelope)}${renderProvenanceStrip(envelope)}`;
  }

  function unavailableMarkup(label, stale = false) {
    return `<div class="status-envelope-workspace token-unavailable${stale ? " stale" : ""}"><span class="status-envelope-summary token-unavailable"><span class="status-envelope-glyph" aria-hidden="true">⚠</span><span>狀態不可用</span></span><p>${escapeHtml(label)} 尚無 current verified envelope；所有依 current state 的操作停用。</p></div>`;
  }

  function getStatusEnvelope(subject) {
    return statusEnvelopeSet?.envelopes?.[subject] || null;
  }

  function getCurrentStatusEnvelope(subject) {
    if (statusEnvelopeStale) return null;
    const envelope = getStatusEnvelope(subject);
    if (subject === "formal_dataset" && currentStrategySetVersionId !== null
      && envelope?.identity?.strategy_set_version_id !== currentStrategySetVersionId) return null;
    return envelope;
  }

  function renderWorkspaceEnvelope(subject) {
    const envelope = getStatusEnvelope(subject);
    if (!envelope) return unavailableMarkup(SUBJECT_LABELS[subject] || subject);
    if (statusEnvelopeStale) {
      return `<div class="status-envelope-workspace token-unavailable stale" data-subject="${escapeHtml(subject)}" data-digest="${escapeHtml(envelope.digest)}"><span class="status-envelope-summary token-unavailable"><span aria-hidden="true">⚠</span><span>狀態不可用</span></span><p class="status-envelope-stale-note">↻ 最後有效：${escapeHtml(envelope.status_label)}；current state 未驗證，操作停用。</p>${renderBlockerList(envelope)}${renderProvenanceStrip(envelope)}</div>`;
    }
    return `<div class="status-envelope-workspace ${tokenClass(envelope)}" data-subject="${escapeHtml(subject)}" data-digest="${escapeHtml(envelope.digest)}">${renderEnvelopeBody(envelope)}</div>`;
  }

  function renderInlineStatus(subject) {
    const envelope = getStatusEnvelope(subject);
    if (!envelope) return '<span class="status-envelope-summary token-unavailable"><span aria-hidden="true">⚠</span><span>狀態不可用</span></span>';
    if (statusEnvelopeStale) return `<span class="status-envelope-summary token-unavailable"><span aria-hidden="true">⚠</span><span>狀態不可用</span></span><span class="status-envelope-stale-note">↻ 最後有效：${escapeHtml(envelope.status_label)}</span>`;
    return renderStatusSummary(envelope);
  }

  function actionAllowed(envelope, action) {
    return envelope.allowed_actions.includes(action)
      && !envelope.blocked_actions.some((item) => item.action === action);
  }

  function isActionAllowed(subject, action) {
    const envelope = getCurrentStatusEnvelope(subject);
    return Boolean(envelope && actionAllowed(envelope, action));
  }

  function areActionsAllowed(requirements) {
    return requirements.every(([subject, action]) => isActionAllowed(subject, action));
  }

  function renderGateMatrix(payload) {
    const rows = SUBJECTS.map((subject) => {
      const envelope = payload.envelopes[subject];
      return `<tr class="${tokenClass(envelope)}"><th scope="row">${escapeHtml(SUBJECT_LABELS[subject])}</th><td>${renderStatusSummary(envelope)}</td><td>${envelope.reason_codes.length ? envelope.reason_codes.map((code) => `<code>${escapeHtml(code)}</code>`).join(" ") : "—"}</td><td>${envelope.blocked_actions.length}</td></tr>`;
    }).join("");
    return `<table class="status-envelope-matrix"><caption>各 subject 由 server 投影的 gate 狀態；UNAVAILABLE／NOT_EVALUATED 不可解讀為 0 或就緒。</caption><thead><tr><th scope="col">Subject</th><th scope="col">狀態</th><th scope="col">reason codes</th><th scope="col">阻擋動作</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderStatusEnvelopeCard(envelope) {
    return `<article class="status-envelope-card ${tokenClass(envelope)}" id="status-envelope-${escapeHtml(envelope.subject)}" data-subject="${escapeHtml(envelope.subject)}" data-digest="${escapeHtml(envelope.digest)}"><header class="status-envelope-card-head"><h3>${escapeHtml(SUBJECT_LABELS[envelope.subject])}</h3>${renderStatusSummary(envelope)}</header>${renderAdvisory(envelope)}${renderBlockerList(envelope)}${renderActions(envelope)}${renderProvenanceStrip(envelope)}</article>`;
  }

  function renderStaleSetSurfaces(message) {
    if (!statusEnvelopeSet) return;
    if (matrix) {
      matrix.innerHTML = `<p class="empty status-envelope-unavailable">⚠ 狀態不可用：${escapeHtml(message)}。保留最後有效 provenance；不可解讀為 current state。</p>`;
      matrix.setAttribute("aria-busy", "false");
    }
    if (cards) {
      cards.innerHTML = SUBJECTS.map((subject) => `<article class="status-envelope-card token-unavailable stale" data-subject="${escapeHtml(subject)}">${renderWorkspaceEnvelope(subject)}</article>`).join("");
    }
    renderedDigestKey = null;
  }

  function clearGlobalLiveRegions() {
    if (alertRegion) alertRegion.textContent = "";
    if (announcement) announcement.textContent = "";
  }

  function statusEventText(envelope) {
    return `${SUBJECT_LABELS[envelope.subject]}：${envelope.status_label}${envelope.reason_codes.length ? `，原因 ${envelope.reason_codes.join("、")}` : ""}`;
  }

  function arbitrateSetAnnouncements(payload) {
    const changed = SUBJECTS.filter((subject) => previousSetDigests[subject] !== payload.envelopes[subject].digest);
    clearGlobalLiveRegions();
    const assertive = changed.filter((subject) => payload.envelopes[subject].live_region === "assertive").map((subject) => statusEventText(payload.envelopes[subject]));
    const polite = changed.filter((subject) => payload.envelopes[subject].live_region === "polite").map((subject) => statusEventText(payload.envelopes[subject]));
    if (alertRegion && assertive.length) alertRegion.textContent = assertive.join("；");
    if (announcement && polite.length) announcement.textContent = polite.join("；");
    SUBJECTS.forEach((subject) => { previousSetDigests[subject] = payload.envelopes[subject].digest; });
  }

  function renderLastValidBanner() {
    if (!lastValidBanner) return;
    if (statusEnvelopeStale && statusEnvelopeSet) {
      lastValidBanner.textContent = `↻ 最後有效資料 · as of ${statusEnvelopeSet.as_of}；目前無法確認 server 狀態，所有依 current state 的操作停用。`;
      lastValidBanner.hidden = false;
      panel?.classList.add("stale");
    } else {
      lastValidBanner.textContent = "";
      lastValidBanner.hidden = true;
      panel?.classList.remove("stale");
    }
  }

  function renderTopbar(payload) {
    if (!topbar) return;
    const worst = ["CRITICAL", "UNAVAILABLE", "BLOCKED", "TERMINAL_FAILED", "DEGRADED", "NOT_EVALUATED", "RUNNING", "EMPTY", "TERMINAL_CANCELLED", "READY", "TERMINAL_SUCCESS"]
      .find((status) => SUBJECTS.some((subject) => payload.envelopes[subject].status === status));
    const count = SUBJECTS.filter((subject) => ["CRITICAL", "UNAVAILABLE", "BLOCKED", "TERMINAL_FAILED"].includes(payload.envelopes[subject].status)).length;
    topbar.className = `status status-envelope-topbar token-${worst.toLowerCase().replaceAll("_", "-")}${statusEnvelopeStale ? " stale" : ""}`;
    topbar.innerHTML = `<span class="status-dot" aria-hidden="true"></span>狀態信封 · ${count ? `${count} 個 subject 受阻` : "無阻擋"}${statusEnvelopeStale ? " · ↻ 最後有效" : ""}`;
  }

  function resolveMobilePolicy(payload) {
    const envelope = payload.envelopes.local_paper_runtime;
    const policy = envelope.client_policy;
    if (!hasExactKeys(policy, MOBILE_POLICY_KEYS)) return null;
    const advisory = envelope.advisory.find((item) => item.code === policy.reason_code);
    return advisory ? { ...policy, text: advisory.text, a11y: advisory.a11y, digest: envelope.digest } : null;
  }

  function describedByWithPolicy(node, add) {
    const ids = new Set((node.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
    if (add) ids.add("mobile-read-only-banner");
    else ids.delete("mobile-read-only-banner");
    if (ids.size) node.setAttribute("aria-describedby", [...ids].join(" "));
    else node.removeAttribute("aria-describedby");
  }

  function applyMobileReadOnlyPolicy() {
    const active = mobileQuery.matches;
    document.documentElement.classList.toggle("mobile-read-only", active);
    document.querySelectorAll(MOBILE_MUTATION_SELECTOR).forEach((node) => {
      if (active) {
        if (!node.hasAttribute("inert")) node.dataset.mobileReadOnlyAddedInert = "true";
        node.setAttribute("inert", "");
        node.dataset.mobileReadOnly = "true";
        describedByWithPolicy(node, true);
      } else if (node.dataset.mobileReadOnly === "true") {
        if (node.dataset.mobileReadOnlyAddedInert === "true") node.removeAttribute("inert");
        delete node.dataset.mobileReadOnlyAddedInert;
        delete node.dataset.mobileReadOnly;
        describedByWithPolicy(node, false);
      }
    });
    if (!mobileReadOnlyBanner || !mobileReadOnlyReason) return;
    if (active) {
      const fallback = {
        reason_code: "STATUS_ENVELOPE_UNAVAILABLE",
        a11y: "A-BLOCK",
        text: "狀態信封尚未可用；手機仍維持唯讀監看，所有變更操作已關閉。"
      };
      const visible = mobilePolicy || fallback;
      mobileReadOnlyReason.textContent = visible.text;
      mobileReadOnlyBanner.dataset.reasonCode = visible.reason_code;
      mobileReadOnlyBanner.dataset.a11y = visible.a11y;
      mobileReadOnlyBanner.hidden = false;
    } else {
      mobileReadOnlyBanner.hidden = true;
    }
  }

  function notify(event) {
    subscribers.forEach((listener) => listener(event));
  }

  function subscribe(listener) {
    subscribers.add(listener);
    return () => subscribers.delete(listener);
  }

  function renderStatusEnvelopes(payload) {
    statusEnvelopeSet = payload;
    statusEnvelopeStale = false;
    mobilePolicy = resolveMobilePolicy(payload);
    unavailableAnnounced = false;
    const digestKey = SUBJECTS.map((subject) => payload.envelopes[subject].digest).join("|");
    if (digestKey !== renderedDigestKey) {
      renderedDigestKey = digestKey;
      if (matrix) { matrix.innerHTML = renderGateMatrix(payload); matrix.setAttribute("aria-busy", "false"); }
      if (cards) cards.innerHTML = SUBJECTS.map((subject) => renderStatusEnvelopeCard(payload.envelopes[subject])).join("");
    } else {
      cards?.querySelectorAll("time").forEach((node, index) => {
        const envelope = payload.envelopes[SUBJECTS[index]];
        if (envelope) { node.dateTime = envelope.as_of; node.textContent = envelope.as_of; }
      });
    }
    arbitrateSetAnnouncements(payload);
    renderLastValidBanner();
    renderTopbar(payload);
    applyMobileReadOnlyPolicy();
    notify({ type: "set", payload });
  }

  function markStatusEnvelopesUnavailable(message) {
    statusEnvelopeStale = true;
    renderStaleSetSurfaces(message);
    renderLastValidBanner();
    if (statusEnvelopeSet) renderTopbar(statusEnvelopeSet);
    if (!statusEnvelopeSet && matrix) {
      matrix.innerHTML = `<p class="empty status-envelope-unavailable">⚠ 狀態不可用：${escapeHtml(message)}。尚無任何有效投影；不可解讀為 0、空或就緒。</p>`;
      matrix.setAttribute("aria-busy", "false");
    }
    if (!statusEnvelopeSet && topbar) {
      topbar.className = "status status-envelope-topbar token-unavailable";
      topbar.innerHTML = '<span class="status-dot" aria-hidden="true"></span>狀態信封 · ⚠ 不可用';
    }
    if (!unavailableAnnounced) {
      clearGlobalLiveRegions();
      if (alertRegion) alertRegion.textContent = "狀態信封不可用；所有依 current state 的操作停用。";
      unavailableAnnounced = true;
    }
    applyMobileReadOnlyPolicy();
    notify({ type: "unavailable", message });
  }

  function normalizedSetId(value) {
    const normalized = typeof value === "string" ? value.trim() : "";
    return normalized || null;
  }

  async function loadStatusEnvelopes(strategySetVersionId = currentStrategySetVersionId) {
    const requestedSetId = normalizedSetId(strategySetVersionId);
    if (requestedSetId !== currentStrategySetVersionId) currentStrategySetVersionId = requestedSetId;
    const generation = ++setRequestGeneration;
    try {
      const query = requestedSetId ? `?strategy_set_version_id=${encodeURIComponent(requestedSetId)}` : "";
      const response = await fetch(`/api/dashboard/status-envelopes${query}`, { cache: "no-store" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload && typeof payload.detail === "object" ? payload.detail.code || payload.detail.message : payload?.detail;
        throw new Error(detail || `HTTP ${response.status}`);
      }
      const validated = validateStatusEnvelopeSet(payload);
      await validateStatusEnvelopeDigests(validated);
      if (generation !== setRequestGeneration || requestedSetId !== currentStrategySetVersionId) return statusEnvelopeSet;
      const projectedSetId = validated.envelopes.formal_dataset.identity.strategy_set_version_id || null;
      if (projectedSetId !== requestedSetId) throw new Error("Formal Dataset strategy set identity 不符");
      renderStatusEnvelopes(validated);
      return statusEnvelopeSet;
    } catch (error) {
      if (generation === setRequestGeneration && requestedSetId === currentStrategySetVersionId) markStatusEnvelopesUnavailable(error.message || "unknown");
      throw error;
    }
  }

  function setStrategySetVersionId(strategySetVersionId, { load = true } = {}) {
    const next = normalizedSetId(strategySetVersionId);
    if (next === currentStrategySetVersionId) return load ? loadStatusEnvelopes(next) : Promise.resolve(statusEnvelopeSet);
    currentStrategySetVersionId = next;
    setRequestGeneration += 1;
    statusEnvelopeStale = true;
    renderStaleSetSurfaces("strategy set scope 已變更，等待 exact identity 投影");
    renderLastValidBanner();
    if (statusEnvelopeSet) renderTopbar(statusEnvelopeSet);
    notify({ type: "scope", strategySetVersionId: next });
    return load ? loadStatusEnvelopes(next) : Promise.resolve(statusEnvelopeSet);
  }

  function pollStatusEnvelopes() {
    if (document.visibilityState !== "visible") return;
    loadStatusEnvelopes(currentStrategySetVersionId).catch(() => {});
  }

  function entityKey(kind, entityId) {
    return `${kind}:${entityId}`;
  }

  function entityRecordForSubject(subject, entityId) {
    const kind = subject === "cost_snapshot" ? "backtest_run" : subject;
    return entityRecords.get(entityKey(kind, entityId)) || null;
  }

  function getEntityEnvelope(subject, entityId) {
    return entityRecordForSubject(subject, entityId)?.payload?.envelopes?.[subject] || null;
  }

  function getCurrentEntityEnvelope(subject, entityId) {
    const record = entityRecordForSubject(subject, entityId);
    return record && !record.stale ? record.payload.envelopes[subject] || null : null;
  }

  function isEntityActionAllowed(subject, entityId, action) {
    const envelope = getCurrentEntityEnvelope(subject, entityId);
    return Boolean(envelope && actionAllowed(envelope, action));
  }

  function renderEntityEnvelope(subject, entityId) {
    const record = entityRecordForSubject(subject, entityId);
    const envelope = record?.payload?.envelopes?.[subject];
    if (!envelope) return unavailableMarkup(`${SUBJECT_LABELS[subject] || subject} ${entityId}`);
    if (record.stale) {
      return `<div class="status-envelope-workspace token-unavailable stale" data-subject="${escapeHtml(subject)}" data-entity-id="${escapeHtml(entityId)}" data-digest="${escapeHtml(envelope.digest)}"><span class="status-envelope-summary token-unavailable"><span aria-hidden="true">⚠</span><span>狀態不可用</span></span><p class="status-envelope-stale-note">↻ 最後有效：${escapeHtml(envelope.status_label)}；entity current state 未驗證，操作停用。</p>${renderBlockerList(envelope)}${renderProvenanceStrip(envelope)}</div>`;
    }
    return `<div class="status-envelope-workspace ${tokenClass(envelope)}" data-subject="${escapeHtml(subject)}" data-entity-id="${escapeHtml(entityId)}" data-digest="${escapeHtml(envelope.digest)}">${renderEnvelopeBody(envelope)}</div>`;
  }

  function announceEntity(envelope, entityId) {
    const key = `${envelope.subject}:${entityId}:${envelope.digest}`;
    clearGlobalLiveRegions();
    if (announcedEntityEvents.has(key)) return;
    announcedEntityEvents.add(key);
    const target = envelope.live_region === "assertive" ? alertRegion : announcement;
    if (target) target.textContent = `${statusEventText(envelope)}，entity ${entityId}`;
  }

  async function loadEntityStatus(kind, entityId, { activate = true } = {}) {
    const config = ENTITY_CONFIG[kind];
    const normalizedId = typeof entityId === "string" ? entityId.trim() : "";
    if (!config || !normalizedId) throw new Error("entity kind/id 不合法");
    const key = entityKey(kind, normalizedId);
    const generation = (entityGenerations.get(key) || 0) + 1;
    entityGenerations.set(key, generation);
    if (activate) activeEntityIds.set(kind, normalizedId);
    try {
      const response = await fetch(config.route(normalizedId), { cache: "no-store" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload && typeof payload.detail === "object" ? payload.detail.code || payload.detail.message : payload?.detail;
        throw new Error(detail || `HTTP ${response.status}`);
      }
      const validated = validateStatusEnvelopeSet(payload, config.subjects);
      await validateStatusEnvelopeDigests(validated, config.subjects);
      if (entityGenerations.get(key) !== generation
        || (activate && activeEntityIds.get(kind) !== normalizedId)) return entityRecords.get(key)?.payload || null;
      if (validated.envelopes[config.identitySubject].identity[config.identityKey] !== normalizedId) throw new Error("entity envelope identity 不符");
      entityRecords.set(key, { payload: validated, stale: false, unavailableAnnounced: false });
      if (activate && activeEntityIds.get(kind) === normalizedId) announceEntity(validated.envelopes[config.identitySubject], normalizedId);
      notify({ type: "entity", kind, entityId: normalizedId, payload: validated });
      return validated;
    } catch (error) {
      if (entityGenerations.get(key) === generation) {
        const prior = entityRecords.get(key) || { payload: null, stale: true, unavailableAnnounced: false };
        prior.stale = true;
        if (!prior.unavailableAnnounced && activate && activeEntityIds.get(kind) === normalizedId) {
          clearGlobalLiveRegions();
          if (alertRegion) alertRegion.textContent = `${SUBJECT_LABELS[config.identitySubject]} ${normalizedId} 狀態不可用；操作已停用。`;
          prior.unavailableAnnounced = true;
        }
        entityRecords.set(key, prior);
        notify({ type: "entity-unavailable", kind, entityId: normalizedId, message: error.message || "unknown" });
      }
      throw error;
    }
  }

  function isStatusEnvelopeStale() {
    return statusEnvelopeStale;
  }

  mobileQuery.addEventListener?.("change", applyMobileReadOnlyPolicy);
  if (typeof MutationObserver !== "undefined" && document.body) {
    new MutationObserver(applyMobileReadOnlyPolicy).observe(document.body, { childList: true, subtree: true });
  }
  applyMobileReadOnlyPolicy();

  return {
    SUBJECTS,
    validateSignedValue,
    canonicalJson,
    sha256,
    validateStatusEnvelope,
    validateStatusEnvelopeSet,
    validateStatusEnvelopeDigests,
    renderStatusSummary,
    renderBlockerList,
    renderProvenanceStrip,
    renderWorkspaceEnvelope,
    renderInlineStatus,
    renderGateMatrix,
    renderStatusEnvelopes,
    markStatusEnvelopesUnavailable,
    loadStatusEnvelopes,
    pollStatusEnvelopes,
    setStrategySetVersionId,
    getStatusEnvelope,
    getCurrentStatusEnvelope,
    isActionAllowed,
    areActionsAllowed,
    loadEntityStatus,
    getEntityEnvelope,
    getCurrentEntityEnvelope,
    isEntityActionAllowed,
    renderEntityEnvelope,
    isStatusEnvelopeStale,
    subscribe,
    applyMobileReadOnlyPolicy
  };
}
