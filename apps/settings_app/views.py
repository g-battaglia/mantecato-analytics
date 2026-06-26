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
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.analytics.services import resolve_websites_for_user
from apps.common.constants import COUNTRY_CHOICES_SORTED
from apps.common.forms import (
    ApiKeyForm,
    BotConfigForm,
    ChangePasswordForm,
    UmamiImportForm,
    UserCreateForm,
    UserEditForm,
    WebsiteModelForm,
    first_error,
)
from apps.core.models import Website
from apps.settings_app.services import (
    UserActionError,
    change_own_password,
    create_user_account,
    create_website,
    generate_new_api_key,
    get_all_users,
    get_api_keys_for_user,
    get_bot_config,
    get_latest_umami_import_job,
    get_umami_import_job,
    get_user,
    purge_website_data,
    remove_api_key,
    save_bot_config,
    set_website_badge,
    soft_delete_user,
    soft_delete_website,
    start_umami_import_job,
    update_user_account,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def _accessible_sites(request: HttpRequest) -> list[dict]:
    """Return the (id, name) of every website the current user can access.

    Wraps :func:`apps.analytics.services.resolve_websites_for_user` so the
    settings templates render a single dropdown source.
    """
    return resolve_websites_for_user(str(request.user.id), request.user.is_staff)


def _assert_website_accessible(request: HttpRequest, website_id: str) -> None:
    """Raise :class:`~django.http.Http404` unless the user owns *website_id*.

    Guards object-level access for views that take a website id straight from
    the request (``?website=`` / ``website_id``). Returning 404 (rather than
    403) also avoids disclosing the existence of websites the user can't see.
    """
    accessible = {s["id"] for s in _accessible_sites(request)}
    if website_id not in accessible:
        raise Http404("Website not found.")


class _AdminRequiredMixin(LoginRequiredMixin):
    """Restrict a view to admin (``is_staff``) users.

    Unauthenticated users fall through to :class:`LoginRequiredMixin`'s login
    redirect; authenticated non-admins get a ``403``. Used for the Umami import,
    which can mutate analytics data across the whole instance.
    """

    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Reject authenticated non-admins with ``PermissionDenied`` (403)."""
        if request.user.is_authenticated and not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


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
        _assert_website_accessible(request, website_id)
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
        _assert_website_accessible(request, website_id)
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


class SitePurgeView(LoginRequiredMixin, View):
    """Purge ALL tracking data for a website (POST only).

    Requires the user to confirm by submitting the exact site name in a
    hidden + JS-validated field. The confirmation happens client-side via
    a modal that forces the user to type the full site name.
    """

    def get(self, request: HttpRequest, site_id: str) -> HttpResponse:
        return redirect("site_list")

    def post(self, request: HttpRequest, site_id: str) -> HttpResponse:
        confirm_name = request.POST.get("confirm_name", "").strip()
        site = Website.objects.filter(id=site_id, is_deleted=False).first()
        if site is None:
            messages.error(request, "Site not found.")
            return redirect("site_list")

        if confirm_name != site.name:
            messages.error(request, "Site name confirmation did not match. Purge aborted.")
            return redirect("site_list")

        result = purge_website_data(
            site_id=str(site_id),
            user_id=str(request.user.id),
            is_admin=request.user.is_staff,
        )
        if result is None:
            messages.error(request, "Site not found or access denied.")
        else:
            messages.success(
                request,
                f"Purged all data for '{result['name']}': "
                f"{result['events']:,} events, {result['visitor_rows']:,} visitor count rows.",
            )
        return redirect("site_list")


class SiteBadgeView(LoginRequiredMixin, View):
    """Manage a site's public README view-counter badge.

    ``GET`` shows the badge state with a ready-to-paste snippet (absolute URL
    built from the current request host, so the operator never has to know it).
    ``POST`` with ``action`` ∈ ``enable|regenerate|disable`` toggles the site's
    ``share_id`` (the badge endpoint is gated on it). A site needs no real
    domain — a name-only "site" is a valid README/badge-only entry.
    """

    template_name = "settings/site_badge.html"

    def _get_site(self, request: HttpRequest, site_id: str) -> Website | None:
        qs = Website.objects.filter(id=site_id, is_deleted=False)
        if not request.user.is_staff:
            qs = qs.filter(user_id=request.user.id)
        return qs.first()

    def get(self, request: HttpRequest, site_id: str) -> HttpResponse:
        site = self._get_site(request, site_id)
        if site is None:
            raise Http404("Website not found.")
        return render(request, self.template_name, self._context(request, site))

    def post(self, request: HttpRequest, site_id: str) -> HttpResponse:
        action = request.POST.get("action", "enable")
        if action not in ("enable", "regenerate", "disable"):
            action = "enable"
        result = set_website_badge(
            site_id=str(site_id),
            user_id=str(request.user.id),
            is_admin=request.user.is_staff,
            action=action,
        )
        if result is None:
            messages.error(request, "Site not found.")
            return redirect("site_list")
        messages.success(
            request,
            {
                "enable": "Badge enabled.",
                "regenerate": "Badge link regenerated — update the old snippet.",
                "disable": "Badge disabled.",
            }[action],
        )
        return redirect("site_badge", site_id=site_id)

    def _context(self, request: HttpRequest, site: Website) -> dict:
        badge_url = markdown = html = None
        if site.share_id:
            path = f"{reverse('tracker_badge')}?share_id={site.share_id}&label=views"
            badge_url = request.build_absolute_uri(path)
            markdown = f"![views]({badge_url})"
            html = f'<img src="{badge_url}" alt="views">'
        return {
            "site": site,
            "badge_url": badge_url,
            "markdown_snippet": markdown,
            "html_snippet": html,
        }


# ============================================================================
# Umami import (background, data-only, single-site)
# ============================================================================


class UmamiImportView(_AdminRequiredMixin, View):
    """Render and start a data-only, single-site Umami import (admin-only).

    ``GET`` renders the form plus the relevant job (``?job=<id>`` or the latest
    one) so a page reload restores the progress bar. ``POST`` validates the
    form, starts the background import via the service layer and redirects
    (post/redirect/get) with ``?job=<id>`` so the progress partial begins polling.
    """

    template_name = "settings/umami_import.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the import form and the current/last job for this user."""
        job_id = request.GET.get("job", "").strip()
        job = (
            get_umami_import_job(job_id, str(request.user.id))
            if job_id
            else get_latest_umami_import_job(str(request.user.id))
        )
        return render(
            request,
            self.template_name,
            {"sites": _accessible_sites(request), "job": job},
        )

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate the form and start the background import, then redirect (PRG)."""
        form = UmamiImportForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return redirect("umami_import")
        data = form.cleaned_data
        result = start_umami_import_job(
            user_id=str(request.user.id),
            target_website=str(data["target_website"]),
            source_website=str(data["source_website"]),
            source_dsn=data["source_dsn"],
            since_date=data["since"],
            replace=data["replace"],
        )
        messages.success(request, "Umami import started.")
        return redirect(f"{request.path}?job={result['id']}")


class UmamiImportStatusView(_AdminRequiredMixin, View):
    """HTMX polling endpoint: render the progress partial for a single job."""

    template_name = "settings/_umami_import_progress.html"

    def get(
        self, request: HttpRequest, job_id: str, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Render the progress partial for *job_id* (scoped to the current user)."""
        job = get_umami_import_job(str(job_id), str(request.user.id))
        return render(request, self.template_name, {"job": job})


# ============================================================================
# User management (admin-only CRUD)
# ============================================================================


class UserListView(_AdminRequiredMixin, View):
    """Render the list of all active users (admin-only)."""

    template_name = "settings/users.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the user list page."""
        return render(request, self.template_name, {"users": get_all_users()})


class UserCreateView(_AdminRequiredMixin, View):
    """Render and process the user-creation form (admin-only)."""

    template_name = "settings/user_form.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the empty user creation form."""
        return render(request, self.template_name, {"action": "create", "form_data": {}})

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and create a new user."""
        form = UserCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return render(request, self.template_name, {"action": "create", "form_data": request.POST})
        try:
            result = create_user_account(
                username=form.cleaned_data["username"],
                role=form.cleaned_data["role"],
                password=form.cleaned_data["password"],
            )
        except UserActionError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {"action": "create", "form_data": request.POST})
        messages.success(request, f"User '{result['username']}' created.")
        return redirect("user_list")


class UserEditView(_AdminRequiredMixin, View):
    """Render and process the user-edit form (admin-only)."""

    template_name = "settings/user_form.html"

    def get(self, request: HttpRequest, user_id: str, *args: object, **kwargs: object) -> HttpResponse:
        """Render the edit form pre-filled with the user's data."""
        user_data = get_user(user_id)
        if user_data is None:
            messages.error(request, "User not found.")
            return redirect("user_list")
        return render(
            request,
            self.template_name,
            {"action": "edit", "form_data": {}, "target_user": user_data},
        )

    def post(self, request: HttpRequest, user_id: str, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and update the user."""
        form = UserEditForm(request.POST)
        target_user = get_user(user_id)
        if target_user is None:
            messages.error(request, "User not found.")
            return redirect("user_list")
        if not form.is_valid():
            messages.error(request, first_error(form))
            return render(
                request,
                self.template_name,
                {"action": "edit", "form_data": request.POST, "target_user": target_user},
            )
        try:
            update_user_account(
                user_id,
                role=form.cleaned_data["role"],
                new_password=form.cleaned_data.get("new_password") or None,
                acting_user_id=str(request.user.id),
            )
        except UserActionError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                self.template_name,
                {"action": "edit", "form_data": request.POST, "target_user": target_user},
            )
        messages.success(request, f"User '{target_user['username']}' updated.")
        return redirect("user_list")


class UserDeleteView(_AdminRequiredMixin, View):
    """Soft-delete a user (POST-only, admin-only)."""

    def get(self, request: HttpRequest, user_id: str, *args: object, **kwargs: object) -> HttpResponse:
        """Redirect GET to the list page (deletion is POST-only)."""
        return redirect("user_list")

    def post(self, request: HttpRequest, user_id: str, *args: object, **kwargs: object) -> HttpResponse:
        """Soft-delete the user with anti-lockout guards."""
        try:
            username = soft_delete_user(user_id, str(request.user.id))
        except UserActionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"User '{username}' deleted.")
        return redirect("user_list")


# ============================================================================
# Self-service account (all logged-in users)
# ============================================================================


class AccountView(LoginRequiredMixin, View):
    """Self-service password change (all logged-in users)."""

    template_name = "settings/account.html"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Render the account/password-change form."""
        return render(request, self.template_name)

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Validate and change the user's own password."""
        form = ChangePasswordForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return render(request, self.template_name)
        try:
            change_own_password(
                request.user,
                current_password=form.cleaned_data["current_password"],
                new_password=form.cleaned_data["new_password"],
            )
        except UserActionError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name)
        # Keep the user logged in after password change.
        update_session_auth_hash(request, request.user)
        messages.success(request, "Password changed successfully.")
        return redirect("account")


# ============================================================================
# Settings landing
# ============================================================================


class SettingsIndexView(LoginRequiredMixin, TemplateView):
    """Top-level ``/settings/`` page (just renders the index template)."""

    template_name = "settings/index.html"
