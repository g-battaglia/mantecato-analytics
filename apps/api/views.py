"""JSON API views — class-based, DRF-free.

All endpoints authenticate via the ``Authorization: Bearer mtk_...`` header
(see :class:`mantecato.middleware.ApiKeyMiddleware`) and respond with JSON
through :func:`apps.common.json_views.json_response` (the same sanitiser
used everywhere else in the project).

Two abstract base classes drive the design:

- :class:`_AnalyticsJSONView` — read-only endpoints that need
  ``(website_id, date_range, filters)`` and call exactly one service
  function. Subclasses set :attr:`service_fn` and (optionally) override
  :meth:`extra_kwargs` to inject endpoint-specific query params.
- Per-resource CRUD subclasses of :class:`JSONListView` / :class:`JSONFormView` /
  :class:`JSONDeleteView` from :mod:`apps.common.json_views`, customised
  through the same ``ApiAuthMixin`` / ``ApiWriteMixin`` MRO used by the
  rest of the project.

Service functions are imported by name so existing tests can keep
patching ``apps.api.views.X``; the views call them as bare module
attributes, which the test patches replace at runtime.

URL → View map lives in :mod:`apps.api.urls`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.http import JsonResponse  # noqa: TC002  used at runtime in helpers below

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest

from apps.analytics.services import (
    # The ``get_*_data`` functions below are looked up dynamically by
    # ``_AnalyticsJSONView._resolve_service`` via ``sys.modules``, so they
    # must remain bound to this module even though no direct call site
    # references them.
    get_compare_data,  # noqa: F401
    get_devices_data,  # noqa: F401
    get_events_data,  # noqa: F401
    get_geo_data,  # noqa: F401
    get_overview_data,  # noqa: F401
    get_pages_data,  # noqa: F401
    get_realtime_data,
    resolve_websites_for_user,
)
from apps.common.http import safe_int
from apps.common.json_views import JSONView, json_response
from apps.common.mixins import (
    ApiAuthMixin,
    ApiWriteMixin,
    DateRangeMixin,
    FiltersMixin,
    GranularityMixin,
    WebsiteContextMixin,
)
from apps.dashboards.services import (
    create_new_dashboard,
    get_dashboard_detail,
    get_dashboards_for_user,
    remove_dashboard,
    update_existing_dashboard,
)
from apps.settings_app.services import (
    generate_new_api_key,
    get_api_keys_for_user,
    get_bot_config,
    remove_api_key,
    save_bot_config,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


# ============================================================================
# Helpers: request body parsing + canned error responses
# ============================================================================


def _parse_json_body(request: HttpRequest) -> tuple[dict[str, Any] | None, JsonResponse | None]:
    """Parse a JSON request body, returning a dict on success or a 400 error response.

    Handles the common pattern of extracting a JSON body from POST requests
    used by all write endpoints in the API. An empty body is valid and returns
    an empty dict (to support endpoints where all fields are optional).

    Args:
        request: The incoming HTTP request whose ``body`` attribute is parsed.

    Returns:
        A 2-tuple ``(body_dict, error_response)``. Exactly one element is
        ``None``: on success ``error_response`` is ``None``; on parse failure
        ``body_dict`` is ``None`` and ``error_response`` is a 400 JSON response
        with an ``{"error": ...}`` payload.
    """
    if not request.body:
        return {}, None
    try:
        import json

        return json.loads(request.body), None
    except (ValueError, UnicodeDecodeError):
        return None, json_response({"error": "Invalid JSON body."}, status=400)


def _no_website() -> JsonResponse:
    """Return a 400 JSON error response when no website ID was supplied or resolved.

    Returns:
        A ``JsonResponse`` with status 400 and body
        ``{"error": "No accessible website found."}``.
    """
    return json_response({"error": "No accessible website found."}, status=400)


def _forbidden_website() -> JsonResponse:
    """Return a 403 JSON error response when the API user lacks access to the requested website.

    Returns:
        A ``JsonResponse`` with status 403 and body
        ``{"error": "Website not accessible."}``.
    """
    return json_response({"error": "Website not accessible."}, status=403)


def _website_accessible(request: HttpRequest, website_id: str) -> bool:
    """Check whether the authenticated API user has access to a specific website.

    Admin-scoped API keys can access all websites; regular keys are limited to
    websites the owning user has been granted membership to. The check is
    performed by resolving the full list of accessible websites and testing
    set membership, which is acceptable because the website list is small.

    Args:
        request: The authenticated HTTP request. Must have ``api_user_id``
            and ``api_key_scopes`` attributes set by
            :class:`~mantecato.middleware.ApiKeyMiddleware`.
        website_id: The UUID string of the website to check access for.

    Returns:
        ``True`` if *website_id* is in the set of websites accessible to the
        API user, ``False`` otherwise (including when *website_id* is empty).
    """
    if not website_id:
        return False
    # Admin-scoped keys bypass per-user website restrictions
    is_admin = "admin" in getattr(request, "api_key_scopes", [])
    websites = resolve_websites_for_user(request.api_user_id, is_admin=is_admin)
    return website_id in {w["id"] for w in websites}


# ============================================================================
# Sites
# ============================================================================


class SitesListView(ApiAuthMixin, JSONView):
    """``GET /api/sites/`` -- list websites accessible to the API user.

    Authentication:
        Requires a valid ``Authorization: Bearer mtk_...`` header.

    Response:
        200 JSON with ``{"websites": [{"id": "<uuid>", "name": "...",
        "domain": "...", ...}, ...]}``. Admin-scoped keys see all websites;
        regular keys see only those the owning user is a member of.
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Return the list of websites the authenticated API user can access."""
        is_admin = "admin" in getattr(request, "api_key_scopes", [])
        websites = resolve_websites_for_user(request.api_user_id, is_admin=is_admin)
        return json_response({"websites": websites})


# ============================================================================
# Analytics read endpoints
# ============================================================================


class _AnalyticsJSONView(ApiAuthMixin, WebsiteContextMixin, DateRangeMixin, GranularityMixin, FiltersMixin, JSONView):
    """Base for analytics ``GET`` endpoints needing website + date range.

    Subclasses define:

    Attributes:
        service_name (str): name of the service function exposed on this
            module. Looking up via ``sys.modules`` rather than a staticmethod
            keeps the function late-bound, so test patches on
            ``apps.api.views.<service_name>`` apply transparently.
        pass_filters (bool, optional, default ``True``): when ``False`` the
            view drops ``self.filters`` from the call signature.

    Override :meth:`extra_kwargs` to inject endpoint-specific query
    parameters (``page``, ``country``, ``granularity``, ...).
    """

    service_name: str = ""
    pass_filters: bool = True
    http_method_names = ("get",)

    def extra_kwargs(self, request: HttpRequest) -> dict[str, Any]:
        """Return endpoint-specific kwargs to forward to the service function.

        Override in subclasses to extract additional query parameters (e.g.
        ``page``, ``country``, ``granularity``) from the request and pass
        them to the service function as keyword arguments.

        Args:
            request: The incoming HTTP request to extract params from.

        Returns:
            A dict of keyword arguments merged into the service function call.
            Defaults to an empty dict.
        """
        return {}

    def _resolve_service(self) -> Callable[..., Any]:
        """Look up the service function by name on this module at call time.

        Uses ``sys.modules`` for late binding so that test patches applied to
        ``apps.api.views.<service_name>`` take effect transparently without
        needing to reload the module.

        Returns:
            The callable service function.

        Raises:
            AttributeError: If ``service_name`` does not resolve to an
                attribute on this module.
        """
        import sys

        return getattr(sys.modules[type(self).__module__], self.service_name)

    def _precheck(self) -> JsonResponse | None:
        """Validate that the request has a valid website and date range.

        Runs the shared precondition checks that all analytics endpoints
        require before calling the service function.

        Returns:
            A JSON error response (400 or 403) if validation fails, or
            ``None`` if all preconditions are satisfied.
        """
        if not self.website_id:
            return _no_website()
        if self.website_forbidden:
            return _forbidden_website()
        if not self.date_range:
            return json_response({"error": "Invalid date range."}, status=400)
        return None

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Handle GET requests by delegating to the configured service function.

        Runs precondition checks, resolves the service function, builds the
        positional arguments (website_id, date_range, and optionally filters),
        merges in any endpoint-specific kwargs, and returns the result as JSON.

        Args:
            request: The incoming HTTP GET request.

        Returns:
            A ``JsonResponse`` with the analytics data from the service
            function, or an error response if prechecks fail.
        """
        err = self._precheck()
        if err is not None:
            return err
        fn = self._resolve_service()
        positional: tuple[Any, ...] = (self.website_id, self.date_range)
        if self.pass_filters:
            positional = (*positional, self.filters)
        return json_response(fn(*positional, **self.extra_kwargs(request)))


