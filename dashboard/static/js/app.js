import { createCandidateWorkspace } from "./workspaces/candidates.js";
import { createSimulationWorkspace } from "./workspaces/simulation.js?v=20260823-local-paper-settings-v1";
import { createMomentumWorkspace } from "./workspaces/momentum.js";
import { createBacktestWorkspace } from "./workspaces/backtest.js?v=20260821-atomic-strategy-v2";

        const state = {
          workspace: "overview",
          workspaceBeforeDrawer: "overview",
          snapshot: null,
        selectedSymbol: null,
        historyPeriod: "1d",
        historyByKey: {},
        historyLoadingKey: null,
        simulationProjectionLoading: false,
        simulationSocket: null,
        simulationSocketState: "idle",
        simulationReconnectAttempt: 0,
        simulationReconnectTimer: null,
        momentum: null,
        momentumLoading: false,
        momentumRenderKey: null,
        momentumStreamId: null,
        momentumRevision: null,
        momentumSocket: null,
        momentumSocketState: "idle",
        momentumTransportGeneration: 0,
        momentumPendingBootstrapGeneration: null,
        momentumReconnectAttempt: 0,
        momentumReconnectTimer: null,
        momentumLastHeartbeatAt: null,
        momentumDialogSymbol: null,
        momentumDialogLastItem: null,
        strategyCatalog: {
          strategies: [],
          templates: [],
          drafts: [],
          versions: [],
          strategySets: [],
          auditEvents: [],
          selectedTemplateId: null,
          activeDraftId: null,
          csrfToken: null,
          atomicAvailable: false,
          loading: false
        },
        backtest: {
          capabilities: null,
          incrementalSync: null,
          datasets: [],
          strategies: [],
          runs: [],
          qualifications: [],
          qualificationUnavailable: null,
          activeRunId: null,
          activeResult: null,
          activeTrade: null,
          activeTab: "data",
          polling: false
        }
      };
      const sourceLabels = { AUTO: "自動", MANUAL: "手動" };
      const ruleLabels = {
        gap_up: "跳空開高",
        high_volume: "高成交量",
        relative_volume: "相對成交量",
        gap_score: "跳空分數",
        above_vwap: "站上 VWAP",
        stop_loss: "停損",
        take_profit: "停利"
      };
      const premarketStatusLabels = {
        READY: "完整性已驗證",
        PENDING: "等待完整性證據",
        NOT_APPLICABLE: "今日不適用",
        DEGRADED: "部分資料可用",
        UNAVAILABLE: "資料不可用"
      };
      const premarketReconciliationLabels = {
        PENDING: "等待中",
        MATCHED: "已相符",
        MISMATCHED: "有差異",
        PARTIAL: "部分完成",
        UNAVAILABLE: "不可用"
      };
      const premarketReasonLabels = {
        QUERY_NOT_YET_ELIGIBLE: "尚未到可查詢時間",
        SOURCE_COMPLETENESS_UNQUALIFIED: "來源完整性尚未證明",
        SESSION_START_NOT_OBSERVED: "缺少夜盤起始證據",
        SESSION_END_NOT_OBSERVED: "缺少夜盤結束證據",
        CONTRACT_IDENTITY_UNRESOLVED: "實際月份尚未解析",
        PROVIDER_REFERENCE_UNAVAILABLE: "Shioaji 參考價不可用",
        SOURCE_QUERY_FAILED: "來源查詢失敗",
        SOURCE_CAPABILITY_UNAVAILABLE: "來源不支援台指期夜盤",
        CALENDAR_COVERAGE_UNAVAILABLE: "交易日行事曆未涵蓋",
        SESSION_NOT_APPLICABLE: "本交易日沒有適用夜盤",
        FEATURE_DISABLED: "功能目前關閉"
      };
      const escapeMap = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };

      const statusElement = document.getElementById("status");
      const errorElement = document.getElementById("error-message");
      const refreshButton = document.getElementById("refresh-button");
      const detailPanel = document.getElementById("detail-panel");
      const momentumStatus = document.getElementById("momentum-status");
      const momentumSource = document.getElementById("momentum-source");
      const momentumContent = document.getElementById("momentum-content");
      const momentumDetailDialog = document.getElementById("momentum-detail-dialog");
      const momentumDetailHeading = document.getElementById("momentum-detail-heading");
      const momentumDetailTitleMeta = document.getElementById("momentum-detail-title-meta");
      const momentumDetailStatus = document.getElementById("momentum-detail-status");
      const momentumDetailBody = document.getElementById("momentum-detail-body");
      const momentumDetailOrder = document.getElementById("momentum-detail-order");
      const momentumDetailClose = document.getElementById("momentum-detail-close");
      const simulationStatus = document.getElementById("simulation-status");
      const shioajiUsageStatus = document.getElementById("shioaji-usage-status");
      const premarketContextHealth = document.getElementById("premarket-context-health");
      const premarketContent = document.getElementById("premarket-content");
      const ordersToggle = document.getElementById("orders-toggle");
      const orderTicketButton = document.getElementById("order-ticket-button");
      const ordersDrawer = document.getElementById("orders-drawer");
      const ordersPanel = document.getElementById("orders-panel");
      const ordersClose = document.getElementById("orders-close");
      const ordersBackdrop = document.getElementById("orders-backdrop");
      const orderForm = document.getElementById("order-form");
      const orderSymbol = document.getElementById("order-symbol");
      const orderSide = document.getElementById("order-side");
      const orderPrice = document.getElementById("order-price");
      const orderSubmit = document.getElementById("order-submit");
      const orderError = document.getElementById("order-error");
      const orderMessage = document.getElementById("order-message");
      const positionsToggle = document.getElementById("positions-toggle");
      const positionsDrawer = document.getElementById("positions-drawer");
      const positionsPanel = document.getElementById("positions-panel");
      const positionsClose = document.getElementById("positions-close");
      const positionsBackdrop = document.getElementById("positions-backdrop");
      const simulationSettingsToggle = document.getElementById("simulation-settings-toggle");
      const simulationSettingsDrawer = document.getElementById("simulation-settings-drawer");
      const simulationSettingsClose = document.getElementById("simulation-settings-close");
      const simulationSettingsBackdrop = document.getElementById("simulation-settings-backdrop");
      const strategyToggle = document.getElementById("strategy-toggle");
      const strategyCatalogDrawer = document.getElementById("strategy-catalog-drawer");
      const strategyCatalogPanel = document.getElementById("strategy-catalog-panel");
      const strategyCatalogClose = document.getElementById("strategy-catalog-close");
      const strategyCatalogBackdrop = document.getElementById("strategy-catalog-backdrop");
      const strategyCatalogRefreshButton = document.getElementById("strategy-catalog-refresh");
      const strategyCatalogRole = document.getElementById("strategy-catalog-role");
      const strategyCatalogPhase = document.getElementById("strategy-catalog-phase");
      const strategyCatalogStatus = document.getElementById("strategy-catalog-status");
      const strategyCatalogNotice = document.getElementById("strategy-catalog-notice");
      const strategyCatalogList = document.getElementById("strategy-catalog-list");
      const backtestToggle = document.getElementById("backtest-toggle");
      const backtestDrawer = document.getElementById("backtest-drawer");
      const backtestPanel = document.getElementById("backtest-panel");
      const backtestClose = document.getElementById("backtest-close");
      const backtestBackdrop = document.getElementById("backtest-backdrop");
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
      const sidebarToggle = document.getElementById("sidebar-toggle");
      const overviewView = document.getElementById("overview-view");
      const candidatesView = document.getElementById("candidates-view");
      const momentumView = document.getElementById("momentum-view");
      const workspaceKicker = document.getElementById("workspace-kicker");
      const workspaceHeading = document.getElementById("workspace-heading");
      const workspaceDescription = document.getElementById("workspace-description");
      const workspaceNavButtons = [...document.querySelectorAll("[data-workspace]")];
      const backtestTabs = [...document.querySelectorAll("[data-backtest-tab]")];

      const workspaceMeta = {
        overview: ["工作區", "市場總覽", "市場摘要、資料健康與盤前情境"],
        candidates: ["工作區", "候選清單", "選擇標的，查看規則分數、盤中快照與 K 線評估"],
        momentum: ["研究工具", "盤中動能", "即時候選策略、規則值與待確認告警"],
        strategy: ["研究工具", "策略管理", "參數草稿、不可變版本、策略組合與歷史回測"],
        backtest: ["研究工具", "歷史回測", "資料準備、策略組合、結果與比較"],
        orders: ["本機紙上模擬", "委託", "查看送出、成交、取消與拒絕的委託"],
        "order-ticket": ["本機紙上模擬", "模擬下單", "建立只存在本機記憶體的限價委託"],
        positions: ["本機紙上模擬", "持倉", "查看已成交部位、行情與未實現損益"],
        "simulation-settings": ["本機紙上模擬", "模擬設定", "設定現金、每日買入額度與手續費"]
      };

      function setWorkspace(workspace) {
        state.workspace = workspace;
        closeMobileSidebar();
        const [kicker, heading, description] = workspaceMeta[workspace] || workspaceMeta.overview;
        workspaceKicker.textContent = kicker;
        workspaceHeading.textContent = heading;
        workspaceDescription.textContent = description;
        workspaceNavButtons.forEach((button) => {
          const active = button.dataset.workspace === workspace;
          button.classList.toggle("active", active);
          if (active) button.setAttribute("aria-current", "page");
          else button.removeAttribute("aria-current");
        });
        overviewView.classList.toggle("active", workspace === "overview");
        candidatesView.classList.toggle("active", workspace === "candidates");
        momentumView.classList.toggle("active", workspace === "momentum");
        const drawerNames = {
          orders: ["orders", "order-ticket"],
          positions: ["positions"],
          settings: ["simulation-settings"],
          strategy: ["strategy"],
          backtest: ["backtest"]
        };
        Object.entries(drawerNames).forEach(([drawerName, workspaceNames]) => {
          const drawer = { orders: ordersDrawer, positions: positionsDrawer, settings: simulationSettingsDrawer, strategy: strategyCatalogDrawer, backtest: backtestDrawer }[drawerName];
          if (!workspaceNames.includes(workspace)) {
            drawer.classList.remove("open");
            drawer.setAttribute("aria-hidden", "true");
            const toggle = { orders: ordersToggle, positions: positionsToggle, settings: simulationSettingsToggle, strategy: strategyToggle, backtest: backtestToggle }[drawerName];
            toggle.setAttribute("aria-expanded", "false");
          }
        });
      }

      function syncSidebarToggle() {
        const shell = document.querySelector(".app-shell");
        const mobile = window.matchMedia("(max-width: 700px)").matches;
        const expanded = mobile
          ? shell.classList.contains("sidebar-mobile-open")
          : !shell.classList.contains("sidebar-collapsed");
        sidebarToggle.setAttribute("aria-expanded", String(expanded));
        sidebarToggle.setAttribute("aria-label", expanded ? "隱藏功能導覽" : "顯示功能導覽");
      }

      function closeMobileSidebar() {
        if (!window.matchMedia("(max-width: 700px)").matches) return;
        document.querySelector(".app-shell")?.classList.remove("sidebar-mobile-open");
        syncSidebarToggle();
      }

      function setBacktestTab(tabName) {
        state.backtest.activeTab = tabName;
        backtestTabs.forEach((tab) => {
          const active = tab.dataset.backtestTab === tabName;
          tab.classList.toggle("active", active);
          tab.setAttribute("aria-selected", String(active));
        });
        document.querySelectorAll("[data-backtest-panel]").forEach((panel) => {
          panel.classList.toggle("active", panel.dataset.backtestPanel === tabName);
        });
      }

      function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, (character) => escapeMap[character]);
      }

      function formatNumber(value, digits = 2) {
        if (value === null || value === undefined) return "—";
        return Number(value).toLocaleString("zh-TW", {
          maximumFractionDigits: digits,
          minimumFractionDigits: digits
        });
      }

      function formatVolume(value) {
        if (value === null || value === undefined) return "—";
        if (value >= 10000) return `${formatNumber(value / 10000, value % 10000 === 0 ? 0 : 1)} 萬`;
        return `${Number(value).toLocaleString("zh-TW")} 股`;
      }

      function formatPercent(value) {
        if (value === null || value === undefined) return "—";
        const sign = value >= 0 ? "+" : "";
        return `${sign}${formatNumber(value)}%`;
      }

      function formatQuoteTime(timestamp) {
        if (!timestamp) return "等待即時行情";
        return new Date(timestamp).toLocaleTimeString("zh-TW", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
        });
      }

      function formatSource(sources) {
        return sources.map((source) => sourceLabels[source] || source).join("＋");
      }

      function formatRule(rule) {
        return ruleLabels[rule] || rule;
      }

      function newIdempotencyKey(prefix) {
        if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
        return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      }


