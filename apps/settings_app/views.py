"""Settings views — API keys, bot config, sites.

All views are class-based, with persistence delegated to
:mod:`apps.settings_app.services`. The decision to keep service calls in
the chain (rather than calling the ORM directly from ``form.save()``) is
the same as in :mod:`apps.dashboards.views`: it preserves the test patch
surface (``@patch("apps.settings_app.views.X")``) and concentrates the
report-table side effects (key hashing, defaults merging) in one module.

URL routing lives in :mod:`apps.settings_app.urls` and uses the historical
URL pattern names (``api_key_list``, ``bot_config``, …) so reverses across
the codebase continue to resolve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.analytics.services import resolve_websites_for_user
from apps.common.constants import COUNTRY_CHOICES_SORTED
from apps.common.forms import (
    ApiKeyForm,
    BotConfigForm,
    WebsiteModelForm,
    first_error,
)
from apps.core.models import Website
from apps.settings_app.services import (
    create_website,
    generate_new_api_key,
    get_api_keys_for_user,
    get_bot_config,
    remove_api_key,
    save_bot_config,
    soft_delete_website,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def _accessible_sites(request: HttpRequest) -> list[dict]:
    """Return the (id, name) of every website the current user can access.

    Wraps :func:`apps.analytics.services.resolve_websites_for_user` so the
    settings templates render a single dropdown source.
    """
    return resolve_websites_for_user(str(request.user.id), request.user.is_staff)


# ============================================================================
# API Keys
# ============================================================================


class ApiKeyListView(LoginRequiredMixin, View):
    """Render the API-key list.

    ``GET``: read-only list of the current user's keys.
    """

    template_name = "settings/api_keys.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the API key list page.

        Args:
            request: The incoming HTTP request.

        Returns:
            The rendered template with the user's API keys and ``new_key``
            set to ``None`` (no key was just created).
        """
        return render(
            request,
            self.template_name,
            {
                "api_keys": get_api_keys_for_user(str(request.user.id)),
                "new_key": None,
            },
        )


class ApiKeyCreateView(LoginRequiredMixin, View):
    """Generate a new API key (POST-only).

    The list template is re-rendered with the freshly-generated raw key, which
    is shown to the user **exactly once** — afterwards only its SHA-256 hash
    remains in the database (see :func:`apps.core.api_keys.hash_key`).
    """

    template_name = "settings/api_keys.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Redirect GET to the list page (creation is POST-only).

        Args:
            request: The incoming HTTP request.

        Returns:
            A redirect to ``api_key_list``.
        """
        return redirect("api_key_list")

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Generate a new API key and re-render the list with the raw key visible.

        The raw key is included in the template context as ``new_key`` so
        the user can copy it. After this response the raw key is lost
        forever -- only its SHA-256 hash persists in the database.

        Args:
            request: The incoming HTTP request carrying POST data.

        Returns:
            The rendered key list with the freshly-generated raw key, or
            a redirect on validation failure.
        """
        user_id = str(request.user.id)
        form = ApiKeyForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return redirect("api_key_list")

        result = generate_new_api_key(user_id, form.cleaned_data["name"], scopes=form.scope_list())
        messages.success(request, "API key created. Copy it now — it won't be shown again.")
        return render(
            request,
            self.template_name,
            {
                "api_keys": get_api_keys_for_user(user_id),
                "new_key": result,
            },
        )


class ApiKeyDeleteView(LoginRequiredMixin, View):
    """Revoke an API key by id (POST-only)."""

    def get(self, request: HttpRequest, key_id: str) -> HttpResponse:
        """Redirect GET to the list page (revocation is POST-only).

        Args:
            request: The incoming HTTP request.
            key_id: UUID of the API key (from the URL).

        Returns:
            A redirect to ``api_key_list``.
        """
        return redirect("api_key_list")

    def post(self, request: HttpRequest, key_id: str) -> HttpResponse:
        """Revoke (delete) the API key and redirect to the list.

        Args:
            request: The incoming HTTP request.
            key_id: UUID of the API key to revoke (from the URL).

        Returns:
            A redirect to ``api_key_list`` with a success or error flash.
        """
        if remove_api_key(key_id, str(request.user.id)):
            messages.success(request, "API key revoked.")
        else:
            messages.error(request, "API key not found.")
        return redirect("api_key_list")


# ============================================================================
# Bot config
# ============================================================================


