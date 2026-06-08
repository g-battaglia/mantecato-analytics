"""Unit tests for :mod:`apps.common.mixins`.

Each mixin is exercised in isolation via :class:`~django.test.RequestFactory`
and a minimal ad-hoc CBV that combines the mixin under test with a
``TemplateView`` or a plain ``View``. The full URL conf is not touched.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django.http import JsonResponse
from django.test import RequestFactory
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import (
    ApiAuthMixin,
    ApiWriteMixin,
    BaseContextMixin,
    DateRangeMixin,
    FiltersMixin,
    WebsiteContextMixin,
    _bot_filter_default_enabled,
    _parse_offset,
    load_bot_filter_payload,
)
from tests.conftest import ADMIN_USER_ID, WEBSITE_ID, make_admin_user

if TYPE_CHECKING:
    from django.http import HttpRequest

_WEBSITES = [{"id": WEBSITE_ID, "name": "Test site"}]


class _WebStack(WebsiteContextMixin, DateRangeMixin, FiltersMixin, BaseContextMixin, TemplateView):
    """Test scaffold composing the web-side mixins."""

    template_name = "doesnt-matter.html"


@pytest.fixture
def request_factory() -> RequestFactory:
    return RequestFactory()


def _web_request(rf: RequestFactory, **params: str) -> HttpRequest:
    request = rf.get("/x/", data=params)
    request.user = make_admin_user()
    return request


def _patched_setup(
    view_cls: type, request: HttpRequest, websites: list[dict] | None = None
) -> object:
    """Instantiate ``view_cls``, run ``setup`` with patched ``resolve_websites_for_user``."""
    with patch(
        "apps.analytics.services.resolve_websites_for_user",
        return_value=websites if websites is not None else _WEBSITES,
    ):
        view = view_cls()
        view.setup(request)
        return view


# ---------------------------------------------------------------------------
# WebsiteContextMixin
# ---------------------------------------------------------------------------


class TestWebsiteContextMixin:
    def test_resolves_explicit_website(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory, website=WEBSITE_ID))
        assert view.website_id == WEBSITE_ID
        assert view.websites == _WEBSITES
        assert view.selected_website_name == "Test site"
        assert view.website_forbidden is False

    def test_falls_back_to_first_website(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory))
        assert view.website_id == WEBSITE_ID
        assert view.website_forbidden is False

    def test_marks_forbidden_when_invalid_website_id(self, request_factory: RequestFactory) -> None:
        request = _web_request(request_factory, website="00000000-0000-0000-0000-deadbeef0000")
        view = _patched_setup(_WebStack, request)
        assert view.website_id is None
        assert view.website_forbidden is True

    def test_no_websites_yields_none(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory), websites=[])
        assert view.website_id is None
        assert view.websites == []
        assert view.selected_website_name == ""


# ---------------------------------------------------------------------------
# DateRangeMixin
# ---------------------------------------------------------------------------


class TestDateRangeMixin:
    def test_default_preset_is_24h_for_web(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory))
        assert view.range_preset == "24h"
        assert view.date_range is not None

    def test_explicit_valid_preset(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory, range="7d"))
        assert view.range_preset == "7d"

    def test_invalid_preset_falls_back_to_default(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory, range="not-a-real-preset"))
        assert view.range_preset == "24h"

    def test_explicit_start_and_end_yields_custom(self, request_factory: RequestFactory) -> None:
        request = _web_request(
            request_factory,
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-02T00:00:00+00:00",
        )
        view = _patched_setup(_WebStack, request)
        assert view.range_preset == "custom"
        assert view.date_range is not None
        assert view.date_range.start_date.year == 2024

    def test_malformed_start_yields_none_range(self, request_factory: RequestFactory) -> None:
        request = _web_request(request_factory, start="not-a-date", end="2024-01-02T00:00:00+00:00")
        view = _patched_setup(_WebStack, request)
        assert view.date_range is None
        assert view.range_preset == "custom"

    def test_default_offset_is_zero(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory, range="24h"))
        assert view.range_offset == 0

    def test_offset_shifts_window_back_by_its_duration(
        self, request_factory: RequestFactory
    ) -> None:
        """``?offset=N`` lands on the Nth immediately-preceding window of equal length."""
        # Pin "now" so the offset=0 and offset=2 windows are directly comparable
        # (resolve_date_range calls _now() on each setup).
        fixed = datetime(2025, 5, 20, 12, 0, tzinfo=UTC)
        with patch("core.mantecato_core.date_utils._now", return_value=fixed):
            base = _patched_setup(_WebStack, _web_request(request_factory, range="24h"))
            shifted = _patched_setup(
                _WebStack, _web_request(request_factory, range="24h", offset="2")
            )
        assert base.range_offset == 0
        assert shifted.range_offset == 2
        duration = base.date_range.end_date - base.date_range.start_date
        # Equal length, shifted back by exactly two whole periods (no gap).
        assert shifted.date_range.end_date == base.date_range.end_date - 2 * duration
        assert shifted.date_range.start_date == base.date_range.start_date - 2 * duration

    def test_invalid_or_negative_offset_is_ignored(self, request_factory: RequestFactory) -> None:
        fixed = datetime(2025, 5, 20, 12, 0, tzinfo=UTC)
        with patch("core.mantecato_core.date_utils._now", return_value=fixed):
            base = _patched_setup(_WebStack, _web_request(request_factory, range="24h"))
            neg = _patched_setup(_WebStack, _web_request(request_factory, range="24h", offset="-5"))
            bad = _patched_setup(
                _WebStack, _web_request(request_factory, range="24h", offset="abc")
            )
        assert neg.range_offset == 0
        assert bad.range_offset == 0
        assert neg.date_range.start_date == base.date_range.start_date
        assert bad.date_range.start_date == base.date_range.start_date

    def test_offset_ignored_for_custom_range(self, request_factory: RequestFactory) -> None:
        """Explicit start/end windows are pinned, so offset does not page them."""
        request = _web_request(
            request_factory,
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-02T00:00:00+00:00",
            offset="3",
        )
        view = _patched_setup(_WebStack, request)
        assert view.range_offset == 0
        assert view.date_range.start_date.year == 2024


class TestParseOffset:
    def test_parses_and_clamps(self) -> None:
        from apps.common.mixins import _MAX_RANGE_OFFSET

        assert _parse_offset(None) == 0
        assert _parse_offset("") == 0
        assert _parse_offset("abc") == 0
        assert _parse_offset("-3") == 0
        assert _parse_offset("0") == 0
        assert _parse_offset("7") == 7
        assert _parse_offset(str(_MAX_RANGE_OFFSET + 100)) == _MAX_RANGE_OFFSET


# ---------------------------------------------------------------------------
# FiltersMixin
# ---------------------------------------------------------------------------


class TestFiltersMixin:
    def test_no_filters_default(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory))
        assert view.filters == []
        assert view.bot_filter is False

    def test_bot_filter_applies_cheap_defaults_when_no_config(
        self, request_factory: RequestFactory
    ) -> None:
        """Without a saved BotConfig the toggle still filters known bots."""
        # The default fallback enables ``knownBots`` + ``emptyUa`` (both
        # cheap, no NOT EXISTS subquery) so the toggle is never a no-op.
        payload = json.dumps({"enabled": True, "knownBots": True, "emptyUa": True})
        with patch("apps.common.mixins.load_bot_filter_payload", return_value=payload):
            view = _patched_setup(_WebStack, _web_request(request_factory, bot_filter="1"))
            filters = view.filters
        assert view.bot_filter is True
        assert any(f.column == "__bot_filter__" for f in filters)

    def test_bot_filter_skipped_when_payload_none(self, request_factory: RequestFactory) -> None:
        """A ``None`` payload (lookup unavailable) injects no synthetic filter."""
        # ``load_bot_filter_payload`` only returns None now when the BotConfig
        # lookup itself fails; the toggle is on but no filter is injected so
        # analytics rendering never breaks on a missing config table.
        with patch("apps.common.mixins.load_bot_filter_payload", return_value=None):
            view = _patched_setup(_WebStack, _web_request(request_factory, bot_filter="1"))
            filters = view.filters
        assert not any(f.column == "__bot_filter__" for f in filters)

    def test_bot_filter_defaults_to_saved_enabled_when_param_absent(
        self, request_factory: RequestFactory
    ) -> None:
        """No ``?bot_filter`` param falls back to the site's "filter by default" flag."""
        with patch("apps.common.mixins._bot_filter_default_enabled", return_value=True):
            view = _patched_setup(_WebStack, _web_request(request_factory))
            assert view.bot_filter is True
        with patch("apps.common.mixins._bot_filter_default_enabled", return_value=False):
            view = _patched_setup(_WebStack, _web_request(request_factory))
            assert view.bot_filter is False

    def test_explicit_bot_filter_param_overrides_default(
        self, request_factory: RequestFactory
    ) -> None:
        """An explicit ``?bot_filter=0`` wins even when the site defaults to on."""
        with patch("apps.common.mixins._bot_filter_default_enabled", return_value=True):
            view = _patched_setup(_WebStack, _web_request(request_factory, bot_filter="0"))
            assert view.bot_filter is False

    def test_bot_filter_injects_serialised_config(self, request_factory: RequestFactory) -> None:
        """An enabled config is JSON-serialised into the synthetic filter value."""
        payload = json.dumps({"enabled": True, "knownBots": True})
        with patch("apps.common.mixins.load_bot_filter_payload", return_value=payload):
            view = _patched_setup(_WebStack, _web_request(request_factory, bot_filter="1"))
            filters = view.filters
        bot_filter = next(f for f in filters if f.column == "__bot_filter__")
        assert json.loads(bot_filter.value) == {"enabled": True, "knownBots": True}

    def test_bot_filter_passes_only_website_id(
        self, request_factory: RequestFactory
    ) -> None:
        """The payload lookup is keyed on the website id alone (no precompute scan).

        Privacy-first mode has no session/visitor identifiers, so bot exclusion
        is a pure event-level clause — there is nothing to precompute per range.
        """
        mock = MagicMock(return_value=json.dumps({"enabled": True, "knownBots": True}))
        with patch("apps.common.mixins.load_bot_filter_payload", mock):
            view = _patched_setup(
                _WebStack, _web_request(request_factory, range="24h", bot_filter="1")
            )
            _ = view.filters
        assert mock.call_count == 1
        assert mock.call_args.args == (WEBSITE_ID,)


