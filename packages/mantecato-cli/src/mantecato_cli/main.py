"""Remote Mantecato command-line interface."""

# Typer declares options through function-call defaults by design.
# ruff: noqa: B008

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003  Typer resolves this runtime annotation
from typing import Any

import typer

from mantecato_cli import __version__
from mantecato_cli._http import ApiTransport
from mantecato_cli.config import (
    UserConfig,
    resolve_client_config,
    segment_filters,
)
from mantecato_cli.errors import CliError, UsageError
from mantecato_cli.output import render

app = typer.Typer(
    name="mantecato",
    help="Remote CLI for a Mantecato instance. Uses HTTPS and an API key.",
    no_args_is_help=True,
    invoke_without_command=True,
)


def _website_option() -> Any:
    return typer.Option(..., "--website", "-w", help="Website UUID")


def _range_option() -> Any:
    return typer.Option("30d", "--range", "-r", help="Date range preset")


def _start_option() -> Any:
    return typer.Option(None, "--start", help="ISO-8601 start boundary")


def _end_option() -> Any:
    return typer.Option(None, "--end", help="Exclusive ISO-8601 end boundary")


def _timezone_option() -> Any:
    return typer.Option("UTC", "--timezone", help="IANA timezone")


def _filter_option() -> Any:
    return typer.Option(None, "--filter", help="Repeat column:operator:value")


def _segment_option() -> Any:
    return typer.Option(None, "--segment", help="Named filter segment")


def _limit_option() -> Any:
    return typer.Option(50, "--limit", "-l", min=1, max=500)


def _format_option() -> Any:
    return typer.Option("table", "--format", help="table, json, or csv")


@dataclass
class AppState:
    url: str | None
    key_file: Path | None
    profile: str | None
    config_path: Path | None
    timeout: float
    _transport: ApiTransport | None = None
    _user_config: UserConfig | None = None

    def connect(self) -> tuple[ApiTransport, UserConfig]:
        if self._transport is None or self._user_config is None:
            config, user = resolve_client_config(
                url=self.url,
                key_file=self.key_file,
                profile=self.profile,
                config_path=self.config_path,
                timeout=self.timeout,
            )
            self._transport = ApiTransport(config)
            self._user_config = user
        return self._transport, self._user_config

    def close(self) -> None:
        if self._transport:
            self._transport.close()


@app.callback()
def root(
    ctx: typer.Context,
    url: str | None = typer.Option(None, "--url", envvar="MANTECATO_URL"),
    key_file: Path | None = typer.Option(None, "--key-file", envvar="MANTECATO_API_KEY_FILE"),
    profile: str | None = typer.Option(None, "--profile"),
    config: Path | None = typer.Option(None, "--config"),
    timeout: float = typer.Option(30.0, "--timeout", min=0.1),
    version: bool = typer.Option(False, "--version", is_eager=True),
) -> None:
    """Configure connection options without opening the network."""
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)
    state = AppState(url, key_file, profile, config, timeout)
    ctx.obj = state
    ctx.call_on_close(state.close)


@app.command("schema")
def schema_cmd(format: str = typer.Option("json", "--format")) -> None:
    """Print the client-side v1 request outline without network access."""
    _print(
        {
            "schema_version": "1",
            "transport": "https",
            "authentication": "Authorization: Bearer mtk_...",
            "operations": ["query", "compare", "traffic_quality", "dimension_values"],
            "note": "Use capabilities to inspect the connected server's exact schema.",
        },
        format,
    )


@app.command("capabilities")
def capabilities_cmd(ctx: typer.Context, format: str = typer.Option("json", "--format")) -> None:
    """Describe operations supported by the connected server."""
    _request(ctx, format, lambda api, _user: api.get("/api/v1/capabilities/"))


@app.command("sites")
def sites_cmd(ctx: typer.Context, format: str = typer.Option("table", "--format")) -> None:
    """List websites accessible to the API key."""
    _request(ctx, format, lambda api, _user: api.get("/api/sites/"))