class AnalyticsOverviewView(_AnalyticsJSONView):
    """``GET /api/analytics/overview/`` -- aggregated site-wide metrics.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, plus any filter
        params parsed by :class:`FiltersMixin`.

    Response:
        200 JSON with pageviews, estimated visitors, custom-event aggregates,
        device breakdowns, geo data, heatmap data, and realtime counters.
    """

    service_name = "get_overview_data"


class AnalyticsPagesView(_AnalyticsJSONView):
    """``GET /api/analytics/pages/`` -- page-level analytics with pagination.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, ``page`` (1-based
        pagination index, default 1), plus filter params.

    Response:
        200 JSON with per-page view counts and anonymous estimated visitors
        when the active filters allow sketch-based estimates.
    """

    service_name = "get_pages_data"

    def extra_kwargs(self, request: HttpRequest) -> dict[str, Any]:
        """Extract the ``page`` query param for pagination."""
        return {"page": safe_int(request.GET.get("page"))}


class AnalyticsEventsView(_AnalyticsJSONView):
    """``GET /api/analytics/events/`` -- custom event analytics.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, plus filter params.

    Response:
        200 JSON with event names, aggregate counts, and event time series.
    """

    service_name = "get_events_data"

    def extra_kwargs(self, request: HttpRequest) -> dict[str, Any]:
        """Forward the resolved granularity for event timelines."""
        return {"granularity": self.granularity}