class BotConfigView(LoginRequiredMixin, View):
    """GET / POST the per-website bot-detection config.

    The view is intentionally **not** a :class:`~django.views.generic.UpdateView`
    because the object is keyed by a query-string parameter (``?website=``)
    rather than a URL kwarg, and the underlying row is created on first save
    rather than required up-front.
    """

    template_name = "settings/bot_config.html"

    def _website_id(self, request: HttpRequest) -> str:
        """Extract the website UUID from GET or POST parameters.

        Checks ``?website=`` first (GET), then ``website_id`` in POST data.
        This dual-source approach covers both the initial page load (GET
        with query param) and form submissions (POST with hidden field).

        Args:
            request: The incoming HTTP request.

        Returns:
            The stripped website UUID string, or ``""`` when absent.
        """
        return request.GET.get("website", "").strip() or request.POST.get("website_id", "").strip()

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the bot config form for the selected website.

        Without a ``?website=`` parameter the page renders a placeholder
        prompting the user to select a website from the dropdown.

        Args:
            request: The incoming HTTP request.

        Returns:
            The rendered bot-config template.
        """
        website_id = self._website_id(request)
        sites = _accessible_sites(request)
        if not website_id:
            return render(
                request,
                self.template_name,
                {
                    "config": None,
                    "website_id": "",
                    "sites": sites,
                    "country_choices": COUNTRY_CHOICES_SORTED,
                },
            )
        config = get_bot_config(website_id)
        return render(
            request,
            self.template_name,
            {
                "config": config.get("config", {}),
                "website_id": website_id,
                "sites": sites,
                "country_choices": COUNTRY_CHOICES_SORTED,
            },
        )

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and save the bot config, then redirect back to the form.

        The redirect preserves the ``?website=`` query parameter so the
        user sees the updated config for the same website after saving.

        Args:
            request: The incoming HTTP request carrying POST data.

        Returns:
            A redirect to the same page with the ``?website=`` parameter.
        """
        website_id = self._website_id(request)
        if not website_id:
            return render(request, self.template_name, {"config": None, "website_id": ""})
        form = BotConfigForm(request.POST)
        if form.is_valid():
            save_bot_config(str(request.user.id), website_id, form.to_config())
            messages.success(request, "Bot config saved.")
        else:
            messages.error(request, first_error(form))
        return redirect(f"{request.path}?website={website_id}")


# ============================================================================
# Sites (tracked websites)
# ============================================================================


class SiteListView(LoginRequiredMixin, View):
    """List the websites the current user can manage.

    Admins (``role == "admin"``) see every non-deleted website; regular users
    see only the websites they own.
    """

    template_name = "settings/sites.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the list of tracked websites.

        Admin users see all non-deleted websites; regular users see only
        their own. The list is ordered alphabetically by name.

        Args:
            request: The incoming HTTP request.

        Returns:
            The rendered sites list template.
        """
        qs = Website.objects.filter(is_deleted=False)
        if not request.user.is_staff:
            qs = qs.filter(user_id=request.user.id)
        return render(
            request,
            self.template_name,
            {"sites": qs.order_by("name")},
        )


class SiteCreateView(LoginRequiredMixin, View):
    """Render and process the website-creation form.

    The new ``Website`` row is stamped with ``user_id = request.user.id`` so
    non-admin users see their own creations on the list page.
    """

    template_name = "settings/site_form.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the empty website creation form.

        Args:
            request: The incoming HTTP request.

        Returns:
            The rendered site form template with ``action="create"``.
        """
        return render(request, self.template_name, {"action": "create", "form_data": {}})

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and persist a new website, stamping the current user as owner.

        The ``user_id`` is set to ``request.user.id`` before saving so that
        non-admin users see their own creations on the list page.

        Args:
            request: The incoming HTTP request carrying POST data.

        Returns:
            A redirect to ``site_list`` on success, or the re-rendered
            form on validation failure.
        """
        form = WebsiteModelForm(data=request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return render(
                request,
                self.template_name,
                {"action": "create", "form_data": request.POST},
            )
        # Delegate persistence to the service layer (consistent with
        # dashboards and the other CRUD sections)
        result = create_website(
            name=form.cleaned_data["name"],
            user_id=str(request.user.id),
            domain=form.cleaned_data.get("domain") or None,
            share_id=form.cleaned_data.get("share_id") or None,
        )
        messages.success(request, f"Site '{result['name']}' created.")
        return redirect("site_list")


class SiteDeleteView(LoginRequiredMixin, View):
    """Soft-delete a website (POST only; GET silently redirects).

    Soft delete = ``is_deleted = True`` so the row stays for historical
    reference and analytics joins keep resolving.
    """

    http_method_names = ("post", "get")

    def get(self, request: HttpRequest, site_id: str) -> HttpResponse:
        """Redirect GET to the list page (deletion is POST-only).

        Args:
            request: The incoming HTTP request.
            site_id: UUID of the website (from the URL).

        Returns:
            A redirect to ``site_list``.
        """
        return redirect("site_list")

    def post(self, request: HttpRequest, site_id: str) -> HttpResponse:
        """Soft-delete the website by setting ``is_deleted=True``.

        Soft deletion preserves the row for historical analytics joins --
        events that reference this ``website_id`` continue to resolve. Only
        the ``is_deleted`` column is updated to keep the write minimal.

        Args:
            request: The incoming HTTP request.
            site_id: UUID of the website to delete (from the URL).

        Returns:
            A redirect to ``site_list`` with a success or error flash.
        """
        # Delegate to service layer; returns site name on success, None on miss
        name = soft_delete_website(
            site_id=site_id,
            user_id=str(request.user.id),
            is_admin=request.user.is_staff,
        )
        if name is None:
            messages.error(request, "Site not found.")
        else:
            messages.success(request, f"Site '{name}' deleted.")
        return redirect("site_list")


# ============================================================================
# Settings landing
# ============================================================================


class SettingsIndexView(LoginRequiredMixin, TemplateView):
    """Top-level ``/settings/`` page (just renders the index template)."""

    template_name = "settings/index.html"