@app.command("doctor")
def doctor_cmd(ctx: typer.Context, format: str = typer.Option("table", "--format")) -> None:
    """Check local configuration, authentication, and API v1 support."""

    def check(api: ApiTransport, _user: UserConfig) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        try:
            sites = api.get("/api/sites/")
            checks.append(
                {
                    "check": "authentication",
                    "status": "pass",
                    "detail": f"{len(sites.get('websites', []))} accessible site(s)",
                }
            )
        except CliError as exc:
            checks.append({"check": "authentication", "status": "fail", "detail": str(exc)})
            return {"schema_version": "1", "rows": checks, "ok": False}
        try:
            capabilities = api.get("/api/v1/capabilities/")
            checks.append(
                {
                    "check": "api_v1",
                    "status": "pass",
                    "detail": f"schema {capabilities.get('schema_version')}",
                }
            )
        except CliError as exc:
            checks.append({"check": "api_v1", "status": "fail", "detail": str(exc)})
        return {
            "schema_version": "1",
            "rows": checks,
            "ok": all(item["status"] == "pass" for item in checks),
        }

    _request(ctx, format, check, fail_on_not_ok=True)


@app.command("query")
def query_cmd(
    ctx: typer.Context,
    input: Path | None = typer.Option(None, "--input", help="JSON file; use - for stdin"),
    format: str = typer.Option("json", "--format"),
) -> None:
    """Execute a complete API v1 query supplied as JSON."""
    if input is None:
        raise typer.BadParameter("--input is required")
    try:
        text = sys.stdin.read() if str(input) == "-" else input.read_text(encoding="utf-8")
        body = json.loads(text)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(f"Cannot read query JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise typer.BadParameter("Query JSON must be an object")
    _request(ctx, format, lambda api, _user: api.post("/api/v1/analytics/query/", body))


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    format: str = _format_option(),
) -> None:
    """Return numeric site totals."""
    payload = _payload(website, range, start, end, timezone, filter, segment)
    payload["metrics"] = _pageview_metrics()
    _v1_query(ctx, payload, format)


@app.command("overview")
def overview_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    format: str = _format_option(),
) -> None:
    """Alias for numeric overview totals."""
    payload = _payload(website, range, start, end, timezone, filter, segment)
    payload["metrics"] = _pageview_metrics()
    _v1_query(ctx, payload, format)


@app.command("timeseries")
def timeseries_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    granularity: str = typer.Option("day", "--granularity", "-g"),
    dimension: list[str] | None = typer.Option(None, "--dimension"),
    metric: list[str] | None = typer.Option(None, "--metric"),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    exclude_partial_bucket: bool = typer.Option(False, "--exclude-partial-bucket"),
    format: str = _format_option(),
) -> None:
    """Return a time series, optionally grouped by dimensions."""
    payload = _payload(website, range, start, end, timezone, filter, segment)
    payload.update(
        {
            "operation": "timeseries",
            "granularity": granularity,
            "dimensions": _split_values(dimension),
            "metrics": _split_values(metric) or ["pageviews", "daily_unique_visitors", "visits"],
            "limit": limit,
            "include_partial_bucket": not exclude_partial_bucket,
        }
    )
    _v1_query(ctx, payload, format)


@app.command("top-pages")
@app.command("pages")
def top_pages_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank pages by pageviews."""
    _breakdown(
        ctx, website, "url_path", range, start, end, timezone, filter, segment, limit, format
    )


@app.command("top-sections")
def top_sections_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    depth: int = typer.Option(2, "--depth", min=1, max=6),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank URL sections by pageviews."""
    payload = _breakdown_payload(
        website, "section", range, start, end, timezone, filter, segment, limit
    )
    payload["section_depth"] = depth
    _v1_query(ctx, payload, format)


@app.command("top-groups")
def top_groups_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    group_prefix: str | None = typer.Option(None, "--group-prefix"),
    group_exact: str | None = typer.Option(None, "--group-exact"),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank overlapping site-declared content groups."""
    payload = _breakdown_payload(
        website, "content_group", range, start, end, timezone, filter, segment, limit
    )
    payload["dimension_prefix"] = group_prefix
    payload["dimension_exact"] = group_exact
    _v1_query(ctx, payload, format)


@app.command("events")
def events_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    start: str | None = _start_option(),
    end: str | None = _end_option(),
    timezone: str = _timezone_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank custom event names."""
    payload = _breakdown_payload(
        website, "event_name", range, start, end, timezone, filter, segment, limit
    )
    payload.update({"dataset": "events", "metrics": ["events", "daily_unique_visitors"]})
    _v1_query(ctx, payload, format)


