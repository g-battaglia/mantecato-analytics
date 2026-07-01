"""Custom-dashboard widget engine.

Turns a saved dashboard ``config`` into rendered widgets by dispatching each
widget to the existing analytics services (``apps.analytics.services``) with the
right date range and filters, then shaping the result into a uniform render
context the templates consume.

Config schema (v2), stored in ``report.parameters`` and exposed as ``config``::

    {
      "version": 2,
      "layout": {"columns": 12},
      "dateRange": "30d",                         # dashboard default
      "filters": ["url_path:starts_with:/pro/"],  # cascade onto every widget
      "widgets": [ <widget>, ... ]
    }
    <widget> = {
      "id": "w1",
      "type": "kpi" | "timeseries" | "breakdown" | "heatmap",
      "title": "Pro — AI generations",
      "metric": "visitors" | ...,        # kpi
      "source": "events" | "sections" | ..., # breakdown
      "depth": 1,                        # breakdown source=sections (1 = tier)
      "chart": "bar" | "pie",            # breakdown viz
      "dateRange": "7d",                 # optional per-widget override
      "filters": ["event_name:eq:ai-generate-success"],
      "grid": {"x": 0, "y": 0, "w": 6, "h": 2}
    }

Filters cascade as ``dashboard.filters`` + ``widget.filters`` (the saved scope)
plus runtime (ad-hoc) filters. The engine OR-s same-column entries and AND-s
across columns; runtime filters may only add *new* columns (narrowing) — they
cannot relax a column the saved config already scopes. See :func:`_resolve_filters`.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Callable

from apps.analytics import services
from apps.analytics.chart_data import build_timeseries_chart_data
from apps.common.constants import VALID_RANGE_PRESETS
from core.mantecato_core.date_utils import DateRange, resolve_date_range
from core.mantecato_core.filters import (
    VALID_FILTER_COLUMNS,
    VALID_OPERATORS,
    parse_filters_from_params,
)

logger = logging.getLogger(__name__)

# A widget id is reversed into ``<str:widget_id>`` (regex ``[^/]+``) for the
# per-widget HTMX URL, so it must be a safe single URL path segment.
_WIDGET_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

if TYPE_CHECKING:
    from core.mantecato_core.filters import Filter

# ── Catalogs ─────────────────────────────────────────────────────────────────

WIDGET_TYPES = {"kpi", "timeseries", "breakdown", "heatmap"}

#: KPI metric → human label. Keys index into the ``stats`` card dict.
KPI_METRICS: dict[str, str] = {
    "pageviews": "Pageviews",
    "visitors": "Visitors",
    "visits": "Visits",
    "bounce_rate": "Bounce rate",
    "avg_duration": "Avg duration",
    "pages_per_visit": "Pages / visit",
}

#: Breakdown source → (service fn name, result key, label key, value key, value label).
BREAKDOWN_SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    "pages": ("get_pages_data", "pages", "urlPath", "views", "Views"),
    "sections": ("get_sections_data", "sections", "section", "views", "Views"),
    "events": ("get_events_data", "events", "eventName", "count", "Count"),
    "browser": ("get_devices_data", "browser", "value", "pageviews", "Views"),
    "os": ("get_devices_data", "os", "value", "pageviews", "Views"),
    "device": ("get_devices_data", "device", "value", "pageviews", "Views"),
    "country": ("get_geo_data", "geo", "country", "pageviews", "Views"),
    "sources": ("get_sources_data", "sources", "referrer", "pageviews", "Views"),
    "entry": ("get_landing_data", "landing", "entry_path", "visits", "Visits"),
}

_PALETTE = [
    "rgb(99, 102, 241)", "rgb(34, 197, 94)", "rgb(234, 179, 8)", "rgb(239, 68, 68)",
    "rgb(168, 85, 247)", "rgb(6, 182, 212)", "rgb(249, 115, 22)", "rgb(107, 114, 128)",
]
_BAR_FILL = "rgba(99, 102, 241, 0.7)"


# ── Resolution helpers ───────────────────────────────────────────────────────


def _resolve_filters(
    dashboard_cfg: dict[str, Any],
    widget: dict[str, Any],
    runtime_filters: list[Filter] | None,
) -> list[Filter]:
    """Combine the saved (dashboard + widget) filters with runtime (ad-hoc) filters.

    The engine OR-s same-column entries and AND-s across columns. A configured
    filter defines the dashboard's intended scope, so a runtime filter may only
    **narrow** by adding a *new* column — it cannot relax a column the saved
    config already scopes (which OR-ing on that column would do, e.g. a ``/pro/``
    dashboard widened to ``/pro/ OR /free/`` by ``?filter=url_path:...``). Runtime
    filters on already-scoped columns are therefore dropped. The synthetic
    ``__bot_filter__`` column is never configured, so bot filtering still applies.
    """
    raw = list(dashboard_cfg.get("filters") or []) + list(widget.get("filters") or [])
    filters = parse_filters_from_params([f for f in raw if isinstance(f, str)])
    scoped_columns = {f.column for f in filters}
    if runtime_filters:
        filters.extend(f for f in runtime_filters if f.column not in scoped_columns)
    return filters


def _resolve_range(widget: dict[str, Any], runtime_range: DateRange) -> DateRange:
    """A per-widget ``dateRange`` override wins; otherwise the runtime range."""
    token = widget.get("dateRange")
    if isinstance(token, str) and token:
        dr = resolve_date_range(token)
        if dr is not None:
            return dr
    return runtime_range


def _normalize_rows(rows: list[dict], label_key: str, value_key: str) -> list[dict]:
    """Shape heterogeneous breakdown rows into ``[{label, value, visitors, pct}]``."""
    out: list[dict[str, Any]] = []
    for r in rows:
        value = r.get(value_key)
        if value is None:
            value = r.get("visitors") or 0
        out.append(
            {
                "label": str(r.get(label_key) or "—"),
                "value": value,
                "visitors": r.get("visitors"),
            }
        )
    total = sum(x["value"] for x in out) or 0
    for x in out:
        x["pct"] = round(x["value"] / total * 100, 1) if total else 0
    return out


def _bar_payload(rows: list[dict], label: str, limit: int = 20) -> dict:
    top = rows[:limit]
    return {
        "labels": [r["label"] for r in top],
        "datasets": [{"label": label, "data": [r["value"] for r in top], "backgroundColor": _BAR_FILL}],
    }


def _pie_payload(rows: list[dict], limit: int = 8) -> dict:
    top = rows[:limit]
    return {
        "labels": [r["label"] for r in top],
        "datasets": [{"data": [r["value"] for r in top], "backgroundColor": _PALETTE[: len(top)]}],
    }


# ── Per-type renderers ───────────────────────────────────────────────────────


def _render_kpi(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    metric = widget.get("metric", "pageviews")
    if metric not in KPI_METRICS:
        return {"error": f"Unknown KPI metric: {metric}"}
    stats = services.get_kpis_data(website_id, date_range, filters)["stats"]
    return {"kind": "kpi", "stat": stats.get(metric), "metric_label": KPI_METRICS[metric]}


def _render_timeseries(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    # A per-widget granularity wins; otherwise the runtime (filter-bar) value.
    gran = widget.get("granularity") or granularity or "auto"
    data = services.get_timeseries_data(website_id, date_range, filters, granularity=gran)
    return {"kind": "timeseries", "chart": build_timeseries_chart_data(data["timeseries"])}


def _render_breakdown(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    source = widget.get("source", "events")
    spec = BREAKDOWN_SOURCES.get(source)
    if spec is None:
        return {"error": f"Unknown breakdown source: {source}"}
    service_name, result_key, label_key, value_key, value_label = spec
    fn: Callable[..., dict] = getattr(services, service_name)

    if source == "sections":
        depth = widget.get("depth", 2)
        depth = depth if isinstance(depth, int) and depth >= 1 else 2
        data = fn(website_id, date_range, filters, depth=depth)
    else:
        data = fn(website_id, date_range, filters)

    rows = _normalize_rows(data.get(result_key, []), label_key, value_key)
    chart_kind = "pie" if widget.get("chart") == "pie" else "bar"
    chart = _pie_payload(rows) if chart_kind == "pie" else _bar_payload(rows, value_label)
    return {
        "kind": "breakdown",
        "rows": rows,
        "value_label": value_label,
        "chart": chart,
        "chart_kind": chart_kind,
    }


def _render_heatmap(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    data = services.get_heatmap_data(website_id, date_range, filters)
    return {"kind": "heatmap", "grid": data["grid"], "max_val": data["max_val"]}


_RENDERERS: dict[str, Callable[..., dict]] = {
    "kpi": _render_kpi,
    "timeseries": _render_timeseries,
    "breakdown": _render_breakdown,
    "heatmap": _render_heatmap,
}


# ── Public API ───────────────────────────────────────────────────────────────


def render_widget(
    website_id: str,
    dashboard_cfg: dict[str, Any],
    widget: dict[str, Any],
    *,
    runtime_range: DateRange,
    runtime_filters: list[Filter] | None = None,
    runtime_granularity: str = "auto",
) -> dict[str, Any]:
    """Render one widget into a uniform context dict for the templates.

    Never raises: a bad widget yields ``{"error": "..."}`` so one broken widget
    can't take the whole dashboard down.
    """
    base = {
        "id": str(widget.get("id") or ""),
        "type": widget.get("type"),
        "title": widget.get("title") or "",
        "grid": widget.get("grid") or {},
    }
    wtype = widget.get("type")
    renderer = _RENDERERS.get(wtype) if isinstance(wtype, str) else None
    if renderer is None:
        return {**base, "error": f"Unknown widget type: {wtype}"}
    try:
        date_range = _resolve_range(widget, runtime_range)
        filters = _resolve_filters(dashboard_cfg, widget, runtime_filters)
        return {**base, **renderer(website_id, widget, date_range, filters, runtime_granularity)}
    except Exception:  # noqa: BLE001 — a widget must never break the page
        # Log the real error (with traceback) but show the viewer a generic
        # message — don't leak internal detail into the rendered card.
        logger.exception("Dashboard widget %s (%s) failed to render", base["id"], base["type"])
        return {**base, "error": "Could not load this widget."}


# ── Validation ───────────────────────────────────────────────────────────────


def _validate_filter_strings(values: Any, where: str, errors: list[str]) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        errors.append(f"{where}: 'filters' must be a list")
        return
    for f in values:
        if not isinstance(f, str) or f.count(":") < 2:
            errors.append(f"{where}: invalid filter '{f}' (expected 'column:operator:value')")
            continue
        column, operator, _ = f.split(":", 2)
        if column not in VALID_FILTER_COLUMNS:
            errors.append(f"{where}: unknown filter column '{column}'")
        if operator not in VALID_OPERATORS:
            errors.append(f"{where}: unknown filter operator '{operator}'")


def validate_dashboard_config(config: Any) -> list[str]:
    """Validate a dashboard config; return a list of human-readable errors (empty = ok).

    Lenient about extra keys (forward-compatible) but strict about the widget
    contract so a saved dashboard always renders.
    """
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["config must be a JSON object"]

    # ``x in <set|dict>`` raises TypeError for an unhashable x (a JSON list /
    # object), so every membership check first confirms the value is a string —
    # otherwise a malformed config (e.g. ``dateRange: []``) would 500 instead of
    # returning a clean validation error.
    date_range = config.get("dateRange")
    if date_range is not None and (not isinstance(date_range, str) or date_range not in VALID_RANGE_PRESETS):
        errors.append(f"dateRange '{date_range}' is not a valid preset")
    _validate_filter_strings(config.get("filters"), "dashboard", errors)

    widgets = config.get("widgets", [])
    if not isinstance(widgets, list):
        return errors + ["'widgets' must be a list"]

    seen_ids: set[str] = set()
    for i, w in enumerate(widgets):
        where = f"widget[{i}]"
        if not isinstance(w, dict):
            errors.append(f"{where}: must be an object")
            continue
        # A stable, unique, url-safe id is required: it is reversed into the
        # per-widget HTMX URL ({% url 'dashboard_widget' %}, a ``[^/]+`` segment),
        # so an empty id or one containing '/' 500s the page (NoReverseMatch).
        wid = w.get("id")
        if not isinstance(wid, str) or not _WIDGET_ID_RE.match(wid):
            errors.append(f"{where}: 'id' must be a non-empty url-safe string ([A-Za-z0-9_-]+)")
        elif wid in seen_ids:
            errors.append(f"{where}: duplicate id '{wid}'")
        else:
            seen_ids.add(wid)
        wtype = w.get("type")
        if not isinstance(wtype, str) or wtype not in WIDGET_TYPES:
            errors.append(f"{where}: type '{wtype}' must be one of {sorted(WIDGET_TYPES)}")
        if wtype == "kpi":
            metric = w.get("metric")
            if not isinstance(metric, str) or metric not in KPI_METRICS:
                errors.append(f"{where}: kpi metric '{metric}' must be one of {sorted(KPI_METRICS)}")
        if wtype == "breakdown":
            source = w.get("source")
            if not isinstance(source, str) or source not in BREAKDOWN_SOURCES:
                errors.append(
                    f"{where}: breakdown source '{source}' must be one of {sorted(BREAKDOWN_SOURCES)}"
                )
        wr = w.get("dateRange")
        if wr is not None and (not isinstance(wr, str) or wr not in VALID_RANGE_PRESETS):
            errors.append(f"{where}: dateRange '{wr}' is not a valid preset")
        _validate_filter_strings(w.get("filters"), where, errors)

    return errors
