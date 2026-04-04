from __future__ import annotations

import asyncio
import json
from typing import Any

from rich.console import Console
from rich.table import Table

from mantecato_cli.helpers import (
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
)

console = Console()

BAR_WIDTH = 20


def _bar(value: int | float, max_value: int | float) -> str:
    if max_value == 0:
        return ""
    filled = int((value / max_value) * BAR_WIDTH)
    return "\u2588" * filled + "\u2591" * (BAR_WIDTH - filled)


async def run_report(
    site: str,
    period: str,
    start: str | None,
    end: str | None,
    fmt: str,
    filter_strs: list[str],
    human: bool,
) -> None:
    site_id = await resolve_site_id(site)
    date_range = parse_date_args(period, start, end)
    filters = parse_filter_args(filter_strs)

    from mantecato_core.date_utils import get_comparison_range
    from mantecato_core.queries.events import get_event_properties
    from mantecato_core.queries.sources import get_channel_metrics
    from mantecato_core.queries.stats import (
        get_top_events_with_properties,
        get_top_pages,
        get_top_referrers,
        get_website_stats,
    )

    prev_range = get_comparison_range(date_range, "previous_period")

    # Run all queries in parallel (like the TS version with Promise.allSettled)
    results = await asyncio.gather(
        get_website_stats(site_id, date_range.start_date, date_range.end_date, filters),
        get_website_stats(site_id, prev_range.start_date, prev_range.end_date, filters),
        get_top_pages(site_id, date_range.start_date, date_range.end_date, 10, filters),
        get_top_referrers(site_id, date_range.start_date, date_range.end_date, 10, filters),
        get_top_events_with_properties(site_id, date_range.start_date, date_range.end_date, 5, 3, filters),
        get_channel_metrics(site_id, date_range.start_date, date_range.end_date, filters),
        return_exceptions=True,
    )

    current_raw = results[0] if not isinstance(results[0], Exception) else {}
    previous_raw = results[1] if not isinstance(results[1], Exception) else {}
    top_pages = results[2] if not isinstance(results[2], Exception) else []
    top_referrers = results[3] if not isinstance(results[3], Exception) else []
    top_events = results[4] if not isinstance(results[4], Exception) else []
    channels = results[5] if not isinstance(results[5], Exception) else []

    current = compute_derived_stats(current_raw)
    previous = compute_derived_stats(previous_raw)

    # JSON output
    if fmt == "json":
        data = {
            "site": site,
            "period": period,
            "overview": current,
            "comparison": {
                "current": current,
                "previous": previous,
            },
            "topPages": top_pages,
            "topSources": top_referrers,
            "topEvents": top_events,
            "channels": channels,
        }
        console.print(json.dumps(data, indent=2, default=str))
        return

    # Human-friendly output with Rich tables
    if human:
        _print_human_report(site, period, current, previous, top_pages, top_referrers, top_events, channels)
        return

    # Default compact output
    _print_compact_report(site, period, current, previous, top_pages, top_referrers, top_events, channels)


