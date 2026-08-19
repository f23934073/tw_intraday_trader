export function createCandidateWorkspace(context) {
  const { state, services, escapeHtml, formatNumber, formatPercent, formatVolume, formatQuoteTime, formatRule, formatSource } = context;
  const detailPanel = document.getElementById("detail-panel");

      function percentage(numerator, denominator) {
        if (!denominator) return 0;
        return Math.max(0, Math.min(100, numerator / denominator * 100));
      }

      function historyKey(symbol, period) {
        return `${symbol}:${period}`;
      }

      function formatHistoryTimestamp(timestamp, resolution) {
        const date = new Date(timestamp);
        return date.toLocaleString("zh-TW", resolution === "5分鐘"
          ? { hour: "2-digit", minute: "2-digit", hour12: false }
          : { month: "numeric", day: "numeric" }
        );
      }

      function chartNumber(value) {
        if (value === null || value === undefined || value === "") return null;
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
      }

      function renderMovingAverageMeta(history) {
        if (history.period !== "3m" || !history.candles.length) return "";
        const latest = history.candles[history.candles.length - 1];
        return [
          ["ma5", "MA5"],
          ["ma20", "MA20"],
          ["ma60", "MA60"]
        ].map(([key, label]) => {
          const value = chartNumber(latest[key]);
          return value === null
            ? ""
            : `<span class="ma-value ${key}">${label} ${formatNumber(value)}</span>`;
        }).join("");
      }

      function getVisibleCandidates(candidates) {
        return candidates
          .filter((candidate) => Number(candidate.score.total) > 0)
          .sort((left, right) => {
            const scoreDifference = Number(right.score.total) - Number(left.score.total);
            return scoreDifference || left.symbol.localeCompare(right.symbol, "en");
          });
      }

      function renderStatus(snapshot) {
        const timestamp = new Date(snapshot.generated_at).toLocaleTimeString("zh-TW", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
        });
        statusElement.innerHTML = `<span class="status-dot" aria-hidden="true"></span>單次快照 · ${escapeHtml(snapshot.provider.name)} · ${timestamp}`;
      }

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

      function renderCandidates(candidates) {
        document.getElementById("candidate-count").textContent = `${candidates.length} 檔`;
        document.getElementById("overview-candidate-count").textContent = `${candidates.length} 檔`;
        const list = document.getElementById("candidate-list");

        if (!candidates.length) {
          list.innerHTML = '<p class="empty">目前沒有分數大於 0 的候選股票。</p>';
          return;
        }

        list.innerHTML = candidates.map((candidate) => {
          const selected = candidate.symbol === state.selectedSymbol;
          const momentum = state.momentum?.items?.find((item) => item.symbol === candidate.symbol);
          return `
            <button class="candidate-button ${selected ? "selected" : ""}" type="button" data-symbol="${escapeHtml(candidate.symbol)}" aria-pressed="${selected}">
              <span class="candidate-symbol">${escapeHtml(candidate.symbol)}</span>
              <span class="candidate-score">${candidate.score.total}</span>
              <span class="candidate-name">${escapeHtml(candidate.stock.name)} · ${escapeHtml(formatSource(candidate.sources))}${momentum ? ` · <span class="momentum-candidate-badge">${escapeHtml(momentum.current_stage_label)}</span>` : ""}</span>
            </button>
          `;
        }).join("");

        list.querySelectorAll("[data-symbol]").forEach((button) => {
          button.addEventListener("click", () => {
            selectCandidate(button.dataset.symbol);
          });
        });
      }

      function selectCandidate(symbol) {
        if (!symbol || !state.snapshot) return;
        const candidateList = document.getElementById("candidate-list");
        const candidateScrollTop = candidateList.scrollTop;
        state.selectedSymbol = symbol;
        render(state.snapshot);
        document.getElementById("candidate-list").scrollTop = candidateScrollTop;
        resetDetailScroll();
        loadSelectedHistory();
      }

      function resetDetailScroll() {
        if (window.matchMedia("(max-width: 700px)").matches) {
          detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        detailPanel.scrollTo({ top: 0, behavior: "smooth" });
      }

      function renderCandidateDetail(candidate) {
        const detail = document.getElementById("candidate-detail");

        if (!candidate) {
          detail.innerHTML = '<div class="kicker">評估</div><h2 id="detail-heading">沒有可顯示的 Candidate</h2><p class="empty">請先重新掃描或調整候選規則。</p>';
          return;
        }

        const stock = candidate.stock;
        const gapPct = stock.previous_close > 0 ? (stock.open - stock.previous_close) / stock.previous_close * 100 : null;
        const changePct = stock.previous_close > 0 ? (stock.price - stock.previous_close) / stock.previous_close * 100 : null;
        const dayPosition = stock.high > stock.low ? (stock.price - stock.low) / (stock.high - stock.low) * 100 : null;
        const dayRangePct = stock.previous_close > 0 ? (stock.high - stock.low) / stock.previous_close * 100 : null;
        const vwapDeviation = stock.vwap > 0 ? (stock.price - stock.vwap) / stock.vwap * 100 : null;
        const scoreParts = candidate.score.details.map((detail) => `
          <span class="score-piece" style="width:${percentage(detail.score, candidate.score.max)}%"></span>
        `).join("");
        const scoreRows = candidate.score.details.map((detail) => `
          <div class="score-row"><span>${escapeHtml(formatRule(detail.rule))}</span><strong>+${detail.score} / ${detail.max_score}</strong></div>
        `).join("");
        const matchedRules = candidate.matched_rules.length
          ? candidate.matched_rules.map(formatRule).join(" · ")
          : "無自動選股規則";

        detail.innerHTML = `
          <div class="kicker">評估</div>
          <div class="selected-title">
            <strong>${escapeHtml(candidate.symbol)}</strong>
            <span>${escapeHtml(stock.name)}</span>
            <span class="source-badge">${escapeHtml(formatSource(candidate.sources))}</span>
          </div>
          <p class="rule-line">符合規則：<strong>${escapeHtml(matchedRules)}</strong></p>
          <button class="order-ticket-button detail-order-button" type="button" data-order-symbol="${escapeHtml(candidate.symbol)}" data-order-price="${escapeHtml(stock.price)}">以 ${formatNumber(stock.price)} 模擬買進</button>
          <div class="metrics" aria-label="${escapeHtml(candidate.symbol)} 最新市場快照">
            <div class="metric">
              <div class="metric-label">目前價格</div>
              <div class="metric-value">${formatNumber(stock.price)}</div>
              <div class="metric-note">較昨收 ${changePct === null ? "—" : formatPercent(changePct)}</div>
            </div>
            <div class="metric">
              <div class="metric-label">開盤／昨收</div>
              <div class="metric-value">${formatNumber(stock.open)} / ${formatNumber(stock.previous_close)}</div>
              <div class="metric-note">跳空 ${gapPct === null ? "—" : formatPercent(gapPct)}</div>
            </div>
            <div class="metric">
              <div class="metric-label">成交量／VWAP</div>
              <div class="metric-value">${formatVolume(stock.volume)} / ${formatNumber(stock.vwap)}</div>
              <div class="metric-note">${stock.vwap === null ? "尚無 VWAP" : stock.price > stock.vwap ? "現價高於 VWAP" : "現價低於 VWAP"}</div>
            </div>
          </div>
          <div class="observation-grid" aria-label="${escapeHtml(candidate.symbol)} 盤中觀察指標">
            <div class="observation">
              <div class="observation-label">日內位置</div>
              <div class="observation-value">${dayPosition === null ? "—" : `${formatNumber(dayPosition, 0)}%`}</div>
              <div class="observation-note">低 ${formatNumber(stock.low)} ／高 ${formatNumber(stock.high)}</div>
            </div>
            <div class="observation">
              <div class="observation-label">VWAP 偏離</div>
              <div class="observation-value">${formatPercent(vwapDeviation)}</div>
              <div class="observation-note">${stock.vwap > 0 ? `VWAP ${formatNumber(stock.vwap)}` : "尚無 VWAP"}</div>
            </div>
            <div class="observation">
              <div class="observation-label">日內振幅</div>
              <div class="observation-value">${formatPercent(dayRangePct)}</div>
              <div class="observation-note">以昨收為分母</div>
            </div>
            <div class="observation">
              <div class="observation-label">相對量</div>
              <div class="observation-value">${stock.relative_volume === null || stock.relative_volume === undefined ? "—" : `${formatNumber(stock.relative_volume)} 倍`}</div>
              <div class="observation-note">${stock.relative_volume === null || stock.relative_volume === undefined ? "尚無資料" : "今日累積量／昨量"}</div>
            </div>
          </div>
          ${renderHistory(candidate)}
          <div class="score-region">
            <div class="score-header">
              <div><div class="kicker">買入評分</div><strong>${candidate.score.total} / ${candidate.score.max}</strong></div>
              <span>可解釋的二元規則</span>
            </div>
            <div class="score-track" role="img" aria-label="買入評分組成">${scoreParts}</div>
            ${scoreRows}
          </div>
        `;

        detail.querySelectorAll("[data-history-period]").forEach((button) => {
          button.addEventListener("click", () => {
            state.historyPeriod = button.dataset.historyPeriod;
            renderCandidateDetail(candidate);
            loadSelectedHistory();
          });
        });

        const orderButton = detail.querySelector("[data-order-symbol]");
        if (orderButton) {
          orderButton.addEventListener("click", () => {
            services.openOrderTicket(orderButton.dataset.orderSymbol, orderButton.dataset.orderPrice);
          });
        }

        const history = state.historyByKey[historyKey(candidate.symbol, state.historyPeriod)];
        if (history?.status === "ready") {
          bindCandlestickTooltip(detail, history);
        }
      }

      function renderHistory(candidate) {
        const key = historyKey(candidate.symbol, state.historyPeriod);
        const history = state.historyByKey[key];
        const controls = [
          ["1d", "1日"],
          ["5d", "5日"],
          ["20d", "20日"],
          ["3m", "3月"]
        ].map(([period, label]) => `
          <button class="period-button ${state.historyPeriod === period ? "active" : ""}" type="button" data-history-period="${period}" aria-pressed="${state.historyPeriod === period}">${label}</button>
        `).join("");

        let body = '<div class="history-empty">正在讀取來源 Kbar…</div>';
        let meta = "Kbar 只會在選取這檔候選股時，才由後端向資料 Provider 查詢。";

        if (history) {
          if (history.status === "ready") {
            body = renderCandlestickChart(history);
            const sourceNote = history.source === "MockProvider"
              ? "MockProvider 模擬資料"
              : `${history.source} 來源資料`;
            const candleTitle = history.resolution === "日"
              ? `${history.label} K`
              : `${history.label} ${history.resolution} K`;
            const displayStart = history.display_start || history.candles[0].timestamp.slice(0, 10);
            const displayEnd = history.display_end || history.candles[history.candles.length - 1].timestamp.slice(0, 10);
            meta = `<span><strong>${escapeHtml(candleTitle)}</strong> · 顯示 ${escapeHtml(displayStart)} 至 ${escapeHtml(displayEnd)} · ${history.candles.length} 根</span>${renderMovingAverageMeta(history)}<span>${escapeHtml(sourceNote)}</span>`;
          } else if (history.status === "empty") {
            body = '<div class="history-empty">此期間沒有可繪製的 Kbar。可能為休市日、資料尚未建立，或 Provider 未回傳歷史行情。</div>';
            meta = `${escapeHtml(history.start)} 至 ${escapeHtml(history.end)} · ${escapeHtml(history.source)} 未回傳 Kbar`;
          } else if (history.status === "error") {
            body = `<div class="history-empty">${escapeHtml(history.message)}</div>`;
            meta = "保留目前掃描結果；可再次選擇週期重試。";
          } else {
            body = '<div class="history-empty">目前資料 Provider 未提供歷史 Kbar。</div>';
            meta = `${escapeHtml(history.source)} 目前不支援 Kbar 查詢。`;
          }
        }

        return `
          <section class="history-region" aria-label="${escapeHtml(candidate.symbol)} 歷史 K 線">
            <div class="history-heading">
              <div><div class="kicker">走勢</div><h3>來源 K 線與成交量</h3></div>
              <div class="period-controls" role="group" aria-label="K 線週期">${controls}</div>
            </div>
            <div class="history-chart" data-history-chart>${body}<div class="chart-tooltip" data-chart-tooltip aria-hidden="true"></div></div>
            <div class="history-meta">${meta}</div>
          </section>
        `;
      }

      function bindCandlestickTooltip(detail, history) {
        const chart = detail.querySelector("[data-history-chart]");
        const tooltip = detail.querySelector("[data-chart-tooltip]");
        const svg = chart?.querySelector("svg");
        if (!chart || !tooltip || !svg) return;

        const width = 640;
        const height = 270;
        const left = 46;
        const right = 10;
        const priceTop = 28;
        const volumeBottom = 252;
        const plotWidth = width - left - right;
        const step = plotWidth / history.candles.length;

        const hideTooltip = () => {
          tooltip.classList.remove("visible");
          tooltip.setAttribute("aria-hidden", "true");
        };

        svg.addEventListener("pointermove", (event) => {
          const bounds = svg.getBoundingClientRect();
          const viewX = (event.clientX - bounds.left) / bounds.width * width;
          const viewY = (event.clientY - bounds.top) / bounds.height * height;
          if (viewX < left || viewX > width - right || viewY < priceTop || viewY > volumeBottom) {
            hideTooltip();
            return;
          }

          const index = Math.min(
            history.candles.length - 1,
            Math.max(0, Math.floor((viewX - left) / step)),
          );
          const candle = history.candles[index];
          tooltip.innerHTML = renderCandleTooltip(candle, history.resolution);
          tooltip.classList.add("visible");
          tooltip.setAttribute("aria-hidden", "false");

          const chartBounds = chart.getBoundingClientRect();
          const desiredLeft = event.clientX - chartBounds.left + 14;
          const desiredTop = event.clientY - chartBounds.top + 14;
          tooltip.style.left = `${Math.min(desiredLeft, chart.clientWidth - tooltip.offsetWidth - 8)}px`;
          tooltip.style.top = `${Math.min(desiredTop, chart.clientHeight - tooltip.offsetHeight - 8)}px`;
        });
        svg.addEventListener("pointerleave", hideTooltip);
      }

      function renderCandleTooltip(candle, resolution) {
        const date = new Date(candle.timestamp);
        const timestamp = date.toLocaleString("zh-TW", resolution === "5分鐘"
          ? { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }
          : { year: "numeric", month: "numeric", day: "numeric" }
        );
        const values = [
          ["開", formatNumber(candle.open)],
          ["高", formatNumber(candle.high)],
          ["低", formatNumber(candle.low)],
          ["收", formatNumber(candle.close)],
          ["成交量", formatVolume(candle.volume)]
        ].map(([label, value]) => `<span class="chart-tooltip-item"><span>${label}</span><strong>${value}</strong></span>`).join("");
        const indicators = [
          ["ma5", "MA5"],
          ["ma20", "MA20"],
          ["ma60", "MA60"]
        ].map(([key, label]) => {
          const value = chartNumber(candle[key]);
          return value === null ? "" : `<span class="${key}">${label} ${formatNumber(value)}</span>`;
        }).join("");

        return `
          <div class="chart-tooltip-heading">${escapeHtml(timestamp)}</div>
          <div class="chart-tooltip-grid">${values}</div>
          ${indicators ? `<div class="chart-tooltip-indicators">${indicators}</div>` : ""}
        `;
      }

      function renderCandlestickChart(history) {
        const candles = history.candles;
        const width = 640;
        const height = 270;
        const left = 46;
        const right = 10;
        const priceTop = 28;
        const priceBottom = 190;
        const volumeTop = 212;
        const volumeBottom = 252;
        const plotWidth = width - left - right;
        const lows = candles.map((candle) => Number(candle.low));
        const highs = candles.map((candle) => Number(candle.high));
        const movingAverageSeries = [
          { key: "ma5", label: "MA5", color: "var(--amber)" },
          { key: "ma20", label: "MA20", color: "var(--blue)" },
          { key: "ma60", label: "MA60", color: "var(--teal)" }
        ].filter((series) => candles.some((candle) => chartNumber(candle[series.key]) !== null));
        const movingAverageValues = movingAverageSeries.flatMap((series) => candles
          .map((candle) => chartNumber(candle[series.key]))
          .filter((value) => value !== null)
        );
        const rawMin = Math.min(...lows, ...movingAverageValues);
        const rawMax = Math.max(...highs, ...movingAverageValues);
        const baseSpan = Math.max(rawMax - rawMin, Math.abs(rawMax) * 0.002, 0.01);
        const scaleMin = rawMin - baseSpan * 0.12;
        const scaleMax = rawMax + baseSpan * 0.12;
        const y = (price) => priceTop + (scaleMax - price) / (scaleMax - scaleMin) * (priceBottom - priceTop);
        const step = plotWidth / candles.length;
        const bodyWidth = Math.max(2, Math.min(14, step * 0.58));
        const maxVolume = Math.max(...candles.map((candle) => Number(candle.volume)), 1);
        const gridValues = [scaleMax, (scaleMax + scaleMin) / 2, scaleMin];
        const grids = gridValues.map((value) => `
          <line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--line)" stroke-width="1" />
          <text x="${left - 7}" y="${y(value) + 4}" text-anchor="end" fill="var(--muted)" font-size="10">${formatNumber(value)}</text>
        `).join("");
        const xForIndex = (index) => left + step * index + step / 2;
        const bars = candles.map((candle, index) => {
          const open = Number(candle.open);
          const close = Number(candle.close);
          const x = xForIndex(index);
          const rising = close >= open;
          const color = rising ? "var(--green)" : "var(--red)";
          const bodyY = y(Math.max(open, close));
          const bodyHeight = Math.max(2, Math.abs(y(open) - y(close)));
          const volumeHeight = Number(candle.volume) / maxVolume * (volumeBottom - volumeTop);
          return `
            <line x1="${x}" x2="${x}" y1="${y(Number(candle.high))}" y2="${y(Number(candle.low))}" stroke="${color}" stroke-width="1.4" />
            <rect x="${x - bodyWidth / 2}" y="${bodyY}" width="${bodyWidth}" height="${bodyHeight}" fill="${color}" rx="1" />
            <rect x="${x - bodyWidth / 2}" y="${volumeBottom - volumeHeight}" width="${bodyWidth}" height="${volumeHeight}" fill="${color}" opacity=".55" rx="1" />
          `;
        }).join("");
        const movingAverageLines = movingAverageSeries.map((series) => {
          let drawing = false;
          const path = candles.map((candle, index) => {
            const value = chartNumber(candle[series.key]);
            if (value === null) {
              drawing = false;
              return "";
            }
            const command = drawing ? "L" : "M";
            drawing = true;
            return `${command}${xForIndex(index).toFixed(2)} ${y(value).toFixed(2)}`;
          }).join(" ");
          return path
            ? `<path d="${path}" fill="none" stroke="${series.color}" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" />`
            : "";
        }).join("");
        const highValue = Math.max(...highs);
        const lowValue = Math.min(...lows);
        const highIndex = highs.indexOf(highValue);
        const lowIndex = lows.indexOf(lowValue);
        const highX = xForIndex(highIndex);
        const lowX = xForIndex(lowIndex);
        const highY = y(highValue);
        const lowY = y(lowValue);
        const highLabelY = Math.max(23, highY - 9);
        const lowLabelY = Math.min(priceBottom - 4, lowY + 14);
        const extrema = `
          <line x1="${highX}" x2="${highX}" y1="${highY}" y2="${highLabelY + 3}" stroke="var(--text)" stroke-width="1" />
          <text x="${highX}" y="${highLabelY}" text-anchor="middle" fill="var(--text)" font-size="10">高 ${formatNumber(highValue)}</text>
          <line x1="${lowX}" x2="${lowX}" y1="${lowY}" y2="${lowLabelY - 10}" stroke="var(--text)" stroke-width="1" />
          <text x="${lowX}" y="${lowLabelY}" text-anchor="middle" fill="var(--text)" font-size="10">低 ${formatNumber(lowValue)}</text>
        `;
        const movingAverageLegend = movingAverageSeries.map((series, index) => `
          <text x="${left + index * 48}" y="15" fill="${series.color}" font-size="10">${series.label}</text>
        `).join("");
        const last = candles[candles.length - 1];
        const labelLimit = history.resolution === "日" ? 6 : 5;
        const labelStep = Math.max(1, Math.ceil(candles.length / labelLimit));
        const labels = candles.map((candle, index) => {
          if (index % labelStep !== 0 && index !== candles.length - 1) return "";
          const x = xForIndex(index);
          return `<text x="${x}" y="266" text-anchor="middle" fill="var(--muted)" font-size="10">${escapeHtml(formatHistoryTimestamp(candle.timestamp, history.resolution))}</text>`;
        }).join("") + `
          <text x="${left}" y="207" fill="var(--muted)" font-size="10">成交量</text>
        `;
        const candleTitle = history.resolution === "日"
          ? `${history.label} K`
          : `${history.label} ${history.resolution} K`;

        return `
          <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(candleTitle)}，共 ${candles.length} 根，含成交量">
            ${grids}
            ${bars}
            ${movingAverageLines}
            <line x1="${left}" x2="${width - right}" y1="${y(Number(last.close))}" y2="${y(Number(last.close))}" stroke="var(--blue)" stroke-width="1" stroke-dasharray="3 3" />
            ${extrema}
            ${movingAverageLegend}
            ${labels}
          </svg>
        `;
      }

      async function loadSelectedHistory() {
        const candidate = state.snapshot?.candidates.find((item) => item.symbol === state.selectedSymbol);
        if (!candidate) return;

        const key = historyKey(candidate.symbol, state.historyPeriod);
        if (state.historyByKey[key]) return;

        state.historyLoadingKey = key;
        renderCandidateDetail(candidate);

        try {
          const response = await fetch(`/api/dashboard/candidates/${encodeURIComponent(candidate.symbol)}/history?period=${encodeURIComponent(state.historyPeriod)}`);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          state.historyByKey[key] = await response.json();
        } catch (error) {
          state.historyByKey[key] = {
            status: "error",
            message: `無法取得 Kbar：${error.message}`
          };
        } finally {
          if (state.historyLoadingKey === key) state.historyLoadingKey = null;
          if (historyKey(state.selectedSymbol, state.historyPeriod) === key) {
            renderCandidateDetail(candidate);
          }
        }
      }


  return { getVisibleCandidates, renderCandidates, selectCandidate, renderCandidateDetail, loadSelectedHistory };
}
