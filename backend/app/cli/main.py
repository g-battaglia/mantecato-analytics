from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from rich.console import Console

from .helpers import (
    compute_derived_stats,
    format_duration,
    format_output,
    format_percent,
    num,
    parse_date_args,
    parse_filter_args,
    pct_change,
    resolve_granularity_arg,
    resolve_site_id,
    resolve_user_id,
    run_with_db,
)

app = typer.Typer(name="mantecato", help="Mantecato Analytics CLI", no_args_is_help=True)
console = Console()


def _sync(coro):
    """Run an async coroutine with DB lifecycle management."""
    return asyncio.run(run_with_db(coro))


# ── Core ────────────────────────────────────────────────────────────────


@app.command()
def sites(
    format: str = typer.Option("table", "-f", "--format", help="Output: json, table, csv"),
):
    """List all tracked sites."""
    async def _run():
        from .helpers import list_sites
        data = await list_sites()
        console.print(format_output(data, format, title="Sites"))

    _sync(_run())


@app.command()
def stats(
    site: str = typer.Option(..., "-s", "--site", help="Site name, domain, or UUID"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
):
    """Overview: pageviews, visitors, visits, bounce rate, avg duration, pages/visit."""
    async def _run():
        from ..queries.stats import get_website_stats

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        raw = await get_website_stats(site_id, date_range.start_date, date_range.end_date, filters)
        data = compute_derived_stats(raw)
        console.print(format_output(data, format, title=f"Stats: {site}"))

    _sync(_run())


@app.command()
def timeseries(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    granularity: str = typer.Option("auto", "-g", "--granularity"),
):
    """Pageview and visitor time series."""
    async def _run():
        from ..queries.stats import get_pageview_time_series

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        gran = resolve_granularity_arg(granularity, date_range)
        data = await get_pageview_time_series(
            site_id, date_range.start_date, date_range.end_date, gran, filters
        )
        console.print(format_output(data, format, title="Time Series"))

    _sync(_run())


@app.command()
def compare(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    compare_mode: str = typer.Option("previous_period", "--compare-mode"),
):
    """Current vs previous period with deltas."""
    async def _run():
        from ..date_utils import get_comparison_range
        from ..queries.compare import get_comparison_stats

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        prev_range = get_comparison_range(date_range, compare_mode)
        data = await get_comparison_stats(
            site_id,
            date_range.start_date, date_range.end_date,
            prev_range.start_date, prev_range.end_date,
        )
        console.print(format_output(data, format, title="Comparison"))

    _sync(_run())


@app.command("report")
def report_cmd(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    human: bool = typer.Option(False, "-H", "--human", help="Human-friendly output with tables and bars"),
):
    """Full analytics report in one shot."""
    from .report import run_report
    _sync(run_report(site, period, start, end, format, filter, human))


# ── Pages ───────────────────────────────────────────────────────────────


@app.command()
def pages(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
    mode: str = typer.Option("path", "--mode", help="path or slug"),
):
    """Page analytics: views, time-on-page, bounce rate, entries/exits."""
    async def _run():
        from ..queries.pageviews import get_page_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_page_metrics(
            site_id, date_range.start_date, date_range.end_date,
            limit=limit, filters=filters, page_mode=mode,
        )
        console.print(format_output(data, format, title="Pages"))

    _sync(_run())


@app.command("page-detail")
def page_detail(
    site: str = typer.Option(..., "-s", "--site"),
    url: str = typer.Option(..., "--url"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
    granularity: str = typer.Option("auto", "-g", "--granularity"),
):
    """Drill-down: referrers, next pages, time distribution."""
    async def _run():
        from ..queries.pageviews import (
            get_next_pages,
            get_page_referrers,
            get_page_time_series,
            get_time_on_page_distribution,
        )

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        gran = resolve_granularity_arg(granularity, date_range)

        referrers, next_pages, distribution, ts = await asyncio.gather(
            get_page_referrers(site_id, url, date_range.start_date, date_range.end_date, limit),
            get_next_pages(site_id, url, date_range.start_date, date_range.end_date, limit),
            get_time_on_page_distribution(site_id, url, date_range.start_date, date_range.end_date),
            get_page_time_series(site_id, url, date_range.start_date, date_range.end_date, gran, filters),
        )
        data = {
            "referrers": referrers,
            "next_pages": next_pages,
            "time_distribution": distribution,
            "timeseries": ts,
        }
        console.print(format_output(data, format, title=f"Page Detail: {url}"))

    _sync(_run())


@app.command("top-pages")
def top_pages(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Quick top pages by visitors."""
    async def _run():
        from ..queries.stats import get_top_pages

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_top_pages(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Top Pages"))

    _sync(_run())


# ── Sources ─────────────────────────────────────────────────────────────


@app.command()
def sources(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Traffic sources with bounce rate and duration."""
    async def _run():
        from ..queries.sources import get_referrer_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_referrer_metrics(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Sources"))

    _sync(_run())


@app.command("referrer-pages")
def referrer_pages(
    site: str = typer.Option(..., "-s", "--site"),
    referrer: str = typer.Option(..., "--referrer"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Pages a referrer drives traffic to."""
    async def _run():
        from ..queries.sources import get_referrer_pages as _get

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await _get(
            site_id, date_range.start_date, date_range.end_date,
            referrer, limit, filters,
        )
        console.print(format_output(data, format, title=f"Referrer Pages: {referrer}"))

    _sync(_run())


@app.command()
def channels(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
):
    """Auto-grouped channels (Organic, Direct, Social, Paid, etc.)."""
    async def _run():
        from ..queries.sources import get_channel_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_channel_metrics(
            site_id, date_range.start_date, date_range.end_date, filters
        )
        console.print(format_output(data, format, title="Channels"))

    _sync(_run())


@app.command()
def utm(
    site: str = typer.Option(..., "-s", "--site"),
    dimension: str = typer.Option("utm_source", "--dimension"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """UTM parameter breakdown."""
    async def _run():
        from ..queries.sources import get_utm_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_utm_metrics(
            site_id, date_range.start_date, date_range.end_date,
            dimension, limit, filters,
        )
        console.print(format_output(data, format, title=f"UTM: {dimension}"))

    _sync(_run())


@app.command()
def clickids(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
):
    """Click ID analysis (gclid, fbclid, etc.)."""
    async def _run():
        from ..queries.sources import get_click_id_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_click_id_metrics(
            site_id, date_range.start_date, date_range.end_date, filters
        )
        console.print(format_output(data, format, title="Click IDs"))

    _sync(_run())


@app.command()
def hostnames(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Hostname breakdown."""
    async def _run():
        from ..queries.sources import get_hostname_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_hostname_metrics(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Hostnames"))

    _sync(_run())


@app.command("top-referrers")
def top_referrers(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Quick top referrers."""
    async def _run():
        from ..queries.stats import get_top_referrers

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_top_referrers(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Top Referrers"))

    _sync(_run())


# ── Events ──────────────────────────────────────────────────────────────


@app.command()
def events(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Custom event metrics."""
    async def _run():
        from ..queries.events import get_event_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_event_metrics(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Events"))

    _sync(_run())


@app.command("event-detail")
def event_detail(
    site: str = typer.Option(..., "-s", "--site"),
    event: str = typer.Option(..., "--event"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
    granularity: str = typer.Option("auto", "-g", "--granularity"),
):
    """Time series + property breakdown for one event."""
    async def _run():
        from ..queries.events import get_event_properties, get_event_time_series

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        gran = resolve_granularity_arg(granularity, date_range)

        ts, properties = await asyncio.gather(
            get_event_time_series(
                site_id, event, date_range.start_date, date_range.end_date, gran, filters
            ),
            get_event_properties(
                site_id, event, date_range.start_date, date_range.end_date, limit
            ),
        )
        data = {"timeseries": ts, "properties": properties}
        console.print(format_output(data, format, title=f"Event Detail: {event}"))

    _sync(_run())


@app.command("top-events")
def top_events(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Quick top events."""
    async def _run():
        from ..queries.stats import get_top_events

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_top_events(
            site_id, date_range.start_date, date_range.end_date, limit, filters
        )
        console.print(format_output(data, format, title="Top Events"))

    _sync(_run())


# ── Sessions ────────────────────────────────────────────────────────────


@app.command()
def sessions(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
    visited_page: str = typer.Option(None, "--visited-page"),
    triggered_event: str = typer.Option(None, "--triggered-event"),
):
    """Session list with location, device, engagement."""
    async def _run():
        from ..queries.sessions import get_session_list

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_session_list(
            site_id, date_range.start_date, date_range.end_date,
            limit=limit, filters=filters,
            visited_page=visited_page, triggered_event=triggered_event,
        )
        console.print(format_output(data, format, title="Sessions"))

    _sync(_run())


@app.command("session-activity")
def session_activity(
    site: str = typer.Option(..., "-s", "--site"),
    session_id: str = typer.Option(..., "--session-id"),
    format: str = typer.Option("table", "-f", "--format"),
):
    """Full event replay for a session."""
    async def _run():
        from ..queries.sessions import get_session_activity

        site_id = await resolve_site_id(site)
        data = await get_session_activity(session_id, site_id)
        console.print(format_output(data, format, title="Session Activity"))

    _sync(_run())


# ── Devices ─────────────────────────────────────────────────────────────


@app.command()
def devices(
    site: str = typer.Option(..., "-s", "--site"),
    dimension: str = typer.Option("device", "--dimension", help="browser, os, device, screen, language"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Device type breakdown (default) or by dimension."""
    async def _run():
        from ..queries.devices import get_device_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_device_metrics(
            site_id, date_range.start_date, date_range.end_date,
            dimension, limit, filters,
        )
        console.print(format_output(data, format, title=f"Devices: {dimension}"))

    _sync(_run())


# ── Geographic ──────────────────────────────────────────────────────────


@app.command()
def geo(
    site: str = typer.Option(..., "-s", "--site"),
    level: str = typer.Option("country", "--level", help="country, region, city"),
    country: str = typer.Option(None, "--country"),
    region: str = typer.Option(None, "--region"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Geographic breakdown by country, region, or city."""
    async def _run():
        from ..queries.geo import get_geo_metrics

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)
        data = await get_geo_metrics(
            site_id, date_range.start_date, date_range.end_date,
            level=level, country_filter=country, region_filter=region,
            limit=limit, filters=filters,
        )
        console.print(format_output(data, format, title=f"Geo: {level}"))

    _sync(_run())


# ── Advanced ────────────────────────────────────────────────────────────


@app.command()
def realtime(
    site: str = typer.Option(..., "-s", "--site"),
    format: str = typer.Option("table", "-f", "--format"),
):
    """Live active visitors."""
    async def _run():
        from ..queries.realtime import get_active_visitors, get_current_pages, get_recent_events

        site_id = await resolve_site_id(site)
        visitors, pages, events = await asyncio.gather(
            get_active_visitors(site_id),
            get_current_pages(site_id),
            get_recent_events(site_id),
        )
        data = {
            "active_visitors": visitors,
            "current_pages": pages,
            "recent_events": events,
        }
        console.print(format_output(data, format, title="Realtime"))

    _sync(_run())


@app.command()
def retention(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    retention_granularity: str = typer.Option("week", "--retention-granularity"),
):
    """Cohort retention analysis."""
    async def _run():
        from ..queries.retention import get_retention

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        data = await get_retention(
            site_id, date_range.start_date, date_range.end_date, retention_granularity
        )
        console.print(format_output(data, format, title="Retention"))

    _sync(_run())


@app.command()
def funnel(
    site: str = typer.Option(..., "-s", "--site"),
    steps: str = typer.Option(..., "--steps", help="Comma-separated URLs or event names"),
    window: int = typer.Option(60, "--window", help="Window in minutes"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
):
    """Conversion funnel analysis."""
    async def _run():
        from ..queries.funnels import get_funnel

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        step_list = [
            {"type": "url", "value": s.strip()}
            for s in steps.split(",")
        ]
        data = await get_funnel(
            site_id, date_range.start_date, date_range.end_date,
            step_list, window,
        )
        console.print(format_output(data, format, title="Funnel"))

    _sync(_run())


@app.command()
def journeys(
    site: str = typer.Option(..., "-s", "--site"),
    path_length: int = typer.Option(3, "--path-length"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """User journey paths."""
    async def _run():
        from ..queries.journeys import get_journeys

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        data = await get_journeys(
            site_id, date_range.start_date, date_range.end_date,
            path_length, limit,
        )
        console.print(format_output(data, format, title="Journeys"))

    _sync(_run())


@app.command()
def revenue(
    site: str = typer.Option(..., "-s", "--site"),
    view: str = typer.Option("summary", "--view", help="summary, timeseries, by-event, by-country"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    granularity: str = typer.Option("auto", "-g", "--granularity"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Revenue analytics."""
    async def _run():
        from ..queries.revenue import (
            get_revenue_by_country,
            get_revenue_by_event,
            get_revenue_summary,
            get_revenue_time_series,
        )

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)

        if view == "summary":
            data = await get_revenue_summary(site_id, date_range.start_date, date_range.end_date)
        elif view == "timeseries":
            gran = resolve_granularity_arg(granularity, date_range)
            data = await get_revenue_time_series(
                site_id, date_range.start_date, date_range.end_date, gran
            )
        elif view == "by-event":
            data = await get_revenue_by_event(
                site_id, date_range.start_date, date_range.end_date, limit
            )
        elif view == "by-country":
            data = await get_revenue_by_country(
                site_id, date_range.start_date, date_range.end_date, limit
            )
        else:
            raise SystemExit(f"Unknown view: {view}")
        console.print(format_output(data, format, title=f"Revenue: {view}"))

    _sync(_run())


@app.command()
def engagement(
    site: str = typer.Option(..., "-s", "--site"),
    view: str = typer.Option("percentiles", "--view", help="distribution, percentiles, by-page, bounce-by-page, bounce-by-source"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    filter: list[str] = typer.Option([], "--filter"),
    limit: int = typer.Option(20, "-l", "--limit"),
):
    """Duration distribution, percentiles, bounce rates."""
    async def _run():
        from ..queries.engagement import (
            get_bounce_rate_by_page,
            get_bounce_rate_by_source,
            get_duration_by_page,
            get_duration_distribution,
            get_duration_percentiles,
        )

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        filters = parse_filter_args(filter)

        if view == "distribution":
            data = await get_duration_distribution(
                site_id, date_range.start_date, date_range.end_date, filters
            )
        elif view == "percentiles":
            data = await get_duration_percentiles(
                site_id, date_range.start_date, date_range.end_date, filters
            )
        elif view == "by-page":
            data = await get_duration_by_page(
                site_id, date_range.start_date, date_range.end_date, limit, filters
            )
        elif view == "bounce-by-page":
            data = await get_bounce_rate_by_page(
                site_id, date_range.start_date, date_range.end_date, limit, filters
            )
        elif view == "bounce-by-source":
            data = await get_bounce_rate_by_source(
                site_id, date_range.start_date, date_range.end_date, limit, filters
            )
        else:
            raise SystemExit(f"Unknown view: {view}")
        console.print(format_output(data, format, title=f"Engagement: {view}"))

    _sync(_run())


@app.command("filter-values")
def filter_values(
    site: str = typer.Option(..., "-s", "--site"),
    column: str = typer.Option(..., "--column"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    search: str = typer.Option(None, "--search"),
    limit: int = typer.Option(50, "-l", "--limit"),
    format: str = typer.Option("table", "-f", "--format"),
):
    """Available filter values for a column."""
    async def _run():
        from ..queries.filter_values import get_filter_values

        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        data = await get_filter_values(
            site_id, column, date_range.start_date, date_range.end_date,
            search=search, limit=limit,
        )
        # Return as list of dicts for consistent formatting
        formatted = [{"value": v} for v in data]
        console.print(format_output(formatted, format, title=f"Filter Values: {column}"))

    _sync(_run())


# ── CRUD: Annotations ──────────────────────────────────────────────────


@app.command()
def annotations(
    site: str = typer.Option(..., "-s", "--site"),
    period: str = typer.Option("30d", "-p", "--period"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """List annotations."""
    async def _run():
        from ..queries.annotations import list_annotations

        user_id = await resolve_user_id(api_key)
        site_id = await resolve_site_id(site)
        date_range = parse_date_args(period, start, end)
        data = await list_annotations(
            user_id, site_id, date_range.start_date, date_range.end_date
        )
        console.print(format_output(data, format, title="Annotations"))

    _sync(_run())


@app.command("annotation-create")
def annotation_create(
    site: str = typer.Option(..., "-s", "--site"),
    title: str = typer.Option(..., "--title"),
    date: str = typer.Option(..., "--date"),
    description: str = typer.Option("", "--description"),
    color: str = typer.Option("blue", "--color"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Create an annotation."""
    async def _run():
        from ..queries.annotations import create_annotation

        user_id = await resolve_user_id(api_key)
        site_id = await resolve_site_id(site)
        data = await create_annotation(user_id, site_id, title, description, date, color)
        console.print(format_output(data, format, title="Annotation Created"))

    _sync(_run())


@app.command("annotation-delete")
def annotation_delete(
    id: str = typer.Option(..., "--id"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Delete an annotation."""
    async def _run():
        from ..queries.annotations import delete_annotation

        user_id = await resolve_user_id(api_key)
        ok = await delete_annotation(id, user_id)
        if ok:
            console.print(f"Deleted annotation {id}")
        else:
            console.print(f"Annotation not found or not owned: {id}")

    _sync(_run())


# ── CRUD: Saved Views ──────────────────────────────────────────────────


@app.command("saved-views")
def saved_views(
    site: str = typer.Option(..., "-s", "--site"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """List saved views."""
    async def _run():
        from ..queries.saved_views import list_saved_views

        user_id = await resolve_user_id(api_key)
        site_id = await resolve_site_id(site)
        data = await list_saved_views(user_id, site_id)
        console.print(format_output(data, format, title="Saved Views"))

    _sync(_run())


@app.command("saved-view")
def saved_view(
    id: str = typer.Option(..., "--id"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Get a saved view."""
    async def _run():
        from ..queries.saved_views import get_saved_view

        user_id = await resolve_user_id(api_key)
        data = await get_saved_view(id, user_id)
        if data:
            console.print(format_output(data, format, title="Saved View"))
        else:
            console.print(f"Saved view not found: {id}")

    _sync(_run())


@app.command("saved-view-create")
def saved_view_create(
    site: str = typer.Option(..., "-s", "--site"),
    name: str = typer.Option(..., "--name"),
    description: str = typer.Option("", "--description"),
    config: str = typer.Option(..., "--config", help="JSON config"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Create a saved view."""
    async def _run():
        from ..queries.saved_views import create_saved_view

        user_id = await resolve_user_id(api_key)
        site_id = await resolve_site_id(site)
        config_obj = json.loads(config)
        data = await create_saved_view(user_id, site_id, name, description, config_obj)
        console.print(format_output(data, format, title="Saved View Created"))

    _sync(_run())


@app.command("saved-view-delete")
def saved_view_delete(
    id: str = typer.Option(..., "--id"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Delete a saved view."""
    async def _run():
        from ..queries.saved_views import delete_saved_view

        user_id = await resolve_user_id(api_key)
        ok = await delete_saved_view(id, user_id)
        if ok:
            console.print(f"Deleted saved view {id}")
        else:
            console.print(f"Saved view not found or not owned: {id}")

    _sync(_run())


# ── CRUD: Dashboards ───────────────────────────────────────────────────


@app.command()
def dashboards(
    site: str = typer.Option(None, "-s", "--site"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """List dashboards."""
    async def _run():
        from ..queries.dashboards import list_dashboards

        user_id = await resolve_user_id(api_key)
        site_id = await resolve_site_id(site) if site else None
        data = await list_dashboards(user_id, site_id)
        console.print(format_output(data, format, title="Dashboards"))

    _sync(_run())


@app.command("dashboard")
def dashboard(
    id: str = typer.Option(..., "--id"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Get a dashboard."""
    async def _run():
        from ..queries.dashboards import get_dashboard

        user_id = await resolve_user_id(api_key)
        data = await get_dashboard(id, user_id)
        if data:
            console.print(format_output(data, format, title="Dashboard"))
        else:
            console.print(f"Dashboard not found: {id}")

    _sync(_run())


@app.command("dashboard-delete")
def dashboard_delete(
    id: str = typer.Option(..., "--id"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Delete a dashboard."""
    async def _run():
        from ..queries.dashboards import delete_dashboard

        user_id = await resolve_user_id(api_key)
        ok = await delete_dashboard(id, user_id)
        if ok:
            console.print(f"Deleted dashboard {id}")
        else:
            console.print(f"Dashboard not found or not owned: {id}")

    _sync(_run())


# ── CRUD: Scheduled Exports ────────────────────────────────────────────


@app.command("scheduled-exports")
def scheduled_exports(
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """List scheduled exports."""
    async def _run():
        from ..queries.scheduled_exports import list_scheduled_exports

        user_id = await resolve_user_id(api_key)
        data = await list_scheduled_exports(user_id)
        console.print(format_output(data, format, title="Scheduled Exports"))

    _sync(_run())


@app.command("scheduled-export")
def scheduled_export(
    id: str = typer.Option(..., "--id"),
    format: str = typer.Option("table", "-f", "--format"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Get a scheduled export."""
    async def _run():
        from ..queries.scheduled_exports import get_scheduled_export

        user_id = await resolve_user_id(api_key)
        data = await get_scheduled_export(id, user_id)
        if data:
            console.print(format_output(data, format, title="Scheduled Export"))
        else:
            console.print(f"Scheduled export not found: {id}")

    _sync(_run())


@app.command("scheduled-export-delete")
def scheduled_export_delete(
    id: str = typer.Option(..., "--id"),
    api_key: str = typer.Option(None, "--api-key"),
):
    """Delete a scheduled export."""
    async def _run():
        from ..queries.scheduled_exports import delete_scheduled_export

        user_id = await resolve_user_id(api_key)
        ok = await delete_scheduled_export(id, user_id)
        if ok:
            console.print(f"Deleted scheduled export {id}")
        else:
            console.print(f"Scheduled export not found or not owned: {id}")

    _sync(_run())


if __name__ == "__main__":
    app()
