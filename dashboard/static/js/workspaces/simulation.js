export function createSimulationWorkspace(context) {
  const { state, escapeHtml, formatNumber, formatPercent, formatQuoteTime, newIdempotencyKey, setWorkspace } = context;
  const simulationStatus = document.getElementById("simulation-status");
  const ordersToggle = document.getElementById("orders-toggle");
  const ordersDrawer = document.getElementById("orders-drawer");
  const ordersPanel = document.getElementById("orders-panel");
  const orderSymbol = document.getElementById("order-symbol");
  const orderSide = document.getElementById("order-side");
  const orderLots = document.getElementById("order-lots");
  const orderPrice = document.getElementById("order-price");
  const orderSubmit = document.getElementById("order-submit");
  const orderError = document.getElementById("order-error");
  const orderMessage = document.getElementById("order-message");
  const positionsToggle = document.getElementById("positions-toggle");
  const positionsDrawer = document.getElementById("positions-drawer");
  const positionsPanel = document.getElementById("positions-panel");

      function renderSimulation(simulation) {
        const session = simulation.session || {};
        const label = session.label || "本機紙上模擬";
        const subscribedCount = (session.subscribed_symbols || []).length;
        const stateLabel = session.stream_health === "BLOCKED"
          ? "行情保護已阻擋下單"
          : session.stream_health === "DEGRADED"
            ? "行情待復原"
            : session.stream_error
          ? "行情異常"
          : session.streaming && subscribedCount && session.last_quote_received_at
            ? `即時 ${formatQuoteTime(session.last_quote_received_at)}`
            : session.streaming && subscribedCount
              ? "等待行情"
              : session.streaming
                ? "串流待命"
                : "Snapshot";
        simulationStatus.classList.toggle("degraded", Boolean(session.stream_error) || session.stream_health !== "HEALTHY");
        simulationStatus.classList.toggle("waiting", !session.stream_error && session.stream_health === "HEALTHY" && !session.last_quote_received_at);
        simulationStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>${escapeHtml(label)} · ${escapeHtml(stateLabel)}`;
        document.getElementById("position-count").textContent = String((simulation.positions || []).length);
        document.getElementById("order-count").textContent = String((simulation.orders || []).filter((order) => order.status === "SUBMITTED").length);
        document.getElementById("overview-position-count").textContent = String((simulation.positions || []).length);
        document.getElementById("overview-order-count").textContent = String((simulation.orders || []).filter((order) => order.status === "SUBMITTED").length);
        document.getElementById("order-preview").textContent = session.available_cash === null || session.available_cash === undefined
          ? "買進以賣一、賣出以買一判斷模擬成交；未達限價則保留在委託清單。"
          : `可用虛擬現金：${formatNumber(session.available_cash, 0)} 元${Number(session.reserved_cash || 0) > 0 ? `（已保留 ${formatNumber(session.reserved_cash, 0)} 元掛單額度）` : ""}。買進以賣一、賣出以買一判斷模擬成交。`;
      }

      function renderPositions(positions) {
        const list = document.getElementById("position-list");

        if (!positions.length) {
          list.innerHTML = '<p class="empty">目前沒有已成交的本機模擬持倉。</p>';
          return;
        }

        list.innerHTML = positions.map((position) => {
          const positive = position.unrealized_pnl >= 0;

          return `
            <article class="position-card">
              <div class="position-top">
                <div class="position-name"><strong>${escapeHtml(position.symbol)}</strong><span>${escapeHtml(position.name)} · ${position.quantity.toLocaleString("zh-TW")} 股</span></div>
                <span class="decision-badge hold">已成交</span>
              </div>
              <div class="pnl ${positive ? "positive" : "negative"}">${formatPercent(position.unrealized_pnl_pct)}</div>
              <div class="pnl-note">未實現損益 ${position.unrealized_pnl >= 0 ? "+" : ""}${formatNumber(position.unrealized_pnl, 0)} 元 · 市值 ${formatNumber(position.market_value, 0)} 元</div>
              <p class="position-footer"><strong>平均成交價：</strong>${formatNumber(position.average_price)} · <strong>最新成交：</strong>${formatNumber(position.current_price)} · <strong>買一／賣一：</strong>${formatNumber(position.bid_price)}／${formatNumber(position.ask_price)}<br><strong>行情時間：</strong>${escapeHtml(formatQuoteTime(position.last_quote_at))} · <strong>已實現損益：</strong>${position.realized_pnl >= 0 ? "+" : ""}${formatNumber(position.realized_pnl, 0)} 元。</p>
            </article>
          `;
        }).join("");
      }

      function orderStatusLabel(status) {
        return { SUBMITTED: "已送出", FILLED: "已成交", CANCELLED: "已取消", REJECTED: "已拒絕" }[status] || status;
      }

      function orderStatusClass(status) {
        return String(status || "").toLowerCase();
      }

      function formatOrderTime(timestamp) {
        if (!timestamp) return "—";
        return new Date(timestamp).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
      }

      function renderOrders(orders) {
        document.getElementById("order-list-count").textContent = `${orders.length} 筆`;
        const list = document.getElementById("order-list");
        if (!orders.length) {
          list.innerHTML = '<p class="empty">目前沒有本機模擬委託。</p>';
          return;
        }

        list.innerHTML = orders.map((order) => {
          const side = order.side === "BUY" ? "買進" : "賣出";
          const filled = order.status === "FILLED";
          const note = order.reason
            ? escapeHtml(order.reason)
            : filled
              ? `成交 ${formatNumber(order.filled_quantity, 0)} 股 @ ${formatNumber(order.filled_price)}`
              : `限價 ${formatNumber(order.limit_price)} · 預估 ${formatNumber(order.estimated_amount, 0)} 元`;
          return `
            <article class="order-card">
              <div class="order-card-top">
                <div class="order-card-title">${escapeHtml(order.symbol)} <span>${escapeHtml(order.name)} · ${side} ${order.lots} 張</span></div>
                <span class="order-status ${orderStatusClass(order.status)}">${escapeHtml(orderStatusLabel(order.status))}</span>
              </div>
              <div class="order-card-meta">${formatOrderTime(order.updated_at)} · ${escapeHtml(order.origin === "MANUAL_WEB" ? "網頁手動" : order.origin)}</div>
              <p class="order-card-note">${note}</p>
              ${order.status === "SUBMITTED" ? `<button class="cancel-order" type="button" data-cancel-order="${escapeHtml(order.order_id)}">取消委託</button>` : ""}
            </article>
          `;
        }).join("");

        list.querySelectorAll("[data-cancel-order]").forEach((button) => {
          button.addEventListener("click", () => cancelSimulationOrder(button.dataset.cancelOrder));
        });
      }

      function renderDataHealth(snapshot, simulation) {
        const missing = [
          ...snapshot.market.missing_candidate_symbols,
          ...snapshot.market.missing_position_symbols
        ];
        const missingText = missing.length ? `；${missing.length} 檔缺少最新資料` : "";
        const session = simulation.session || {};
        const streamText = session.streaming
          ? `持倉與掛單已啟用 Shioaji Tick／BidAsk，目前訂閱 ${(session.subscribed_symbols || []).length} 檔`
          : session.stream_error || "持倉與掛單目前使用 Snapshot 行情";
        const notice = session.notice || "本機模擬狀態尚未取得。";
        document.getElementById("data-health").innerHTML = `候選清單已從 <strong>${escapeHtml(snapshot.provider.name)}</strong> 載入 <strong>${snapshot.market.loaded_symbols}</strong> 檔單次快照${missingText}；${escapeHtml(streamText)}。${escapeHtml(notice)}`;
        const dataStatus = document.getElementById("overview-data-status");
        const dataNote = document.getElementById("overview-data-note");
        const degraded = Boolean(missing.length || session.stream_error || session.stream_health !== "HEALTHY");
        dataStatus.textContent = degraded ? "需注意" : "正常";
        dataStatus.classList.toggle("good", !degraded);
        dataStatus.classList.toggle("alert", degraded);
        dataStatus.classList.remove("waiting");
        dataNote.textContent = `${snapshot.market.loaded_symbols} 檔快照 · ${session.streaming ? "Tick／BidAsk" : "Snapshot"}`;
      }

      function openOrderTicket(symbol, price) {
        const selectedCandidate = state.snapshot?.candidates.find((candidate) => candidate.symbol === state.selectedSymbol);
        const selectedSymbol = symbol || selectedCandidate?.symbol;
        const selectedPrice = price || selectedCandidate?.stock?.price;
        if (selectedSymbol) orderSymbol.value = selectedSymbol;
        if (selectedPrice !== undefined && selectedPrice !== null) orderPrice.value = Number(selectedPrice).toFixed(2);
        orderSide.value = "BUY";
        orderError.style.display = "none";
        orderMessage.classList.remove("visible");
        setOrdersDrawer(true, "order-ticket");
        requestAnimationFrame(() => orderSymbol.focus());
      }

      function setOrdersDrawer(open, workspace = "orders") {
        if (open) {
          state.workspaceBeforeDrawer = state.workspace;
          setWorkspace(workspace);
        } else {
          setWorkspace(state.workspaceBeforeDrawer || "overview");
        }
        ordersDrawer.classList.toggle("open", open);
        ordersDrawer.setAttribute("aria-hidden", String(!open));
        ordersToggle.setAttribute("aria-expanded", String(open));
        if (open) {
          requestAnimationFrame(() => ordersPanel.focus());
        } else {
          ordersToggle.focus();
        }
      }

      async function loadSimulationProjection() {
        if (state.simulationProjectionLoading || !state.snapshot) return;
        state.simulationProjectionLoading = true;
        try {
          const response = await fetch("/api/simulation/projection", { cache: "no-store" });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const simulation = await response.json();
          state.snapshot = { ...state.snapshot, simulation };
          renderSimulation(simulation);
          renderPositions(simulation.positions || []);
          renderOrders(simulation.orders || []);
          renderDataHealth(state.snapshot, simulation);
        } finally {
          state.simulationProjectionLoading = false;
        }
      }

      async function submitSimulationOrder(event) {
        event.preventDefault();
        const symbol = orderSymbol.value.trim();
        const lots = Number(orderLots.value);
        const limitPrice = Number(orderPrice.value);
        orderError.style.display = "none";
        orderMessage.classList.remove("visible");

        if (!symbol || !Number.isInteger(lots) || lots <= 0 || !Number.isFinite(limitPrice) || limitPrice <= 0) {
          orderError.textContent = "請輸入股票代碼、正確張數與大於 0 的限價。";
          orderError.style.display = "block";
          return;
        }

        orderSubmit.disabled = true;
        orderSubmit.textContent = "送單中…";
        try {
          const response = await fetch("/api/simulation/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              symbol,
              side: orderSide.value,
              lots,
              limit_price: limitPrice,
              idempotency_key: newIdempotencyKey("manual")
            })
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
          await loadSimulationProjection();
          orderMessage.textContent = `${payload.order.symbol} ${payload.order.side === "BUY" ? "買進" : "賣出"}委託${orderStatusLabel(payload.order.status)}。`;
          orderMessage.classList.add("visible");
        } catch (error) {
          orderError.textContent = `無法送出模擬委託：${error.message}`;
          orderError.style.display = "block";
        } finally {
          orderSubmit.disabled = false;
          orderSubmit.textContent = "送出本機模擬委託";
        }
      }

      async function cancelSimulationOrder(orderId) {
        if (!orderId) return;
        orderError.style.display = "none";
        try {
          const response = await fetch(`/api/simulation/orders/${encodeURIComponent(orderId)}/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ idempotency_key: newIdempotencyKey("cancel") })
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
          await loadSimulationProjection();
          orderMessage.textContent = "委託已取消。";
          orderMessage.classList.add("visible");
        } catch (error) {
          orderError.textContent = `無法取消委託：${error.message}`;
          orderError.style.display = "block";
        }
      }

      function setPositionsDrawer(open) {
        if (open) setWorkspace("positions");
        else setWorkspace("overview");
        positionsDrawer.classList.toggle("open", open);
        positionsDrawer.setAttribute("aria-hidden", String(!open));
        positionsToggle.setAttribute("aria-expanded", String(open));
        if (open) {
          requestAnimationFrame(() => positionsPanel.focus());
        } else {
          positionsToggle.focus();
        }
      }

      function pollSimulationProjection() {
        if (document.visibilityState !== "visible") return;
        loadSimulationProjection().catch((error) => {
          simulationStatus.classList.remove("waiting");
          simulationStatus.classList.add("degraded");
          simulationStatus.innerHTML = `<span class="status-dot" aria-hidden="true"></span>本機模擬行情更新失敗 · ${escapeHtml(error.message)}`;
        });
      }


  return { renderSimulation, renderPositions, renderOrders, renderDataHealth, openOrderTicket, setOrdersDrawer, setPositionsDrawer, loadSimulationProjection, pollSimulationProjection, submitSimulationOrder, cancelSimulationOrder };
}