class AnalyticsDevicesView(_AnalyticsJSONView):
    """``GET /api/analytics/devices/`` -- device, browser, and OS breakdown.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, plus filter params.

    Response:
        200 JSON with breakdowns by browser name, OS name, and device type.
    """

    service_name = "get_devices_data"


class AnalyticsGeoView(_AnalyticsJSONView):
    """``GET /api/analytics/geo/`` -- geographic analytics with drill-down.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, plus filter params.

    Response:
        200 JSON with pageview counts grouped by country (ISO 3166-1 alpha-2).
    """

    service_name = "get_geo_data"


class AnalyticsCompareView(_AnalyticsJSONView):
    """``GET /api/analytics/compare/`` -- period-over-period comparison.

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required), ``start_at``, ``end_at``, ``mode``
        (``"previous_period"`` or ``"previous_year"``, defaults to
        ``"previous_period"``), plus filter params.

    Response:
        200 JSON with current and comparison period metrics side-by-side,
        including absolute and percentage change for each metric.
    """

    service_name = "get_compare_data"

    def extra_kwargs(self, request: HttpRequest) -> dict[str, Any]:
        """Extract and validate the ``mode`` comparison param."""
        mode = request.GET.get("mode", "previous_period")
        # Guard against arbitrary values -- only two modes are supported
        if mode not in ("previous_period", "previous_year"):
            mode = "previous_period"
        return {"comparison_mode": mode}


class AnalyticsRealtimeView(ApiAuthMixin, WebsiteContextMixin, JSONView):
    """``GET /api/analytics/realtime/`` -- live visitor activity.

    Unlike other analytics endpoints, this does not require a date range --
    it returns data for the current moment (active visitors in the last
    few minutes).

    Authentication:
        Requires API key with access to the specified website.

    Query params:
        ``website`` (required).

    Response:
        200 JSON with current active visitors, recent pageviews, and
        live geographic distribution.

    Error codes:
        400 if no website specified, 403 if website not accessible.
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Return real-time analytics data for the specified website."""
        if not self.website_id:
            return _no_website()
        if self.website_forbidden:
            return _forbidden_website()
        return json_response(get_realtime_data(self.website_id))


# ============================================================================
# Dashboard CRUD
# ============================================================================


