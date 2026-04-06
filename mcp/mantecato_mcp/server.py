from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mantecato_core.helpers import (
    compute_derived_stats,
    parse_date_args,
    parse_filter_args,
    resolve_granularity_arg,
    resolve_site_id,
    resolve_user_id,
)
from mantecato_core.database import close_pool, create_pool, get_pool

server = Server("mantecato")


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {message}")]


# Schema building blocks
_SITE = {"type": "string", "description": "Site name, domain, or UUID"}
_PERIOD = {
    "type": "string",
    "description": "Date range preset (e.g. 7d, 30d, 90d, this_month)",
    "default": "30d",
}
_START = {
    "type": "string",
    "description": "Custom start date (ISO 8601). Overrides period.",
}
_END = {"type": "string", "description": "Custom end date (ISO 8601)"}
_FILTER = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Filters as column:operator:value strings",
    "default": [],
}
_GRANULARITY = {
    "type": "string",
    "description": "Time granularity: auto, minute, hour, day, week, month",
    "default": "auto",
}
_LIMIT = {"type": "number", "description": "Maximum rows to return", "default": 20}


def _std_props(**extra) -> dict:
    """Standard properties: site + period + start + end + filter."""
    props = {
        "site": _SITE,
        "period": _PERIOD,
        "start": _START,
        "end": _END,
        "filter": _FILTER,
    }
    props.update(extra)
    return props


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    s = {"type": "object", "properties": properties}
    if required:
        s["required"] = required
    return s


