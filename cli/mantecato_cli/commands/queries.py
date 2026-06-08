"""Query-level CLI commands — direct access to the core query engine.

Most commands take ``--website / --range / [--limit] / --filter / --format``,
follow the same bootstrap-then-emit shape, and use the shared option
templates declared in :mod:`cli.mantecato_cli.app`.
"""

from __future__ import annotations

import typer

from cli.mantecato_cli.app import (
    FILTER_OPTION,
    FORMAT_OPTION,
    LIMIT_OPT,
    RANGE_ALIAS_OPT,
    WEBSITE_ALIAS_OPT,
    app,
    bootstrap,
    emit,
    parse_filters,
    resolve_range,
)


@app.command("stats")
def stats_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Raw overview stats with derived metrics."""
    bootstrap()
    from core.mantecato_core.helpers import compute_derived_stats
    from core.mantecato_core.queries.stats import get_website_stats

    dr = resolve_range(range)
    raw = get_website_stats(website, dr.start_date, dr.end_date, parse_filters(filter))
    emit(compute_derived_stats({**raw, "total_duration": raw.get("totaltime", 0)}), format)


@app.command("timeseries")
def timeseries_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    granularity: str = typer.Option("auto", "--granularity", "-g"),
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Pageview and visitor time series."""
    bootstrap()
    from core.mantecato_core.date_utils import resolve_granularity
    from core.mantecato_core.queries.stats import get_pageview_time_series

    dr = resolve_range(range)
    emit(
        get_pageview_time_series(
            website,
            dr.start_date,
            dr.end_date,
            resolve_granularity(granularity, dr),
            parse_filters(filter),
        ),
        format,
    )


@app.command("top-pages")
def top_pages_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    mode: str = typer.Option("path", "--mode"),
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Top pages by views."""
    bootstrap()
    from core.mantecato_core.queries.stats import get_top_pages

    dr = resolve_range(range)
    emit(
        get_top_pages(
            website,
            dr.start_date,
            dr.end_date,
            limit=limit,
            filters=parse_filters(filter),
            page_mode=mode,
        ),
        format,
    )


@app.command("top-sections")
def top_sections_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    depth: int = typer.Option(2, "--depth"),
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Top URL sections by views."""
    bootstrap()
    from core.mantecato_core.queries.stats import get_top_sections

    dr = resolve_range(range)
    emit(
        get_top_sections(website, dr.start_date, dr.end_date, depth, limit, parse_filters(filter)),
        format,
    )


@app.command("event-timeseries")
def event_timeseries_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    event: str = typer.Option(..., "--event"),
    range: str = RANGE_ALIAS_OPT,
    granularity: str = typer.Option("auto", "--granularity", "-g"),
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Time series for one event."""
    bootstrap()
    from core.mantecato_core.date_utils import resolve_granularity
    from core.mantecato_core.queries.events import get_event_time_series

    dr = resolve_range(range)
    emit(
        get_event_time_series(
            website,
            event,
            dr.start_date,
            dr.end_date,
            resolve_granularity(granularity, dr),
            parse_filters(filter),
        ),
        format,
    )


@app.command("filter-values")
def filter_values_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    column: str = typer.Option(..., "--column"),
    range: str = RANGE_ALIAS_OPT,
    search: str | None = typer.Option(None, "--search"),
    limit: int = typer.Option(50, "--limit", "-l"),
    format: str = FORMAT_OPTION,
) -> None:
    """Available filter values for a column."""
    bootstrap()
    from core.mantecato_core.queries.filter_values import get_filter_values

    dr = resolve_range(range)
    values = get_filter_values(
        website, column, dr.start_date, dr.end_date, search=search, limit=limit
    )
    emit([{"value": value} for value in values], format)


@app.command("heatmap")
def heatmap_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    timezone: str = typer.Option("UTC", "--timezone"),
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Traffic heatmap by hour/day."""
    bootstrap()
    from core.mantecato_core.queries.heatmap import get_traffic_heatmap

    dr = resolve_range(range)
    emit(
        get_traffic_heatmap(website, dr.start_date, dr.end_date, timezone, parse_filters(filter)),
        format,
    )