@app.command("devices")
def devices_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    dimension: str = typer.Option("device", "--dimension", help="device, browser, or os"),
    range: str = _range_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank device, browser, or operating-system values."""
    if dimension not in ("device", "browser", "os"):
        raise typer.BadParameter("dimension must be device, browser, or os")
    _breakdown(ctx, website, dimension, range, None, None, "UTC", filter, segment, limit, format)


@app.command("geo")
def geo_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank country-level traffic."""
    _breakdown(ctx, website, "country", range, None, None, "UTC", filter, segment, limit, format)


@app.command("sources")
def sources_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Rank referrer domains; null values are labelled direct."""
    _breakdown(
        ctx,
        website,
        "referrer_domain",
        range,
        None,
        None,
        "UTC",
        filter,
        segment,
        limit,
        format,
    )


@app.command("event-timeseries")
def event_timeseries_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    event: str = typer.Option(..., "--event"),
    range: str = _range_option(),
    granularity: str = typer.Option("day", "--granularity", "-g"),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    format: str = _format_option(),
) -> None:
    """Return the time series for one custom event name."""
    payload = _payload(website, range, None, None, "UTC", filter, segment)
    payload.update(
        {
            "operation": "timeseries",
            "dataset": "events",
            "granularity": granularity,
            "dimensions": ["event_name"],
            "metrics": ["events", "daily_unique_visitors"],
            "filters": [*(filter or []), f"event_name:eq:{event}"],
        }
    )
    _v1_query(ctx, payload, format)


@app.command("filter-values")
def filter_values_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    dimension: str = typer.Option(..., "--dimension", "--column"),
    range: str = _range_option(),
    search: str | None = typer.Option(None, "--search"),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Discover bounded values for one dimension."""

    def call(api: ApiTransport, user: UserConfig) -> Any:
        payload = _payload(website, range, None, None, "UTC", filter, segment, user=user)
        payload.update({"dimension": dimension, "search": search, "limit": limit})
        return api.post("/api/v1/analytics/dimension-values/", payload)

    _request(ctx, format, call)


