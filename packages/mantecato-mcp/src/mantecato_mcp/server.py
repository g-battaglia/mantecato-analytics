"""Stdio MCP server exposing bounded, read-only Mantecato analytics tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from mantecato_mcp import __version__
from mantecato_mcp._http import get, post
from mantecato_mcp.config import ConfigError, load_config

mcp = FastMCP("Mantecato", instructions="Read-only aggregate analytics from a Mantecato API.")
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}


@mcp.tool(annotations=_READ_ONLY)
async def list_sites() -> dict[str, Any]:
    """List websites accessible to the configured Mantecato API key."""
    return await get("/api/sites/")


@mcp.tool(annotations=_READ_ONLY)
async def describe_analytics() -> dict[str, Any]:
    """Describe supported metrics, dimensions, filters, operations, and request schema."""
    capabilities, schema = await asyncio.gather(
        get("/api/v1/capabilities/"),
        get("/api/v1/schema/"),
    )
    return {"capabilities": capabilities, "schema": schema}


@mcp.tool(annotations=_READ_ONLY)
async def query_metrics(
    website_id: str,
    metrics: list[str] | None = None,
    range: str = "30d",
    start: str | None = None,
    end: str | None = None,
    timezone: str = "UTC",
    filters: list[str] | None = None,
    filter_groups: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Return numeric aggregate metrics for one site and half-open period."""
    body = _base_query(website_id, range, start, end, timezone, filters, filter_groups)
    body.update(
        {
            "operation": "totals",
            "metrics": metrics
            or [
                "pageviews",
                "daily_unique_visitors",
                "visits",
                "bounce_rate",
                "pages_per_visit",
                "human_pageviews",
                "bot_pageviews",
            ],
        }
    )
    return await post("/api/v1/analytics/query/", body)


@mcp.tool(annotations=_READ_ONLY)
async def query_timeseries(
    website_id: str,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    range: str = "30d",
    start: str | None = None,
    end: str | None = None,
    timezone: str = "UTC",
    granularity: str = "day",
    filters: list[str] | None = None,
    filter_groups: list[list[str]] | None = None,
    limit: int = 50,
    include_partial_bucket: bool = True,
) -> dict[str, Any]:
    """Return a bounded time series, optionally grouped by up to two dimensions."""
    body = _base_query(website_id, range, start, end, timezone, filters, filter_groups)
    body.update(
        {
            "operation": "timeseries",
            "metrics": metrics or ["pageviews", "daily_unique_visitors", "visits"],
            "dimensions": dimensions or [],
            "granularity": granularity,
            "limit": limit,
            "include_partial_bucket": include_partial_bucket,
        }
    )
    return await post("/api/v1/analytics/query/", body)


@mcp.tool(annotations=_READ_ONLY)
async def compare_breakdown(
    website_id: str,
    dimension: str,
    metric: str = "pageviews",
    range: str = "7d",
    start: str | None = None,
    end: str | None = None,
    previous_start: str | None = None,
    previous_end: str | None = None,
    compare: str = "previous_period",
    align: str = "full",
    timezone: str = "UTC",
    filters: list[str] | None = None,
    filter_groups: list[list[str]] | None = None,
    direction: str = "both",
    sort: str = "absolute_change",
    limit: int = 50,
) -> dict[str, Any]:
    """Compare complete dimension sets before ranking gains or losses."""
    body = _base_query(website_id, range, start, end, timezone, filters, filter_groups)
    body.update(
        {
            "dimensions": [dimension],
            "metric": metric,
            "previous_start": previous_start,
            "previous_end": previous_end,
            "compare": compare,
            "align": align,
            "direction": direction,
            "sort": sort,
            "limit": limit,
        }
    )
    return await post("/api/v1/analytics/compare/", body)


@mcp.tool(annotations=_READ_ONLY)
async def traffic_quality(
    website_id: str,
    dimension: str = "country",
    range: str = "7d",
    compare: str | None = None,
    filters: list[str] | None = None,
    filter_groups: list[list[str]] | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Return measured traffic diagnostics without inferring new bot labels."""
    body = _base_query(website_id, range, None, None, "UTC", filters, filter_groups)
    body.update({"dimensions": [dimension], "compare": compare, "limit": limit})
    return await post("/api/v1/analytics/traffic-quality/", body)


@mcp.tool(annotations=_READ_ONLY)
async def list_dimension_values(
    website_id: str,
    dimension: str,
    range: str = "30d",
    search: str | None = None,
    filters: list[str] | None = None,
    filter_groups: list[list[str]] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Discover bounded raw values for one stored analytics dimension."""
    body = _base_query(website_id, range, None, None, "UTC", filters, filter_groups)
    body.update({"dimension": dimension, "search": search, "limit": limit})
    return await post("/api/v1/analytics/dimension-values/", body)


def _base_query(
    website_id: str,
    range: str,
    start: str | None,
    end: str | None,
    timezone: str,
    filters: list[str] | None,
    filter_groups: list[list[str]] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "website_id": website_id,
        "range": range,
        "timezone": timezone,
        "filters": filters or [],
        "filter_groups": filter_groups or [],
    }
    if start is not None or end is not None:
        body["start"], body["end"] = start, end
    return body


async def _check() -> int:
    try:
        config = load_config()
        sites, capabilities = await asyncio.gather(
            get("/api/sites/"),
            get("/api/v1/capabilities/"),
        )
        result = {
            "ok": True,
            "server": config.base_url,
            "accessible_sites": len(sites.get("websites", [])),
            "schema_version": capabilities.get("schema_version"),
        }
        print(json.dumps(result, indent=2))
        return 0
    except (ConfigError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Mantecato MCP server")
    parser.add_argument("--check", action="store_true", help="Check API configuration and exit")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return
    if args.check:
        raise SystemExit(asyncio.run(_check()))
    # stdout belongs exclusively to MCP framing from this point onward.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
