"""Tests for the ORM-backed report-table CRUD services.

Exercises the dashboard, API key, bot config, and
scheduled export services against a real (test) database via the Django ORM.
"""

from __future__ import annotations

import pytest

from apps.core.api_keys import generate_key, hash_key, validate_api_key
from apps.core.models import ScheduledExport
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
    get_scheduled_export_detail,
    get_scheduled_exports_for_user,
    remove_api_key,
    remove_scheduled_export,
    save_bot_config,
)

pytestmark = pytest.mark.django_db

USER_A = "a1111111-1111-1111-1111-111111111111"
USER_B = "b2222222-2222-2222-2222-222222222222"
SITE = "c3333333-3333-3333-3333-333333333333"
SITE_2 = "d4444444-4444-4444-4444-444444444444"
MISSING = "00000000-0000-0000-0000-000000000099"


class TestDashboardCrud:
    def test_create_returns_serialized_dashboard(self) -> None:
        result = create_new_dashboard(USER_A, SITE, "My Dashboard", description="d")
        assert result["name"] == "My Dashboard"
        assert result["description"] == "d"
        assert result["userId"] == USER_A
        assert result["websiteId"] == SITE
        assert result["config"] == {
            "version": 2,
            "layout": {"columns": 12},
            "dateRange": "30d",
            "filters": [],
            "widgets": [],
        }
        assert result["id"]
        assert result["createdAt"]

    def test_create_with_explicit_config(self) -> None:
        result = create_new_dashboard(USER_A, SITE, "X", config={"widgets": ["a"]})
        assert result["config"] == {"widgets": ["a"]}

    def test_list_returns_user_dashboards_only(self) -> None:
        create_new_dashboard(USER_A, SITE, "A")
        create_new_dashboard(USER_A, SITE, "B")
        create_new_dashboard(USER_B, SITE, "C")
        assert {d["name"] for d in get_dashboards_for_user(USER_A)} == {"A", "B"}

    def test_list_scoped_to_website(self) -> None:
        create_new_dashboard(USER_A, SITE, "OnSite")
        create_new_dashboard(USER_A, SITE_2, "OffSite")
        items = get_dashboards_for_user(USER_A, website_id=SITE)
        assert [d["name"] for d in items] == ["OnSite"]

    def test_get_detail(self) -> None:
        created = create_new_dashboard(USER_A, SITE, "D")
        fetched = get_dashboard_detail(created["id"], USER_A)
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_detail_wrong_user(self) -> None:
        created = create_new_dashboard(USER_A, SITE, "D")
        assert get_dashboard_detail(created["id"], USER_B) is None

    def test_update(self) -> None:
        created = create_new_dashboard(USER_A, SITE, "Old")
        updated = update_existing_dashboard(
            created["id"], USER_A, name="New", config={"widgets": ["w"]}
        )
        assert updated is not None
        assert updated["name"] == "New"
        assert updated["config"] == {"widgets": ["w"]}

    def test_update_missing_returns_none(self) -> None:
        assert update_existing_dashboard(MISSING, USER_A, name="X") is None

    def test_delete(self) -> None:
        created = create_new_dashboard(USER_A, SITE, "D")
        assert remove_dashboard(created["id"], USER_A) is True
        assert get_dashboard_detail(created["id"], USER_A) is None

    def test_delete_missing_returns_false(self) -> None:
        assert remove_dashboard(MISSING, USER_A) is False


class TestApiKeyCrud:
    def test_create_returns_raw_key_once(self) -> None:
        result = generate_new_api_key(USER_A, "My Key")
        assert result["key"].startswith("mtk_")
        assert result["prefix"].endswith("...")
        assert result["scopes"] == ["read", "write"]

    def test_list_omits_raw_key(self) -> None:
        generate_new_api_key(USER_A, "K")
        keys = get_api_keys_for_user(USER_A)
        assert len(keys) == 1
        assert "key" not in keys[0]
        assert keys[0]["name"] == "K"

    def test_delete(self) -> None:
        created = generate_new_api_key(USER_A, "K")
        assert remove_api_key(created["id"], USER_A) is True
        assert get_api_keys_for_user(USER_A) == []

    def test_delete_wrong_user(self) -> None:
        created = generate_new_api_key(USER_A, "K")
        assert remove_api_key(created["id"], USER_B) is False


class TestApiKeyAuth:
    def test_hash_key_deterministic(self) -> None:
        assert hash_key("mtk_abc") == hash_key("mtk_abc")
        assert hash_key("mtk_abc") != hash_key("mtk_xyz")

    def test_generate_key_format(self) -> None:
        key = generate_key()
        assert key.startswith("mtk_")
        assert len(key) > 20

    def test_validate_rejects_non_mtk(self) -> None:
        assert validate_api_key("not-a-key") is None

    def test_validate_unknown_key(self) -> None:
        assert validate_api_key("mtk_nonexistent") is None

    def test_validate_resolves_created_key(self) -> None:
        created = generate_new_api_key(USER_A, "CI", scopes=["read", "write"])
        result = validate_api_key(created["key"])
        assert result is not None
        assert result["userId"] == USER_A
        assert result["scopes"] == ["read", "write"]

    def test_validate_refreshes_last_used(self) -> None:
        created = generate_new_api_key(USER_A, "CI")
        assert get_api_keys_for_user(USER_A)[0]["lastUsedAt"] is None
        validate_api_key(created["key"])
        assert get_api_keys_for_user(USER_A)[0]["lastUsedAt"] is not None


class TestBotConfigCrud:
    def test_get_returns_defaults_when_unset(self) -> None:
        config = get_bot_config(SITE)
        assert config["id"] is None
        assert config["config"]["enabled"] is False
        assert config["config"]["knownBots"] is True

    def test_save_then_get(self) -> None:
        save_bot_config(USER_A, SITE, {"enabled": True, "excludedCountries": ["SG"]})
        config = get_bot_config(SITE)
        assert config["id"] is not None
        assert config["config"]["enabled"] is True
        assert config["config"]["excludedCountries"] == ["SG"]

    def test_save_is_upsert(self) -> None:
        first = save_bot_config(USER_A, SITE, {"enabled": True})
        second = save_bot_config(USER_A, SITE, {"enabled": False})
        assert first["id"] == second["id"]
        assert get_bot_config(SITE)["config"]["enabled"] is False


class TestScheduledExportCrud:
    def _make(self, user_id: str = USER_A) -> str:
        export = ScheduledExport.objects.create(
            user_id=user_id,
            website_id=SITE,
            name="Weekly",
            description="",
            parameters={"schedule": "weekly", "format": "csv"},
        )
        return str(export.id)

    def test_list_and_get(self) -> None:
        report_id = self._make()
        assert [e["name"] for e in get_scheduled_exports_for_user(USER_A)] == ["Weekly"]
        detail = get_scheduled_export_detail(report_id, USER_A)
        assert detail is not None
        assert detail["config"] == {"schedule": "weekly", "format": "csv"}

    def test_delete(self) -> None:
        report_id = self._make()
        assert remove_scheduled_export(report_id, USER_A) is True
        assert get_scheduled_export_detail(report_id, USER_A) is None