@app.command("compare-breakdown")
@app.command("compare")
def compare_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    dimension: str = typer.Option("country", "--dimension"),
    metric: str = typer.Option("pageviews", "--metric"),
    range: str = _range_option(),
    start: str | None = typer.Option(None, "--start", "--current-start"),
    end: str | None = typer.Option(None, "--end", "--current-end"),
    previous_start: str | None = typer.Option(None, "--previous-start", "--compare-start"),
    previous_end: str | None = typer.Option(None, "--previous-end", "--compare-end"),
    compare: str = typer.Option("previous_period", "--compare", "--mode"),
    align: str = typer.Option("full", "--align"),
    direction: str = typer.Option("both", "--direction"),
    sort: str = typer.Option("absolute_change", "--sort"),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Compare complete dimension sets before ranking."""

    def call(api: ApiTransport, user: UserConfig) -> Any:
        payload = _payload(website, range, start, end, "UTC", filter, segment, user=user)
        payload.update(
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
        return api.post("/api/v1/analytics/compare/", payload)

    _request(ctx, format, call)


@app.command("traffic-quality")
def traffic_quality_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    dimension: str = typer.Option("country", "--dimension"),
    range: str = _range_option(),
    compare: str | None = typer.Option(None, "--compare"),
    filter: list[str] | None = _filter_option(),
    segment: list[str] | None = _segment_option(),
    limit: int = _limit_option(),
    format: str = _format_option(),
) -> None:
    """Inspect traffic measures and transparent anomaly indicators."""

    def call(api: ApiTransport, user: UserConfig) -> Any:
        payload = _payload(website, range, None, None, "UTC", filter, segment, user=user)
        payload.update({"dimensions": [dimension], "compare": compare, "limit": limit})
        return api.post("/api/v1/analytics/traffic-quality/", payload)

    _request(ctx, format, call)


@app.command("heatmap")
def heatmap_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    range: str = _range_option(),
    filter: list[str] | None = _filter_option(),
    format: str = _format_option(),
) -> None:
    """Return the existing dashboard traffic heatmap."""

    def call(api: ApiTransport, _user: UserConfig) -> Any:
        response = api.get(
            "/api/analytics/overview/",
            params={"website": website, "range": range, "filter": filter or []},
        )
        return {
            "schema_version": "legacy",
            "query": {"website_id": website, "range": range, "filters": filter or []},
            "comparison": None,
            "totals": {},
            "rows": response.get("heatmap", []),
        }

    _request(ctx, format, call)


@app.command("realtime")
def realtime_cmd(
    ctx: typer.Context,
    website: str = _website_option(),
    format: str = _format_option(),
) -> None:
    """Return the existing server realtime response."""
    _request(
        ctx,
        format,
        lambda api, _user: api.get("/api/analytics/realtime/", params={"website": website}),
    )


def _request(
    ctx: typer.Context,
    fmt: str,
    call: Any,
    *,
    fail_on_not_ok: bool = False,
) -> None:
    try:
        api, user = _state(ctx).connect()
        result = call(api, user)
        _print(result, fmt)
        if fail_on_not_ok and isinstance(result, dict) and not result.get("ok", True):
            raise typer.Exit(1)
    except CliError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(exc.exit_code) from exc


def _v1_query(ctx: typer.Context, payload: dict[str, Any], fmt: str) -> None:
    def call(api: ApiTransport, user: UserConfig) -> Any:
        _apply_segments(payload, user)
        return api.post("/api/v1/analytics/query/", payload)

    _request(ctx, fmt, call)


def _breakdown(
    ctx: typer.Context,
    website: str,
    dimension: str,
    range: str,
    start: str | None,
    end: str | None,
    timezone: str,
    filters: list[str] | None,
    segments: list[str] | None,
    limit: int,
    fmt: str,
) -> None:
    _v1_query(
        ctx,
        _breakdown_payload(
            website, dimension, range, start, end, timezone, filters, segments, limit
        ),
        fmt,
    )


def _breakdown_payload(
    website: str,
    dimension: str,
    range: str,
    start: str | None,
    end: str | None,
    timezone: str,
    filters: list[str] | None,
    segments: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    payload = _payload(website, range, start, end, timezone, filters, segments)
    payload.update(
        {
            "operation": "breakdown",
            "dimensions": [dimension],
            "metrics": ["pageviews", "daily_unique_visitors", "visits"],
            "limit": limit,
        }
    )
    return payload


def _payload(
    website: str,
    range: str,
    start: str | None,
    end: str | None,
    timezone: str,
    filters: list[str] | None,
    segments: list[str] | None,
    *,
    user: UserConfig | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "website_id": website,
        "range": range,
        "timezone": timezone,
        "filters": filters or [],
        "_segments": segments or [],
    }
    if start is not None or end is not None:
        payload["start"], payload["end"] = start, end
    if user is not None:
        _apply_segments(payload, user)
    return payload


def _apply_segments(payload: dict[str, Any], user: UserConfig) -> None:
    names = payload.pop("_segments", [])
    groups = segment_filters(user, names)
    if groups:
        payload["filter_groups"] = groups


def _pageview_metrics() -> list[str]:
    return [
        "pageviews",
        "daily_unique_visitors",
        "visits",
        "bounces",
        "bounce_rate",
        "total_duration",
        "average_visit_duration",
        "pages_per_visit",
        "human_pageviews",
        "bot_pageviews",
    ]


def _split_values(values: list[str] | None) -> list[str]:
    return [part.strip() for value in (values or []) for part in value.split(",") if part.strip()]


def _print(data: Any, fmt: str) -> None:
    typer.echo(render(data, fmt))


def _state(ctx: typer.Context) -> AppState:
    if not isinstance(ctx.obj, AppState):
        raise UsageError("CLI state is unavailable.")
    return ctx.obj


if __name__ == "__main__":
    app()