def _tool(
    name: str, desc: str, properties: dict, required: list[str] | None = None
) -> Tool:
    return Tool(name=name, description=desc, inputSchema=_schema(properties, required))


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── Core ──
        _tool("list_sites", "List all tracked sites", {}),
        _tool(
            "get_stats",
            "Get overview stats: pageviews, visitors, visits, bounce rate, avg duration",
            _std_props(),
            ["site"],
        ),
        _tool(
            "get_timeseries",
            "Get pageview and visitor time series",
            _std_props(granularity=_GRANULARITY),
            ["site"],
        ),
        _tool(
            "get_comparison",
            "Compare current vs previous period",
            _std_props(
                mode={
                    "type": "string",
                    "enum": ["previous_period", "previous_year"],
                    "default": "previous_period",
                    "description": "Comparison mode",
                }
            ),
            ["site"],
        ),
        # ── Pages ──
        _tool(
            "get_pages",
            "Get page analytics: views, time-on-page, bounce rate",
            _std_props(
                limit=_LIMIT,
                mode={
                    "type": "string",
                    "enum": ["path", "slug"],
                    "default": "path",
                    "description": "Page URL mode",
                },
            ),
            ["site"],
        ),
        _tool(
            "get_page_detail",
            "Get detailed page info: referrers, next pages, time distribution",
            {
                "site": _SITE,
                "url": {"type": "string", "description": "Page URL path"},
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "granularity": _GRANULARITY,
                "limit": _LIMIT,
            },
            ["site", "url"],
        ),
        _tool(
            "get_top_pages",
            "Get top pages by visitors",
            _std_props(limit=_LIMIT),
            ["site"],
        ),
        # ── Sources ──
        _tool(
            "get_sources",
            "Get traffic sources with bounce rate and duration",
            _std_props(limit=_LIMIT),
            ["site"],
        ),
        _tool(
            "get_referrer_pages",
            "Get pages a referrer drives traffic to",
            {
                "site": _SITE,
                "referrer": {"type": "string", "description": "Referrer domain"},
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "limit": _LIMIT,
                "filter": _FILTER,
            },
            ["site", "referrer"],
        ),
        _tool(
            "get_channels", "Get auto-grouped traffic channels", _std_props(), ["site"]
        ),
        _tool(
            "get_utm",
            "Get UTM parameter breakdown",
            _std_props(
                dimension={
                    "type": "string",
                    "enum": [
                        "utm_source",
                        "utm_medium",
                        "utm_campaign",
                        "utm_content",
                        "utm_term",
                    ],
                    "default": "utm_source",
                    "description": "UTM dimension",
                },
                limit=_LIMIT,
            ),
            ["site"],
        ),
        _tool(
            "get_click_ids",
            "Get click ID analysis (gclid, fbclid, etc.)",
            _std_props(),
            ["site"],
        ),
        _tool(
            "get_hostnames",
            "Get hostname breakdown",
            _std_props(limit=_LIMIT),
            ["site"],
        ),
        _tool(
            "get_top_referrers",
            "Get top referrers by visitors",
            _std_props(limit=_LIMIT),
            ["site"],
        ),
        # ── Events ──
        _tool(
            "get_events", "Get custom event metrics", _std_props(limit=_LIMIT), ["site"]
        ),
        _tool(
            "get_event_detail",
            "Get event time series and property breakdown",
            {
                "site": _SITE,
                "event": {"type": "string", "description": "Event name"},
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "granularity": _GRANULARITY,
                "limit": _LIMIT,
                "filter": _FILTER,
            },
            ["site", "event"],
        ),
        _tool(
            "get_top_events",
            "Get top events by count",
            _std_props(limit=_LIMIT),
            ["site"],
        ),
        # ── Sessions ──
        _tool(
            "get_sessions",
            "Get session list with location, device, engagement",
            _std_props(
                limit=_LIMIT,
                visitedPage={
                    "type": "string",
                    "description": "Filter sessions that visited this page",
                },
                triggeredEvent={
                    "type": "string",
                    "description": "Filter sessions that triggered this event",
                },
            ),
            ["site"],
        ),
        _tool(
            "get_session_activity",
            "Get full event replay for a session",
            {
                "site": _SITE,
                "sessionId": {"type": "string", "description": "Session UUID"},
            },
            ["site", "sessionId"],
        ),
        # ── Devices ──
        _tool(
            "get_devices",
            "Get device breakdown by dimension",
            _std_props(
                dimension={
                    "type": "string",
                    "enum": ["browser", "os", "device", "screen", "language"],
                    "default": "device",
                    "description": "Breakdown dimension",
                },
                limit=_LIMIT,
            ),
            ["site"],
        ),
        # ── Geo ──
        _tool(
            "get_geo",
            "Get geographic breakdown",
            {
                "site": _SITE,
                "level": {
                    "type": "string",
                    "enum": ["country", "region", "city"],
                    "default": "country",
                    "description": "Geographic level",
                },
                "country": {
                    "type": "string",
                    "description": "Country code for region/city drill-down",
                },
                "region": {
                    "type": "string",
                    "description": "Region for city drill-down",
                },
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "limit": _LIMIT,
                "filter": _FILTER,
            },
            ["site"],
        ),
        # ── Realtime ──
        _tool("get_realtime", "Get live active visitors", {"site": _SITE}, ["site"]),
        # ── Retention ──
        _tool(
            "get_retention",
            "Get cohort retention analysis",
            _std_props(
                granularity={
                    "type": "string",
                    "enum": ["week", "month"],
                    "default": "week",
                    "description": "Retention granularity",
                }
            ),
            ["site"],
        ),
        # ── Funnel ──
        _tool(
            "run_funnel",
            "Run a conversion funnel analysis",
            {
                "site": _SITE,
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["url", "event"]},
                            "value": {"type": "string"},
                        },
                        "required": ["type", "value"],
                    },
                    "description": "Funnel steps",
                },
                "windowMinutes": {
                    "type": "number",
                    "description": "Window in minutes",
                    "default": 60,
                },
                "period": _PERIOD,
                "start": _START,
                "end": _END,
            },
            ["site", "steps"],
        ),
        # ── Journeys ──
        _tool(
            "get_journeys",
            "Get user journey paths",
            {
                "site": _SITE,
                "pathLength": {
                    "type": "number",
                    "description": "Path length",
                    "default": 3,
                },
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "limit": _LIMIT,
            },
            ["site"],
        ),
        # ── Revenue ──
        _tool(
            "get_revenue",
            "Get revenue analytics",
            {
                "site": _SITE,
                "view": {
                    "type": "string",
                    "enum": ["summary", "timeseries", "by-event", "by-country"],
                    "default": "summary",
                    "description": "Revenue view",
                },
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "granularity": _GRANULARITY,
                "limit": _LIMIT,
            },
            ["site"],
        ),
        # ── Engagement ──
        _tool(
            "get_engagement",
            "Get engagement analytics: duration distribution, percentiles, bounce rates",
            _std_props(
                view={
                    "type": "string",
                    "enum": [
                        "distribution",
                        "percentiles",
                        "by-page",
                        "bounce-by-page",
                        "bounce-by-source",
                    ],
                    "default": "percentiles",
                    "description": "Engagement view",
                },
                limit=_LIMIT,
            ),
            ["site"],
        ),
        # ── Filter Values ──
        _tool(
            "get_filter_values",
            "Get available filter values for a column",
            {
                "site": _SITE,
                "column": {"type": "string", "description": "Column name"},
                "period": _PERIOD,
                "start": _START,
                "end": _END,
                "search": {"type": "string", "description": "Search term"},
                "limit": {
                    "type": "number",
                    "description": "Maximum values to return",
                    "default": 50,
                },
            },
            ["site", "column"],
        ),
        # ── CRUD: Annotations ──
        _tool(
            "list_annotations",
            "List annotations for a site",
            {"site": _SITE, "period": _PERIOD, "start": _START, "end": _END},
            ["site"],
        ),
        _tool(
            "create_annotation",
            "Create an annotation",
            {
                "site": _SITE,
                "title": {"type": "string"},
                "date": {"type": "string"},
                "description": {"type": "string", "default": ""},
                "color": {
                    "type": "string",
                    "enum": ["blue", "green", "red", "amber", "purple"],
                    "default": "blue",
                },
            },
            ["site", "title", "date"],
        ),
        _tool(
            "delete_annotation",
            "Delete an annotation",
            {"id": {"type": "string", "description": "Annotation ID"}},
            ["id"],
        ),
        # ── CRUD: Saved Views ──
        _tool(
            "list_saved_views", "List saved views for a site", {"site": _SITE}, ["site"]
        ),
        _tool(
            "get_saved_view",
            "Get a saved view",
            {"id": {"type": "string", "description": "Saved view ID"}},
            ["id"],
        ),
        _tool(
            "create_saved_view",
            "Create a saved view",
            {
                "site": _SITE,
                "name": {"type": "string"},
                "description": {"type": "string", "default": ""},
                "config": {
                    "type": "object",
                    "properties": {
                        "preset": {"type": "string"},
                        "granularity": {"type": "string", "default": "auto"},
                        "filters": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "column": {"type": "string"},
                                    "operator": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                                "required": ["column", "operator", "value"],
                            },
                            "default": [],
                        },
                        "page": {"type": "string"},
                    },
                },
            },
            ["site", "name", "config"],
        ),
        _tool(
            "delete_saved_view",
            "Delete a saved view",
            {"id": {"type": "string", "description": "Saved view ID"}},
            ["id"],
        ),
        # ── CRUD: Dashboards ──
        _tool(
            "list_dashboards",
            "List dashboards",
            {
                "site": {
                    "type": "string",
                    "description": "Site (optional, returns all if omitted)",
                }
            },
        ),
        _tool(
            "get_dashboard",
            "Get a dashboard",
            {"id": {"type": "string", "description": "Dashboard ID"}},
            ["id"],
        ),
        _tool(
            "delete_dashboard",
            "Delete a dashboard",
            {"id": {"type": "string", "description": "Dashboard ID"}},
            ["id"],
        ),
        # ── CRUD: Scheduled Exports ──
        _tool("list_scheduled_exports", "List scheduled exports", {}),
        _tool(
            "get_scheduled_export",
            "Get a scheduled export",
            {"id": {"type": "string", "description": "Scheduled export ID"}},
            ["id"],
        ),
        _tool(
            "delete_scheduled_export",
            "Delete a scheduled export",
            {"id": {"type": "string", "description": "Scheduled export ID"}},
            ["id"],
        ),
    ]


