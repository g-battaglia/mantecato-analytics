"""HTMX partial views — lightweight fragments returned inside the analytics pages.

Unlike full-page views (see :mod:`apps.analytics.views`), partials never render
a complete HTML document.  They return small HTML snippets that HTMX swaps into
an already-loaded page — think drill-down tables, tab contents, live-updating
counters.  Separating them into their own module keeps the page-level views
clean and makes it immediately obvious which endpoints are "internal" HTMX
plumbing vs user-navigable pages.

Architecture
~~~~~~~~~~~~

All concrete partials inherit from :class:`_HtmxPartialBase`, which applies the
**Template Method** pattern:

1. Validate that the request carries a resolved ``website_id``.
2. Optionally validate that ``date_range`` is present.
3. Optionally require a named GET parameter (e.g. ``?url_path=/about``).
4. Delegate the actual data-fetching to the subclass's
   :meth:`get_partial_data` hook.
5. Render the partial template with the returned context dict.

The only exception is :class:`OverviewTabView`, which uses the
``_OVERVIEW_TABS`` **Registry pattern** to select both its template and its
data-fetcher from a single dict keyed by ``?tab=<key>``.

URL → Partial map (routed in ``apps/analytics/urls.py``):

============================================ ===================================
URL pattern                                   View
============================================ ===================================
``GET  /overview/tab/``                       :class:`OverviewTabView`
``GET  /pages/next/``                         :class:`NextPagesView`
``GET  /sessions/activity/``                  :class:`SessionActivityView`
``GET  /events/properties/``                  :class:`EventPropertiesView`
``GET  /engagement/bucket/``                  :class:`EngagementBucketDetailView`
``GET  /engagement/time-on-page/``            :class:`TimeOnPageDetailView`
``GET  /journeys/section-detail/``            :class:`JourneySectionDetailView`
``GET  /realtime/partial/``                   :class:`RealtimePartialView`
============================================ ===================================

All service functions are imported at module level so test patches on
``apps.analytics.partials.<fn>`` remain effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from apps.analytics.services import (
    get_engagement_bucket_data,
    get_event_properties_data,
    get_journey_section_detail_data,
    get_next_pages_data,
    get_overview_tab_devices,
    get_overview_tab_events,
    get_overview_tab_geo,
    get_overview_tab_pages,
    get_overview_tab_referrers,
    get_overview_tab_sources,
    get_realtime_data,
    get_session_activity_data,
    get_time_on_page_data,
    resolve_websites_for_user,  # noqa: F401  — imported so tests can patch it here
)
from apps.common.mixins import (
    DateRangeMixin,
    FiltersMixin,
    WebsiteContextMixin,
)
from core.mantecato_core.queries.filter_values import get_filter_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest


# ============================================================================
# Base class — Template Method for all HTMX partials
# ============================================================================


class _HtmxPartialBase(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    View,
):
    """Abstract base for HTMX partial views (Template Method pattern).

    The ``get()`` method encodes the shared validation logic once:
    check that a website is selected, optionally check that a date range
    is resolved, and optionally require a specific GET parameter to be
    present.  Subclasses only need to set class-level attributes and
    override :meth:`get_partial_data` with the actual data-fetch.

    Attributes:
        template_name: Path to the partial template (e.g.
            ``"analytics/_next_pages.html"``).  Must start with ``_``
            by project convention for partial templates.
        required_param: Name of a GET parameter that must be non-empty
            for the partial to render.  Set to ``None`` (default) when
            the partial doesn't depend on a specific entity.
        require_date_range: When ``True`` (default), the partial returns
            an empty response if no date range could be resolved from the
            query string.  Set to ``False`` for partials that don't need
            temporal filtering (e.g. session activity).
    """

    template_name: str
    required_param: str | None = None
    require_date_range: bool = True

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate context, delegate to ``get_partial_data``, render the partial.

        Returns an empty ``HttpResponse("")`` whenever the required context
        is missing.  This is intentional: HTMX silently ignores empty swap
        responses, so the user sees no visible change — which is the correct
        UX when the partial can't render meaningful content.
        """
        # Without a website, no analytics data can be queried at all
        if not self.website_id:
            return HttpResponse("")

        # Most partials operate within a date window; skip if not resolved
        if self.require_date_range and not self.date_range:
            return HttpResponse("")

        # If the partial needs a specific entity (URL, event name, etc.),
        # extract it from the query string and bail if absent
        param_value: str | None = None
        if self.required_param:
            param_value = request.GET.get(self.required_param, "")
            if not param_value:
                return HttpResponse("")

        ctx = self.get_partial_data(request, param_value)
        return render(request, self.template_name, ctx)

    def get_partial_data(
        self,
        request: HttpRequest,
        param_value: str | None,
    ) -> dict:
        """Fetch data from the service layer and return the template context.

        Subclasses MUST override this method.  The base implementation
        returns an empty dict so a misconfigured subclass renders a blank
        partial rather than crashing.

        Args:
            request: The current HTTP request (available for reading
                additional GET parameters if needed).
            param_value: The resolved value of ``required_param``, or
                ``None`` if ``required_param`` is not set.

        Returns:
            A dict that is passed directly to ``render()`` as the template
            context.  The partial template receives *only* these keys (no
            base context from ``BaseContextMixin``).
        """
        return {}


