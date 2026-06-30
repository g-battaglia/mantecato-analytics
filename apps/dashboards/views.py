"""Dashboard CRUD views — list, create, edit, delete.

The four views are class-based and delegate persistence to
:mod:`apps.dashboards.services`. Form validation goes through the shared
:class:`apps.common.forms.DashboardModelForm`, which centralises field
constraints (``name`` ≤200 chars, ``website_id`` UUID, ``config`` JSON
default layout) and is reused by the JSON API CRUD endpoints in
:mod:`apps.api.views`.

URL → View → Template map:

- ``GET  /dashboards/`` → :class:`DashboardListView` (``dashboards/dashboard_list.html``)
- ``GET  /dashboards/create/`` → :class:`DashboardCreateView` (``dashboard_form.html``)
- ``POST /dashboards/create/`` → :class:`DashboardCreateView` (redirect on success)
- ``GET  /dashboards/<pk>/edit/`` → :class:`DashboardUpdateView` (``dashboard_form.html``)
- ``POST /dashboards/<pk>/edit/`` → :class:`DashboardUpdateView` (redirect on success)
- ``POST /dashboards/<pk>/delete/`` → :class:`DashboardDeleteView` (redirect on success)

Cross-refs:
    - :class:`apps.common.forms.DashboardModelForm`
    - :mod:`apps.dashboards.services`
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import ListView

from apps.common.constants import VALID_RANGE_PRESETS
from apps.common.forms import DashboardModelForm, first_error
from apps.common.mixins import load_bot_filter_payload
from apps.dashboards.services import (
    create_new_dashboard,
    get_dashboard_detail,
    get_dashboards_for_user,
    remove_dashboard,
    update_existing_dashboard,
)
from apps.dashboards.widgets import render_widget
from core.mantecato_core.date_utils import (
    VALID_GRANULARITIES,
    DateRange,
    resolve_date_range,
)
from core.mantecato_core.filters import Filter, parse_filters_from_params

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

_FALLBACK_RANGE = "30d"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _form_data_from_post(post_data: dict[str, str]) -> dict[str, str]:
    """Build the template ``form_data`` dict from raw POST data.

    Called after a validation failure so the form can re-render with the
    user's previously entered values pre-filled (avoiding data loss on
    error).

    Args:
        post_data: The ``request.POST`` QueryDict.

    Returns:
        A dict with ``name``, ``description``, ``website_id``, and
        ``config`` keys, all strings (possibly empty).
    """
    return {
        "name": post_data.get("name", ""),
        "description": post_data.get("description", ""),
        "website_id": post_data.get("website_id", ""),
        "config": post_data.get("config", ""),
    }


def _form_data_from_dashboard(dashboard: dict) -> dict:
    """Build the template ``form_data`` dict from a serialized dashboard.

    Used when rendering the edit form for an existing dashboard. The
    ``config`` dict is serialised to indented JSON so the ``<textarea>``
    receives a human-readable string.

    Args:
        dashboard: The camelCase dict returned by
            :meth:`Dashboard.to_dict`.

    Returns:
        A dict with ``name``, ``description``, ``website_id``, and
        ``config`` keys suitable for the template.
    """
    return {
        "name": dashboard.get("name", ""),
        "description": dashboard.get("description", ""),
        "website_id": dashboard.get("websiteId", ""),
        "config": json.dumps(dashboard.get("config", {}), indent=2),
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class DashboardListView(LoginRequiredMixin, ListView):
    """List dashboards owned by the current user, newest-updated first."""

    template_name = "dashboards/dashboard_list.html"
    context_object_name = "dashboards"

    def get_queryset(self) -> list[dict]:
        """Return serialized dashboards for the logged-in user.

        Returns:
            A list of camelCase dicts from :func:`get_dashboards_for_user`,
            ordered newest-updated first.
        """
        return get_dashboards_for_user(str(self.request.user.id))


class DashboardCreateView(LoginRequiredMixin, View):
    """Render and process the dashboard-creation form.

    Plain :class:`~django.views.View` (not :class:`CreateView`) so we can
    route persistence through :func:`create_new_dashboard` — both for test
    patchability and so the JSON column default ends up in one place.
    """

    template_name = "dashboards/dashboard_form.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the empty dashboard creation form.

        Args:
            request: The incoming HTTP request.

        Returns:
            The rendered ``dashboard_form.html`` template with
            ``action="create"`` and empty ``form_data``.
        """
        return render(
            request,
            self.template_name,
            {"action": "create", "form_data": {}},
        )

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and persist a new dashboard, then redirect to the list.

        On validation failure the form is re-rendered with the user's
        input preserved via :func:`_form_data_from_post`.

        Args:
            request: The incoming HTTP request carrying POST data.

        Returns:
            A redirect to ``dashboard_list`` on success, or the re-rendered
            form on validation failure.
        """
        form = DashboardModelForm(data=request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return render(
                request,
                self.template_name,
                {"action": "create", "form_data": _form_data_from_post(request.POST)},
            )
        cleaned = form.cleaned_data
        created = create_new_dashboard(
            user_id=str(request.user.id),
            website_id=str(cleaned["website_id"]),
            name=cleaned["name"],
            description=cleaned["description"],
            config=cleaned["config"] or {},
        )
        messages.success(request, "Dashboard created — add some widgets.")
        # Straight into the visual builder for the freshly-created dashboard.
        return redirect("dashboard_edit", report_id=created["id"])


class DashboardUpdateView(LoginRequiredMixin, View):
    """Render the visual builder and process its saved config for a single dashboard."""

    template_name = "dashboards/dashboard_builder.html"

    def _render(self, request: HttpRequest, dashboard: dict, form_data: dict) -> HttpResponse:
        """Render the edit template with the dashboard context.

        Args:
            request: The incoming HTTP request.
            dashboard: Serialized dashboard dict (for read-only display).
            form_data: Editable field values for the form inputs.

        Returns:
            The rendered ``dashboard_form.html`` response.
        """
        return render(
            request,
            self.template_name,
            {"action": "edit", "dashboard": dashboard, "form_data": form_data},
        )

    def get(self, request: HttpRequest, report_id: str) -> HttpResponse:
        """Render the edit form pre-populated with the dashboard's current values.

        Args:
            request: The incoming HTTP request.
            report_id: UUID of the dashboard (from the URL).

        Returns:
            The rendered form, or a redirect to the list with an error
            message if the dashboard is not found.
        """
        dashboard = get_dashboard_detail(report_id, str(request.user.id))
        if dashboard is None:
            messages.error(request, "Dashboard not found.")
            return redirect("dashboard_list")
        return self._render(request, dashboard, _form_data_from_dashboard(dashboard))

    def post(self, request: HttpRequest, report_id: str) -> HttpResponse:
        """Validate and apply dashboard edits, then redirect to the list.

        The ``website_id`` is immutable after creation, so its value is
        copied from the persisted dashboard rather than the POST payload.
        This prevents accidentally changing the website association.

        Args:
            request: The incoming HTTP request carrying POST data.
            report_id: UUID of the dashboard (from the URL).

        Returns:
            A redirect to ``dashboard_list`` on success, or the re-rendered
            form on validation failure.
        """
        user_id = str(request.user.id)
        dashboard = get_dashboard_detail(report_id, user_id)
        if dashboard is None:
            messages.error(request, "Dashboard not found.")
            return redirect("dashboard_list")
        # On edit the website_id is immutable, so it does not need to validate;
        # we forward only the editable fields through the form.
        form_data = {
            "name": request.POST.get("name", ""),
            "description": request.POST.get("description", ""),
            "website_id": dashboard.get("websiteId", ""),
            "config": request.POST.get("config", ""),
        }
        form = DashboardModelForm(data=form_data)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return self._render(request, dashboard, _form_data_from_post(request.POST))
        cleaned = form.cleaned_data
        update_existing_dashboard(
            report_id=report_id,
            user_id=user_id,
            name=cleaned["name"],
            description=cleaned["description"],
            config=cleaned["config"],
        )
        messages.success(request, "Dashboard updated successfully.")
        return redirect("dashboard_list")


class DashboardDeleteView(LoginRequiredMixin, View):
    """POST-only delete endpoint — GET silently redirects to the list page."""

    http_method_names = ("post", "get")

    def get(
        self, request: HttpRequest, report_id: str, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Redirect GET requests to the list page (delete is POST-only).

        Args:
            request: The incoming HTTP request.
            report_id: UUID of the dashboard (from the URL).

        Returns:
            A redirect to ``dashboard_list``.
        """
        # Preserve legacy behaviour: GET to the delete URL is a no-op redirect.
        return redirect("dashboard_list")

    def post(
        self, request: HttpRequest, report_id: str, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Remove the dashboard and redirect to the list page.

        Args:
            request: The incoming HTTP request.
            report_id: UUID of the dashboard to delete (from the URL).

        Returns:
            A redirect to ``dashboard_list`` with a success or error flash
            message.
        """
        if remove_dashboard(report_id, str(request.user.id)):
            messages.success(request, "Dashboard deleted.")
        else:
            messages.error(request, "Dashboard not found or already deleted.")
        return redirect("dashboard_list")


# ---------------------------------------------------------------------------
# Rendered dashboard (detail) + per-widget HTMX partial
# ---------------------------------------------------------------------------


def _parse_offset(raw: str | None) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _resolve_runtime(request: HttpRequest, default_range_preset: str, website_id: str) -> dict[str, Any]:
    """Parse the runtime date range + ad-hoc filters from the query string.

    Mirrors the analytics filter bar so a saved dashboard is interactively
    sliceable. Everything lives in the query string (bookmarkable); the
    dashboard's own ``dateRange`` is the default when ``?range=`` is absent.
    """
    offset = 0
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start and end:
        try:
            date_range: DateRange | None = DateRange(
                datetime.fromisoformat(start), datetime.fromisoformat(end)
            )
        except ValueError:
            date_range = None
        range_preset = "custom"
    else:
        range_preset = request.GET.get("range") or default_range_preset
        if range_preset not in VALID_RANGE_PRESETS:
            range_preset = (
                default_range_preset if default_range_preset in VALID_RANGE_PRESETS else _FALLBACK_RANGE
            )
        date_range = resolve_date_range(range_preset)
        offset = _parse_offset(request.GET.get("offset"))
        if offset and date_range is not None:
            shift = (date_range.end_date - date_range.start_date) * offset
            date_range = DateRange(date_range.start_date - shift, date_range.end_date - shift)
    if date_range is None:
        date_range = resolve_date_range(_FALLBACK_RANGE)

    granularity = request.GET.get("granularity", "auto")
    if granularity != "auto" and granularity not in VALID_GRANULARITIES:
        granularity = "auto"

    raw = [*request.GET.getlist("filter"), *request.GET.getlist("f")]
    active_filters = parse_filters_from_params(raw) if raw else []

    bot_filter = request.GET.get("bot_filter") == "1"
    filters = list(active_filters)
    if bot_filter and website_id:
        payload = load_bot_filter_payload(str(website_id))
        if payload is not None:
            filters.append(Filter(column="__bot_filter__", operator="eq", value=payload))

    return {
        "date_range": date_range,
        "range_preset": range_preset,
        "granularity": granularity,
        "range_offset": offset,
        "current_range": date_range,
        "active_filters": active_filters,
        "filters": filters,
        "bot_filter": bot_filter,
    }


class DashboardDetailView(LoginRequiredMixin, View):
    """Render a saved dashboard: filter bar + the widget grid (lazy-loaded by HTMX)."""

    template_name = "dashboards/dashboard_detail.html"

    def get(self, request: HttpRequest, report_id: str) -> HttpResponse:
        dashboard = get_dashboard_detail(str(report_id), str(request.user.id))
        if dashboard is None:
            messages.error(request, "Dashboard not found.")
            return redirect("dashboard_list")
        config = dashboard.get("config") or {}
        website_id = dashboard.get("websiteId") or ""
        default_range = config.get("dateRange")
        if not isinstance(default_range, str):
            default_range = _FALLBACK_RANGE
        runtime = _resolve_runtime(request, default_range, website_id)
        widgets = [w for w in config.get("widgets", []) if isinstance(w, dict)]
        layout = config.get("layout") if isinstance(config.get("layout"), dict) else {}
        ctx = {
            "dashboard": dashboard,
            "website_id": website_id,
            "selected_website": website_id,
            "selected_website_name": dashboard.get("name"),
            "websites": [],
            "columns": layout.get("columns", 12),
            "widgets": widgets,
            "range_preset": runtime["range_preset"],
            "granularity": runtime["granularity"],
            "range_offset": runtime["range_offset"],
            "current_range": runtime["current_range"],
            "active_filters": runtime["active_filters"],
            "bot_filter": runtime["bot_filter"],
        }
        return render(request, self.template_name, ctx)


class DashboardWidgetView(LoginRequiredMixin, View):
    """HTMX partial: render a single widget's data with the current runtime filters."""

    template_name = "dashboards/_widget.html"

    def get(self, request: HttpRequest, report_id: str, widget_id: str) -> HttpResponse:
        dashboard = get_dashboard_detail(str(report_id), str(request.user.id))
        if dashboard is None:
            raise Http404("Dashboard not found")
        config = dashboard.get("config") or {}
        website_id = dashboard.get("websiteId") or ""
        widget = next(
            (
                w
                for w in config.get("widgets", [])
                if isinstance(w, dict) and str(w.get("id")) == str(widget_id)
            ),
            None,
        )
        if widget is None:
            raise Http404("Widget not found")
        default_range = config.get("dateRange")
        if not isinstance(default_range, str):
            default_range = _FALLBACK_RANGE
        runtime = _resolve_runtime(request, default_range, website_id)
        rendered = render_widget(
            website_id,
            config,
            widget,
            runtime_range=runtime["date_range"],
            runtime_filters=runtime["filters"],
        )
        return render(request, self.template_name, {"w": rendered})


class DashboardWidgetPreviewView(LoginRequiredMixin, View):
    """POST an *unsaved* widget config → its rendered partial (builder live preview)."""

    http_method_names = ("post",)
    template_name = "dashboards/_widget.html"

    def post(self, request: HttpRequest, report_id: str) -> HttpResponse:
        dashboard = get_dashboard_detail(str(report_id), str(request.user.id))
        if dashboard is None:
            raise Http404("Dashboard not found")
        website_id = dashboard.get("websiteId") or ""
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        widget = payload.get("widget") if isinstance(payload, dict) else None
        if not isinstance(widget, dict):
            return render(request, self.template_name, {"w": {"error": "Invalid widget config"}})
        dashboard_cfg = {
            "filters": payload.get("dashboardFilters") or [],
            "dateRange": payload.get("dashboardDateRange"),
        }
        default_range = dashboard_cfg.get("dateRange")
        if not isinstance(default_range, str):
            default_range = _FALLBACK_RANGE
        runtime = _resolve_runtime(request, default_range, website_id)
        rendered = render_widget(
            website_id,
            dashboard_cfg,
            widget,
            runtime_range=runtime["date_range"],
            runtime_filters=runtime["filters"],
        )
        return render(request, self.template_name, {"w": rendered})
