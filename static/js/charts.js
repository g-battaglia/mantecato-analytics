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

/* ── Toggleable categorical charts (bar ⇄ pie) + chart cards ─ */
/*
 * A "chart card" is any element carrying ``data-chart-card="<key>"``.  It holds
 * one categorical canvas (``data-chart-role="categorical"``) that can render as
 * a bar OR a pie from the *same* payload, plus optional extra views (e.g. a
 * time-series ``data-chart-role="timeline"`` canvas, used by the Events page).
 * Toggle buttons (``data-chart-toggle-btn`` with ``data-type``) switch the view;
 * the choice is remembered per key in localStorage.
 *
 * Both bar and pie consume the shape ``{labels, datasets:[{data}]}`` — we strip
 * any per-series colors so each renderer applies its own theme palette (single
 * accent for bars, multi-color slices for pies).
 */

var CHART_TYPE_PREFIX = "mantecato:charttype:";

function _savedChartType(key) {
  if (!key) return null;
  try {
    var v = localStorage.getItem(CHART_TYPE_PREFIX + key);
    return v === "bar" || v === "pie" || v === "timeline" ? v : null;
  } catch (e) {
    return null;
  }
}

function _stripSeriesColors(data) {
  return {
    labels: (data && data.labels) || [],
    datasets: ((data && data.datasets) || []).map(function (ds) {
      var copy = Object.assign({}, ds);
      delete copy.backgroundColor;
      delete copy.borderColor;
      return copy;
    }),
  };
}

// Render `data` as a bar or pie chart from a single shared payload.
function initToggleableChart(canvasId, data, type) {
  var normalized = _stripSeriesColors(data || {});
  return type === "pie"
    ? initPieChart(canvasId, normalized)
    : initBarChart(canvasId, normalized);
}

function _readJSON(elId) {
  var el = elId ? document.getElementById(elId) : null;
  if (!el) return null;
  try {
    return JSON.parse(el.textContent);
  } catch (e) {
    return null;
  }
}

// Initialize standalone charts (time-series, sparkline) that live outside a card.
function autoInitCharts(scope) {
  var root = scope && scope.querySelectorAll ? scope : document;
  root.querySelectorAll("canvas[data-chart-src]").forEach(function (canvas) {
    if (canvas.closest("[data-chart-card]")) return; // handled by initChartCards
    var data = _readJSON(canvas.getAttribute("data-chart-src"));
    if (!data) return;
    var kind = canvas.getAttribute("data-chart-kind") || "categorical";
    if (kind === "timeseries") initTimeSeriesChart(canvas.id, data);
    else if (kind === "sparkline") initSparkline(canvas.id, data);
    else initToggleableChart(canvas.id, data, canvas.getAttribute("data-chart-default") || "bar");
  });
}

// Switch a card to a view (bar/pie/timeline): show the right wrapper, re-render
// the categorical canvas, sync button styles, and optionally persist the choice.
function _selectChartView(card, key, type, persist) {
  var view = type === "timeline" ? "timeline" : "categorical";

  card.querySelectorAll("[data-chart-view]").forEach(function (wrap) {
    wrap.classList.toggle("hidden", wrap.getAttribute("data-chart-view") !== view);
  });

  if (view === "categorical") {
    var canvas = card.querySelector('canvas[data-chart-role="categorical"]');
    if (canvas) {
      var data = canvas._chartData || _readJSON(canvas.getAttribute("data-chart-src"));
      if (data) initToggleableChart(canvas.id, data, type);
    }
  }

  card.querySelectorAll("[data-chart-toggle-btn]").forEach(function (btn) {
    var active = btn.getAttribute("data-type") === type;
    btn.classList.toggle("bg-primary", active);
    btn.classList.toggle("text-primary-foreground", active);
    btn.classList.toggle("bg-muted", !active);
    btn.classList.toggle("text-muted-foreground", !active);
    btn.classList.toggle("hover:text-foreground", !active);
  });

  if (persist && key) {
    try {
      localStorage.setItem(CHART_TYPE_PREFIX + key, type);
    } catch (e) {
      /* storage unavailable — choice just won't persist */
    }
  }
}

// Initialize every chart card within `scope`.
function initChartCards(scope) {
  var root = scope && scope.querySelectorAll ? scope : document;
  root.querySelectorAll("[data-chart-card]").forEach(function (card) {
    if (card._chartCardReady) return;
    card._chartCardReady = true;

    var key = card.getAttribute("data-chart-card");
    var def = card.getAttribute("data-chart-default") || "bar";

    // Render extra (timeline) views up front so switching is instant; hidden
    // canvases size correctly on show via Chart.js's ResizeObserver.
    card.querySelectorAll('canvas[data-chart-role="timeline"][data-chart-src]').forEach(function (canvas) {
      var data = _readJSON(canvas.getAttribute("data-chart-src"));
      if (data) initTimeSeriesChart(canvas.id, data);
    });

    _selectChartView(card, key, _savedChartType(key) || def, false);
  });
}

// Delegated toggle-button handler.
document.addEventListener("click", function (e) {
  var btn = e.target.closest("[data-chart-toggle-btn]");
  if (!btn) return;
  var card = btn.closest("[data-chart-card]");
  if (!card) return;
  _selectChartView(card, card.getAttribute("data-chart-card"), btn.getAttribute("data-type"), true);
});

/* ── Re-render charts after HTMX swaps and theme changes ──── */

function _initAllCharts(scope) {
  autoInitCharts(scope);
  initChartCards(scope);
}

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

document.addEventListener("DOMContentLoaded", function () {
  _initAllCharts(document);
});
document.addEventListener("htmx:afterSwap", function (e) {
  _initAllCharts((e.detail && e.detail.target) || e.target || document);
});
window.addEventListener("mantecato:themechange", _reinitAllCharts);
