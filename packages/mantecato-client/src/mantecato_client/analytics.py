"""Analytics API endpoint methods for the Mantecato Python SDK.

Provides read-only analytics query methods: overview, pages, events, devices,
geo, compare, and realtime. Date-range endpoints accept aggregate filters and
return parsed JSON response dicts.
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

        Returns stats, time series, top pages, event counts, device breakdowns,
        geo data, heatmap data, and realtime counters.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Full overview data dict with stats, timeseries, top_pages,
            event_metrics, and aggregate breakdowns.

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

        Returns each tracked URL with view count and estimated visitors when
        filters allow anonymous sketch estimates. 50 rows per page.

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
        """Fetch custom event analytics: counts and time series by event name.

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
        """Fetch device dimension breakdowns: browser, OS, and device type.

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``browser``, ``os``, and ``device``.
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
    ) -> dict[str, Any]:
        """Fetch geographic pageview breakdown (country-level only).

        Args:
            website_id: UUID of the tracked website.
            date_range: Shorthand range (e.g. ``"30d"``).
            start: ISO start date.
            end: ISO end date.
            filters: Column-level filter expressions.
            bot_filter: Exclude bot traffic if ``True``.

        Returns:
            Dict with keys ``geo`` (list of country rows) and ``level`` ("country").

        Example::

            geo = client.analytics.geo("uuid", date_range="30d")
        """
        params = self._base_params(website_id, date_range, start, end, filters, bot_filter)
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

    def realtime(self, website_id: str) -> dict[str, Any]:
        """Fetch realtime pageview data: active count, recent rows, current pages.

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