# ---------------------------------------------------------------------------
# load_bot_filter_payload / _bot_filter_default_enabled
# ---------------------------------------------------------------------------


class TestLoadBotFilterPayload:
    def test_forces_enabled_when_saved_config_disabled(self) -> None:
        """The toggle applies the saved rules even if the stored config has enabled=False.

        Mirrors Mantecato v2, whose dashboard toggle auto-enables the config on
        click -- a saved ``enabled=False`` must never silently neutralise an
        explicit ?bot_filter=1.
        """
        row = MagicMock()
        row.parameters = {"enabled": False, "knownBots": True, "excludedCountries": ["SG"]}
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.return_value.first.return_value = row
            payload = load_bot_filter_payload(WEBSITE_ID)
        config = json.loads(payload)["config"]
        assert config["enabled"] is True
        assert config["knownBots"] is True
        assert config["excludedCountries"] == ["SG"]

    def test_falls_back_to_defaults_when_no_row(self) -> None:
        """No saved config -> the v2 baseline defaults with enabled forced on."""
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.return_value.first.return_value = None
            payload = load_bot_filter_payload(WEBSITE_ID)
        config = json.loads(payload)["config"]
        assert config["enabled"] is True
        assert config["knownBots"] is True

    def test_returns_none_on_lookup_error(self) -> None:
        """A failing BotConfig lookup degrades to None (no filter), never an exception."""
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.side_effect = RuntimeError("db down")
            assert load_bot_filter_payload(WEBSITE_ID) is None


