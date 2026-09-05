"""Tests for content groups — site-declared page labels.

Covers the whole path: normalisation at ingest, aggregation, the
``content_group`` filter (SQL builder and ORM fallback), exact per-group unique
visitors, and the Sections page's ``?by=group`` mode.

The aggregation and visitor tests run against the ORM fallback, since the suite
runs on SQLite; the raw-SQL branch is exercised by the same public functions on
PostgreSQL deployments.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from apps.analytics.services import get_groups_data
from apps.core.models import WebsiteEvent
from apps.tracker.services import (
    MAX_CONTENT_GROUP_LEN,
    MAX_CONTENT_GROUPS,
    content_groups_from,
)
from core.mantecato_core.filters import Filter, build_filter_sql
from core.mantecato_core.queries.groups import get_top_groups
from tests.conftest import WEBSITE_ID, make_admin_user

if TYPE_CHECKING:
    from django.test import Client

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
WINDOW = (NOW - timedelta(days=1), NOW + timedelta(days=1))


# ---------------------------------------------------------------------------
# Normalisation (pure function — no DB)
# ---------------------------------------------------------------------------


class TestContentGroupsFrom:
    def test_comma_string_is_split_and_normalised(self) -> None:
        assert content_groups_from({"groups": " Guides, Pricing "}) == ["guides", "pricing"]

    def test_list_is_accepted(self) -> None:
        assert content_groups_from({"groups": ["Blog", "news"]}) == ["blog", "news"]

    def test_duplicates_collapse_keeping_first_order(self) -> None:
        assert content_groups_from({"groups": ["b", "a", "B", "a"]}) == ["b", "a"]

    def test_capped_at_max_groups(self) -> None:
        payload = {"groups": [f"g{i}" for i in range(MAX_CONTENT_GROUPS + 4)]}
        assert len(content_groups_from(payload)) == MAX_CONTENT_GROUPS

    def test_label_truncated(self) -> None:
        groups = content_groups_from({"groups": ["x" * (MAX_CONTENT_GROUP_LEN + 50)]})
        assert len(groups[0]) == MAX_CONTENT_GROUP_LEN

    def test_umami_tag_becomes_a_group(self) -> None:
        assert content_groups_from({"tag": "Blog"}) == ["blog"]

    def test_tag_deduplicates_against_groups(self) -> None:
        assert content_groups_from({"groups": ["blog"], "tag": "Blog"}) == ["blog"]

    def test_missing_or_empty_is_none(self) -> None:
        assert content_groups_from({}) is None
        assert content_groups_from({"groups": ""}) is None
        assert content_groups_from({"groups": ",,"}) is None
        assert content_groups_from({"groups": [" ", ""]}) is None

    @pytest.mark.parametrize("value", [123, {"a": 1}, None, [1, 2]])
    def test_malformed_payload_is_ignored(self, value: object) -> None:
        assert content_groups_from({"groups": value}) is None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _event(groups: list[str] | None, path: str = "/a", visitor: str | None = None) -> None:
    event = WebsiteEvent.objects.create(
        website_id=WEBSITE_ID,
        url_path=path,
        event_type=1,
        content_groups=groups,
        visitor_key=visitor,
    )
    WebsiteEvent.objects.filter(pk=event.pk).update(created_at=NOW)


@pytest.mark.django_db
class TestGroupAggregation:
    def test_counts_views_and_distinct_pages(self) -> None:
        _event(["guides"], "/a")
        _event(["guides"], "/a")
        _event(["guides"], "/b")
        rows = get_top_groups(WEBSITE_ID, *WINDOW)
        assert rows == [{"group": "guides", "views": 3, "pages": 2}]

    def test_a_page_in_several_groups_counts_in_each(self) -> None:
        _event(["guides", "python", "beginner"], "/a")
        rows = {row["group"]: row["views"] for row in get_top_groups(WEBSITE_ID, *WINDOW)}
        assert rows == {"guides": 1, "python": 1, "beginner": 1}

    def test_unlabelled_pageviews_are_not_bucketed(self) -> None:
        _event(None, "/a")
        _event(["guides"], "/b")
        assert [row["group"] for row in get_top_groups(WEBSITE_ID, *WINDOW)] == ["guides"]

    def test_sorted_by_views_desc(self) -> None:
        _event(["small"])
        for _ in range(3):
            _event(["big"])
        assert [r["group"] for r in get_top_groups(WEBSITE_ID, *WINDOW)] == ["big", "small"]

    def test_limit_applies(self) -> None:
        for i in range(5):
            _event([f"g{i}"])
        assert len(get_top_groups(WEBSITE_ID, *WINDOW, limit=2)) == 2

    def test_malformed_stored_value_is_skipped(self) -> None:
        _event("not-a-list")  # type: ignore[arg-type]
        _event(["ok"])
        assert [r["group"] for r in get_top_groups(WEBSITE_ID, *WINDOW)] == ["ok"]


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestContentGroupFilterSQL:
    def test_eq_uses_key_existence(self) -> None:
        result = build_filter_sql([Filter("content_group", "eq", "guides")])
        assert "content_groups ?|" in result["where"]
        assert result["params"]["f0"] == ["guides"]

    def test_in_binds_every_label(self) -> None:
        result = build_filter_sql([Filter("content_group", "in", "a, b")])
        assert result["params"]["f0"] == ["a", "b"]

    def test_negated_keeps_unlabelled_rows(self) -> None:
        where = build_filter_sql([Filter("content_group", "neq", "x")])["where"]
        assert "IS NULL OR NOT" in where

    @pytest.mark.parametrize("operator", ["contains", "starts_with", "not_contains"])
    def test_substring_operators_are_dropped(self, operator: str) -> None:
        # A substring test over a list of labels has no meaning; it must not
        # silently degrade into "match everything".
        assert build_filter_sql([Filter("content_group", operator, "x")])["where"] == ""

    def test_combines_with_other_columns(self) -> None:
        where = build_filter_sql(
            [Filter("content_group", "eq", "g"), Filter("country", "eq", "IT")]
        )["where"]
        assert "content_groups ?|" in where and "country" in where


@pytest.mark.django_db
class TestContentGroupFilterORM:
    def test_eq_selects_only_matching_rows(self) -> None:
        _event(["guides"], "/a")
        _event(["pricing"], "/b")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "eq", "guides")]
        )
        assert [r["group"] for r in rows] == ["guides"]

    def test_in_matches_any_label(self) -> None:
        _event(["guides"], "/a")
        _event(["pricing"], "/b")
        _event(["other"], "/c")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "in", "guides,pricing")]
        )
        assert sorted(r["group"] for r in rows) == ["guides", "pricing"]

    def test_negated_keeps_unlabelled_rows(self) -> None:
        _event(["guides"], "/a")
        _event(None, "/b")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "neq", "guides")]
        )
        # The unlabelled pageview survives the filter but contributes no group.
        assert rows == []
        assert WebsiteEvent.objects.count() == 2


# ---------------------------------------------------------------------------
# Exact per-group unique visitors
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGroupVisitors:
    def test_same_visitor_on_two_pages_counts_once(self) -> None:
        _event(["guides"], "/a", visitor="v1")
        _event(["guides"], "/b", visitor="v1")
        _event(["guides"], "/c", visitor="v2")
        data = get_groups_data(WEBSITE_ID, _range())
        assert data["groups"][0]["visitors"] == 2

    def test_visitors_counted_per_group(self) -> None:
        _event(["guides", "python"], "/a", visitor="v1")
        _event(["python"], "/b", visitor="v2")
        rows = get_groups_data(WEBSITE_ID, _range())["groups"]
        by_group = {row["group"]: row["visitors"] for row in rows}
        assert by_group == {"python": 2, "guides": 1}


def _range():
    from core.mantecato_core.date_utils import DateRange

    return DateRange(*WINDOW)


# ---------------------------------------------------------------------------
# Sections page, group mode
# ---------------------------------------------------------------------------


class TestSectionsGroupMode:
    def _login(self, client: Client) -> None:
        """Authenticate without touching the DB, like the other view tests."""
        from django.contrib.auth.signals import user_logged_in

        user = make_admin_user()
        user.backend = "django.contrib.auth.backends.ModelBackend"
        with patch.object(user_logged_in, "send", return_value=[]):
            client.force_login(user)
        patcher = patch(
            "django.contrib.auth.middleware.AuthenticationMiddleware.process_request",
            side_effect=lambda request: setattr(request, "user", user),
        )
        patcher.start()
        self._patcher = patcher

    def teardown_method(self) -> None:
        if hasattr(self, "_patcher"):
            self._patcher.stop()

    @patch("apps.analytics.views.get_groups_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_by_group_renders_labels(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client
    ) -> None:
        self._login(client)
        mock_websites.return_value = [{"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"}]
        mock_data.return_value = {
            "groups": [{"group": "guides", "views": 42, "visitors": 30, "pages": 7, "pct": 60.0}]
        }
        content = client.get("/sections/?by=group").content.decode()
        assert "guides" in content
        assert "42" in content
        # Drilldown links filter the Pages view by label, not by URL prefix.
        assert "content_group%3Aeq%3Aguides" in content

    @patch("apps.analytics.views.get_sections_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_default_mode_still_groups_by_url(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client
    ) -> None:
        self._login(client)
        mock_websites.return_value = [{"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"}]
        mock_data.return_value = {
            "sections": [{"section": "/blog", "views": 10, "visitors": 8, "pages": 3, "pct": 50.0}]
        }
        content = client.get("/sections/").content.decode()
        assert "/blog" in content
        # urlencode leaves "/" alone (it is safe in a query value).
        assert "url_path%3Astarts_with%3A/blog" in content
