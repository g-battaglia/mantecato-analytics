"""Chart.js payload builders for analytics templates.

These helpers shape query-engine results into the exact dict structure the
``Chart.js`` initialisation code in :file:`static/js/charts.js` expects.
Keeping them out of :mod:`apps.analytics.views` makes the view classes thin
control-flow and lets templates render the same payloads from any caller
(HTMX partials, future MCP responses, ...).

Cross-refs:
    - :file:`static/js/charts.js` — client-side Chart.js initialisation.
    - :func:`apps.analytics.services.get_overview_data`
"""

from __future__ import annotations

# Indigo / green pair used for the "Pageviews vs Visitors" time series.
_TS_PAGEVIEWS_BORDER = "rgb(99, 102, 241)"
_TS_PAGEVIEWS_BG = "rgba(99, 102, 241, 0.1)"
_TS_VISITORS_BORDER = "rgb(34, 197, 94)"
_TS_VISITORS_BG = "rgba(34, 197, 94, 0.1)"

# Doughnut palette reused for device / browser / OS slices.
_DIMENSION_PALETTE = (
    "rgb(99, 102, 241)",
    "rgb(34, 197, 94)",
    "rgb(234, 179, 8)",
    "rgb(239, 68, 68)",
    "rgb(168, 85, 247)",
    "rgb(6, 182, 212)",
    "rgb(249, 115, 22)",
    "rgb(107, 114, 128)",
    "rgb(236, 72, 153)",
    "rgb(20, 184, 166)",
)

# Funnel-bar fills (lower-opacity variants of the doughnut palette).
_FUNNEL_PALETTE = (
    "rgba(99, 102, 241, 0.7)",
    "rgba(34, 197, 94, 0.7)",
    "rgba(234, 179, 8, 0.7)",
    "rgba(239, 68, 68, 0.7)",
    "rgba(168, 85, 247, 0.7)",
)


_TS_PREV_PAGEVIEWS_BORDER = "rgba(99, 102, 241, 0.4)"
_TS_PREV_VISITORS_BORDER = "rgba(34, 197, 94, 0.4)"


def build_timeseries_chart_data(
    timeseries: list[dict],
    prev_timeseries: list[dict] | None = None,
) -> dict:
    """Convert ``[{"time", "pageviews", "visitors"}, ...]`` to Chart.js shape.

    When *prev_timeseries* is provided, a dashed dataset is appended
    representing the previous period. Aligned by index — zero-padded if shorter,
    truncated if longer.
    """
    if not timeseries:
        return {"labels": [], "datasets": []}

    labels = [p["time"] for p in timeseries]
    datasets = [
        {
            "label": "Pageviews",
            "data": [p["pageviews"] for p in timeseries],
            "borderColor": _TS_PAGEVIEWS_BORDER,
            "backgroundColor": _TS_PAGEVIEWS_BG,
        },
    ]

    # Exact "Visits" series — present only at day+ granularity (visits are daily).
    if any("visits" in p for p in timeseries):
        datasets.append({
            "label": "Visits",
            "data": [p.get("visits", 0) for p in timeseries],
            "borderColor": _TS_VISITORS_BORDER,
            "backgroundColor": _TS_VISITORS_BG,
        })

    if prev_timeseries:
        prev_pv = [p["pageviews"] for p in prev_timeseries]
        n = len(labels)
        if len(prev_pv) < n:
            prev_pv.extend([0] * (n - len(prev_pv)))
        datasets.append({
            "label": "Prev Pageviews",
            "data": prev_pv[:n],
            "borderColor": _TS_PREV_PAGEVIEWS_BORDER,
            "backgroundColor": "transparent",
            "borderDash": [5, 5],
            "fill": False,
        })

    return {"labels": labels, "datasets": datasets}


def build_dimension_chart_data(dimensions: list[dict]) -> dict:
    """Convert device-dimension rows to a Chart.js doughnut payload.

    Args:
        dimensions: rows shaped ``[{"value": "<label>", "pageviews": <int>}, ...]``
            (the format returned by :func:`core.mantecato_core.queries.devices.get_device_metrics`
            for ``browser`` / ``os`` / ``device``).

    Returns:
        ``{"labels": [...], "datasets": [{"data": [...], "backgroundColor": [...]}]}``.
    """
    if not dimensions:
        return {"labels": [], "datasets": []}

    labels = [d["value"] for d in dimensions]
    values = [d.get("pageviews", d.get("visitors", 0)) for d in dimensions]
    return {
        "labels": labels,
        "datasets": [
            {
                "data": values,
                "backgroundColor": list(_DIMENSION_PALETTE[: len(values)]),
            }
        ],
    }


