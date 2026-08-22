import { createMutationKeyStore } from "../mutation_keys.js?v=20260821-atomic-strategy-v2";

export function createBacktestWorkspace(context) {
  const { state, escapeHtml, formatNumber, newIdempotencyKey, setWorkspace } = context;
  const strategyToggle = document.getElementById("strategy-toggle");
  const strategyCatalogDrawer = document.getElementById("strategy-catalog-drawer");
  const strategyCatalogPanel = document.getElementById("strategy-catalog-panel");
  const strategyCatalogRole = document.getElementById("strategy-catalog-role");
  const strategyCatalogPhase = document.getElementById("strategy-catalog-phase");
  const strategyCatalogStatus = document.getElementById("strategy-catalog-status");
  const strategyCatalogNotice = document.getElementById("strategy-catalog-notice");
  const strategyCatalogList = document.getElementById("strategy-catalog-list");
  const strategyTemplateList = document.getElementById("strategy-template-list");
  const strategyDraftForm = document.getElementById("strategy-draft-form");
  const strategyParameterFields = document.getElementById("strategy-parameter-fields");
  const strategyChangeNote = document.getElementById("strategy-change-note");
  const strategyDraftSave = document.getElementById("strategy-draft-save");
  const strategyDraftValidate = document.getElementById("strategy-draft-validate");
  const strategyDraftPublish = document.getElementById("strategy-draft-publish");
  const strategyDraftMessage = document.getElementById("strategy-draft-message");
  const strategyDraftList = document.getElementById("strategy-draft-list");
  const strategyVersionList = document.getElementById("strategy-version-list");
  const strategyVersionLeft = document.getElementById("strategy-version-left");
  const strategyVersionRight = document.getElementById("strategy-version-right");
  const strategyVersionCompare = document.getElementById("strategy-version-compare");
  const strategyVersionDiff = document.getElementById("strategy-version-diff");
  const strategySetForm = document.getElementById("strategy-set-form");
  const strategySetName = document.getElementById("strategy-set-name");
  const strategySetPolicy = document.getElementById("strategy-set-policy");
  const strategySetMinimum = document.getElementById("strategy-set-minimum");
  const strategySetChangeNote = document.getElementById("strategy-set-change-note");
  const strategySetMembers = document.getElementById("strategy-set-members");
  const strategySetMessage = document.getElementById("strategy-set-message");
  const strategySetList = document.getElementById("strategy-set-list");
  const strategyAuditList = document.getElementById("strategy-audit-list");
  const backtestToggle = document.getElementById("backtest-toggle");
  const backtestDrawer = document.getElementById("backtest-drawer");
  const backtestPanel = document.getElementById("backtest-panel");
  const backtestNotice = document.getElementById("backtest-notice");
  const backtestIncrementalStatus = document.getElementById("backtest-incremental-status");
  const backtestSyncButton = document.getElementById("backtest-sync");
  const backtestRefreshButton = document.getElementById("backtest-refresh");
  const backtestSyncYears = document.getElementById("backtest-sync-years");
  const backtestDatasetList = document.getElementById("backtest-dataset-list");
  const backtestDataset = document.getElementById("backtest-dataset");
  const backtestRunForm = document.getElementById("backtest-run-form");
  const backtestRunSubmit = document.getElementById("backtest-run-submit");
  const backtestFormMessage = document.getElementById("backtest-form-message");
  const backtestRunList = document.getElementById("backtest-run-list");
  const backtestRunCount = document.getElementById("backtest-run-count");
  const backtestResult = document.getElementById("backtest-result");
  const backtestCloneButton = document.getElementById("backtest-clone");
  const backtestCompareButton = document.getElementById("backtest-compare");
  const backtestBaseline = document.getElementById("backtest-baseline");
  const backtestChallenger = document.getElementById("backtest-challenger");
  const backtestComparison = document.getElementById("backtest-comparison");
  const qualificationForm = document.getElementById("backtest-qualification-form");
  const qualificationFolds = document.getElementById("qualification-folds");
  const qualificationAddFold = document.getElementById("qualification-add-fold");
  const qualificationSubmit = document.getElementById("qualification-submit");
  const qualificationMessage = document.getElementById("qualification-message");
  const qualificationResult = document.getElementById("qualification-result");
  const qualificationList = document.getElementById("qualification-list");
  const atomicBacktestForm = document.getElementById("atomic-backtest-form");
  const atomicBacktestSet = document.getElementById("atomic-backtest-set");
  const atomicBacktestDataset = document.getElementById("atomic-backtest-dataset");
  const atomicBacktestBaseline = document.getElementById("atomic-backtest-baseline");
  const atomicBacktestSubmit = document.getElementById("atomic-backtest-submit");
  const atomicBacktestMessage = document.getElementById("atomic-backtest-message");
  const pendingAtomicMutationKeys = createMutationKeyStore(newIdempotencyKey);
  let qualificationFoldSequence = 0;

      function formatBacktestPercent(value, digits = 2) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
        return `${formatNumber(Number(value) * 100, digits)}%`;
      }

      function backtestStatusLabel(value) {
        return {
          QUEUED: "排隊中", PREFLIGHT: "預檢中", RUNNING: "執行中", CANCELLING: "取消中",
          COMPLETED: "已完成", CANCELLED: "已取消", FAILED: "失敗"
        }[value] || value || "—";
      }

      async function backtestFetch(path, options = {}) {
        const response = await fetch(path, { cache: "no-store", ...options });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = typeof payload.detail === "object" ? payload.detail.message || payload.detail.code : payload.detail;
          const error = new Error(detail || `HTTP ${response.status}`);
          error.httpStatus = response.status;
          throw error;
        }
        return payload;
      }

      async function atomicMutation(path, method, body = null, keyPrefix = "strategy") {
        if (!state.strategyCatalog.csrfToken) throw new Error("策略管理安全狀態尚未就緒，請重新整理。");
        const operationSignature = `${method}:${path}:${JSON.stringify(body)}`;
        const key = pendingAtomicMutationKeys.keyFor(operationSignature, keyPrefix);
        const requestBody = body === null ? null : { ...body };
        if (requestBody && Object.hasOwn(requestBody, "idempotency_key") && !requestBody.idempotency_key) {
          requestBody.idempotency_key = key;
        }
        const headers = {
          "X-Strategy-CSRF": state.strategyCatalog.csrfToken,
          "Idempotency-Key": key
        };
        if (requestBody !== null) headers["Content-Type"] = "application/json";
        try {
          const payload = await backtestFetch(path, {
            method,
            headers,
            body: requestBody === null ? undefined : JSON.stringify(requestBody)
          });
          pendingAtomicMutationKeys.complete(operationSignature);
          return payload;
        } catch (error) {
          pendingAtomicMutationKeys.failed(operationSignature, error.httpStatus);
          throw error;
        }
      }

      const strategyRoleLabels = { CANDIDATE: "候選", SCORE: "評分", SIGNAL: "訊號", ENTRY: "買入", EXIT: "賣出" };
      const strategyPhaseLabels = { PRE_MARKET: "盤前", OPENING: "開盤", INTRADAY: "盤中", END_OF_DAY: "收盤", POSITION_LIFECYCLE: "持倉生命週期", ALL_SESSION: "全時段" };
      const strategyStatusLabels = { ACTIVE: "啟用", EXPERIMENTAL: "實驗中", DRAFT: "草稿", DEPRECATED: "已淘汰", ARCHIVED: "封存" };

      function setStrategyCatalogDrawer(open) {
        if (open) setWorkspace("strategy");
        else setWorkspace("overview");
        strategyCatalogDrawer.classList.toggle("open", open);
        strategyCatalogDrawer.setAttribute("aria-hidden", String(!open));
        strategyToggle.setAttribute("aria-expanded", String(open));
        if (open) {
          requestAnimationFrame(() => strategyCatalogPanel.focus());
        } else {
          strategyToggle.focus();
        }
      }

      function selectedAtomicTemplate() {
        return state.strategyCatalog.templates.find((item) => item.strategy_id === state.strategyCatalog.selectedTemplateId) || null;
      }

      function activeAtomicDraft() {
        return state.strategyCatalog.drafts.find((item) => item.draft_id === state.strategyCatalog.activeDraftId) || null;
      }

      function renderAtomicTemplates() {
        const templates = state.strategyCatalog.templates;
        if (!templates.length) {
          strategyTemplateList.innerHTML = '<p class="backtest-empty">目前沒有已部署的原子策略。</p>';
          return;
        }
        strategyTemplateList.innerHTML = templates.map((template) => `
          <button class="strategy-template-button ${template.strategy_id === state.strategyCatalog.selectedTemplateId ? "selected" : ""}" type="button" data-atomic-template="${escapeHtml(template.strategy_id)}">
            <strong>${escapeHtml(template.display_name_zh_tw)}</strong>
            <span>${escapeHtml(strategyRoleLabels[template.role] || template.role)} · ${escapeHtml(strategyPhaseLabels[template.session_phase] || template.session_phase)} · ${escapeHtml(template.description_zh_tw)}</span>
            <span>需要資料：${escapeHtml((template.required_capabilities || []).join("、"))}</span>
          </button>
        `).join("");
        strategyTemplateList.querySelectorAll("[data-atomic-template]").forEach((button) => {
          button.addEventListener("click", () => {
            state.strategyCatalog.selectedTemplateId = button.dataset.atomicTemplate;
            state.strategyCatalog.activeDraftId = null;
            strategyChangeNote.value = "";
            renderAtomicManagement();
          });
        });
      }

      function parameterInput(template, name, specification, value) {
        const id = `strategy-parameter-${name}`;
        const label = specification.label || name;
        const required = specification.required === false ? "" : "required";
        const data = `data-strategy-parameter="${escapeHtml(name)}" data-parameter-type="${escapeHtml(specification.type)}"`;
        let control;
        if (specification.type === "boolean") {
          control = `<select id="${id}" ${data}><option value="true" ${value === true ? "selected" : ""}>是</option><option value="false" ${value === false ? "selected" : ""}>否</option></select>`;
        } else if (Array.isArray(specification.enum)) {
          control = `<select id="${id}" ${data}>${specification.enum.map((item) => `<option value="${escapeHtml(item)}" ${String(value) === String(item) ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select>`;
        } else {
          const inputType = specification.type === "time" ? "time" : ["integer", "decimal"].includes(specification.type) ? "number" : "text";
          const step = specification.type === "integer" ? "1" : specification.type === "decimal" ? "any" : null;
          control = `<input id="${id}" type="${inputType}" ${data} value="${escapeHtml(value ?? "")}" ${required} ${step ? `step="${step}"` : ""} ${specification.minimum !== undefined ? `min="${escapeHtml(specification.minimum)}"` : ""} ${specification.maximum !== undefined ? `max="${escapeHtml(specification.maximum)}"` : ""}>`;
        }
        const constraints = [
          specification.unit ? `單位 ${specification.unit}` : "",
          specification.minimum !== undefined ? `最小 ${specification.minimum}` : "",
          specification.maximum !== undefined ? `最大 ${specification.maximum}` : ""
        ].filter(Boolean).join(" · ");
        return `<div class="backtest-field"><label for="${id}">${escapeHtml(label)}</label>${control}<span class="strategy-parameter-help">${escapeHtml(constraints)}</span></div>`;
      }

      function renderAtomicParameterEditor() {
        const template = selectedAtomicTemplate();
        const draft = activeAtomicDraft();
        if (!template) {
          strategyParameterFields.innerHTML = '<p class="backtest-empty">請先選擇策略。</p>';
          strategyDraftSave.disabled = true;
          strategyDraftValidate.disabled = true;
          strategyDraftPublish.disabled = true;
          return;
        }
        const fields = template.parameter_schema?.fields || {};
        const values = draft?.parameters || Object.fromEntries(Object.entries(fields).map(([name, spec]) => [name, spec.default]));
        strategyParameterFields.innerHTML = `<div class="strategy-parameter-grid">${Object.entries(fields).map(([name, spec]) => parameterInput(template, name, spec, values[name])).join("")}</div>`;
        const editable = !draft?.is_sealed;
        strategyDraftSave.disabled = !editable;
        strategyDraftSave.textContent = draft ? "儲存草稿" : "建立草稿";
        strategyDraftValidate.disabled = !draft || draft.is_sealed;
        strategyDraftPublish.disabled = !draft || draft.is_sealed;
        strategyChangeNote.value = draft?.change_note || strategyChangeNote.value;
      }

      function readAtomicParameters() {
        const parameters = {};
        strategyParameterFields.querySelectorAll("[data-strategy-parameter]").forEach((input) => {
          const type = input.dataset.parameterType;
          let value = input.value;
          if (type === "integer") value = Number.parseInt(value, 10);
          if (type === "boolean") value = value === "true";
          parameters[input.dataset.strategyParameter] = value;
        });
        return parameters;
      }

      function renderAtomicDrafts() {
        const drafts = state.strategyCatalog.drafts;
        strategyDraftList.innerHTML = drafts.length ? drafts.map((draft) => `
          <button class="backtest-list-item ${draft.draft_id === state.strategyCatalog.activeDraftId ? "selected" : ""}" type="button" data-atomic-draft="${escapeHtml(draft.draft_id)}">
            <strong>${escapeHtml(state.strategyCatalog.templates.find((item) => item.strategy_id === draft.strategy_id)?.display_name_zh_tw || draft.strategy_id)}</strong>
            <span>修訂 ${draft.revision} · ${draft.is_sealed ? "已發布，不可修改" : "可修改草稿"}</span>
            <span>${escapeHtml(draft.change_note || "沒有調整說明")}</span>
          </button>
        `).join("") : '<p class="backtest-empty">目前沒有草稿。</p>';
        strategyDraftList.querySelectorAll("[data-atomic-draft]").forEach((button) => {
          button.addEventListener("click", () => {
            const draft = state.strategyCatalog.drafts.find((item) => item.draft_id === button.dataset.atomicDraft);
            state.strategyCatalog.activeDraftId = draft?.draft_id || null;
            state.strategyCatalog.selectedTemplateId = draft?.strategy_id || null;
            strategyDraftMessage.textContent = draft?.is_sealed ? "這份草稿已發布；如要調整，請從已發布版本複製新草稿。" : "已載入草稿。";
            renderAtomicManagement();
          });
        });
      }

      function renderAtomicVersions() {
        const versions = state.strategyCatalog.versions;
        strategyVersionList.innerHTML = versions.length ? versions.map((version) => `
          <article class="strategy-catalog-card">
            <div class="strategy-catalog-card-heading"><strong>${escapeHtml(state.strategyCatalog.templates.find((item) => item.strategy_id === version.strategy_id)?.display_name_zh_tw || version.strategy_id)} v${version.version_number}</strong><span>${escapeHtml(version.configuration_digest.slice(0, 10))}</span></div>
            <p class="strategy-catalog-description">${escapeHtml(version.change_note || "沒有發布說明")}</p>
            <div class="strategy-catalog-parameters">${escapeHtml(JSON.stringify(version.parameters, null, 2))}</div>
            <div class="backtest-actions"><button class="backtest-button secondary" type="button" data-clone-version="${escapeHtml(version.strategy_version_id)}">複製成新草稿</button></div>
          </article>
        `).join("") : '<p class="backtest-empty">目前沒有已發布版本。</p>';
        strategyVersionList.querySelectorAll("[data-clone-version]").forEach((button) => {
          button.addEventListener("click", () => cloneAtomicVersion(button.dataset.cloneVersion));
        });
        const options = versions.map((version) => `<option value="${escapeHtml(version.strategy_version_id)}">${escapeHtml(state.strategyCatalog.templates.find((item) => item.strategy_id === version.strategy_id)?.display_name_zh_tw || version.strategy_id)} v${version.version_number}</option>`).join("");
        strategyVersionLeft.innerHTML = options || '<option value="">尚無版本</option>';
        strategyVersionRight.innerHTML = options || '<option value="">尚無版本</option>';
        if (versions.length > 1) strategyVersionRight.value = versions[1].strategy_version_id;
        strategyVersionCompare.disabled = versions.length < 2;
      }

      async function compareAtomicVersions() {
        if (!strategyVersionLeft.value || !strategyVersionRight.value || strategyVersionLeft.value === strategyVersionRight.value) {
          strategyVersionDiff.innerHTML = '<p class="backtest-empty">請選擇兩個不同的已發布版本。</p>';
          return;
        }
        try {
          const payload = await backtestFetch(`/api/strategy-versions/${encodeURIComponent(strategyVersionLeft.value)}/diff/${encodeURIComponent(strategyVersionRight.value)}`);
          const changes = payload.diff?.changes || [];
          strategyVersionDiff.innerHTML = changes.length
            ? `<div class="strategy-catalog-parameters">${changes.map((item) => `${escapeHtml(item.parameter)}：${escapeHtml(JSON.stringify(item.left))} → ${escapeHtml(JSON.stringify(item.right))}`).join("\n")}</div>`
            : '<p class="backtest-empty">兩個版本的參數相同。</p>';
        } catch (error) {
          strategyVersionDiff.innerHTML = `<p class="backtest-empty">版本比較失敗：${escapeHtml(error.message)}</p>`;
        }
      }

      function renderAtomicAuditEvents() {
        const events = state.strategyCatalog.auditEvents || [];
        strategyAuditList.innerHTML = events.length ? events.map((event) => `
          <article class="strategy-catalog-card">
            <div class="strategy-catalog-card-heading"><strong>${escapeHtml(event.action)}</strong><span>${escapeHtml(event.outcome)}</span></div>
            <p class="strategy-catalog-description">${escapeHtml(event.resource_type)} · ${escapeHtml(event.resource_id)} · ${escapeHtml(event.actor_id)}</p>
            <p class="strategy-catalog-description">${escapeHtml(event.change_note || "沒有說明")} · ${escapeHtml(event.occurred_at)}</p>
          </article>
        `).join("") : '<p class="backtest-empty">目前沒有 Audit 紀錄。</p>';
      }

      function renderAtomicSetBuilder() {
        const versions = state.strategyCatalog.versions.filter((version) => {
          const template = state.strategyCatalog.templates.find((item) => item.strategy_id === version.strategy_id);
          return template?.role === "ENTRY";
        });
        strategySetMembers.innerHTML = versions.length ? versions.map((version, index) => `
          <label class="strategy-option"><input type="checkbox" data-strategy-set-version="${escapeHtml(version.strategy_version_id)}" value="${escapeHtml(version.strategy_version_id)}"><span><strong>${escapeHtml(state.strategyCatalog.templates.find((item) => item.strategy_id === version.strategy_id)?.display_name_zh_tw || version.strategy_id)} v${version.version_number}</strong><span>${escapeHtml(JSON.stringify(version.parameters))}</span></span></label>
        `).join("") : '<p class="backtest-empty">請先發布買入策略版本。</p>';
        const sets = state.strategyCatalog.strategySets;
        strategySetList.innerHTML = sets.length ? sets.map((set) => `
          <article class="strategy-catalog-card"><div class="strategy-catalog-card-heading"><strong>${escapeHtml(set.display_name_zh_tw)}</strong><span>${escapeHtml(set.policy)}</span></div><p class="strategy-catalog-description">${set.members.length} 個精確版本 · ${escapeHtml(set.snapshot_digest.slice(0, 12))}</p></article>
        `).join("") : '<p class="backtest-empty">目前沒有策略組合。</p>';
      }

      function renderAtomicLauncherOptions() {
        const datasetOptions = state.backtest.datasets.map((dataset) => `<option value="${escapeHtml(dataset.dataset_id)}">${escapeHtml(dataset.dataset_id.slice(0, 18))}… · ${escapeHtml(dataset.start_date)} ～ ${escapeHtml(dataset.end_date)}</option>`).join("");
        atomicBacktestDataset.innerHTML = datasetOptions || '<option value="">請先建立 READY 資料集</option>';
        atomicBacktestSet.innerHTML = state.strategyCatalog.strategySets.length
          ? state.strategyCatalog.strategySets.map((set) => `<option value="${escapeHtml(set.strategy_set_version_id)}">${escapeHtml(set.display_name_zh_tw)} · ${escapeHtml(set.policy)} · ${set.members.length} 個版本</option>`).join("")
          : '<option value="">請先到策略管理建立組合</option>';
        atomicBacktestSubmit.disabled = !state.strategyCatalog.atomicAvailable || !state.strategyCatalog.strategySets.length || !state.backtest.datasets.length;
      }

      function renderAtomicManagement() {
        renderAtomicTemplates();
        renderAtomicParameterEditor();
        renderAtomicDrafts();
        renderAtomicVersions();
        renderAtomicSetBuilder();
        renderAtomicAuditEvents();
        renderAtomicLauncherOptions();
      }

      function renderStrategyCatalog() {
        const strategies = state.strategyCatalog.strategies;
        if (!strategies.length) {
          strategyCatalogList.innerHTML = '<p class="backtest-empty">目前沒有符合篩選條件的策略。</p>';
          return;
        }
        strategyCatalogList.innerHTML = strategies.map((strategy) => {
          const role = strategyRoleLabels[strategy.role] || strategy.role || "—";
          const phase = strategyPhaseLabels[strategy.session_phase] || strategy.session_phase || "—";
          const status = strategyStatusLabels[strategy.status] || strategy.status || "—";
          const statusClass = String(strategy.status || "").toLowerCase();
          const parameters = JSON.stringify(strategy.parameters || {}, null, 2);
          return `
            <article class="strategy-catalog-card">
              <div class="strategy-catalog-card-heading"><strong>${escapeHtml(strategy.display_name_zh_tw)}</strong><span>${escapeHtml(strategy.strategy_id)} · ${escapeHtml(strategy.version)}</span></div>
              <div class="strategy-catalog-badges"><span class="strategy-catalog-badge">${escapeHtml(role)}</span><span class="strategy-catalog-badge">${escapeHtml(phase)}</span><span class="strategy-catalog-badge ${statusClass}">${escapeHtml(status)}</span></div>
              <p class="strategy-catalog-description">${escapeHtml(strategy.description_zh_tw || "尚未填寫策略說明")}</p>
              <div class="strategy-catalog-details"><span>執行 binding：<strong>${escapeHtml(strategy.execution_binding || "僅 metadata／尚未接線")}</strong></span><span>資料來源：<strong>${escapeHtml(strategy.source || "—")}</strong></span><span>能力：<strong>${escapeHtml((strategy.required_capabilities || []).join("、") || "—")}</strong></span><span>版本摘要：<strong title="${escapeHtml(strategy.definition_digest || "")}">${escapeHtml((strategy.definition_digest || "").slice(0, 12) || "—")}</strong></span></div>
              <div class="strategy-catalog-parameters">${escapeHtml(parameters)}</div>
            </article>
          `;
        }).join("");
      }

      async function refreshStrategyCatalog() {
        if (state.strategyCatalog.loading) return;
        state.strategyCatalog.loading = true;
        strategyCatalogNotice.textContent = "正在讀取原子策略、草稿與版本…";
        const query = new URLSearchParams();
        if (strategyCatalogRole.value) query.set("role", strategyCatalogRole.value);
        if (strategyCatalogPhase.value) query.set("session_phase", strategyCatalogPhase.value);
        if (strategyCatalogStatus.value) query.set("status", strategyCatalogStatus.value);
        try {
          const capabilities = await backtestFetch("/api/atomic-strategies/capabilities");
          state.strategyCatalog.atomicAvailable = Boolean(capabilities.available);
          state.strategyCatalog.csrfToken = capabilities.csrf_token || null;
          if (!capabilities.available) throw new Error(capabilities.message || "PostgreSQL 原子策略管理目前不可用");
          const [templates, drafts, versions, sets, audits, legacy] = await Promise.all([
            backtestFetch("/api/strategy-templates"),
            backtestFetch("/api/strategy-versions/drafts"),
            backtestFetch("/api/strategy-versions"),
            backtestFetch("/api/strategy-sets"),
            backtestFetch("/api/strategy-audit-events?limit=100"),
            backtestFetch(`/api/strategies${query.toString() ? `?${query.toString()}` : ""}`)
          ]);
          state.strategyCatalog.templates = templates.templates || [];
          state.strategyCatalog.drafts = drafts.drafts || [];
          state.strategyCatalog.versions = versions.versions || [];
          state.strategyCatalog.strategySets = sets.strategy_sets || [];
          state.strategyCatalog.auditEvents = audits.audit_events || [];
          state.strategyCatalog.strategies = legacy.strategies || [];
          if (!state.strategyCatalog.selectedTemplateId && state.strategyCatalog.templates.length) {
            state.strategyCatalog.selectedTemplateId = state.strategyCatalog.templates[0].strategy_id;
          }
          strategyCatalogNotice.textContent = `${state.strategyCatalog.templates.length} 個原子策略 · ${state.strategyCatalog.drafts.length} 份草稿 · ${state.strategyCatalog.versions.length} 個已發布版本。${capabilities.safety}`;
          renderAtomicManagement();
          renderStrategyCatalog();
        } catch (error) {
          state.strategyCatalog.atomicAvailable = false;
          strategyCatalogNotice.textContent = `原子策略管理不可用：${error.message}`;
          strategyTemplateList.innerHTML = '<p class="backtest-empty">需要 PostgreSQL 才能管理原子策略；不會退回 SQLite。</p>';
          renderAtomicLauncherOptions();
        } finally {
          state.strategyCatalog.loading = false;
        }
      }

      async function submitAtomicDraft(event) {
        event.preventDefault();
        const template = selectedAtomicTemplate();
        const draft = activeAtomicDraft();
        if (!template) return;
        strategyDraftSave.disabled = true;
        strategyDraftMessage.textContent = draft ? "正在儲存草稿…" : "正在建立草稿…";
        try {
          const body = {
            parameters: readAtomicParameters(),
            actor_id: "local-researcher",
            change_note: strategyChangeNote.value.trim()
          };
          const payload = draft
            ? await atomicMutation(`/api/strategy-versions/drafts/${encodeURIComponent(draft.draft_id)}`, "PUT", { ...body, expected_revision: draft.revision }, "draft-update")
            : await atomicMutation("/api/strategy-versions/drafts", "POST", { ...body, strategy_id: template.strategy_id }, "draft-create");
          state.strategyCatalog.activeDraftId = payload.draft.draft_id;
          strategyDraftMessage.textContent = `草稿已保存，修訂 ${payload.draft.revision}。`;
          await refreshStrategyCatalog();
        } catch (error) {
          strategyDraftMessage.textContent = `草稿保存失敗：${error.message}`;
        } finally {
          strategyDraftSave.disabled = false;
        }
      }

      async function validateAtomicDraft() {
        const draft = activeAtomicDraft();
        if (!draft) return;
        try {
          const payload = await atomicMutation(`/api/strategy-versions/drafts/${encodeURIComponent(draft.draft_id)}/validate`, "POST", null, "draft-validate");
          strategyDraftMessage.textContent = `驗證通過：Schema ${payload.parameter_schema_version}，目前修訂 ${payload.revision}。發布時仍會在同一資料庫 transaction 重新驗證。`;
        } catch (error) {
          strategyDraftMessage.textContent = `驗證失敗：${error.message}`;
        }
      }

      async function publishAtomicDraft() {
        const draft = activeAtomicDraft();
        if (!draft) return;
        strategyDraftPublish.disabled = true;
        try {
          const payload = await atomicMutation(`/api/strategy-versions/drafts/${encodeURIComponent(draft.draft_id)}/publish`, "POST", {
            expected_draft_revision: draft.revision,
            actor_id: "local-researcher",
            actor_session_id: "local-dashboard",
            change_note: strategyChangeNote.value.trim()
          }, "draft-publish");
          strategyDraftMessage.textContent = `已發布不可變版本 v${payload.publish.version_number}。`;
          await refreshStrategyCatalog();
        } catch (error) {
          strategyDraftMessage.textContent = `發布失敗：${error.message}`;
        } finally {
          strategyDraftPublish.disabled = false;
        }
      }

      async function cloneAtomicVersion(versionId) {
        try {
          const payload = await atomicMutation(`/api/strategy-versions/${encodeURIComponent(versionId)}/clone`, "POST", {
            actor_id: "local-researcher",
            change_note: strategyChangeNote.value.trim() || "從已發布版本複製"
          }, "version-clone");
          state.strategyCatalog.activeDraftId = payload.draft.draft_id;
          state.strategyCatalog.selectedTemplateId = payload.draft.strategy_id;
          strategyDraftMessage.textContent = "已複製成可修改的新草稿。";
          await refreshStrategyCatalog();
        } catch (error) {
          strategyDraftMessage.textContent = `複製失敗：${error.message}`;
        }
      }

      async function submitAtomicStrategySet(event) {
        event.preventDefault();
        const selected = [...strategySetMembers.querySelectorAll("[data-strategy-set-version]:checked")]
          .map((input) => state.strategyCatalog.versions.find((version) => version.strategy_version_id === input.value))
          .filter(Boolean);
        if (!selected.length) {
          strategySetMessage.textContent = "請至少選擇一個已發布版本。";
          return;
        }
        const minimum = strategySetPolicy.value === "AT_LEAST_N" ? Number(strategySetMinimum.value) : 1;
        if (!Number.isInteger(minimum) || minimum < 1 || minimum > selected.length) {
          strategySetMessage.textContent = `至少觸發數必須介於 1 與 ${selected.length}。`;
          return;
        }
        try {
          const payload = await atomicMutation("/api/strategy-sets", "POST", {
            display_name_zh_tw: strategySetName.value.trim(),
            stage: "ENTRY",
            policy: strategySetPolicy.value,
            minimum_trigger_count: minimum,
            actor_id: "local-researcher",
            change_note: strategySetChangeNote.value.trim(),
            members: selected.map((version, index) => ({
              strategy_version_id: version.strategy_version_id,
              strategy_id: version.strategy_id,
              configuration_digest: version.configuration_digest,
              implementation_digest: version.implementation_digest,
              member_order: index,
              attribution_priority: index
            }))
          }, "strategy-set-create");
          strategySetMessage.textContent = `策略組合「${payload.strategy_set.display_name_zh_tw}」已保存。`;
          strategySetName.value = "";
          strategySetChangeNote.value = "";
          await refreshStrategyCatalog();
        } catch (error) {
          strategySetMessage.textContent = `策略組合建立失敗：${error.message}`;
        }
      }

      function selectedBacktestStrategies(side) {
        return [...document.querySelectorAll(`[data-backtest-strategy="${side}"]:checked`)]
          .map((input) => input.value);
      }

      function syncBacktestStrategyControls(side) {
        const prefix = side === "ENTRY" ? "entry" : "exit";
        const label = side === "ENTRY" ? "買入" : "賣出";
        const selectedCount = selectedBacktestStrategies(side).length;
        const policy = document.getElementById(`backtest-${prefix}-policy`);
        const minimum = document.getElementById(`backtest-${prefix}-min`);
        const count = document.getElementById(`backtest-${prefix}-count`);
        count.textContent = selectedCount === 0
          ? "尚未選擇"
          : selectedCount === 1 ? "已選 1 個 · 單一策略" : `已選 ${selectedCount} 個 · 多策略`;
        minimum.max = String(Math.max(1, selectedCount));
        if (Number(minimum.value) > Math.max(1, selectedCount)) minimum.value = String(Math.max(1, selectedCount));
        minimum.disabled = policy.value !== "AT_LEAST_N";
        minimum.setAttribute("aria-label", `${label}至少觸發策略數`);
        syncDailySmaExitWarning();
      }

      function syncDailySmaExitWarning() {
        const warning = document.getElementById("backtest-daily-sma-warning");
        if (!warning) return;
        const dailySmaIds = new Set([
          "sma_20_60_golden_cross_entry_v1",
          "sma_20_60_death_cross_exit_v1"
        ]);
        const selected = [
          ...selectedBacktestStrategies("ENTRY"),
          ...selectedBacktestStrategies("EXIT")
        ];
        const hasDailySma = selected.some((strategyId) => dailySmaIds.has(strategyId));
        const hasEodExit = selected.includes("end_of_day_exit_v1");
        warning.hidden = !(hasDailySma && hasEodExit);
        warning.textContent = hasDailySma && hasEodExit
          ? "提醒：EOD exit 會在每個日 K 收盤平倉，可能不符合 MA 趨勢持有；這不會自動變更你選擇的策略。"
          : "";
      }

      function validateBacktestStrategyPolicy(side, selected) {
        const prefix = side === "ENTRY" ? "entry" : "exit";
        const label = side === "ENTRY" ? "買入" : "賣出";
        const policy = document.getElementById(`backtest-${prefix}-policy`).value;
        const minimum = Number(document.getElementById(`backtest-${prefix}-min`).value);
        if (!selected.length) throw new Error(`請至少選擇一個${label}策略。`);
        if (policy === "AT_LEAST_N" && (!Number.isInteger(minimum) || minimum < 1 || minimum > selected.length)) {
          throw new Error(`${label}的 N 必須介於 1 與已選策略數量 ${selected.length}。`);
        }
      }

      function setBacktestDrawer(open) {
        if (open) setWorkspace("backtest");
        else setWorkspace("overview");
        backtestDrawer.classList.toggle("open", open);
        backtestDrawer.setAttribute("aria-hidden", String(!open));
        backtestToggle.setAttribute("aria-expanded", String(open));
        if (open) {
          requestAnimationFrame(() => backtestPanel.focus());
        } else {
          backtestToggle.focus();
        }
      }

      function renderBacktestNotice() {
        const capabilities = state.backtest.capabilities;
        if (!capabilities) return;
        const providerWarning = capabilities.provider_supports_kbars
          ? "可由目前資料 Provider 準備 Kbar。"
          : "目前資料 Provider 不支援歷史 Kbar；可改用已匯入資料集。";
        backtestNotice.innerHTML = `<strong>${escapeHtml(capabilities.database)}</strong> 保存 immutable run、策略版本與交易紀錄。${escapeHtml(providerWarning)}<br>${escapeHtml(capabilities.safety)}`;
        backtestSyncButton.disabled = !capabilities.enabled || !capabilities.provider_supports_kbars;
        backtestRunSubmit.disabled = !capabilities.enabled;
      }

      function renderBacktestIncrementalStatus() {
        const payload = state.backtest.incrementalSync;
        if (!payload) return;
        const schedule = payload.schedule || {};
        const job = payload.latest_job;
        const labels = {
          STOPPED: "尚未啟動",
          DISABLED: "已停用",
          WAITING_FOR_CLOSE: "等待收盤",
          WAITING_FOR_TRADING_DAY: "等待交易日",
          WAITING_FOR_BASE: "等待初始資料集",
          BLOCKED_BY_ACTIVE_JOB: "等待既有下載工作",
          SYNC_IN_PROGRESS: "增量同步中",
          SUBMITTED: "已提交",
          COMPLETED: "本日同步完成",
          ERROR: "排程錯誤"
        };
        const scheduleLabel = labels[schedule.state] || schedule.state || "未知";
        const latest = job
          ? `<br>最近工作：${escapeHtml(job.job_id)} · ${escapeHtml(backtestStatusLabel(job.status))} · ${escapeHtml(job.progress_message || "")}`
          : "<br>尚無增量同步紀錄。";
        backtestIncrementalStatus.innerHTML = `<strong>收盤後自動增量同步：${escapeHtml(scheduleLabel)}</strong> · 每個工作日 ${escapeHtml(schedule.close_time || "14:30")}（${escapeHtml(schedule.timezone || "Asia/Taipei")}）<br>${escapeHtml(schedule.message || "只下載各檔 watermark 之後的新 Kbar；舊資料集保持不變。")} ${latest}`;
      }

      function renderBacktestSetup(remembered = {}) {
        const entry = state.backtest.strategies.filter((strategy) => strategy.side === "ENTRY");
        const exit = state.backtest.strategies.filter((strategy) => strategy.side === "EXIT");
        const datasets = state.backtest.datasets;
        const priorDataset = remembered.dataset || backtestDataset.value;
        const selectedDataset = datasets.find((dataset) => dataset.dataset_id === priorDataset) || datasets[0] || null;
        const availableCapabilities = new Set(selectedDataset?.capabilities || []);
        const missingCapabilities = (strategy) => (strategy.required_capabilities || []).filter((capability) => !availableCapabilities.has(capability));
        const entrySelected = new Set(remembered.entry || selectedBacktestStrategies("ENTRY"));
        const exitSelected = new Set(remembered.exit || selectedBacktestStrategies("EXIT"));
        entry.forEach((strategy) => { if (missingCapabilities(strategy).length) entrySelected.delete(strategy.strategy_id); });
        exit.forEach((strategy) => { if (missingCapabilities(strategy).length) exitSelected.delete(strategy.strategy_id); });
        if (!entrySelected.size) {
          const defaultEntry = entry.find((strategy) => strategy.status === "ACTIVE" && !missingCapabilities(strategy).length);
          if (defaultEntry) entrySelected.add(defaultEntry.strategy_id);
        }
        if (!exitSelected.size) {
          exit.filter((strategy) => strategy.status === "ACTIVE" && !missingCapabilities(strategy).length)
            .forEach((strategy) => exitSelected.add(strategy.strategy_id));
        }
        const renderStrategies = (items, side, selected) => items.map((strategy) => {
          const missing = missingCapabilities(strategy);
          const disabledReason = missing.length ? `資料集缺少：${missing.join("、")}` : "";
          const experimental = strategy.status === "EXPERIMENTAL" ? " · 實驗中" : "";
          return `
          <label class="strategy-option" title="${escapeHtml(disabledReason || JSON.stringify(strategy.parameters || {}))}">
            <input type="checkbox" data-backtest-strategy="${side}" value="${escapeHtml(strategy.strategy_id)}" aria-describedby="backtest-${side === "ENTRY" ? "entry" : "exit"}-help" ${selected.has(strategy.strategy_id) ? "checked" : ""} ${missing.length ? "disabled" : ""}>
            <span><strong>${escapeHtml(strategy.display_name_zh_tw)}</strong><span>${escapeHtml(strategy.strategy_id)} · ${escapeHtml(strategy.version)} · ${escapeHtml(strategyPhaseLabels[strategy.session_phase] || strategy.session_phase || "全時段")}${escapeHtml(experimental)}${disabledReason ? ` · ${escapeHtml(disabledReason)}` : ""}</span></span>
          </label>
        `;
        }).join("") || '<p class="backtest-empty">沒有可用策略。</p>';
        document.getElementById("backtest-entry-strategies").innerHTML = renderStrategies(entry, "ENTRY", entrySelected);
        document.getElementById("backtest-exit-strategies").innerHTML = renderStrategies(exit, "EXIT", exitSelected);
        document.querySelectorAll("[data-backtest-strategy]").forEach((input) => {
          input.addEventListener("change", () => syncBacktestStrategyControls(input.dataset.backtestStrategy));
        });
        ["ENTRY", "EXIT"].forEach((side) => {
          const prefix = side === "ENTRY" ? "entry" : "exit";
          document.getElementById(`backtest-${prefix}-policy`).onchange = () => syncBacktestStrategyControls(side);
          syncBacktestStrategyControls(side);
        });

        backtestDataset.innerHTML = datasets.length
          ? datasets.map((dataset) => `<option value="${escapeHtml(dataset.dataset_id)}">${escapeHtml(dataset.dataset_id.slice(0, 18))}… · ${escapeHtml(dataset.start_date)} ～ ${escapeHtml(dataset.end_date)} · ${dataset.bar_count.toLocaleString("zh-TW")} 根${dataset.research_eligible ? "" : " · exploratory"}</option>`).join("")
          : '<option value="">請先建立或匯入 READY 資料集</option>';
        if (selectedDataset) backtestDataset.value = selectedDataset.dataset_id;
        backtestDataset.onchange = () => renderBacktestSetup({
          dataset: backtestDataset.value,
          entry: selectedBacktestStrategies("ENTRY"),
          exit: selectedBacktestStrategies("EXIT")
        });

        backtestDatasetList.innerHTML = datasets.length ? datasets.map((dataset) => `
          <button class="backtest-list-item" type="button" data-backtest-dataset="${escapeHtml(dataset.dataset_id)}">
            <strong>${escapeHtml(dataset.dataset_id)}</strong>
            <span>${escapeHtml(dataset.source)} · ${escapeHtml(dataset.profile)} · ${dataset.bar_count.toLocaleString("zh-TW")} 根 · ${dataset.research_eligible ? "可作正式研究檢核" : "探索性（CURRENT_SNAPSHOT）"}</span>
            <span>能力：${escapeHtml((dataset.capabilities || []).join("、") || "OHLCV 未確認")}${dataset.cadence_summary?.dominant_interval_seconds ? ` · dominant ${escapeHtml(dataset.cadence_summary.dominant_interval_seconds)} 秒` : ""}</span>
            <span>${escapeHtml(dataset.start_date)} ～ ${escapeHtml(dataset.end_date)}${dataset.storage_format === "JSONL_DELTA_V1" ? ` · 增量 ${Number(dataset.delta_bar_count || 0).toLocaleString("zh-TW")} 根 · parent ${escapeHtml(dataset.parent_dataset_id || "—")}` : " · 完整基礎資料集"}${dataset.issues?.length ? ` · ${escapeHtml(dataset.issues[0])}` : ""}</span>
          </button>
        `).join("") : '<p class="backtest-empty">尚未有 READY 資料集。請建立，或使用匯入的 date-effective 資料集。</p>';
        backtestDatasetList.querySelectorAll("[data-backtest-dataset]").forEach((button) => {
          button.addEventListener("click", () => {
            backtestDataset.value = button.dataset.backtestDataset;
            backtestDataset.dispatchEvent(new Event("change"));
          });
        });
      }

      function renderBacktestRuns() {
        const runs = state.backtest.runs;
        backtestRunCount.textContent = `${runs.length} 個 Run`;
        backtestRunList.innerHTML = runs.length ? runs.map((run) => `
          <button class="backtest-list-item ${run.run_id === state.backtest.activeRunId ? "selected" : ""}" type="button" data-backtest-run="${escapeHtml(run.run_id)}">
            <strong>${escapeHtml(run.run_id.slice(0, 24))}…</strong>
            <span class="backtest-status ${String(run.status).toLowerCase()}">${escapeHtml(backtestStatusLabel(run.status))}</span>
            <span>${escapeHtml(run.progress_message || "等待處理")} · ${formatNumber((run.progress || 0) * 100, 0)}%</span>
            <span>${escapeHtml(run.created_at || "")} · ${escapeHtml(run.config?.change_note || "原始設定")}</span>
          </button>
        `).join("") : '<p class="backtest-empty">尚未建立回測。資料集 READY 後可在上方選擇策略。</p>';
        backtestRunList.querySelectorAll("[data-backtest-run]").forEach((button) => {
          button.addEventListener("click", () => loadBacktestRunDetails(button.dataset.backtestRun));
        });

        const completed = runs.filter((run) => run.status === "COMPLETED");
        const oldBaseline = backtestBaseline.value;
        const oldChallenger = backtestChallenger.value;
        const options = completed.length
          ? completed.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id.slice(0, 24))}… · ${escapeHtml(run.config?.change_note || "原始設定")}</option>`).join("")
          : '<option value="">尚無已完成 Run</option>';
        backtestBaseline.innerHTML = options;
        backtestChallenger.innerHTML = options;
        if (completed.some((run) => run.run_id === oldBaseline)) backtestBaseline.value = oldBaseline;
        if (completed.some((run) => run.run_id === oldChallenger)) backtestChallenger.value = oldChallenger;
        if (completed.length > 1 && !oldChallenger) backtestChallenger.value = completed[1].run_id;

        const completedAtomic = completed.filter((run) => Boolean(run.config?.atomic_strategy_run_snapshot));
        const selectedAtomicBaseline = atomicBacktestBaseline.value;
        atomicBacktestBaseline.innerHTML = '<option value="">不加入 qualification family</option>' + completedAtomic.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id.slice(0, 24))}… · ${escapeHtml(run.config?.change_note || "原始設定")}</option>`).join("");
        if (completedAtomic.some((run) => run.run_id === selectedAtomicBaseline)) atomicBacktestBaseline.value = selectedAtomicBaseline;
        renderQualifications();
      }

      function qualificationWindow(element, label) {
        if (!element) throw new Error(`找不到 ${label} 日期欄位。`);
        const value = (name) => element.querySelector(`[data-window-field="${name}"]`)?.value || "";
        return {
          label,
          train_start: value("train_start"),
          train_end: value("train_end"),
          validation_start: value("validation_start"),
          validation_end: value("validation_end"),
          oos_start: value("oos_start"),
          oos_end: value("oos_end")
        };
      }

      function addQualificationFold() {
        qualificationFoldSequence += 1;
        const label = `fold-${qualificationFoldSequence}`;
        const inputId = (name) => `qualification-${label}-${name.replace("_", "-")}`;
        qualificationFolds.insertAdjacentHTML("beforeend", `
          <div class="qualification-window" data-qualification-fold="${label}">
            <div class="qualification-window-heading"><strong>Walk-forward ${escapeHtml(label)}</strong><button class="backtest-button secondary" type="button" data-remove-qualification-fold>移除</button></div>
            <div class="backtest-form-grid">
              <div class="backtest-field"><label for="${inputId("train_start")}">Train 起</label><input id="${inputId("train_start")}" data-window-field="train_start" required type="date"></div>
              <div class="backtest-field"><label for="${inputId("train_end")}">Train 迄</label><input id="${inputId("train_end")}" data-window-field="train_end" required type="date"></div>
              <div class="backtest-field"><label for="${inputId("validation_start")}">Validation 起</label><input id="${inputId("validation_start")}" data-window-field="validation_start" required type="date"></div>
              <div class="backtest-field"><label for="${inputId("validation_end")}">Validation 迄</label><input id="${inputId("validation_end")}" data-window-field="validation_end" required type="date"></div>
              <div class="backtest-field"><label for="${inputId("oos_start")}">OOS 起</label><input id="${inputId("oos_start")}" data-window-field="oos_start" required type="date"></div>
              <div class="backtest-field"><label for="${inputId("oos_end")}">OOS 迄</label><input id="${inputId("oos_end")}" data-window-field="oos_end" required type="date"></div>
            </div>
          </div>
        `);
        qualificationFolds.lastElementChild.querySelector("[data-remove-qualification-fold]")?.addEventListener("click", (event) => {
          event.currentTarget.closest("[data-qualification-fold]")?.remove();
        });
      }

      function renderQualification(record) {
        const evidence = record?.evidence || {};
        const primary = evidence.primary_oos || {};
        const challenger = primary.challenger || {};
        const walkForward = evidence.walk_forward || {};
        const protocol = evidence.protocol || record?.protocol || {};
        const multiple = protocol.multiple_testing || {};
        const policy = protocol.policy || {};
        const windows = [protocol.primary_window, ...(protocol.walk_forward_windows || [])].filter(Boolean);
        const windowRows = windows.map((window) => `${escapeHtml(window.label)}: Train ${escapeHtml(window.train_start)}~${escapeHtml(window.train_end)}；Validation ${escapeHtml(window.validation_start)}~${escapeHtml(window.validation_end)}；OOS ${escapeHtml(window.oos_start)}~${escapeHtml(window.oos_end)}`).join("<br>");
        const familySnapshot = record?.family_snapshot || {};
        const currentFamilySnapshot = record?.current_family_snapshot || familySnapshot;
        const familyLinks = (snapshot) => (snapshot?.attempts || []).map((attempt) => `${escapeHtml(attempt.attempt_sequence || "—")}. ${escapeHtml(attempt.run_id || "—")} · hypothesis ${escapeHtml(attempt.hypothesis_id || "尚未建立")} · qualification ${escapeHtml(attempt.qualification_id || "尚未建立")}`).join("<br>") || "—";
        const attempts = (evidence.attempted_runs || []).map((attempt, index) => {
          const versions = (attempt.strategy_version_ids || []).join("、") || "—";
          const featureRequests = (attempt.feature_requests || []).flatMap((owner) => owner.requests || []).map((request) => `${request.feature_id || "feature"}:${String(request.runtime_identity_digest || "").slice(0, 12)}…`).join("、") || "—";
          return `${index + 1}. ${escapeHtml(attempt.run_id)} · status ${escapeHtml(attempt.status || "—")} · Strategy ${escapeHtml(versions)} · adapter ${escapeHtml(attempt.feature_adapter_identity || "—")} · Feature ${escapeHtml(featureRequests)}`;
        }).join("<br>");
        const reasons = evidence.reasons?.length ? evidence.reasons.join("；") : "所有固定門檻通過，等待人工 Review。";
        qualificationResult.innerHTML = `<div class="backtest-trade-detail"><strong>${escapeHtml(record?.verdict || evidence.verdict || "—")}</strong> · ${escapeHtml(reasons)}<br><strong>Authoritative family</strong>：${escapeHtml(multiple.family_id || record?.family_id || "—")} · research baseline ${escapeHtml(String(multiple.research_baseline_digest || familySnapshot.research_baseline_digest || "—").slice(0, 16))}… · attempt ${escapeHtml(multiple.attempt_number || record?.attempt_number || "—")}/${escapeHtml(multiple.planned_attempts || "—")} · head ${escapeHtml(multiple.family_head_sequence || record?.family_head_sequence || "—")} · adjusted alpha ${escapeHtml(multiple.adjusted_alpha || "—")}<br><strong>Server policy</strong>：Train/Validation 至少 ${escapeHtml(policy.minimum_train_observed_sessions || "—")}/${escapeHtml(policy.minimum_validation_observed_sessions || "—")} 個 sessions；OOS 至少 ${escapeHtml(policy.minimum_oos_trades || "—")} 筆/${escapeHtml(policy.minimum_oos_independent_days || "—")} 日；回撤 ≤ ${formatBacktestPercent(policy.maximum_oos_drawdown)}；folds ≥ ${escapeHtml(policy.minimum_walk_forward_folds || "—")}；正向比例 ≥ ${formatBacktestPercent(policy.minimum_positive_fold_ratio)}<br><strong>固定日期窗</strong><br>${windowRows || "—"}<br><strong>Run／Strategy／Feature／adapter history</strong><br>${attempts || "—"}<br><strong>Historical family linkage（建立證據時）</strong><br>${familyLinks(familySnapshot)}<br><strong>Current family linkage</strong><br>${familyLinks(currentFamilySnapshot)}<br>Primary OOS：${challenger.closed_trades || 0} 筆/${challenger.independent_days || 0} 日；Expectancy ${formatNumber(challenger.expectancy || 0, 0)}；最大回撤 ${formatBacktestPercent(challenger.max_drawdown)}<br>Walk-forward 正向比例：${formatBacktestPercent(walkForward.positive_fold_ratio)}；Family snapshot ${escapeHtml(String(record?.family_snapshot_digest || multiple.family_snapshot_digest || "").slice(0, 16))}…；Current ${escapeHtml(String(currentFamilySnapshot.family_snapshot_digest || "").slice(0, 16))}…；Evidence ${escapeHtml(String(record?.evidence_digest || evidence.evidence_digest || "").slice(0, 16))}…<br><strong>只供人工審核，不會自動啟用策略。</strong></div>`;
      }

      function renderQualifications() {
        if (state.backtest.qualificationUnavailable) {
          qualificationList.innerHTML = `<p class="backtest-empty">資格證據需要 PostgreSQL：${escapeHtml(state.backtest.qualificationUnavailable)}</p>`;
          return;
        }
        const rows = state.backtest.qualifications || [];
        qualificationList.innerHTML = rows.length ? rows.map((item) => `
          <button class="backtest-list-item" type="button" data-qualification-id="${escapeHtml(item.qualification_id)}">
            <strong>${escapeHtml(item.verdict)}</strong>
            <span>${escapeHtml(item.baseline_run_id.slice(0, 18))}… → ${escapeHtml(item.challenger_run_id.slice(0, 18))}…</span>
            <span>${escapeHtml(item.change_note)} · ${escapeHtml(item.created_at)}</span>
          </button>
        `).join("") : '<p class="backtest-empty">尚未建立資格證據。</p>';
        qualificationList.querySelectorAll("[data-qualification-id]").forEach((button) => {
          button.addEventListener("click", async () => {
            try {
              renderQualification(await backtestFetch(`/api/backtests/qualifications/${encodeURIComponent(button.dataset.qualificationId)}`));
            } catch (error) {
              qualificationMessage.textContent = `無法讀取資格證據：${error.message}`;
            }
          });
        });
      }

      function renderBacktestEquityChart(equity = [], drawdown = []) {
        if (!equity.length) return '<p class="backtest-empty">尚無每日權益曲線。</p>';
        const width = 760;
        const height = 135;
        const padding = 16;
        const values = equity.map((point) => Number(point.equity));
        const low = Math.min(...values);
        const high = Math.max(...values);
        const span = Math.max(high - low, 1);
        const x = (index) => padding + index / Math.max(1, values.length - 1) * (width - padding * 2);
        const y = (value) => height - padding - (value - low) / span * (height - padding * 2);
        const path = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
        const maxDrawdown = Math.max(0, ...drawdown.map((point) => Number(point.drawdown || 0)));
        return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="每日權益曲線，最大回撤 ${formatBacktestPercent(maxDrawdown)}"><line x1="${padding}" x2="${width - padding}" y1="${padding}" y2="${padding}" stroke="var(--line)"/><line x1="${padding}" x2="${width - padding}" y1="${height - padding}" y2="${height - padding}" stroke="var(--line)"/><path d="${path}" fill="none" stroke="var(--blue)" stroke-linejoin="round" stroke-width="2"/><text x="${padding}" y="12" fill="var(--muted)" font-size="10">${formatNumber(high, 0)}</text><text x="${padding}" y="${height - 3}" fill="var(--muted)" font-size="10">${formatNumber(low, 0)}</text></svg>`;
      }

      function renderBacktestTradeChart(chart) {
        const bars = chart.bars || [];
        if (!bars.length) return '<p class="backtest-empty">資料集沒有可顯示的交易 Kbar。</p>';
        const width = 760;
        const height = 190;
        const left = 36;
        const right = 12;
        const top = 23;
        const bottom = 166;
        const highs = bars.map((bar) => Number(bar.high));
        const lows = bars.map((bar) => Number(bar.low));
        const rawLow = Math.min(...lows);
        const rawHigh = Math.max(...highs);
        const margin = Math.max((rawHigh - rawLow) * .08, .01);
        const low = rawLow - margin;
        const high = rawHigh + margin;
        const xStep = (width - left - right) / bars.length;
        const x = (index) => left + xStep * index + xStep / 2;
        const y = (price) => top + (high - price) / (high - low) * (bottom - top);
        const bodyWidth = Math.max(2, Math.min(9, xStep * .58));
        const candles = bars.map((bar, index) => {
          const open = Number(bar.open);
          const close = Number(bar.close);
          const color = close >= open ? "var(--green)" : "var(--red)";
          return `<line x1="${x(index)}" x2="${x(index)}" y1="${y(Number(bar.high))}" y2="${y(Number(bar.low))}" stroke="${color}"/><rect x="${x(index) - bodyWidth / 2}" y="${y(Math.max(open, close))}" width="${bodyWidth}" height="${Math.max(2, Math.abs(y(open) - y(close)))}" fill="${color}" rx="1"/>`;
        }).join("");
        const marker = (item) => {
          const index = bars.findIndex((bar) => bar.timestamp === item.at);
          if (index < 0) return "";
          const color = item.side === "ENTRY" ? "var(--blue)" : "var(--amber)";
          const direction = item.side === "ENTRY" ? -1 : 1;
          const lineEnd = Math.max(15, Math.min(bottom - 3, y(Number(item.price)) + direction * 24));
          return `<line x1="${x(index)}" x2="${x(index)}" y1="${y(Number(item.price))}" y2="${lineEnd}" stroke="${color}" stroke-width="1.5"/><text x="${x(index)}" y="${lineEnd + (direction < 0 ? -3 : 11)}" text-anchor="middle" fill="${color}" font-size="10">${item.side === "ENTRY" ? "買入" : "賣出"} ${formatNumber(item.price)}</text>`;
        };
        return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chart.symbol)} 交易期間 K 線，藍色為買入、黃色為賣出"><line x1="${left}" x2="${width - right}" y1="${top}" y2="${top}" stroke="var(--line)"/><line x1="${left}" x2="${width - right}" y1="${bottom}" y2="${bottom}" stroke="var(--line)"/><text x="${left - 4}" y="${top + 4}" text-anchor="end" fill="var(--muted)" font-size="10">${formatNumber(high)}</text><text x="${left - 4}" y="${bottom + 4}" text-anchor="end" fill="var(--muted)" font-size="10">${formatNumber(low)}</text>${candles}${(chart.markers || []).map(marker).join("")}</svg>`;
      }

      function renderBacktestResult() {
        const data = state.backtest.activeResult;
        if (!data) {
          if (state.backtest.activeRunId) backtestResult.innerHTML = '<p class="backtest-empty">正在讀取回測結果…</p>';
          return;
        }
        const { run, summary, equity, drawdown, trades, attribution } = data;
        if (run.status !== "COMPLETED") {
          const canCancel = ["QUEUED", "PREFLIGHT", "RUNNING"].includes(run.status);
          const canRetry = ["FAILED", "CANCELLED"].includes(run.status);
          backtestResult.innerHTML = `<div class="backtest-trade-detail"><strong>${escapeHtml(backtestStatusLabel(run.status))}</strong> · ${escapeHtml(run.progress_message || "等待處理")}${run.error_message ? `<br><span class="negative">${escapeHtml(run.error_message)}</span>` : ""}<div class="backtest-actions">${canCancel ? `<button class="backtest-button danger" type="button" data-backtest-cancel="${escapeHtml(run.run_id)}">取消回測</button>` : ""}${canRetry ? `<button class="backtest-button secondary" type="button" data-backtest-retry="${escapeHtml(run.run_id)}">重試原設定</button>` : ""}</div></div>`;
          bindBacktestResultButtons();
          return;
        }
        const oos = summary.oos || {};
        const full = summary.full || {};
        const strategySet = run.config?.strategy_set || {};
        const strategySummary = [
          `買入：${(strategySet.entry_strategy_ids || []).join("、") || "—"}`,
          `賣出：${(strategySet.exit_strategy_ids || []).join("、") || "—"}`,
          `買入組合：${strategySet.entry_policy || "—"}`,
          `賣出組合：${strategySet.exit_policy || "—"}`
        ].join("；");
        const metrics = [
          ["OOS 勝率", formatBacktestPercent(oos.win_rate)],
          ["OOS 95% CI", Array.isArray(oos.win_rate_ci) ? `${formatBacktestPercent(oos.win_rate_ci[0], 1)} ～ ${formatBacktestPercent(oos.win_rate_ci[1], 1)}` : "—"],
          ["淨損益", `${Number(oos.net_pnl || 0) >= 0 ? "+" : ""}${formatNumber(oos.net_pnl || 0, 0)}`],
          ["最大回撤", formatBacktestPercent(summary.equity?.max_drawdown)]
        ].map(([label, value]) => `<div class="backtest-metric"><span>${label}</span><strong>${value}</strong></div>`).join("");
        const tradeRows = (trades.trades || []).map((trade) => `
          <tr><td><button class="backtest-trade-button" type="button" data-backtest-trade="${escapeHtml(trade.trade_id)}">${escapeHtml(trade.symbol)} ${escapeHtml(trade.name || "")}</button></td><td>${escapeHtml(formatOrderTime(trade.entry.filled_at))}</td><td>${escapeHtml(trade.entry_decision.primary_strategy_id)}</td><td>${escapeHtml(trade.exit_decision.primary_strategy_id)}</td><td class="${Number(trade.net_pnl) >= 0 ? "positive" : "negative"}">${Number(trade.net_pnl) >= 0 ? "+" : ""}${formatNumber(trade.net_pnl, 0)}</td></tr>
        `).join("") || '<tr><td colspan="5" class="backtest-empty">沒有已平倉交易。</td></tr>';
        const attributionRows = (attribution.rows || []).filter((row) => row.role !== "EVALUATION").map((row) => `<tr><td>${escapeHtml(row.role)}</td><td>${escapeHtml(row.strategy_id)}</td><td>${row.primary_trades || 0}</td><td>${row.participated_in_trades || 0}</td><td class="${Number(row.primary_net_pnl || 0) >= 0 ? "positive" : "negative"}">${formatNumber(row.primary_net_pnl || 0, 0)}</td></tr>`).join("") || '<tr><td colspan="5" class="backtest-empty">尚無交易歸因。</td></tr>';
        backtestResult.innerHTML = `
          <div class="backtest-trade-detail"><strong>${escapeHtml(summary.verdict)}</strong> · ${summary.reasons?.length ? escapeHtml(summary.reasons.join("；")) : "資料與 OOS 檢核通過"}<br><span>${escapeHtml(strategySummary)}<br>完整已平倉 ${full.closed_trades || 0} 筆；OOS ${oos.closed_trades || 0} 筆；Profit Factor ${oos.profit_factor_display || (oos.profit_factor === null ? "—" : formatNumber(oos.profit_factor))}；Expectancy ${formatNumber(oos.expectancy || 0, 0)}</span></div>
          <div class="backtest-metrics">${metrics}</div>
          <div class="backtest-chart">${renderBacktestEquityChart(equity.daily_equity, drawdown.drawdown)}</div>
          <div class="backtest-actions"><a class="backtest-button secondary" href="/api/backtests/runs/${encodeURIComponent(run.run_id)}/trades.csv">匯出交易 CSV</a></div>
          <div class="backtest-section-heading"><h3>交易明細</h3><span class="panel-count">${trades.total || 0} 筆</span></div>
          <div class="backtest-table-wrap"><table class="backtest-table"><thead><tr><th>標的</th><th>進場</th><th>主要買入策略</th><th>主要賣出策略</th><th>淨損益</th></tr></thead><tbody>${tradeRows}</tbody></table></div>
          <div id="backtest-trade-detail"></div>
          <div class="backtest-section-heading"><h3>策略歸因</h3><span class="panel-count">primary／參與交易分開統計</span></div>
          <div class="backtest-table-wrap"><table class="backtest-table"><thead><tr><th>方向</th><th>策略版本</th><th>主要交易</th><th>參與交易</th><th>主要淨損益</th></tr></thead><tbody>${attributionRows}</tbody></table></div>
        `;
        backtestResult.querySelectorAll("[data-backtest-trade]").forEach((button) => {
          button.addEventListener("click", () => loadBacktestTrade(button.dataset.backtestTrade));
        });
      }

      function bindBacktestResultButtons() {
        backtestResult.querySelector("[data-backtest-cancel]")?.addEventListener("click", async (event) => {
          await changeBacktestRun(event.currentTarget.dataset.backtestCancel, "cancel");
        });
        backtestResult.querySelector("[data-backtest-retry]")?.addEventListener("click", async (event) => {
          await changeBacktestRun(event.currentTarget.dataset.backtestRetry, "retry");
        });
      }

      async function refreshBacktestWorkspace() {
        const remembered = { dataset: backtestDataset.value, entry: selectedBacktestStrategies("ENTRY"), exit: selectedBacktestStrategies("EXIT") };
        const [capabilities, incrementalSync, datasetsPayload, strategiesPayload, runsPayload, qualificationPayload] = await Promise.all([
          backtestFetch("/api/backtests/capabilities"),
          backtestFetch("/api/backtests/datasets/incremental-sync"),
          backtestFetch("/api/backtests/datasets"),
          backtestFetch("/api/backtests/strategies"),
          backtestFetch("/api/backtests/runs"),
          backtestFetch("/api/backtests/qualifications").catch((error) => ({ qualifications: [], unavailable: error.message }))
        ]);
        state.backtest.capabilities = capabilities;
        state.backtest.incrementalSync = incrementalSync;
        state.backtest.datasets = datasetsPayload.datasets || [];
        state.backtest.strategies = strategiesPayload.strategies || [];
        state.backtest.runs = runsPayload.runs || [];
        state.backtest.qualifications = qualificationPayload.qualifications || [];
        state.backtest.qualificationUnavailable = qualificationPayload.unavailable || null;
        await refreshStrategyCatalog();
        renderBacktestNotice();
        renderBacktestIncrementalStatus();
        renderBacktestSetup(remembered);
        renderBacktestRuns();
        const active = state.backtest.runs.find((run) => run.run_id === state.backtest.activeRunId);
        if (!active) {
          state.backtest.activeRunId = null;
          state.backtest.activeResult = null;
          backtestResult.innerHTML = "";
        } else if (active.status !== "COMPLETED") {
          state.backtest.activeResult = { run: active };
          renderBacktestResult();
        }
      }

      async function loadBacktestRunDetails(runId) {
        if (!runId) return;
        state.backtest.activeRunId = runId;
        state.backtest.activeResult = null;
        renderBacktestRuns();
        renderBacktestResult();
        try {
          const run = await backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}`);
          if (run.status !== "COMPLETED") {
            state.backtest.activeResult = { run };
            renderBacktestResult();
            return;
          }
          const [summary, equity, drawdown, trades, attribution] = await Promise.all([
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/summary`),
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/equity`),
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/drawdown`),
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/trades?page=1&page_size=100`),
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/strategy-attribution`)
          ]);
          state.backtest.activeResult = { run, summary, equity, drawdown, trades, attribution };
          renderBacktestResult();
        } catch (error) {
          backtestResult.innerHTML = `<p class="backtest-empty">無法讀取回測結果：${escapeHtml(error.message)}</p>`;
        }
      }

      async function loadBacktestTrade(tradeId) {
        const runId = state.backtest.activeRunId;
        const target = document.getElementById("backtest-trade-detail");
        if (!runId || !tradeId || !target) return;
        target.innerHTML = '<p class="backtest-empty">正在讀取交易決策、策略證據與 Kbar…</p>';
        try {
          const [trade, chart] = await Promise.all([
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/trades/${encodeURIComponent(tradeId)}`),
            backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/trades/${encodeURIComponent(tradeId)}/chart`)
          ]);
          const evidence = (side, evaluations) => evaluations.map((item) => `<li><strong>${escapeHtml(item.strategy_name)}</strong> (${escapeHtml(item.strategy_version)})：${escapeHtml(item.reason)}<br><span>觀測 ${escapeHtml(JSON.stringify(item.observed))}；門檻 ${escapeHtml(JSON.stringify(item.threshold))}</span></li>`).join("") || "<li>沒有觸發策略。</li>";
          const chartSummary = chart.bars.length ? `${chart.bars.length} 根 Kbar，買入 ${formatNumber(chart.markers[0].price)}／賣出 ${formatNumber(chart.markers[1].price)}` : "沒有可顯示的 Kbar";
          const decisionSummary = (decision) => `主策略：${decision.primary_strategy_id}；已觸發：${(decision.triggered_strategy_ids || []).join("、") || "—"}；聚合：${decision.policy || "—"}；成交時域：${decision.execution_horizon || "legacy NEXT_BAR"}`;
          target.innerHTML = `<div class="backtest-trade-detail"><strong>${escapeHtml(trade.symbol)} ${escapeHtml(trade.name || "")}</strong> · ${chartSummary}<div class="backtest-chart">${renderBacktestTradeChart(chart)}</div>買入 ${escapeHtml(decisionSummary(trade.entry_decision))}<br>賣出 ${escapeHtml(decisionSummary(trade.exit_decision))}<br><strong>買入觸發證據</strong><ul>${evidence("ENTRY", trade.entry_strategies || [])}</ul><strong>賣出觸發證據</strong><ul>${evidence("EXIT", trade.exit_strategies || [])}</ul></div>`;
        } catch (error) {
          target.innerHTML = `<p class="backtest-empty">無法讀取交易細節：${escapeHtml(error.message)}</p>`;
        }
      }

      async function startBacktestDatasetSync() {
        backtestSyncButton.disabled = true;
        backtestSyncButton.textContent = "建立中…";
        try {
          const job = await backtestFetch("/api/backtests/datasets/sync", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ years: Number(backtestSyncYears.value) })
          });
          backtestFormMessage.textContent = "資料集工作已建立，背景下載中；可繼續操作頁面。";
          await pollBacktestDatasetJob(job.job_id);
        } catch (error) {
          backtestFormMessage.textContent = `無法建立資料集：${error.message}`;
        } finally {
          backtestSyncButton.textContent = "建立資料集";
          backtestSyncButton.disabled = !state.backtest.capabilities?.provider_supports_kbars;
        }
      }

      async function pollBacktestDatasetJob(jobId) {
        for (let attempt = 0; attempt < 720; attempt += 1) {
          const job = await backtestFetch(`/api/backtests/datasets/jobs/${encodeURIComponent(jobId)}`);
          backtestFormMessage.textContent = `${backtestStatusLabel(job.status)} · ${job.progress_message || ""} · ${formatNumber((job.progress || 0) * 100, 0)}%`;
          if (["COMPLETED", "FAILED", "CANCELLED"].includes(job.status)) {
            await refreshBacktestWorkspace();
            if (job.status !== "COMPLETED") throw new Error(job.error_message || "資料集工作未完成");
            return;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 2000));
        }
        throw new Error("資料集工作等待逾時；工作仍可能在背景繼續，可稍後重新整理。");
      }

      function backtestRunRequest() {
        const entry = selectedBacktestStrategies("ENTRY");
        const exit = selectedBacktestStrategies("EXIT");
        if (!backtestDataset.value) throw new Error("請先選擇 READY 歷史資料集。");
        validateBacktestStrategyPolicy("ENTRY", entry);
        validateBacktestStrategyPolicy("EXIT", exit);
        return {
          dataset_id: backtestDataset.value,
          entry_strategy_ids: entry,
          exit_strategy_ids: exit,
          entry_policy: document.getElementById("backtest-entry-policy").value,
          exit_policy: document.getElementById("backtest-exit-policy").value,
          entry_min_trigger_count: Number(document.getElementById("backtest-entry-min").value),
          exit_min_trigger_count: Number(document.getElementById("backtest-exit-min").value),
          priority_order: [...exit, ...entry],
          starting_cash: document.getElementById("backtest-cash").value,
          position_fraction: document.getElementById("backtest-position-fraction").value,
          target_win_rate: document.getElementById("backtest-win-rate").value,
          minimum_oos_trades: Number(document.getElementById("backtest-oos-trades").value),
          idempotency_key: newIdempotencyKey("backtest")
        };
      }

      async function submitBacktestRun(event) {
        event.preventDefault();
        try {
          const request = backtestRunRequest();
          backtestRunSubmit.disabled = true;
          backtestRunSubmit.textContent = "建立中…";
          const payload = await backtestFetch("/api/backtests/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
          state.backtest.activeRunId = payload.run.run_id;
          state.backtest.activeResult = { run: payload.run };
          backtestFormMessage.textContent = "回測已建立；資料只會從封存資料集讀取。";
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(payload.run.run_id);
        } catch (error) {
          backtestFormMessage.textContent = `無法建立回測：${error.message}`;
        } finally {
          backtestRunSubmit.disabled = false;
          backtestRunSubmit.textContent = "建立回測";
        }
      }

      async function submitAtomicBacktestRun(event) {
        event.preventDefault();
        if (!atomicBacktestSet.value || !atomicBacktestDataset.value) {
          atomicBacktestMessage.textContent = "請先選擇策略組合與 READY 歷史資料集。";
          return;
        }
        atomicBacktestSubmit.disabled = true;
        atomicBacktestSubmit.textContent = "建立中…";
        try {
          const payload = await atomicMutation("/api/backtests/runs/atomic", "POST", {
            dataset_id: atomicBacktestDataset.value,
            strategy_set_version_id: atomicBacktestSet.value,
            starting_cash: document.getElementById("atomic-backtest-cash").value,
            position_fraction: document.getElementById("atomic-backtest-position-fraction").value,
            change_note: document.getElementById("atomic-backtest-note").value.trim(),
            baseline_run_id: atomicBacktestBaseline.value || null,
            actor_id: "local-researcher"
          }, "atomic-backtest");
          state.backtest.activeRunId = payload.run.run_id;
          state.backtest.activeResult = { run: payload.run };
          atomicBacktestMessage.textContent = "原子策略回測已建立；Run 已鎖定精確版本與 Feature 證據。";
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(payload.run.run_id);
        } catch (error) {
          atomicBacktestMessage.textContent = `無法建立原子策略回測：${error.message}`;
        } finally {
          atomicBacktestSubmit.textContent = "用原子策略建立回測";
          renderAtomicLauncherOptions();
        }
      }

      async function changeBacktestRun(runId, action) {
        try {
          const path = action === "cancel" ? `/api/backtests/runs/${encodeURIComponent(runId)}/cancel` : `/api/backtests/runs/${encodeURIComponent(runId)}/retry`;
          const activeRun = state.backtest.activeResult?.run;
          const atomic = activeRun?.run_id === runId && Boolean(activeRun?.config?.atomic_strategy_run_snapshot);
          const payload = atomic
            ? await atomicMutation(path, "POST", { idempotency_key: null, actor_id: "local-researcher" }, `atomic-backtest-${action}`)
            : await backtestFetch(path, action === "cancel"
              ? { method: "POST" }
              : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idempotency_key: newIdempotencyKey("backtest-retry") }) });
          state.backtest.activeRunId = (payload.run || payload).run_id || runId;
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(state.backtest.activeRunId);
        } catch (error) {
          backtestFormMessage.textContent = `無法${action === "cancel" ? "取消" : "重試"}回測：${error.message}`;
        }
      }

      async function cloneBacktestRun() {
        const runId = state.backtest.activeRunId;
        const changeNote = document.getElementById("backtest-change-note").value.trim();
        if (!runId) { backtestFormMessage.textContent = "請先選擇一個既有回測。"; return; }
        if (!changeNote) { backtestFormMessage.textContent = "請填寫調整說明，才能建立可比較的 challenger。"; return; }
        try {
          const activeRun = state.backtest.activeResult?.run;
          const atomic = Boolean(activeRun?.config?.atomic_strategy_run_snapshot);
          let payload;
          if (atomic) {
            payload = await atomicMutation(`/api/backtests/runs/${encodeURIComponent(runId)}/clone`, "POST", {
              idempotency_key: null,
              actor_id: "local-researcher",
              change_note: changeNote,
              overrides: {
                starting_cash: document.getElementById("backtest-cash").value,
                position_fraction: document.getElementById("backtest-position-fraction").value,
                target_win_rate: document.getElementById("backtest-win-rate").value,
                minimum_oos_trades: Number(document.getElementById("backtest-oos-trades").value)
              }
            }, "atomic-backtest-clone");
          } else {
            const request = backtestRunRequest();
            payload = await backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/clone`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ idempotency_key: newIdempotencyKey("backtest-clone"), change_note: changeNote, overrides: { strategy_set: { entry_strategy_ids: request.entry_strategy_ids, exit_strategy_ids: request.exit_strategy_ids, entry_policy: request.entry_policy, exit_policy: request.exit_policy, entry_min_trigger_count: request.entry_min_trigger_count, exit_min_trigger_count: request.exit_min_trigger_count, priority_order: request.priority_order }, starting_cash: request.starting_cash, position_fraction: request.position_fraction, target_win_rate: request.target_win_rate, minimum_oos_trades: request.minimum_oos_trades } })
            });
          }
          state.backtest.activeRunId = payload.run.run_id;
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(payload.run.run_id);
        } catch (error) {
          backtestFormMessage.textContent = `無法複製回測：${error.message}`;
        }
      }

      async function compareBacktestRuns() {
        if (!backtestBaseline.value || !backtestChallenger.value) { backtestComparison.innerHTML = '<p class="backtest-empty">請選擇兩個已完成 Run。</p>'; return; }
        if (backtestBaseline.value === backtestChallenger.value) { backtestComparison.innerHTML = '<p class="backtest-empty">Baseline 與 Challenger 必須不同。</p>'; return; }
        try {
          const comparison = await backtestFetch("/api/backtests/comparisons", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ baseline_run_id: backtestBaseline.value, challenger_run_id: backtestChallenger.value }) });
          const deltas = comparison.deltas || {};
          backtestComparison.innerHTML = `<div class="backtest-trade-detail"><strong>${escapeHtml(comparison.verdict)}</strong> · ${escapeHtml(comparison.message)}<br>勝率差：${formatBacktestPercent(deltas.win_rate)}；期望值差：${formatNumber(deltas.expectancy || 0, 0)}；最大回撤差：${formatBacktestPercent(deltas.max_drawdown)}${comparison.win_rate_delta_ci ? `<br>群集 bootstrap 勝率差 95% CI：${formatBacktestPercent(comparison.win_rate_delta_ci[0])} ～ ${formatBacktestPercent(comparison.win_rate_delta_ci[1])}` : ""}${comparison.config_diff?.length ? `<br>不可比較欄位：${escapeHtml(comparison.config_diff.map((item) => item.field).join("、"))}` : ""}</div>`;
        } catch (error) {
          backtestComparison.innerHTML = `<p class="backtest-empty">無法比較：${escapeHtml(error.message)}</p>`;
        }
      }

      async function submitBacktestQualification(event) {
        event.preventDefault();
        const baselineRunId = backtestBaseline.value;
        const challengerRunId = backtestChallenger.value;
        if (!baselineRunId || !challengerRunId || baselineRunId === challengerRunId) {
          qualificationMessage.textContent = "請選擇兩個不同的已完成 Run。";
          return;
        }
        try {
          qualificationSubmit.disabled = true;
          qualificationSubmit.textContent = "建立證據中…";
          const body = {
            baseline_run_id: baselineRunId,
            challenger_run_id: challengerRunId,
            hypothesis_id: document.getElementById("qualification-hypothesis").value.trim(),
            protocol: {
              contract_version: "backtest-qualification-request-v2",
              primary_window: qualificationWindow(document.querySelector('[data-qualification-window="primary"]'), "primary"),
              walk_forward_windows: [...qualificationFolds.querySelectorAll("[data-qualification-fold]")].map((element) => qualificationWindow(element, element.dataset.qualificationFold))
            },
            actor_id: "local-researcher",
            change_note: document.getElementById("qualification-change-note").value.trim()
          };
          const payload = await atomicMutation("/api/backtests/qualifications", "POST", body, "backtest-qualification");
          qualificationMessage.textContent = payload.replayed ? "已回放原本的不可變資格證據。" : "資格證據已永久保存；結果只供人工 Review。";
          renderQualification(payload.qualification);
          await refreshBacktestWorkspace();
        } catch (error) {
          qualificationMessage.textContent = `無法建立資格證據：${error.message}`;
        } finally {
          qualificationSubmit.disabled = false;
          qualificationSubmit.textContent = "建立不可變資格證據";
        }
      }

      function pollBacktestWorkspace() {
        if (document.visibilityState !== "visible" || !backtestDrawer.classList.contains("open") || state.backtest.polling) return;
        state.backtest.polling = true;
        refreshBacktestWorkspace().then(async () => {
          const active = state.backtest.runs.find((run) => run.run_id === state.backtest.activeRunId);
          if (active?.status === "COMPLETED" && state.backtest.activeResult?.run?.status !== "COMPLETED") await loadBacktestRunDetails(active.run_id);
        }).catch((error) => { backtestNotice.textContent = `回測工作區更新失敗：${error.message}`; }).finally(() => { state.backtest.polling = false; });
      }

      strategyDraftForm?.addEventListener("submit", submitAtomicDraft);
      strategyDraftValidate?.addEventListener("click", validateAtomicDraft);
      strategyDraftPublish?.addEventListener("click", publishAtomicDraft);
      strategySetForm?.addEventListener("submit", submitAtomicStrategySet);
      strategyVersionCompare?.addEventListener("click", compareAtomicVersions);
      strategySetPolicy?.addEventListener("change", () => {
        strategySetMinimum.disabled = strategySetPolicy.value !== "AT_LEAST_N";
      });
      atomicBacktestForm?.addEventListener("submit", submitAtomicBacktestRun);
      qualificationForm?.addEventListener("submit", submitBacktestQualification);
      qualificationAddFold?.addEventListener("click", addQualificationFold);
      addQualificationFold();
      addQualificationFold();


  return { refreshStrategyCatalog, setStrategyCatalogDrawer, setBacktestDrawer, refreshBacktestWorkspace, startBacktestDatasetSync, submitBacktestRun, cloneBacktestRun, compareBacktestRuns, pollBacktestWorkspace };
}