# ============================================================================
# Overview tab registry — Registry pattern for the overview sub-tabs
# ============================================================================
#
# The overview page uses a tabbed layout where each tab body is loaded via
# HTMX from ``/overview/tab/?tab=<key>``.  Instead of maintaining two parallel
# dicts (one for templates, one for fetchers) that must stay in sync, we use
# a single registry keyed by tab name.  Adding a new tab = adding one line.
# ============================================================================


class _TabConfig(NamedTuple):
    """Pair of (template_path, data_fetcher) for one overview tab.

    Bundling both in a NamedTuple makes it impossible to add a template
    without its fetcher (or vice versa) — the two stay in sync by
    construction.
    """

    template: str
    fetcher: Callable


_OVERVIEW_TABS: dict[str, _TabConfig] = {
    "pages": _TabConfig("analytics/_tab_pages.html", get_overview_tab_pages),
    "referrers": _TabConfig("analytics/_tab_referrers.html", get_overview_tab_referrers),
    "events": _TabConfig("analytics/_tab_events.html", get_overview_tab_events),
    "devices": _TabConfig("analytics/_tab_devices.html", get_overview_tab_devices),
    "geo": _TabConfig("analytics/_tab_geo.html", get_overview_tab_geo),
    "sources": _TabConfig("analytics/_tab_sources.html", get_overview_tab_sources),
}


# ============================================================================
# Concrete partials
# ============================================================================


class OverviewTabView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    View,
):
    """HTMX partial — renders a single tab body fragment of the overview page.

    The ``?tab=`` parameter selects which overview sub-section to render
    (pages, referrers, events, devices, geo, sources).  Unknown tab keys
    silently fall back to ``"pages"`` — the safest default and the one the
    overview template shows on first load.

    This view does NOT extend ``_HtmxPartialBase`` because its template is
    dynamically selected from the registry rather than being a fixed
    class attribute.
    """

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not self.website_id or not self.date_range:
            return HttpResponse("")

        tab = request.GET.get("tab", "pages")
        # Fall back to "pages" for unknown tab keys instead of raising
        config = _OVERVIEW_TABS.get(tab, _OVERVIEW_TABS["pages"])
        data = config.fetcher(self.website_id, self.date_range, self.filters)
        return render(request, config.template, {"active_tab": tab, **data})


class NextPagesView(_HtmxPartialBase):
    """HTMX partial — pages visitors navigate to after a given URL.

    Triggered when a user clicks a row in the pages table; shows a drill-down
    of subsequent page transitions for the selected ``url_path``.
    """

    template_name = "analytics/_next_pages.html"
    required_param = "url_path"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_next_pages_data(self.website_id, param_value, self.date_range)


