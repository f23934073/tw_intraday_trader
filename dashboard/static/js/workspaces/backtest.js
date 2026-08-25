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
  const strategyDraftClone = document.getElementById("strategy-draft-clone");
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
  const strategySetEditorTitle = document.getElementById("strategy-set-editor-title");
  const strategySetName = document.getElementById("strategy-set-name");
  const strategySetPolicy = document.getElementById("strategy-set-policy");
  const strategySetMinimum = document.getElementById("strategy-set-minimum");
  const strategySetMinimumHelp = document.getElementById("strategy-set-minimum-help");
  const strategySetChangeNote = document.getElementById("strategy-set-change-note");
  const strategySetMembers = document.getElementById("strategy-set-members");
  const strategySetMessage = document.getElementById("strategy-set-message");
  const strategySetSave = document.getElementById("strategy-set-save");
  const strategySetCancel = document.getElementById("strategy-set-cancel");
  const strategySetList = document.getElementById("strategy-set-list");
  const strategyAuditList = document.getElementById("strategy-audit-list");
  const strategyWorkflowTabs = [...document.querySelectorAll("[data-strategy-tab]")];
  const strategyWorkflowPanels = [...document.querySelectorAll("[data-strategy-panel]")];
  const strategyTemplateCount = document.getElementById("strategy-template-count");
  const strategyLibraryCount = document.getElementById("strategy-library-count");
  const strategySetCount = document.getElementById("strategy-set-count");
  const strategyAuditCount = document.getElementById("strategy-audit-count");
  const strategyEditorName = document.getElementById("strategy-editor-name");
  const strategyEditorMeta = document.getElementById("strategy-editor-meta");
  const strategyDraftEditorCard = document.getElementById("strategy-draft-editor-card");
  const strategyEditorMount = document.getElementById("strategy-editor-mount");
  const strategyLibraryEditorMount = document.getElementById("strategy-library-editor-mount");
  const backtestToggle = document.getElementById("backtest-toggle");
  const backtestDrawer = document.getElementById("backtest-drawer");
  const backtestPanel = document.getElementById("backtest-panel");
  const backtestNotice = document.getElementById("backtest-notice");
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
  const atomicBacktestDatasetStatus = document.getElementById("atomic-backtest-dataset-status");
  const atomicBacktestBaseline = document.getElementById("atomic-backtest-baseline");
  const atomicBacktestSubmit = document.getElementById("atomic-backtest-submit");
  const atomicBacktestMessage = document.getElementById("atomic-backtest-message");
  const pendingAtomicMutationKeys = createMutationKeyStore(newIdempotencyKey);
  let pendingAtomicBacktestRequest = null;
  let editingStrategySetVersionId = null;
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
          setStrategyManagementView(state.strategyCatalog.activeView || "editor");
          requestAnimationFrame(() => strategyCatalogPanel.focus());
        } else {
          strategyToggle.focus();
        }
      }

      function setStrategyManagementView(viewName, { focusTab = false } = {}) {
        const targetTab = strategyWorkflowTabs.find((tab) => tab.dataset.strategyTab === viewName);
        if (!targetTab) return;
        state.strategyCatalog.activeView = viewName;
        mountStrategyDraftEditor(viewName);
        strategyWorkflowTabs.forEach((tab) => {
          const active = tab === targetTab;
          tab.classList.toggle("active", active);
          tab.setAttribute("aria-selected", String(active));
          tab.tabIndex = active ? 0 : -1;
        });
        strategyWorkflowPanels.forEach((panel) => {
          const active = panel.dataset.strategyPanel === viewName;
          panel.classList.toggle("active", active);
          panel.hidden = !active;
        });
        if (focusTab) targetTab.focus();
      }

      function mountStrategyDraftEditor(viewName) {
        const showBesideLibrary = viewName === "library" && activeAtomicDraft();
        const target = showBesideLibrary ? strategyLibraryEditorMount : strategyEditorMount;
        if (target && strategyDraftEditorCard?.parentElement !== target) target.append(strategyDraftEditorCard);
      }

      function handleStrategyTabKeydown(event) {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const currentIndex = strategyWorkflowTabs.indexOf(event.currentTarget);
        let nextIndex = currentIndex;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = strategyWorkflowTabs.length - 1;
        if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % strategyWorkflowTabs.length;
        if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + strategyWorkflowTabs.length) % strategyWorkflowTabs.length;
        setStrategyManagementView(strategyWorkflowTabs[nextIndex].dataset.strategyTab, { focusTab: true });
      }

      function syncStrategyWorkflowCounts() {
        const templateTotal = state.strategyCatalog.templates.length;
        const draftTotal = state.strategyCatalog.drafts.length;
        const versionTotal = state.strategyCatalog.versions.length;
        const setTotal = state.strategyCatalog.strategySets.length;
        const auditTotal = state.strategyCatalog.auditEvents.length;
        strategyTemplateCount.textContent = String(templateTotal);
        strategyLibraryCount.textContent = String(draftTotal + versionTotal);
        strategySetCount.textContent = String(setTotal);
        strategyAuditCount.textContent = String(auditTotal);
        strategyWorkflowTabs.find((tab) => tab.dataset.strategyTab === "editor")?.setAttribute("aria-label", `1. 選擇與設定，${templateTotal} 個策略`);
        strategyWorkflowTabs.find((tab) => tab.dataset.strategyTab === "library")?.setAttribute("aria-label", `2. 草稿與版本，${draftTotal} 份草稿、${versionTotal} 個版本`);
        strategyWorkflowTabs.find((tab) => tab.dataset.strategyTab === "sets")?.setAttribute("aria-label", `3. 策略組合，${setTotal} 個組合`);
        strategyWorkflowTabs.find((tab) => tab.dataset.strategyTab === "audit")?.setAttribute("aria-label", `4. 操作紀錄，${auditTotal} 筆`);
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
          <button class="strategy-template-button ${template.strategy_id === state.strategyCatalog.selectedTemplateId ? "selected" : ""}" type="button" data-atomic-template="${escapeHtml(template.strategy_id)}" aria-pressed="${template.strategy_id === state.strategyCatalog.selectedTemplateId ? "true" : "false"}">
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
            strategyDraftMessage.textContent = "";
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
          strategyEditorName.textContent = "請先選擇策略";
          strategyEditorMeta.textContent = "—";
          strategyParameterFields.innerHTML = '<p class="backtest-empty">請先選擇策略。</p>';
          strategyDraftForm.classList.remove("sealed");
          strategyChangeNote.readOnly = false;
          strategyDraftClone.hidden = true;
          strategyDraftSave.hidden = false;
          strategyDraftValidate.hidden = false;
          strategyDraftPublish.hidden = false;
          strategyDraftSave.disabled = true;
          strategyDraftValidate.disabled = true;
          strategyDraftPublish.disabled = true;
          return;
        }
        strategyEditorName.textContent = template.display_name_zh_tw;
        const sealed = Boolean(draft?.is_sealed);
        strategyEditorMeta.textContent = `${strategyRoleLabels[template.role] || template.role} · ${strategyPhaseLabels[template.session_phase] || template.session_phase}${sealed ? " · 已封存" : ""}`;
        const fields = template.parameter_schema?.fields || {};
        const values = draft?.parameters || Object.fromEntries(Object.entries(fields).map(([name, spec]) => [name, spec.default]));
        strategyParameterFields.innerHTML = `<div class="strategy-parameter-grid">${Object.entries(fields).map(([name, spec]) => parameterInput(template, name, spec, values[name])).join("")}</div>`;
        strategyParameterFields.querySelectorAll("input, select").forEach((control) => { control.disabled = sealed; });
        strategyDraftForm.classList.toggle("sealed", sealed);
        strategyChangeNote.readOnly = sealed;
        strategyDraftClone.hidden = !sealed;
        strategyDraftClone.disabled = !draft?.published_strategy_version_id;
        strategyDraftSave.hidden = sealed;
        strategyDraftValidate.hidden = sealed;
        strategyDraftPublish.hidden = sealed;
        const editable = !sealed;
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
        strategySetMembers.querySelectorAll("[data-strategy-set-version]").forEach((input) => {
          input.addEventListener("change", syncStrategySetMinimumControl);
        });
        const editingSet = state.strategyCatalog.strategySets.find((set) => set.strategy_set_version_id === editingStrategySetVersionId);
        if (editingSet) {
          const memberVersionIds = new Set(editingSet.members.map((member) => member.strategy_version_id));
          strategySetMembers.querySelectorAll("[data-strategy-set-version]").forEach((input) => {
            input.checked = memberVersionIds.has(input.value);
          });
        } else if (editingStrategySetVersionId) {
          resetStrategySetEditor();
        }
        syncStrategySetMinimumControl();
        const sets = state.strategyCatalog.strategySets;
        const latestVersionByFamily = new Map();
        sets.forEach((set) => {
          latestVersionByFamily.set(set.strategy_set_id, Math.max(latestVersionByFamily.get(set.strategy_set_id) || 0, set.version_number));
        });
        strategySetList.innerHTML = sets.length ? sets.map((set) => `
          <article class="strategy-catalog-card">
            <div class="strategy-catalog-card-heading"><strong>${escapeHtml(set.display_name_zh_tw)}</strong><span>${escapeHtml(set.policy)} · v${set.version_number}</span></div>
            <p class="strategy-catalog-description">${set.members.length} 個精確版本 · ${escapeHtml(set.snapshot_digest.slice(0, 12))}</p>
            ${latestVersionByFamily.get(set.strategy_set_id) === set.version_number ? `<div class="strategy-set-card-actions"><button class="backtest-button secondary" type="button" data-strategy-set-edit="${escapeHtml(set.strategy_set_version_id)}" aria-label="修改策略組合 ${escapeHtml(set.display_name_zh_tw)}">修改</button><button class="backtest-button danger" type="button" data-strategy-set-delete="${escapeHtml(set.strategy_set_version_id)}" aria-label="刪除策略組合 ${escapeHtml(set.display_name_zh_tw)}">刪除</button></div>` : '<div class="strategy-catalog-badges"><span class="strategy-catalog-badge">歷史版本</span></div>'}
          </article>
        `).join("") : '<p class="backtest-empty">目前沒有策略組合。</p>';
        strategySetList.querySelectorAll("[data-strategy-set-edit]").forEach((button) => {
          button.addEventListener("click", () => editAtomicStrategySet(button.dataset.strategySetEdit));
        });
        strategySetList.querySelectorAll("[data-strategy-set-delete]").forEach((button) => {
          button.addEventListener("click", () => archiveAtomicStrategySet(button.dataset.strategySetDelete));
        });
      }

      function renderAtomicLauncherOptions() {
        const selectedSet = atomicBacktestSet.value;
        atomicBacktestSet.innerHTML = state.strategyCatalog.strategySets.length
          ? state.strategyCatalog.strategySets.map((set) => `<option value="${escapeHtml(set.strategy_set_version_id)}">${escapeHtml(set.display_name_zh_tw)} · ${escapeHtml(set.policy)} · ${set.members.length} 個版本</option>`).join("")
          : '<option value="">請先到策略管理建立組合</option>';
        if ([...atomicBacktestSet.options].some((option) => option.value === selectedSet)) {
          atomicBacktestSet.value = selectedSet;
        }
        const projection = state.backtest.atomicDataset;
        if (projection?.available) {
          const mode = projection.resolution_mode === "BASELINE_DATASET" ? "沿用 Baseline" : `binding r${projection.binding_revision}`;
          const amount = projection.amount_kind
            ? ` · VWAP：${escapeHtml(projection.vwap_semantic || projection.amount_kind)}`
            : "";
          atomicBacktestDatasetStatus.innerHTML = `<strong>歷史資料已就緒</strong> · ${escapeHtml(mode)}<br><span>${escapeHtml(projection.start_date)} ～ ${escapeHtml(projection.end_date)} · ${Number(projection.symbol_count || 0).toLocaleString("zh-TW")} 檔 · ${Number(projection.bar_count || 0).toLocaleString("zh-TW")} 根 Kbar · ${projection.research_eligible ? "研究資料" : "探索資料"}${amount}</span>`;
        } else if (projection) {
          atomicBacktestDatasetStatus.innerHTML = `<strong>目前不可建立回測</strong> · ${escapeHtml(projection.message || "Dataset binding 尚未就緒")}`;
        } else {
          atomicBacktestDatasetStatus.innerHTML = "<strong>正在確認 ATOMIC_BACKTEST_DEFAULT…</strong>";
        }
        atomicBacktestSubmit.disabled = !state.strategyCatalog.atomicAvailable || !state.strategyCatalog.strategySets.length || !projection?.available;
      }

      async function refreshAtomicDatasetProjection() {
        if (!atomicBacktestSet.value) {
          state.backtest.atomicDataset = null;
          renderAtomicLauncherOptions();
          return;
        }
        const query = new URLSearchParams({ strategy_set_version_id: atomicBacktestSet.value });
        if (atomicBacktestBaseline.value) query.set("baseline_run_id", atomicBacktestBaseline.value);
        try {
          const payload = await backtestFetch(`/api/backtests/atomic-dataset?${query.toString()}`);
          state.backtest.atomicDataset = payload.binding;
        } catch (error) {
          state.backtest.atomicDataset = { available: false, message: error.message };
        }
        renderAtomicLauncherOptions();
      }

      function renderAtomicManagement() {
        renderAtomicTemplates();
        renderAtomicParameterEditor();
        renderAtomicDrafts();
        renderAtomicVersions();
        renderAtomicSetBuilder();
        renderAtomicAuditEvents();
        renderAtomicLauncherOptions();
        syncStrategyWorkflowCounts();
        setStrategyManagementView(state.strategyCatalog.activeView || "editor");
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
          syncStrategyWorkflowCounts();
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

      async function cloneActiveAtomicDraft() {
        const draft = activeAtomicDraft();
        if (!draft?.published_strategy_version_id) return;
        strategyDraftClone.disabled = true;
        strategyDraftClone.textContent = "複製中…";
        try {
          await cloneAtomicVersion(draft.published_strategy_version_id);
        } finally {
          strategyDraftClone.disabled = false;
          strategyDraftClone.textContent = "複製為新草稿";
        }
      }

      function syncStrategySetMinimumControl() {
        const selectedCount = strategySetMembers.querySelectorAll("[data-strategy-set-version]:checked").length;
        if (selectedCount) strategySetMinimum.max = String(selectedCount);
        else strategySetMinimum.removeAttribute("max");
        strategySetMinimumHelp.textContent = strategySetPolicy.value === "AT_LEAST_N"
          ? selectedCount
            ? `請輸入 1 到 ${selectedCount}；目前已選 ${selectedCount} 個策略。`
            : "請先選擇策略，再設定至少觸發數。"
          : "調整此數值會自動切換成「至少 N 個」。";
      }

      function resetStrategySetEditor() {
        editingStrategySetVersionId = null;
        strategySetEditorTitle.textContent = "建立策略組合";
        strategySetSave.textContent = "建立策略組合";
        strategySetCancel.hidden = true;
        strategySetName.value = "";
        strategySetPolicy.value = "ANY";
        strategySetMinimum.value = "1";
        strategySetChangeNote.value = "";
        strategySetMembers.querySelectorAll("[data-strategy-set-version]").forEach((input) => { input.checked = false; });
        syncStrategySetMinimumControl();
      }

      function editAtomicStrategySet(strategySetVersionId) {
        const strategySet = state.strategyCatalog.strategySets.find((set) => set.strategy_set_version_id === strategySetVersionId);
        if (!strategySet) {
          strategySetMessage.textContent = "找不到要修改的策略組合，請重新整理。";
          return;
        }
        editingStrategySetVersionId = strategySetVersionId;
        strategySetEditorTitle.textContent = `修改策略組合 · v${strategySet.version_number}`;
        strategySetSave.textContent = `儲存為 v${strategySet.version_number + 1}`;
        strategySetCancel.hidden = false;
        strategySetName.value = strategySet.display_name_zh_tw;
        strategySetPolicy.value = strategySet.policy;
        strategySetMinimum.value = String(strategySet.minimum_trigger_count);
        strategySetChangeNote.value = "";
        const memberVersionIds = new Set(strategySet.members.map((member) => member.strategy_version_id));
        strategySetMembers.querySelectorAll("[data-strategy-set-version]").forEach((input) => {
          input.checked = memberVersionIds.has(input.value);
        });
        syncStrategySetMinimumControl();
        strategySetMessage.textContent = `正在修改「${strategySet.display_name_zh_tw}」；儲存後會新增 v${strategySet.version_number + 1}，原版本仍會保留。`;
        strategySetName.focus();
      }

      async function archiveAtomicStrategySet(strategySetVersionId) {
        const strategySet = state.strategyCatalog.strategySets.find((set) => set.strategy_set_version_id === strategySetVersionId);
        if (!strategySet) {
          strategySetMessage.textContent = "找不到要刪除的策略組合，請重新整理。";
          return;
        }
        const confirmed = window.confirm(`確定刪除策略組合「${strategySet.display_name_zh_tw}」？\n\n它會從新回測與 Local Paper 的可用清單移除，但歷史快照仍會保留。`);
        if (!confirmed) return;
        try {
          await atomicMutation(`/api/strategy-sets/${encodeURIComponent(strategySetVersionId)}`, "DELETE", {
            actor_id: "local-researcher",
            change_note: `封存策略組合「${strategySet.display_name_zh_tw}」；保留歷史精確版本快照。`
          }, "strategy-set-archive");
          if (editingStrategySetVersionId === strategySetVersionId) resetStrategySetEditor();
          await refreshStrategyCatalog();
          strategySetMessage.textContent = `策略組合「${strategySet.display_name_zh_tw}」已刪除；歷史快照仍保留。`;
        } catch (error) {
          strategySetMessage.textContent = `策略組合刪除失敗：${error.message}`;
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
          const revisionBase = editingStrategySetVersionId;
          const endpoint = revisionBase
            ? `/api/strategy-sets/${encodeURIComponent(revisionBase)}/revisions`
            : "/api/strategy-sets";
          const payload = await atomicMutation(endpoint, "POST", {
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
          }, revisionBase ? "strategy-set-revise" : "strategy-set-create");
          resetStrategySetEditor();
          await refreshStrategyCatalog();
          strategySetMessage.textContent = revisionBase
            ? `策略組合「${payload.strategy_set.display_name_zh_tw}」已新增 v${payload.strategy_set.version_number}；原版本仍保留。`
            : `策略組合「${payload.strategy_set.display_name_zh_tw}」已保存。`;
        } catch (error) {
          strategySetMessage.textContent = `策略組合${editingStrategySetVersionId ? "修改" : "建立"}失敗：${error.message}`;
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
        const projection = state.backtest.atomicDataset;
        const readiness = projection?.available ? `已鎖定 ${escapeHtml(projection.dataset_id)}` : "預設 Dataset binding 尚未就緒";
        backtestNotice.innerHTML = `<strong>${escapeHtml(capabilities.database)}</strong> 保存 immutable run、策略版本、資料快照與交易紀錄。${readiness}。<br>${escapeHtml(capabilities.safety)}`;
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
        `).join("") : '<p class="backtest-empty">尚未建立回測。回到「設定策略組合」即可開始。</p>';
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
        const [capabilities, runsPayload, qualificationPayload] = await Promise.all([
          backtestFetch("/api/backtests/capabilities"),
          backtestFetch("/api/backtests/runs"),
          backtestFetch("/api/backtests/qualifications").catch((error) => ({ qualifications: [], unavailable: error.message }))
        ]);
        state.backtest.capabilities = capabilities;
        state.backtest.runs = runsPayload.runs || [];
        state.backtest.qualifications = qualificationPayload.qualifications || [];
        state.backtest.qualificationUnavailable = qualificationPayload.unavailable || null;
        await refreshStrategyCatalog();
        renderAtomicLauncherOptions();
        await refreshAtomicDatasetProjection();
        renderBacktestNotice();
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

      async function submitAtomicBacktestRun(event) {
        event.preventDefault();
        if (!atomicBacktestSet.value) {
          atomicBacktestMessage.textContent = "請先選擇策略組合。";
          return;
        }
        atomicBacktestSubmit.disabled = true;
        atomicBacktestSubmit.textContent = "建立中…";
        const requestBody = pendingAtomicBacktestRequest || {
          strategy_set_version_id: atomicBacktestSet.value,
          starting_cash: document.getElementById("atomic-backtest-cash").value,
          position_fraction: document.getElementById("atomic-backtest-position-fraction").value,
          change_note: document.getElementById("atomic-backtest-note").value.trim(),
          baseline_run_id: atomicBacktestBaseline.value || null,
          expected_binding_revision: state.backtest.atomicDataset?.resolution_mode === "DEFAULT_BINDING" ? state.backtest.atomicDataset.binding_revision : null,
          expected_dataset_digest: state.backtest.atomicDataset?.resolution_mode === "DEFAULT_BINDING" ? state.backtest.atomicDataset.dataset_digest : null,
          actor_id: "local-researcher"
        };
        try {
          const payload = await atomicMutation("/api/backtests/runs/atomic", "POST", requestBody, "atomic-backtest");
          pendingAtomicBacktestRequest = null;
          state.backtest.activeRunId = payload.run.run_id;
          state.backtest.activeResult = { run: payload.run };
          atomicBacktestMessage.textContent = "原子策略回測已建立；Run 已自動鎖定歷史快照、精確版本與 Feature 證據。";
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(payload.run.run_id);
        } catch (error) {
          if (error.httpStatus === 409) {
            pendingAtomicBacktestRequest = null;
            await refreshAtomicDatasetProjection();
            atomicBacktestMessage.textContent = `Dataset binding 已變更，請確認更新後的資料範圍再送出：${error.message}`;
          } else {
            if (!error.httpStatus) pendingAtomicBacktestRequest = requestBody;
            atomicBacktestMessage.textContent = `無法建立原子策略回測：${error.message}`;
          }
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
          atomicBacktestMessage.textContent = `無法${action === "cancel" ? "取消" : "重試"}回測：${error.message}`;
        }
      }

      async function cloneBacktestRun() {
        const runId = state.backtest.activeRunId;
        const changeNote = document.getElementById("backtest-change-note").value.trim();
        if (!runId) { atomicBacktestMessage.textContent = "請先選擇一個既有回測。"; return; }
        if (!changeNote) { atomicBacktestMessage.textContent = "請填寫調整說明，才能建立可比較的 challenger。"; return; }
        try {
          const activeRun = state.backtest.activeResult?.run;
          const atomic = Boolean(activeRun?.config?.atomic_strategy_run_snapshot);
          if (!atomic) {
            atomicBacktestMessage.textContent = "舊版 Run 只保留查閱，請用原子策略組合建立新的回測。";
            return;
          }
          const payload = await atomicMutation(`/api/backtests/runs/${encodeURIComponent(runId)}/clone`, "POST", {
            idempotency_key: null,
            actor_id: "local-researcher",
            change_note: changeNote,
            overrides: {
              starting_cash: document.getElementById("atomic-backtest-cash").value,
              position_fraction: document.getElementById("atomic-backtest-position-fraction").value
            }
          }, "atomic-backtest-clone");
          state.backtest.activeRunId = payload.run.run_id;
          await refreshBacktestWorkspace();
          await loadBacktestRunDetails(payload.run.run_id);
        } catch (error) {
          atomicBacktestMessage.textContent = `無法複製回測：${error.message}`;
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
      strategyWorkflowTabs.forEach((tab) => {
        tab.addEventListener("click", () => setStrategyManagementView(tab.dataset.strategyTab));
        tab.addEventListener("keydown", handleStrategyTabKeydown);
      });
      strategyDraftValidate?.addEventListener("click", validateAtomicDraft);
      strategyDraftPublish?.addEventListener("click", publishAtomicDraft);
      strategyDraftClone?.addEventListener("click", cloneActiveAtomicDraft);
      strategySetForm?.addEventListener("submit", submitAtomicStrategySet);
      strategySetCancel?.addEventListener("click", () => {
        resetStrategySetEditor();
        strategySetMessage.textContent = "已取消修改，原版本沒有變更。";
      });
      strategyVersionCompare?.addEventListener("click", compareAtomicVersions);
      strategySetPolicy?.addEventListener("change", syncStrategySetMinimumControl);
      strategySetMinimum?.addEventListener("input", () => {
        if (strategySetPolicy.value !== "AT_LEAST_N") strategySetPolicy.value = "AT_LEAST_N";
        syncStrategySetMinimumControl();
      });
      atomicBacktestForm?.addEventListener("submit", submitAtomicBacktestRun);
      atomicBacktestSet?.addEventListener("change", refreshAtomicDatasetProjection);
      atomicBacktestBaseline?.addEventListener("change", refreshAtomicDatasetProjection);
      qualificationForm?.addEventListener("submit", submitBacktestQualification);
      qualificationAddFold?.addEventListener("click", addQualificationFold);
      addQualificationFold();
      addQualificationFold();
      setStrategyManagementView(state.strategyCatalog.activeView || "editor");


  return { refreshStrategyCatalog, setStrategyCatalogDrawer, setBacktestDrawer, refreshBacktestWorkspace, cloneBacktestRun, compareBacktestRuns, pollBacktestWorkspace };
}
