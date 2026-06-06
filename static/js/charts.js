/**
 * Chart initialization helpers for Mantecato analytics pages.
 *
 * Charts read their colors from the active theme (light/dark) and
 * re-render automatically when the theme is toggled.
 */

/* ── Theme-aware colors ───────────────────────────────────── */

var CHART_COLORS = [
  "oklch(0.894 0.192 123)",  // lime (primary accent)
  "oklch(0.800 0.182 152)",  // green
  "oklch(0.837 0.164 84)",   // amber
  "oklch(0.711 0.166 22)",   // red
  "oklch(0.714 0.144 255)",  // blue
  "oklch(0.750 0.150 200)",  // cyan
  "oklch(0.780 0.150 55)",   // orange
  "oklch(0.700 0.150 330)",  // pink
];

function themeVar(name) {
  var raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return raw ? "oklch(" + raw + ")" : "#888";
}

function chartTheme() {
  return {
    text: themeVar("--muted-foreground"),
    grid: themeVar("--border"),
    tooltipBg: themeVar("--popover"),
    tooltipFg: themeVar("--popover-foreground"),
  };
}

function applyChartDefaults() {
  if (!window.Chart) return;
  var t = chartTheme();
  Chart.defaults.font.family =
    "Geist, ui-sans-serif, system-ui, sans-serif";
  Chart.defaults.color = t.text;
  Chart.defaults.borderColor = t.grid;
}

/* ── Registry: re-render every chart on theme change ──────── */

function _register(canvas, type, data) {
  canvas._chartType = type;
  canvas._chartData = data;
}

/* ── Timezone: convert UTC labels to browser local time ───── */

function localizeLabels(labels) {
  if (!labels || !labels.length) return labels;
  var sample = labels[0];
  if (!sample || typeof sample !== "string") return labels;
  var d = new Date(sample);
  if (isNaN(d.getTime())) return labels;

  var span = labels.length > 1
    ? new Date(labels[labels.length - 1]) - new Date(labels[0])
    : 0;
  var hours = span / 3600000;

  return labels.map(function (lbl) {
    var dt = new Date(lbl);
    if (isNaN(dt.getTime())) return lbl;
    if (hours <= 24) return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (hours <= 2160) return dt.toLocaleDateString([], { month: "short", day: "numeric" });
    return dt.toLocaleDateString([], { year: "numeric", month: "short" });
  });
}

/* ── Time series (area / line chart) ──────────────────────── */

function initTimeSeriesChart(canvasId, data) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  _register(canvas, "timeseries", data);
  applyChartDefaults();
  var t = chartTheme();
  var existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  return new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: localizeLabels(data.labels || []),
      datasets: (data.datasets || []).map(function (ds, i) {
        var color = ds.borderColor || CHART_COLORS[i % CHART_COLORS.length];
        return Object.assign(
          {
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderColor: color,
            backgroundColor: color.replace("hsl(", "hsla(").replace(")", ", 0.10)"),
            pointBackgroundColor: color,
          },
          ds
        );
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "top",
          align: "end",
          labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, padding: 16, filter: function (item) { return !item.text.startsWith("Prev"); } },
        },
        tooltip: {
          backgroundColor: t.tooltipBg,
          titleColor: t.tooltipFg,
          bodyColor: t.tooltipFg,
          borderColor: t.grid,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          usePointStyle: true,
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true },
        },
        y: {
          beginAtZero: true,
          grid: { color: t.grid, drawTicks: false },
          border: { display: false },
          ticks: { font: { size: 11 }, padding: 8 },
        },
      },
    },
  });
}

/* ── Bar chart ────────────────────────────────────────────── */

function initBarChart(canvasId, data) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  _register(canvas, "bar", data);
  applyChartDefaults();
  var t = chartTheme();
  var existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  return new Chart(canvas.getContext("2d"), {
    type: "bar",
    data: {
      labels: localizeLabels(data.labels || []),
      datasets: (data.datasets || []).map(function (ds, i) {
        return Object.assign(
          {
            borderRadius: 6,
            backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
            maxBarThickness: 36,
          },
          ds
        );
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: t.tooltipBg,
          titleColor: t.tooltipFg,
          bodyColor: t.tooltipFg,
          borderColor: t.grid,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
        },
      },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true, callback: function(val) { var l = this.getLabelForValue(val); return l.length > 20 ? l.slice(0,18) + '…' : l; } } },
        y: {
          beginAtZero: true,
          grid: { color: t.grid, drawTicks: false },
          border: { display: false },
          ticks: { font: { size: 11 }, padding: 8 },
        },
      },
    },
  });
}

/* ── Pie / doughnut chart ─────────────────────────────────── */

function initPieChart(canvasId, data) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  _register(canvas, "pie", data);
  applyChartDefaults();
  var t = chartTheme();
  var existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  return new Chart(canvas.getContext("2d"), {
    type: "doughnut",
    data: {
      labels: localizeLabels(data.labels || []),
      datasets: (data.datasets || []).map(function (ds) {
        return Object.assign(
          {
            backgroundColor: CHART_COLORS,
            borderColor: themeVar("--card"),
            borderWidth: 2,
          },
          ds
        );
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: {
          display: true,
          position: "right",
          labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: t.tooltipBg,
          titleColor: t.tooltipFg,
          bodyColor: t.tooltipFg,
          borderColor: t.grid,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
        },
      },
    },
  });
}

/* ── Sparkline (tiny line, no axes) ───────────────────────── */

function initSparkline(canvasId, data) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  _register(canvas, "sparkline", data);
  var existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  return new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: localizeLabels(data.labels || []),
      datasets: [
        Object.assign(
          {
            fill: false,
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 0,
            borderColor: CHART_COLORS[0],
          },
          data.dataset || {}
        ),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

/* ── Re-render charts after HTMX swaps and theme changes ──── */

function _reinitAllCharts() {
  document.querySelectorAll("canvas").forEach(function (canvas) {
    if (!canvas._chartData) return;
    var type = canvas._chartType;
    var data = canvas._chartData;
    if (type === "timeseries") initTimeSeriesChart(canvas.id, data);
    else if (type === "bar") initBarChart(canvas.id, data);
    else if (type === "pie") initPieChart(canvas.id, data);
    else if (type === "sparkline") initSparkline(canvas.id, data);
  });
}

window.addEventListener("mantecato:themechange", _reinitAllCharts);
