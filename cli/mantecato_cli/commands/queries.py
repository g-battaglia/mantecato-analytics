"""Query-level CLI commands — direct access to the core query engine.

Most commands take ``--website / --range / [--limit] / --filter / --format``,
follow the same bootstrap-then-emit shape, and use the shared option
templates :data:`WEBSITE_ALIAS_OPT` / :data:`RANGE_ALIAS_OPT` /
:data:`LIMIT_OPT` declared in :mod:`cli.mantecato_cli.app`. A handful of
commands (``page-detail``, ``event-detail``, ``session-activity``) compose
multiple query calls and are kept verbose so each call site stays auditable.
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


@app.command("top-referrers")
def top_referrers_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Top referrers by visitors."""
    bootstrap()
    from core.mantecato_core.queries.stats import get_top_referrers

    dr = resolve_range(range)
    emit(
        get_top_referrers(website, dr.start_date, dr.end_date, limit, parse_filters(filter)),
        format,
    )


@app.command("top-events")
def top_events_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    properties: bool = typer.Option(False, "--properties"),
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Top custom events, optionally with properties."""
    bootstrap()
    from core.mantecato_core.queries.stats import get_top_events, get_top_events_with_properties

    dr = resolve_range(range)
    query = get_top_events_with_properties if properties else get_top_events
    emit(query(website, dr.start_date, dr.end_date, limit, parse_filters(filter)), format)


@app.command("page-detail")
def page_detail_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    url: str = typer.Option(..., "--url"),
    range: str = RANGE_ALIAS_OPT,
    granularity: str = typer.Option("auto", "--granularity", "-g"),
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Page referrers, next pages, duration distribution, and time series."""
    bootstrap()
    from core.mantecato_core.date_utils import resolve_granularity
    from core.mantecato_core.queries.pageviews import (
        get_next_pages,
        get_page_referrers,
        get_page_time_series,
        get_time_on_page_distribution,
    )

    dr = resolve_range(range)
    gran = resolve_granularity(granularity, dr)
    emit(
        {
            "referrers": get_page_referrers(website, url, dr.start_date, dr.end_date, limit),
            "next_pages": get_next_pages(website, url, dr.start_date, dr.end_date, limit),
            "time_distribution": get_time_on_page_distribution(
                website, url, dr.start_date, dr.end_date
            ),
            "timeseries": get_page_time_series(
                website, url, dr.start_date, dr.end_date, gran, parse_filters(filter)
            ),
        },
        format,
    )


@app.command("page-referrers")
def page_referrers_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    url: str = typer.Option(..., "--url"),
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Referrers for one page."""
    bootstrap()
    from core.mantecato_core.queries.pageviews import get_page_referrers

    dr = resolve_range(range)
    emit(get_page_referrers(website, url, dr.start_date, dr.end_date, limit), format)


@app.command("next-pages")
def next_pages_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    url: str = typer.Option(..., "--url"),
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Next pages after one URL."""
    bootstrap()
    from core.mantecato_core.queries.pageviews import get_next_pages

    dr = resolve_range(range)
    emit(get_next_pages(website, url, dr.start_date, dr.end_date, limit), format)


@app.command("event-detail")
def event_detail_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    event: str = typer.Option(..., "--event"),
    range: str = RANGE_ALIAS_OPT,
    granularity: str = typer.Option("auto", "--granularity", "-g"),
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Event time series and property breakdown."""
    bootstrap()
    from core.mantecato_core.date_utils import resolve_granularity
    from core.mantecato_core.queries.events import get_event_properties, get_event_time_series

    dr = resolve_range(range)
    gran = resolve_granularity(granularity, dr)
    emit(
        {
            "timeseries": get_event_time_series(
                website, event, dr.start_date, dr.end_date, gran, parse_filters(filter)
            ),
            "properties": get_event_properties(
                website, event, dr.start_date, dr.end_date, limit
            ),
        },
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


@app.command("event-properties")
def event_properties_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    event: str = typer.Option(..., "--event"),
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Property values for one event."""
    bootstrap()
    from core.mantecato_core.queries.events import get_event_properties

    dr = resolve_range(range)
    emit(get_event_properties(website, event, dr.start_date, dr.end_date, limit), format)


@app.command("session-activity")
def session_activity_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    session_id: str = typer.Option(..., "--session-id"),
    format: str = FORMAT_OPTION,
) -> None:
    """Full event replay for a session."""
    bootstrap()
    from core.mantecato_core.queries.sessions import get_session_activity

    emit(get_session_activity(session_id, website), format)


@app.command("channels")
def channels_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Auto-grouped traffic channels."""
    bootstrap()
    from core.mantecato_core.queries.sources import get_channel_metrics

    dr = resolve_range(range)
    emit(get_channel_metrics(website, dr.start_date, dr.end_date, parse_filters(filter)), format)


@app.command("utm")
def utm_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    dimension: str = typer.Option("utm_source", "--dimension"),
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """UTM parameter breakdown."""
    bootstrap()
    from core.mantecato_core.queries.sources import get_utm_metrics

    dr = resolve_range(range)
    emit(
        get_utm_metrics(
            website, dr.start_date, dr.end_date, dimension, limit, parse_filters(filter)
        ),
        format,
    )


@app.command("clickids")
def clickids_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Click ID analysis."""
    bootstrap()
    from core.mantecato_core.queries.sources import get_click_id_metrics

    dr = resolve_range(range)
    emit(get_click_id_metrics(website, dr.start_date, dr.end_date, parse_filters(filter)), format)


@app.command("hostnames")
def hostnames_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Hostname breakdown."""
    bootstrap()
    from core.mantecato_core.queries.sources import get_hostname_metrics

    dr = resolve_range(range)
    emit(
        get_hostname_metrics(website, dr.start_date, dr.end_date, limit, parse_filters(filter)),
        format,
    )


@app.command("referrer-pages")
def referrer_pages_cmd(
    website: str = WEBSITE_ALIAS_OPT,
    referrer: str = typer.Option(..., "--referrer"),
    range: str = RANGE_ALIAS_OPT,
    limit: int = LIMIT_OPT,
    filter: list[str] = FILTER_OPTION,
    format: str = FORMAT_OPTION,
) -> None:
    """Pages driven by one referrer."""
    bootstrap()
    from core.mantecato_core.queries.sources import get_referrer_pages

    dr = resolve_range(range)
    emit(
        get_referrer_pages(
            website, dr.start_date, dr.end_date, referrer, limit, parse_filters(filter)
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