const services = {};
const candidates = createCandidateWorkspace({ state, services, escapeHtml, formatNumber, formatPercent, formatVolume, formatQuoteTime, formatRule, formatSource });
const simulation = createSimulationWorkspace({ state, escapeHtml, formatNumber, formatPercent, formatQuoteTime, newIdempotencyKey, setWorkspace });
const momentum = createMomentumWorkspace({ state, services, escapeHtml, formatNumber, formatPercent, formatVolume, formatRule, formatSource, ruleLabels, setWorkspace });
const backtest = createBacktestWorkspace({ state, escapeHtml, formatNumber, newIdempotencyKey, setWorkspace });
Object.assign(services, candidates, simulation, momentum, backtest);
const { getVisibleCandidates, renderCandidates, selectCandidate, renderCandidateDetail, loadSelectedHistory } = candidates;
const { renderSimulation, renderPositions, renderOrders, renderDataHealth, openOrderTicket, setOrdersDrawer, setPositionsDrawer, setSimulationSettingsDrawer, loadSimulationProjection, loadAutomatedStrategyStatus, pollSimulationProjection, pollAutomatedStrategyStatus, bootstrapSimulationStream, submitSimulationOrder, cancelSimulationOrder } = simulation;
const { renderMomentum, syncMomentumDialog, openMomentumDialog, closeMomentumDialog, openOrderTicketFromMomentum, bootstrapMomentumStream, checkMomentumHeartbeat, pollMomentumProjection } = momentum;
const { refreshStrategyCatalog, setStrategyCatalogDrawer, setBacktestDrawer, refreshBacktestWorkspace, startBacktestDatasetSync, submitBacktestRun, cloneBacktestRun, compareBacktestRuns, pollBacktestWorkspace } = backtest;

      function renderPremarketContext(context) {
        const status = context?.health?.state || context?.status || "UNAVAILABLE";
        const metrics = context?.metrics || {};
        const providerReference = context?.provider_reference || {};
        const identity = context?.contract_identity || {};
        const reconciliation = context?.reconciliation || { status: "PENDING" };
        const reasons = context?.health?.reasons || [];
        const reasonText = reasons.map((reason) => premarketReasonLabels[reason] || reason).join("；");
        const statusLabel = premarketStatusLabels[status] || status;
        const reconciliationLabel = premarketReconciliationLabels[reconciliation.status] || reconciliation.status || "等待中";
        const statusClass = status.toLowerCase().replaceAll("_", "-");
        premarketContextHealth.className = `premarket-state ${statusClass}`;
        premarketContextHealth.textContent = statusLabel;
        premarketContent.setAttribute("aria-busy", "false");

        if (metrics.close === null || metrics.close === undefined) {
          premarketContent.innerHTML = `
            <p class="premarket-empty"><strong>${escapeHtml(statusLabel)}</strong>${reasonText ? ` · ${escapeHtml(reasonText)}` : ""}</p>
            <div class="premarket-meta"><span>查詢資格 <strong>${formatQuoteTime(context?.query_not_before)}</strong></span><span>TAIFEX 對帳 <strong id="premarket-reconciliation-status">${escapeHtml(reconciliationLabel)}</strong></span></div>
            <p class="premarket-disclaimer">市場情境，不等於個股開盤預測。</p>
          `;
          return;
        }

        const resolvedContract = identity.resolved_contract_code
          ? `${context.contract_alias} → ${identity.resolved_contract_code}`
          : `${context.contract_alias || "TXFR1"} → 未解析`;
        premarketContent.innerHTML = `
          <div class="premarket-grid">
            <article class="premarket-item"><span>夜開至夜收</span><strong>${formatPercent(context.metrics?.session_move_pct)}</strong></article>
            <article class="premarket-item"><span>夜收</span><strong>${formatNumber(metrics.close)}</strong></article>
            <article class="premarket-item"><span>Shioaji 參考價</span><strong>${formatNumber(providerReference.price)}</strong></article>
            <article class="premarket-item"><span>相對 Shioaji 參考價</span><strong>${formatPercent(context.metrics?.provider_reference_change_pct)}</strong></article>
          </div>
          <div class="premarket-meta">
            <span>夜盤高／低 <strong>${formatNumber(metrics.high)}／${formatNumber(metrics.low)}</strong></span>
            <span>查詢時間 <strong>${formatQuoteTime(context.queried_at)}</strong></span>
            <span>合約 <strong>${escapeHtml(resolvedContract)}</strong></span>
            <span>完整性 <strong>${escapeHtml(context.completeness?.status || "UNKNOWN")}</strong></span>
            <span>TAIFEX 對帳 <strong id="premarket-reconciliation-status">${escapeHtml(reconciliationLabel)}</strong></span>
          </div>
          ${reasonText ? `<p class="premarket-empty">${escapeHtml(reasonText)}</p>` : ""}
          <p class="premarket-disclaimer">市場情境，不等於個股開盤預測。</p>
        `;
      }

      function render(snapshot) {
        state.snapshot = snapshot;
        const candidates = getVisibleCandidates(snapshot.candidates);
        const simulation = snapshot.simulation || {
          session: { label: "本機紙上模擬", available_cash: null, notice: "尚未取得模擬 session。" },
          orders: [],
          positions: []
        };
        if (!candidates.some((candidate) => candidate.symbol === state.selectedSymbol)) {
          state.selectedSymbol = candidates[0]?.symbol || null;
        }

        renderStatus(snapshot);
        renderPremarketContext(snapshot.premarket_context);
        renderSimulation(simulation);
        renderCandidates(candidates);
        renderCandidateDetail(candidates.find((candidate) => candidate.symbol === state.selectedSymbol));
        renderPositions(simulation.positions);
        renderOrders(simulation.orders);
        renderDataHealth(snapshot, simulation);
        syncMomentumDialog();
      }

      function renderStatus(snapshot) {
        const timestamp = new Date(snapshot.generated_at).toLocaleTimeString("zh-TW", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
        });
        statusElement.innerHTML = `<span class="status-dot" aria-hidden="true"></span>單次快照 · ${escapeHtml(snapshot.provider.name)} · ${timestamp}`;
      }

      function formatMiB(bytes) {
        return `${(Number(bytes) / 1024 / 1024).toFixed(1)} MiB`;
      }

      function renderProviderUsage(usage) {
        const exhausted = Boolean(usage?.supported && usage?.exhausted);
        shioajiUsageStatus.hidden = !exhausted;
        if (!exhausted) return;

        const used = formatMiB(usage.bytes_used);
        const limit = formatMiB(usage.limit_bytes);
        shioajiUsageStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>Shioaji 流量已超過 · ${escapeHtml(used)} / ${escapeHtml(limit)}`;
      }

      async function loadProviderUsage() {
        const response = await fetch("/api/dashboard/provider-usage", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        renderProviderUsage(await response.json());
      }

      function pollProviderUsage() {
        if (document.visibilityState !== "visible") return;
        loadProviderUsage().catch(() => {});
      }

      async function loadSnapshot(refresh) {
        refreshButton.disabled = true;
        refreshButton.textContent = refresh ? "掃描中…" : "載入中…";
        errorElement.style.display = "none";

        try {
          const response = await fetch(refresh ? "/api/dashboard/refresh" : "/api/dashboard/snapshot", {
            method: refresh ? "POST" : "GET"
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          state.historyByKey = {};
          state.historyLoadingKey = null;
          render(await response.json());
          loadSelectedHistory();
        } catch (error) {
          errorElement.textContent = `無法取得掃描快照：${error.message}`;
          errorElement.style.display = "block";
        } finally {
          refreshButton.disabled = false;
          refreshButton.textContent = "重新掃描";
        }
      }

      sidebarToggle.addEventListener("click", () => {
        const mobile = window.matchMedia("(max-width: 700px)").matches;
        const shell = document.querySelector(".app-shell");
        if (mobile) {
          const open = !shell.classList.contains("sidebar-mobile-open");
          shell.classList.toggle("sidebar-mobile-open", open);
        } else {
          const collapsed = !shell.classList.contains("sidebar-collapsed");
          shell.classList.toggle("sidebar-collapsed", collapsed);
        }
        syncSidebarToggle();
      });
      workspaceNavButtons.filter((button) => ["overview", "candidates", "momentum"].includes(button.dataset.workspace)).forEach((button) => {
        button.addEventListener("click", () => {
          setWorkspace(button.dataset.workspace);
        });
      });
      window.addEventListener("resize", syncSidebarToggle);
      syncSidebarToggle();
      backtestTabs.forEach((tab) => tab.addEventListener("click", () => setBacktestTab(tab.dataset.backtestTab)));
      refreshButton.addEventListener("click", () => loadSnapshot(true).finally(pollProviderUsage));
      momentumContent.addEventListener("click", (event) => {
        const row = event.target.closest("[data-momentum-symbol]");
        if (row) openMomentumDialog(row.dataset.momentumSymbol);
      });
      momentumDetailOrder.addEventListener("click", openOrderTicketFromMomentum);
      momentumDetailClose.addEventListener("click", () => closeMomentumDialog());
      momentumDetailDialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeMomentumDialog();
      });
      momentumDetailDialog.addEventListener("click", (event) => {
        if (event.target === momentumDetailDialog) closeMomentumDialog();
      });
      momentumDetailBody.addEventListener("click", (event) => {
        if (event.target.closest('[data-momentum-detail-action="candidate"]')) openCandidateFromMomentum();
      });
      ordersToggle.addEventListener("click", () => {
        setOrdersDrawer(true);
        pollSimulationProjection();
      });
      orderTicketButton.addEventListener("click", () => openOrderTicket());
      ordersClose.addEventListener("click", () => setOrdersDrawer(false));
      ordersBackdrop.addEventListener("click", () => setOrdersDrawer(false));
      orderForm.addEventListener("submit", submitSimulationOrder);
      positionsToggle.addEventListener("click", () => {
        setPositionsDrawer(true);
        pollSimulationProjection();
      });
      positionsClose.addEventListener("click", () => setPositionsDrawer(false));
      positionsBackdrop.addEventListener("click", () => setPositionsDrawer(false));
      simulationSettingsToggle.addEventListener("click", () => setSimulationSettingsDrawer(true));
      simulationSettingsClose.addEventListener("click", () => setSimulationSettingsDrawer(false));
      simulationSettingsBackdrop.addEventListener("click", () => setSimulationSettingsDrawer(false));
      strategyToggle.addEventListener("click", async () => {
        setStrategyCatalogDrawer(true);
        await refreshStrategyCatalog();
      });
      strategyCatalogClose.addEventListener("click", () => setStrategyCatalogDrawer(false));
      strategyCatalogBackdrop.addEventListener("click", () => setStrategyCatalogDrawer(false));
      strategyCatalogRefreshButton.addEventListener("click", () => refreshStrategyCatalog());
      [strategyCatalogRole, strategyCatalogPhase, strategyCatalogStatus].forEach((select) => {
        select.addEventListener("change", () => refreshStrategyCatalog());
      });
      backtestToggle.addEventListener("click", async () => {
        setBacktestDrawer(true);
        try {
          await refreshBacktestWorkspace();
        } catch (error) {
          backtestNotice.textContent = `無法讀取回測工作區：${error.message}`;
        }
      });
      backtestClose.addEventListener("click", () => setBacktestDrawer(false));
      backtestBackdrop.addEventListener("click", () => setBacktestDrawer(false));
      backtestRefreshButton.addEventListener("click", () => refreshBacktestWorkspace().catch((error) => { backtestNotice.textContent = `無法重新整理：${error.message}`; }));
      backtestSyncButton.addEventListener("click", startBacktestDatasetSync);
      backtestRunForm.addEventListener("submit", submitBacktestRun);
      backtestCloneButton.addEventListener("click", cloneBacktestRun);
      backtestCompareButton.addEventListener("click", compareBacktestRuns);
      document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (momentumDetailDialog.open) {
          event.preventDefault();
          closeMomentumDialog();
        } else if (strategyCatalogDrawer.classList.contains("open")) {
          setStrategyCatalogDrawer(false);
        } else if (backtestDrawer.classList.contains("open")) {
          setBacktestDrawer(false);
        } else if (ordersDrawer.classList.contains("open")) {
          setOrdersDrawer(false);
        } else if (positionsDrawer.classList.contains("open")) {
          setPositionsDrawer(false);
        } else if (simulationSettingsDrawer.classList.contains("open")) {
          setSimulationSettingsDrawer(false);
        }
      });
      document.addEventListener("visibilitychange", () => {
        pollProviderUsage();
        pollSimulationProjection();
        checkMomentumHeartbeat();
        pollMomentumProjection();
        pollBacktestWorkspace();
      });
      window.setInterval(pollSimulationProjection, 2000);
      window.setInterval(pollAutomatedStrategyStatus, 2000);
      window.setInterval(pollMomentumProjection, 2000);
      window.setInterval(checkMomentumHeartbeat, 5000);
      window.setInterval(pollBacktestWorkspace, 3000);
      window.setInterval(pollProviderUsage, 60000);
      refreshStrategyCatalog();
      bootstrapMomentumStream();
      loadAutomatedStrategyStatus().catch(() => {});
      pollProviderUsage();
      loadSnapshot(false).finally(bootstrapSimulationStream);