class TestBotFilterDefaultEnabled:
    def test_reads_saved_enabled_flag(self) -> None:
        row = MagicMock()
        row.parameters = {"enabled": True}
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.return_value.first.return_value = row
            assert _bot_filter_default_enabled(WEBSITE_ID) is True

    def test_false_when_no_row(self) -> None:
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.return_value.first.return_value = None
            assert _bot_filter_default_enabled(WEBSITE_ID) is False

    def test_false_on_lookup_error(self) -> None:
        with patch("apps.core.models.BotConfig") as bot_config:
            bot_config.objects.filter.side_effect = RuntimeError("db down")
            assert _bot_filter_default_enabled(WEBSITE_ID) is False


# ---------------------------------------------------------------------------
# BaseContextMixin
# ---------------------------------------------------------------------------


class TestBaseContextMixin:
    def test_injects_default_context_keys(self, request_factory: RequestFactory) -> None:
        view = _patched_setup(_WebStack, _web_request(request_factory))
        ctx = view.get_context_data()
        assert ctx["websites"] == _WEBSITES
        assert ctx["selected_website"] == WEBSITE_ID
        assert ctx["selected_website_name"] == "Test site"
        assert ctx["range_preset"] == "24h"
        assert ctx["bot_filter"] is False
        assert ctx["range_offset"] == 0
        assert ctx["current_range"] is view.date_range


