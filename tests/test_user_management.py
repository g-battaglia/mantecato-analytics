"""Tests for user management: service layer, views, forms, and anti-lockout guards.

Covers:
- Service functions: create, update, soft-delete, change password, guards.
- Views: admin-only access (403 for non-admin, 302 for anonymous), PRG pattern.
- Forms: validation (password length, match, blank username).
- Anti-lockout: cannot self-delete, cannot demote/delete last admin.
- Default password flag: set by createuser --password-is-default, cleared on change.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings as django_settings
from django.test import Client

from apps.common.forms import (
    MIN_PASSWORD_LENGTH,
    ChangePasswordForm,
    UserCreateForm,
    UserEditForm,
)
from apps.core.models import MantecatoUser
from apps.settings_app.services import (
    UserActionError,
    change_own_password,
    create_user_account,
    get_all_users,
    get_user,
    soft_delete_user,
    update_user_account,
)

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "b0000000-0000-0000-0000-000000000002"

# Migration 0002 uses PostgreSQL-only SQL (SET DEFAULT now()); skip DB tests on SQLite.
_requires_postgres = pytest.mark.skipif(
    django_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3",
    reason="Requires PostgreSQL (migration 0002 breaks SQLite)",
)


# ============================================================================
# Helpers
# ============================================================================


def _login_as_admin(client: Client) -> MantecatoUser:
    """Force-login as admin, patching the login signal (no DB required)."""
    from django.contrib.auth.signals import user_logged_in

    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)
    return user


def _login_as_nonadmin(client: Client) -> MantecatoUser:
    """Force-login as regular user, patching the login signal (no DB required)."""
    from django.contrib.auth.signals import user_logged_in

    user = MantecatoUser(username="regular", role="user")
    user.pk = OTHER_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)
    return user


def _patch_middleware_user(user: MantecatoUser):
    """Patch AuthenticationMiddleware to set request.user."""
    return patch(
        "django.contrib.auth.middleware.AuthenticationMiddleware.process_request",
        side_effect=lambda request: setattr(request, "user", user),
    )


# ============================================================================
# Service layer tests (DB-backed)
# ============================================================================


@pytest.mark.django_db
@_requires_postgres
class TestCreateUserAccount:
    def test_creates_user(self) -> None:
        result = create_user_account("alice", "user", "password123")
        assert result["username"] == "alice"
        assert result["role"] == "user"
        assert MantecatoUser.objects.filter(username="alice", deleted_at__isnull=True).exists()

    def test_rejects_duplicate_username(self) -> None:
        create_user_account("bob", "user", "password123")
        with pytest.raises(UserActionError, match="already exists"):
            create_user_account("bob", "admin", "otherpass1")

    def test_password_is_hashed(self) -> None:
        create_user_account("carol", "user", "mypassword1")
        user = MantecatoUser.objects.get(username="carol")
        assert not user.check_password("wrongpass1")
        assert user.check_password("mypassword1")

    def test_new_user_password_is_default_false(self) -> None:
        create_user_account("dave", "user", "password123")
        user = MantecatoUser.objects.get(username="dave")
        assert user.password_is_default is False


@pytest.mark.django_db
@_requires_postgres
class TestUpdateUserAccount:
    def test_updates_role(self) -> None:
        user = MantecatoUser.objects.create_user("alice", "password123", "user")
        update_user_account(str(user.id), role="admin", acting_user_id=ADMIN_USER_ID)
        user.refresh_from_db()
        assert user.role == "admin"

    def test_resets_password(self) -> None:
        user = MantecatoUser.objects.create_user("bob", "oldpassword1", "user")
        update_user_account(str(user.id), new_password="newpassword1", acting_user_id=ADMIN_USER_ID)
        user.refresh_from_db()
        assert user.check_password("newpassword1")
        assert user.password_is_default is False

    def test_prevents_last_admin_demotion(self) -> None:
        admin = MantecatoUser.objects.create_user("admin1", "password123", "admin")
        with pytest.raises(UserActionError, match="last admin"):
            update_user_account(str(admin.id), role="user", acting_user_id=str(admin.id))

    def test_allows_demotion_when_other_admins_exist(self) -> None:
        admin1 = MantecatoUser.objects.create_user("admin1", "password123", "admin")
        admin2 = MantecatoUser.objects.create_user("admin2", "password123", "admin")
        update_user_account(str(admin1.id), role="user", acting_user_id=str(admin2.id))
        admin1.refresh_from_db()
        assert admin1.role == "user"


@pytest.mark.django_db
@_requires_postgres
class TestSoftDeleteUser:
    def test_soft_deletes(self) -> None:
        user = MantecatoUser.objects.create_user("alice", "password123", "user")
        admin = MantecatoUser.objects.create_user("admin1", "password123", "admin")
        username = soft_delete_user(str(user.id), str(admin.id))
        assert username == "alice"
        user.refresh_from_db()
        assert user.deleted_at is not None

    def test_prevents_self_delete(self) -> None:
        admin = MantecatoUser.objects.create_user("admin1", "password123", "admin")
        with pytest.raises(UserActionError, match="own account"):
            soft_delete_user(str(admin.id), str(admin.id))

    def test_prevents_last_admin_delete(self) -> None:
        admin = MantecatoUser.objects.create_user("admin1", "password123", "admin")
        other_admin = MantecatoUser.objects.create_user("admin2", "password123", "admin")
        # Delete admin2 first, then try to delete admin1 (who would be last)
        soft_delete_user(str(other_admin.id), str(admin.id))
        with pytest.raises(UserActionError, match="last admin"):
            soft_delete_user(str(admin.id), str(other_admin.id))

    def test_raises_on_not_found(self) -> None:
        with pytest.raises(UserActionError, match="not found"):
            soft_delete_user(ADMIN_USER_ID, OTHER_USER_ID)


@pytest.mark.django_db
@_requires_postgres
class TestChangeOwnPassword:
    def test_changes_password(self) -> None:
        user = MantecatoUser.objects.create_user("alice", "oldpassword1", "user")
        change_own_password(user, "oldpassword1", "newpassword1")
        user.refresh_from_db()
        assert user.check_password("newpassword1")
        assert user.password_is_default is False

    def test_rejects_wrong_current_password(self) -> None:
        user = MantecatoUser.objects.create_user("bob", "correctpass1", "user")
        with pytest.raises(UserActionError, match="incorrect"):
            change_own_password(user, "wrongpass1", "newpassword1")


@pytest.mark.django_db
@_requires_postgres
class TestGetAllUsers:
    def test_returns_active_users_ordered(self) -> None:
        MantecatoUser.objects.create_user("bob", "password123", "user")
        MantecatoUser.objects.create_user("alice", "password123", "admin")
        users = get_all_users()
        assert len(users) == 2
        assert users[0]["username"] == "alice"
        assert users[1]["username"] == "bob"

    def test_excludes_deleted(self) -> None:
        user = MantecatoUser.objects.create_user("gone", "password123", "user")
        from django.utils import timezone
        user.deleted_at = timezone.now()
        user.save(update_fields=["deleted_at"])
        assert get_all_users() == []


@pytest.mark.django_db
@_requires_postgres
class TestGetUser:
    def test_returns_user_dict(self) -> None:
        user = MantecatoUser.objects.create_user("alice", "password123", "admin")
        result = get_user(str(user.id))
        assert result is not None
        assert result["username"] == "alice"
        assert result["is_admin"] is True

    def test_returns_none_for_missing(self) -> None:
        assert get_user(ADMIN_USER_ID) is None


# ============================================================================
# View tests (no DB, mocked services)
# ============================================================================


class TestUserViewsAdminOnly:
    """Admin-only routes: 403 for non-admin, 302 for anonymous."""

    ADMIN_ROUTES_GET = [
        "/settings/users/",
        "/settings/users/create/",
    ]

    @pytest.mark.parametrize("url", ADMIN_ROUTES_GET)
    def test_anonymous_redirected_to_login(self, client: Client, url: str) -> None:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    @pytest.mark.parametrize("url", ADMIN_ROUTES_GET)
    def test_non_admin_gets_403(self, client: Client, url: str) -> None:
        user = _login_as_nonadmin(client)
        with _patch_middleware_user(user):
            response = client.get(url)
        assert response.status_code == 403


class TestUserListView:
    @patch("apps.settings_app.views.get_all_users")
    def test_renders_user_list(self, mock_list: MagicMock, client: Client) -> None:
        mock_list.return_value = [
            {"id": ADMIN_USER_ID, "username": "admin", "role": "admin", "is_admin": True,
             "last_login": None, "created_at": "2025-01-01", "password_is_default": False},
        ]
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.get("/settings/users/")
        assert response.status_code == 200
        assert "admin" in response.content.decode()


class TestUserCreateView:
    def test_get_renders_form(self, client: Client) -> None:
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.get("/settings/users/create/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="username"' in content
        assert 'name="password"' in content

    @patch("apps.settings_app.views.create_user_account")
    def test_post_creates_and_redirects(self, mock_create: MagicMock, client: Client) -> None:
        mock_create.return_value = {"id": OTHER_USER_ID, "username": "alice", "role": "user"}
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.post(
                "/settings/users/create/",
                {"username": "alice", "role": "user", "password": "password123", "password2": "password123"},
            )
        assert response.status_code == 302
        mock_create.assert_called_once_with(username="alice", role="user", password="password123")


class TestUserEditView:
    @patch("apps.settings_app.views.get_user")
    def test_get_renders_form(self, mock_get: MagicMock, client: Client) -> None:
        mock_get.return_value = {
            "id": OTHER_USER_ID, "username": "alice", "role": "user",
            "is_admin": False, "password_is_default": False,
        }
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.get(f"/settings/users/{OTHER_USER_ID}/edit/")
        assert response.status_code == 200
        assert "alice" in response.content.decode()

    @patch("apps.settings_app.views.update_user_account")
    @patch("apps.settings_app.views.get_user")
    def test_post_updates_and_redirects(
        self, mock_get: MagicMock, mock_update: MagicMock, client: Client,
    ) -> None:
        mock_get.return_value = {
            "id": OTHER_USER_ID, "username": "alice", "role": "user",
            "is_admin": False, "password_is_default": False,
        }
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.post(
                f"/settings/users/{OTHER_USER_ID}/edit/",
                {"role": "admin"},
            )
        assert response.status_code == 302
        mock_update.assert_called_once()


class TestUserDeleteView:
    @patch("apps.settings_app.views.soft_delete_user")
    def test_post_deletes_and_redirects(self, mock_del: MagicMock, client: Client) -> None:
        mock_del.return_value = "alice"
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.post(f"/settings/users/{OTHER_USER_ID}/delete/")
        assert response.status_code == 302
        mock_del.assert_called_once()

    @patch("apps.settings_app.views.soft_delete_user")
    def test_get_redirects_no_mutation(self, mock_del: MagicMock, client: Client) -> None:
        user = _login_as_admin(client)
        with _patch_middleware_user(user):
            response = client.get(f"/settings/users/{OTHER_USER_ID}/delete/")
        assert response.status_code == 302
        mock_del.assert_not_called()


class TestAccountView:
    def test_get_renders_for_non_admin(self, client: Client) -> None:
        user = _login_as_nonadmin(client)
        with _patch_middleware_user(user):
            response = client.get("/settings/account/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Change Password" in content or "password" in content.lower()

    def test_anonymous_redirected_to_login(self, client: Client) -> None:
        response = client.get("/settings/account/")
        assert response.status_code == 302
        assert "/login/" in response.url


# ============================================================================
# Form validation tests (no DB)
# ============================================================================


class TestUserCreateForm:
    def test_valid_data(self) -> None:
        form = UserCreateForm(data={
            "username": "alice",
            "role": "user",
            "password": "password123",
            "password2": "password123",
        })
        assert form.is_valid()

    def test_blank_username_invalid(self) -> None:
        form = UserCreateForm(data={
            "username": "",
            "role": "user",
            "password": "password123",
            "password2": "password123",
        })
        assert not form.is_valid()

    def test_short_password_invalid(self) -> None:
        form = UserCreateForm(data={
            "username": "alice",
            "role": "user",
            "password": "short",
            "password2": "short",
        })
        assert not form.is_valid()

    def test_password_mismatch(self) -> None:
        form = UserCreateForm(data={
            "username": "alice",
            "role": "user",
            "password": "password123",
            "password2": "different1",
        })
        assert not form.is_valid()

    def test_password_min_length_is_8(self) -> None:
        assert MIN_PASSWORD_LENGTH == 8


class TestUserEditForm:
    def test_role_only_valid(self) -> None:
        form = UserEditForm(data={"role": "admin"})
        assert form.is_valid()

    def test_optional_password_valid(self) -> None:
        form = UserEditForm(data={
            "role": "user",
            "new_password": "newpassword1",
            "new_password2": "newpassword1",
        })
        assert form.is_valid()

    def test_password_mismatch(self) -> None:
        form = UserEditForm(data={
            "role": "user",
            "new_password": "newpassword1",
            "new_password2": "different1",
        })
        assert not form.is_valid()

    def test_short_new_password(self) -> None:
        form = UserEditForm(data={
            "role": "user",
            "new_password": "short",
            "new_password2": "short",
        })
        assert not form.is_valid()


class TestChangePasswordForm:
    def test_valid_data(self) -> None:
        form = ChangePasswordForm(data={
            "current_password": "oldpassword1",
            "new_password": "newpassword1",
            "new_password2": "newpassword1",
        })
        assert form.is_valid()

    def test_mismatch_invalid(self) -> None:
        form = ChangePasswordForm(data={
            "current_password": "oldpassword1",
            "new_password": "newpassword1",
            "new_password2": "different1",
        })
        assert not form.is_valid()

    def test_short_new_password_invalid(self) -> None:
        form = ChangePasswordForm(data={
            "current_password": "oldpassword1",
            "new_password": "short",
            "new_password2": "short",
        })
        assert not form.is_valid()


# ============================================================================
# URL resolution tests
# ============================================================================


class TestUserURLResolution:
    def test_user_list_url(self) -> None:
        from django.urls import reverse
        assert reverse("user_list") == "/settings/users/"

    def test_user_create_url(self) -> None:
        from django.urls import reverse
        assert reverse("user_create") == "/settings/users/create/"

    def test_user_edit_url(self) -> None:
        from django.urls import reverse
        url = reverse("user_edit", kwargs={"user_id": OTHER_USER_ID})
        assert url == f"/settings/users/{OTHER_USER_ID}/edit/"

    def test_user_delete_url(self) -> None:
        from django.urls import reverse
        url = reverse("user_delete", kwargs={"user_id": OTHER_USER_ID})
        assert url == f"/settings/users/{OTHER_USER_ID}/delete/"

    def test_account_url(self) -> None:
        from django.urls import reverse
        assert reverse("account") == "/settings/account/"