async def _get_mcp_user_id() -> str:
    """Resolve user ID from MANTECATO_API_KEY env var for MCP context."""
    key = os.environ.get("MANTECATO_API_KEY")
    if not key:
        raise ValueError(
            "MANTECATO_API_KEY environment variable is required for this operation"
        )
    result = await resolve_user_id(key)
    return result


_REMOTE_MODE = bool(os.environ.get("MANTECATO_API_URL"))
_remote_client: Any | None = None


def _get_remote_client() -> Any:
    global _remote_client
    if _remote_client is None:
        from .remote import RemoteClient

        api_url = os.environ.get("MANTECATO_API_URL", "")
        api_key = os.environ.get("MANTECATO_API_KEY", "")
        _remote_client = RemoteClient(api_url, api_key)
    return _remote_client


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if _REMOTE_MODE:
            return await _dispatch_remote(name, arguments)
        else:
            await get_pool()
            return await _dispatch(name, arguments)
    except Exception as e:
        return _err(str(e))


async def _dispatch(name: str, args: dict[str, Any]) -> list[TextContent]:
    # ── List Sites ──────────────────────────────────────────────────
    if name == "list_sites":
        from mantecato_core.helpers import list_sites

        return _ok(await list_sites())

    # ── Stats ───────────────────────────────────────────────────────
    if name == "get_stats":
        from mantecato_core.queries.stats import get_website_stats

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        raw = await get_website_stats(site_id, dr.start_date, dr.end_date, filters)
        return _ok(compute_derived_stats(raw))

    if name == "get_timeseries":
        from mantecato_core.queries.stats import get_pageview_time_series

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        gran = resolve_granularity_arg(args.get("granularity", "auto"), dr)
        return _ok(
            await get_pageview_time_series(
                site_id, dr.start_date, dr.end_date, gran, filters
            )
        )

    if name == "get_comparison":
        from mantecato_core.date_utils import get_comparison_range
        from mantecato_core.queries.compare import get_comparison_stats

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        mode = args.get("mode", "previous_period")
        prev = get_comparison_range(dr, mode)
        return _ok(
            await get_comparison_stats(
                site_id, dr.start_date, dr.end_date, prev.start_date, prev.end_date
            )
        )

    # ── Pages ───────────────────────────────────────────────────────
    if name == "get_pages":
        from mantecato_core.queries.pageviews import get_page_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_page_metrics(
                site_id,
                dr.start_date,
                dr.end_date,
                limit=args.get("limit", 20),
                filters=filters,
                page_mode=args.get("mode", "path"),
            )
        )

    if name == "get_page_detail":
        from mantecato_core.queries.pageviews import (
            get_next_pages,
            get_page_referrers,
            get_page_time_series,
            get_time_on_page_distribution,
        )

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        url = args["url"]
        gran = resolve_granularity_arg(args.get("granularity", "auto"), dr)
        limit = args.get("limit", 20)
        referrers, next_pages, distribution, ts = await asyncio.gather(
            get_page_referrers(site_id, url, dr.start_date, dr.end_date, limit),
            get_next_pages(site_id, url, dr.start_date, dr.end_date, limit),
            get_time_on_page_distribution(site_id, url, dr.start_date, dr.end_date),
            get_page_time_series(site_id, url, dr.start_date, dr.end_date, gran),
        )
        return _ok(
            {
                "referrers": referrers,
                "next_pages": next_pages,
                "time_distribution": distribution,
                "timeseries": ts,
            }
        )

    if name == "get_top_pages":
        from mantecato_core.queries.stats import get_top_pages

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_top_pages(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    # ── Sources ─────────────────────────────────────────────────────
    if name == "get_sources":
        from mantecato_core.queries.sources import get_referrer_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_referrer_metrics(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    if name == "get_referrer_pages":
        from mantecato_core.queries.sources import get_referrer_pages as _q

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await _q(
                site_id,
                dr.start_date,
                dr.end_date,
                args["referrer"],
                args.get("limit", 20),
                filters,
            )
        )

    if name == "get_channels":
        from mantecato_core.queries.sources import get_channel_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_channel_metrics(site_id, dr.start_date, dr.end_date, filters)
        )

    if name == "get_utm":
        from mantecato_core.queries.sources import get_utm_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_utm_metrics(
                site_id,
                dr.start_date,
                dr.end_date,
                args.get("dimension", "utm_source"),
                args.get("limit", 20),
                filters,
            )
        )

    if name == "get_click_ids":
        from mantecato_core.queries.sources import get_click_id_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_click_id_metrics(site_id, dr.start_date, dr.end_date, filters)
        )

    if name == "get_hostnames":
        from mantecato_core.queries.sources import get_hostname_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_hostname_metrics(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    if name == "get_top_referrers":
        from mantecato_core.queries.stats import get_top_referrers

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_top_referrers(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    # ── Events ──────────────────────────────────────────────────────
    if name == "get_events":
        from mantecato_core.queries.events import get_event_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_event_metrics(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    if name == "get_event_detail":
        from mantecato_core.queries.events import (
            get_event_properties,
            get_event_time_series,
        )

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        gran = resolve_granularity_arg(args.get("granularity", "auto"), dr)
        event = args["event"]
        ts, props = await asyncio.gather(
            get_event_time_series(
                site_id, event, dr.start_date, dr.end_date, gran, filters
            ),
            get_event_properties(
                site_id, event, dr.start_date, dr.end_date, args.get("limit", 20)
            ),
        )
        return _ok({"timeseries": ts, "properties": props})

    if name == "get_top_events":
        from mantecato_core.queries.stats import get_top_events

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_top_events(
                site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
            )
        )

    # ── Sessions ────────────────────────────────────────────────────
    if name == "get_sessions":
        from mantecato_core.queries.sessions import get_session_list

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_session_list(
                site_id,
                dr.start_date,
                dr.end_date,
                limit=args.get("limit", 20),
                filters=filters,
                visited_page=args.get("visitedPage"),
                triggered_event=args.get("triggeredEvent"),
            )
        )

    if name == "get_session_activity":
        from mantecato_core.queries.sessions import get_session_activity

        site_id = await resolve_site_id(args["site"])
        return _ok(await get_session_activity(args["sessionId"], site_id))

    # ── Devices ─────────────────────────────────────────────────────
    if name == "get_devices":
        from mantecato_core.queries.devices import get_device_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_device_metrics(
                site_id,
                dr.start_date,
                dr.end_date,
                args.get("dimension", "device"),
                args.get("limit", 20),
                filters,
            )
        )

    # ── Geo ─────────────────────────────────────────────────────────
    if name == "get_geo":
        from mantecato_core.queries.geo import get_geo_metrics

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        return _ok(
            await get_geo_metrics(
                site_id,
                dr.start_date,
                dr.end_date,
                level=args.get("level", "country"),
                country_filter=args.get("country"),
                region_filter=args.get("region"),
                limit=args.get("limit", 20),
                filters=filters,
            )
        )

    # ── Realtime ────────────────────────────────────────────────────
    if name == "get_realtime":
        from mantecato_core.queries.realtime import (
            get_active_visitors,
            get_current_pages,
            get_recent_events,
        )

        site_id = await resolve_site_id(args["site"])
        visitors, pages, events = await asyncio.gather(
            get_active_visitors(site_id),
            get_current_pages(site_id),
            get_recent_events(site_id),
        )
        return _ok(
            {
                "active_visitors": visitors,
                "current_pages": pages,
                "recent_events": events,
            }
        )

    # ── Retention ───────────────────────────────────────────────────
    if name == "get_retention":
        from mantecato_core.queries.retention import get_retention

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        return _ok(
            await get_retention(
                site_id, dr.start_date, dr.end_date, args.get("granularity", "week")
            )
        )

    # ── Funnel ──────────────────────────────────────────────────────
    if name == "run_funnel":
        from mantecato_core.queries.funnels import get_funnel

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        steps = args["steps"]
        if len(steps) < 2:
            return _err("Funnel requires at least 2 steps")
        return _ok(
            await get_funnel(
                site_id,
                dr.start_date,
                dr.end_date,
                steps,
                args.get("windowMinutes", 60),
            )
        )

    # ── Journeys ────────────────────────────────────────────────────
    if name == "get_journeys":
        from mantecato_core.queries.journeys import get_journeys

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        return _ok(
            await get_journeys(
                site_id,
                dr.start_date,
                dr.end_date,
                args.get("pathLength", 3),
                args.get("limit", 20),
            )
        )

    # ── Revenue ─────────────────────────────────────────────────────
    if name == "get_revenue":
        from mantecato_core.queries.revenue import (
            get_revenue_by_country,
            get_revenue_by_event,
            get_revenue_summary,
            get_revenue_time_series,
        )

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        view = args.get("view", "summary")
        if view == "summary":
            return _ok(await get_revenue_summary(site_id, dr.start_date, dr.end_date))
        elif view == "timeseries":
            gran = resolve_granularity_arg(args.get("granularity", "auto"), dr)
            return _ok(
                await get_revenue_time_series(site_id, dr.start_date, dr.end_date, gran)
            )
        elif view == "by-event":
            return _ok(
                await get_revenue_by_event(
                    site_id, dr.start_date, dr.end_date, args.get("limit", 20)
                )
            )
        elif view == "by-country":
            return _ok(
                await get_revenue_by_country(
                    site_id, dr.start_date, dr.end_date, args.get("limit", 20)
                )
            )
        return _err(f"Unknown view: {view}")

    # ── Engagement ──────────────────────────────────────────────────
    if name == "get_engagement":
        from mantecato_core.queries.engagement import (
            get_bounce_rate_by_page,
            get_bounce_rate_by_source,
            get_duration_by_page,
            get_duration_distribution,
            get_duration_percentiles,
        )

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        filters = parse_filter_args(args.get("filter", []))
        view = args.get("view", "percentiles")
        if view == "distribution":
            return _ok(
                await get_duration_distribution(
                    site_id, dr.start_date, dr.end_date, filters
                )
            )
        elif view == "percentiles":
            return _ok(
                await get_duration_percentiles(
                    site_id, dr.start_date, dr.end_date, filters
                )
            )
        elif view == "by-page":
            return _ok(
                await get_duration_by_page(
                    site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
                )
            )
        elif view == "bounce-by-page":
            return _ok(
                await get_bounce_rate_by_page(
                    site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
                )
            )
        elif view == "bounce-by-source":
            return _ok(
                await get_bounce_rate_by_source(
                    site_id, dr.start_date, dr.end_date, args.get("limit", 20), filters
                )
            )
        return _err(f"Unknown view: {view}")

    # ── Filter Values ───────────────────────────────────────────────
    if name == "get_filter_values":
        from mantecato_core.queries.filter_values import get_filter_values

        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        return _ok(
            await get_filter_values(
                site_id,
                args["column"],
                dr.start_date,
                dr.end_date,
                search=args.get("search"),
                limit=args.get("limit", 50),
            )
        )

    # ── CRUD: Annotations ───────────────────────────────────────────
    if name == "list_annotations":
        from mantecato_core.queries.annotations import list_annotations

        user_id = await _get_mcp_user_id()
        site_id = await resolve_site_id(args["site"])
        dr = parse_date_args(
            args.get("period", "30d"), args.get("start"), args.get("end")
        )
        return _ok(await list_annotations(user_id, site_id, dr.start_date, dr.end_date))

    if name == "create_annotation":
        from mantecato_core.queries.annotations import create_annotation

        user_id = await _get_mcp_user_id()
        site_id = await resolve_site_id(args["site"])
        return _ok(
            await create_annotation(
                user_id,
                site_id,
                args["title"],
                args.get("description", ""),
                args["date"],
                args.get("color", "blue"),
            )
        )

    if name == "delete_annotation":
        from mantecato_core.queries.annotations import delete_annotation

        user_id = await _get_mcp_user_id()
        ok = await delete_annotation(args["id"], user_id)
        return _ok({"deleted": ok})

    # ── CRUD: Saved Views ───────────────────────────────────────────
    if name == "list_saved_views":
        from mantecato_core.queries.saved_views import list_saved_views

        user_id = await _get_mcp_user_id()
        site_id = await resolve_site_id(args["site"])
        return _ok(await list_saved_views(user_id, site_id))

    if name == "get_saved_view":
        from mantecato_core.queries.saved_views import get_saved_view

        user_id = await _get_mcp_user_id()
        data = await get_saved_view(args["id"], user_id)
        return _ok(data)

    if name == "create_saved_view":
        from mantecato_core.queries.saved_views import create_saved_view

        user_id = await _get_mcp_user_id()
        site_id = await resolve_site_id(args["site"])
        return _ok(
            await create_saved_view(
                user_id,
                site_id,
                args["name"],
                args.get("description", ""),
                args["config"],
            )
        )

    if name == "delete_saved_view":
        from mantecato_core.queries.saved_views import delete_saved_view

        user_id = await _get_mcp_user_id()
        ok = await delete_saved_view(args["id"], user_id)
        return _ok({"deleted": ok})

    # ── CRUD: Dashboards ────────────────────────────────────────────
    if name == "list_dashboards":
        from mantecato_core.queries.dashboards import list_dashboards

        user_id = await _get_mcp_user_id()
        site_id = await resolve_site_id(args["site"]) if args.get("site") else None
        return _ok(await list_dashboards(user_id, site_id))

    if name == "get_dashboard":
        from mantecato_core.queries.dashboards import get_dashboard

        user_id = await _get_mcp_user_id()
        data = await get_dashboard(args["id"], user_id)
        return _ok(data)

    if name == "delete_dashboard":
        from mantecato_core.queries.dashboards import delete_dashboard

        user_id = await _get_mcp_user_id()
        ok = await delete_dashboard(args["id"], user_id)
        return _ok({"deleted": ok})

    # ── CRUD: Scheduled Exports ─────────────────────────────────────
    if name == "list_scheduled_exports":
        from mantecato_core.queries.scheduled_exports import list_scheduled_exports

        user_id = await _get_mcp_user_id()
        return _ok(await list_scheduled_exports(user_id))

    if name == "get_scheduled_export":
        from mantecato_core.queries.scheduled_exports import get_scheduled_export

        user_id = await _get_mcp_user_id()
        data = await get_scheduled_export(args["id"], user_id)
        return _ok(data)

    if name == "delete_scheduled_export":
        from mantecato_core.queries.scheduled_exports import delete_scheduled_export

        user_id = await _get_mcp_user_id()
        ok = await delete_scheduled_export(args["id"], user_id)
        return _ok({"deleted": ok})

    return _err(f"Unknown tool: {name}")


