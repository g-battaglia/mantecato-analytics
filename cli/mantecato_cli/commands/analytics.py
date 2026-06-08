"""Analytics CLI commands — one per analytics page exposed by the web UI.

Each command body is a single :func:`run_with_range` call: the shared helper
takes care of Django bootstrap, date-range parsing, service invocation and
output formatting.
"""

from __future__ import annotations

import typer

from cli.mantecato_cli.app import (
    FORMAT_OPTION,
    RANGE_OPT,
    WEBSITE_OPT,
    app,
    bootstrap,
    emit,
    run_with_range,
)


@app.command("sites")
def sites_list(format: str = FORMAT_OPTION) -> None:
    """List accessible websites (admin view: lists every site)."""
    bootstrap()
    from apps.analytics.services import resolve_websites_for_user

    emit(resolve_websites_for_user(user_id="*", is_admin=True), format)


@app.command("overview")
def overview(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Overview analytics for a website."""
    from apps.analytics.services import get_overview_data

    run_with_range(get_overview_data, website, range, format)


@app.command("pages")
def pages(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    page: int = typer.Option(1, "--page", help="Page number"),
    format: str = FORMAT_OPTION,
) -> None:
    """Page-level analytics."""
    from apps.analytics.services import get_pages_data

    run_with_range(get_pages_data, website, range, format, page=page)


@app.command("events")
def events(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Custom event analytics."""
    from apps.analytics.services import get_events_data

    run_with_range(get_events_data, website, range, format)


@app.command("devices")
def devices(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Device breakdowns."""
    from apps.analytics.services import get_devices_data

    run_with_range(get_devices_data, website, range, format)


@app.command("geo")
def geo(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Geographic breakdown (country-level)."""
    from apps.analytics.services import get_geo_data

    run_with_range(get_geo_data, website, range, format)


@app.command("compare")
def compare(
    website: str = WEBSITE_OPT,
    range: str = RANGE_OPT,
    mode: str = typer.Option("previous_period", "--mode"),
    format: str = FORMAT_OPTION,
) -> None:
    """Period comparison."""
    from apps.analytics.services import get_compare_data

    run_with_range(get_compare_data, website, range, format, comparison_mode=mode)


@app.command("realtime")
def realtime(
    website: str = WEBSITE_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Realtime visitor data (no date range required)."""
    bootstrap()
    from apps.analytics.services import get_realtime_data

    emit(get_realtime_data(website), format)
