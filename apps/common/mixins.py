"""Reusable class-based-view mixins.

These mixins replace the inline ``_resolve_*`` helpers and ``@analytics_view`` /
``with_analytics_params`` / ``require_api_auth`` decorators that previously
lived in :mod:`apps.analytics.views`, :mod:`apps.api.views`, and
:mod:`apps.common.http`.

Two principles guide the design:

1. **Identity-agnostic access**: the same mixin set supports both web views
   (``request.user`` set by Django's ``AuthenticationMiddleware``) and API
   endpoints (``request.api_user_id`` set by
   :class:`mantecato.middleware.ApiKeyMiddleware`). The
   :class:`_AccessIdentityMixin` hooks let subclasses such as
   :class:`ApiAuthMixin` swap the source of identity without touching the
   downstream mixins.

2. **State on ``self`` after ``setup()``**: each mixin computes its values
   inside Django's ``View.setup()`` hook so they are available both to
   ``dispatch()`` and to template-context builders. Read paths therefore
   never re-parse the query string.

MRO recommendation when composing mixins:

.. code-block:: python

    class MyApiView(ApiAuthMixin, WebsiteContextMixin, DateRangeMixin,
                    FiltersMixin, View):
        ...

    class MyWebView(LoginRequiredMixin, WebsiteContextMixin, DateRangeMixin,
                    FiltersMixin, BaseContextMixin, TemplateView):
        ...
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

from django.http import JsonResponse

from apps.common.constants import VALID_RANGE_PRESETS
from core.mantecato_core.date_utils import (
    DateRange,
    get_comparison_range,
    resolve_date_range,
    resolve_granularity,
)
from core.mantecato_core.date_utils import (
    VALID_GRANULARITIES,
)
from core.mantecato_core.filters import Filter, parse_filters_from_params

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse


# Default ``?range=`` preset when none is specified. The web pages historically
# default to the "last 24 hours" view, while the JSON API surfaces (CLI, MCP)
# default to the broader "last 30 days" window used by external tooling.
DEFAULT_WEB_RANGE_PRESET = "24h"
DEFAULT_API_RANGE_PRESET = "30d"

# Hard cap on how many whole periods the prev/next controls may step back, so a
# hand-edited ``?offset=`` cannot spin the comparison-range chain pathologically.
_MAX_RANGE_OFFSET = 10_000


def _parse_offset(raw: str | None) -> int:
    """Parse ``?offset=`` into a clamped, non-negative period count.

    Returns ``0`` (the most recent window) for missing, non-integer, or
    negative input; otherwise the value clamped to :data:`_MAX_RANGE_OFFSET`.
    """
    if not raw:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, _MAX_RANGE_OFFSET))


class _AccessIdentityMixin:
    """Internal helper: return ``(user_id, is_admin)`` for the acting principal.

    Defaults to the Django session user (``request.user``) populated by
    :class:`django.contrib.auth.middleware.AuthenticationMiddleware`. The
    :class:`ApiAuthMixin` overrides both methods to read the API-key context
    set by :class:`mantecato.middleware.ApiKeyMiddleware`.

    Subclasses are not expected to override these methods directly except via
    :class:`ApiAuthMixin` / :class:`ApiWriteMixin`.
    """

    def get_acting_user_id(self) -> str | None:
        """Return the UUID string of the current principal, or ``None``.

        For web views: ``str(request.user.id)`` when the user is authenticated.
        For API views: overridden by :class:`ApiAuthMixin`.
        """
        user = getattr(self.request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        return str(user.id)

    def is_acting_user_admin(self) -> bool:
        """Return whether the acting principal has admin privileges.

        For web views: ``True`` when ``MantecatoUser.role == "admin"``.
        For API views: overridden by :class:`ApiAuthMixin`.
        """
        user = getattr(self.request, "user", None)
        return bool(user and getattr(user, "is_staff", False))


class WebsiteContextMixin(_AccessIdentityMixin):
    """Resolve the ``?website=<uuid>`` query parameter against the principal's sites.

    After :meth:`setup` (called by ``View.as_view()`` before ``dispatch``) the
    following attributes are guaranteed on ``self``:

    Attributes:
        websites (list[dict]): all websites accessible to the principal,
            in the order returned by
            :func:`apps.analytics.services.resolve_websites_for_user`.
        website_id (str | None): the selected website UUID.
            ``None`` when no websites are accessible OR when a website was
            requested but the principal cannot access it.
        selected_website_name (str): convenience for templates.
        website_forbidden (bool): ``True`` only when the request explicitly
            asked for a website the principal cannot access. API views can use
            this flag to return ``403`` instead of falling back silently.

    Behaviour:
        - ``?website=`` empty → falls back to the first accessible website.
        - ``?website=<known>`` → that website is used.
        - ``?website=<unknown>`` → ``website_id = None`` and
          ``website_forbidden = True``.

    Example:
        .. code-block:: python

            class MyPageView(LoginRequiredMixin, WebsiteContextMixin,
                             DateRangeMixin, FiltersMixin,
                             BaseContextMixin, TemplateView):
                template_name = "analytics/overview.html"

                def get_context_data(self, **kwargs):
                    ctx = super().get_context_data(**kwargs)
                    if not self.website_id or not self.date_range:
                        ctx["no_data"] = True
                        return ctx
                    ctx.update(my_service(self.website_id, self.date_range))
                    return ctx

    Cross-refs:
        - :func:`apps.analytics.services.resolve_websites_for_user`
    """

    def _websites_resolver(self):
        """Locate ``resolve_websites_for_user`` to use for the current view.

        Looks up the function on the view's defining module first (e.g.
        ``apps.analytics.views``), falling back to the canonical service.
        The indirection lets test suites patch
        ``apps.analytics.views.resolve_websites_for_user`` and have the
        mock visible to the mixin without coupling the mixin to the
        analytics package import path.
        """
        import sys

        module = sys.modules.get(type(self).__module__)
        fn = getattr(module, "resolve_websites_for_user", None)
        if fn is not None:
            return fn
        from apps.analytics.services import resolve_websites_for_user

        return resolve_websites_for_user

    def setup(self, request: HttpRequest, *args: object, **kwargs: object) -> None:
        """Resolve the website context during Django's view setup phase.

        This runs before ``dispatch()`` so all downstream mixins and the
        view handler itself can rely on ``self.website_id`` being set.

        Args:
            request: The incoming HTTP request.
            *args: Positional URL arguments.
            **kwargs: URL keyword arguments.
        """
        super().setup(request, *args, **kwargs)
        resolve_fn = self._websites_resolver()
        user_id = self.get_acting_user_id()
        is_admin = self.is_acting_user_admin()
        # Fetch the full list of sites the principal may access.
        self.websites: list[dict] = resolve_fn(user_id, is_admin) if user_id else []
        valid_ids = {w["id"] for w in self.websites}
        requested = request.GET.get("website", "")

        if requested:
            if requested in valid_ids:
                # Explicitly requested and accessible -- use it.
                self.website_id: str | None = requested
                self.website_forbidden = False
            else:
                # Requested but not in the principal's accessible set.
                self.website_id = None
                self.website_forbidden = True
        else:
            # No explicit request -- fall back to the first accessible site.
            self.website_id = self.websites[0]["id"] if self.websites else None
            self.website_forbidden = False

        # Convenience attribute for template rendering (avoids a lookup in
        # every template that needs the site name).
        self.selected_website_name: str = next(
            (w["name"] for w in self.websites if w["id"] == self.website_id),
            "",
        )


class DateRangeMixin:
    """Resolve the analytics date range from ``?start=`` / ``?end=`` / ``?range=``.

    After :meth:`setup` the following attributes are available:

    Attributes:
        date_range (DateRange | None): resolved range. ``None`` when the explicit
            ``start``/``end`` pair is malformed OR when the preset is ``custom``
            / ``all`` without bounds.
        range_preset (str): the preset name (``"30d"``, ``"24h"``, ``"custom"``
            for explicit start/end, …).

    Subclasses may override :attr:`default_range_preset` to change the fallback
    used when ``?range=`` is missing or invalid. The web pages default to
    :data:`DEFAULT_WEB_RANGE_PRESET` (``"24h"``); the JSON API endpoints to
    :data:`DEFAULT_API_RANGE_PRESET` (``"30d"``) via :class:`ApiAuthMixin`.

    Cross-refs:
        - :func:`core.mantecato_core.date_utils.resolve_date_range`
        - :data:`apps.common.constants.VALID_RANGE_PRESETS`
    """

    default_range_preset: str = DEFAULT_WEB_RANGE_PRESET

    def setup(self, request: HttpRequest, *args: object, **kwargs: object) -> None:
        """Parse date-range parameters from the query string.

        Resolution order:
            1. Explicit ``?start=`` + ``?end=`` pair (ISO-8601) -- treated
               as a ``"custom"`` preset.
            2. Named preset via ``?range=`` (e.g. ``"30d"``, ``"this_month"``).
            3. Fallback to :attr:`default_range_preset`.

        Args:
            request: The incoming HTTP request.
            *args: Positional URL arguments.
            **kwargs: URL keyword arguments.
        """
        super().setup(request, *args, **kwargs)
        # Periods stepped back from "now" via the prev/next controls. Stays 0
        # for explicit start/end (those windows are pinned, not navigable).
        self.range_offset = 0
        start = request.GET.get("start")
        end = request.GET.get("end")
        if start and end:
            # Explicit start/end takes priority over named presets.
            try:
                self.date_range: DateRange | None = DateRange(
                    datetime.fromisoformat(start),
                    datetime.fromisoformat(end),
                )
            except ValueError:
                self.date_range = None
            self.range_preset = "custom"
            return

        # Fall back to a named preset, clamped to the known set.
        preset = request.GET.get("range", self.default_range_preset)
        if preset not in VALID_RANGE_PRESETS:
            preset = self.default_range_preset
        self.range_preset = preset
        self.date_range = resolve_date_range(preset)

        # Optional ?offset=N pages the window back by N whole periods so the
        # prev/next controls step onto the immediately-preceding window of the
        # same length (e.g. "previous" on a 24h view shows the prior 24h, with
        # no gap). The comparison overlay is re-derived from this shifted window
        # downstream, so it always tracks the period actually being viewed.
        self.range_offset = _parse_offset(request.GET.get("offset"))
        if self.range_offset and self.date_range is not None:
            shift = (self.date_range.end_date - self.date_range.start_date) * self.range_offset
            self.date_range = DateRange(
                self.date_range.start_date - shift,
                self.date_range.end_date - shift,
            )


class GranularityMixin:
    """Resolve the time-bucket granularity from ``?granularity=``.

    After :meth:`setup` the following attributes are available:

    Attributes:
        granularity (str): the raw granularity string from the query string.
            One of ``"auto"``, ``"minute"``, ``"hour"``, ``"day"``,
            ``"week"``, ``"month"``.  Defaults to ``"auto"``.
        resolved_granularity (str | None): the concrete bucket size after
            resolving ``"auto"`` via :func:`~core.mantecato_core.date_utils.resolve_granularity`.
            ``None`` when ``date_range`` is not available.

    This mixin must appear **after** :class:`DateRangeMixin` in the MRO
    because it reads ``self.date_range`` set by that mixin.

    Cross-refs:
        - :func:`core.mantecato_core.date_utils.resolve_granularity`
        - :data:`core.mantecato_core.date_utils.VALID_GRANULARITIES`
    """

    def setup(self, request: HttpRequest, *args: object, **kwargs: object) -> None:
        """Parse the granularity query parameter.

        Resolution order:
            1. ``?granularity=`` with a valid value (``"day"``, ``"month"``, ...).
            2. ``?granularity=auto`` (default) -- resolved via
               :func:`resolve_granularity` based on the date-range span.
            3. Invalid values silently fall back to ``"auto"``.

        Args:
            request: The incoming HTTP request.
            *args: Positional URL arguments.
            **kwargs: URL keyword arguments.
        """
        super().setup(request, *args, **kwargs)
        raw = request.GET.get("granularity", "auto")
        if raw != "auto" and raw not in VALID_GRANULARITIES:
            raw = "auto"
        self.granularity: str = raw
        date_range = getattr(self, "date_range", None)
        if date_range is not None:
            self.resolved_granularity: str | None = resolve_granularity(raw, date_range)
        else:
            self.resolved_granularity = None


class FiltersMixin:
    """Parse analytics filters from ``?filter=``, ``?f=`` and ``?bot_filter=1``.

    After :meth:`setup`:

    Attributes:
        filters (list[Filter]): parsed :class:`~core.mantecato_core.filters.Filter`
            objects. Includes a synthetic ``__bot_filter__`` filter when
            ``?bot_filter=1`` is set, so the query engine can apply bot
            exclusion rules.
        bot_filter (bool): convenience flag for templates and downstream code.

    Cross-refs:
        - :func:`core.mantecato_core.filters.parse_filters_from_params`
        - :data:`core.mantecato_core.filters.BOT_BROWSER_PATTERN`
    """

    def setup(self, request: HttpRequest, *args: object, **kwargs: object) -> None:
        """Parse filter query parameters and remember the bot-filter toggle.

        The actual filter list (including the synthetic ``__bot_filter__``
        entry) is built lazily by :attr:`filters` on first access, because
        ``setup()`` may run before :class:`WebsiteContextMixin` has had a
        chance to populate ``self.website_id`` -- the bot config lookup
        depends on that attribute being set.
        """
        super().setup(request, *args, **kwargs)
        # Merge both parameter names -- ``filter`` is canonical, ``f`` is
        # the short alias used by bookmarkable share-links.
        raw = [*request.GET.getlist("filter"), *request.GET.getlist("f")]
        self._raw_filters: list[Filter] = parse_filters_from_params(raw) if raw else []
        # Resolved lazily by the ``bot_filter`` property: an explicit
        # ?bot_filter=1/0 wins, otherwise the site's "filter bots by default"
        # preference decides. Stored raw here because ``website_id`` is not
        # populated until WebsiteContextMixin.setup runs later in the MRO.
        self._bot_filter_param: str | None = request.GET.get("bot_filter")

    @cached_property
    def bot_filter(self) -> bool:
        """Whether bot filtering is active for this view.

        An explicit ``?bot_filter=1``/``0`` always wins. When the param is
        absent, fall back to the website's saved "filter bots by default"
        preference (the :class:`~apps.core.models.BotConfig` ``enabled`` flag),
        so a site can opt into always-on filtering that mirrors Umami's
        server-side bot exclusion.

        Lazily computed because ``website_id`` (set by
        :class:`WebsiteContextMixin.setup` later in the MRO) must be available
        to resolve the per-site default. Cached because templates and the
        ``filters`` property both read it.
        """
        if self._bot_filter_param is not None:
            return self._bot_filter_param == "1"
        website_id = getattr(self, "website_id", None)
        return _bot_filter_default_enabled(website_id) if website_id else False

    @cached_property
    def filters(self) -> list[Filter]:
        """Materialise the final filter list, including bot exclusion when applicable.

        Lazily-computed so that ``self.website_id`` (set by
        :class:`WebsiteContextMixin.setup` after the MRO chain unwinds) is
        available by the time we resolve the bot config.  Cached because
        downstream code reads ``self.filters`` from many places per request.
        """
        result = list(self._raw_filters)
        if self.bot_filter:
            website_id = getattr(self, "website_id", None)
            payload = load_bot_filter_payload(website_id) if website_id else None
            if payload is not None:
                # The query engine treats this synthetic column as a
                # directive to apply the configured bot exclusion clause
                # (see core.mantecato_core.filters.build_bot_filter_sql).
                result.append(
                    Filter(
                        column="__bot_filter__",
                        operator="eq",
                        value=payload,
                    )
                )
        return result


def load_bot_filter_payload(
    website_id: str,
) -> str | None:
    """Return the JSON-encoded BotConfig payload for *website_id*, or ``None``.

    Module-level helper so :class:`FiltersMixin` does not need to import
    ``apps.core`` at module load (which would create a circular import) and
    so tests can patch this single function instead of stubbing the
    BotConfig manager.

    Resolution rules:

    - **No row in DB**: fall back to :data:`BOT_CONFIG_DEFAULTS` with
      ``enabled`` forced to ``True`` so the URL toggle still filters known
      bots and empty user-agents.
    - **Row with** ``enabled=False``: return ``None`` so the synthetic
      ``__bot_filter__`` is skipped entirely.
    - **Row with** ``enabled=True``: return that config verbatim.

    Args:
        website_id: UUID of the tracked website.
    """
    try:
        from apps.core.models import BOT_CONFIG_DEFAULTS, BotConfig

        config_row = BotConfig.objects.filter(website_id=website_id).first()
    except Exception:
        # Defensive: never block analytics rendering because the bot
        # config table is missing or migrations haven't run yet.
        logger.warning("BotConfig lookup failed for website %s", website_id, exc_info=True)
        return None

    if config_row is None:
        # No saved preference -- treat the URL toggle as a request for the
        # mantecato v2 baseline (known bots + empty UA + cluster + velocity).
        config = {**BOT_CONFIG_DEFAULTS, "enabled": True}
    else:
        # The dashboard toggle IS the enable signal -- this mirrors Mantecato
        # v2, whose toggle auto-enables the saved config on click. Apply the
        # saved rules (knownBots, emptyUa, excludedCountries) but force
        # ``enabled`` on, so a saved ``enabled=False``
        # no longer silently neutralises an explicit ?bot_filter=1. The
        # per-view on/off decision already happened upstream in
        # ``FiltersMixin.bot_filter``; this payload is only built when it is on.
        params = config_row.parameters if isinstance(config_row.parameters, dict) else {}
        config = {**params, "enabled": True}

    return json.dumps({"config": config})


def _bot_filter_default_enabled(website_id: str) -> bool:
    """Return the site's "filter bots by default" preference.

    Reads the saved :class:`~apps.core.models.BotConfig` ``enabled`` flag for
    *website_id*. This drives the default state of the dashboard bot-filter
    toggle when the request carries no explicit ``?bot_filter`` param (see
    :attr:`FiltersMixin.bot_filter`). Unlike :func:`load_bot_filter_payload`,
    this honours the literal saved flag -- it decides whether filtering is on
    by default, not how to apply it.

    Returns ``False`` (default off, matching Mantecato v2) when there is no
    saved config, the row is malformed, or the lookup fails.
    """
    try:
        from apps.core.models import BotConfig

        row = BotConfig.objects.filter(website_id=website_id).first()
    except Exception:
        # Never block rendering because the config table is unavailable.
        logger.warning("BotConfig default lookup failed for website %s", website_id, exc_info=True)
        return False
    if row is None or not isinstance(row.parameters, dict):
        return False
    return bool(row.parameters.get("enabled", False))


class BaseContextMixin:
    """Inject the analytics-page template context keys shared by every page.

    Adds to the context dict (without overwriting keys already provided):

    - ``websites``: list of accessible websites.
    - ``selected_website``: the resolved website UUID (or ``None``).
    - ``selected_website_name``: human-readable name.
    - ``range_preset``: ``"24h"``, ``"30d"``, ``"custom"``, ...
    - ``bot_filter``: bool.

    Designed to be stacked on top of :class:`WebsiteContextMixin`,
    :class:`DateRangeMixin`, and :class:`FiltersMixin` so the attributes
    these set are present on ``self`` when ``get_context_data`` runs.
    """

    def get_context_data(self, **kwargs: object) -> dict:
        """Inject shared analytics-page context keys.

        Uses ``setdefault`` so view-specific overrides (set earlier in the
        MRO) are never clobbered. ``getattr`` guards against partial mixin
        composition -- e.g. a view that includes ``BaseContextMixin`` but
        not ``FiltersMixin`` will still render without raising
        ``AttributeError``.

        Args:
            **kwargs: Additional context keys from the URL resolver.

        Returns:
            The template context dict with analytics keys populated.
        """
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("websites", getattr(self, "websites", []))
        ctx.setdefault("selected_website", getattr(self, "website_id", None))
        ctx.setdefault(
            "selected_website_name",
            getattr(self, "selected_website_name", ""),
        )
        ctx.setdefault(
            "range_preset",
            getattr(self, "range_preset", DEFAULT_WEB_RANGE_PRESET),
        )
        ctx.setdefault("bot_filter", getattr(self, "bot_filter", False))
        ctx.setdefault("active_filters", getattr(self, "filters", []))
        # Prev/next navigation state for the date-range controls. ``current_range``
        # is the (possibly offset-shifted) window, used to label which period the
        # user is viewing when ``range_offset`` > 0.
        ctx.setdefault("range_offset", getattr(self, "range_offset", 0))
        ctx.setdefault("current_range", getattr(self, "date_range", None))
        ctx.setdefault("granularity", getattr(self, "granularity", "auto"))
        return ctx


class ApiAuthMixin(_AccessIdentityMixin):
    """Reject unauthenticated API requests with HTTP 401.

    Reads the attributes set by :class:`mantecato.middleware.ApiKeyMiddleware`:

    - ``request.is_api_authenticated``: ``True`` after a valid Bearer key.
    - ``request.api_user_id``: UUID string of the key's owner.
    - ``request.api_key_scopes``: list of scope strings (``["read", "write"]`` …).

    Also overrides :meth:`get_acting_user_id` and :meth:`is_acting_user_admin`
    so :class:`WebsiteContextMixin` consults the API identity instead of the
    Django session user.

    The default :attr:`default_range_preset` is set to
    :data:`DEFAULT_API_RANGE_PRESET` (``"30d"``) to mirror the legacy API
    behaviour.

    Cross-refs:
        - :class:`mantecato.middleware.ApiKeyMiddleware`
    """

    default_range_preset: str = DEFAULT_API_RANGE_PRESET

    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Reject unauthenticated requests before reaching the view handler.

        Args:
            request: The incoming HTTP request.
            *args: Positional URL arguments.
            **kwargs: URL keyword arguments.

        Returns:
            401 JSON error when ``request.is_api_authenticated`` is falsy,
            otherwise the result of the parent ``dispatch``.
        """
        if not getattr(request, "is_api_authenticated", False):
            return JsonResponse({"error": "Authentication required."}, status=401)
        return super().dispatch(request, *args, **kwargs)

    def get_acting_user_id(self) -> str | None:
        """Return the API key owner's UUID from the middleware-stamped attribute."""
        return getattr(self.request, "api_user_id", None)

    def is_acting_user_admin(self) -> bool:
        """Return ``True`` when the API key carries the ``admin`` scope."""
        return "admin" in getattr(self.request, "api_key_scopes", [])