class DashboardListView(ApiAuthMixin, JSONView):
    """``GET /api/dashboards/?website=...`` -- list custom dashboards.

    Authentication:
        Requires a valid API key.

    Query params:
        ``website`` (optional UUID) -- when provided, only dashboards for
        that website are returned. Website access is checked.

    Response:
        200 JSON with ``{"dashboards": [{"id": "...", "name": "...",
        "description": "...", "config": {...}, ...}, ...]}``.

    Error codes:
        403 if the specified website is not accessible.
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Return dashboards owned by the API user, optionally filtered by website."""
        website_id = request.GET.get("website") or None
        if website_id and not _website_accessible(request, website_id):
            return _forbidden_website()
        dashboards = get_dashboards_for_user(request.api_user_id, website_id=website_id)
        return json_response({"dashboards": dashboards})


class DashboardDetailView(ApiAuthMixin, JSONView):
    """``GET /api/dashboards/<report_id>/`` -- retrieve a single dashboard.

    Authentication:
        Requires a valid API key. Only returns dashboards owned by the
        authenticated user.

    URL params:
        ``report_id`` -- UUID of the dashboard (``report`` table row).

    Response:
        200 JSON with the full dashboard object including ``config``.

    Error codes:
        404 if the dashboard does not exist or is not owned by this user.
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, report_id: str) -> JsonResponse:
        """Fetch and return a single dashboard by its report ID."""
        result = get_dashboard_detail(report_id, request.api_user_id)
        if not result:
            return json_response({"error": "Dashboard not found."}, status=404)
        return json_response(result)


class DashboardCreateView(ApiWriteMixin, JSONView):
    """``POST /api/dashboards/create/`` -- create a new custom dashboard.

    Authentication:
        Requires a valid API key with write scope.

    Request body (JSON):
        ``name`` (required str) -- dashboard display name.
        ``website_id`` (required UUID str) -- website this dashboard belongs to.
        ``description`` (optional str) -- human-readable description.
        ``config`` (optional dict) -- widget layout and query configuration.

    Response:
        201 JSON with the created dashboard object.

    Error codes:
        400 if ``name`` or ``website_id`` is missing or body is invalid JSON.
        403 if the website is not accessible.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Validate the request body and create a new dashboard."""
        body, err = _parse_json_body(request)
        if err is not None:
            return err
        name = (body.get("name") or "").strip()
        if not name:
            return json_response({"error": "name is required."}, status=400)
        website_id = body.get("website_id", "")
        if not website_id:
            return json_response({"error": "website_id is required."}, status=400)
        if not _website_accessible(request, website_id):
            return _forbidden_website()
        result = create_new_dashboard(
            user_id=request.api_user_id,
            website_id=website_id,
            name=name,
            description=body.get("description", ""),
            config=body.get("config"),
        )
        return json_response(result, status=201)


class DashboardUpdateView(ApiWriteMixin, JSONView):
    """``POST /api/dashboards/<report_id>/update/`` -- update an existing dashboard.

    Authentication:
        Requires a valid API key with write scope. Only the dashboard owner
        can update it.

    URL params:
        ``report_id`` -- UUID of the dashboard to update.

    Request body (JSON):
        All fields are optional; only provided fields are updated:
        ``name`` (str), ``description`` (str), ``config`` (dict).

    Response:
        200 JSON with the updated dashboard object.

    Error codes:
        400 if body is invalid JSON. 404 if dashboard not found or not owned.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, report_id: str) -> JsonResponse:
        """Parse the update payload and apply changes to the dashboard."""
        body, err = _parse_json_body(request)
        if err is not None:
            return err
        result = update_existing_dashboard(
            report_id=report_id,
            user_id=request.api_user_id,
            name=body.get("name"),
            description=body.get("description"),
            config=body.get("config"),
        )
        if not result:
            return json_response({"error": "Dashboard not found."}, status=404)
        return json_response(result)