class SessionActivityView(_HtmxPartialBase):
    """HTMX partial — event timeline for a single session.

    Shows every pageview and custom event recorded during a session, in
    chronological order.  Does not require a date range because a session
    is identified by its ID regardless of when it occurred.
    """

    template_name = "analytics/_session_activity.html"
    required_param = "session_id"
    require_date_range = False

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_session_activity_data(param_value, self.website_id)


class EventPropertiesView(_HtmxPartialBase):
    """HTMX partial — property breakdown and time series for a named event.

    Triggered by clicking an event row on the Events page; shows the custom
    properties (key/value pairs) attached to that event type, plus a small
    sparkline chart of the event's frequency over the selected date range.
    """

    template_name = "analytics/_event_properties.html"
    required_param = "event_name"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_event_properties_data(self.website_id, param_value, self.date_range)


class EngagementBucketDetailView(_HtmxPartialBase):
    """HTMX partial — sessions that fall within a specific duration bucket.

    The engagement page shows a duration-distribution histogram.  Clicking a
    bucket bar opens this drill-down with the actual sessions whose duration
    matches the bucket range (e.g. "30s–1m").
    """

    template_name = "analytics/_engagement_bucket.html"
    required_param = "bucket"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_engagement_bucket_data(
            self.website_id,
            self.date_range,
            param_value,
            filters=self.filters,
        )


class TimeOnPageDetailView(_HtmxPartialBase):
    """HTMX partial — time-on-page distribution for a specific URL.

    Shows how long visitors spend on a given page, broken into duration
    buckets with percentage bars.  Triggered from the duration-by-page table
    on the engagement page.
    """

    template_name = "analytics/_time_on_page.html"
    required_param = "url_path"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_time_on_page_data(self.website_id, param_value, self.date_range)


class JourneySectionDetailView(_HtmxPartialBase):
    """HTMX partial — top pages within a site section prefix.

    The journeys page groups navigation by URL section (e.g. ``/blog/``,
    ``/docs/``).  Clicking a section node in the Sankey diagram opens this
    drill-down showing the most-visited individual pages under that prefix.
    """

    template_name = "analytics/_journey_section_detail.html"
    required_param = "section"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return get_journey_section_detail_data(
            self.website_id,
            param_value,
            self.date_range,
        )


class RealtimePartialView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    View,
):
    """HTMX partial — realtime data refreshed by a polling loop.

    The realtime page includes an ``hx-trigger="every 5s"`` on its data
    container.  Each poll hits this endpoint, which returns the latest
    active-visitor count, recent events, and current pages.

    This view does NOT extend ``_HtmxPartialBase`` because it doesn't need
    ``required_param`` or ``require_date_range`` — it only needs a website.
    """

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not self.website_id:
            return HttpResponse("")
        return render(
            request,
            "analytics/_realtime_data.html",
            {"selected_website": self.website_id, **get_realtime_data(self.website_id)},
        )


class FilterValuesView(_HtmxPartialBase):
    """HTMX partial — distinct values for a column, powering the filter typeahead.

    Backs the value ``<datalist>`` in the "Add filter" popover.  Given a
    ``?column=`` (validated against the query engine's whitelist) and an
    optional ``?search=`` substring, returns up to 20 matching distinct
    values for the current website + date range as ``<option>`` tags.

    ``column`` reuses ``required_param`` so the base class returns an empty
    response when it is missing; :func:`get_filter_values` itself returns an
    empty list for any column outside its whitelist, so an invalid column
    renders no options rather than erroring.
    """

    template_name = "analytics/_filter_values.html"
    required_param = "column"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        search = request.GET.get("search", "").strip() or None
        values = get_filter_values(
            self.website_id,
            param_value,
            self.date_range.start_date,
            self.date_range.end_date,
            search=search,
            limit=20,
        )
        return {"values": values}
