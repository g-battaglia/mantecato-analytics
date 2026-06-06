"""Analytics API endpoint methods for the Mantecato Python SDK.

Provides read-only analytics query methods: overview, pages, sources, events,
sessions, devices, geo, compare, retention, funnels, journeys, revenue,
engagement, and realtime.  All methods accept date-range and filter parameters
and return parsed JSON response dicts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mantecato_client._client import MantecatoClient


class AnalyticsEndpoints:
    """Read-only analytics query methods.

    Accessed via ``client.analytics`` on a :class:`MantecatoClient` instance.
    All methods return parsed JSON response dicts from the Mantecato API.

    Date ranges can be specified either as a shorthand string (``date_range``)
    or as explicit ISO date strings (``start`` / ``end``).
    """

    def __init__(self, client: MantecatoClient) -> None:
        """Initialize with a reference to the parent client.

        Args:
            client: The :class:`MantecatoClient` instance that owns this
                endpoint group.
        """
        self._client = client

    @staticmethod
    def _base_params(
        website_id: str,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Build the common query parameters shared by all analytics endpoints.

        Args:
            website_id: UUID string of the tracked website.
            date_range: Shorthand range string (e.g. ``"7d"``, ``"30d"``,
                ``"12mo"``).  Mutually exclusive with ``start``/``end``.
            start: ISO date string for the range start (e.g. ``"2024-01-01"``).
            end: ISO date string for the range end (e.g. ``"2024-01-31"``).
            filters: Optional list of filter expressions (e.g.
                ``["country:US", "browser:Chrome"]``).
            bot_filter: If ``True``, exclude bot traffic from results.

        Returns:
            A dict of query parameters ready to pass to ``_get``.
        """
        p: dict[str, Any] = {"website": website_id}
        if date_range:
            p["range"] = date_range
        if start:
            p["start"] = start
        if end:
            p["end"] = end
        if filters:
            p["filter"] = filters
        if bot_filter:
            p["bot_filter"] = "1"
        return p

    def overview(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Fetch the full overview dashboard data for a website.

        Returns stats, time series, top pages, referrers, events, device
        breakdowns, geo data, channel metrics, and realtime counters.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Full overview data dict with stats, timeseries, top_pages,
            top_referrers, top_events, and more.

        Example::

            overview = client.analytics.overview("uuid", date_range="30d")
            print(overview["stats"]["visitors"]["value"])
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        return self._client._get("/api/analytics/overview/", params)

    def pages(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch paginated per-URL page metrics.

        Returns each tracked URL with view count, visitors, average duration,
        bounce rate, entry/exit counts.  50 rows per page.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"7d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.
            page: 1-based page number for pagination.

        Returns:
            ``{"pages": [...], "page": int}`` dict.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        if page is not None:
            params["page"] = page
        return self._client._get("/api/analytics/pages/", params)

    def sources(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Fetch traffic source breakdowns: referrers, UTMs, channels, click IDs, hostnames.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``referrers``, ``channels``, ``utm_source``,
            ``utm_medium``, ``utm_campaign``, ``click_ids``, ``hostnames``.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        return self._client._get("/api/analytics/sources/", params)

    def events(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Fetch custom event analytics: counts, visitors, time series.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``events``, ``total_events``, ``event_types``,
            ``top_event``, ``event_timeseries``.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        return self._client._get("/api/analytics/events/", params)

    def sessions(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a paginated list of individual visitor sessions.

        Each session includes device info, geo location, duration, and
        page-view count.  50 sessions per page.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"7d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.
            page: 1-based page number for pagination.

        Returns:
            ``{"sessions": [...], "page": int}`` dict.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        if page is not None:
            params["page"] = page
        return self._client._get("/api/analytics/sessions/", params)

    def devices(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Fetch device dimension breakdowns: browser, OS, device type, screen, language.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``browser``, ``os``, ``device``, ``screen``,
            ``language``, each containing a list of ``{value, visitors}`` dicts.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        return self._client._get("/api/analytics/devices/", params)

    def geo(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
        country: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        """Fetch geographic visitor breakdown with drill-down support.

        Returns country-level data by default.  Pass ``country`` to drill
        into regions, or both ``country`` and ``region`` for cities.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.
            country: ISO 3166-1 alpha-2 code to drill into (e.g. ``"US"``).
            region: Region name to drill into (requires ``country``).

        Returns:
            Dict with keys ``geo``, ``level``, ``country``, ``region``.

        Example::

            # Country-level
            geo = client.analytics.geo("uuid", date_range="30d")

            # Drill into US regions
            geo = client.analytics.geo("uuid", date_range="30d", country="US")
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        if country:
            params["country"] = country
        if region:
            params["region"] = region
        return self._client._get("/api/analytics/geo/", params)

    def compare(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Fetch current-vs-previous period comparison stats and time series.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.
            mode: Comparison mode -- ``"previous_period"`` (default) or
                ``"previous_year"``.

        Returns:
            Dict with keys ``stats``, ``comparison``, ``comparison_mode``,
            ``current_ts``, ``previous_ts``.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        if mode:
            params["mode"] = mode
        return self._client._get("/api/analytics/compare/", params)

    def retention(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        granularity: str | None = None,
    ) -> dict[str, Any]:
        """Fetch cohort retention analysis data.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"90d"``).
            start: ISO start date.
            end: ISO end date.
            granularity: Cohort bucket size -- ``"week"`` or ``"month"``.

        Returns:
            Dict with keys ``cohorts`` (list of cohort dicts with ``periods``
            retention percentages) and ``granularity``.
        """
        params = self._base_params(website_id, date_range, start, end)
        if granularity:
            params["granularity"] = granularity
        return self._client._get("/api/analytics/retention/", params)

    def funnels(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        steps: list[tuple[str, str]] | None = None,
        window: int | None = None,
    ) -> dict[str, Any]:
        """Fetch multi-step funnel conversion analysis.

        Steps are encoded as indexed query parameters (``step_type.0``,
        ``step_value.0``, ``step_type.1``, etc.) for the API.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            steps: Ordered list of ``(type, value)`` tuples where type is
                ``"url"`` or ``"event"`` and value is the path or event name.
            window: Maximum minutes between first and last step.

        Returns:
            Dict with keys ``funnel_steps`` and ``steps_config``.

        Example::

            result = client.analytics.funnels(
                "uuid",
                date_range="30d",
                steps=[("url", "/"), ("url", "/pricing"), ("url", "/signup")],
                window=60,
            )
        """
        params = self._base_params(website_id, date_range, start, end)
        if steps:
            # Encode each step as indexed query params for the API
            for i, (step_type, step_value) in enumerate(steps):
                params[f"step_type.{i}"] = step_type
                params[f"step_value.{i}"] = step_value
        if window is not None:
            params["window"] = window
        return self._client._get("/api/analytics/funnels/", params)

    def journeys(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        path_length: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Fetch user journey paths with Sankey diagram data.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            path_length: Number of steps per journey path (default 3).
            limit: Maximum number of journey paths to retrieve.

        Returns:
            Dict with keys ``journeys``, ``sankey`` (node/link data for
            D3-sankey rendering), ``mode``, and ``conversions``.
        """
        params = self._base_params(website_id, date_range, start, end)
        if path_length is not None:
            params["path_length"] = path_length
        if limit is not None:
            params["limit"] = limit
        return self._client._get("/api/analytics/journeys/", params)

    def revenue(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Fetch revenue analytics: summary, time series, by-event, by-country.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.

        Returns:
            Dict with keys ``summary``, ``time_series``, ``by_event``,
            ``by_country``, ``revenue_chart_data``, ``event_chart_data``.
        """
        params = self._base_params(website_id, date_range, start, end)
        return self._client._get("/api/analytics/revenue/", params)

    def engagement(
        self,
        website_id: str,
        *,
        date_range: str | None = None,
        start: str | None = None,
        end: str | None = None,
        filters: list[str] | None = None,
        bot_filter: bool = False,
    ) -> dict[str, Any]:
        """Fetch engagement metrics: duration distribution, percentiles, bounce rates.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``distribution``, ``percentiles``,
            ``duration_by_page``, ``bounce_by_page``, ``bounce_by_source``,
            ``distribution_chart_data``, ``bounce_chart_data``.
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
        return self._client._get("/api/analytics/engagement/", params)

    def realtime(self, website_id: str) -> dict[str, Any]:
        """Fetch realtime visitor data: active count, recent events, current pages.

        Unlike other analytics methods, this endpoint does not accept date
        range parameters -- it always returns data for the live window
        (last 5 minutes).

        Args:
            website_id: UUID of the tracked website.

        Returns:
            Dict with keys ``active`` (int), ``recent_events`` (list),
            ``current_pages`` (list).
        """
        return self._client._get("/api/analytics/realtime/", {"website": website_id})