async def _dispatch_remote(name: str, args: dict[str, Any]) -> list[TextContent]:
    client = _get_remote_client()
    site = args.get("site", "")

    tool_map = {
        "list_sites": lambda: client.list_sites(),
        "get_stats": lambda: client.get_stats(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
        ),
        "get_timeseries": lambda: client.get_timeseries(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            granularity=args.get("granularity", "auto"),
        ),
        "get_comparison": lambda: client.get_comparison(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
        ),
        "get_pages": lambda: client.get_pages(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            limit=args.get("limit", 20),
        ),
        "get_top_pages": lambda: client.get_pages(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            limit=args.get("limit", 20),
        ),
        "get_sources": lambda: client.get_sources(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            limit=args.get("limit", 20),
        ),
        "get_events": lambda: client.get_events(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            limit=args.get("limit", 20),
        ),
        "get_sessions": lambda: client.get_sessions(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
            limit=args.get("limit", 20),
        ),
        "get_devices": lambda: client.get_devices(
            site,
            device_type=args.get("type", "browser"),
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
        ),
        "get_geo": lambda: client.get_geo(
            site,
            geo_type=args.get("type", "country"),
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
            filter=args.get("filter", []),
        ),
        "get_realtime": lambda: client.get_realtime(site),
        "get_retention": lambda: client.get_retention(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "get_funnels": lambda: client.get_funnels(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "get_journeys": lambda: client.get_journeys(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "get_revenue": lambda: client.get_revenue(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "get_engagement": lambda: client.get_engagement(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "get_filter_values": lambda: client.get_filter_values(
            site,
            column=args.get("column", ""),
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "list_annotations": lambda: client.list_annotations(
            site,
            period=args.get("period", "30d"),
            start=args.get("start"),
            end=args.get("end"),
        ),
        "create_annotation": lambda: client.create_annotation(site, args),
        "delete_annotation": lambda: client.delete_annotation(site, args.get("id", "")),
        "list_saved_views": lambda: client.list_saved_views(site),
        "get_saved_view": lambda: client.get_saved_view(site, args.get("id", "")),
        "create_saved_view": lambda: client.create_saved_view(site, args),
        "delete_saved_view": lambda: client.delete_saved_view(site, args.get("id", "")),
        "list_dashboards": lambda: client.list_dashboards(site),
        "get_dashboard": lambda: client.get_dashboard(site, args.get("id", "")),
        "delete_dashboard": lambda: client.delete_dashboard(site, args.get("id", "")),
        "list_scheduled_exports": lambda: client.list_scheduled_exports(site),
        "get_scheduled_export": lambda: client.get_scheduled_export(
            site, args.get("id", "")
        ),
        "delete_scheduled_export": lambda: client.delete_scheduled_export(
            site, args.get("id", "")
        ),
    }

    handler = tool_map.get(name)
    if handler:
        result = await handler()
        return _ok(result)
    return _err(f"Unknown tool: {name}")


async def main():
    if _REMOTE_MODE:
        api_url = os.environ.get("MANTECATO_API_URL", "")
        print(f"Mantecato MCP server (remote mode: {api_url})", file=sys.stderr)
    else:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            print("Error: DATABASE_URL or MANTECATO_API_URL required", file=sys.stderr)
            sys.exit(1)
        print("Mantecato MCP server (direct DB mode)", file=sys.stderr)
        await create_pool(dsn=db_url)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
    finally:
        if not _REMOTE_MODE:
            await close_pool()


if __name__ == "__main__":
    asyncio.run(main())


def run():
    asyncio.run(main())
