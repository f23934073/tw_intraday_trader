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
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        return payload;
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

      function renderStrategyCatalog() {
        const strategies = state.strategyCatalog.strategies;
        strategyCatalogNotice.textContent = `${strategies.length} 個策略版本；相同 strategy_id 的邏輯變更請建立新 version。`;
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
        strategyCatalogNotice.textContent = "正在讀取策略目錄…";
        const query = new URLSearchParams();
        if (strategyCatalogRole.value) query.set("role", strategyCatalogRole.value);
        if (strategyCatalogPhase.value) query.set("session_phase", strategyCatalogPhase.value);
        if (strategyCatalogStatus.value) query.set("status", strategyCatalogStatus.value);
        try {
          const payload = await backtestFetch(`/api/strategies${query.toString() ? `?${query.toString()}` : ""}`);
          state.strategyCatalog.strategies = payload.strategies || [];
          renderStrategyCatalog();
        } catch (error) {
          strategyCatalogNotice.textContent = `策略目錄讀取失敗：${error.message}`;
          strategyCatalogList.innerHTML = '<p class="backtest-empty">請稍後重新整理。</p>';
        } finally {
          state.strategyCatalog.loading = false;
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
        const [capabilities, incrementalSync, datasetsPayload, strategiesPayload, runsPayload] = await Promise.all([
          backtestFetch("/api/backtests/capabilities"),
          backtestFetch("/api/backtests/datasets/incremental-sync"),
          backtestFetch("/api/backtests/datasets"),
          backtestFetch("/api/backtests/strategies"),
          backtestFetch("/api/backtests/runs")
        ]);
        state.backtest.capabilities = capabilities;
        state.backtest.incrementalSync = incrementalSync;
        state.backtest.datasets = datasetsPayload.datasets || [];
        state.backtest.strategies = strategiesPayload.strategies || [];
        state.backtest.runs = runsPayload.runs || [];
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

      async function changeBacktestRun(runId, action) {
        try {
          const path = action === "cancel" ? `/api/backtests/runs/${encodeURIComponent(runId)}/cancel` : `/api/backtests/runs/${encodeURIComponent(runId)}/retry`;
          const options = action === "cancel" ? { method: "POST" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idempotency_key: newIdempotencyKey("backtest-retry") }) };
          const payload = await backtestFetch(path, options);
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
          const request = backtestRunRequest();
          const payload = await backtestFetch(`/api/backtests/runs/${encodeURIComponent(runId)}/clone`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ idempotency_key: newIdempotencyKey("backtest-clone"), change_note: changeNote, overrides: { strategy_set: { entry_strategy_ids: request.entry_strategy_ids, exit_strategy_ids: request.exit_strategy_ids, entry_policy: request.entry_policy, exit_policy: request.exit_policy, entry_min_trigger_count: request.entry_min_trigger_count, exit_min_trigger_count: request.exit_min_trigger_count, priority_order: request.priority_order }, starting_cash: request.starting_cash, position_fraction: request.position_fraction, target_win_rate: request.target_win_rate, minimum_oos_trades: request.minimum_oos_trades } })
          });
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

      function pollBacktestWorkspace() {
        if (document.visibilityState !== "visible" || !backtestDrawer.classList.contains("open") || state.backtest.polling) return;
        state.backtest.polling = true;
        refreshBacktestWorkspace().then(async () => {
          const active = state.backtest.runs.find((run) => run.run_id === state.backtest.activeRunId);
          if (active?.status === "COMPLETED" && state.backtest.activeResult?.run?.status !== "COMPLETED") await loadBacktestRunDetails(active.run_id);
        }).catch((error) => { backtestNotice.textContent = `回測工作區更新失敗：${error.message}`; }).finally(() => { state.backtest.polling = false; });
      }


  return { refreshStrategyCatalog, setStrategyCatalogDrawer, setBacktestDrawer, refreshBacktestWorkspace, startBacktestDatasetSync, submitBacktestRun, cloneBacktestRun, compareBacktestRuns, pollBacktestWorkspace };
}
