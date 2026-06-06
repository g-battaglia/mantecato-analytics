"""Tests for models and report proxy models — privacy-first aggregate mode.

All assertions are purely structural — no database access required.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.db import models

from apps.core.models import (
    REPORT_TYPE_API_KEY,
    REPORT_TYPE_BOT_CONFIG,
    REPORT_TYPE_DASHBOARD,
    REPORT_TYPE_SCHEDULED_EXPORT,
    ApiKey,
    BotConfig,
    Dashboard,
    MantecatoUser,
    Report,
    ScheduledExport,
    Team,
    TeamUser,
    Website,
    WebsiteEvent,
)

# ---------------------------------------------------------------------------
# Concrete models: db_table
# ---------------------------------------------------------------------------

EXPECTED_DB_TABLES: dict[type, str] = {
    Team: "team",
    MantecatoUser: "mantecato_user",
    Website: "website",
    WebsiteEvent: "website_event",
    TeamUser: "team_user",
    Report: "report",
}


class TestDbTable:
    @pytest.mark.parametrize(
        "model_cls",
        list(EXPECTED_DB_TABLES.keys()),
        ids=lambda m: m.__name__,
    )
    def test_db_table(self, model_cls: type) -> None:
        expected = EXPECTED_DB_TABLES[model_cls]
        assert model_cls._meta.db_table == expected

    def test_user_table_name(self) -> None:
        assert MantecatoUser._meta.db_table == "mantecato_user"

    def test_report_db_table(self) -> None:
        assert Report._meta.db_table == "report"


# ---------------------------------------------------------------------------
# MantecatoUser model
# ---------------------------------------------------------------------------


class TestMantecatoUser:
    def test_auth_user_model_setting(self) -> None:
        from django.conf import settings

        assert settings.AUTH_USER_MODEL == "core.MantecatoUser"

    def test_username_field(self) -> None:
        assert MantecatoUser.USERNAME_FIELD == "username"

    def test_pk_is_uuid(self) -> None:
        assert isinstance(MantecatoUser._meta.get_field("id"), models.UUIDField)

    def test_has_role_field(self) -> None:
        field = MantecatoUser._meta.get_field("role")
        assert isinstance(field, models.CharField)

    def test_has_deleted_at_field(self) -> None:
        field = MantecatoUser._meta.get_field("deleted_at")
        assert field.null is True

    def test_is_abstract_base_user(self) -> None:
        from django.contrib.auth.models import AbstractBaseUser

        assert issubclass(MantecatoUser, AbstractBaseUser)

    def test_str(self) -> None:
        user = MantecatoUser(username="testuser")
        assert str(user) == "testuser"


# ---------------------------------------------------------------------------
# Proxy models
# ---------------------------------------------------------------------------

PROXY_MODELS = (Dashboard, ApiKey, BotConfig, ScheduledExport)


class TestProxyModels:
    @pytest.mark.parametrize("model_cls", PROXY_MODELS, ids=lambda m: m.__name__)
    def test_is_proxy(self, model_cls: type) -> None:
        assert model_cls._meta.proxy is True

    @pytest.mark.parametrize("model_cls", PROXY_MODELS, ids=lambda m: m.__name__)
    def test_proxy_inherits_report(self, model_cls: type) -> None:
        assert issubclass(model_cls, Report)

    @pytest.mark.parametrize("model_cls", PROXY_MODELS, ids=lambda m: m.__name__)
    def test_proxy_db_table_is_report(self, model_cls: type) -> None:
        assert model_cls._meta.db_table == "report"

    @pytest.mark.parametrize("model_cls", PROXY_MODELS, ids=lambda m: m.__name__)
    def test_proxy_parent_is_managed(self, model_cls: type) -> None:
        parent = model_cls._meta.get_field("id").model
        while parent._meta.proxy:
            parent = parent.__bases__[0]
        assert parent._meta.managed is True


# ---------------------------------------------------------------------------
# Proxy managers: type filtering
# ---------------------------------------------------------------------------

PROXY_TYPE_MAP: dict[type, str] = {
    Dashboard: REPORT_TYPE_DASHBOARD,
    ApiKey: REPORT_TYPE_API_KEY,
    BotConfig: REPORT_TYPE_BOT_CONFIG,
    ScheduledExport: REPORT_TYPE_SCHEDULED_EXPORT,
}


class TestProxyManagerFilter:
    @pytest.mark.parametrize(
        "model_cls",
        list(PROXY_TYPE_MAP.keys()),
        ids=lambda m: m.__name__,
    )
    def test_manager_has_correct_report_type(self, model_cls: type) -> None:
        expected_type = PROXY_TYPE_MAP[model_cls]
        manager = model_cls.objects
        assert manager._report_type == expected_type

    def test_dashboard_type(self) -> None:
        assert Dashboard.objects._report_type == "mantecato-dashboard"

    def test_api_key_type(self) -> None:
        assert ApiKey.objects._report_type == "api-key"

    def test_bot_config_type(self) -> None:
        assert BotConfig.objects._report_type == "mantecato-bot-config"

    def test_scheduled_export_type(self) -> None:
        assert ScheduledExport.objects._report_type == "mantecato-scheduled-export"

    @pytest.mark.parametrize(
        "model_cls",
        list(PROXY_TYPE_MAP.keys()),
        ids=lambda m: m.__name__,
    )
    def test_queryset_filter_clause(self, model_cls: type) -> None:
        qs = model_cls.objects.get_queryset()
        query_str = str(qs.query)
        assert '"report"."type"' in query_str


# ---------------------------------------------------------------------------
# Field type sanity checks
# ---------------------------------------------------------------------------


class TestFieldTypes:
    def test_website_pk_is_uuid(self) -> None:
        assert isinstance(Website._meta.get_field("id"), models.UUIDField)

    def test_user_pk_is_uuid(self) -> None:
        assert isinstance(MantecatoUser._meta.get_field("id"), models.UUIDField)

    def test_event_pk_is_uuid(self) -> None:
        assert isinstance(WebsiteEvent._meta.get_field("event_id"), models.UUIDField)

    def test_report_pk_is_uuid(self) -> None:
        assert isinstance(Report._meta.get_field("id"), models.UUIDField)

    def test_report_has_json_parameters(self) -> None:
        assert isinstance(Report._meta.get_field("parameters"), models.JSONField)

    def test_website_is_deleted_is_boolean(self) -> None:
        assert isinstance(Website._meta.get_field("is_deleted"), models.BooleanField)

    def test_website_event_event_type_is_int(self) -> None:
        assert isinstance(WebsiteEvent._meta.get_field("event_type"), models.IntegerField)

    def test_website_user_id_is_nullable(self) -> None:
        field = Website._meta.get_field("user_id")
        assert field.null is True


# ---------------------------------------------------------------------------
# Proxy model to_dict() serialization
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)
_TS_ISO = _TS.isoformat()
_ID = "11111111-1111-1111-1111-111111111111"
_USER = "22222222-2222-2222-2222-222222222222"
_SITE = "33333333-3333-3333-3333-333333333333"


def _stamp(obj: Report) -> Report:
    obj.created_at = _TS
    obj.updated_at = _TS
    return obj


class TestProxyToDict:
    @pytest.mark.parametrize(
        "model_cls", [Dashboard, ScheduledExport], ids=lambda m: m.__name__
    )
    def test_report_shaped_to_dict(self, model_cls: type) -> None:
        instance = _stamp(
            model_cls(
                id=_ID,
                name="Test",
                user_id=_USER,
                website_id=_SITE,
                parameters={},
            )
        )
        d = instance.to_dict()
        assert d["id"] == _ID
        assert d["name"] == "Test"
        assert d["userId"] == _USER
        assert d["websiteId"] == _SITE
        assert "createdAt" in d
        assert "updatedAt" in d

    def test_api_key_to_dict(self) -> None:
        instance = ApiKey(
            id=_ID,
            name="Key",
            parameters={"prefix": "mtk_abc", "scopes": ["read"]},
        )
        d = instance.to_dict()
        assert d["id"] == _ID
        assert d["name"] == "Key"
        assert d["prefix"] == "mtk_abc"
        assert d["scopes"] == ["read"]

    def test_bot_config_to_dict_merges_defaults(self) -> None:
        from apps.core.models import BOT_CONFIG_DEFAULTS

        instance = BotConfig(
            id=_ID,
            website_id=_SITE,
            parameters={"enabled": True},
        )
        d = instance.to_dict()
        config = d["config"]
        assert config["enabled"] is True
        for key in BOT_CONFIG_DEFAULTS:
            assert key in config

    def test_dashboard_config_key(self) -> None:
        instance = Dashboard(
            id=_ID,
            name="D",
            user_id=_USER,
            parameters={"version": 1, "columns": 2},
        )
        d = instance.to_dict()
        assert d["config"]["version"] == 1
        assert d["config"]["columns"] == 2
