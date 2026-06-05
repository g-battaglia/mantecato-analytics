"""Shared pytest fixtures and constants for the Mantecato v3 test suite.

Centralises the authenticated-client and API-key-auth setup that the test
modules previously redefined individually.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from django.test import Client

from apps.core.models import MantecatoUser

if TYPE_CHECKING:
    from collections.abc import Iterator

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
WEBSITE_ID = "a0000000-0000-0000-0000-000000000001"
REPORT_ID = "c0000000-0000-0000-0000-000000000001"
API_TOKEN = "Bearer mtk_test_token_1234567890"


def make_admin_user() -> MantecatoUser:
    """Build an in-memory admin user (no DB row)."""
    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    return user


@contextmanager
def patch_session_user(user: MantecatoUser | None = None) -> Iterator[MantecatoUser]:
    """Patch ``AuthenticationMiddleware`` so ``request.user`` is *user*."""
    user = user or make_admin_user()
    with patch(
        "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"
    ) as mock_process:
        mock_process.side_effect = lambda request: setattr(request, "user", user)
        yield user


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def admin_user() -> MantecatoUser:
    return make_admin_user()


def force_login_admin(client: Client) -> MantecatoUser:
    """Authenticate *client* as an in-memory admin user without DB hits.

    ``client.force_login`` fires the ``user_logged_in`` signal whose stock
    receiver writes the ``last_login`` timestamp back to the user row. We
    patch ``Signal.send`` for the duration of the call so the helper works
    without ``django_db``.

    Returns:
        The :class:`apps.core.models.MantecatoUser` instance used to log in.
        Callers can hand it to :func:`patch_session_user` so subsequent
        requests see the same identity through ``AuthenticationMiddleware``.
    """
    from django.contrib.auth.signals import user_logged_in

    user = make_admin_user()
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)
    return user


@pytest.fixture
def authenticated_client() -> Iterator[Client]:
    """A test client with an authenticated admin web session (no DB hit).

    Combines :func:`force_login_admin` (sets the session cookie) with
    :func:`patch_session_user` (intercepts ``AuthenticationMiddleware``).
    """
    test_client = Client()
    user = force_login_admin(test_client)
    with patch_session_user(user):
        yield test_client


@pytest.fixture
def api_auth() -> Iterator[None]:
    """Patch the API-key middleware so requests carrying ``API_TOKEN`` authenticate."""
    with patch("mantecato.middleware.validate_api_key") as mock_validate:
        mock_validate.return_value = {
            "userId": ADMIN_USER_ID,
            "scopes": ["read", "write", "admin"],
        }
        yield