def _print_human_report(
    site: str,
    period: str,
    current: dict[str, Any],
    previous: dict[str, Any],
    top_pages: list[dict],
    top_referrers: list[dict],
    top_events: list[dict],
    channels: list[dict],
) -> None:
    console.print(f"\n[bold cyan]Report: {site}[/] ({period})\n")

    # Overview table
    table = Table(title="Overview", show_header=True, header_style="bold")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("vs Previous", justify="right")

    metrics = [
        ("Pageviews", "pageviews", None),
        ("Visitors", "visitors", None),
        ("Visits", "visits", None),
        ("Bounce Rate", "bounce_rate", "pct"),
        ("Avg Duration", "avg_duration", "duration"),
        ("Pages/Visit", "pages_per_visit", None),
    ]

    for label, key, kind in metrics:
        val = current.get(key)
        prev_val = previous.get(key)

        if kind == "pct":
            formatted = format_percent(val)
            delta = pct_change(val, prev_val)
        elif kind == "duration":
            formatted = format_duration(val)
            delta = pct_change(val, prev_val)
        else:
            formatted = num(val)
            delta = pct_change(val, prev_val)

        delta_style = "green" if delta.startswith("+") else "red" if delta.startswith("-") else "dim"
        table.add_row(label, formatted, f"[{delta_style}]{delta}[/]")

    console.print(table)
    console.print()

    # Channels
    if channels:
        table = Table(title="Channels", show_header=True, header_style="bold")
        table.add_column("Channel", style="cyan")
        table.add_column("Visitors", justify="right")
        table.add_column("", width=BAR_WIDTH + 2)

        max_v = max((c.get("visitors", 0) or 0) for c in channels) if channels else 1
        for c in channels:
            v = c.get("visitors", 0) or 0
            table.add_row(
                c.get("channel", "-"),
                num(v),
                _bar(v, max_v),
            )
        console.print(table)
        console.print()

    # Top Pages
    if top_pages:
        table = Table(title="Top Pages", show_header=True, header_style="bold")
        table.add_column("Page", style="cyan", max_width=50)
        table.add_column("Visitors", justify="right")
        table.add_column("Views", justify="right")
        table.add_column("", width=BAR_WIDTH + 2)

        max_v = max((p.get("visitors", 0) or 0) for p in top_pages) if top_pages else 1
        for p in top_pages:
            v = p.get("visitors", 0) or 0
            table.add_row(
                p.get("url_path", "-"),
                num(v),
                num(p.get("pageviews", 0) or 0),
                _bar(v, max_v),
            )
        console.print(table)
        console.print()

    # Top Sources
    if top_referrers:
        table = Table(title="Top Sources", show_header=True, header_style="bold")
        table.add_column("Referrer", style="cyan")
        table.add_column("Visitors", justify="right")
        table.add_column("", width=BAR_WIDTH + 2)

        max_v = max((s.get("visitors", 0) or 0) for s in top_referrers) if top_referrers else 1
        for s in top_referrers:
            v = s.get("visitors", 0) or 0
            table.add_row(
                s.get("referrer_domain", "-"),
                num(v),
                _bar(v, max_v),
            )
        console.print(table)
        console.print()

    # Top Events (with properties)
    if top_events:
        table = Table(title="Top Events", show_header=True, header_style="bold")
        table.add_column("Event", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("", width=BAR_WIDTH + 2)

        max_v = max((e.get("count", 0) or 0) for e in top_events) if top_events else 1
        for e in top_events:
            v = e.get("count", 0) or 0
            table.add_row(
                e.get("event_name", "-"),
                num(v),
                _bar(v, max_v),
            )
        console.print(table)

        # Print event properties inline
        for e in top_events:
            props = e.get("properties", [])
            if props:
                for prop in props[:2]:  # Max 2 keys per event
                    key = prop.get("key", "")
                    values = prop.get("values", [])
                    val_strs = [f"{pv.get('value', '?')} ({pv.get('count', 0)})" for pv in values[:3]]
                    console.print(f"    [dim]{e.get('event_name', '')}.{key}: {', '.join(val_strs)}[/]")
        console.print()


def _print_compact_report(
    site: str,
    period: str,
    current: dict[str, Any],
    previous: dict[str, Any],
    top_pages: list[dict],
    top_referrers: list[dict],
    top_events: list[dict],
    channels: list[dict],
) -> None:
    lines: list[str] = []
    lines.append(f"Report: {site} ({period})")
    lines.append("=" * 40)

    # Overview (2 lines)
    lines.append(
        f"  {num(current.get('pageviews'))} pageviews | "
        f"{num(current.get('visitors'))} visitors | "
        f"{num(current.get('visits'))} visits"
    )
    lines.append(
        f"  {format_percent(current.get('bounce_rate'))} bounce | "
        f"{format_duration(current.get('avg_duration'))} avg duration | "
        f"{current.get('pages_per_visit', 0):.1f} pages/visit"
    )

    # Comparison
    lines.append("")
    lines.append("Comparison vs Previous Period")
    lines.append("-" * 40)
    comp_metrics = [
        ("Pageviews", "pageviews"),
        ("Visitors", "visitors"),
        ("Visits", "visits"),
        ("Bounce Rate", "bounce_rate"),
    ]
    for label, key in comp_metrics:
        delta = pct_change(current.get(key), previous.get(key))
        lines.append(f"  {label}: {delta}")

    # Top Pages
    if top_pages:
        lines.append("")
        lines.append("Top Pages")
        lines.append("-" * 40)
        for p in top_pages[:10]:
            lines.append(
                f"  {p.get('url_path', '-'):<50} "
                f"{num(p.get('visitors')):>10} visitors"
            )

    # Top Sources
    if top_referrers:
        lines.append("")
        lines.append("Top Sources")
        lines.append("-" * 40)
        for s in top_referrers[:10]:
            lines.append(
                f"  {s.get('referrer_domain', '-'):<40} "
                f"{num(s.get('visitors')):>10} visitors"
            )

    # Top Events (with inline properties)
    if top_events:
        lines.append("")
        lines.append("Top Events")
        lines.append("-" * 40)
        for e in top_events:
            lines.append(
                f"  {e.get('event_name', '-'):<40} "
                f"{num(e.get('count')):>10} events"
            )
            props = e.get("properties", [])
            for prop in props[:2]:
                key = prop.get("key", "")
                values = prop.get("values", [])
                val_strs = [f"{pv.get('value', '?')} ({pv.get('count', 0)})" for pv in values[:3]]
                lines.append(f"    {key}: {', '.join(val_strs)}")

    # Channels
    if channels:
        lines.append("")
        lines.append("Channels")
        lines.append("-" * 40)
        for c in channels:
            lines.append(
                f"  {c.get('channel', '-'):<20} "
                f"{num(c.get('visitors')):>10} visitors"
            )

    console.print("\n".join(lines))
