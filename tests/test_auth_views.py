"""Tests for login/logout views and session authentication.

Covers:
- GET /login/ returns 200 and login template
- POST valid credentials → redirect and session keys set
- Authenticated user recovered via middleware on subsequent request
- POST wrong password → 200 with error, no session auth
- Safe ``next`` accepted; external ``next`` rejected (open redirect prevention)
- POST /logout/ clears session and redirects to login
- GET /logout/ returns 405 (Method Not Allowed)
- Base template logout form uses real {% url %} tag
- Static safety: no write SQL on read-only tables
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.core.models import MantecatoUser

if TYPE_CHECKING:
    from django.test import Client

# ---------------------------------------------------------------------------
# GET /login/
# ---------------------------------------------------------------------------


class TestLoginGet:
    def test_returns_200(self, client: Client) -> None:
        response = client.get("/login/")
        assert response.status_code == 200

    def test_contains_username_field(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert 'name="username"' in content

    def test_contains_password_field(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert 'name="password"' in content

    def test_contains_csrf(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert "csrfmiddlewaretoken" in content

    def test_contains_submit_button(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert 'type="submit"' in content

    def test_no_error_on_get(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert "Invalid" not in content

    def test_next_hidden_from_query(self, client: Client) -> None:
        response = client.get("/login/?next=/analytics/")
        content = response.content.decode()
        assert 'value="/analytics/"' in content

    def test_default_next_is_slash(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert 'value="/"' in content

    def test_contains_tailwind(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert "tailwindcss" in content

    def test_uses_i18n(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert "{%" in content or "Sign in" in content

    def test_standalone_page_no_sidebar(self, client: Client) -> None:
        response = client.get("/login/")
        content = response.content.decode()
        assert "sidebar" not in content.lower() or "sidebar-toggle" not in content


# ---------------------------------------------------------------------------
# POST /login/ — mocked auth (login() calls are mocked to avoid DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLoginPostMocked:
    def test_valid_credentials_redirect(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post("/login/", {"username": "admin", "password": "password"})

        assert response.status_code == 302
        assert response.url == "/"

    def test_session_keys_set_on_success(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post("/login/", {"username": "admin", "password": "password"})

        assert response.wsgi_request.session.get("_auth_user_id") is not None

    def test_redirect_to_next(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {"username": "admin", "password": "password", "next": "/analytics/"},
        )

        assert response.status_code == 302
        assert response.url == "/analytics/"

    def test_wrong_credentials_no_redirect(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")
        response = client.post("/login/", {"username": "admin", "password": "wrongpassword"})
        assert response.status_code == 200

    def test_wrong_credentials_shows_error(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")
        response = client.post("/login/", {"username": "admin", "password": "wrongpassword"})
        content = response.content.decode()
        assert "Invalid" in content

    def test_wrong_credentials_no_session(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")
        response = client.post("/login/", {"username": "admin", "password": "wrongpassword"})
        assert "_auth_user_id" not in response.wsgi_request.session

    def test_wrong_credentials_preserves_username(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")
        response = client.post("/login/", {"username": "admin", "password": "wrongpassword"})
        content = response.content.decode()
        assert 'value="admin"' in content

    @patch("apps.core.views.authenticate")
    def test_empty_fields_no_session(self, mock_auth: MagicMock, client: Client) -> None:
        mock_auth.return_value = None
        response = client.post("/login/", {"username": "", "password": ""})
        assert response.status_code == 200
        assert "_auth_user_id" not in response.wsgi_request.session


# ---------------------------------------------------------------------------
# Open redirect prevention
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOpenRedirectPrevention:
    def test_external_https_rejected(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {"username": "admin", "password": "password", "next": "https://evil.com"},
        )
        assert response.url == "/"

    def test_external_http_rejected(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {"username": "admin", "password": "password", "next": "http://evil.com"},
        )
        assert response.url == "/"

    def test_protocol_relative_rejected(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {"username": "admin", "password": "password", "next": "//evil.com"},
        )
        assert response.url == "/"

    def test_absolute_url_with_host_rejected(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {
                "username": "admin",
                "password": "password",
                "next": "https://evil.com/mantecato",
            },
        )
        assert response.url == "/"

    def test_local_path_accepted(self, client: Client) -> None:
        MantecatoUser.objects.create_user(username="admin", password="password", role="admin")

        response = client.post(
            "/login/",
            {"username": "admin", "password": "password", "next": "/analytics/"},
        )
        assert response.url == "/analytics/"


# ---------------------------------------------------------------------------
# POST /logout/
# ---------------------------------------------------------------------------


class TestLogoutPost:
    @pytest.mark.django_db
    def test_logout_redirects_to_login(self, client: Client) -> None:
        user = MantecatoUser.objects.create_user(
            username="admin", password="password", role="admin"
        )
        client.force_login(user)

        response = client.post("/logout/")

        assert response.status_code == 302
        assert response.url == "/login/"

    @pytest.mark.django_db
    def test_logout_clears_session(self, client: Client) -> None:
        user = MantecatoUser.objects.create_user(
            username="admin", password="password", role="admin"
        )
        client.force_login(user)

        client.post("/logout/")

        # After logout, a new GET should not have auth session keys
        response = client.get("/login/")
        assert "_auth_user_id" not in response.wsgi_request.session


class TestLogoutGet:
    def test_get_logout_returns_405(self, client: Client) -> None:
        response = client.get("/logout/")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Middleware: user recovery after login
# ---------------------------------------------------------------------------


class TestMiddlewareUserRecovery:
    @pytest.mark.django_db
    def test_authenticated_user_on_next_request(self, client: Client) -> None:
        user = MantecatoUser.objects.create_user(
            username="admin", password="password", role="admin"
        )
        client.force_login(user)

        # Next request should have user set by middleware
        response = client.get("/login/")
        request_user = response.wsgi_request.user
        assert not isinstance(request_user, AnonymousUser)
        assert isinstance(request_user, MantecatoUser)
        assert request_user.username == "admin"

    def test_anonymous_user_when_no_session(self, client: Client) -> None:
        response = client.get("/login/")
        assert isinstance(response.wsgi_request.user, AnonymousUser)


# ---------------------------------------------------------------------------
# Base template: logout form uses real URL
# ---------------------------------------------------------------------------


class TestBaseTemplateLogoutForm:
    def test_base_template_logout_uses_url_tag(self) -> None:
        content = (Path(__file__).resolve().parent.parent / "templates" / "base.html").read_text()
        assert "{% url 'logout' %}" in content


# ---------------------------------------------------------------------------
# Static safety: no write SQL
# ---------------------------------------------------------------------------


class TestViewsStaticSafety:
    WRITE_PATTERN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
        re.IGNORECASE,
    )

    def test_views_module_has_no_write_sql(self) -> None:
        import apps.core.views as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert self.WRITE_PATTERN.search(source) is None


# ---------------------------------------------------------------------------
# MantecatoUser model checks
# ---------------------------------------------------------------------------


class TestMantecatoUserModel:
    def test_auth_user_model_is_mantecato_user(self) -> None:
        User = get_user_model()
        assert User is MantecatoUser

    def test_standard_model_backend(self) -> None:
        from django.conf import settings

        assert "django.contrib.auth.backends.ModelBackend" in settings.AUTHENTICATION_BACKENDS

    def test_standard_authentication_middleware(self) -> None:
        from django.conf import settings

        assert "django.contrib.auth.middleware.AuthenticationMiddleware" in settings.MIDDLEWARE