def build_funnel_chart_data(funnel_steps: list[dict]) -> dict:
    """Convert funnel step rows to a horizontal Chart.js bar payload.

    Args:
        funnel_steps: rows shaped ``[{"label": "<step>", "visitors": <int>}, ...]``
            returned by :func:`apps.analytics.services.get_funnels_data`.

    Returns:
        Chart.js horizontal-bar config ready to render in
        :file:`templates/analytics/funnels.html`.
    """
    if not funnel_steps:
        return {"labels": [], "datasets": []}

    labels = [s["label"] for s in funnel_steps]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Visitors",
                "data": [s["visitors"] for s in funnel_steps],
                "backgroundColor": list(_FUNNEL_PALETTE[: len(funnel_steps)]),
            }
        ],
    }


def build_pages_bar_chart_data(pages: list[dict], limit: int = 10) -> dict:
    """Convert page-metric rows to a Chart.js vertical bar payload.

    Targets a ``Chart('bar', ...)`` with indigo-filled bars showing view counts.
    Uses the page title as the bar label when available, falling back to the
    URL path.

    Args:
        pages: Rows shaped ``[{"urlPath": str, "pageTitle": str | None,
            "views": int}, ...]`` from ``get_page_metrics`` or ``get_top_pages``.
        limit: Maximum number of pages to include (default 10).

    Returns:
        ``{"labels": [...], "datasets": [{"label": "Views", "data": [...],
        "backgroundColor": "rgba(99, 102, 241, 0.7)"}]}``.
    """
    if not pages:
        return {"labels": [], "datasets": []}
    top = pages[:limit]
    labels = [p.get("pageTitle") or p["urlPath"] for p in top]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Views",
                "data": [p["views"] for p in top],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_sections_bar_chart_data(sections: list[dict], limit: int = 15) -> dict:
    """Convert section-metric rows to a Chart.js vertical bar payload.

    Targets a ``Chart('bar', ...)`` with indigo-filled bars showing view counts
    per URL-prefix section (e.g. ``/blog``, ``/docs``).

    Args:
        sections: Rows ``[{"section": str, "views": int}, ...]`` from
            ``get_top_sections``.
        limit: Maximum sections to include (default 15).

    Returns:
        Chart.js bar config with section names as labels and view counts as data.
    """
    if not sections:
        return {"labels": [], "datasets": []}
    top = sections[:limit]
    return {
        "labels": [s["section"] for s in top],
        "datasets": [
            {
                "label": "Views",
                "data": [s["views"] for s in top],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_channels_doughnut_data(channels: list[dict], limit: int = 6) -> dict:
    """Convert marketing-channel rows to a Chart.js doughnut payload.

    Targets a ``Chart('doughnut', ...)`` using the ``_DIMENSION_PALETTE``
    color cycle.  Capped at 6 slices to keep the doughnut chart readable.

    Args:
        channels: Rows ``[{"channel": str, "visitors": int}, ...]`` from
            ``get_channel_metrics``.
        limit: Maximum slices (default 6).

    Returns:
        Chart.js doughnut config with channel names as labels and visitor
        counts as data, each slice colored from ``_DIMENSION_PALETTE``.
    """
    if not channels:
        return {"labels": [], "datasets": []}
    top = channels[:limit]
    return {
        "labels": [c["channel"] for c in top],
        "datasets": [
            {
                "data": [c["visitors"] for c in top],
                "backgroundColor": list(_DIMENSION_PALETTE[: len(top)]),
            }
        ],
    }


def build_referrers_bar_chart_data(referrers: list[dict], limit: int = 10) -> dict:
    """Convert referrer-domain rows to a Chart.js vertical bar payload.

    Targets a ``Chart('bar', ...)`` with green-filled bars showing visitor
    counts per referring domain.

    Args:
        referrers: Rows ``[{"referrerDomain": str, "visitors": int}, ...]``
            from ``get_referrer_metrics``.
        limit: Maximum referrers to include (default 10).

    Returns:
        Chart.js bar config with referrer domains as labels and visitor
        counts as data, using green ``rgba(34, 197, 94, 0.7)`` fill.
    """
    if not referrers:
        return {"labels": [], "datasets": []}
    top = referrers[:limit]
    return {
        "labels": [r["referrerDomain"] for r in top],
        "datasets": [
            {
                "label": "Visitors",
                "data": [r["visitors"] for r in top],
                "backgroundColor": "rgba(34, 197, 94, 0.7)",
            }
        ],
    }


def build_events_pie_chart_data(events: list[dict], limit: int = 8) -> dict:
    """Convert event-metric rows to a Chart.js doughnut/pie payload.

    Targets a ``Chart('doughnut', ...)`` using the ``_DIMENSION_PALETTE``
    color cycle to show the distribution of custom events by count.

    Args:
        events: Rows ``[{"eventName": str, "count": int}, ...]`` from
            ``get_event_metrics``.
        limit: Maximum slices (default 8).

    Returns:
        Chart.js doughnut config with event names as labels and counts as data.
    """
    if not events:
        return {"labels": [], "datasets": []}
    top = events[:limit]
    return {
        "labels": [e["eventName"] for e in top],
        "datasets": [
            {
                "data": [e["count"] for e in top],
                "backgroundColor": list(_DIMENSION_PALETTE[: len(top)]),
            }
        ],
    }


def build_events_timeline_data(event_timeseries: list[dict]) -> dict:
    """Convert multiple event time series into a Chart.js multi-line payload.

    Targets a ``Chart('line', ...)`` with one dataset per event type, each
    drawn in a different color from ``_DIMENSION_PALETTE``.  All series share
    the same X-axis (unified timestamp labels), with missing data points
    filled as zero.

    The unified label set is built by collecting all unique timestamps across
    all series, then sorting them chronologically.

    Args:
        event_timeseries: List of per-event series, each shaped
            ``{"name": str, "data": [{"time": str, "count": int}, ...]}``.
            Typically the top 5 events from ``get_events_data``.

    Returns:
        ``{"labels": [<sorted timestamps>], "datasets": [...]}``, one dataset
        per event with ``borderColor`` and a 10%-opacity ``backgroundColor``.
    """
    if not event_timeseries:
        return {"labels": [], "datasets": []}
    all_times: set[str] = set()
    for series in event_timeseries:
        for point in series["data"]:
            all_times.add(point["time"])
    labels = sorted(all_times)
    colors = list(_DIMENSION_PALETTE)
    datasets = []
    for i, series in enumerate(event_timeseries):
        time_map = {p["time"]: p["count"] for p in series["data"]}
        datasets.append(
            {
                "label": series["name"],
                "data": [time_map.get(t, 0) for t in labels],
                "borderColor": colors[i % len(colors)],
                "backgroundColor": colors[i % len(colors)]
                .replace("rgb(", "rgba(")
                .replace(")", ", 0.1)"),
            }
        )
    return {"labels": labels, "datasets": datasets}


def build_events_bar_chart_data(events: list[dict], limit: int = 10) -> dict:
    """Convert event-metric rows to a Chart.js vertical bar payload.

    Targets a ``Chart('bar', ...)`` with purple-filled bars showing event
    counts.  Used as an alternative to the pie chart on the Events page when
    the user toggles to bar-chart mode.

    Args:
        events: Rows ``[{"eventName": str, "count": int}, ...]`` from
            ``get_event_metrics``.
        limit: Maximum events to include (default 10).

    Returns:
        Chart.js bar config with event names as labels and counts as data,
        using purple ``rgba(168, 85, 247, 0.7)`` fill.
    """
    if not events:
        return {"labels": [], "datasets": []}
    top = events[:limit]
    return {
        "labels": [e["eventName"] for e in top],
        "datasets": [
            {
                "label": "Count",
                "data": [e["count"] for e in top],
                "backgroundColor": "rgba(168, 85, 247, 0.7)",
            }
        ],
    }


_COUNTRY_CENTERS: dict[str, tuple[float, float]] = {
    "AF": (33.9, 67.7),
    "AL": (41.2, 20.2),
    "DZ": (28.0, 1.7),
    "AR": (-38.4, -63.6),
    "AU": (-25.3, 133.8),
    "AT": (47.5, 14.6),
    "BD": (23.7, 90.4),
    "BE": (50.5, 4.5),
    "BR": (-14.2, -51.9),
    "BG": (42.7, 25.5),
    "CA": (56.1, -106.3),
    "CL": (-35.7, -71.5),
    "CN": (35.9, 104.2),
    "CO": (4.6, -74.3),
    "HR": (45.1, 15.2),
    "CZ": (49.8, 15.5),
    "DK": (56.3, 9.5),
    "EG": (26.8, 30.8),
    "FI": (61.9, 25.7),
    "FR": (46.2, 2.2),
    "DE": (51.2, 10.4),
    "GR": (39.1, 21.8),
    "HK": (22.4, 114.1),
    "HU": (47.2, 19.5),
    "IN": (20.6, 78.9),
    "ID": (-0.8, 113.9),
    "IE": (53.4, -8.2),
    "IL": (31.0, 34.9),
    "IT": (41.9, 12.6),
    "JP": (36.2, 138.3),
    "KR": (35.9, 127.8),
    "MY": (4.2, 101.9),
    "MX": (23.6, -102.6),
    "NL": (52.1, 5.3),
    "NZ": (-40.9, 174.9),
    "NG": (9.1, 8.7),
    "NO": (60.5, 8.5),
    "PK": (30.4, 69.3),
    "PE": (-9.2, -75.0),
    "PH": (12.9, 121.8),
    "PL": (51.9, 19.1),
    "PT": (39.4, -8.2),
    "RO": (45.9, 25.0),
    "RU": (61.5, 105.3),
    "SA": (23.9, 45.1),
    "SG": (1.4, 103.8),
    "ZA": (-30.6, 22.9),
    "ES": (40.5, -3.7),
    "SE": (60.1, 18.6),
    "CH": (46.8, 8.2),
    "TW": (23.7, 121.0),
    "TH": (15.9, 100.9),
    "TR": (38.9, 35.2),
    "UA": (48.4, 31.2),
    "AE": (23.4, 53.8),
    "GB": (55.4, -3.4),
    "US": (37.1, -95.7),
    "VN": (14.1, 108.3),
}


def build_geo_bubble_data(geo: list[dict]) -> list[dict]:
    """Convert geo-metric rows into Leaflet bubble-map data points.

    Looks up each country's approximate center coordinates from the
    ``_COUNTRY_CENTERS`` lookup table and builds a list of
    ``{country, visitors, lat, lng}`` dicts that the Leaflet map layer
    renders as proportionally-sized circles.

    Countries not present in ``_COUNTRY_CENTERS`` are silently skipped.

    Args:
        geo: Rows ``[{"country": str, "visitors": int}, ...]`` from
            ``get_geo_metrics``.

    Returns:
        ``[{"country": str, "visitors": int, "lat": float, "lng": float}, ...]``
        -- only countries with known center coordinates are included.
    """
    result = []
    for g in geo:
        code = g.get("country", "")
        if code in _COUNTRY_CENTERS:
            lat, lng = _COUNTRY_CENTERS[code]
            result.append(
                {
                    "country": code,
                    "pageviews": g.get("pageviews", g.get("visitors", 0)),
                    "lat": lat,
                    "lng": lng,
                }
            )
    return result




def build_geo_duration_bar_data(geo: list[dict], limit: int = 10) -> dict:
    """Convert geo-metric rows to a Chart.js bar payload showing avg duration by country."""
    if not geo:
        return {"labels": [], "datasets": []}
    top = geo[:limit]
    return {
        "labels": [g["country"] for g in top],
        "datasets": [
            {
                "label": "Avg Duration (s)",
                "data": [round(g["avgDuration"]) for g in top],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_duration_by_page_chart_data(pages: list[dict], limit: int = 10) -> dict:
    """Convert duration-by-page rows to a Chart.js horizontal bar payload.

    Targets a ``Chart('bar', ...)`` (rendered horizontally via ``indexAxis: 'y'``
    in the template) with indigo-filled bars showing average session duration
    per page in seconds.

    Args:
        pages: Rows ``[{"urlPath": str, "avgDuration": float}, ...]`` from
            ``get_duration_by_page``.
        limit: Maximum pages to include (default 10).

    Returns:
        Chart.js bar config with URL paths as labels and average duration
        values as data.
    """
    if not pages:
        return {"labels": [], "datasets": []}
    top = pages[:limit]
    return {
        "labels": [p["urlPath"] for p in top],
        "datasets": [
            {
                "label": "Avg Duration (s)",
                "data": [p["avgDuration"] for p in top],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_bounce_by_source_chart_data(sources: list[dict], limit: int = 10) -> dict:
    """Convert bounce-rate-by-source rows to a Chart.js bar payload with conditional colors.

    Targets a ``Chart('bar', ...)`` where each bar is color-coded by severity:
    red for bounce rates > 60%, yellow for 40-60%, and green for < 40%.
    This traffic-light scheme helps users quickly spot problematic referrers.

    Args:
        sources: Rows ``[{"referrerDomain": str, "bounceRate": float}, ...]``
            from ``get_bounce_rate_by_source``.
        limit: Maximum sources to include (default 10).

    Returns:
        Chart.js bar config with per-bar conditional ``backgroundColor`` array.
    """
    if not sources:
        return {"labels": [], "datasets": []}
    top = sources[:limit]
    return {
        "labels": [s["referrerDomain"] for s in top],
        "datasets": [
            {
                "label": "Bounce Rate %",
                "data": [s["bounceRate"] for s in top],
                "backgroundColor": [
                    "rgba(239, 68, 68, 0.7)"
                    if s["bounceRate"] > 60
                    else "rgba(234, 179, 8, 0.7)"
                    if s["bounceRate"] > 40
                    else "rgba(34, 197, 94, 0.7)"
                    for s in top
                ],
            }
        ],
    }


def build_conversion_chart_data(conversions: list[dict]) -> dict:
    """Convert cross-section conversion flows to a Chart.js grouped bar payload.

    Targets a ``Chart('bar', ...)`` with two dataset groups per entry section:
    one for cross-section navigation (indigo) and one for event triggers
    (yellow).  Shows the top 5 entry sections and their downstream activity.

    The session counts for each group are computed by summing over the nested
    ``destinations`` and ``events`` lists within each conversion row.

    Args:
        conversions: Rows ``[{"entry": str, "destinations": [...],
            "events": [...]}, ...]`` from ``get_section_conversions``.

    Returns:
        Chart.js grouped-bar config with two datasets (Cross-section, Events).
    """
    if not conversions:
        return {"labels": [], "datasets": []}
    labels = []
    sections_data = []
    events_data = []
    for c in conversions[:5]:
        labels.append(c["entry"])
        sections_data.append(sum(d["sessions"] for d in c.get("destinations", [])))
        events_data.append(sum(e["sessions"] for e in c.get("events", [])))
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Cross-section",
                "data": sections_data,
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            },
            {"label": "Events", "data": events_data, "backgroundColor": "rgba(234, 179, 8, 0.7)"},
        ],
    }


def build_entry_exit_chart_data(
    entry_pages: list[dict], exit_pages: list[dict], limit: int = 8
) -> dict:
    """Convert entry and exit page data into a Chart.js grouped bar payload.

    Targets a ``Chart('bar', ...)`` with two datasets: green bars for entries
    and red bars for exits.  Pages from both lists are merged by URL path,
    then sorted by total (entries + exits) to show the most significant pages.

    The merge ensures that a page appearing in the entry list but not the exit
    list (or vice versa) still gets a zero value for the missing dimension.

    Args:
        entry_pages: Rows ``[{"urlPath": str, "entries": int}, ...]``.
        exit_pages: Rows ``[{"urlPath": str, "exits": int}, ...]``.
        limit: Maximum pages to include after merging (default 8).

    Returns:
        Chart.js grouped-bar config with two datasets (Entries in green,
        Exits in red), labels being the URL paths.
    """
    if not entry_pages and not exit_pages:
        return {"labels": [], "datasets": []}
    all_pages = {}
    for p in entry_pages[:limit]:
        all_pages.setdefault(p["urlPath"], {"entries": 0, "exits": 0})["entries"] = p["entries"]
    for p in exit_pages[:limit]:
        all_pages.setdefault(p["urlPath"], {"entries": 0, "exits": 0})["exits"] = p["exits"]
    sorted_pages = sorted(
        all_pages.items(), key=lambda x: x[1]["entries"] + x[1]["exits"], reverse=True
    )[:limit]
    return {
        "labels": [p[0] for p in sorted_pages],
        "datasets": [
            {
                "label": "Entries",
                "data": [p[1]["entries"] for p in sorted_pages],
                "backgroundColor": "rgba(34, 197, 94, 0.7)",
            },
            {
                "label": "Exits",
                "data": [p[1]["exits"] for p in sorted_pages],
                "backgroundColor": "rgba(239, 68, 68, 0.7)",
            },
        ],
    }


def build_utm_bar_chart_data(utm: list[dict], limit: int = 10) -> dict:
    """Convert UTM parameter rows to a Chart.js vertical bar payload.

    Targets a ``Chart('bar', ...)`` with purple-filled bars.  The label for
    each bar is taken from ``utmSource`` if present, falling back to
    ``value`` (which covers utm_medium and utm_campaign rows that use a
    different key name).

    Args:
        utm: Rows ``[{"utmSource"|"value": str, "visitors": int}, ...]``
            from ``get_utm_metrics``.
        limit: Maximum entries to include (default 10).

    Returns:
        Chart.js bar config with UTM values as labels and visitor counts
        as data, using purple ``rgba(168, 85, 247, 0.7)`` fill.
    """
    if not utm:
        return {"labels": [], "datasets": []}
    top = utm[:limit]
    return {
        "labels": [u.get("utmSource") or u.get("value", "—") for u in top],
        "datasets": [
            {
                "label": "Visitors",
                "data": [u["visitors"] for u in top],
                "backgroundColor": "rgba(168, 85, 247, 0.7)",
            }
        ],
    }


def build_generic_pie_data(
    items: list[dict], label_key: str, value_key: str, limit: int = 8
) -> dict:
    """Convert any label/value rows to a Chart.js doughnut payload.

    A generic builder for cases where the caller specifies which dict keys
    hold the label and numeric value.  Uses the ``_DIMENSION_PALETTE`` color
    cycle for slice colors.

    Args:
        items: Rows ``[{label_key: str, value_key: int|float}, ...]``.
        label_key: Dict key containing the display label (e.g. ``"value"``).
        value_key: Dict key containing the numeric value (e.g. ``"visitors"``).
        limit: Maximum slices to include (default 8).

    Returns:
        Chart.js doughnut config with labels and a single dataset.
    """
    if not items:
        return {"labels": [], "datasets": []}
    top = items[:limit]
    return {
        "labels": [i[label_key] for i in top],
        "datasets": [
            {
                "data": [i[value_key] for i in top],
                "backgroundColor": list(_DIMENSION_PALETTE[: len(top)]),
            }
        ],
    }


def build_session_duration_chart_data(sessions: list[dict]) -> dict:
    """Convert a list of sessions into a duration-distribution bar chart payload.

    Targets a ``Chart('bar', ...)`` that shows how many sessions fall into
    each of five fixed duration buckets: 0-10s, 10-30s, 30-60s, 1-5m, 5m+.
    Unlike ``build_distribution_chart_data`` (which uses pre-computed buckets
    from the query engine), this function computes buckets client-side from
    raw session rows.

    Args:
        sessions: Rows ``[{"duration": int | None}, ...]`` from
            ``get_session_list``.  Missing or ``None`` durations are treated
            as zero.

    Returns:
        Chart.js bar config with 5 bucket labels and session counts as data,
        using indigo ``rgba(99, 102, 241, 0.7)`` fill.
    """
    buckets = {"0-10s": 0, "10-30s": 0, "30-60s": 0, "1-5m": 0, "5m+": 0}
    for s in sessions:
        d = s.get("duration", 0) or 0
        if d <= 10:
            buckets["0-10s"] += 1
        elif d <= 30:
            buckets["10-30s"] += 1
        elif d <= 60:
            buckets["30-60s"] += 1
        elif d <= 300:
            buckets["1-5m"] += 1
        else:
            buckets["5m+"] += 1
    return {
        "labels": list(buckets.keys()),
        "datasets": [
            {
                "label": "Sessions",
                "data": list(buckets.values()),
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_comparison_chart_data(current_ts: list[dict], previous_ts: list[dict]) -> dict:
    """Convert current and previous time series into an overlaid Chart.js line payload.

    Targets a ``Chart('line', ...)`` with two datasets: the current period
    as a solid indigo line and the previous period as a dashed gray line.
    If the previous series is shorter than the current one, it is zero-padded;
    if longer, it is truncated to match.

    Args:
        current_ts: Current-period rows ``[{"time": str, "pageviews": int}, ...]``.
        previous_ts: Previous-period rows (same shape).  May be empty.

    Returns:
        Chart.js line config with one or two datasets.  The previous dataset
        includes ``borderDash: [5, 5]`` for a dashed-line appearance.
    """
    if not current_ts:
        return {"labels": [], "datasets": []}
    labels = [p["time"] for p in current_ts]
    datasets = [
        {
            "label": "Current",
            "data": [p["pageviews"] for p in current_ts],
            "borderColor": _TS_PAGEVIEWS_BORDER,
            "backgroundColor": _TS_PAGEVIEWS_BG,
        },
    ]
    if previous_ts:
        prev_data = [p["pageviews"] for p in previous_ts]
        if len(prev_data) < len(labels):
            prev_data.extend([0] * (len(labels) - len(prev_data)))
        datasets.append(
            {
                "label": "Previous",
                "data": prev_data[: len(labels)],
                "borderColor": "rgb(107, 114, 128)",
                "backgroundColor": "rgba(107, 114, 128, 0.1)",
                "borderDash": [5, 5],
            }
        )
    return {"labels": labels, "datasets": datasets}


def build_retention_curve_data(cohorts: list[dict]) -> dict:
    """Convert cohort retention data into a Chart.js average-retention line payload.

    Targets a ``Chart('line', ...)`` that shows the average retention percentage
    across all cohorts for each period offset (P0, P1, P2, ...).  For each
    period index, the function averages all non-zero cohort values, ignoring
    cohorts that have no data for that period yet (triangular matrix).

    Args:
        cohorts: Rows ``[{"cohort": str, "visitors": int,
            "periods": [float, ...]}, ...]`` from ``get_retention``.

    Returns:
        Chart.js line config with period labels (``P0``, ``P1``, ...) and a
        single "Avg Retention %" dataset in indigo.
    """
    if not cohorts or not cohorts[0].get("periods"):
        return {"labels": [], "datasets": []}
    num_periods = len(cohorts[0]["periods"])
    labels = [f"P{i}" for i in range(num_periods)]
    avgs = []
    for i in range(num_periods):
        vals = [c["periods"][i] for c in cohorts if i < len(c["periods"]) and c["periods"][i] > 0]
        avgs.append(round(sum(vals) / len(vals), 1) if vals else 0)
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Avg Retention %",
                "data": avgs,
                "borderColor": _TS_PAGEVIEWS_BORDER,
                "backgroundColor": _TS_PAGEVIEWS_BG,
            }
        ],
    }


def build_revenue_country_chart_data(countries: list[dict], limit: int = 10) -> dict:
    """Convert revenue-by-country rows to a Chart.js horizontal-bar payload.

    Args:
        countries: Rows ``[{"country": str, "revenue": float}, ...]``.
        limit: Maximum countries to display.

    Returns:
        Chart.js bar config with country labels and revenue values.
    """
    if not countries:
        return {"labels": [], "datasets": []}
    top = countries[:limit]
    return {
        "labels": [c["country"] for c in top],
        "datasets": [
            {
                "label": "Revenue",
                "data": [c["revenue"] for c in top],
                "backgroundColor": "rgba(34, 197, 94, 0.7)",
            }
        ],
    }


def build_event_timeseries_chart_data(event_name: str, ts: list[dict]) -> dict:
    """Convert a single-event time series to a Chart.js line payload.

    Args:
        event_name: Display label for the dataset.
        ts: Rows ``[{"time": str, "count": int}, ...]``.

    Returns:
        Chart.js line config with timestamps as labels.
    """
    if not ts:
        return {"labels": [], "datasets": []}
    return {
        "labels": [p["time"] for p in ts],
        "datasets": [
            {
                "label": event_name,
                "data": [p["count"] for p in ts],
                "borderColor": _TS_PAGEVIEWS_BORDER,
                "backgroundColor": _TS_PAGEVIEWS_BG,
            }
        ],
    }


def build_revenue_timeseries_chart_data(time_series: list[dict]) -> dict:
    """Convert revenue time series to a Chart.js line payload.

    Args:
        time_series: Rows ``[{"time": str, "revenue": float}, ...]``.

    Returns:
        Chart.js line config with green revenue line.
    """
    if not time_series:
        return {"labels": [], "datasets": []}
    return {
        "labels": [p["time"] for p in time_series],
        "datasets": [
            {
                "label": "Revenue",
                "data": [p["revenue"] for p in time_series],
                "borderColor": "rgb(34, 197, 94)",
                "backgroundColor": "rgba(34, 197, 94, 0.1)",
            }
        ],
    }


def build_revenue_event_chart_data(by_event: list[dict]) -> dict:
    """Convert revenue-by-event rows to a Chart.js bar payload.

    Args:
        by_event: Rows ``[{"eventName": str, "revenue": float}, ...]``.

    Returns:
        Chart.js bar config with event names as labels.
    """
    if not by_event:
        return {"labels": [], "datasets": []}
    return {
        "labels": [e["eventName"] for e in by_event],
        "datasets": [
            {
                "label": "Revenue",
                "data": [e["revenue"] for e in by_event],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_distribution_chart_data(distribution: list[dict]) -> dict:
    """Convert duration-distribution buckets to a Chart.js bar payload.

    Args:
        distribution: Rows ``[{"bucket": str, "visits": int}, ...]``.

    Returns:
        Chart.js bar config with bucket labels and visit counts.
    """
    if not distribution:
        return {"labels": [], "datasets": []}
    return {
        "labels": [d["bucket"] for d in distribution],
        "datasets": [
            {
                "label": "Visits",
                "data": [d["visits"] for d in distribution],
                "backgroundColor": "rgba(99, 102, 241, 0.7)",
            }
        ],
    }


def build_bounce_page_chart_data(bounce_by_page: list[dict]) -> dict:
    """Convert bounce-rate-by-page rows to a Chart.js bar payload.

    Args:
        bounce_by_page: Rows ``[{"urlPath": str, "bounceRate": float}, ...]``.

    Returns:
        Chart.js bar config with URL paths and red bounce-rate bars.
    """
    if not bounce_by_page:
        return {"labels": [], "datasets": []}
    return {
        "labels": [b["urlPath"] for b in bounce_by_page],
        "datasets": [
            {
                "label": "Bounce Rate %",
                "data": [b["bounceRate"] for b in bounce_by_page],
                "backgroundColor": "rgba(239, 68, 68, 0.7)",
            }
        ],
    }


def build_sankey_data(
    journeys: list[dict],
    max_nodes_per_step: int = 8,
) -> dict:
    """Convert journey paths to D3-sankey node/link format.

    Implements a multi-pass algorithm to transform raw navigation paths into
    the strict DAG (directed acyclic graph) structure that d3-sankey requires:

    **Pass 1 -- Step-based node IDs and raw links:**
    Each page/section name is prefixed with its step index (e.g. ``"0:/blog"``,
    ``"1:/docs"``) so that the same page appearing at different journey steps
    becomes distinct nodes.  This prevents cycles, which would cause d3-sankey
    to crash or produce infinite loops.  Raw (source, target, count) link
    triples are accumulated.

    **Pass 2 -- Overflow bucketing:**
    For each step column, nodes are ranked by total traffic.  Only the top
    ``max_nodes_per_step`` are kept; the rest are folded into a single
    ``"Other (N)"`` bucket (where N is the number of collapsed nodes).  A
    remap dict records which original node IDs map to the overflow bucket.

    **Pass 3 -- Link merging and self-loop removal:**
    Raw links are remapped through the overflow dict, self-loops (where
    source == target after remapping) are dropped, and duplicate links
    between the same node pair are summed.  Finally, sequential integer IDs
    are assigned to nodes.

    Args:
        journeys: Rows ``[{"path": list[str], "count": int}, ...]`` from
            ``get_journeys`` or ``get_section_journeys``.
        max_nodes_per_step: Keep at most this many nodes per step column;
            the rest are collapsed into an "Other" bucket.  Default is 8.

    Returns:
        ``{"nodes": [{"name": str, "step": int}, ...],
        "links": [{"source": int, "target": int, "value": int}, ...],
        "steps": int}`` ready for the D3-sankey layout in
        ``static/js/sankey.js``.  Returns ``{"nodes": [], "links": []}``
        if input is empty.
    """
    # --- Pass 1: Build step-prefixed node IDs and accumulate raw links ---
    step_totals: dict[str, int] = {}  # "step:name" -> total traffic through this node
    raw_links: list[tuple[str, str, int]] = []  # (src_key, tgt_key, count) triples

    for journey in journeys:
        path = journey["path"]
        count = journey["count"]
        for i in range(len(path) - 1):
            src_name, tgt_name = path[i], path[i + 1]
            # Prefix with step index to prevent cycles (e.g. "0:/home" != "2:/home")
            src_key = f"{i}:{src_name}"
            tgt_key = f"{i + 1}:{tgt_name}"
            step_totals[src_key] = step_totals.get(src_key, 0) + count
            step_totals[tgt_key] = step_totals.get(tgt_key, 0) + count
            raw_links.append((src_key, tgt_key, count))

    if not raw_links:
        return {"nodes": [], "links": []}

    # --- Pass 2: Overflow bucketing -- collapse low-traffic nodes per step ---
    # Group nodes by their step column
    steps: dict[int, list[tuple[str, int]]] = {}
    for key, total in step_totals.items():
        step = int(key.split(":", 1)[0])
        steps.setdefault(step, []).append((key, total))

    # For each step, keep top N nodes and remap the rest to "Other (M)"
    remap: dict[str, str] = {}
    for step_idx, entries in steps.items():
        entries.sort(key=lambda x: x[1], reverse=True)  # highest traffic first
        keep = {e[0] for e in entries[:max_nodes_per_step]}
        overflow = [e for e in entries if e[0] not in keep]
        if overflow:
            other_key = f"{step_idx}:Other ({len(overflow)})"
            for old_key, _ in overflow:
                remap[old_key] = other_key  # redirect to the overflow bucket

    # --- Pass 3: Remap links, drop self-loops, merge duplicates ---
    node_set: dict[str, int] = {}  # "step:name" -> sequential integer ID
    merged: dict[tuple[int, int], int] = {}  # (src_id, tgt_id) -> summed count

    for src_key, tgt_key, count in raw_links:
        # Apply overflow remapping
        src_key = remap.get(src_key, src_key)
        tgt_key = remap.get(tgt_key, tgt_key)
        # Self-loops happen when both src and tgt are remapped to the same
        # overflow bucket -- d3-sankey cannot handle these, so skip them
        if src_key == tgt_key:
            continue
        # Assign sequential IDs to nodes on first encounter
        if src_key not in node_set:
            node_set[src_key] = len(node_set)
        if tgt_key not in node_set:
            node_set[tgt_key] = len(node_set)
        # Merge duplicate links (same src->tgt pair) by summing counts
        link_key = (node_set[src_key], node_set[tgt_key])
        merged[link_key] = merged.get(link_key, 0) + count

    # Build final output: strip step prefix from node names for display
    nodes = [
        {"name": key.split(":", 1)[1], "step": int(key.split(":", 1)[0])}
        for key, _ in sorted(node_set.items(), key=lambda x: x[1])
    ]
    merged_links = [{"source": s, "target": t, "value": v} for (s, t), v in merged.items()]
    max_step = max((n["step"] for n in nodes), default=0)
    return {"nodes": nodes, "links": merged_links, "steps": max_step + 1}
