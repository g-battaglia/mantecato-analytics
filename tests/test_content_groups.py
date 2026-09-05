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
from core.mantecato_core.queries.filter_values import get_filter_values
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


def _event(
    groups: list[str] | None,
    path: str = "/a",
    visitor: str | None = None,
    **fields: object,
) -> None:
    event = WebsiteEvent.objects.create(
        website_id=WEBSITE_ID,
        url_path=path,
        event_type=1,
        content_groups=groups,
        visitor_key=visitor,
        **fields,
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

    def test_percentage_is_share_of_all_pageviews(self) -> None:
        _event(["guides", "python"], "/labelled")
        _event(None, "/unlabelled")

        rows = get_groups_data(WEBSITE_ID, _range())["groups"]
        assert {row["group"]: row["pct"] for row in rows} == {
            "guides": 50.0,
            "python": 50.0,
        }

    def test_overlapping_groups_can_each_be_one_hundred_percent(self) -> None:
        _event(["guides", "python"], "/labelled")

        rows = get_groups_data(WEBSITE_ID, _range())["groups"]
        assert {row["group"]: row["pct"] for row in rows} == {
            "guides": 100.0,
            "python": 100.0,
        }

    def test_percentage_denominator_uses_active_filters(self) -> None:
        _event(["guides"], "/it", country="IT")
        _event(None, "/it-unlabelled", country="IT")
        _event(["guides"], "/us", country="US")

        rows = get_groups_data(
            WEBSITE_ID,
            _range(),
            filters=[Filter("country", "eq", "IT")],
        )["groups"]
        assert rows[0]["pct"] == 50.0


class TestMalformedStoredValues:
    """`content_groups` is an unconstrained JSONField — anything can be in there.

    The tracker normalises what it writes, but a backfill script, a fixture or a
    direct DB write can store a scalar or a nested value. Neither may take the
    group queries down.
    """

    @pytest.mark.django_db
    def test_non_string_members_do_not_break_visitor_counting(self) -> None:
        # A dict/list member is unhashable: an unguarded `in` against the wanted
        # set raises TypeError instead of simply not matching.
        _event(["guides", {"nested": 1}, ["deep"], 42], "/a", visitor="v1")
        rows = get_groups_data(WEBSITE_ID, _range())["groups"]
        assert [row["group"] for row in rows] == ["guides"]
        assert rows[0]["visitors"] == 1

    @staticmethod
    def _generated_sql(module: str, call) -> str:
        """Run *call* with the PostgreSQL branch forced and return its SQL.

        SQLite cannot execute these queries, so the guards they rely on are
        asserted on the generated statement instead of by running it. Weaker
        than a PostgreSQL integration test, and deliberately so noted.
        """
        captured: dict[str, str] = {}

        def fake_raw_query(sql: str, params: dict) -> list:
            captured["sql"] = sql
            return []

        with (
            patch(f"{module}.should_use_orm_fallback", return_value=False),
            patch(f"{module}.raw_query", side_effect=fake_raw_query),
        ):
            call()
        return " ".join(captured["sql"].split())

    def test_postgres_expansion_is_guarded_inside_the_lateral(self) -> None:
        """A scalar row must not abort the whole aggregation on PostgreSQL.

        The expansion raises on a non-array, and a WHERE predicate is not
        ordered before the FROM clause that expands the value, so the guard has
        to sit inside the lateral.
        """
        sql = self._generated_sql(
            "core.mantecato_core.queries.groups",
            lambda: get_top_groups(WEBSITE_ID, *WINDOW),
        )
        assert "CASE WHEN jsonb_typeof(we.content_groups) = 'array'" in sql
        assert "ELSE '[]'::jsonb END" in sql
        # The bare expansion (unguarded) must not survive anywhere.
        assert "jsonb_array_elements( we.content_groups" not in sql

    @pytest.mark.parametrize(
        ("module", "call"),
        [
            (
                "core.mantecato_core.queries.groups",
                lambda: get_top_groups(WEBSITE_ID, *WINDOW),
            ),
            (
                "core.mantecato_core.queries.filter_values",
                lambda: get_filter_values(WEBSITE_ID, "content_group", *WINDOW),
            ),
        ],
        ids=["aggregation", "typeahead"],
    )
    def test_postgres_only_expands_string_members(self, module: str, call) -> None:
        """Both PostgreSQL paths must agree with SQLite on what counts as a label.

        `jsonb_array_elements_text()` stringifies every member, so `42` and
        `{"nested": 1}` would become groups of their own on PostgreSQL while the
        SQLite fallback and the visitor counter drop them — the same row would
        report differently per backend.
        """
        sql = self._generated_sql(module, call)
        assert "CROSS JOIN LATERAL jsonb_array_elements(" in sql
        # The text-returning variant would stringify non-string members.
        assert "CROSS JOIN LATERAL jsonb_array_elements_text(" not in sql
        assert "jsonb_typeof(grp.elem) = 'string'" in sql


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

    @pytest.mark.parametrize("operator", ["contains", "not_contains"])
    def test_substring_operators_are_dropped(self, operator: str) -> None:
        # A substring test over a list of labels has no meaning — "guides"
        # matching inside "sub-guides-x" answers no real question. It must not
        # silently degrade into "match everything".
        # (Prefix matching does have a meaning: see TestNamespacedLabels.)
        assert build_filter_sql([Filter("content_group", operator, "x")])["where"] == ""

    def test_combines_with_other_columns(self) -> None:
        where = build_filter_sql(
            [Filter("content_group", "eq", "g"), Filter("country", "eq", "IT")]
        )["where"]
        assert "content_groups ?|" in where and "country" in where


class TestNamespacedLabels:
    """Prefixed labels ("cat:", "tag:") are how one list carries several taxonomies.

    Without them a category and a tag that share a name collapse into one row —
    "aspects" is both on this site.
    """

    def test_prefix_survives_normalisation(self) -> None:
        assert content_groups_from({"groups": ["Cat:Birth-Chart", "TAG:Aspects"]}) == [
            "cat:birth-chart",
            "tag:aspects",
        ]

    def test_same_name_in_two_taxonomies_stays_distinct(self) -> None:
        groups = content_groups_from({"groups": ["cat:aspects", "tag:aspects"]})
        assert groups == ["cat:aspects", "tag:aspects"]

    def test_twelve_labels_fit(self) -> None:
        # Three category levels + a family + eight tags is the site's shape.
        payload = {"groups": ["cat:a", "cat:b", "cat:c", "fam:d"] + [f"tag:{i}" for i in range(8)]}
        assert len(content_groups_from(payload)) == 12

    def test_prefix_filter_is_answerable(self) -> None:
        where = build_filter_sql([Filter("content_group", "starts_with", "tag:")])["where"]
        assert "EXISTS" in where and "ILIKE" in where

    def test_negated_prefix_filter_is_answerable(self) -> None:
        where = build_filter_sql([Filter("content_group", "not_starts_with", "tag:")])["where"]
        assert where.strip().startswith("AND NOT EXISTS")


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

    def test_prefix_selects_one_taxonomy(self) -> None:
        _event(["cat:aspects", "tag:aspects", "tag:squares"], "/a")
        _event(["cat:transits"], "/b")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "starts_with", "tag:")]
        )
        # The row matched on its tags, so all of its labels are aggregated —
        # the filter picks rows, not individual labels.
        assert sorted(r["group"] for r in rows) == ["cat:aspects", "tag:aspects", "tag:squares"]

    def test_prefix_does_not_match_mid_label(self) -> None:
        _event(["tag:aspects"], "/a")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "starts_with", "aspects")]
        )
        assert rows == []

    def test_nested_value_does_not_answer_the_filter(self) -> None:
        """A label buried in a nested object is not a label.

        The row carries a second, real label, which is what makes this
        observable: substring-matching the serialised document would let the row
        through the `guides` filter and report its `other` label, while the
        aggregation — which counts only top-level string members — never sees
        `guides` on it at all. Both backends must agree that the row does not
        answer the filter.
        """
        _event([{"nested": "guides"}, "other"], "/a")  # type: ignore[list-item]
        _event(["guides"], "/b")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "eq", "guides")]
        )
        assert [(r["group"], r["views"]) for r in rows] == [("guides", 1)]

    def test_prefix_ignores_nested_values(self) -> None:
        _event([{"nested": "tag:x"}, "other"], "/a")  # type: ignore[list-item]
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "starts_with", "tag:")]
        )
        assert rows == []

    def test_negated_keeps_unlabelled_rows(self) -> None:
        _event(["guides"], "/a")
        _event(None, "/b")
        rows = get_top_groups(
            WEBSITE_ID, *WINDOW, filters=[Filter("content_group", "neq", "guides")]
        )
        # The unlabelled pageview survives the filter but contributes no group.
        assert rows == []
        assert WebsiteEvent.objects.count() == 2

    def test_typeahead_extracts_distinct_group_labels(self) -> None:
        _event(["guides", "python"])
        _event(["guides", "pricing"])
        _event(None)

        assert get_filter_values(WEBSITE_ID, "content_group", *WINDOW) == [
            "guides",
            "pricing",
            "python",
        ]
        assert get_filter_values(WEBSITE_ID, "content_group", *WINDOW, search="pri") == ["pricing"]

    @patch("core.mantecato_core.queries.filter_values.should_use_orm_fallback", return_value=False)
    @patch("core.mantecato_core.queries.filter_values.raw_query")
    def test_typeahead_uses_json_array_expansion_on_postgres(
        self, mock_query: MagicMock, _mock_fallback: MagicMock
    ) -> None:
        mock_query.return_value = [{"value": "guides"}]

        assert get_filter_values(WEBSITE_ID, "content_group", *WINDOW, search="guide") == ["guides"]
        sql, params = mock_query.call_args.args
        assert "jsonb_array_elements(" in sql
        assert "grp.elem #>> '{}' ILIKE" in sql
        assert params["search"] == "%guide%"


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
        assert 'value="content_group"' in content

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
