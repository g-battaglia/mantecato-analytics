"""Core views: login, logout, health check.

This module is intentionally thin: the bulk of the auth machinery comes from
:mod:`django.contrib.auth.views` (``LoginView`` / ``LogoutView``). Only two
small adaptations are needed:

- :class:`LoginView` exposes ``error`` and ``username`` context keys consumed
  by the existing :file:`templates/login.html` (which predates Django's
  ``AuthenticationForm`` integration in the template).
- A module-level ``authenticate`` re-export lets older tests patch
  ``apps.core.views.authenticate`` without changes; the CBV itself relies on
  Django's standard ``AuthenticationForm``.

:func:`health_check` stays as a plain function — it has no shared behaviour
with the auth flow and using a CBV would add no value.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.auth import authenticate, login, logout  # noqa: F401  re-exported for tests
from django.contrib.auth.views import LoginView as _BaseLoginView
from django.contrib.auth.views import LogoutView as _BaseLogoutView
from django.db import connections
from django.http import JsonResponse

if TYPE_CHECKING:
    from typing import Any

    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class LoginView(_BaseLoginView):
    """Render and process the sign-in form.

    Wraps :class:`django.contrib.auth.views.LoginView` with:

    - ``template_name = "login.html"``: matches the project's existing template.
    - ``redirect_authenticated_user = True``: skips the form when the visitor
      already has a session.
    - Extra context (``error``, ``username``) so the existing template can
      keep its current markup unchanged.

    Open-redirect protection comes for free: Django's
    :func:`~django.utils.http.url_has_allowed_host_and_scheme` is called on
    the ``next`` parameter before any redirect.
    """

    template_name = "login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add legacy template context keys (``error``, ``username``, ``next``).

        The existing ``login.html`` template predates Django's built-in
        ``AuthenticationForm`` integration and expects three custom keys:

        - ``error`` (bool): whether the form submission failed.
        - ``username`` (str): re-fills the username input after failure.
        - ``next`` (str): the post-login redirect target (never blank).

        Args:
            **kwargs: Additional context from the URL resolver.

        Returns:
            The template context dict.
        """
        ctx = super().get_context_data(**kwargs)
        form = ctx.get("form")
        # Mirror the legacy template's context contract: ``error`` is a bool
        # used by ``{% if error %}``, ``username`` re-fills the input field,
        # and ``next`` falls back to ``"/"`` so the hidden input always has a
        # non-empty value.
        ctx["error"] = bool(form and form.is_bound and not form.is_valid())
        ctx["username"] = (
            self.request.POST.get("username", "") if self.request.method == "POST" else ""
        )
        ctx["next"] = ctx.get(self.redirect_field_name) or "/"
        return ctx


class LogoutView(_BaseLogoutView):
    """POST-only logout; redirects to the sign-in page.

    Django 5.x already enforces POST-only by default and returns 405 on GET,
    matching the behaviour expected by the legacy test suite.
    """

    next_page = "/login/"


def health_check(request: HttpRequest) -> JsonResponse:
    """Return JSON status indicating Django and DB connectivity.

    Used by the reverse proxy / Kubernetes liveness probe.

    Behaviour:
        - GET /health/ → 200 with ``{"status": "ok", "database": "ok"}``.
        - On DB failure → 503 with ``{"status": "unhealthy", "database": "error"}``.

    The DB check executes ``SELECT 1`` rather than opening an ORM query, so it
    works without any application table being present.
    """
    db_status = "ok"

    try:
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.warning("Health check: database unreachable", exc_info=True)
        db_status = "error"

    if db_status == "ok":
        return JsonResponse({"status": "ok", "database": "ok"})

    return JsonResponse({"status": "unhealthy", "database": "error"}, status=503)
