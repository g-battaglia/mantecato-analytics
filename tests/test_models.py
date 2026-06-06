"""Tests for models and report proxy models.

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
    EventData,
    MantecatoUser,
    Report,
    Revenue,
    ScheduledExport,
    Segment,
    Session,
    SessionData,
    Team,
    TeamUser,
    Website,
    WebsiteEvent,
)

# ---------------------------------------------------------------------------
# Concrete model registry
# ---------------------------------------------------------------------------

CONCRETE_MODELS = [
    Team,
    MantecatoUser,
    Website,
    Session,
    WebsiteEvent,
    EventData,
    SessionData,
    TeamUser,
    Revenue,
    Segment,
    Report,
]

PROXY_MODELS = [
    Dashboard,
    ApiKey,
    BotConfig,
    ScheduledExport,
]

ALL_MODELS = CONCRETE_MODELS + PROXY_MODELS


# ---------------------------------------------------------------------------
# Concrete models: managed = True (default)
# ---------------------------------------------------------------------------


class TestManaged:
    """Every concrete model must have ``managed = True`` (the default)."""

    @pytest.mark.parametrize("model_cls", CONCRETE_MODELS, ids=lambda m: m.__name__)
    def test_concrete_managed_true(self, model_cls: type) -> None:
        assert model_cls._meta.managed is True

    @pytest.mark.parametrize("model_cls", CONCRETE_MODELS, ids=lambda m: m.__name__)
    def test_no_auto_field(self, model_cls: type) -> None:
        """Concrete models use UUID PKs, not Django's default BigAutoField."""
        assert not isinstance(model_cls._meta.pk, models.BigAutoField)


# ---------------------------------------------------------------------------
# Concrete models: db_table
# ---------------------------------------------------------------------------

EXPECTED_DB_TABLES: dict[type, str] = {
    Team: "team",
    MantecatoUser: "mantecato_user",
    Website: "website",
    Session: "session",
    WebsiteEvent: "website_event",
    EventData: "event_data",
    SessionData: "session_data",
    TeamUser: "team_user",
    Revenue: "revenue",
    Segment: "segment",
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
        """Proxy models inherit ``managed`` from their concrete parent.

        The concrete base model (Report) has ``managed = True``, which means
        Django manages migrations for it.
        """
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
    """Verify the queryset filter without hitting the database."""

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

    def test_session_pk_is_uuid(self) -> None:
        assert isinstance(Session._meta.get_field("session_id"), models.UUIDField)

    def test_event_pk_is_uuid(self) -> None:
        assert isinstance(WebsiteEvent._meta.get_field("event_id"), models.UUIDField)

    def test_event_data_pk_is_uuid(self) -> None:
        assert isinstance(EventData._meta.get_field("event_data_id"), models.UUIDField)

    def test_report_pk_is_uuid(self) -> None:
        assert isinstance(Report._meta.get_field("id"), models.UUIDField)

    def test_report_has_json_parameters(self) -> None:
        assert isinstance(Report._meta.get_field("parameters"), models.JSONField)

    def test_segment_has_json_name_filters(self) -> None:
        assert isinstance(Segment._meta.get_field("name_filters"), models.JSONField)

    def test_revenue_has_decimal_field(self) -> None:
        assert isinstance(Revenue._meta.get_field("revenue"), models.DecimalField)

    def test_website_is_deleted_is_boolean(self) -> None:
        assert isinstance(Website._meta.get_field("is_deleted"), models.BooleanField)

    def test_website_event_event_type_is_int(self) -> None:
        assert isinstance(WebsiteEvent._meta.get_field("event_type"), models.IntegerField)

    def test_event_data_data_type_is_int(self) -> None:
        assert isinstance(EventData._meta.get_field("data_type"), models.IntegerField)

    def test_session_data_data_type_is_int(self) -> None:
        assert isinstance(SessionData._meta.get_field("data_type"), models.IntegerField)

    # ------------------------------------------------------------------
    # T3 review fixes: nullable Website.user_id
    # ------------------------------------------------------------------

    def test_website_user_id_is_nullable(self) -> None:
        field = Website._meta.get_field("user_id")
        assert field.null is True

    # ------------------------------------------------------------------
    # T3 review fixes: DecimalField decimal_places > 0
    # ------------------------------------------------------------------

    def test_event_data_number_value_has_decimal_places(self) -> None:
        field = EventData._meta.get_field("number_value")
        assert isinstance(field, models.DecimalField)
        assert field.decimal_places > 0

    def test_session_data_number_value_has_decimal_places(self) -> None:
        field = SessionData._meta.get_field("number_value")
        assert isinstance(field, models.DecimalField)
        assert field.decimal_places > 0

    def test_revenue_field_has_decimal_places(self) -> None:
        field = Revenue._meta.get_field("revenue")
        assert isinstance(field, models.DecimalField)
        assert field.decimal_places > 0


# ---------------------------------------------------------------------------
# Proxy model to_dict() serialization (camelCase API/template contract)
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 15, 12, 30, 0, tzinfo=UTC)
_TS_ISO = _TS.isoformat()
_ID = "11111111-1111-1111-1111-111111111111"
_USER = "22222222-2222-2222-2222-222222222222"
_SITE = "33333333-3333-3333-3333-333333333333"


