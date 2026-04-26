const servicesHealthEl = document.getElementById("servicesHealth");
const quickSummaryEl = document.getElementById("quickSummary");
const metricsOverviewEl = document.getElementById("metricsOverview");
const metricSelectEl = document.getElementById("metricSelect");
const metricDetailEl = document.getElementById("metricDetail");
const lastUpdatedEl = document.getElementById("lastUpdated");
const statusTextEl = document.getElementById("statusText");
const refreshSecondsEl = document.getElementById("refreshSeconds");
const refreshNowEl = document.getElementById("refreshNow");
const brokerFilterEl = document.getElementById("brokerFilter");
const tokenFilterEl = document.getElementById("tokenFilter");
const matchPanelEl = document.getElementById("matchPanel");
const buySellPanelEl = document.getElementById("buySellPanel");

let snapshotCache = null;
let refreshTimer = null;
let selectedBroker = "";
let tokenFilter = "";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function makeTable(headers, rows) {
  const headHtml = headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("");
  const rowHtml = rows
    .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${headHtml}</tr></thead><tbody>${rowHtml}</tbody></table>`;
}

function renderHealth(snapshot) {
  const health = snapshot?.health?.["heartbeat-monitor"]?.services || {};
  const rows = Object.entries(health).map(([serviceName, info]) => [
    serviceName,
    info.status || "unknown",
    info.age_seconds ?? "-",
    info.cpu_percent ?? "-",
    info.memory_mb ?? "-",
  ]);
  servicesHealthEl.innerHTML = makeTable(
    ["Service", "Status", "Age(s)", "CPU %", "Memory MB"],
    rows
  );
}

function renderSummary(snapshot) {
  const metrics = snapshot?.metrics || {};
  const summaryItems = [
    { label: "Ticks (count)", value: metrics?.ticks_received_total?.value ?? "-" },
    { label: "Candles (count)", value: metrics?.candles_closed_total?.value ?? "-" },
    { label: "Signals (count)", value: metrics?.signals_generated_total?.value ?? "-" },
    { label: "Signal->Order Ratio", value: metrics?.signals_to_orders_ratio?.value ?? "-" },
    { label: "SL Modifications", value: metrics?.sl_modifications_total?.value ?? "-" },
    { label: "Exited Orders", value: metrics?.orders_exited_total?.value ?? "-" },
  ];
  quickSummaryEl.innerHTML = summaryItems
    .map(
      (item) => `
      <div class="summary-item">
        <div class="label">${escapeHtml(item.label)}</div>
        <div class="value">${escapeHtml(item.value)}</div>
      </div>
    `
    )
    .join("");
}

function renderMatchPanel(snapshot) {
  const ratioMetric = snapshot?.metrics?.signals_to_orders_ratio || {};
  const ratio = ratioMetric.value ?? "-";
  const signals = ratioMetric.signals ?? "-";
  const orders = ratioMetric.orders_submitted ?? "-";
  const mismatch = Number(signals) > 0 && Number(orders) >= 0 ? Number(signals) - Number(orders) : "-";
  const items = [
    { label: "Match Ratio", value: ratio },
    { label: "Signals", value: signals },
    { label: "Orders Submitted", value: orders },
    { label: "Gap (Signals-Orders)", value: mismatch },
  ];
  matchPanelEl.innerHTML = items
    .map(
      (item) => `
      <div class="summary-item">
        <div class="label">${escapeHtml(item.label)}</div>
        <div class="value">${escapeHtml(item.value)}</div>
      </div>
    `
    )
    .join("");
}

function renderBuySellPanel(snapshot) {
  const dist = snapshot?.metrics?.signals_generated_total?.buy_sell_distribution || {};
  const buy = Number(dist.BUY || dist.buy || 0);
  const sell = Number(dist.SELL || dist.sell || 0);
  const total = buy + sell;
  const buyPct = total > 0 ? ((buy / total) * 100).toFixed(2) : "0.00";
  const sellPct = total > 0 ? ((sell / total) * 100).toFixed(2) : "0.00";
  buySellPanelEl.innerHTML = makeTable(
    ["Signal", "Count", "Percent"],
    [
      ["BUY", buy, `${buyPct}%`],
      ["SELL", sell, `${sellPct}%`],
      ["TOTAL", total, "100%"],
    ]
  );
}

function applyFilters(metricId, metricValue) {
  if (!selectedBroker && !tokenFilter) return metricValue;
  const clone = JSON.parse(JSON.stringify(metricValue));
  if (!clone.breakdown || typeof clone.breakdown !== "object") {
    return clone;
  }
  const filtered = {};
  for (const [key, val] of Object.entries(clone.breakdown)) {
    const loweredKey = key.toLowerCase();
    const brokerOk = !selectedBroker || loweredKey.includes(selectedBroker.toLowerCase());
    const tokenOk = !tokenFilter || loweredKey.includes(tokenFilter.toLowerCase());
    if (brokerOk && tokenOk) {
      filtered[key] = val;
    }
  }
  clone.breakdown = filtered;
  return clone;
}

function renderMetricsOverview(snapshot) {
  const metrics = snapshot?.metrics || {};
  const rows = Object.entries(metrics).map(([metricId, metricValue]) => {
    const filteredMetric = applyFilters(metricId, metricValue);
    return [
    metricId,
    filteredMetric?.value !== undefined ? JSON.stringify(filteredMetric.value) : "-",
    filteredMetric?.window_seconds ?? "-",
  ];
  });
  metricsOverviewEl.innerHTML = makeTable(["Metric ID", "Value", "Window(s)"], rows);
}

function populateMetricSelector(snapshot) {
  const metrics = snapshot?.metrics || {};
  const metricIds = Object.keys(metrics);
  metricSelectEl.innerHTML = metricIds
    .map((id) => `<option value="${escapeHtml(id)}">${escapeHtml(id)}</option>`)
    .join("");
  if (metricIds.length > 0) {
    renderMetricDetail(metricIds[0], snapshot);
  } else {
    metricDetailEl.textContent = "No metrics available.";
  }
}

function renderMetricDetail(metricId, snapshot) {
  const metric = applyFilters(metricId, snapshot?.metrics?.[metricId] || {});
  metricDetailEl.textContent = JSON.stringify(metric, null, 2);
}

function refreshBrokerOptions(snapshot) {
  const metrics = snapshot?.metrics || {};
  const brokers = new Set();
  for (const metricValue of Object.values(metrics)) {
    const breakdown = metricValue?.breakdown || {};
    for (const key of Object.keys(breakdown)) {
      const parts = String(key).split("|");
      if (parts.length > 0 && parts[0]) {
        brokers.add(parts[0]);
      }
    }
  }
  const current = brokerFilterEl.value;
  brokerFilterEl.innerHTML =
    `<option value="">All</option>` +
    Array.from(brokers)
      .sort()
      .map((broker) => `<option value="${escapeHtml(broker)}">${escapeHtml(broker)}</option>`)
      .join("");
  brokerFilterEl.value = current && brokers.has(current) ? current : "";
  selectedBroker = brokerFilterEl.value;
}

async function fetchSnapshot() {
  statusTextEl.textContent = "Status: refreshing...";
  try {
    const response = await fetch("/dashboard/snapshot", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const snapshot = await response.json();
    snapshotCache = snapshot;

    renderHealth(snapshot);
    renderSummary(snapshot);
    renderMatchPanel(snapshot);
    renderBuySellPanel(snapshot);
    refreshBrokerOptions(snapshot);
    renderMetricsOverview(snapshot);
    populateMetricSelector(snapshot);

    const now = new Date();
    lastUpdatedEl.textContent = `Last updated: ${now.toLocaleTimeString()}`;
    statusTextEl.textContent = "Status: up";
    statusTextEl.className = "status-ok";
  } catch (error) {
    statusTextEl.textContent = `Status: error (${error.message})`;
    statusTextEl.className = "status-error";
  }
}

function restartAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
  }
  const intervalMs = Math.max(1000, Number(refreshSecondsEl.value) * 1000);
  refreshTimer = setInterval(fetchSnapshot, intervalMs);
}

metricSelectEl.addEventListener("change", (event) => {
  if (!snapshotCache) return;
  renderMetricDetail(event.target.value, snapshotCache);
});

brokerFilterEl.addEventListener("change", () => {
  selectedBroker = brokerFilterEl.value;
  if (!snapshotCache) return;
  renderMetricsOverview(snapshotCache);
  renderMetricDetail(metricSelectEl.value, snapshotCache);
});

tokenFilterEl.addEventListener("input", () => {
  tokenFilter = tokenFilterEl.value.trim();
  if (!snapshotCache) return;
  renderMetricsOverview(snapshotCache);
  renderMetricDetail(metricSelectEl.value, snapshotCache);
});

refreshSecondsEl.addEventListener("change", restartAutoRefresh);
refreshNowEl.addEventListener("click", fetchSnapshot);

fetchSnapshot();
restartAutoRefresh();
