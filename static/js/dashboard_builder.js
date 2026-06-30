/* Custom-dashboard visual builder.
 *
 * A vanilla-JS layer over Gridstack: holds the dashboard config as a JS model,
 * renders each widget as a draggable/resizable grid item with a live preview
 * (POSTed to the preview endpoint), edits widgets through a side drawer, and
 * serialises everything back into the hidden form's `config` field on save.
 */
(function () {
  "use strict";

  var root = document.getElementById("builder-root");
  if (!root || typeof GridStack === "undefined") return;

  var PREVIEW_URL = root.getAttribute("data-preview-url");
  var COLUMNS = [
    "url_path", "page_title", "hostname", "country",
    "browser", "os", "device", "event_name", "referrer_domain",
  ];
  var OPERATORS = [
    ["eq", "is"], ["neq", "is not"], ["contains", "contains"],
    ["not_contains", "does not contain"], ["starts_with", "starts with"],
    ["not_starts_with", "does not start with"], ["in", "in (comma list)"],
    ["not_in", "not in (comma list)"],
  ];
  var DEFAULTS = { kpi: { metric: "pageviews" }, breakdown: { source: "events", chart: "bar" } };

  function readJSON(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try { return JSON.parse(el.textContent); } catch (e) { return fallback; }
  }
  function csrf() {
    var i = document.querySelector("#builder-form [name=csrfmiddlewaretoken]");
    return i ? i.value : "";
  }
  function uid() {
    return "w" + Math.random().toString(36).slice(2, 8) + (state.widgets.length + 1);
  }

  /* ── State ───────────────────────────────────────────────────────────── */
  var cfg = readJSON("dash-config", {}) || {};
  var state = {
    version: 2,
    layout: { columns: 12 },
    dateRange: typeof cfg.dateRange === "string" ? cfg.dateRange : "30d",
    filters: Array.isArray(cfg.filters) ? cfg.filters.slice() : [],
    widgets: (Array.isArray(cfg.widgets) ? cfg.widgets : []).filter(function (w) {
      return w && typeof w === "object";
    }).map(function (w) { return Object.assign({}, w, { id: w.id || uid() }); }),
  };

  /* ── Grid ────────────────────────────────────────────────────────────── */
  var grid = GridStack.init({ column: 12, cellHeight: 90, margin: 8, float: true, handle: ".w-drag" });

  function widgetShell(w) {
    var badge = w.type === "breakdown" ? (w.source || "breakdown") : w.type;
    return (
      '<div class="flex h-full flex-col rounded-lg border border-border bg-card shadow-sm" data-wid="' + w.id + '">' +
        '<div class="w-drag flex cursor-move items-center justify-between gap-2 border-b border-border/50 px-3 py-1.5">' +
          '<span class="truncate text-xs font-medium text-foreground">' + (w.title || "") +
            ' <span class="ml-1 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">' + badge + "</span></span>" +
          '<span class="flex shrink-0 items-center gap-1">' +
            '<button type="button" data-act="edit" class="text-muted-foreground hover:text-foreground" title="Edit"><i data-lucide="settings-2" class="size-3.5"></i></button>' +
            '<button type="button" data-act="del" class="text-muted-foreground hover:text-destructive" title="Remove"><i data-lucide="trash-2" class="size-3.5"></i></button>' +
          "</span></div>" +
        '<div class="wpreview min-h-0 flex-1 overflow-auto p-1"><div class="flex h-full items-center justify-center p-4 text-xs text-muted-foreground"><span class="animate-pulse">…</span></div></div>' +
      "</div>"
    );
  }

  function addGridItem(w) {
    var box = w.grid || {};
    var el = grid.addWidget({
      x: box.x, y: box.y, w: box.w || 6, h: box.h || 3,
      id: w.id, content: widgetShell(w),
    });
    if (window.lucide) lucide.createIcons();
    preview(w);
    return el;
  }

  function findWidget(id) {
    for (var i = 0; i < state.widgets.length; i++) if (state.widgets[i].id === id) return state.widgets[i];
    return null;
  }

  function preview(w) {
    var host = root.querySelector('[data-wid="' + w.id + '"] .wpreview');
    if (!host) return;
    fetch(PREVIEW_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ widget: w, dashboardFilters: state.filters, dashboardDateRange: state.dateRange }),
    })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        host.innerHTML = html;
        if (window.lucide) lucide.createIcons();
        if (typeof window.htmx !== "undefined") window.htmx.process(host);
        // Re-init any chart payloads that arrived in the preview.
        document.dispatchEvent(new CustomEvent("htmx:afterSwap", { detail: { target: host } }));
      })
      .catch(function () { host.innerHTML = '<div class="p-4 text-xs text-destructive">Preview failed</div>'; });
  }

  function syncPositions() {
    var nodes = grid.save(false) || [];
    nodes.forEach(function (n) {
      var w = findWidget(n.id);
      if (w) w.grid = { x: n.x, y: n.y, w: n.w, h: n.h };
    });
  }

  function refreshEmptyHint() {
    document.getElementById("empty-hint").classList.toggle("hidden", state.widgets.length > 0);
  }

  /* ── Drawer (widget editor) ──────────────────────────────────────────── */
  var drawer = document.getElementById("cfg-drawer");
  var overlay = document.getElementById("cfg-overlay");
  var editingId = null;

  function showFields() {
    var t = document.getElementById("cfg-type").value;
    var src = document.getElementById("cfg-source").value;
    drawer.querySelectorAll("[data-when]").forEach(function (el) {
      var when = el.getAttribute("data-when");
      var on = (when === t) || (when === "breakdown-sections" && t === "breakdown" && src === "sections");
      el.classList.toggle("hidden", !on);
    });
  }

  function filterRow(container, f) {
    var row = document.createElement("div");
    row.className = "mb-1.5 flex items-center gap-1";
    var parts = (f || "").split(":");
    var colOpts = COLUMNS.map(function (c) { return '<option value="' + c + '"' + (parts[0] === c ? " selected" : "") + ">" + c + "</option>"; }).join("");
    var opOpts = OPERATORS.map(function (o) { return '<option value="' + o[0] + '"' + (parts[1] === o[0] ? " selected" : "") + ">" + o[1] + "</option>"; }).join("");
    row.innerHTML =
      '<select class="f-col h-8 rounded-md border border-input bg-background px-1.5 text-xs">' + colOpts + "</select>" +
      '<select class="f-op h-8 rounded-md border border-input bg-background px-1 text-xs">' + opOpts + "</select>" +
      '<input class="f-val h-8 w-full rounded-md border border-input bg-background px-1.5 text-xs" value="' + (parts.slice(2).join(":") || "") + '">' +
      '<button type="button" class="f-del shrink-0 text-muted-foreground hover:text-destructive"><i data-lucide="x" class="size-3.5"></i></button>';
    row.querySelector(".f-del").addEventListener("click", function () { row.remove(); });
    container.appendChild(row);
    if (window.lucide) lucide.createIcons();
  }

  function readFilters(container) {
    var out = [];
    container.querySelectorAll(":scope > div").forEach(function (row) {
      var col = row.querySelector(".f-col").value;
      var op = row.querySelector(".f-op").value;
      var val = row.querySelector(".f-val").value.trim();
      if (val) out.push(col + ":" + op + ":" + val);
    });
    return out;
  }

  function openDrawer(w) {
    editingId = w ? w.id : null;
    var d = w || { type: "kpi" };
    document.getElementById("cfg-type").value = d.type || "kpi";
    document.getElementById("cfg-title").value = d.title || "";
    document.getElementById("cfg-metric").value = d.metric || "pageviews";
    document.getElementById("cfg-source").value = d.source || "events";
    document.getElementById("cfg-chart").value = d.chart || "bar";
    document.getElementById("cfg-depth").value = d.depth || 2;
    document.getElementById("cfg-dateRange").value = d.dateRange || "";
    var fc = document.getElementById("cfg-filters");
    fc.innerHTML = "";
    (d.filters || []).forEach(function (f) { filterRow(fc, f); });
    showFields();
    overlay.classList.remove("hidden");
    drawer.classList.remove("hidden");
  }
  function closeDrawer() { overlay.classList.add("hidden"); drawer.classList.add("hidden"); }

  document.getElementById("cfg-type").addEventListener("change", showFields);
  document.getElementById("cfg-source").addEventListener("change", showFields);
  document.getElementById("cfg-close").addEventListener("click", closeDrawer);
  overlay.addEventListener("click", closeDrawer);
  document.getElementById("cfg-add-filter").addEventListener("click", function () {
    filterRow(document.getElementById("cfg-filters"), "");
  });

  document.getElementById("cfg-apply").addEventListener("click", function () {
    var t = document.getElementById("cfg-type").value;
    var w = {
      id: editingId || uid(),
      type: t,
      title: document.getElementById("cfg-title").value.trim(),
      dateRange: document.getElementById("cfg-dateRange").value || undefined,
      filters: readFilters(document.getElementById("cfg-filters")),
    };
    if (t === "kpi") w.metric = document.getElementById("cfg-metric").value;
    if (t === "breakdown") {
      w.source = document.getElementById("cfg-source").value;
      w.chart = document.getElementById("cfg-chart").value;
      if (w.source === "sections") w.depth = parseInt(document.getElementById("cfg-depth").value, 10) || 1;
    }
    if (editingId) {
      var existing = findWidget(editingId);
      w.grid = existing ? existing.grid : undefined;
      Object.keys(existing).forEach(function (k) { delete existing[k]; });
      Object.assign(existing, w);
      preview(existing);
      // Refresh the header (title/type may have changed).
      var shell = root.querySelector('[data-wid="' + w.id + '"]');
      if (shell) {
        var holder = document.createElement("div");
        holder.innerHTML = widgetShell(existing);
        shell.parentNode.replaceChild(holder.firstChild, shell);
        if (window.lucide) lucide.createIcons();
        preview(existing);
      }
    } else {
      state.widgets.push(w);
      addGridItem(w);
    }
    refreshEmptyHint();
    closeDrawer();
  });

  /* ── Grid item actions (edit / delete) ───────────────────────────────── */
  root.querySelector(".grid-stack").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn) return;
    var shell = btn.closest("[data-wid]");
    if (!shell) return;
    var id = shell.getAttribute("data-wid");
    if (btn.getAttribute("data-act") === "edit") {
      openDrawer(findWidget(id));
    } else if (btn.getAttribute("data-act") === "del") {
      var item = shell.closest(".grid-stack-item");
      if (item) grid.removeWidget(item);
      state.widgets = state.widgets.filter(function (w) { return w.id !== id; });
      refreshEmptyHint();
    }
  });

  /* ── Dashboard-level filters ─────────────────────────────────────────── */
  var dashFiltersBox = document.getElementById("b-dash-filters");
  function renderDashFilters() {
    dashFiltersBox.innerHTML = "";
    state.filters.forEach(function (f, idx) {
      var chip = document.createElement("span");
      chip.className = "inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2 font-mono text-[11px] text-foreground";
      chip.innerHTML = "<span>" + f + '</span><button type="button" class="text-muted-foreground hover:text-destructive">×</button>';
      chip.querySelector("button").addEventListener("click", function () {
        state.filters.splice(idx, 1); renderDashFilters(); state.widgets.forEach(preview);
      });
      dashFiltersBox.appendChild(chip);
    });
    var add = document.createElement("button");
    add.type = "button";
    add.className = "inline-flex h-7 items-center gap-1 rounded-md border border-input bg-background px-2 text-xs text-muted-foreground hover:bg-muted";
    add.innerHTML = '<i data-lucide="plus" class="size-3"></i>filter';
    add.addEventListener("click", function () {
      var f = prompt("Filter (column:operator:value), e.g. url_path:starts_with:/pro/");
      if (f && f.split(":").length >= 3) { state.filters.push(f.trim()); renderDashFilters(); state.widgets.forEach(preview); }
    });
    dashFiltersBox.appendChild(add);
    if (window.lucide) lucide.createIcons();
  }

  /* ── Toolbar wiring ──────────────────────────────────────────────────── */
  document.getElementById("b-dateRange").value = state.dateRange;
  document.getElementById("b-dateRange").addEventListener("change", function () {
    state.dateRange = this.value; state.widgets.forEach(preview);
  });
  document.getElementById("btn-add-widget").addEventListener("click", function () { openDrawer(null); });

  document.getElementById("btn-advanced").addEventListener("click", function () {
    var panel = document.getElementById("advanced-panel");
    syncPositions();
    document.getElementById("b-json").value = JSON.stringify(currentConfig(), null, 2);
    panel.classList.toggle("hidden");
  });
  document.getElementById("btn-json-apply").addEventListener("click", function () {
    try {
      var parsed = JSON.parse(document.getElementById("b-json").value);
      document.getElementById("json-error").textContent = "";
      cfg = parsed;
      state.dateRange = typeof parsed.dateRange === "string" ? parsed.dateRange : "30d";
      state.filters = Array.isArray(parsed.filters) ? parsed.filters.slice() : [];
      state.widgets = (Array.isArray(parsed.widgets) ? parsed.widgets : []).map(function (w) {
        return Object.assign({}, w, { id: w.id || uid() });
      });
      grid.removeAll();
      state.widgets.forEach(addGridItem);
      renderDashFilters();
      refreshEmptyHint();
    } catch (err) {
      document.getElementById("json-error").textContent = "Invalid JSON";
    }
  });

  function currentConfig() {
    syncPositions();
    return {
      version: 2,
      layout: { columns: 12 },
      dateRange: state.dateRange,
      filters: state.filters,
      widgets: state.widgets,
    };
  }

  document.getElementById("btn-save").addEventListener("click", function () {
    document.getElementById("f-name").value = document.getElementById("b-name").value.trim() || "Dashboard";
    document.getElementById("f-description").value = root.getAttribute("data-description") || "";
    document.getElementById("f-config").value = JSON.stringify(currentConfig());
    document.getElementById("builder-form").submit();
  });

  grid.on("change", syncPositions);

  /* ── Boot ────────────────────────────────────────────────────────────── */
  state.widgets.forEach(addGridItem);
  renderDashFilters();
  refreshEmptyHint();
})();
