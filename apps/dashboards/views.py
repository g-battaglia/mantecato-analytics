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
from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import ListView

from apps.common.forms import DashboardModelForm, first_error
from apps.dashboards.services import (
    create_new_dashboard,
    get_dashboard_detail,
    get_dashboards_for_user,
    remove_dashboard,
    update_existing_dashboard,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


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
        create_new_dashboard(
            user_id=str(request.user.id),
            website_id=str(cleaned["website_id"]),
            name=cleaned["name"],
            description=cleaned["description"],
            config=cleaned["config"] or {},
        )
        messages.success(request, "Dashboard created successfully.")
        return redirect("dashboard_list")


class DashboardUpdateView(LoginRequiredMixin, View):
    """Render and process the edit form for a single owned dashboard."""

    template_name = "dashboards/dashboard_form.html"

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