# ---------------------------------------------------------------------------
# ApiAuthMixin
# ---------------------------------------------------------------------------


class _ApiEcho(ApiAuthMixin, View):
    """Echoes the API identity if authentication passes."""

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        return JsonResponse(
            {"user_id": self.get_acting_user_id(), "is_admin": self.is_acting_user_admin()}
        )


class TestApiAuthMixin:
    def test_anonymous_request_returns_401(self, request_factory: RequestFactory) -> None:
        request = request_factory.get("/api/test/")
        request.is_api_authenticated = False
        request.api_user_id = None
        request.api_key_scopes = []
        response = _ApiEcho.as_view()(request)
        assert response.status_code == 401

    def test_authenticated_request_passes_through(self, request_factory: RequestFactory) -> None:
        request = request_factory.get("/api/test/")
        request.is_api_authenticated = True
        request.api_user_id = ADMIN_USER_ID
        request.api_key_scopes = ["read", "admin"]
        response = _ApiEcho.as_view()(request)
        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["user_id"] == ADMIN_USER_ID
        assert body["is_admin"] is True

    def test_default_range_preset_is_api_default(self) -> None:
        # The mixin attribute should reflect the API default ("30d"), not "24h".
        assert _ApiEcho.default_range_preset == "30d"


# ---------------------------------------------------------------------------
# ApiWriteMixin
# ---------------------------------------------------------------------------


class _ApiWriteEcho(ApiWriteMixin, View):
    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        return JsonResponse({"ok": True})


class TestApiWriteMixin:
    def _make_request(
        self, rf: RequestFactory, *, authenticated: bool, scopes: list[str]
    ) -> HttpRequest:
        request = rf.get("/api/test/")
        request.is_api_authenticated = authenticated
        request.api_user_id = ADMIN_USER_ID if authenticated else None
        request.api_key_scopes = scopes
        return request

    def test_anonymous_request_returns_401(self, request_factory: RequestFactory) -> None:
        request = self._make_request(request_factory, authenticated=False, scopes=[])
        response = _ApiWriteEcho.as_view()(request)
        assert response.status_code == 401

    def test_read_only_key_returns_403(self, request_factory: RequestFactory) -> None:
        request = self._make_request(request_factory, authenticated=True, scopes=["read"])
        response = _ApiWriteEcho.as_view()(request)
        assert response.status_code == 403

    def test_write_scope_passes_through(self, request_factory: RequestFactory) -> None:
        request = self._make_request(request_factory, authenticated=True, scopes=["read", "write"])
        response = _ApiWriteEcho.as_view()(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}
