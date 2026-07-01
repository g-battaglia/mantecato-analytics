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

WIDGET_TYPES = {"kpi", "timeseries", "breakdown", "heatmap", "funnel", "namespace", "ratio", "compare"}

# Upper bound for the "sections" breakdown grouping depth. Beyond this the
# breakdown degrades into a near-per-full-URL list, so a hand-edited config
# with an absurd depth is both clamped (dispatcher) and rejected (validation).
_MAX_SECTION_DEPTH = 6

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

    Within a column the engine OR-s positive filters and AND-s negated ones;
    columns AND together. A configured filter defines the dashboard's scope, so
    a runtime **positive** filter on a column already scoped by a positive would
    OR — *widening* the saved scope (a ``/pro/`` dashboard relaxed to
    ``/pro/ OR /free/``); those are dropped. Runtime **negated** filters (and any
    filter on a new column) only ever *narrow*, so they are kept. The synthetic
    ``__bot_filter__`` column is never configured, so bot filtering still applies.
    """
    from core.mantecato_core.filters import POSITIVE_OPERATORS

    raw = list(dashboard_cfg.get("filters") or []) + list(widget.get("filters") or [])
    filters = parse_filters_from_params([f for f in raw if isinstance(f, str)])
    scoped_positive_cols = {f.column for f in filters if f.operator in POSITIVE_OPERATORS}
    if runtime_filters:
        filters.extend(
            f
            for f in runtime_filters
            if not (f.operator in POSITIVE_OPERATORS and f.column in scoped_positive_cols)
        )
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
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
            depth = 2
        depth = min(depth, _MAX_SECTION_DEPTH)  # avoid degrading into per-full-URL
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


def _unique_visitors_for_events(website_id, date_range, filters, names: list[str]) -> dict[str, int]:
    """Exact unique visitors per event name within the window (cookieless digest).

    Reuses ``read_scope_visitors(scope="event")`` — the same monthly-rotating,
    IP-coarsened HMAC digest the rest of the app counts with. No per-person
    cross-time identity.
    """
    from core.mantecato_core.queries.visitors import read_scope_visitors

    if not names:
        return {}
    return read_scope_visitors(
        website_id,
        date_range.start_date,
        date_range.end_date,
        scope="event",
        scope_values=names,
        filters=filters,
    )


def _render_funnel(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    # Steps: [{"event": "funnel/signup/start", "label": "Signup"}, ...]. Each step
    # is the count of distinct visitors (within the window) who fired that event —
    # an aggregate flow, never a same-person cross-time cohort.
    steps = [s for s in (widget.get("steps") or []) if isinstance(s, dict) and s.get("event")]
    if not steps:
        return {"error": "Funnel needs at least one step with an 'event'."}
    counts = _unique_visitors_for_events(website_id, date_range, filters, [s["event"] for s in steps])
    rows = [{"label": s.get("label") or s["event"], "visitors": counts.get(s["event"], 0)} for s in steps]
    first = rows[0]["visitors"] if rows else 0
    for r in rows:
        r["pct"] = round(r["visitors"] / first * 100, 1) if first else 0
    from apps.analytics.chart_data import build_funnel_chart_data

    return {"kind": "funnel", "chart": build_funnel_chart_data(rows), "rows": rows}


def _render_namespace(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    # Group event names by a slash- (or custom-) delimited prefix depth, mirroring
    # url_path section grouping but for events. Generic: delimiter is configurable
    # and it degrades to full names when there is no delimiter.
    from collections import defaultdict

    from core.mantecato_core.queries.events import get_event_metrics

    delimiter = widget.get("delimiter") or "/"
    depth = widget.get("depth", 1)
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
        depth = 1
    depth = min(depth, _MAX_SECTION_DEPTH)

    rows_raw = get_event_metrics(
        website_id, date_range.start_date, date_range.end_date, limit=1000, filters=filters
    )
    groups: dict[str, int] = defaultdict(int)
    for r in rows_raw:
        name = r.get("eventName") or r.get("event_name") or ""
        prefix = delimiter.join(name.split(delimiter)[:depth]) if name else "—"
        groups[prefix or "—"] += r.get("count") or 0

    rows = [{"label": k, "value": v, "visitors": None} for k, v in sorted(groups.items(), key=lambda x: -x[1])]
    total = sum(x["value"] for x in rows) or 0
    for x in rows:
        x["pct"] = round(x["value"] / total * 100, 1) if total else 0
    chart_kind = "pie" if widget.get("chart") == "pie" else "bar"
    chart = _pie_payload(rows) if chart_kind == "pie" else _bar_payload(rows, "Count")
    # Reuse the breakdown template (same shape).
    return {"kind": "breakdown", "rows": rows, "value_label": "Count", "chart": chart, "chart_kind": chart_kind}


def _render_ratio(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    # Generic ratio of two event-visitor counts (e.g. upgrade ÷ trial-start).
    # Both operands are event names → distinct visitors within the window.
    num, den = widget.get("numerator") or {}, widget.get("denominator") or {}
    num_event, den_event = num.get("event"), den.get("event")
    if not num_event or not den_event:
        return {"error": "Ratio needs numerator.event and denominator.event."}
    counts = _unique_visitors_for_events(website_id, date_range, filters, [num_event, den_event])
    num_val, den_val = counts.get(num_event, 0), counts.get(den_event, 0)
    pct = round(num_val / den_val * 100, 1) if den_val else None
    return {
        "kind": "ratio",
        "pct": pct,
        "numerator": num_val,
        "denominator": den_val,
        "num_label": num.get("label") or num_event,
        "den_label": den.get("label") or den_event,
    }


def _render_compare(website_id, widget, date_range, filters, granularity="auto") -> dict[str, Any]:
    mode = widget.get("comparison")
    if mode not in ("previous_period", "previous_year"):
        mode = "previous_period"
    gran = widget.get("granularity") or granularity or "auto"
    data = services.get_compare_data(website_id, date_range, filters, mode, granularity=gran)
    return {
        "kind": "compare",
        "chart": build_timeseries_chart_data(data["current_ts"], data["previous_ts"]),
    }


_RENDERERS: dict[str, Callable[..., dict]] = {
    "kpi": _render_kpi,
    "timeseries": _render_timeseries,
    "breakdown": _render_breakdown,
    "heatmap": _render_heatmap,
    "funnel": _render_funnel,
    "namespace": _render_namespace,
    "ratio": _render_ratio,
    "compare": _render_compare,
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
            depth = w.get("depth")
            if depth is not None and (
                not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= _MAX_SECTION_DEPTH
            ):
                errors.append(f"{where}: depth must be an integer 1–{_MAX_SECTION_DEPTH}")
        if wtype == "namespace":
            depth = w.get("depth")
            if depth is not None and (
                not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= _MAX_SECTION_DEPTH
            ):
                errors.append(f"{where}: depth must be an integer 1–{_MAX_SECTION_DEPTH}")
        if wtype == "funnel":
            steps = w.get("steps")
            if not isinstance(steps, list) or not steps:
                errors.append(f"{where}: funnel needs a non-empty 'steps' list")
            elif not all(isinstance(s, dict) and isinstance(s.get("event"), str) and s.get("event") for s in steps):
                errors.append(f"{where}: each funnel step needs a string 'event'")
        if wtype == "ratio":
            for side in ("numerator", "denominator"):
                spec = w.get(side)
                if not isinstance(spec, dict) or not isinstance(spec.get("event"), str) or not spec.get("event"):
                    errors.append(f"{where}: ratio '{side}' needs an object with a string 'event'")
        if wtype == "compare":
            mode = w.get("comparison")
            if mode is not None and mode not in ("previous_period", "previous_year"):
                errors.append(f"{where}: comparison must be 'previous_period' or 'previous_year'")
        wr = w.get("dateRange")
        if wr is not None and (not isinstance(wr, str) or wr not in VALID_RANGE_PRESETS):
            errors.append(f"{where}: dateRange '{wr}' is not a valid preset")
        _validate_filter_strings(w.get("filters"), where, errors)

    return errors