def _stamp(obj: Report) -> Report:
    """Set the auto timestamps on an unsaved instance for serialization tests."""
    obj.created_at = _TS
    obj.updated_at = _TS
    return obj


class TestProxyToDict:
    """``to_dict()`` must match the camelCase shape the JSON API returns."""

    @pytest.mark.parametrize(
        "model_cls", [Dashboard, ScheduledExport], ids=lambda m: m.__name__
    )
    def test_report_shaped_to_dict(self, model_cls: type) -> None:
        obj = _stamp(
            model_cls(
                id=_ID,
                user_id=_USER,
                website_id=_SITE,
                name="Item",
                description="desc",
                parameters={"k": "v"},
            )
        )
        assert obj.to_dict() == {
            "id": _ID,
            "name": "Item",
            "description": "desc",
            "userId": _USER,
            "websiteId": _SITE,
            "config": {"k": "v"},
            "createdAt": _TS_ISO,
            "updatedAt": _TS_ISO,
        }

    def test_report_to_dict_normalizes_blank_fields(self) -> None:
        obj = _stamp(
            Dashboard(
                id=_ID,
                user_id=_USER,
                website_id=_SITE,
                name="X",
                description=None,
                parameters={},
            )
        )
        result = obj.to_dict()
        assert result["description"] == ""
        assert result["config"] == {}

    def test_api_key_to_dict(self) -> None:
        obj = ApiKey(
            id=_ID,
            user_id=_USER,
            name="CI key",
            parameters={
                "prefix": "mtk_abc1234...",
                "scopes": ["read", "write"],
                "createdAt": _TS_ISO,
                "lastUsedAt": None,
            },
        )
        assert obj.to_dict() == {
            "id": _ID,
            "name": "CI key",
            "prefix": "mtk_abc1234...",
            "scopes": ["read", "write"],
            "createdAt": _TS_ISO,
            "lastUsedAt": None,
        }

    def test_api_key_to_dict_defaults(self) -> None:
        obj = ApiKey(id=_ID, user_id=_USER, name="K", parameters={})
        result = obj.to_dict()
        assert result["prefix"] == "mtk_???"
        assert result["scopes"] == ["read"]
        assert result["lastUsedAt"] is None

    def test_bot_config_to_dict_merges_defaults(self) -> None:
        obj = _stamp(
            BotConfig(
                id=_ID,
                user_id=_USER,
                website_id=_SITE,
                name="Bot Detection Config",
                parameters={"enabled": True, "minDuration": 5},
            )
        )
        result = obj.to_dict()
        assert result["id"] == _ID
        assert result["websiteId"] == _SITE
        assert result["createdAt"] == _TS_ISO
        assert result["config"]["enabled"] is True
        assert result["config"]["minDuration"] == 5
        assert result["config"]["knownBots"] is True
        assert result["config"]["excludedCountries"] == []
