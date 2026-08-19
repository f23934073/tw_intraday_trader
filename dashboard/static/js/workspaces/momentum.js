export function createMomentumWorkspace(context) {
  const { state, services, escapeHtml, formatNumber, formatPercent, formatVolume, formatRule, formatSource, ruleLabels, setWorkspace } = context;
  const momentumStatus = document.getElementById("momentum-status");
  const momentumSource = document.getElementById("momentum-source");
  const momentumContent = document.getElementById("momentum-content");
  const momentumDetailDialog = document.getElementById("momentum-detail-dialog");
  const momentumDetailHeading = document.getElementById("momentum-detail-heading");
  const momentumDetailTitleMeta = document.getElementById("momentum-detail-title-meta");
  const momentumDetailStatus = document.getElementById("momentum-detail-status");
  const momentumDetailBody = document.getElementById("momentum-detail-body");
  const momentumDetailClose = document.getElementById("momentum-detail-close");

      const momentumRuleLabels = {
        price_above_vwap: "站上 VWAP",
        breakout: "突破前高",
        return_2m: "2 分鐘動能",
        distance_to_limit: "距離漲停",
        volume_acceleration_2m: "成交量加速",
        external_ratio_rising: "外盤比上升",
        opening_volume_context: "開盤量能情境"
      };

      function formatMomentumTime(timestamp) {
        if (!timestamp) return "—";
        return new Date(timestamp).toLocaleTimeString("zh-TW", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
        });
      }

      const momentumFeatureLabels = {
        price: "即時價格",
        vwap: "VWAP",
        previous_intraday_high: "盤中前高",
        distance_to_limit: "距離漲停",
        return_2m: "2 分鐘報酬",
        volume_2m: "2 分鐘成交量",
        volume_acceleration_2m: "量能加速",
        external_ratio_session: "本日外盤比",
        bid_ask_ratio_5: "五檔委買／委賣比",
        book_imbalance_5: "五檔委託簿不平衡"
      };
      const momentumFeatureStatusLabels = {
        VALID: "有效",
        MISSING: "缺資料",
        STALE: "資料過期",
        UNVERIFIED: "尚未驗證"
      };

      function formatMomentumFeature(key, metric) {
        if (!metric || metric.status !== "VALID" || metric.value === null || metric.value === undefined) return "—";
        const value = Number(metric.value);
        if (!Number.isFinite(value)) return String(metric.value);
        if (["return_2m", "book_imbalance_5"].includes(key)) return formatPercent(value * 100);
        if (["distance_to_limit", "external_ratio_session"].includes(key)) return `${formatNumber(value * 100)}%`;
        if (key === "volume_2m") return formatVolume(value);
        if (key === "volume_acceleration_2m") return `${formatNumber(value)} 倍`;
        if (key === "bid_ask_ratio_5") return formatNumber(value);
        return formatNumber(value);
      }

      function renderMomentumMetric(key, metric) {
        const valid = metric?.status === "VALID";
        const stateLabel = momentumFeatureStatusLabels[metric?.status] || metric?.status || "尚無資料";
        const reason = !valid && metric?.reason ? ` · ${metric.reason}` : "";
        return `
          <article class="momentum-detail-metric ${valid ? "" : "invalid"}">
            <div class="momentum-detail-metric-label">${escapeHtml(momentumFeatureLabels[key] || key)}</div>
            <div class="momentum-detail-metric-value">${escapeHtml(formatMomentumFeature(key, metric))}</div>
            <div class="momentum-detail-metric-meta">${escapeHtml(stateLabel)} · ${formatMomentumTime(metric?.source_as_of)}${escapeHtml(reason)}</div>
          </article>
        `;
      }

      function momentumRuleState(detail) {
        if (detail.status !== "VALID") {
          return {
            className: String(detail.status || "missing").toLowerCase(),
            label: momentumFeatureStatusLabels[detail.status] || detail.status || "缺資料"
          };
        }
        return detail.passed
          ? { className: "passed", label: "成立" }
          : { className: "failed", label: "未成立" };
      }

      function renderMomentumRule(detail) {
        const stateValue = momentumRuleState(detail);
        const missingReason = detail.missing_reason ? `<span>原因 <strong>${escapeHtml(detail.missing_reason)}</strong></span>` : "";
        return `
          <article class="momentum-detail-rule ${escapeHtml(stateValue.className)}">
            <div>
              <div class="momentum-detail-rule-title">${escapeHtml(momentumRuleLabels[detail.rule] || detail.rule)}</div>
              <div class="momentum-detail-rule-state">${escapeHtml(stateValue.label)} · ${escapeHtml(detail.points_awarded)} / ${escapeHtml(detail.points_possible)} 分</div>
            </div>
            <div class="momentum-detail-rule-values">
              <span>觀察值 <strong>${escapeHtml(detail.observed_value ?? "—")}</strong></span>
              <span>門檻 <strong>${escapeHtml(detail.threshold ?? "—")}</strong></span>
              <span>資料時間 <strong>${formatMomentumTime(detail.source_as_of)}</strong></span>
              ${missingReason}
            </div>
          </article>
        `;
      }

      function momentumSnapshotCandidate(symbol) {
        return (state.snapshot?.candidates || []).find((candidate) => candidate.symbol === symbol) || null;
      }

      function renderMomentumCandidateSummary(candidate, item) {
        if (!candidate) {
          return '<div class="momentum-detail-summary">候選掃描快照目前沒有這檔標的；以下保留最後一筆盤中 projection，不會以其他資料補值。</div>';
        }
        const stock = candidate.stock || {};
        const candidateRules = (candidate.matched_rules || []).map(formatRule).join("、") || "—";
        const source = formatSource(candidate.sources || []) || "—";
        return `
          <div class="momentum-detail-summary">候選分數 <strong>${escapeHtml(candidate.score?.total ?? item.candidate_score ?? "—")} / ${escapeHtml(candidate.score?.max ?? item.candidate_score_max ?? "—")}</strong> · 來源 <strong>${escapeHtml(source)}</strong> · 候選規則 <strong>${escapeHtml(candidateRules)}</strong></div>
          <div class="momentum-detail-metrics">
            <article class="momentum-detail-metric"><div class="momentum-detail-metric-label">掃描快照價格</div><div class="momentum-detail-metric-value">${formatNumber(stock.price)}</div><div class="momentum-detail-metric-meta">${formatMomentumTime(stock.timestamp)}</div></article>
            <article class="momentum-detail-metric"><div class="momentum-detail-metric-label">開盤／昨收</div><div class="momentum-detail-metric-value">${formatNumber(stock.open)} / ${formatNumber(stock.previous_close)}</div><div class="momentum-detail-metric-meta">單次掃描快照</div></article>
            <article class="momentum-detail-metric"><div class="momentum-detail-metric-label">日高／日低</div><div class="momentum-detail-metric-value">${formatNumber(stock.high)} / ${formatNumber(stock.low)}</div><div class="momentum-detail-metric-meta">單次掃描快照</div></article>
            <article class="momentum-detail-metric"><div class="momentum-detail-metric-label">成交量／相對量</div><div class="momentum-detail-metric-value">${formatVolume(stock.volume)} / ${stock.relative_volume === null || stock.relative_volume === undefined ? "—" : `${formatNumber(stock.relative_volume)} 倍`}</div><div class="momentum-detail-metric-meta">VWAP ${formatNumber(stock.vwap)}</div></article>
          </div>
        `;
      }

      function setMomentumDialogStatus(message) {
        momentumDetailStatus.textContent = message || "";
        momentumDetailStatus.classList.toggle("visible", Boolean(message));
      }

      function renderMomentumDialog(item, { removed = false } = {}) {
        const scrollTop = momentumDetailBody.scrollTop;
        const focusedAction = momentumDetailBody.contains(document.activeElement)
          ? document.activeElement.dataset.momentumDetailAction
          : null;
        const candidate = momentumSnapshotCandidate(item.symbol);
        const signal = item.signal;
        const source = state.momentum?.source || {};
        momentumDetailHeading.textContent = `${item.symbol} ${item.name || candidate?.stock?.name || ""}`.trim();
        momentumDetailTitleMeta.innerHTML = `
          <span class="momentum-detail-badge ${item.availability === "EVALUATED" ? "evaluated" : ""}">${escapeHtml(item.availability_label || "資料狀態未知")}</span>
          <span>${escapeHtml(item.current_stage_label || "等待資料")}</span>
          <span>訊號 ${formatMomentumTime(item.as_of)}</span>
        `;
        setMomentumDialogStatus(
          removed
            ? "此標的已離開目前候選清單，以下保留最後一次成功更新的資料。"
            : source.candidate_refresh_error
              ? `候選更新異常：${source.candidate_refresh_error}`
              : !item.intraday
                ? item.availability_label || "盤中明細尚未建立。"
                : ""
        );

        const intraday = item.intraday
          ? `<div class="momentum-detail-metrics">${Object.entries(item.intraday).map(([key, metric]) => renderMomentumMetric(key, metric)).join("")}</div>`
          : '<div class="momentum-detail-summary">尚未取得完整 Tick／BidAsk feature；保留候選資訊並等待資料暖機。</div>';
        const rules = signal?.details?.length
          ? `<div class="momentum-detail-rules">${signal.details.map(renderMomentumRule).join("")}</div>`
          : '<div class="momentum-detail-summary">目前沒有可顯示的盤中規則證據。</div>';
        const blockReasons = signal?.block_reasons?.length
          ? `<div class="momentum-detail-summary">阻擋原因：<strong>${escapeHtml(signal.block_reasons.join("、"))}</strong></div>`
          : "";
        const candidateAction = candidate
          ? '<button class="momentum-detail-candidate-link" type="button" data-momentum-detail-action="candidate">前往候選完整評估</button>'
          : "";
        momentumDetailBody.innerHTML = `
          <section class="momentum-detail-section">
            <div class="momentum-detail-section-heading"><h3>候選摘要</h3><span>Candidate scanner snapshot</span></div>
            ${renderMomentumCandidateSummary(candidate, item)}
          </section>
          <section class="momentum-detail-section">
            <div class="momentum-detail-section-heading"><h3>盤中行情與動能</h3><span>Tick／BidAsk feature projection</span></div>
            ${intraday}
          </section>
          <section class="momentum-detail-section">
            <div class="momentum-detail-section-heading"><h3>完整規則證據</h3><span>${signal ? `${escapeHtml(signal.passed_rule_count)} / ${escapeHtml(signal.total_rule_count)} 條成立` : "等待評估"}</span></div>
            ${blockReasons}${rules}
          </section>
          <section class="momentum-detail-section">
            <div class="momentum-detail-section-heading"><h3>資料來源與版本</h3><span>唯讀 projection</span></div>
            <div class="momentum-detail-provenance">
              <span>來源 <strong>${escapeHtml(source.name || "Shioaji Tick/BidAsk")}</strong></span>
              <span>連線 <strong>${escapeHtml(source.connection_state || "—")}</strong></span>
              <span>資料健康 <strong>${escapeHtml(signal?.data_health || source.data_health || "—")}</strong></span>
              <span>候選更新 <strong>${formatMomentumTime(source.candidate_as_of)}</strong></span>
              <span>訊號版本 <strong>${escapeHtml(signal?.config_version || "—")}</strong></span>
              <span>Feature 版本 <strong>${escapeHtml(signal?.feature_version || "—")}</strong></span>
              <span>證據覆蓋率 <strong>${signal ? `${formatNumber(Number(signal.coverage) * 100)}%` : "—"}</strong></span>
              <span>訊號時間 <strong>${formatMomentumTime(item.as_of)}</strong></span>
            </div>
          </section>
          <div class="momentum-detail-footer">
            <p>${escapeHtml(state.momentum?.disclaimer || "盤中分數是規則證據，不代表漲停機率，也不是買進或下單指令。")}</p>
            ${candidateAction}
          </div>
        `;
        momentumDetailBody.scrollTop = scrollTop;
        if (focusedAction) {
          momentumDetailBody.querySelector(`[data-momentum-detail-action="${focusedAction}"]`)?.focus({ preventScroll: true });
        }
      }

      function openMomentumDialog(symbol) {
        const normalized = String(symbol || "").trim().toUpperCase();
        const item = (state.momentum?.items || []).find((candidate) => candidate.symbol === normalized);
        if (!item) return;
        state.momentumDialogSymbol = normalized;
        state.momentumDialogLastItem = item;
        renderMomentumDialog(item);
        if (!momentumDetailDialog.open) momentumDetailDialog.showModal();
        requestAnimationFrame(() => momentumDetailClose.focus());
      }

      function closeMomentumDialog({ restoreFocus = true } = {}) {
        const symbol = state.momentumDialogSymbol;
        if (momentumDetailDialog.open) momentumDetailDialog.close();
        state.momentumDialogSymbol = null;
        state.momentumDialogLastItem = null;
        setMomentumDialogStatus("");
        if (!restoreFocus || !symbol) return;
        requestAnimationFrame(() => {
          const trigger = momentumContent.querySelector(`[data-momentum-symbol="${CSS.escape(symbol)}"] .momentum-row-trigger`);
          (trigger || document.getElementById("momentum-heading"))?.focus();
        });
      }

      function syncMomentumDialog(momentum = state.momentum) {
        if (!momentumDetailDialog.open || !state.momentumDialogSymbol) return;
        const item = (momentum?.items || []).find((candidate) => candidate.symbol === state.momentumDialogSymbol);
        if (item) {
          state.momentumDialogLastItem = item;
          renderMomentumDialog(item);
        } else if (state.momentumDialogLastItem) {
          renderMomentumDialog(state.momentumDialogLastItem, { removed: true });
        }
      }

      function openCandidateFromMomentum() {
        const symbol = state.momentumDialogSymbol;
        if (!symbol || !momentumSnapshotCandidate(symbol)) return;
        closeMomentumDialog({ restoreFocus: false });
        setWorkspace("candidates");
        services.selectCandidate(symbol);
        requestAnimationFrame(() => document.querySelector(`.candidate-button[data-symbol="${CSS.escape(symbol)}"]`)?.focus());
      }

      function renderMomentum(momentum) {
        const focusedMomentumSymbol = document.activeElement
          ?.closest?.("[data-momentum-symbol]")
          ?.dataset.momentumSymbol;
        state.momentum = momentum;
        state.momentumRenderKey = momentum.summary?.projection_digest || null;
        const pendingAlerts = (momentum.alerts || []).filter((alert) => !alert.acknowledged_at);
        const items = momentum.items || [];
        const evaluatedCount = momentum.summary?.evaluated_candidate_count || 0;
        const triggeredCount = momentum.summary?.triggered_candidate_count || 0;
        const live = momentum.source?.is_live === true && momentum.status === "live";
        momentumContent.setAttribute("aria-busy", "false");
        momentumStatus.classList.toggle("degraded", !live);
        momentumStatus.classList.toggle("active", live && triggeredCount > 0);
        momentumStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>${live ? `盤中評估 · ${evaluatedCount}/${items.length} 檔` : "即時盤中動能未啟動"}`;
        renderMomentumSourceStatus(momentum);

        if (!items.length) {
          const reason = momentum.source?.candidate_refresh_error || momentum.notice || "目前沒有可評估候選。";
          momentumContent.innerHTML = `<div class="momentum-empty">${escapeHtml(reason)}</div>`;
          syncMomentumDialog(momentum);
          return;
        }

        const rows = items.map((item) => {
          const signal = item.signal;
          const passedDetails = (signal?.details || []).filter((detail) => detail.passed === true);
          const passedValues = passedDetails.length
            ? passedDetails.map((detail) => `<span class="momentum-rule-value" title="門檻：${escapeHtml(detail.threshold || "—")}">${escapeHtml(momentumRuleLabels[detail.rule] || detail.rule)} ${escapeHtml(detail.observed_value || "—")}</span>`).join("")
            : '<span class="muted">—</span>';
          const strategy = signal
            ? `${signal.family_label} · ${signal.evaluation_status === "TRIGGERED" ? "觸發" : "未觸發"}`
            : item.availability_label;
          const score = signal
            ? `${signal.evidence_score} / ${signal.evidence_max_score}`
            : "—";
          const candidateRules = (item.candidate_matched_rules || []).map((rule) => ruleLabels[rule] || rule).join("、") || "—";
          return `
            <tr class="momentum-candidate-row" data-momentum-symbol="${escapeHtml(item.symbol)}">
              <td><button class="momentum-row-trigger" type="button" aria-label="查看 ${escapeHtml(item.symbol)} ${escapeHtml(item.name || "")} 盤中動能明細"><strong>${escapeHtml(item.symbol)}</strong><span class="muted">${escapeHtml(item.name || "")}</span></button></td>
              <td class="score">${escapeHtml(score)}<br><span class="muted">候選分 ${escapeHtml(item.candidate_score ?? "—")}</span></td>
              <td>${escapeHtml(strategy)}<br><span class="muted">${escapeHtml(item.current_stage_label || "—")}</span></td>
              <td><div class="momentum-strategy-list">${passedValues}</div></td>
              <td>${escapeHtml(candidateRules)}</td>
              <td class="${signal ? "" : "unavailable"}">${escapeHtml(item.availability_label || "—")}<br><span class="muted">${formatMomentumTime(item.as_of)}</span></td>
            </tr>
          `;
        }).join("");
        const alerts = pendingAlerts.length
          ? pendingAlerts.map((alert) => `
              <article class="momentum-alert">
                <strong>${escapeHtml(alert.headline)}</strong>
                <div class="momentum-alert-meta">${formatMomentumTime(alert.occurred_at)} · ${escapeHtml(alert.config_version)}</div>
                <button class="momentum-ack" type="button" data-momentum-alert="${escapeHtml(alert.alert_id)}">確認告警</button>
              </article>
            `).join("")
          : '<p class="momentum-disclaimer">目前沒有待確認告警；已確認事件仍保留在後端 audit history。</p>';

        momentumContent.innerHTML = `
          <div class="momentum-layout">
            <article class="momentum-card">
              <div class="momentum-evidence-header">
                <div class="momentum-evidence-score"><strong>${evaluatedCount} / ${items.length}</strong><span>已完成即時評估／全部候選</span></div>
                <div class="momentum-evidence-meta">觸發 ${triggeredCount} 檔<br>訂閱 ${momentum.source?.subscriptions_in_use || 0}/${(momentum.source?.subscription_max_symbols || 0) * 2}</div>
              </div>
              <div class="momentum-candidate-table" aria-label="候選盤中策略評估清單"><table><thead><tr><th>標的</th><th>盤中分數</th><th>策略結果</th><th>已成立規則與值</th><th>候選規則</th><th>資料狀態</th></tr></thead><tbody>${rows}</tbody></table></div>
              <p class="momentum-disclaimer">${escapeHtml(momentum.disclaimer)}</p>
            </article>
            <article class="momentum-card momentum-alert-card">
              <div class="momentum-alert-heading"><strong>待確認告警</strong><span>${pendingAlerts.length} 則</span></div>
              <div class="momentum-alerts">${alerts}</div>
            </article>
          </div>
        `;

        momentumContent.querySelectorAll("[data-momentum-alert]").forEach((button) => {
          button.addEventListener("click", () => acknowledgeMomentumAlert(button.dataset.momentumAlert));
        });
        if (focusedMomentumSymbol && !momentumDetailDialog.open) {
          requestAnimationFrame(() => {
            momentumContent
              .querySelector(`[data-momentum-symbol="${CSS.escape(focusedMomentumSymbol)}"] .momentum-row-trigger`)
              ?.focus({ preventScroll: true });
          });
        }
        syncMomentumDialog(momentum);
      }

      function momentumSocketIsOpen() {
        return state.momentumSocket?.readyState === WebSocket.OPEN;
      }

      function renderMomentumSourceStatus(momentum = state.momentum) {
        if (!momentum) return;
        const live = momentum.source?.is_live === true && momentum.status === "live";
        let transport = "HTTP 輪詢";
        if (momentum.stream?.enabled && momentumSocketIsOpen()) transport = "WebSocket 即時推送";
        else if (momentum.stream?.enabled && state.momentumSocketState === "connecting") transport = "資料同步中";
        else if (momentum.stream?.enabled) transport = "HTTP 輪詢備援";
        momentumSource.innerHTML = `<strong>${live ? `即時 Tick／BidAsk · ${transport}` : "即時資料不可用"}</strong><span>候選更新 ${formatMomentumTime(momentum.source?.candidate_as_of)} · 訊號 as of ${formatMomentumTime(momentum.source?.as_of)}</span>`;
      }

      function momentumWebSocketUrl(stream) {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const url = new URL(stream.resume_path || "/ws/dashboard/momentum", `${protocol}//${window.location.host}`);
        url.searchParams.set("stream_id", stream.stream_id);
        url.searchParams.set("since_revision", String(stream.revision));
        return url.toString();
      }

      function renderMomentumIfChanged(momentum) {
        const changed = state.momentumRenderKey !== momentum.summary?.projection_digest;
        state.momentum = momentum;
        if (!changed) return;
        renderMomentum(momentum);
        if (state.snapshot) services.renderCandidates(services.getVisibleCandidates(state.snapshot.candidates));
      }

      function acceptMomentumSnapshot(momentum) {
        const stream = momentum.stream;
        if (
          stream?.enabled
          && stream.stream_id === state.momentumStreamId
          && Number.isInteger(state.momentumRevision)
          && stream.revision < state.momentumRevision
        ) return false;
        state.momentumStreamId = stream?.enabled ? stream.stream_id : null;
        state.momentumRevision = stream?.enabled ? stream.revision : null;
        renderMomentumIfChanged(momentum);
        return true;
      }

      function applyMomentumDelta(message) {
        if (message.stream_id !== state.momentumStreamId) {
          bootstrapMomentumStream();
          return;
        }
        if (message.revision <= state.momentumRevision) return;
        if (message.base_revision !== state.momentumRevision || !state.momentum) {
          bootstrapMomentumStream();
          return;
        }
        const removed = new Set(message.removed_symbols || []);
        const itemBySymbol = new Map(
          (state.momentum.items || [])
            .filter((item) => !removed.has(item.symbol))
            .map((item) => [item.symbol, item]),
        );
        (message.item_upserts || []).forEach((item) => itemBySymbol.set(item.symbol, item));
        const orderedItems = (message.ordered_symbols || [])
          .map((symbol) => itemBySymbol.get(symbol))
          .filter(Boolean);
        state.momentumRevision = message.revision;
        renderMomentumIfChanged({
          ...state.momentum,
          status: message.status ?? state.momentum.status,
          mode: message.mode ?? state.momentum.mode,
          source: message.source || state.momentum.source,
          summary: message.summary || state.momentum.summary,
          items: orderedItems,
          alerts: message.alerts || [],
          disclaimer: message.disclaimer ?? state.momentum.disclaimer,
          notice: message.notice ?? state.momentum.notice,
          stream: {
            ...state.momentum.stream,
            revision: message.revision,
            generated_at: message.emitted_at,
          },
        });
      }

      function scheduleMomentumReconnect() {
        if (state.momentumReconnectTimer || momentumSocketIsOpen()) return;
        const delays = [1000, 2000, 5000, 10000, 30000];
        const delay = delays[Math.min(state.momentumReconnectAttempt, delays.length - 1)];
        const delayWithJitter = delay + Math.floor(delay * Math.random() * 0.2);
        const generation = state.momentumTransportGeneration;
        state.momentumReconnectAttempt += 1;
        state.momentumReconnectTimer = window.setTimeout(() => {
          state.momentumReconnectTimer = null;
          if (generation !== state.momentumTransportGeneration || momentumSocketIsOpen()) return;
          const stream = state.momentum?.stream;
          if (stream?.enabled) connectMomentumSocket({ ...stream, revision: state.momentumRevision }, generation);
        }, delayWithJitter);
      }

      function connectMomentumSocket(stream, generation = state.momentumTransportGeneration) {
        if (!stream?.enabled || !stream.stream_id || !Number.isInteger(stream.revision)) return;
        if (generation !== state.momentumTransportGeneration || momentumSocketIsOpen()) return;
        const previous = state.momentumSocket;
        state.momentumSocket = null;
        if (previous && previous.readyState < WebSocket.CLOSING) previous.close(1000, "reconnect");

        const socket = new WebSocket(momentumWebSocketUrl(stream));
        state.momentumSocket = socket;
        state.momentumSocketState = "connecting";
        renderMomentumSourceStatus();
        socket.addEventListener("open", () => {
          if (generation !== state.momentumTransportGeneration || socket !== state.momentumSocket) return;
          state.momentumSocketState = "open";
          state.momentumReconnectAttempt = 0;
          state.momentumLastHeartbeatAt = Date.now();
          renderMomentumSourceStatus();
        });
        socket.addEventListener("message", (event) => {
          if (generation !== state.momentumTransportGeneration || socket !== state.momentumSocket) return;
          let message;
          try {
            message = JSON.parse(event.data);
          } catch (_) {
            socket.close(4002, "invalid-json");
            return;
          }
          state.momentumLastHeartbeatAt = Date.now();
          if (message.type === "delta") applyMomentumDelta(message);
          if (message.type === "resync_required") {
            bootstrapMomentumStream();
          }
        });
        socket.addEventListener("close", () => {
          if (generation !== state.momentumTransportGeneration || socket !== state.momentumSocket) return;
          state.momentumSocket = null;
          state.momentumSocketState = "degraded";
          renderMomentumSourceStatus();
          scheduleMomentumReconnect();
        });
        socket.addEventListener("error", () => {
          if (socket === state.momentumSocket) socket.close();
        });
      }

      async function loadMomentumProjection({ connect = false, generation = state.momentumTransportGeneration } = {}) {
        if (state.momentumLoading) {
          if (connect) state.momentumPendingBootstrapGeneration = generation;
          return;
        }
        state.momentumLoading = true;
        try {
          const response = await fetch("/api/dashboard/momentum", { cache: "no-store" });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const momentum = await response.json();
          if (generation !== state.momentumTransportGeneration) return;
          const previousStreamId = state.momentumStreamId;
          if (!acceptMomentumSnapshot(momentum)) return;
          if (connect || (previousStreamId && previousStreamId !== state.momentumStreamId)) {
            connectMomentumSocket(momentum.stream, generation);
          }
        } catch (error) {
          momentumStatus.classList.remove("active");
          momentumStatus.classList.add("degraded");
          momentumStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>漲停加速讀取失敗 · ${escapeHtml(error.message)}`;
          momentumContent.setAttribute("aria-busy", "false");
          momentumContent.innerHTML = `<div class="momentum-empty">無法讀取本機 Momentum projection：${escapeHtml(error.message)}</div>`;
          if (momentumDetailDialog.open) {
            setMomentumDialogStatus(`盤中資料更新失敗，以下保留最後成功內容：${error.message}`);
          }
        } finally {
          state.momentumLoading = false;
          const pendingGeneration = state.momentumPendingBootstrapGeneration;
          if (pendingGeneration === state.momentumTransportGeneration) {
            state.momentumPendingBootstrapGeneration = null;
            loadMomentumProjection({ connect: true, generation: pendingGeneration });
          }
        }
      }

      function bootstrapMomentumStream() {
        state.momentumTransportGeneration += 1;
        const generation = state.momentumTransportGeneration;
        if (state.momentumReconnectTimer) {
          window.clearTimeout(state.momentumReconnectTimer);
          state.momentumReconnectTimer = null;
        }
        const socket = state.momentumSocket;
        state.momentumSocket = null;
        if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, "resync");
        state.momentumSocketState = "connecting";
        loadMomentumProjection({ connect: true, generation });
      }

      function checkMomentumHeartbeat() {
        if (!momentumSocketIsOpen() || !state.momentumLastHeartbeatAt) return;
        const heartbeatSeconds = state.momentum?.stream?.heartbeat_seconds || 10;
        if (Date.now() - state.momentumLastHeartbeatAt > heartbeatSeconds * 2500) {
          state.momentumSocket.close(4001, "heartbeat-timeout");
        }
      }

      async function acknowledgeMomentumAlert(alertId) {
        if (!alertId) return;
        try {
          const response = await fetch(`/api/dashboard/momentum/alerts/${encodeURIComponent(alertId)}/acknowledge`, { method: "POST" });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
          acceptMomentumSnapshot(payload);
        } catch (error) {
          momentumStatus.classList.add("degraded");
          momentumStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>告警確認失敗 · ${escapeHtml(error.message)}`;
        }
      }

      function pollMomentumProjection() {
        if (document.visibilityState !== "visible") return;
        if (momentumSocketIsOpen()) return;
        loadMomentumProjection({ connect: false });
      }

  return { renderMomentum, syncMomentumDialog, openMomentumDialog, closeMomentumDialog, bootstrapMomentumStream, checkMomentumHeartbeat, pollMomentumProjection, acceptMomentumSnapshot };
}