class DashboardDeleteView(ApiWriteMixin, JSONView):
    """``POST /api/dashboards/<report_id>/delete/`` -- delete a dashboard.

    Authentication:
        Requires a valid API key with write scope. Only the dashboard owner
        can delete it.

    URL params:
        ``report_id`` -- UUID of the dashboard to delete.

    Response:
        200 JSON with ``{"deleted": true}``.

    Error codes:
        404 if dashboard not found or not owned by the API user.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, report_id: str) -> JsonResponse:
        """Delete the specified dashboard and return a confirmation."""
        if not remove_dashboard(report_id, request.api_user_id):
            return json_response({"error": "Dashboard not found."}, status=404)
        return json_response({"deleted": True})


# ============================================================================
# API Keys CRUD
# ============================================================================


class ApiKeyListView(ApiAuthMixin, JSONView):
    """``GET /api/api-keys/`` -- list API keys for the authenticated user.

    Authentication:
        Requires a valid API key.

    Response:
        200 JSON with ``{"api_keys": [{"id": "...", "name": "...",
        "scopes": [...], "created_at": "...", "last_used_at": "..."}, ...]}``.
        The raw key value is never returned (only the SHA-256 hash is stored).
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Return all API keys belonging to the authenticated user."""
        return json_response({"api_keys": get_api_keys_for_user(request.api_user_id)})


class ApiKeyCreateView(ApiWriteMixin, JSONView):
    """``POST /api/api-keys/create/`` -- generate a new API key.

    Authentication:
        Requires a valid API key with write scope.

    Request body (JSON):
        ``name`` (required str) -- human-readable label for the key.
        ``scopes`` (optional list[str]) -- permission scopes for the key
        (e.g. ``["read", "write", "admin"]``). Defaults to read-only.

    Response:
        201 JSON with the created key metadata **including the raw key
        value**. This is the only time the plaintext key is returned;
        subsequent reads only return the key metadata without the secret.

    Error codes:
        400 if ``name`` is missing or body is invalid JSON.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Validate the request and generate a new API key."""
        body, err = _parse_json_body(request)
        if err is not None:
            return err
        name = (body.get("name") or "").strip()
        if not name:
            return json_response({"error": "name is required."}, status=400)
        result = generate_new_api_key(
            user_id=request.api_user_id,
            name=name,
            scopes=body.get("scopes"),
        )
        # The raw key is included in this response only -- it is hashed before storage
        return json_response(result, status=201)


class ApiKeyDeleteView(ApiWriteMixin, JSONView):
    """``POST /api/api-keys/<key_id>/delete/`` -- revoke an API key.

    Authentication:
        Requires a valid API key with write scope. Only the key owner can
        revoke keys.

    URL params:
        ``key_id`` -- UUID of the API key to revoke.

    Response:
        200 JSON with ``{"deleted": true}``.

    Error codes:
        404 if the API key does not exist or is not owned by the API user.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, key_id: str) -> JsonResponse:
        """Revoke the specified API key by deleting its report row."""
        if not remove_api_key(key_id, request.api_user_id):
            return json_response({"error": "API key not found."}, status=404)
        return json_response({"deleted": True})


# ============================================================================
# Bot Config
# ============================================================================


class BotConfigGetView(ApiAuthMixin, JSONView):
    """``GET /api/bot-config/?website=...`` -- retrieve bot detection configuration.

    Authentication:
        Requires a valid API key with access to the specified website.

    Query params:
        ``website`` (required UUID) -- the website whose bot config to retrieve.

    Response:
        200 JSON with the bot configuration object (detection rules, whitelist,
        blacklist, etc.). Returns a default config if none has been customized.

    Error codes:
        400 if ``website`` param is missing. 403 if website not accessible.
    """

    http_method_names = ("get",)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Return the bot detection configuration for the specified website."""
        website_id = request.GET.get("website", "")
        if not website_id:
            return json_response({"error": "website parameter required."}, status=400)
        if not _website_accessible(request, website_id):
            return _forbidden_website()
        return json_response(get_bot_config(website_id))


class BotConfigSaveView(ApiWriteMixin, JSONView):
    """``POST /api/bot-config/save/`` -- create or update bot detection config.

    Authentication:
        Requires a valid API key with write scope and access to the website.

    Request body (JSON):
        ``website_id`` (required UUID str) -- target website.
        ``config`` (optional dict) -- the bot detection configuration object.
        Defaults to an empty dict if omitted.

    Response:
        200 JSON with the saved bot configuration object (upsert semantics).

    Error codes:
        400 if ``website_id`` is missing or body is invalid JSON.
        403 if the website is not accessible.
    """

    http_method_names = ("post",)

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        """Validate the request and upsert the bot detection configuration."""
        body, err = _parse_json_body(request)
        if err is not None:
            return err
        website_id = body.get("website_id", "")
        if not website_id:
            return json_response({"error": "website_id is required."}, status=400)
        if not _website_accessible(request, website_id):
            return _forbidden_website()
        result = save_bot_config(
            user_id=request.api_user_id,
            website_id=website_id,
            config=body.get("config", {}),
        )
        return json_response(result)