class ApiWriteMixin(ApiAuthMixin):
    """Like :class:`ApiAuthMixin` but also requires the ``write`` scope.

    Returns ``401`` for unauthenticated requests and ``403`` for read-only keys.

    Note:
        ``dispatch`` calls ``super(ApiAuthMixin, self).dispatch`` after both
        checks so the auth check is not run twice along the MRO.
    """

    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Enforce authentication *and* write-scope before reaching the view.

        Two-step guard:
            1. ``is_api_authenticated`` must be truthy (set by the middleware).
            2. The key's scopes list must include ``"write"``.

        The ``super()`` call deliberately skips :class:`ApiAuthMixin` to
        avoid running the auth check a second time -- it jumps straight to
        ``View.dispatch``.

        Args:
            request: The incoming HTTP request.
            *args: Positional URL arguments.
            **kwargs: URL keyword arguments.

        Returns:
            401 when unauthenticated, 403 when the key lacks the write
            scope, otherwise the view handler's response.
        """
        if not getattr(request, "is_api_authenticated", False):
            return JsonResponse({"error": "Authentication required."}, status=401)
        if "write" not in getattr(request, "api_key_scopes", []):
            return JsonResponse({"error": "Write scope required."}, status=403)
        # Skip ApiAuthMixin.dispatch (auth already verified) -- go straight to View.
        return super(ApiAuthMixin, self).dispatch(request, *args, **kwargs)


class OwnedReportQuerysetMixin:
    """Restrict ``get_queryset()`` to rows owned by the acting user.

    Designed to be combined with :class:`~django.views.generic.ListView`,
    :class:`~django.views.generic.DetailView`,
    :class:`~django.views.generic.UpdateView`, or
    :class:`~django.views.generic.DeleteView` over one of the proxy models
    in :mod:`apps.core.models` (Dashboard, …).

    Admin users (``request.user.is_staff``) bypass the ownership filter and
    see every row of the proxy model.

    Example:
        .. code-block:: python

            class DashboardListView(LoginRequiredMixin,
                                    OwnedReportQuerysetMixin, ListView):
                model = Dashboard
                template_name = "dashboards/dashboard_list.html"

    Cross-refs:
        - :class:`apps.core.models.Dashboard`
    """

    def get_queryset(self) -> QuerySet:
        """Return the proxy model queryset, filtered to the acting user's rows.

        Admin users (``is_staff=True``) bypass the ownership filter and
        receive every row of the proxy model -- this supports the admin-level
        management UI. Regular users only see their own reports.

        Returns:
            A :class:`~django.db.models.QuerySet` scoped to the acting user
            (or unfiltered for admins).
        """
        qs = super().get_queryset()
        if getattr(self.request.user, "is_staff", False):
            return qs
        return qs.filter(user_id=str(self.request.user.id))
